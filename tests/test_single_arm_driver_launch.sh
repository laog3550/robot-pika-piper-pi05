#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
launch_path="${repo_root}/src/pi05_control/launch/s09_single_arm_driver.launch"

/usr/bin/python3 -m unittest \
  "${repo_root}/src/pi05_control/test/test_single_arm_driver_launch.py"

source /opt/ros/noetic/setup.bash

left_nodes=$(roslaunch --nodes "$launch_path" side:=left start_driver:=true)
right_nodes=$(roslaunch --nodes "$launch_path" side:=right start_driver:=true)
disabled_nodes=$(roslaunch --nodes "$launch_path" side:=left start_driver:=false)
[[ "$left_nodes" == "/left_arm/piper_driver_raw" ]]
[[ "$right_nodes" == "/right_arm/piper_driver_raw" ]]
[[ -z "$disabled_nodes" ]]

if roslaunch --nodes "$launch_path" side:=invalid start_driver:=true >/dev/null 2>&1; then
  printf '%s\n' 'invalid side unexpectedly produced a launch graph' >&2
  exit 1
fi

if rg -n '<(include|node)[^>]+(start_double_piper|start_single_piper)' "$launch_path"; then
  printf '%s\n' 'S09 wrapper must not include unsafe upstream launch defaults' >&2
  exit 1
fi

printf '%s\n' '[PASS] S09 single-arm driver launch isolation'
