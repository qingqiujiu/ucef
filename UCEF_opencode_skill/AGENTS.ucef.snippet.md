# UCEF repository guidance

- Treat source projects as read-only facts exposed through `index-mcp`.
- Use `obsidian-mcp` as the only analysis writing surface and durable memory.
- Keep business purpose, behavior, branch reasons, data meaning, and outcomes ahead of framework mechanisms.
- Reconstruct the end-to-end business chain and trace every important field to its final consumption or an explicit unknown break.
- Give each method on the selected business chain a stable Obsidian drill-down target without cataloging the entire repository.
- Select sequence, flow, state, ER, relationship, field-lifecycle, or decision diagrams only when the underlying facts support them.
- Maintain `调查状态.md` after meaningful understanding changes and before interruption; resume from it instead of rescanning.
- Keep the primary Agent as the sole Obsidian writer. Optional probes use only `index-mcp` and return compact evidence.
- Do not use custom UCEF runtimes, JSON submission schemas, coverage metrics, SQLite fact graphs, or generated HTML.
