#!/usr/bin/env bash
set -Eeuo pipefail
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
source /opt/ros/noetic/setup.bash --extend
source /home/mips/pika_ros/install/setup.bash --extend
source /home/mips/robot/pi05-upstream-ws/devel/setup.bash --extend
source "$repo_root/devel/setup.bash" --extend
source "$repo_root/.venv/bin/activate"
# Select only the official model, avoiding legacy package shadowing.
official_model=/home/mips/robot/pi05-upstream-src/piper_ros/src/piper_description
export ROS_PACKAGE_PATH="$official_model:$ROS_PACKAGE_PATH"
export ROS_MASTER_URI=http://localhost:11311
python - <<'PY'
import rosgraph
publishers,subscribers,services=rosgraph.Master('/pi05_left_start_check').getSystemState()
nodes={node for _,owners in publishers+subscribers+services for node in owners}
if any('piper' in node.lower() or 'teleop' in node.lower() for node in nodes):
    raise SystemExit('Stop existing arm drivers/teleoperation before starting the left arm.')
if not any(topic=='/pi05/pika_input/left/pose' and owners for topic,owners in publishers):
    raise SystemExit('Start the Pika input-only program first.')
PY
"$repo_root/scripts/configure_can.sh" check left
exec roslaunch pi05_left_teleop left_teleop.launch start:=true connect_driver:=true "$@"
