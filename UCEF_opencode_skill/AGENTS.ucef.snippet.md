# UCEF repository guidance

- Keep source repositories read-only; write only to the user-selected Obsidian analysis directory.
- Let the primary model own business understanding, prioritization, note structure, and diagram choice.
- Reconstruct the business chain from the user's question to its outcome, not as a class inventory.
- Trace every important field through its meaningful lifecycle, preserving explicit unknown breaks.
- Give every method on the selected business chain a stable Obsidian drill-down target.
- Use `.ucef/state.json` only for questions, claims, evidence references, current focus, and recovery checkpoints.
- Update state when understanding changes, not after every lookup; checkpoint before interruption or focus changes.
- Keep the primary Agent as the sole state writer. Optional probes return compact evidence and never edit global notes.
- Do not use entity coverage, fixed Planner/Block/Finalizer queues, SQLite fact graphs, or generated HTML.
