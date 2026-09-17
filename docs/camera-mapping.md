# 相机角色映射（双臂腕部 + 顶部）

状态：**2026-09-17 现场确认全部三个角色：左右腕部 = Orbbec Dabai DC1，顶部 = Intel RealSense D455。**

本文只记录角色、拓扑与驱动路径。真实序列号属于机器本地信息，只写入 Git 忽略的
`config/cameras.env`，仓库内一律不出现；`scripts/check_cameras.sh` 的输出也只显示
脱敏值（形如 `***CW`）。

## 角色与型号

| 角色 | 型号 | 组成 | 相机侧接口 | 现状 |
|---|---|---|---|---|
| 左腕 | Orbbec Dabai DC1 | 彩色半边 + 深度半边 | UVC + OpenNI 协议 | 已现场确认 |
| 右腕 | Orbbec Dabai DC1 | 彩色半边 + 深度半边 | UVC + OpenNI 协议 | 已现场确认 |
| 顶部 | Intel RealSense D455 | 单台 | UVC + librealsense | 已现场确认，USB3 |
| 备用 | Orbbec Dabai DC1 | 彩色半边 + 深度半边 | 同上 | 当前不在线 |
| Pika 手持端 | Intel RealSense D405 ×2 | 单台 | UVC + librealsense | 每台 Pika 各一台深度相机；左右归属未逐侧追踪 |

上表前三行是本仓库关心的**腕部 + 顶部**角色，`scripts/check_cameras.sh` 只校验这三项。
后两行（Pika 端相机）只做记录，不在校验范围内。

Dabai DC1 在 USB 上是**两个设备**，必须挂在同一个父 hub 下：

- 彩色半边 `2bc5:0557`（UVC 1.00，制造商为 UVC 芯片厂商），**带序列号**；
- 深度半边 `2bc5:0657`（`ORBBEC Depth Sensor`，class `0xff`），**没有 USB 序列号**。

因此**分左右不能靠深度半边**，只能靠彩色半边的序列号或 USB 物理端口。左右映射一旦
确认就写入 `config/cameras.env`，由 `scripts/check_cameras.sh` 在每次上机前复核。

## Pika 手持端相机（仅记录）

参考工作区的 `sensor_tools/open_multi_sensor.launch` 按每侧一组启动：Pika 串口 +
`l/r_fisheye_port`（鱼眼）+ `l/r_depth_camera_no`（RealSense 深度相机序列号）。本机对应
的硬件是两台 **DECXIN 鱼眼**（`1bcf:2cd1`，udev 规则名 `sensor_fisheye`，两台序列号相同
且都指向同一个 `/dev/video50`，因此左右必须用 USB 物理端口区分）和两台 **RealSense D405**
深度相机（`2-8.3.2` 与 `1-11.2`，后者无序列号且挂在 USB2）。

这两组相机属于 Pika 手持端，不在本仓库的腕部/顶部角色映射内，`scripts/check_cameras.sh`
不校验它们；需要时再单独追踪左右归属。

## 官方规格（DaBai DC1）

来自奥比中光官网产品目录：双目结构光，基线 40mm；最大工作范围 0.3–3m、推荐
0.3–2m，相对精度 6mm@1m；深度 FoV 68°×45°，最高 640×400@30fps；RGB 66°×51°，
1280×720@30fps；**USB 2.0**（Micro USB）；59.6×17.4×11.1mm / 17g；嵌入式安装；
官方 SDK 一栏写明 **Orbbec SDK 或 OpenNI2**。体积与量程决定它适合腕部近距视角，
而不是大视场的顶部视角。

## 驱动路径（现场已验证）

- **必须使用 Orbbec SDK v1**（`github.com/orbbec/OrbbecSDK`，当前 `v1.10.37`）。
  Orbbec SDK v2 明确不再支持 OpenNI 协议老机型，DaBai 不在 v2 支持列表内。
  下载页 `cate=121&id=1` 的 `dabai` 条目同时给出 OrbbecSDK、OrbbecSDK_ROS1（支持
  Noetic）、pyorbbecsdk 与 OpenNI_SDK。
- 参考工作区已有的 `sensor_tools/usb_camera.py` 只是 OpenCV UVC 节点，**只能取彩色**，
  不能取深度；它和 SDK 也不要同时用于同一台相机（见下）。
- 顶部 RealSense 走 `librealsense` + `realsense2_camera`，参考工作区
  `~/pika_ros/install/lib/librealsense2_camera.so` 已编译，`rs-enumerate-devices`
  可枚举。

### 三个已实测的坑

1. **SDK 会接管 Dabai 的彩色接口。** 用 SDK 打开相机后，内核 `uvcvideo` 会从该接口
   解绑，`/dev/videoN` 与 `/dev/v4l/by-id/...` 一起消失（现场症状：接口 `driver` 为空、
   UVC 节点数为 0、无 USB 断连日志）。恢复方法是重新插拔该相机。结论：**同一台 Dabai
   不要「SDK 取深度 + `/dev/videoN` 取彩色」混用**，彩色与深度都交给 SDK。
2. **ROS 侧用 `serial_number` 选相机，不要用 `usb_port`。** SDK 会为 Dabai 报出彩色半边
   的序列号；而 `usb_port` 参数实际是拿 uid 做精确匹配，uid 形如 `<端口>-<后缀>`，后缀
   与枚举序号有关，插拔后会变。
3. **udev 符号链接对多台同型号不唯一。** Orbbec 规则里的 `dabai_dc1` /
   `dabai_dc1_rgb` 对两台相机是同一个名字，只指向最后枚举的那一台；分侧必须用序列号
   或物理端口。

## 配置与校验

```bash
# 复制模板并填写现场值（config/cameras.env 已被 Git 忽略）
cp config/cameras.env.example config/cameras.env

# 只读发现当前在线候选相机（序列号脱敏），用于填写端口
scripts/check_cameras.sh --discover

# 上机前只读复核角色映射
scripts/check_cameras.sh
```

校验内容：USB 物理端口、VID:PID、序列号（脱敏比对）、彩色与深度是否同父 hub、
彩色流的 `uvcvideo` 绑定与 UVC 节点数、`v4l/by-id` 稳定名称是否存在、顶部 RealSense
是否为 USB3。未填写的角色跳过并警告，因此只追了一条线的现场也能检查。退出码 `0`
通过（允许警告）、`1` 不匹配、`2` 参数错误、`3` 配置或环境错误。

离线契约测试：`tests/test_cameras_checker.sh`（用假 sysfs/udev，不接触真实硬件，
并断言输出不泄露完整序列号）。

## 启动（Noetic）

腕部（左右各一个节点，`serial_number` 取自 `config/cameras.env`）：

```bash
roslaunch orbbec_camera dabai_dcl.launch camera_name:=camera_left  serial_number:=<左腕序列号> device_num:=2
roslaunch orbbec_camera dabai_dcl.launch camera_name:=camera_right serial_number:=<右腕序列号> device_num:=2
```

`dabai_dcl.launch` 默认：color 640×360@15 MJPG、depth 640×400@15 Y14、IR 640×400@15、
`depth_registration:=true`、`enable_point_cloud:=true`；话题前缀为 `camera_name`。

顶部 D455 用 `realsense2_camera`（参考工作区已编译），按序列号选择，并核对它确实在
USB3 端口上：

```bash
source /opt/ros/noetic/setup.bash && source ~/pika_ros/install/setup.bash
roslaunch realsense2_camera rs_camera.launch serial_no:=<顶部序列号> camera:=cam_top
# 看图：rqt_image_view，选 /cam_top/color/image_raw 与 /cam_top/depth/image_rect_raw
```

`rs-capture` / `rs-color` / `rs-save-to-disk` 之类示例不接受设备参数，只会打开枚举到的
第一台；要按序列号挑设备请用 `realsense-viewer`（GUI 里逐台 Add Source）或上面的 ROS
入口。`rs-multicam` 可以一次显示所有 RealSense。

## 与当前阶段基线的关系

本阶段的 PI05 + Pika + Piper 遥操作基线仍然不含相机数据链路
（见 [软件环境清单](software-environment.md)）。本文与校验脚本只固定**角色映射与
只读复核**，不启动相机节点、不改变遥操作链路。
