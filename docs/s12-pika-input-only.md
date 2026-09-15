# S12 Pika 定位输入-only 整理

## 目标与状态

为左右 Pika 定位提供隔离的观察入口，不连接 Piper，不运行遥操作、运动学、控制过滤或
夹爪控制节点。新包 `pi05_pika_input` 状态为 **等待真机验收**，验证等级为构建及仿真/回放。
右侧跟踪器尚在充电；双侧活动与新 launch 真机验收未执行。

本轮所有改动为新增文件。`docs/status.md`、既有 S12 阶段报告、根 README 与其他进入本轮前
已修改路径保持原样，避免混入已有成果；本补充记录不改变 S12 的安全阻塞状态，不发布 PR。

## 完成内容与接口

- `pika_input_only.launch` 默认仅创建左侧观察转发节点，默认不启动 locator。
- `pika_input_side.launch side:=left|right` 将每侧原始 pose/status 转发到对应侧观察接口。
- 左原始入口：`/pi05/pika_input/raw/left/pose` 与 `.../localization_status`；右侧同构。
- 左观察输出：`/pi05/pika_input/left/pose` 与 `.../localization_status`；右侧同构。
- locator 的 TF 隔离到 `/pi05/pika_input/raw/tf` 与 `.../tf_static`，不占用全局 `/tf`。
- 不提供 gripper/ctrl、joint command、teleop trigger、arm status 或运动服务接口。
- pose 和 localization status 原样转发；缓存 pose 不表示有效输入，必须独立检查状态、
  时间戳与活动。该包不是控制授权或超时安全门禁，不得连接机械臂命令入口。

上游 `sensor_tools/serial_gripper_imu` 启动时会发送力控、灯光等串口命令，并有夹爪控制
订阅者，故未纳入本包；其右侧状态串线通过“不启动该节点”避免，不宣称修复了上游源码。
串口完整性继续用项目既有 `check_pika_stream.sh` 被动检查。

## 启动与停机

先关闭其他 locator，避免两个 libsurvive 实例争用接收器。当前旧 RViz 查看会话不属于新包，
不能与新 locator 同时运行。依赖现有 ROS Noetic、data_msgs、参考区本机 locator 二进制：

```bash
source /opt/ros/noetic/setup.bash
source /home/mips/pika_ros/install/setup.bash --extend
source /home/mips/robot/pi05-upstream-ws/devel/setup.bash --extend
source /home/mips/robot/robot-pika-piper-pi05/devel/setup.bash --extend
source /home/mips/robot/robot-pika-piper-pi05/.venv/bin/activate
roslaunch pi05_pika_input pika_input_only.launch \
  start_locator:=true mapping_order:=swapped left:=true right:=false
```

`swapped` 表示将既有 `pika_R_code` 用作物理左侧、`pika_L_code` 用作物理右侧。
这是公开的选择标志，不保存或展示映射值，不修改已有环境文件。
`unverified`（默认）、缺失或重复映射值会拒绝启动；`direct` 只能在另一次现场核对后使用。
右侧启用需明确 `right:=true`，不等于右侧已验收。

私有映射只从进程继承的环境读取并暂存 ROS 参数服务器；不进入 launch 参数摘要、子进程
argv 或文件。子 locator stdout/stderr 和本地 ROS 日志均送入 `/dev/null`，rosout 被隔离。
禁止 `rosparam dump`、`roslaunch --dump-params`、查询并粘贴私有参数，禁止录制原始日志、bag
或截图包含设备标识的参数面板。ROS 参数服务器不是保密存储，其他本机进程仍可能读到参数。

Ctrl-C 停止 launch；监督节点中断子 locator、等待退出并清除其私有参数。
子进程异常退出会使 required 节点终止该 launch。强杀监督进程可能跳过清理，恢复前需停止
遗留 locator 与清除私有参数，必要时关闭此测试 ROS Master；不得导出参数作诊断。
RViz 不自动启动；若单独查看，应选择本包观察 pose 话题或显式选择隔离 TF 话题。
启动检查还会拒绝图中名称含 piper/teleop 的节点，但这不是完整的机器安全审计：被改名的
驱动或直接 CAN 程序可能绕过名称检查。仍需操作员确认机械臂驱动和控制进程全部关闭。

## 验证记录

2026-09-15：

- `bash tests/test_pika_input_only.sh`：映射选择、缺失/重复/未核对映射拒绝、监督进程 argv
  无映射值、日志抑制、私有参数清理、已有 locator/已知驱动拒绝与 launch 静态白名单通过。
- `catkin_make`（叠加指定 Noetic/upstream/项目环境）：返回 0，新包构建通过。
- 在独立 `localhost:11331` ROS Master 中运行
  `ROS_MASTER_URI=http://localhost:11331 ROS_HOSTNAME=localhost /usr/bin/python3 tests/replay_pika_input_only.py`：
  返回 0，合成左右 pose、true/false 状态各侧不串线，ROS 图未出现转发节点的控制入口。
- 完整 `tests/test_*.sh`：首次因新包错误声明外部 data_msgs 构建依赖失败；改为运行时依赖后，
  全部重跑返回 0。`git diff --check`：返回 0。
- `catkin_make run_tests_pi05_control && catkin_test_results build/test_results`：返回 0，
  79 tests、0 errors、0 failures、0 skipped（既有控制包回归，不包括本包独立回放）。

## 真机证据与限制

新包尚未做真机启动验收。此前使用本机旧双 locator、运行时交换左右参数，对物理左 Pika
单独观测 15 秒：1804 条 pose、119.9 Hz、2617/2617 状态有效、motion=detected，返回 0。
用户通过 RViz 确认物理左侧与旧右侧映射相对应，并确认随动正常。
这些是旧启动方式的输入证据，不是新 launch 或 Piper 运动验收；右侧映射待独立运动核对。
此前回调诊断中的 new_object 是区间创建事件计数，不能当作存量跟踪对象总数。

左 Piper J2/J3 实际异常未闭环。不得放宽阈值、自动 disable、添加未经验证补偿或把 Pika
输入通过解释成遥操作放行；机械臂异常使用硬件急停。

## 回滚方式

停止新 launch 后恢复此前只读查看方式。新增包不修改环境映射或 Piper 配置；不要 reset、
stash 或 checkout 既有 S12 改动。新包的停止不负责关闭其他会话启动的 RViz/ROS Master。

## 来源与许可证

新包和测试为项目原创实现，MIT；未复制上游 C++ 或分发预编译 locator。
仅观察参考区 `sensor_tools/src/serial_gripper_imu.cpp` 与 launch 接口，未将其 TODO 许可源码
纳入仓库。`pika_locator` 的来源与许可证据仍不完整，只调用已存在的本机二进制，不将它
恢复为批准依赖，也不宣称可重复构建或发布。后续须补齐来源或实现批准的自有定位适配。
