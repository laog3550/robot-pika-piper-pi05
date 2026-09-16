# Launch 文件

当前真机入口位于 `pi05_left_teleop/launch`：

- `left_teleop.launch`：左 Pika 到 `left_piper`
- `right_teleop.launch`：右 Pika 到 `right_piper`
- `dual_teleop.launch`：同时实例化左右链路
- `side_teleop.launch`：上述入口复用的分侧实现

Piper 驱动仍由 `pi05_control/launch/s09_single_arm_driver.launch` 封装。左右 CAN 名称、
`auto_enable` 和是否连接驱动均为显式 launch 参数。
