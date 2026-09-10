# S02 硬件清单

状态：**基线草案已冻结，现场值待采集；未批准上电运动。**

## 范围与证据规则

本阶段的目标拓扑是单机、单右手、单臂：PI05 工控机运行 ROS 1，通过一个 Pika 右手采集器（定位器及串口夹爪/IMU）产生遥操作输入，通过一只 USB-CAN 适配器连接一台带夹爪的 Piper。相机、数据采集背包、双臂、升降轴、XArm 和 UR 不在 S02 范围内。

“参考确认”只表示 `/home/mips/pika_ros` 的源码或构建产物存在相应能力，不代表 PI05 现场已经安装或接线。“现场待确认”不得用默认值代替。

## 冻结清单

| 编号 | 项目 | S02 基线 | 状态 | 验收证据 |
|---|---|---|---|---|
| H-01 | PI05 工控机 | x86_64；Ubuntu 20.04；可用 USB 口、CAN 网络接口 | 目标要求，现场待确认 | `uname`、`lscpu`、`os-release` 的脱敏输出 |
| H-02 | Piper 机械臂 | 单台、6 轴、右臂用途、带夹爪 | 逻辑拓扑由参考代码确认；具体型号待确认 | 铭牌只记录产品型号；不记录序列号 |
| H-03 | Piper 固件 | 与所选 `piper_sdk`/ROS 驱动兼容 | 现场待确认 | 厂商工具或维护界面中的固件版本，省略设备标识 |
| H-04 | USB-CAN 适配器 | 单只、Linux SocketCAN、`gs_usb` 兼容、1 Mbps | 驱动与速率为参考要求；实物待确认 | USB VID:PID、内核驱动、CAN 详细状态 |
| H-05 | CAN 线束与终端 | Piper 对应 CAN-H/CAN-L/GND；总线两端正确终端 | 现场待确认 | 断电电阻测量、接线复核签字 |
| H-06 | Pika 右手采集器 | 单只；串口输出夹爪/IMU；460800 8N1 | 串口协议参数由源码确认；实物待确认 | 脱敏 udev 属性、串口节点、只读启动日志 |
| H-07 | Pika 定位设备 | 与 `pika_single_locator_node`/libsurvive 兼容的单手定位链路 | 参考确认；型号、数量、安装待确认 | `rosnode`、话题类型/频率；现场安装复核 |
| H-08 | 急停 | 独立于 ROS/主机软件，操作员可立即触达并能切断或禁止危险运动 | 现场待确认，阻塞项 | 接线图、功能测试记录，不记录资产编号 |
| H-09 | Piper 供电 | 电压、电流、保护和接地符合该实物型号手册 | 现场待确认，阻塞项 | 电源铭牌额定值与实测值；省略序列号 |
| H-10 | 安装与工作区 | 底座刚性固定；夹爪、负载、工具和工作空间明确 | 现场待确认，阻塞项 | 安装检查表、负载质量/重心、净空确认 |

参考工作区中的右臂 launch 默认使用 `right_piper`。S05 模板不预填 CAN 接口身份；最终
接口名和 USB bus-info 必须由现场拓扑采集后写入未纳入版本控制的
`config/pi05.env`。配置流程见 [`device-configuration.md`](device-configuration.md)。

## 现场采集命令

以下命令均为只读。输出存档前再次检查，禁止把主机名、用户名、IP、MAC、设备序列号或完整 `/dev/serial/by-id` 链接提交到 Git。

### 主机和 USB

```bash
uname -m
lscpu | grep -E '^(Architecture|Model name|CPU\(s\)):'
grep -E '^(NAME|VERSION|VERSION_ID|ID)=' /etc/os-release
lsusb
lsmod | grep '^gs_usb'
```

`lsusb` 仅用于记录产品级 VID:PID 与描述，不使用 `lsusb -v`。不要运行或保存会输出 DMI/磁盘序列号的全量硬件清单。

### CAN 适配器与总线

```bash
ip -brief link show type can
ip -details -statistics link show type can
for iface in $(ip -brief link show type can | awk '{print $1}'); do
  ethtool -i "$iface" | grep -E '^(driver|version|bus-info):'
done
```

记录 `bus-info` 仅用于物理 USB 端口到逻辑 CAN 名的映射，它不是设备序列号。确认总线处于 `DOWN` 或机械臂未使能后，才可由现场负责人决定是否执行监听：

```bash
timeout 5 candump -L <can-interface>
```

不要在 S02 执行 `cansend`、CAN 回放、接口重命名或比特率变更。

### Pika 串口与定位

```bash
find /dev -maxdepth 1 -type c -name 'ttyUSB*' -printf '%f\n'
udevadm info --query=property --name=/dev/<pika-tty> \
  | grep -E '^(ID_VENDOR_ID|ID_MODEL_ID|ID_USB_DRIVER|ID_PATH)='
stty -F /dev/<pika-tty> -a
source /opt/ros/noetic/setup.bash
source /home/mips/pika_ros/install/setup.bash
rospack find pika_locator
rospack find sensor_tools
```

`ID_SERIAL*`、`ID_USB_SERIAL*` 和 `/dev/serial/by-id/*` 不得进入采集记录。只读 ROS 验证必须在机械臂禁用、控制节点未启动的条件下进行：

```bash
rosnode list
rostopic type /pika_pose_r
rostopic type /pika_localization_status_r
rostopic hz /pika_pose_r
rostopic hz /pika_localization_status_r
```

### 机械臂、电源、急停和安装

这些项目无法仅靠仓库可靠确定，必须现场人工采集：

1. 从铭牌/厂商维护界面记录 Piper **型号与固件版本**，遮挡或省略序列号、二维码和资产编号。
2. 按对应型号手册记录额定电源、峰值需求、保护方式和接地要求。
3. 断电并隔离能源后测量 CAN-H 与 CAN-L 间等效终端电阻；结果和仪表状态写入现场记录。
4. 验证急停为硬件安全链路，断网、ROS 崩溃或 PI05 死机时仍有效。
5. 记录底座固定、工具/负载质量与重心、夹爪型号和清空后的运动包络；图片必须先移除序列号、人员和场地敏感信息。

## S02 硬件退出条件

- H-01 至 H-10 均有“符合/不符合/不适用”结论和证据责任人。
- H-03、H-08、H-09、H-10 未确认前，不进入任何使能或运动阶段。
- CAN 和串口使用稳定逻辑名称，但映射只保存在机器本地配置。
- 仓库中不存在设备序列号、现场网络标识或不可公开的接线照片。
