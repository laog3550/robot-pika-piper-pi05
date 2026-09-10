#!/usr/bin/env bash

# Shared helpers for PI05 environment scripts. Callers enable strict mode.

pi05_log() {
  printf '[PI05] %s\n' "$*"
}

pi05_warn() {
  printf '[PI05] WARNING: %s\n' "$*" >&2
}

pi05_die() {
  local exit_code="$1"
  shift
  printf '[PI05] ERROR: %s\n' "$*" >&2
  exit "$exit_code"
}

pi05_require_command() {
  command -v "$1" >/dev/null 2>&1 || pi05_die 4 "required command not found: $1"
}

pi05_require_focal_amd64() {
  [[ -r /etc/os-release ]] || pi05_die 3 'cannot read /etc/os-release'

  local os_id os_version architecture
  os_id=$(. /etc/os-release && printf '%s' "${ID:-}")
  os_version=$(. /etc/os-release && printf '%s' "${VERSION_ID:-}")
  architecture=$(uname -m)

  [[ "$os_id" == ubuntu && "$os_version" == 20.04 ]] ||
    pi05_die 3 "unsupported OS: expected Ubuntu 20.04, got ${os_id:-unknown} ${os_version:-unknown}"
  [[ "$architecture" == x86_64 ]] ||
    pi05_die 3 "unsupported architecture: expected x86_64, got $architecture"
}

pi05_require_apply_yes_pair() {
  local apply="$1"
  local assume_yes="$2"
  if [[ "$assume_yes" == true && "$apply" != true ]]; then
    pi05_die 2 '--yes is valid only together with --apply'
  fi
}

pi05_confirm_apply() {
  local assume_yes="$1"
  local description="$2"

  pi05_warn "requested changes: $description"
  if [[ "$assume_yes" == true ]]; then
    pi05_log 'continuing because --apply --yes was explicitly supplied'
    return 0
  fi

  [[ -t 0 ]] || pi05_die 5 'refusing non-interactive changes; rerun interactively or add --apply --yes'
  local answer
  read -r -p 'Type APPLY to continue: ' answer
  [[ "$answer" == APPLY ]] || pi05_die 5 'change cancelled'
}

pi05_repo_root() {
  local common_dir
  common_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  cd "$common_dir/../.." && pwd
}

pi05_read_list() {
  local list_file="$1"
  local -n destination="$2"
  destination=()
  while IFS= read -r line || [[ -n "$line" ]]; do
    line=${line%%#*}
    line=${line//$'\r'/}
    [[ -n "${line//[[:space:]]/}" ]] || continue
    read -r line <<<"$line"
    destination+=("$line")
  done <"$list_file"
}
