# S10 通用安全过滤与状态桥

S10 提供一个由 `side:=left|right` 选择的通用节点。它只在全部安全门禁成立时，把
`/joint_states_gripper_raw_l|r` 整形为 `/joint_states_gripper_l|r`；当前没有与 S09 驱动
原始命令入口连接，因此不构成真机运动链路。

## 门禁与状态

过滤器状态为 `DISCONNECTED`、`DISABLED`、`ENABLED_HOLD`、`TELEOP_ACTIVE` 或
`FAULT_LATCHED`，发布到 `/{side}_arm/safety_filter_status`。进入 `TELEOP_ACTIVE` 必须依次
取得新鲜且有限的七轴真实反馈、有效定位、IK 未越界、`control_authorized=true` 和新的
`TeleopStatus(fail=false, quit=false)`。授权与会话顺序不可交换，旧目标不能恢复。
授权是由协调器周期续期的租约；超过 `authorization_timeout_s` 未收到心跳会锁存故障，
避免协调器退出后继续接受命令。

下列情况拒绝输出并锁存故障：

- 反馈、定位或命令超时；
- 定位在授权期间失效或 IK 越界；
- 关节/夹爪位置含 NaN/Inf、长度不足或名称不完整/重复；
- ROS 时间倒退或时间值异常；
- 授权时反馈、定位或 IK 前置条件不成立。

清除故障前必须先发布 `control_authorized=false`，恢复新鲜反馈、有效定位和正常 IK 状态，
再调用 `/{side}_arm/reset_filter_fault`。清除后仍需重新授权和开启新会话。

## 过滤行为

六个关节与夹爪分别使用共享 YAML 中的死区、指数低通和单消息最大步长。输出始终从真实
反馈基线开始；速度百分比固定写入参考 Piper 适配约定的 `JointState.velocity[6]`。该百分比
与最大步长尚未做左右真机限位和频率联合验收，不能视为安全认证值。

自动返回没有迁移；`double_gripper_return=true` 会使节点启动失败。节点不调用 enable、
stop、回零、reset 或夹爪服务，也不发布 `joint_ctrl_raw`、`pos_cmd_raw` 等驱动内部入口。

## 只读展开与离线验证

以下命令只展开节点名称，不启动节点：

```bash
source /opt/ros/noetic/setup.bash
export ROS_PACKAGE_PATH="$PWD/src${ROS_PACKAGE_PATH:+:$ROS_PACKAGE_PATH}"
roslaunch --nodes src/pi05_control/launch/s10_arm_safety_filter.launch \
  side:=left start_filter:=true
roslaunch --nodes src/pi05_control/launch/s10_arm_safety_filter.launch \
  side:=right start_filter:=true
```

离线回放不需要 ROS master、Piper 驱动或真机：

```bash
tests/test_safety_filter.sh
```

实际启动还需要从 `third_party/pi05-upstream.repos` 的固定提交构建 `data_msgs` overlay。
不得使用来源不明的历史 `install.zip` 补齐消息包。
