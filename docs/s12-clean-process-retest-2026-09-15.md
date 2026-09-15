# S12 清理进程后左 J2 单次复测

日期：2026-09-15。状态：阻塞。验证等级：真机（失败记录）。

## 条件与执行

用户要求清理其它仓库遗留进程，再次批准左 J2 +0.005 rad、5% 的一次复测，并确认现场安全条件。既有本机门禁包含事件复核、左侧机械检查、防坠支撑、硬件急停、双人值守及左侧 enable-settle 通过记录；本次只写入一次性 RETEST_APPROVED=yes，测试后清空。

先清理 11 个机器人业务进程，确认 ROS Master 端口关闭，检查结束后没有 CAN 接收注册。清理后左 CAN 5 秒收到 15,200 帧、20/20 类反馈齐全、无控制/配置帧，六轴反馈范围均为零。右侧无反馈，不作失能确认，没有启动右驱动。

阶段 preflight 通过；保留全部原有未提交文件。HEAD 3c17a3219091df63e0845aef00e4feef058a8934，分支 stage/S12-split-side-low-speed-acceptance。git fetch origin main 成功。gh 不可用，未完成开放 PR 查询；本次不创建新阶段分支或发布。

启动隔离 ROS core 及 s09 左侧驱动（start_driver=true、auto_enable=false；初始化会发送模式命令），启动 40 秒独立被动监听。运动前 3 秒六轴反馈静止。没有启动 Pika、RViz、遥操、IK、安全过滤器或双臂协调器。

```bash
/usr/bin/python3 scripts/diagnose_piper_command_feedback.py \
  --side left --joint 2 --duration 40

rosrun pi05_control single_arm_low_speed_acceptance.py move \
  --side left --joint 2 --delta-rad 0.005 --speed-percent 5 \
  --resume-stop --apply --confirm-single-arm --confirm-mechanical-support
```

## 结果

运动命令返回 1；非目标 J3 连续三样本超过 0.002 rad，末次 delta=-0.004695 rad，同时 J2 delta=+0.005271 rad。ROS/CAN 基准最大差为 J5 0.000234 rad。保护终止去程，未进入返回阶段，未重试。

运动工具短窗口电机速度峰值 J1–J6 分别为 0.002、0.162、0.141、0.000、0.325、0.000 rad/s；电流峰值分别为 0.041、0.847、0.827、0.014、0.591、0.013 A。

独立监听返回 1 / REVIEW_REQUIRED：

- 首个目标前稳定基准成立；收到 6 个目标帧、2 个完整目标组，结束时没有部分组。
- J2 最大目标变化 0.004992 rad；其余五轴目标变化全部为零。
- J3/J5 分别有 41/40 个样本在近期目标未变化时反馈超漂移门限；各轴近期关联样本 50 个。
- 较长窗口反馈最大绝对变化 J2 0.012933、J3 0.010071、J5 0.026913 rad；电机速度峰值 J2 0.205、J3 0.239、J5 0.749 rad/s。
- 较长窗口涵盖使能、运动及停止前后，以上峰值不能当作保护触发时的瞬时读数，不能直接计算 software stop 后的运动量。
- 28,578 个关节样本没有近期完整目标，是关联窗口边界标签，不证明发送失败。SocketCAN 接收不是控制器 ACK，电机反馈不是独立外部运动测量。

## 停止与关闭

运动工具已请求 software stop，服务调用未报错，没有自动 disable。停止后独立 5 秒六轴反馈静止。用户进一步确认机械支撑已经实际承载后，执行独立命令：

```bash
rosrun pi05_control single_arm_low_speed_acceptance.py supported-disable \
  --side left --apply --confirm-mechanical-support
```

返回 0 / supported disable accepted。随后关闭左侧驱动；独立 3 秒低速反馈核验六轴各 120 个 disabled 样本、零 enabled 样本，5 秒关节反馈范围全部为零。最后关闭测试 ROS core，核对没有遗留 ROS/Piper/Pika/RViz/串口夹爪进程。git diff --check 通过。

## 结论与限制

清理其它仓库进程后非目标响应仍可复现，遗留进程不是全部现象的充分解释。没有改变固件、模式策略、保护阈值或添加补偿。根因继续集中于设备端接收/执行、参考状态及安装/机械响应，不能据本次结果唯一断言固件故障。其它仓库历史调用是否改变设备持久状态未确认。独立外部运动测量、主从航空接线、安装方向及支撑接触信息仍缺。

本次失败不构成运动验收或连续遥操放行，不提交、推送或发布 PR。一次性批准已清空。
