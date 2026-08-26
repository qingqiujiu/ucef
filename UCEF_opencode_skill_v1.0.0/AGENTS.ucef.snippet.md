# UCEF repository guidance

- Keep Java repositories read-only and write UCEF state only to the explicitly selected independent workspace.
- Let the primary model directly understand the business chain; do not create a fixed Planner/Block/Finalizer pipeline.
- Persist small semantic milestones into the shared UCEF 1.0 fact graph; do not checkpoint every source lookup.
- Keep all meaningful decisions and branches, trace P0 field transformations and boundaries, and collapse ordinary DTO copies.
- Without verified production configuration or PADB access, retain `CONFIG_UNRESOLVED`; never guess the active branch.
- Use focused `index-mcp_*` and bounded UCEF context/entity queries instead of loading full repositories or dossiers.
- Exclude logs by default; redact secrets and preserve source-relative evidence.
- Let the runtime generate cross-linked offline HTML and deterministic diagrams from persisted facts.
- Keep v0.9/v0.10 import and direct commands readable for compatibility, but out of the default workflow.
