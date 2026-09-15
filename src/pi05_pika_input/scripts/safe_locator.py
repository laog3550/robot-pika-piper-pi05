#!/usr/bin/env python3
"""Run the local-only locator without putting identities in argv or logs."""
import os
import signal
import subprocess


def mapping(environ, order):
    if order not in ("direct", "swapped"):
        raise ValueError("explicit verified mapping_order is required")
    left = environ.get("pika_L_code", "").strip()
    right = environ.get("pika_R_code", "").strip()
    if not left or not right or left == right:
        raise ValueError("two distinct mapping environment values are required")
    return (right, left) if order == "swapped" else (left, right)


def main():
    import rospy
    rospy.init_node("safe_locator")
    try:
        left, right = mapping(os.environ, rospy.get_param("~mapping_order", "unverified"))
        # Do not launch while another locator owns the physical receivers.
        import rosgraph
        master = rosgraph.Master(rospy.get_name())
        publishers, subscribers, services = master.getSystemState()
        nodes = {node for _, owners in publishers + subscribers + services for node in owners}
        if any("piper" in node.lower() or "teleop" in node.lower() for node in nodes):
            raise ValueError("stop arm drivers and teleoperation nodes before input-only startup")
        raw_topics = {"/pika_pose_l", "/pika_pose_r",
                      "/pi05/pika_input/raw/left/pose", "/pi05/pika_input/raw/right/pose"}
        if any(topic in raw_topics and nodes for topic, nodes in publishers):
            raise ValueError("a locator is already publishing; stop it first")
        child_name = rospy.get_name() + "_backend"
        for key, value in (("left_hand_code", left), ("right_hand_code", right),
                           ("dist_limit", 0.2), ("angle_limit", 0.2),
                           ("linear_limit", 5), ("angular_limit", 20)):
            rospy.set_param(child_name + "/" + key, value)
        argv = ["rosrun", "pika_locator", "pika_double_locator_node",
                "__name:=" + child_name.rsplit("/", 1)[-1],
                "__ns:=" + child_name.rsplit("/", 1)[0], "__log:=/dev/null",
                "/rosout:=/pi05/pika_input/suppressed_rosout",
                "/tf:=/pi05/pika_input/raw/tf", "/tf_static:=/pi05/pika_input/raw/tf_static",
                "/pika_pose_l:=/pi05/pika_input/raw/left/pose",
                "/pika_pose_r:=/pi05/pika_input/raw/right/pose",
                "/pika_localization_status_l:=/pi05/pika_input/raw/left/localization_status",
                "/pika_localization_status_r:=/pi05/pika_input/raw/right/localization_status"]
        child = None
        try:
            with open(os.devnull, "wb") as sink:
                child = subprocess.Popen(argv, stdout=sink, stderr=sink,
                                         start_new_session=True)
                while not rospy.is_shutdown() and child.poll() is None:
                    rospy.rostime.wallsleep(0.1)
                if not rospy.is_shutdown():
                    rospy.logerr("local-only locator exited; input is unavailable")
                    return 1
        finally:
            if child is not None and child.poll() is None:
                os.killpg(child.pid, signal.SIGINT)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            if rospy.has_param(child_name):
                rospy.delete_param(child_name)
        return 0
    except Exception:
        # Never stringify exceptions that might contain a private parameter value.
        rospy.logerr("safe locator startup failed; check mapping and local package availability")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
