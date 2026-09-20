# 部署文档

当前迁移与启动以 [直接遥操作](direct-teleop.md) 为准。架构和接口见
[双臂架构](architecture.md) 与 [ROS 接口矩阵](ros-interface-matrix.md)，
手动命令见 [机械臂命令速查](arm-commands.md)，阶段状态见 [部署进度](status.md)
和 [后续路线](roadmap.md)。

## 当前有效文档

- 运行与操作：[直接遥操作](direct-teleop.md)、[机械臂命令速查](arm-commands.md)、
  [双臂架构](architecture.md)、[ROS 接口矩阵](ros-interface-matrix.md)、
  [双臂连续数据采集](data-collection.md)
- 环境与设备：[环境安装与检查](environment-setup.md)、[设备配置](device-configuration.md)、
  [软件环境清单](software-environment.md)、[硬件清单](hardware-inventory.md)、
  [相机角色映射](camera-mapping.md)
- 依赖与安全：[上游依赖基线](upstream-dependencies.md)、[安全约束](safety-constraints.md)
- 进度：[部署进度](status.md)、[项目进度](project-progress.md)、[后续路线](roadmap.md)

## 2026-09-16 现场记录

- [上机前检查](teleop-preflight-2026-09-16.md)
- [左臂已使能观察](left-enabled-observation-2026-09-16.md)
- [左 J1 微动异常](left-j1-micro-motion-2026-09-16.md)
- [反馈解码只读核查](feedback-decoding-review-2026-09-16.md)
- [右侧直接遥操作联调](right-teleop-retest-2026-09-16.md)

## 历史记录

以下内容只用于追溯，不代表当前代码：

- 阶段成果与验收：[阶段记录](stages/)（S01–S12）、
  [S07 双侧硬件现场验收](s07-field-acceptance.md)、
  [S08 双侧只读通信](s08-readonly-communication.md)、
  [S09 通用单臂驱动封装](s09-single-arm-driver-wrapper.md)
- 已删除的旧方案：[S10 旧过滤方案记录](s10-safety-filter-status-bridge.md)、
  [S11 旧协调方案记录](s11-dual-arm-safety.md)。两者的节点、launch 和测试已在直连重构
  提交 `d9b46ef` 中删除，文中提到的命令和文件不再存在。
- S12 调试与失败记录：`s12-*.md`。[Piper 兼容性](s12-piper-compatibility.md)、
  [低速验收流程](s12-low-speed-acceptance.md)、[Pika input-only 转发](s12-pika-input-only.md)、
  [旧左臂遥操作配置](s12-left-teleop-configuration.md)、
  [接线回放](s12-teleop-wiring-replay-2026-09-15.md) 等文档记录了当时的工具与判据；
  其中引用的 `single_arm_low_speed_acceptance.py`、`safety_gate.py`、`supervisor.py`、
  `pi05_teleop_replay` 等文件均已删除，文档内的操作命令不可再执行。

后续工作以打通双臂遥操作、采集数据和部署 PI0.5 为顺序。快捷复原动作另行设计。
