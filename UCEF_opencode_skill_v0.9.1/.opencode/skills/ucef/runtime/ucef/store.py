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
'''


TABLES: dict[str, tuple[str, str]] = {
    "evidences": ("evidences", "evidence_id"),
    "scenarios": ("scenarios", "scenario_id"),
    "fragments": ("behavior_fragments", "fragment_id"),
    "trace_stages": ("trace_stages", "stage_id"),
    "route_decisions": ("route_decisions", "decision_id"),
    "field_lineage_steps": ("field_lineage_steps", "lineage_step_id"),
    "persistence_effects": ("persistence_effects", "effect_id"),
    "external_interactions": ("external_interactions", "interaction_id"),
    "gaps": ("gaps", "gap_id"),
    "work_units": ("work_units", "work_unit_id"),
}


class FactStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA_SQL)
        self.conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version','0.9.1')")
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
        if scenario_id and collection not in {"fragments"}:
            sql += " WHERE scenario_id=?"
            params.append(scenario_id)
        if collection == "trace_stages":
            sql += " ORDER BY sequence_no,stage_id"
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
            "trace_stages", "route_decisions", "field_lineage_steps",
            "persistence_effects", "external_interactions", "gaps",
        ):
            result[collection] = self.list_collection(collection, scenario_id)
        fragment_ids = {x.get("fragment_id") for x in result["trace_stages"] if x.get("fragment_id")}
        result["fragments"] = [self.get("fragments", x) for x in fragment_ids if self.get("fragments", x)]
        evidence_ids: set[str] = set()
        for collection in ("trace_stages", "route_decisions", "field_lineage_steps", "persistence_effects", "external_interactions"):
            for item in result[collection]:
                evidence_ids.update(item.get("evidence_ids") or [])
        for fragment in result["fragments"]:
            evidence_ids.update(fragment.get("evidence_ids") or [])
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
