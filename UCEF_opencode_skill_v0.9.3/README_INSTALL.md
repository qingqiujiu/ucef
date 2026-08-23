# UCEF v0.9.3 for OpenCode

UCEF builds reusable, evidence-backed Java business execution dossiers. Its analysis workspace is independent from every Java project and has no third-party Python runtime dependencies.

## Install

Copy `.opencode/skills/ucef/` to a location OpenCode can discover. OpenCode may require the skill files to be project-local, but that installation location is not the UCEF analysis workspace and must not receive analysis state.

This release also contains `.opencode/agents/ucef-java-chain.md`, a selectable primary Agent with all OpenCode permissions allowed. It loads `ucef` and the user's `padb` Skill, enables `index-mcp_*`, and enforces one-probe/one-checkpoint persistence for long chains. See [OPENCODE_AGENT_SETUP.md](OPENCODE_AGENT_SETUP.md).

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
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis scenario-put --file scenarios/pay.json
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis resume --scenario scenarios/pay.json --work-unit work_units/pending/wu.json --output contexts/wu.md
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis checkpoint --file runs/checkpoint.json --work-unit work_units/pending/wu.json
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis memory-query --work-unit WU-PAY-01 --status PENDING --subject paymentNo
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis ingest --file runs/result.json --work-unit WU-PAY-01
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis audit --scenario SCN-PAY --persist
python .opencode/skills/ucef/scripts/ucef.py --workspace D:/ucef/order-analysis site
```

## Long-chain anti-loss cycle

The chat context is not the source of truth. For each bounded probe:

1. retrieve one symbol, route, mapper, persistence operation, external call, or focused configuration question;
2. convert every chain-changing discovery into concise Observations;
3. persist the Observations and current Checkpoint before retrieving another target;
4. after compaction or a new session, run `resume` and continue from `latest_checkpoint.next_probe`.

`checkpoint` accepts `runs/checkpoint.example.json` format. Identical Observations are deduplicated. Checkpoints are append-only. Resume packs include a bounded pending frontier, grouped counts, visited references, and explicit omitted counts. Use `memory-query` to retrieve omitted durable facts by subject, kind, source, or Observation ID.

When a Work Unit is ready, canonical result records cite `observation_ids`. Successful ingestion links those Observations to Evidence and final Fragment/stage/route/lineage/persistence/external/Gap entities without deleting the original ledger entries. Evidence-only facts remain in the pending-assembly frontier until they are actually placed into the reusable or Scenario layer.

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
