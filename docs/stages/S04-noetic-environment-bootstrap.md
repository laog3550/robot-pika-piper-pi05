# S04 Ubuntu 20.04 + ROS Noetic 环境流程

## 目标

为 x86_64 Ubuntu 20.04 + ROS Noetic 建立可重复执行、失败可见、默认无副作用的 apt、
rosdep、Python 依赖和 catkin 构建流程。所有入口必须提供帮助，错误返回非零；sudo
动作不得静默发生。

## 完成内容

- 增加声明式 apt 清单与 Python 3.8 直接依赖固定清单。
- 增加 apt/ROS 引导脚本，固定 ROS key commit、SHA-256 和指纹。
- 增加 rosdep 初始化、更新、模拟和安装脚本。
- 增加隔离 `.venv` 的 Python 安装脚本，并校验 S03 `piper_sdk` SHA。
- 增加 catkin 增量构建脚本与统一只读环境检查。
- 增加脚本契约测试，验证帮助、错误码、dry-run 和“默认不调用 sudo”。
- 增加操作者文档并更新 README 快速开始与目录索引。

## 接口与兼容性

支持 Ubuntu 20.04 x86_64、ROS Noetic 和 `/usr/bin/python3` 3.8。脚本的稳定公共入口为：

- `scripts/bootstrap_ubuntu.sh [--apply] [--yes] [--skip-ros-repo]`
- `scripts/setup_rosdep.sh [--workspace PATH] [--apply] [--yes] [--skip-init]`
- `scripts/install_python_deps.sh [--venv PATH] [--source-root PATH] [--apply] [--yes]`
- `scripts/build_catkin.sh [--workspace PATH] [--venv PATH] [--jobs N] [--install]`
- `scripts/check_environment.sh [--workspace PATH] [--venv PATH]`

默认安装命令均为 dry-run。`--yes` 不能脱离 `--apply` 使用。环境检查不访问网络和
硬件，不记录主机名、IP、USB/设备序列号或环境变量。

## 验证记录

验证日期：2026-09-10。

- `bash tests/test_environment_scripts.sh`：通过；五个入口的帮助、非法参数失败、三类
  安装 dry-run 和默认不调用 sudo 均通过。
- `bash -n scripts/*.sh scripts/lib/common.sh tests/test_environment_scripts.sh`：通过。
- 临时 catkin 工作区构建命令：通过；使用 `/usr/bin/python3` 构建当前两个骨架包，
  产物只写入 `/tmp`。
- `/usr/bin/python3 --version`：3.8.10，符合 Noetic 基线。
- 临时 `/usr/bin/python3 -m venv`：失败，确认本机缺少 `python3-venv`；已纳入 apt 清单。
- Python wheel 联网安装：未通过；当前网络链路对新 pip 返回 TLS EOF，未修改系统。

因此验证等级为“构建”：仓库 catkin 骨架与脚本契约已验证，但完整 apt/Python 安装
仍需在配置好网络和 `python3-venv` 后复验。

## 真机证据

未执行。本阶段不配置 CAN/串口、不启动节点、不使能机械臂，也不发送任何控制指令。

## 风险与限制

- Python 文件固定直接依赖版本；pip 的间接依赖解析仍依赖当时可用的兼容 wheel，安装
  后以 `pip check` 和导入测试作为强制门禁。
- `pika_locator` 仍缺少可验证源码和许可证证据，不进入安装流程。
- Piper ROS 内嵌副本的许可证溯源仍未闭环；本阶段没有复制该源码。
- 本机尚未完成 apt、rosdep 和 Python 环境安装，不能把 S04 视为真机部署完成。

## 回滚方式

本阶段不自动卸载系统包。代码回滚只需回退本阶段提交。`.venv`、build、devel 和
install 均为 Git 忽略的本地产物；若需清理，必须由操作者先确认路径归属后人工处理。
apt keyring/source 的撤销也必须人工审阅，脚本不会自动删除系统文件。

## 来源与许可证

- ROS apt key：`ros/rosdistro@eb71c289f4495a0327cd03a29205a2c411cd8129`，
  key SHA-256 `490a879375bd4f3dfbe1483efbf8db8985e2ad66b7a19baee0087b333c67caf0`，
  指纹 `C1CF6E31E6BADE8868B172B4F42ED6FBAB17C654`。
- `piper_sdk`：`agilexrobotics/piper_sdk@081e7c588e5b79eeaefa67a0469bcc701c81014f`，MIT；
  仅从 S03 外部 VCS checkout 安装。
- NumPy、CasADi、Pin、Meshcat 与 python-can：从 PyPI 安装固定的直接版本；本阶段只写
  安装元数据，不复制其源码或许可证正文。
- 其余上游来源与许可证状态沿用 [`docs/upstream-dependencies.md`](../upstream-dependencies.md)。
