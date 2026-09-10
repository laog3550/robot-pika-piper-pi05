#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/build_catkin.sh [OPTIONS]

Incrementally build the PI05 catkin workspace with ROS Noetic and the managed
Python virtual environment.

Options:
  --workspace PATH      Catkin workspace (default: repository root).
  --venv PATH           Python venv (default: <workspace>/.venv).
  --jobs N              Parallel build jobs (default: number of CPUs).
  --install             Also produce the catkin install space.
  --skip-rosdep-check   Skip the read-only rosdep check.
  -h, --help            Show this help.

The command is incremental and never deletes build/devel/install directories.
EOF
}

repo_root=$(pi05_repo_root)
workspace="$repo_root"
venv_path=''
jobs=$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf '1')
make_install=false
check_rosdep=true

while (($#)); do
  case "$1" in
    --workspace)
      (($# >= 2)) || pi05_die 2 '--workspace requires a path'
      workspace="$2"; shift
      ;;
    --venv)
      (($# >= 2)) || pi05_die 2 '--venv requires a path'
      venv_path="$2"; shift
      ;;
    --jobs)
      (($# >= 2)) || pi05_die 2 '--jobs requires a positive integer'
      jobs="$2"; shift
      ;;
    --install) make_install=true ;;
    --skip-rosdep-check) check_rosdep=false ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; pi05_die 2 "unknown argument: $1" ;;
  esac
  shift
done

[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || pi05_die 2 '--jobs must be a positive integer'
pi05_require_focal_amd64
[[ -f "$workspace/src/CMakeLists.txt" ]] || pi05_die 3 "catkin workspace not found: $workspace"
workspace=$(cd "$workspace" && pwd)
[[ -n "$venv_path" ]] || venv_path="$workspace/.venv"
[[ -x "$venv_path/bin/python" ]] ||
  pi05_die 3 "Python venv not ready: $venv_path (run scripts/install_python_deps.sh --apply)"
venv_version=$("$venv_path/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
[[ "$venv_version" == 3.8 ]] || pi05_die 3 "venv Python must be 3.8, got $venv_version"
[[ -r /opt/ros/noetic/setup.bash ]] || pi05_die 3 'ROS Noetic setup not found'

# shellcheck disable=SC1091
source /opt/ros/noetic/setup.bash
# shellcheck disable=SC1091
source "$venv_path/bin/activate"
export CMAKE_PREFIX_PATH="/opt/openrobots${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
export LD_LIBRARY_PATH="/opt/openrobots/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PKG_CONFIG_PATH="/opt/openrobots/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
export PYTHONPATH="/opt/openrobots/lib/python3.8/site-packages${PYTHONPATH:+:$PYTHONPATH}"
pi05_require_command catkin_make

if [[ "$check_rosdep" == true ]]; then
  pi05_require_command rosdep
  rosdep check --from-paths "$workspace/src" --ignore-src --rosdistro noetic
fi

pi05_log "building $workspace with $venv_path/bin/python and $jobs jobs"
build_args=(-C "$workspace" "-j$jobs" -DPYTHON_EXECUTABLE="$venv_path/bin/python" -DCMAKE_BUILD_TYPE=RelWithDebInfo)
if [[ "$make_install" == true ]]; then
  build_args+=(install)
fi
catkin_make "${build_args[@]}"
pi05_log 'catkin build complete'
