# Ubuntu 20.04 + ROS Noetic 环境安装

本文是 S04 的可重复安装入口，目标平台固定为 Ubuntu 20.04、x86_64、ROS Noetic
和系统 CPython 3.8。所有安装脚本默认只显示计划；只有显式 `--apply` 才会产生修改。

## 安全模型

- `bootstrap_ubuntu.sh` 和首次 `rosdep init` 需要 sudo，但会先列出写入目标并确认。
- 交互执行时输入完整的 `APPLY`；自动化执行必须显式传入 `--apply --yes`。
- 不执行 `apt upgrade`、包删除、CAN/串口配置、机械臂使能或运动命令。
- Python 包只进入仓库的 `.venv`，不写系统 Python；构建脚本显式使用该解释器。
- 当前交互 shell 可能由 Conda 把 `python3` 指向 3.13；Noetic 流程始终使用
  `/usr/bin/python3` 3.8，不依赖当前 `PATH` 中的 Python。

## 从零安装顺序

以下命令均在仓库根目录执行。先审阅 dry-run：

```bash
scripts/bootstrap_ubuntu.sh
scripts/setup_rosdep.sh
scripts/install_python_deps.sh
```

确认计划后安装 apt/ROS 基线：

```bash
scripts/bootstrap_ubuntu.sh --apply
```

脚本使用固定 commit 的 ROS 签名密钥，校验 SHA-256 与指纹后才写入 keyring；apt
包名由 [`config/apt-packages-noetic.txt`](../config/apt-packages-noetic.txt) 提供。
已有同版本配置和包会被跳过或由 apt 保持不变，因此可重复执行。

按 S03 清单在仓库外获取依赖：

```bash
mkdir -p ../pi05-upstream-src
vcs validate < third_party/pi05-upstream.repos
vcs import ../pi05-upstream-src < third_party/pi05-upstream.repos
```

不要递归初始化 `pika_ros` 子模块。`pika_locator` 仍因源码与许可证证据不足而不在清单
中，S04 不会下载或复制它。

创建 Python 3.8 环境：

```bash
scripts/install_python_deps.sh --apply
```

直接依赖固定在
[`config/python-requirements-noetic.txt`](../config/python-requirements-noetic.txt)。
`piper_sdk` 只允许从 `../pi05-upstream-src/piper_sdk` 安装；脚本会校验其完整 commit
为 `081e7c588e5b79eeaefa67a0469bcc701c81014f` 且工作树干净。每次安装后执行
`pip check` 以及 NumPy、CasADi、Pinocchio、Meshcat、python-can 和 piper_sdk 导入检查。

初始化 rosdep 并安装当前工作区声明的依赖：

```bash
scripts/setup_rosdep.sh --apply
```

脚本只在 `/etc/ros/rosdep/sources.list.d/20-default.list` 缺失时执行一次
`sudo rosdep init`，随后运行 Noetic 索引更新。真正安装前先打印 `rosdep --simulate`
结果。上游 package.xml 存在漏报，rosdep 不能替代 Python 固定清单和 S03 依赖矩阵。

## 构建与检查

```bash
scripts/build_catkin.sh
scripts/check_environment.sh
```

`build_catkin.sh` 先执行只读 `rosdep check`，再用 `.venv/bin/python` 增量运行
`catkin_make`；不会清理已有 build/devel/install。需要 install space 时使用：

```bash
scripts/build_catkin.sh --install
```

`check_environment.sh` 完全只读；任何必需项缺失都返回 1。它不会连接 CAN、枚举设备
序列号或启动 ROS master。硬件联通与运动验收不属于 S04。

## 当前主机的已知缺口

2026-09-10 的只读检查确认系统 `/usr/bin/python3` 为 3.8.10，但当前 shell 中
`python3` 为 Conda 3.13.13；首次临时 venv 验证还确认 `python3-venv` 未安装。联网
解析 Python wheel 时发生 TLS EOF，因此本阶段不宣称完整 Python 联网安装通过。
执行上述 apt 安装后，应重新运行 Python 安装和环境检查，并保留非敏感的成功/失败摘要。

## 常见恢复方式

- apt 或网络失败：修复软件源/网络后原命令重跑，不需要删除工作区。
- `.venv` 版本错误：不要让脚本覆盖它；先人工确认其归属，再换一个 `--venv PATH`。
- rosdep 报缺包：修复 package.xml 或补充受审查的安装清单，不能用忽略错误冒充通过。
- `piper_sdk` SHA 或工作区状态不符：重新按 S03 VCS 清单获取，不从参考工作区复制。
