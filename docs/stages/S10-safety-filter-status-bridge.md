# S10 通用安全过滤与状态桥

## 目标

把历史右臂过滤行为重构为项目原创、左右复用的安全状态机和 ROS 状态桥，并以无硬件的
单元测试及双侧确定性回放验证门禁、过滤、超时和故障恢复。

## 完成内容

- 新增 ROS 无关的 `ArmSafetyFilter`，左右两侧使用完全相同的实现和配置结构。
- 新增分侧 ROS 节点，汇总真实反馈、定位、遥操作状态、IK 状态及协调器授权。
- 实现 NaN/Inf、长度/名称、时间倒退、反馈/定位/命令超时拒绝和故障锁存。
- 每次禁用、会话退出及故障均使旧目标失效；新会话从新鲜真实反馈重新初始化。
- 保留死区、低通、关节/夹爪单消息步长和 Piper 速度百分比适配。
- 自动返回保持关闭；节点不调用任何 Piper 服务，不连接 S09 原始驱动命令入口。

## 接口与兼容性

输入和输出见 `docs/ros-interface-matrix.md`。`side` 只接受 `left` 或 `right`，launch 默认
`start_filter=false`。新增的 `control_authorized` 是为 S11 协调器预留的内部门禁；ROS 1
本身不保证唯一发布者，完整图审计仍是 S11 的退出条件。

运行时依赖固定的 `data_msgs@868860123c40a0f7dc96984bb313fdc79afbaa8d`。该包保持外置，
没有复制到本仓库。基础工作区可在跳过未解析 rosdep 键后构建；实际节点须叠加该固定包。

## 验证记录

验证日期：2026-09-12。

- `tests/test_safety_filter.sh`：12 项通过；覆盖左右一致回放、会话门禁、死区/低通/步长、
  异常输入、超时、时间倒退、锁存恢复、闭集 side 和默认不启动。
- `/usr/bin/python3 -m py_compile ...`：通过。
- `scripts/build_catkin.sh` 与 `--install`：通过；rosdep 继续检查系统键，仅跳过固定 VCS
  源码键 `data_msgs`，基础仓库构建及安装成功。
- `catkin_make run_tests_pi05_control && catkin_test_results --verbose`：19 项、0 错误、0 失败。
- 全部 10 个 `tests/test_*.sh` 仓库级入口：通过。
- 临时 catkin 工作区加入固定且干净的外置 `data_msgs`：构建成功，生成 5 个消息和 1 个服务。
- 临时 ROS master 消息回放：通过；有效门禁产生 30 条受限输出，注入定位失效后输出计数
  不再增加，最终状态锁存为 `localization invalid`。

## 真机证据

未执行。没有启动 Piper 驱动、调用控制服务、发布到驱动原始命令入口或发送 CAN 帧。
本阶段涉及控制输出，故状态为“等待真机验收”，验证等级为“仿真/回放”。

## 风险与限制

- `speed_percent=15` 和单消息步长尚未结合真实发布频率、关节方向和软硬限位验收。
- 过滤后的业务话题尚未接入 S09 驱动；S11 必须保证唯一所有者且消除 ROS graph 旁路。
- 锁存只阻止本节点继续发布，并不等同软件 stop、disable 或硬件急停。
- `data_msgs` 不是系统 rosdep 包，部署工作区必须按固定 VCS 清单显式构建它。
- 自动返回、回零和手势动作均未实现，也未批准。

## 回滚方式

撤销本阶段提交即可。launch 默认不启动过滤器，本阶段没有修改主机、CAN 或机械臂状态。

## 来源与许可证

- 行为对照：只读参考
  `/home/mips/pika_ros/src/PikaAnyArm/piper/pika_remote_piper/scripts/right_arm_command_filter.py`；
  历史内嵌来源许可证不完整，未复制其源码。
- 消息定义：`agilexrobotics/data_msgs@868860123c40a0f7dc96984bb313fdc79afbaa8d`，
  根 BSD-3-Clause；仅作为外置固定依赖，没有复制源码或许可证正文。
- 本阶段过滤器、ROS 桥和测试为本项目独立实现。
