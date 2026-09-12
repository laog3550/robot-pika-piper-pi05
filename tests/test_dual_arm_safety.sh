#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

/usr/bin/python3 -m unittest \
  "${repo_root}/src/pi05_control/test/test_dual_arm_safety.py" \
  "${repo_root}/src/pi05_control/test/test_dual_arm_bringup_launch.py"

source /opt/ros/noetic/setup.bash
export ROS_PACKAGE_PATH="${repo_root}/src${ROS_PACKAGE_PATH:+:${ROS_PACKAGE_PATH}}"
launch_path="${repo_root}/src/pi05_control/launch/s11_dual_arm_bringup.launch"

off_nodes=$(roslaunch --nodes "$launch_path" mode:=off)
simulation_nodes=$(roslaunch --nodes "$launch_path" mode:=simulation | sort)
hardware_nodes=$(roslaunch --nodes "$launch_path" mode:=hardware | sort)
[[ -z "$off_nodes" ]]
[[ "$simulation_nodes" == $'/dual_arm_safety_coordinator\n/left_arm/safety_filter\n/right_arm/safety_filter' ]]
[[ "$hardware_nodes" == $'/dual_arm_safety_coordinator\n/left_arm/piper_driver_raw\n/left_arm/safety_filter\n/right_arm/piper_driver_raw\n/right_arm/safety_filter' ]]

if roslaunch --nodes "$launch_path" mode:=invalid >/dev/null 2>&1; then
  printf '%s\n' 'invalid dual-arm mode unexpectedly produced a launch graph' >&2
  exit 1
fi

printf '%s\n' '[PASS] S11 dual-arm coordinator and bringup contracts'
