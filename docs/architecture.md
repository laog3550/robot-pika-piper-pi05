# PI05 控制架构

## 组件边界

| 组件 | 职责 | 预期来源 |
|---|---|---|
| Pika 传感与定位 | 发布手柄位姿、夹爪和定位状态 | Pika SDK / pika_ros |
| 遥操作解算 | 将位姿转换为 Piper 关节目标 | PikaAnyArm |
| pi05_control | 过滤、限速、看门狗和状态桥接 | 本仓库 |
| Piper ROS 驱动 | ROS 与 Piper SDK/CAN 之间的适配 | piper_ros |
| pi05_bringup | 参数装载、命名空间、重映射与启动顺序 | 本仓库 |

## 数据流

```text
Pika pose + gripper
        │
        ▼
teleoperation IK
        │ /joint_states_gripper_raw_r
        ▼
command safety filter
        │ /joint_states_gripper_r
        ▼
Piper ROS driver ─── USB-CAN ─── Piper
        │
        ├─ /joint_states_single_r ──► feedback/safety state
        └─ /right_arm/joint_states ─► robot_state_publisher/RViz
```

## 安全状态边界

运动命令只有在以下条件同时成立时才可透传：

1. Piper 驱动已成功使能；
2. 当前遥操作会话在使能后重新建立；
3. 已收到有效的机械臂真实关节反馈；
4. Pika 定位状态有效；
5. 指令流未超过超时阈值；
6. 指令经死区、低通、最大步长和速度限制处理。

禁用、重新使能、退出遥操作、定位丢失或指令超时都必须清除旧目标。重新开始时，以真实反馈作为安全初值。

## 启动顺序

```text
设备检查 → CAN 激活 → ROS Master → Piper 驱动（默认不自动使能）
→ 状态反馈检查 → Pika 设备 → 安全过滤 → 遥操作 → 人工使能
```

停机顺序与运动风险相关：先停止遥操作和命令源，再禁用机械臂，最后退出驱动和关闭 CAN 接口。
