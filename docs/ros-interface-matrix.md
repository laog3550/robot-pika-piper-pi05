# PI05 双臂 ROS 接口矩阵

状态：**S08 双侧 Pika 定位与原始 Piper ROS 反馈已完成真机验证；目标控制接口尚未实现，不构成运动许可。**

## 命名约定

- `s` 表示短侧标：左侧 `l`、右侧 `r`；`side` 表示 `left`、`right`。
- 同一通用节点以 `side` 参数实例化两次，业务话题使用 `_l/_r`，驱动原始接口进入
  `/left_arm`、`/right_arm` 命名空间。
- `JointState.position[0:6]` 是 6 个关节 rad，索引 6 是夹爪开度 m。
- `JointState.velocity[6]` 被参考驱动用作 0–100 速度百分比，是需隔离的非标准适配约定。
- 任何不含侧别的 driver 运动话题或服务均视为命名冲突/安全旁路，禁止公开。

## 分侧接口模板

下表每行必须分别实例化为 `l/left` 和 `r/right`，不能只实现右侧。

| 接口模板 | 类型 | 用途 | 风险 |
|---|---|---|---|
| `/pika_pose_{s}` | `geometry_msgs/PoseStamped` | 对应 Pika 位姿 | 安全关键输入 |
| `/pika_localization_status_{s}` | `data_msgs/LocalizationStatus` | 对应侧定位有效性 | 安全关键输入 |
| `/imu_{s}/data`、`/gripper_{s}/data` | `sensor_msgs/Imu`、`data_msgs/Gripper` | 手部只读状态 | 只读 |
| `/gripper_{s}/ctrl` | `data_msgs/Gripper` | Pika 夹爪动作入口 | 运动入口，必须受控 |
| `/joint_states_single_{s}` | `sensor_msgs/JointState` | Piper 真实反馈 | 安全关键反馈 |
| `/piper_IK_{s}/ctrl_end_pose` | `geometry_msgs/PoseStamped` | IK 目标 | 运动中间量 |
| `/joint_states_gripper_raw_{s}` | `sensor_msgs/JointState` | 未整形目标 | 禁止接驱动 |
| `/joint_states_gripper_{s}` | `sensor_msgs/JointState` | 过滤后目标 | 直接运动命令 |
| `/teleop_status_{s}` | `data_msgs/TeleopStatus` | 分侧会话状态 | 安全关键状态 |
| `/arm_control_status_{s}` | `data_msgs/ArmControlStatus` | IK/限位状态 | 安全提示 |
| `/{side}_arm/joint_states_raw` | `sensor_msgs/JointState` | S08 协议原始反馈：6 关节 rad + 夹爪行程 m | 已真机验证；禁止作控制目标 |
| `/{side}_arm/joint_states` | `sensor_msgs/JointState` | URDF 兼容反馈 | 只读 |
| `/{side}_arm/arm_status` | `piper_msgs/PiperStatusMsg` | 驱动/通信/错误状态 | 安全关键反馈 |

## 服务边界

| 接口 | 所有者 | 约定 |
|---|---|---|
| `/dual_arm/enable_srv` | 双臂安全协调器 | 唯一公开使能入口；仅在双侧前置条件通过时转发 |
| `/dual_arm/stop_srv` | 双臂安全协调器 | 同时请求两侧已验证的软件停止；不等同硬件急停 |
| `/dual_arm/status` | 双臂安全协调器 | 汇总双侧状态、故障锁存与会话状态 |
| `/teleop_trigger_{s}` | 分侧遥操作节点 | 切换语义，协调器不得据响应猜测实际状态 |
| `/{side}_arm/enable_srv_raw` | 对应 Piper driver | 内部入口；禁止作为运维 API |
| `/{side}_arm/stop_srv_raw` | 对应 Piper driver | 内部入口；行为需分侧真机验证 |
| `/{side}_arm/gripper_srv_raw` | 对应 Piper driver | 可直接动作，必须隔离 |
| `/{side}_arm/reset_srv_raw`、`go_zero_srv_raw` | 对应 Piper driver | 默认不公开、不自动启动 |

驱动原有 `/enable_flag`、`/pos_cmd`、`/gripper_srv`、`/go_zero_srv` 等全局入口必须在
bringup 中 remap 到对应侧的 `*_raw` 内部名称，或禁用。ROS graph 审计发现全局运动入口、
跨侧订阅或同一目标话题多个发布者时，保持双臂禁用。

## 参数基线

左右两侧从同一 `arm_filter.yaml` 载入独立参数实例：`auto_enable=false`、
`speed_percent=15.0`、`command_timeout_s=0.35`、`double_gripper_return=false`。数值仅是首次
低速测试上限，不是两侧已经验收的安全值；每侧需单独记录发布频率、限位和夹爪标定。

## 只读核对

S08 独立只读入口只创建 `/{side}_arm/joint_states_raw`，不创建命令订阅者或服务：

```bash
source /opt/ros/noetic/setup.bash
source devel/setup.bash
roslaunch pi05_control s08_readonly_feedback.launch
rostopic hz /left_arm/joint_states_raw
rostopic hz /right_arm/joint_states_raw
```

该 `raw` 接口已验证协议顺序和单位，但尚未完成 URDF 关节名、安装方向和零点适配。
以下接口属于后续完整链路核对，不应在 S08 强行启动现有上游驱动：

在两臂禁用且不存在命令发布者时执行：

```bash
rosnode list
rostopic list -v
rosservice list
for s in l r; do
  rostopic type /joint_states_single_${s}
  rostopic echo -n 1 /joint_states_single_${s}
  rostopic hz /joint_states_single_${s}
  rostopic hz /pika_pose_${s}
  rostopic hz /pika_localization_status_${s}
done
```

还必须分别确认 `/left_arm` 与 `/right_arm` 的 `can_port`、`auto_enable=false`，以及所有
命令话题只有预期的分侧过滤器发布。
