#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
checker="$repo_root/scripts/check_s07_hardware.sh"

bash -n "$checker"
"$checker" --help >/dev/null
if "$checker" --invalid >/dev/null 2>&1; then
  printf 'S07 checker unexpectedly accepted an invalid option\n' >&2
  exit 1
fi

test_root=$(mktemp -d /tmp/pi05-s07-test.XXXXXX)
trap 'rm -rf -- "$test_root"' EXIT
valid="$test_root/valid.env"
sed \
  -e 's/^PI05_S07_RECORD_DATE=$/PI05_S07_RECORD_DATE=2026-09-10/' \
  -e 's/^PI05_S07_REVIEWER_COUNT=$/PI05_S07_REVIEWER_COUNT=2/' \
  -e 's/^PI05_\(LEFT\|RIGHT\)_PIPER_MODEL=$/PI05_\1_PIPER_MODEL=PiPER/' \
  -e 's/^PI05_\(LEFT\|RIGHT\)_PIPER_FIRMWARE=$/PI05_\1_PIPER_FIRMWARE=V1.0/' \
  -e 's/^PI05_\(LEFT\|RIGHT\)_GRIPPER_MODEL=$/PI05_\1_GRIPPER_MODEL=standard/' \
  -e 's/^PI05_\(LEFT\|RIGHT\)_MANUAL_REVISION=$/PI05_\1_MANUAL_REVISION=manual-v1/' \
  -e 's/^PI05_\(LEFT\|RIGHT\)_POWER_VOLTAGE_V=$/PI05_\1_POWER_VOLTAGE_V=24/' \
  -e 's/^PI05_\(LEFT\|RIGHT\)_POWER_RATED_W=$/PI05_\1_POWER_RATED_W=240/' \
  -e 's/^PI05_\(LEFT\|RIGHT\)_POWER_CURRENT_A=$/PI05_\1_POWER_CURRENT_A=10/' \
  -e 's/^PI05_\(LEFT\|RIGHT\)_POWER_PROTECTION=$/PI05_\1_POWER_PROTECTION=fused/' \
  -e 's/^PI05_\(LEFT\|RIGHT\)_CAN_TERMINATION_OHMS=$/PI05_\1_CAN_TERMINATION_OHMS=60.1/' \
  -e 's/^PI05_\(LEFT\|RIGHT\)_PAYLOAD_KG=$/PI05_\1_PAYLOAD_KG=0/' \
  -e 's/^\(PI05_.*_RESULT\)=$/\1=pass/' \
  -e 's/^PI05_NO_MOTION_PERFORMED=$/PI05_NO_MOTION_PERFORMED=yes/' \
  -e 's/^PI05_SENSITIVE_IDENTIFIERS_OMITTED=$/PI05_SENSITIVE_IDENTIFIERS_OMITTED=yes/' \
  "$repo_root/config/s07-hardware.env.example" >"$valid"

"$checker" --config "$valid" >/dev/null

single_reviewer="$test_root/single-reviewer.env"
sed 's/PI05_S07_REVIEWER_COUNT=2/PI05_S07_REVIEWER_COUNT=1/' "$valid" >"$single_reviewer"
if "$checker" --config "$single_reviewer" >/dev/null 2>&1; then
  printf 'S07 checker unexpectedly accepted one reviewer\n' >&2
  exit 1
fi

failed_check="$test_root/failed-check.env"
sed 's/PI05_ESTOP_COVERS_BOTH_RESULT=pass/PI05_ESTOP_COVERS_BOTH_RESULT=fail/' "$valid" >"$failed_check"
if "$checker" --config "$failed_check" >/dev/null 2>&1; then
  printf 'S07 checker unexpectedly accepted a failed safety check\n' >&2
  exit 1
fi

unsafe="$test_root/unsafe.env"
sed 's/PI05_LEFT_PIPER_MODEL=PiPER/PI05_LEFT_PIPER_MODEL=$(touch\/tmp\/bad)/' "$valid" >"$unsafe"
if "$checker" --config "$unsafe" >/dev/null 2>&1; then
  printf 'S07 checker unexpectedly accepted executable content\n' >&2
  exit 1
fi

serial="$test_root/serial.env"
sed 's/PI05_RIGHT_PIPER_MODEL=PiPER/PI05_RIGHT_PIPER_MODEL=123456789012/' "$valid" >"$serial"
if "$checker" --config "$serial" >/dev/null 2>&1; then
  printf 'S07 checker unexpectedly accepted a likely serial number\n' >&2
  exit 1
fi

printf 'S07 hardware record tests: PASS\n'
