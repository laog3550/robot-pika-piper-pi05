#!/usr/bin/env bash
# 确定性收尾：停掉某侧遗留的遥操作栈（驱动 + FK/IK/平滑器 + 夹爪输入 + 遥操作）。
#
# 为什么需要它：会话在“未安全结束”时（退出码 4）会故意保留节点，方便先检查机械臂。
# 但如果没有明确的收尾手段，这些节点会一直占着 CAN 和串口，导致之后每次启动都失败。
#
# 安全前提：kill 驱动会切断指令源，控制器看门狗随后可能让机械臂失力。执行前先确认
# 机械臂已支撑或已回到支撑姿态。脚本默认只显示计划，加 --apply 才真正停止。
set -Eeuo pipefail

usage() {
  echo "usage: $0 <left|right|all> [--apply]"
  echo "  停止遗留的遥操作栈。默认只列出将要停止的进程，不做修改。"
  echo "  --apply 才真正发送 SIGINT/SIGTERM。"
}

side=${1:-}
case "$side" in left|right|all) ;; *) usage >&2; exit 2 ;; esac
shift || true

apply=false
for argument in "$@"; do
  case "$argument" in
    --apply) apply=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $argument" >&2; usage >&2; exit 2 ;;
  esac
done

# 用命令行特征匹配，不依赖 ROS master 是否可用（master 常常已经退出）。
pattern='pi05_left_teleop/component\.py|joint_command_smoother\.py|gripper_input\.py|safe_gripper_piper_driver\.py|piper_ctrl_single_node\.py'
if [[ "$side" != all ]]; then
  pattern="(${pattern}).*--side ${side}|(${pattern}).*${side}_arm"
fi

mapfile -t pids < <(ps -eo pid,args | grep -E "$pattern" | grep -v grep | awk '{print $1}')

if (( ${#pids[@]} == 0 )); then
  echo "[PI05] ${side}: 没有发现遗留的遥操作进程。"
  exit 0
fi

echo "[PI05] ${side}: 发现 ${#pids[@]} 个遗留进程："
ps -o pid,etime,args -p "$(IFS=,; echo "${pids[*]}")" 2>/dev/null | tail -n +2 | cut -c1-160

if [[ "$apply" != true ]]; then
  echo
  echo "默认只显示计划。确认机械臂已支撑后，加 --apply 执行停止："
  echo "  $0 $side --apply"
  exit 0
fi

echo
echo "[PI05] 先停驱动（切断指令源）..."
for pid in "${pids[@]}"; do
  if grep -q "safe_gripper_piper_driver\|piper_ctrl_single_node" "/proc/$pid/cmdline" 2>/dev/null; then
    kill "$pid" 2>/dev/null && echo "  停止驱动 $pid"
  fi
done
sleep 2

echo "[PI05] 停止其余节点..."
for pid in "${pids[@]}"; do
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null && echo "  停止 $pid"
  fi
done
sleep 2

remaining=()
for pid in "${pids[@]}"; do
  kill -0 "$pid" 2>/dev/null && remaining+=("$pid")
done
if (( ${#remaining[@]} )); then
  echo "[PI05] 仍未退出，发送 SIGKILL: ${remaining[*]}"
  kill -9 "${remaining[@]}" 2>/dev/null || true
  sleep 1
fi

echo
echo "[PI05] 收尾结果："
left_over=$(ps -eo pid,args | grep -E "$pattern" | grep -v grep || true)
if [[ -n "$left_over" ]]; then
  echo "  仍有残留进程：" >&2
  echo "$left_over" >&2
  exit 1
fi
echo "  遥操作节点已全部停止。"
for device in /dev/pi05-pika-left /dev/pi05-pika-right; do
  [[ -e "$device" ]] || continue
  if lsof "$device" >/dev/null 2>&1; then
    echo "  $device 仍被占用" >&2
  else
    echo "  $device 已释放"
  fi
done
