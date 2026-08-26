# UCEF 1.0 Shared Business Fact Model

New adaptive analysis writes a globally reusable entity graph plus small scenario-specific relationships. The model is storage and presentation infrastructure; it does not dictate the main model’s analysis sequence.

## Adaptive graph tables

- `knowledge_entities`: stable global `entity_type + logical_key` identity, human display name, summary, P0/P1/P2 priority, confirmation state, attributes, evidence references, and content hash.
- `knowledge_memberships`: reusable entities referenced by one or many Scenarios, with scenario-specific ordering, role, branch status, configuration value, summary, attributes, and evidence references.
- `knowledge_edges`: scenario-specific typed relations, conditional applicability, sequence, and stable source/target references.
- `exploration_sessions`: resumable main-model business question, global digest, current focus, P0 field names, token budget, and status.
- `exploration_milestones`: compact durable records created only for meaningful semantic state changes.
- `entity_revisions`: immutable previous versions retained when shared entities or relations change.

Supported entity types are `SYSTEM`, `MODULE`, `BUSINESS_STEP`, `DECISION`, `BRANCH`, `FIELD`, `FIELD_EVENT`, `INTERACTION`, `PERSISTENCE`, `TABLE`, `COLUMN`, `CONFIG`, `STATE`, `EVIDENCE`, and `GAP`.

Common generated relations include `OWNS`, `BRANCHES_TO`, `DEPENDS_ON`, `LEADS_TO`, `HAS_FIELD_EVENT`, `INITIATES`, `TARGETS`, `INTERACTS_WITH`, `WRITES_TABLE`, and `EVIDENCED_BY`. An entity can appear in multiple scenarios without being copied; renaming it updates every generated perspective.

## Decisions, configuration, and field projections

Configuration references remain `CONFIG_UNRESOLVED` until evidence verifies an actual value. Once resolved, matching branch entities become `ACTIVE` and comparable alternatives become `INACTIVE`; code reachability alone is never runtime confirmation. The shared entity identity and display name stay global, while configuration values and selected branch states remain scoped to their own Scenario, so two tenants can safely resolve the same key to different production values.

P0 field events preserve meaningful transformations and boundaries. Adjacent `COPY`, `DTO_COPY`, `PASS_THROUGH`, `IDENTITY`, and `ALIAS` events remain durable but are collapsed in reader-facing projections and context ranking. P1/P2 records can remain boundary-only.

## Workspace and source layer

- The UCEF workspace owns `workspace.json`, `sources.json`, `ucef.db`, Scenario/Work Unit JSON, context packs, run results, and the generated site.
- `sources.json` registers Java projects by stable `source_id` and absolute root path. Source roots are read-only and must be outside the workspace tree.
- Stored source Evidence uses `source_id` plus a source-relative path. This keeps facts portable when repositories move while preventing same-named files from different projects from colliding.

UCEF separates reusable business identity from Scenario-specific ordering, branches, and applicability.

## Historical compatibility model

The tables below are still readable so existing v0.9/v0.10 workspaces and artifacts require no destructive migration. They do not create 1.0 adaptive tasks, force a legacy page layout, or constrain the new main-model workflow.

### In-progress memory layer

- `observations`: deduplicated atomic claims captured immediately after a bounded probe. Claims are immutable and remain outside the published dossier.
- `work_unit_checkpoints`: append-only state-changing resume points with an assigned sequence number, current focus, visited references, provisional chain spine, unresolved questions, and next probe; repeated semantic states are suppressed.
- `observation_promotions`: immutable links from supporting Observations to canonical entities created during ingestion.

Pending Observation lists are bounded in context packs, but the database retains all records. The context also carries grouped counts and an omitted count so overflow is visible and queryable.

### Reusable layer

- `behavior_fragments`: semantically complete behavior contracts.
- `method_definitions`: reusable method identity, code hash, location, input/output contract, and error contract.
- `fragment_revisions`: immutable history of Fragment changes.
- `evidence`: source/config/test/runtime observations.

### Scenario layer

- `scenarios`: business operation plus project/environment/config/request constraints.
- `trace_stages`: ordered reader-facing execution stages; may reference Fragments.
- `execution_nodes`: Scenario tree of modules, method invocation instances, method-internal steps, branches, loops, async handoffs, and reference/back-edge nodes.
- `field_inventory`: explicit P0/P1/P2 tracking, exclusion, or Gap decision for every discovered boundary field.
- `route_decisions`: definitions and current Scenario outcomes.
- `field_lineage_steps`: field graph attached to exact execution nodes; non-origin steps link predecessors through `previous_step_ids`.
- `persistence_effects`: store operations and column/value provenance.
- `external_interactions`: request/response provenance and business effect.
- `gaps`: explicit missing knowledge and repair targets.

### Legacy identity and reuse

Fragment lookup uses `logical_key` plus source ID, repository, code hash, binding hash, and applicability. Method definitions reuse source/symbol/code identity, while METHOD_INVOCATION nodes retain the current caller, inputs, configuration, branch, outputs, and position. Scenario stages reference Fragments but retain current inputs, route outcomes, outputs, handoffs, and cross-source boundaries.

### Legacy versioning

Changed payloads create immutable entity revisions before updating the current row. Status/evidence upgrades update the current entity and remain auditable. Code/config changes may mark a Fragment stale without deleting its historical uses.
