# S12 Pika 间歇定位失效专项诊断

## 目标

定位双 Pika 运动时出现的 inaccurate 样本原因，避免重复验收但缺少失效时序证据。
当前状态：**等待真机验收**，运动期间问题未解决，S12 安全阻塞不变。
用户授权直接排查并修复输入链路软件问题，不授权放宽验收标准或启动 Piper 遥操作。

## 完成内容

新增 `scripts/diagnose_pika_tracking.py` 与 `tests/test_pika_tracking_diagnostic.sh`。
start preflight 返回 0，HEAD 为 `3c17a3219091df63e0845aef00e4feef058a8934`，继续原 S12 分支。
fetch 后 origin/main 一致，GitHub 查询没有开放 stage PR。所有进入本轮前的脏路径保持原样，
本记录为独立新增文件，不覆写此前验收记录、状态表、README 或输入-only 包。

## 接口与兼容性

诊断器只订阅新 input-only 命名空间下的 raw/relay pose/status，输出聚合 JSON。
不创建 Publisher、控制服务、串口或 CAN 写入，不导出 pose、frame、设备标识或原始日志。
缓存的数值和消息签名只留在内存，匹配缓冲上限为每层 5000 条。
未改变原有 30 Hz、状态至少 5 条且全部有效、0.02 m 或 0.10 rad 活动阈值。

- inaccurate_samples / invalid_runs：无效样本数及连续无效区间数。
- longest_invalid_run_ms / invalid_duration_observed_ms：从首个无效状态接收到后续有效状态
  接收时刻的观察间隔；窗口末仍无效时以窗口结束截断。
- first_run_left_censored / last_run_right_censored：区间是否在窗口开始前已失效或结束时未恢复。
- max_status_gap_ms / max_pose_gap_ms：接收间隔，包含窗口末无数据的尾部。
- max_published_pose_age_ms：发布的 PoseStamped 时间戳年龄，不证明底层跟踪已经更新；
  locator 可用新时间戳发布缓存 pose。
- bad_samples_with_recent_pose_change：无效状态之前 0.2 秒内是否发生任何数值变化，包含
  定位抖动，不等于人为运动，也不能直接证明遮挡或运动导致失效。
- identical_pose_pairs / different_pose_pairs：相同时间戳的两层消息内容一致/不一致计数。
- unpaired_boundary_or_missing：边界差异或潜在缺失，不能单独当作丢包证据。
- max_pair_arrival_difference_ms：两层配对消息接收时间差绝对值，不是设备定位延迟。

无效观察间隔不是精确光学断流时长；状态消息之间可能无观测，必须结合接收间隔和
边界标志解释。工具不识别具体遮挡动作，不修改 libsurvive 配置或内部判定逻辑。

## 验证记录

```bash
bash tests/test_pika_tracking_diagnostic.sh
```

返回 0；覆盖连续无效区间、恢复、窗口截断、合法/非法时长、消息配对差异及内存上限。
静态检查拒绝诊断器出现 ROS 控制发布、服务、参数设置或设备写入 API。
全部 `tests/test_*.sh` 返回 0，`git diff --check` 返回 0。

运行时叠加 Noetic、参考 install、锁定上游 devel、项目 devel；先启动已核对交换映射的
input-only（Piper 全部关闭），再执行：

```bash
/usr/bin/python3 scripts/diagnose_pika_tracking.py --duration 5 --phase static
/usr/bin/python3 scripts/diagnose_pika_tracking.py --duration 30 --phase static
```

5 秒启动观察返回 1：两侧各 1 条无效状态，左有效 484/485，右有效 529/530。
左首个无效到恢复观察间隔 873.4 ms，右 953.66 ms；均首区间左截断。
左 603、右 600 条 pose 配对内容一致，0 条不同，最大到达差 1.14/1.11 ms。
两侧此窗口检测到活动，不能当作静置通过；未跳过或抹除这些失败样本。
启动后的 30.01 秒独立静置窗口返回 0：左原始 3768/3768、转发 3766/3766 状态有效；
右原始 4001/4001、转发 4000/4000 有效，四路均 0 无效区间、motion=not-detected。
左 3598、右 3596 对 pose 内容一致，0 对不同；最大配对到达差 4.64/4.28 ms。
两侧原始 pose 最大接收间隔约 9.53 ms，原始状态最大间隔左 36.1、右 18.3 ms。
边界上未配对消息每侧 1 条，没有据此断言丢包。仅证明该窗口静置稳定，不代表运动问题已修复。
诊断后保留仅 input-only 与 ROS Master 等待同步运动操作，未启动 Piper 或 RViz。

需要运动时，仅在操作员已拿好两只 Pika、基站无遮挡后开始同步窗口：

```bash
/usr/bin/python3 scripts/diagnose_pika_tracking.py --duration 30 --phase motion
```

返回 0 要求两侧两层全部状态有效、pose 检查通过且活动 detected，匹配得到一致消息。
返回 1 表示观察条件/有效性/一致性失败；返回 3 表示环境或订阅失败；CLI 参数错误返回 2。
它是诊断，不替代左右单侧身份核对和运动安全验收。

## 真机证据

2026-09-15，Ubuntu 20.04、ROS Noetic、双 Pika，未启动 Piper/遥操作。
此前新 input-only 分侧右活动：1928/1928 状态有效、右 detected、左 not-detected、返回 0。
分侧左活动：2149/2149 状态有效、左 detected、右 not-detected、返回 0。
双侧活动窗口失败：左 1858/2029、右 1649/1650 有效；另一次左 1850/1858、右 1925/1928。
两次双侧均检测到活动，但不得记为双侧输入验收通过。
后一次失败后的原始静置检查为左 621/621、右 624/624 全部有效。

## 风险与限制

已知左右映射错误通过显式 swapped 运行选择纠正；没有永久写入设备标识。
转发不是当前已观察到的失效来源；运动间歇无效原因仍待时序与现场动作关联。
本机 pika_locator 只有预编译产物，无法声称修复其内部逻辑。不得擅自放宽 dist/angle/velocity
判定，或通过过滤 false 样本伪造通过。校准、配对和基站位置调整会改变设备/配置状态，
必须说明具体现场步骤、保护既有配置，不自动启动 force-calibrate 或升级定位依赖。
左 Piper J2/J3 安全异常未闭环，禁止连接遥操作。按 pi05-stage-sync 安全与归属门禁不发布。

## 回滚方式

停止诊断器不会改变输入映射或设备配置；Ctrl-C 停止 input-only 清理其子进程与私有映射。
若保留 input-only 等待下一动作，仍仅为观察链路，不产生机械臂命令。
新增工具不要求覆盖此前脏路径，不执行 reset、stash、checkout 或删除用户数据。

## 来源与许可证

诊断器与测试为项目原创，MIT；复用项目既有定位检查器统计与验收定义，未复制或
分发预编译 locator。其不可重复构建和许可缺口不因本诊断消失。
