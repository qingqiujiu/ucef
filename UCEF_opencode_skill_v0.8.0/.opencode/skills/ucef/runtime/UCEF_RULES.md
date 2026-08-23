# UCEF Rules — AI Minimal Interface

你不需要理解 UCEF 的内部实现，只需要完成当前 Context Pack 中的一个 Work Unit。

## 必须遵守

1. 只完成当前 Work Unit，不扩展范围。
2. 不假设系统一定有 Flow、Task、Config、RPC 或 MQ。
3. 只用六类语义描述发现：Execution、Decision、Data Mutation、Interaction、State、Evidence。
4. IDEA Index MCP 返回的是候选代码关系，不自动代表当前 Scenario 实际执行。
5. 当前 Scenario 实际路径与静态可能路径必须分开。
6. 每条事实必须绑定 Evidence；证据不足就写 UNKNOWN。
7. 字段每次修改都保留前版本、新版本、来源、条件和操作类型。
8. Decision 必须记录输入来源、条件、可能结果和当前 Scenario 结果（若可确认）。
9. Interaction 必须记录目标、输入、输出及输出的实际业务作用；看不到用途就写 UNKNOWN。
10. 不得为了让链路完整而脑补缺失步骤。
11. 新证据与旧事实不一致时写 Conflict，不直接覆盖。
12. 达到 Work Unit stop condition 后停止。
13. Obsidian 笔记是人类理解/导航信息，不是 CONFIRMED 技术事实；除非另有源码、配置或运行证据验证。
14. 输出必须是单一 JSON Object，不输出解释性前言。

## 输出结构

```json
{
  "evidences": [],
  "execution_nodes": [],
  "execution_edges": [],
  "decisions": [],
  "data_mutations": [],
  "interactions": [],
  "unknowns": [],
  "conflicts": [],
  "next_work_units": []
}
```

新发现默认 `CANDIDATE`。只有满足 Evidence 和 Scenario 条件时才标记 `CONFIRMED`。
