#!/usr/bin/env bash
set -Eeuo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source /opt/ros/noetic/setup.bash
source /home/mips/pika_ros/install/setup.bash --extend
source /home/mips/robot/pi05-upstream-ws/devel/setup.bash --extend
source "$repo_root/devel/setup.bash" --extend
source "$repo_root/.venv/bin/activate"
# Select this one reviewed model package, not the whole upstream ROS tree.
replay_model_package=/home/mips/robot/pi05-upstream-src/piper_ros/src/piper_description
export ROS_PACKAGE_PATH="$replay_model_package:$repo_root/src${ROS_PACKAGE_PATH:+:$ROS_PACKAGE_PATH}"
export ROS_MASTER_URI=http://localhost:11333
python - <<'PY'
import socket
s=socket.socket();s.settimeout(.2)
busy=s.connect_ex(('127.0.0.1',11333))==0;s.close()
if busy:raise RuntimeError('Isolated replay port 11333 already in use')
PY
roscore -p 11333 >/dev/null 2>&1 &
teleop_replay_core_pid=$!
cleanup() {
  kill -INT "$teleop_replay_core_pid" 2>/dev/null || true
  wait "$teleop_replay_core_pid" 2>/dev/null || true
}
trap cleanup EXIT
python - <<'PY'
import socket,time
for _ in range(50):
    s=socket.socket();s.settimeout(.1)
    ready=s.connect_ex(('127.0.0.1',11333))==0;s.close()
    if ready:break
    time.sleep(.1)
else:raise RuntimeError('Isolated replay Master unavailable')
PY
python "$repo_root/tests/replay_teleop_safety_pipeline.py"
