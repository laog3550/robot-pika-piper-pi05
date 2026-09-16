#!/usr/bin/env python3
"""Run one enabled teleop interval, then return home and disable the arm."""
import argparse
import math
import sys
import time
from pathlib import Path

from publish_arm_home import load_home


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("side", choices=("left", "right"))
    parser.add_argument("--duration", type=float,
                        help="stop automatically after this many seconds; otherwise press Enter")
    parser.add_argument("--home-timeout", type=float, default=180.0)
    parser.add_argument("--home-tolerance", type=float, default=0.02)
    parser.add_argument("--stable-seconds", type=float, default=1.0)
    parser.add_argument("--config", type=Path,
                        default=Path(__file__).resolve().parents[1] / "config/arm-home.yaml")
    parser.add_argument("--apply", action="store_true",
                        help="authorize enable, teleop, automatic return and disable")
    parser.add_argument("--check-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--startup-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.duration is not None and (not math.isfinite(args.duration) or args.duration <= 0):
        parser.error("--duration must be a positive finite number")
    for name in ("home_timeout", "home_tolerance", "stable_seconds"):
        value = getattr(args, name)
        if not math.isfinite(value) or value <= 0:
            parser.error("--%s must be positive and finite" % name.replace("_", "-"))
    if not args.apply:
        parser.error("this command moves hardware; add --apply after checking the workspace")
    if args.duration is None and not args.startup_only and not sys.stdin.isatty():
        parser.error("interactive mode needs a terminal; use --duration for non-interactive use")
    return args


def wait_for_topology(rospy, side, timeout=20.0):
    import rosgraph
    suffix = {"left": "l", "right": "r"}[side]
    ik_target = "/%s_arm/teleop/ik_target_raw" % side
    command = "/%s_arm/joint_ctrl_raw" % side
    expected = {
        ik_target: (["/%s_arm/teleop/ik" % side],
                    ["/%s_arm/teleop/joint_command_smoother" % side]),
        command: (["/%s_arm/teleop/joint_command_smoother" % side],
                  ["/%s_arm/piper_driver_raw" % side]),
        "/pi05/pika_input/%s/pose" % side: (None,
                                              ["/%s_arm/teleop/teleop" % side]),
    }
    deadline = time.monotonic() + timeout
    last = None
    master = rosgraph.Master("/pi05_%s_session_topology" % suffix)
    while not rospy.is_shutdown() and time.monotonic() < deadline:
        publishers, subscribers, _ = master.getSystemState()
        publishers = {topic: sorted(nodes) for topic, nodes in publishers}
        subscribers = {topic: sorted(nodes) for topic, nodes in subscribers}
        last = (publishers, subscribers)
        valid = True
        for topic, (wanted_publishers, wanted_subscribers) in expected.items():
            if wanted_publishers is not None and publishers.get(topic, []) != wanted_publishers:
                valid = False
            if not set(wanted_subscribers).issubset(subscribers.get(topic, [])):
                valid = False
        if valid:
            return
        rospy.sleep(0.1)
    raise RuntimeError("smoothed teleop ROS topology did not become ready: %r" % (last,))


def reset_then_enable(rospy, reset, enable, context):
    reset_response = reset()
    if not reset_response.success:
        raise RuntimeError("driver rejected software-stop reset %s" % context)
    # Recovery is asynchronous on the controller.  If enable is queried
    # immediately it can still see the old enabled state, return success, and
    # then be undone by the delayed reset effect.
    rospy.sleep(1.0)
    enable_response = enable(True)
    if not enable_response.enable_response:
        raise RuntimeError("driver rejected enable %s" % context)


def wait_for_home(rospy, publisher, JointState, feedback_topic, names, target,
                  speed, timeout, tolerance, stable_seconds,
                  recover_motion=None, stall_seconds=5.0, max_recoveries=5):
    message = JointState()
    message.name = names
    message.position = target
    message.velocity = [0.0] * 6 + [float(speed)]
    deadline = time.monotonic() + timeout
    stable_since = None
    last_error = float("inf")
    best_error = float("inf")
    last_progress = time.monotonic()
    recoveries = 0
    while not rospy.is_shutdown() and time.monotonic() < deadline:
        message.header.stamp = rospy.Time.now()
        publisher.publish(message)
        try:
            feedback = rospy.wait_for_message(feedback_topic, JointState, timeout=1.0)
        except rospy.ROSException:
            continue
        if len(feedback.position) < 6:
            stable_since = None
            continue
        positions = [float(value) for value in feedback.position[:6]]
        if not all(math.isfinite(value) for value in positions):
            stable_since = None
            continue
        last_error = max(abs(actual - expected)
                         for actual, expected in zip(positions, target))
        now = time.monotonic()
        if last_error < best_error - 0.002:
            best_error = last_error
            last_progress = now
        if last_error <= tolerance:
            stable_since = stable_since or now
            if now - stable_since >= stable_seconds:
                return last_error
        else:
            stable_since = None
            if (recover_motion is not None and
                    now - last_progress >= stall_seconds):
                if recoveries >= max_recoveries:
                    raise RuntimeError(
                        "home motion stalled after %d recovery attempts; arm remains enabled"
                        % recoveries)
                recoveries += 1
                recover_motion(recoveries, last_error)
                best_error = last_error
                last_progress = time.monotonic()
        rospy.sleep(0.1)
    raise RuntimeError(
        "home was not stable within %.1fs (last max error %.6frad); arm remains enabled"
        % (timeout, last_error))


def main(argv=None):
    args = parse_args(argv)
    try:
        names, target, speed = load_home(args.config, args.side)
    except (OSError, KeyError, TypeError, ValueError) as error:
        print("invalid arm-home configuration: %s" % error, file=sys.stderr)
        return 2
    if args.check_only:
        return 0

    import rospy
    from piper_msgs.srv import Enable
    from sensor_msgs.msg import JointState
    from std_srvs.srv import SetBool, Trigger

    suffix = {"left": "l", "right": "r"}[args.side]
    enable_service = "/%s_arm/enable_srv_raw" % args.side
    reset_service = "/%s_arm/reset_srv_raw" % args.side
    trigger_service = "/teleop_trigger_%s" % suffix
    gate_service = "/%s_arm/teleop/joint_command_smoother/set_enabled" % args.side
    feedback_topic = "/joint_states_single_%s" % suffix
    command_topic = "/%s_arm/joint_ctrl_raw" % args.side

    rospy.init_node("pi05_%s_smoothed_teleop_session" % args.side, anonymous=True)
    try:
        wait_for_topology(rospy, args.side)
        rospy.wait_for_service(enable_service, timeout=20.0)
        rospy.wait_for_service(reset_service, timeout=20.0)
        rospy.wait_for_service(trigger_service, timeout=20.0)
        rospy.wait_for_service(gate_service, timeout=20.0)
        rospy.wait_for_message(feedback_topic, JointState, timeout=10.0)
    except Exception as error:
        print("teleop stack is not ready: %s" % error, file=sys.stderr)
        return 3

    enable = rospy.ServiceProxy(enable_service, Enable)
    reset = rospy.ServiceProxy(reset_service, Trigger)
    trigger = rospy.ServiceProxy(trigger_service, Trigger)
    set_smoother_enabled = rospy.ServiceProxy(gate_service, SetBool)
    publisher = rospy.Publisher(command_topic, JointState, queue_size=1)
    deadline = time.monotonic() + 5.0
    while publisher.get_num_connections() == 0 and time.monotonic() < deadline:
        rospy.sleep(0.05)
    if publisher.get_num_connections() == 0:
        print("motion driver does not subscribe to %s" % command_topic, file=sys.stderr)
        return 3
    if args.startup_only:
        print("Smoothed teleop stack startup and topology check passed; arm was not enabled.")
        return 0

    enabled = False
    trigger_active = False
    failure = None
    try:
        gate_response = set_smoother_enabled(True)
        if not gate_response.success:
            raise RuntimeError("could not enable smoother output")
        enabled = True
        reset_then_enable(rospy, reset, enable, "before teleop")
        trigger()
        trigger_active = True
        print("%s arm teleop is active with smoothing." % args.side)
        if args.duration is None:
            input("Move the Pika; press Enter once to finish and return home: ")
        else:
            print("Teleop will stop automatically after %.1f seconds." % args.duration)
            rospy.sleep(args.duration)
    except KeyboardInterrupt:
        print("\nStop requested; closing teleop and returning home.")
    except Exception as error:
        failure = error
    finally:
        commands_blocked = False
        try:
            gate_response = set_smoother_enabled(False)
            commands_blocked = bool(gate_response.success)
            if not commands_blocked:
                failure = failure or RuntimeError("smoother refused to disable its output")
        except BaseException as error:
            failure = failure or RuntimeError("could not disable smoother output: %s" % error)
        if trigger_active:
            try:
                trigger()
                trigger_active = False
                rospy.sleep(0.4)
            except BaseException as error:
                # The explicit smoother gate already blocks driver commands.
                print("warning: could not close teleop trigger: %s" % error, file=sys.stderr)
        if enabled and commands_blocked:
            try:
                def recover_home_motion(attempt, stalled_error):
                    print("Home motion stalled at %.6frad; recovery %d/%d: reset -> enable."
                          % (stalled_error, attempt, 5))
                    reset_then_enable(rospy, reset, enable, "during return")

                print("Teleop closed; returning to support home at %d%% speed." % speed)
                error = wait_for_home(
                    rospy, publisher, JointState, feedback_topic, names, target,
                    speed, args.home_timeout, args.home_tolerance,
                    args.stable_seconds, recover_motion=recover_home_motion)
                print("Home confirmed (max joint error %.6frad)." % error)
                response = enable(False)
                if not response.enable_response:
                    raise RuntimeError("driver rejected the disable request")
                enabled = False
                print("%s arm disabled after reaching home." % args.side)
            except BaseException as error:
                failure = failure or error

    if failure is not None:
        print("session failed: %s" % failure, file=sys.stderr)
        if enabled:
            print("The arm may remain enabled; keep the driver running and inspect it in place.",
                  file=sys.stderr)
            return 4
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
