# S08 双侧只读通信

本阶段只验证设备身份和反馈数据，不使能 Piper、不发送 CAN 帧、不向 Pika 写串口命令。
S07 未完成项仍然有效；本页不是运动许可。

## Pika 串口检查

先确认当前登录会话属于 `dialout`，并检查稳定别名：

```bash
id -nG | tr ' ' '\n' | grep -x dialout
scripts/configure_pika_serial.sh check left
scripts/configure_pika_serial.sh check right
```

然后分别执行只读帧检查：

```bash
scripts/check_pika_stream.sh left
scripts/check_pika_stream.sh right
```

检查器从 `config/pi05.env` 读取分侧别名，在一次只读打开中临时设置 460800/8N1，并在
退出时恢复原 termios。它不调用串口写 API、不启动 ROS，只输出字节数、候选帧数、完整
帧数、完整率和候选频率；原始数据及传感器值不会显示或保存。

默认退出条件是 5 秒内至少 10 个完整帧、完整率至少 95%。返回码含义：

- `0`：数据存在且达到完整性阈值。
- `1`：空流、没有 Pika 帧头、完整帧不足或完整率不足。
- `2`：参数错误。
- `3`：配置、权限或设备读取错误。

参考工作区的 `sensor_tools/serial_gripper_imu.cpp` 启动时会写入电流限制命令，后续还可
写灯光、振动和夹爪控制，因此不作为 S08 只读检查入口。

## Piper CAN 检查

分别执行：

```bash
scripts/check_piper_can_stream.sh left
scripts/check_piper_can_stream.sh right
```

该入口先复用 S05 的接口身份、USB bus-info、UP 状态和 1 Mbps 检查，再用 Linux 原生
SocketCAN `recv` 被动统计反馈 ID。它不调用 SDK、不发送帧，也不打印或保存 payload。
退出码 `0` 要求标准反馈 ID `0x251–0x256`、`0x261–0x266`、`0x2A1–0x2A8` 均至少出现
两次；发现已知运动/配置 ID 或缺少反馈 ID 时返回 `1`。

参考 `start_double_piper.launch` 默认 `auto_enable=true`；即使覆盖为 false，其单臂节点
初始化仍会发送 `MotionCtrl_2`。因此该 launch 和现有 Piper ROS 节点均不属于 S08 只读
入口。

## Piper ROS 原始反馈

完成 catkin 构建后，可以启动本项目独立实现的双侧接收节点：

```bash
source /opt/ros/noetic/setup.bash
source devel/setup.bash
roslaunch pi05_control s08_readonly_feedback.launch
```

该 launch 仅启动两个 SocketCAN `recv` 节点，不导入 Piper SDK、不创建订阅者或服务、
不调用 CAN 发送 API。输出是：

- `/left_arm/joint_states_raw`
- `/right_arm/joint_states_raw`

消息类型均为 `sensor_msgs/JointState`。`position[0:6]` 按协议反馈 ID `0x2A5–0x2A7`
解码为 rad，`position[6]` 按 `0x2A8` 解码为夹爪行程 m；名称明确包含 `left` 或
`right`。该接口只表达协议原始顺序，尚未声明与 URDF 的关节命名/方向兼容，不能作为
控制目标。

## Pika ROS 定位检查

先启动经现场批准的定位发布者并 source 含固定版 `data_msgs` 的工作区，然后运行：

```bash
scripts/check_pika_localization.sh --duration 10
```

检查器只订阅 `/pika_pose_l|r` 和 `/pika_localization_status_l|r`，不启动定位节点、不创建
发布者或服务，也不显示坐标、frame 名称或跟踪器标识。默认要求两侧位姿至少 30 Hz、
各至少 5 条状态消息、所有状态均为 `accurate=true`，同时要求位姿有限、四元数合理、
时间戳单调且 frame 在窗口内稳定。全部满足返回 `0`，验收失败返回 `1`，参数错误返回
`2`，ROS 或消息环境缺失返回 `3`。
ROS Master 不可达时检查器会在 2 秒内返回 `3`，不会无限等待定位节点启动。

## 已取得的真机结果

2026-09-11，在 ROS Master 未运行、两台 Piper 未由本项目驱动使能的条件下：

- `left_piper` 与 `right_piper` 均唯一匹配已确认的 USB bus-info，处于 1 Mbps；被动监听
  5 秒分别收到 15193 和 15186 帧，未显示或保存帧内容。
- `/dev/pi05-pika-left` 与 `/dev/pi05-pika-right` 均唯一匹配已确认物理路径，权限恢复为
  `dialout:0660`。
- 最终检查对左右各读取 5 秒：左侧发现并完整解析 626 个候选帧，右侧发现并完整解析
  625 个候选帧；两侧完整率均为 100%，候选频率分别约 125.2 Hz 和 125.0 Hz，检查
  前后 termios 一致。
- 新 CAN 检查器对左右各被动接收 3 秒：左侧 9121 帧、右侧 9120 帧；两侧均覆盖 20/20
  个预期反馈 ID，未观察到控制/配置 ID 或未知 ID，payload 未显示或保存。
- 双侧只读 ROS 节点以持续订阅方式观测 5 秒：左侧 859 条（171.8 Hz）、右侧 839 条
  （167.8 Hz）；每条消息均有 7 个分侧名称和 7 个有限、合理范围内的位置值，时间戳
  单调。节点运行期间并行被动审计两侧各 1 秒 3040 帧，仍覆盖 20/20 个反馈 ID，未
  观察到控制/配置或未知 ID。
- ROS graph 审计未发现该 launch 创建命令订阅者、控制服务或全局运动入口。
- 使用本机现有 `pika_double_locator_node` 在隔离 ROS Master 中进行 20 秒只读观测：左右
  `/pika_pose_l|r` 各收到 2401 条（120.0 Hz），位姿有限、四元数范数合理且时间戳单调；
  但左右 `/pika_localization_status_l|r` 的 `accurate` 均为 0/20，因此当前定位不得作为
  控制输入。观测未显示或保存坐标、跟踪器标识。
- 跟踪器重新识别后的复验中，左右位姿各 1202 条（119.9 Hz）；左侧状态 1110 条、
  右侧 996 条，但两侧均只有 1 条 `accurate=true`。参考节点持续发布最后一次位姿，
  而定位更新超时后高频发布 `accurate=false`；因此该结果仍为失败，不能把 Pose 发布
  频率当作持续跟踪频率。

早先用 `stty` 与独立 `cat` 进程组合所得的截断结果不能复现，原因是临时读取方法没有在
同一只读打开中管理串口状态；该结果已被新检查器推翻，不作为设备故障证据。

## 验收结论与后续边界

- 在不启动任何命令发布者的情况下确认左右 Pika 定位数据、侧别、坐标语义和断流行为。
- 当前首要现场门禁是恢复 Vive 有效定位：检查基站供电、可视范围和遮挡后重新观测，
  再运行 `scripts/check_pika_localization.sh --duration 10`；必须返回 `0`，不能仅以
  `/pika_pose_l|r` 有消息判定通过。
- 若跟踪器能够枚举但有效更新不能持续，按照 libsurvive 的现场流程重新标定基站；该
  操作会更新用户目录中的 libsurvive 配置，执行前应单独备份且不得提交配置文件。
- 现场已在逐字节校验备份后执行 45 秒 `--force-calibrate`，随后提供移动/静置跟踪器的
  现场窗口并继续标定 60 秒。两次均识别 2 个跟踪对象并更新配置，后一次出现 4 个拟合
  成功标记和 2 条 OOTX 相关日志。最终 15 秒检查中左右位姿约 120 Hz，两侧仍各只有
  1 条有效状态，检查返回 `1`。因此当前缺口收敛为基站 OOTX、模式或可视条件，不能
  继续重复配对或放宽验收标准。
- 用户确认完成后续现场校准后，在隔离 ROS Master 中再次执行 15 秒验收：左右各收到
  1804 条位姿（119.9 Hz）和 15 条状态，但两侧有效状态仍为 0，检查返回 `1`。同期
  15 秒底层有 4 条 OOTX 事件和 2 个拟合成功事件，未输出或保存原始日志、位姿或设备
  标识。校准操作完成不等同于定位验收通过。
- 随后完成有效跟踪恢复并执行最终 15 秒验收：左侧 1804 条位姿（120.0 Hz）、状态
  1900/1900 有效；右侧 1803 条位姿（119.9 Hz）、状态 1777/1777 有效。有限值、
  四元数、时间戳和 frame 检查全部通过，检查器返回 `0`。
- 将已验证的 Piper 原始 ROS 反馈与 URDF 的关节命名、顺序和安装方向做后续只读适配；
  当前 `joint_states_raw` 不作兼容性承诺。

S08 的双侧数据门禁已经满足。发布前发现并由现场修正了覆盖右侧 Pika 权限的遗留 udev
规则，最终左右字符设备均为 `root:dialout 0660`。该结论不授权运动，仍不得把参考
`start_double_piper.launch` 作为只读入口；Pika 到机械臂的坐标语义、安装变换和定位
丢失停机行为留待后续安全控制与遥操作阶段验证。

`pika_locator` 仅在参考工作区中以已安装 ELF 形式存在。其安装包元数据声明 MIT，但当前
没有可核验的源码来源、commit 和许可证文件，所以本阶段没有把该二进制或源码复制进
项目，也没有把它加入可重复依赖清单；上述运行只使用本机既有安装进行现场诊断。
