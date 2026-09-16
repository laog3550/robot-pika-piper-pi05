# PI05 双臂遥操作架构

当前运行链路沿用厂商 PikaAnyArm 的 FK、IK 和遥操作实现，并通过同一套 `side` 参数
分别实例化左右两侧。直连模式：

```text
Pika Left  ─► FK/teleop/IK ─► /left_arm/joint_ctrl_raw  ─► left_piper
Pika Right ─► FK/teleop/IK ─► /right_arm/joint_ctrl_raw ─► right_piper
```

平滑模式在同一链路中间插入平滑器，并可选择把 Pika 夹爪编码器接到 Piper 夹爪：

```text
Pika pose ─► teleop ─► IK ─► <side>_arm/teleop/ik_target_raw ─┐
Pika 夹爪编码器 ─► /pi05/pika_input/<side>/gripper ───────────┤
                                                              ▼
                             joint_command_smoother ─► <side>_arm/joint_ctrl_raw
```

平滑器是唯一的关节目标发布者，输出 50 Hz、低通滤波并限制速度与加速度；启用夹爪时
把夹爪目标作为第七轴一并发布，任一输入超过 `0.25 s` 未刷新就停止整组输出。两种模式
由 `side_teleop.launch` 的 `smooth_commands` 参数选择，默认直连。

`left_piper`、`right_piper` 是目标机既有 USB-CAN 固定别名。Pika 串口、CAN 身份和其余机器
参数由目标机的 `config/pi05.env` 与 `PI05_*` 环境变量提供，仓库不写死真实端口；SteamVR
到左右手部的映射（`pika_L_code`／`pika_R_code`）来自启动终端已加载的本机环境，不在
`config/pi05.env` 里。左右链路使用相同组件，通过命名空间和 remap 隔离。

FK 与 IK 使用 `tool_offset_m`（默认 `0.19` m）作为 `gripper_xyzrpy` 的 X 分量，即末端工具
偏移。该值沿用上游默认，未做实测标定，需要时按侧在 launch 命令行覆盖。

## 启动路径

- `side_teleop.launch`：通用单侧实现，两种模式共用。
- `left_teleop.launch`、`right_teleop.launch`：分侧兼容入口。
- `dual_teleop.launch`：同时启动左右遥操作。
- `s09_single_arm_driver.launch`：分侧封装厂商 Piper 驱动，`safe_gripper_enable`
  为真时改用夹爪模式驱动。
- `scripts/start_teleop.sh left|right|dual`：目标机统一入口。
- `scripts/run_smoothed_teleop.sh <left|right> --apply`：单臂平滑会话入口，负责启动、
  运行期间的门控、结束时返回支撑姿态并失能。

启动脚本先加载固定的 ROS、PikaAnyArm、项目工作区和 Python 环境，确认目标侧 Pika 位姿
正在发布并检查 CAN 别名，然后启动驱动及厂商遥操作链路。`start_teleop.sh` 的
`auto_enable` 默认为 `true`，即驱动启动后自动使能；平滑会话固定以 `auto_enable:=false`
启动，再由脚本按 `reset → enable` 明确使能，并在结束流程中确认回位后才失能。驱动仍
保留厂商的分侧 enable、stop、reset 和 go-zero 服务。

历史 S01–S12 调试、事故和验收资料继续保存在 `docs/`，只用于追溯，不再描述当前运行
链路。当前迁移与操作步骤以 [direct-teleop.md](direct-teleop.md) 为准，完整接口清单见
[ros-interface-matrix.md](ros-interface-matrix.md)。
