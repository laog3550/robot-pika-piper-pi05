# 双臂连续数据采集

本入口一次启动后可连续录制多条双臂 episode。成功轨迹不是在操作任务结束时停止，
而是包含随后由程序执行的完整自动回位：

```text
人工任务操作 -> S 提前完成或到达时长 -> 自动返回支撑初始姿态（继续录制）
             -> 双臂稳定到位 -> 关闭 episode -> 保持使能，等待下一条
```

任务文本只描述操作任务，不写“回到初始位置”。训练数据中所有成功示范都以返回支撑姿态
结束，使回位成为任务结束后的固定行为。

## 固定映射

程序读取并严格校验 `config/data-collection-mapping.yaml`。机器相关相机序列号和物理端口
仍只存放在 Git 忽略的 `config/cameras.env`，不会写入训练特征或提交到仓库。

| 角色 | 输入/反馈 | 输出字段或控制话题 |
|---|---|---|
| 左腕 RGB | 本机配置中的左腕序列号，MJPG | `observation.images.left_wrist` |
| 右腕 RGB | 本机配置中的右腕序列号，MJPG | `observation.images.right_wrist` |
| 顶部 RGB | 本机配置中的顶部序列号，YUYV | `observation.images.top` |
| 左臂状态 | `/joint_states_single_l` | `observation.state[0:7]` |
| 右臂状态 | `/joint_states_single_r` | `observation.state[7:14]` |
| 左臂目标 | `/left_arm/joint_ctrl_raw` | `action[0:7]` |
| 右臂目标 | `/right_arm/joint_ctrl_raw` | `action[7:14]` |

每侧七维顺序固定为 `J1, J2, J3, J4, J5, J6, gripper`，因此完整 14 维顺序为
`左 J1–J6、左夹爪、右 J1–J6、右夹爪`。右腕彩色接口离线时保持映射到右腕角色并报错，
不会使用其它在线相机自动替代。

## 前提

- 双侧 Pika input-only、定位和映射已经启动并通过检查。
- `config/cameras.env` 已记录左腕、右腕和顶部相机身份。
- 两路 Pika 夹爪稳定别名已经配置；正式数据固定包含双臂各六轴和夹爪，共 14 维。
- 三个彩色 UVC 接口没有被 Orbbec SDK、RealSense ROS 节点或其它程序占用。
- 已运行 `scripts/build_catkin.sh`，并有图形桌面可显示 Tk 操作台。

腕部只使用 Dabai DC1 的 MJPG 彩色接口，顶部 D455 使用 YUYV 彩色接口。程序按机器配置
中的序列号解析 `/dev/video*`，不会使用易变化的数字节点作为角色配置，也不启动深度流。

## 启动

先做无动作预检。此命令会打开完整操作台并持续显示三路画面、双臂 J2/J3、Pika
定位和设备状态，但“开始采集”按钮保持禁用，直到按 `Q` 退出：

```bash
scripts/run_data_collection.sh \
  --dataset-name apple-demo \
  --task "Pick up the apple and put it into the basket." \
  --duration 30 --startup-only --apply
```

通过后去掉 `--startup-only`。程序会保持运行，不需要每条 episode 重启命令：

```bash
scripts/run_data_collection.sh \
  --dataset-name apple-demo \
  --task "Pick up the apple and put it into the basket." \
  --duration 30 --apply
```

固定数据规格为三路 `640x480@30 FPS` RGB。顶部画面默认顺时针旋转 90°并重新整理为
固定尺寸；若现场安装方向不同，使用 `--top-rotation none|cw|ccw|180`。
采集器打开两台 Dabai 时会关闭 `exposure_dynamic_framerate`，并使用两个 V4L2 缓冲区；
这是本机维持约 30 FPS 实测解码速率所必需的设置。界面刷新独立限制为 20 FPS，不会让
预览重绘抢占 30 FPS 采集线程。

任务描述和操作时长都可直接在窗口顶部修改，不需要返回终端重输命令。设备预检未通过时，
窗口仍然保持打开并在对应画面上显示原因，“开始采集”自动禁用。例如右腕 UVC 被 Orbbec
SDK 占用时，先退出占用进程或重新插拔相机，再点击“重新检测相机（F5）”。

如果 Dabai 彩色设备仍在线、但 UVC interface 被 SDK 解绑，可恢复已配置的右腕接口：

```bash
scripts/restore_wrist_uvc.sh right --apply
```

脚本会先验证物理 USB 端口、`2bc5:0557` 和本机序列号，发现设备被进程占用或身份不符时
拒绝操作；通过后只把该腕部的两个标准 UVC interface 绑定回 `uvcvideo`。此操作需要在
终端输入 sudo 密码。成功后回到采集窗口按 `F5`。

窗口的“关节姿态 / 肘关节曲线”标签页显示左右臂 J1–J6 和夹爪的当前反馈、action 目标及
误差。左右 J3 肘关节另有最近 10 秒实时曲线：绿色实线是反馈，橙色虚线是控制目标；顶部
红色 `REC` 表示这些状态和画面正在写入当前 episode，空闲时的数值只用于预检。

## 快捷键

| 键 | 行为 |
|---|---|
| `Space` | 预检、双侧 reset/enable、开启遥操作并开始 episode |
| `S` | 提前完成并按成功处理，切入仍被录制的自动回位阶段 |
| `F` | 将本条锁定为失败，但继续采集到设定时长，再自动回位 |
| `D` | 放弃本条，回位成功后删除临时数据 |
| `F5` | 空闲时按配置序列号重新发现并打开三路相机 |
| `E` | 空闲且完成回位后，由操作员手动失能双臂 |
| `Q` | 采集中先放弃并回位；双臂仍使能时要求先按 `E` 才退出 |
| `X` | 双侧 software stop，不自动回位；现场检查前保持节点运行 |

回位期间普通结束键无效，只有 `X` 可以中断。默认由 `--duration` 结束人工任务阶段：未按
`F` 的 episode 自动判为成功，按过 `F` 的 episode 保持失败标记；两者都在相同时限开始
自动回位。`F` 不会立即缩短采集时长，失败标记也不能被后续 `S` 或定时结束改回成功。
两臂均需在 `[0, 0, 0, 0, 0.567, 0] rad` 附近保持至少
1 秒，episode 才会关闭。回位完成后双臂保持使能，下一条 episode 不重复 reset/enable，
只重新打开平滑器和遥操作触发器。只有操作员在空闲状态按 `E` 才会失能。为避免关闭程序
后遗留无法管理的使能机械臂，`Q` 不会绕过该手动失能确认。

## 输出

默认目录是 `/home/mips/datasets/pi05/<dataset-name>/`：

- `raw/success/<episode>/raw.bag`：原始 ROS 消息及三路 JPEG 压缩图像；
- 同目录的三路 AVI 与 `frames.jsonl`：可恢复的 30 FPS 转换中间格式；
- `raw/failure/`：失败、异常或紧急停止记录，默认不进训练集；
- `lerobot/`：LeRobot 0.4.2、Dataset v3.0 的 Parquet、MP4 和任务元数据；
- `conversion.json`：每条后台转换结果。

LeRobot 字段为三路 `observation.images.*`、14 维 `observation.state`、14 维 `action`
和原始任务文本。`frames.jsonl` 额外保存 `manipulation`、`return_home` 阶段用于诊断，
阶段字段不进入训练特征。转换失败不会删除 bag，可重新运行：

成功和失败物理分目录保存：正常到时且完整回位的轨迹进入 `raw/success/` 并排队转换到
`lerobot/`；人工按 `F`、数据异常或回位失败的轨迹进入 `raw/failure/`，不会混入训练集。

```bash
/home/mips/miniconda3/envs/lerobot/bin/python \
  scripts/export_lerobot_episode.py \
  --episode /home/mips/datasets/pi05/apple-demo/raw/success/<episode> \
  --dataset-root /home/mips/datasets/pi05/apple-demo/lerobot \
  --repo-id local/apple-demo
```

## 故障规则

- 启动前会检查两路 `/dev/pi05-pika-*` 是否被旧会话锁定。发现占用时在启动任何新驱动前
  退出并打印占用 PID；必须先在 Piper 控制界面确认双臂已手动失能，再停止旧会话。不要在
  使能状态下直接杀死残留驱动进程。
- 回位超时、反馈丢失或恢复次数耗尽时，episode 只能进入失败归档，程序锁定后续采集，
  驱动保持运行供现场检查。
- 某路相机没有 `/dev/video*` 节点时，程序不会在界面出现前退出；该画面显示故障，修复后
  可按 `F5` 原地重试。三路画面及实际帧率全部合格前不能开始 episode。
- 相机或写盘异常会把本条降级为失败；只要双臂反馈仍健康，安全回位仍会继续。
- `X`、采集中 Ctrl-C 或未处理异常走 software stop，不会盲目解除停止并回位。
- 启动脚本退出码 `4` 表示机械臂可能仍使能或处于 software stop，故意不关闭遥操作节点。
