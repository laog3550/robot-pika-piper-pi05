#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/check_upstream_manifest.sh [--manifest PATH] [--remote]

Validate the PI05 VCS manifest without importing sources into the repository.
The default mode checks its restricted YAML shape, GitHub HTTPS URLs and exact
40-character commits. --remote additionally fetches commit/tree metadata into
a temporary bare repository and confirms that each fixed commit has a root
LICENSE file. No checkout, sudo, submodule initialization or device access is
performed.
EOF
}

repo_root=$(pi05_repo_root)
manifest="$repo_root/third_party/pi05-upstream.repos"
remote=false

while (($#)); do
  case "$1" in
    --manifest)
      (($# >= 2)) || pi05_die 2 '--manifest requires a path'
      manifest="$2"
      shift 2
      ;;
    --remote)
      remote=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      pi05_die 2 "unknown argument: $1"
      ;;
  esac
done

[[ -r "$manifest" ]] || pi05_die 3 "manifest not readable: $manifest"

declare -a names=() urls=() versions=()
declare -A seen=()
current_name=''
current_type=''
current_url=''
current_version=''
seen_header=false

finish_entry() {
  [[ -n "$current_name" ]] || return 0
  [[ "$current_type" == git ]] || pi05_die 3 "$current_name must have type: git"
  [[ "$current_url" =~ ^https://github[.]com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+[.]git$ ]] ||
    pi05_die 3 "$current_name must use a canonical GitHub HTTPS .git URL"
  [[ "$current_version" =~ ^[0-9a-f]{40}$ ]] ||
    pi05_die 3 "$current_name must use an exact lowercase 40-character commit"
  names+=("$current_name")
  urls+=("$current_url")
  versions+=("$current_version")
}

while IFS= read -r line || [[ -n "$line" ]]; do
  line=${line//$'\r'/}
  [[ -n "${line//[[:space:]]/}" ]] || continue
  [[ "$line" == \#* ]] && continue
  if [[ "$line" == repositories: ]]; then
    [[ "$seen_header" == false ]] || pi05_die 3 'duplicate repositories header'
    seen_header=true
  elif [[ "$line" =~ ^[[:space:]]{2}([A-Za-z0-9_-]+):$ ]]; then
    matched_value=${BASH_REMATCH[1]}
    [[ "$seen_header" == true ]] || pi05_die 3 'repository entry appears before header'
    finish_entry
    current_name=$matched_value
    [[ -z "${seen[$current_name]+present}" ]] || pi05_die 3 "duplicate repository: $current_name"
    seen[$current_name]=1
    current_type=''
    current_url=''
    current_version=''
  elif [[ "$line" =~ ^[[:space:]]{4}type:[[:space:]]git$ ]]; then
    [[ -n "$current_name" && -z "$current_type" ]] || pi05_die 3 'duplicate or misplaced type field'
    current_type=git
  elif [[ "$line" =~ ^[[:space:]]{4}url:[[:space:]]([^[:space:]]+)$ ]]; then
    matched_value=${BASH_REMATCH[1]}
    [[ -n "$current_name" && -z "$current_url" ]] || pi05_die 3 'duplicate or misplaced url field'
    current_url=$matched_value
  elif [[ "$line" =~ ^[[:space:]]{4}version:[[:space:]]([^[:space:]]+)$ ]]; then
    matched_value=${BASH_REMATCH[1]}
    [[ -n "$current_name" && -z "$current_version" ]] || pi05_die 3 'duplicate or misplaced version field'
    current_version=$matched_value
  else
    pi05_die 3 "unsupported manifest line: $line"
  fi
done <"$manifest"
finish_entry

[[ "$seen_header" == true && ${#names[@]} -gt 0 ]] || pi05_die 3 'manifest has no repositories'
pi05_log "upstream manifest structure passed: ${#names[@]} repositories use exact commits"

if [[ "$remote" == true ]]; then
  pi05_require_command git
  verify_root=$(mktemp -d /tmp/pi05-upstream-verify.XXXXXX)
  trap 'rm -rf -- "$verify_root"' EXIT
  for index in "${!names[@]}"; do
    name=${names[$index]}
    url=${urls[$index]}
    version=${versions[$index]}
    bare_repo="$verify_root/$name.git"
    git init --bare --quiet "$bare_repo"
    git -C "$bare_repo" config extensions.partialClone origin
    git -C "$bare_repo" remote add origin "$url"
    git -C "$bare_repo" config remote.origin.promisor true
    git -C "$bare_repo" config remote.origin.partialclonefilter blob:none
    git -C "$bare_repo" fetch --quiet --depth=1 --filter=blob:none origin "$version"
    actual=$(git -C "$bare_repo" rev-parse FETCH_HEAD^{commit})
    [[ "$actual" == "$version" ]] || pi05_die 4 "$name fetched unexpected commit: $actual"
    git -C "$bare_repo" cat-file -e "$actual:LICENSE" 2>/dev/null ||
      pi05_die 4 "$name fixed commit has no root LICENSE file"
    pi05_log "$name remote commit and root LICENSE passed"
  done
fi
