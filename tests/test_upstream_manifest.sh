#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
checker="$repo_root/scripts/check_upstream_manifest.sh"

bash -n "$checker"
"$checker" --help >/dev/null
"$checker" >/dev/null

test_root=$(mktemp -d /tmp/pi05-upstream-test.XXXXXX)
trap 'rm -rf -- "$test_root"' EXIT

movable="$test_root/movable.repos"
sed '0,/version: [0-9a-f]\{40\}/s//version: master/' \
  "$repo_root/third_party/pi05-upstream.repos" >"$movable"
if "$checker" --manifest "$movable" >/dev/null 2>&1; then
  printf 'manifest checker unexpectedly accepted a movable ref\n' >&2
  exit 1
fi

unknown="$test_root/unknown.repos"
sed '0,/    type: git/a\    recursive: true' \
  "$repo_root/third_party/pi05-upstream.repos" >"$unknown"
if "$checker" --manifest "$unknown" >/dev/null 2>&1; then
  printf 'manifest checker unexpectedly accepted an unknown field\n' >&2
  exit 1
fi

printf 'upstream manifest tests: PASS\n'
