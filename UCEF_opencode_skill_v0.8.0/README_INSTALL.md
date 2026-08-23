# UCEF for OpenCode — Install

This package is already laid out for a project-local OpenCode skill.

## Project-local install

Extract/copy the `.opencode/skills/ucef/` directory into your Java project root:

```text
your-java-project/
├── .opencode/
│   └── skills/
│       └── ucef/
│           ├── SKILL.md
│           ├── scripts/
│           ├── runtime/
│           ├── templates/
│           └── references/
├── AGENTS.md
└── src/
```

OpenCode automatically discovers project skills under `.opencode/skills/<name>/SKILL.md`.

## Global install

The same `ucef` directory can instead be copied to:

```text
~/.config/opencode/skills/ucef/
```

Then every project can use the same UCEF skill.

## Initialize one project

From the project root, run:

```bash
python .opencode/skills/ucef/scripts/init_project.py
```

For a global install, use the equivalent path under `~/.config/opencode/skills/ucef/`.

This creates:

```text
.ucef/
├── config.yaml
├── ucef.db
├── scenarios/
├── work_units/
├── contexts/
├── metadata/
├── overrides.json
├── site/
└── runs/
```

## OpenCode-native MCP recommendation

Keep IDEA/Obsidian `transport: none` in `.ucef/config.yaml` when OpenCode itself already exposes those MCP tools.

In that mode the OpenCode agent calls MCP tools natively. UCEF runtime remains responsible for durable facts, validation, context state, and queries.

Only configure UCEF `bridge` transport if your MCP server is independently callable outside OpenCode.

## AGENTS.md

Do not paste the whole UCEF rule set into AGENTS.md. Add only the short snippet in `AGENTS.ucef.snippet.md`.


## Business Explorer (v0.8)

UCEF now has three human projections over the same store:

- **业务链路 / Chains** — one Scenario across multiple systems and modules.
- **系统结构 / Systems** — one system, its modules, participating chains, nodes and data.
- **数据模型 / Data Model** — authoritative Table/Column/Index/Relation metadata.

Import system/database metadata:

```bash
python .opencode/skills/ucef/scripts/ucef.py metadata import --file .ucef/metadata/system-db.yaml
```

Build/read offline:

```bash
python .opencode/skills/ucef/scripts/ucef.py site build
```

Open `.ucef/site/index.html`. This mode is read-only and works with `file://`.

For the editable local workbench:

```bash
python .opencode/skills/ucef/scripts/ucef.py site serve --open
```

Manual display/classification edits are written to `.ucef/overrides.json`; physical DB metadata and technical Facts are not overwritten. A technical correction from the UI creates a `MANUAL_FACT_REVIEW` Work Unit for AI verification.

Normal `ingest` and `metadata import` can incrementally update the site. Entity hashes ensure unchanged pages/data chunks are not rewritten.

Detailed behavior: `.opencode/skills/ucef/references/HTML_EXPLORER.md` and `DATA_MODEL.md`.
