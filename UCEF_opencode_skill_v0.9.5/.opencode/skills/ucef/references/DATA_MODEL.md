# UCEF v0.9.5 Data Model

## Workspace and source layer

- The UCEF workspace owns `workspace.json`, `sources.json`, `ucef.db`, Scenario/Work Unit JSON, context packs, run results, and the generated site.
- `sources.json` registers Java projects by stable `source_id` and absolute root path. Source roots are read-only and must be outside the workspace tree.
- Stored source Evidence uses `source_id` plus a source-relative path. This keeps facts portable when repositories move while preventing same-named files from different projects from colliding.

UCEF separates reusable behavior from Scenario-specific execution.

## In-progress memory layer

- `observations`: deduplicated atomic claims captured immediately after a bounded probe. Claims are immutable and remain outside the published dossier.
- `work_unit_checkpoints`: append-only resume points with an assigned sequence number, current focus, visited references, provisional chain spine, unresolved questions, and next probe.
- `observation_promotions`: immutable links from supporting Observations to canonical entities created during ingestion.

Pending Observation lists are bounded in context packs, but the database retains all records. The context also carries grouped counts and an omitted count so overflow is visible and queryable.

## Reusable layer

- `behavior_fragments`: semantically complete behavior contracts.
- `method_definitions`: reusable method identity, code hash, location, input/output contract, and error contract.
- `fragment_revisions`: immutable history of Fragment changes.
- `evidence`: source/config/test/runtime observations.

## Scenario layer

- `scenarios`: business operation plus project/environment/config/request constraints.
- `trace_stages`: ordered reader-facing execution stages; may reference Fragments.
- `execution_nodes`: Scenario tree of modules, method invocation instances, method-internal steps, branches, loops, async handoffs, and reference/back-edge nodes.
- `field_inventory`: explicit P0/P1/P2 tracking, exclusion, or Gap decision for every discovered boundary field.
- `route_decisions`: definitions and current Scenario outcomes.
- `field_lineage_steps`: field graph attached to exact execution nodes; non-origin steps link predecessors through `previous_step_ids`.
- `persistence_effects`: store operations and column/value provenance.
- `external_interactions`: request/response provenance and business effect.
- `gaps`: explicit missing knowledge and repair targets.

## Identity and reuse

Fragment lookup uses `logical_key` plus source ID, repository, code hash, binding hash, and applicability. Method definitions reuse source/symbol/code identity, while METHOD_INVOCATION nodes retain the current caller, inputs, configuration, branch, outputs, and position. Scenario stages reference Fragments but retain current inputs, route outcomes, outputs, handoffs, and cross-source boundaries.

## Versioning

Changed payloads create immutable entity revisions before updating the current row. Status/evidence upgrades update the current entity and remain auditable. Code/config changes may mark a Fragment stale without deleting its historical uses.
