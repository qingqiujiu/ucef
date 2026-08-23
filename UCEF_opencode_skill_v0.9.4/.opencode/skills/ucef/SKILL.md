---
name: ucef
description: Reconstruct reusable, evidence-backed Java business execution dossiers across projects, production configurations, routing variants, field transformations, persistence, and external APIs. Use when a reader who knows Java but not the system must understand and compare complete business paths without repeatedly excavating already verified behavior.
compatibility: OpenCode v2; Python 3.10+
metadata:
  framework: UCEF
  version: "0.9.4"
---

# UCEF

Produce a self-contained business execution dossier, not a directory of code facts. The primary acceptance test is whether a Java developer unfamiliar with the system can understand the selected path, expand it from module to method invocation and method-internal steps, explain why production configuration selects it, trace important fields without discontinuities, and identify every persistence and external parameter's origin and business effect.

## Hard workspace boundary

UCEF is an independent analysis workspace. Java projects are registered read-only data sources; they never contain UCEF databases, scenarios, contexts, runs, or generated sites.

- Select one explicit absolute workspace path for the entire analysis and reuse it in every command: `ucef.py --workspace <UCEF_WORKSPACE> ...`.
- Never infer the workspace from the current directory and never create `.ucef/` in a Java repository.
- Register every participating Java project with a stable `source_id`. Cross-project handoffs retain both the caller and callee `source_id`.
- Source Evidence uses `source_id` plus a path relative to that source root. Absolute source paths belong only in `sources.json`.
- Treat registered source roots as read-only. UCEF writes only beneath its workspace.

## Durable memory before final outputs

Conversation context is a disposable cache, not analysis storage. During excavation, every bounded probe produces:

1. **Observations** — concise atomic claims with evidence pointers, including partial facts and explicit unknowns.
2. **A Checkpoint** — current focus, visited references, provisional chain spine, unresolved questions, exactly one next probe, and a resume summary.

Run `checkpoint` after each probe and before retrieving a different symbol, branch, mapper, client, persistence statement, or configuration question. Never wait for a complete Fragment. After compaction or a new session, run `resume` and continue only from the latest durable Checkpoint.

Read [references/CHECKPOINT_CONTRACT.md](references/CHECKPOINT_CONTRACT.md) before excavating or resuming a Work Unit.

## Two final outputs

Each Work Unit contributes both:

1. **Reusable behavior** — a `BehaviorFragment` with a stable logical key, applicability conditions, entry/exit contract, decisions, field deltas, side effects, version/binding identity, and Evidence.
2. **Scenario assembly** — one or more `TraceStage` records that place reusable behavior into the current Scenario's ordered business story with current inputs, route outcomes, outputs, and handoffs.

Do not put pending Observations into the main dossier. Promote them into Evidence, reusable behavior, Scenario stages, lineage, persistence, external interaction, or explicit Gaps when the Work Unit contract is complete.

## Method tree and field graph

Business Stages are only the orientation layer. The main execution knowledge is a tree of reusable `MethodDefinition`, Scenario-specific `METHOD_INVOCATION`, and method-internal `STEP` nodes. Field lineage is a graph attached to those nodes, because values can split, merge, branch, overwrite, persist, leave the system, or return.

Before descending from an entry or newly discovered boundary, create or update the field inventory. Every field is tracked, explicitly excluded with a reason, or a visible Gap. Every method step declares `field_reads` and `field_writes`; “maps object A to B” is incomplete when relevant contained fields have not been enumerated.

Read [references/EXECUTION_TREE_CONTRACT.md](references/EXECUTION_TREE_CONTRACT.md) before decomposing methods or publishing HTML.

## Start or resume

If the named UCEF workspace does not exist, ask before creating it because initialization writes durable analysis artifacts. Then run `scripts/init_workspace.py --workspace <absolute-path>`. The chosen path must be outside every Java source tree.

Before excavation, load `<UCEF_WORKSPACE>/sources.json` and verify that every project needed by the Scenario has a registered `source_id`. Add missing sources explicitly with `ucef.py --workspace <UCEF_WORKSPACE> source-add`; do not relocate the workspace into a project.

Before excavation:

1. persist the Scenario, then run `resume --scenario <file> --work-unit <file>`; read `DURABLE RESUME STATE` first;
2. load only the active Scenario, Work Unit, and their referenced source registry entries;
3. run `ucef.py reuse` for each logical behavior key and `method-reuse` for each method symbol before opening its body;
4. reuse a Fragment only when code identity, binding context, applicability, and required coverage match;
5. if a reusable Fragment lacks one contract element, create `FRAGMENT_GAP_FILL` instead of re-excavating it;
6. load production configuration evidence relevant to the current decisions, never the entire configuration estate.

Read [references/WORKFLOW.md](references/WORKFLOW.md) for the execution cycle. Read [references/OUTPUT_CONTRACT.md](references/OUTPUT_CONTRACT.md) before creating an ingestion result. Read [references/READER_CONTRACT.md](references/READER_CONTRACT.md) when auditing or publishing a Scenario. Read [references/DATA_MODEL.md](references/DATA_MODEL.md) only when changing storage or import behavior.

## Excavation boundaries

- Work on one business stage, route decision, field lineage segment, persistence effect, or external interaction at a time.
- Inside that boundary, retrieve only one probe target at a time. Normalize and checkpoint all returned chain-changing facts before opening the next target.
- A method probe must identify the current invocation, split meaningful internal steps, and inventory every field read/write visible in the retrieved region before following another call.
- Do not close a method as complete when it contains only object names, method calls, or an opaque mapper description. Missing internal steps or unexpanded relevant fields become explicit Gaps.
- A method is Evidence, not automatically a reusable Fragment. Prefer a semantically complete fragment such as “resolve payment route” or “build and submit supplier request”.
- Separate reusable definitions from Scenario-specific outcomes. A route definition can be reused; its result must be recomputed for the current request and effective production configuration.
- Static reachability is a candidate path. Production configuration, runtime binding, request constraints, and test/runtime evidence determine Scenario applicability.
- Every important claim needs Evidence. Missing origins, consumers, branch outcomes, or response uses become explicit Gaps.
- Stop when the Work Unit objective is met, a verified complete Fragment contract is reached, an external boundary is fully described, or a named Gap is opened. Never stop merely because an existing symbol was found.

## Reuse rule

A Fragment may be reused without reopening its internal code only when all required dimensions match:

- source ID, repository, and logical symbol/behavior identity;
- code content hash or verified compatible revision;
- dependency-injection/profile/binding context;
- relevant configuration and request preconditions;
- required branch and field coverage;
- complete entry, exit, side-effect, and handoff contracts.

Otherwise reuse only the valid prefix and analyze the changed or missing part.

## Persist and audit

During excavation, write checkpoint payloads matching `runtime/checkpoint.schema.json` and persist them with `checkpoint --file <file> --work-unit <work-unit-file>`.

When ready to promote, write one JSON object matching `runtime/schema.json` under `<UCEF_WORKSPACE>/runs/`. Canonical records should cite their supporting `observation_ids`. Ingest it with `scripts/ucef.py --workspace <UCEF_WORKSPACE> ingest`. The runtime validates identities and references, records Observation promotion links, versions changed entities, and updates the Scenario dossier.

After each ingest, run Scenario audit. A Scenario may be marked `READABLE_COMPLETE` only when its trigger, terminal result, route outcomes, stage handoffs, critical field origins, persistence mappings, external parameter origins/uses, and known gaps satisfy the reader contract.

The default human view is `<UCEF_WORKSPACE>/site/index.html`. It must inline reused Fragment content inside the Scenario story. Links to source facts are secondary evidence, never the main narrative.
