---
name: ucef
description: Reconstruct reusable, evidence-backed Java business execution dossiers across projects, production configurations, routing variants, field transformations, persistence, and external APIs. Use when a reader who knows Java but not the system must understand and compare complete business paths without repeatedly excavating already verified behavior.
compatibility: OpenCode v2; Python 3.10+
metadata:
  framework: UCEF
  version: "0.9.1"
---

# UCEF

Produce a self-contained business execution dossier, not a directory of code facts. The primary acceptance test is whether a Java developer unfamiliar with the system can understand the selected path, explain why production configuration selects it, trace important fields from origin to persistence or external use, and identify every external request/response's origin and business effect.

## Hard workspace boundary

UCEF is an independent analysis workspace. Java projects are registered read-only data sources; they never contain UCEF databases, scenarios, contexts, runs, or generated sites.

- Select one explicit absolute workspace path for the entire analysis and reuse it in every command: `ucef.py --workspace <UCEF_WORKSPACE> ...`.
- Never infer the workspace from the current directory and never create `.ucef/` in a Java repository.
- Register every participating Java project with a stable `source_id`. Cross-project handoffs retain both the caller and callee `source_id`.
- Source Evidence uses `source_id` plus a path relative to that source root. Absolute source paths belong only in `sources.json`.
- Treat registered source roots as read-only. UCEF writes only beneath its workspace.

## Two outputs, every time

Each Work Unit contributes both:

1. **Reusable behavior** — a `BehaviorFragment` with a stable logical key, applicability conditions, entry/exit contract, decisions, field deltas, side effects, version/binding identity, and Evidence.
2. **Scenario assembly** — one or more `TraceStage` records that place reusable behavior into the current Scenario's ordered business story with current inputs, route outcomes, outputs, and handoffs.

Do not submit disconnected facts. Facts that are not placed into the Scenario remain pending evidence and must not appear in the main dossier.

## Start or resume

If the named UCEF workspace does not exist, ask before creating it because initialization writes durable analysis artifacts. Then run `scripts/init_workspace.py --workspace <absolute-path>`. The chosen path must be outside every Java source tree.

Before excavation, load `<UCEF_WORKSPACE>/sources.json` and verify that every project needed by the Scenario has a registered `source_id`. Add missing sources explicitly with `ucef.py --workspace <UCEF_WORKSPACE> source-add`; do not relocate the workspace into a project.

Before excavation:

1. load only the active Scenario, Work Unit, and their referenced source registry entries;
2. run `ucef.py reuse` for each entry symbol or logical behavior key;
3. reuse a Fragment only when code identity, binding context, applicability, and required coverage match;
4. if a reusable Fragment lacks one contract element, create `FRAGMENT_GAP_FILL` instead of re-excavating it;
5. load production configuration evidence relevant to the current decisions, never the entire configuration estate.

Read [references/WORKFLOW.md](references/WORKFLOW.md) for the execution cycle. Read [references/OUTPUT_CONTRACT.md](references/OUTPUT_CONTRACT.md) before creating an ingestion result. Read [references/READER_CONTRACT.md](references/READER_CONTRACT.md) when auditing or publishing a Scenario. Read [references/DATA_MODEL.md](references/DATA_MODEL.md) only when changing storage or import behavior.

## Excavation boundaries

- Work on one business stage, route decision, field lineage segment, persistence effect, or external interaction at a time.
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

Write one JSON object matching `runtime/schema.json` under `<UCEF_WORKSPACE>/runs/`, then ingest it with `scripts/ucef.py --workspace <UCEF_WORKSPACE> ingest`. The runtime assigns missing IDs, validates source identities and references, versions changed entities, and updates the Scenario dossier.

After each ingest, run Scenario audit. A Scenario may be marked `READABLE_COMPLETE` only when its trigger, terminal result, route outcomes, stage handoffs, critical field origins, persistence mappings, external parameter origins/uses, and known gaps satisfy the reader contract.

The default human view is `<UCEF_WORKSPACE>/site/index.html`. It must inline reused Fragment content inside the Scenario story. Links to source facts are secondary evidence, never the main narrative.
