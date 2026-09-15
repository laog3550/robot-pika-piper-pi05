# S12 新 Pika input-only 启动验收记录

## 目标

在双侧跟踪器充电后，以项目自有 launch 核对双侧定位、转发隔离、输入活动与停机清理。
结论：**等待真机验收**；已取得真机启动及静态输入证据，但右侧活动和双侧完整验收未通过。
本记录补充 `s12-pika-input-only.md` 的此前快照，不更改既有 S12 文档或安全阻塞状态。

## 完成内容

start preflight 与 git status 已执行，仓库身份正确；起始 HEAD 为
`3c17a3219091df63e0845aef00e4feef058a8934`，分支为
`stage/S12-split-side-low-speed-acceptance`。进入本轮前所有改动保持原样。
fetch 后 origin/main 与 HEAD 一致，GitHub 未发现开放 stage PR。
关闭旧双 locator 和旧 RViz，清除旧私有参数，再启动新 input-only launch。
未执行 reset、stash、checkout、提交、推送或 PR 发布。

## 接口与兼容性

仅启用 `/pi05/pika_input/left|right/pose` 和 `.../localization_status` 观察入口。
显式 `mapping_order:=swapped`，映射值只从已有环境读取，不显示或写入文件。
没有启动 Piper 驱动、遥操作、串口控制节点或 RViz。
首次启动摘要仅包含 side 和 mapping_order 等非敏感参数，没有展开跟踪器标识。

## 验证记录

启动环境为 Noetic、参考区 install、锁定上游工作区、项目 devel 与 Python 3.8 venv。

```bash
roslaunch pi05_pika_input pika_input_only.launch \
  start_locator:=true mapping_order:=swapped left:=true right:=true
```

使用内存 Python 订阅器复用现有 LocalizationStats/evaluate，订阅新包两侧观察话题。
每次窗口 15 秒，位姿最低 30 Hz，状态至少 5 条且全部有效；右侧活动要求
平移至少 0.02 m 或旋转至少 0.10 rad，左侧静置用于身份核对。不打印或保存位姿值。

| 窗口 | 左 pose / 速率 | 左有效状态 | 右 pose / 速率 | 右有效状态 | 活动与返回码 |
|---|---|---|---|---|---|
| 右侧核对 1 | 1804 / 120.0 Hz | 1909/1909 | 1803 / 119.9 Hz | 2034/2034 | 两侧 not-detected；1 |
| 右侧核对 2 | 1804 / 120.0 Hz | 1869/1869 | 1803 / 119.9 Hz | 1957/1957 | 两侧 not-detected；1 |

两个窗口的有效状态、有限值、四元数、时间戳和 frame 检查未报告失败，唯一失败项是
右侧未检测到要求的活动。采样窗口内尚无用户明确反馈已执行指定动作，不能据此认定
设备故障，也不能把右侧或双侧活动记为通过。

随后 5 秒对比原始话题与转发输出：左侧原始 601、转发 600，600 条转发内容和时间戳
与原始一致；右侧原始 600、转发 599，599 条转发与原始一致。
两层级均 motion=not-detected，未发现转发冻结。
ROS 图未发现名称含 Piper/teleop 的节点，分侧转发接口均在输入命名空间内。
该图检查不能替代机械臂安全审计。

Ctrl-C 关闭新 launch 后检查 `/pi05/pika_input/safe_locator_backend` 不存在，
private_mapping_cleanup=PASS；随后关闭 ROS Master。最终进程检查无 ROS Master、locator、
RViz、Piper 或 teleop 遗留进程。`git diff --check` 返回 0。

## 真机证据

日期 2026-09-15，Ubuntu 20.04、ROS Noetic、双 Pika 跟踪接收器。
用户报告右侧跟踪器充电完成；新 launch 两侧定位状态全部有效。
未运行任何 Piper 驱动或机械臂运动测试。右侧独立活动与双侧活动验收仍待同步操作窗口。

## 风险与限制

现有左侧身份核对证据来自旧 locator 和用户 RViz 观察；新启动方式下右侧运动身份未确认。
下一步须同步开始窗口：只移动右侧并检查右侧 detected/左侧 not-detected，再反向核对，
最后两侧活动均满足且返回 0。
Piper J2/J3 异常仍未闭环，禁止跳到机械臂遥操作，不放宽阈值或恢复自动 disable。
依据 pi05-stage-sync 的归属、安全和验收门禁，本轮不发布。

## 回滚方式

本轮未改变映射环境文件。新 launch、旧查看会话和 ROS Master 均已停止；按下一次明确的
输入-only 验收指令重新启动。不要覆盖此前未提交改动。

## 来源与许可证

新包为项目原创；本机 pika_locator 仅作现场调用，未复制或分发二进制。
其来源和许可证据缺口保持原有记录，不作为批准发布依赖。
