# S05 PI05 CAN 与 Pika 串口配置流程

## 目标

建立脱敏、可审计的设备发现和配置流程：Piper CAN 固定为 1 Mbps，并以 USB bus-info
绑定稳定接口名；Pika 串口以物理路径和 VID:PID 建立稳定别名。只读 check 与系统修改
apply 必须明确分离，设备身份不唯一时禁止修改。

## 完成内容

- 增加不调用 sudo 的 `discover_devices.sh`，仅输出 CAN 名称/驱动/bus-info 和串口
  device/ID_PATH/VID/PID/驱动。
- 增加 `configure_can.sh check|apply`；只接受唯一的 `gs_usb + bus-info` 匹配，并验证
  bus-info 是 sysfs 祖先端口，固定 bitrate 为 1000000，安装持久化 udev 命名规则并
  执行 apply 后检查。
- 增加 `configure_pika_serial.sh check|apply`；只接受唯一的
  `ID_PATH + ID_VENDOR_ID + ID_MODEL_ID` 匹配，以 `dialout:0660` 安装串口别名规则。
- 增加安全 `.env` 解析器；配置内容不会作为 shell 执行，未知键或不安全字符直接失败。
- 扩展 `pi05.env.example` 和操作文档，所有机器唯一身份字段保持为空。
- 增加模拟测试，覆盖帮助、错误码、check 无 sudo、脱敏输出和歧义身份拒绝。

## 接口与兼容性

公共入口：

- `scripts/discover_devices.sh`
- `scripts/configure_can.sh check|apply [--config PATH] [--yes]`
- `scripts/configure_pika_serial.sh check|apply [--config PATH] [--yes]`

目标系统为 Ubuntu 20.04，依赖 S04 的 `iproute2`、`ethtool`、`udev` 和 SocketCAN
`gs_usb`。Pika 串口协议参数固定为参考 `sensor_tools` 使用的 460800 8N1；S05 只创建
别名，不打开串口。

`apply --yes` 仅省略交互确认，不绕过配置完整性、驱动、精确匹配、唯一性或目标名冲突
检查。CAN apply 只改变链路名称/bitrate/UP 状态，不发送任何 CAN 帧。

## 验证记录

验证日期：2026-09-10。

- `bash tests/test_device_configuration_scripts.sh`：通过。模拟命令确认只读发现不调用
  sudo、不泄露 `ID_SERIAL`，CAN/串口歧义匹配在 sudo 前失败，恶意配置文本不执行。
- `bash tests/test_environment_scripts.sh`：通过，S04 环境流程未回归。
- `bash -n scripts/*.sh scripts/lib/*.sh tests/*.sh`：通过。
- `git diff --check`：通过。
- `scripts/discover_devices.sh`：在当前主机只读执行成功；观察到 2 个 `gs_usb` CAN
  接口和 2 个同 VID:PID 的 USB 串口候选。本文不记录实际名称、物理路径或设备标识。
- 对当前两个 CAN 候选执行只读 sysfs 祖先核对：两者的 `ethtool bus-info` 均是可用于
  `KERNELS` udev 匹配的物理端口标记。

验证等级为“静态”。脚本契约和只读发现已验证，但没有执行 apply，也没有确认哪一条
物理线缆属于右 Piper/Pika。

## 真机证据

未执行配置或通信验收。没有关闭/重命名 CAN 接口、没有安装 udev 规则、没有打开 Pika
串口、没有监听或发送 CAN 帧，也没有启动 ROS 节点、使能机械臂或发送运动指令。

由于当前存在多个 CAN 与串口候选，必须由现场负责人沿线确认物理身份。S05 状态为
“等待真机验收”。

## 风险与限制

- USB bus-info/ID_PATH 绑定的是物理端口；更换主机 USB 插口后 check 会失败，需要重新
  现场确认，不能自动选择另一个设备。
- 安装 udev 规则属于系统修改；若已有同名规则由其他维护流程管理，应用前必须人工审阅。
- CAN link UP 不代表 Piper 通信、终端、电源、急停或运动安全已经验收。
- 串口别名存在不代表数据协议或 Pika 定位质量已验证。
- S03 记录的 `pika_locator` 和内嵌 Piper ROS 许可证阻塞不由本阶段解决。

## 回滚方式

本阶段代码可回退单个 S05 提交。现场 apply 的系统规则必须在机械臂禁用、相关节点停止
且确认文件归属后，由维护者人工删除
`/etc/udev/rules.d/80-pi05-can.rules` 和
`/etc/udev/rules.d/80-pi05-pika-serial.rules`，再重新加载 udev。仓库脚本不自动删除
系统规则，也不自动关闭当前 CAN 接口。

## 来源与许可证

- CAN 行为约定参考只读工作区
  `PikaAnyArm/piper/piper_ros/can_activate.sh` 与 `can_config.sh`，参考工作区 SHA
  `PikaAnyArm@6d8685218c1c39a2a0f7614620919b34481fbdc4`；S03 可获取基线为
  `d2b8b84c756d8684cfdd3970741d32d89b248257`，BSD-3-Clause。
- Pika 波特率参考只读工作区 `pika_ros/src/sensor_tools/src/serial_gripper_imu.cpp`，参考
  SHA `pika_ros@535eac9ad54001ff82f3a0c1256bca3206b5b51f`；S03 可获取基线为
  `ed82f402cebe57aa093d59303215929f0119b0fc`，根许可证 BSD-3-Clause，子包元数据
  `TODO` 的限制继续保留。
- S05 脚本为本项目独立实现，没有复制参考脚本、控制代码、二进制或未知许可证源码。
