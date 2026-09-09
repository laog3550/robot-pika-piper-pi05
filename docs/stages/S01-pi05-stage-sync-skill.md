# S01 PI05 阶段成果同步 Skill

## 目标

建立仓库级 `$pi05-stage-sync`，使 Codex 在完成可验收的 PI05 阶段任务后，能够保护
既有改动、整理阶段文档，并通过独立分支和 PR 发布成果。

## 完成内容

- 定义自动与显式触发条件、发布门禁和阻塞条件。
- 定义阶段编号、状态、验证等级、文档和 Git/PR 约定。
- 增加只读预检脚本，核对目标仓库、`origin/main`、变更范围与危险文件。
- 启用仓库级隐式调用，并提供 `$pi05-stage-sync` 默认提示。

## 接口与兼容性

- 显式调用接口：`$pi05-stage-sync`。
- 自动匹配范围仅限 `laog3550/robot-pika-piper-pi05` 的阶段实现、迁移、修复与验收。
- 发布分支固定为 `stage/SNN-<lowercase-slug>`，目标分支固定为 `main`。
- 不修改 ROS 节点、消息、话题、服务或真机运行参数。

## 验证记录

- `quick_validate.py .agents/skills/pi05-stage-sync`：通过，技能 frontmatter、命名和
  UI 元数据有效。
- `PYTHONPYCACHEPREFIX=/tmp/pi05-skill-pycache python3 -m py_compile
  .agents/skills/pi05-stage-sync/scripts/preflight.py`：通过。
- 临时 Git 仓库预检：正确 HTTPS origin 返回 0；错误 origin 返回 2；SSH origin
  能正确归一化；已有用户改动被报告但未删除；越界文件和 `build/output.log` 同时
  阻塞发布，返回 2。
- 触发边界人工核对：“迁移右臂安全过滤并验证”匹配；“解释滤波参数”、只读审查和
  状态查询被 description 排除；失败测试和缺少真机证据由发布门禁阻塞。

## 真机证据

未执行，也不需要执行。本阶段只增加 Codex 工作流和只读仓库检查，不改变机械臂行为。

## 风险与限制

- Skill 仅在 Codex 处理匹配任务时运行，不是监控外部文件变化的后台服务。
- PR 由用户人工合并；存在开放阶段 PR 时，下一阶段发布会被阻塞。
- 预检能识别危险文件名和范围污染，但不能替代人工 diff、凭据和许可证审查。

## 回滚方式

关闭对应 PR 或回退该阶段提交即可移除技能；该阶段不包含数据库、设备或运行环境迁移。

## 来源与许可证

- 结构和元数据约定依据 OpenAI Skills 文档与系统 `skill-creator` 指南编写。
- 代码为本项目新编写，未复制 `pika_ros`、`PikaAnyArm` 或其他第三方源码。
