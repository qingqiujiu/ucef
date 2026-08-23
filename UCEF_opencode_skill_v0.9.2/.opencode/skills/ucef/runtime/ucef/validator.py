from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import new_id
from .store import FactStore


COLLECTION_RULES: dict[str, dict[str, Any]] = {
    "evidences": {"id": "evidence_id", "prefix": "EV", "required": ["evidence_kind", "source", "observation"]},
    "fragments": {"id": "fragment_id", "prefix": "FRAG", "required": ["logical_key", "name", "business_purpose", "entry_contract", "exit_contract", "status", "evidence_ids"]},
    "trace_stages": {"id": "stage_id", "prefix": "STAGE", "required": ["scenario_id", "sequence_no", "name", "business_purpose", "input", "processing", "output", "status"]},
    "route_decisions": {"id": "decision_id", "prefix": "DEC", "required": ["scenario_id", "question", "inputs", "current_outcome", "reason", "evidence_ids"]},
    "field_lineage_steps": {"id": "lineage_step_id", "prefix": "FLD", "required": ["scenario_id", "canonical_field", "sequence_no", "lineage_role", "operation", "source", "target", "business_use", "evidence_ids"]},
    "persistence_effects": {"id": "effect_id", "prefix": "DB", "required": ["scenario_id", "store", "operation", "mappings", "business_effect", "evidence_ids"]},
    "external_interactions": {"id": "interaction_id", "prefix": "EXT", "required": ["scenario_id", "target_system", "operation", "business_purpose", "request_params", "response_params", "evidence_ids"]},
    "gaps": {"id": "gap_id", "prefix": "GAP", "required": ["scenario_id", "category", "severity", "question"]},
    "next_work_units": {"id": "work_unit_id", "prefix": "WU", "required": ["scenario_id", "work_type", "objective"]},
}

EVIDENCE_COLLECTIONS = {
    "fragments", "route_decisions", "field_lineage_steps",
    "persistence_effects", "external_interactions",
}


def _observation_reference_errors(store: FactStore, record: dict[str, Any]) -> list[str]:
    return [
        f"Missing Observation reference: {observation_id}"
        for observation_id in record.get("observation_ids") or []
        if not store.observation_exists(str(observation_id))
    ]


def _missing(record: dict[str, Any], field: str) -> bool:
    return field not in record or record[field] is None or record[field] == "" or record[field] == []


class IngestionValidator:
    def __init__(
        self,
        store: FactStore,
        registered_sources: set[str] | None = None,
        require_registered_sources: bool = False,
    ):
        self.store = store
        self.registered_sources = registered_sources or set()
        self.require_registered_sources = require_registered_sources
        self.active_scenario_sources: set[str] = set()

    def _source_id_errors(self, source_id: Any, label: str) -> list[str]:
        if not source_id:
            return [f"{label} requires source_id"] if self.require_registered_sources else []
        if self.registered_sources and str(source_id) not in self.registered_sources:
            return [f"Unknown source_id in {label}: {source_id}"]
        if self.active_scenario_sources and str(source_id) not in self.active_scenario_sources:
            return [f"source_id is not in active Scenario scope for {label}: {source_id}"]
        return []

    def _ensure_id(self, collection: str, record: dict[str, Any]) -> None:
        rule = COLLECTION_RULES[collection]
        field = rule["id"]
        if _missing(record, field) or str(record[field]).upper() == "AUTO":
            record[field] = new_id(rule["prefix"])

    def validate_record(
        self,
        collection: str,
        record: dict[str, Any],
        scenario_id: str | None,
        batch_ids: dict[str, set[str]],
    ) -> list[str]:
        errors: list[str] = []
        if not isinstance(record, dict):
            return ["Record must be a JSON object"]
        self._ensure_id(collection, record)
        if collection not in {"evidences", "fragments"} and scenario_id and not record.get("scenario_id"):
            record["scenario_id"] = scenario_id
        for field in COLLECTION_RULES[collection]["required"]:
            if _missing(record, field):
                errors.append(f"Missing required field: {field}")
        errors.extend(_observation_reference_errors(self.store, record))

        if collection == "evidences" and record.get("evidence_kind") == "SOURCE":
            source = record.get("source")
            if not isinstance(source, dict):
                errors.append("SOURCE Evidence requires an object source with source_id and relative file")
            else:
                errors.extend(self._source_id_errors(source.get("source_id"), "SOURCE Evidence"))
                relative_file = source.get("file") or source.get("relative_path")
                if not relative_file:
                    errors.append("SOURCE Evidence requires file or relative_path")
                elif Path(str(relative_file)).is_absolute():
                    errors.append("SOURCE Evidence file must be relative to its registered source root")

        if collection == "fragments":
            errors.extend(self._source_id_errors(record.get("source_id"), "Behavior Fragment"))

        if collection in {
            "trace_stages", "route_decisions", "field_lineage_steps",
            "persistence_effects", "external_interactions",
        }:
            errors.extend(self._source_id_errors(record.get("source_id"), collection))

        if collection in EVIDENCE_COLLECTIONS:
            for evidence_id in record.get("evidence_ids") or []:
                if evidence_id not in batch_ids["evidences"] and not self.store.has_evidence(evidence_id):
                    errors.append(f"Missing Evidence reference: {evidence_id}")

        sid = record.get("scenario_id")
        if sid and sid not in batch_ids["scenarios"] and not self.store.has("scenarios", sid):
            errors.append(f"Missing Scenario reference: {sid}")
        stage_id = record.get("stage_id")
        if stage_id and stage_id not in batch_ids["trace_stages"] and not self.store.has("trace_stages", stage_id):
            errors.append(f"Missing TraceStage reference: {stage_id}")
        fragment_id = record.get("fragment_id")
        if fragment_id and fragment_id not in batch_ids["fragments"] and not self.store.has("fragments", fragment_id):
            errors.append(f"Missing Fragment reference: {fragment_id}")

        if collection == "trace_stages":
            if not record.get("terminal") and _missing(record, "next_handoff"):
                errors.append("Non-terminal TraceStage requires next_handoff")
            if not record.get("evidence_ids") and not record.get("fragment_id"):
                errors.append("TraceStage requires evidence_ids or a reusable fragment_id")

        if collection == "fragments":
            for contract in ("entry_contract", "exit_contract"):
                if not isinstance(record.get(contract), dict):
                    errors.append(f"{contract} must be an object")
            if record.get("contract_complete") and not record.get("handoffs"):
                errors.append("A complete Fragment requires handoffs")

        if collection == "persistence_effects":
            for index, mapping in enumerate(record.get("mappings") or []):
                if not isinstance(mapping, dict) or not mapping.get("target") or not mapping.get("value_source") or not mapping.get("business_use"):
                    errors.append(f"Persistence mapping {index} requires target, value_source, and business_use")

        if collection == "external_interactions":
            for index, param in enumerate(record.get("request_params") or []):
                if not isinstance(param, dict) or not param.get("external_name") or not param.get("internal_origin") or not param.get("business_use"):
                    errors.append(f"Request parameter {index} requires external_name, internal_origin, and business_use")
            for index, param in enumerate(record.get("response_params") or []):
                if not isinstance(param, dict) or not param.get("external_name"):
                    errors.append(f"Response parameter {index} requires external_name")
                elif param.get("consumed", True) and (not param.get("internal_target") or not param.get("business_use")):
                    errors.append(f"Consumed response parameter {index} requires internal_target and business_use")
        return errors

    def ingest(
        self,
        output: dict[str, Any],
        scenario_id: str | None = None,
        work_unit_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(output, dict):
            raise ValueError("Ingestion output must be a JSON object")
        report: dict[str, Any] = {"inserted": {}, "errors": []}
        scenario = output.get("scenario")
        if scenario:
            if not isinstance(scenario, dict):
                report["errors"].append({"collection": "scenario", "errors": ["Scenario must be an object"]})
            else:
                scenario_id = scenario.get("scenario_id") or scenario_id
        active_scenario = scenario if isinstance(scenario, dict) else None
        if active_scenario is None and scenario_id and self.store.has("scenarios", scenario_id):
            active_scenario = self.store.get("scenarios", scenario_id)
        self.active_scenario_sources = set(((active_scenario or {}).get("scope") or {}).get("source_ids") or [])
        batch_ids = {key: set() for key in COLLECTION_RULES}
        batch_ids["scenarios"] = set()
        if scenario and isinstance(scenario, dict) and scenario.get("scenario_id"):
            batch_ids["scenarios"].add(str(scenario["scenario_id"]))

        for collection, rule in COLLECTION_RULES.items():
            records = output.get(collection) or []
            if not isinstance(records, list):
                report["errors"].append({"collection": collection, "errors": ["Collection must be an array"]})
                continue
            for record in records:
                if isinstance(record, dict):
                    self._ensure_id(collection, record)
                    batch_ids[collection].add(str(record[rule["id"]]))

        for evidence in output.get("evidences") or []:
            errors = self.validate_record("evidences", evidence, scenario_id, batch_ids)
            if errors:
                report["errors"].append({"collection": "evidences", "record": evidence, "errors": errors})
            else:
                self.store.upsert("evidences", evidence, work_unit_id)
                self.store.promote_observations(
                    evidence.get("observation_ids") or [], "evidences", evidence["evidence_id"]
                )
                report["inserted"]["evidences"] = report["inserted"].get("evidences", 0) + 1

        if scenario and isinstance(scenario, dict):
            required = ["scenario_id", "name", "business_operation", "business_goal", "trigger", "scope", "expected_outcome"]
            errors = [f"Missing required field: {field}" for field in required if _missing(scenario, field)]
            errors.extend(_observation_reference_errors(self.store, scenario))
            scope = scenario.get("scope") or {}
            source_ids = scope.get("source_ids") if isinstance(scope, dict) else None
            if self.require_registered_sources and not source_ids:
                errors.append("Scenario scope requires source_ids")
            for source_id in source_ids or []:
                errors.extend(self._source_id_errors(source_id, "Scenario scope"))
            if errors:
                report["errors"].append({"collection": "scenario", "record": scenario, "errors": errors})
            else:
                self.store.upsert("scenarios", scenario, work_unit_id)
                self.store.promote_observations(
                    scenario.get("observation_ids") or [], "scenarios", scenario["scenario_id"]
                )
                report["inserted"]["scenario"] = 1

        order = (
            "fragments", "trace_stages", "route_decisions", "field_lineage_steps",
            "persistence_effects", "external_interactions", "gaps", "next_work_units",
        )
        table_collection = {"next_work_units": "work_units"}
        for collection in order:
            for record in output.get(collection) or []:
                errors = self.validate_record(collection, record, scenario_id, batch_ids)
                if errors:
                    report["errors"].append({"collection": collection, "record": record, "errors": errors})
                    continue
                destination = table_collection.get(collection, collection)
                self.store.upsert(destination, record, work_unit_id)
                self.store.promote_observations(
                    record.get("observation_ids") or [], destination, record[COLLECTION_RULES[collection]["id"]]
                )
                report["inserted"][collection] = report["inserted"].get(collection, 0) + 1
        self.store.commit()
        report["scenario_id"] = scenario_id
        return report
