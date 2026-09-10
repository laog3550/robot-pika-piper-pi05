#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap_ubuntu.sh [--apply] [--yes] [--skip-ros-repo]

Prepare the Ubuntu 20.04 apt baseline for ROS Noetic.

Without --apply this command is a read-only plan and never invokes sudo.
--apply              Perform apt/keyring/source-list changes after confirmation.
--yes                With --apply, record explicit non-interactive consent.
--skip-ros-repo      Keep the existing ROS apt source instead of installing the
                     pinned ROS key and focal source entry.
-h, --help           Show this help.

The script never runs apt upgrade, removes packages, or changes robot devices.
EOF
}

apply=false
assume_yes=false
configure_ros_repo=true

while (($#)); do
  case "$1" in
    --apply) apply=true ;;
    --yes) assume_yes=true ;;
    --skip-ros-repo) configure_ros_repo=false ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; pi05_die 2 "unknown argument: $1" ;;
  esac
  shift
done

pi05_require_apply_yes_pair "$apply" "$assume_yes"
pi05_require_focal_amd64

repo_root=$(pi05_repo_root)
package_file="$repo_root/config/apt-packages-noetic.txt"
[[ -r "$package_file" ]] || pi05_die 3 "package list not found: $package_file"
pi05_read_list "$package_file" apt_packages
((${#apt_packages[@]} > 0)) || pi05_die 3 'apt package list is empty'

ros_key_commit=eb71c289f4495a0327cd03a29205a2c411cd8129
ros_key_sha256=490a879375bd4f3dfbe1483efbf8db8985e2ad66b7a19baee0087b333c67caf0
ros_key_fingerprint=C1CF6E31E6BADE8868B172B4F42ED6FBAB17C654
ros_key_url="https://raw.githubusercontent.com/ros/rosdistro/$ros_key_commit/ros.asc"
ros_keyring=/usr/share/keyrings/ros-archive-keyring.gpg
ros_source=/etc/apt/sources.list.d/ros1-latest.list
ros_source_line='deb [arch=amd64 signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros/ubuntu focal main'

pi05_log 'platform: Ubuntu 20.04 / x86_64'
pi05_log "package manifest: $package_file (${#apt_packages[@]} packages)"
printf '  %s\n' "${apt_packages[@]}"
if [[ "$configure_ros_repo" == true ]]; then
  pi05_log "ROS key: ros/rosdistro@$ros_key_commit"
  pi05_log "ROS apt source: $ros_source_line"
else
  pi05_warn 'ROS apt repository setup is disabled by --skip-ros-repo'
fi

if [[ "$apply" != true ]]; then
  pi05_log 'DRY-RUN complete; rerun with --apply to make changes'
  exit 0
fi

pi05_confirm_apply "$assume_yes" "apt update/install and optional writes to $ros_keyring and $ros_source via sudo"
pi05_require_command sudo

pi05_log 'sudo apt-get update'
sudo -- apt-get update
pi05_log 'installing apt bootstrap tools'
sudo -- apt-get install --no-install-recommends -y ca-certificates curl gnupg lsb-release

if [[ "$configure_ros_repo" == true ]]; then
  temp_dir=$(mktemp -d /tmp/pi05-ros-key.XXXXXX)
  trap 'rm -rf -- "$temp_dir"' EXIT
  pi05_log "downloading pinned ROS signing key from $ros_key_url"
  curl --fail --location --silent --show-error "$ros_key_url" --output "$temp_dir/ros.asc"
  printf '%s  %s\n' "$ros_key_sha256" "$temp_dir/ros.asc" | sha256sum --check --status ||
    pi05_die 6 'ROS signing-key checksum mismatch'
  actual_fingerprint=$(gpg --show-keys --with-colons "$temp_dir/ros.asc" 2>/dev/null |
    awk -F: '$1 == "fpr" && !found {print $10; found=1}')
  [[ "$actual_fingerprint" == "$ros_key_fingerprint" ]] ||
    pi05_die 6 "ROS signing-key fingerprint mismatch: ${actual_fingerprint:-missing}"
  gpg --batch --yes --dearmor --output "$temp_dir/ros-archive-keyring.gpg" "$temp_dir/ros.asc"
  printf '%s\n' "$ros_source_line" >"$temp_dir/ros1-latest.list"

  if ! cmp -s "$temp_dir/ros-archive-keyring.gpg" "$ros_keyring" 2>/dev/null; then
    pi05_log "sudo install pinned keyring -> $ros_keyring"
    sudo -- install -o root -g root -m 0644 "$temp_dir/ros-archive-keyring.gpg" "$ros_keyring"
  else
    pi05_log 'ROS keyring already matches the pinned key'
  fi
  if ! cmp -s "$temp_dir/ros1-latest.list" "$ros_source" 2>/dev/null; then
    pi05_log "sudo install ROS source -> $ros_source"
    sudo -- install -o root -g root -m 0644 "$temp_dir/ros1-latest.list" "$ros_source"
  else
    pi05_log 'ROS apt source already matches the requested configuration'
  fi
  pi05_log 'sudo apt-get update after ROS repository configuration'
  sudo -- apt-get update
fi

pi05_log 'installing declared apt baseline; already-installed packages are retained'
sudo -- apt-get install --no-install-recommends -y "${apt_packages[@]}"
pi05_log 'apt baseline installation complete'
