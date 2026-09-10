# S04 Ubuntu 20.04 + ROS Noetic 环境流程

## 目标

为 x86_64 Ubuntu 20.04 + ROS Noetic 建立可重复执行、失败可见、默认无副作用的 apt、
rosdep、Python 依赖和 catkin 构建流程。所有入口必须提供帮助，错误返回非零；sudo
动作不得静默发生。

## 完成内容

- 增加声明式 apt 清单与 Python 3.8 直接依赖固定清单。
- 增加 apt/ROS 引导脚本，固定 ROS key commit、SHA-256 和指纹。
- 增加 rosdep 初始化、更新、模拟和安装脚本。
- 增加 Python 3.8 venv 安装脚本，并校验 S03 `piper_sdk` SHA；venv 通过
  `--system-site-packages` 与 ROS Noetic 的 Python 包兼容。
- 修复 Pinocchio/CasADi：不再使用缺少 `pinocchio.casadi` 的 PyPI `pin` wheel，也不
  混编 ABI 不兼容的 C++ 库；改用签名 robotpkg 源中的 Python 3.8 Pinocchio 3.2.0 与
  CasADi 3.6.7 固定包，并显式锁定 qpoases、hpp-fcl、eigenpy 传递依赖的兼容版本。
- 增加 catkin 增量构建脚本与统一只读环境检查。
- 增加脚本契约测试，验证帮助、错误码、dry-run 和“默认不调用 sudo”。
- 增加操作者文档并更新 README 快速开始与目录索引。

## 接口与兼容性

支持 Ubuntu 20.04 x86_64、ROS Noetic 和 `/usr/bin/python3` 3.8。脚本的稳定公共入口为：

- `scripts/bootstrap_ubuntu.sh [--apply] [--yes] [--skip-ros-repo] [--skip-robotpkg-repo]`
- `scripts/setup_rosdep.sh [--workspace PATH] [--apply] [--yes] [--skip-init]`
- `scripts/install_python_deps.sh [--venv PATH] [--source-root PATH] [--index-url URL] [--apply] [--yes]`
- `scripts/build_catkin.sh [--workspace PATH] [--venv PATH] [--jobs N] [--install]`
- `scripts/check_environment.sh [--workspace PATH] [--venv PATH]`

默认安装命令均为 dry-run。`--yes` 不能脱离 `--apply` 使用。环境检查不访问网络和
硬件，不记录主机名、IP、USB/设备序列号或环境变量。

## 验证记录

验证日期：2026-09-10。

- `bash tests/test_environment_scripts.sh`：通过；五个入口的帮助、非法参数失败、三类
  安装 dry-run 和默认不调用 sudo 均通过。
- `bash -n scripts/*.sh scripts/lib/common.sh tests/test_environment_scripts.sh`：通过。
- 临时 catkin 工作区构建命令：通过；使用全新 venv 的 Python 3.8.10，确认
  `CMAKE_PREFIX_PATH=/opt/openrobots;/opt/ros/noetic`，产物只写入 `/tmp`。
- `/usr/bin/python3 --version`：3.8.10，符合 Noetic 基线。
- 全新 `/usr/bin/python3 -m venv --system-site-packages`：通过。
- `apt-get --simulate install --no-install-recommends <完整清单>`：通过；新增 18 个、升级
  0 个、卸载 0 个，固定的 8 个 robotpkg 包均可求解。
- `scripts/install_python_deps.sh --venv /tmp/<fresh>/venv ... --apply --yes`：通过；在全新
  Python 3.8.10 venv 中安装成功，再次执行也通过。
- 清除继承的 `PYTHONPATH`/`LD_LIBRARY_PATH` 后直接使用新 venv 导入 `rospy`、CasADi、
  Pinocchio 和 `pinocchio.casadi`：通过，并成功构造 `cpin.Model(pinocchio.Model())`。
- `scripts/check_environment.sh --workspace <repo> --venv /tmp/<fresh>/venv`：通过，摘要为
  `all required environment checks passed`。

因此修复达到“构建”验证等级。没有执行 CAN、串口、ROS 节点启动或机械臂运动验收。

## 真机证据

未执行。本阶段不配置 CAN/串口、不启动节点、不使能机械臂，也不发送任何控制指令。

## 风险与限制

- Python 索引依赖已固定完整传递闭包；安装后仍以 `pip check` 和功能导入测试作为
  强制门禁。robotpkg 安装需要其签名仓库可达。
- `pika_locator` 仍缺少可验证源码和许可证证据，不进入安装流程。
- Piper ROS 内嵌副本的许可证溯源仍未闭环；本阶段没有复制该源码。
- S04 环境通过不代表真机部署完成；硬件与运动验收仍未执行。

## 回滚方式

本阶段不自动卸载系统包。代码回滚只需回退本阶段提交。`.venv`、build、devel 和
install 均为 Git 忽略的本地产物；若需清理，必须由操作者先确认路径归属后人工处理。
apt keyring/source 的撤销也必须人工审阅，脚本不会自动删除系统文件。

## 来源与许可证

- ROS apt key：`ros/rosdistro@eb71c289f4495a0327cd03a29205a2c411cd8129`，
  key SHA-256 `490a879375bd4f3dfbe1483efbf8db8985e2ad66b7a19baee0087b333c67caf0`，
  指纹 `C1CF6E31E6BADE8868B172B4F42ED6FBAB17C654`。
- robotpkg apt key：SHA-256
  `0582476e2e90b3666686e6c50d4d58714e8fddb90786db9f42942baf71e67e68`，主指纹
  `F6F93D4D425860C0B0FBE848ADD535E05E56C3FD`；HTTP 获取的 key 在写入前同时校验两者，
  apt 索引必须通过该 key 的签名验证。
- `piper_sdk`：`agilexrobotics/piper_sdk@081e7c588e5b79eeaefa67a0469bcc701c81014f`，MIT；
  仅从 S03 外部 VCS checkout 安装。
- NumPy、Meshcat 与 python-can：从 Python 包索引安装固定直接版本和完整传递闭包。
- Pinocchio 3.2.0：robotpkg `robotpkg-py38-pinocchio`（BSD-2-Clause）。
- CasADi 3.6.7：robotpkg `robotpkg-py38-casadi`（LGPL-3.0）。两者仅作为系统依赖安装，
  不复制源码进项目。
- 其余上游来源与许可证状态沿用 [`docs/upstream-dependencies.md`](../upstream-dependencies.md)。
