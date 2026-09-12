#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
checker="${repo_root}/scripts/check_control_graph.py"

"$checker" --help >/dev/null
if "$checker" --mode invalid >/dev/null 2>&1; then
  printf '%s\n' 'invalid graph mode unexpectedly succeeded' >&2
  exit 1
fi
/usr/bin/python3 -m unittest \
  "${repo_root}/src/pi05_control/test/test_control_graph.py"

printf '%s\n' '[PASS] S11 read-only control graph checker contracts'
