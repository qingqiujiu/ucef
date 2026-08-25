from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .artifacts import ArtifactStore
from .audit import audit_scenario
from .compare import compare_scenarios
from .context import ContextBuilder
from .core import load_json, write_json
from .direct import DirectAnalysisService
from .ledger import CheckpointLedger
from .site import DossierSiteBuilder
from .store import FactStore
from .validator import IngestionValidator
from .workspace import AnalysisWorkspace, DEFAULT_CONFIG


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
        runtime_root() / "direct.schema.json",
        runtime_root() / "schema.json",
        runtime_root().parent / "references" / "DIRECT_ANALYSIS_CONTRACT.md",
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
    payload = json.loads(raw)
    store = make_store(workspace)
    try:
        result = DirectAnalysisService(store).submit(
            args.kind, args.run_id, args.task_id, payload
        )
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
        scenario = load_json(workspace.resolve(args.file))
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

    command = sub.add_parser("ingest")
    command.add_argument("--file", required=True)
    command.add_argument("--scenario")
    command.add_argument("--work-unit")
    command.set_defaults(func=cmd_ingest)

    command = sub.add_parser("scenario-put")
    command.add_argument("--file", required=True, help="Raw Scenario JSON relative to workspace")
    command.set_defaults(func=cmd_scenario_put)

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
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (KeyError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        emit({"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"})
        return 2
