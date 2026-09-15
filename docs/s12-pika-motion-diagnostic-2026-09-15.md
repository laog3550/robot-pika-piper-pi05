# S12 双 Pika 运动诊断与停机回调修复

## 目标

捕获双侧活动时的无效状态区间，区分定位、转发与设备更新问题。
定位运动验收状态仍为 **等待真机验收**；本轮未解决运动间歇失效，不放行 Piper 遥操作。

## 完成内容

用户确认开始运动诊断后执行 30 秒双侧采集；原始与转发层同时观察。
另在停止转发节点时发现 closed-topic 回调竞态，按用户已授权的软件排查/修复范围，
对本会话新增的 `side_input.py` 做最小修复，并新增 `test_pika_shutdown_forwarding.sh`。
没有覆盖原有 S12 控制、配置或文档路径，也未复制设备标识或修改映射环境文件。

修复前直接把 Publisher.publish 作为订阅回调，停机关闭 Publisher 后仍可能收到消息，
导致 `publish() to a closed topic`。现在回调先判断 shutdown，并仅在 shutdown 期间忽略
ROSException；非 shutdown 异常仍抛出。正常 pose/status 内容和 false 状态不被过滤。
这个停机问题与采集中观察到的定位失效不是同一根因。

再次运行技能 start preflight 与 git status：仓库身份、S12 分支正确，起始 HEAD 为
`3c17a3219091df63e0845aef00e4feef058a8934`，origin/main 一致。没有开放 stage PR。
按 pi05-stage-sync 的脏路径、安全和真机门禁，本轮不提交、推送或发布 PR。

## 接口与兼容性

仅观察 `/pi05/pika_input/raw/left|right` 与 `/pi05/pika_input/left|right` 的 pose/status。
映射仍为经过分侧核对的显式 swapped，不展示实际映射值，不启动串口控制、Piper、teleop 或 RViz。
停机修复不改变 ROS 图、侧别、消息类型、队列或验收阈值。

## 验证记录

运行时依照项目已记录的 Noetic、上游 devel、项目 devel 环境执行：

```bash
/usr/bin/python3 scripts/diagnose_pika_tracking.py --duration 30 --phase motion
```

采集 30.03 秒，返回 1：

| 指标 | 左原始 | 右原始 |
|---|---|---|
| pose 数量/速率 | 3602 / 119.9 Hz | 3600 / 119.9 Hz |
| 有效/全部状态 | 3794/3821 | 3912/3912 |
| 无效样本/区间 | 27 / 4 | 0 / 0 |
| 最长无效观察区间 | 136.31 ms | 0 |
| 无效观察区间总和 | 223.69 ms | 0 |
| 最大 pose 接收间隔 | 9.39 ms | 11.15 ms |
| 最大 status 接收间隔 | 29.83 ms | 18.00 ms |
| 活动 | detected | detected |

两侧无窗口截断无效区间。左 3600、右 3597 对 pose 原始/转发内容一致，0 对不同；
最大配对到达差 2.14 / 1.07 ms。转发层同样记录到左 27 条无效状态、4 段区间，右无失效。
左全部 27 条无效状态之前 0.2 秒内存在 pose 数值变化，但包括定位抖动，不能证明遮挡因果。
上述无效区间是状态接收时序上的观察间隔，不是精确光学断流时长。

停止 locator 后单独通过本机 libsurvive 的对象更新接口统计，前 5 秒初始化、后 15 秒测量。
读取标识只在内存中与既有交换映射匹配，原生库输出被抑制，不写日志/文件；不调用 pose
数值 getter、配对、触觉或强制校准 API。禁用校准与配置序列化，未与其他 locator 同时运行。
匹配到左右两侧；左 2458、右 2019 次对象更新，最大观察更新间隔 13.00 / 12.95 ms，
未映射对象更新 0。该接口可能合并事件，计数不是原始光学脉冲数，也不证明光学准确性；
静置更新连续不能排除运动期间无线/光学/解算间断。

```bash
bash tests/test_pika_shutdown_forwarding.sh
bash tests/test_pika_input_only.sh
```

均返回 0；覆盖正常转发、shutdown 先发生、Publisher 关闭竞态和非停机异常仍可见。
独立 localhost:11331 Master 上 `replay_pika_input_only.py` 返回 0，左右内容和状态隔离正常，
未出现控制接口。完整 `tests/test_*.sh` 回归全部返回 0，`git diff --check` 返回 0。

## 真机证据

2026-09-15，Ubuntu 20.04、ROS Noetic、双 Pika。用户按提示配合双侧运动采集。
运动时右定位本窗口全部有效，左定位出现间歇失效。原始状态失效与转发一致，消息传输
没有对应的长间隔，所以不是本窗口转发冻结或 ROS 整体断流。
发现并修复的 closed-topic 问题有实际停机异常记录；修复后的确定性测试和合成回放通过，
不声称已通过所有真机停机时序。没有执行 Piper 运动验收。

## 风险与限制

左侧运动失效具体原因仍未确认：遮挡、光学/解算更新间断、定位参考变化或本机 locator
内部判定都需要进一步区分。下一步在可视条件明确的左侧动作窗口采集，必要时做直接底层
运动更新诊断；不重复无证据的双侧验收，不直接修改未知含义的定位阈值。
本机 locator 缺少可核对源码，不能仅凭二进制字符串声称修复内部逻辑。
J2/J3 机械臂安全异常不受本次输入诊断影响，禁止连接真机遥操作。

## 回滚方式

当前 locator、直接底层诊断、测试 Master 与真机测试 Master 均已结束；私有映射清理检查通过。
下一次仅按 input-only 指令重新启动。不 reset/stash/checkout 或删除既有数据。
停机回调修复是局部新增保护，不影响设备配置。

## 来源与许可证

修复与测试为项目原创，MIT。底层接口定义参考 libsurvive 项目
[survive_api.h](https://github.com/collabora/libsurvive/blob/master/include/libsurvive/survive_api.h)，
并核对本机导出符号；只使用指针/字符串接口，未依赖未知 FLT 或 pose 结构布局。
未复制/分发本机 locator 或库产物，其来源与许可限制保持既有记录。
