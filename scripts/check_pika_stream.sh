#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$script_dir/lib/common.sh"
# shellcheck source=scripts/lib/device_config.sh
source "$script_dir/lib/device_config.sh"

usage() {
  cat <<'EOF'
Usage: scripts/check_pika_stream.sh [--config PATH] [--duration SECONDS] <left|right>

Passively validate one Pika serial stream at the configured 460800 baud. The
checker opens the serial alias read-only, never transmits bytes, restores the
original terminal settings, and prints only aggregate frame statistics.

Exit status 0 requires at least 10 complete frames and a complete-frame ratio
of at least 0.95. Raw data and sensor values are never printed or saved.
EOF
}

repo_root=$(pi05_repo_root)
config_file="$repo_root/config/pi05.env"
duration=5
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
pi05_select_serial_config "$side"
pi05_validate_serial_config

[[ -c "$PI05_PIKA_SERIAL_ALIAS" ]] ||
  pi05_die 3 "configured $side Pika alias is not a character device"
[[ -r "$PI05_PIKA_SERIAL_ALIAS" ]] ||
  pi05_die 3 "configured $side Pika alias is not readable; verify dialout membership"

exec /usr/bin/python3 "$script_dir/check_pika_stream.py" \
  --device "$PI05_PIKA_SERIAL_ALIAS" \
  --label "$side" \
  --duration "$duration"
