#!/usr/bin/env python3
"""Guarded, two-phase S12 single-joint acceptance utility."""

import argparse
import collections
import re
import socket
import struct
import sys
import threading
import time

from pi05_control.low_speed_acceptance import (
    AcceptanceConfig,
    MAX_ENABLE_SHIFT_RAD,
    MotionEvidence,
    ReturnEvidence,
    StableBaseline,
    maximum_joint_shift,
    require_enable_settle_clearance,
    require_move_clearance,
    require_legacy_stack_compatible_firmware,
)
from pi05_control.piper_feedback import FeedbackAssembler, MotorTelemetryWindow


CAN_FRAME = struct.Struct("=IB3x8s")
CAN_EFF_MASK = 0x1FFFFFFF
INTERFACE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,14}$")

rosgraph = None
rosnode = None
rospy = None
PiperStatusMsg = None
Enable = None
JointState = None
Trigger = None


def load_ros_dependencies():
    """Load hardware-only ROS dependencies after dry-run gates have passed."""
    global rosgraph, rosnode, rospy
    global PiperStatusMsg, Enable, JointState, Trigger
    if all(item is not None for item in (
            rosgraph, rosnode, rospy, PiperStatusMsg, Enable, JointState, Trigger)):
        return
    try:
        import rosgraph as rosgraph_module
        import rosnode as rosnode_module
        import rospy as rospy_module
        from piper_msgs.msg import PiperStatusMsg as piper_status_type
        from piper_msgs.srv import Enable as enable_type
        from sensor_msgs.msg import JointState as joint_state_type
        from std_srvs.srv import Trigger as trigger_type
    except ImportError as exc:
        raise RuntimeError(
            "hardware apply dependencies are unavailable; source the pinned "
            "Piper ROS Noetic workspace: {}".format(exc))
    rosgraph = rosgraph_module
    rosnode = rosnode_module
    rospy = rospy_module
    PiperStatusMsg = piper_status_type
    Enable = enable_type
    JointState = joint_state_type
    Trigger = trigger_type


class PassiveCanFeedbackSource(object):
    """Receive coherent Piper feedback cycles without any CAN transmit API."""

    def __init__(self, interface):
        if not INTERFACE_RE.fullmatch(interface):
            raise ValueError("invalid SocketCAN interface name")
        self.source = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        self.source.bind((interface,))
        self.assembler = FeedbackAssembler()
        self.motor_telemetry = MotorTelemetryWindow()
        self.pending = collections.deque()
        self.condition = threading.Condition()
        self.closed = False
        self.failure = None
        self.worker = threading.Thread(target=self._receive, daemon=True)
        self.worker.start()

    def _receive(self):
        try:
            self.source.settimeout(0.05)
            while not self.closed:
                try:
                    frame = self.source.recv(CAN_FRAME.size)
                except socket.timeout:
                    continue
                if len(frame) != CAN_FRAME.size:
                    continue
                can_id, dlc, payload = CAN_FRAME.unpack(frame)
                if dlc != 8:
                    continue
                clean_id = can_id & CAN_EFF_MASK
                with self.condition:
                    self.motor_telemetry.update(clean_id, payload)
                    positions = self.assembler.update(clean_id, payload)
                    if positions is not None:
                        if len(self.pending) >= 256:
                            raise RuntimeError("passive CAN feedback queue overflow")
                        self.pending.append((time.monotonic(), list(positions)))
                        self.condition.notify_all()
        except Exception:
            with self.condition:
                if not self.closed:
                    self.failure = "passive CAN receiver failed or queue overflowed"
                self.condition.notify_all()

    def next_positions(self, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.condition:
                if self.failure or self.closed:
                    raise RuntimeError(self.failure or "passive CAN receiver closed")
                if self.pending:
                    received, positions = self.pending.popleft()
                    if time.monotonic() - received > 0.1:
                        raise RuntimeError("passive CAN feedback is stale")
                    return positions
                self.condition.wait(max(0.001, deadline - time.monotonic()))
        raise RuntimeError("passive raw CAN feedback timed out")

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()
        self.worker.join(timeout=0.2)
        self.source.close()

    def telemetry_summary(self):
        with self.condition:
            return self.motor_telemetry.summary()


def parser():
    item = argparse.ArgumentParser(
        description=(
            "S12 guarded single-arm low-speed acceptance. Enable-settle sends no "
            "joint target; move never disables; supported-disable is separate."
        )
    )
    sub = item.add_subparsers(dest="action", required=True)
    move = sub.add_parser("move", help="perform one guarded joint out-and-back move")
    move.add_argument("--side", required=True, choices=("left", "right"))
    move.add_argument("--joint", required=True, type=int, choices=range(1, 7))
    move.add_argument("--delta-rad", type=float, default=0.005)
    move.add_argument("--speed-percent", type=float, default=5.0)
    move.add_argument("--resume-stop", action="store_true",
                      help="explicitly resume a previously latched software stop")
    move.add_argument("--apply", action="store_true",
                      help="send commands; without this flag only print the plan")
    move.add_argument("--confirm-single-arm", action="store_true")
    move.add_argument("--confirm-mechanical-support", action="store_true")
    move.add_argument(
        "--clearance-file", default="config/s12-acceptance.env",
        help="Git-ignored incident clearance record required by --apply")
    move.add_argument(
        "--hardware-file", default="config/s07-hardware.env",
        help="Git-ignored firmware record required by --apply")

    settle = sub.add_parser(
        "enable-settle", help="measure enable settling without a joint target")
    settle.add_argument("--side", required=True, choices=("left", "right"))
    settle.add_argument("--resume-stop", action="store_true")
    settle.add_argument("--apply", action="store_true")
    settle.add_argument("--confirm-single-arm", action="store_true")
    settle.add_argument("--confirm-mechanical-support", action="store_true")
    settle.add_argument(
        "--clearance-file", default="config/s12-acceptance.env",
        help="Git-ignored incident clearance record required by --apply")
    settle.add_argument(
        "--hardware-file", default="config/s07-hardware.env",
        help="Git-ignored firmware record required by --apply")

    disable = sub.add_parser(
        "supported-disable", help="disable one already-supported arm after a move")
    disable.add_argument("--side", required=True, choices=("left", "right"))
    disable.add_argument("--apply", action="store_true")
    disable.add_argument("--confirm-mechanical-support", action="store_true")
    return item


class AcceptanceRunner(object):
    def __init__(self, side):
        self.side = side
        self.prefix = "/{}_arm".format(side)
        self.feedback_topic = self.prefix + "/joint_states_driver_raw"
        self.status_topic = self.prefix + "/arm_status"
        self.command_topic = self.prefix + "/joint_ctrl_raw"
        self.enable_service = self.prefix + "/enable_srv_raw"
        self.stop_service = self.prefix + "/stop_srv_raw"
        self.reset_service = self.prefix + "/reset_srv_raw"
        self.can_interface = "{}_piper".format(side)

    def _require_isolated_graph(self):
        expected_driver = self.prefix + "/piper_driver_raw"
        nodes = set(rosnode.get_node_names())
        allowed = {"/rosout", expected_driver, rospy.get_name()}
        unexpected = sorted(nodes - allowed)
        if expected_driver not in nodes or unexpected:
            raise RuntimeError(
                "expected only {} and rosout; unexpected nodes={}".format(
                    expected_driver, unexpected
                )
            )
        publishers, subscribers, _services = rosgraph.Master(rospy.get_name()).getSystemState()
        command_publishers = []
        command_subscribers = []
        for topic, names in publishers:
            if topic == self.command_topic:
                command_publishers = list(names)
        for topic, names in subscribers:
            if topic == self.command_topic:
                command_subscribers = list(names)
        if command_publishers:
            raise RuntimeError("raw command topic already has a publisher")
        if command_subscribers != [expected_driver]:
            raise RuntimeError("raw command topic does not have exactly the selected driver")

    @staticmethod
    def _status_clear(message):
        limits = [getattr(message, "joint_{}_angle_limit".format(i))
                  for i in range(1, 7)]
        communication = [getattr(message, "communication_status_joint_{}".format(i))
                         for i in range(1, 7)]
        return message.err_code == 0 and not any(limits) and not any(communication)

    def _fresh_status(self):
        message = rospy.wait_for_message(self.status_topic, PiperStatusMsg, timeout=3.0)
        if not self._status_clear(message):
            raise RuntimeError("driver reported an error, limit, or communication fault")

    def _stable_baseline(self, recovery_time, config):
        collector = StableBaseline(
            config.baseline_samples, config.baseline_tolerance_rad)
        collector.begin_after_recovery(recovery_time)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            message = rospy.wait_for_message(
                self.feedback_topic, JointState, timeout=0.5)
            stamp = message.header.stamp.to_sec()
            if stamp <= 0.0:
                stamp = rospy.Time.now().to_sec()
            baseline = collector.add(stamp, message.position)
            if baseline is not None:
                return list(baseline)
        raise RuntimeError("feedback did not produce a stable post-recovery baseline")

    def _publish_until(self, publisher, positions, predicate, label):
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            command = JointState()
            command.header.stamp = rospy.Time.now()
            command.position = positions
            command.velocity = [0.0] * 6 + [self.config.speed_percent]
            command.effort = [0.0] * 6 + [1.0]
            publisher.publish(command)
            feedback = rospy.wait_for_message(
                self.feedback_topic, JointState, timeout=0.2)
            if predicate(feedback):
                return feedback
            rospy.sleep(0.05)
        raise RuntimeError("{} timed out".format(label))

    def _open_can_feedback(self):
        return PassiveCanFeedbackSource(self.can_interface)

    @staticmethod
    def _stable_can_baseline(source, config):
        collector = StableBaseline(
            config.baseline_samples, config.baseline_tolerance_rad)
        collector.begin_after_recovery(time.monotonic())
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            positions = source.next_positions(0.5)
            baseline = collector.add(time.monotonic(), positions)
            if baseline is not None:
                return list(baseline)
        raise RuntimeError("raw CAN did not produce a stable baseline")

    def _publish_until_can(self, publisher, positions, source, predicate, label):
        deadline = time.monotonic() + 4.0
        next_publish = 0.0
        while time.monotonic() < deadline:
            feedback = source.next_positions(0.2)
            if predicate(feedback):
                return feedback
            if time.monotonic() >= next_publish:
                command = JointState()
                command.header.stamp = rospy.Time.now()
                command.position = positions
                command.velocity = [0.0] * 6 + [self.config.speed_percent]
                command.effort = [0.0] * 6 + [1.0]
                publisher.publish(command)
                next_publish = time.monotonic() + 0.05
        raise RuntimeError("{} timed out".format(label))

    def _stop_only(self):
        rospy.wait_for_service(self.stop_service, timeout=2.0)
        response = rospy.ServiceProxy(self.stop_service, Trigger)()
        if not response.success:
            raise RuntimeError("software stop service returned false")

    def run_move(self, config, resume_stop):
        self.config = config
        self._require_isolated_graph()
        for name in (self.enable_service, self.stop_service):
            rospy.wait_for_service(name, timeout=3.0)
        self._fresh_status()

        recovery_time = rospy.Time.now().to_sec()
        if resume_stop:
            rospy.wait_for_service(self.reset_service, timeout=3.0)
            response = rospy.ServiceProxy(self.reset_service, Trigger)()
            if not response.success:
                raise RuntimeError("resume/reset service returned false")
            recovery_time = rospy.Time.now().to_sec()
            rospy.sleep(1.0)
            self._fresh_status()
        pre_enable_baseline = self._stable_baseline(recovery_time, config)

        publisher = rospy.Publisher(self.command_topic, JointState, queue_size=1)
        deadline = time.monotonic() + 3.0
        while publisher.get_num_connections() < 1 and time.monotonic() < deadline:
            rospy.sleep(0.05)
        if publisher.get_num_connections() != 1:
            raise RuntimeError("raw command topic does not have exactly one subscriber")

        enable = rospy.ServiceProxy(self.enable_service, Enable)
        enable_attempted = False
        returned = False
        try:
            enable_attempted = True
            if not enable(True).enable_response:
                raise RuntimeError("enable service returned false")
            enable_time = rospy.Time.now().to_sec()
            rospy.sleep(0.5)
            self._fresh_status()
            baseline = self._stable_baseline(enable_time, config)
            shifted_joint, enable_shift = maximum_joint_shift(
                pre_enable_baseline, baseline)
            if abs(enable_shift) > MAX_ENABLE_SHIFT_RAD:
                raise RuntimeError(
                    "enable settling exceeded {:.6f} rad: J{} delta={:.6f}".format(
                        MAX_ENABLE_SHIFT_RAD, shifted_joint, enable_shift
                    )
                )
            raw_source = self._open_can_feedback()
            try:
                raw_baseline = self._stable_can_baseline(raw_source, config)
                mismatch_joint, mismatch = maximum_joint_shift(
                    baseline, raw_baseline)
                if abs(mismatch) > MAX_ENABLE_SHIFT_RAD:
                    raise RuntimeError(
                        "ROS/raw CAN baseline mismatch exceeded {:.6f} rad: "
                        "J{} delta={:.6f}".format(
                            MAX_ENABLE_SHIFT_RAD, mismatch_joint, mismatch))
                rospy.loginfo(
                    "ROS/raw CAN baseline maximum difference: J%d delta=%.6f rad",
                    mismatch_joint, mismatch)
                # Use one measurement epoch for both command generation and
                # motion evidence.  Reusing the earlier ROS baseline here can
                # command every non-selected joint toward a slightly stale
                # value even when the ROS/CAN agreement check passes.
                index = config.joint - 1
                target = list(raw_baseline)
                target[index] += config.delta_rad
                motion_evidence = MotionEvidence(
                    raw_baseline, config.joint, config.delta_rad)
                moved = self._publish_until_can(
                    publisher, target, raw_source, motion_evidence.add,
                    "outward move")
                observed = moved[index] - raw_baseline[index]
                self._fresh_status()
                return_evidence = ReturnEvidence(raw_baseline)
                return_guard = MotionEvidence(
                    raw_baseline, config.joint, config.delta_rad)
                def guarded_return(positions):
                    return_guard.add(positions)
                    return return_evidence.add(positions)
                returned_msg = self._publish_until_can(
                    publisher, raw_baseline, raw_source, guarded_return,
                    "return move")
            finally:
                for joint, count, peak_speed, peak_current in raw_source.telemetry_summary():
                    rospy.loginfo(
                        "raw CAN motor J%d: samples=%d peak_speed=%.3f rad/s "
                        "peak_current=%.3f A",
                        joint, count, peak_speed, peak_current)
                raw_source.close()
            returned = True
            self._fresh_status()
            return observed, max(
                abs(returned_msg[i] - raw_baseline[i]) for i in range(6))
        finally:
            if enable_attempted:
                try:
                    self._stop_only()
                except Exception as stop_error:
                    rospy.logfatal(
                        "software stop failed after an enable attempt; use the hardware "
                        "emergency stop immediately: %s", stop_error)
                    raise
                if not returned:
                    rospy.logerr(
                        "motion or enable transition failed: software stop requested; the "
                        "arm may remain enabled. "
                        "Use hardware emergency stop if it moves unexpectedly. Mechanically "
                        "support it before running supported-disable."
                    )

    def run_enable_settle(self, config, resume_stop):
        self.config = config
        self._require_isolated_graph()
        for name in (self.enable_service, self.stop_service):
            rospy.wait_for_service(name, timeout=3.0)
        self._fresh_status()

        recovery_time = rospy.Time.now().to_sec()
        if resume_stop:
            rospy.wait_for_service(self.reset_service, timeout=3.0)
            response = rospy.ServiceProxy(self.reset_service, Trigger)()
            if not response.success:
                raise RuntimeError("resume/reset service returned false")
            recovery_time = rospy.Time.now().to_sec()
            rospy.sleep(1.0)
            self._fresh_status()
        before = self._stable_baseline(recovery_time, config)

        enable = rospy.ServiceProxy(self.enable_service, Enable)
        enable_attempted = False
        try:
            enable_attempted = True
            if not enable(True).enable_response:
                raise RuntimeError("enable service returned false")
            enable_time = rospy.Time.now().to_sec()
            rospy.sleep(0.5)
            self._fresh_status()
            after = self._stable_baseline(enable_time, config)
            joint, shift = maximum_joint_shift(before, after)
            if abs(shift) > MAX_ENABLE_SHIFT_RAD:
                raise RuntimeError(
                    "enable settling exceeded {:.6f} rad: J{} delta={:.6f}".format(
                        MAX_ENABLE_SHIFT_RAD, joint, shift
                    )
                )
            return joint, shift
        finally:
            if enable_attempted:
                try:
                    self._stop_only()
                except Exception as stop_error:
                    rospy.logfatal(
                        "software stop failed after enable-settle; use the hardware "
                        "emergency stop immediately: %s", stop_error)
                    raise

    def run_supported_disable(self):
        self._require_isolated_graph()
        rospy.wait_for_service(self.enable_service, timeout=3.0)
        response = rospy.ServiceProxy(self.enable_service, Enable)(False)
        if not response.enable_response:
            raise RuntimeError("supported disable service returned false")


def main(argv=None):
    args = parser().parse_args(argv)
    if args.action == "move":
        config = AcceptanceConfig(
            args.side, args.joint, args.delta_rad, args.speed_percent)
        print(
            "[PI05] plan: {} J{} delta={:.6f} rad speed={:.1f}%; "
            "move never calls disable".format(
                config.side, config.joint, config.delta_rad, config.speed_percent
            )
        )
        if not args.apply:
            return 0
        if not args.confirm_single_arm or not args.confirm_mechanical_support:
            raise RuntimeError(
                "--apply requires --confirm-single-arm and --confirm-mechanical-support")
        require_legacy_stack_compatible_firmware(args.hardware_file, args.side)
        require_move_clearance(args.clearance_file, args.side)
    elif args.action == "enable-settle":
        print(
            "[PI05] plan: {} enable-settle only; no joint target will be published".format(
                args.side
            )
        )
        if not args.apply:
            return 0
        if not args.confirm_single_arm or not args.confirm_mechanical_support:
            raise RuntimeError(
                "--apply requires --confirm-single-arm and --confirm-mechanical-support")
        require_legacy_stack_compatible_firmware(args.hardware_file, args.side)
        require_enable_settle_clearance(args.clearance_file, args.side)
    else:
        print("[PI05] plan: disable {} only after mechanical support carries the arm".format(
            args.side))
        if not args.apply:
            return 0
        if not args.confirm_mechanical_support:
            raise RuntimeError(
                "--apply requires --confirm-mechanical-support")

    load_ros_dependencies()
    if not rosgraph.is_master_online():
        raise RuntimeError("ROS master is not online")
    rospy.init_node("s12_single_arm_acceptance", anonymous=True, disable_signals=True)
    runner = AcceptanceRunner(args.side)
    if args.action == "supported-disable":
        runner.run_supported_disable()
        print("[PI05] supported disable accepted")
        return 0
    if args.action == "enable-settle":
        config = AcceptanceConfig(args.side, 1)
        joint, shift = runner.run_enable_settle(config, args.resume_stop)
        print(
            "[PI05] enable-settle passed: maximum J{} delta={:.6f}; "
            "software stop requested and arm remains enabled".format(joint, shift)
        )
        print("[PI05] mechanically support the arm, then run supported-disable")
        return 0
    observed, return_error = runner.run_move(config, args.resume_stop)
    print(
        "[PI05] move passed: observed_delta={:.6f} return_error={:.6f}; "
        "software stop requested and arm remains enabled".format(observed, return_error)
    )
    print("[PI05] mechanically support the arm, then run supported-disable")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print("[PI05] ERROR: {}".format(error), file=sys.stderr)
        sys.exit(1)
