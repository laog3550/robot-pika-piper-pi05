#!/usr/bin/env python3
"""Isolated ROS supervisor replay, synthetic joints and fake device services."""
import os
import signal
import socket
import subprocess
import tempfile
import threading
import time


def main():
    if os.environ.get('ROS_MASTER_URI')!='http://localhost:11334':
        raise RuntimeError('requires isolated localhost Master 11334')
    probe=socket.socket()
    probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    try:
        probe.bind(('127.0.0.1',11334))
    finally:
        probe.close()
    core=child=None
    closed=threading.Event()
    with tempfile.TemporaryFile() as sink:
        try:
            core=subprocess.Popen(['roscore','-p','11334'],stdout=sink,stderr=sink,start_new_session=True)
            import rosgraph
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                try:
                    rosgraph.Master('/left_replay_boot').getPid();break
                except Exception:time.sleep(.1)
            else:raise RuntimeError('isolated Master did not start')
            import rospy
            from sensor_msgs.msg import JointState
            from data_msgs.msg import LocalizationStatus,ArmControlStatus
            from std_msgs.msg import Bool
            from std_srvs.srv import Trigger,TriggerResponse
            from piper_msgs.srv import Enable,EnableResponse
            rospy.init_node('left_teleop_synthetic_fixture',disable_signals=True)
            actions=[];outputs=[];authorizations=[]
            state={'valid':True,'target':0.0}
            services=[rospy.Service('/left_arm/enable_srv_raw',Enable,lambda req:(actions.append('enable') or EnableResponse(True))),
                      rospy.Service('/left_arm/stop_srv_raw',Trigger,lambda req:(actions.append('stop') or TriggerResponse(True,'fake stop')))]
            pubs={
                'feedback':rospy.Publisher('/joint_states_single_l',JointState,queue_size=1),
                'localization':rospy.Publisher('/pi05/pika_input/left/localization_status',LocalizationStatus,queue_size=1),
                'ik':rospy.Publisher('/arm_control_status_l',ArmControlStatus,queue_size=1),
                'target':rospy.Publisher('/left_arm/teleop/filtered_target',JointState,queue_size=1)}
            subscribers=[rospy.Subscriber('/left_arm/joint_ctrl_raw',JointState,lambda m:outputs.append(m)),
                         rospy.Subscriber('/left_arm/control_authorized',Bool,lambda m:authorizations.append(m.data))]
            def feed():
                while not closed.wait(.02):
                    feedback=JointState();feedback.name=['joint'+str(i) for i in range(1,8)];feedback.position=[0.0]*6+[.04]
                    pubs['feedback'].publish(feedback)
                    localization=LocalizationStatus();localization.accurate=state['valid'];pubs['localization'].publish(localization)
                    ik=ArmControlStatus();ik.over_limit=False;pubs['ik'].publish(ik)
                    target=JointState();target.name=feedback.name;target.position=[state['target']]+[0.0]*6
                    pubs['target'].publish(target)
            threading.Thread(target=feed,daemon=True).start()
            child=subprocess.Popen(['rosrun','pi05_left_teleop','supervisor.py','_hardware_actions_enabled:=true'],stdout=sink,stderr=sink,start_new_session=True)
            def wait(predicate,label,seconds=8):
                end=time.monotonic()+seconds
                while time.monotonic()<end:
                    if predicate():return
                    if child.poll() is not None:raise RuntimeError('supervisor exited: '+label)
                    time.sleep(.02)
                raise RuntimeError('timeout: '+label)
            rospy.wait_for_service('/left_arm/teleop/enable',timeout=10)
            wait(lambda:all(p.get_num_connections()>0 for p in pubs.values()),'fixture connections')
            time.sleep(.3)
            assert not outputs and not actions and not any(authorizations),'activity before explicit enable'
            import json
            snapshot=json.loads(rospy.ServiceProxy('/left_arm/teleop/status',Trigger)().message)
            assert snapshot['phase']=='DISARMED' and not snapshot['blockers'] and not snapshot['enable_attempted'],'status before enable'
            result=[]
            def enable():result.append(rospy.ServiceProxy('/left_arm/teleop/enable',Trigger)())
            thread=threading.Thread(target=enable);thread.start()
            wait(lambda:'enable' in actions,'fake enable')
            time.sleep(.5)
            assert not outputs,'target forwarded during settling'
            thread.join(timeout=5)
            assert result and result[0].success,'settling failed'
            wait(lambda:len(outputs)>3,'authorized targets')
            assert all(m.velocity[6]==5 and m.position[6]==.04 for m in outputs),'speed/gripper conditioning'
            state['target']=.005
            wait(lambda:any(m.position[0]==.005 for m in outputs),'small target')
            state['valid']=False
            wait(lambda:'stop' in actions,'fake stop on localization loss')
            time.sleep(.2);before=len(outputs)
            state['valid']=True;time.sleep(.3)
            assert len(outputs)==before and authorizations[-1] is False,'fault auto recovered'
            result=rospy.ServiceProxy('/left_arm/teleop/enable',Trigger)()
            assert not result.success and actions.count('enable')==1,'fault re-enabled'
            print('PASS: isolated supervisor; explicit fake enable, no output during settling, speed/gripper conditioning, localization loss stop and fault latch; no driver or SDK.')
        except Exception:
            sink.flush();sink.seek(0)
            print(sink.read().decode('utf-8',errors='replace')[-2500:])
            raise
        finally:
            closed.set()
            for process in (child,core):
                if process is not None and process.poll() is None:
                    os.killpg(process.pid,signal.SIGINT)
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGKILL);process.wait()


if __name__=='__main__':main()
