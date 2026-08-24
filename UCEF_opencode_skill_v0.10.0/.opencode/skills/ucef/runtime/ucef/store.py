from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .core import canonical_hash, new_id, now_iso


SCHEMA_SQL = r'''
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entity_revisions (
  revision_id TEXT PRIMARY KEY,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_revisions_entity
  ON entity_revisions(entity_type, entity_id, created_at);

CREATE TABLE IF NOT EXISTS evidences (
  evidence_id TEXT PRIMARY KEY,
  scenario_id TEXT,
  evidence_kind TEXT,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenarios (
  scenario_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  business_operation TEXT,
  status TEXT,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS behavior_fragments (
  fragment_id TEXT PRIMARY KEY,
  logical_key TEXT NOT NULL,
  repository TEXT,
  code_hash TEXT,
  binding_hash TEXT,
  status TEXT,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fragments_lookup
  ON behavior_fragments(logical_key, repository, code_hash, binding_hash, status);

CREATE TABLE IF NOT EXISTS method_definitions (
  method_definition_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  code_hash TEXT,
  status TEXT,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_method_definition_lookup
  ON method_definitions(source_id, symbol, code_hash, status);

CREATE TABLE IF NOT EXISTS trace_stages (
  stage_id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  sequence_no REAL NOT NULL,
  fragment_id TEXT,
  stage_type TEXT,
  status TEXT,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id),
  FOREIGN KEY(fragment_id) REFERENCES behavior_fragments(fragment_id)
);
CREATE INDEX IF NOT EXISTS idx_trace_scenario
  ON trace_stages(scenario_id, sequence_no, stage_id);

CREATE TABLE IF NOT EXISTS implementation_slices (
  slice_id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  stage_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  focus_mode TEXT NOT NULL,
  sequence_no REAL NOT NULL,
  closure_status TEXT NOT NULL,
  status TEXT,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id),
  FOREIGN KEY(stage_id) REFERENCES trace_stages(stage_id)
);
CREATE INDEX IF NOT EXISTS idx_slice_stage
  ON implementation_slices(scenario_id, stage_id, sequence_no, slice_id);

CREATE TABLE IF NOT EXISTS coverage_gates (
  gate_id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  stage_id TEXT,
  gate_type TEXT NOT NULL,
  priority TEXT NOT NULL,
  status TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id),
  FOREIGN KEY(stage_id) REFERENCES trace_stages(stage_id)
);
CREATE INDEX IF NOT EXISTS idx_gate_priority
  ON coverage_gates(scenario_id, status, priority, gate_type);

CREATE TABLE IF NOT EXISTS scenario_plans (
  plan_id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  status TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id)
);

CREATE TABLE IF NOT EXISTS business_blocks (
  block_id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  sequence_no REAL NOT NULL,
  depth TEXT NOT NULL,
  status TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id)
);
CREATE INDEX IF NOT EXISTS idx_business_blocks_scenario
  ON business_blocks(scenario_id, sequence_no, block_id);

CREATE TABLE IF NOT EXISTS scenario_overviews (
  overview_id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  status TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id)
);

CREATE TABLE IF NOT EXISTS analysis_runs (
  run_id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  deadline_at TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id)
);

CREATE TABLE IF NOT EXISTS analysis_tasks (
  task_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  scenario_id TEXT NOT NULL,
  role TEXT NOT NULL,
  block_id TEXT,
  sequence_no REAL NOT NULL,
  status TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id),
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id)
);
CREATE INDEX IF NOT EXISTS idx_analysis_tasks_pending
  ON analysis_tasks(run_id, status, sequence_no, task_id);

CREATE TABLE IF NOT EXISTS submission_receipts (
  receipt_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(run_id, task_id, payload_hash),
  FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id),
  FOREIGN KEY(task_id) REFERENCES analysis_tasks(task_id)
);

CREATE TABLE IF NOT EXISTS execution_nodes (
  execution_node_id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  parent_node_id TEXT,
  stage_id TEXT,
  method_definition_id TEXT,
  node_type TEXT NOT NULL,
  sequence_no REAL NOT NULL,
  status TEXT,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id),
  FOREIGN KEY(stage_id) REFERENCES trace_stages(stage_id),
  FOREIGN KEY(method_definition_id) REFERENCES method_definitions(method_definition_id)
);
CREATE INDEX IF NOT EXISTS idx_execution_tree
  ON execution_nodes(scenario_id, parent_node_id, sequence_no, execution_node_id);

CREATE TABLE IF NOT EXISTS field_inventory (
  field_id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  canonical_field TEXT NOT NULL,
  priority TEXT NOT NULL,
  tracking_status TEXT NOT NULL,
  status TEXT,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_field_inventory_scenario
  ON field_inventory(scenario_id, canonical_field);

CREATE TABLE IF NOT EXISTS route_decisions (
  decision_id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  stage_id TEXT,
  status TEXT,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id),
  FOREIGN KEY(stage_id) REFERENCES trace_stages(stage_id)
);

CREATE TABLE IF NOT EXISTS field_lineage_steps (
  lineage_step_id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  stage_id TEXT,
  canonical_field TEXT NOT NULL,
  sequence_no REAL NOT NULL,
  status TEXT,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id),
  FOREIGN KEY(stage_id) REFERENCES trace_stages(stage_id)
);
CREATE INDEX IF NOT EXISTS idx_lineage_scenario_field
  ON field_lineage_steps(scenario_id, canonical_field, sequence_no);

CREATE TABLE IF NOT EXISTS persistence_effects (
  effect_id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  stage_id TEXT,
  status TEXT,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id),
  FOREIGN KEY(stage_id) REFERENCES trace_stages(stage_id)
);

CREATE TABLE IF NOT EXISTS external_interactions (
  interaction_id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  stage_id TEXT,
  status TEXT,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id),
  FOREIGN KEY(stage_id) REFERENCES trace_stages(stage_id)
);

CREATE TABLE IF NOT EXISTS gaps (
  gap_id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  stage_id TEXT,
  category TEXT,
  severity TEXT,
  status TEXT,
  auto_generated INTEGER NOT NULL DEFAULT 0,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id),
  FOREIGN KEY(stage_id) REFERENCES trace_stages(stage_id)
);
CREATE INDEX IF NOT EXISTS idx_gaps_scenario
  ON gaps(scenario_id, status, severity, category);

CREATE TABLE IF NOT EXISTS work_units (
  work_unit_id TEXT PRIMARY KEY,
  scenario_id TEXT,
  work_type TEXT,
  status TEXT,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
  observation_id TEXT PRIMARY KEY,
  fingerprint TEXT NOT NULL UNIQUE,
  scenario_id TEXT NOT NULL,
  work_unit_id TEXT NOT NULL,
  source_id TEXT,
  observation_kind TEXT NOT NULL,
  subject_key TEXT NOT NULL,
  confidence TEXT,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id),
  FOREIGN KEY(work_unit_id) REFERENCES work_units(work_unit_id)
);
CREATE INDEX IF NOT EXISTS idx_observations_work_unit
  ON observations(work_unit_id, observation_kind, source_id, created_at);
CREATE INDEX IF NOT EXISTS idx_observations_subject
  ON observations(scenario_id, source_id, subject_key, observation_kind);

CREATE TABLE IF NOT EXISTS work_unit_checkpoints (
  checkpoint_id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  work_unit_id TEXT NOT NULL,
  sequence_no INTEGER NOT NULL,
  status TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(work_unit_id, sequence_no),
  FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id),
  FOREIGN KEY(work_unit_id) REFERENCES work_units(work_unit_id)
);
CREATE INDEX IF NOT EXISTS idx_checkpoints_latest
  ON work_unit_checkpoints(work_unit_id, sequence_no DESC);

CREATE TABLE IF NOT EXISTS observation_promotions (
  observation_id TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  promoted_at TEXT NOT NULL,
  PRIMARY KEY(observation_id, entity_type, entity_id),
  FOREIGN KEY(observation_id) REFERENCES observations(observation_id)
);
'''


TABLES: dict[str, tuple[str, str]] = {
    "evidences": ("evidences", "evidence_id"),
    "scenarios": ("scenarios", "scenario_id"),
    "fragments": ("behavior_fragments", "fragment_id"),
    "method_definitions": ("method_definitions", "method_definition_id"),
    "trace_stages": ("trace_stages", "stage_id"),
    "implementation_slices": ("implementation_slices", "slice_id"),
    "coverage_gates": ("coverage_gates", "gate_id"),
    "scenario_plans": ("scenario_plans", "plan_id"),
    "business_blocks": ("business_blocks", "block_id"),
    "scenario_overviews": ("scenario_overviews", "overview_id"),
    "analysis_runs": ("analysis_runs", "run_id"),
    "analysis_tasks": ("analysis_tasks", "task_id"),
    "execution_nodes": ("execution_nodes", "execution_node_id"),
    "field_inventory": ("field_inventory", "field_id"),
    "route_decisions": ("route_decisions", "decision_id"),
    "field_lineage_steps": ("field_lineage_steps", "lineage_step_id"),
    "persistence_effects": ("persistence_effects", "effect_id"),
    "external_interactions": ("external_interactions", "interaction_id"),
    "gaps": ("gaps", "gap_id"),
    "work_units": ("work_units", "work_unit_id"),
    "observations": ("observations", "observation_id"),
    "checkpoints": ("work_unit_checkpoints", "checkpoint_id"),
}


class FactStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA_SQL)
        self.conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version','0.10.0')")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def commit(self) -> None:
        self.conn.commit()

    def has(self, collection: str, entity_id: str) -> bool:
        table, id_field = TABLES[collection]
        row = self.conn.execute(f"SELECT 1 FROM {table} WHERE {id_field}=?", (entity_id,)).fetchone()
        return row is not None

    def has_evidence(self, evidence_id: str) -> bool:
        return self.has("evidences", evidence_id)

    def _archive_existing(self, entity_type: str, entity_id: str, row: sqlite3.Row, source_work_unit: str | None) -> None:
        revision_id = new_id("REV")
        self.conn.execute(
            "INSERT INTO entity_revisions(revision_id,entity_type,entity_id,payload_json,content_hash,source_work_unit,created_at) VALUES(?,?,?,?,?,?,?)",
            (revision_id, entity_type, entity_id, row["payload_json"], row["content_hash"], source_work_unit, now_iso()),
        )

    def upsert(self, collection: str, payload: dict[str, Any], source_work_unit: str | None = None) -> str:
        table, id_field = TABLES[collection]
        entity_id = str(payload[id_field])
        content_hash = canonical_hash(payload)
        existing = self.conn.execute(
            f"SELECT payload_json,content_hash,created_at FROM {table} WHERE {id_field}=?", (entity_id,)
        ).fetchone()
        ts = now_iso()
        if existing and existing["content_hash"] == content_hash:
            return entity_id
        if existing:
            self._archive_existing(collection, entity_id, existing, source_work_unit)

        common = {
            "payload_json": json.dumps(payload, ensure_ascii=False),
            "content_hash": content_hash,
            "created_at": existing["created_at"] if existing else ts,
            "updated_at": ts,
        }
        if collection == "evidences":
            columns = {
                id_field: entity_id,
                "scenario_id": payload.get("scenario_id"),
                "evidence_kind": payload.get("evidence_kind") or payload.get("kind"),
                **common,
                "source_work_unit": source_work_unit,
            }
        elif collection == "scenarios":
            columns = {
                id_field: entity_id,
                "name": payload.get("name") or entity_id,
                "business_operation": payload.get("business_operation"),
                "status": payload.get("status", "ACTIVE"),
                **common,
                "source_work_unit": source_work_unit,
            }
        elif collection == "fragments":
            columns = {
                id_field: entity_id,
                "logical_key": payload.get("logical_key") or entity_id,
                "repository": payload.get("repository"),
                "code_hash": payload.get("code_hash"),
                "binding_hash": payload.get("binding_hash"),
                "status": payload.get("status", "CANDIDATE"),
                **common,
                "source_work_unit": source_work_unit,
            }
        elif collection == "method_definitions":
            columns = {
                id_field: entity_id,
                "source_id": payload["source_id"],
                "symbol": payload["symbol"],
                "code_hash": payload.get("code_hash"),
                "status": payload.get("status", "CANDIDATE"),
                **common,
                "source_work_unit": source_work_unit,
            }
        elif collection == "trace_stages":
            columns = {
                id_field: entity_id,
                "scenario_id": payload["scenario_id"],
                "sequence_no": float(payload["sequence_no"]),
                "fragment_id": payload.get("fragment_id"),
                "stage_type": payload.get("stage_type", "PROCESS"),
                "status": payload.get("status", "CANDIDATE"),
                **common,
                "source_work_unit": source_work_unit,
            }
        elif collection == "implementation_slices":
            columns = {
                id_field: entity_id,
                "scenario_id": payload["scenario_id"],
                "stage_id": payload["stage_id"],
                "source_id": payload["source_id"],
                "focus_mode": payload.get("focus_mode", "GENERAL"),
                "sequence_no": float(payload["sequence_no"]),
                "closure_status": payload.get("closure_status", "OPEN"),
                "status": payload.get("status", "CANDIDATE"),
                **common,
                "source_work_unit": source_work_unit,
            }
        elif collection == "coverage_gates":
            columns = {
                id_field: entity_id,
                "scenario_id": payload["scenario_id"],
                "stage_id": payload.get("stage_id"),
                "gate_type": payload["gate_type"],
                "priority": payload["priority"],
                "status": payload.get("status", "OPEN"),
                **common,
                "source_work_unit": source_work_unit,
            }
        elif collection == "scenario_plans":
            columns = {
                id_field: entity_id,
                "scenario_id": payload["scenario_id"],
                "run_id": payload["run_id"],
                "status": payload.get("status", "DRAFT"),
                **common,
                "source_work_unit": source_work_unit,
            }
        elif collection == "business_blocks":
            columns = {
                id_field: entity_id,
                "scenario_id": payload["scenario_id"],
                "run_id": payload["run_id"],
                "sequence_no": float(payload["sequence_no"]),
                "depth": payload.get("depth", "STANDARD"),
                "status": payload.get("status", "COMPLETE"),
                **common,
                "source_work_unit": source_work_unit,
            }
        elif collection == "scenario_overviews":
            columns = {
                id_field: entity_id,
                "scenario_id": payload["scenario_id"],
                "run_id": payload["run_id"],
                "status": payload.get("status", "COMPLETE"),
                **common,
                "source_work_unit": source_work_unit,
            }
        elif collection == "execution_nodes":
            columns = {
                id_field: entity_id,
                "scenario_id": payload["scenario_id"],
                "source_id": payload["source_id"],
                "parent_node_id": payload.get("parent_node_id"),
                "stage_id": payload.get("stage_id"),
                "method_definition_id": payload.get("method_definition_id"),
                "node_type": payload["node_type"],
                "sequence_no": float(payload["sequence_no"]),
                "status": payload.get("status", "CANDIDATE"),
                **common,
                "source_work_unit": source_work_unit,
            }
        elif collection == "field_inventory":
            columns = {
                id_field: entity_id,
                "scenario_id": payload["scenario_id"],
                "canonical_field": payload["canonical_field"],
                "priority": payload["priority"],
                "tracking_status": payload["tracking_status"],
                "status": payload.get("status", "CANDIDATE"),
                **common,
                "source_work_unit": source_work_unit,
            }
        elif collection == "field_lineage_steps":
            columns = {
                id_field: entity_id,
                "scenario_id": payload["scenario_id"],
                "stage_id": payload.get("stage_id"),
                "canonical_field": payload["canonical_field"],
                "sequence_no": float(payload["sequence_no"]),
                "status": payload.get("status", "CANDIDATE"),
                **common,
                "source_work_unit": source_work_unit,
            }
        elif collection == "work_units":
            columns = {
                id_field: entity_id,
                "scenario_id": payload.get("scenario_id"),
                "work_type": payload.get("work_type"),
                "status": payload.get("status", "PENDING"),
                "payload_json": common["payload_json"],
                "content_hash": common["content_hash"],
                "created_at": common["created_at"],
                "updated_at": common["updated_at"],
            }
        else:
            columns = {
                id_field: entity_id,
                "scenario_id": payload["scenario_id"],
                "stage_id": payload.get("stage_id"),
                "status": payload.get("status", "OPEN" if collection == "gaps" else "CANDIDATE"),
                **common,
                "source_work_unit": source_work_unit,
            }
            if collection == "gaps":
                columns.update({
                    "category": payload.get("category"),
                    "severity": payload.get("severity", "MEDIUM"),
                    "auto_generated": 1 if payload.get("auto_generated") else 0,
                })

        names = list(columns)
        placeholders = ",".join("?" for _ in names)
        updates = ",".join(f"{name}=excluded.{name}" for name in names if name not in {id_field, "created_at"})
        self.conn.execute(
            f"INSERT INTO {table}({','.join(names)}) VALUES({placeholders}) ON CONFLICT({id_field}) DO UPDATE SET {updates}",
            [columns[name] for name in names],
        )
        return entity_id

    def get(self, collection: str, entity_id: str) -> dict[str, Any] | None:
        table, id_field = TABLES[collection]
        row = self.conn.execute(f"SELECT payload_json FROM {table} WHERE {id_field}=?", (entity_id,)).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list_collection(self, collection: str, scenario_id: str | None = None) -> list[dict[str, Any]]:
        table, _ = TABLES[collection]
        sql = f"SELECT payload_json FROM {table}"
        params: list[Any] = []
        if scenario_id and collection not in {"fragments", "method_definitions"}:
            sql += " WHERE scenario_id=?"
            params.append(scenario_id)
        if collection == "trace_stages":
            sql += " ORDER BY sequence_no,stage_id"
        elif collection == "implementation_slices":
            sql += " ORDER BY sequence_no,slice_id"
        elif collection == "coverage_gates":
            sql += " ORDER BY priority,gate_type,gate_id"
        elif collection == "business_blocks":
            sql += " ORDER BY sequence_no,block_id"
        elif collection == "execution_nodes":
            sql += " ORDER BY sequence_no,execution_node_id"
        elif collection == "field_inventory":
            sql += " ORDER BY priority,canonical_field"
        elif collection == "field_lineage_steps":
            sql += " ORDER BY canonical_field,sequence_no,lineage_step_id"
        else:
            sql += " ORDER BY updated_at"
        return [json.loads(row["payload_json"]) for row in self.conn.execute(sql, params).fetchall()]

    def list_scenarios(self) -> list[dict[str, Any]]:
        return self.list_collection("scenarios")

    def scenario_dossier(self, scenario_id: str) -> dict[str, Any]:
        scenario = self.get("scenarios", scenario_id)
        if scenario is None:
            raise KeyError(f"Scenario not found: {scenario_id}")
        result: dict[str, Any] = {"scenario": scenario}
        for collection in (
            "scenario_plans", "business_blocks", "scenario_overviews",
            "analysis_runs",
            "trace_stages", "implementation_slices", "coverage_gates",
            "execution_nodes", "field_inventory", "route_decisions", "field_lineage_steps",
            "persistence_effects", "external_interactions", "gaps",
        ):
            result[collection] = self.list_collection(collection, scenario_id)
        fragment_ids = {x.get("fragment_id") for x in result["trace_stages"] if x.get("fragment_id")}
        result["fragments"] = [self.get("fragments", x) for x in fragment_ids if self.get("fragments", x)]
        method_definition_ids = {
            x.get("method_definition_id") for x in result["execution_nodes"] if x.get("method_definition_id")
        }
        result["method_definitions"] = [
            self.get("method_definitions", x) for x in method_definition_ids
            if self.get("method_definitions", x)
        ]
        evidence_ids: set[str] = set()
        for collection in (
            "scenario_plans", "business_blocks", "scenario_overviews",
            "trace_stages", "implementation_slices", "coverage_gates",
            "execution_nodes", "field_inventory", "route_decisions",
            "field_lineage_steps", "persistence_effects", "external_interactions",
        ):
            for item in result[collection]:
                evidence_ids.update(item.get("evidence_ids") or [])
        for fragment in result["fragments"]:
            evidence_ids.update(fragment.get("evidence_ids") or [])
        for method in result["method_definitions"]:
            evidence_ids.update(method.get("evidence_ids") or [])
        result["evidences"] = [self.get("evidences", x) for x in sorted(evidence_ids) if self.get("evidences", x)]
        return result

    def find_fragments(
        self,
        logical_key: str,
        repository: str | None = None,
        code_hash: str | None = None,
        binding_hash: str | None = None,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT payload_json,repository,code_hash,binding_hash,status FROM behavior_fragments WHERE logical_key=? ORDER BY updated_at DESC",
            (logical_key,),
        ).fetchall()
        results = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            source_match = not source_id or source_id == payload.get("source_id")
            repo_match = not repository or repository == row["repository"]
            code_match = not code_hash or code_hash == row["code_hash"]
            binding_match = not binding_hash or binding_hash == row["binding_hash"]
            complete = bool(payload.get("contract_complete")) and row["status"] in {"STATIC_VERIFIED", "SCENARIO_CONFIRMED", "CONFIRMED"}
            if source_match and repo_match and code_match and binding_match and complete:
                reuse = "EXACT_REUSE"
            elif source_match and repo_match and code_match and binding_match:
                reuse = "PARTIAL_REUSE"
            elif source_match and repo_match and code_match:
                reuse = "CONDITIONAL_REUSE"
            else:
                reuse = "STALE"
            results.append({"reuse": reuse, "fragment": payload})
        return results

    def find_method_definitions(
        self,
        source_id: str,
        symbol: str,
        code_hash: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT payload_json,code_hash,status FROM method_definitions WHERE source_id=? AND symbol=? ORDER BY updated_at DESC",
            (source_id, symbol),
        ).fetchall()
        results = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            verified = row["status"] in {"STATIC_VERIFIED", "SCENARIO_CONFIRMED", "CONFIRMED"}
            contracts = isinstance(payload.get("input_contract"), dict) and isinstance(payload.get("output_contract"), dict)
            if code_hash and code_hash == row["code_hash"] and verified and contracts:
                reuse = "EXACT_REUSE"
            elif not code_hash and verified and contracts:
                reuse = "CONDITIONAL_REUSE"
            elif code_hash and code_hash != row["code_hash"]:
                reuse = "STALE"
            else:
                reuse = "PARTIAL_REUSE"
            results.append({"reuse": reuse, "method_definition": payload})
        return results

    def observation_exists(self, observation_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM observations WHERE observation_id=?", (observation_id,)
        ).fetchone()
        return row is not None

    def append_observations(
        self,
        observations: list[dict[str, Any]],
        work_unit_id: str,
        scenario_id: str,
    ) -> dict[str, Any]:
        inserted: list[str] = []
        deduplicated: list[str] = []
        for source_payload in observations:
            payload = dict(source_payload)
            payload["work_unit_id"] = work_unit_id
            payload["scenario_id"] = scenario_id
            payload.setdefault("status", "PENDING")
            fingerprint_payload = {
                key: value for key, value in payload.items()
                if key not in {"observation_id", "fingerprint", "created_at", "updated_at", "status"}
            }
            fingerprint = str(payload.get("fingerprint") or canonical_hash(fingerprint_payload))
            existing = self.conn.execute(
                "SELECT observation_id FROM observations WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
            if existing:
                observation_id = str(existing["observation_id"])
                payload["observation_id"] = observation_id
                deduplicated.append(observation_id)
                continue
            observation_id = str(payload.get("observation_id") or new_id("OBS"))
            id_collision = self.conn.execute(
                "SELECT fingerprint FROM observations WHERE observation_id=?", (observation_id,)
            ).fetchone()
            if id_collision:
                raise ValueError(f"Observation ID already exists with different content: {observation_id}")
            payload["observation_id"] = observation_id
            payload["fingerprint"] = fingerprint
            content_hash = canonical_hash(payload)
            ts = now_iso()
            self.conn.execute(
                "INSERT INTO observations(observation_id,fingerprint,scenario_id,work_unit_id,source_id,observation_kind,subject_key,confidence,payload_json,content_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    observation_id,
                    fingerprint,
                    scenario_id,
                    work_unit_id,
                    payload.get("source_id"),
                    payload["observation_kind"],
                    payload["subject_key"],
                    payload.get("confidence", "CANDIDATE"),
                    json.dumps(payload, ensure_ascii=False),
                    content_hash,
                    ts,
                    ts,
                ),
            )
            inserted.append(observation_id)
        return {"inserted": inserted, "deduplicated": deduplicated, "all_ids": inserted + deduplicated}

    def append_checkpoint(
        self,
        checkpoint: dict[str, Any],
        work_unit_id: str,
        scenario_id: str,
        observation_ids: list[str],
    ) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(sequence_no),0) AS n FROM work_unit_checkpoints WHERE work_unit_id=?",
            (work_unit_id,),
        ).fetchone()
        sequence_no = int(row["n"]) + 1
        payload = dict(checkpoint)
        payload["checkpoint_id"] = str(payload.get("checkpoint_id") or new_id("CP"))
        payload["work_unit_id"] = work_unit_id
        payload["scenario_id"] = scenario_id
        payload["sequence_no"] = sequence_no
        payload["observation_ids"] = list(dict.fromkeys((payload.get("observation_ids") or []) + observation_ids))
        payload.setdefault("status", "ACTIVE")
        content_hash = canonical_hash(payload)
        ts = now_iso()
        self.conn.execute(
            "INSERT INTO work_unit_checkpoints(checkpoint_id,scenario_id,work_unit_id,sequence_no,status,payload_json,content_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                payload["checkpoint_id"], scenario_id, work_unit_id, sequence_no,
                payload["status"], json.dumps(payload, ensure_ascii=False), content_hash, ts, ts,
            ),
        )
        return payload

    def latest_checkpoint(self, work_unit_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT payload_json FROM work_unit_checkpoints WHERE work_unit_id=? ORDER BY sequence_no DESC LIMIT 1",
            (work_unit_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list_observations(
        self,
        observation_id: str | None = None,
        work_unit_id: str | None = None,
        scenario_id: str | None = None,
        source_id: str | None = None,
        observation_kind: str | None = None,
        subject: str | None = None,
        promotion_status: str = "ANY",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = "SELECT o.payload_json FROM observations o WHERE 1=1"
        params: list[Any] = []
        for column, value in (
            ("o.observation_id", observation_id),
            ("o.work_unit_id", work_unit_id),
            ("o.scenario_id", scenario_id),
            ("o.source_id", source_id),
            ("o.observation_kind", observation_kind),
        ):
            if value:
                sql += f" AND {column}=?"
                params.append(value)
        if subject:
            sql += " AND o.subject_key LIKE ?"
            params.append(f"%{subject}%")
        if promotion_status == "PENDING":
            sql += " AND NOT EXISTS(SELECT 1 FROM observation_promotions p WHERE p.observation_id=o.observation_id AND p.entity_type NOT IN ('evidences','work_units'))"
        elif promotion_status == "PROMOTED":
            sql += " AND EXISTS(SELECT 1 FROM observation_promotions p WHERE p.observation_id=o.observation_id AND p.entity_type NOT IN ('evidences','work_units'))"
        elif promotion_status == "EVIDENCED":
            sql += " AND EXISTS(SELECT 1 FROM observation_promotions p WHERE p.observation_id=o.observation_id AND p.entity_type='evidences')"
        sql += " ORDER BY o.created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        rows = self.conn.execute(sql, params).fetchall()
        result = []
        for row in reversed(rows):
            payload = json.loads(row["payload_json"])
            promotions = self.conn.execute(
                "SELECT entity_type,entity_id,promoted_at FROM observation_promotions WHERE observation_id=? ORDER BY promoted_at",
                (payload["observation_id"],),
            ).fetchall()
            if promotions:
                payload["promoted_to"] = [dict(item) for item in promotions]
            result.append(payload)
        return result

    def promote_observations(self, observation_ids: list[str], entity_type: str, entity_id: str) -> None:
        for observation_id in dict.fromkeys(observation_ids):
            if not self.observation_exists(observation_id):
                raise ValueError(f"Missing Observation reference: {observation_id}")
            self.conn.execute(
                "INSERT OR IGNORE INTO observation_promotions(observation_id,entity_type,entity_id,promoted_at) VALUES(?,?,?,?)",
                (observation_id, entity_type, entity_id, now_iso()),
            )

    def work_unit_memory(
        self,
        work_unit_id: str,
        max_observations: int = 60,
        max_visited_refs: int = 100,
    ) -> dict[str, Any]:
        checkpoint_rows = self.conn.execute(
            "SELECT payload_json FROM work_unit_checkpoints WHERE work_unit_id=? ORDER BY sequence_no",
            (work_unit_id,),
        ).fetchall()
        checkpoints = [json.loads(row["payload_json"]) for row in checkpoint_rows]
        latest = checkpoints[-1] if checkpoints else None
        visited: dict[str, dict[str, Any]] = {}
        for checkpoint in checkpoints:
            for ref in checkpoint.get("visited_refs") or []:
                if not isinstance(ref, dict):
                    continue
                key = "|".join(str(ref.get(field) or "") for field in ("source_id", "kind", "symbol", "config_key"))
                visited[key] = ref

        count_row = self.conn.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN EXISTS(SELECT 1 FROM observation_promotions p WHERE p.observation_id=o.observation_id AND p.entity_type='evidences') THEN 1 ELSE 0 END) AS evidenced, SUM(CASE WHEN EXISTS(SELECT 1 FROM observation_promotions p WHERE p.observation_id=o.observation_id AND p.entity_type NOT IN ('evidences','work_units')) THEN 1 ELSE 0 END) AS assembled FROM observations o WHERE work_unit_id=?",
            (work_unit_id,),
        ).fetchone()
        total = int(count_row["total"] or 0)
        evidenced = int(count_row["evidenced"] or 0)
        assembled = int(count_row["assembled"] or 0)
        pending = total - assembled
        loaded = self.list_observations(
            work_unit_id=work_unit_id,
            promotion_status="PENDING",
            limit=max_observations,
        )
        index_rows = self.conn.execute(
            "SELECT COALESCE(source_id,'NON_CODE') AS source_id, observation_kind, COUNT(*) AS total, SUM(CASE WHEN EXISTS(SELECT 1 FROM observation_promotions p WHERE p.observation_id=o.observation_id AND p.entity_type NOT IN ('evidences','work_units')) THEN 0 ELSE 1 END) AS pending FROM observations o WHERE work_unit_id=? GROUP BY COALESCE(source_id,'NON_CODE'), observation_kind ORDER BY source_id, observation_kind",
            (work_unit_id,),
        ).fetchall()
        visited_values = list(visited.values())
        loaded_visited = visited_values[-max_visited_refs:]
        return {
            "latest_checkpoint": latest,
            "checkpoint_count": len(checkpoints),
            "visited_ref_count": len(visited_values),
            "visited_refs": loaded_visited,
            "omitted_visited_refs": max(0, len(visited_values) - len(loaded_visited)),
            "observation_counts": {
                "total": total,
                "pending_assembly": pending,
                "evidenced": evidenced,
                "assembled": assembled,
            },
            "observation_index": [dict(row) for row in index_rows],
            "pending_observations": loaded,
            "omitted_pending_observations": max(0, pending - len(loaded)),
        }

    def scenario_pending_observation_count(self, scenario_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM observations o WHERE o.scenario_id=? AND NOT EXISTS(SELECT 1 FROM observation_promotions p WHERE p.observation_id=o.observation_id AND p.entity_type NOT IN ('evidences','work_units'))",
            (scenario_id,),
        ).fetchone()
        return int(row["n"] or 0)

    def sync_audit_gaps(self, scenario_id: str, gaps: list[dict[str, Any]]) -> None:
        current_ids = {gap["gap_id"] for gap in gaps}
        rows = self.conn.execute(
            "SELECT gap_id,payload_json FROM gaps WHERE scenario_id=? AND auto_generated=1 AND status='OPEN'",
            (scenario_id,),
        ).fetchall()
        for row in rows:
            if row["gap_id"] not in current_ids:
                payload = json.loads(row["payload_json"])
                payload["status"] = "RESOLVED"
                self.upsert("gaps", payload, "AUDIT")
        for gap in gaps:
            self.upsert("gaps", gap, "AUDIT")
        self.commit()
