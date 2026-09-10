#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$script_dir/lib/common.sh"
# shellcheck source=scripts/lib/device_config.sh
source "$script_dir/lib/device_config.sh"

usage() {
  cat <<'EOF'
Usage: scripts/discover_devices.sh

Read-only discovery of SocketCAN interfaces and candidate Pika USB serial
devices. Output is limited to interface names, driver/bus-info and privacy-safe
udev path/VID/PID/driver fields. Device serial numbers are never queried or
printed. This command never invokes sudo or changes a device.
EOF
}

if (($#)); then
  case "$1" in
    -h|--help) usage; exit 0 ;;
    *) usage >&2; pi05_die 2 "unknown argument: $1" ;;
  esac
fi

for command_name in ip ethtool udevadm find; do
  pi05_require_command "$command_name"
done

pi05_log 'SocketCAN interfaces (read-only)'
can_count=0
while IFS= read -r interface; do
  [[ -n "$interface" ]] || continue
  can_count=$((can_count + 1))
  driver=$(pi05_can_driver "$interface")
  bus_info=$(pi05_can_bus_info "$interface")
  printf 'CAN interface=%s driver=%s bus-info=%s\n' \
    "$interface" "${driver:-unknown}" "${bus_info:-unavailable}"
done < <(pi05_can_interfaces)
((can_count > 0)) || printf 'CAN none\n'

pi05_log 'USB serial candidates (read-only; serial-number fields omitted)'
serial_count=0
while IFS= read -r device; do
  [[ -n "$device" ]] || continue
  serial_count=$((serial_count + 1))
  printf 'SERIAL device=%s id-path=%s vid=%s pid=%s driver=%s\n' \
    "$device" \
    "$(pi05_udev_property "$device" ID_PATH || true)" \
    "$(pi05_udev_property "$device" ID_VENDOR_ID || true)" \
    "$(pi05_udev_property "$device" ID_MODEL_ID || true)" \
    "$(pi05_udev_property "$device" ID_USB_DRIVER || true)"
done < <(pi05_serial_devices)
((serial_count > 0)) || printf 'SERIAL none\n'
