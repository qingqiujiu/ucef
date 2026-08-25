# UCEF v0.10.0 直接分析契约

## 目标

一次接口分析只允许三层最终产物，不允许“事实片段 → 子 Agent 摘要 → 主 Agent 摘要 → Integration 重写 → HTML 再解释”的传递链。

## 1. ScenarioPlan

Planner 一次提交完整业务骨架。每个 BusinessBlock 按业务顺序定义：`block_id`、稳定 `logical_key`、标题、业务目标、深度、为什么需要该深度、已知输入/判断/输出和少量证据引用。任务胶囊只带最多 30 条历史 logical_key 索引，不带旧报告正文。

- `SUMMARY`：业务交接足以理解，不分配 Worker。
- `STANDARD`：涉及字段、配置、外部、落库或结果，需要一次定向深挖。
- `CRITICAL`：决定生产选路或核心结果，优先占用深挖名额。

Runtime 在计划落库时立即写入所有块的骨架，所以此时 HTML 已可阅读。超出模式预算的计划被拒绝，不会偷偷裁成更多任务。

## 2. BusinessBlock

每个 Block Worker 只解决一个块，并一次提交：

- `business_goal`、`why_current`；
- 收到的业务数据及来源；
- 当前配置/条件/路由判断；
- 最多 10 个读者相关的实现步骤；
- 字段的 `from → transformation → to → business_use`；
- 外部请求来源、响应去向、失败行为；
- 落库字段映射与业务效果；
- 输出如何交给下一块；
- 最多 8 个方法/源码证据或透明技术桥；
- 无法确认的显式 Gap。

Worker 先检查 Runtime 按 logical_key 给出的最多 3 个紧凑候选，并在 `reuse` 中记录 `EXACT_REUSE`、`PARTIAL_REUSE` 或 `NEW` 及其代码/绑定/配置/契约依据。最多 6 次定向语义检索，不遍历整个调用图。`padb` 只用于当前块确实依赖生产配置或数据库映射时。提交成功后只返回 receipt。

## 3. ScenarioOverview

Finalizer 只能读取压缩后的 BusinessBlock，不读源码、配置、方法树或旧对话。它必须覆盖全部 block ID，并形成：一句话链路、业务背景、当前选路、P0 字段旅程、外部效果、持久化效果、失败结果与开放 Gap。

## 硬停止

| 模式 | 业务块 | 深挖块 | 模型任务 | 时间 | 单 Worker 上下文 |
|---|---:|---:|---:|---:|---:|
| QUICK | 5 | 2 | 4 | 15 分钟 | 10K |
| STANDARD | 8 | 4 | 6 | 30 分钟 | 12K |
| DEEP | 12 | 6 | 8 | 45 分钟 | 16K |

模型任务包含 Planner 和 Finalizer。Runtime 到期后把未执行任务标记为 `SKIPPED`，保留当前页面，不做自动重试。校验失败允许当前 Worker纠正一次提交，但不得新建分析层或子任务。

## 自描述任务胶囊

`analysis-next` 优先返回尚未完成的 `CLAIMED` 任务，确保校验失败后不会越过当前任务。每个胶囊携带角色专用 `output_contract`：提交工具名、必填字段、硬数量限制和最小 `payload_template`。运行时已填入 Block 身份及 Overview 的完整 block ID 顺序，并自动注入 run、scenario 和可生成的产物 ID。

Worker 不读取 Python/TypeScript 脚本、完整 Schema、示例 JSON 或本合同来学习调用方式。结构错误返回 `code + JSON path + expected + hint`，不返回整个 payload。初次失败后只允许一次定向修正；再次失败时 Block 标为 `FAILED` 并生成可见 Gap，Planner 或 Finalizer 失败则以 `SUBMISSION_CORRECTION_BUDGET_EXHAUSTED` 停止运行。

## 单写入与幂等

模型没有文件编辑或命令权限。所有正式产物经 `.opencode/tools/ucef.ts` 调用 Runtime：校验任务归属、字段、数量、状态和覆盖范围后，在同一事务中入库并生成 receipt。同一 payload 重复提交返回 `ALREADY_ACCEPTED`，不会重复写入或触发任务。工作区初始化、数据源、Scenario、配置制品和站点构建也由专用工具封装，CLI 只作为人工运维入口。

## 复用

优先查询已存 BusinessBlock/Fragment/MethodDefinition。只有代码版本、运行绑定、相关配置/请求条件和契约覆盖相符才复用；条件变化只分析差异。复用事实直接进入当前 BusinessBlock，父 Agent不搬运完整旧报告。

## 可读性判定

直接模式不运行旧版自动扩张审计。所有 BusinessBlock 为 `COMPLETE`、`SUMMARY_COMPLETE` 或显式 `GAP`，且 ScenarioOverview 覆盖每个 block ID 时，页面为 `READABLE_COMPLETE`。Gap 可见，但不会让调度器循环。
