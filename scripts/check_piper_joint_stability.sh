#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$script_dir/lib/common.sh"
# shellcheck source=scripts/lib/device_config.sh
source "$script_dir/lib/device_config.sh"

usage() {
  cat <<'EOF'
Usage: scripts/check_piper_joint_stability.sh [--config PATH] [--duration SECONDS]
                                                [--exclude-joint 1..6] <left|right>

Passively report per-joint Piper feedback ranges. This command never transmits
CAN frames and never prints or saves absolute positions or payload bytes.
EOF
}

repo_root=$(pi05_repo_root)
config_file="$repo_root/config/pi05.env"
duration=5
exclude_joint=
side=

while (($#)); do
  case "$1" in
    --config)
      (($# >= 2)) || pi05_die 2 '--config requires a path'
      config_file=$2
      shift 2
      ;;
    --duration)
      (($# >= 2)) || pi05_die 2 '--duration requires seconds'
      duration=$2
      shift 2
      ;;
    --exclude-joint)
      (($# >= 2)) || pi05_die 2 '--exclude-joint requires 1..6'
      exclude_joint=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    left|right)
      [[ -z "$side" ]] || pi05_die 2 'side may be specified only once'
      side=$1
      shift
      ;;
    *)
      usage >&2
      pi05_die 2 "unknown argument: $1"
      ;;
  esac
done

[[ -n "$side" ]] || {
  usage >&2
  pi05_die 2 'side must be left or right'
}

pi05_load_device_config "$config_file"
pi05_validate_dual_identity_separation
pi05_select_can_config "$side"
pi05_validate_can_config
"$script_dir/configure_can.sh" check "$side" >/dev/null

args=(--interface "$PI05_CAN_INTERFACE" --label "$side" --duration "$duration")
if [[ -n "$exclude_joint" ]]; then
  args+=(--exclude-joint "$exclude_joint")
fi
exec /usr/bin/python3 "$script_dir/check_piper_joint_stability.py" "${args[@]}"
