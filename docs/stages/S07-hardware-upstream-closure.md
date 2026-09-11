# S07 双侧硬件与上游闭环

## 目标

在不迁移控制代码、不发送 CAN/串口命令、不使能和不运动机械臂的前提下，形成左右
Piper 型号/固件、接线、供电、急停、安装与负载的可审计现场记录，并通过选择许可证
明确的官方候选或排除不明确组件，解除 S03 对后续实现的来源阻塞。

## 完成内容

- 新增 Git 忽略的 S07 本地硬件记录模板及只读校验器，强制左右分侧、双人复核、急停
  覆盖、静态共享空间评审、无运动和敏感标识省略。
- 新增现场清单，明确断电终端测量、型号手册判据、带电但禁用的急停状态检查和失败
  停止条件；仓库不预填电源、接地或终端默认值。
- 将来源不明的 `pika_locator`、内嵌 Piper ROS 和许可证冲突的 `pika_sdk` 排除出批准
  部署路径；不复制相应源码或二进制。
- 固定官方 Noetic `piper_ros@ac41fcbc...` 与 MIT `libsurvive@f1e6eddb...` 供后续阶段
  审查，保留历史仓库仅作行为参考，并禁止把完整审计缓存直接作为 catkin 工作区。

## 接口与兼容性

本阶段不新增 ROS 接口。`scripts/check_s07_hardware.sh [--config PATH]` 只读取本地记录，
不访问 CAN、串口或 ROS。官方 Piper ROS 明确区分固件 `S-V1.6-3` 前后的 URDF，因此
左右固件值与对应模型选择必须在进入驱动封装前确认。

`libsurvive` 只是定位底层候选，不提供旧 `pika_locator` 的 ROS 接口兼容承诺。S08 必须
单独实现或选择许可证明确的适配并验证左右定位身份、坐标语义、频率和断流行为。

## 验证记录

验证日期：2026-09-11。

- `.agents/skills/pi05-stage-sync/scripts/preflight.py --mode start ...`：通过；仓库、base、
  工作区和远端一致，无预存改动。
- GitHub 开放 PR 查询：没有开放的 `stage/*` PR。
- `tests/test_s07_hardware.sh`：通过；覆盖完整记录、双人复核、失败安全项、危险配置文本
  和疑似敏感数字标识拒绝。
- `scripts/check_upstream_manifest.sh`：通过；六个仓库均使用受限清单结构和完整 commit。
- `scripts/check_upstream_manifest.sh --remote`：通过；六个固定 commit 均可从远端获取，
  且各自存在根 `LICENSE`。该检查替代在本机 `python3-vcstool 0.3.0` 上对完整 SHA
  异常的 `vcs validate`。
- `tests/test_environment_scripts.sh`：通过；仅有上游 MoveIt metapackage 依赖警告。
- `tests/test_device_configuration_scripts.sh`：通过。
- `tests/test_upstream_manifest.sh`：通过；可移动 ref 和未知字段均被拒绝。
- `bash -n scripts/*.sh scripts/lib/*.sh tests/*.sh`：通过。
- `git diff --check`：通过。

当前最高验证等级为真机（仅覆盖左右机械臂型号与既有 S06 设备映射）。完整现场记录未
完成前，状态保持“等待真机验收”。

## 真机证据

2026-09-11，现场人员已分侧核对两台机械臂铭牌：左右侧品牌/制造商均为
AGILE·X / 松灵，型号均为 PIPER；用户随后指定厂商知识库的“PIPER 标准版使用资料”
目录作为这两台设备的资料入口。该目录链接的 `PIPER 机械臂用户手册` 标记为 V2.0.0，
官方产品页给出的标准版规格包括 6 轴、1.5 kg 有效负载、4.2 kg 本体、626 mm 工作半径
和 DC 24 V。仓库只保留产品级结论；铭牌上的序列号、联系电话及详细地址未录入。

上述信息关闭 H-02 的机械臂版本系列，并为 H-09 提供型号级额定电压。现场人员进一步
确认左右机械臂各使用一台独立 DC 24 V、10 A、240 W 电源，额定输出按侧记录。
当前仍未确认两侧电源保护或接地，也没有确认 Piper 固件、夹爪型号、接线终端、急停、
安装、实际负载或共享空间；本次没有执行设备命令、使能或运动。

S06 已取得的双侧 CAN/Pika 身份绑定和 CAN 1 Mbps 证据同样不能替代上述剩余验收项。

现场人员须继续按 `docs/s07-field-acceptance.md` 填写 Git 忽略的
`config/s07-hardware.env`，运行 `scripts/check_s07_hardware.sh`，并只回传脚本的脱敏结果。
任一剩余字段未知或失败时不进入 S08。

## 风险与限制

- 记录校验通过只证明字段完整和现场结论明确，不替代厂商手册、测量真实性或安全责任。
- 旧版 Pika 手册没有补足 `pika_locator` 的源码和许可链，并包含不接受的全目录 0777
  权限步骤；不得照搬。
- 官方 `pika_sdk` 当前根 LGPL-3.0 与打包元数据 MIT 声明冲突，上游澄清前仍排除。
- 官方 Piper ROS 根许可证明确，但部分 package.xml 元数据仍不一致；后续只取批准的包，
  并保留根许可证及所有第三方声明。
- 本阶段没有验证定位、CAN 帧、ROS 反馈、驱动启动或任何运动能力。

## 回滚方式

代码回滚只需撤销本阶段原子提交。本地 `config/s07-hardware.env` 不受 Git 回滚影响；如
不再需要，可由现场人员自行保留或删除。该文件不修改系统、udev、CAN 或机械臂状态。

## 来源与许可证

- `agilexrobotics/piper_ros@ac41fcbcdda598f01b51cf6175ed9a24d0dacadc`：根 MIT；Noetic
  官方部署候选。
- `cntools/libsurvive@f1e6eddb669320f2a30760f4b42936bdb4306da0`：根 MIT；定位底层
  候选，不递归获取未审核子模块。
- `agilexrobotics/pika_sdk@902b476df86c7f140b98dde6254c5d491e002c6a`：根 LGPL-3.0
  与 `setup.py` MIT 冲突，只记录调查结论，不进入 VCS 清单。
- 用户提供的 AgileX 旧版 Pika ROS1 手册：确认旧二进制交付流程，但没有源码 commit 与
  完整许可链；页面内容和链接不复制到公共仓库。
- 用户指定的 AgileX `PIPER 产品使用资料清单-202607`：用于确认两侧为标准版资料系列；
  其中 `PIPER 机械臂用户手册` 标记 V2.0.0。松灵官方产品页用于交叉核对标准版公开规格。

本阶段没有复制任何第三方源码、二进制或许可证正文。
