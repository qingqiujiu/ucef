# Work Unit Output Contract

Output one JSON object. Omit irrelevant collections; never add prose outside the object.

```json
{
  "scenario": {},
  "evidences": [],
  "fragments": [],
  "trace_stages": [],
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

A stage places behavior into the reader-facing Scenario. It states its executing `source_id`, sequence, business purpose, why it runs in this Scenario, input, processing, output, state/field delta, next handoff, status, and optional Fragment reference. Route decisions, lineage steps, persistence effects, and external interactions also retain the `source_id` of the Java project where they occur.

When a handoff crosses projects, record caller `source_id`, callee `source_id`, boundary symbol/protocol, transferred fields, and why control moves there.

## Field lineage

Each step records canonical field, sequence, lineage role (`ORIGIN`, `TRANSFORM`, or `SINK`), Java location, source, target, operation, condition, transformation, business meaning, and eventual use. Allowed operations include `COPY`, `RENAME`, `DEFAULT`, `OVERRIDE`, `COMPUTE`, `CONVERT`, `MERGE`, `SPLIT`, `DROP`, `MASK`, `PERSIST`, and `RESPONSE_MAPPING`. External and persistence parameter mappings should carry the same `canonical_field` so the reader can follow one value across boundaries.

## Persistence

Record table/store, operation, condition, transaction context, key fields, and column mappings. Each column mapping includes the value source and business purpose.

## External interaction

Record target system/service/operation/protocol, trigger condition, business purpose, timeout/retry/fallback/error behavior, request mappings, and response mappings. Each request parameter needs its internal origin; each consumed response parameter needs its internal target and business use.

## Gaps

Use a Gap instead of guessing. Gaps have a category, severity, question, affected stage/entity, missing evidence, and suggested next Work Unit.
