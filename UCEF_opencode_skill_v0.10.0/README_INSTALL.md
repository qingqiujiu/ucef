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
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis bootstrap
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis source-add --source-id gateway --path D:/repos/gateway
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis source-add --source-id order-core --path D:/repos/order-core
```

`init_workspace.py` 仍作为兼容入口保留。使用 OpenCode 时无需执行或阅读这些脚本：主 Agent 可直接调用 `ucef_workspace_bootstrap`、`ucef_source_register` 和 `ucef_scenario_register`。

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
- `.opencode/tools/ucef.ts`：封装工作区、数据源、Scenario、制品、站点和提交命令；把最终 JSON 交给 Runtime 校验、事务入库、幂等回执和增量 HTML。

每个 `ucef_control_next` 任务胶囊自带角色专用 `output_contract.payload_template`。Agent 只填写该模板，不读取脚本、完整 Schema 或示例 JSON；run、scenario 和可生成的产物 ID 由 Runtime 注入。结构错误只返回精确字段路径，并且最多允许一次修正。详细合同仅供 Runtime 开发和人工诊断查看。

所有 `ucef_*` 都是 `.opencode/tools/ucef.ts` 注册的本地自定义工具，不属于 MCP。若 Worker 的工具列表中没有对应的 `ucef_submit_plan`、`ucef_submit_block` 或 `ucef_submit_overview`，这是安装或工具发现故障：不要让 Worker 查 MCP、输出大段 JSON，主 Agent 也不要代交。确认 OpenCode 当前项目根目录就是含 `.opencode/` 的控制目录，并重新加载项目以重新发现工具，然后重新开始运行。

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

## 原始配置制品与可视化站点

配置 JSON 不需要交给 Agent 改写或放入 Scenario 主页面。运行时会按内容哈希保存脱敏快照，并为它生成独立的可搜索 JSON 页面：

```bash
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis artifact-add --file D:/snapshots/payment-prod.json --scenario SCN-PAY --source-id order-core --environment PROD --snapshot 2026-08-25
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis artifact-list --scenario SCN-PAY
```

`password`、`secret`、`token`、访问密钥等常见敏感键默认脱敏；额外键可重复使用 `--redact-key` 指定。站点主场景页提供业务链路导航、由已提交事实确定性生成的 SVG 时序图和证据抽屉。原始制品在 `site/artifacts/` 下独立加载，不进入模型上下文或 Scenario HTML。
