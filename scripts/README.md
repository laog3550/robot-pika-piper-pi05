# 运维脚本

所有脚本支持 `--help`，参数错误或执行失败时返回非零状态码。S04 已实现环境相关入口：

- `bootstrap_ubuntu.sh`：安装 Ubuntu 20.04 与 ROS Noetic apt 基线；默认只显示计划
- `setup_rosdep.sh`：初始化、更新并按工作区安装 rosdep 依赖；先执行模拟
- `install_python_deps.sh`：创建可访问 Noetic/robotpkg 系统包的 Python 3.8 venv，安装
  固定依赖，并安装 S03 固定的 `piper_sdk`
- `build_catkin.sh`：使用 Noetic 与 `.venv` 增量构建 catkin 工作区
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
- `check_pika_localization.sh`：S08 订阅既有左右 Pika 位姿/有效状态，只报告汇总频率和
  有效样本数；不启动定位节点、不显示坐标或设备标识

以下真机运维入口仍为后续阶段预留：

- `check_hardware.sh`：只读检查 CAN、串口、ROS 和反馈
- `start_pi05.sh`：按安全顺序启动
- `stop_pi05.sh`：停止命令源、禁用机械臂并退出节点
- `collect_diagnostics.sh`：采集版本、节点、话题、CAN 错误和日志

机器唯一参数从 `config/pi05.env` 读取，不写入脚本。环境安装和设备配置均把只读检查
与 apply 分开；需要 `sudo` 的动作会先打印目标并要求输入 `APPLY`，或要求调用方显式
传入 `apply --yes`。设备身份必须唯一匹配，且 CAN 配置不会发送 CAN 帧。脚本不会执行
发行版升级、包删除、机械臂使能或进程终止。
