# robot-pika-piper-pi05

面向 **PI05 + Pika 遥操作器 + Piper 机械臂** 的 ROS 1 真机部署工程。

> 当前状态：项目骨架已建立，尚未完成 PI05 真机联调与验收。机械臂上电前，请先完成 CAN 通信、急停、限位、低速空载和指令超时保护检查。

## 项目目标

本仓库用于把现有 `pika_ros / PikaAnyArm / piper_ros` 工作区中的相关能力整理成一个可复现、可检查、可逐步验收的 PI05 真机部署项目，重点覆盖：

- Ubuntu 20.04、ROS Noetic 与 catkin 工作区安装
- Pika 右手遥操作器与 Piper 单臂接入
- USB-CAN 配置与 1 Mbps CAN 通信
- 机械臂驱动、状态反馈、TF/RViz 可视化
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
| 右臂传感器启动 | `open_right_pika_sensor.launch` |
| 右臂遥操作编排 | `teleop_right_piper.launch` |
| 安全指令整形 | `right_arm_command_filter.py` |
| 关节名可视化桥接 | `right_arm_joint_state_bridge.py` |

当前参考环境为 x86_64、Ubuntu 20.04、ROS Noetic；Python 节点使用 Python 3。正式部署前仍需根据 PI05 工控机、CAN 适配器 USB 地址、Pika 串口和机械臂安装方向校准参数。

## 目录结构

```text
robot-pika-piper-pi05/
├── README.md
├── .gitignore
├── config/
│   └── pi05.env.example             # 机器相关变量模板，不保存真实设备配置
├── docs/
│   ├── README.md                    # 文档索引与阶段划分
│   └── architecture.md              # 节点、话题、服务和安全边界
├── scripts/
│   └── README.md                    # 安装、检查、启动和停机脚本约定
├── src/
│   ├── pi05_bringup/
│   │   ├── CMakeLists.txt
│   │   ├── package.xml
│   │   ├── config/
│   │   │   └── right_arm_filter.yaml
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

## 计划中的控制链路

```text
Pika 定位器 + 串口夹爪
          │
          ▼
  原始 JointState 指令
          │
          ▼
pi05_control 安全过滤
  ├─ 必须已使能且进入新的遥操作会话
  ├─ 关节/夹爪死区与低通滤波
  ├─ 单周期最大步长与全局速度限制
  ├─ 定位丢失和指令超时停止
  └─ 重新使能时以真实反馈清除旧目标
          │
          ▼
   Piper ROS 控制节点
          │
          ▼
      USB-CAN / Piper
```

计划沿用的主要接口如下，最终以 launch 文件和验收记录为准：

- 原始遥操作指令：`/joint_states_gripper_raw_r`
- 安全过滤后指令：`/joint_states_gripper_r`
- Piper 反馈：`/joint_states_single_r`
- 可视化关节状态：`/right_arm/joint_states`
- 对外使能服务：`/enable_srv`
- 驱动内部使能服务：`/right_arm/enable_srv_raw`
- 遥操作触发服务：`/teleop_trigger_r`
- 定位状态：`/pika_localization_status_r`

## 从 0 到 1 的实施阶段

1. **冻结硬件清单**：记录 PI05 主机、Piper 型号/固件、CAN 适配器、Pika 串口、急停与供电。
2. **安装基础环境**：安装 ROS Noetic、catkin、can-utils、ethtool 和 Python 依赖。
3. **固定上游版本**：引入并锁定 Pika、Piper SDK/ROS 驱动及消息包版本。
4. **设备持久化**：为 CAN 与串口建立稳定命名，填写本机私有配置。
5. **只读联通测试**：不上使能，只检查 CAN 帧、ROS 节点、状态话题和关节反馈。
6. **安全功能测试**：验证急停、禁用、超时、定位丢失、旧指令清除和限速。
7. **低速单关节测试**：机械臂腾空、现场有人值守，从最小速度和小步长开始。
8. **遥操作联调**：确认坐标系、方向、夹爪范围、回零逻辑和工作空间。
9. **验收与固化**：保存版本、参数、日志、测试结果，并配置受控的开机启动。

## 快速开始（骨架阶段）

```bash
git clone https://github.com/laog3550/robot-pika-piper-pi05.git
cd robot-pika-piper-pi05

cp config/pi05.env.example config/pi05.env
# 按实际硬件修改 config/pi05.env；该文件不会提交到 Git。

rosdep install --from-paths src --ignore-src -r -y
catkin_make
source devel/setup.bash
```

当前 launch 和控制脚本仍是待迁移入口，**不要在此阶段直接用于机械臂上电运动**。

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

优先完成以下任务：

- [x] 建立 S02 硬件、软件、ROS 接口和安全约束文档基线
- [ ] 按 S02 现场采集命令确认 PI05 架构、Ubuntu/ROS、实物与安全链路
- [ ] 确认右单臂的 Piper CAN 接口稳定名称
- [x] 形成 S03 上游依赖与许可证基线（`pika_locator` 与 Piper ROS 溯源仍为阻塞项）
- [ ] 迁移右臂 launch、指令过滤器和关节状态桥接
- [ ] 增加环境检查、CAN 检查、启动与安全停机脚本
- [ ] 建立仿真/回放测试与真机验收表
- [ ] 在 PI05 上完成低速真机验证并记录结果

## 许可证

暂未确定。引入上游代码前，需要分别核对其许可证和再分发要求；在许可证明确前，请勿对外发布复制的第三方源码。
