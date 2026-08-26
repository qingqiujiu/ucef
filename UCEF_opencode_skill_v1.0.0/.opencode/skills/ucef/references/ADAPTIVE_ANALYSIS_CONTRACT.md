# UCEF 1.0 自适应分析契约

这个契约只定义 Runtime 必须稳定理解的业务事实，不规定模型思考顺序、步骤数量、分支数量、模块数量或 HTML 版式。

## 会话生命周期

`ucef_analysis_start` 开始或恢复指定 Scenario。主模型自行使用语义索引理解业务，只有确认一个有意义的结论后调用 `ucef_analysis_record`。`ucef_analysis_context` 只返回场景摘要、当前相关事实、关键未知和省略数量。最后 `ucef_analysis_finish` 保存简明结论。

会话使用可调整的上下文目标与总 token 软预算；没有固定 Planner、Block、Finalizer，没有预设“只允许两个深挖块”，没有每次检索必须 Checkpoint 的要求。已有 Gap 不自动启动额外 Agent。

## 灵活增量

一次增量可以包含任何与当前认识有关的组；不要为了凑格式提交空数组。

```json
{
  "summary": "确认支付渠道判断与金额落库",
  "focus": "PaymentRouter#route",
  "scenario_summary": "订单服务按渠道配置选择支付路径并保存金额。",
  "systems": [{"key": "order", "name": "订单系统"}],
  "decisions": [{
    "key": "payment.route",
    "name": "选择支付渠道",
    "priority": "P0",
    "condition": "payment.channel.mode",
    "config_keys": ["payment.channel.mode"],
    "branches": [
      {"name": "直连", "condition": "mode == DIRECT", "expected_value": "DIRECT"},
      {"name": "异步", "condition": "mode == ASYNC", "expected_value": "ASYNC"}
    ]
  }],
  "field_journeys": [{
    "key": "amount",
    "name": "支付金额",
    "priority": "P0",
    "events": [
      {"kind": "COPY", "from": "Request.amount", "to": "Command.amount"},
      {"kind": "UNIT_CONVERSION", "from": "Command.amount(元)", "to": "Payment.amountFen(分)"},
      {"kind": "PERSIST", "from": "Command.amount", "to": "t_order.pay_amount"}
    ]
  }]
}
```

Runtime 接受 `systems`、`modules`、`steps`、`decisions`、`fields` / `field_journeys`、`interactions`、`persistence`、`tables`、`configurations`、`states`、`evidences`、`gaps`，以及通用 `entities` 和 `relations`。每个实体至少有稳定 `key` / `logical_key` 或业务名称；重复逻辑身份会合并，并保留跨场景引用与版本修订。

`sequence_no` 是业务顺序提示，不是流程控制。`priority` 使用 `P0`、`P1`、`P2`。大段源码、完整配置正文和模型内部思考不进入增量。

## 决策与配置

一个决策可包含多个真实业务分支，并引用一个或多个配置键。分支可注明 `condition`、`expected_value`、`business_effect`、`target`。

- 未查询到可信配置：相关配置和分支状态为 `CONFIG_UNRESOLVED`。
- 仅从代码可达：分支为 `POSSIBLE`；不能宣称生产一定命中。
- 有明确 PADB 或人工证据：调用 `ucef_configuration_resolve`，Runtime 将匹配分支标为 `ACTIVE`，其余已比较分支标为 `INACTIVE`。
- 密钥、口令、令牌等配置值必须脱敏；不扫描无关配置或数据库。

不要展开条件组合的完整笛卡尔积；保留改变业务结果的决策点、可选路径和必要的汇合关系。

## 字段追踪

P0 字段沿请求 → 判断 → 转换 → 数据库列 → 外部请求 → 响应消费追踪。`UNIT_CONVERSION`、`ENUM_MAPPING`、`DEFAULT_VALUE`、`OVERRIDE`、`SPLIT`、`MERGE`、`DB_LOOKUP`、`PERSIST`、`OUTBOUND`、`RESPONSE_CONSUME` 等语义事件保留。

`COPY`、`DTO_COPY`、`PASS_THROUGH`、`IDENTITY` 和 `ALIAS` 由 Runtime 在 HTML 与字段投影中折叠；不把每一次对象复制展开成一个展示模块。P1 记录必要系统边界；P2 只保留读者确实需要的交接。

## 边界、证据与展示

- 外部调用提供 `source_system`、`target_system`、`protocol`、请求字段来源和响应字段用途。
- 落库提供 `table`、`operation` 及关键 `field_mappings`。
- 源码证据提供已登记 `source_id`、项目相对路径、symbol 和行号；禁止绝对路径、目录穿越和大段源码。
- 无法确认的业务前提以 `gaps` 明示。日志默认不分析。
- 站点与 SVG 图由 Runtime 根据已存实体和关系确定性生成；模型不产出 HTML、CSS、Mermaid、图表坐标或长篇场景报告。

## 兼容性

v0.10 的 direct Runtime、旧提交工具与 v0.9 事实导入只用于历史工作区兼容，不参与 1.0 主 Agent 默认流程。
