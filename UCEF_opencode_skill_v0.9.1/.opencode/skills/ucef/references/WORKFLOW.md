# UCEF v0.9.1 Workflow

## 0. Bind the analysis workspace and data sources

Choose one independent UCEF workspace and use it for every command. Read its `sources.json`. Each Java project is a read-only source with a stable `source_id`, absolute root path, repository identity, and optional revision/role. The workspace and a source must never be nested inside one another.

## 1. Define the Scenario

Identify the business operation, technical entry, participating `source_ids`, repository revisions, production environment, configuration snapshot, and request constraints. Unknown constraints remain explicit.

## 2. Define a narrow Work Unit

Use one of:

- `ENTRY_AND_OUTCOME`
- `BUSINESS_STAGE_TRACE`
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

## 4. Retrieve a bounded code neighborhood

Use the connected IDEA Index MCP for definitions, implementations, callers, callees, and references. Search only the registered source roots named by the Work Unit, and preserve `source_id` at every cross-project handoff. Retrieve only what answers the current Work Unit. Production config queries should be restricted to keys that influence current bindings, decisions, clients, transformations, or persistence.

## 5. Produce reusable facts and a trace patch

The result must contain Evidence plus the relevant Fragment/Scenario records. A Scenario-facing discovery must include a `trace_stage` or explicitly record why it is pending placement.

## 6. Ingest and audit

Ingestion validates IDs, Evidence, references, and versions. Audit detects broken stage handoffs, unresolved routes, missing field origins, incomplete persistence mappings, external parameters without origin/use, and missing terminal outcomes.

## 7. Select the next Gap

Continue from the highest-impact audit Gap. Do not expand the repository broadly. A completed reusable Fragment reduces later retrieval to its contract and Evidence pointers.
