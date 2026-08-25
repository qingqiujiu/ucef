---
name: ucef
description: Compile one Java business scenario across projects, production configuration, routing, field transformations, persistence, and external APIs into a reader-ready dossier. Use when an OpenCode agent must finish within a hard time/task budget, reuse prior analysis, and let bounded subagents submit final artifacts directly without repeated relay or rewriting.
compatibility: OpenCode v2; Python 3.10+
metadata:
  framework: UCEF
  version: "0.10.0"
---

# UCEF

UCEF 把多个 Java 项目和生产配置当作只读数据源，在独立工作区中把一个 Scenario 编译成可直接阅读的业务链路。默认流程只产生三类模型产物：

1. `ScenarioPlan`：一次性确定 4–7 个业务块以及哪些块值得深挖。
2. `BusinessBlock[]`：每个重点块一次提交，正文同时说明业务目的、实现步骤、字段变化、配置选路、外部接口和落库。
3. `ScenarioOverview`：只读取压缩后的 BusinessBlock，补充全链总结与横向字段旅程。

方法、类、源码位置属于技术证据附录，不作为第四层叙事。子 Agent 的最终 JSON 通过 `ucef_submit_*` 直接校验并入库；父 Agent 只接收 receipt，不复制、不重写、不复审正文。每个任务胶囊自带角色专用 `output_contract` 和最小可填写模板，正常 Agent 不读取脚本、Schema 或示例文件。

## 默认执行

使用包内 `ucef-java-chain` 主 Agent。它只执行：

`start → next task → 派给固定角色 → 接收 receipt → next task → stop`

- 默认 `STANDARD`：最多 7 个业务块、2 个深挖块、4 次模型任务、20 分钟。
- `QUICK`：最多 5 个业务块、1 个深挖块、3 次模型任务、10 分钟。
- `DEEP`：最多 10 个业务块、4 个深挖块、6 次模型任务、35 分钟；只有用户明确要求才允许。

Runtime 的队列和截止时间是硬约束。审计、Gap、模型判断或“还能再找”都不得自动创建任务。达到预算时发布已有骨架和明确 Gap；用户再次启动同一 Scenario 时，Runtime 复用已存 Plan 和完成块，只补未完成块并生成总览，不重新派发 Planner。

正常分析只遵循当前任务胶囊，不再额外读取参考文档。修改 Runtime 或诊断合同本身时才读取 [references/DIRECT_ANALYSIS_CONTRACT.md](references/DIRECT_ANALYSIS_CONTRACT.md)；修改存储或导入兼容层时才读取 [references/DATA_MODEL.md](references/DATA_MODEL.md)。旧 Work Unit、Checkpoint、CoverageGate 和 ImplementationSlice 仅用于导入 v0.9.x 数据，不属于默认分析路径。

## 无脚本准备

主 Agent 使用 `ucef_workspace_bootstrap` 创建独立工作区，使用 `ucef_source_register` 登记只读 Java 数据源，使用 `ucef_scenario_register` 按明确字段保存 Scenario。配置快照使用 `ucef_artifact_register`，站点重建使用 `ucef_site_build`。这些工具封装全部 CLI 参数；Agent 不打开 `scripts/`，也不创建中间 JSON 文件。

`ucef_*` 均由当前项目的 `.opencode/tools/ucef.ts` 注册，是本地自定义工具而不是 MCP 工具。角色专用提交工具必须直接出现在对应 Worker 的可调用工具列表中。若缺失，Worker 只返回 `TOOL_UNAVAILABLE: <tool>`，主 Agent立即停止调度并报告安装或工具发现故障；双方都不得搜索 MCP、传回正文 JSON 或由父 Agent 代交。

`ucef_control_next` 每次只返回当前任务、必要事实和 `output_contract.payload_template`。Worker 填值后调用合同指定的 submit 工具。Runtime 自动注入 run、scenario 和可生成的产物 ID；校验错误只返回错误代码、JSON 路径、期望值和修正提示，不回显大 payload。初次提交失败后只允许一次修正；再次失败时 Block 确定性转为 Gap，Planner 或 Finalizer 则停止当前运行。

## 工作区边界

- 每次都使用一个明确的 UCEF 工作区绝对路径；它必须位于所有 Java 项目之外。
- Java 项目通过稳定 `source_id` 注册，只读访问；UCEF 只写独立工作区。
- 源码证据保存 `source_id + 相对路径 + symbol/line`，不要复制大段源码。
- 生产配置或数据库查询只回答当前块的选路、字段来源、映射或业务效果；不得扫描整个配置或数据库。
- 不得持久化密钥、口令、令牌或个人敏感数据。
- 需要保留原始配置结构时，由人或 `ucef_artifact_register` 登记脱敏 JSON 快照；Agent 只引用 `artifact_id + JSON Pointer`，不得把完整制品读入上下文或写入 BusinessBlock。

## 深挖标准

Planner 只将以下业务影响标为 `STANDARD`/`CRITICAL`：

- 决定实际分支、实现或 Bean 的生产配置与请求条件；
- P0 字段的非平凡转换、拆分、合并、覆盖或来源变化；
- 外部请求参数来源、响应消费和失败语义；
- 落库字段来源、事务边界和业务副作用；
- 改变最终输出、异常、异步时序或幂等结果的实现。

显而易见的委派、DTO 透传、日志、普通框架代理等保留一句业务交接和方法证据即可。BusinessBlock 必须让不了解系统但懂 Java 的读者知道“为什么来到这里、具体怎样实现、字段怎样变化、产生什么结果”；只有方法名或对象名不合格。

## 复用与停止

遇到已分析过的业务块，只有代码身份、绑定/配置条件、输入输出契约和所需字段覆盖都匹配时才直接复用；否则只补当前差异。复用不会增加任务预算。

每个 Worker 只能提交当前任务对应的一个最终产物，不能派发子任务。无法在预算内确认的事实提交为 Gap。Finalizer 不读源码、配置或数据库，只从已存 BusinessBlock 形成全局视角。

HTML 在 Plan 和每个 Block 提交后增量生成。业务时序图由 Runtime 从 BusinessBlock、外部调用和持久化事实确定性生成，Agent 不提交 Mermaid、SVG 或 HTML。默认页面只展示中文业务主线、时序图、结构化输入/判断/输出、P0 字段全链、外部与持久化影响、失败与 Gap；技术依据点击后打开，原始 JSON 在独立制品页按需加载。横向对比按业务块、字段旅程、路由、外部系统和落库对齐。
