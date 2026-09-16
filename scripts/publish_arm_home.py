#!/usr/bin/python3
"""Publish one configured PI05 arm-home target; does not enable or disable."""
import argparse
import math
import sys
import time
from pathlib import Path


def load_home(path, side):
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    home = data[side + "_arm_home"]
    names = list(home["joint_names"])
    positions = [float(value) for value in home["positions_rad"]]
    speed = int(home["speed_percent"])
    if names != ["joint%d" % number for number in range(1, 7)]:
        raise ValueError("home joint names must be joint1..joint6")
    if len(positions) != 6 or not all(math.isfinite(value) for value in positions):
        raise ValueError("home pose must contain six finite joint positions")
    if not 1 <= speed <= 100:
        raise ValueError("home speed_percent must be in 1..100")
    return names, positions, speed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("side", choices=("left", "right"))
    parser.add_argument("--config", type=Path,
                        default=Path(__file__).resolve().parents[1] / "config/arm-home.yaml")
    parser.add_argument("--apply", action="store_true",
                        help="publish the configured target once")
    args = parser.parse_args(argv)
    try:
        names, positions, speed = load_home(args.config, args.side)
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.exit(2, "invalid arm-home configuration: %s\n" % error)
    topic = "/%s_arm/joint_ctrl_raw" % args.side
    if not args.apply:
        print("Planned target: %s, six configured joints, %d%% speed; add --apply to publish once."
              % (topic, speed))
        return 0

    import rospy
    from sensor_msgs.msg import JointState
    rospy.init_node("pi05_%s_arm_home" % args.side, anonymous=True)
    publisher = rospy.Publisher(topic, JointState, queue_size=1)
    deadline = time.monotonic() + 5.0
    while publisher.get_num_connections() == 0:
        if rospy.is_shutdown() or time.monotonic() >= deadline:
            parser.exit(3, "no motion driver subscribes to %s\n" % topic)
        rospy.sleep(0.05)
    message = JointState()
    message.header.stamp = rospy.Time.now()
    message.name = names
    message.position = positions
    # The pinned vendor driver interprets velocity[6] as a percentage.
    message.velocity = [0.0] * 6 + [float(speed)]
    publisher.publish(message)
    rospy.sleep(0.5)
    print("Published one %s arm-home target at %d%% speed; verify feedback before disabling."
          % (args.side, speed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
