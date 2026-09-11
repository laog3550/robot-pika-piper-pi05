# robot-pika-piper-pi05

面向 **PI05 + 双 Pika 遥操作器 + 双 Piper 机械臂** 的 ROS 1 真机部署工程。

> 当前状态：项目骨架已建立，尚未完成 PI05 真机联调与验收。机械臂上电前，请先完成 CAN 通信、急停、限位、低速空载和指令超时保护检查。

## 项目目标

本仓库用于把现有 `pika_ros / PikaAnyArm / piper_ros` 工作区中的相关能力整理成一个可复现、可检查、可逐步验收的 PI05 真机部署项目，重点覆盖：

- Ubuntu 20.04、ROS Noetic 与 catkin 工作区安装
- 左右 Pika 遥操作器与左右 Piper 双臂接入
- 两路 USB-CAN 配置、唯一侧别绑定与 1 Mbps CAN 通信
- 双臂驱动隔离、状态反馈、TF/RViz 可视化
- 指令死区、低通滤波、单周期步长限制和速度限制
- 定位丢失、指令超时、停机与重新使能时的安全处理
- 分阶段真机测试、验收记录与故障排查

## 已知基线

本项目骨架依据当前工作区中的以下实现整理：

| 能力 | 当前参考实现 |
|---|---|
| Piper CAN 驱动 | `piper_ros/piper` |
| Piper 消息与服务 | `piper_ros/piper_msgs` |
| Pika 到 Piper 遥操作 | `pika_remote_piper` |
| 右侧参考传感器启动 | `open_right_pika_sensor.launch`（仅作迁移参考） |
| 右侧参考遥操作编排 | `teleop_right_piper.launch`（需参数化为双侧） |
| 参考安全指令整形 | `right_arm_command_filter.py`（需改为通用节点） |
| 参考关节名桥接 | `right_arm_joint_state_bridge.py`（需改为通用节点） |

当前参考环境为 x86_64、Ubuntu 20.04、ROS Noetic；Python 节点使用 Python 3。正式部署前仍需根据 PI05 工控机、CAN 适配器 USB 地址、Pika 串口和机械臂安装方向校准参数。

## 目录结构

```text
robot-pika-piper-pi05/
├── .agents/skills/pi05-stage-sync/ # 阶段验收、文档与 PR 自动化技能
├── README.md
├── .gitignore
├── config/
│   └── pi05.env.example             # 机器相关变量模板，不保存真实设备配置
├── docs/
│   ├── README.md                    # 文档索引与阶段划分
│   ├── architecture.md              # 双臂节点、话题、服务和安全边界
│   ├── roadmap.md                   # S06 之后的双臂阶段目标
│   ├── status.md                    # 阶段状态与验证等级
│   └── stages/                      # 每阶段的证据、风险与回滚记录
├── scripts/
│   ├── bootstrap_ubuntu.sh          # apt 与 ROS Noetic 基线（默认 dry-run）
│   ├── setup_rosdep.sh              # rosdep 初始化、预览与安装
│   ├── install_python_deps.sh       # Python 3.8 虚拟环境
│   ├── build_catkin.sh              # 增量 catkin 构建
│   ├── check_environment.sh         # 只读环境检查
│   ├── check_upstream_manifest.sh   # 固定 commit 与许可证远端校验
│   ├── check_s07_hardware.sh        # S07 本地硬件记录校验
│   ├── discover_devices.sh          # 脱敏、只读的 CAN/串口发现
│   ├── configure_can.sh             # CAN check/apply 与 bus-info 绑定
│   └── configure_pika_serial.sh     # Pika 串口 check/apply 与稳定别名
├── src/
│   ├── pi05_bringup/
│   │   ├── CMakeLists.txt
│   │   ├── package.xml
│   │   ├── config/
│   │   │   └── arm_filter.yaml      # 左右实例共享的保守默认参数
│   │   └── launch/
│   │       └── README.md
│   └── pi05_control/
│       ├── CMakeLists.txt
│       ├── package.xml
│       ├── scripts/
│       │   └── README.md
│       └── test/
│           └── README.md
├── tests/
│   └── README.md                    # 真机前检查与验收测试
└── third_party/
    └── README.md                    # 上游依赖及版本固定策略
```

Git 不跟踪空目录，因此各预留目录使用说明文件保留。后续实现进入目录后，再删除对应占位说明。

## 阶段协作

在本仓库中使用 Codex 实现、迁移、修复或验收阶段任务时，仓库级
`$pi05-stage-sync` 技能会在任务完成后整理阶段报告、执行发布门禁，并创建
`stage/SNN-<slug>` 分支和面向 `main` 的 PR。它不会自动合并 PR，也不会把计划、
解释、失败测试或缺少真机证据的机械臂变更标记为已经验收。

当前阶段与验证等级见 [`docs/status.md`](docs/status.md)。

## 计划中的双臂控制链路

```text
Pika Left  ─► left filter  ─► /left_arm driver  ─► left_piper
                         ┐
                          ├─► dual-arm safety coordinator
                         ┘
Pika Right ─► right filter ─► /right_arm driver ─► right_piper
```

计划沿用的主要接口如下，最终以 launch 文件和验收记录为准：

- 左右原始遥操作：`/joint_states_gripper_raw_l`、`/joint_states_gripper_raw_r`
- 左右过滤后指令：`/joint_states_gripper_l`、`/joint_states_gripper_r`
- Piper 反馈：`/joint_states_single_l`、`/joint_states_single_r`
- 驱动命名空间：`/left_arm/*_raw`、`/right_arm/*_raw`
- 唯一公开使能/停止：`/dual_arm/enable_srv`、`/dual_arm/stop_srv`
- 遥操作触发与定位状态：`/teleop_trigger_l|r`、`/pika_localization_status_l|r`

## 从 S06 开始的实施阶段

后续工作以双手双臂为唯一交付目标。S07–S16 的目标、退出条件和验证等级见
[`docs/roadmap.md`](docs/roadmap.md)；右侧历史验收只代表右侧，不自动扩展到左侧。

## 快速开始（S04 环境阶段）

```bash
git clone https://github.com/laog3550/robot-pika-piper-pi05.git
cd robot-pika-piper-pi05

# 所有安装入口默认只显示计划，不调用 sudo：
scripts/bootstrap_ubuntu.sh
scripts/setup_rosdep.sh
scripts/install_python_deps.sh

# 审阅输出后逐步执行；交互模式会再次要求输入 APPLY：
scripts/bootstrap_ubuntu.sh --apply
vcs validate < third_party/pi05-upstream.repos
vcs import ../pi05-upstream-src < third_party/pi05-upstream.repos
scripts/install_python_deps.sh --apply
scripts/setup_rosdep.sh --apply
scripts/build_catkin.sh
scripts/check_environment.sh

# 复制私有模板后，只读发现设备；不要按 can0/ttyUSB0 的枚举顺序猜测身份：
cp config/pi05.env.example config/pi05.env
scripts/discover_devices.sh
# 现场沿线确认后填写 config/pi05.env，再先 check、后 apply：
scripts/configure_can.sh check left
scripts/configure_can.sh check right
scripts/configure_pika_serial.sh check left
scripts/configure_pika_serial.sh check right

# S07：按现场清单填写 Git 忽略的硬件记录；校验器不访问设备：
cp config/s07-hardware.env.example config/s07-hardware.env
scripts/check_s07_hardware.sh

# S08：只读检查左右 Pika 数据完整性；不会发送串口数据：
scripts/check_pika_stream.sh left
scripts/check_pika_stream.sh right
scripts/check_piper_can_stream.sh left
scripts/check_piper_can_stream.sh right
# 构建后可启动本项目独立的双侧 Piper ROS 原始反馈；只接收、不使能：
source devel/setup.bash
roslaunch pi05_control s08_readonly_feedback.launch
# 定位发布者已由现场批准并启动后，只读检查双侧位姿和 accurate 状态：
scripts/check_pika_localization.sh --duration 10

# S09：只展开并审查分侧驱动节点名称，不执行驱动：
roslaunch --nodes src/pi05_control/launch/s09_single_arm_driver.launch \
  side:=left start_driver:=true
roslaunch --nodes src/pi05_control/launch/s09_single_arm_driver.launch \
  side:=right start_driver:=true
```

环境步骤见 [`docs/environment-setup.md`](docs/environment-setup.md)，设备身份确认、apply
和回滚见 [`docs/device-configuration.md`](docs/device-configuration.md)。S09 launch 默认
不启动驱动；显式启动仍会发送 CAN 模式帧，控制脚本也尚未迁移，**不要在此阶段直接
用于机械臂上电运动**。

## 真机部署安全原则

- 初次测试必须清空机械臂工作空间，并保证急停按钮可立即触达。
- 第一次连通只读取反馈，不发送运动指令、不自动使能。
- 先验证关节编号、正方向、单位、限位和夹爪量程，再执行组合动作。
- 驱动使能前，命令目标必须同步到机械臂真实反馈，防止执行缓存目标。
- 控制链路必须具有指令超时和定位丢失停机策略。
- 配置、设备序列号、令牌、密码和现场网络信息不得提交到仓库。
- 每次修改限位、速度、坐标变换或回零逻辑后，都应重新执行低速验收。

## 配置管理

`config/pi05.env.example` 只描述变量。真实配置写入 `config/pi05.env`，并由 `.gitignore` 排除。ROS 运行参数放在对应包的 `config/*.yaml`，机器唯一信息不应硬编码在节点中。

## 下一步

- [ ] S07：上游来源已按选择/排除策略闭环；等待左/右硬件、供电、急停与安装现场记录
- [x] S08：双侧 CAN、Pika 串口/定位及 Piper 原始 ROS 反馈已完成只读真机验证；
  URDF 关节名、安装方向与零点适配留待后续驱动阶段
- [ ] S09：通用分侧驱动封装已完成构建验证，等待后续阶段的受控真机验收
- [ ] S10–S11：完成通用安全过滤器和双臂安全协调器
- [ ] S12–S16：依次完成分侧低速、双臂协同、双手遥操作、故障注入与交付固化

## 许可证

暂未确定。引入上游代码前，需要分别核对其许可证和再分发要求；在许可证明确前，请勿对外发布复制的第三方源码。
