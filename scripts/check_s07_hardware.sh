#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/check_s07_hardware.sh [--config PATH]

Validate the machine-local S07 dual-arm hardware acceptance record. This is a
read-only check: it never invokes sudo, opens CAN/serial devices, enables an
arm or sends a command. The default record is config/s07-hardware.env.

The record must be completed from the physical labels, applicable manuals and
no-motion field checks in docs/s07-field-acceptance.md. Do not enter serial
numbers, asset tags, QR contents, network identifiers, people or site names.
EOF
}

repo_root=$(pi05_repo_root)
config_file="$repo_root/config/s07-hardware.env"

while (($#)); do
  case "$1" in
    --config)
      (($# >= 2)) || pi05_die 2 '--config requires a path'
      config_file="$2"
      shift 2
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

[[ -r "$config_file" ]] || pi05_die 3 "hardware record not readable: $config_file"

declare -A record=()
allowed_keys=(
  PI05_S07_RECORD_DATE
  PI05_S07_REVIEWER_COUNT
)
for side in LEFT RIGHT; do
  for field in \
    PIPER_MODEL PIPER_FIRMWARE GRIPPER_MODEL MANUAL_REVISION \
    POWER_VOLTAGE_V POWER_RATED_W POWER_CURRENT_A POWER_PROTECTION \
    PROTECTIVE_EARTH_RESULT CAN_WIRING_RESULT CAN_TERMINATION_OHMS \
    CAN_TERMINATION_RESULT BASE_MOUNT_RESULT PAYLOAD_KG \
    PAYLOAD_COM_RESULT; do
    allowed_keys+=("PI05_${side}_${field}")
  done
done
allowed_keys+=(
  PI05_ESTOP_INDEPENDENT_OF_HOST_RESULT
  PI05_ESTOP_COVERS_BOTH_RESULT
  PI05_ESTOP_REACHABLE_RESULT
  PI05_ESTOP_DISABLED_STATE_TEST_RESULT
  PI05_ESTOP_MANUAL_RECOVERY_RESULT
  PI05_SHARED_WORKSPACE_REVIEW_RESULT
  PI05_CABLE_ROUTING_REVIEW_RESULT
  PI05_NO_MOTION_PERFORMED
  PI05_SENSITIVE_IDENTIFIERS_OMITTED
)

is_allowed_key() {
  local wanted="$1" key
  for key in "${allowed_keys[@]}"; do
    [[ "$key" == "$wanted" ]] && return 0
  done
  return 1
}

while IFS= read -r line || [[ -n "$line" ]]; do
  line=${line%%#*}
  line=${line//$'\r'/}
  [[ -n "${line//[[:space:]]/}" ]] || continue
  [[ "$line" =~ ^([A-Z][A-Z0-9_]*)=([-A-Za-z0-9_.+:/]*)$ ]] ||
    pi05_die 3 "unsafe or invalid hardware record line in $config_file"
  key=${BASH_REMATCH[1]}
  value=${BASH_REMATCH[2]}
  is_allowed_key "$key" || pi05_die 3 "unknown hardware record key: $key"
  [[ -z "${record[$key]+present}" ]] || pi05_die 3 "duplicate hardware record key: $key"
  record[$key]=$value
done <"$config_file"

for key in "${allowed_keys[@]}"; do
  [[ -n "${record[$key]:-}" ]] || pi05_die 3 "required hardware record value is empty: $key"
done

[[ "${record[PI05_S07_RECORD_DATE]}" =~ ^20[0-9]{2}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$ ]] ||
  pi05_die 3 'PI05_S07_RECORD_DATE must use YYYY-MM-DD'
[[ "${record[PI05_S07_REVIEWER_COUNT]}" =~ ^[0-9]+$ ]] ||
  pi05_die 3 'PI05_S07_REVIEWER_COUNT must be an integer'
((10#${record[PI05_S07_REVIEWER_COUNT]} >= 2)) ||
  pi05_die 3 'S07 field acceptance requires at least two reviewers'

validate_number() {
  local key="$1"
  [[ "${record[$key]}" =~ ^[0-9]+([.][0-9]+)?$ ]] ||
    pi05_die 3 "$key must be a non-negative decimal number"
}

validate_result() {
  local key="$1"
  [[ "${record[$key]}" == pass ]] || pi05_die 3 "$key must be pass"
}

for side in LEFT RIGHT; do
  for field in \
    POWER_VOLTAGE_V POWER_RATED_W POWER_CURRENT_A \
    CAN_TERMINATION_OHMS PAYLOAD_KG; do
    validate_number "PI05_${side}_${field}"
  done
  for field in \
    PROTECTIVE_EARTH_RESULT CAN_WIRING_RESULT CAN_TERMINATION_RESULT \
    BASE_MOUNT_RESULT PAYLOAD_COM_RESULT; do
    validate_result "PI05_${side}_${field}"
  done
done

for key in \
  PI05_ESTOP_INDEPENDENT_OF_HOST_RESULT \
  PI05_ESTOP_COVERS_BOTH_RESULT \
  PI05_ESTOP_REACHABLE_RESULT \
  PI05_ESTOP_DISABLED_STATE_TEST_RESULT \
  PI05_ESTOP_MANUAL_RECOVERY_RESULT \
  PI05_SHARED_WORKSPACE_REVIEW_RESULT \
  PI05_CABLE_ROUTING_REVIEW_RESULT; do
  validate_result "$key"
done

[[ "${record[PI05_NO_MOTION_PERFORMED]}" == yes ]] ||
  pi05_die 3 'PI05_NO_MOTION_PERFORMED must be yes for S07'
[[ "${record[PI05_SENSITIVE_IDENTIFIERS_OMITTED]}" == yes ]] ||
  pi05_die 3 'PI05_SENSITIVE_IDENTIFIERS_OMITTED must be yes'

for key in "${allowed_keys[@]}"; do
  value=${record[$key]}
  [[ ! "$value" =~ ([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2} ]] ||
    pi05_die 3 "possible MAC address detected in $key"
  [[ ! "$value" =~ ^([0-9]{1,3}[.]){3}[0-9]{1,3}$ ]] ||
    pi05_die 3 "possible IP address detected in $key"
  [[ ! "$value" =~ ^[0-9]{8,}$ ]] ||
    pi05_die 3 "possible serial or asset identifier detected in $key"
done

pi05_log "S07 hardware record passed for ${record[PI05_S07_RECORD_DATE]}: dual-side identity, power, CAN wiring/termination, mounting, payload, emergency stop and shared-workspace checks are complete"
pi05_log 'record asserts that no motion was performed and sensitive identifiers were omitted'
