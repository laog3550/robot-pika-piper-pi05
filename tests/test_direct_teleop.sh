#!/usr/bin/env bash
set -Eeuo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python3 -m unittest -v "$repo_root/tests/test_direct_teleop.py"

source /opt/ros/noetic/setup.bash
export ROS_PACKAGE_PATH="$repo_root/src${ROS_PACKAGE_PATH:+:$ROS_PACKAGE_PATH}"
/usr/bin/python3 - "$repo_root" <<'PY'
import sys

import roslaunch

launch_path = sys.argv[1] + "/src/pi05_left_teleop/launch/right_teleop.launch"


def nodes_for(smooth):
    arguments = [
        "start:=true",
        "connect_driver:=false",
        "auto_enable:=false",
        "smooth_commands:=" + ("true" if smooth else "false"),
    ]
    config = roslaunch.config.load_config_default(
        [(launch_path, arguments)], None, assign_machines=False)
    return {node.name: node for node in config.nodes}


smoothed = nodes_for(True)
ik_remaps = dict(smoothed["ik"].remap_args)
smoother_remaps = dict(smoothed["joint_command_smoother"].remap_args)
assert ik_remaps["/joint_states_r"] == "/right_arm/teleop/ik_target_raw"
assert smoother_remaps["ik_target"] == "/right_arm/teleop/ik_target_raw"
assert smoother_remaps["smoothed_target"] == "/right_arm/joint_ctrl_raw"

direct = nodes_for(False)
assert "joint_command_smoother" not in direct
assert dict(direct["ik"].remap_args)["/joint_states_r"] == "/right_arm/joint_ctrl_raw"
print("Direct teleop launch resolution tests: PASS")
PY
