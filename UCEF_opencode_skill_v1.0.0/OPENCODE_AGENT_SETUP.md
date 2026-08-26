# OpenCode Agent 配置：UCEF 1.0

OpenCode 从控制目录的 `.opencode/agents/`、`.opencode/tools/` 与 `.opencode/skills/` 发现 UCEF 主 Agent、可选窄问题 Agent、运行时工具和技能。

## 前置条件

1. Python 3.10+ 可用；必要时设置 `UCEF_PYTHON`。
2. `index-mcp` 已连接 IDEA 的 Java 语义索引。
3. UCEF 工作区与所有 Java 项目都是互不嵌套的独立目录。
4. `padb` 可不存在；缺少可信生产配置时按 `CONFIG_UNRESOLVED` 显示。

## 权限与职责

`ucef-java-chain` 是默认主 Agent：直接访问只读 `index-mcp_*`、`ucef_analysis_*`、`ucef_knowledge_*`、`ucef_configuration_*` 和工作区/场景/制品工具。它保留全局业务上下文，自主理解代码，再提交小型事实增量。

`ucef-probe` 是可选 subagent，只用于一个真正独立的窄问题。它只能用只读索引查询，不能修改文件、写数据库、创建任务或再次委派；默认主流程不依赖它。

所有其他操作默认拒绝。主 Agent 不拥有旧 `ucef_control_*` 或 `ucef_submit_*` 权限，因此不会退回 Planner → Block → Finalizer 流水线。

如果你的 OpenCode MCP 注册键不是 `index-mcp`，同步修改两个 Agent frontmatter 中的 `index-mcp_*` 权限模式。

## 启动示例

```text
使用 ucef-java-chain 分析 SCN-PAY。
UCEF 工作区是 D:/ucef/order-analysis，Java 项目只读。
重点理解多个业务决策分支，并完整追踪 amount 与 paymentChannel 从请求到落库和外部系统。
padb 当前不可用，生产配置保持待确认；不要分析日志。
完成后告诉我业务结论、关键分支、配置缺口和 HTML 入口。
```

不要要求模型直接生成 HTML、Mermaid 或固定长度报告；站点和离线图表由 Runtime 根据事实自动渲染。
