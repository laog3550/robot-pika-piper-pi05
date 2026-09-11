#!/usr/bin/env python3
"""Validate dual Pika ROS localization without printing pose or device data."""

import argparse
import math
import os
import sys
import threading
import time
import xmlrpc.client


EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_ENVIRONMENT = 3


class LocalizationStats:
    """Thread-safe aggregate containing no raw pose or device identifiers."""

    def __init__(self):
        self.lock = threading.Lock()
        self.pose_count = 0
        self.status_count = 0
        self.accurate_count = 0
        self.invalid_pose_count = 0
        self.non_monotonic_count = 0
        self.frame_changed_count = 0
        self.last_stamp = None
        self.frame_id = None

    def observe_pose(self, position, orientation, stamp, frame_id):
        values = tuple(position) + tuple(orientation)
        finite = all(math.isfinite(value) for value in values)
        quaternion_norm = math.sqrt(sum(value * value for value in orientation))
        with self.lock:
            self.pose_count += 1
            if not finite or not 0.9 <= quaternion_norm <= 1.1:
                self.invalid_pose_count += 1
            if self.last_stamp is not None and stamp < self.last_stamp:
                self.non_monotonic_count += 1
            self.last_stamp = stamp
            if self.frame_id is None:
                self.frame_id = frame_id
            elif frame_id != self.frame_id:
                self.frame_changed_count += 1

    def observe_status(self, accurate):
        with self.lock:
            self.status_count += 1
            self.accurate_count += int(bool(accurate))

    def snapshot(self):
        with self.lock:
            return {
                "pose_count": self.pose_count,
                "status_count": self.status_count,
                "accurate_count": self.accurate_count,
                "invalid_pose_count": self.invalid_pose_count,
                "non_monotonic_count": self.non_monotonic_count,
                "frame_changed_count": self.frame_changed_count,
                "frame_present": bool(self.frame_id),
            }


def evaluate(stats, elapsed, min_pose_rate, min_status_samples):
    failures = []
    pose_rate = stats["pose_count"] / elapsed if elapsed > 0 else 0.0
    if pose_rate < min_pose_rate:
        failures.append("pose rate below threshold")
    if stats["status_count"] < min_status_samples:
        failures.append("insufficient localization status samples")
    if stats["accurate_count"] != stats["status_count"]:
        failures.append("one or more localization status samples are inaccurate")
    if stats["invalid_pose_count"]:
        failures.append("invalid pose or quaternion observed")
    if stats["non_monotonic_count"]:
        failures.append("non-monotonic pose timestamp observed")
    if stats["frame_changed_count"] or not stats["frame_present"]:
        failures.append("missing or unstable pose frame")
    return pose_rate, failures


def positive_float(value):
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return parsed


def positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=(
            "Subscribe to dual Pika pose/status topics and report only aggregate "
            "validity statistics. The checker never starts a locator or prints poses."
        )
    )
    parser.add_argument("--duration", type=positive_float, default=10.0)
    parser.add_argument("--min-pose-rate", type=positive_float, default=30.0)
    parser.add_argument("--min-status-samples", type=positive_int, default=5)
    return parser.parse_args(argv)


class TimeoutTransport(xmlrpc.client.Transport):
    """XML-RPC transport with a bounded ROS Master connection timeout."""

    def make_connection(self, host):
        connection = super().make_connection(host)
        connection.timeout = 2.0
        return connection


def ros_master_reachable(uri):
    try:
        proxy = xmlrpc.client.ServerProxy(uri, transport=TimeoutTransport())
        code, _, _ = proxy.getUri("/pi05_pika_localization_preflight")
        return code == 1
    except (OSError, ValueError, xmlrpc.client.Error):
        return False


def main(argv=None):
    try:
        args = parse_args(argv)
    except SystemExit as error:
        return EXIT_USAGE if error.code else 0

    try:
        import rospy
        from data_msgs.msg import LocalizationStatus
        from geometry_msgs.msg import PoseStamped
    except ImportError as error:
        print(
            "[PI05] ERROR: ROS Noetic and data_msgs must be available in the current environment: %s"
            % error,
            file=sys.stderr,
        )
        return EXIT_ENVIRONMENT

    master_uri = os.environ.get("ROS_MASTER_URI", "http://localhost:11311")
    if not ros_master_reachable(master_uri):
        print(
            "[PI05] ERROR: ROS Master is not reachable at the configured ROS_MASTER_URI",
            file=sys.stderr,
        )
        return EXIT_ENVIRONMENT

    sides = {"left": LocalizationStats(), "right": LocalizationStats()}

    def pose_callback(side):
        def callback(message):
            sides[side].observe_pose(
                (
                    message.pose.position.x,
                    message.pose.position.y,
                    message.pose.position.z,
                ),
                (
                    message.pose.orientation.x,
                    message.pose.orientation.y,
                    message.pose.orientation.z,
                    message.pose.orientation.w,
                ),
                message.header.stamp.to_sec(),
                message.header.frame_id,
            )

        return callback

    def status_callback(side):
        return lambda message: sides[side].observe_status(message.accurate)

    try:
        rospy.init_node("pi05_pika_localization_check", anonymous=True, disable_signals=True)
        subscribers = [
            rospy.Subscriber("/pika_pose_l", PoseStamped, pose_callback("left"), queue_size=100),
            rospy.Subscriber("/pika_pose_r", PoseStamped, pose_callback("right"), queue_size=100),
            rospy.Subscriber(
                "/pika_localization_status_l",
                LocalizationStatus,
                status_callback("left"),
                queue_size=100,
            ),
            rospy.Subscriber(
                "/pika_localization_status_r",
                LocalizationStatus,
                status_callback("right"),
                queue_size=100,
            ),
        ]
    except Exception as error:
        print("[PI05] ERROR: cannot connect to the ROS graph: %s" % error, file=sys.stderr)
        return EXIT_ENVIRONMENT

    started = time.monotonic()
    try:
        while time.monotonic() - started < args.duration and not rospy.is_shutdown():
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("[PI05] ERROR: localization check interrupted", file=sys.stderr)
        return EXIT_FAILED
    elapsed = max(time.monotonic() - started, 1e-9)
    del subscribers

    failed = False
    for side in ("left", "right"):
        snapshot = sides[side].snapshot()
        pose_rate, failures = evaluate(
            snapshot, elapsed, args.min_pose_rate, args.min_status_samples
        )
        print(
            "[PI05] %s Pika localization: poses=%d rate=%.1fHz status=%d accurate=%d"
            % (
                side,
                snapshot["pose_count"],
                pose_rate,
                snapshot["status_count"],
                snapshot["accurate_count"],
            )
        )
        for failure in failures:
            print("[PI05] ERROR: %s: %s" % (side, failure), file=sys.stderr)
        failed = failed or bool(failures)

    if failed:
        print("[PI05] Pika localization check failed", file=sys.stderr)
        return EXIT_FAILED
    print("[PI05] dual Pika localization check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
