# UCEF 1.0 Minimal Rules

The main model understands the Scenario; the runtime owns persistence, stable shared identities, bounded recall, evidence, configuration state, and deterministic presentation.

1. Keep Java repositories read-only and write only to the explicitly selected independent workspace.
2. Explain behavior that changes the current business outcome; do not enumerate an irrelevant whole-repository call graph.
3. Preserve real decisions and alternative branches without claiming production certainty from static reachability.
4. If PADB or another trustworthy configuration source is unavailable, record `CONFIG_UNRESOLVED`; never guess a value.
5. Track P0 fields across request, decision, significant transformation, database column, outbound request, and consumed response.
6. Collapse ordinary DTO copies, simple delegation, and framework pass-through; keep P1/P2 detail proportional to business impact.
7. Record origins for external request fields, targets for consumed responses, and mappings for important persistence columns.
8. Every significant claim needs concise source-relative evidence; missing knowledge becomes an explicit Gap, not an invented bridge.
9. Persist concise milestones when a meaningful understanding has formed, not after every semantic probe.
10. Resume through the global digest and focus-targeted context; the entire graph stays in SQLite.
11. Reuse shared systems, modules, decisions, fields, and tables only when their stable logical identity and applicability match.
12. Exclude logs unless the user explicitly requests them, and never persist credentials, secrets, tokens, or unrelated sensitive values.
13. Let the program select HTML components and generate diagrams from the same facts; the model does not write presentation markup.
14. Stop once the business objective is met, the agreed budget is reached, or a required permission or source is unavailable.
