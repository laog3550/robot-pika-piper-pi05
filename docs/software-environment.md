# S02 软件环境清单

状态：**需求基线已冻结；PI05 实机版本待采集。**

## 支持基线

| 层级 | 冻结要求 | 证据与备注 |
|---|---|---|
| CPU 架构 | x86_64 | `pika_ros` 与 `PikaAnyArm` README 声明的支持平台；不是 PI05 实测值 |
| 操作系统 | Ubuntu 20.04 | 上游 README 声明；具体 20.04.x 与内核待现场采集 |
| ROS | ROS 1 Noetic | 上游 README、`/opt/ros/noetic` 构建路径与 catkin 缓存一致 |
| 构建系统 | catkin / `catkin_make` | 参考区存在 catkin build、devel、install 产物 |
| Python | Python 3 (`/usr/bin/python3`) | CMake 缓存与节点 shebang 确认；微版本待采集 |
| CAN | SocketCAN、`gs_usb`、`iproute2`、`can-utils`、`ethtool` | Piper 辅助脚本的显式依赖；适配器兼容性待现场确认 |
| Pika 串口节点 | `sensor_tools/serial_gripper_imu` | C++/Boost.Asio；串口 460800、8N1、无流控 |
| Pika 定位 | `pika_locator/pika_single_locator_node`、libsurvive | 参考 install 空间存在二进制与包描述；源码不在参考区，需补齐可复现来源 |
| Piper 驱动 | `piper`、`piper_msgs`、`piper_sdk` | ROS 包在 `PikaAnyArm`；Python SDK 版本未由仓库固定 |
| 遥操作/运动学 | `pika_remote_piper`、NumPy、Pinocchio、CasADi | 源码 import 确认；版本未固定 |
| ROS 运行依赖 | `rospy`、`roscpp`、`sensor_msgs`、`geometry_msgs`、`std_msgs`、`std_srvs`、`tf`、`robot_state_publisher`、`rviz`、`data_msgs` | package/launch/source 交叉确认 |
| C++ 系统依赖 | Boost.System、jsoncpp | `sensor_tools` CMake 确认 |

相机、RealSense、OpenCV/PCL 数据采集链路虽然存在于参考工作区，但不属于本阶段的最小 PI05 + Pika + Piper 遥操作基线。

## 参考源码快照

盘点日期：2026-09-09。SHA 可公开，但不能单独复现工作区中的本地修改。

| 组件 | 仓库 | 参考提交 | 工作区状态 |
|---|---|---|---|
| 目标部署仓库 | `robot-pika-piper-pi05` | `12821883426155a26b1d8e02b78d8eb7940f9dda`（盘点开始时） | S02 文档由该点继续修改 |
| `pika_ros` | `https://github.com/agilexrobotics/pika_ros.git` | `535eac9ad54001ff82f3a0c1256bca3206b5b51f` | 脏；含已修改脚本、子仓库和生成物 |
| `PikaAnyArm` | `https://github.com/agilexrobotics/PikaAnyArm.git` | `6d8685218c1c39a2a0f7614620919b34481fbdc4` | 脏；右臂安全链路包含未提交文件/修改 |
| `data_msgs` | `https://github.com/agilexrobotics/data_msgs.git` | `868860123c40a0f7dc96984bb313fdc79afbaa8d` | 子模块提交已识别 |
| `data_tools` | `https://github.com/agilexrobotics/data_tools.git` | `58d0ec7b30fa2c1b53981226ffb56e1a5fff73ab` | 子模块工作区有修改；本阶段不使用 |

参考区的右臂专用 launch、安全过滤器、关节状态桥和 Piper `hold_position_on_enable` 改动不属于上表提交内容。后续阶段必须将其作为独立补丁审查、测试并固定，不能把当前目录直接复制为依赖快照。

## 已识别但未冻结的版本

- `pika_locator` install 包描述为 `0.0.1`，但缺少对应源码仓库和提交证据。
- `piper`、`piper_msgs`、`pika_remote_piper` 的 package 版本均为 `0.0.0`，不能作为发布版本标识。
- `piper_description` package 版本为 `1.0.0`；URDF 内的导出工具版本不是 Piper 实机固件版本。
- `piper_sdk`、NumPy、Pinocchio、CasADi、Boost、jsoncpp、内核和 Python 微版本均待 PI05 采集。
- `pika_remote_piper/package.xml` 没有完整声明源码实际使用的 `data_msgs`、`sensor_msgs`、NumPy、Pinocchio/CasADi 等依赖；不能仅凭 `rosdep` 认为环境可复现。
- 上游 package.xml 中仍有 `TODO` 许可证。许可证闭环前不得复制或对外再发布第三方源码。

## PI05 现场采集命令

命令只输出软件版本与包状态，不采集令牌、环境变量、用户名、主机名、IP 或设备序列号。

```bash
uname -m
uname -r
grep -E '^(NAME|VERSION|VERSION_ID|ID)=' /etc/os-release
python3 --version
gcc --version | head -n 1
cmake --version | head -n 1
catkin_make --version 2>/dev/null || catkin --version 2>/dev/null
rosversion -d
rosversion roslaunch
```

```bash
dpkg-query -W -f='${Package}\t${Version}\n' \
  ros-noetic-ros-base ros-noetic-robot-state-publisher ros-noetic-rviz \
  can-utils ethtool iproute2 libboost-system-dev libjsoncpp-dev 2>&1
```

```bash
python3 - <<'PY'
from importlib import import_module, metadata

for dist in ('numpy', 'casadi', 'pin', 'pinocchio', 'piper-sdk', 'piper_sdk'):
    try:
        print(f'{dist}\t{metadata.version(dist)}')
    except metadata.PackageNotFoundError:
        pass

for module in ('numpy', 'casadi', 'pinocchio', 'piper_sdk'):
    try:
        obj = import_module(module)
        print(f'import {module}\tOK\t{getattr(obj, "__version__", "version-not-exported")}')
    except Exception as exc:
        print(f'import {module}\tFAIL\t{type(exc).__name__}')
PY
```

加载预期工作区后采集 ROS 包解析结果；只保存路径是否正确，不需要保存用户名化路径：

```bash
source /opt/ros/noetic/setup.bash
source <pi05-workspace>/install/setup.bash
for pkg in data_msgs sensor_tools pika_locator pika_remote_piper piper piper_msgs piper_description; do
  printf '%s\t' "$pkg"
  rosversion "$pkg" 2>/dev/null || echo MISSING
done
```

采集源码状态：

```bash
git -C <pika_ros> rev-parse HEAD
git -C <pika_ros> status --porcelain=v1
git -C <PikaAnyArm> rev-parse HEAD
git -C <PikaAnyArm> status --porcelain=v1
```

## S02 软件退出条件

- PI05 实测平台符合 x86_64 + Ubuntu 20.04 + ROS Noetic，或形成经批准的偏差单。
- 所有运行/构建依赖有可重复安装的版本来源，不以参考区的 build/install 目录作为唯一来源。
- `pika_locator`、`piper_sdk` 和需参数化为双侧的参考右臂本地补丁有明确来源及版本固定方案。
- 许可证 TODO 已登记为后续发布阻塞项。
