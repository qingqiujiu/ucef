from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from .artifacts import ArtifactStore
from .audit import audit_scenario
from .compare import compare_scenarios
from .context import ContextBuilder
from .core import load_json, write_json
from .direct import DirectAnalysisService, SubmissionContractError
from .graph import ENTITY_TYPES, KnowledgeGraphService
from .ledger import CheckpointLedger
from .site import DossierSiteBuilder
from .store import FactStore
from .validator import IngestionValidator
from .workspace import AnalysisWorkspace, DEFAULT_CONFIG


def configure_utf8_stdio() -> None:
    """Keep the OpenCode/Bun subprocess boundary deterministic on every OS."""
    for stream, errors in ((sys.stdin, "strict"), (sys.stdout, "strict"), (sys.stderr, "backslashreplace")):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors=errors)


def load_json_text(raw: str) -> Any:
    """Parse UTF-8 text while accepting the optional BOM used by some Windows editors."""
    return json.loads(raw.removeprefix("\ufeff"))


def runtime_root() -> Path:
    return Path(__file__).resolve().parents[1]


def open_workspace(args: argparse.Namespace) -> AnalysisWorkspace:
    return AnalysisWorkspace.open(args.workspace, args.config)


def make_store(workspace: AnalysisWorkspace) -> FactStore:
    return FactStore(workspace.database_path)


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def cmd_doctor(args: argparse.Namespace) -> int:
    issues = []
    for path in (
        runtime_root() / "UCEF_RULES.md",
        runtime_root() / "schema.json",
        runtime_root() / "ucef" / "graph.py",
        runtime_root() / "ucef" / "experience.py",
        runtime_root().parent / "references" / "ADAPTIVE_ANALYSIS_CONTRACT.md",
    ):
        if not path.exists():
            issues.append(f"Missing: {path}")
    try:
        workspace = open_workspace(args)
        workspace.initialize_directories()
        sources = workspace.source_status()
        if not sources:
            issues.append("No Java data sources are registered")
        for source in sources:
            if not source["exists"]:
                issues.append(f"Source path does not exist: {source['source_id']} -> {source['path']}")
        store = make_store(workspace)
        store.close()
    except Exception as exc:
        issues.append(f"Runtime initialization failed: {type(exc).__name__}: {exc}")
    result = {
        "status": "OK" if not issues else "WARN",
        "issues": issues,
        "python": sys.version.split()[0],
        "external_dependencies": [],
        "workspace": str(Path(args.workspace).expanduser().resolve()),
    }
    emit(result)
    return 0 if not issues else 1


def cmd_init(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    workspace.initialize_directories()
    ArtifactStore(workspace.root).initialize()
    store = make_store(workspace)
    store.close()
    emit({"status": "initialized", **workspace.summary()})
    return 0


def cmd_bootstrap(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace).expanduser().resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    templates = runtime_root().parent / "templates"
    copies = (
        (templates / "config.json", workspace_root / "workspace.json"),
        (templates / "sources.json", workspace_root / "sources.json"),
        (templates / "scenario.json", workspace_root / "scenarios" / "scenario.example.json"),
        (templates / "adaptive_delta.example.json", workspace_root / "runs" / "adaptive_delta.example.json"),
    )
    created, kept = [], []
    for source, target in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            kept.append(str(target))
        else:
            shutil.copy2(source, target)
            created.append(str(target))
    workspace = AnalysisWorkspace.open(workspace_root, args.config)
    workspace.initialize_directories()
    ArtifactStore(workspace.root).initialize()
    store = make_store(workspace)
    store.close()
    emit({"status": "bootstrapped", **workspace.summary(), "created": created, "kept": kept})
    return 0


def make_graph(workspace: AnalysisWorkspace, store: FactStore) -> KnowledgeGraphService:
    registered = workspace.source_map()
    required = bool((workspace.config.get("sources") or {}).get("require_registered_evidence", True))
    return KnowledgeGraphService(
        store,
        registered_sources=set(registered) if required else None,
        config=workspace.config,
    )


def refresh_site(workspace: AnalysisWorkspace, store: FactStore) -> None:
    if (workspace.config.get("site") or {}).get("auto_update", True):
        DossierSiteBuilder(store, workspace.config, workspace.root).build()


def split_values(value: str | list[str] | None) -> list[str]:
    items = value if isinstance(value, list) else [value] if value else []
    return [part.strip() for item in items for part in str(item).split(",") if part.strip()]


def cmd_session_start(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        result = make_graph(workspace, store).start_session(
            args.scenario,
            goal=args.goal,
            priority_fields=split_values(args.priority_fields),
            context_target_tokens=args.context_target,
            total_token_budget=args.token_budget,
        )
        refresh_site(workspace, store)
        emit(result)
        return 0
    finally:
        store.close()


def cmd_session_delta(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    raw = args.payload if args.payload is not None else sys.stdin.read()
    if not raw.strip():
        raise ValueError("session-delta requires one semantic JSON milestone on stdin or --payload")
    payload = load_json_text(raw)
    store = make_store(workspace)
    try:
        result = make_graph(workspace, store).record_delta(args.session_id, payload)
        refresh_site(workspace, store)
        emit(result)
        return 0
    finally:
        store.close()


def cmd_session_context(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        emit(make_graph(workspace, store).build_context(
            args.session_id,
            focus=args.focus,
            fields=split_values(args.field),
            symbols=split_values(args.symbol),
            max_tokens=args.max_tokens,
        ))
        return 0
    finally:
        store.close()


def cmd_session_status(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        emit(make_graph(workspace, store).summary(args.session_id))
        return 0
    finally:
        store.close()


def cmd_session_finish(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        result = make_graph(workspace, store).finish_session(
            args.session_id, summary=args.summary, status=args.status,
        )
        refresh_site(workspace, store)
        emit(result)
        return 0
    finally:
        store.close()


def cmd_graph_query(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        service = make_graph(workspace, store)
        if args.entity:
            entity = service.find_entity(args.entity, args.scenario)
            if not entity:
                raise ValueError(f"Unknown graph entity: {args.entity}")
            result = {
                "entity": entity,
                "neighbors": service.entity_neighbors(entity["entity_id"], args.scenario),
                "scenarios": service.entity_scenarios(entity["entity_id"]),
            }
        elif args.full and args.scenario:
            result = service.scenario_graph(args.scenario)
        else:
            entities = service.list_entities(
                entity_type=args.type,
                scenario_id=args.scenario,
                search=args.search,
                limit=args.limit,
            )
            if not args.full:
                entities = [
                    {key: item.get(key) for key in (
                        "entity_id", "entity_type", "logical_key", "display_name",
                        "summary", "priority", "status",
                    )}
                    for item in entities
                ]
            result = {"count": len(entities), "entities": entities}
        emit(result)
        return 0
    finally:
        store.close()


def cmd_field_lineage(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        emit(make_graph(workspace, store).field_projection(args.scenario, args.field))
        return 0
    finally:
        store.close()


def cmd_config_resolve(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        try:
            value = load_json_text(args.value)
        except json.JSONDecodeError:
            value = args.value
        result = make_graph(workspace, store).resolve_configuration(
            args.scenario, args.key, value,
            environment=args.environment,
            evidence=args.evidence,
        )
        refresh_site(workspace, store)
        emit(result)
        return 0
    finally:
        store.close()


def cmd_entity_rename(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        result = make_graph(workspace, store).rename_entity(args.entity_id, args.name)
        refresh_site(workspace, store)
        emit(result)
        return 0
    finally:
        store.close()


def cmd_analysis_start(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        result = DirectAnalysisService(store).start(args.scenario, args.mode)
        DossierSiteBuilder(store, workspace.config, workspace.root).build()
        emit(result)
        return 0
    finally:
        store.close()


def cmd_analysis_next(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        emit(DirectAnalysisService(store).next_task(args.run_id))
        return 0
    finally:
        store.close()


def cmd_analysis_status(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        emit(DirectAnalysisService(store).status(args.run_id))
        return 0
    finally:
        store.close()


def cmd_submit_direct(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    raw = args.payload if args.payload is not None else sys.stdin.read()
    if not raw.strip():
        raise ValueError("submit-direct requires JSON on stdin or --payload")
    payload = load_json_text(raw)
    store = make_store(workspace)
    try:
        try:
            result = DirectAnalysisService(store).submit(
                args.kind, args.run_id, args.task_id, payload
            )
        except SubmissionContractError:
            DossierSiteBuilder(store, workspace.config, workspace.root).build()
            raise
        site = DossierSiteBuilder(store, workspace.config, workspace.root).build()
        emit({**result, "site": site})
        return 0
    finally:
        store.close()


def cmd_ingest(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    config = workspace.config
    store = make_store(workspace)
    try:
        data = load_json(workspace.resolve(args.file))
        registered_sources = set(workspace.source_map())
        require_sources = bool((config.get("sources") or {}).get("require_registered_evidence", True))
        report = IngestionValidator(store, registered_sources, require_sources).ingest(data, args.scenario, args.work_unit)
        scenario_id = report.get("scenario_id")
        if scenario_id and store.has("scenarios", scenario_id):
            report["audit"] = audit_scenario(store, scenario_id, persist=True)
        site_cfg = config.get("site") or {}
        if site_cfg.get("auto_update", True):
            report["site"] = DossierSiteBuilder(store, config, workspace.root).build()
        emit(report)
        return 1 if report["errors"] else 0
    finally:
        store.close()


def cmd_scenario_put(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    config = workspace.config
    store = make_store(workspace)
    try:
        if args.file:
            scenario = load_json(workspace.resolve(args.file))
        else:
            raw = args.payload if args.payload is not None else sys.stdin.read()
            if not raw.strip():
                raise ValueError("scenario-put requires --file, JSON on stdin, or --payload")
            scenario = load_json_text(raw)
        registered_sources = set(workspace.source_map())
        require_sources = bool((config.get("sources") or {}).get("require_registered_evidence", True))
        report = IngestionValidator(store, registered_sources, require_sources).ingest(
            {"scenario": scenario}, work_unit_id="SCENARIO_REGISTER"
        )
        emit(report)
        return 1 if report["errors"] else 0
    finally:
        store.close()


def cmd_audit(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        report = audit_scenario(store, args.scenario, persist=args.persist)
        emit(report)
        return 0 if report["readability_status"] == "READABLE_COMPLETE" else 2
    finally:
        store.close()


def cmd_reuse(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        results = store.find_fragments(
            args.logical_key, args.repository, args.code_hash, args.binding_hash, args.source_id
        )
        emit({"logical_key": args.logical_key, "result": results or [{"reuse": "MISS"}]})
        return 0
    finally:
        store.close()


def cmd_method_reuse(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        results = store.find_method_definitions(args.source_id, args.symbol, args.code_hash)
        if not args.full:
            results = [
                {
                    "reuse": item.get("reuse"),
                    "method_definition": {
                        key: (item.get("method_definition") or {}).get(key)
                        for key in (
                            "method_definition_id", "source_id", "symbol", "module", "signature",
                            "code_hash", "input_contract", "output_contract", "throws", "status",
                        )
                        if (item.get("method_definition") or {}).get(key) is not None
                    },
                }
                for item in results
            ]
        emit({"source_id": args.source_id, "symbol": args.symbol, "result": results or [{"reuse": "MISS"}]})
        return 0
    finally:
        store.close()


def cmd_context(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    config = workspace.config
    store = make_store(workspace)
    try:
        scenario = load_json(workspace.resolve(args.scenario))
        work_unit = load_json(workspace.resolve(args.work_unit))
        text = ContextBuilder(runtime_root(), store, config, workspace.load_sources()).build(scenario, work_unit)
        if args.output:
            target = workspace.resolve(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            print(target)
        else:
            print(text)
        return 0
    finally:
        store.close()


def cmd_checkpoint(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        payload = load_json(workspace.resolve(args.file))
        work_unit = load_json(workspace.resolve(args.work_unit))
        report = CheckpointLedger(store, set(workspace.source_map())).capture(payload, work_unit)
        emit(report)
        return 1 if report["errors"] else 0
    finally:
        store.close()


def cmd_memory_query(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        observations = store.list_observations(
            observation_id=args.observation_id,
            work_unit_id=args.work_unit,
            scenario_id=args.scenario,
            source_id=args.source_id,
            observation_kind=args.kind,
            subject=args.subject,
            promotion_status=args.status,
            limit=args.limit,
        )
        result: dict[str, Any] = {"count": len(observations), "observations": observations}
        if args.work_unit:
            state = store.work_unit_memory(args.work_unit, 1)
            state.pop("pending_observations", None)
            result["memory_index"] = state
        emit(result)
        return 0
    finally:
        store.close()


def cmd_query(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        if args.collection == "dossier":
            if not args.scenario:
                raise ValueError("--scenario is required for dossier")
            result = store.scenario_dossier(args.scenario)
        else:
            result = store.list_collection(args.collection, args.scenario)
        emit(result)
        return 0
    finally:
        store.close()


def cmd_compare(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    store = make_store(workspace)
    try:
        result = compare_scenarios(store, args.left, args.right)
        if args.output:
            write_json(workspace.resolve(args.output), result)
        else:
            emit(result)
        return 0
    finally:
        store.close()


def cmd_site(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    config = workspace.config
    store = make_store(workspace)
    try:
        result = DossierSiteBuilder(store, config, workspace.root).build()
        emit(result)
        return 0
    finally:
        store.close()


def cmd_source_list(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    emit({"workspace": str(workspace.root), "sources": workspace.source_status()})
    return 0


def cmd_source_add(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    source = workspace.add_source(
        args.source_id, args.path, args.repository, args.revision, args.role
    )
    emit({"status": "registered", "source": source})
    return 0


def cmd_artifact_add(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    source_path = Path(args.file).expanduser()
    if not source_path.is_absolute():
        source_path = workspace.resolve(args.file)
    artifact = ArtifactStore(workspace.root).add_json(
        source_path,
        scenario_id=args.scenario,
        source_id=args.source_id,
        environment=args.environment,
        snapshot_id=args.snapshot,
        kind=args.kind,
        extra_redact_keys=set(args.redact_key or []),
    )
    store = make_store(workspace)
    try:
        site = DossierSiteBuilder(store, workspace.config, workspace.root).build()
    finally:
        store.close()
    emit({"status": "registered", "artifact": artifact, "site": site})
    return 0


def cmd_artifact_list(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    artifacts = ArtifactStore(workspace.root).list_artifacts(args.scenario)
    emit({"workspace": str(workspace.root), "count": len(artifacts), "artifacts": artifacts})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ucef", description="UCEF business execution dossier runtime")
    parser.add_argument(
        "--workspace",
        required=True,
        help="Independent UCEF analysis workspace; must be outside every Java source tree",
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Config path relative to the workspace")
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("doctor")
    command.set_defaults(func=cmd_doctor)
    command = sub.add_parser("init")
    command.set_defaults(func=cmd_init)
    command = sub.add_parser("bootstrap")
    command.set_defaults(func=cmd_bootstrap)

    command = sub.add_parser("ingest")
    command.add_argument("--file", required=True)
    command.add_argument("--scenario")
    command.add_argument("--work-unit")
    command.set_defaults(func=cmd_ingest)

    command = sub.add_parser("scenario-put")
    command.add_argument("--file", help="Raw Scenario JSON relative to workspace")
    command.add_argument("--payload", help="Scenario JSON object; stdin is preferred")
    command.set_defaults(func=cmd_scenario_put)

    command = sub.add_parser("session-start", help="Start or resume one adaptive main-model exploration")
    command.add_argument("--scenario", required=True)
    command.add_argument("--goal")
    command.add_argument("--priority-fields", help="Comma-separated P0 business fields")
    command.add_argument("--context-target", type=int)
    command.add_argument("--token-budget", type=int)
    command.set_defaults(func=cmd_session_start)

    command = sub.add_parser("session-delta", help="Persist one compact semantic milestone")
    command.add_argument("--session-id", required=True)
    command.add_argument("--payload", help="JSON object; stdin is preferred")
    command.set_defaults(func=cmd_session_delta)

    command = sub.add_parser("session-context", help="Retrieve bounded facts relevant to the current focus")
    command.add_argument("--session-id", required=True)
    command.add_argument("--focus")
    command.add_argument("--field", action="append")
    command.add_argument("--symbol", action="append")
    command.add_argument("--max-tokens", type=int)
    command.set_defaults(func=cmd_session_context)

    command = sub.add_parser("session-status")
    command.add_argument("--session-id", required=True)
    command.set_defaults(func=cmd_session_status)

    command = sub.add_parser("session-finish")
    command.add_argument("--session-id", required=True)
    command.add_argument("--summary")
    command.add_argument("--status", choices=["COMPLETE", "PARTIAL", "STOPPED"], default="COMPLETE")
    command.set_defaults(func=cmd_session_finish)

    command = sub.add_parser("graph-query", help="Query shared business entities without loading the whole graph")
    command.add_argument("--scenario")
    command.add_argument("--type", choices=sorted(ENTITY_TYPES))
    command.add_argument("--search")
    command.add_argument("--entity")
    command.add_argument("--full", action="store_true")
    command.add_argument("--limit", type=int, default=30)
    command.set_defaults(func=cmd_graph_query)

    command = sub.add_parser("field-lineage")
    command.add_argument("--scenario", required=True)
    command.add_argument("--field", required=True)
    command.set_defaults(func=cmd_field_lineage)

    command = sub.add_parser("config-resolve")
    command.add_argument("--scenario", required=True)
    command.add_argument("--key", required=True)
    command.add_argument("--value", required=True)
    command.add_argument("--environment", default="prod")
    command.add_argument("--evidence")
    command.set_defaults(func=cmd_config_resolve)

    command = sub.add_parser("entity-rename")
    command.add_argument("--entity-id", required=True)
    command.add_argument("--name", required=True)
    command.set_defaults(func=cmd_entity_rename)

    command = sub.add_parser("analysis-start")
    command.add_argument("--scenario", required=True)
    command.add_argument("--mode", choices=["QUICK", "STANDARD", "DEEP"], default="STANDARD")
    command.set_defaults(func=cmd_analysis_start)

    command = sub.add_parser("analysis-next")
    command.add_argument("--run-id", required=True)
    command.set_defaults(func=cmd_analysis_next)

    command = sub.add_parser("analysis-status")
    command.add_argument("--run-id", required=True)
    command.set_defaults(func=cmd_analysis_status)

    command = sub.add_parser("submit-direct")
    command.add_argument("--kind", required=True, choices=["plan", "block", "overview", "gap"])
    command.add_argument("--run-id", required=True)
    command.add_argument("--task-id", required=True)
    command.add_argument("--payload", help="JSON object; stdin is preferred for large submissions")
    command.set_defaults(func=cmd_submit_direct)

    command = sub.add_parser("audit")
    command.add_argument("--scenario", required=True)
    command.add_argument("--persist", action="store_true")
    command.set_defaults(func=cmd_audit)

    command = sub.add_parser("reuse")
    command.add_argument("--logical-key", required=True)
    command.add_argument("--source-id")
    command.add_argument("--repository")
    command.add_argument("--code-hash")
    command.add_argument("--binding-hash")
    command.set_defaults(func=cmd_reuse)

    command = sub.add_parser("method-reuse")
    command.add_argument("--source-id", required=True)
    command.add_argument("--symbol", required=True)
    command.add_argument("--code-hash")
    command.add_argument("--full", action="store_true", help="return the complete stored method record")
    command.set_defaults(func=cmd_method_reuse)

    command = sub.add_parser("build-context")
    command.add_argument("--scenario", required=True)
    command.add_argument("--work-unit", required=True)
    command.add_argument("--output")
    command.set_defaults(func=cmd_context)

    command = sub.add_parser("resume")
    command.add_argument("--scenario", required=True)
    command.add_argument("--work-unit", required=True)
    command.add_argument("--output")
    command.set_defaults(func=cmd_context)

    command = sub.add_parser("checkpoint")
    command.add_argument("--file", required=True, help="Checkpoint payload relative to workspace")
    command.add_argument("--work-unit", required=True, help="Active Work Unit JSON relative to workspace")
    command.set_defaults(func=cmd_checkpoint)

    command = sub.add_parser("memory-query")
    command.add_argument("--observation-id")
    command.add_argument("--work-unit")
    command.add_argument("--scenario")
    command.add_argument("--source-id")
    command.add_argument("--kind")
    command.add_argument("--subject")
    command.add_argument("--status", choices=["ANY", "PENDING", "EVIDENCED", "PROMOTED"], default="ANY")
    command.add_argument("--limit", type=int, default=100)
    command.set_defaults(func=cmd_memory_query)

    command = sub.add_parser("query")
    command.add_argument("--collection", required=True, choices=[
        "dossier", "scenarios", "scenario_plans", "business_blocks", "scenario_overviews", "analysis_runs", "analysis_tasks", "fragments", "method_definitions", "trace_stages", "execution_nodes",
        "field_inventory", "route_decisions", "field_lineage_steps", "persistence_effects", "external_interactions", "gaps", "work_units",
        "observations", "checkpoints",
    ])
    command.add_argument("--scenario")
    command.set_defaults(func=cmd_query)

    command = sub.add_parser("compare")
    command.add_argument("--left", required=True)
    command.add_argument("--right", required=True)
    command.add_argument("--output")
    command.set_defaults(func=cmd_compare)

    command = sub.add_parser("site")
    command.set_defaults(func=cmd_site)

    command = sub.add_parser("source-list")
    command.set_defaults(func=cmd_source_list)

    command = sub.add_parser("source-add")
    command.add_argument("--source-id", required=True)
    command.add_argument("--path", required=True)
    command.add_argument("--repository")
    command.add_argument("--revision")
    command.add_argument("--role")
    command.set_defaults(func=cmd_source_add)

    command = sub.add_parser("artifact-add")
    command.add_argument("--file", required=True, help="UTF-8 JSON file; copied as a redacted content-addressed snapshot")
    command.add_argument("--scenario")
    command.add_argument("--source-id")
    command.add_argument("--environment")
    command.add_argument("--snapshot")
    command.add_argument("--kind", default="CONFIG_JSON")
    command.add_argument("--redact-key", action="append", help="Additional exact JSON key to redact; may be repeated")
    command.set_defaults(func=cmd_artifact_add)

    command = sub.add_parser("artifact-list")
    command.add_argument("--scenario")
    command.set_defaults(func=cmd_artifact_list)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except SubmissionContractError as exc:
        emit(exc.as_dict())
        return 2
    except (KeyError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        emit({"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"})
        return 2
