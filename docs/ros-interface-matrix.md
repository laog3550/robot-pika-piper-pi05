# S02 ROS 接口矩阵

状态：**接口按参考实现冻结；未经真机验证，不构成运动许可。**

## 命名与消息约定

- 范围为右臂，后缀统一为 `_r`；Piper 原始驱动接口置于 `/right_arm/*_raw` 时才表示受控内部入口。
- `sensor_msgs/JointState.position[0:6]` 为 6 个臂关节，单位 rad；索引 6 为夹爪开度，参考实现按 m 处理。
- Piper 驱动反馈名为 `joint0` 至 `joint6`；URDF 可视化桥把前 6 个名称映射为 `joint1` 至 `joint6`。
- 参考驱动把 `JointState.velocity[6]` 解释成 0–100 的全局速度百分比。这不是标准 `JointState` 语义，必须保持为显式适配约定。
- 参考 `pika_locator` 只有 install 二进制，定位话题的发布频率、frame_id 与时间戳质量必须现场确认。

## 目标控制链路

```text
/pika_pose_r ─► teleop_piper_r ─► /piper_IK_r/ctrl_end_pose
                                         │
/joint_states_single_r ─► FK/IK ◄────────┘
                              │ /joint_states_r
                              ▼
Pika 串口节点 + 夹爪编码器 ─► /joint_states_gripper_raw_r
                              │
                              ▼
                     right_arm_command_filter
                              │ /joint_states_gripper_r
                              ▼
                    Piper driver ─► CAN/Piper
```

## 话题矩阵

| 接口 | 类型 | 发布者 | 订阅者 | 方向/用途 | 风险级别 |
|---|---|---|---|---|---|
| `/pika_pose_r` | `geometry_msgs/PoseStamped` | `pika_right_locator` | `teleop_piper_r` | Pika 右手定位输入 | 安全关键输入 |
| `/pika_localization_status_r` | `data_msgs/LocalizationStatus` | `pika_right_locator` | Pika 串口节点、命令过滤器 | `accurate` 定位有效性 | 安全关键输入 |
| `/imu_r/data` | `sensor_msgs/Imu` | Pika 串口节点 | 可选监控 | Pika IMU | 只读 |
| `/gripper_r/data` | `data_msgs/Gripper` | Pika 串口节点 | 可选监控 | Pika 夹爪状态 | 只读 |
| `/gripper_r/joint_state` | `sensor_msgs/JointState` | Pika 串口节点 | 可视化/监控 | Pika 夹爪关节 | 只读 |
| `/gripper_r/ctrl` | `data_msgs/Gripper` | 未指定 | Pika 串口节点 | Pika 夹爪控制 | **可产生设备动作** |
| `/joint_states_single_r` | `sensor_msgs/JointState` | Piper driver | FK、IK、过滤器、状态桥 | 6 关节 + 夹爪反馈 | 安全关键反馈 |
| `/piper_FK_r/urdf_end_pose` | `geometry_msgs/PoseStamped` | `piper_FK_r` | 诊断/可视化 | FK 末端位姿 | 只读 |
| `/piper_FK_r/urdf_end_pose_orient` | `geometry_msgs/PoseStamped` | `piper_FK_r` | `teleop_piper_r` | FK 参考位姿 | 安全关键输入 |
| `/piper_IK_r/ctrl_end_pose` | `geometry_msgs/PoseStamped` | `teleop_piper_r` | `piper_IK_r` | 遥操作末端目标 | **运动命令中间量** |
| `/piper_IK_r/urdf_end_pose_orient` | `geometry_msgs/PoseStamped` | `piper_IK_r` | 诊断/可视化 | IK 解算结果 | 只读 |
| `/joint_states_r` | `sensor_msgs/JointState` | `piper_IK_r`、`teleop_piper_r` 的可选回零逻辑 | Pika 串口节点 | 6 关节目标；参考代码存在两个发布者 | **运动命令中间量** |
| `/joint_states_gripper_raw_r` | `sensor_msgs/JointState` | Pika 串口节点 | 命令过滤器 | 6 关节 + 夹爪原始目标 | **未经整形，禁止接驱动** |
| `/joint_states_gripper_r` | `sensor_msgs/JointState` | 命令过滤器 | Piper driver；`teleop_piper_r` 也订阅 | 整形后的 6 关节 + 夹爪目标 | **直接运动命令** |
| `/teleop_status_r` | `data_msgs/TeleopStatus` | `teleop_piper_r` | Pika 串口节点、过滤器 | 遥操作会话状态 | 安全关键状态 |
| `/arm_control_status_r` | `data_msgs/ArmControlStatus` | `piper_IK_r` | Pika 串口节点 | IK 超限提示 | 安全提示；不是硬停 |
| `/right_arm/joint_states` | `sensor_msgs/JointState` | 状态桥 | `robot_state_publisher` | URDF 兼容反馈 | 只读 |
| `/arm_status` | `piper_msgs/PiperStatusMsg` | Piper driver | 未指定 | 模式、错误、限位与通信状态 | 安全关键反馈 |
| `/end_pose` | `geometry_msgs/PoseStamped` | Piper driver | 未指定 | 实测末端位姿 | 只读 |
| `/end_pose_euler` | `piper_msgs/PosCmd` | Piper driver | 未指定 | 实测末端位姿（Euler） | 只读 |
| `/enable_flag` | `std_msgs/Bool` | 未指定 | Piper driver | 绕过安全包装的原始使能 | **禁止对外暴露** |
| `/pos_cmd` | `piper_msgs/PosCmd` | 未指定 | Piper driver | 绕过过滤器的笛卡尔目标 | **禁止对外暴露** |

## 服务矩阵

| 接口 | 类型 | 服务端 | 客户端/用途 | 风险与冻结要求 |
|---|---|---|---|---|
| `/teleop_trigger_r` | `std_srvs/Trigger` | `teleop_piper_r` | Pika 串口节点、过滤器 | 开始/停止是切换语义，不是幂等 set；必须核对当前状态 |
| `/enable_srv` | `piper_msgs/Enable` | 命令过滤器 | 操作员/bringup | 唯一允许公开的 Piper 使能入口 |
| `/right_arm/enable_srv_raw` | `piper_msgs/Enable` | Piper driver | 命令过滤器 | 内部原始入口；必须限制调用方，不能作为运维 API |
| `/gripper_srv` | `piper_msgs/Gripper` | Piper driver | 未指定 | 可直接动作且绕过过滤器；必须命名空间隔离或禁用 |
| `/stop_srv` | `std_srvs/Trigger` | Piper driver | 未指定 | 软件暂停；不能等同硬件急停 |
| `/reset_srv` | `std_srvs/Trigger` | Piper driver | 未指定 | 可恢复运动状态；必须受控 |
| `/go_zero_srv` | `piper_msgs/GoZero` | Piper driver | 未指定 | 直接发零位运动，参考实现固定 50% 速度；真机前必须隔离 |

## 关键参数基线

这些是参考右臂 launch 的当前值，不是已验收的真机安全值。

| 参数 | 参考值 | 状态 |
|---|---:|---|
| `can_port` | `right_piper` | 仅为参考 launch 默认值；目标 env 留空，现场决定 |
| `auto_enable` | `false` | 冻结为必须 false |
| `hold_position_on_enable` | `true` | 本地补丁行为，待测试 |
| `speed_percent` | `15.0` | launch 值；仓库 YAML 当前为 `30.0`，不得混用 |
| `arm_alpha` | `0.35` | 待低速验证 |
| `arm_deadband_rad` | `0.002` | 待低速验证 |
| `max_arm_step_rad` | `0.012` | 待结合实际发布频率换算速度 |
| `gripper_alpha` | `0.25` | 待验证 |
| `gripper_deadband_m` | `0.0015` | 待验证 |
| `max_gripper_step_m` | `0.0006` | 待结合频率验证 |
| `command_timeout_s` | `0.35` | 超时只停止新目标流，不等同禁用/急停 |
| `gesture_open_m` / `gesture_closed_m` | `0.075` / `0.030` | 与驱动中其他夹爪范围描述不一致，禁止启用手势返回 |
| `double_gripper_return` | `true` | S02 冻结为部署前必须改为 false |

## 现场只读核对

在机械臂禁用且不存在命令发布者时执行：

```bash
rosnode list
rostopic list -v
rosservice list
rosparam get /piper_ctrl_right_node/auto_enable
rosparam get /piper_ctrl_right_node/can_port
rostopic type /joint_states_single_r
rostopic echo -n 1 /joint_states_single_r
rostopic echo -n 1 /arm_status
rostopic hz /joint_states_single_r
rostopic hz /pika_pose_r
rostopic hz /pika_localization_status_r
```

命令发布者审计：

```bash
for topic in /enable_flag /pos_cmd /joint_states_gripper_raw_r /joint_states_gripper_r /gripper_r/ctrl; do
  echo "$topic"
  rostopic info "$topic"
done
```

发现未知发布者、多个 `/joint_states_r` 发布者或任何原始入口被外部节点使用时，保持禁用并退出测试。
