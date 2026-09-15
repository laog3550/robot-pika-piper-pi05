#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python_tool="$repo_root/scripts/query_piper_firmware.py"
shell_tool="$repo_root/scripts/query_piper_firmware.sh"

bash -n "$shell_tool"
/usr/bin/python3 -m py_compile "$python_tool"
PYTHON_TOOL="$python_tool" /usr/bin/python3 - <<'PY'
import importlib.util
import os

spec = importlib.util.spec_from_file_location("query_piper_firmware", os.environ["PYTHON_TOOL"])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

assert module.FIRMWARE_RE.fullmatch("S-V1.8-2")
assert not module.FIRMWARE_RE.fullmatch("S-V1")
assert not module.FIRMWARE_RE.fullmatch("S-V1.8-")
PY
"$shell_tool" --help | grep -q 'check <left|right>'

if rg -n 'EnableArm|JointCtrl|GripperCtrl|MotionCtrl|ResetPiper|EmergencyStop' \
    "$python_tool"; then
  echo 'firmware query tool contains a control API' >&2
  exit 1
fi
grep -q 'piper.ConnectPort(piper_init=True, start_thread=True)' "$python_tool"
grep -q 'piper.DisconnectPort()' "$python_tool"
grep -q "apply requires --confirm-query-only" "$shell_tool"

echo 'Piper firmware query tests: PASS'
