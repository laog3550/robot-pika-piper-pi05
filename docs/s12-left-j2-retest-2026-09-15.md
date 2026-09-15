# S12 左 J2 单次支撑下复测

状态：阻塞。日期：2026-09-15。验证等级：真机（失败记录，不是验收通过）。

## 条件与范围

用户明确批准一次左 J2 +0.005 rad、5% 复测。此前确认机械支撑、硬件急停、
双人值守；原门禁已有 incident review、mechanical inspection、enable-settle
通过记录。只记录本次批准到 Git 忽略的现场 env，测试后已清空。
未启动右驱动或遥操作。测试前关闭 Pika input-only，核对仅剩 ROS Master/rosout，
随后以 auto_enable=false 启动项目 s09 单侧驱动（其初始化会发送模式命令）。
固件保持 S-V1.8-2，依赖版本不变。

## 执行与结果

使用已修补的逐样本 CAN 检查和返回保护工具执行：

```bash
rosrun pi05_control single_arm_low_speed_acceptance.py move \
  --side left --joint 2 --delta-rad 0.005 --speed-percent 5 \
  --resume-stop --apply --confirm-single-arm --confirm-mechanical-support
```

返回 1，去程检测失败，未继续返回阶段：

- ROS/raw CAN 基准最大差异 J5 = 0.000192 rad。
- 非目标 J3 漂移连续三样本超过 0.002 rad：delta = -0.004677 rad。
- 同时目标 J2 delta = +0.002391 rad。
- 接收窗口峰值电机速度 J1 0.024、J2 0.150、J3 0.186、J4 0.000、
  J5 0.070、J6 0.000 rad/s。说明本次并非只看到关节位姿反馈变化。
- 工具 software stop 服务调用未报错；未自动 disable。

随后的独立 5 秒被动检查，六轴关节变化范围均为 0.000000 rad，
各电机 1000 样本，报告速度均为 0.000 rad/s。
这仅证明该观察窗口反馈静止，不等于安全禁用、机械承载确认或硬件急停验证。

## 当前限制

本次只表明去程漂移保护触发并终止了验收；返回保护没有得到真机验证。
非目标运动仍可复现，根因未知，不启动连续遥操作、不重复运动、不加入补偿。
一次性批准已清空，未发布 PR。
左驱动在本记录写入时仍保留，以便经现场确认机械支撑已实际承载后执行独立
supported-disable；机械臂可能仍使能。现场异响、抖动、支撑受力观察尚待用户补充。
若出现异常运动必须立即使用硬件急停，不能依赖 ROS。

## 后续停止状态核对

用户随后确认机械支撑实际承载。独立 supported-disable 工具返回 1：
`ROS master is not online`，未调用 disable 服务，不能记为本工具禁用成功。
检查发现 ROS Master、Piper 驱动、Pika locator 和验收进程均已不在运行；
这些进程何时以及由谁关闭未确认，没有重新启动控制系统。

之后 5 秒被动 CAN 检查反馈 20/20 类齐全，无控制/配置帧，六轴变化范围均为零。
另一个 3 秒被动窗口按现有 SDK 低速反馈定义解码 0x261..0x266 的
Byte 5 bit 6：六轴各 120 样本均反馈 disabled，没有发送 CAN 帧。
因此当前已观察到六轴失能且控制进程关闭，但禁用操作来源未知，
仍不表述为 supported-disable 命令执行成功，也不替代现场机械支撑与硬件安全确认。
