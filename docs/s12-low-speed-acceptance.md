# S12 分侧低速验收操作约束

本流程因 2026-09-13 左臂 J2 下砸事件暂未批准再次真机执行。只有完成机械检查、现场双人
复核并解除 S12 阻塞后，才能使用下述 `--apply` 命令。当前只允许不连接硬件的单元测试和
不发送命令的 dry-run。

2026-09-14 确认左右固件均为 `S-V1.8-2`。厂商当前资料清单将该版本分配到
`piper_sdk + piper_ros/noetic` 旧栈路线，因此不要求升级固件；但版本路线匹配不能解除本次
真机异常造成的 S12 阻塞。

`move --apply` 还会读取 Git 忽略的 `config/s12-acceptance.env` 并逐项校验事件复核、目标侧
机械检查、防坠支撑、硬件急停、双人值守和重测批准。缺文件、空值或错误值都会在连接 ROS
master 前失败。示例模板不会被当成现场记录，也不得填写姓名或设备标识。

`move --apply` 和 `enable-settle --apply` 同时读取 Git 忽略的 `config/s07-hardware.env`。
对应侧 `PI05_<SIDE>_PIPER_FIRMWARE` 必须是完整版本，且必须位于本项目已审查的旧栈范围
`S-V1.8-0` 至 `S-V1.8-7`。从 `S-V1.8-8` 起不能继续使用该软件路线。

发生非目标关节漂移后，目标侧必须先单独通过 `enable-settle`。该子命令不创建关节命令
发布器，只比较使能前后的稳定反馈并 software stop；现场支撑后仍须用独立子命令 disable。
只有把对应侧 `PI05_S12_<SIDE>_ENABLE_SETTLE` 记录为 `pass`，`move --apply` 门禁才会开放。

## 安全模型

- 一次只启动一侧 Piper 驱动；另一侧必须保持禁用且不得启动驱动。
- 单次只测试一个关节，绝对步长不超过 `0.005 rad`，速度不超过 5%。
- 若需要恢复已锁存的软件停止，恢复之后必须丢弃全部旧反馈，再采集连续稳定的新基准。
- 使能前后分别采集稳定基准；任一关节在使能建立保持力时偏移超过 `0.002 rad`，必须在发送
  关节目标前停止。实际小步长目标只相对于使能后的稳定基准生成。
- 目标关节达到最小反馈位移和返回基准都必须连续 3 个样本成立；普通非目标漂移也必须连续
  3 个样本超过 `0.002 rad` 才形成漂移结论。任一非目标关节单样本超过 `0.010 rad` 仍立即
  停止，避免以过滤瞬态为由掩盖严重异常。
- 运动前由验收进程自身打开接收型 SocketCAN，要求 ROS 驱动基准与原始 CAN 稳定基准的
  最大差值不超过 `0.002 rad`；运动和回程判定使用该原始 CAN 数据源，审计窗口与命令生命周期
  相同。整组外移目标和回程目标也必须由该次原始 CAN 基准生成，不能把较早的 ROS 基准作为
  非目标关节命令，否则允许范围内的采样差会被主动变成非目标关节位移。接收器没有 CAN 发送 API。
- 运动成功或失败后只调用 software stop，保持驱动使能和关节支撑力。
- 运动命令绝不调用 disable。现场人员确认机械支撑已经实际承载机械臂后，使用独立命令
  disable；服务返回成功后才关闭驱动。
- 任何非目标关节移动超过 `0.002 rad`、状态错误、限位、通信故障、反馈超时或返回超时均
  判定失败。若机械臂出现非预期运动，使用独立硬件急停，不依赖 ROS 服务。

## 当前允许执行

```bash
source /opt/ros/noetic/setup.bash
source /home/mips/robot/pi05-upstream-ws/devel/setup.bash
source devel/setup.bash --extend
source .venv/bin/activate

rosrun pi05_control single_arm_low_speed_acceptance.py --help
rosrun pi05_control single_arm_low_speed_acceptance.py move \
  --side left --joint 2
rosrun pi05_control single_arm_low_speed_acceptance.py enable-settle \
  --side left
```

第二条命令仅显示计划；缺少 `--apply` 时不会连接 ROS master、不会使能，也不会发送运动命令。
dry-run 在返回前不加载 `piper_msgs` 等硬件运行依赖，因此即使尚未叠加外置 Piper ROS
工作区，也能独立检查参数和计划；只有 `--apply` 才要求完整运行依赖。

不启动驱动时，可用下列命令被动检查原始 CAN 关节反馈稳定性。它只调用 SocketCAN `recv`，
只输出各关节在窗口内的变化范围，不输出绝对角度或 payload：

```bash
scripts/check_piper_joint_stability.sh --duration 5 left
scripts/check_piper_motor_telemetry.sh --duration 5 left
scripts/query_piper_limits.sh check left
scripts/query_piper_limits.sh check right
```

第二条被动命令只读取 `0x251`–`0x256` 高速反馈，汇总每个电机的样本数、绝对速度峰值和
绝对电流峰值；不输出电机位置或 CAN payload。它可确认诊断数据源是否可用，但禁用状态下
速度为零不能解释运动期间的 J3 漂移。验收工具会在下一次获准运动时同步汇总相同信息。

后两条参数命令的 `check` 只验证接口身份并打印计划，不发送 CAN。实际查询必须保持 ROS
和 Piper 驱动关闭，然后分别显式执行：

```bash
scripts/query_piper_limits.sh apply left --confirm-query-only
scripts/query_piper_limits.sh apply right --confirm-query-only
```

`apply` 只使用固定 SDK 初始化中的查询帧，输出六轴角度上下限、最大速度和最大加速度；不会
使能、运动或修改参数。任一关节响应缺失、速度/加速度非正或上下限颠倒都会返回非零。

2026-09-15 左右参数查询均返回 0，六轴响应完整且两侧一致；紧随其后的左右 5 秒被动 CAN
检查也均返回 0，预期反馈 ID 为 20/20，未观察到控制/配置 ID 或非预期帧。这些结果关闭参数
响应完整性和持续并行命令源两项检查，但不构成新的运动授权。

同日经现场明确确认左臂机械支撑、右臂禁用、双人值守和硬件急停条件后，左臂单独执行一次
`enable-settle --resume-stop`。工具未创建关节目标发布器，最大使能偏移为 J6
`0.000000 rad`，随后 software stop；在支撑持续承载条件下独立 disable 成功，并关闭驱动和
ROS master。事后 3 秒被动 CAN 检查取得 9,120 帧、20/20 反馈 ID，无控制/配置帧或总线错误。
一次性使能批准已清空，左侧使能稳定性结果已在本机记录为 `pass`。现场外观观察仍需操作员
确认后，才能申请独立的低速运动批准。

下次获准进行 J2 小步长测试时，应同时运行 `--exclude-joint 2` 的被动检查作为非目标关节
对照；该检查不替代验收工具的停止逻辑。

## 阻塞解除后的受控流程

以下流程只是待验收操作定义，并非当前执行授权：

1. 按 `docs/s12-piper-compatibility.md` 核对固件与软件路线；当前保持 `S-V1.8-2`，完成固件
   参数、模式和主从角色的只读核验。其他版本需先重新完成路线兼容性审查。
2. 清空工作区，一人操作、一人守硬件急停；确认目标臂得到可承载其全部重量的机械支撑。
3. 完成 `config/s12-acceptance.env.example` 中的现场项目，将其另存为 Git 忽略的
   `config/s12-acceptance.env`；不得在示例文件中伪造或预填通过结果。
4. 仅启动目标侧驱动，确认没有其他控制发布者。工具会再次执行 ROS 图检查。先使用一次性
   `PI05_S12_ENABLE_SETTLE_APPROVED=yes` 执行 `enable-settle`；完成后清空该批准值。
5. `enable-settle` 通过且机械臂已安全禁用后，记录对应侧
   `PI05_S12_<SIDE>_ENABLE_SETTLE=pass`，再单独取得 `PI05_S12_RETEST_APPROVED=yes`。
6. 如上一次结束于 software stop，向 `move` 增加 `--resume-stop`。工具将在恢复后重新采集稳定
   基准，禁止复用恢复前位置。
7. 明确添加 `--apply --confirm-single-arm --confirm-mechanical-support` 后执行一次小步长往返。
8. 工具返回后机械臂仍保持使能。现场确认支撑已经实际承载机械臂，再单独执行：

   ```bash
   rosrun pi05_control single_arm_low_speed_acceptance.py supported-disable \
     --side left --apply --confirm-mechanical-support
   ```

9. 确认 disable 成功且机械臂由支撑承载后，才能关闭该侧驱动。

任何失败都不得通过扩大步长、提高速度、自动 disable 或继续下一个关节来绕过。
