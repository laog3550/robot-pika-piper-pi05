#!/usr/bin/env bash
set -Eeuo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python3 -m unittest -v "$repo_root/tests/test_direct_teleop.py"

source /opt/ros/noetic/setup.bash
export ROS_PACKAGE_PATH="$repo_root/src${ROS_PACKAGE_PATH:+:$ROS_PACKAGE_PATH}"
/usr/bin/python3 - "$repo_root" <<'PY'
import sys

import roslaunch

launch_dir = sys.argv[1] + "/src/pi05_left_teleop/launch"


def load(side, smooth, connect=False, gripper=False):
    arguments = [
        "start:=true",
        "connect_driver:=" + ("true" if connect else "false"),
        "auto_enable:=false",
        "smooth_commands:=" + ("true" if smooth else "false"),
        "enable_gripper_teleop:=" + ("true" if gripper else "false"),
    ]
    return roslaunch.config.load_config_default(
        [(launch_dir + "/" + side + "_teleop.launch", arguments)],
        None, assign_machines=False)


for side, suffix in (("left", "l"), ("right", "r")):
    smoothed_config = load(side, True)
    smoothed = {node.name: node for node in smoothed_config.nodes}
    ik_remaps = dict(smoothed["ik"].remap_args)
    smoother_remaps = dict(smoothed["joint_command_smoother"].remap_args)
    assert ik_remaps["/joint_states_" + suffix] == "/%s_arm/teleop/ik_target_raw" % side
    assert smoother_remaps["ik_target"] == "/%s_arm/teleop/ik_target_raw" % side
    assert smoother_remaps["smoothed_target"] == "/%s_arm/joint_ctrl_raw" % side
    assert dict(smoothed["teleop"].remap_args)["/pika_pose_" + suffix] == (
        "/pi05/pika_input/%s/pose" % side)

    direct = {node.name: node for node in load(side, False).nodes}
    assert "joint_command_smoother" not in direct
    assert dict(direct["ik"].remap_args)["/joint_states_" + suffix] == (
        "/%s_arm/joint_ctrl_raw" % side)

    gripper_config = load(side, True, connect=True, gripper=True)
    for parameter in (
        "/%s_arm/piper_driver_raw/gripper_maximum" % side,
        "/%s_arm/teleop/joint_command_smoother/gripper_maximum" % side,
        "/%s_arm/teleop/pika_gripper_input/piper_maximum" % side,
    ):
        assert gripper_config.params[parameter].value == 0.10, parameter
    gripper_node = next(
        node for node in gripper_config.nodes if node.name == "pika_gripper_input")
    assert dict(gripper_node.remap_args)["gripper_target"] == (
        "/pi05/pika_input/%s/gripper" % side)
print("Direct teleop launch resolution tests: PASS")
PY
