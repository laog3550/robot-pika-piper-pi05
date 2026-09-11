#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
checker="$repo_root/scripts/check_piper_can_stream.py"
wrapper="$repo_root/scripts/check_piper_can_stream.sh"
test_root=$(mktemp -d /tmp/pi05-piper-can-test.XXXXXX)
trap 'rm -rf -- "$test_root"' EXIT

PYTHONPYCACHEPREFIX="$test_root/pycache" /usr/bin/python3 -m py_compile "$checker"
bash -n "$wrapper"
"$checker" --help >/dev/null
"$wrapper" --help >/dev/null

valid="$test_root/valid.ids"
missing="$test_root/missing.ids"
control="$test_root/control.ids"

for repeat in 1 2; do
  for id in 251 252 253 254 255 256 261 262 263 264 265 266 2A1 2A2 2A3 2A4 2A5 2A6 2A7 2A8; do
    printf '%s\n' "$id"
  done
done >"$valid"

sed '/^2A8$/d' "$valid" >"$missing"
cp "$valid" "$control"
printf '151\n' >>"$control"

"$checker" --input-file "$valid" --label test >/dev/null

if "$checker" --input-file "$missing" --label test >/dev/null 2>&1; then
  printf 'Piper CAN checker unexpectedly accepted a missing feedback ID\n' >&2
  exit 1
fi

if "$checker" --input-file "$control" --label test >/dev/null 2>&1; then
  printf 'Piper CAN checker unexpectedly accepted a control ID\n' >&2
  exit 1
fi

if rg -n '[.]send(to)?[(]|sendmsg|os[.]write' "$checker" >/dev/null; then
  printf 'Piper CAN checker contains a transmit API\n' >&2
  exit 1
fi
rg -n 'recv[(]' "$checker" >/dev/null

printf 'Piper CAN stream checker tests: PASS\n'
