# PI05 双臂控制架构

> 这是目标架构，不代表当前真机已经满足放行条件。S05 只验证了右侧设备映射。

## 目标拓扑

```text
Pika Left  ─► left teleop  ─► left safety filter  ─► /left_arm driver  ─► left_piper
       │                              │                        │
       └──── localization/status ─────┤                        └─ left CAN
                                      ├─► dual-arm safety coordinator
       ┌──── localization/status ─────┤       │
Pika Right ─► right teleop ─► right safety filter ─► /right_arm driver ─► right_piper
                                                               └─ right CAN
```

左右链路使用相同代码和参数结构，以 `side:=left|right`、命名空间和 remap 实例化；禁止
维护两份逐渐分叉的控制实现。每侧拥有独立的设备身份、反馈、命令过滤器、看门狗和驱动。

## 安全所有权

- 分侧过滤器只允许向本侧驱动内部命令入口发布。
- S10 分侧过滤器当前发布业务层 `/joint_states_gripper_l|r`，尚未与 S09 的
  `/{side}_arm/joint_ctrl_raw` 接通；该连接只能由 S11 协调器在无旁路审计后建立。
- 双臂协调器是公开 enable/stop 的唯一入口，并汇总双侧通信、定位、反馈和故障状态。
- 双手协同会话中，任一侧关键状态失效都撤销整个会话；默认对双侧执行经验证的
  hold/stop/disable 策略，不允许另一侧继续执行缓存轨迹。
- 硬件急停独立于 PI05、ROS 和上述协调器，必须覆盖两台机械臂。
- 原始 driver 服务和话题只存在于 `/left_arm/*_raw`、`/right_arm/*_raw` 内部边界。
- 分侧状态桥把反馈新鲜度、定位、IK、遥操作会话与协调器授权汇总为
  `/{side}_arm/safety_filter_status`；故障锁存后必须撤销授权并满足恢复前置条件。

## 启停顺序

```text
双侧设备检查 → 两路 CAN 激活 → ROS Master
→ 左右驱动（auto_enable=false）→ 双侧反馈检查
→ 左右 Pika → 分侧过滤器 → 双臂协调器 → 遥操作 → 人工使能
```

停机时先终止双手会话和命令源，再停止/禁用两臂，最后退出驱动并关闭两路 CAN。单侧
调试必须显式选择侧别，另一侧保持禁用；它是验收步骤，不是最终运行模式。
