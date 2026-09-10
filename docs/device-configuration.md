# PI05 双侧 CAN 与 Pika 串口配置

目标设备为左右两台 Piper 和左右两套 Pika。发现脚本保持只读；配置脚本必须显式传入
`left` 或 `right`，不会根据 `can0`、`ttyUSB0` 等枚举顺序猜测侧别，也不会启动 ROS、
发送 CAN/串口数据或使能机械臂。

## 安全边界

- `scripts/discover_devices.sh` 不调用 sudo，不查询或输出序列号。
- `check` 只读；`apply` 只有在身份唯一且明确确认后才修改系统。
- CAN 使用 `gs_usb + ethtool bus-info`，Pika 使用
  `ID_PATH + ID_VENDOR_ID + ID_MODEL_ID` 绑定物理端口。
- 左右接口名、CAN bus-info、串口别名和串口 ID_PATH 必须互不相同；脚本发现碰撞立即退出。
- 真实物理路径只写入 Git 忽略的 `config/pi05.env`。

## 1. 逐线确认并填写配置

机械臂禁用、控制节点停止后执行：

```bash
cp config/pi05.env.example config/pi05.env
scripts/discover_devices.sh
```

现场负责人沿线逐一断开/接回，确定四个设备的逻辑侧别。填写模板中的
`PI05_LEFT_*`、`PI05_RIGHT_*` 字段；未确认的一侧保持身份字段为空，脚本会拒绝配置该侧，
但不妨碍先配置另一侧。禁止使用序列号、`ID_SERIAL*` 或 `/dev/serial/by-id`。

逻辑名称固定为：

| 侧别 | CAN | Pika 串口别名 |
|---|---|---|
| left | `left_piper` | `/dev/pi05-pika-left` |
| right | `right_piper` | `/dev/pi05-pika-right` |

## 2. 分侧 check 和 apply

先只读检查；初次配置时因接口名/别名尚未创建而失败是预期结果：

```bash
scripts/configure_can.sh check left
scripts/configure_can.sh check right
scripts/configure_pika_serial.sh check left
scripts/configure_pika_serial.sh check right
```

审阅身份后，逐侧交互执行并输入完整的 `APPLY`：

```bash
scripts/configure_can.sh apply left
scripts/configure_can.sh apply right
scripts/configure_pika_serial.sh apply left
scripts/configure_pika_serial.sh apply right
```

CAN 固定为 1000000 bit/s。每侧使用独立规则文件：

- `/etc/udev/rules.d/80-pi05-can-left.rules`
- `/etc/udev/rules.d/80-pi05-can-right.rules`
- `/etc/udev/rules.d/80-pi05-pika-serial-left.rules`
- `/etc/udev/rules.d/80-pi05-pika-serial-right.rules`

执行后重新运行四项 `check`。S06 已取得四项通过和四份分侧规则存在的脱敏真机证据，
双侧设备配置验收通过。该结论仅覆盖身份绑定、稳定名称和 CAN 1 Mbps 链路状态；设备
数据和 ROS 反馈仍待 S08 验证。

## S05 单侧配置迁移

若主机已安装旧的 `80-pi05-can.rules` 和 `80-pi05-pika-serial.rules`，先保持机械臂禁用，
审阅旧规则与私有配置，按新模板重新确认右侧并安装 side-specific 规则。确认新 `right`
check 通过且没有其他维护流程使用旧规则后，才由维护者人工移除旧文件；脚本不自动删除。

## 回滚

停止所有相关节点并禁用两臂后，仅删除明确属于本项目和目标侧别的规则，再重新加载 udev：

```bash
sudo rm -- /etc/udev/rules.d/80-pi05-can-left.rules
sudo rm -- /etc/udev/rules.d/80-pi05-can-right.rules
sudo rm -- /etc/udev/rules.d/80-pi05-pika-serial-left.rules
sudo rm -- /etc/udev/rules.d/80-pi05-pika-serial-right.rules
sudo udevadm control --reload-rules
```

删除规则不会关闭当前 CAN 或立即移除已有别名；应在安全禁用后重新插拔或重启。
