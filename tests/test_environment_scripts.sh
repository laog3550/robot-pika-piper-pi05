#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
scripts=(
  scripts/bootstrap_ubuntu.sh
  scripts/setup_rosdep.sh
  scripts/install_python_deps.sh
  scripts/build_catkin.sh
  scripts/check_environment.sh
)

for relative_path in "${scripts[@]}" scripts/lib/common.sh; do
  bash -n "$repo_root/$relative_path"
done

for relative_path in "${scripts[@]}"; do
  "$repo_root/$relative_path" --help >/dev/null
  if "$repo_root/$relative_path" --definitely-invalid >/dev/null 2>&1; then
    printf 'expected invalid option to fail: %s\n' "$relative_path" >&2
    exit 1
  fi
done

fake_dir=$(mktemp -d /tmp/pi05-script-test.XXXXXX)
trap 'rm -rf -- "$fake_dir"' EXIT
marker="$fake_dir/sudo-called"
printf '#!/usr/bin/env bash\nprintf called >%q\nexit 99\n' "$marker" >"$fake_dir/sudo"
chmod +x "$fake_dir/sudo"

PATH="$fake_dir:$PATH" "$repo_root/scripts/bootstrap_ubuntu.sh" >"$fake_dir/bootstrap.out"
PATH="$fake_dir:$PATH" "$repo_root/scripts/setup_rosdep.sh" >"$fake_dir/rosdep.out"
PATH="$fake_dir:$PATH" "$repo_root/scripts/install_python_deps.sh" >"$fake_dir/python.out"
[[ ! -e "$marker" ]] || { printf 'dry-run unexpectedly invoked sudo\n' >&2; exit 1; }
grep -q 'DRY-RUN complete' "$fake_dir/bootstrap.out"
grep -q 'DRY-RUN complete' "$fake_dir/rosdep.out"
grep -q 'DRY-RUN complete' "$fake_dir/python.out"

if "$repo_root/scripts/install_python_deps.sh" --index-url http://example.invalid/simple >/dev/null 2>&1; then
  printf '%s\n' 'insecure --index-url unexpectedly succeeded' >&2
  exit 1
fi
if grep -q '^pin==' "$repo_root/config/python-requirements-noetic.txt"; then
  printf '%s\n' 'PyPI pin wheel must not be used for the CasADi binding' >&2
  exit 1
fi
grep -q '^robotpkg-py38-casadi=3.6.7$' "$repo_root/config/apt-packages-noetic.txt"
grep -q '^robotpkg-py38-pinocchio=3.2.0$' "$repo_root/config/apt-packages-noetic.txt"
grep -q '^robotpkg-py38-eigenpy=3.10.0$' "$repo_root/config/apt-packages-noetic.txt"
grep -q '^robotpkg-py38-hpp-fcl=2.4.5$' "$repo_root/config/apt-packages-noetic.txt"
grep -q -- '--system-site-packages' "$repo_root/scripts/install_python_deps.sh"
grep -q 'pi05-system-packages.pth' "$repo_root/scripts/install_python_deps.sh"
grep -q -- 'data_msgs piper_msgs' "$repo_root/scripts/build_catkin.sh"
grep -q -- 'data_msgs piper_msgs' "$repo_root/scripts/setup_rosdep.sh"

for guarded_script in bootstrap_ubuntu.sh setup_rosdep.sh; do
  if PATH="$fake_dir:$PATH" "$repo_root/scripts/$guarded_script" --apply </dev/null >/dev/null 2>&1; then
    printf 'non-interactive --apply unexpectedly succeeded: %s\n' "$guarded_script" >&2
    exit 1
  fi
done
[[ ! -e "$marker" ]] || { printf 'refused --apply unexpectedly invoked sudo\n' >&2; exit 1; }

mkdir -p "$fake_dir/catkin" "$fake_dir/venv/bin"
ln -s "$repo_root/src" "$fake_dir/catkin/src"
ln -s /usr/bin/python3 "$fake_dir/venv/bin/python"
printf '%s\n' ':' >"$fake_dir/venv/bin/activate"
"$repo_root/scripts/build_catkin.sh" \
  --workspace "$fake_dir/catkin" \
  --venv "$fake_dir/venv" \
  --jobs 2 \
  --skip-rosdep-check >"$fake_dir/build.out"
grep -q 'catkin build complete' "$fake_dir/build.out"

"$repo_root/scripts/build_catkin.sh" \
  --workspace "$fake_dir/catkin" \
  --venv "$fake_dir/venv" \
  --jobs 2 \
  --skip-rosdep-check \
  --install >"$fake_dir/install.out"
grep -q 'catkin build complete' "$fake_dir/install.out"
grep -q 'SETUPTOOLS_DEB_LAYOUT=OFF' "$fake_dir/install.out"

if "$repo_root/scripts/bootstrap_ubuntu.sh" --yes >/dev/null 2>&1; then
  printf '%s\n' '--yes without --apply unexpectedly succeeded' >&2
  exit 1
fi

printf 'environment script contract tests: PASS\n'
