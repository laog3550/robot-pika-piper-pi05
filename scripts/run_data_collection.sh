#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/run_data_collection.sh --dataset-name NAME [OPTIONS] --apply

Options:
  --task TEXT              Initial task description (also editable in the window).
  --duration SECONDS       Manipulation duration before recorded return-home (default: 30).
  --output-root PATH       Dataset parent (default: /home/mips/datasets/pi05).
  --top-rotation MODE      none, cw, ccw, or 180 (default: cw).
  --startup-only           Open the visual preflight UI; never enable or move either arm.
  --apply                  Required acknowledgement that this entry point can move hardware.

One process remains open for repeated episodes. Edit task and duration directly in
the window. F marks failure but continues to the timer; timer expiry is otherwise
success. Arms remain enabled between episodes; E manually disables them. Use
buttons or SPACE/S/F/D/E/Q/X; F5 retries camera discovery.
EOF
}

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
config_file="$repo_root/config/cameras.env"
dataset_name=''
apply=false
startup_only=false
collector_args=()

while (($#)); do
  case "$1" in
    --dataset-name)
      (($# >= 2)) || { usage >&2; exit 2; }
      dataset_name=$2
      collector_args+=("$1" "$2")
      shift
      ;;
    --task|--duration|--output-root|--top-rotation|--home-timeout|--home-tolerance|--stable-seconds)
      (($# >= 2)) || { usage >&2; exit 2; }
      collector_args+=("$1" "$2")
      shift
      ;;
    --startup-only)
      startup_only=true
      collector_args+=("$1")
      ;;
    --apply)
      apply=true
      collector_args+=("$1")
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
  shift
done

[[ -n "$dataset_name" ]] || { usage >&2; echo '--dataset-name is required' >&2; exit 2; }
[[ "$apply" == true ]] || { usage >&2; echo '--apply is required' >&2; exit 2; }
[[ -r "$config_file" ]] || {
  echo "camera configuration missing: $config_file" >&2
  exit 3
}

source /opt/ros/noetic/setup.bash --extend
source /home/mips/pika_ros/install/setup.bash --extend
source /home/mips/robot/pi05-upstream-ws/devel/setup.bash --extend
source "$repo_root/devel/setup.bash" --extend
source "$repo_root/.venv/bin/activate"
export PYTHONPATH="$repo_root/src/pi05_data_collection/src${PYTHONPATH:+:$PYTHONPATH}"

"$script_dir/check_cameras.sh" --config "$config_file"

# shellcheck source=scripts/lib/device_config.sh
source "$script_dir/lib/device_config.sh"
pi05_load_device_config "$repo_root/config/pi05.env"
pi05_validate_dual_identity_separation
"$script_dir/configure_pika_serial.sh" check left
"$script_dir/configure_pika_serial.sh" check right

check_pika_device_free() {
  local side=$1 device=$2 resolved holders holder_csv
  resolved=$(readlink -f "$device")
  holders=$(fuser "$resolved" 2>/dev/null || true)
  if [[ -n "${holders//[[:space:]]/}" ]]; then
    echo "$side Pika device is already locked by another session: $device -> $resolved" >&2
    echo "Refusing to start a second control stack. Manually disable both arms before" >&2
    echo "stopping the stale session, then retry data collection." >&2
    # Show only process identity and command; never read or print serial data.
    holder_csv=$(tr ' ' '\n' <<<"$holders" | sed '/^$/d' | paste -sd, -)
    [[ -n "$holder_csv" ]] &&
      ps -o pid=,ppid=,pgid=,stat=,comm=,args= -p "$holder_csv" >&2 || true
    return 1
  fi
}

check_pika_device_free left /dev/pi05-pika-left || exit 3
check_pika_device_free right /dev/pi05-pika-right || exit 3

python "$repo_root/src/pi05_data_collection/scripts/collector_node.py" \
  "${collector_args[@]}" --camera-config "$config_file" --help >/dev/null

log_file="/tmp/pi05-data-collection-$$.log"
setsid "$script_dir/start_teleop.sh" dual \
  auto_enable:=false smooth_commands:=true enable_gripper_teleop:=true \
  left_pika_gripper_device:=/dev/pi05-pika-left \
  right_pika_gripper_device:=/dev/pi05-pika-right >"$log_file" 2>&1 &
launch_pid=$!

stop_launch() {
  if kill -0 "$launch_pid" 2>/dev/null; then
    kill -INT -- "-$launch_pid" 2>/dev/null || true
    wait "$launch_pid" 2>/dev/null || true
  fi
}

interrupted=false
trap 'interrupted=true' INT
ready=false
for _attempt in $(seq 1 300); do
  if [[ "$interrupted" == true ]]; then
    stop_launch
    exit 130
  fi
  if ! kill -0 "$launch_pid" 2>/dev/null; then
    wait "$launch_pid" 2>/dev/null || true
    echo "dual teleop exited during startup; log: $log_file" >&2
    tail -100 "$log_file" >&2
    exit 3
  fi
  if rosservice list 2>/dev/null | grep -Fxq /left_arm/teleop/joint_command_smoother/set_enabled &&
     rosservice list 2>/dev/null | grep -Fxq /right_arm/teleop/joint_command_smoother/set_enabled; then
    ready=true
    break
  fi
  sleep 0.1
done
if [[ "$ready" != true ]]; then
  stop_launch
  echo "dual teleop did not become ready; log: $log_file" >&2
  tail -100 "$log_file" >&2
  exit 3
fi

trap '' INT
set +e
(trap - INT; python "$repo_root/src/pi05_data_collection/scripts/collector_node.py" \
  "${collector_args[@]}" --camera-config "$config_file")
status=$?
set -e

if ((status == 0)); then
  stop_launch
  if [[ "$startup_only" == true ]]; then
    echo 'Data-collection startup-only UI closed; nodes stopped.'
  else
    echo 'Data-collection session completed; arms reported safely disabled.'
  fi
  echo "Launch log: $log_file"
  exit 0
fi

if ((status < 4)); then
  stop_launch
  echo "Collector failed before reporting an enabled-arm hazard; log: $log_file" >&2
  exit "$status"
fi

echo "Collector locked or failed while an arm may remain enabled." >&2
echo "Teleop nodes remain running as PID $launch_pid; inspect the arms before stopping them." >&2
echo "Launch log: $log_file" >&2
exit "$status"
