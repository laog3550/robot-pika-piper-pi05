# 运维脚本

此目录预留以下脚本，脚本实现后必须支持 `--help`，失败时返回非零状态码：

- `bootstrap_ubuntu.sh`：安装系统与 ROS 依赖
- `configure_can.sh`：按接口或 USB bus-info 配置 1 Mbps CAN
- `check_hardware.sh`：只读检查 CAN、串口、ROS 和反馈
- `start_pi05.sh`：按安全顺序启动
- `stop_pi05.sh`：停止命令源、禁用机械臂并退出节点
- `collect_diagnostics.sh`：采集版本、节点、话题、CAN 错误和日志

机器唯一参数从 `config/pi05.env` 读取，不写入脚本。涉及 `sudo`、网络接口或进程终止的动作必须打印目标并进行严格校验。
