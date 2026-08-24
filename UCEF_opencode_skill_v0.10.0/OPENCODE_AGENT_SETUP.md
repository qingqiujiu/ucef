# OpenCode Agent 配置

本包使用一个主 Agent、三个固定角色子 Agent和一个项目级自定义工具文件。OpenCode 从控制目录的 `.opencode/agents/`、`.opencode/tools/` 与 `.opencode/skills/` 发现它们。

## 前置条件

1. Python 3.10+ 可用；非 `python` 命令时设置 `UCEF_PYTHON`。
2. `index-mcp` 已在 OpenCode 中连接 IDEA 索引。
3. 用户的 `padb` Skill 已安装；仅 Block Worker 在确有生产配置/数据库问题时加载。
4. UCEF 分析工作区和全部 Java 项目是互不嵌套的目录。

## 权限模型

主 Agent 使用 `permission: allow`，但提示词只允许调用 `ucef_control_*` 和固定角色委派。三个子 Agent 均禁止文件编辑、命令执行和再次委派：

- Planner 只能提交 Plan；
- Block Worker 只能提交一个 Block 或显式 Gap；
- Finalizer 只能提交 Overview，且源码索引关闭。

Runtime 再次检查 task ID、角色、字段结构、数量预算、最终覆盖和重复提交。模型即使偏离提示，也不能通过正式入口新增层级或超预算任务。

## 启动用语

```text
使用 ucef-java-chain 分析 SCN-PAY，UCEF 工作区是 D:/ucef/order-analysis，采用 STANDARD。Java 项目只读，按 Runtime 队列执行，完成后给我 HTML 路径、块完成数、Gap 和停止原因。
```

不要把“分析整个系统”交给 UCEF。每次以一个有入口、条件和预期结果的 Scenario 为单位；已分析知识由 SQLite 按条件复用。
