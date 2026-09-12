#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

/usr/bin/python3 -m unittest \
  "${repo_root}/src/pi05_control/test/test_safety_filter.py" \
  "${repo_root}/src/pi05_control/test/test_safety_filter_launch.py"

source /opt/ros/noetic/setup.bash
export ROS_PACKAGE_PATH="${repo_root}/src${ROS_PACKAGE_PATH:+:${ROS_PACKAGE_PATH}}"

launch_path="${repo_root}/src/pi05_control/launch/s10_arm_safety_filter.launch"
left_nodes=$(roslaunch --nodes "$launch_path" side:=left start_filter:=true)
right_nodes=$(roslaunch --nodes "$launch_path" side:=right start_filter:=true)
disabled_nodes=$(roslaunch --nodes "$launch_path" side:=left start_filter:=false)
[[ "$left_nodes" == "/left_arm/safety_filter" ]]
[[ "$right_nodes" == "/right_arm/safety_filter" ]]
[[ -z "$disabled_nodes" ]]

if roslaunch --nodes "$launch_path" side:=invalid start_filter:=true >/dev/null 2>&1; then
  printf '%s\n' 'invalid side unexpectedly produced a launch graph' >&2
  exit 1
fi

printf '%s\n' '[PASS] S10 safety filter unit and replay contracts'
