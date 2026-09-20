#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/restore_wrist_uvc.sh <left|right> --apply

Rebind only the configured Dabai DC1 RGB USB interfaces to uvcvideo. The
configured physical port, VID:PID and serial are verified before sudo is used.
This does not start Orbbec SDK or any camera stream.
EOF
}

[[ $# == 2 ]] || { usage >&2; exit 2; }
side=$1
[[ "$side" == left || "$side" == right ]] || { usage >&2; exit 2; }
[[ "$2" == --apply ]] || { usage >&2; echo '--apply is required' >&2; exit 2; }

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
config_file="$repo_root/config/cameras.env"
"$script_dir/check_cameras.sh" --config "$config_file" >/dev/null

# check_cameras.sh has already validated the restricted KEY=VALUE grammar.
# shellcheck disable=SC1090
source "$config_file"
if [[ "$side" == left ]]; then
  usb_port=$PI05_CAMERA_LEFT_WRIST_RGB_USB_PORT
  serial=$PI05_CAMERA_LEFT_WRIST_SERIAL
else
  usb_port=$PI05_CAMERA_RIGHT_WRIST_RGB_USB_PORT
  serial=$PI05_CAMERA_RIGHT_WRIST_SERIAL
fi

device="/sys/bus/usb/devices/$usb_port"
[[ -d "$device" ]] || { echo "configured $side wrist RGB device is offline: $usb_port" >&2; exit 3; }
[[ "$(<"$device/idVendor")" == 2bc5 && "$(<"$device/idProduct")" == 0557 ]] || {
  echo "refusing to bind: $usb_port is not Dabai RGB 2bc5:0557" >&2
  exit 3
}
[[ "$(<"$device/serial")" == "$serial" ]] || {
  echo "refusing to bind: configured $side wrist serial does not match $usb_port" >&2
  exit 3
}

bus=$(<"$device/busnum")
number=$(<"$device/devnum")
usb_node=$(printf '/dev/bus/usb/%03d/%03d' "$bus" "$number")
if command -v fuser >/dev/null && fuser "$usb_node" >/dev/null 2>&1; then
  echo "refusing to bind: a process is using $usb_node" >&2
  fuser -v "$usb_node" >&2 || true
  exit 3
fi

interfaces=("$usb_port:1.0" "$usb_port:1.1")
for interface in "${interfaces[@]}"; do
  path="/sys/bus/usb/devices/$interface"
  [[ -d "$path" && "$(<"$path/bInterfaceClass")" == 0e ]] || {
    echo "refusing to bind: expected UVC interface is missing: $interface" >&2
    exit 3
  }
  if [[ -L "$path/driver" && "$(basename "$(readlink -f "$path/driver")")" != uvcvideo ]]; then
    echo "refusing to replace another driver on $interface" >&2
    exit 3
  fi
done

sudo modprobe uvcvideo
for interface in "${interfaces[@]}"; do
  path="/sys/bus/usb/devices/$interface"
  if [[ ! -L "$path/driver" ]]; then
    printf '%s' "$interface" | sudo tee /sys/bus/usb/drivers/uvcvideo/bind >/dev/null
  fi
done
udevadm settle

deadline=$((SECONDS + 5))
found=''
while ((SECONDS < deadline)); do
  for node in /dev/video*; do
    [[ -c "$node" ]] || continue
    node_serial=$(udevadm info --query=property --name="$node" 2>/dev/null |
      sed -n 's/^ID_SERIAL_SHORT=//p')
    [[ "$node_serial" == "$serial" ]] || continue
    if v4l2-ctl --device="$node" --list-formats 2>/dev/null | grep -Fq "'MJPG'"; then
      found=$node
      break 2
    fi
  done
  sleep 0.1
done
[[ -n "$found" ]] || {
  echo "uvcvideo was bound but no configured MJPG node appeared" >&2
  exit 3
}

echo "[PI05] $side wrist UVC restored at $found (serial verified)."
"$script_dir/check_cameras.sh" --config "$config_file"
