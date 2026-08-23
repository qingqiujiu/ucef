# UCEF v0.9.4 Workflow

## 0. Bind the analysis workspace and data sources

Choose one independent UCEF workspace and use it for every command. Read its `sources.json`. Each Java project is a read-only source with a stable `source_id`, absolute root path, repository identity, and optional revision/role. The workspace and a source must never be nested inside one another.

## 1. Define the Scenario

Identify the business operation, technical entry, participating `source_ids`, repository revisions, production environment, configuration snapshot, and request constraints. Inventory entry fields as P0/P1/P2 and TRACKED/EXCLUDED/GAP before descending. Unknown constraints remain explicit.

## 2. Define a narrow Work Unit

Use one of:

- `ENTRY_AND_OUTCOME`
- `BUSINESS_STAGE_TRACE`
- `METHOD_EXECUTION_TRACE`
- `METHOD_STEP_DECOMPOSITION`
- `FIELD_INVENTORY`
- `ROUTE_DECISION_ANALYSIS`
- `FIELD_LINEAGE`
- `PERSISTENCE_TRACE`
- `EXTERNAL_INTERACTION_TRACE`
- `FRAGMENT_GAP_FILL`
- `SCENARIO_AUDIT_REPAIR`
- `VARIANT_COMPARE`

The Work Unit names its objective, entry refs, questions, required outputs, and stop conditions.

## 3. Check reuse first

Query by source ID, repository, logical key/symbol, code hash, binding hash, and applicability. Results are:

- `EXACT_REUSE`: use the Fragment and its contract as-is.
- `CONDITIONAL_REUSE`: reuse code behavior but resolve the current config/request outcome.
- `PARTIAL_REUSE`: reuse covered behavior and open a focused Gap Fill.
- `STALE`: code or binding changed; revalidate the affected behavior.
- `MISS`: excavate a new Fragment.

## 4. Resume durable work state

Build a resume context and read its latest Checkpoint, pending Observation frontier, Observation index, and visited-reference union. Chat summaries are not authoritative. If there is an `ACTIVE` Checkpoint, continue from its single `next_probe`.

## 5. Retrieve one bounded probe

Use the connected IDEA Index MCP for definitions, implementations, callers, callees, and references. Search only the registered source roots named by the Work Unit, and preserve `source_id` at every cross-project handoff. Retrieve only what answers the current Work Unit. Production config queries should be restricted to keys that influence current bindings, decisions, clients, transformations, or persistence.

## 6. Checkpoint before the next probe

Convert the probe result into concise Observations and persist a Checkpoint. For a method probe, also update its Scenario invocation, meaningful internal steps, and every visible field read/write before following another call. Include routing, persistence, external mappings, configuration outcomes, error behavior, terminal behavior, contradictions, and unknowns that affect the chain. Do not open another target first.

If the pending frontier is larger than the resume pack, use `memory-query` by subject, kind, or source. The complete ledger remains in SQLite even when only a bounded frontier is loaded.

## 7. Produce reusable facts and a trace patch

Canonical records cite the `observation_ids` they promote. The result contains Evidence plus the relevant Fragment/Scenario records, reusable MethodDefinitions, Scenario execution nodes, field inventory, and field lineage graph. A Scenario-facing discovery must be placed in a business Stage and concrete execution node, or explicitly record why placement is pending.

## 8. Ingest and audit

Ingestion validates IDs, Evidence, references, and versions. Audit detects broken stage handoffs, opaque methods, orphan/cyclic execution nodes, silent field omission, discontinuous lineage, unresolved routes, incomplete persistence mappings, external parameters without origin/use, and missing terminal outcomes.

## 9. Select the next Gap

Continue from the highest-impact audit Gap. Do not expand the repository broadly. A completed reusable Fragment reduces later retrieval to its contract and Evidence pointers.
