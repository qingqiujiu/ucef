# OpenCode Agent 配置

本包新增主 Agent `ucef-java-chain`，文件位于 `.opencode/agents/ucef-java-chain.md`。它不绑定具体模型，方便在 OpenCode 中选择你当前可用的模型。

## 安装关系

建议准备一个独立的 OpenCode 控制目录，把本包中的整个 `.opencode/` 复制进去：

```text
java-analysis-controller/
└── .opencode/
    ├── agents/
    │   └── ucef-java-chain.md
    └── skills/
        └── ucef/
            └── SKILL.md
```

这个控制目录只负责让 OpenCode 发现 Agent 和 Skill，不是 UCEF 分析工作区，也不是任何 Java 项目。UCEF 分析工作区继续使用单独的绝对路径；多个 Java 项目仅作为注册后的只读数据源。

## `padb` Skill

Agent 启动时会显式加载名为 `padb` 的 Skill。保证它能被 OpenCode 发现即可，推荐放在全局位置：

```text
~/.config/opencode/skills/padb/SKILL.md
```

也可放在控制目录的 `.opencode/skills/padb/SKILL.md`。目录名、Skill 的 `name` 和 Agent 中使用的 ID 都应为 `padb`。

## `index-mcp` MCP

Agent 已显式启用工具通配符 `index-mcp_*`。你的 OpenCode 配置中必须已经存在且启用了键名为 `index-mcp` 的 MCP 连接，例如把你现有的 IDEA Index MCP 连接保留在全局或控制目录的 `opencode.json` / `opencode.jsonc` 中：

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "index-mcp": {
      // 保留你现有的 type、command/url、environment 等连接参数
      "enabled": true
    }
  }
}
```

本包没有虚构 `command` 或 `url`，因为这取决于你安装的 IDEA 插件和本机启动方式。如果你现有配置的服务器键不是 `index-mcp`，应把 Agent frontmatter 中的 `index-mcp_*` 改成 `<实际服务器键>_*`。

可先运行：

```bash
opencode mcp list
```

确认列表中的服务器 ID 是 `index-mcp` 且可用。

## 使用

在控制目录启动 OpenCode，用 Tab（或你的 Agent 切换快捷键）选择 `ucef-java-chain`。首次可以输入：

```text
只做启动检查：加载 ucef 和 padb，确认 index-mcp 可用，列出状态，不开始业务挖掘。
```

通过后，再给出 UCEF 工作区绝对路径、要分析的入口/场景和相关 Java 项目路径。

## 权限说明

Agent frontmatter 使用 `permission: allow`，并显式启用 `index-mcp_*`。这会取消 OpenCode 的逐次授权询问；Agent 的系统提示仍约束 Java 源码和生产数据库为默认只读，分析产物只写入独立 UCEF 工作区。

