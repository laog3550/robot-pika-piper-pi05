#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "usage: $0 <left|right> --apply [--duration SECONDS] [--home-timeout SECONDS]"
}

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
  usage
  exit 0
fi

side=${1:-}
if [[ "$side" != left && "$side" != right ]]; then
  usage >&2
  exit 2
fi
shift
startup_only=false
for argument in "$@"; do
  if [[ "$argument" == -h || "$argument" == --help ]]; then
    usage
    exit 0
  fi
  if [[ "$argument" == --startup-only ]]; then
    startup_only=true
  fi
done

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
source /opt/ros/noetic/setup.bash --extend
source /home/mips/pika_ros/install/setup.bash --extend
source /home/mips/robot/pi05-upstream-ws/devel/setup.bash --extend
source "$repo_root/devel/setup.bash" --extend
source "$repo_root/.venv/bin/activate"

python "$script_dir/run_smoothed_teleop.py" "$side" "$@" --check-only

log_file="/tmp/pi05-${side}-smoothed-teleop-$$.log"
setsid "$script_dir/start_teleop.sh" "$side" \
  auto_enable:=false smooth_commands:=true >"$log_file" 2>&1 &
launch_pid=$!

stop_launch() {
  if kill -0 "$launch_pid" 2>/dev/null; then
    kill -INT -- "-$launch_pid" 2>/dev/null || true
    wait "$launch_pid" 2>/dev/null || true
  fi
}

# Do not start the ROS session controller until start_teleop.sh has completed
# its conflict check. Registering the controller earlier makes that check see
# its own pending session as an existing teleop process.
gate_service="/${side}_arm/teleop/joint_command_smoother/set_enabled"
stack_ready=false
for _attempt in $(seq 1 200); do
  if ! kill -0 "$launch_pid" 2>/dev/null; then
    wait "$launch_pid" 2>/dev/null || true
    echo "Teleop stack exited during startup. Launch log: $log_file" >&2
    cat "$log_file" >&2
    exit 3
  fi
  if rosservice list 2>/dev/null | grep -Fxq "$gate_service"; then
    stack_ready=true
    break
  fi
  sleep 0.1
done
if [[ "$stack_ready" != true ]]; then
  stop_launch
  echo "Teleop stack did not become ready. Launch log: $log_file" >&2
  cat "$log_file" >&2
  exit 3
fi

# Ctrl-C is handled by the Python session controller so it can return home.
trap '' INT
set +e
(trap - INT; python "$script_dir/run_smoothed_teleop.py" "$side" "$@")
session_status=$?
set -e

if ((session_status == 0)); then
  stop_launch
  if [[ "$startup_only" == true ]]; then
    echo "Startup-only validation completed; arm was not enabled and nodes were stopped."
  else
    echo "Completed: teleop closed, home confirmed, arm disabled, nodes stopped."
  fi
  echo "Launch log: $log_file"
  exit 0
fi

if ((session_status < 4)); then
  stop_launch
  echo "Session ended without reporting an enabled arm; nodes were stopped. Launch log: $log_file" >&2
  exit "$session_status"
fi

echo "Session did not complete safely; teleop nodes are left running (PID $launch_pid)." >&2
echo "Inspect the arm before stopping them. Launch log: $log_file" >&2
exit "$session_status"
