# UCEF 持续开发版 for OpenCode

`UCEF_opencode_skill/` 是随 Git 持续更新的唯一开发目录，不再为每次修改创建新的版本文件夹。历史 `UCEF_opencode_skill_v*` 目录和发布包只作为快照保留。

本版以大模型推理和 Obsidian Markdown 为核心：主模型理解业务全链路、重要字段生命周期和方法细节；轻量工具只保存调查状态、断点并校验链接，不建立事实图，也不生成 HTML。

## 安装

把本目录作为 OpenCode 控制目录使用，或将其中 `.opencode/` 合并到现有控制目录：

```text
UCEF_opencode_skill/
└── .opencode/
    ├── agents/
    │   ├── ucef-java-chain.md
    │   └── ucef-probe.md
    ├── tools/
    │   └── ucef.ts
    └── skills/
        └── ucef/
```

后续在仓库中执行 Git 更新即可获得同一路径的新内容。若安装位置是复制出来的控制目录，需要再次同步 `.opencode/`；不要再复制到新的版本号目录。

运行时仅要求 Python 3.10+ 标准库。若 Python 命令不是 `python`，设置 `UCEF_PYTHON`。TypeScript 工具与 Python 之间固定使用 UTF-8。

## Obsidian 分析目录

为每项分析选择 Obsidian Vault 内的一个目录，例如：

```text
D:/ObsidianVault/UCEF/订单处理分析
```

它就是 UCEF 工作区，不再另外创建 SQLite、站点、运行队列等目录。源码项目可以位于其他路径，并始终保持只读。

在 OpenCode 中选择 `ucef-java-chain`，给出分析目录、源码范围和业务目标。主 Agent 会按需调用 `ucef_workspace_init`，创建：

```text
分析首页.md
业务全链路.md
字段生命周期.md
方法明细/
证据库.md
调查工作台.md
附件/
.ucef/state.json
```

已有文件不会被初始化覆盖。

## 轻量工具

- `ucef_workspace_init`：创建或恢复最小 Obsidian 分析目录。
- `ucef_state_read`：默认只读取当前焦点、关键未知和最近检查点。
- `ucef_state_update`：理解改变时原子更新 JSON 状态。
- `ucef_state_checkpoint`：中断或切换重点前保存恢复摘要。
- `ucef_workspace_validate`：检查 UTF-8、状态引用、Wikilink 和块锚点。

工具不判断业务对象、不计算覆盖率、不决定分析重点，也不生成正文。

## Obsidian MCP

主 Agent 默认允许 `obsidian_*` 和 `mcp_obsidian_*`。如果你的 MCP 工具前缀不同，请修改 `.opencode/agents/ucef-java-chain.md` 中的权限模式。没有 Obsidian MCP 时，主 Agent可用普通文件工具写入分析目录。

## 直接诊断

必要时可以直接调用脚本；Agent 正常分析不需要阅读脚本用法：

```bash
python .opencode/skills/ucef/scripts/ucef_state.py --workspace D:/ObsidianVault/UCEF/订单处理分析 init --goal "理解该业务的完整执行链路"
python .opencode/skills/ucef/scripts/ucef_state.py --workspace D:/ObsidianVault/UCEF/订单处理分析 status
python .opencode/skills/ucef/scripts/ucef_state.py --workspace D:/ObsidianVault/UCEF/订单处理分析 validate
```

## 与旧版本的关系

这是一次架构重写，不直接读取旧版 SQLite 事实图，也不会覆盖旧工作区。需要复用旧结论时，将真正有价值的结论与证据人工迁入新的 Obsidian 笔记；不要把旧实体库存整体转换过来。
