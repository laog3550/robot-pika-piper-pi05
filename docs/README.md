# 部署文档

文档按真机部署顺序维护。当前已形成以下阶段基线：

- [硬件清单](hardware-inventory.md)：目标拓扑、待确认实物与脱敏现场采集命令
- [软件环境清单](software-environment.md)：支持平台、依赖、参考 SHA 与版本采集命令
- [ROS 接口矩阵](ros-interface-matrix.md)：右臂话题、服务、参数、单位与旁路风险
- [安全约束](safety-constraints.md)：不可妥协约束、状态机、缺口与阶段门禁
- [上游依赖基线](upstream-dependencies.md)：S03 来源、commit、依赖图、许可证与 VCS 清单

后续文档将按真机部署顺序维护：

1. 硬件清单与接线
2. PI05 系统和 ROS 环境安装
3. 上游依赖及版本固定
4. CAN、串口和 udev 持久化配置
5. ROS 节点、话题与服务检查
6. 安全策略和故障处理
7. 低速真机调试步骤
8. 验收清单与部署回滚

[architecture.md](architecture.md) 保留为控制链路概览；S02 四份文档是当前详细基线。所有会引起机械臂运动的步骤必须标明前置条件、预期现象、停止方法和失败回滚方式。
