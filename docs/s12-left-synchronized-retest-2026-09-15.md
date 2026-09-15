# S12 左侧同步诊断复测

状态：阻塞。验证等级：真机（诊断失败记录，不是运动验收通过）。
2026-09-15 用户批准一次左 J2 +0.005 rad、5% 同步诊断复测，并重新确认
支撑已实际承载、双人值守及硬件急停可用。开始前关闭 Pika input-only/RViz，
核对隔离 ROS 图；未启动右驱动或遥操作。pi05-stage-sync preflight 与 git status
已运行，初始 HEAD `3c17a3219091df63e0845aef00e4feef058a8934`，保留全部现有改动。

## 执行

先启动左侧 s09 驱动 auto_enable=false，再启动独立被动监听：

```bash
/usr/bin/python3 scripts/diagnose_piper_command_feedback.py \
  --side left --joint 2 --duration 40
```

3 秒被动关节稳定性检查六轴范围均为零后，执行一次：

```bash
rosrun pi05_control single_arm_low_speed_acceptance.py move \
  --side left --joint 2 --delta-rad 0.005 --speed-percent 5 \
  --resume-stop --apply --confirm-single-arm --confirm-mechanical-support
```

## 结果与停止

运动工具返回 1，去程非目标 J5 连续三个样本超过 0.002 rad：
J5 +0.008517 rad，同时 J2 -0.003211 rad。ROS/CAN 基准最大差异
J5 0.000229 rad。未继续返回或重试；software stop 服务调用未报错，
没有在运动工具失败路径自动 disable。一次性批准随后已清空。

监听工具返回 1 / REVIEW_REQUIRED：

- 第一目标前稳定基准确认；观察到 3 个目标帧、1 个完整目标组，
  没有缺帧、乱序、末尾部分组的标记。
- J2 目标最大绝对变化 0.004992 rad；J1、J3、J4、J5、J6 目标变化均为零。
- J3 反馈最大绝对变化 0.007575 rad，J5 0.009704 rad；
  近期目标未变化但反馈超过漂移门限，J3/J5 各 39 个关联样本。
- 监听窗口 J2/J3/J5 电机速度峰值分别为 0.276/0.149/0.212 rad/s。
  这是监听的较长窗口，不是运动工具短窗口的峰值。
- 每轴 40 个关节样本位于完整目标接收后 200 ms 内；
  更晚 24516 个关节样本没有近期完整目标，不能作近期目标关联。
  单次目标后 software stop、继续被动观察，出现此标签是预期的窗口边界，
  不是证明 24516 帧发生发送失败。
- 观察到 CAN/MOVE J，以及停止后状态 arm_status=1；该状态不能区分
  software stop 和现场硬件急停，不能据此宣称硬件急停已经验证。

software stop 后独立 5 秒检查六轴反馈静止。随后基于本次已明确确认承载的
机械支撑，独立执行 supported-disable，返回 0 / accepted；不是失败路径自动禁用。
已请求关闭左驱动，再次 5 秒关节反馈静止；3 秒低速反馈检查六轴均失能。
无其它业务节点后请求关闭隔离 ROS core。

## 结论与限制

本机观察到非目标 J3/J5 指令字段保持监听基准不变，但反馈和电机速度有变化。
该记录不支持简单的目标字段串位解释；排查重点转向控制器执行、参考系和机械响应。
本机 SocketCAN 观察仍不是控制器接收 ACK，没有 kernel/hardware 时间戳，
也没有独立外部运动测量，不能确定根因或排除设备端丢帧。
不添加补偿、不修改保护阈值、不升级固件或控制栈、不继续运动、不发布 PR。
返回保护未进入，未得到真机验证。现场异响、抖动、支撑受力观察待用户补充。
