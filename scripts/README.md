# 运维脚本

所有 `.sh` 脚本都接受 `--help`，参数错误或执行失败时返回非零状态码，唯一例外是
`start_teleop.sh`：它把第一个参数当侧别，`--help` 会被判为非法侧别并退出。直接执行
部分 `.py` 实现（例如 `check_piper_motor_telemetry.py`）需要先满足其导入依赖，
见下方“诊断实现”。S04 已实现环境相关入口：

- `bootstrap_ubuntu.sh`：安装 Ubuntu 20.04 与 ROS Noetic apt 基线；默认只显示计划
- `setup_rosdep.sh`：初始化、更新并按工作区安装 rosdep 依赖；先执行模拟
- `install_python_deps.sh`：创建可访问 Noetic/robotpkg 系统包的 Python 3.8 venv，安装
  固定依赖，并安装 S03 固定的 `piper_sdk`
- `build_catkin.sh`：使用 Noetic 与 `.venv` 增量构建 catkin 工作区；`--install` 使用
  与 venv 兼容的非 Debian Python 安装布局
- `check_environment.sh`：只读检查操作系统、apt、ROS、rosdep、Python 和工作区
- `discover_devices.sh`：只读列出 CAN 与 Pika 串口候选，不查询设备序列号
- `configure_can.sh check|apply <left|right>`：分侧按唯一 `gs_usb + bus-info` 绑定名称并配置 1 Mbps
- `configure_pika_serial.sh check|apply <left|right>`：分侧按唯一物理路径和 VID:PID 安装 Pika 串口别名
- `check_s07_hardware.sh`：只读校验 Git 忽略的 S07 双侧硬件现场记录，不访问设备
- `check_upstream_manifest.sh`：严格校验固定 commit 清单；可选 `--remote` 在临时裸仓库
  核对远端 commit 和根许可证
- `check_pika_stream.sh <left|right>`：S08 分侧只读检查 Pika JSON 完整率和候选频率；
  不写串口、不显示或保存传感器值
- `check_piper_can_stream.sh <left|right>`：S08 分侧被动检查 Piper 标准反馈 ID，并拒绝
  观察到控制/配置 ID 的窗口；不发送帧、不显示或保存 payload
- `check_piper_joint_stability.sh <left|right>`：被动统计六关节原始 CAN 反馈变化范围；可用
  `--exclude-joint` 排除正在执行的小步长目标，只审计非目标关节，不显示绝对角度或 payload
- `check_piper_motor_telemetry.sh <left|right>`：只接收 `0x251`–`0x256` 电机高速反馈并
  汇总样本数、绝对速度峰值和绝对电流峰值，不输出电机位置或 CAN payload
- `query_piper_firmware.sh check|apply <left|right>`：`check` 不发送帧；`apply` 需显式确认，
  仅通过固定 SDK 发送 `0x472`/`0x4AF` 查询并输出固件版本，不调用任何运动 API
- `query_piper_limits.sh check|apply <left|right>`：`check` 不发送帧；`apply` 需显式确认，
  仅通过固定 SDK 的 `0x472`/`0x4AF` 初始化查询读取六轴角度、速度和加速度上限，拒绝缺轴、
  非正速度/加速度或上下限颠倒的响应，不调用使能、运动或参数设置 API
- `check_pika_localization.sh`：S08 订阅既有 Pika 位姿/有效状态，支持 `--side left|right|both`，只报告汇总频率和
  有效样本数；`--require-motion` 可在机械臂禁用时要求两只 Pika 均检测到平移或旋转活动；
  不启动定位节点、不显示坐标或设备标识
- `publish_arm_home.py <left|right> [--apply]`：读取已确认的共同支撑初始姿态；默认只显示计划，
  `--apply` 向对应原始控制话题发布一次 5% 六关节目标，不使能、解除 stop、失能或控制夹爪
- `check_pika_mapping.py --duration 秒`：现场确认左右 Pika 的映射关系。采样窗口内只移动一
  只手柄，工具用 IMU 峰值找出正在被移动的一侧，并检查该侧位姿是否同步响应；位姿不动说明
  光学定位没跟上。同时核对“现场配置声明值”与“当前运行实例实际取值”是否一致。只订阅
  话题，不写设备。映射错误是静默的（两侧照样 120 Hz、照样 accurate），确认方法见
  [直接遥操作](../docs/direct-teleop.md) 的“左右映射确认”一节
- `start_pika_input.sh [--check]`：双 Pika 输入链路的正常入口。要求 `pika_L_code`/
  `pika_R_code` 存在，读取 `config/pika-mapping.env` 的 `PI05_PIKA_MAPPING_ORDER`，
  再以显式 `mapping_order:=` 启动 launch。缺失或非法时退出码 3，不静默串侧
- `run_smoothed_teleop.sh <left|right> --apply [选项]`：启动单臂平滑摇操；按 Enter
  或到达 `--duration 秒` 后关闭摇操，返回已确认的支撑初始姿态，确认到位后失能并关闭
  本次节点。另有 `--home-timeout 秒`（默认 180）、`--home-tolerance rad`（默认 0.02）、
  `--stable-seconds 秒`（默认 1.0）和只做启动与拓扑检查的 `--startup-only`。
  增加 `--with-gripper` 后，会校验并只读对应 Pika 串口，将其编码器映射到 Piper
  夹爪第七轴；该模式仅用于平滑会话
- `start_left_teleop.sh`：使用 `left_piper` 启动左侧直接遥操作
- `start_right_teleop.sh`：使用 `right_piper` 启动右侧直接遥操作
- `start_dual_teleop.sh`：使用两路固定 CAN 同时启动双臂直接遥操作

以下真机运维入口仍为后续阶段预留：

- `check_hardware.sh`：只读检查 CAN、串口、ROS 和反馈
- `start_pi05.sh`：按安全顺序启动
- `stop_pi05.sh`：停止命令源、禁用机械臂并退出节点
- `collect_diagnostics.sh`：采集版本、节点、话题、CAN 错误和日志

## 启动入口

- `start_teleop.sh <left|right|dual> [roslaunch 参数]`：三个 `start_*_teleop.sh` 的实际
  实现。按顺序加载固定 overlay 与 venv，运行 `check_teleop_start.py` 做 ROS 图冲突检查，
  再执行 `configure_can.sh check`，最后启动对应 launch。它不会启动 Pika 定位，必须先按
  [直接遥操作](../docs/direct-teleop.md) 启动 input-only 转发
- `run_smoothed_teleop.py <left|right> --apply`：`run_smoothed_teleop.sh` 调用的会话
  控制器，负责拓扑检查、`reset → enable`、触发遥操作、关闭输出、返回支撑姿态并失能。
  `--check-only` 仅供 `run_smoothed_teleop.sh` 内部预检使用
- `check_teleop_start.py <left|right|dual>`：只读查询 ROS master，拒绝本侧已有的驱动或
  遥操作节点，允许对侧命名空间和 `piper_readonly_feedback` 继续运行，并要求目标侧
  `/pi05/pika_input/<side>/pose` 已有发布者

## 诊断实现

带 `.sh` 包装器的工具由同名 `.py` 实现，包装器只负责加载环境与参数校验，直接调用
`.py` 时需要自行准备 ROS/venv 环境。没有包装器的两个：

- `check_piper_feedback_decoding.py <left|right>`：同一批真实 CAN 帧分别用项目解码器与
  厂商 `C_PiperParserV2` 解析并逐帧比对，只接收、不发送
- `diagnose_pika_tracking.py`、`diagnose_piper_command_feedback.py`：分别输出 Pika 跟踪
  和命令/反馈相关性的 JSON 诊断，含 `diagnostic_tags`，但没有安全结论能力

`scripts/lib/common.sh` 和 `scripts/lib/device_config.sh` 是被其他脚本 source 的共享库，
用于日志、`apply` 确认、`config/pi05.env` 白名单解析和双侧身份分离校验，不单独执行。
部分 `.py` 依赖 `pi05_control` 包或 `piper_sdk`，直接运行前需要设置 `PYTHONPATH` 或
激活 `.venv`；对应的 `.sh` 包装器已经处理好。

机器唯一参数从 `config/pi05.env` 读取，不写入脚本。环境安装和设备配置均把只读检查
与 apply 分开；需要 `sudo` 的动作会先打印目标并要求输入 `APPLY`，或要求调用方显式
传入 `apply --yes`。设备身份必须唯一匹配，且 CAN 配置不会发送 CAN 帧。脚本不会执行
发行版升级、包删除、机械臂使能或进程终止。
