---
name: ucef
description: Analyze a Java business scenario across projects, decisions and branches, optional production configuration, key-field provenance, database writes, and external systems. Use when OpenCode should freely understand business code while a local UCEF runtime persists a shared fact graph, bounds recalled context, and generates cross-linked offline HTML diagrams and perspectives.
---

# UCEF 1.0：模型理解业务，程序组织事实

主模型保留完整业务判断权，使用 `index-mcp_*` 自主理解 Java 主链、分支、字段和跨系统交互；Runtime 负责稳定身份、SQLite、上下文裁剪、证据、配置状态、图表与 HTML。不要把分析拆成固定 Planner/Block/Finalizer，不要求固定业务块数量，不生成 HTML 或长报告。

## 默认工作方式

1. 使用明确的独立工作区。必要时调用 `ucef_workspace_bootstrap`、`ucef_source_register`、`ucef_scenario_register`；Java 项目始终只读。
2. 调用 `ucef_analysis_start` 开始或恢复场景，声明业务目标与用户关心的 P0 字段。
3. 直接理解代码，跟随真正影响业务结果的决策、策略、状态、配置、字段变化、落库与外部调用；数量和顺序由当前事实决定。
4. 理解一个有意义的业务阶段后调用 `ucef_analysis_record`，提交小而灵活的事实增量。每次代码检索不必落库；一条增量也不必对应固定版式。
5. 切换问题时用 `ucef_analysis_context` 召回“场景摘要 + 局部相关事实 + 关键未知”；按需使用 `ucef_knowledge_query` 或 `ucef_knowledge_lineage`，不要读取整个事实库。
6. 调用 `ucef_analysis_finish` 形成简短结论。Runtime 已从统一事实生成可互相跳转的场景、系统、模块、决策、字段和数据库表页面，以及离线流程图、时序图、系统关系图、状态流转图与字段溯源图。

## 重点与边界

- 决策保留真实条件、多个业务分支、各分支影响和汇合；不要枚举无意义的条件笛卡尔积。
- 没有 `padb` 或其他可信生产配置证据时记录 `CONFIG_UNRESOLVED`，不猜测实际环境命中的路径；后续只针对相关键使用 `ucef_configuration_resolve`。
- P0 字段追踪请求 → 判断 → 有意义的转换 → 数据库列 → 外部请求 → 响应消费；P1 保留边界映射，P2 与普通 DTO 复制交给 Runtime 折叠。
- 外部交互记录调用双方、协议、请求参数来源、响应使用与业务影响；落库记录表、操作和关键列来源。
- Java 证据采用 `source_id + 相对路径 + symbol/line`。配置制品通过 `ucef_artifact_register` 脱敏登记，不保存口令、密钥、令牌或完整快照正文。
- 日志默认不分析。无法确认的事实写成明确 Gap，不编造运行期行为；达到约定软预算时交付已有结果。
- 只有确实独立的小问题才考虑 `ucef-probe`；默认由主模型保持连续上下文和全局理解。

只在修改事实格式或排查 Runtime 时读取 [references/ADAPTIVE_ANALYSIS_CONTRACT.md](references/ADAPTIVE_ANALYSIS_CONTRACT.md)。修改存储、跨场景身份或旧数据迁移时读取 [references/DATA_MODEL.md](references/DATA_MODEL.md)；处理超长链路召回时读取 [references/CONTEXT_BUDGET_CONTRACT.md](references/CONTEXT_BUDGET_CONTRACT.md)。普通分析不读取脚本、完整 Schema、旧版合同或整个 HTML。
