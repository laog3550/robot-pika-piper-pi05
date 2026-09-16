#!/usr/bin/env bash
# 启动双 Pika 输入链路，并强制使用现场实测的左右映射。
#
# 映射取值不写在仓库里（它是现场事实，取决于哪只手柄的 code 存在哪个环境变量），
# 而是读取 Git 忽略的 config/pika-mapping.env。缺失或非法时明确失败，不会静默串侧。
set -Eeuo pipefail

usage() {
  echo "usage: $0 [--check] [roslaunch args...]"
  echo "  读取 config/pika-mapping.env 的 PI05_PIKA_MAPPING_ORDER 后启动 input-only。"
  echo "  --check 只校验映射配置与手柄 code，不启动任何节点。"
}

check_only=false
if [[ ${1:-} == -h || ${1:-} == --help ]]; then
  usage
  exit 0
fi
if [[ ${1:-} == --check ]]; then
  check_only=true
  shift
fi

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
mapping_file="$repo_root/config/pika-mapping.env"

# 手柄 code 来自机器本机环境；映射取值来自现场配置文件。
for name in pika_L_code pika_R_code; do
  if [[ -z "${!name:-}" ]]; then
    echo "缺少 $name：先加载保存手柄 code 的本机环境。" >&2
    exit 3
  fi
done
if [[ -z "${PI05_PIKA_MAPPING_ORDER:-}" && -f "$mapping_file" ]]; then
  # shellcheck disable=SC1090
  source "$mapping_file"
fi
case "${PI05_PIKA_MAPPING_ORDER:-}" in
  direct|swapped) ;;
  "")
    echo "未设置映射取值。请先确认后写入 $mapping_file：" >&2
    echo "  cp $repo_root/config/pika-mapping.env.example $mapping_file" >&2
    echo "  scripts/check_pika_mapping.py --duration 10   # 确认方法见 docs/direct-teleop.md" >&2
    exit 3
    ;;
  *)
    echo "非法的 PI05_PIKA_MAPPING_ORDER=${PI05_PIKA_MAPPING_ORDER}（只能是 direct 或 swapped）。" >&2
    exit 3
    ;;
esac

echo "[PI05] Pika 映射：mapping_order=${PI05_PIKA_MAPPING_ORDER}（来源：${mapping_file}）"
if [[ "$check_only" == true ]]; then
  echo "[PI05] 映射配置检查通过；未启动节点。"
  exit 0
fi

source /opt/ros/noetic/setup.bash --extend
source /home/mips/pika_ros/install/setup.bash --extend
source /home/mips/robot/pi05-upstream-ws/devel/setup.bash --extend
source "$repo_root/devel/setup.bash" --extend
source "$repo_root/.venv/bin/activate"

exec roslaunch pi05_pika_input pika_input_only.launch \
  start_locator:=true "mapping_order:=$PI05_PIKA_MAPPING_ORDER" \
  left:=true right:=true "$@"
