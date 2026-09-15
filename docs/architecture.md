# PI05 双臂遥操作架构

当前运行链路沿用厂商 PikaAnyArm 的 FK、IK 和遥操作实现，并通过同一套 `side` 参数分别实例化左右两侧：

```text
Pika Left  ─► FK/teleop/IK ─► /left_arm/joint_ctrl_raw  ─► left_piper
Pika Right ─► FK/teleop/IK ─► /right_arm/joint_ctrl_raw ─► right_piper
```

`left_piper`、`right_piper` 是目标机既有 USB-CAN 固定别名。Pika 串口、SteamVR 映射和其余机器参数仍由目标机的 `config/pi05.env` 与 `PI05_*` 环境变量提供，仓库不写死真实端口。左右链路使用相同组件，通过命名空间和 remap 隔离。

## 启动路径

- `side_teleop.launch`：通用单侧实现。
- `left_teleop.launch`、`right_teleop.launch`：分侧兼容入口。
- `dual_teleop.launch`：同时启动左右遥操作。
- `scripts/start_teleop.sh left|right|dual`：目标机统一入口。

启动脚本先加载固定的 ROS、PikaAnyArm、项目工作区和 Python 环境，确认目标侧 Pika 位姿正在发布并检查 CAN 别名，然后启动驱动及厂商遥操作链路。驱动默认自动使能。停止时在运行终端按 `Ctrl-C`；驱动仍保留厂商的分侧 enable、stop、reset 和 go-zero 服务。

历史 S01–S12 调试、事故和验收资料继续保存在 `docs/`，只用于追溯，不再描述当前运行链路。当前迁移与操作步骤以 [direct-teleop.md](direct-teleop.md) 为准。
