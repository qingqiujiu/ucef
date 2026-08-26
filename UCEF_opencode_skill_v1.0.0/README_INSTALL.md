# UCEF 1.0.0 for OpenCode

UCEF 1.0 采用“主模型自由理解业务，程序固定管理事实与展示”的方式：Java 主 Agent 自己分析多个决策、关键字段、数据库和外部系统；Runtime 维护 SQLite 事实图、聚焦上下文与可跳转的离线 HTML。

## 安装

把整个 `.opencode/` 放入 OpenCode 能发现的控制目录。控制目录、UCEF 独立工作区和各 Java 项目互不混用：

```text
java-analysis-controller/
└── .opencode/
    ├── agents/
    │   ├── ucef-java-chain.md
    │   └── ucef-probe.md
    ├── tools/ucef.ts
    └── skills/ucef/
```

运行时只要求 Python 3.10+ 标准库。若可执行命令不是 `python`，设置 `UCEF_PYTHON`。连接 IDEA 语义索引 `index-mcp`；未来的 `padb` 是可选项，当前没有也可以正常分析。

## 建立独立工作区

```bash
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis bootstrap
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis source-add --source-id order-service --path D:/repos/order-service
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis source-add --source-id payment-center --path D:/repos/payment-center
```

工作区和 Java 项目不能互相嵌套。OpenCode 主 Agent 也可直接用 `ucef_workspace_bootstrap`、`ucef_source_register`、`ucef_scenario_register` 完成这些步骤，不需要阅读脚本或创建中间文件。

登记一个明确的业务 Scenario：

```bash
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis scenario-put --file scenarios/pay.json
```

在 OpenCode 中选择 `ucef-java-chain`，提供工作区、Scenario ID、业务问题和重点字段。例如：

```text
分析 SCN-PAY，UCEF 工作区 D:/ucef/order-analysis。
重点找所有真正影响支付结果的决策点和分支；完整追踪 amount、paymentChannel。
解释字段如何进入支付请求、响应如何被消费、哪些列落库，并生成可跳转的系统时序和字段溯源 HTML。
padb 当前不可用，生产配置按待确认处理。
```

## 主模型与程序如何协作

主模型用 `index-mcp_*` 保持对完整业务链路的理解，自主决定先分析哪里、哪些分支值得深入以及如何归纳业务含义。

- `ucef_analysis_start`：开始或恢复场景，指定 P0 字段与可选 token 预算。
- `ucef_analysis_record`：提交一次有意义的业务事实增量，自动刷新站点。
- `ucef_analysis_context`：只召回场景摘要和当前字段、方法、模块或配置的相关事实。
- `ucef_knowledge_query` / `ucef_knowledge_lineage`：查询共享实体或单个字段旅程。
- `ucef_configuration_resolve`：未来有 PADB 或其他可信生产证据后确认一个配置键。
- `ucef_entity_rename`：修改一次共享实体名称，同时更新所有场景和视角。
- `ucef_analysis_finish`：保存简短业务结论和显式未知项。

没有固定 Planner、Block、Finalizer，没有预设只深挖两个模块，也不要求每次索引查询立即写 Checkpoint。`ucef-probe` 仅在确实存在独立窄问题时可选使用。

## 决策、配置与字段

配置、请求、状态、策略等因素产生的真实业务分支都可以保留，不展开无意义的全量条件组合。缺少 PADB 或其他可信配置值时，Runtime 将配置标为 `CONFIG_UNRESOLVED`，不猜测生产实际命中路径。

P0 字段追踪请求、判断、单位转换/枚举映射/覆盖等语义变化、数据库列、外部请求和响应消费；连续普通 DTO 复制自动折叠。P1 记录边界，P2 只保留必要交接。日志默认不分析。

## 离线 HTML

默认入口为 `D:/ucef/order-analysis/site/index.html`，提供场景、系统、模块、决策、关键字段和数据库表视角。页面根据现有事实选择决策卡片、分支、交互、响应消费、字段变更与落库映射；没有事实的模块不会显示。

流程图、系统时序图、系统关系图、业务状态流转图和字段溯源图由 Runtime 直接生成本地 SVG，不依赖 CDN，也不要求模型写 HTML、Mermaid 或冗长报告。源码证据通过点击按需查看。

## CLI 诊断

```bash
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis doctor
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis session-start --scenario SCN-PAY --priority-fields amount,paymentChannel
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis session-context --session-id SESSION-... --focus amount
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis graph-query --scenario SCN-PAY --type DECISION
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis field-lineage --scenario SCN-PAY --field amount
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis config-resolve --scenario SCN-PAY --key payment.channel.mode --value DIRECT --evidence padb:payment.channel.mode
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis site
```

## 从旧版本升级

用 1.0 的完整 `.opencode/` 替换旧控制目录内容，并重新加载 OpenCode 项目；保留自行修改的 MCP 名称或环境配置。已有 UCEF 工作区和数据库不需要删除：新 Runtime 自动补齐事实图库表，继续读取 v0.9/v0.10 数据、旧方法树、历史 HTML、脱敏制品与 UTF-8 JSON。

旧 `analysis-start`、`submit-direct` 与相关 TypeScript 工具仅为历史兼容而保留；新主 Agent 不再拥有或使用旧调度工具权限。
