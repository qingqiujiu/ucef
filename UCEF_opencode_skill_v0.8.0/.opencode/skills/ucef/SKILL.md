---
name: ucef
description: Analyze large Java business call chains with scenario-scoped evidence, field evolution, decisions, external interactions, and durable facts. Use for deep tracing across Flow/Task, routers, extensions, configs, DB, RPC, MQ, listeners, state synchronization, or for comparing multiple business variants without relying on long chat context.
compatibility: OpenCode v2; Python 3.10+
metadata:
  framework: UCEF
  version: "0.8.0"
---

# UCEF

Use UCEF when the user wants to deeply reconstruct or compare a real business execution chain in a large Java codebase.

## Core behavior

1. Treat the current conversation as a workbench, not project memory.
2. Use `.ucef/ucef.db` as durable machine memory.
3. Work on one Scenario and one narrow Work Unit at a time.
4. Use the connected IDEA Index MCP natively for semantic code retrieval.
5. Do not assume Flow, Task, Config, RPC, or MQ must exist.
6. Model findings as Execution, Decision, Data Mutation, Interaction, State, and Evidence.
7. Static reachability is not the same as the current Scenario's actual path.
8. Every technical fact needs Evidence. If it cannot be proven, record UNKNOWN.
9. Preserve each important field's value evolution and overrides instead of collapsing it into one mapping.
10. Treat the incremental HTML Explorer as the default human system view.
11. Treat Obsidian as optional personal notes/learning context, not as a confirmed-fact source.

## Start or resume

If `.ucef/` does not exist, run the bundled `scripts/init_project.py` from this skill's base directory.

Before analysis, inspect only what is needed:
- `.ucef/config.yaml`
- the active Scenario
- the active Work Unit
- relevant confirmed facts / unknowns from SQLite
- `runtime/UCEF_RULES.md` when detailed rules are needed

Do not load every supporting file.

## Code excavation

For the active Work Unit, use IDEA Index MCP directly. Prefer semantic operations such as:
- definition
- references/usages
- implementations
- callers
- callees
- symbol/text search

Start from the entry symbol or focused field/decision. Expand only until the Work Unit objective is answered or a stop condition is reached.

MCP search results are candidate code relationships, not automatically confirmed business execution.

## Persist results

Produce a single JSON object matching `runtime/schema.json`, save it under `.ucef/runs/`, then ingest it with the bundled `scripts/ucef.py`. By default ingest also incrementally updates `.ucef/site/`; the HTML viewer itself is not AI context.

New discoveries should normally be CANDIDATE. Upgrade important facts to CONFIRMED only after verification.

Never overwrite a conflicting prior fact just to make the chain coherent. Record Conflict or Unknown instead.

## Incremental HTML Explorer

The primary human reading surface is `.ucef/site/index.html`. It is compiled from SQLite facts and must not become a second source of truth.

- `site build`: first/full build.
- `site update`: hash-based incremental update.
- Normal `ingest` auto-updates the site when `site.auto_update: true`.
- Search/index data is lightweight and loaded immediately.
- Entity details are split into on-demand chunks so direct `file://` opening works without a server.
- Use Scenario pages for lifecycle progress, execution graph, decisions, fields, interactions, unknowns/conflicts, and cross-scenario compare.

Do not ask the AI to read generated HTML unless the user explicitly asks to analyze the UI.

## Obsidian

Use the connected Obsidian MCP only for compact human-readable views or explicitly requested manual context.

By default:
- do not read the whole Vault;
- do not mirror every Fact into a note;
- keep Scenario/index pages compact;
- preserve user-authored notes;
- never promote human notes directly to CONFIRMED technical facts.

## Comparison

When comparing scenarios, compare confirmed structured facts by:
lifecycle stage, first divergence decision, decision inputs, field evolution, interactions, state propagation, and unresolved gaps.

Do not re-scan the whole repository merely to produce a comparison.

## Supporting reference

Read `references/WORKFLOW.md` only if you need the detailed execution cycle.


## Human explorer

UCEF exposes the same knowledge through three projections:
- **Chain View**: one Scenario across multiple systems/modules.
- **System View**: one system and its internal modules, chains, nodes, and data.
- **Data Model**: authoritative Table/Column/Index/Relation metadata linked back to code/business facts.

Import database/system metadata with `metadata import`; do not ask the model to guess physical schema.

Use `site build`/`site update` for offline read-only HTML. Use `site serve` when the user wants to edit display names, descriptions, classification, order, or visibility from the browser. These edits are stored as manual overrides and do not rewrite technical Facts.

If the user says a technical fact is wrong, create a review Work Unit instead of directly editing the fact.

Read `references/DATA_MODEL.md` only when importing or mapping system/database metadata.
