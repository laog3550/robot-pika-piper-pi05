# PI05 直接遥操作

## 目标

按 PikaAnyArm 的整体结构，将左右 Pika 位姿分别连接到对应 Piper 的 FK、IK 和关节控制，
优先取得可用于后续数据采集的双臂遥操作能力。

## 保留的现场配置

重构不改变 `PI05_*` 环境变量、ROS overlay 路径、串口别名或 USB-CAN 身份绑定。Piper
驱动默认继续使用 `left_piper` 和 `right_piper`，可通过单侧 launch 的 `can_port`
（双臂入口为 `left_can_port`／`right_can_port`）显式覆盖。

## 启动顺序

日常启动顺序：

1. 按现有部署启动 ROS master。
2. 加载保存 `pika_L_code`、`pika_R_code` 的本机环境，然后用统一入口启动双 Pika 输入：

   ```bash
   scripts/start_pika_input.sh              # 读取 config/pika-mapping.env 后启动
   scripts/start_pika_input.sh --check       # 只校验映射配置，不启动节点
   ```

   该脚本把左右映射当成显式现场配置：先要求 `pika_L_code`/`pika_R_code` 存在，再读取
   Git 忽略的 `config/pika-mapping.env` 取得 `PI05_PIKA_MAPPING_ORDER`，最后以
   `mapping_order:=<实测值>` 启动 launch。缺失或非法时**直接退出码 3**，不会静默串侧
   （首次使用先 `cp config/pika-mapping.env.example config/pika-mapping.env` 并填实测值）。
   需要临时覆盖时显式传参，或直接 `roslaunch pi05_pika_input pika_input_only.launch
   start_locator:=true left:=true right:=true mapping_order:=<取值>` —— 此时 launch 的默认值
   是 `unverified`，`safe_locator` 会拒绝启动。

   取值错误时两侧位姿话题仍按 120 Hz 发布、`accurate` 也可能为真，但左右会静默对调——
   表现为操作一只手柄时另一只臂不动。确认方法见下面“左右映射确认”一节。
3. 运行 `scripts/check_pika_mapping.py --duration 10`，只移动一只手柄，确认该侧 IMU 与
   位姿同步响应、另一侧完全静止。换另一只手柄再测一次，确认左右与操作直觉一致。
   工具会同时核对“现场配置声明值”与“当前运行实例实际取值”，两者不一致直接判失败。
4. 确认 `/pi05/pika_input/left/pose` 和 `/pi05/pika_input/right/pose` 正在发布，
   并运行 `scripts/check_pika_localization.sh --side both --duration 10` 检查实际频率与定位有效性。
   工具默认检查当前 input-only 话题；仅检查一侧时使用 `--side left` 或 `--side right`。
   检查旧厂商话题时显式使用 `--topic-layout vendor`。
   若状态为 inaccurate，先恢复定位，再继续分侧遥操作。
5. 分侧联调优先使用平滑会话入口，它把使能、运行、返回支撑姿态和失能串成一次会话：
   `scripts/run_smoothed_teleop.sh left --apply`（或 `right`）。按 Enter 结束，或用
   `--duration 20` 定时结束。需要夹爪时加 `--with-gripper`。
6. 只做直连（不做自动回位）时，运行 `scripts/start_left_teleop.sh` 或
   `scripts/start_right_teleop.sh`，然后使用 Pika 厂商触发动作开始或停止该侧遥操作。
   该入口的 `auto_enable` 默认为 `true`，即驱动启动后自动使能；需要手动使能时显式传
   `auto_enable:=false`。注意厂商 `/teleop_trigger_*` 响应的 `success` 字段恒为假，
   判断触发结果要看节点日志的 `start`／`close`。
7. 两侧分别通过后，退出已有分侧驱动和遥操作，再运行 `scripts/start_dual_teleop.sh`
   验证双臂入口。

更新已有目标机仓库时，先保存 `config/pi05.env`，执行 `git pull` 和
`scripts/build_catkin.sh`，再确认该文件仍在且两路 `configure_can.sh check` 均通过。

左臂运行时可另开终端启动右臂，反之亦然。启动检查只拒绝本侧冲突；双臂入口
检查两侧。既有 `piper_readonly_feedback` 节点可继续运行；本侧已有运动驱动或
未明确归属左右命名空间的旧 Piper/teleop 节点仍需先退出。
检查话题存在只说明有注册发布者，实际输入频率和定位有效性需在联调时确认。

## 左右映射确认

`mapping_order` 只有 `direct`（`pika_L_code` 那只手柄当左）和 `swapped`（反过来）两个
取值，取决于哪只手柄的 code 存在哪个环境变量里，属机器现场事实。**接错或改动过 USB、
重新配对过 dongle、换过手柄之后都要重新确认**，因为错误是静默的：

| 看起来正常 | 实际可能已错 |
|---|---|
| 两侧位姿 120 Hz | 左右对调，操作右手柄时左臂动 |
| `localization_status` 全 `accurate` | 定位本身没问题，只是标签错了 |
| 夹爪（走串口编码器）能动 | 关节链路可能吃的是另一只手柄的静止数据 |

确认方法（依据 IMU 与位姿必须同侧响应，不依赖操作员记忆）：

```bash
# 采样窗口内【只移动一只手柄】，另一只完全不动
scripts/check_pika_mapping.py --duration 10
```

- 只有一侧 IMU 峰值明显（≥0.30 rad/s）且该侧位姿同步变化（≥0.02 m）→ 这只手柄被
  分配为该侧；换另一只手柄再测一次即可确认左右是否符合操作直觉。
- IMU 动而位姿不动 → 光学定位没跟上这只手柄，此时遥操作必然表现为“手柄动了臂不动”。
- 两侧同时动 → 无法区分，请分次只动一只。

实测确认后，把结论写进 Git 忽略的本机文件 `config/pika-mapping.env`：

```bash
cp config/pika-mapping.env.example config/pika-mapping.env   # 首次
# 编辑填入实测取值：PI05_PIKA_MAPPING_ORDER=direct 或 swapped
scripts/start_pika_input.sh --check                          # 校验配置可被正确读取
```

之后统一用 `scripts/start_pika_input.sh` 启动；`scripts/check_pika_mapping.py` 也会核对
“配置声明值”与“当前运行实例实际取值”是否一致，不一致直接判失败。

该文件含机器相关结论，已被 `.gitignore` 忽略，不要提交；仓库里只保留
`config/pika-mapping.env.example` 模板。

> 已实测确认（2026-09-16）：右手柄驱动 `right`、左手柄驱动 `left` 需要
> `mapping_order:=swapped`。若现场出现“操作一只手柄时另一只臂不动”，先按本节重测，
> 不要直接去查 IK 或平滑器。

## 接口

| 侧别 | Pika 输入 | Piper 反馈 | Piper 指令 | CAN |
|---|---|---|---|---|
| 左 | `/pi05/pika_input/left/pose` | `/joint_states_single_l` | `/left_arm/joint_ctrl_raw` | `left_piper` |
| 右 | `/pi05/pika_input/right/pose` | `/joint_states_single_r` | `/right_arm/joint_ctrl_raw` | `right_piper` |

使能成功后的关节轻微变化不参与软件判定。运行链路没有授权心跳、故障锁存、现场批准文件
或跨侧联锁。Piper 驱动提供的原生服务保持可用。

## 可选关节目标平滑

厂商 IK 以 50 Hz 直接发布目标，原始驱动在消息未指定速度时使用 50% 速度。
若遥操作抖动明显，可启用本项目的轻量平滑节点：

```bash
# 右臂，保持手动使能
scripts/start_right_teleop.sh auto_enable:=false smooth_commands:=true

# 左臂
scripts/start_left_teleop.sh auto_enable:=false smooth_commands:=true

# 双臂
scripts/start_dual_teleop.sh auto_enable:=false smooth_commands:=true
```

平滑器位于 IK 和驱动之间，默认使用：

- 50 Hz 输出；
- `0.12 s` 低通时间常数；
- `0.30 rad/s` 目标速度上限；
- `0.50 rad/s²` 目标加速度上限；
- `0.0005 rad` 死区；
- Piper 驱动速度百分比 `20%`。

例如希望更柔和、允许更明显延迟：

```bash
scripts/start_right_teleop.sh auto_enable:=false smooth_commands:=true \
  smoothing_time_constant:=0.20 \
  smoothing_max_velocity:=0.20 \
  smoothing_max_acceleration:=0.30 \
  smoothing_driver_speed_percent:=15
```

时间常数越大、速度和加速度越低，动作越平滑，但跟手延迟越明显。默认只处理
J1–J6；输入超过 `0.25 s` 未更新时停止继续发布，恢复后从最新机械臂反馈重新起步。
它不是运动安全状态机，仍需使用原生 stop／急停。

### 夹爪遥操作

平滑会话可增加 `--with-gripper`。该选项先用 `config/pi05.env` 校验对应侧 Pika
串口身份，再启动只读编码器节点。左右 Pika 与 Piper 夹爪行程均按现场确认配置为
`0–100 mm`。限幅后直接作为
`JointState.position[6]` 与六轴目标一起发送。
串口输入超过 `0.25 s` 未刷新时停止整组目标输出。

```bash
scripts/run_smoothed_teleop.sh right --apply --with-gripper --duration 20
```

左侧使用完全对称的入口：

```bash
scripts/run_smoothed_teleop.sh left --apply --with-gripper --duration 20
```

注意位姿和夹爪采用两套不同的身份来源：位姿按已确认的 `mapping_order=swapped` 将
`pika_R_code` 归入逻辑 `left`；夹爪编码器则直接使用稳定设备别名
`/dev/pi05-pika-left`。两者最终都只能进入 `/left_arm` 链路。

`--with-gripper` 只是让会话脚本按 `config/pi05.env` 校验该侧串口，再把下面这些 launch
参数传给 `side_teleop.launch`；直接使用 launch 时也可以自己传：

| launch 参数 | 默认值 | 作用 |
|---|---|---|
| `enable_gripper_teleop` | `false` | 启动 `gripper_input.py` 并让驱动改用 `safe_gripper_piper_driver.py` |
| `pika_gripper_device` | `/dev/null` | 要只读打开的 Pika 串口设备 |
| `pika_gripper_topic` | `/pi05/pika_input/{side}/gripper` | 夹爪目标话题 |
| `piper_gripper_maximum` | `0.10` | 映射后的 Piper 行程上限（m），必须与控制器 `max_range_config` 一致 |

右侧控制器参数查询返回 `max_range_config: 100`，现场同时确认左、右 Pika 行程一致，
因此左右单臂入口和双臂入口均使用 `0.10`。

夹爪输入只有在平滑模式下才会被消费：平滑器节点受 `smooth_commands` 控制，不带
`--with-gripper` 时维持已验收的六关节行为。**不要在非平滑模式单独设
`enable_gripper_teleop:=true`**——那会换上夹爪模式驱动并启动编码器节点，但没有平滑器
订阅夹爪话题，夹爪只被保持当前位置。

该功能默认关闭，现有直连行为不变。上线前先分侧使用保守参数验证，再用于双臂。

## 不接运动驱动的组件联调

有双侧只读反馈时，可使用以下入口验证厂商组件启动和 FK 链路。反馈来自
`src/pi05_control/launch/s08_readonly_feedback.launch` 启动的只读节点，它从 SocketCAN
直接解码并发布 `/{side}_arm/joint_states_raw`，不需要运动驱动。
先加载 [命令速查](arm-commands.md) 中的 ROS 环境；官方 Piper 模型路径与启动脚本一致。

```bash
export ROS_PACKAGE_PATH="/home/mips/robot/pi05-upstream-src/piper_ros/src/piper_description:$ROS_PACKAGE_PATH"
roslaunch pi05_left_teleop dual_teleop.launch \
  start:=true connect_drivers:=false auto_enable:=false \
  left_feedback_topic:=/left_arm/joint_states_raw \
  right_feedback_topic:=/right_arm/joint_states_raw \
  left_command_topic:=/pi05/rehearsal/left/joint_target \
  right_command_topic:=/pi05/rehearsal/right/joint_target
```

这组参数不启动运动驱动，并将 IK 目标输出至独立诊断话题。不要将诊断话题连接到
运动驱动；该联调不调用触发开始服务。结束时在该终端按 Ctrl+C。
实际遥操作继续使用原有启动脚本及默认反馈／控制话题。

2026-09-16 已运行约 18 秒：六个组件持续运行，左／右 FK 收到 2855／2840 个
位姿样本，诊断输出无订阅者，测试节点正常退出。未验证触发后的 IK 跟随或真机运动。

## 本阶段之外

左右臂共同的支撑初始姿态、手动返回入口及单臂平滑会话结束后的自动回位流程已记录在
[机械臂命令速查](arm-commands.md)。数据录制和 π0.5 模型部署不属于当前直接遥操作改动。
