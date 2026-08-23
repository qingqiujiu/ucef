# Work Unit Output Contract

Output one JSON object. Omit irrelevant collections; never add prose outside the object.

Canonical records derived from the durable ledger include `observation_ids`. Ingestion rejects missing Observation references and records promotion links for successfully stored entities.

```json
{
  "scenario": {},
  "evidences": [],
  "fragments": [],
  "method_definitions": [],
  "trace_stages": [],
  "execution_nodes": [],
  "field_inventory": [],
  "route_decisions": [],
  "field_lineage_steps": [],
  "persistence_effects": [],
  "external_interactions": [],
  "gaps": [],
  "next_work_units": []
}
```

## Evidence

Source-code Evidence identifies registered `source_id`, repository/revision when known, source-relative file, line range, symbol, evidence kind, and a concise observation. Never put an absolute Java project path in an Evidence record. Source locations must support the attached claim.

## Behavior Fragment

A reusable Fragment requires:

- `logical_key`, `name`, and `business_purpose`;
- source ID plus repository/revision/code hash and binding hash when available;
- applicability and coverage statements;
- entry and exit contracts;
- preconditions, postconditions, side effects, and handoffs;
- status and Evidence IDs.

Do not make a Fragment for a method whose only meaning is “calls another method”. Keep such methods as Evidence inside a semantically meaningful Fragment.

## Trace Stage

A stage is a concise business orientation layer. It states its executing `source_id`, sequence, business purpose, why it runs in this Scenario, input, processing, output, state/field delta, next handoff, status, and optional Fragment reference. It does not replace the execution tree.

When a handoff crosses projects, record caller `source_id`, callee `source_id`, boundary symbol/protocol, transferred fields, and why control moves there.

## Method definition and execution tree

Record reusable method identity separately from Scenario invocation context. `MethodDefinition` contains the source ID, module, symbol/signature, source-relative location, code hash, input/output contracts, errors, status, and Evidence.

Build `execution_nodes` as MODULE → METHOD_INVOCATION → STEP, nesting called invocations beneath the calling STEP. Every STEP explicitly contains `field_reads` and `field_writes`, including empty arrays. Use BRANCH, LOOP, ASYNC_HANDOFF, REFERENCE, and RECURSION rather than flattening or forming parent cycles. Read `EXECUTION_TREE_CONTRACT.md` for node rules.

## Field inventory

Before detailed descent, record every discovered boundary field as P0/P1/P2 and TRACKED/EXCLUDED/GAP. Exclusion requires a reason. A STEP may not read or write a field absent from this inventory.

## Field lineage

Each step records its `execution_node_id`, canonical field, sequence, lineage role (`ORIGIN`, `TRANSFORM`, or `SINK`), Java location, source, target, operation, expression/transformation, condition, before/after type or value semantics, null behavior, business meaning, and eventual use. Every non-origin step names `previous_step_ids`; this makes split/merge paths explicit and lets audit detect a missing middle segment. External and persistence parameter mappings carry the same `canonical_field`.

## Persistence

Record table/store, operation, condition, transaction context, key fields, and column mappings. Each column mapping includes the value source and business purpose.

## External interaction

Record target system/service/operation/protocol, trigger condition, business purpose, timeout/retry/fallback/error behavior, request mappings, and response mappings. Each request parameter needs its internal origin; each consumed response parameter needs its internal target and business use.

## Gaps

Use a Gap instead of guessing. Gaps have a category, severity, question, affected stage/entity, missing evidence, and suggested next Work Unit.
