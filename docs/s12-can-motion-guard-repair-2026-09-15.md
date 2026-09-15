# S12 返回保护与 CAN 接收修补

## 目标与状态

状态：等待真机验收。验证等级：构建、仿真/回放。
继续 `stage/S12-split-side-low-speed-acceptance`，初始 HEAD 为
`3c17a3219091df63e0845aef00e4feef058a8934`。预检与 git status 已运行，
现有 S12 改动保留；用户明确授权在既有验收工具中增量修复。
不提交、推送或发布 PR，不覆盖原阶段报告和状态文件。

## 完成内容

- 返回阶段在原有 ReturnEvidence 前运行独立 MotionEvidence：保持目标关节
  0.020 rad 窗口、非目标关节 0.002 rad 连续三样本保护，以及单样本
  0.010 rad 硬保护。没有放宽阈值或加入关节补偿。
- 原始 CAN 使用独立接收线程持续接收、组装反馈，主线程按 FIFO 顺序检查
  每个组装样本，不丢弃中间的短时异常。目标发布保持至少 50 ms 间隔，
  不再每检查一个反馈便休眠 50 ms。
- 接收队列上限 256 个组装样本；溢出、接收线程异常或组装样本在队列中
  超过 100 ms 均失败关闭，走原有 software stop 路径。100 ms 是本地
  接收后等待时间门限，不是设备生成时间或光学定位时间戳。
- 每次发布目标前先检查反馈。保留 4 秒阶段超时及 0.2 秒反馈等待超时。
- 失败仍只请求 software stop，不自动 disable；支持下 disable 仍为独立操作。

## 验证记录

- `bash tests/test_s12_can_motion_guards.sh`：5 项测试通过，覆盖返回阶段
  漂移/超窗后停止且不 disable、FIFO 短时异常不跳过、陈旧反馈拒绝、
  接收故障优先拒绝、真实接收循环溢出保护和无 ROS 休眠的逐样本检查。
- `PYTHONPATH=src/pi05_control/src /usr/bin/python3 -m unittest discover -s src/pi05_control/test -p 'test_low_speed_acceptance*.py'`：38 项通过。
- `catkin_make`：通过。
- `catkin_make run_tests_pi05_control` 与 `catkin_test_results build/test_results`：79 项，0 errors、0 failures、0 skipped。
- `for test_path in tests/test_*.sh; do bash "$test_path" || exit; done`：全部通过。
- `git diff --check`：通过。

## 真机证据与限制

本修补未执行真机运动、enable 或 disable。此前独立的 10 秒被动检查中，
左侧反馈 ID 20/20，未见控制/配置帧，六轴关节范围及电机反馈速度均为零；
这不证明运动异常已消除，也不是真机修补验收。
此前 J2 超窗、J3 非目标运动及下砸的根因仍未确定。本次修补提升检测保护，
不能保证 hardware stop，也不能作为连续遥操作启动许可。
异常运动必须使用硬件急停；后续真机复测仍要求机械支撑、双人值守及现场批准。

## 接口、回滚与来源

CLI、话题、固件和锁定依赖版本不变。增量仅修改
`src/pi05_control/scripts/single_arm_low_speed_acceptance.py`，新增独立 shell 回归测试和本文。
回滚仅撤销本次增量补丁，保留全部此前未提交工作，不使用 reset、stash 或 checkout。
项目自有实现，沿用仓库许可证；未复制上游源码或二进制。
