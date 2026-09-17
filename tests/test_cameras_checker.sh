#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
checker="$repo_root/scripts/check_cameras.sh"

bash -n "$checker"
"$checker" --help >/dev/null
if "$checker" --invalid >/dev/null 2>&1; then
  printf 'camera checker unexpectedly accepted an invalid option\n' >&2
  exit 1
fi

test_root=$(mktemp -d /tmp/pi05-cameras-test.XXXXXX)
trap 'rm -rf -- "$test_root"' EXIT

sysfs="$test_root/sysfs"
udev="$test_root/udev"
mkdir -p "$sysfs/bus/usb/devices" "$udev"

# --- fixture helpers ---------------------------------------------------------

add_device() {
  local port="$1" vid="$2" pid="$3" product="$4" speed="$5" serial="$6"
  local dir="$sysfs/bus/usb/devices/$port"
  mkdir -p "$dir"
  printf '%s\n' "$vid" >"$dir/idVendor"
  printf '%s\n' "$pid" >"$dir/idProduct"
  printf '%s\n' "$product" >"$dir/product"
  printf '%s\n' "$speed" >"$dir/speed"
  if [[ -n "$serial" ]]; then
    printf '%s\n' "$serial" >"$dir/serial"
  fi
}

add_uvc_interface() {
  local port="$1" nodes="$2" bind_driver="$3"
  local iface="$sysfs/bus/usb/devices/$port:1.0"
  mkdir -p "$iface"
  printf '0e\n' >"$iface/bInterfaceClass"
  if [[ "$bind_driver" == true ]]; then
    ln -s /sys/bus/usb/drivers/uvcvideo "$iface/driver"
    mkdir -p "$iface/video4linux"
    local offset=0 node
    for node in $nodes; do
      : >"$iface/video4linux/$node"
      offset=$((offset + 1))
    done
  fi
}

# Left wrist: colour half bound to uvcvideo, depth half bare (OpenNI protocol).
add_device 1-2.2.2 2bc5 0557 'Dabai DC1' 480 FIXTURE-LEFT-1
add_uvc_interface 1-2.2.2 'video8 video9' true
add_device 1-2.2.4 2bc5 0657 'ORBBEC Depth Sensor' 480 ''
# Right wrist: colour half currently taken over by the Orbbec SDK (no driver).
add_device 1-7.2 2bc5 0557 'Dabai DC1' 480 FIXTURE-RIGHT-1
add_uvc_interface 1-7.2 '' false
add_device 1-7.4 2bc5 0657 'ORBBEC Depth Sensor' 480 ''
# Top camera on a USB3 port.
add_device 2-5 8086 0b5c 'Intel(R) RealSense(TM) Depth Camera 455 ' 5000 FIXTURE-TOP-1

cat >"$udev/c81:8" <<EOF
S:video8
S:v4l/by-id/usb-Fixture_Dabai_DC1_FIXTURE-LEFT-1-video-index0
E:ID_SERIAL_SHORT=FIXTURE-LEFT-1
EOF

valid="$test_root/cameras.env"
sed \
  -e 's/^PI05_CAMERA_LEFT_WRIST_RGB_USB_PORT=$/PI05_CAMERA_LEFT_WRIST_RGB_USB_PORT=1-2.2.2/' \
  -e 's/^PI05_CAMERA_LEFT_WRIST_DEPTH_USB_PORT=$/PI05_CAMERA_LEFT_WRIST_DEPTH_USB_PORT=1-2.2.4/' \
  -e 's/^PI05_CAMERA_LEFT_WRIST_SERIAL=$/PI05_CAMERA_LEFT_WRIST_SERIAL=FIXTURE-LEFT-1/' \
  -e 's/^PI05_CAMERA_RIGHT_WRIST_RGB_USB_PORT=$/PI05_CAMERA_RIGHT_WRIST_RGB_USB_PORT=1-7.2/' \
  -e 's/^PI05_CAMERA_RIGHT_WRIST_DEPTH_USB_PORT=$/PI05_CAMERA_RIGHT_WRIST_DEPTH_USB_PORT=1-7.4/' \
  -e 's/^PI05_CAMERA_RIGHT_WRIST_SERIAL=$/PI05_CAMERA_RIGHT_WRIST_SERIAL=FIXTURE-RIGHT-1/' \
  -e 's/^PI05_CAMERA_TOP_USB_PORT=$/PI05_CAMERA_TOP_USB_PORT=2-5/' \
  -e 's/^PI05_CAMERA_TOP_SERIAL=$/PI05_CAMERA_TOP_SERIAL=FIXTURE-TOP-1/' \
  "$repo_root/config/cameras.env.example" >"$valid"

run_checker() {
  "$checker" --config "$1" --sysfs-root "$sysfs" --udev-root "$udev"
}

# --- happy path --------------------------------------------------------------

output=$(run_checker "$valid" 2>&1)
printf '%s\n' "$output" | grep -q '左腕部相机' ||
  { printf 'checker did not report the left wrist camera\n' >&2; exit 1; }
printf '%s\n' "$output" | grep -q '顶部相机' ||
  { printf 'checker did not report the top camera\n' >&2; exit 1; }
printf '%s\n' "$output" | grep -qi 'OK.*v4l/by-id' ||
  { printf 'checker did not confirm the stable by-id name\n' >&2; exit 1; }

# Privacy contract: the recorded serial number must never be printed.
if printf '%s\n' "$output" | grep -q 'FIXTURE-LEFT-1\|FIXTURE-RIGHT-1\|FIXTURE-TOP-1'; then
  printf 'checker leaked a full serial number\n' >&2
  exit 1
fi

# --- mismatch cases ----------------------------------------------------------

wrong_port="$test_root/wrong-port.env"
sed 's/^PI05_CAMERA_LEFT_WRIST_RGB_USB_PORT=1-2.2.2$/PI05_CAMERA_LEFT_WRIST_RGB_USB_PORT=1-9.9.9/' \
  "$valid" >"$wrong_port"
if run_checker "$wrong_port" >/dev/null 2>&1; then
  printf 'checker unexpectedly accepted a missing colour port\n' >&2
  exit 1
fi

cross_wired="$test_root/cross-wired.env"
sed 's/^PI05_CAMERA_LEFT_WRIST_RGB_USB_PORT=1-2.2.2$/PI05_CAMERA_LEFT_WRIST_RGB_USB_PORT=1-7.2/' \
  "$valid" >"$cross_wired"
if run_checker "$cross_wired" >/dev/null 2>&1; then
  printf 'checker unexpectedly accepted swapped left/right cameras\n' >&2
  exit 1
fi

split_hub="$test_root/split-hub.env"
sed 's/^PI05_CAMERA_LEFT_WRIST_DEPTH_USB_PORT=1-2.2.4$/PI05_CAMERA_LEFT_WRIST_DEPTH_USB_PORT=1-7.4/' \
  "$valid" >"$split_hub"
if run_checker "$split_hub" >/dev/null 2>&1; then
  printf 'checker unexpectedly accepted a depth half on another hub\n' >&2
  exit 1
fi

printf '480\n' >"$sysfs/bus/usb/devices/2-5/speed"
if run_checker "$valid" >/dev/null 2>&1; then
  printf 'checker unexpectedly accepted a top camera on USB2\n' >&2
  exit 1
fi
printf '5000\n' >"$sysfs/bus/usb/devices/2-5/speed"

# --- configuration safety ----------------------------------------------------

unknown_key="$test_root/unknown-key.env"
sed 's/^PI05_CAMERA_TOP_REQUIRE_USB3=true$/PI05_CAMERA_UNKNOWN_KEY=1/' "$valid" >"$unknown_key"
if run_checker "$unknown_key" >/dev/null 2>&1; then
  printf 'checker unexpectedly accepted an unknown configuration key\n' >&2
  exit 1
fi

injection="$test_root/injection.env"
sed 's/^PI05_CAMERA_TOP_REQUIRE_USB3=true$/PI05_CAMERA_TOP_REQUIRE_USB3=$(touch\/tmp\/bad)/' \
  "$valid" >"$injection"
if run_checker "$injection" >/dev/null 2>&1; then
  printf 'checker unexpectedly accepted executable content\n' >&2
  exit 1
fi

if run_checker "$test_root/missing.env" >/dev/null 2>&1; then
  printf 'checker unexpectedly accepted a missing record\n' >&2
  exit 1
fi

# --- discovery mode ----------------------------------------------------------

discover_output=$("$checker" --discover --sysfs-root "$sysfs" --udev-root "$udev" 2>&1)
printf '%s\n' "$discover_output" | grep -q '2bc5:0657' ||
  { printf 'discover mode did not list the Dabai depth half\n' >&2; exit 1; }
if printf '%s\n' "$discover_output" | grep -q 'FIXTURE-LEFT-1'; then
  printf 'discover mode leaked a full serial number\n' >&2
  exit 1
fi

printf 'camera mapping checker tests: PASS\n'
