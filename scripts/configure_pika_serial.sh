#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$script_dir/lib/common.sh"
# shellcheck source=scripts/lib/device_config.sh
source "$script_dir/lib/device_config.sh"

usage() {
  cat <<'EOF'
Usage: scripts/configure_pika_serial.sh check [--config PATH]
       scripts/configure_pika_serial.sh apply [--config PATH] [--yes]

check  Read-only: require exactly one ttyUSB/ttyACM device matching the
       configured ID_PATH + VID + PID identity and verify the configured alias.
apply  After the same unique identity check and explicit confirmation, install
       /etc/udev/rules.d/80-pi05-pika-serial.rules and reload only that tty.

Serial numbers and /dev/serial/by-id values are neither required nor printed.
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

for command_name in find udevadm readlink; do pi05_require_command "$command_name"; done
pi05_load_device_config "$config_file"
pi05_validate_serial_config

matches=()
while IFS= read -r device; do
  [[ -n "$device" ]] || continue
  [[ "$(pi05_udev_property "$device" ID_PATH || true)" == "$PI05_PIKA_SERIAL_ID_PATH" ]] || continue
  [[ "${PI05_PIKA_SERIAL_VENDOR_ID,,}" == "$(pi05_udev_property "$device" ID_VENDOR_ID | tr 'A-F' 'a-f')" ]] || continue
  [[ "${PI05_PIKA_SERIAL_MODEL_ID,,}" == "$(pi05_udev_property "$device" ID_MODEL_ID | tr 'A-F' 'a-f')" ]] || continue
  matches+=("$device")
done < <(pi05_serial_devices)

((${#matches[@]} == 1)) ||
  pi05_die 6 "Pika serial identity is not unique: ID_PATH+VID+PID matched ${#matches[@]} devices; refusing changes"
matched_device=${matches[0]}

serial_alias_is_ready() {
  [[ -L "$PI05_PIKA_SERIAL_ALIAS" ]] || return 1
  [[ "$(readlink -f -- "$PI05_PIKA_SERIAL_ALIAS")" == "$(readlink -f -- "$matched_device")" ]]
}

if [[ "$mode" == check ]]; then
  serial_alias_is_ready && {
    pi05_log "Pika serial check passed: $PI05_PIKA_SERIAL_ALIAS uniquely resolves to the configured physical USB path"
    exit 0
  }
  pi05_die 1 "Pika identity matched $matched_device, but alias $PI05_PIKA_SERIAL_ALIAS is absent or points elsewhere"
fi

pi05_require_command sudo
rule_target=/etc/udev/rules.d/80-pi05-pika-serial.rules
rule_tmp=$(mktemp /tmp/pi05-pika-serial-rule.XXXXXX)
trap 'rm -f -- "$rule_tmp"' EXIT
printf '%s\n' \
  '# Managed by robot-pika-piper-pi05; identity intentionally excludes serial numbers.' \
  "SUBSYSTEM==\"tty\", ENV{ID_PATH}==\"$PI05_PIKA_SERIAL_ID_PATH\", ENV{ID_VENDOR_ID}==\"${PI05_PIKA_SERIAL_VENDOR_ID,,}\", ENV{ID_MODEL_ID}==\"${PI05_PIKA_SERIAL_MODEL_ID,,}\", SYMLINK+=\"$PI05_PIKA_SERIAL_ALIAS_NAME\", GROUP=\"dialout\", MODE=\"0660\"" \
  >"$rule_tmp"
pi05_confirm_apply "$assume_yes" \
  "install $rule_target for the one tty matched by configured ID_PATH+VID+PID, then retrigger only $(basename "$matched_device")"

pi05_log "sudo install -m 0644 <generated-rule> $rule_target"
sudo -- install -m 0644 "$rule_tmp" "$rule_target"
pi05_log 'sudo udevadm control --reload-rules'
sudo -- udevadm control --reload-rules
pi05_log "sudo udevadm trigger --action=add --sysname-match=$(basename "$matched_device")"
sudo -- udevadm trigger --action=add --sysname-match="$(basename "$matched_device")"
sudo -- udevadm settle

serial_alias_is_ready || pi05_die 1 'serial rule installed but alias post-check failed'
pi05_log 'Pika serial apply and post-check passed'
