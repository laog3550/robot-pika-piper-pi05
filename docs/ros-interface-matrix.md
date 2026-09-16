# PI05 双臂 ROS 接口矩阵

左右两侧使用同一套接口模板，`s` 为 `l` 或 `r`，`side` 为 `left` 或 `right`。
厂商驱动的全局接口在 launch 中进入 `/left_arm` 或 `/right_arm` 命名空间，因此两侧
不会使用同一个命令入口。

## 输入

| 接口 | 类型 | 用途 |
|---|---|---|
| `/pi05/pika_input/{side}/pose` | `geometry_msgs/PoseStamped` | Pika 位姿，input-only 转发后的遥操作输入 |
| `/pi05/pika_input/{side}/localization_status` | `data_msgs/LocalizationStatus` | Pika 定位状态 |
| `/pi05/pika_input/{side}/gripper` | `std_msgs/Float64` | Pika 夹爪编码器换算后的 Piper 目标行程（m），仅 `--with-gripper` 时发布 |
| `/pi05/pika_input/raw/{side}/pose`、`.../localization_status` | 同上 | 定位节点原始输出，仅用于诊断；遥操作使用上面的转发话题 |
| `/pika_pose_{s}` | `geometry_msgs/PoseStamped` | 厂商组件订阅的 Pika 位姿，由 launch remap 到 `/pi05/pika_input/{side}/pose` |
| `/joint_states_single_{s}` | `sensor_msgs/JointState` | Piper 反馈供厂商 FK、IK 与平滑器使用 |

## 本侧关节命令

| 接口 | 类型 | 用途 |
|---|---|---|
| `/{side}_arm/joint_ctrl_raw` | `sensor_msgs/JointState` | 发给本侧驱动的关节目标。直连模式下由厂商 IK 发布，平滑模式下由平滑器发布，同一时刻只有一个发布者 |
| `/{side}_arm/teleop/ik_target_raw` | `sensor_msgs/JointState` | 仅平滑模式存在：IK 的原始输出。不要把它接到驱动上 |
| `/{side}_arm/pos_cmd_raw` | `piper_msgs/PosCmd` | 驱动保留的笛卡尔命令入口，绕开 IK；不由本项目遥操作链路使用 |
| `/{side}_arm/enable_flag_raw` | `std_msgs/Bool` | 驱动保留的使能标志话题入口；优先使用 `enable_srv_raw` 服务 |

`joint_ctrl_raw` 的语义沿用厂商约定：`position[0:6]` 为 J1–J6（rad）；
`position[6]` 存在时是夹爪行程（m），驱动按 `position[6] × 1e6` 下发；
`velocity` 为空或全零时驱动使用 50% 速度，否则 `velocity[6]` 是速度百分比；
`effort[6]` 存在时被限制在 `0.5–3` 之间作为夹爪力矩。

## 反馈与状态

| 接口 | 类型 | 用途 |
|---|---|---|
| `/{side}_arm/joint_states_driver_raw` | `sensor_msgs/JointState` | 本侧 Piper 驱动原始反馈（`publish_business_feedback:=false` 时） |
| `/joint_states_single_{s}` | `sensor_msgs/JointState` | 业务反馈别名；遥操作入口用 `publish_business_feedback:=true` 让驱动直接发到这里。驱动只发布这一路关节反馈 |
| `/{side}_arm/joint_states_raw` | `sensor_msgs/JointState` | 只读反馈节点从 SocketCAN 直接解码的七元反馈，供不接驱动的联调使用；由 `s08_readonly_feedback.launch` 启动 |
| `/{side}_arm/arm_status` | `piper_msgs/PiperStatusMsg` | 驱动和机械臂状态 |
| `/{side}_arm/end_pose_raw`、`.../end_pose_euler_raw` | `geometry_msgs/PoseStamped`、`piper_msgs/PiperEulerPose` | 驱动上报的末端位姿 |

关节反馈的元数据约定与命令相反：驱动反馈固定为 7 元，`position[6]` 是夹爪实际开度，
`velocity[6]` 和 `effort[6]` 分别是夹爪速度与电流。

## 厂商组件内部话题

这些话题由厂商 `piper_FK.py`、`piper_IK.py`、`teleop_piper_publish.py` 创建。节点本身
在 `/{side}_arm/teleop` 命名空间下，但下表是 launch 未改写的全局话题名，靠 `_l`／`_r`
后缀区分左右。

| 接口 | 类型 | 用途 |
|---|---|---|
| `/piper_IK_{s}/ctrl_end_pose` | `geometry_msgs/PoseStamped` | 遥操作到 IK 的末端目标 |
| `/piper_FK_{s}/urdf_end_pose_orient` | `geometry_msgs/PoseStamped` | FK 输出供遥操作节点使用 |
| `/piper_IK_{s}/urdf_end_pose_orient`、`/piper_FK_{s}/urdf_end_pose` | `geometry_msgs/PoseStamped` | 诊断用末端位姿 |
| `/joint_states_{s}` | `sensor_msgs/JointState` | 厂商 IK 的关节输出，被 launch remap 到 `/{side}_arm/joint_ctrl_raw` 或 `/{side}_arm/teleop/ik_target_raw`；遥操作节点也向它发布回零目标 |
| `/teleop_status{s}` | `data_msgs/TeleopStatus` | 遥操作状态与失败标志 |
| `/arm_control_status{s}` | `data_msgs/ArmControlStatus` | IK 控制状态 |

## 服务

| 分侧服务 | 用途 |
|---|---|
| `/{side}_arm/enable_srv_raw` | 使能或失能对应机械臂 |
| `/{side}_arm/stop_srv_raw` | 对应机械臂软件停止 |
| `/{side}_arm/gripper_srv_raw` | 夹爪配置 |
| `/{side}_arm/reset_srv_raw` | 复位驱动 |
| `/{side}_arm/go_zero_srv_raw` | 厂商回零接口，六关节全零且固定 50% 速度 |
| `/{side}_arm/block_arm_raw` | 驱动阻塞接口 |
| `/{side}_arm/teleop/joint_command_smoother/set_enabled` | `std_srvs/SetBool`：平滑器输出开关。置 false 立即停止发布整组目标并丢弃缓存目标；置 true 后要等新的 IK 目标才恢复发布 |

触发服务 `/teleop_trigger_l`、`/teleop_trigger_r` 由厂商遥操作节点提供，用于开始或
停止对应侧遥操作。注意厂商 Trigger 回调的响应字段恒为默认 `success=false`，不能用
它判断触发结果，应以节点日志的 `start`／`close` 为准。

## 命名与 remap 约定

- 启动脚本用绝对话题做 remap，因此相对 remap 名会落到全局而不是
  `/{side}_arm/teleop/` 下。例如平滑器的 `gripper_target` 实际是
  `/pi05/pika_input/{side}/gripper`。
- 厂商组件虽然用 `rospy.init_node(..., anonymous=True)` 初始化，但 roslaunch 会传
  `__name:=fk|ik|teleop`，rospy 见到 `__name` 就采用它并关闭 anonymous，所以
  `side_teleop.launch` 里的 `name` 生效，节点名是 `/{side}_arm/teleop/{name}`。
- 平滑器要求 IK 目标在 `0.25 s` 内刷新才继续发布；启用夹爪模式时还要求夹爪输入同样
  新鲜，否则整组目标（含六个关节）一起停发。

CAN 映射固定为 `left_piper` 和 `right_piper`；真实设备路径不写入仓库。启动顺序见
[直接遥操作](direct-teleop.md)，手动命令见 [机械臂命令速查](arm-commands.md)。
旧 S10/S11 过滤器和协调器接口只存在于历史文档，当前代码不创建这些节点、话题或服务。
