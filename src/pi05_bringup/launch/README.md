# Launch 文件

计划提供：

- `pi05_arm_driver.launch`：以 `side:=left|right` 启动单侧 Piper，默认 `auto_enable:=false`
- `pi05_hand_sensors.launch`：以 `side:=left|right` 启动单侧 Pika 串口与定位
- `pi05_arm.launch`：装载通用过滤参数并编排指定侧链路
- `pi05_dual_arm.launch`：实例化左右链路与双臂安全协调器
- `pi05_visualization.launch`：robot_state_publisher 与 RViz
- `pi05_diagnostics.launch`：只读诊断

完整启动文件应暴露侧别、对应 CAN 接口、Pika 串口和使能策略；左右命名空间必须隔离，真机默认值不得自动使能机械臂。
