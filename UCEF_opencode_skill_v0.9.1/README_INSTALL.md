# UCEF v0.9.1 for OpenCode

UCEF builds reusable, evidence-backed Java business execution dossiers. Its analysis workspace is independent from every Java project and has no third-party Python runtime dependencies.

## Install

Copy `.opencode/skills/ucef/` to a location OpenCode can discover. OpenCode may require the skill files to be project-local, but that installation location is not the UCEF analysis workspace and must not receive analysis state.

## Initialize

Choose a dedicated directory outside all Java repositories. Initialization creates durable analysis artifacts only there:

```bash
python .opencode/skills/ucef/scripts/init_workspace.py --workspace D:/ucef/order-analysis
```

Register every Java project as a read-only data source. The stable ID is used in Scenarios, Work Units, Fragments, and source Evidence:

```bash
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis source-add --source-id gateway --path D:/repos/order-gateway --repository company/order-gateway
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis source-add --source-id order-core --path D:/repos/order-core --repository company/order-core
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis source-list
```

The runtime rejects a source nested inside the UCEF workspace and a workspace nested inside a source repository.

## Core commands

```bash
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis doctor
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis reuse --logical-key payment.route --source-id order-core
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis build-context --scenario scenarios/pay.json --work-unit work_units/pending/wu.json
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis ingest --file runs/result.json --work-unit WU-PAY-01
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis audit --scenario SCN-PAY --persist
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis site
```

Open `D:/ucef/order-analysis/site/index.html`. The main view is a Scenario dossier with an inline business story, field lineage, persistence, external request/response provenance, and explicit gaps. Reused Fragments appear inline rather than as link-only cards.

## Workspace layout

```text
D:/ucef/order-analysis/
├── workspace.json
├── sources.json
├── ucef.db
├── scenarios/
├── work_units/
├── contexts/
├── runs/
└── site/
```

Java projects remain separate:

```text
D:/repos/order-gateway/   # source_id=gateway, read only
D:/repos/order-core/      # source_id=order-core, read only
D:/repos/common-client/   # source_id=common-client, read only
```

## Runtime requirements

- Python 3.10+
- Python standard library only
- OpenCode v2
- IDEA Index MCP recommended for semantic Java retrieval

Production configuration may be queried through the tools available in the user's OpenCode environment. Store relevant effective values as `CONFIG` Evidence; do not persist secrets.
