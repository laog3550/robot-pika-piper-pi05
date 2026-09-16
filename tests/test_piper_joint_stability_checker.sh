#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
checker="$repo_root/scripts/check_piper_joint_stability.py"
wrapper="$repo_root/scripts/check_piper_joint_stability.sh"
test_root=$(mktemp -d /tmp/pi05-joint-stability-test.XXXXXX)
trap 'rm -rf -- "$test_root"' EXIT

PYTHONPYCACHEPREFIX="$test_root/pycache" /usr/bin/python3 -m py_compile "$checker"
bash -n "$wrapper"
"$checker" --help >/dev/null
"$wrapper" --help >/dev/null

stable="$test_root/stable.frames"
drift="$test_root/drift.frames"
: >"$stable"
for _sample in $(seq 1 10); do
  printf '%s\n' \
    '2A5 0000000000000000' '2A6 0000000000000000' '2A7 0000000000000000' \
    >>"$stable"
done
cp "$stable" "$drift"
# 200 milli-degrees is about 0.00349 rad and therefore exceeds 0.002 rad.
printf '%s\n' '2A6 000000C800000000' >>"$drift"

"$checker" --input-file "$stable" --label test >/dev/null
if "$checker" --input-file "$drift" --label test >/dev/null 2>&1; then
  printf 'Joint stability checker accepted excessive drift\n' >&2
  exit 1
fi
"$checker" --input-file "$drift" --label test --exclude-joint 3 >/dev/null

if grep -En '[.]send(to)?[(]|sendmsg|os[.]write' "$checker" >/dev/null; then
  printf 'Joint stability checker contains a transmit API\n' >&2
  exit 1
fi
grep -En 'recv[(]' "$checker" >/dev/null

printf 'Piper joint stability checker tests: PASS\n'
