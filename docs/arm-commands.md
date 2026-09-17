# Piper 手动控制命令

以下命令供手动执行，不会因打开本文件而运行。示例以左臂为主；执行运动前确认
周围空间可用，并停止已有遥操作，避免并行命令源。失能前确认机械支撑已承载。

## 每个终端加载环境

仅激活 `.venv` 不能替代 ROS overlay。按顺序执行：

```bash
source /opt/ros/noetic/setup.bash --extend
source /home/mips/pika_ros/install/setup.bash --extend
source /home/mips/robot/pi05-upstream-ws/devel/setup.bash --extend
source /home/mips/robot/robot-pika-piper-pi05/devel/setup.bash --extend
source /home/mips/robot/robot-pika-piper-pi05/.venv/bin/activate
```

检查服务消息定义：

```bash
rossrv show piper_msgs/Enable
rossrv show piper_msgs/GoZero
```

若报 `Unable to load type [piper_msgs/Enable]`，先重新加载以上环境。

## 启动驱动

ROS master 未运行时，在独立终端执行 `roscore`。另开已加载环境的终端，选择需要的侧别。
已有对应驱动时不要重复启动。

```bash
# 左臂；不自动使能
roslaunch pi05_control s09_single_arm_driver.launch \
  side:=left start_driver:=true auto_enable:=false

# 右臂；在另一个终端运行
roslaunch pi05_control s09_single_arm_driver.launch \
  side:=right start_driver:=true auto_enable:=false
```

驱动启动本身会发送模式指令，`auto_enable:=false` 不代表纯只读。

## 使能与失能

```bash
# 左臂使能
rosservice call /left_arm/enable_srv_raw "enable_request: true"

# 左臂失能
rosservice call /left_arm/enable_srv_raw "enable_request: false"

# 右臂使能
rosservice call /right_arm/enable_srv_raw "enable_request: true"

# 右臂失能
rosservice call /right_arm/enable_srv_raw "enable_request: false"
```

厂商使能／失能服务同时发送夹爪指令。`enable_response: true` 表示服务判定请求成功，
仍应结合实际反馈确认状态。

夹爪遥操作模式（`enable_gripper_teleop:=true`）会改用
`src/pi05_control/scripts/safe_gripper_piper_driver.py`，它的使能回调先读取当前夹爪
开度并保持该位置，不发送闭合目标；失能时才发送松开指令。该驱动**要求
`auto_enable:=false`**，否则节点直接报错退出，而它的 `required="true"` 会连带关闭整
个 launch。因此不要用 `start_*.sh` 的默认 `auto_enable` 搭配这个模式。

## software stop 与恢复

```bash
# 左臂停止
rosservice call /left_arm/stop_srv_raw "{}"

# 左臂解除 software stop
rosservice call /left_arm/reset_srv_raw "{}"

# 右臂停止
rosservice call /right_arm/stop_srv_raw "{}"

# 右臂解除 software stop
rosservice call /right_arm/reset_srv_raw "{}"
```

`reset_srv_raw` 发送恢复指令，不是归零，也不自动使能。
硬件急停仍按下时需先在现场释放；software stop 不能替代硬件急停。

## 返回左右臂支撑初始姿态

用户于 2026-09-16 根据 Piper UI 截图确认，左右臂共同使用以下初始姿态：

| 关节 | 初始坐标（rad） |
|---|---:|
| J1 | 0.000 |
| J2 | 0.000 |
| J3 | 0.000 |
| J4 | 0.000 |
| J5 | +0.567 |
| J6 | 0.000 |

配置保存在 [arm-home.yaml](../config/arm-home.yaml)。这是机械臂未使能时由机械结构
支撑的姿态，不是六关节零位，也不是末端笛卡尔原点；夹爪位置未指定。
用户现场观察到：使能后若发送全零关节目标，机械臂会先回到全零；之后失能时，
机械结构会从全零姿态向上述支撑姿态产生小幅下沉。因此，完成目标移动后需要返回时，
左右臂均先返回上述姿态，确认到位并静止后再失能。

统一返回脚本默认只显示计划，不发送目标：

```bash
scripts/publish_arm_home.py left
scripts/publish_arm_home.py right
```

对应机械臂已使能、software stop 已解除、没有其他命令源，且返回路径可用时，发送一次
5% 速度目标：

```bash
# 左臂返回支撑初始姿态
scripts/publish_arm_home.py left --apply

# 右臂返回支撑初始姿态
scripts/publish_arm_home.py right --apply
```

脚本只发布一次六关节目标，不使能、不解除 stop、不失能、不控制夹爪，也不自动判断到位。
发送后持续查看对应关节反馈；确认已到位且静止，再执行失能命令。

等价的左臂原始命令为：

```bash
rostopic pub -1 /left_arm/joint_ctrl_raw sensor_msgs/JointState \
  "{name: [joint1, joint2, joint3, joint4, joint5, joint6], position: [0.0, 0.0, 0.0, 0.0, 0.567, 0.0], velocity: [0, 0, 0, 0, 0, 0, 5]}"
```

右臂只需把话题改为 `/right_arm/joint_ctrl_raw`。
`speed_percent: 5` 是当前返回速度设置；截图确认的是六关节坐标。

## 完整平滑摇操并在结束后自动返回

以下单条命令会启动对应机械臂的平滑摇操节点，以 `auto_enable:=false` 启动驱动，
完成运行时话题拓扑检查后按 `reset → enable` 顺序解除 software stop 并使能。
摇操期间按一次 **Enter**，程序会依次关闭摇操、
等待平滑器停止发布、以 5% 速度返回上述支撑初始姿态、连续确认 1 秒六轴最大误差
不超过 0.02 rad、失能机械臂，最后关闭本次启动的节点：

```bash
# 右臂：按 Enter 结束
scripts/run_smoothed_teleop.sh right --apply

# 左臂：按 Enter 结束
scripts/run_smoothed_teleop.sh left --apply
```

也可以设定摇操时长，时间结束后自动执行同一回位和失能流程：

```bash
# 右臂摇操 20 秒
scripts/run_smoothed_teleop.sh right --apply --duration 20
```

同时控制 Pika 夹爪与 Piper 夹爪时显式增加 `--with-gripper`：

```bash
# 右臂，20 秒后自动回支撑初始姿态并失能
scripts/run_smoothed_teleop.sh right --apply --with-gripper --duration 20

# 左臂；需要 /dev/pi05-pika-left 已按 config/pi05.env 正确绑定
scripts/run_smoothed_teleop.sh left --apply --with-gripper --duration 20
```

左侧首次运行前安装并核对稳定串口别名（会提示输入 `sudo` 密码）：

```bash
scripts/configure_pika_serial.sh apply left
scripts/configure_pika_serial.sh check left
scripts/check_pika_stream.sh --duration 3 left

# 只检查左侧完整拓扑，不使能机械臂
scripts/run_smoothed_teleop.sh left --apply --with-gripper --startup-only
```

位姿映射继续使用现场已确认的 `mapping_order=swapped`：物理左手柄虽然来自历史变量
`pika_R_code`，但对外必须发布到 `/pi05/pika_input/left/pose`。夹爪编码器不经过该变量
映射，物理左夹爪固定使用 `/dev/pi05-pika-left`。

会话在使能前要求对应侧 `localization_status.accurate` 连续为真至少 `0.5 s`。若 Pika
只有夹爪编码器数据、六自由度定位失效，会直接拒绝使能并提示检查追踪器/接收器，避免
再次出现“夹爪能动但机械臂没有位姿目标”的状态。

夹爪模式只读取 Pika 串口，不向 Pika 写入控制数据。左右 Pika 全行程均线性映射到
Piper `0–0.10 m`；右侧控制器查询结果为 `max_range_config: 100`，左侧行程由现场确认
与右侧一致。限幅后直接跟随，不再另加速度限制。串口目标超过 `0.25 s`
未更新时，平滑器停止向 Piper 发布整组目标。该功能仅通过上述平滑会话入口启用。

默认允许最多 180 秒返回支撑初始姿态；若回位误差连续 5 秒没有改善，会自动按
`reset → enable` 恢复运动，最多尝试 5 次。若反馈中断、话题拓扑不正确或超时未到位，
脚本不会把“已回位”当作成功；可能仍使能时会保留驱动节点并显示其 PID 和日志位置，
供现场检查。正常结束应看到 `Home confirmed`、`arm disabled` 和 `Completed`。

该入口的其它选项：

| 选项 | 默认值 | 作用 |
|---|---|---|
| `--duration 秒` | 交互等待 Enter | 定时结束摇操并进入回位流程 |
| `--home-timeout 秒` | `180` | 回位等待上限，超时视为未到位 |
| `--home-tolerance rad` | `0.02` | 六轴最大误差的到位判据 |
| `--stable-seconds 秒` | `1.0` | 达到判据后需保持的时间 |
| `--startup-only` | 关闭 | 只做启动与拓扑检查：不使能、不发运动命令，检查完直接退出 |

`--startup-only` 适合在不动机器的情况下验证驱动、FK、IK、平滑器、遥操作节点和
`--with-gripper` 的串口身份是否就绪。

## 厂商归零服务

厂商服务发送六关节全零目标，并固定使用 **50% 速度**。它不会返回上面记录的
J5=+0.567 rad 支撑初始姿态，因此不能用于失能前的常规返回。

```bash
# 左臂厂商归零：位置速度模式，50% 速度
rosservice call /left_arm/go_zero_srv_raw "is_mit_mode: false"

# 右臂厂商归零：这不是右臂支撑初始姿态
rosservice call /right_arm/go_zero_srv_raw "is_mit_mode: false"
```

响应 `status: true` 只说明服务发出了指令，不表示已到位。
服务没有先按驱动使能标志拒绝未使能请求，调用者应先确认使能状态。

## 一次左 J1 微动（5% 速度）

先使能并解除 software stop。以下脚本只给 J1 增加 0.001 rad，其余关节沿用当前反馈；
只发送一次目标，不自动回程，也不发送夹爪目标。

```bash
python - <<'PY'
import time
import rospy
from sensor_msgs.msg import JointState

rospy.init_node("left_j1_micro_target", anonymous=True)
publisher = rospy.Publisher(
    "/left_arm/joint_ctrl_raw", JointState, queue_size=1
)
deadline = time.monotonic() + 5
while publisher.get_num_connections() == 0:
    if rospy.is_shutdown() or time.monotonic() > deadline:
        raise SystemExit("未连接到驱动")
    rospy.sleep(0.05)

# 在发布连接建立后读取反馈，减少等待造成的基准过期。
feedback = rospy.wait_for_message(
    "/left_arm/joint_states_driver_raw", JointState, timeout=5
)
if len(feedback.position) < 6:
    raise SystemExit("六轴反馈不完整")

target = JointState()
target.header.stamp = rospy.Time.now()
target.name = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]
target.position = list(feedback.position[:6])
target.position[0] += 0.001
# 当前厂商驱动将 velocity[6] 解释为速度百分比。
target.velocity = [0, 0, 0, 0, 0, 0, 5]
publisher.publish(target)
rospy.sleep(0.5)
PY
```

若启动驱动时使用 `publish_business_feedback:=true`，左反馈改用
`/joint_states_single_l`。右臂对应控制话题为 `/right_arm/joint_ctrl_raw`，
默认驱动反馈为 `/right_arm/joint_states_driver_raw`，业务反馈为 `/joint_states_single_r`。

`position[0:6]` 顺序是 J1–J6，单位 rad；若提供第七个位置，则它是夹爪开口，单位 m。
当前驱动中，七元素 `velocity` 的最后一个值是速度百分比；留空或全部为零会使用
50% 速度。该约定属于厂商驱动，不是标准 JointState 的速度语义。

## 查看反馈

```bash
rostopic echo -n 1 /left_arm/joint_states_driver_raw
rostopic echo -n 1 /left_arm/arm_status

rostopic echo -n 1 /right_arm/joint_states_driver_raw
rostopic echo -n 1 /right_arm/arm_status
```
