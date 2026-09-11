#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
checker="$repo_root/scripts/check_pika_stream.py"
wrapper="$repo_root/scripts/check_pika_stream.sh"

test_root=$(mktemp -d /tmp/pi05-pika-stream-test.XXXXXX)
trap 'rm -rf -- "$test_root"' EXIT

PYTHONPYCACHEPREFIX="$test_root/pycache" /usr/bin/python3 -m py_compile "$checker"
bash -n "$wrapper"
"$checker" --help >/dev/null
"$wrapper" --help >/dev/null

valid="$test_root/valid.stream"
truncated="$test_root/truncated.stream"
empty="$test_root/empty.stream"

for index in $(seq 1 20); do
  printf '{"Command":%d,"AS5047":{"angle":0.1,"rad":0.2}}\r\n' "$index"
done >"$valid"

for index in $(seq 1 20); do
  if ((index % 4 == 0)); then
    printf '{"Command":%d,"AS5047":{"angle":0.1\r\n' "$index"
  else
    printf '{"Command":%d,"AS5047":{"angle":0.1,"rad":0.2}}\r\n' "$index"
  fi
done >"$truncated"

: >"$empty"

"$checker" --input-file "$valid" --duration 1 --label test >/dev/null

if "$checker" --input-file "$truncated" --duration 1 --label test >/dev/null 2>&1; then
  printf 'Pika checker unexpectedly accepted truncated frames\n' >&2
  exit 1
fi

if "$checker" --input-file "$empty" --duration 1 --label test >/dev/null 2>&1; then
  printf 'Pika checker unexpectedly accepted an empty stream\n' >&2
  exit 1
fi

if "$checker" --input-file "$valid" --duration 0 >/dev/null 2>&1; then
  printf 'Pika checker unexpectedly accepted an invalid duration\n' >&2
  exit 1
fi

if rg -n 'os[.]write|[.]write_bytes|[.]write_text' "$checker" >/dev/null; then
  printf 'Pika checker contains a device/file write API\n' >&2
  exit 1
fi
rg -n 'os[.]O_RDONLY' "$checker" >/dev/null

printf 'Pika stream checker tests: PASS\n'
