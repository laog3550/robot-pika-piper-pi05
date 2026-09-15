#!/usr/bin/env python3
"""Relay one explicit Pika side; outputs are observation-only, not commands."""


def forward(publisher, message, ros):
    """Handle shutdown racing with a subscriber callback, without masking faults."""
    if ros.is_shutdown():
        return
    try:
        publisher.publish(message)
    except ros.ROSException:
        if not ros.is_shutdown():
            raise


def main():
    import rospy
    from geometry_msgs.msg import PoseStamped
    from data_msgs.msg import LocalizationStatus
    rospy.init_node("side_input")
    side = rospy.get_param("~side", "")
    if side not in ("left", "right"):
        rospy.logerr("side must be left or right")
        return 2
    source = "/pi05/pika_input/raw/" + side
    target = "/pi05/pika_input/" + side
    pose = rospy.Publisher(target + "/pose", PoseStamped, queue_size=10)
    status = rospy.Publisher(target + "/localization_status", LocalizationStatus, queue_size=10)
    subscribers = [
        rospy.Subscriber(source + "/pose", PoseStamped,
                         lambda message: forward(pose, message, rospy), queue_size=10),
        rospy.Subscriber(source + "/localization_status", LocalizationStatus,
                         lambda message: forward(status, message, rospy), queue_size=10),
    ]
    rospy.spin()
    del subscribers
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
