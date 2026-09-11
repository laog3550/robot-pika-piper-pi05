# S08 双侧只读通信

## 目标

在不使能、不发送 CAN 帧和不向 Pika 写串口命令的条件下，验证两路 CAN、两路 Pika
串口/定位和两臂 ROS 反馈可以按侧独立识别。

## 完成内容

- 新增标准库-only Pika 串口检查器和分侧 shell 入口。
- 设备仅以 `O_RDONLY | O_NOCTTY | O_NONBLOCK` 打开；临时设置 460800/8N1 后恢复原
  termios，不输出或保存原始数据。
- 按 `Command + AS5047` 顶层字段识别当前 Pika JSON 帧，只报告汇总统计。
- 新增离线测试，覆盖完整流、截断流、空流、非法时长和无写 API 约束。
- 新增独立 SocketCAN 被动检查器，要求 20 个标准反馈 ID 完整出现，并在发现控制/配置
  ID 时失败；只使用 `recv`，不导入会发送帧的 Piper SDK 接口。
- 新增独立双侧 ROS 原始反馈节点和 launch，只接收 `0x2A5–0x2A8`，分别发布
  `/left_arm/joint_states_raw` 与 `/right_arm/joint_states_raw`。
- 新增协议解码单元测试和 ROS 节点静态契约测试，覆盖端序、单位、完整帧组、分侧命名
  空间、无 CAN 发送 API、无命令订阅者和无控制服务。
- 新增双侧 Pika ROS 定位验收器；只订阅并汇总频率/有效性，拒绝无效状态、异常位姿、
  时间戳倒退和 frame 变化，不启动定位节点或输出坐标/设备标识；ROS Master 缺失时
  2 秒内以环境错误退出。

## 接口与兼容性

新增运维入口：

```bash
scripts/check_pika_stream.sh [--config PATH] [--duration SECONDS] <left|right>
scripts/check_piper_can_stream.sh [--config PATH] [--duration SECONDS] <left|right>
scripts/check_pika_localization.sh [--duration SECONDS]
```

检查器只依赖 Ubuntu 20.04 的 `/usr/bin/python3` 标准库和现有 `config/pi05.env`，不会
导入或执行上游 `sensor_tools`。新增 ROS 接口均为显式原始反馈：

| 接口 | 类型 | 内容 | 边界 |
|---|---|---|---|
| `/left_arm/joint_states_raw` | `sensor_msgs/JointState` | 左侧 6 关节 rad + 夹爪行程 m | 只读、非 URDF 兼容承诺 |
| `/right_arm/joint_states_raw` | `sensor_msgs/JointState` | 右侧 6 关节 rad + 夹爪行程 m | 只读、非 URDF 兼容承诺 |

## 验证记录

验证日期：2026-09-11。

- `tests/test_pika_stream_checker.sh`：通过。
- `tests/test_piper_can_stream_checker.sh`：通过；覆盖反馈完整、缺失反馈、出现控制 ID 和
  无发送 API 约束。
- `tests/test_piper_readonly_feedback.sh`：通过；4 个协议解码测试及 ROS launch/无发送
  契约通过。
- `tests/test_pika_localization_checker.sh`：通过；有效/无效聚合判断、参数失败和无写 API
  契约通过。
- `scripts/check_pika_localization.sh --duration 10`：按预期返回 `1`；左右各 1202 条位姿
  （119.9 Hz）和 10 条状态，左右有效状态均为 0，准确拒绝了当前无效跟踪。
- `scripts/check_pika_localization.sh --duration 15`：最终返回 `0`；左侧位姿 1804 条
  （120.0 Hz）、状态 1900/1900 有效，右侧位姿 1803 条（119.9 Hz）、状态
  1777/1777 有效。
- `catkin_make run_tests_pi05_control`、`catkin_test_results --verbose`：4 个测试，0 错误、
  0 失败。
- `bash -n scripts/check_pika_stream.sh tests/test_pika_stream_checker.sh`：通过。
- `/usr/bin/python3 -m py_compile scripts/check_pika_stream.py`：通过。
- `scripts/build_catkin.sh`：通过。
- `git diff --check`：通过。

## 真机证据

- 左右 CAN 身份与 1 Mbps 检查通过；仅被动监听 5 秒，分别统计到 15193、15186 帧。
- 左右 Pika 稳定别名通过，设备权限为 `dialout:0660`。
- 左侧 Pika：最终检查 5 秒 626 个候选帧、626 个完整帧、完整率 1.000、约 125.2 Hz。
- 右侧 Pika：最终检查 5 秒 625 个候选帧、625 个完整帧、完整率 1.000、约 125.0 Hz。
- 左侧 Piper CAN：3 秒 9121 帧，20/20 个反馈 ID，无控制或未知 ID。
- 右侧 Piper CAN：3 秒 9120 帧，20/20 个反馈 ID，无控制或未知 ID。
- 双侧 ROS 原始反馈持续订阅 5 秒：左侧 859 条（171.8 Hz）、右侧 839 条（167.8 Hz）；
  7 个名称/位置、有限值、合理范围与单调时间戳检查均通过。
- ROS 节点运行时并行被动审计左右各 1 秒 3040 个 CAN 帧，20/20 个反馈 ID 完整，未
  观察到控制、配置或未知 ID；ROS graph 未发现命令订阅者或控制服务。
- 本机既有 Pika 双定位节点在隔离 ROS Master 中只读观测 20 秒：左右位姿各 2401 条、
  均为 120.0 Hz；有限值、四元数范数和单调时间戳通过。左右定位有效状态均为 0/20，
  所以本项明确判定未通过，不以“位姿话题有数据”替代有效定位。
- 重新识别两只跟踪器后的 10 秒复验：左右位姿各 1202 条（119.9 Hz），左/右状态分别
  1110/996 条，但两侧各仅 1 条有效。二进制行为审查确认 Pose 线程会重复发布最后值，
  定位更新超时则发布无效状态，因此仍判定未通过并要求重新标定基站。
- 经用户授权，在校验本地配置备份后执行 45 秒强制标定及 60 秒继续标定；两次均识别
  2 个跟踪对象并更新配置，继续标定有 4 个拟合成功标记和 2 条 OOTX 相关日志。最终 15 秒
  检查左右位姿分别 1805/1804 条（约 120 Hz），左右状态分别 1796/1700 条，但各仅
  1 条有效，返回 `1`。标定未被表述为通过，备份保留在用户配置目录用于恢复。
- 用户确认完成后续现场校准后再次隔离复验 15 秒：左右各收到 1804 条位姿（119.9 Hz）
  和 15 条状态，两侧有效状态均为 0，检查返回 `1`。同期底层摘要出现 4 条 OOTX 事件
  和 2 个拟合成功事件；未输出或保存原始日志、位姿、frame 或跟踪器标识。因此 S08
  仍不满足定位退出条件。
- 有效跟踪恢复后的最终 15 秒真机复验通过：左侧 1804 条位姿（120.0 Hz）、状态
  1900/1900 有效；右侧 1803 条位姿（119.9 Hz）、状态 1777/1777 有效。检查期间未
  输出或保存位姿、frame 或跟踪器标识，退出码为 `0`。
- 两侧检查前后 termios 一致；未输出或保存原始帧，未启动上游 Piper 驱动或会写串口
  的 Pika 传感器节点，未发送串口/CAN 数据。定位诊断只启动了既有 Vive 读取节点。

## 风险与限制

- S07 仍有用户选择不采集的现场安全字段，本阶段证据不关闭这些缺口，也不提供运动许可。
- 已确认左右 Piper 原始反馈到 ROS 的分侧、协议顺序、单位、时间戳和频率，并确认双侧
  Pika 定位在最终观察窗口内持续有效；尚未完成 URDF 安装方向、零点和坐标映射适配。
- libsurvive 用户配置和标定备份均留在仓库外；不得删除备份或将本机配置提交到仓库。
- “校准完成”只表示配置流程结束；阶段验收以两侧状态在完整观察窗口内持续
  `accurate=true` 且检查器返回 `0` 为准。
- 发布前复核发现右侧 Pika 字符设备为 `root:dialout 0777`；遗留
  `/etc/udev/rules.d/sensor_serial.rules` 中的物理路径规则使用 `MODE:="0777"`，覆盖了
  S05 的 `0660` 规则。该规则属于主机配置，未由本阶段自动修改；现场修正后左右设备
  均复验为 `root:dialout 0660`。
- 当前协议识别只覆盖现场观测到的 `Command + AS5047` JSON；固件改变格式时检查器会
  安全失败，需要重新审查而不是放宽阈值。

## 回滚方式

撤销本阶段仓库文件即可。检查器不创建持久配置、不修改 udev、不保存数据；真机运行
结束时恢复原 termios。本次 libsurvive 标定另有逐字节校验的现场备份；如需回滚，先
停止所有 Vive 进程，再用该备份覆盖用户目录中的 `config.json`。备份不得提交到仓库。

## 来源与许可证

- 帧字段和 460800/8N1 基线来自只读观察及
  `/home/mips/pika_ros/src/sensor_tools/src/serial_gripper_imu.cpp` 的行为审查。
- Piper 反馈/控制 ID、端序与比例单位来自批准依赖 `piper_sdk@081e7c58...` 的协议事实，
  并由现场被动流交叉验证；没有复制 SDK 实现。
- 检查器为本项目独立实现，没有复制上游源码、二进制或许可证正文。
- `pika_locator` 仅有本机安装产物；包元数据声明 MIT，但缺少可核验源码来源、commit 与
  对应许可证文件。本阶段仅执行既有产物做现场诊断，没有复制或纳入项目依赖。
