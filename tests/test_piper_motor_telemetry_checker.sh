#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
checker="$repo_root/scripts/check_piper_motor_telemetry.py"
test_root=$(mktemp -d /tmp/pi05-motor-telemetry-test.XXXXXX)
trap 'rm -rf -- "$test_root"' EXIT

fixture="$test_root/feedback.txt"
for can_id in 251 252 253 254 255 256; do
  for _sample in $(seq 1 10); do
    printf '%s 007B0929FFFFFF85\n' "$can_id" >>"$fixture"
  done
done

output=$(PYTHONPATH="$repo_root/src/pi05_control/src" /usr/bin/python3 \
  "$checker" --input-file "$fixture" --label test)
grep -q 'J3\[n=10 speed=0.123rad/s current=2.345A\]' <<<"$output"

short_fixture="$test_root/short.txt"
printf '251 0000000000000000\n' >"$short_fixture"
if PYTHONPATH="$repo_root/src/pi05_control/src" /usr/bin/python3 \
    "$checker" --input-file "$short_fixture" >/dev/null 2>&1; then
  echo 'checker unexpectedly accepted incomplete feedback' >&2
  exit 1
fi

grep -q 'never' <("$repo_root/scripts/check_piper_motor_telemetry.sh" --help)
if rg -n 'send\(|sendall|sendmsg' "$checker"; then
  echo 'passive telemetry checker contains a transmit API' >&2
  exit 1
fi

echo 'Piper motor telemetry checker tests: PASS'
