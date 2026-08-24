# UCEF 版本迭代记录

## v0.9.6 — 业务主链、实现切片与受控子 Agent

- 将最终知识分为业务主链 `TraceStage`、跨方法 `ImplementationSlice`、底层 Evidence 三层，避免片段事实和完整方法树取代业务叙事。
- 新增 `CoverageGate`，按 G0–G4 的确定性优先级控制展开；自动任务必须明确关闭哪个 Gate。
- 引入 P0/P1/P2 字段深度策略，P0 保证入口到外发、响应消费、落库或返回的连续谱系。
- 为实现切片增加语义闭合标准：输入、决策/配置、字段、副作用/边界、输出和未知 Gap 必须逐项闭合。
- 透明框架机制以 `TechnicalBridge` 留痕，只有影响业务判断、字段值、副作用、异常、事务、时序或输出时才进入深挖。
- 增加只读 Skeleton、Slice、Integration 子 Agent；主 Agent 通过 v0.9.6 Task Capsule、允许操作和硬预算控制其工作流程，UCEF 运行时保持单写入。
- Integration Agent 仅从压缩事实组装全局叙事，不回读源码和生产配置，从而保留全链路视角并避免重复挖掘。
- HTML 改为业务主链优先，每个阶段内联实现切片、跨方法路径、内部步骤、字段效果、配置、边界和透明技术桥；完整方法树作为可展开证据。
- 上下文默认调整为 32K 总预算、8K 输出预留、约 24K 输入，并按 Agent 角色装载不同投影。
- 检查点改为“每个状态变化的语义探针至多一次”；相同事实和相同恢复前沿返回 `no_state_delta`，不重复落盘或触发完整审计。

## v0.9.5 — 120K 上下文裁剪与定向召回

- 将完整事实库与模型临时工作集分离；SQLite 保留完整档案。
- 默认 UCEF 上下文预算上限调整为 52K，其中约 36K 用于事实装载、16K 预留给推理和输出。
- 按 Work Unit 阶段路由规范：`EXCAVATE`、`PROMOTE`、`ASSEMBLE`、`PUBLISH`。
- 按 `anchor_execution_node_id` 装载局部方法树，超深调用链仍保证锚点不被裁掉。
- 目标字段、显式活跃字段、局部节点字段采用稳定优先级，限制字段库存和谱系规模。
- 从最近候选池之外按字段或符号定向召回历史 Observation。
- Gap 按当前锚点、字段和影响优先级装载，并提供遗漏计数与定向恢复提示。
- `method-reuse` 默认返回紧凑契约，通过 `--full` 按需读取完整记录。
- 新增上下文预算契约及 OpenCode Agent 的 120K 上下文纪律。

## v0.9.4 — 方法执行树与字段级完整性

- 分离可复用 `MethodDefinition` 与 Scenario 特定 `METHOD_INVOCATION`。
- 将方法内部拆分为校验、转换、路由、调用、持久化、外部交互、返回等 `STEP`。
- 每个步骤显式记录 `field_reads` 和 `field_writes`。
- 引入 P0/P1/P2 字段库存以及 `TRACKED`、`EXCLUDED`、`GAP` 状态。
- 字段谱系通过 `previous_step_ids` 形成可分叉、合并的图，而不是线性文字。
- 审计不透明方法、静默字段遗漏和不连续字段谱系。
- HTML 升级为方法树、节点详情、字段路径同步的三视图。

## v0.9.3 — OpenCode 主 Agent 与工具编排

- 增加可选择的 `ucef-java-chain` OpenCode primary Agent。
- Agent 权限设为允许，并约束 Java 项目保持只读。
- 每个新会话强制加载 `ucef` 与用户的 `padb` Skill。
- 启用 `index-mcp_*`，优先使用 IDEA 语义索引完成 Java 跨项目检索。
- 强制单探针、单 Checkpoint 的长链路防丢失事务。

## v0.9.2 — 持久化分析记忆与断点恢复

- 新增原子 Observation 账本和追加式 Work Unit Checkpoint。
- 工具检索后立即持久化事实，避免长链路被上下文压缩淹没。
- 支持 Observation 去重、提升关联、反向查询和未组装状态。
- 新增 `resume`、`checkpoint`、`memory-query` 等命令。
- 上下文溢出显示遗漏数量，并可按主题、类型和来源定向取回。
- HTML 增加分析记忆页面和待组装完整性审计。

## v0.9.1 — 独立分析工作区与多项目数据源

- UCEF 工作区与 Java 项目彻底分离，Java 项目仅作为只读数据源注册。
- 使用稳定 `source_id` 支持多项目入口、调用和证据关联。
- 建立 Scenario、BehaviorFragment、TraceStage、Evidence、Gap 等核心模型。
- 支持代码/绑定身份校验、片段复用和版本修订。
- 生成 Scenario 优先的 HTML 档案，并展示字段生命周期、落库和外部交互。
- 加入读者完整性审计与多链路差异对齐。

## v0.9.0 — 过渡发布

- 保留原始发布压缩包作为版本档案。
- 当前本地成果中没有对应的解压源码目录，因此不补写未经验证的详细变更。

## v0.8.0 — 初始 OpenCode Skill

- 建立项目内可发现的 OpenCode `ucef` Skill 包装结构。
- 提供安装脚本、模板、运行时和参考契约的初始版本。
- 奠定 Java 业务链路、字段、路由、持久化和外部交互分析方向。
