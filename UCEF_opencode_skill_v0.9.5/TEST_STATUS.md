# UCEF v0.9.5 Test Status

Validated on Python 3.12 using only the standard library:

- Python source compilation: PASS
- JSON templates and runtime Schema parsing: PASS
- Independent analysis workspace initialization: PASS
- Execution from an arbitrary current directory: PASS
- Multiple read-only Java source registration: PASS
- Workspace/source tree nesting rejection: PASS
- Workspace artifact path escape rejection: PASS
- Registered `source_id` enforcement for source Evidence and code facts: PASS
- Append-only Work Unit Checkpoint sequencing: PASS
- Atomic Observation capture and exact-fact deduplication: PASS
- Store close/reopen and resume-context recovery: PASS
- Pending Observation overflow visibility and targeted retrieval: PASS
- Observation-to-canonical-entity promotion links: PASS
- Promoted Observation retention and reverse lookup: PASS
- Evidence-only Observation remains pending assembly: PASS
- Work Unit completion rejected while Observations remain unassembled: PASS
- Scenario `MEMORY_ASSEMBLY` completeness audit: PASS
- CLI `scenario-put`, `checkpoint`, `resume`, and `memory-query`: PASS
- Analysis Memory HTML page with pending/evidenced/assembled counts: PASS
- CLI doctor: PASS
- Scenario/Fragment/Evidence ingestion: PASS
- Candidate-to-confirmed Fragment upgrade with revision history: PASS
- Exact Fragment reuse lookup: PASS
- Scenario assembly context pack with reuse candidates: PASS
- 52K/16K default context budget and phase-routed contracts: PASS
- Anchor-preserving local execution-tree neighborhood selection: PASS
- Explicit target/active-field priority with bounded lineage loading: PASS
- Active Observation recovery outside the recent candidate pool: PASS
- Compact method reuse with full-record opt-in: PASS
- Omitted counts and narrow recovery hints: PASS
- Reader completeness audit: PASS
- Incomplete Scenario Gap generation and persistence: PASS
- Scenario-first HTML dossier generation: PASS
- Inline reused Fragment rendering: PASS
- Field lifecycle rendering: PASS
- Persistence mapping rendering: PASS
- External request origin / response usage rendering: PASS
- Variant alignment and first-divergence comparison: PASS
- End-to-end CLI smoke test in an isolated temporary workspace: PASS
- OpenCode primary Agent packaging, full permission, `padb` bootstrap, and `index-mcp_*` enablement: PASS
- MethodDefinition reuse plus Scenario-specific invocation tree ingestion: PASS
- Method-internal STEP decomposition and opaque-method audit: PASS
- Explicit field inventory and silent-field audit: PASS
- Predecessor-linked field lineage continuity audit: PASS
- Three-view HTML execution tree, node detail, and field-path synchronization: PASS

Seventeen runtime/package unit and integration tests pass. The skill-creator `quick_validate.py` helper could not run because its own PyYAML dependency is unavailable in the bundled environment; required frontmatter, all seven SKILL links, Python syntax, JSON parsing, and runtime behavior were checked separately.

The in-app browser blocks local `file://` navigation, so visual screenshot QA was not available in this environment. Generated DOM content and required reader sections were verified programmatically.
