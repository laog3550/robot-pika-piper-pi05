#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f /opt/ros/noetic/setup.bash ]]; then
  # Preserve any already-sourced overlay that supplies the pinned data_msgs package.
  # Passing --extend also prevents this wrapper's own CLI arguments from leaking
  # into catkin's sourced setup script.
  source /opt/ros/noetic/setup.bash --extend
fi

exec /usr/bin/python3 "${script_dir}/check_pika_localization.py" "$@"
