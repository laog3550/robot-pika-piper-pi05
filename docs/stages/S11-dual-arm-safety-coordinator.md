# S11 双臂协调安全与故障联锁

## 目标

建立不可分侧启动的双臂 bringup、唯一公开控制入口和跨侧故障联锁，使任一侧关键故障都
撤销双侧控制授权，并以确定顺序请求双侧 stop/disable；以仿真、ROS 图审计和服务回放验收，
不启动真机驱动。

## 完成内容

- 新增 ROS 无关的 `DualArmSafetyCoordinator`，统一检查双侧过滤、反馈、定位、IK、驱动
  状态及超时，并保留首个故障原因。
- 新增双臂协调节点，独占公开 enable/stop/reset 服务并发布双侧授权心跳和汇总状态。
- 为 S10 授权增加租约超时；协调器退出或心跳中断时，过滤器会锁存并停止输出。
- 新增 `off`、`simulation`、`hardware` 三态闭集 launch；不能只启动一侧，也不能组合出
  单驱动或控制旁路。
- 在统一 launch 内将每侧过滤输出和驱动反馈闭集映射到对应侧内部接口；单独启动 S09/S10
  时仍默认断开。
- 新增只读 ROS 图审计，检查节点集合、发布者、订阅者、服务所有者、跨侧映射和已知全局
  旁路接口。
- `data_msgs`、`piper_msgs` 按 VCS 固定源码依赖处理；没有复制上游源码。

## 接口与兼容性

公开服务为 `/dual_arm/enable_srv`、`/dual_arm/stop_srv` 和
`/dual_arm/reset_fault`；汇总状态为 `/dual_arm/status`。内部授权为
`/{left|right}_arm/control_authorized`，原始驱动命令和服务保持在分侧 `*_raw` 边界。
完整映射见 `docs/ros-interface-matrix.md`。

S09/S10 原有默认行为保持安全关闭。S09 新增的 `publish_business_feedback` 和 S10 新增的
`connect_driver` 默认均为 `false`，只有 S11 统一 launch 固定开启映射。

## 验证记录

验证日期：2026-09-12。

- 全部 12 个 `tests/test_*.sh` 仓库级入口：通过；其中 S10 安全过滤 13 项、S11 协调器
  与 bringup 13 项、控制图检查器 5 项通过。
- `catkin_make run_tests_pi05_control && catkin_test_results --verbose`：38 项、0 错误、
  0 失败、0 跳过。
- `scripts/build_catkin.sh` 与 `scripts/build_catkin.sh --install`：通过；rosdep 继续检查
  系统键，仅跳过固定 VCS 源码键 `data_msgs` 和 `piper_msgs`。
- `mode:=off` 展开为零节点；`simulation` 仅包含协调器和双侧过滤器；`hardware` 只做
  launch 展开，确认包含双侧驱动、双侧过滤器和协调器；非法模式拒绝。
- 临时 catkin 工作区加入固定 `data_msgs` 和官方固定 `piper_msgs` 后构建成功。
- 实际启动 `mode:=simulation` 后，运行时 ROS 图审计通过；两侧内部命令话题各只有对应
  过滤器发布，且不存在驱动订阅者。
- 使用临时 mock 原始服务和合成状态回放：双侧 enable 成功后注入右侧驱动故障，观察到
  双侧授权变为 false，精确调用顺序为 left/right stop 后 left/right disable，汇总状态
  锁存 ERROR。

## 真机证据

未执行。没有启动 Piper 驱动、访问 CAN、调用真实控制服务或发布真机命令。本阶段改变
未来真机控制路径，因此状态为“等待真机验收”，验证等级为“仿真/回放”。

## 风险与限制

- 官方 software stop/disable 的制动效果、时序、下坠风险和失败模式尚未真机验证，不能
  替代硬件急停。
- `hardware` 模式会连接两路 CAN；必须留到 S12 的分侧低速现场验收，不能仅凭 S11 回放
  直接运行。
- ROS 1 没有 ACL；图审计能发现误配置和普通旁路，不能防御有 ROS master 权限的恶意节点。
- 共享工作空间碰撞约束尚未完成，双臂协同运动必须等待后续阶段。
- 当前超时、授权心跳和速度参数是回放基线，仍需结合真机发布频率逐侧确认。

## 回滚方式

停止 S11 launch 即撤销协调器心跳，过滤器会在授权租约超时后锁存。撤销本阶段提交可恢复
S10 的断开式过滤链路；本阶段未修改主机、CAN 或机械臂持久状态。

## 来源与许可证

- 官方接口核对：`agilexrobotics/piper_ros@ac41fcbcdda598f01b51cf6175ed9a24d0dacadc`，
  根 MIT；仅作为固定外置构建依赖，没有复制源码。
- 消息定义：`agilexrobotics/data_msgs@868860123c40a0f7dc96984bb313fdc79afbaa8d`，
  根 BSD-3-Clause；仅作为固定外置构建依赖，没有复制源码。
- 本阶段协调状态机、ROS 节点、launch、图审计和测试为本项目独立实现。
