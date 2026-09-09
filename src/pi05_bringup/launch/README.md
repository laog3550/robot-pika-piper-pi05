# Launch 文件

计划提供：

- `pi05_driver.launch`：仅启动 Piper 驱动，默认 `auto_enable:=false`
- `pi05_sensors.launch`：仅启动 Pika 串口与定位
- `pi05_right_arm.launch`：装载过滤参数并编排完整右臂链路
- `pi05_visualization.launch`：robot_state_publisher 与 RViz
- `pi05_diagnostics.launch`：只读诊断

完整启动文件应暴露 CAN 接口、Pika 串口、是否自动使能等参数；真机默认值不得自动使能机械臂。
