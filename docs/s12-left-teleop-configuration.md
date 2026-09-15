# S12 左臂独立遥操作配置

状态：等待真机验收。右侧 Pika 电量不足，本配置只使用左側输入及左臂驱动。
现场报告：底座正立、原装夹爪；用户确认支撑干涉已排除、左臂静止、急停可操作。
这些事实不证明此前 J3/J5 非目标响应根因已闭环。

## 配置

`pi05_left_teleop/left_teleop.launch` 默认关闭，连接驱动另需显式 `connect_driver:=true`。
`scripts/start_left_teleop.sh` 设置本机已核对的环境及官方模型，检查左 CAN 后启动左臂。
不启动右臂、定位程序、串口夹爪输入或 RViz。现有 input-only 程序需继续运行。
驱动初始化会发送查询及控制模式帧；此入口不是只读诊断。

FK/IK/相对遥操复用经 SHA256 检查的上游源码与官方 URDF，数值求解不修改，禁用上游强制 Meshcat 可视化。
工具偏移暂沿用上游 0.19 m，可用 `tool_offset_m:=...` 显式调整；没有完成真实测量或标定。
反馈与命令分离。PI05 过滤器限制速度 5%、每次关节步长 0.002 rad。
额外监督器仅在明确使能并通过两秒静置检查后提供授权心跳。
使能过渡关节变化超过 0.002 rad 即故障；遥操目标相对使能前基准限制 0.02 rad，目标与反馈差限制 0.01 rad。
反馈相对基准超过 0.025 rad、定位/反馈/IK 超时或过滤器故障会撤权并请求软件停止，故障不自动恢复。
这些限制不是对真实轨迹安全或机械根因的认证。

## 操作顺序

配置完成不代表已启动真机遥操。启动后保持 Pika 静置，先打开预览会话让 IK 产生状态；此时没有授权，不输出驱动目标。

```bash
cd ~/robot/robot-pika-piper-pi05
scripts/start_left_teleop.sh
```

其它终端需先加载 Noetic、上游及项目 devel。预览、使能、停止入口分别为：

```bash
rosservice call /teleop_trigger_l '{}'
rosservice call /left_arm/teleop/status '{}'
rosservice call /left_arm/teleop/enable '{}'
rosservice call /left_arm/teleop/stop '{}'
```

预览触发是切换服务，不重复调用以确认。使能前及两秒静置期间保持 Pika 不动；使能成功后原预览会话开始获得运动授权。
上游预览服务返回默认的 `success: False`，它未填写确认字段；应观察实际会话/IK 输入以及只读 status，而不是凭返回值再次切换。
status 应显示 `phase=DISARMED`、`blockers=[]`、`enable_attempted=false`，再进行使能。
新版拒绝消息逐项列出缺失/过期输入或锁存状态原因。旧运行进程不会自动加载修改，需先关闭原遥操 launch 再重启；不要同时启动第二套。
本轮没有 Pika 夹爪输入，转发目标保持使能前反馈的夹爪开度。
但锁定上游驱动的使能服务本身调用 `GripperCtrl(0,1000,0x01,0)`，使能可能闭合夹爪；保持夹爪周围无接触物，不能把本配置描述为全程锁定夹爪。
软件停止不等于失能。故障后不自动重试、复位或失能；异常运动使用硬件急停，支撑后另走已审查的失能流程。
未执行上述真机启动/预览/使能操作。

## 来源与发布

数值来源：本机 `pika_remote_piper`，五项 SHA256 基线由既有 `pi05_teleop_replay` 提供；不复制外部源码。
驱动来源：既有 S09 锁定的官方 piper_ros 节点。
新增启动配置、监督器与门禁测试为项目 BSD-3-Clause 代码。
已有 S12 文件大量未提交改动且安全问题未闭环，本次保留为本地配置，不提交、推送或创建 PR。

## 验证记录

- `/usr/bin/python3 -m unittest discover -s tests -p test_left_teleop_gate.py`：15 项通过，包含初始不完整反馈等待、使能后无效反馈锁存、具体拒绝原因。
- `catkin_make`：构建通过。
- `roslaunch --nodes pi05_left_teleop left_teleop.launch start:=true connect_driver:=true`：解析通过，只有左侧六个节点；`--nodes` 不启动节点。
- `roslaunch --args /left_arm/teleop/fk ... start:=true connect_driver:=false`：确认数值组件所需 remap 在实际 argv 中存在。
- 在加载 Noetic、锁定上游、项目 devel 和 .venv 后执行 `ROS_MASTER_URI=http://localhost:11334 python tests/replay_left_teleop_supervisor.py`：PASS；只启动独立 Master 与监督器，用合成反馈及假使能/停止服务验证未授权拒绝、静置阶段拒绝、5% 速度/夹爪目标处理、定位失效停止及故障锁存。关闭独立 Master 与监督器。
- 回放首次失败于 catkin devel relay 对辅助模块的导入；修正 source 路径并把辅助模块按文件安装后重新运行通过。首次失败不记作通过。
- 真机遥操启动、使能及运动：未执行。此前已有数值链路回放不能代替本次完整真机链路验收。

## 用户启动后的诊断补充

用户已自行启动真机驱动并调用预览/使能。两次使能均在前置门禁拒绝，错误消息本身不能追溯旧监督器的 phase/reason。
只读观察确认反馈为七项有限数值、Pika 定位有效。最初没有预览/IK 消息，确认过滤器 DISABLED 后重新打开预览，恢复到 IK clear；再次拒绝时三项输入在观察窗口内仍正常。
因此不把“没有预览”当作最终根因。新增只读 `/left_arm/teleop/status` 并细化拒绝信息。
代码检查还发现使能前不完整反馈被无条件锁存；改为 DISARMED 时等待有效反馈，使能开始后的无效反馈仍锁存。
这项缺陷是否就是旧进程本次拒绝的来源尚未证实，需重启新版后读状态确认。助手未重试使能或输出运动目标。
