# UCEF 持续开发版 for OpenCode

`UCEF_opencode_skill/` 是随Git持续更新的唯一开发目录。历史 `UCEF_opencode_skill_v*` 和发布包只作为快照保留，后续修改不再创建新的版本文件夹。

本版没有自定义 Runtime、Python脚本、SQLite、JSON提交协议或HTML生成器。UCEF是一套强业务分析提示词，直接使用已经安装的 `index-mcp` 与 `obsidian-mcp`：前者提供源码事实，后者承载持续笔记、图形与断点恢复；遇到源码无法确认的数据库问题时，按需加载用户已有的 `padb` Skill。

## 安装内容

将 `.opencode/` 合并到OpenCode控制目录，或直接把本目录作为控制项目：

```text
UCEF_opencode_skill/
└── .opencode/
    ├── agents/
    │   ├── ucef-java-chain.md
    │   └── ucef-probe.md
    └── skills/
        └── ucef/
            ├── SKILL.md
            └── references/
```

后续在仓库中更新Git即可得到同一路径的新内容。如果使用复制方式安装，只需同步 `.opencode/` 到原控制目录，不要创建新的版本号目录。

## 前置能力

- `index-mcp`：能够定位符号、定义、实现、引用、调用关系和精确源码区段；
- `obsidian-mcp`：能够搜索、读取、创建和局部更新笔记，并支持Wikilink、块引用与Mermaid；
- `padb`（可选）：能够按自身说明只读查询数据库，用于必要的配置、元数据和运行数据佐证；
- 如果 `obsidian-mcp` 只读，需要已有 Obsidian Skill/CLI 提供写入能力；
- Obsidian Vault中的一个分析目录；
- 源项目只读。

OpenCode中MCP工具通常以服务器名作为前缀。本版 Agent 默认直接允许：

```text
index-mcp_*
obsidian-mcp_*
```

其他未知工具默认询问授权，以兼容 `padb` 或 Obsidian CLI 的实际实现。若你的 MCP 注册名不同，只修改 `.opencode/agents/*.md` frontmatter 中的权限前缀；若希望数据库查询不逐次询问，把 `padb` 自身文档要求的最小只读工具权限合并进去。不要为匹配名称重新包装一层 UCEF 工具，也不要改成全局无条件允许。

## 启动

选择 `ucef-java-chain`，给出：

- Obsidian分析目录或目标Vault位置；
- 源码范围；
- 用户真正关心的业务问题；
- 已知入口、重点字段或限制条件（如果有）。

示例：

```text
使用 ucef-java-chain 分析这项业务。
分析笔记写入 Obsidian 的 UCEF/本次分析。
源码通过当前 index-mcp 只读访问。
需要数据库事实时加载 padb，并严格保持只读和最小范围。

请从业务视角解释完整链路、关键分支为什么发生、重要字段的完整生命周期，
识别关键模块，并让主链中的每个方法都能跳转到详细笔记。
根据真实关系生成有助于理解的时序图、流程图、状态图、ER图或字段流转图；
无法确认的运行条件和关系明确保留为未知。
```

主Agent会先用 `obsidian-mcp` 查找 `调查状态.md`。已有分析从恢复胶囊继续；新分析只创建最小入口，再随着理解增加笔记。

开始大规模检索前，主 Agent 会先确认 Obsidian 确实存在可写路径，避免分析结果只停留在易丢失的聊天上下文中。

## 推荐笔记

不要求一次性创建完整目录。最终通常包括：

```text
分析首页.md
调查状态.md
业务全链路.md
字段生命周期.md
关键模块.md
方法明细/...
证据库.md
```

这些是阅读入口，不是必须填满的输出Schema。内容规模和拆分方式由模型根据实际业务决定。

## 更新与迁移

Skill更新只需要Git拉取或重新同步 `.opencode/`。分析成果始终留在Obsidian中，不受Skill目录更新影响。

旧版SQLite/HTML工作区不会自动转换。需要复用时，将真正有价值且能够重新验证的结论链接或迁入Obsidian；不要把旧实体库存整体导入。
