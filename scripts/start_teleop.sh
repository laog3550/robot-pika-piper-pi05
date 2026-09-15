#!/usr/bin/env bash
set -Eeuo pipefail
side=${1:?usage: start_teleop.sh <left|right|dual> [roslaunch args...]}
shift
case "$side" in left|right|dual) ;; *) echo "side must be left, right or dual" >&2; exit 2;; esac
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
source /opt/ros/noetic/setup.bash --extend
source /home/mips/pika_ros/install/setup.bash --extend
source /home/mips/robot/pi05-upstream-ws/devel/setup.bash --extend
source "$repo_root/devel/setup.bash" --extend
source "$repo_root/.venv/bin/activate"
official_model=/home/mips/robot/pi05-upstream-src/piper_ros/src/piper_description
export ROS_PACKAGE_PATH="$official_model:$ROS_PACKAGE_PATH"
export ROS_MASTER_URI=http://localhost:11311
PI05_TELEOP_SIDE="$side" python - <<'PY'
import os
import rosgraph
side=os.environ['PI05_TELEOP_SIDE']
publishers,subscribers,services=rosgraph.Master('/pi05_teleop_start_check').getSystemState()
nodes={node for _,owners in publishers+subscribers+services for node in owners}
if any('piper' in node.lower() or 'teleop' in node.lower() for node in nodes):
    raise SystemExit('Stop existing arm drivers/teleoperation before starting.')
required=('left','right') if side=='dual' else (side,)
missing=[item for item in required if not any(
    topic=='/pi05/pika_input/'+item+'/pose' and owners for topic,owners in publishers)]
if missing:
    raise SystemExit('Start Pika input-only first; missing pose: '+','.join(missing))
PY
if [[ "$side" == dual ]]; then
  "$repo_root/scripts/configure_can.sh" check left
  "$repo_root/scripts/configure_can.sh" check right
  exec roslaunch pi05_left_teleop dual_teleop.launch start:=true connect_drivers:=true "$@"
fi
"$repo_root/scripts/configure_can.sh" check "$side"
exec roslaunch pi05_left_teleop "${side}_teleop.launch" start:=true connect_driver:=true "$@"
