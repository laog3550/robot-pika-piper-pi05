# 包级测试

计划覆盖：

- 死区与低通计算
- 最大关节/夹爪步长限制
- 未使能和未开始会话时拒绝命令
- 定位丢失与命令超时
- disable/enable 清除旧目标
- 回到会话起始姿态的插值与中断
- JointState 长度、名称和异常输入处理

优先使用不连接真机的单元测试和 ROS 回放测试。

当前已有：

- `test_piper_feedback.py`：S08 Piper 原始反馈端序、单位和完整帧组。
- `test_single_arm_driver_launch.py`：S09 必填 side、安全默认值及全部驱动接口分侧 remap。
