#!/usr/bin/env bash
# 契约测试：start_pika_input.sh 必须把左右映射当作显式现场配置，缺失或非法时明确失败，
# 绝不静默放行（静默串侧会让“操作一只手柄、另一只臂不动”，历史上排查成本很高）。
set -Eeuo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
wrapper="$repo_root/scripts/start_pika_input.sh"
failures=0

expect_exit() {
  local expected="$1" label="$2"
  shift 2
  local status=0
  "$@" >/dev/null 2>&1 || status=$?
  if [[ "$status" != "$expected" ]]; then
    echo "FAIL $label: 期望 exit=$expected，实际 exit=$status" >&2
    failures=$((failures + 1))
  else
    echo "ok   $label (exit=$status)"
  fi
}

# 用临时仓库副本，避免动到现场配置
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/scripts" "$tmp/config"
cp "$wrapper" "$tmp/scripts/"
cp "$repo_root/config/pika-mapping.env.example" "$tmp/config/"
cp -r "$repo_root/scripts/lib" "$tmp/scripts/lib"

run_check() {
  pika_L_code="${1:-}" pika_R_code="${2:-}" PI05_PIKA_MAPPING_ORDER="${3:-}" \
    bash "$tmp/scripts/start_pika_input.sh" --check
}
export -f run_check

expect_exit 3 "缺少手柄 code 时拒绝" env -u pika_L_code -u pika_R_code \
  bash "$tmp/scripts/start_pika_input.sh" --check
expect_exit 3 "映射文件缺失且无环境变量时拒绝" env pika_L_code=x pika_R_code=y \
  bash "$tmp/scripts/start_pika_input.sh" --check

printf 'PI05_PIKA_MAPPING_ORDER=sideways\n' >"$tmp/config/pika-mapping.env"
expect_exit 3 "非法映射取值时拒绝" env pika_L_code=x pika_R_code=y \
  bash "$tmp/scripts/start_pika_input.sh" --check

printf 'PI05_PIKA_MAPPING_ORDER=swapped\n' >"$tmp/config/pika-mapping.env"
if ! env pika_L_code=x pika_R_code=y bash "$tmp/scripts/start_pika_input.sh" --check \
    | grep -q "mapping_order=swapped"; then
  echo "FAIL 合法配置应通过并回显取值" >&2
  failures=$((failures + 1))
else
  echo "ok   合法配置通过并回显取值"
fi

# 环境变量优先于文件，便于临时覆盖
if ! env pika_L_code=x pika_R_code=y PI05_PIKA_MAPPING_ORDER=direct \
    bash "$tmp/scripts/start_pika_input.sh" --check | grep -q "mapping_order=direct"; then
  echo "FAIL 显式环境变量应覆盖配置文件" >&2
  failures=$((failures + 1))
else
  echo "ok   显式环境变量覆盖配置文件"
fi

# 模板必须留空，避免把某台机器的结论当成默认值
if grep -qE '^PI05_PIKA_MAPPING_ORDER=\s*$' "$repo_root/config/pika-mapping.env.example"; then
  echo "ok   仓库模板中取值为空"
else
  echo "FAIL 仓库模板不应预填 mapping_order" >&2
  failures=$((failures + 1))
fi

# 模板不能被 git 跟踪以外的路径泄露真实取值：模板里不得出现 direct/swapped 赋值
if grep -qE '^PI05_PIKA_MAPPING_ORDER=(direct|swapped)' \
    "$repo_root/config/pika-mapping.env.example"; then
  echo "FAIL 模板不得预填 direct/swapped" >&2
  failures=$((failures + 1))
else
  echo "ok   模板未预填具体取值"
fi

if ((failures)); then
  echo "Pika 映射配置契约测试: FAIL ($failures)" >&2
  exit 1
fi
echo "Pika 映射配置契约测试: PASS"
