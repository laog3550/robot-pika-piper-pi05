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
3. 确认 `/pi05/pika_input/left/pose` 和 `/pi05/pika_input/right/pose` 正在发布。
4. 运行 `scripts/start_left_teleop.sh` 或 `scripts/start_right_teleop.sh` 完成分侧联调。
5. 两侧分别通过后运行 `scripts/start_dual_teleop.sh`。
6. 使用 Pika 厂商触发动作开始或停止对应侧遥操作。

更新已有目标机仓库时，先保存 `config/pi05.env`，执行 `git pull` 和
`scripts/build_catkin.sh`，再确认该文件仍在且两路 `configure_can.sh check` 均通过。

## 接口

| 侧别 | Pika 输入 | Piper 反馈 | Piper 指令 | CAN |
|---|---|---|---|---|
| 左 | `/pi05/pika_input/left/pose` | `/joint_states_single_l` | `/left_arm/joint_ctrl_raw` | `left_piper` |
| 右 | `/pi05/pika_input/right/pose` | `/joint_states_single_r` | `/right_arm/joint_ctrl_raw` | `right_piper` |

使能成功后的关节轻微变化不参与软件判定。运行链路没有授权心跳、故障锁存、现场批准文件
或跨侧联锁。Piper 驱动提供的原生服务保持可用。

## 本阶段之外

初始位置、快捷复原、数据录制和 π0.5 模型部署不属于本次改动。
