# 控制节点

此目录将迁移并整理：

- `piper_readonly_feedback_node.py`：S08 仅接收 SocketCAN 的分侧反馈节点；不导入 SDK、
  不注册控制入口、不发送 CAN 帧

S09 不复制上游 Piper 控制脚本；`launch/s09_single_arm_driver.launch` 仅封装外部 `piper`
包，并将其所有命令、反馈和服务放入选择侧的内部命名空间。

- `arm_safety_filter_node.py`：S10 通过必填 `side` 为左右臂复用同一过滤、限速、看门狗、
  故障锁存和状态桥；不调用驱动服务，不发布原始驱动入口
- `arm_joint_state_bridge.py`：将指定侧 Piper 反馈关节名适配到对应 URDF，仅用于状态/可视化
- `dual_arm_safety_coordinator.py`：汇总双侧状态并拥有公开 enable/stop 接口

迁移时必须消除右侧硬编码，以同一实现实例化左右链路，并补齐 package.xml/CMakeLists.txt 依赖和跨侧故障测试。
