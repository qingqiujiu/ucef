import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .core import canonical_hash

SCHEMA_SQL = '''
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS facts (
  fact_id TEXT PRIMARY KEY,
  fact_type TEXT NOT NULL,
  scenario_id TEXT,
  fact_status TEXT,
  certainty TEXT,
  payload_json TEXT NOT NULL,
  canonical_hash TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_canonical
  ON facts(fact_type, scenario_id, canonical_hash);
CREATE INDEX IF NOT EXISTS idx_facts_scenario
  ON facts(scenario_id, fact_type, fact_status);

CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY,
  scenario_id TEXT,
  payload_json TEXT NOT NULL,
  content_hash TEXT,
  source_work_unit TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_units (
  work_unit_id TEXT PRIMARY KEY,
  scenario_id TEXT,
  status TEXT,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS unknowns (
  unknown_id TEXT PRIMARY KEY,
  scenario_id TEXT,
  status TEXT,
  payload_json TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conflicts (
  conflict_id TEXT PRIMARY KEY,
  scenario_id TEXT,
  status TEXT,
  payload_json TEXT NOT NULL,
  source_work_unit TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_entities (
  entity_key TEXT PRIMARY KEY,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  parent_key TEXT,
  payload_json TEXT NOT NULL,
  source_type TEXT,
  source_ref TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_catalog_type ON catalog_entities(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_catalog_parent ON catalog_entities(parent_key);

'''


def now_iso():
    return datetime.now(timezone.utc).isoformat()


FACT_ID_FIELDS = {
    "execution_nodes": "node_id",
    "execution_edges": "edge_id",
    "decisions": "decision_id",
    "data_mutations": "mutation_id",
    "interactions": "interaction_id",
}


class FactStore:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def commit(self):
        self.conn.commit()

    def has_evidence(self, evidence_id):
        return self.conn.execute("SELECT 1 FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone() is not None

    def has_fact_id(self, fact_id):
        return self.conn.execute("SELECT 1 FROM facts WHERE fact_id=?", (fact_id,)).fetchone() is not None

    def upsert_evidence(self, record, scenario_id, work_unit_id):
        self.conn.execute(
            '''INSERT INTO evidence(evidence_id,scenario_id,payload_json,content_hash,source_work_unit,created_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(evidence_id) DO UPDATE SET payload_json=excluded.payload_json,content_hash=excluded.content_hash,source_work_unit=excluded.source_work_unit''',
            (record["evidence_id"], scenario_id, json.dumps(record, ensure_ascii=False), record.get("content_hash"), work_unit_id, now_iso())
        )

    def upsert_fact(self, fact_type, record, scenario_id, work_unit_id):
        fact_id = str(record[FACT_ID_FIELDS[fact_type]])
        h = canonical_hash(record, {FACT_ID_FIELDS[fact_type], "evidence_ids", "fact_status", "certainty"})
        ts = now_iso()
        try:
            self.conn.execute(
                '''INSERT INTO facts(fact_id,fact_type,scenario_id,fact_status,certainty,payload_json,canonical_hash,source_work_unit,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (fact_id, fact_type, scenario_id, record.get("fact_status"), record.get("certainty"), json.dumps(record, ensure_ascii=False), h, work_unit_id, ts, ts)
            )
            return fact_id
        except sqlite3.IntegrityError:
            row = self.conn.execute(
                "SELECT fact_id FROM facts WHERE fact_type=? AND scenario_id=? AND canonical_hash=?",
                (fact_type, scenario_id, h)
            ).fetchone()
            if row:
                return row["fact_id"]
            raise

    def save_work_unit(self, record):
        ts = now_iso()
        self.conn.execute(
            '''INSERT INTO work_units(work_unit_id,scenario_id,status,payload_json,created_at,updated_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(work_unit_id) DO UPDATE SET status=excluded.status,payload_json=excluded.payload_json,updated_at=excluded.updated_at''',
            (record["work_unit_id"], record.get("scenario_id"), record.get("status", "PENDING"), json.dumps(record, ensure_ascii=False), ts, ts)
        )

    def upsert_unknown(self, record, scenario_id, work_unit_id):
        ts = now_iso()
        self.conn.execute(
            '''INSERT INTO unknowns(unknown_id,scenario_id,status,payload_json,source_work_unit,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(unknown_id) DO UPDATE SET status=excluded.status,payload_json=excluded.payload_json,updated_at=excluded.updated_at''',
            (record["unknown_id"], scenario_id, record.get("status", "OPEN"), json.dumps(record, ensure_ascii=False), work_unit_id, ts, ts)
        )

    def upsert_conflict(self, record, scenario_id, work_unit_id):
        ts = now_iso()
        self.conn.execute(
            '''INSERT INTO conflicts(conflict_id,scenario_id,status,payload_json,source_work_unit,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(conflict_id) DO UPDATE SET status=excluded.status,payload_json=excluded.payload_json,updated_at=excluded.updated_at''',
            (record["conflict_id"], scenario_id, record.get("status", "OPEN"), json.dumps(record, ensure_ascii=False), work_unit_id, ts, ts)
        )

    def related_facts(self, scenario_id, needles, limit=120):
        needles = [n for n in needles if n]
        if not needles:
            rows = self.conn.execute(
                "SELECT fact_type,payload_json FROM facts WHERE scenario_id=? AND fact_status='CONFIRMED' ORDER BY updated_at DESC LIMIT ?",
                (scenario_id, limit)
            ).fetchall()
        else:
            clauses = " OR ".join(["payload_json LIKE ?" for _ in needles])
            params = [scenario_id] + [f"%{n}%" for n in needles] + [limit]
            rows = self.conn.execute(
                f"SELECT fact_type,payload_json FROM facts WHERE scenario_id=? AND fact_status='CONFIRMED' AND ({clauses}) ORDER BY updated_at DESC LIMIT ?",
                params
            ).fetchall()
        return [{"fact_type": r["fact_type"], **json.loads(r["payload_json"])} for r in rows]

    def open_unknowns(self, scenario_id, limit=30):
        rows = self.conn.execute(
            "SELECT payload_json FROM unknowns WHERE scenario_id=? AND status='OPEN' ORDER BY updated_at DESC LIMIT ?",
            (scenario_id, limit)
        ).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    def open_conflicts(self, scenario_id, limit=20):
        rows = self.conn.execute(
            "SELECT payload_json FROM conflicts WHERE scenario_id=? AND status='OPEN' ORDER BY updated_at DESC LIMIT ?",
            (scenario_id, limit)
        ).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]


    def list_scenarios(self):
        rows = self.conn.execute(
            "SELECT DISTINCT scenario_id FROM facts WHERE scenario_id IS NOT NULL AND scenario_id <> '' ORDER BY scenario_id"
        ).fetchall()
        return [str(r["scenario_id"]) for r in rows]

    def query(self, scenario_id=None, fact_type=None, text=None, limit=100):
        where, params = [], []
        if scenario_id:
            where.append("scenario_id=?"); params.append(scenario_id)
        if fact_type:
            where.append("fact_type=?"); params.append(fact_type)
        if text:
            where.append("payload_json LIKE ?"); params.append(f"%{text}%")
        sql = "SELECT fact_type,payload_json FROM facts"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC LIMIT ?"; params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [{"fact_type": r["fact_type"], **json.loads(r["payload_json"])} for r in rows]

    # --- HTML Explorer export API ---
    def export_fact_rows(self, scenario_id=None):
        """Return facts with store metadata for deterministic site compilation."""
        sql = "SELECT fact_id,fact_type,scenario_id,fact_status,certainty,payload_json,source_work_unit,created_at,updated_at FROM facts"
        params = []
        if scenario_id:
            sql += " WHERE scenario_id=?"; params.append(scenario_id)
        sql += " ORDER BY updated_at,fact_id"
        rows = self.conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            payload = json.loads(r["payload_json"])
            payload.update({
                "fact_id": r["fact_id"], "fact_type": r["fact_type"],
                "scenario_id": r["scenario_id"],
                "fact_status": payload.get("fact_status") or r["fact_status"],
                "certainty": payload.get("certainty") or r["certainty"],
                "_source_work_unit": r["source_work_unit"],
                "_created_at": r["created_at"], "_updated_at": r["updated_at"],
            })
            out.append(payload)
        return out

    def export_evidence_rows(self, scenario_id=None):
        sql = "SELECT evidence_id,scenario_id,payload_json,source_work_unit,created_at FROM evidence"
        params = []
        if scenario_id:
            sql += " WHERE scenario_id=?"; params.append(scenario_id)
        sql += " ORDER BY created_at,evidence_id"
        rows = self.conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            payload = json.loads(r["payload_json"])
            payload.update({"scenario_id": r["scenario_id"], "_source_work_unit": r["source_work_unit"], "_created_at": r["created_at"]})
            out.append(payload)
        return out

    def export_unknown_rows(self, scenario_id=None):
        sql = "SELECT unknown_id,scenario_id,status,payload_json,source_work_unit,created_at,updated_at FROM unknowns"
        params = []
        if scenario_id:
            sql += " WHERE scenario_id=?"; params.append(scenario_id)
        sql += " ORDER BY updated_at,unknown_id"
        rows = self.conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            payload = json.loads(r["payload_json"])
            payload.update({"scenario_id": r["scenario_id"], "status": payload.get("status") or r["status"], "_source_work_unit": r["source_work_unit"], "_created_at": r["created_at"], "_updated_at": r["updated_at"]})
            out.append(payload)
        return out

    def export_conflict_rows(self, scenario_id=None):
        sql = "SELECT conflict_id,scenario_id,status,payload_json,source_work_unit,created_at,updated_at FROM conflicts"
        params = []
        if scenario_id:
            sql += " WHERE scenario_id=?"; params.append(scenario_id)
        sql += " ORDER BY updated_at,conflict_id"
        rows = self.conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            payload = json.loads(r["payload_json"])
            payload.update({"scenario_id": r["scenario_id"], "status": payload.get("status") or r["status"], "_source_work_unit": r["source_work_unit"], "_created_at": r["created_at"], "_updated_at": r["updated_at"]})
            out.append(payload)
        return out

    def export_work_unit_rows(self, scenario_id=None):
        sql = "SELECT work_unit_id,scenario_id,status,payload_json,created_at,updated_at FROM work_units"
        params = []
        if scenario_id:
            sql += " WHERE scenario_id=?"; params.append(scenario_id)
        sql += " ORDER BY updated_at,work_unit_id"
        rows = self.conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            payload = json.loads(r["payload_json"])
            payload.update({"scenario_id": r["scenario_id"], "status": payload.get("status") or r["status"], "_created_at": r["created_at"], "_updated_at": r["updated_at"]})
            out.append(payload)
        return out

    # --- Authoritative metadata catalog (systems/modules/database structure) ---
    def upsert_catalog_entity(self, entity_type, entity_id, payload, parent_key=None, source_type="MANUAL_IMPORT", source_ref=None):
        entity_key = f"{entity_type}:{entity_id}"
        ts = now_iso()
        data = dict(payload)
        data.setdefault("entity_type", entity_type)
        data.setdefault("entity_id", entity_id)
        payload_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
        existing = self.conn.execute(
            "SELECT parent_key,payload_json,source_type,source_ref FROM catalog_entities WHERE entity_key=?", (entity_key,)
        ).fetchone()
        if existing and existing["parent_key"] == parent_key and existing["source_type"] == source_type and existing["source_ref"] == source_ref:
            try:
                same_payload = json.dumps(json.loads(existing["payload_json"]), ensure_ascii=False, sort_keys=True) == payload_json
            except Exception:
                same_payload = existing["payload_json"] == payload_json
            if same_payload:
                return entity_key
        self.conn.execute(
            """INSERT INTO catalog_entities(entity_key,entity_type,entity_id,parent_key,payload_json,source_type,source_ref,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(entity_key) DO UPDATE SET
               parent_key=excluded.parent_key,payload_json=excluded.payload_json,
               source_type=excluded.source_type,source_ref=excluded.source_ref,updated_at=excluded.updated_at""",
            (entity_key, entity_type, entity_id, parent_key, payload_json, source_type, source_ref, ts, ts)
        )
        return entity_key

    def export_catalog_entities(self, entity_type=None):
        sql = "SELECT entity_key,entity_type,entity_id,parent_key,payload_json,source_type,source_ref,created_at,updated_at FROM catalog_entities"
        params = []
        if entity_type:
            sql += " WHERE entity_type=?"; params.append(entity_type)
        sql += " ORDER BY entity_type, entity_id"
        rows = self.conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            payload = json.loads(r["payload_json"])
            payload.update({
                "entity_key": r["entity_key"], "entity_type": r["entity_type"], "entity_id": r["entity_id"],
                "parent_key": r["parent_key"], "source_type": r["source_type"], "source_ref": r["source_ref"],
                "_created_at": r["created_at"], "_updated_at": r["updated_at"],
            })
            out.append(payload)
        return out

    def delete_catalog_entity(self, entity_key):
        self.conn.execute("DELETE FROM catalog_entities WHERE entity_key=?", (entity_key,))

