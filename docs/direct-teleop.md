# PI05 直接遥操作

## 目标

按 PikaAnyArm 的整体结构，将左右 Pika 位姿分别连接到对应 Piper 的 FK、IK 和关节控制，
优先取得可用于后续数据采集的双臂遥操作能力。

## 保留的现场配置

重构不改变 `PI05_*` 环境变量、ROS overlay 路径、串口别名或 USB-CAN 身份绑定。Piper
驱动默认继续使用 `left_piper` 和 `right_piper`，可通过 launch 的 `can_port` 参数显式覆盖。

## 启动顺序

首次迁移或 USB-CAN 物理端口发生变化时，先从本机保存的值恢复 Git 忽略的
`config/pi05.env`，再执行：

```bash
scripts/configure_can.sh apply left
scripts/configure_can.sh apply right
```

日常启动顺序：

1. 按现有部署启动 ROS master。
2. 加载保存 `pika_L_code`、`pika_R_code` 的本机环境，然后启动双 Pika 输入：
   `roslaunch pi05_pika_input pika_input_only.launch start_locator:=true mapping_order:=swapped left:=true right:=true`。
   若现场绑定是直连顺序，则使用已经确认的 `mapping_order:=direct`。
3. 确认 `/pi05/pika_input/left/pose` 和 `/pi05/pika_input/right/pose` 正在发布，
   并运行 `scripts/check_pika_localization.sh --side both --duration 10` 检查实际频率与定位有效性。
   工具默认检查当前 input-only 话题；仅检查一侧时使用 `--side left` 或 `--side right`。
   检查旧厂商话题时显式使用 `--topic-layout vendor`。
   若状态为 inaccurate，先恢复定位，再继续分侧遥操作。
4. 运行 `scripts/start_left_teleop.sh` 或 `scripts/start_right_teleop.sh` 完成分侧联调。
5. 两侧分别通过后，退出已有分侧驱动和遥操作，再运行 `scripts/start_dual_teleop.sh`。
6. 使用 Pika 厂商触发动作开始或停止对应侧遥操作。

更新已有目标机仓库时，先保存 `config/pi05.env`，执行 `git pull` 和
`scripts/build_catkin.sh`，再确认该文件仍在且两路 `configure_can.sh check` 均通过。

左臂运行时可另开终端启动右臂，反之亦然。启动检查只拒绝本侧冲突；双臂入口
检查两侧。既有 `piper_readonly_feedback` 节点可继续运行；本侧已有运动驱动或
未明确归属左右命名空间的旧 Piper/teleop 节点仍需先退出。
检查话题存在只说明有注册发布者，实际输入频率和定位有效性需在联调时确认。

## 接口

| 侧别 | Pika 输入 | Piper 反馈 | Piper 指令 | CAN |
|---|---|---|---|---|
| 左 | `/pi05/pika_input/left/pose` | `/joint_states_single_l` | `/left_arm/joint_ctrl_raw` | `left_piper` |
| 右 | `/pi05/pika_input/right/pose` | `/joint_states_single_r` | `/right_arm/joint_ctrl_raw` | `right_piper` |

使能成功后的关节轻微变化不参与软件判定。运行链路没有授权心跳、故障锁存、现场批准文件
或跨侧联锁。Piper 驱动提供的原生服务保持可用。

## 可选关节目标平滑

厂商 IK 以 50 Hz 直接发布目标，原始驱动在消息未指定速度时使用 50% 速度。
若遥操作抖动明显，可启用本项目的轻量平滑节点：

```bash
# 右臂，保持手动使能
scripts/start_right_teleop.sh auto_enable:=false smooth_commands:=true

# 左臂
scripts/start_left_teleop.sh auto_enable:=false smooth_commands:=true

# 双臂
scripts/start_dual_teleop.sh auto_enable:=false smooth_commands:=true
```

平滑器位于 IK 和驱动之间，默认使用：

- 50 Hz 输出；
- `0.12 s` 低通时间常数；
- `0.30 rad/s` 目标速度上限；
- `0.50 rad/s²` 目标加速度上限；
- `0.0005 rad` 死区；
- Piper 驱动速度百分比 `20%`。

例如希望更柔和、允许更明显延迟：

```bash
scripts/start_right_teleop.sh auto_enable:=false smooth_commands:=true \
  smoothing_time_constant:=0.20 \
  smoothing_max_velocity:=0.20 \
  smoothing_max_acceleration:=0.30 \
  smoothing_driver_speed_percent:=15
```

时间常数越大、速度和加速度越低，动作越平滑，但跟手延迟越明显。平滑器只处理
J1–J6，不发送夹爪目标；输入超过 `0.25 s` 未更新时停止继续发布，恢复后从最新机械臂
反馈重新起步。它不是运动安全状态机，仍需使用原生 stop／急停。

该功能默认关闭，现有直连行为不变。上线前先分侧使用保守参数验证，再用于双臂。

## 不接运动驱动的组件联调

有双侧只读反馈时，可使用以下入口验证厂商组件启动和 FK 链路。
先加载 [命令速查](arm-commands.md) 中的 ROS 环境；官方 Piper 模型路径与启动脚本一致。

```bash
export ROS_PACKAGE_PATH="/home/mips/robot/pi05-upstream-src/piper_ros/src/piper_description:$ROS_PACKAGE_PATH"
roslaunch pi05_left_teleop dual_teleop.launch \
  start:=true connect_drivers:=false auto_enable:=false \
  left_feedback_topic:=/left_arm/joint_states_raw \
  right_feedback_topic:=/right_arm/joint_states_raw \
  left_command_topic:=/pi05/rehearsal/left/joint_target \
  right_command_topic:=/pi05/rehearsal/right/joint_target
```

这组参数不启动运动驱动，并将 IK 目标输出至独立诊断话题。不要将诊断话题连接到
运动驱动；该联调不调用触发开始服务。结束时在该终端按 Ctrl+C。
实际遥操作继续使用原有启动脚本及默认反馈／控制话题。

2026-09-16 已运行约 18 秒：六个组件持续运行，左／右 FK 收到 2855／2840 个
位姿样本，诊断输出无订阅者，测试节点正常退出。未验证触发后的 IK 跟随或真机运动。

## 本阶段之外

左右臂共同的支撑初始姿态、手动返回入口及单臂平滑会话结束后的自动回位流程已记录在
[机械臂命令速查](arm-commands.md)。数据录制和 π0.5 模型部署不属于当前直接遥操作改动。
