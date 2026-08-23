# UCEF OpenCode Workflow

## Responsibility split

- OpenCode agent: orchestration and reasoning.
- IDEA Index MCP: Java semantic navigation and source discovery.
- UCEF SQLite: durable machine fact store.
- Obsidian MCP: compact human-readable knowledge view.
- Obsidian notes are not technical truth unless re-verified against evidence.

## Recommended cycle

1. Define or select one Scenario.
2. Define one narrow Work Unit.
3. Query IDEA Index MCP natively in OpenCode:
   definition → implementations/references → callers/callees as needed.
4. Analyze only the Work Unit scope.
5. Save one UCEF JSON result under `.ucef/runs/`.
6. Ingest it through `scripts/ucef.py ingest`.
7. Verify important Candidate facts before marking Confirmed.
8. Create the next Work Unit from remaining Unknowns.
9. Sync compact Scenario summaries to Obsidian only when useful.

## Important

Do not try to read the entire repository or Vault into context.
Use IDEA MCP and SQLite queries to retrieve only the current neighborhood.


## Human explorer

After an ingest, open `.ucef/site/index.html`. The site is incremental: entity chunks are content-hashed and unchanged files are not rewritten. Use `python .opencode/skills/ucef/scripts/ucef.py site stats` to inspect the current build.
