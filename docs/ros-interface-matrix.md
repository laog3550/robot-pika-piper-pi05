# PI05 双臂 ROS 接口矩阵

左右两侧使用相同接口模板，`s` 为 `l` 或 `r`，`side` 为 `left` 或 `right`。

| 接口 | 类型 | 用途 |
|---|---|---|
| `/pika_pose_{s}` | `geometry_msgs/PoseStamped` | Pika 位姿输入 |
| `/pika_localization_status_{s}` | `data_msgs/LocalizationStatus` | Pika 定位状态 |
| `/gripper_{s}/data` | `data_msgs/Gripper` | Pika 夹爪输入 |
| `/joint_states_single_{s}` | `sensor_msgs/JointState` | Piper 反馈供厂商 FK 使用 |
| `/piper_IK_{s}/ctrl_end_pose` | `geometry_msgs/PoseStamped` | 遥操作到 IK 的末端目标 |
| `/{side}_arm/joint_ctrl_raw` | `sensor_msgs/JointState` | IK 直接发送给本侧驱动的关节目标 |
| `/{side}_arm/joint_states_driver_raw` | `sensor_msgs/JointState` | 本侧 Piper 驱动原始反馈 |
| `/{side}_arm/joint_states` | `sensor_msgs/JointState` | URDF 兼容反馈 |
| `/{side}_arm/arm_status` | `piper_msgs/PiperStatusMsg` | 驱动和机械臂状态 |

厂商 Piper 驱动的全局接口在 launch 中进入 `/left_arm` 或 `/right_arm` 命名空间，因此两侧不会使用同一个命令入口。`JointState.position[0:6]` 为六个关节角，索引 6 为夹爪开度；厂商驱动在未收到 `velocity[6]` 时沿用其默认速度值。

| 分侧服务 | 用途 |
|---|---|
| `/{side}_arm/enable_srv_raw` | 使能或失能对应机械臂 |
| `/{side}_arm/stop_srv_raw` | 对应机械臂软件停止 |
| `/{side}_arm/gripper_srv_raw` | 夹爪配置 |
| `/{side}_arm/reset_srv_raw` | 复位驱动 |
| `/{side}_arm/go_zero_srv_raw` | 厂商回零接口 |

CAN 映射固定为 `left_piper` 和 `right_piper`；真实设备路径不写入仓库。完整启动方式见 [direct-teleop.md](direct-teleop.md)。旧 S10/S11 过滤器和协调器接口只存在于历史文档，当前代码不创建这些节点、话题或服务。
