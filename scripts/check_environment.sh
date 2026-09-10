#!/usr/bin/env bash
set -uo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/check_environment.sh [OPTIONS]

Read-only validation of the Ubuntu 20.04, ROS Noetic, rosdep, Python and catkin
environment. No sudo, network, device configuration, or robot command is used.

Options:
  --workspace PATH   Catkin workspace (default: repository root).
  --venv PATH        Python venv (default: <workspace>/.venv).
  -h, --help         Show this help.

Returns 0 only when every required check passes; otherwise returns 1.
EOF
}

repo_root=$(pi05_repo_root)
workspace="$repo_root"
venv_path=''

while (($#)); do
  case "$1" in
    --workspace)
      (($# >= 2)) || { usage >&2; exit 2; }
      workspace="$2"; shift
      ;;
    --venv)
      (($# >= 2)) || { usage >&2; exit 2; }
      venv_path="$2"; shift
      ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; pi05_die 2 "unknown argument: $1" ;;
  esac
  shift
done

[[ -n "$venv_path" ]] || venv_path="$workspace/.venv"
failures=0

pass() { printf '[PASS] %s\n' "$*"; }
fail() { printf '[FAIL] %s\n' "$*" >&2; failures=$((failures + 1)); }

if [[ -r /etc/os-release ]]; then
  os_id=$(. /etc/os-release && printf '%s' "${ID:-}")
  os_version=$(. /etc/os-release && printf '%s' "${VERSION_ID:-}")
  [[ "$os_id" == ubuntu && "$os_version" == 20.04 ]] && pass 'Ubuntu 20.04' ||
    fail "expected Ubuntu 20.04, got ${os_id:-unknown} ${os_version:-unknown}"
else
  fail 'cannot read /etc/os-release'
fi
[[ "$(uname -m)" == x86_64 ]] && pass 'architecture x86_64' || fail "architecture $(uname -m)"

if [[ -x /usr/bin/python3 ]]; then
  system_python_version=$(/usr/bin/python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
  [[ "$system_python_version" == 3.8.* ]] && pass "/usr/bin/python3 $system_python_version" ||
    fail "/usr/bin/python3 must be 3.8.x, got $system_python_version"
else
  fail '/usr/bin/python3 missing'
fi
shell_python=$(command -v python3 2>/dev/null || true)
if [[ "$shell_python" != /usr/bin/python3 ]]; then
  printf '[WARN] shell python3 resolves to %s; scripts use explicit managed interpreters\n' "${shell_python:-missing}"
fi

package_file="$repo_root/config/apt-packages-noetic.txt"
if [[ -r "$package_file" ]]; then
  pi05_read_list "$package_file" apt_packages
  for package in "${apt_packages[@]}"; do
    dpkg-query -W -f='${db:Status-Status}' "$package" 2>/dev/null | grep -qx installed &&
      pass "apt $package" || fail "apt package missing: $package"
  done
else
  fail "apt manifest missing: $package_file"
fi

for command_name in catkin_make rosdep roscore vcs; do
  command -v "$command_name" >/dev/null 2>&1 && pass "command $command_name" || fail "command missing: $command_name"
done
[[ -r /opt/ros/noetic/setup.bash ]] && pass 'ROS Noetic setup' || fail 'ROS Noetic setup missing'
[[ -f /etc/ros/rosdep/sources.list.d/20-default.list ]] && pass 'rosdep initialized' || fail 'rosdep not initialized'

if [[ -x "$venv_path/bin/python" ]]; then
  venv_version=$($venv_path/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
  [[ "$venv_version" == 3.8.* ]] && pass "venv Python $venv_version" || fail "venv Python must be 3.8.x, got $venv_version"
  if [[ -r /opt/ros/noetic/setup.bash ]]; then
    # shellcheck disable=SC1091
    source /opt/ros/noetic/setup.bash
  fi
  "$venv_path/bin/python" - <<'PY' >/dev/null 2>&1
import can
import casadi
import meshcat
import numpy
import pinocchio
import piper_sdk
from pinocchio import casadi as pinocchio_casadi
PY
  [[ $? -eq 0 ]] && pass 'Python dependency imports' || fail 'one or more Python dependency imports failed'
  "$venv_path/bin/python" -m pip check >/dev/null 2>&1 && pass 'pip dependency consistency' || fail 'pip check failed'
else
  fail "Python venv missing: $venv_path"
fi

[[ -f "$workspace/src/CMakeLists.txt" ]] && pass "catkin workspace $workspace" || fail "catkin workspace missing: $workspace"

if ((failures)); then
  printf '[SUMMARY] %d required environment check(s) failed\n' "$failures" >&2
  exit 1
fi
printf '[SUMMARY] all required environment checks passed\n'
