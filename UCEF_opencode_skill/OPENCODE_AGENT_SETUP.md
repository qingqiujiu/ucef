# OpenCode Agent 配置

默认选择 `ucef-java-chain`。它负责全局理解、Obsidian 笔记和唯一状态写入；`ucef-probe` 只在主 Agent 明确委派时调查一个独立问题。

## 所需能力

- `index-mcp_*` 或等价的源码语义索引；
- `obsidian_*` / `mcp_obsidian_*`，或普通文件读写能力；
- `ucef_*` 轻量状态工具；
- Python 3.10+。

实际 MCP 名称不同时，只调整 Agent frontmatter 中的权限前缀，不修改 Skill 的分析原则。

## 启动示例

```text
使用 ucef-java-chain 分析这项业务。
Obsidian 分析目录：D:/ObsidianVault/UCEF/示例分析。
源码范围：由当前 index-mcp 提供，只读。

请从业务视角形成完整链路，识别并追踪真正重要字段的完整生命周期。
主链中出现的每个方法都要能跳转到详细分析；未确认内容保持显式状态。
```

不要要求固定数量的章节、实体、字段或子任务。图形类型由模型根据实际内容选择。
