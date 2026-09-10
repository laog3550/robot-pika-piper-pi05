# S03 上游依赖基线

状态：**可审计源码已固定；`pika_locator` 因来源不完整而阻塞。**

盘点日期：2026-09-09。参考工作区为只读的 `/home/mips/pika_ros`。本阶段只记录来源并创建获取清单，不复制上游源码、二进制或许可证正文，也不迁移控制代码。

## 冻结策略

1. 使用完整 Git commit，而不是可移动分支或仅 package 版本号。
2. `pika_ros` 与 `PikaAnyArm` 从现场参考 SHA 前进到各自的许可证承载提交；两个提交均以参考 SHA 为直接父提交。
3. `PikaAnyArm` 的许可证提交只增加根 `LICENSE`。`pika_ros` 的许可证提交增加根 `LICENSE`，并登记相同许可证提交的 `PikaAnyArm` gitlink；其余参考源码不变。
4. `piper_sdk` 固定到 0.6.1：它发布早于参考 `PikaAnyArm` 提交，并包含当前 Piper ROS 驱动调用的 `C_PiperInterface`、`ConnectPort`、`MotionCtrl_2`、`JointCtrl`、`GripperCtrl`、`EnableArm` 和 `DisableArm` API。由于 Piper 固件版本尚未采集，这只是源码获取基线，不是运动兼容性结论。
5. 没有可验证源码 URL、commit 和许可证正文的组件不进入 VCS 清单，也不得复制进本项目。

## 来源与版本

| 组件 | 实际来源边界 | 固定 commit | 参考区对应点 | 许可证证据 | 结论 |
|---|---|---|---|---|---|
| `pika_ros` | [agilexrobotics/pika_ros](https://github.com/agilexrobotics/pika_ros) | `ed82f402cebe57aa093d59303215929f0119b0fc` | `535eac9ad54001ff82f3a0c1256bca3206b5b51f` | 固定提交根目录的 BSD-3-Clause `LICENSE` | 可获取；再分发前仍需核对各内嵌二进制/第三方内容 |
| `sensor_tools` | `pika_ros/src/sensor_tools`，不是独立仓库 | 随 `pika_ros`：`ed82f402...` | 随参考 `pika_ros` | 根 LICENSE 为 BSD-3-Clause；package.xml 仍写 `TODO` | 有条件使用；元数据不一致需上游确认 |
| `PikaAnyArm` | [agilexrobotics/PikaAnyArm](https://github.com/agilexrobotics/PikaAnyArm) | `d2b8b84c756d8684cfdd3970741d32d89b248257` | `6d8685218c1c39a2a0f7614620919b34481fbdc4` | 固定提交根目录的 BSD-3-Clause `LICENSE` | 可获取；子包元数据需核对 |
| Piper ROS | 参考实现位于 `PikaAnyArm/piper/piper_ros`；另有[官方独立仓库](https://github.com/agilexrobotics/piper_ros) | 实际参考副本随 `PikaAnyArm`：`d2b8b84...` | 随参考 `PikaAnyArm` | 官方仓库为 MIT；内嵌副本未保留独立 LICENSE，且 `piper`/`piper_msgs` package.xml 为 `TODO` | **再分发阻塞**；先厘清内嵌副本来源并恢复应有声明 |
| `data_msgs` | [agilexrobotics/data_msgs](https://github.com/agilexrobotics/data_msgs) | `868860123c40a0f7dc96984bb313fdc79afbaa8d` | `pika_ros` 子模块同一 SHA | 仓库 `LICENSE` 为 BSD-3-Clause；package.xml 为 `TODO` | 可获取；保留许可证文件，修复元数据前不对外发布副本 |
| `piper_sdk` | [agilexrobotics/piper_sdk](https://github.com/agilexrobotics/piper_sdk) | `081e7c588e5b79eeaefa67a0469bcc701c81014f`（tag `0.6.1`） | 参考主机未发现可识别安装 | 固定提交 `LICENSE` 和 setup 元数据均为 MIT | 可获取；固件兼容性待确认 |
| `pika_locator` | 参考 `pika_ros/source/install.zip` 中的预编译 catkin 包 | **未知** | package 版本 `0.0.1`；无源码目录或 Git 元数据 | package.xml 声明 MIT，但归档中未找到对应源码与独立 LICENSE | **阻塞：不进入 VCS 清单，不复制/分发** |

许可证名称只记录仓库证据，不构成法律意见。尤其是 `pika_ros`/`PikaAnyArm` 根 LICENSE 与部分 package.xml 的 `TODO` 不一致，而内嵌 Piper ROS 与官方仓库的声明方式也不同，必须在发布或复制源码前取得上游确认。

### Piper ROS 来源辨析

官方 `piper_ros` 的 Noetic 分支确实存在。参考 `PikaAnyArm` 在 2025-07-25 首次加入内嵌 Piper ROS；官方 Noetic 在此之前最近的提交是 `f1f8f868fe6ed4e59ef13585f66e0b1641a96227`（2025-07-22）。但逐提交比对没有找到与内嵌目录树或核心驱动文件完全相同的官方 commit，因此不能把 `f1f8f868...` 冒充为参考实现的来源 commit。

VCS 清单只通过 `PikaAnyArm@d2b8b84...` 固定实际参考副本，不再额外获取官方 `piper_ros`，以免同一 ROS package 出现两个来源。官方仓库及 `f1f8f868...` 仅作为后续溯源候选；在差异审查完成前不得用它替换参考副本。

## 依赖关系

```text
PikaAnyArm / pika_remote_piper
├── Piper ROS（同一 PikaAnyArm 仓库）
│   ├── piper_msgs（同一目录树）
│   ├── piper_description（同一目录树）
│   └── piper_sdk 0.6.1
│       └── python-can >= 3.3.4
├── pika_ros / sensor_tools
│   ├── data_msgs
│   ├── Boost.System + jsoncpp
│   └── ROS sensor/geometry/std 消息
├── pika_locator 0.0.1 [来源阻塞]
│   ├── data_msgs
│   └── libsurvive [二进制链路，来源仍需固定]
└── Python/ROS 运动学依赖
    ├── NumPy
    ├── Pinocchio + CasADi + Meshcat
    └── rospy, rospkg, tf, sensor_msgs, geometry_msgs, std_srvs
```

当前上游 package.xml 并未完整表达这张依赖图：`pika_remote_piper` 漏报 `data_msgs`、`sensor_msgs` 和 Python 运动学依赖；`sensor_tools` 的 package/CMake 元数据也不完全一致。因此 `rosdep install` 不能作为依赖完整性的唯一证据。Python 与 apt 依赖的精确版本将在环境锁定阶段单独记录。

## 可重复获取

清单位于 [`third_party/pi05-upstream.repos`](../third_party/pi05-upstream.repos)。它把四个可审计仓库作为并列源码快照获取，不会初始化 `pika_ros` 自带的子模块，也不会获取 `pika_locator`。

先安装 `vcstool`，然后导入到项目目录之外的源码缓存：

```bash
sudo apt-get install python3-vcstool
mkdir -p ../pi05-upstream-src
vcs validate < third_party/pi05-upstream.repos
vcs import ../pi05-upstream-src < third_party/pi05-upstream.repos
vcs export --exact ../pi05-upstream-src
```

复核结果：

```bash
for repo in pika_ros PikaAnyArm data_msgs piper_sdk; do
  git -C "../pi05-upstream-src/$repo" rev-parse HEAD
  git -C "../pi05-upstream-src/$repo" status --porcelain=v1
done
```

预期四个 SHA 与清单完全一致，且状态为空。不要执行 `git submodule update --init --recursive`：这会额外拉取本阶段未审核的子模块。源码缓存不得直接作为已批准的真机工作区。

## `pika_locator` 补齐要求

在进入可重复构建前，必须向上游或设备供应方取得：

- 官方源码仓库 URL 和不可变 commit/tag；
- 与交付二进制对应的源码及构建说明；
- 完整 LICENSE/NOTICE，以及 libsurvive 等链接依赖的许可证清单；
- 支持 Ubuntu 20.04、ROS Noetic、x86_64 的构建证据；
- 二进制或源码发布物的校验和与签名来源。

参考归档仅可用于识别，不作为获准依赖来源。其 `source/install.zip` 在本次参考区中的 SHA-256 为 `3bf19782d04d8e9658ba6575a35898fba4b32d8197db949bb2704fc11ecd710d`，对应固定 `pika_ros` 提交中的 Git blob 为 `4c4c1567a1b81ec21a48f624d1fedf72a86bfb55`。这些哈希只能证明文件一致，不能补足源码或许可证权利。

## S03 退出条件

- [x] 可验证仓库均使用完整 commit 固定。
- [x] Piper ROS 与 `sensor_tools` 的真实仓库边界已记录。
- [x] 已创建不含 `pika_locator` 的 VCS 获取清单。
- [x] 已记录直接依赖关系和 package 元数据缺口。
- [ ] `pika_locator` 源码、commit、构建方法与许可证证据齐全。
- [ ] 内嵌 Piper ROS 与官方仓库的来源差异和许可证声明已得到上游确认。
- [ ] Piper 实机固件版本已采集，并与 `piper_sdk` 0.6.1 完成兼容性确认。

在后三项完成前，S03 为“有条件冻结”，不能宣告整套真机依赖已完全可重复构建或可再分发。
