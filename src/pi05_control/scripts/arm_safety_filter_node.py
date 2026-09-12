#!/usr/bin/env python3
"""ROS bridge for the side-parameterized PI05 arm safety filter."""

import threading

import rospy
from data_msgs.msg import ArmControlStatus, LocalizationStatus, TeleopStatus
from diagnostic_msgs.msg import DiagnosticStatus, KeyValue
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool
from std_srvs.srv import Trigger, TriggerResponse

from pi05_control.safety_filter import ArmSafetyFilter, FilterConfig


class ArmSafetyFilterNode(object):
    def __init__(self):
        side = rospy.get_param("~side")
        if side not in ("left", "right"):
            raise ValueError("~side must be 'left' or 'right'")
        if bool(rospy.get_param("~double_gripper_return", False)):
            raise ValueError("automatic return is not implemented or approved")

        self.side = side
        self.short_side = {"left": "l", "right": "r"}[side]
        self.lock = threading.RLock()
        self.filter = ArmSafetyFilter(side, FilterConfig(
            arm_alpha=rospy.get_param("~arm_alpha", 0.35),
            arm_deadband_rad=rospy.get_param("~arm_deadband_rad", 0.002),
            max_arm_step_rad=rospy.get_param("~max_arm_step_rad", 0.012),
            gripper_alpha=rospy.get_param("~gripper_alpha", 0.25),
            gripper_deadband_m=rospy.get_param("~gripper_deadband_m", 0.0015),
            max_gripper_step_m=rospy.get_param("~max_gripper_step_m", 0.0006),
            speed_percent=rospy.get_param("~speed_percent", 15.0),
            command_timeout_s=rospy.get_param("~command_timeout_s", 0.35),
            feedback_timeout_s=rospy.get_param("~feedback_timeout_s", 0.35),
            localization_timeout_s=rospy.get_param("~localization_timeout_s", 0.35),
        ))

        suffix = self.short_side
        arm_ns = "/{}_arm".format(side)
        self.command_pub = rospy.Publisher(
            "/joint_states_gripper_{}".format(suffix), JointState, queue_size=1)
        self.status_pub = rospy.Publisher(
            arm_ns + "/safety_filter_status", DiagnosticStatus,
            queue_size=1, latch=True)

        rospy.Subscriber(
            "/joint_states_gripper_raw_{}".format(suffix), JointState,
            self.command_callback, queue_size=1, tcp_nodelay=True)
        rospy.Subscriber(
            "/joint_states_single_{}".format(suffix), JointState,
            self.feedback_callback, queue_size=1, tcp_nodelay=True)
        rospy.Subscriber(
            "/pika_localization_status_{}".format(suffix), LocalizationStatus,
            self.localization_callback, queue_size=1, tcp_nodelay=True)
        rospy.Subscriber(
            "/teleop_status_{}".format(suffix), TeleopStatus,
            self.teleop_callback, queue_size=1, tcp_nodelay=True)
        rospy.Subscriber(
            "/arm_control_status_{}".format(suffix), ArmControlStatus,
            self.arm_status_callback, queue_size=1, tcp_nodelay=True)
        rospy.Subscriber(
            arm_ns + "/control_authorized", Bool,
            self.authorization_callback, queue_size=1, tcp_nodelay=True)
        rospy.Service(arm_ns + "/reset_filter_fault", Trigger, self.reset_fault_callback)
        self.watchdog_timer = rospy.Timer(rospy.Duration(0.05), self.watchdog_callback)
        self.publish_status()

    @staticmethod
    def now():
        return rospy.Time.now().to_sec()

    def feedback_callback(self, message):
        with self.lock:
            valid = self.filter.update_feedback(message.position, message.name, self.now())
            self.publish_status()
        if not valid:
            rospy.logerr_throttle(2.0, "%s safety filter rejected invalid feedback", self.side)

    def localization_callback(self, message):
        with self.lock:
            valid = self.filter.update_localization(message.accurate, self.now())
            self.publish_status()
        if not valid:
            rospy.logerr_throttle(2.0, "%s localization is invalid", self.side)

    def teleop_callback(self, message):
        with self.lock:
            accepted = self.filter.update_teleop_status(message.fail, message.quit, self.now())
            self.publish_status()
        if not accepted and not message.quit:
            rospy.logwarn_throttle(2.0, "%s teleoperation session was not accepted", self.side)

    def arm_status_callback(self, message):
        with self.lock:
            valid = self.filter.update_arm_status(message.over_limit, self.now())
            self.publish_status()
        if not valid:
            rospy.logerr_throttle(2.0, "%s IK limit status blocked commands", self.side)

    def authorization_callback(self, message):
        with self.lock:
            accepted = self.filter.set_authorized(message.data, self.now())
            self.publish_status()
        if message.data and not accepted:
            rospy.logerr("%s authorization rejected while a fault is latched", self.side)

    def command_callback(self, message):
        with self.lock:
            output = self.filter.command(message.position, message.name, self.now())
            self.publish_status()
        if output is None:
            return
        conditioned = JointState()
        conditioned.header.stamp = rospy.Time.now()
        conditioned.header.frame_id = message.header.frame_id
        conditioned.name = output.names
        conditioned.position = output.positions
        # The approved Piper adapter consumes velocity[6] as a global percentage.
        conditioned.velocity = [0.0] * 6 + [output.speed_percent]
        self.command_pub.publish(conditioned)

    def watchdog_callback(self, _event):
        with self.lock:
            previously_faulted = bool(self.filter.fault_reason)
            self.filter.watchdog(self.now())
            newly_faulted = not previously_faulted and bool(self.filter.fault_reason)
            self.publish_status()
        if newly_faulted:
            rospy.logerr("%s safety filter fault: %s", self.side, self.filter.fault_reason)

    def reset_fault_callback(self, _request):
        with self.lock:
            reset = self.filter.reset_fault(self.now())
            self.publish_status()
        if reset:
            return TriggerResponse(success=True, message="fault reset; new authorization and session required")
        return TriggerResponse(
            success=False,
            message="reset requires deauthorization plus fresh feedback, localization and clear IK status",
        )

    def publish_status(self):
        now = self.now()
        state = self.filter.state(now)
        status = DiagnosticStatus()
        status.name = "pi05/{}/safety_filter".format(self.side)
        status.hardware_id = "redacted"
        if state == "FAULT_LATCHED":
            status.level = DiagnosticStatus.ERROR
            status.message = self.filter.fault_reason
        elif state in ("DISCONNECTED", "DISABLED"):
            status.level = DiagnosticStatus.WARN
            status.message = state
        else:
            status.level = DiagnosticStatus.OK
            status.message = state
        status.values = [
            KeyValue(key="side", value=self.side),
            KeyValue(key="state", value=state),
            KeyValue(key="authorized", value=str(self.filter.authorized).lower()),
            KeyValue(key="session_active", value=str(self.filter.session_active).lower()),
            KeyValue(key="feedback_fresh", value=str(self.filter._feedback_fresh(now)).lower()),
            KeyValue(key="localization_accurate", value=str(self.filter.localization_accurate).lower()),
            KeyValue(key="localization_fresh", value=str(self.filter._localization_fresh(now)).lower()),
            KeyValue(key="ik_over_limit", value=str(self.filter.ik_over_limit).lower()),
        ]
        self.status_pub.publish(status)


def main():
    rospy.init_node("arm_safety_filter")
    try:
        ArmSafetyFilterNode()
    except (KeyError, TypeError, ValueError) as error:
        rospy.logfatal("invalid arm safety filter configuration: %s", error)
        raise SystemExit(2)
    rospy.spin()


if __name__ == "__main__":
    main()
