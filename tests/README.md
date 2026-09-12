# 验收测试

测试按风险递增执行，并保存日期、硬件编号、软件提交 SHA、参数和结果。

## 阶段 A：静态检查

- catkin 构建成功
- launch/XML/YAML/Python 语法检查通过
- 依赖和许可证清单完整
- 配置中没有密钥或现场隐私信息

## 阶段 B：无电机运动

- CAN 接口名称、比特率和错误计数正确
- Piper 状态、六关节与夹爪反馈稳定
- Pika 串口、定位和触发服务稳定
- 话题频率、单位、关节顺序和时间戳正确

## 阶段 C：安全故障注入

- 未使能时不输出运动命令
- 指令超时后停止并清除旧目标
- Pika 定位丢失后停止
- disable/enable 后不会执行上次目标
- 急停、软件停机与节点退出均符合预期

## 阶段 D：低速真机

- 单关节小角度逐项核对方向和限位
- 夹爪开合范围与单位核对
- 组合运动、遥操作和工作空间核对
- 回零/返回逻辑在可中断条件下验证

任何阶段失败都应停止进入下一阶段。

## 仓库级脚本测试

- `test_environment_scripts.sh`：S04 环境脚本契约测试。
- `test_device_configuration_scripts.sh`：S05 check/apply 分离、脱敏发现、安全配置解析和
  身份歧义拒绝测试；使用模拟命令，不修改主机设备。
- `test_s07_hardware.sh`：S07 现场记录字段、双人复核、安全结论、危险文本与疑似敏感
  标识拒绝测试；不访问硬件。
- `test_upstream_manifest.sh`：固定 commit、受限清单结构和未知字段拒绝测试。
- `test_pika_stream_checker.sh`：S08 Pika 完整/截断/空流、参数校验和只读 API 约束测试。
- `test_piper_can_stream_checker.sh`：S08 Piper CAN 反馈 ID 完整性、控制 ID 拒绝和无发送
  API 约束测试。
- `test_piper_readonly_feedback.sh`：S08 Piper 协议端序/单位/完整帧组，以及双侧 ROS
  launch、无 CAN 发送 API、无命令入口契约测试。
- `test_pika_localization_checker.sh`：S08 双侧定位频率、有效状态、时间戳、frame 稳定性
  聚合判断和无写入 API 契约测试。
- `test_single_arm_driver_launch.sh`：S09 左右 launch 展开、必填 side、默认不启动、
  `auto_enable=false` 和全部驱动接口相对命名/分侧隔离契约测试；不启动驱动节点。
- `test_safety_filter.sh`：S10 通用过滤状态机的左右离线回放、故障注入及 launch 安全边界；
  不启动 Piper 驱动，不连接真机命令入口。
- `test_dual_arm_safety.sh`：S11 双侧协调状态机、闭集 bringup 及撤权→stop→disable 顺序契约。
- `test_control_graph_checker.sh`：S11 只读 ROS 图所有权规则和旁路拒绝；测试不连接真机。
