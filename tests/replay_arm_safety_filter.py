#!/usr/bin/env python3
"""Synthetic ROS filter replay; requires isolated localhost Master on port 11332.

No Piper driver, CAN or device source is started. Synthetic authorization replaces
the coordinator in this test; dual-arm behavior is covered separately.
"""
import os
import subprocess
import time
import threading
import signal

if os.environ.get('ROS_MASTER_URI') != 'http://localhost:11332':
    raise RuntimeError('Replay requires isolated localhost Master on port 11332')
import rospy
import rosnode
import rosgraph
from sensor_msgs.msg import JointState
from data_msgs.msg import LocalizationStatus, TeleopStatus, ArmControlStatus
from std_msgs.msg import Bool

rospy.init_node('synthetic_filter_replay', disable_signals=True)
lock = threading.Lock()
seen = {'l': [], 'r': []}
pubs = {}
children = []
sink = open(os.devnull, 'wb')
def receive(msg, side):
    with lock:
        seen[side].append(tuple(msg.position))
subs = [rospy.Subscriber('/joint_states_gripper_'+s, JointState, receive, callback_args=s) for s in seen]
for s in seen:
    pubs[s] = {
        'feedback': rospy.Publisher('/joint_states_single_'+s, JointState, queue_size=1),
        'loc': rospy.Publisher('/pika_localization_status_'+s, LocalizationStatus, queue_size=1),
        'ik': rospy.Publisher('/arm_control_status_'+s, ArmControlStatus, queue_size=1),
        'session': rospy.Publisher('/teleop_status_'+s, TeleopStatus, queue_size=1),
        'auth': rospy.Publisher('/'+{'l':'left','r':'right'}[s]+'_arm/control_authorized', Bool, queue_size=1),
        'command': rospy.Publisher('/joint_states_gripper_raw_'+s, JointState, queue_size=1),
    }
def joint(s, command=False):
    msg=JointState()
    msg.name=['joint'+str(i) for i in range(1,8)]
    msg.position=[0.1 if s=='l' else -0.1]*6+[0.02]
    if command: msg.position[0]+=.02 if s=='l' else -.02
    return msg
def pump(duration, auth=False, active=False, bad_left=False, commands=True):
    end=time.monotonic()+duration
    while time.monotonic()<end:
        for s,p in pubs.items():
            p['feedback'].publish(joint(s))
            p['loc'].publish(LocalizationStatus(accurate=not (s=='l' and bad_left)))
            p['ik'].publish(ArmControlStatus(over_limit=False))
        time.sleep(.01)
        for s,p in pubs.items(): p['auth'].publish(Bool(data=auth))
        time.sleep(.01)
        for s,p in pubs.items():
            p['session'].publish(TeleopStatus(fail=False, quit=not active))
            if commands:p['command'].publish(joint(s, True))
        time.sleep(.02)
def counts():
    with lock:return {s:len(v) for s,v in seen.items()}
try:
    for side in ('left','right'):
        children.append(subprocess.Popen(['roslaunch','pi05_control','s10_arm_safety_filter.launch',
            'side:='+side,'start_filter:=true','connect_driver:=false'], stdout=sink,stderr=sink,start_new_session=True))
    end=time.monotonic()+10
    while not all(p.get_num_connections() for group in pubs.values() for p in group.values()):
        if time.monotonic()>end or any(c.poll() is not None for c in children):raise RuntimeError('filter startup failed')
        time.sleep(.1)
    nodes=set(rosnode.get_node_names())
    assert nodes=={'/rosout','/synthetic_filter_replay','/left_arm/safety_filter','/right_arm/safety_filter'}, nodes
    pubs_state, subs_state, services=rosgraph.Master('/synthetic_filter_replay').getSystemState()
    assert not any('joint_ctrl_raw' in t for t,n in pubs_state+subs_state)
    pump(.4)
    assert counts()=={'l':0,'r':0}, 'unauthorized output'
    pump(.3,auth=True,active=False,commands=False)
    assert counts()=={'l':0,'r':0}, 'output without session'
    pump(.5,auth=True,active=True)
    with lock:
        assert seen['l'] and seen['r'], 'missing authorized output'
        assert all(.1 < p[0] <= .12 for p in seen['l']), 'left mapping'
        assert all(-.12 <= p[0] < -.1 for p in seen['r']), 'right mapping'
    pump(.2,auth=True,active=False)
    a=counts();pump(.2,auth=True,active=False)
    assert counts()==a, 'output after session quit'
    pump(.3,auth=True,active=True)
    pump(.2,auth=True,active=True,bad_left=True)
    a=counts();pump(.3,auth=True,active=True,bad_left=True)
    b=counts();assert b['l']==a['l'] and b['r']>a['r'], 'side fault isolation'
    pump(.2,auth=True,active=True,bad_left=False)
    assert counts()['l']==a['l'], 'latched fault restarted automatically'
    print('PASS: ROS filters: no driver graph, unauthorized/session gates, distinct sides, quit, localization fault, fault latch. Synthetic authorization only; coordinator not in this ROS replay.')
finally:
    for child in children:
        if child.poll() is None:
            os.killpg(child.pid,signal.SIGINT)
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
    sink.close()
