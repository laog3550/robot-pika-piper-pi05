# robot-pika-piper-pi05

面向 **PI05 + 双 Pika Sense + 双 Piper** 的 ROS 1 遥操作工程。当前首要目标是打通
左右 Pika 到对应 Piper 的实时控制链路，为后续数据采集和 π0.5 部署提供稳定接口。

## 固定环境

- x86_64、Ubuntu 20.04、ROS Noetic、Python 3
- 左臂 CAN：`left_piper`
- 右臂 CAN：`right_piper`
- Pika/Piper 上游版本：`third_party/pi05-upstream.repos`
- 机器配置：Git 忽略的 `config/pi05.env`

USB-CAN 的左右身份仍由 `PI05_LEFT_CAN_*`、`PI05_RIGHT_CAN_*` 和现有配置脚本管理。
运行代码不使用 `can0`、`can1` 的枚举顺序猜测左右机械臂。

## 直接遥操作链路

```text
left Pika pose  -> vendor teleop/FK/IK -> /left_arm/joint_ctrl_raw  -> left_piper
right Pika pose -> vendor teleop/FK/IK -> /right_arm/joint_ctrl_raw -> right_piper
```

可选平滑模式在 IK 与 `joint_ctrl_raw` 之间加入低通及速度／加速度限制；默认仍为直连。

控制路径沿用厂商 `PikaAnyArm` 的 FK、IK 和 `teleop_piper_publish.py`。本项目只提供
无界面运行包装、左右命名空间以及固定 CAN 入口，不再插入授权租约、使能漂移阈值、
安全过滤状态机、双臂故障联锁或现场批准文件。

厂商 IK 在输入停止约 1 秒后停止发布目标。Piper 原生 enable、stop、reset、disable 服务
仍位于各自驱动命名空间内。

## 上机启动

首次迁移先复制并填写 Git 忽略的 `config/pi05.env`，按 `docs/environment-setup.md` 导入
固定上游版本并构建工作区，然后执行两侧 `scripts/configure_can.sh apply`。已有目标机更新
时必须保留原来的 `config/pi05.env`，代码更新不会覆盖它。

先按 `docs/direct-teleop.md` 启动 Pika 定位和本项目的 input-only 转发，使以下话题存在：

```text
/pi05/pika_input/left/pose
/pi05/pika_input/right/pose
```

然后选择需要的入口。已完成真机验证的单臂入口是平滑会话，它提供自动返回支撑姿态和
结束失能：

```bash
# 左臂 / 右臂：按 Enter 结束，或加 --duration 秒数自动结束
scripts/run_smoothed_teleop.sh left --apply
scripts/run_smoothed_teleop.sh right --apply

# 需要同时控制 Pika 夹爪时（会先校验该侧串口身份）
scripts/run_smoothed_teleop.sh right --apply --with-gripper --duration 20
```

只启动驱动与直连链路，不含自动回位，需要自行按 `docs/arm-commands.md` 返回并失能：

```bash
# 左臂
scripts/start_left_teleop.sh

# 右臂
scripts/start_right_teleop.sh

# 双臂
scripts/start_dual_teleop.sh
```

`start_*.sh` 的 `auto_enable` 默认为 `true`，即启动驱动后按厂商默认流程自动使能；
需要手动使能时显式传 `auto_enable:=false`。平滑会话入口固定以 `auto_enable:=false`
启动，再由脚本按 `reset → enable` 明确使能。启动脚本保持原有 ROS overlay、虚拟环境
和官方 Piper 模型路径，并在启动前检查配置好的 `left_piper`/`right_piper`。

Pika 遥操作的开始和停止继续使用厂商 `/teleop_trigger_l`、`/teleop_trigger_r` 服务及
设备触发动作。注意厂商 Trigger 响应的 `success` 字段恒为假，不能用来判断触发结果，
应以节点日志的 `start`／`close` 为准。左右臂可单独运行，也可通过双臂入口同时运行。

手动使能、失能、stop／恢复、归零、返回支撑姿态及微动命令见
[机械臂命令速查](docs/arm-commands.md)。

## 环境和设备配置

- 环境安装：`docs/environment-setup.md`
- 设备绑定：`docs/device-configuration.md`
- 硬件清单：`docs/hardware-inventory.md`
- 上游来源：`docs/upstream-dependencies.md`
- 接口与话题：`docs/ros-interface-matrix.md`
- 阶段状态：`docs/status.md`、`docs/project-progress.md`
- 文档索引：`docs/README.md`
- 历史阶段记录：`docs/stages/`

启动脚本依赖仓库外的固定 overlay（`~/pika_ros/install`、`~/robot/pi05-upstream-ws/devel`）
和官方 `piper_description` 模型路径，这些路径写在 `scripts/start_teleop.sh` 里。已有
环境、CAN、Pika 输入、Piper 反馈和诊断工具均继续保留。真实设备路径、USB bus-info
和现场配置不得写入仓库。

## 开发同步

仓库 skill 只负责检查改动、提交代码和推送当前分支到 GitHub，不再设置阶段、PR、硬件
验收或运动许可门禁。

## 当前进度

环境、设备绑定、只读诊断和双侧直接遥操作入口已实现；启动检查支持另一侧继续运行。
左右单臂的平滑遥操作已完成真机验证，包括自动返回支撑姿态、到位确认和结束失能；
双臂同时遥操作尚无成功运行记录。用户已自行测试机械臂并确认无异常，历史反馈差异
不作为当前阶段阻塞项。Pika 夹爪遥操作只完成右侧启动与拓扑集成测试，夹爪真机动作
尚未执行。详细状态和下一步见 [部署进度](docs/status.md) 与
[项目进度](docs/project-progress.md)。

左右臂共同的未使能支撑初始姿态已按用户截图确认为
`[0, 0, 0, 0, 0.567, 0] rad`，见 [初始姿态配置](config/arm-home.yaml)。
完成目标移动后需要返回时，先回到该姿态并确认静止，再失能。

## 当前范围

本阶段已实现直接／可选平滑遥操作、共同支撑初始姿态、手动/单臂自动回位，以及双臂
连续数据采集入口。采集 episode 会在人工任务完成后继续记录程序自动回位，双臂稳定到位
后才关闭轨迹，并同时保留原始 bag 与 LeRobot v3 数据；操作见
[双臂连续数据采集](docs/data-collection.md)。该入口已通过构建、离线状态机和合成数据转换
验证，仍需按文档完成真机分阶段验收。π0.5 模型部署尚未实现。
