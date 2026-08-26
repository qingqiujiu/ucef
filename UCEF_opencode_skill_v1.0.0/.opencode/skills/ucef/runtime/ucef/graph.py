"""Adaptive, scenario-aware business knowledge for UCEF 1.0.

The language model owns exploration.  This module owns stable identity,
incremental persistence, bounded recall, and deterministic projections.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Iterable

from .core import approx_tokens, canonical_hash, new_id, now_iso, short_hash
from .store import FactStore


ENTITY_TYPES = frozenset({
    "SYSTEM", "MODULE", "BUSINESS_STEP", "DECISION", "BRANCH", "FIELD",
    "FIELD_EVENT", "INTERACTION", "PERSISTENCE", "TABLE", "COLUMN",
    "CONFIG", "STATE", "EVIDENCE", "GAP",
})

ENTITY_PREFIXES = {
    "SYSTEM": "SYS", "MODULE": "MOD", "BUSINESS_STEP": "STEP",
    "DECISION": "DEC", "BRANCH": "BR", "FIELD": "FLD",
    "FIELD_EVENT": "FLOW", "INTERACTION": "CALL", "PERSISTENCE": "DB",
    "TABLE": "TBL", "COLUMN": "COL", "CONFIG": "CFG", "STATE": "STATE",
    "EVIDENCE": "EV", "GAP": "GAP",
}

GROUP_TYPES = {
    "systems": "SYSTEM",
    "modules": "MODULE",
    "steps": "BUSINESS_STEP",
    "business_steps": "BUSINESS_STEP",
    "decisions": "DECISION",
    "fields": "FIELD",
    "field_journeys": "FIELD",
    "interactions": "INTERACTION",
    "persistence": "PERSISTENCE",
    "tables": "TABLE",
    "configurations": "CONFIG",
    "config_references": "CONFIG",
    "states": "STATE",
    "evidences": "EVIDENCE",
    "gaps": "GAP",
}

PASS_THROUGH_OPERATIONS = frozenset({
    "COPY", "ALIAS", "PASS_THROUGH", "PASSTHROUGH", "DTO_COPY", "IDENTITY",
})

SENSITIVE_KEY = re.compile(
    r"(?:password|passwd|secret|credential|private[_.-]?key|access[_.-]?key|api[_.-]?key|(?:^|[_.-])token(?:$|[_.-]))",
    re.IGNORECASE,
)

DEFAULT_CONTEXT_TARGET = 12_000
DEFAULT_SESSION_BUDGET = 300_000
MAX_DELTA_CHARS = 80_000
MAX_ENTITIES_PER_DELTA = 100
MAX_EDGES_PER_DELTA = 240


class GraphContractError(ValueError):
    """A small, actionable contract error rather than a giant schema dump."""


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _string(value: Any, default: str = "") -> str:
    return str(value).strip() if value is not None else default


def _safe_number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _compact_text(value: Any, maximum: int = 320) -> str:
    text = _string(value)
    return text if len(text) <= maximum else text[: maximum - 1] + "…"


def _slug(value: Any) -> str:
    raw = _string(value)
    slug = re.sub(r"[^\w.\-]+", "-", raw, flags=re.UNICODE).strip("-.")
    return slug or short_hash(raw, 12).lower()


def _redact_config_value(key: str, value: Any) -> Any:
    return "***REDACTED***" if SENSITIVE_KEY.search(key) else value


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class KnowledgeGraphService:
    """Persist small semantic deltas without prescribing model reasoning."""

    def __init__(
        self,
        store: FactStore,
        *,
        registered_sources: Iterable[str] | None = None,
        config: dict[str, Any] | None = None,
    ):
        self.store = store
        self.registered_sources = (
            {str(value) for value in registered_sources}
            if registered_sources is not None else None
        )
        self.config = config or {}

    @staticmethod
    def stable_entity_id(entity_type: str, logical_key: str) -> str:
        normalized = _string(entity_type).upper()
        if normalized not in ENTITY_TYPES:
            raise GraphContractError(f"Unknown entity type {normalized!r}")
        return f"{ENTITY_PREFIXES[normalized]}-{short_hash([normalized, logical_key], 14)}"

    def start_session(
        self,
        scenario_id: str,
        *,
        goal: str | None = None,
        priority_fields: list[str] | None = None,
        context_target_tokens: int | None = None,
        total_token_budget: int | None = None,
    ) -> dict[str, Any]:
        scenario = self.store.get("scenarios", scenario_id)
        if not scenario:
            raise GraphContractError(f"Persist the Scenario before analysis: {scenario_id}")
        active = self.store.conn.execute(
            "SELECT payload_json FROM exploration_sessions WHERE scenario_id=? "
            "AND status='ACTIVE' ORDER BY updated_at DESC LIMIT 1",
            (scenario_id,),
        ).fetchone()
        if active:
            return {"status": "RESUMED", "session": json.loads(active["payload_json"])}

        adaptive_config = self.config.get("adaptive_analysis") or {}
        started_at = now_iso()
        fields = list(dict.fromkeys(
            _string(item) for item in (
                priority_fields
                or scenario.get("critical_fields")
                or adaptive_config.get("priority_fields")
                or []
            ) if _string(item)
        ))
        session = {
            "session_id": new_id("SESSION"),
            "scenario_id": scenario_id,
            "status": "ACTIVE",
            "started_at": started_at,
            "updated_at": started_at,
            "goal": goal or scenario.get("business_goal") or scenario.get("name"),
            "priority_fields": fields,
            "context_target_tokens": max(1_000, int(
                context_target_tokens
                or adaptive_config.get("context_target_tokens")
                or DEFAULT_CONTEXT_TARGET
            )),
            "total_token_budget": max(1_000, int(
                total_token_budget
                or adaptive_config.get("total_token_budget")
                or DEFAULT_SESSION_BUDGET
            )),
            "estimated_tokens_used": 0,
            "milestone_count": 0,
            "digest": _compact_text(scenario.get("business_goal") or scenario.get("name"), 1600),
            "current_focus": "",
            "constraints": {
                "exploration": "adaptive; no preallocated blocks or probe count",
                "configuration": "record CONFIG_UNRESOLVED until PADB evidence exists",
                "logs": "out of scope unless explicitly requested",
                "field_policy": "P0 full provenance; P1 boundaries; P2 collapsed copies",
            },
        }
        self.store.conn.execute(
            "INSERT INTO exploration_sessions(session_id,scenario_id,status,started_at,updated_at,payload_json,content_hash) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                session["session_id"], scenario_id, session["status"], started_at,
                started_at, _json(session), canonical_hash(session),
            ),
        )
        self.store.commit()
        return {"status": "STARTED", "session": session}

    def get_session(self, session_id: str) -> dict[str, Any]:
        row = self.store.conn.execute(
            "SELECT payload_json FROM exploration_sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        if not row:
            raise GraphContractError(f"Unknown exploration session: {session_id}")
        return json.loads(row["payload_json"])

    def latest_session(self, scenario_id: str) -> dict[str, Any] | None:
        row = self.store.conn.execute(
            "SELECT payload_json FROM exploration_sessions WHERE scenario_id=? "
            "ORDER BY updated_at DESC LIMIT 1",
            (scenario_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def _save_session(self, session: dict[str, Any]) -> None:
        session["updated_at"] = now_iso()
        self.store.conn.execute(
            "UPDATE exploration_sessions SET status=?,updated_at=?,payload_json=?,content_hash=? "
            "WHERE session_id=?",
            (
                session["status"], session["updated_at"], _json(session),
                canonical_hash(session), session["session_id"],
            ),
        )

    def _normalize_entity(
        self,
        item: dict[str, Any],
        fallback_type: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise GraphContractError("Each business fact must be an object")
        entity_type = _string(
            item.get("entity_type") or item.get("type") or fallback_type or item.get("kind")
        ).upper()
        aliases = {
            "STEP": "BUSINESS_STEP", "CONFIGURATION": "CONFIG", "FIELD_JOURNEY": "FIELD",
            "DATABASE": "PERSISTENCE", "EXTERNAL_CALL": "INTERACTION",
        }
        entity_type = aliases.get(entity_type, entity_type)
        if entity_type not in ENTITY_TYPES:
            raise GraphContractError(
                f"entity_type must be one of {', '.join(sorted(ENTITY_TYPES))}; received {entity_type!r}"
            )
        logical_key = _string(
            item.get("logical_key") or item.get("key")
            or (item.get("canonical_field") if entity_type == "FIELD" else None)
            or (item.get("field") if entity_type == "FIELD" else None)
            or (item.get("config_key") if entity_type == "CONFIG" else None)
            or (item.get("table") if entity_type == "TABLE" else None)
            or item.get("symbol")
        )
        if not logical_key:
            name = item.get("display_name") or item.get("name") or item.get("title")
            if not name:
                raise GraphContractError(f"{entity_type} requires logical_key, key, or a name")
            logical_key = _slug(name)
        display_name = _string(
            item.get("display_name") or item.get("name") or item.get("title")
            or item.get("field") or item.get("config_key") or logical_key
        )
        structural = {
            "entity_id", "entity_type", "type", "kind", "logical_key", "key",
            "display_name", "name", "title", "summary", "description", "priority",
            "status", "attributes", "evidence_refs", "evidence_ids", "sequence_no",
            "role", "scenario_id", "relations", "branches", "events", "steps",
        }
        attributes = dict(item.get("attributes") or {})
        for key, value in item.items():
            if key not in structural:
                attributes.setdefault(key, value)
        priority = _string(item.get("priority") or attributes.get("priority") or "P1").upper()
        if priority not in {"P0", "P1", "P2"}:
            raise GraphContractError("priority must be P0, P1, or P2")
        status = _string(item.get("status") or attributes.get("resolution_status"))
        if not status:
            status = "CONFIG_UNRESOLVED" if entity_type == "CONFIG" else "SOURCE_CONFIRMED"
        if entity_type == "CONFIG":
            config_key = _string(attributes.get("config_key") or logical_key)
            attributes["config_key"] = config_key
            if "value" in attributes:
                attributes["value"] = _redact_config_value(config_key, attributes["value"])
                status = item.get("status") or "CONFIG_CONFIRMED"
            attributes.setdefault("resolution_status", status)
        if entity_type == "EVIDENCE":
            self._validate_evidence(attributes)
        return {
            "entity_id": self.stable_entity_id(entity_type, logical_key),
            "entity_type": entity_type,
            "logical_key": logical_key,
            "display_name": display_name,
            "summary": _compact_text(item.get("summary") or item.get("description"), 1600),
            "priority": priority,
            "status": status,
            "attributes": attributes,
            "evidence_refs": list(dict.fromkeys(
                _string(value) for value in _as_list(
                    item.get("evidence_refs") or item.get("evidence_ids")
                ) if _string(value)
            )),
            "sequence_no": _safe_number(item.get("sequence_no") or attributes.get("sequence_no")),
            "role": _string(item.get("role")),
        }

    def _validate_evidence(self, attributes: dict[str, Any]) -> None:
        source_id = _string(attributes.get("source_id"))
        if self.registered_sources is not None and not source_id:
            raise GraphContractError("Code evidence requires a registered source_id")
        if source_id and self.registered_sources is not None and source_id not in self.registered_sources:
            raise GraphContractError(f"Evidence source_id is not registered: {source_id}")
        location = _string(attributes.get("file") or attributes.get("path"))
        if self.registered_sources is not None and not location:
            raise GraphContractError("Code evidence requires a source-relative file or path")
        if location:
            if PurePosixPath(location).is_absolute() or PureWindowsPath(location).is_absolute():
                raise GraphContractError("Evidence file must be source-relative, not an absolute path")
            if ".." in PurePosixPath(location.replace("\\", "/")).parts:
                raise GraphContractError("Evidence file cannot escape its registered source root")
        excerpt = attributes.get("excerpt")
        if excerpt is not None and len(_string(excerpt)) > 1_200:
            raise GraphContractError("Evidence excerpts must stay below 1200 characters")

    def _upsert_entity(
        self,
        scenario_id: str,
        item: dict[str, Any],
        fallback_type: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        entity = self._normalize_entity(item, fallback_type)
        entity_id = entity["entity_id"]
        existing = self.store.conn.execute(
            "SELECT payload_json,content_hash,created_at FROM knowledge_entities WHERE entity_id=?",
            (entity_id,),
        ).fetchone()
        existing_membership = self.store.conn.execute(
            "SELECT payload_json FROM knowledge_memberships WHERE scenario_id=? AND entity_id=?",
            (scenario_id, entity_id),
        ).fetchone()
        prior_scope = (
            json.loads(existing_membership["payload_json"])
            if existing_membership else {}
        )
        scoped_attributes = dict(prior_scope.get("attributes") or {})
        scoped_attributes.update(entity.get("attributes") or {})
        scoped_status = entity["status"]
        if (
            entity["entity_type"] == "CONFIG"
            and prior_scope.get("status") == "CONFIG_CONFIRMED"
            and scoped_status == "CONFIG_UNRESOLVED"
            and not item.get("status")
            and "value" not in (item.get("attributes") or {})
            and "value" not in item
        ):
            scoped_status = "CONFIG_CONFIRMED"
        if entity["entity_type"] == "CONFIG":
            scoped_attributes["resolution_status"] = scoped_status
        scoped_priority = entity["priority"]
        if prior_scope.get("priority") == "P0" and scoped_priority != "P0":
            scoped_priority = "P0"
        scoped_summary = entity.get("summary") or prior_scope.get("summary") or ""
        scoped_evidence = list(dict.fromkeys(
            _as_list(prior_scope.get("evidence_refs"))
            + _as_list(entity.get("evidence_refs"))
        ))
        entity["status"] = scoped_status
        if existing:
            previous = json.loads(existing["payload_json"])
            merged_attributes = dict(previous.get("attributes") or {})
            merged_attributes.update(entity.get("attributes") or {})
            if entity["entity_type"] == "CONFIG" and scoped_status != "CONFIG_CONFIRMED":
                for key in ("value", "environment", "resolution_source"):
                    merged_attributes.pop(key, None)
                merged_attributes["resolution_status"] = scoped_status
            entity["attributes"] = merged_attributes
            entity["evidence_refs"] = list(dict.fromkeys(
                _as_list(previous.get("evidence_refs")) + _as_list(entity.get("evidence_refs"))
            ))
            if not entity.get("summary"):
                entity["summary"] = previous.get("summary") or ""
            if entity["display_name"] == entity["logical_key"] and previous.get("display_name"):
                entity["display_name"] = previous["display_name"]
            if previous.get("priority") == "P0" and entity.get("priority") != "P0":
                entity["priority"] = "P0"

        sequence_no = entity.pop("sequence_no")
        role = entity.pop("role")
        content_hash = canonical_hash(entity)
        changed = not existing or existing["content_hash"] != content_hash
        timestamp = now_iso()
        if changed:
            if existing:
                self.store._archive_existing("knowledge_entities", entity_id, existing, None)
            self.store.conn.execute(
                "INSERT INTO knowledge_entities(entity_id,entity_type,logical_key,display_name,summary,priority,status,payload_json,content_hash,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(entity_id) DO UPDATE SET "
                "display_name=excluded.display_name,summary=excluded.summary,priority=excluded.priority,"
                "status=excluded.status,payload_json=excluded.payload_json,content_hash=excluded.content_hash,updated_at=excluded.updated_at",
                (
                    entity_id, entity["entity_type"], entity["logical_key"], entity["display_name"],
                    entity["summary"], entity["priority"], entity["status"], _json(entity),
                    content_hash, existing["created_at"] if existing else timestamp, timestamp,
                ),
            )
        membership = {
            "role": role,
            "sequence_no": sequence_no,
            "status": scoped_status,
            "priority": scoped_priority,
            "summary": scoped_summary,
            "attributes": scoped_attributes,
            "evidence_refs": scoped_evidence,
        }
        membership_changed = (
            existing_membership is None
            or canonical_hash(prior_scope) != canonical_hash(membership)
        )
        self.store.conn.execute(
            "INSERT INTO knowledge_memberships(scenario_id,entity_id,role,sequence_no,payload_json,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(scenario_id,entity_id) DO UPDATE SET "
            "role=CASE WHEN excluded.role!='' THEN excluded.role ELSE knowledge_memberships.role END,"
            "sequence_no=CASE WHEN excluded.sequence_no!=0 THEN excluded.sequence_no ELSE knowledge_memberships.sequence_no END,"
            "payload_json=excluded.payload_json,updated_at=excluded.updated_at",
            (scenario_id, entity_id, role, sequence_no, _json(membership), timestamp, timestamp),
        )
        return self._project_membership(entity, membership), changed or membership_changed

    @staticmethod
    def _project_membership(
        entity: dict[str, Any],
        payload: str | dict[str, Any] | None,
        *,
        sequence_no: float | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        """Keep shared identities/names global while runtime state stays per Scenario."""
        if not payload:
            return entity
        scoped = json.loads(payload) if isinstance(payload, str) else payload
        result = dict(entity)
        for key in ("status", "priority", "summary"):
            if key in scoped and scoped[key] not in (None, ""):
                result[key] = scoped[key]
        if "attributes" in scoped:
            result["attributes"] = dict(scoped.get("attributes") or {})
        if "evidence_refs" in scoped:
            result["evidence_refs"] = list(scoped.get("evidence_refs") or [])
        if sequence_no is not None:
            result["sequence_no"] = sequence_no
        if role:
            result["role"] = role
        return result

    def find_entity(self, reference: str, scenario_id: str | None = None) -> dict[str, Any] | None:
        value = _string(reference)
        if not value:
            return None
        typed: tuple[str, str] | None = None
        if ":" in value:
            kind, key = value.split(":", 1)
            normalized_kind = kind.upper()
            if normalized_kind in ENTITY_TYPES:
                typed = (normalized_kind, key)
        query = (
            "SELECT e.payload_json"
            + (",m.payload_json AS membership_json,m.sequence_no,m.role" if scenario_id else "")
            + " FROM knowledge_entities e "
            + ("JOIN knowledge_memberships m ON m.entity_id=e.entity_id " if scenario_id else "")
            + ("WHERE e.entity_type=? AND e.logical_key=? " if typed else "WHERE (e.entity_id=? OR e.logical_key=?) ")
            + ("AND m.scenario_id=? " if scenario_id else "")
            + ("ORDER BY e.updated_at DESC LIMIT 1" if typed else "ORDER BY CASE WHEN e.entity_id=? THEN 0 ELSE 1 END,e.updated_at DESC LIMIT 1")
        )
        parameters: list[Any] = list(typed) if typed else [value, value]
        if scenario_id:
            parameters.append(scenario_id)
        if not typed:
            parameters.append(value)
        row = self.store.conn.execute(query, parameters).fetchone()
        if not row:
            return None
        entity = json.loads(row["payload_json"])
        if scenario_id:
            return self._project_membership(
                entity, row["membership_json"],
                sequence_no=row["sequence_no"], role=row["role"],
            )
        return entity

    def _upsert_edge(self, scenario_id: str, item: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        if not isinstance(item, dict):
            raise GraphContractError("Each relation must be an object")
        source_ref = _string(item.get("source") or item.get("from") or item.get("source_entity_id"))
        target_ref = _string(item.get("target") or item.get("to") or item.get("target_entity_id"))
        relation_type = _string(item.get("relation_type") or item.get("type") or item.get("kind")).upper()
        if not source_ref or not target_ref or not relation_type:
            raise GraphContractError("A relation requires from/source, to/target, and type")
        source = self.find_entity(source_ref, scenario_id)
        target = self.find_entity(target_ref, scenario_id)
        if not source or not target:
            missing = source_ref if not source else target_ref
            raise GraphContractError(f"Relation references an unknown entity: {missing}")
        identity = [scenario_id, source["entity_id"], target["entity_id"], relation_type, item.get("condition_ref")]
        edge_id = f"EDGE-{short_hash(identity, 16)}"
        edge = {
            "edge_id": edge_id,
            "scenario_id": scenario_id,
            "source_entity_id": source["entity_id"],
            "target_entity_id": target["entity_id"],
            "relation_type": relation_type,
            "sequence_no": _safe_number(item.get("sequence_no")),
            "condition_ref": _string(item.get("condition_ref") or item.get("condition")),
            "label": _compact_text(item.get("label") or item.get("summary"), 240),
            "attributes": dict(item.get("attributes") or {}),
        }
        existing = self.store.conn.execute(
            "SELECT payload_json,content_hash,created_at FROM knowledge_edges WHERE edge_id=?",
            (edge_id,),
        ).fetchone()
        digest = canonical_hash(edge)
        changed = not existing or existing["content_hash"] != digest
        if changed:
            timestamp = now_iso()
            if existing:
                self.store._archive_existing("knowledge_edges", edge_id, existing, None)
            self.store.conn.execute(
                "INSERT INTO knowledge_edges(edge_id,scenario_id,source_entity_id,target_entity_id,relation_type,sequence_no,condition_ref,payload_json,content_hash,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(edge_id) DO UPDATE SET "
                "sequence_no=excluded.sequence_no,condition_ref=excluded.condition_ref,payload_json=excluded.payload_json,"
                "content_hash=excluded.content_hash,updated_at=excluded.updated_at",
                (
                    edge_id, scenario_id, source["entity_id"], target["entity_id"], relation_type,
                    edge["sequence_no"], edge["condition_ref"], _json(edge), digest,
                    existing["created_at"] if existing else timestamp, timestamp,
                ),
            )
        return edge, changed

    def _ensure_system(
        self,
        scenario_id: str,
        value: Any,
        created: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not value:
            return None
        if isinstance(value, dict):
            item = dict(value)
        else:
            existing = self.find_entity(_string(value), scenario_id)
            if existing and existing.get("entity_type") != "SYSTEM":
                existing = None
            existing = existing or self.find_entity(f"SYSTEM:{value}", scenario_id)
            if existing:
                return existing
            item = {"logical_key": _slug(value), "display_name": _string(value)}
        system, changed = self._upsert_entity(scenario_id, item, "SYSTEM")
        if changed:
            created.append(system)
        return system

    def _expand_entity(
        self,
        scenario_id: str,
        item: dict[str, Any],
        entity_type: str,
        created: list[dict[str, Any]],
        generated_edges: list[dict[str, Any]],
    ) -> None:
        raw_evidence = _as_list(item.get("evidence_refs") or item.get("evidence_ids"))
        if raw_evidence:
            item = {
                **item,
                "evidence_refs": [
                    (resolved or {}).get("entity_id", _string(reference))
                    for reference in raw_evidence
                    if _string(reference)
                    for resolved in [self.find_entity(_string(reference), scenario_id)]
                ],
            }
        entity, changed = self._upsert_entity(scenario_id, item, entity_type)
        if changed:
            created.append(entity)
        reference = entity["entity_id"]
        for evidence in entity.get("evidence_refs") or []:
            if self.find_entity(evidence, scenario_id):
                generated_edges.append({"source": reference, "target": evidence, "type": "EVIDENCED_BY"})

        if entity_type == "DECISION":
            configuration_keys = _as_list(
                item.get("config_keys") or item.get("configuration_keys")
                or item.get("config_key") or (item.get("attributes") or {}).get("config_keys")
            )
            for key in configuration_keys:
                key_text = _string(key.get("key") if isinstance(key, dict) else key)
                if not key_text:
                    continue
                configuration = key if isinstance(key, dict) else {"logical_key": key_text, "name": key_text}
                config_entity, config_changed = self._upsert_entity(scenario_id, configuration, "CONFIG")
                if config_changed:
                    created.append(config_entity)
                generated_edges.append({"source": reference, "target": config_entity["entity_id"], "type": "DEPENDS_ON"})

            for index, branch in enumerate(_as_list(item.get("branches")), start=1):
                if isinstance(branch, str):
                    branch = {"name": branch}
                if not isinstance(branch, dict):
                    raise GraphContractError("Decision branches must be strings or objects")
                branch_key = _string(branch.get("logical_key") or branch.get("key") or branch.get("name") or index)
                logical_key = f"{entity['logical_key']}::{_slug(branch_key)}"
                previous_branch = self.find_entity(f"BRANCH:{logical_key}", scenario_id)
                branch_payload = {
                    **branch,
                    "logical_key": logical_key,
                    "display_name": branch.get("name") or branch.get("label") or branch_key,
                    "sequence_no": branch.get("sequence_no", index),
                    "priority": branch.get("priority") or entity.get("priority") or "P1",
                    "status": branch.get("status")
                    or (previous_branch or {}).get("status")
                    or ("CONFIG_UNRESOLVED" if configuration_keys else "POSSIBLE"),
                    "decision_key": entity["logical_key"],
                }
                branch_entity, branch_changed = self._upsert_entity(scenario_id, branch_payload, "BRANCH")
                if branch_changed:
                    created.append(branch_entity)
                generated_edges.append({
                    "source": reference,
                    "target": branch_entity["entity_id"],
                    "type": "BRANCHES_TO",
                    "sequence_no": index,
                    "condition": branch.get("condition") or branch.get("when"),
                    "label": branch.get("condition") or branch.get("when") or branch.get("name"),
                })
                if branch.get("target"):
                    generated_edges.append({
                        "source": branch_entity["entity_id"], "target": branch["target"],
                        "type": "LEADS_TO", "condition": branch.get("condition") or branch.get("when"),
                    })

        elif entity_type == "FIELD":
            events = _as_list(item.get("events") or item.get("steps"))
            prior_sequence = self.store.conn.execute(
                "SELECT COALESCE(MAX(sequence_no),0) AS latest FROM knowledge_edges "
                "WHERE scenario_id=? AND source_entity_id=? AND relation_type='HAS_FIELD_EVENT'",
                (scenario_id, reference),
            ).fetchone()["latest"]
            next_sequence = float(prior_sequence or 0)
            for index, event in enumerate(events, start=1):
                if not isinstance(event, dict):
                    event = {"summary": _string(event)}
                operation = _string(event.get("operation") or event.get("kind") or "COPY").upper()
                source = _string(event.get("source") or event.get("from"))
                target = _string(event.get("target") or event.get("to"))
                fingerprint = short_hash([source, target, operation], 12)
                logical_key = _string(event.get("logical_key")) or (
                    f"{entity['logical_key']}::{fingerprint}"
                )
                previous_event = self.find_entity(f"FIELD_EVENT:{logical_key}", scenario_id)
                previous_order = None
                if previous_event:
                    previous_edge = self.store.conn.execute(
                        "SELECT sequence_no FROM knowledge_edges WHERE scenario_id=? "
                        "AND source_entity_id=? AND target_entity_id=? "
                        "AND relation_type='HAS_FIELD_EVENT' LIMIT 1",
                        (scenario_id, reference, previous_event["entity_id"]),
                    ).fetchone()
                    previous_order = previous_edge["sequence_no"] if previous_edge else None
                sequence_no = event.get("sequence_no") or previous_order
                if not sequence_no:
                    next_sequence += 1
                    sequence_no = next_sequence
                event_payload = {
                    **event,
                    "logical_key": logical_key,
                    "display_name": event.get("name") or event.get("label") or f"{source or '未知来源'} → {target or '未知去向'}",
                    "canonical_field": entity["logical_key"],
                    "operation": operation,
                    "source": source,
                    "target": target,
                    "sequence_no": sequence_no,
                    "priority": entity.get("priority", "P1"),
                }
                event_entity, event_changed = self._upsert_entity(scenario_id, event_payload, "FIELD_EVENT")
                if event_changed:
                    created.append(event_entity)
                generated_edges.append({
                    "source": reference, "target": event_entity["entity_id"],
                    "type": "HAS_FIELD_EVENT", "sequence_no": sequence_no,
                    "condition": event.get("condition") or event.get("branch"),
                })

        elif entity_type == "INTERACTION":
            caller = self._ensure_system(
                scenario_id,
                item.get("source_system") or item.get("caller") or item.get("from_system"),
                created,
            )
            target = self._ensure_system(
                scenario_id,
                item.get("target_system") or item.get("callee") or item.get("to_system"),
                created,
            )
            if caller:
                generated_edges.append({"source": caller["entity_id"], "target": reference, "type": "INITIATES"})
            if target:
                generated_edges.append({"source": reference, "target": target["entity_id"], "type": "TARGETS"})
            if caller and target:
                generated_edges.append({
                    "source": caller["entity_id"], "target": target["entity_id"],
                    "type": "INTERACTS_WITH", "label": item.get("operation") or entity["display_name"],
                    "condition": item.get("condition"),
                })

        elif entity_type == "PERSISTENCE":
            table_name = _string(item.get("table") or item.get("store") or (item.get("attributes") or {}).get("table"))
            if table_name:
                table_entity, table_changed = self._upsert_entity(
                    scenario_id,
                    {"logical_key": table_name, "display_name": table_name},
                    "TABLE",
                )
                if table_changed:
                    created.append(table_entity)
                generated_edges.append({"source": reference, "target": table_entity["entity_id"], "type": "WRITES_TABLE"})

        system_ref = item.get("system") or item.get("system_key")
        if system_ref and entity_type not in {"SYSTEM", "INTERACTION"}:
            system = self._ensure_system(scenario_id, system_ref, created)
            if system:
                generated_edges.append({"source": system["entity_id"], "target": reference, "type": "OWNS"})

    def record_delta(self, session_id: str, delta: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(delta, dict):
            raise GraphContractError("An analysis delta must be a JSON object")
        serialized = _json(delta)
        if len(serialized) > MAX_DELTA_CHARS:
            raise GraphContractError("Delta is too large; submit one business milestone without raw source text")
        session = self.get_session(session_id)
        if session.get("status") != "ACTIVE":
            raise GraphContractError(f"Session cannot accept facts in status {session.get('status')}")

        items: list[tuple[dict[str, Any], str | None]] = []
        for item in _as_list(delta.get("entities")):
            items.append((item, None))
        for group, entity_type in GROUP_TYPES.items():
            for item in _as_list(delta.get(group)):
                items.append((item, entity_type))
        if any(not isinstance(item, dict) for item, _ in items):
            raise GraphContractError("Each business fact must be an object")
        priority_fields = {
            _string(field).lower() for field in session.get("priority_fields") or []
            if _string(field)
        }
        if priority_fields:
            normalized_items = []
            for item, fallback_type in items:
                item_type = _string(
                    item.get("entity_type") or item.get("type") or fallback_type
                ).upper()
                candidate_keys = {
                    _string(item.get(key)).lower()
                    for key in ("logical_key", "key", "canonical_field", "field", "name")
                    if _string(item.get(key))
                }
                if item_type in {"FIELD", "FIELD_JOURNEY"} and candidate_keys & priority_fields:
                    item = {**item, "priority": "P0"}
                normalized_items.append((item, fallback_type))
            items = normalized_items
        if len(items) > MAX_ENTITIES_PER_DELTA:
            raise GraphContractError("Delta has too many entities; split by meaningful business milestone")
        explicit_edges = _as_list(delta.get("relations") or delta.get("edges"))
        if len(explicit_edges) > MAX_EDGES_PER_DELTA:
            raise GraphContractError("Delta has too many relations; split by business milestone")

        scenario_id = session["scenario_id"]
        created: list[dict[str, Any]] = []
        generated_edges: list[dict[str, Any]] = []
        edge_changes = 0
        self.store.conn.execute("BEGIN IMMEDIATE")
        try:
            # Evidence and owner systems must exist before later references are resolved.
            order = {"EVIDENCE": 0, "SYSTEM": 1, "MODULE": 2, "BUSINESS_STEP": 3}
            items.sort(key=lambda pair: order.get(
                _string(pair[1] or pair[0].get("entity_type") or pair[0].get("type")).upper(), 4
            ))
            for item, fallback_type in items:
                entity_type = self._normalize_entity(item, fallback_type)["entity_type"]
                self._expand_entity(scenario_id, item, entity_type, created, generated_edges)

            # Generated references can point at entities declared later in the same delta.
            unresolved_edges = []
            for edge in generated_edges + explicit_edges:
                try:
                    _, changed = self._upsert_edge(scenario_id, edge)
                except GraphContractError as exc:
                    if edge in generated_edges and "unknown entity" in str(exc):
                        unresolved_edges.append(_compact_text(str(exc), 220))
                        continue
                    raise
                edge_changes += int(changed)

            focus = _compact_text(delta.get("focus") or delta.get("focus_key"), 320)
            summary = _compact_text(
                delta.get("summary") or delta.get("milestone")
                or (f"更新 {len(created)} 项业务事实" if created or edge_changes else "没有新增业务事实"),
                1_600,
            )
            previous_milestone = self.store.conn.execute(
                "SELECT summary,focus_key FROM exploration_milestones "
                "WHERE session_id=? ORDER BY rowid DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            summary_changed = bool(delta.get("summary") or delta.get("milestone")) and (
                previous_milestone is None
                or previous_milestone["summary"] != summary
                or (previous_milestone["focus_key"] or "") != focus
            )
            digest = delta.get("scenario_summary") or delta.get("digest")
            digest_changed = bool(digest) and _compact_text(digest, 2_400) != session.get("digest")
            semantic_change = bool(created or edge_changes or summary_changed or digest_changed)
            estimated = int(delta.get("observed_tokens") or approx_tokens(serialized))
            session["estimated_tokens_used"] += max(0, estimated)
            session["milestone_count"] += int(semantic_change)
            if focus:
                session["current_focus"] = focus
            if digest:
                session["digest"] = _compact_text(digest, 2_400)
            milestone_id = None
            if semantic_change:
                milestone_id = new_id("MILESTONE")
                milestone = {
                    "milestone_id": milestone_id,
                    "session_id": session_id,
                    "scenario_id": scenario_id,
                    "focus_key": focus,
                    "summary": summary,
                    "entity_ids": [item["entity_id"] for item in created],
                    "changed_edges": edge_changes,
                    "unresolved_generated_edges": unresolved_edges,
                }
                self.store.conn.execute(
                    "INSERT INTO exploration_milestones(milestone_id,session_id,scenario_id,focus_key,summary,estimated_tokens,payload_json,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (milestone_id, session_id, scenario_id, focus, summary, estimated, _json(milestone), now_iso()),
                )
            if session["estimated_tokens_used"] >= session["total_token_budget"]:
                session["budget_notice"] = "SOFT_TOKEN_BUDGET_REACHED"
            self._save_session(session)
            self.store.commit()
        except Exception:
            self.store.conn.rollback()
            raise

        counts = Counter(item["entity_type"] for item in created)
        return {
            "status": "RECORDED" if semantic_change else "NO_CHANGE",
            "session_id": session_id,
            "milestone_id": milestone_id,
            "changed_entities": len(created),
            "changed_edges": edge_changes,
            "entity_types": dict(counts),
            "estimated_tokens_used": session["estimated_tokens_used"],
            "budget_notice": session.get("budget_notice"),
            "unresolved_generated_edges": unresolved_edges,
        }

    def scenario_graph(self, scenario_id: str) -> dict[str, Any]:
        scenario = self.store.get("scenarios", scenario_id)
        if not scenario:
            raise GraphContractError(f"Unknown Scenario: {scenario_id}")
        entity_rows = self.store.conn.execute(
            "SELECT e.payload_json,m.payload_json AS membership_json,m.sequence_no,m.role FROM knowledge_entities e "
            "JOIN knowledge_memberships m ON m.entity_id=e.entity_id "
            "WHERE m.scenario_id=? ORDER BY m.sequence_no,e.entity_type,e.display_name",
            (scenario_id,),
        ).fetchall()
        entities = []
        for row in entity_rows:
            item = self._project_membership(
                json.loads(row["payload_json"]), row["membership_json"],
                sequence_no=row["sequence_no"], role=row["role"],
            )
            entities.append(item)
        edge_rows = self.store.conn.execute(
            "SELECT payload_json FROM knowledge_edges WHERE scenario_id=? ORDER BY sequence_no,edge_id",
            (scenario_id,),
        ).fetchall()
        return {
            "scenario": scenario,
            "session": self.latest_session(scenario_id),
            "entities": entities,
            "edges": [json.loads(row["payload_json"]) for row in edge_rows],
            "coverage": self.coverage(scenario_id, entities=entities),
        }

    def list_entities(
        self,
        *,
        entity_type: str | None = None,
        scenario_id: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT e.payload_json"
            + (",m.payload_json AS membership_json,m.sequence_no,m.role" if scenario_id else "")
            + " FROM knowledge_entities e"
        )
        conditions = []
        params: list[Any] = []
        if scenario_id:
            sql += " JOIN knowledge_memberships m ON m.entity_id=e.entity_id"
            conditions.append("m.scenario_id=?")
            params.append(scenario_id)
        if entity_type:
            conditions.append("e.entity_type=?")
            params.append(entity_type.upper())
        if search:
            conditions.append("(e.logical_key LIKE ? OR e.display_name LIKE ? OR e.summary LIKE ? OR e.payload_json LIKE ?)")
            pattern = f"%{search}%"
            params.extend([pattern, pattern, pattern, pattern])
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY CASE e.priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END,e.updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        result = []
        for row in self.store.conn.execute(sql, params).fetchall():
            item = json.loads(row["payload_json"])
            if scenario_id:
                item = self._project_membership(
                    item, row["membership_json"],
                    sequence_no=row["sequence_no"], role=row["role"],
                )
            result.append(item)
        return result

    def entity_scenarios(self, entity_id: str) -> list[dict[str, Any]]:
        rows = self.store.conn.execute(
            "SELECT s.payload_json FROM scenarios s JOIN knowledge_memberships m ON m.scenario_id=s.scenario_id "
            "WHERE m.entity_id=? ORDER BY s.name",
            (entity_id,),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def entity_neighbors(self, entity_id: str, scenario_id: str | None = None) -> list[dict[str, Any]]:
        where = "(g.source_entity_id=? OR g.target_entity_id=?)"
        params: list[Any] = [entity_id, entity_id]
        if scenario_id:
            where += " AND g.scenario_id=?"
            params.append(scenario_id)
        rows = self.store.conn.execute(
            "SELECT DISTINCT e.payload_json"
            + (",m.payload_json AS membership_json,m.sequence_no,m.role" if scenario_id else "")
            + " FROM knowledge_edges g JOIN knowledge_entities e "
            "ON e.entity_id=CASE WHEN g.source_entity_id=? THEN g.target_entity_id ELSE g.source_entity_id END "
            + ("JOIN knowledge_memberships m ON m.entity_id=e.entity_id AND m.scenario_id=g.scenario_id " if scenario_id else "")
            + f"WHERE {where} ORDER BY e.priority,e.display_name",
            [entity_id, *params],
        ).fetchall()
        result = []
        for row in rows:
            item = json.loads(row["payload_json"])
            if scenario_id:
                item = self._project_membership(
                    item, row["membership_json"],
                    sequence_no=row["sequence_no"], role=row["role"],
                )
            result.append(item)
        return result

    def coverage(
        self,
        scenario_id: str,
        *,
        entities: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        items = entities if entities is not None else self.list_entities(scenario_id=scenario_id, limit=500)
        counts = Counter(item["entity_type"] for item in items)
        unresolved_configuration = [
            item for item in items
            if item["entity_type"] == "CONFIG" and item.get("status") != "CONFIG_CONFIRMED"
        ]
        open_gaps = [
            item for item in items if item["entity_type"] == "GAP"
            and item.get("status") not in {"CLOSED", "RESOLVED"}
        ]
        priority_fields = [
            item for item in items if item["entity_type"] == "FIELD" and item.get("priority") == "P0"
        ]
        return {
            "scenario_id": scenario_id,
            "entity_counts": dict(counts),
            "systems": counts.get("SYSTEM", 0),
            "modules": counts.get("MODULE", 0),
            "business_steps": counts.get("BUSINESS_STEP", 0),
            "decisions": counts.get("DECISION", 0),
            "branches": counts.get("BRANCH", 0),
            "priority_fields": len(priority_fields),
            "interactions": counts.get("INTERACTION", 0),
            "persistence": counts.get("PERSISTENCE", 0),
            "unresolved_configurations": len(unresolved_configuration),
            "configuration_keys": [item["logical_key"] for item in unresolved_configuration],
            "open_gaps": len(open_gaps),
            "gap_questions": [item.get("summary") or item["display_name"] for item in open_gaps],
        }

    def build_context(
        self,
        session_id: str,
        *,
        focus: str | None = None,
        fields: list[str] | None = None,
        symbols: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        session = self.get_session(session_id)
        scenario_id = session["scenario_id"]
        scenario = self.store.get("scenarios", scenario_id) or {}
        budget = max(600, min(int(max_tokens or session["context_target_tokens"]), 60_000))
        requested_terms = list(dict.fromkeys(
            _string(term).lower()
            for term in [focus, *_as_list(fields), *_as_list(symbols), *session.get("priority_fields", [])]
            if _string(term)
        ))
        candidates = self.list_entities(scenario_id=scenario_id, limit=500)
        milestone_rows = self.store.conn.execute(
            "SELECT summary,focus_key FROM exploration_milestones WHERE session_id=? "
            "ORDER BY created_at DESC LIMIT 4",
            (session_id,),
        ).fetchall()
        coverage = self.coverage(scenario_id, entities=candidates)
        preview_limit = max(2, min(8, budget // 250))
        for key, omitted_key in (
            ("configuration_keys", "omitted_configuration_keys"),
            ("gap_questions", "omitted_gap_questions"),
        ):
            values = coverage.get(key) or []
            coverage[key] = [_compact_text(value, 130) for value in values[:preview_limit]]
            coverage[omitted_key] = max(0, len(values) - len(coverage[key]))
        trigger = scenario.get("trigger") or {}
        context = {
            "session_id": session_id,
            "scenario": {
                "scenario_id": scenario_id,
                "name": _compact_text(scenario.get("name"), 150),
                "goal": _compact_text(session.get("goal"), 360),
                "trigger": {
                    key: _compact_text(trigger.get(key), 180)
                    for key in ("kind", "symbol", "input_type") if trigger.get(key)
                },
                "priority_fields": [
                    _compact_text(value, 80) for value in (session.get("priority_fields") or [])[:12]
                ],
            },
            "global_digest": _compact_text(session.get("digest"), min(1200, max(240, budget))),
            "focus": _compact_text(focus or session.get("current_focus"), 220),
            "relevant_facts": [],
            "omitted_fact_count": len(candidates),
            "recent_milestones": [{
                "summary": _compact_text(row["summary"], 160),
                "focus_key": _compact_text(row["focus_key"], 100),
            } for row in milestone_rows],
            "coverage": coverage,
            "context_budget_tokens": budget,
            "approx_context_tokens": 0,
            "retrieval_hint": "Ask for a field, decision, module, system, or symbol; do not load the complete dossier.",
        }
        max_chars = max(0, budget * 4 - len(_json(context)) - 48)

        def score(item: dict[str, Any]) -> tuple[int, int, str]:
            haystack = _json({
                "key": item.get("logical_key"), "name": item.get("display_name"),
                "summary": item.get("summary"), "attributes": item.get("attributes"),
            }).lower()
            term_score = sum(10 for term in requested_terms if term in haystack)
            priority_score = {"P0": 5, "P1": 2, "P2": 0}.get(item.get("priority"), 0)
            type_score = 3 if item.get("entity_type") in {"DECISION", "CONFIG", "GAP"} else 0
            if item.get("status") == "CONFIG_UNRESOLVED":
                type_score += 45
            if item.get("entity_type") == "GAP":
                type_score += 40
            if item.get("entity_type") == "FIELD" and item.get("logical_key", "").lower() in requested_terms:
                type_score += 35
            operation = _string((item.get("attributes") or {}).get("operation")).upper()
            if item.get("entity_type") == "FIELD_EVENT" and operation in PASS_THROUGH_OPERATIONS:
                type_score -= 18
            return (-term_score - priority_score - type_score, int(item.get("sequence_no") or 0), item.get("display_name", ""))

        selected = []
        used = 0
        for item in sorted(candidates, key=score):
            compact = {
                "id": item["entity_id"],
                "type": item["entity_type"],
                "key": item["logical_key"],
                "name": item["display_name"],
                "summary": _compact_text(item.get("summary"), 220),
                "priority": item.get("priority"),
                "status": item.get("status"),
            }
            attrs = item.get("attributes") or {}
            important_keys = (
                "condition", "source", "target", "operation", "config_key", "value",
                "resolution_status", "expected_value", "table", "source_system",
                "target_system", "canonical_field", "business_effect",
            )
            compact_attributes = {key: attrs[key] for key in important_keys if key in attrs}
            if compact_attributes:
                compact["facts"] = compact_attributes
            size = len(_json(compact))
            if used + size > max_chars:
                continue
            selected.append(compact)
            used += size

        context["relevant_facts"] = selected
        context["omitted_fact_count"] = max(0, len(candidates) - len(selected))
        while selected and approx_tokens(_json(context)) > budget:
            selected.pop()
            context["omitted_fact_count"] = max(0, len(candidates) - len(selected))
        context["approx_context_tokens"] = approx_tokens(_json(context))
        while selected and approx_tokens(_json(context)) > budget:
            selected.pop()
            context["omitted_fact_count"] = max(0, len(candidates) - len(selected))
            context["approx_context_tokens"] = approx_tokens(_json(context))
        return context

    def field_projection(self, scenario_id: str, field_reference: str) -> dict[str, Any]:
        field = self.find_entity(f"FIELD:{field_reference}", scenario_id) or self.find_entity(field_reference, scenario_id)
        if not field or field.get("entity_type") != "FIELD":
            raise GraphContractError(f"Unknown business field: {field_reference}")
        rows = self.store.conn.execute(
            "SELECT e.payload_json,m.payload_json AS membership_json,m.sequence_no,m.role "
            "FROM knowledge_edges g "
            "JOIN knowledge_entities e ON e.entity_id=g.target_entity_id "
            "JOIN knowledge_memberships m ON m.entity_id=e.entity_id AND m.scenario_id=g.scenario_id "
            "WHERE g.scenario_id=? AND g.source_entity_id=? AND g.relation_type='HAS_FIELD_EVENT' "
            "ORDER BY g.sequence_no,e.display_name",
            (scenario_id, field["entity_id"]),
        ).fetchall()
        events = [
            self._project_membership(
                json.loads(row["payload_json"]), row["membership_json"],
                sequence_no=row["sequence_no"], role=row["role"],
            )
            for row in rows
        ]
        display_events = []
        pending_copies: list[dict[str, Any]] = []

        def flush_copies() -> None:
            if not pending_copies:
                return
            first = pending_copies[0].get("attributes") or {}
            last = pending_copies[-1].get("attributes") or {}
            display_events.append({
                "kind": "COLLAPSED_COPY",
                "count": len(pending_copies),
                "source": first.get("source"),
                "target": last.get("target"),
                "summary": f"{len(pending_copies)} 次普通复制已折叠",
                "entity_ids": [event["entity_id"] for event in pending_copies],
            })
            pending_copies.clear()

        for event in events:
            attributes = event.get("attributes") or {}
            operation = _string(attributes.get("operation")).upper()
            if operation in PASS_THROUGH_OPERATIONS:
                pending_copies.append(event)
            else:
                flush_copies()
                display_events.append({
                    "kind": "SEMANTIC_CHANGE",
                    "operation": operation,
                    "source": attributes.get("source"),
                    "target": attributes.get("target"),
                    "condition": attributes.get("condition"),
                    "summary": event.get("summary") or event.get("display_name"),
                    "entity_id": event["entity_id"],
                })
        flush_copies()
        return {
            "field": field,
            "priority": field.get("priority"),
            "events": display_events,
            "raw_event_count": len(events),
            "collapsed_copy_count": sum(event.get("count", 0) for event in display_events if event["kind"] == "COLLAPSED_COPY"),
            "scenarios": self.entity_scenarios(field["entity_id"]),
        }

    def resolve_configuration(
        self,
        scenario_id: str,
        config_key: str,
        value: Any,
        *,
        environment: str = "prod",
        evidence: str | None = None,
    ) -> dict[str, Any]:
        configuration = self.find_entity(f"CONFIG:{config_key}", scenario_id)
        if not configuration:
            raise GraphContractError(f"Unknown configuration reference: {config_key}")
        self.store.conn.execute("BEGIN IMMEDIATE")
        try:
            payload = {
                **configuration,
                "attributes": {
                    **(configuration.get("attributes") or {}),
                    "value": _redact_config_value(config_key, value),
                    "environment": environment,
                    "resolution_status": "CONFIG_CONFIRMED",
                    "resolution_source": "PADB" if evidence else "USER_PROVIDED",
                },
                "status": "CONFIG_CONFIRMED",
            }
            if evidence:
                payload["evidence_refs"] = list(dict.fromkeys(configuration.get("evidence_refs", []) + [evidence]))
            updated, _ = self._upsert_entity(scenario_id, payload, "CONFIG")
            selected_branches = []
            decision_rows = self.store.conn.execute(
                "SELECT e.entity_id FROM knowledge_edges g JOIN knowledge_entities e ON e.entity_id=g.source_entity_id "
                "WHERE g.scenario_id=? AND g.target_entity_id=? AND g.relation_type='DEPENDS_ON'",
                (scenario_id, configuration["entity_id"]),
            ).fetchall()
            for decision_row in decision_rows:
                decision = self.find_entity(decision_row["entity_id"], scenario_id)
                if not decision:
                    continue
                decision_selected_branches = []
                branch_rows = self.store.conn.execute(
                    "SELECT e.entity_id FROM knowledge_edges g JOIN knowledge_entities e ON e.entity_id=g.target_entity_id "
                    "WHERE g.scenario_id=? AND g.source_entity_id=? AND g.relation_type='BRANCHES_TO'",
                    (scenario_id, decision["entity_id"]),
                ).fetchall()
                for branch_row in branch_rows:
                    branch = self.find_entity(branch_row["entity_id"], scenario_id)
                    if not branch:
                        continue
                    attrs = branch.get("attributes") or {}
                    expected = attrs.get("expected_value", attrs.get("value"))
                    candidates = _as_list(attrs.get("expected_values") or attrs.get("values"))
                    if expected is not None:
                        candidates.append(expected)
                    if not candidates:
                        continue
                    selected = any(str(candidate) == str(value) for candidate in candidates)
                    branch["status"] = "ACTIVE" if selected else "INACTIVE"
                    self._upsert_entity(scenario_id, branch, "BRANCH")
                    if selected:
                        selected_branches.append(branch["entity_id"])
                        decision_selected_branches.append(branch["entity_id"])
                decision["attributes"] = {
                    **(decision.get("attributes") or {}),
                    "selected_branch_ids": decision_selected_branches,
                    "configuration_status": "CONFIG_CONFIRMED",
                }
                self._upsert_entity(scenario_id, decision, "DECISION")
            self.store.commit()
        except Exception:
            self.store.conn.rollback()
            raise
        return {
            "status": "CONFIG_CONFIRMED",
            "scenario_id": scenario_id,
            "configuration": updated,
            "selected_branch_ids": selected_branches,
        }

    def rename_entity(self, entity_id: str, display_name: str) -> dict[str, Any]:
        name = _compact_text(display_name, 160)
        if not name:
            raise GraphContractError("Display name cannot be empty")
        entity = self.find_entity(entity_id)
        if not entity:
            raise GraphContractError(f"Unknown graph entity: {entity_id}")
        scenarios = self.entity_scenarios(entity_id)
        if not scenarios:
            raise GraphContractError("Cannot rename an entity that has no scenario membership")
        updated = {**entity, "display_name": name}
        previous = self.store.conn.execute(
            "SELECT payload_json,content_hash,created_at FROM knowledge_entities WHERE entity_id=?",
            (entity_id,),
        ).fetchone()
        if entity.get("display_name") != name:
            self.store._archive_existing("knowledge_entities", entity_id, previous, None)
            self.store.conn.execute(
                "UPDATE knowledge_entities SET display_name=?,payload_json=?,content_hash=?,updated_at=? "
                "WHERE entity_id=?",
                (name, _json(updated), canonical_hash(updated), now_iso(), entity_id),
            )
        self.store.commit()
        return {
            "status": "RENAMED",
            "entity": updated,
            "affected_scenario_ids": [scenario["scenario_id"] for scenario in scenarios],
        }

    def finish_session(
        self,
        session_id: str,
        *,
        summary: str | None = None,
        status: str = "COMPLETE",
    ) -> dict[str, Any]:
        session = self.get_session(session_id)
        if status not in {"COMPLETE", "PARTIAL", "STOPPED"}:
            raise GraphContractError("Session status must be COMPLETE, PARTIAL, or STOPPED")
        coverage = self.coverage(session["scenario_id"])
        if status == "COMPLETE" and coverage["open_gaps"]:
            status = "PARTIAL"
        session["status"] = status
        session["completed_at"] = now_iso()
        if summary:
            session["digest"] = _compact_text(summary, 2_400)
        self._save_session(session)
        self.store.commit()
        return {"status": status, "session": session, "coverage": coverage}

    def summary(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        rows = self.store.conn.execute(
            "SELECT summary,focus_key,created_at FROM exploration_milestones WHERE session_id=? "
            "ORDER BY created_at DESC LIMIT 8",
            (session_id,),
        ).fetchall()
        return {
            "session": session,
            "coverage": self.coverage(session["scenario_id"]),
            "recent_milestones": [dict(row) for row in rows],
        }
