#!/usr/bin/env python3
"""Exercise actual FK/teleop/IK/filter/coordinator with synthetic fixtures only."""
import os
import signal
import subprocess
import tempfile
import threading
import time

BASE = '/pi05/teleop_replay'
MASTER = 'http://localhost:11333'


def main():
    if os.environ.get('ROS_MASTER_URI') != MASTER:
        raise RuntimeError('Replay requires isolated localhost Master on port 11333')
    import rospy
    import rosnode
    import rosgraph
    from geometry_msgs.msg import PoseStamped
    from sensor_msgs.msg import JointState
    from data_msgs.msg import LocalizationStatus
    from diagnostic_msgs.msg import DiagnosticStatus
    from piper_msgs.msg import PiperStatusMsg
    from piper_msgs.srv import Enable, EnableResponse
    from std_srvs.srv import Trigger, TriggerResponse
    rospy.init_node('teleop_synthetic_fixture', disable_signals=True)
    before=set(rosnode.get_node_names())
    if before != {'/rosout', '/teleop_synthetic_fixture'}:
        raise RuntimeError('Replay Master contains other nodes')
    lock=threading.RLock()
    outputs={s:[] for s in ('left','right')}
    targets={s:[] for s in outputs}
    controls={s:[] for s in outputs}
    fk={}
    diag={}
    actions=[]
    publishers={}
    subscribers=[]
    services=[]
    condition={'left_x':0.,'right_x':0.,'left_accurate':True,'right_accurate':True}
    done=threading.Event()
    def record(table,side,value):
        with lock: table[side].append(value)
    def status(msg):
        with lock: diag.update({v.key:v.value for v in msg.values})
    def enable(req,side):
        with lock: actions.append(('enable',side,req.enable_request))
        return EnableResponse(True)
    def stop(req,side):
        with lock: actions.append(('stop',side))
        return TriggerResponse(True,'synthetic stop accepted')
    for side in outputs:
        ns=BASE+'/'+side+'_arm'
        publishers[side]=(
            rospy.Publisher('/pi05/pika_input/'+side+'/pose',PoseStamped,queue_size=1),
            rospy.Publisher('/pi05/pika_input/'+side+'/localization_status',LocalizationStatus,queue_size=1),
            rospy.Publisher(ns+'/feedback',JointState,queue_size=1),
            rospy.Publisher(ns+'/arm_status',PiperStatusMsg,queue_size=1),
        )
        subscribers.extend([
            rospy.Subscriber(ns+'/filtered_target',JointState,lambda m,s=side:record(outputs,s,tuple(m.position))),
            rospy.Subscriber(ns+'/raw_target',JointState,lambda m,s=side:record(targets,s,tuple(m.position))),
            rospy.Subscriber(ns+'/ik/ctrl_end_pose',PoseStamped,lambda m,s=side:record(controls,s,m.pose.position.x)),
            rospy.Subscriber(ns+'/fk/urdf_end_pose_orient',PoseStamped,lambda m,s=side:fk.update({s:m})),
        ])
        services.extend([
            rospy.Service(BASE+'/mock/'+side+'/enable',Enable,lambda r,s=side:enable(r,s)),
            rospy.Service(BASE+'/mock/'+side+'/stop',Trigger,lambda r,s=side:stop(r,s)),
        ])
    subscribers.append(rospy.Subscriber(BASE+'/dual_arm/status',DiagnosticStatus,status))
    def feed():
        while not done.is_set() and not rospy.is_shutdown():
            with lock: state=dict(condition)
            for side,(posepub,locpub,feedbackpub,driverpub) in publishers.items():
                pose=PoseStamped();pose.header.stamp=rospy.Time.now();pose.header.frame_id='synthetic_map'
                pose.pose.position.x=state[side+'_x'];pose.pose.orientation.w=1.
                posepub.publish(pose);locpub.publish(LocalizationStatus(accurate=state[side+'_accurate']))
                feedback=JointState();feedback.header.stamp=rospy.Time.now()
                feedback.name=['joint'+str(i) for i in range(1,8)]
                feedback.position=[0.,.8,-.8,0.,.1,0.,.02]
                feedbackpub.publish(feedback);driverpub.publish(PiperStatusMsg())
            done.wait(.04)
    thread=threading.Thread(target=feed,daemon=True)
    def wait_for(predicate,label,timeout=15):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if predicate():return
            if child.poll() is not None:raise RuntimeError('Pipeline launch exited: '+label)
            time.sleep(.05)
        raise RuntimeError('Replay timed out: '+label+'; coordinator='+str(diag))
    def trigger(side):
        name=BASE+'/'+side+'_arm/teleop_trigger'
        rospy.wait_for_service(name,timeout=15)
        rospy.ServiceProxy(name,Trigger)()
        # Upstream Trigger response has no success acknowledgement; observe data.
    def counts():
        with lock:return {s:len(v) for s,v in outputs.items()}
    child=None
    # Diagnostics contain synthetic data only and are deleted on close.
    with tempfile.TemporaryFile(mode='w+b') as sink:
        child=subprocess.Popen(['roslaunch','pi05_teleop_replay','teleop_replay.launch','start:=true'],stdout=sink,stderr=sink,start_new_session=True)
        try:
            thread.start()
            wait_for(lambda:len(fk)==2,'both real FK nodes')
            for side in outputs:trigger(side)
            wait_for(lambda:all(len(v)>2 for v in targets.values()),'both real IK outputs')
            assert counts()=={'left':0,'right':0}, 'unauthorized target reached output'
            assert not actions, 'hardware action before enable'
            expected={'/rosout','/teleop_synthetic_fixture',BASE+'/coordinator'}
            expected.update(BASE+'/'+s+'_arm/'+r for s in outputs for r in ('fk','ik','teleop','filter'))
            assert set(rosnode.get_node_names())==expected, 'unexpected pipeline node'
            graph=rosgraph.Master('/teleop_synthetic_fixture').getSystemState()
            for topic,nodes in graph[0]+graph[1]+graph[2]:
                logger_services={n+'/'+s for n in expected
                                 for s in ('get_loggers','set_logger_level')}
                if topic in ('/rosout','/rosout_agg') or topic in logger_services:continue
                assert topic.startswith((BASE+'/', '/pi05/pika_input/')), 'uncontained endpoint: '+topic
                assert 'joint_ctrl_raw' not in topic, 'driver command connection'
            for side in outputs:
                raw=dict(graph[0])[BASE+'/'+side+'_arm/raw_target']
                assert set(raw)=={BASE+'/'+side+'_arm/ik',BASE+'/'+side+'_arm/teleop'}, 'unreviewed raw publisher'
            enable_name=BASE+'/dual_arm/enable_srv'
            rospy.wait_for_service(enable_name,timeout=10)
            enable_proxy=rospy.ServiceProxy(enable_name,Enable)
            wait_for(lambda:diag.get('state')=='READY','coordinator enable preconditions')
            assert enable_proxy(True).enable_response, 'synthetic dual enable rejected'
            wait_for(lambda:all(v for v in outputs.values()),'authorized filtered outputs')
            left_start=len(controls['left']);right_start=len(controls['right'])
            with lock: condition['left_x']=.001
            wait_for(lambda:len(controls['left'])>left_start+5 and len(controls['right'])>right_start+5,'left input mapping')
            assert max(controls['left'][left_start:])-min(controls['left'][:left_start])>.0005, 'left pose did not reach left IK'
            assert max(controls['right'][right_start:])-min(controls['right'][right_start:])<1e-8, 'left input crossed to right'
            left_start=len(controls['left']);right_start=len(controls['right'])
            right_baseline=controls['right'][-1]
            with lock: condition['right_x']=-.001
            wait_for(lambda:len(controls['left'])>left_start+5 and len(controls['right'])>right_start+5,'right input mapping')
            assert right_baseline-min(controls['right'][right_start:])>.0005, 'right pose did not reach right IK'
            assert max(controls['left'][left_start:])-min(controls['left'][left_start:])<1e-8, 'right input crossed to left'
            for side in outputs:trigger(side)
            time.sleep(.3);a=counts();time.sleep(.3)
            assert counts()==a, 'output after both sessions quit'
            for side in outputs:trigger(side)
            wait_for(lambda:all(counts()[s]>a[s] for s in outputs),'fresh sessions resumed')
            with lock:condition['left_accurate']=False
            wait_for(lambda:any(x==('stop','left') for x in actions) and any(x==('stop','right') for x in actions),'dual stop after left localization fault')
            time.sleep(.3);a=counts();time.sleep(.3)
            assert counts()==a, 'either side continued after localization fault'
            with lock:condition['left_accurate']=True
            time.sleep(.5)
            assert counts()==a, 'fault restarted automatically'
            assert any(x==('enable','left',True) for x in actions) and any(x==('enable','right',True) for x in actions)
            print('PASS: real dual FK -> relative teleop -> real IK -> filters -> coordinator; isolated endpoints, unauthorized rejection, left mapping, session quit/restart, dual stop on left localization loss, fault latch. Synthetic fixtures and services only.')
        except Exception:
            sink.flush();sink.seek(0)
            print(sink.read().decode(errors='replace')[-8000:])
            raise
        finally:
            done.set();thread.join(timeout=2)
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGINT)
                try:child.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()


if __name__=='__main__':
    main()
