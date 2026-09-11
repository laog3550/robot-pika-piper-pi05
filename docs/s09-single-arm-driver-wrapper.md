# S09 通用单臂驱动封装

S09 为官方 Piper ROS 单臂节点提供统一的左右侧 launch 边界。它不复制上游源码，也不
改变上游驱动行为。

## 安全边界

`s09_single_arm_driver.launch` 要求显式提供 `side:=left|right`。默认
`start_driver:=false`，因此普通启动只校验参数，不创建驱动节点：

```bash
source /opt/ros/noetic/setup.bash
source devel/setup.bash
roslaunch pi05_control s09_single_arm_driver.launch side:=left
```

只查看左右展开后的节点名称而不执行节点：

```bash
source /opt/ros/noetic/setup.bash
roslaunch --nodes src/pi05_control/launch/s09_single_arm_driver.launch \
  side:=left start_driver:=true
roslaunch --nodes src/pi05_control/launch/s09_single_arm_driver.launch \
  side:=right start_driver:=true
```

预期分别只有 `/left_arm/piper_driver_raw` 和 `/right_arm/piper_driver_raw`。

不要在 S09 执行 `start_driver:=true`。固定的官方上游节点即使
`auto_enable=false`，构造时仍会连接 CAN 并发送一次 `MotionCtrl_2`；该参数只禁止自动
使能，不代表节点是只读的。真机启动留待固件兼容性、工作区、急停和分侧低速条件满足
后的阶段。

## 参数映射

| `side` | 默认 CAN | 命名空间 |
|---|---|---|
| `left` | `left_piper` | `/left_arm` |
| `right` | `right_piper` | `/right_arm` |

`side` 是 CAN 与命名空间的唯一选择源；两者不暴露可覆盖参数，防止左侧选择连接右侧
CAN。`side` 遗漏或非法时会在 launch 展开阶段失败。`auto_enable` 固定为 `false`，
不能从命令行覆盖。

## 原始接口

以下名称全部相对于所选 `/left_arm` 或 `/right_arm` 命名空间：

| 方向 | 接口 |
|---|---|
| 命令订阅 | `joint_ctrl_raw`、`pos_cmd_raw`、`enable_flag_raw` |
| 反馈发布 | `joint_states_driver_raw`、`arm_status`、`end_pose_raw`、`end_pose_euler_raw` |
| 原始服务 | `enable_srv_raw`、`stop_srv_raw`、`gripper_srv_raw`、`reset_srv_raw`、`go_zero_srv_raw`、`block_arm_raw` |

这些接口只是名称隔离，不是访问控制。任何向命令订阅或原始服务写入的行为都可能引起
机械臂动作；S11 以前不得作为公开运维 API。

## 依赖来源

封装目标是 `agilexrobotics/piper_ros@ac41fcbcdda598f01b51cf6175ed9a24d0dacadc`
中的 `src/piper/scripts/piper_ctrl_single_node.py`。仓库根许可证为 MIT；本项目只引用 ROS
包和节点名称，不复制源码或许可证正文。当前 `/home/mips/pika_ros` 中的历史内嵌副本
仅用于差异审查，不属于部署来源。

官方 ROS 包名 `piper` 没有 Noetic rosdep 键，并且默认 `start_driver=false` 不需要加载
它，因此不把它伪装成基础环境的强制 package.xml 依赖。只有未来显式启动驱动时，才须
先从固定 commit 构建并 source 独立的官方 overlay；历史参考 install 空间不能替代它。
