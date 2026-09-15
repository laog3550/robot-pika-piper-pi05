# S12 遥操与安全链路离线接线

日期：2026-09-15。状态：等待真机验收。验证等级：构建、仿真/回放。完整合成链路回放通过；没有进行 Piper 真机遥操。

## 完成内容

新增独立包 `pi05_teleop_replay`，复用实际 FK、相对遥操、IK、分侧安全过滤器和双臂协调器。原有控制节点、硬件 launch 及参数文件没有修改。

隔离 Master 固定为 `http://localhost:11333`，默认 `start=false`。九个组件均通过入口检查后运行：拒绝其它 Master、错误命名空间、未包含必要隔离 remap 的调用。协调器使用实际动作代码，但服务目标固定为回放中的模拟使能/停止服务，既不启动 Piper 驱动，也不连接 CAN。

上游 FK/IK/遥操及数值依赖按本机已审查源码 SHA256 检查，使用外部源码，不复制进仓库。上游 IK 强制创建 Meshcat server/browser，本包仅在隔离组件进程中替换可视化对象为空操作；数值模型、IK 求解及碰撞检查保持原样。遥操自动回零配置固定为字符串 `False`。

## 接口

以下为左右对称接口，`side=left|right`：

| 来源或功能 | 回放目标 |
|---|---|
| 隔离 Pika 输入 pose/status | `/pi05/pika_input/{side}/pose`、`.../localization_status` |
| FK/IK/遥操关节反馈 | `/pi05/teleop_replay/{side}_arm/feedback` |
| FK 与 IK 末端姿态 | `/pi05/teleop_replay/{side}_arm/fk/*`、`.../ik/*` |
| IK 与遥操回零发布入口 | `/pi05/teleop_replay/{side}_arm/raw_target` |
| 过滤输出 | `/pi05/teleop_replay/{side}_arm/filtered_target` |
| 会话、IK 状态及授权 | 同一分侧命名空间的 `teleop_status`、`ik_status`、`control_authorized` |
| 协调器接口 | `/pi05/teleop_replay/dual_arm/*` |
| 模拟设备动作 | `/pi05/teleop_replay/mock/{side}/enable`、`.../stop` |

上游遥操把旧 `/joint_states_gripper_{l,r}` 当作反馈，而过滤器将同名话题用作输出。本包按节点分开 remap：遥操订阅真实的合成反馈入口，过滤器发布独立 filtered_target，避免命令被误当作反馈。IK 与遥操的原始发布入口均已审查；回零发布器仍注册，但回零功能关闭。

上游遥操→IK 的 PoseStamped 使用 Euler 角打包于 orientation.xyz，IK 默认 `use_orient=false` 与之配套。不能将该内部消息解释为普通四元数或直接接入其它 IK。工具/末端偏移 0.19 m 沿用上游回放基线，未验证真实 Pika 到机械臂的标定。Pika input-only 不提供夹爪串口输入，真实夹爪映射没有在本轮验收。

## 运行与验证

在项目目录运行：

```bash
bash tests/test_teleop_safety_pipeline.sh
```

脚本加载本机 ROS、参考 install、锁定上游及项目 devel、项目 .venv；检查 11333 空闲，启动独立 Master，发布合成 Pika pose/status、合成关节反馈和驱动状态，提供模拟设备服务，最后关闭回放组件和 Master。现有真机 input-only 观察会话可以继续运行在原 Master，数据不会跨 Master 自动传输。

验证结果：

- `/usr/bin/python3 -m unittest tests/test_teleop_replay_boundary.py`：6 项通过，检查默认关闭、反馈与输出分离、命令/服务隔离、回零关闭、错误 Master 与裸组件调用拒绝。
- `bash tests/test_teleop_safety_pipeline.sh`：PASS，退出码 0。实际双侧 FK→相对遥操→IK→过滤器→协调器链路使用合成数据完成；检查左右输入不串线、原始目标发布者限定、未授权无过滤输出、授权后输出、双侧会话退出与重新开始、左定位失效后撤销双侧授权并调用双侧模拟停止、定位恢复后保持故障锁存。
- `catkin_make`：通过。
- `catkin_make run_tests_pi05_control`：通过；`catkin_test_results build/test_results`：79 tests，0 errors，0 failures，0 skipped。
- `git diff --check`：通过。

启动防护联调时发现 roslaunch 通过 `ROS_NAMESPACE` 环境变量传递命名空间，入口已同时支持该标准形式与 `__ns` remap。最终入口及完整回放重新验证通过。没有降低生产安全门限。

## 范围、回滚与来源

移除本次新增的 `src/pi05_teleop_replay/`、`tests/replay_teleop_safety_pipeline.py`、`tests/test_teleop_replay_boundary.py`、`tests/test_teleop_safety_pipeline.sh` 及本文即可撤销新增接线；无需修改或覆盖原有控制文件。

本阶段 preflight 通过，起始 HEAD `3c17a3219091df63e0845aef00e4feef058a8934`、分支 `stage/S12-split-side-low-speed-acceptance`；保留任务开始前 70 个已改动路径。fetch origin main 成功，没有新建阶段分支。左臂非目标响应未闭环，现有阶段路径还有未提交工作，因此本次不提交、推送或发布 PR，也不覆盖已有阶段状态表。仅完成离线接线验证，真实标定、夹爪输入和硬件行为仍待独立验收。

外部源码来源：`agilexrobotics/PikaAnyArm` 固定审查快照 `d2b8b84c756d8684cfdd3970741d32d89b248257` 下 `piper/pika_remote_piper/scripts/`，根许可证 BSD-3-Clause。实际解析的本机 install 中五个 Python 文件 SHA256 与审查快照一致。初次回放的 `piper_description` 实际来自旧 install，本报告此前将其表述为锁定官方模型是不准确的；后续只读标定检查发现该路径问题，已为回放入口添加官方 URDF 校验，并在测试脚本中优先选择锁定官方模型包。重新验证结果见标定预检记录。没有复制外部源码、二进制、设备标识或真实位姿。
