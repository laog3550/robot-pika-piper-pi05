#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/install_python_deps.sh [OPTIONS]

Create/update a Python 3.8 virtual environment and install the pinned PI05
Python dependencies. piper_sdk is installed from the exact S03 VCS checkout.

Options:
  --venv PATH         Virtual environment (default: <repo>/.venv).
  --source-root PATH  S03 VCS import root (default: <repo>/../pi05-upstream-src).
  --index-url URL     Explicit HTTPS Python package index (optional).
  --apply             Create/update the environment after confirmation.
  --yes               With --apply, record explicit non-interactive consent.
  -h, --help          Show this help.

This script never uses sudo and never installs into the system Python. The
ABI-coupled Pinocchio/CasADi pair must first be installed by bootstrap_ubuntu.sh
from pinned robotpkg packages.
EOF
}

repo_root=$(pi05_repo_root)
venv_path="$repo_root/.venv"
source_root="$repo_root/../pi05-upstream-src"
apply=false
assume_yes=false
index_url=''

while (($#)); do
  case "$1" in
    --venv)
      (($# >= 2)) || pi05_die 2 '--venv requires a path'
      venv_path="$2"; shift
      ;;
    --source-root)
      (($# >= 2)) || pi05_die 2 '--source-root requires a path'
      source_root="$2"; shift
      ;;
    --index-url)
      (($# >= 2)) || pi05_die 2 '--index-url requires a URL'
      index_url="$2"; shift
      ;;
    --apply) apply=true ;;
    --yes) assume_yes=true ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; pi05_die 2 "unknown argument: $1" ;;
  esac
  shift
done

pi05_require_apply_yes_pair "$apply" "$assume_yes"
pi05_require_focal_amd64
if [[ -n "$index_url" ]]; then
  [[ "$index_url" == https://* && "$index_url" != *'@'* ]] ||
    pi05_die 2 '--index-url must be HTTPS and must not contain credentials'
fi
requirements="$repo_root/config/python-requirements-noetic.txt"
[[ -r "$requirements" ]] || pi05_die 3 "requirements file not found: $requirements"

pi05_log 'Python interpreter: /usr/bin/python3 (required: 3.8.x)'
pi05_log "virtual environment: $venv_path"
pi05_log "requirements: $requirements"
pi05_log "piper_sdk checkout: $source_root/piper_sdk @ 081e7c588e5b79eeaefa67a0469bcc701c81014f"
pi05_log 'Pinocchio/CasADi: robotpkg Python 3.8 packages 3.2.0 / 3.6.7'
[[ -z "$index_url" ]] || pi05_log 'Python package index: explicit credential-free HTTPS URL supplied'

if [[ "$apply" != true ]]; then
  pi05_log 'DRY-RUN complete; rerun with --apply to make changes'
  exit 0
fi

[[ -x /usr/bin/python3 ]] || pi05_die 4 '/usr/bin/python3 not found'
python_version=$(/usr/bin/python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
[[ "$python_version" == 3.8 ]] || pi05_die 3 "expected /usr/bin/python3 3.8, got $python_version"

piper_source="$source_root/piper_sdk"
[[ -d "$piper_source/.git" ]] || pi05_die 3 "piper_sdk VCS checkout not found: $piper_source"
piper_commit=$(git -C "$piper_source" rev-parse HEAD)
[[ "$piper_commit" == 081e7c588e5b79eeaefa67a0469bcc701c81014f ]] ||
  pi05_die 3 "piper_sdk commit mismatch: $piper_commit"
[[ -z "$(git -C "$piper_source" status --porcelain=v1)" ]] ||
  pi05_die 3 'piper_sdk checkout has local changes; refusing a non-reproducible install'

robotpkg_specs=(
  robotpkg-qpoases=3.2.1r1
  robotpkg-casadi=3.6.7
  robotpkg-py38-casadi=3.6.7
  robotpkg-hpp-fcl=2.4.5
  robotpkg-py38-hpp-fcl=2.4.5
  robotpkg-py38-eigenpy=3.10.0
  robotpkg-pinocchio=3.2.0
  robotpkg-py38-pinocchio=3.2.0
)
for package_spec in "${robotpkg_specs[@]}"; do
  package_name=${package_spec%%=*}
  expected_version=${package_spec#*=}
  installed_version=$(dpkg-query -W -f='${Version}' "$package_name" 2>/dev/null || true)
  [[ "$installed_version" == "$expected_version" ]] ||
    pi05_die 3 "$package_spec is required; run scripts/bootstrap_ubuntu.sh --apply first"
done
[[ -d /opt/openrobots/lib/python3.8/site-packages ]] ||
  pi05_die 3 'robotpkg Python package directory missing: /opt/openrobots/lib/python3.8/site-packages'

if [[ -e "$venv_path" && ! -f "$venv_path/pyvenv.cfg" ]]; then
  pi05_die 3 "refusing to overwrite a non-venv path: $venv_path"
fi
pi05_confirm_apply "$assume_yes" "create/update $venv_path and download pinned Python packages; no sudo"

if [[ ! -f "$venv_path/pyvenv.cfg" ]]; then
  /usr/bin/python3 -m venv --system-site-packages "$venv_path"
fi
venv_python="$venv_path/bin/python"
[[ -x "$venv_python" ]] || pi05_die 3 "venv interpreter missing: $venv_python"
venv_version=$($venv_python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
[[ "$venv_version" == 3.8 ]] || pi05_die 3 "existing venv uses Python $venv_version, expected 3.8"
grep -Eq '^include-system-site-packages = true$' "$venv_path/pyvenv.cfg" ||
  pi05_die 3 "existing venv is isolated from ROS Python packages; recreate it with --system-site-packages: $venv_path"

venv_site_packages="$venv_path/lib/python3.8/site-packages"
system_packages_pth="$venv_site_packages/pi05-system-packages.pth"
printf '%s\n' \
  /opt/ros/noetic/lib/python3/dist-packages \
  /opt/openrobots/lib/python3.8/site-packages >"$system_packages_pth"

pip_index_args=()
[[ -z "$index_url" ]] || pip_index_args=(--index-url "$index_url")

"$venv_python" -m pip install --disable-pip-version-check "${pip_index_args[@]}" --upgrade \
  'pip==21.3.1' 'setuptools==68.0.0' 'wheel==0.41.3'
"$venv_python" -m pip install --disable-pip-version-check "${pip_index_args[@]}" --upgrade -r "$requirements"
"$venv_python" -m pip install --disable-pip-version-check --no-deps --force-reinstall "$piper_source"

env PYTHONNOUSERSITE=1 "$venv_python" -m pip check
env PYTHONNOUSERSITE=1 \
  LD_LIBRARY_PATH="/opt/openrobots/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  "$venv_python" - <<'PY'
import can
import casadi
import meshcat
import numpy
import pinocchio
import piper_sdk
import rospy
import yaml
from pinocchio import casadi as pinocchio_casadi

assert pinocchio.__version__ == '3.2.0'
assert casadi.__version__ == '3.6.7'
assert pinocchio.__file__.startswith('/opt/openrobots/')
assert pinocchio_casadi.Model(pinocchio.Model()).nq == 0
print('PI05 Python imports: OK')
PY
pi05_log 'Python dependency installation complete'
