# 控制节点

此目录将迁移并整理：

- `arm_command_filter.py`：通过私有参数和 remap 为左右臂分别提供过滤、限速、看门狗和安全会话状态
- `arm_joint_state_bridge.py`：将指定侧 Piper 反馈关节名适配到对应 URDF，仅用于状态/可视化
- `dual_arm_safety_coordinator.py`：汇总双侧状态并拥有公开 enable/stop 接口

迁移时必须消除右侧硬编码，以同一实现实例化左右链路，并补齐 package.xml/CMakeLists.txt 依赖和跨侧故障测试。
