# UCEF repository guidance

- Java repositories are read-only data sources. Write UCEF state only to the explicit independent workspace.
- For new analysis use the v0.10 direct flow: one ScenarioPlan, bounded BusinessBlocks, one ScenarioOverview.
- Respect Runtime task/time budgets. Never create recursive analysis tasks or audit-driven expansion.
- Workers submit final artifacts with `ucef_submit_*`; the parent receives receipts only.
- Use `index-mcp` for bounded Java semantic queries. Load `padb` only for a current production configuration or database mapping question.
- Publish current partial results and explicit Gaps when the hard budget is reached.
