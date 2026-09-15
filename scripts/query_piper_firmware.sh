#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$script_dir/lib/common.sh"
# shellcheck source=scripts/lib/device_config.sh
source "$script_dir/lib/device_config.sh"

usage() {
  cat <<'EOF'
Usage: scripts/query_piper_firmware.sh [--config PATH]
       check <left|right>
       apply <left|right> --confirm-query-only

check validates the selected CAN identity and prints the planned query without
transmitting CAN. apply uses the pinned piper_sdk initialization queries
(0x472 and 0x4AF) and prints only the firmware version. It never enables the
arm and never sends mode, joint, gripper, reset or stop commands.
EOF
}

repo_root=$(pi05_repo_root)
config_file="$repo_root/config/pi05.env"
action=
side=
confirmed=false

while (($#)); do
  case "$1" in
    --config)
      (($# >= 2)) || pi05_die 2 '--config requires a path'
      config_file=$2
      shift 2
      ;;
    check|apply)
      [[ -z "$action" ]] || pi05_die 2 'action may be specified only once'
      action=$1
      shift
      ;;
    left|right)
      [[ -z "$side" ]] || pi05_die 2 'side may be specified only once'
      side=$1
      shift
      ;;
    --confirm-query-only)
      confirmed=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      pi05_die 2 "unknown argument: $1"
      ;;
  esac
done

[[ -n "$action" && -n "$side" ]] || {
  usage >&2
  pi05_die 2 'action and side are required'
}

pi05_load_device_config "$config_file"
pi05_validate_dual_identity_separation
pi05_select_can_config "$side"
pi05_validate_can_config
"$script_dir/configure_can.sh" check "$side" >/dev/null

pi05_log "$side firmware query plan: transmit SDK query IDs 0x472 and 0x4AF; no enable or motion"
if [[ "$action" == check ]]; then
  [[ "$confirmed" == false ]] || pi05_die 2 '--confirm-query-only is valid only with apply'
  exit 0
fi
[[ "$confirmed" == true ]] || pi05_die 2 'apply requires --confirm-query-only'

running_control=$(ps -eo comm=,args= | awk '
  $1 ~ /^(roscore|rosmaster|roslaunch)$/ ||
  ($1 !~ /^(bash|sh|timeout|awk)$/ &&
   $0 ~ /piper_ctrl_single_node.py/) {
    print
  }
')
[[ -z "$running_control" ]] ||
  pi05_die 3 'refusing firmware query while ROS or Piper control processes are running'
[[ -x "$repo_root/.venv/bin/python" ]] || pi05_die 3 'Python 3.8 venv is missing'

exec "$repo_root/.venv/bin/python" "$script_dir/query_piper_firmware.py" \
  --interface "$PI05_CAN_INTERFACE"
