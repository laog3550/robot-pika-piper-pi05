# 控制节点

此目录将迁移并整理：

- `piper_readonly_feedback_node.py`：S08 仅接收 SocketCAN 的分侧反馈节点；不导入 SDK、
  不注册控制入口、不发送 CAN 帧

`launch/s09_single_arm_driver.launch` 封装外部 `piper` 包，并将命令、反馈和服务放入
选择侧的命名空间。直接遥操作由 `pi05_left_teleop` 包实例化厂商 FK/IK/teleop 组件。
