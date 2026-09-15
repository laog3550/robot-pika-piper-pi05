#!/usr/bin/env python3
"""Explicit left enable, two-second settling, wall-clock watchdog and envelope."""
import threading
import time
import os
import sys
import json
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import rospy
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool
from std_srvs.srv import Trigger, TriggerResponse
from piper_msgs.srv import Enable
from data_msgs.msg import LocalizationStatus, ArmControlStatus
from diagnostic_msgs.msg import DiagnosticStatus
from safety_gate import SafetyGate


class Supervisor:
    def __init__(self):
        self.lock = threading.RLock()
        self.hardware_actions_enabled = rospy.get_param('~hardware_actions_enabled',False) is True
        self.gate = SafetyGate()
        self.enable_attempted = False
        self.stop_started = False
        self.closed = threading.Event()
        self.authorization = rospy.Publisher('/left_arm/control_authorized',Bool,queue_size=1)
        self.output = rospy.Publisher('/left_arm/joint_ctrl_raw',JointState,queue_size=1)
        rospy.Subscriber('/joint_states_single_l',JointState,self.feedback,queue_size=1)
        rospy.Subscriber('/pi05/pika_input/left/localization_status',LocalizationStatus,self.localization,queue_size=1)
        rospy.Subscriber('/arm_control_status_l',ArmControlStatus,self.ik,queue_size=1)
        rospy.Subscriber('/left_arm/safety_filter_status',DiagnosticStatus,self.filter_status,queue_size=1)
        rospy.Subscriber('/left_arm/teleop/filtered_target',JointState,self.target,queue_size=1)
        rospy.Service('/left_arm/teleop/enable',Trigger,self.enable)
        rospy.Service('/left_arm/teleop/stop',Trigger,self.stop)
        rospy.Service('/left_arm/teleop/status',Trigger,self.status)
        rospy.on_shutdown(self.shutdown)
        threading.Thread(target=self.watchdog,daemon=True).start()

    def feedback(self,m):
        with self.lock:
            self.gate.observe_feedback(m.position,time.monotonic())

    def localization(self,m):
        with self.lock:
            self.gate.localization_ok = bool(m.accurate)
            self.gate.localization_time = time.monotonic()

    def ik(self,m):
        with self.lock:
            self.gate.ik_ok = not m.over_limit
            self.gate.ik_time = time.monotonic()

    def filter_status(self,m):
        with self.lock:
            if self.gate.phase in ('ENABLING','SETTLING','READY') and m.level==DiagnosticStatus.ERROR:
                self.gate.fail('safety filter fault')

    def target(self,m):
        with self.lock:
            # Pika input-only has no gripper input. Keep the measured opening.
            positions = list(m.position)
            if len(positions)==7 and self.gate.reference is not None:
                positions[6] = self.gate.reference[6]
            if not self.gate.accept_target(positions,time.monotonic()):
                return
            out = JointState()
            out.header.stamp = rospy.Time.now()
            out.name = list(m.name)
            out.position = positions
            out.velocity = [0.0]*6+[40.0]
            self.output.publish(out)

    def enable(self,_request):
        if not self.hardware_actions_enabled:
            return TriggerResponse(False,'hardware actions disabled')
        with self.lock:
            if not self.gate.begin(time.monotonic()):
                reasons='; '.join(self.gate.blockers(time.monotonic()))
                return TriggerResponse(False,reasons or 'enable preconditions changed; query status')
            self.enable_attempted = True
        try:
            rospy.wait_for_service('/left_arm/enable_srv_raw',timeout=2)
            response = rospy.ServiceProxy('/left_arm/enable_srv_raw',Enable)(True)
            with self.lock:
                if not response.enable_response:
                    self.gate.fail('driver enable failed')
                elif not self.gate.enabled(time.monotonic()):
                    self.gate.fail('enable interrupted by safety fault')
            until = time.monotonic()+3
            while time.monotonic()<until and not self.closed.wait(.05):
                with self.lock:
                    if self.gate.phase=='READY':
                        return TriggerResponse(True,'enabled and settled; preview session is now authorized')
                    if self.gate.phase=='FAULT':
                        break
        except Exception:
            with self.lock:
                self.gate.fail('enable service unavailable')
        self.request_stop()
        return TriggerResponse(False,'enable/settling failed; software stop requested; arm may remain enabled')

    def status(self,_request):
        with self.lock:
            snapshot={'phase':self.gate.phase,'reason':self.gate.reason,
                      'enable_attempted':self.enable_attempted,
                      'blockers':self.gate.blockers(time.monotonic())}
        return TriggerResponse(True,json.dumps(snapshot))

    def request_stop(self):
        with self.lock:
            self.authorization.publish(False)
            if self.stop_started or not self.enable_attempted:
                return
            self.stop_started = True
        def call():
            try:
                rospy.wait_for_service('/left_arm/stop_srv_raw',timeout=1)
                response = rospy.ServiceProxy('/left_arm/stop_srv_raw',Trigger)()
                if not response.success:
                    rospy.logerr('Left software stop failed; use hardware emergency stop if needed')
            except Exception:
                rospy.logerr('Left software stop unavailable; use hardware emergency stop if needed')
        threading.Thread(target=call,daemon=True).start()

    def stop(self,_request):
        with self.lock:
            self.gate.fail('operator stop')
        self.request_stop()
        return TriggerResponse(True,'authorization revoked; software stop requested; no automatic disable')

    def watchdog(self):
        while not self.closed.wait(.05):
            with self.lock:
                ready = self.gate.tick(time.monotonic())
                fault = self.gate.phase=='FAULT'
                self.authorization.publish(ready)
            if fault:
                self.request_stop()

    def shutdown(self):
        self.closed.set()
        with self.lock:
            self.gate.fail('shutdown')
        self.request_stop()


if __name__=='__main__':
    rospy.init_node('left_teleop_supervisor')
    Supervisor()
    rospy.spin()
