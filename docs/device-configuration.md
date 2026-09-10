# PI05 CAN 与 Pika 串口配置

S05 将设备发现、状态检查和系统修改分成独立入口。配置目标是 Piper 的 1 Mbps
SocketCAN 接口和 Pika 右手串口稳定别名；不启动 ROS 节点、不发送 CAN/串口数据，也
不使能机械臂。

## 安全边界

- `discover_devices.sh` 永远只读，不调用 sudo，不查询或输出设备序列号。
- `check` 永远只读；配置缺失、匹配为零、匹配超过一个、别名冲突或状态错误均返回非零。
- `apply` 先执行与 `check` 相同的身份解析。身份不是唯一匹配时，在调用 sudo 前退出。
- CAN 身份由 `gs_usb` 驱动和精确 `ethtool bus-info` 共同确定；串口身份由精确
  `ID_PATH + ID_VENDOR_ID + ID_MODEL_ID` 共同确定。
- `ID_PATH` 和 CAN `bus-info` 描述物理 USB 端口。它们不等于设备序列号，但仍只写入
  Git 忽略的本机 `config/pi05.env`。
- 禁止使用 `ID_SERIAL*`、`ID_USB_SERIAL*` 或 `/dev/serial/by-id`；udev 权限固定为
  `dialout:0660`，不使用全员可写的 `0777`。

## 1. 创建本机配置

```bash
cp config/pi05.env.example config/pi05.env
scripts/discover_devices.sh
```

发现输出只包含以下字段：

```text
CAN interface=<name> driver=<driver> bus-info=<physical-port>
SERIAL device=<tty> id-path=<physical-port> vid=<vid> pid=<pid> driver=<driver>
```

由现场负责人沿 USB 线缆逐一断开/接回，在机械臂禁用且 CAN 接口不承载控制流量时确认
哪一个端口属于右侧 Piper，哪一个串口属于右侧 Pika。不要只根据 `can0`、`ttyUSB0`
等枚举顺序判断身份。将确认后的非敏感值填入 `config/pi05.env`：

```dotenv
PI05_CAN_INTERFACE=right_piper
PI05_CAN_BITRATE=1000000
PI05_CAN_USB_BUS_INFO=<discover 输出中的精确 bus-info>
PI05_PIKA_SERIAL_ALIAS=/dev/pi05-pika-right
PI05_PIKA_SERIAL_BAUD=460800
PI05_PIKA_SERIAL_ID_PATH=<discover 输出中的精确 ID_PATH>
PI05_PIKA_SERIAL_VENDOR_ID=<四位 VID>
PI05_PIKA_SERIAL_MODEL_ID=<四位 PID>
```

若多个设备具有相同 VID:PID，仍必须通过物理端口 `ID_PATH` 区分。未完成线缆追踪时保持
字段为空；脚本会拒绝猜测。

## 2. 只读检查

```bash
scripts/configure_can.sh check
scripts/configure_pika_serial.sh check
```

CAN `check` 只有在配置的 bus-info 唯一对应一个 `gs_usb` CAN 设备、该值确实是设备的
sysfs 祖先端口、接口名正确、状态为 UP 且 bitrate 为 1000000 时才通过。串口 `check`
只有在三项身份字段唯一匹配一个
`ttyUSB*`/`ttyACM*` 设备，且别名解析到该设备时才通过。

初次配置时，别名或接口状态尚未建立，`check` 返回非零是预期结果；输出应明确区分
“身份不唯一”和“身份唯一但配置未应用”。

## 3. 审阅并应用

机械臂必须保持禁用，控制节点必须停止。先查看帮助与配置，再交互执行：

```bash
scripts/configure_can.sh --help
scripts/configure_pika_serial.sh --help
scripts/configure_can.sh apply
scripts/configure_pika_serial.sh apply
```

每个 `apply` 都会列出修改目标并要求输入完整的 `APPLY`。受控自动化可显式使用
`apply --yes`，但不会绕过身份唯一性门禁。

CAN apply 会安装 `/etc/udev/rules.d/80-pi05-can.rules`，以 `gs_usb + bus-info` 将后续
设备添加绑定到配置的接口名；随后仅对唯一匹配接口执行 down、必要时重命名、设置
1 Mbps 和 up。它不运行 `cansend` 或 `candump`。Pika apply 会安装
`/etc/udev/rules.d/80-pi05-pika-serial.rules`，重新加载规则并只触发匹配 tty，生成稳定
串口别名。Pika 节点仍负责打开串口并设置 460800 8N1，本阶段不启动该节点。

应用后重新运行两个 `check`。若 USB 设备被移到其他物理端口，检查会失败，必须由现场
负责人重新确认并更新私有配置，不能放宽匹配条件。

## 回滚

回滚前确认没有 ROS 节点使用 CAN 或串口：

```bash
sudo rm -- /etc/udev/rules.d/80-pi05-can.rules
sudo rm -- /etc/udev/rules.d/80-pi05-pika-serial.rules
sudo udevadm control --reload-rules
```

删除规则不会自动关闭当前 CAN 接口，也不会立即删除已存在的 udev 别名；应在设备安全
禁用后重新插拔或重启。不要用仓库脚本自动删除规则，因为系统文件可能已由现场维护者
接管。
