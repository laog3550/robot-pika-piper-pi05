#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$script_dir/lib/common.sh"
# shellcheck source=scripts/lib/device_config.sh
source "$script_dir/lib/device_config.sh"

usage() {
  cat <<'EOF'
Usage: scripts/check_piper_can_stream.sh [--config PATH] [--duration SECONDS] <left|right>

Passively validate the configured Piper SocketCAN stream. The checker receives
frames only, prints no payload bytes, and fails if required feedback IDs are
missing or any known control/configuration ID is observed.
EOF
}

repo_root=$(pi05_repo_root)
config_file="$repo_root/config/pi05.env"
duration=3
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

exec /usr/bin/python3 "$script_dir/check_piper_can_stream.py" \
  --interface "$PI05_CAN_INTERFACE" \
  --label "$side" \
  --duration "$duration"
