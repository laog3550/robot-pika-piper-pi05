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

验证等级为“静态”。本阶段没有在 PI05 上修改现场 udev 规则，没有启动 ROS、读取设备
通信、使能或移动机械臂。

## 真机证据

无新增真机测试。S05 仅有右侧设备映射证据；左侧 CAN/Pika 和双侧 side-specific 规则
尚未现场验证。因此阶段状态为“等待真机验收”，不得标记为双臂真机通过。

## 风险、停止与回滚

- 使用新脚本前必须迁移本机私有配置；未迁移会在解析阶段安全失败。
- 两路设备若填入相同物理身份会被拒绝；脚本不会猜测哪一侧正确。
- 双臂协调器和通用控制节点仍是 S09–S11 的计划目标，当前文档接口不能用于运动。
- 回滚代码可撤销 S06 原子提交；现场旧规则不由本阶段自动更改。若以后应用新规则，按
  `docs/device-configuration.md` 在双臂禁用时分侧人工回滚。

## 来源与许可证

本阶段为项目自有脚本和文档纠偏，没有复制上游控制源码。右侧参考实现、固定 SHA 和
未解决许可证项继续以 `docs/upstream-dependencies.md` 为准。
