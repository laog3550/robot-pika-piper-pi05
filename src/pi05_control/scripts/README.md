# 控制节点

此目录将迁移并整理：

- `right_arm_command_filter.py`：右臂指令过滤、限速、看门狗和安全会话状态
- `right_arm_joint_state_bridge.py`：将 Piper 反馈关节名适配到 URDF，仅用于状态/可视化

迁移时需要消除硬编码话题，改为私有参数与 launch remap，并补齐 package.xml/CMakeLists.txt 依赖。
