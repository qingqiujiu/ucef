# UCEF 1.0 Context Budget Contract

SQLite owns the complete durable graph; the main model receives only the current working set. A bounded projection never deletes or invalidates omitted knowledge.

## Adaptive session budgets

- `adaptive_analysis.context_target_tokens`: target for the recalled fact slice; default `12000`.
- `adaptive_analysis.total_token_budget`: observable soft session budget; default `300000`.
- `ucef_analysis_context.max_tokens`: narrower per-question override.
- `ucef_analysis_record`: compact semantic milestones, not full source files, old dossiers, raw configuration snapshots, or long HTML.

These budgets do not preallocate a number of analysis blocks, model tasks, decisions, branches, probes, or checkpoints. Reaching the total target produces an explicit `SOFT_TOKEN_BUDGET_REACHED` notice; the main model should finish or request user direction according to the actual task.

## Retrieval priority

Every context contains the Scenario goal, entry, global digest, active focus, user-selected P0 fields, concise recent milestones, coverage counts, omitted-fact count, and a targeted retrieval hint.

Entity ranking keeps unresolved `CONFIG_UNRESOLVED` references, open Gaps, the exact requested P0 field, relevant semantic field changes, matching decisions, and business boundaries visible before ordinary DTO-copy events. Search terms may be a Java symbol, field name, configuration key, system, module, database table, or business decision.

## Targeted recovery

- `ucef_analysis_context(focus, fields, symbols)` retrieves the bounded local working set.
- `ucef_knowledge_query(entity_type, search, entity_id)` retrieves one business identity or a small filtered collection.
- `ucef_knowledge_lineage(scenario_id, field)` retrieves one collapsed field journey.
- `ucef_configuration_resolve` changes a verified key without loading every production setting.
- Historical `memory-query`, `method-reuse`, and `query` commands are compatibility tools; they are not required in the new default flow.

Never address an omission by pasting every method body, the complete Scenario graph, all code repositories, the full production configuration, or rendered HTML into model context.
