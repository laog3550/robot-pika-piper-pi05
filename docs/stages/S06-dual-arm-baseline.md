# S06 PI05 双手双臂基线纠偏

## 目标

纠正此前以右手和单臂为最终交付目标的范围偏差。从 S06 起，项目唯一目标拓扑为一台
PI05、左右两套 Pika、左右两台 Piper 和两路独立 CAN；右侧仅是已取得部分证据的一侧。

## 完成内容

- README、硬件清单、控制架构、ROS 接口和安全约束统一改为双手双臂。
- 新增 S07–S16 路线图，区分只读通信、通用分侧实现、双臂安全、分侧运动和协同验收。
- 环境模板改为 `PI05_LEFT_*` / `PI05_RIGHT_*`，逻辑名为 `left_piper`、`right_piper` 和
  `/dev/pi05-pika-left`、`/dev/pi05-pika-right`。
- CAN/Pika 配置入口要求显式 `left|right`，检查跨侧身份碰撞，并使用独立 udev 规则，
  防止配置第二侧时覆盖第一侧。
- 将右侧专用参数文件改为共享 `arm_filter.yaml`；速度基线统一为 15%，自动夹爪返回关闭。
- 保留 S05 右侧真机证据，并明确它不能替代左侧或双臂验收。

## 公共接口变化

```text
scripts/configure_can.sh check|apply <left|right> [--config PATH] [--yes]
scripts/configure_pika_serial.sh check|apply <left|right> [--config PATH] [--yes]
```

旧的无侧别调用和 `PI05_CAN_*` / `PI05_PIKA_SERIAL_*` 单侧配置不再接受。已有 S05 主机
应按设备配置文档人工迁移旧规则；脚本不会删除或覆盖不明确归属的系统文件。

## 验证记录

验证日期：2026-09-10。

- `tests/test_device_configuration_scripts.sh`：通过；覆盖左右 CAN、显式侧别、跨侧身份
  冲突、左右串口选择、串口歧义、无确认不得 sudo 和不安全配置拒绝。
- `bash -n scripts/*.sh scripts/lib/*.sh tests/*.sh`：通过。
- `tests/test_environment_scripts.sh`：通过；仅出现上游 MoveIt metapackage 依赖警告，测试通过。
- `git diff --check`：通过。
- `skill-creator/scripts/quick_validate.py .agents/skills/pi05-stage-sync`：通过（在临时 Python
  虚拟环境安装 `PyYAML` 后运行；未修改项目或系统 Python 环境）。
- `scripts/configure_can.sh check left` 与 `check right`：真机通过。左右 USB bus-info
  分别唯一匹配 `gs_usb` 接口，稳定名为 `left_piper`、`right_piper`，均为 UP 且
  bitrate 为 1000000。
- `scripts/configure_pika_serial.sh check left` 与 `check right`：真机通过。左右稳定别名
  `/dev/pi05-pika-left`、`/dev/pi05-pika-right` 分别唯一解析到现场确认串口。
- 只读文件存在性检查：左右 CAN 与 Pika 共四份 side-specific udev 规则均存在；真实
  `config/pi05.env` 由 Git 忽略，公共模板不含现场值。

因此 S06 达到“真机”验证等级，但该等级仅覆盖双侧物理身份绑定、稳定命名和 CAN
1 Mbps 链路配置，不覆盖设备数据、ROS 反馈、控制或运动。

## 真机证据

测试日期：2026-09-10。目标为 x86_64 Ubuntu 20.04 PI05 主机上的左右两台 Piper、
两只独立 `gs_usb` 适配器和左右两套 Pika 串口。现场操作者沿线确认侧别、迁移右侧
S05 私有配置、填写左侧私有配置，并分别应用四份 side-specific 规则；随后由操作者和
本阶段流程重复执行四项只读 check，结果一致通过。

验收记录只保存稳定逻辑名、数量、驱动类别、bitrate 和通过结论；实际 bus-info、
ID_PATH、VID:PID、临时 tty 名和序列号均未写入仓库。测试没有运行
`candump`/`cansend`，没有打开 Pika 数据流，没有启动 ROS 控制节点、使能或移动机械臂。
若任一 check 失败，停止后续启动并保持双臂禁用。

## 风险、停止与回滚

- 使用新脚本前必须迁移本机私有配置；未迁移会在解析阶段安全失败。
- 两路设备若填入相同物理身份会被拒绝；脚本不会猜测哪一侧正确。
- 双臂协调器和通用控制节点仍是 S09–S11 的计划目标，当前文档接口不能用于运动。
- 回滚代码可撤销 S06 原子提交；现场旧规则不由本阶段自动更改。若以后应用新规则，按
  `docs/device-configuration.md` 在双臂禁用时分侧人工回滚。

## 来源与许可证

本阶段为项目自有脚本和文档纠偏，没有复制上游控制源码。右侧参考实现、固定 SHA 和
未解决许可证项继续以 `docs/upstream-dependencies.md` 为准。
