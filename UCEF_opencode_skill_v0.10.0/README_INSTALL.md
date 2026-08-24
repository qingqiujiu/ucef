# UCEF v0.10.0 for OpenCode

v0.10.0 把一次 Java 接口分析收敛为三层直接产物：ScenarioPlan、若干 BusinessBlock、ScenarioOverview。子 Agent 直接经校验工具写入 SQLite，父 Agent 只接收 receipt；HTML 随每次提交增量更新。

## 安装

把本包的整个 `.opencode/` 放入一个 OpenCode 可发现的控制目录。这个目录不是 UCEF 分析工作区，也不是 Java 项目：

```text
java-analysis-controller/
└── .opencode/
    ├── agents/
    │   ├── ucef-java-chain.md
    │   ├── ucef-planner.md
    │   ├── ucef-block.md
    │   └── ucef-finalizer.md
    ├── tools/ucef.ts
    └── skills/ucef/
```

运行时要求 Python 3.10+，只使用标准库。若命令不是 `python`，在 OpenCode 环境中设置 `UCEF_PYTHON` 为 Python 可执行文件绝对路径。

## 初始化独立工作区

```bash
python .opencode/skills/ucef/scripts/init_workspace.py --workspace D:/ucef/order-analysis
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis source-add --source-id gateway --path D:/repos/gateway
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis source-add --source-id order-core --path D:/repos/order-core
```

把场景文件放到 `scenarios/` 并登记：

```bash
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis scenario-put --file scenarios/pay.json
```

随后在 OpenCode 选择 `ucef-java-chain`，提供工作区绝对路径和 scenario ID。默认 STANDARD 的硬上限是 6 次模型任务、30 分钟；DEEP 必须由用户明确选择。

## Agent 与工具职责

- `ucef-java-chain`：只启动、取下一任务、派发固定角色并接 receipt；不能转写结果或自行增加任务。
- `ucef-planner`：8 steps，建立一次业务骨架。
- `ucef-block`：12 steps，最多 6 次定向检索，完成一个可直接展示的业务块。
- `ucef-finalizer`：5 steps，只读压缩后的业务块，形成一次全局总览。
- `.opencode/tools/ucef.ts`：把最终 JSON 通过 stdin 交给 Runtime 校验、事务入库、幂等回执和增量 HTML。

详细字段与停止条件见 `.opencode/skills/ucef/references/DIRECT_ANALYSIS_CONTRACT.md`。

## index-mcp 与 padb

Planner 和 Block Worker 启用 `index-mcp_*`，用于 IDEA 语义检索。Block Worker 只有遇到生产选路或数据库映射问题时才加载用户已有的 `padb` Skill，并且只查询当前块的问题。Finalizer 禁用源码索引，也不得查询 padb。

你的 OpenCode MCP 键应为 `index-mcp`；若实际键不同，修改两个 Worker frontmatter 中的通配符。`padb` 应安装在 OpenCode 能发现的 Skill 目录。

## 手工诊断命令

```bash
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis doctor
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis analysis-status --run-id RUN-...
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis site
```

默认结果位于 `D:/ucef/order-analysis/site/index.html`。旧版 Work Unit、Checkpoint 和 layered result 仍可导入，但不再是新分析的默认流程。
