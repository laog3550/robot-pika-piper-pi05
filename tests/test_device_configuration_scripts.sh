#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
scripts=(
  scripts/discover_devices.sh
  scripts/configure_can.sh
  scripts/configure_pika_serial.sh
)

for relative_path in "${scripts[@]}" scripts/lib/device_config.sh; do
  bash -n "$repo_root/$relative_path"
done
for relative_path in "${scripts[@]}"; do
  "$repo_root/$relative_path" --help >/dev/null
  if "$repo_root/$relative_path" --invalid >/dev/null 2>&1; then
    printf 'expected invalid option to fail: %s\n' "$relative_path" >&2
    exit 1
  fi
done

test_root=$(mktemp -d /tmp/pi05-device-test.XXXXXX)
trap 'rm -rf -- "$test_root"' EXIT
fake_bin="$test_root/bin"
mkdir -p "$fake_bin"
sudo_marker="$test_root/sudo-called"

cat >"$fake_bin/ip" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == '-brief link show type can' ]]; then
  printf 'can0 DOWN <NOARP,ECHO>\n'
  printf 'can1 DOWN <NOARP,ECHO>\n'
  [[ "${MOCK_CAN_MODE:-}" == ambiguous ]] && printf 'can2 DOWN <NOARP,ECHO>\n'
elif [[ "$*" == '-details link show dev can0' ]]; then
  printf '2: can0: <NOARP,UP,LOWER_UP,ECHO> state UP mode DEFAULT\n    can state ERROR-ACTIVE bitrate 1000000\n'
elif [[ "$*" == '-details link show dev can1' ]]; then
  printf '3: can1: <NOARP,UP,LOWER_UP,ECHO> state UP mode DEFAULT\n    can state ERROR-ACTIVE bitrate 1000000\n'
elif [[ "$*" == 'link show dev can0' || "$*" == 'link show dev can1' ]]; then
  exit 0
else
  exit 1
fi
EOF
cat >"$fake_bin/ethtool" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *can1 ]]; then
  printf 'driver: gs_usb\nbus-info: 8-8\n'
else
  printf 'driver: gs_usb\nbus-info: 9-9\n'
fi
EOF
cat >"$fake_bin/find" <<'EOF'
#!/usr/bin/env bash
printf '/dev/ttyUSB0\n'
printf '/dev/ttyUSB1\n'
[[ "${MOCK_SERIAL_MODE:-}" == ambiguous ]] && printf '/dev/ttyUSB2\n'
EOF
cat >"$fake_bin/udevadm" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *ttyUSB1 ]]; then
  printf 'ID_PATH=pci-0000:ff:ff.f-usb-0:8.8:1.0\n'
else
  printf 'ID_PATH=pci-0000:ff:ff.f-usb-0:9.9:1.0\n'
fi
printf 'ID_VENDOR_ID=dead\nID_MODEL_ID=beef\nID_USB_DRIVER=test_uart\n'
printf 'ID_SERIAL=must-never-be-printed\n'
EOF
cat >"$fake_bin/readlink" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *'/sys/class/net/'* ]]; then
  if [[ "$*" == *can1* ]]; then
    printf '/sys/devices/pci-test/usb8/8-8\n'
  else
    printf '/sys/devices/pci-test/usb9/9-9\n'
  fi
  exit 0
fi
/usr/bin/readlink "$@"
EOF
cat >"$fake_bin/sudo" <<EOF
#!/usr/bin/env bash
printf called >'$sudo_marker'
exit 99
EOF
chmod +x "$fake_bin"/*

config="$test_root/pi05.env"
cat >"$config" <<'EOF'
PI05_ROS_DISTRO=noetic
PI05_LEFT_CAN_INTERFACE=can0
PI05_LEFT_CAN_BITRATE=1000000
PI05_LEFT_CAN_USB_BUS_INFO=9-9
PI05_RIGHT_CAN_INTERFACE=can1
PI05_RIGHT_CAN_BITRATE=1000000
PI05_RIGHT_CAN_USB_BUS_INFO=8-8
PI05_LEFT_PIKA_SERIAL_ALIAS=/dev/pi05-pika-left
PI05_LEFT_PIKA_SERIAL_BAUD=460800
PI05_LEFT_PIKA_SERIAL_ID_PATH=pci-0000:ff:ff.f-usb-0:9.9:1.0
PI05_LEFT_PIKA_SERIAL_VENDOR_ID=dead
PI05_LEFT_PIKA_SERIAL_MODEL_ID=beef
PI05_RIGHT_PIKA_SERIAL_ALIAS=/dev/pi05-pika-right
PI05_RIGHT_PIKA_SERIAL_BAUD=460800
PI05_RIGHT_PIKA_SERIAL_ID_PATH=pci-0000:ff:ff.f-usb-0:8.8:1.0
PI05_RIGHT_PIKA_SERIAL_VENDOR_ID=dead
PI05_RIGHT_PIKA_SERIAL_MODEL_ID=beef
PI05_ARM_MODE=dual
PI05_AUTO_ENABLE=false
EOF

PATH="$fake_bin:$PATH" "$repo_root/scripts/discover_devices.sh" >"$test_root/discovery.out"
grep -q 'bus-info=9-9' "$test_root/discovery.out"
grep -q 'id-path=pci-0000:ff:ff.f-usb-0:9.9:1.0 vid=dead pid=beef driver=test_uart' "$test_root/discovery.out"
! grep -q 'must-never-be-printed\|ID_SERIAL' "$test_root/discovery.out"
[[ ! -e "$sudo_marker" ]]

PATH="$fake_bin:$PATH" "$repo_root/scripts/configure_can.sh" check left --config "$config" >/dev/null
PATH="$fake_bin:$PATH" "$repo_root/scripts/configure_can.sh" check right --config "$config" >/dev/null
if PATH="$fake_bin:$PATH" "$repo_root/scripts/configure_can.sh" check left --config "$config" --yes >/dev/null 2>&1; then
  printf 'CAN check unexpectedly accepted --yes\n' >&2
  exit 1
fi
if PATH="$fake_bin:$PATH" "$repo_root/scripts/configure_can.sh" apply left --config "$config" </dev/null >/dev/null 2>&1; then
  printf 'non-interactive CAN apply unexpectedly passed without --yes\n' >&2
  exit 1
fi
[[ ! -e "$sudo_marker" ]] || { printf 'unconfirmed CAN apply invoked sudo\n' >&2; exit 1; }
if MOCK_CAN_MODE=ambiguous PATH="$fake_bin:$PATH" \
  "$repo_root/scripts/configure_can.sh" apply left --config "$config" --yes >/dev/null 2>&1; then
  printf 'ambiguous CAN identity unexpectedly reached apply\n' >&2
  exit 1
fi
[[ ! -e "$sudo_marker" ]] || { printf 'ambiguous CAN identity invoked sudo\n' >&2; exit 1; }

if PATH="$fake_bin:$PATH" "$repo_root/scripts/configure_pika_serial.sh" check left --config "$config" >/dev/null 2>&1; then
  printf 'serial check unexpectedly passed without its alias\n' >&2
  exit 1
fi
selected_right_alias=$(bash -c '
  source "$1/scripts/lib/common.sh"
  source "$1/scripts/lib/device_config.sh"
  pi05_load_device_config "$2"
  pi05_select_serial_config right
  printf "%s" "$PI05_PIKA_SERIAL_ALIAS"
' _ "$repo_root" "$config")
[[ "$selected_right_alias" == /dev/pi05-pika-right ]] || {
  printf 'right serial configuration selected the wrong alias\n' >&2
  exit 1
}
if PATH="$fake_bin:$PATH" "$repo_root/scripts/configure_pika_serial.sh" apply left --config "$config" </dev/null >/dev/null 2>&1; then
  printf 'non-interactive serial apply unexpectedly passed without --yes\n' >&2
  exit 1
fi
[[ ! -e "$sudo_marker" ]] || { printf 'unconfirmed serial apply invoked sudo\n' >&2; exit 1; }
if MOCK_SERIAL_MODE=ambiguous PATH="$fake_bin:$PATH" \
  "$repo_root/scripts/configure_pika_serial.sh" apply left --config "$config" --yes >/dev/null 2>&1; then
  printf 'ambiguous serial identity unexpectedly reached apply\n' >&2
  exit 1
fi
[[ ! -e "$sudo_marker" ]] || { printf 'ambiguous serial identity invoked sudo\n' >&2; exit 1; }

unsafe_config="$test_root/unsafe.env"
cat >"$unsafe_config" <<EOF
PI05_LEFT_CAN_INTERFACE=\$(touch $test_root/executed)
EOF
if PATH="$fake_bin:$PATH" "$repo_root/scripts/configure_can.sh" check left --config "$unsafe_config" >/dev/null 2>&1; then
  printf 'unsafe configuration unexpectedly passed\n' >&2
  exit 1
fi
[[ ! -e "$test_root/executed" ]] || { printf 'configuration content was executed\n' >&2; exit 1; }

collision_config="$test_root/collision.env"
sed 's/PI05_RIGHT_CAN_USB_BUS_INFO=8-8/PI05_RIGHT_CAN_USB_BUS_INFO=9-9/' "$config" >"$collision_config"
if PATH="$fake_bin:$PATH" "$repo_root/scripts/configure_can.sh" check left --config "$collision_config" >/dev/null 2>&1; then
  printf 'cross-side CAN identity collision unexpectedly passed\n' >&2
  exit 1
fi
if PATH="$fake_bin:$PATH" "$repo_root/scripts/configure_can.sh" check --config "$config" >/dev/null 2>&1; then
  printf 'CAN configuration unexpectedly accepted a missing side\n' >&2
  exit 1
fi

printf 'device configuration script tests: PASS\n'
