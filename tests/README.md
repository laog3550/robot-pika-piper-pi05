# 验收测试

测试按风险递增执行，并保存日期、硬件编号、软件提交 SHA、参数和结果。

多数 `.sh` 测试是离线契约测试：用 mock 或临时目录代替 ROS、CAN 和串口，不需要
master，也不接触硬件。少数需要 `roslaunch` 或独立 master 的用例已在下文单独标注。

## 阶段 A：静态检查

- catkin 构建成功
- launch/XML/YAML/Python 语法检查通过
- 依赖和许可证清单完整
- 配置中没有密钥或现场隐私信息

## 阶段 B：无电机运动

- CAN 接口名称、比特率和错误计数正确
- Piper 状态、六关节与夹爪反馈稳定
- Pika 串口、定位和触发服务稳定
- 话题频率、单位、关节顺序和时间戳正确

## 直接遥操作

- 左右 Pika 话题分别进入对应厂商 teleop/FK/IK 组件
- 左右 IK 输出分别连接对应 Piper 驱动
- `left_piper`、`right_piper` 固定 CAN 名称保持不变
- 左、右、双臂启动入口均能展开

## 仓库级脚本测试

- `test_environment_scripts.sh`：S04 环境脚本契约测试。会在临时工作区真实执行
  `catkin_make`，是本目录中最慢的测试。
- `test_device_configuration_scripts.sh`：S05 check/apply 分离、脱敏发现、安全配置解析和
  身份歧义拒绝测试；使用模拟命令，不修改主机设备。
- `test_s07_hardware.sh`：S07 现场记录字段、双人复核、安全结论、危险文本与疑似敏感
  标识拒绝测试；不访问硬件。
- `test_upstream_manifest.sh`：固定 commit、受限清单结构和未知字段拒绝测试。
- `test_pika_stream_checker.sh`：S08 Pika 完整/截断/空流、参数校验和只读 API 约束测试。
- `test_piper_can_stream_checker.sh`：S08 Piper CAN 反馈 ID 完整性、控制 ID 拒绝和无发送
  API 约束测试。
- `test_piper_joint_stability_checker.sh`：六关节反馈变化范围统计、`--exclude-joint`
  和非目标关节越限判据测试。
- `test_piper_motor_telemetry_checker.sh`：`0x251`–`0x256` 样本数、速度/电流峰值汇总和
  样本不足拒绝测试。
- `test_piper_firmware_query.sh`、`test_piper_limit_query.sh`：固件与限位查询脚本的版本
  正则、缺轴拒绝和“不得出现使能/运动 API”契约测试。
- `test_piper_command_feedback_diagnostic.sh`：命令/反馈相关性诊断的标签判定与
  “不是控制器应答”自述测试。
- `test_pika_tracking_diagnostic.sh`：Pika 跟踪诊断的无效段统计、删失处理和输出脱敏测试。
- `test_piper_readonly_feedback.sh`：S08 Piper 协议端序/单位/完整帧组，以及双侧 ROS
  launch、无 CAN 发送 API、无命令入口契约测试。
- `test_pika_localization_checker.sh`：S08 双侧定位频率、有效状态、时间戳、frame 稳定性
  聚合判断和无写入 API 契约测试。
- `test_pika_input_only.sh`：input-only 转发的映射选择、argv 不泄露手持 code、已有
  locator 或 Piper/teleop 节点时拒绝启动。
- `test_pika_shutdown_forwarding.sh`：转发节点在 shutdown 竞态下只发布一次且不掩盖故障。
- `test_single_arm_driver_launch.sh`：左右驱动 launch 展开和接口隔离测试。需要
  `roslaunch`，但不需要 master。
- `test_direct_teleop.sh`：另外用 `roslaunch` 解析 `right_teleop.launch` 在平滑与直连两种
  模式下的节点名和 remap，需要 `roslaunch`，不需要 master。

## 纯离线 Python 测试

这几个 `.py` 不由 `.sh` 包装，需要显式指定解释器；涉及 `piper_sdk`、`yaml` 的用例要用
`.venv/bin/python`。

- `test_direct_teleop.py`：launch XML、平滑器接线、固定 CAN 名称和
  `check_teleop_start.py` 冲突判定的离线回归测试，连同 `test_arm_home.py`、
  `test_joint_command_smoother.py`、`test_piper_feedback_decoding.py`、
  `test_gripper_teleop.py`，覆盖关节与夹爪分离以及会话状态确认。
- `test_piper_feedback_decoding.py`：在 `.venv` 中运行，离线交叉核对固定 SDK 的正负
  int32 反馈解码与六轴目标编码，不建立 CAN 连接。
- `test_arm_home.py`：校验左右臂使用同一组已确认支撑初始姿态及 5% 返回速度；不连接 ROS 或硬件。
- `test_joint_command_smoother.py`：离线验证关节目标平滑器的速度、加速度、死区和异常输入。
- `test_gripper_teleop.py`：验证 Pika 编码器解析、夹爪量程映射、只读串口约束、独立限速
  和夹爪服务接线。
- `replay_pika_input_only.py`：隔离 master 回放脚本，需要 `roslaunch` 和一个独立
  ROS master（`localhost:11331`），只用合成位姿，不接触硬件。
