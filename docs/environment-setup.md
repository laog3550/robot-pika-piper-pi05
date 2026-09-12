# Ubuntu 20.04 + ROS Noetic 环境安装

本文是 S04 的可重复安装入口，目标平台固定为 Ubuntu 20.04、x86_64、ROS Noetic
和系统 CPython 3.8。所有安装脚本默认只显示计划；只有显式 `--apply` 才会产生修改。

## 安全模型

- `bootstrap_ubuntu.sh` 和首次 `rosdep init` 需要 sudo，但会先列出写入目标并确认。
- 交互执行时输入完整的 `APPLY`；自动化执行必须显式传入 `--apply --yes`。
- 不执行 `apt upgrade`、包删除、CAN/串口配置、机械臂使能或运动命令。
- 纯 Python 包只进入 `.venv`；ABI 耦合的 Pinocchio/CasADi 由已审查的 apt 流程安装到
  `/opt/openrobots`。venv 使用 `--system-site-packages`，构建脚本显式使用该解释器。
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

脚本使用固定 commit 的 ROS 签名密钥，并对 robotpkg 签名密钥校验固定 SHA-256 和主
指纹后才写入 keyring；随后写入 focal robotpkg 源和 `/opt/openrobots/lib` 动态链接器
路径。robotpkg 仓库通过已验证密钥校验签名索引，即使源站仅提供 HTTP，也不信任未签名
内容。apt 包名及 Pinocchio/CasADi 版本由
[`config/apt-packages-noetic.txt`](../config/apt-packages-noetic.txt) 提供。
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
scripts/install_python_deps.sh \
  --index-url https://mirrors.ustc.edu.cn/pypi/web/simple \
  --apply
```

`--index-url` 是网络受限时的显式、无凭据镜像选项；能正常访问 PyPI 时可以省略。
脚本不读取或打印带凭据的索引 URL。直接 Python 依赖固定在
[`config/python-requirements-noetic.txt`](../config/python-requirements-noetic.txt)。
`piper_sdk` 只允许从 `../pi05-upstream-src/piper_sdk` 安装；脚本会校验其完整 commit
为 `081e7c588e5b79eeaefa67a0469bcc701c81014f` 且工作树干净。

PikaAnyArm 实际使用 `from pinocchio import casadi`，而 PyPI 的 `pin` wheel 不包含该
Python 绑定；将 PyPI CasADi 与 ROS C++ 库混编还会产生 `_GLIBCXX_USE_CXX11_ABI`
冲突。因此 ABI 耦合的依赖闭包由 robotpkg 固定安装：qpoases 3.2.1r1、CasADi
3.6.7、hpp-fcl 2.4.5、eigenpy 3.10.0 与 Pinocchio 3.2.0（含对应 Python 3.8
包）。venv 通过明确的
`.pth` 文件使用 ROS 与 `/opt/openrobots` Python 包；检查和构建脚本同时固定动态库、
CMake 与 pkg-config 搜索路径。其余纯 Python 依赖仍安装进
venv。每次安装后执行 `pip check`，并检查 ROS Python、NumPy、CasADi、Pinocchio、
`pinocchio.casadi`、Meshcat、python-can 和 `piper_sdk`，同时实际构造一个 CasADi
Pinocchio 模型，避免只通过浅层 import。

初始化 rosdep 并安装当前工作区声明的依赖：

```bash
scripts/setup_rosdep.sh --apply
```

脚本只在 `/etc/ros/rosdep/sources.list.d/20-default.list` 缺失时执行一次
`sudo rosdep init`，随后运行 Noetic 索引更新。真正安装前先打印 `rosdep --simulate`
结果。上游 package.xml 存在漏报，rosdep 不能替代 Python 固定清单和 S03 依赖矩阵。
项目的 `data_msgs` 和 `piper_msgs` 是 VCS 清单固定仓库中的源码依赖，不是 rosdep/apt
键；脚本只对这两个键使用 `--skip-keys`，避免 rosdep 把源码依赖误报为未知系统包。这不
会安装或豁免它们，运行依赖这些消息的节点前仍必须从固定 commit 构建对应 overlay。

## 构建与检查

```bash
scripts/build_catkin.sh
scripts/check_environment.sh
```

`build_catkin.sh` 先执行只读 `rosdep check`（仅跳过上述固定 VCS 键），再用
`.venv/bin/python` 增量运行
`catkin_make`；不会清理已有 build/devel/install。需要 install space 时使用：

```bash
scripts/build_catkin.sh --install
```

安装模式会对使用项目 venv 的 catkin 显式设置 `SETUPTOOLS_DEB_LAYOUT=OFF`，避免把仅由
Ubuntu 系统 Python 支持的 `--install-layout=deb` 参数传给 venv distutils。普通构建不
改变此选项。

`check_environment.sh` 完全只读；任何必需项缺失都返回 1。它不会连接 CAN、枚举设备
序列号或启动 ROS master。硬件联通与运动验收不属于 S04。

## 当前主机说明

2026-09-10 确认系统 `/usr/bin/python3` 为 3.8.10；当前交互 shell 的 Conda
`python3` 为 3.13 不影响脚本。官方 PyPI 链路在本机曾出现 TLS EOF，以上命令给出已
验证可访问的 USTC 镜像作为显式回退。环境验收使用新建 Python 3.8 venv，不能把已有
Conda 环境或旧 `.venv` 的成功结果当作证据；2026-09-10 已按此要求通过完整环境检查。

## 常见恢复方式

- apt 或网络失败：修复软件源/网络后原命令重跑，不需要删除工作区。
- `.venv` 版本错误或不是 `--system-site-packages`：不要让脚本覆盖它；先人工确认其
  归属，再换一个 `--venv PATH`。脚本会明确失败，不会删除已有目录。
- Pinocchio/CasADi 缺失或版本不符：先重跑 `bootstrap_ubuntu.sh --apply`；不要用
  PyPI `pin` wheel 或本机源码混编绕过 robotpkg 版本门禁。
- rosdep 报缺包：修复 package.xml 或补充受审查的安装清单，不能用忽略错误冒充通过。
- `piper_sdk` SHA 或工作区状态不符：重新按 S03 VCS 清单获取，不从参考工作区复制。
