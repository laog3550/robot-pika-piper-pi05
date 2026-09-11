# S09 通用单臂驱动封装

## 目标

用同一 launch 通过 `side:=left|right` 选择单侧 Piper 驱动，使所有命令、反馈和服务
进入对应 `/left_arm` 或 `/right_arm` 命名空间，并保持默认不启动、禁止自动使能。

## 完成内容

- 新增 `s09_single_arm_driver.launch`，使用不可覆盖的闭集映射从 `side` 同时生成 CAN
  接口和命名空间，防止跨侧组合。
- `start_driver` 默认 `false`；`auto_enable` 固定 `false`，不能由调用方覆盖。
- 将官方驱动的 3 个命令订阅、4 个反馈发布和 6 个服务全部 remap 到分侧内部接口。
- 新增 XML 契约和实际 roslaunch 展开测试，验证缺失/非法 side、安全默认值和左右隔离。
- 修复项目 venv 下 `build_catkin.sh --install` 误用 Debian `--install-layout` 的问题，
  并增加临时工作区安装回归，确保新增 launch 可进入 install space。
- 只引用固定官方包名和节点名，没有复制历史参考或官方上游源码。

## 接口与兼容性

左侧默认 `left_piper`、命名空间 `/left_arm`；右侧默认 `right_piper`、命名空间
`/right_arm`。驱动节点名固定为分侧命名空间内的 `piper_driver_raw`。

原始命令入口为 `joint_ctrl_raw`、`pos_cmd_raw`、`enable_flag_raw`；原始服务以
`*_srv_raw` 命名，官方新增的 `block_arm` 映射为 `block_arm_raw`。反馈保持分侧，其中
驱动关节反馈明确命名为 `joint_states_driver_raw`，不冒充 S08 协议反馈或 URDF 兼容反馈。

## 验证记录

验证日期：2026-09-11。

- `tests/test_single_arm_driver_launch.sh`：通过；左右分别只展开一个预期命名空间节点，
  `start_driver=false` 展开为空，非法 side 失败；测试没有启动节点。
- `/usr/bin/python3 -m unittest src/pi05_control/test/test_single_arm_driver_launch.py`：3 个
  XML/接口契约测试通过。
- `scripts/build_catkin.sh`：通过；基础工作区不依赖历史 Piper install 空间。
- `scripts/build_catkin.sh --install`：通过；使用 venv 兼容布局生成 install space。
- `catkin_make run_tests_pi05_control` 与 `catkin_test_results --verbose`：7 个测试、0 错误、
  0 失败。
- 全部 9 个 `tests/test_*.sh` 仓库级入口：通过。
- `git diff --check`：通过。

## 真机证据

未执行。S09 没有启动官方 Piper 节点，没有调用服务或发布命令，也没有发送 CAN 帧、
使能或运动机械臂。当前证据仅为构建和静态 launch 展开。

## 风险与限制

- 官方固定节点在构造阶段调用 `ConnectPort` 后立即发送 `MotionCtrl_2`；所以
  `auto_enable=false` 不能把它变成只读节点，`start_driver=true` 尚未获得真机批准。
- 分侧 remap 解决名称冲突，但 ROS 1 没有原生访问控制；原始运动入口仍需 S11 协调器
  隔离，不能直接公开。
- S07 尚未取得左右固件与 `piper_sdk` 兼容性记录，也未关闭急停、安装和共享空间缺口。
- 尚未完成 URDF 关节名、方向、零点、限位或命令超时适配。
- 官方 `piper` 没有 Noetic rosdep 键；基础构建不强制加载它。未来显式启动前必须从
  固定官方 commit 构建独立 overlay，不能使用历史参考 install 空间代替部署来源。

## 回滚方式

撤销本阶段提交即可。默认 launch 不启动节点，本阶段没有修改系统配置、CAN 状态或
机械臂状态。

## 来源与许可证

- 部署候选：`agilexrobotics/piper_ros@ac41fcbcdda598f01b51cf6175ed9a24d0dacadc`，
  仓库根 MIT；审查路径 `src/piper/scripts/piper_ctrl_single_node.py` 和
  `src/piper/launch/start_single_piper.launch`。
- 行为对照：`/home/mips/pika_ros/src/PikaAnyArm/piper/piper_ros/piper`，仅只读审查；
  内嵌副本许可证证据不足，未复制、未作为部署依赖。
- 本阶段 launch 和测试为本项目独立实现，没有复制第三方实现或许可证正文。
