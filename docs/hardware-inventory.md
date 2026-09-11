# S02 硬件清单

状态：**基线草案已冻结，现场值待采集；未批准上电运动。**

## 范围与证据规则

S06 已纠正 S02 的范围假设。目标拓扑是单机、双手、双臂：PI05 工控机运行 ROS 1，
左右两套 Pika 分别产生遥操作输入，两只独立 USB-CAN 适配器分别连接左右两台带夹爪
Piper。相机、数据采集背包、升降轴、XArm 和 UR 不在当前范围内。

“参考确认”只表示 `/home/mips/pika_ros` 的源码或构建产物存在相应能力，不代表 PI05 现场已经安装或接线。“现场待确认”不得用默认值代替。

## 冻结清单

| 编号 | 项目 | S02 基线 | 状态 | 验收证据 |
|---|---|---|---|---|
| H-01 | PI05 工控机 | x86_64；Ubuntu 20.04；可用 USB 口、CAN 网络接口 | 目标要求，现场待确认 | `uname`、`lscpu`、`os-release` 的脱敏输出 |
| H-02L/R | Piper 机械臂 | 左右各一台 AGILE·X / 松灵 PIPER 标准版、6 轴、带夹爪；公开规格为 1.5 kg 有效负载、4.2 kg 本体、626 mm 工作半径 | 两侧设备映射、实物型号及标准版资料目录已现场确认；夹爪具体型号待确认 | 2026-09-11 分侧核对铭牌和用户指定的厂商资料；序列号等设备标识未入库 |
| H-03L/R | Piper 固件 | 两侧均与固定版本 SDK/ROS 驱动兼容 | 现场待确认 | 分侧记录固件版本，省略设备标识 |
| H-04L/R | USB-CAN 适配器 | 两只、`gs_usb`、1 Mbps，物理端口与逻辑侧别唯一 | 两侧映射、稳定名和 1 Mbps 已验证 | 分侧记录脱敏驱动和 CAN 状态 |
| H-05L/R | CAN 线束与终端 | 两条独立总线的 CAN-H/CAN-L/GND 与终端正确 | 现场待确认 | 分侧断电测量和复核签字 |
| H-06L/R | Pika 手部采集器 | 左右各一套；串口夹爪/IMU；460800 8N1 | 两侧物理映射和稳定别名已验证；数据待验证 | 分侧脱敏 udev 属性和只读日志 |
| H-07L/R | Pika 定位设备 | 左右定位链路可唯一识别且互不串侧 | 参考支持待确认；安装待验证 | 分侧节点、话题类型/频率和遮挡测试 |
| H-08 | 急停 | 独立于 ROS/主机，操作员可立即触达并覆盖两台机械臂 | 现场待确认，阻塞项 | 双臂覆盖的功能测试记录 |
| H-09L/R | Piper 供电 | PIPER 标准版公开额定电压为 DC 24 V；左右各使用一台独立 DC 24 V、10 A、240 W 电源；两侧保护和接地须符合对应实物手册 | 每侧独立供电拓扑及额定输出已现场确认；保护和接地待确认，阻塞项 | 2026-09-11 分侧确认电源额定输出；继续核对保护与接地，不记录序列号 |
| H-10 | 安装与共享工作区 | 两底座固定；负载明确；单臂与双臂运动包络、互碰风险已评审 | 现场待确认，阻塞项 | 安装检查、负载/重心、双臂净空确认 |

逻辑接口固定为 `left_piper`、`right_piper`，但两侧 USB bus-info 必须由现场逐线采集并写入
未纳入版本控制的
`config/pi05.env`。配置流程见 [`device-configuration.md`](device-configuration.md)。

## 现场采集命令

S07 将下列人工检查固化为本地模板和只读校验器，见
[`s07-field-acceptance.md`](s07-field-acceptance.md)。真实记录保存在 Git 忽略的
`config/s07-hardware.env`，仓库只保留脱敏结论。

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
for side in l r; do
  rostopic type /pika_pose_${side}
  rostopic type /pika_localization_status_${side}
  rostopic hz /pika_pose_${side}
  rostopic hz /pika_localization_status_${side}
done
```

### 机械臂、电源、急停和安装

这些项目无法仅靠仓库可靠确定，必须现场人工采集：

1. 从铭牌/厂商维护界面记录 Piper **型号与固件版本**，遮挡或省略序列号、二维码和资产编号。
2. 按对应型号手册记录额定电源、峰值需求、保护方式和接地要求。
3. 断电并隔离能源后测量 CAN-H 与 CAN-L 间等效终端电阻；结果和仪表状态写入现场记录。
4. 验证急停为硬件安全链路，断网、ROS 崩溃或 PI05 死机时仍有效。
5. 记录底座固定、工具/负载质量与重心、夹爪型号和清空后的运动包络；图片必须先移除序列号、人员和场地敏感信息。

## S02 硬件退出条件

- H-01 及所有 L/R 项均有“符合/不符合/不适用”结论和证据责任人。
- 任一侧 H-03/H-09 或公共 H-08/H-10 未确认前，不进入任何使能或运动阶段。
- CAN 和串口使用稳定逻辑名称，但映射只保存在机器本地配置。
- 仓库中不存在设备序列号、现场网络标识或不可公开的接线照片。

## 厂商资料

- 用户于 2026-09-11 指定的
  [PIPER 产品使用资料清单-202607](https://agilexsupport.yuque.com/staff-hso6mo/alxgtf/gg11q9ywverdd8rk?singleDoc)
  位于厂商知识库的“PIPER 标准版使用资料”目录，并链接 `PIPER 机械臂用户手册`
  V2.0.0。该目录用于确认版本系列，不替代现场固件读取。
- 松灵官方 [PiPER 产品页](https://www.agilex.ai/products/piper) 给出上述标准版额定规格。
  公开额定负载不是当前工具/夹爪的实际负载，DC 24 V 也不代表两侧现场供电已经验收。
