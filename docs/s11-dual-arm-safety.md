# S11 双臂协调安全

S11 把左右 S09 驱动封装和 S10 安全过滤器纳入一个闭集 bringup，并增加双臂协调器。
本阶段只完成仿真、ROS 图审计和服务回放；没有启动真机驱动或访问 CAN。

## 运行模式

`s11_dual_arm_bringup.launch` 只接受以下三种模式，不能单独选择一侧：

| `mode` | 启动内容 | 硬件动作 |
|---|---|---|
| `off` | 无节点（默认） | 无 |
| `simulation` | 左右过滤器、双臂协调器 | 禁止调用原始服务，不启动驱动 |
| `hardware` | 左右驱动、左右过滤器、双臂协调器 | 允许访问 CAN 和调用原始服务 |

`hardware` 会启动固定上游 Piper 驱动。该驱动即使 `auto_enable=false`，初始化时仍会连接
CAN 并发送模式帧。本阶段未批准运行 `mode:=hardware`；必须进入 S12，清空工作区、确认急停
可达并按先左后右的低速验收流程执行。

## 授权和故障联锁

协调器只有在左右两侧同时满足以下条件时才接受 `/dual_arm/enable_srv`：

- 过滤器和驱动状态均新鲜、无 ERROR；
- 真实反馈和定位新鲜，IK 明确未越限；
- 两侧过滤器均处于 `DISABLED`，且没有残留授权。

两路原始 enable 都成功后，协调器才以 20 Hz 向左右过滤器发布授权心跳。过滤器把授权视为
租约；超过 `authorization_timeout_s` 没有收到心跳会锁存故障并停止输出。任一侧报告关键
故障、状态超时、授权未确认或左右遥操作状态长期不一致时，响应顺序固定为：

1. 同步撤销左右授权；
2. 请求左右 software stop；
3. 请求左右 disable。

若只成功使能一侧，也执行 stop 和 disable 回滚。故障锁存后，只有两侧保持未授权、状态
重新新鲜且无故障时，`/dual_arm/reset_fault` 才会清除锁存；清除不会自动重新使能。

## 控制所有权

统一 launch 将每侧过滤输出只连接到对应侧 `/{side}_arm/joint_ctrl_raw`，并把对应驱动反馈
连接回本侧过滤器。公开控制服务只有 `/dual_arm/enable_srv` 和 `/dual_arm/stop_srv`；驱动的
`*_raw` 接口属于内部边界。

ROS 1 没有访问控制。`scripts/check_control_graph.py` 通过运行时 ROS 图检查唯一发布者、
订阅者、服务所有者、跨侧映射和已知旁路，但无法阻止拥有同一 ROS master 访问权的恶意
节点。现场必须使用受控启动清单和隔离的 ROS 网络。

## 无硬件验证

先构建并 source 当前工作区，再启动 simulation：

```bash
source /opt/ros/noetic/setup.bash
source devel/setup.bash
roslaunch pi05_control s11_dual_arm_bringup.launch mode:=simulation
```

另一个终端执行只读图审计：

```bash
source /opt/ros/noetic/setup.bash
source devel/setup.bash
scripts/check_control_graph.py --mode simulation
```

离线单元和 launch 测试不需要真机：

```bash
tests/test_safety_filter.sh
tests/test_dual_arm_safety.sh
tests/test_control_graph_checker.sh
```

`simulation` 没有驱动，因而不会提供真实反馈，也不用于验证运动。软件 stop/disable 的
真机效果、制动距离、下坠风险和急停效果仍须在 S12 分侧验证；软件 stop 不等同硬件急停。

## 上游依赖

运行硬件模式需要固定外置的
`agilexrobotics/piper_ros@ac41fcbcdda598f01b51cf6175ed9a24d0dacadc`，以及固定
`data_msgs`。本仓库没有复制上游控制源码。`piper_msgs` 和 `data_msgs` 都从
`third_party/pi05-upstream.repos` 所声明的源码工作区构建，因此基础 rosdep 流程只跳过这
两个精确的 VCS 源码键，不跳过其他系统依赖。
