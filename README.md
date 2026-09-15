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

然后选择需要的入口：

```bash
# 左臂
scripts/start_left_teleop.sh

# 右臂
scripts/start_right_teleop.sh

# 双臂
scripts/start_dual_teleop.sh
```

启动脚本保持原有 ROS overlay、虚拟环境和官方 Piper 模型路径。它会检查配置好的
`left_piper`/`right_piper`，随后启动对应驱动并使用厂商默认流程自动使能。可在命令行
覆盖 `auto_enable:=false`，由 Piper 原生服务手动使能。

Pika 遥操作的开始和停止继续使用厂商 `/teleop_trigger_l`、`/teleop_trigger_r` 服务及
设备触发动作。左右臂可单独运行，也可通过双臂入口同时运行。

## 环境和设备配置

- 环境安装：`docs/environment-setup.md`
- 设备绑定：`docs/device-configuration.md`
- 硬件清单：`docs/hardware-inventory.md`
- 上游来源：`docs/upstream-dependencies.md`
- 历史阶段记录：`docs/stages/`

已有环境、CAN、Pika 输入、Piper 反馈和诊断工具均继续保留。真实设备路径、USB bus-info
和现场配置不得写入仓库。

## 开发同步

仓库 skill 只负责检查改动、提交代码和推送当前分支到 GitHub，不再设置阶段、PR、硬件
验收或运动许可门禁。

## 当前范围

本阶段只实现直接遥操作。初始位置、快捷复原、数据采集格式和 π0.5 模型部署将在遥操作
真机打通后单独实现。
