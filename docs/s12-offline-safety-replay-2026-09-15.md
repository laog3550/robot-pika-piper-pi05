# S12 遥操接入前安全链路回放

日期：2026-09-15。验证等级：仿真/回放。结果：现有安全组件检查及分侧过滤器实际 ROS 回放通过；完整遥操/IK/协调器端到端联调未完成。

## 验证

- `bash tests/test_safety_filter.sh`：13 项通过，覆盖过滤计算、会话与授权门禁、异常输入、超时及故障锁存等现有契约。
- `bash tests/test_dual_arm_safety.sh`：14 项通过，覆盖协调器前置条件、双侧会话、故障传播与 launch 模式等契约。
- `bash tests/test_control_graph_checker.sh`：5 项通过，覆盖控制图所有权检查契约。
- 独立 localhost:11332 ROS Master 上实际运行双侧 S10 过滤节点，`connect_driver=false`；`ROS_MASTER_URI=http://localhost:11332 /usr/bin/python3 tests/replay_arm_safety_filter.py` 返回 PASS、退出码 0。新增脚本包含显式隔离 Master 检查。
- `git diff --check` 通过。独立回放节点和 11332 Master 已关闭；真机 Pika input-only 观察会话保留。

ROS 回放验证无驱动节点及 raw 驱动连接、未授权拦截、无会话拦截、左右不同合成目标不串线、会话退出后停止输出、左定位失效后停止输出并锁存故障、恢复定位不会自动重启。回放使用合成反馈及合成授权发布器，没有协调器参与，不能用右侧继续输出的单侧故障测试推断双手协同策略。协调器双侧故障传播仅由上述离线测试覆盖。

## 重现实际 ROS 回放

先加载 ROS Noetic、参考 Pika install、锁定上游 devel 和项目 devel 环境。在单独终端执行 `roscore -p 11332`，再执行：

```bash
ROS_MASTER_URI=http://localhost:11332 \
  /usr/bin/python3 tests/replay_arm_safety_filter.py
```

只允许隔离 Master，不连接 CAN、不启动 Piper 驱动，不使用真实设备位姿。结束后关闭独立 core。

## 遥操接入缺口

当前输入观察包输出 `/pi05/pika_input/{left,right}/pose` 和 `.../localization_status`，现有过滤器订阅 `/pika_localization_status_{l,r}`，必须显式适配。

上游 `teleop_piper_publish.py` 按 index_name 订阅 `/pika_pose{suffix}`，IK 和遥操回零逻辑均可能发布 `/joint_states{suffix}`，需要一起审查并映射到 `/joint_states_gripper_raw_{l,r}`。不能把该输出直接接入驱动。上游参考 launch 包含真实 Piper 驱动，不是本次回放入口。

后续需独立完成左右参数化、输入 remap、原始目标及 IK/会话状态接入，并在无驱动条件下联合验证。此次没有修改生产控制节点或参数，不宣称已完成 pose→IK→过滤器→协调器的端到端链路。

Piper 非目标响应仍未闭环，不启动真机遥操、不发布 PR，不覆盖既有阶段状态表或报告。
