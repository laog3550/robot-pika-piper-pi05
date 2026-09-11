# 第三方依赖

S03/S07 依赖盘点见 [上游依赖基线](../docs/upstream-dependencies.md)，可审计源码的精确获取清单位于 [`pi05-upstream.repos`](pi05-upstream.repos)。

本目录只保存来源和版本描述，不保存第三方源码副本。VCS 清单应导入到项目目录之外的源码缓存；任何源码进入本仓库前仍需完成许可证、版权声明和修改记录审查。

此清单同时包含“历史行为参考”和“批准的候选上游”，不能把整个导入目录直接作为
catkin 工作区：`PikaAnyArm` 内含一份来源未闭合的 Piper ROS 副本，而清单另行固定了
官方 `piper_ros`。实际部署只能选择文档中批准的单一实现，禁止形成重复 ROS package。

`pika_locator` 没有可验证的源码 URL/commit，明确排除在清单和批准部署路径之外。参考
工作区中的预编译包及 `install.zip` 不得复制或对外分发。S07 固定的 `libsurvive` 只是
后续定位适配的许可证明确底层候选，不是 `pika_locator` 的等价替换，也不代表 S08 已通过。
