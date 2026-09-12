#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/setup_rosdep.sh [OPTIONS]

Initialize rosdep when necessary, refresh its Noetic index, preview dependency
installation, and install missing dependencies for a catkin workspace.

Options:
  --workspace PATH   Catkin workspace (default: repository root).
  --apply            Run rosdep update/install after explicit confirmation.
  --yes              With --apply, record explicit non-interactive consent.
  --skip-init        Refuse to initialize /etc/ros/rosdep; require it to exist.
  -h, --help         Show this help.

Without --apply, no rosdep cache or system package is changed and sudo is never
invoked. With --apply, the simulated install is printed before the real command.
EOF
}

repo_root=$(pi05_repo_root)
workspace="$repo_root"
apply=false
assume_yes=false
allow_init=true

while (($#)); do
  case "$1" in
    --workspace)
      (($# >= 2)) || pi05_die 2 '--workspace requires a path'
      workspace="$2"; shift
      ;;
    --apply) apply=true ;;
    --yes) assume_yes=true ;;
    --skip-init) allow_init=false ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; pi05_die 2 "unknown argument: $1" ;;
  esac
  shift
done

pi05_require_apply_yes_pair "$apply" "$assume_yes"
pi05_require_focal_amd64
[[ -d "$workspace/src" ]] || pi05_die 3 "catkin source directory not found: $workspace/src"
workspace=$(cd "$workspace" && pwd)

pi05_log "workspace: $workspace"
pi05_log 'planned rosdep actions:'
if [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
  [[ "$allow_init" == true ]] || pi05_die 3 'rosdep is not initialized and --skip-init was supplied'
  pi05_log '  sudo rosdep init (only because 20-default.list is absent)'
else
  pi05_log '  rosdep init: already initialized, skip'
fi
pi05_log '  rosdep update --rosdistro noetic'
pi05_log "  rosdep install --from-paths $workspace/src --ignore-src --rosdistro noetic --skip-keys data_msgs -y"
pi05_log '  data_msgs: skipped as a pinned VCS source dependency; this command does not install it'

if [[ "$apply" != true ]]; then
  pi05_log 'DRY-RUN complete; rerun with --apply to make changes'
  exit 0
fi

pi05_require_command rosdep
pi05_confirm_apply "$assume_yes" 'rosdep cache update and installation of its reported apt dependencies'

if [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
  pi05_require_command sudo
  pi05_log 'sudo rosdep init'
  sudo -- rosdep init
fi

rosdep update --rosdistro noetic
pi05_log 'rosdep simulation follows; no packages are changed by this command'
rosdep install --from-paths "$workspace/src" --ignore-src --rosdistro noetic \
  --skip-keys data_msgs --simulate
pi05_log 'running the previously previewed rosdep installation'
rosdep install --from-paths "$workspace/src" --ignore-src --rosdistro noetic \
  --skip-keys data_msgs -y
pi05_log 'rosdep setup and dependency installation complete'
