#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$script_dir/lib/common.sh"
# shellcheck source=scripts/lib/device_config.sh
source "$script_dir/lib/device_config.sh"

usage() {
  cat <<'EOF'
Usage: scripts/configure_can.sh check [--config PATH]
       scripts/configure_can.sh apply [--config PATH] [--yes]

check  Read-only: require exactly one CAN interface whose ethtool bus-info
       matches PI05_CAN_USB_BUS_INFO, then verify its name, 1 Mbps bitrate and
       UP state.
apply  After the same unique identity check and explicit confirmation, rename
       that interface if needed, configure exactly 1000000 bit/s and bring it
       UP. A udev rule binds the configured name to the gs_usb bus-info on later
       device additions. No CAN frames are transmitted.

The default config is config/pi05.env. --yes is valid only with apply.
EOF
}

(($# >= 1)) || { usage >&2; exit 2; }
[[ "$1" != -h && "$1" != --help ]] || { usage; exit 0; }
mode="$1"; shift
[[ "$mode" == check || "$mode" == apply ]] || { usage >&2; pi05_die 2 'mode must be check or apply'; }
repo_root=$(pi05_repo_root)
config_file="$repo_root/config/pi05.env"
assume_yes=false
while (($#)); do
  case "$1" in
    --config) (($# >= 2)) || pi05_die 2 '--config requires a path'; config_file="$2"; shift ;;
    --yes) assume_yes=true ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; pi05_die 2 "unknown argument: $1" ;;
  esac
  shift
done
[[ "$mode" == apply || "$assume_yes" != true ]] || pi05_die 2 '--yes is valid only with apply'

for command_name in ip ethtool readlink; do pi05_require_command "$command_name"; done
pi05_load_device_config "$config_file"
pi05_validate_can_config

matches=()
while IFS= read -r interface; do
  [[ -n "$interface" ]] || continue
  [[ "$(pi05_can_bus_info "$interface")" == "$PI05_CAN_USB_BUS_INFO" ]] || continue
  [[ "$(pi05_can_driver "$interface")" == gs_usb ]] || continue
  pi05_can_bus_info_is_udev_ancestor "$interface" "$PI05_CAN_USB_BUS_INFO" || continue
  matches+=("$interface")
done < <(pi05_can_interfaces)

((${#matches[@]} == 1)) ||
  pi05_die 6 "CAN identity is not unique: bus-info matched ${#matches[@]} interfaces; refusing changes"
current_interface=${matches[0]}

can_is_ready() {
  local details
  [[ "$current_interface" == "$PI05_CAN_INTERFACE" ]] || return 1
  details=$(ip -details link show dev "$PI05_CAN_INTERFACE" 2>/dev/null) || return 1
  grep -Eq 'state UP|<[^>]*UP[^>]*>' <<<"$details" || return 1
  grep -Eq 'bitrate[[:space:]]+1000000([[:space:]]|$)' <<<"$details"
}

if [[ "$mode" == check ]]; then
  if can_is_ready; then
    pi05_log "CAN check passed: $PI05_CAN_INTERFACE uniquely matches configured bus-info and is UP at 1000000 bit/s"
    exit 0
  fi
  pi05_die 1 "CAN identity matched $current_interface, but expected name/UP/1000000 bit/s state is not active"
fi

pi05_require_command sudo
pi05_require_command udevadm
if [[ "$current_interface" != "$PI05_CAN_INTERFACE" ]] && ip link show dev "$PI05_CAN_INTERFACE" >/dev/null 2>&1; then
  pi05_die 6 "target interface $PI05_CAN_INTERFACE already exists and is not the matched USB device"
fi
rule_target=/etc/udev/rules.d/80-pi05-can.rules
rule_tmp=$(mktemp /tmp/pi05-can-rule.XXXXXX)
trap 'rm -f -- "$rule_tmp"' EXIT
printf '%s\n' \
  '# Managed by robot-pika-piper-pi05; binds a physical USB port, not a device serial number.' \
  "ACTION==\"add\", SUBSYSTEM==\"net\", DRIVERS==\"gs_usb\", KERNELS==\"$PI05_CAN_USB_BUS_INFO\", NAME=\"$PI05_CAN_INTERFACE\"" \
  >"$rule_tmp"
pi05_confirm_apply "$assume_yes" \
  "install $rule_target and reconfigure only CAN interface $current_interface matched by gs_usb bus-info; no frames are sent"

pi05_log "sudo install -m 0644 <generated-rule> $rule_target"
sudo -- install -m 0644 "$rule_tmp" "$rule_target"
pi05_log 'sudo udevadm control --reload-rules'
sudo -- udevadm control --reload-rules
pi05_log "sudo ip link set dev $current_interface down"
sudo -- ip link set dev "$current_interface" down
if [[ "$current_interface" != "$PI05_CAN_INTERFACE" ]]; then
  pi05_log "sudo ip link set dev $current_interface name $PI05_CAN_INTERFACE"
  sudo -- ip link set dev "$current_interface" name "$PI05_CAN_INTERFACE"
  current_interface=$PI05_CAN_INTERFACE
fi
pi05_log "sudo ip link set dev $current_interface type can bitrate 1000000"
sudo -- ip link set dev "$current_interface" type can bitrate 1000000
pi05_log "sudo ip link set dev $current_interface up"
sudo -- ip link set dev "$current_interface" up

can_is_ready || pi05_die 1 'CAN apply completed but post-check failed'
pi05_log 'CAN apply and post-check passed'
