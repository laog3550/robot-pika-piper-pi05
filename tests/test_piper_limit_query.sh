#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python_tool="$repo_root/scripts/query_piper_limits.py"
shell_tool="$repo_root/scripts/query_piper_limits.sh"

bash -n "$shell_tool"
/usr/bin/python3 -m py_compile "$python_tool"
PYTHON_TOOL="$python_tool" /usr/bin/python3 - <<'PY'
import importlib.util
import os
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("query_piper_limits", os.environ["PYTHON_TOOL"])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

angles = [None] + [
    SimpleNamespace(
        motor_num=joint,
        min_angle_limit=-1000 - joint,
        max_angle_limit=1000 + joint,
        max_joint_spd=2000 + joint,
    )
    for joint in module.JOINTS
]
accelerations = [None] + [
    SimpleNamespace(joint_motor_num=joint, max_joint_acc=3000 + joint)
    for joint in module.JOINTS
]
angle_state = SimpleNamespace(
    all_motor_angle_limit_max_spd=SimpleNamespace(motor=angles))
acceleration_state = SimpleNamespace(
    all_motor_max_acc_limit=SimpleNamespace(motor=accelerations))

result = module.extract_limits(angle_state, acceleration_state)
assert len(result) == 6
assert result[1] == (-1002, 1002, 2002, 3002)

angles[3].motor_num = 0
try:
    module.extract_limits(angle_state, acceleration_state)
except ValueError as exc:
    assert "incomplete limit response for J3" in str(exc)
else:
    raise AssertionError("incomplete response was accepted")
PY

"$shell_tool" --help | grep -q 'check <left|right>'
grep -q 'piper.ConnectPort(piper_init=True, start_thread=True)' "$python_tool"
grep -q 'apply requires --confirm-query-only' "$shell_tool"

if rg -n 'EnableArm|DisableArm|JointCtrl|GripperCtrl|MotionCtrl|ResetPiper|EmergencyStop|MotorAngleLimitMaxSpdSet|JointMaxAccConfig' \
    "$python_tool"; then
  echo 'limit query tool contains a control or parameter-setting API' >&2
  exit 1
fi

echo 'Piper limit query tests: PASS'
