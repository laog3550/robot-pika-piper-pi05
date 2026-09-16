# Piper 反馈解码只读核查（2026-09-16）

## 结论

未发现项目与固定厂商 SDK 的关节反馈解码差异；此前“现场几乎没动”与大幅反馈变化
的差异尚未闭环。当前采样没有再次切换模式，不能还原上次瞬态或确定其原因。

## 本地代码与版本

- SDK 0.6.1，源码 checkout 为清单固定的 `081e7c588e5b79eeaefa67a0469bcc701c81014f`，
  无源码改动；安装的 V2 协议文件与该 checkout 的 SHA-256 一致。
- 项目和 SDK 均把 0x2A5、0x2A6、0x2A7 映射为 J1/J2、J3/J4、J5/J6。
- 两者均读取两个大端有符号 int32，以 0.001° 为单位；转 rad 的系数为 π/180000。
- 上次临时测试代码使用相同 ID、格式和系数；J1 增量 57 单位为 0.000994838 rad。
- 离线测试覆盖三个反馈帧各四组正负值／int32 边界向量，以及三组厂商 JointCtrl
  编码帧，确认编码保留六关节目标值。浮点乘法顺序在 int32 极值有极小舍入差异。
- 固定厂商 ROS 驱动反馈使用 `0.017444` 而非精确 π/180，约有 0.053% 相对误差。
  上次直接 SDK 测试不经过该驱动，不能用此误差解释本次现象。

## 同帧真机对比

新增 `scripts/check_piper_feedback_decoding.py`，只接收 SocketCAN，将每个关节帧
分别交给项目解码器和 SDK 纯协议解析器；不创建 SDK 设备接口，不发送查询或指令。

```bash
source .venv/bin/activate
python scripts/check_piper_feedback_decoding.py left --duration 5
python scripts/check_piper_feedback_decoding.py right --duration 5
python tests/test_piper_feedback_decoding.py
```

| 项目 | 左臂 | 右臂 |
|---|---|---|
| 三类关节帧样本 | 各 1000 | 各 1000 |
| 解码不一致／畸形关节帧 | 0／0 | 0／0 |
| 最大解码差（rad） | 0 | 6.94e-18 |
| 六轴窗口反馈范围 | 全部为零 | 全部为零 |
| 电机状态 | 六轴 disabled | 六轴 enabled |
| 状态 | 待机、急停、MOVE_J | 待机、急停、MOVE_J |

同帧对比避免不同接收线程的时差；协议解码一致只证明软件按同一方式解释字节，
不证明设备字节代表的物理参考正确。

## 固件与参考值方向

历史 2026-09-14 查询记录两侧均为 S-V1.8-2，本次没有重新发送固件查询。
[piper_sdk issue #114](https://github.com/agilexrobotics/piper_sdk/issues/114)
报告该固件在 MOVE_J → MIT → MOVE_J 后发生关节零点／参考重建。
[pyAgxArm discussion #58 厂商答复](https://github.com/agilexrobotics/pyAgxArm/discussions/58)
确认该版本存在零点／参考重建、主从状态复发等已知问题。
本次没有执行 MIT 切换，因此这些材料只能支持进一步核查参考状态，不能证明同一触发路径。
维持现有不升级固件的决定，没有修改模式、主从、零点、限位或安装配置。

## 后续证据缺口

上次未保存按时间关联的原始目标／反馈帧和全过程状态，无法只靠统计摘要证明
变化发生在 resume、模式命令、目标执行还是停止阶段。后续如再进行经授权的测试，
应先启动被动记录，将目标编码、模式状态、六轴反馈与现场运动观察关联；不能直接
放宽反馈阈值或把数值变化认定为物理运动。

本次两项新离线测试、既有六项反馈测试及只读节点契约检查通过。
