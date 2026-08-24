from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import new_id, validate_task_capsule
from .store import FactStore


COLLECTION_RULES: dict[str, dict[str, Any]] = {
    "evidences": {"id": "evidence_id", "prefix": "EV", "required": ["evidence_kind", "source", "observation"]},
    "fragments": {"id": "fragment_id", "prefix": "FRAG", "required": ["logical_key", "name", "business_purpose", "entry_contract", "exit_contract", "status", "evidence_ids"]},
    "method_definitions": {"id": "method_definition_id", "prefix": "MDEF", "required": ["source_id", "symbol", "module", "class_name", "method_name", "signature", "file", "code_hash", "input_contract", "output_contract", "status", "evidence_ids"]},
    "trace_stages": {"id": "stage_id", "prefix": "STAGE", "required": ["scenario_id", "sequence_no", "name", "business_purpose", "input", "processing", "output", "status"]},
    "implementation_slices": {"id": "slice_id", "prefix": "SLICE", "required": ["scenario_id", "stage_id", "source_id", "sequence_no", "name", "business_purpose", "focus_mode", "method_path", "internal_steps", "semantic_closure", "closure_status", "status", "evidence_ids"]},
    "coverage_gates": {"id": "gate_id", "prefix": "GATE", "required": ["scenario_id", "gate_type", "priority", "question", "status"]},
    "execution_nodes": {"id": "execution_node_id", "prefix": "NODE", "required": ["scenario_id", "source_id", "node_type", "sequence_no", "name", "business_purpose", "status"]},
    "field_inventory": {"id": "field_id", "prefix": "FIELD", "required": ["scenario_id", "canonical_field", "priority", "tracking_status", "business_use", "evidence_ids"]},
    "route_decisions": {"id": "decision_id", "prefix": "DEC", "required": ["scenario_id", "question", "inputs", "current_outcome", "reason", "evidence_ids"]},
    "field_lineage_steps": {"id": "lineage_step_id", "prefix": "FLD", "required": ["scenario_id", "canonical_field", "sequence_no", "lineage_role", "operation", "source", "target", "business_use", "evidence_ids"]},
    "persistence_effects": {"id": "effect_id", "prefix": "DB", "required": ["scenario_id", "store", "operation", "mappings", "business_effect", "evidence_ids"]},
    "external_interactions": {"id": "interaction_id", "prefix": "EXT", "required": ["scenario_id", "target_system", "operation", "business_purpose", "request_params", "response_params", "evidence_ids"]},
    "gaps": {"id": "gap_id", "prefix": "GAP", "required": ["scenario_id", "category", "severity", "question"]},
    "next_work_units": {"id": "work_unit_id", "prefix": "WU", "required": ["scenario_id", "work_type", "objective"]},
}

EVIDENCE_COLLECTIONS = {
    "fragments", "method_definitions", "implementation_slices", "execution_nodes", "field_inventory",
    "route_decisions", "field_lineage_steps",
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

        if collection == "method_definitions":
            errors.extend(self._source_id_errors(record.get("source_id"), "Method Definition"))

        if collection in {
            "trace_stages", "implementation_slices", "execution_nodes", "route_decisions", "field_lineage_steps",
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
        method_definition_id = record.get("method_definition_id")
        if method_definition_id and method_definition_id not in batch_ids["method_definitions"] and not self.store.has("method_definitions", method_definition_id):
            errors.append(f"Missing MethodDefinition reference: {method_definition_id}")
        parent_node_id = record.get("parent_node_id")
        if parent_node_id:
            if parent_node_id == record.get("execution_node_id"):
                errors.append("ExecutionNode cannot be its own parent")
            elif parent_node_id not in batch_ids["execution_nodes"] and not self.store.has("execution_nodes", parent_node_id):
                errors.append(f"Missing parent ExecutionNode reference: {parent_node_id}")
        execution_node_id = record.get("execution_node_id")
        if collection != "execution_nodes" and execution_node_id and execution_node_id not in batch_ids["execution_nodes"] and not self.store.has("execution_nodes", execution_node_id):
            errors.append(f"Missing ExecutionNode reference: {execution_node_id}")

        if collection == "trace_stages":
            if not record.get("terminal") and _missing(record, "next_handoff"):
                errors.append("Non-terminal TraceStage requires next_handoff")
            if not record.get("evidence_ids") and not record.get("fragment_id"):
                errors.append("TraceStage requires evidence_ids or a reusable fragment_id")

        if collection == "method_definitions":
            for contract in ("input_contract", "output_contract"):
                if not isinstance(record.get(contract), dict):
                    errors.append(f"{contract} must be an object")

        if collection == "execution_nodes":
            node_type = record.get("node_type")
            if node_type == "MODULE" and not record.get("module"):
                errors.append("MODULE ExecutionNode requires module")
            if node_type == "METHOD_INVOCATION":
                for field in ("method_definition_id", "input", "output"):
                    if _missing(record, field):
                        errors.append(f"METHOD_INVOCATION requires {field}")
            if node_type == "STEP":
                if not parent_node_id:
                    errors.append("STEP ExecutionNode requires parent_node_id")
                for field in ("step_kind", "processing"):
                    if _missing(record, field):
                        errors.append(f"STEP ExecutionNode requires {field}")
                for field in ("field_reads", "field_writes"):
                    if field not in record or not isinstance(record.get(field), list):
                        errors.append(f"STEP ExecutionNode requires explicit {field} array")
            if node_type in {"REFERENCE", "RECURSION"} and not record.get("reference_node_id"):
                errors.append(f"{node_type} ExecutionNode requires reference_node_id")
            if node_type in {"METHOD_INVOCATION", "STEP", "BRANCH", "LOOP", "ASYNC_HANDOFF"} and not record.get("evidence_ids"):
                errors.append(f"{node_type} ExecutionNode requires evidence_ids")

        if collection == "implementation_slices":
            for field in ("method_path", "internal_steps", "technical_bridges"):
                if field not in record or not isinstance(record.get(field), list):
                    errors.append(f"ImplementationSlice requires explicit {field} array")
            if not record.get("method_path"):
                errors.append("ImplementationSlice requires a non-empty method_path")
            if not record.get("internal_steps"):
                errors.append("ImplementationSlice requires non-empty internal_steps")
            closure = record.get("semantic_closure")
            closure_keys = (
                "input_understood", "decisions_understood", "fields_understood",
                "side_effects_understood", "output_understood", "unknowns_as_gaps",
            )
            if not isinstance(closure, dict):
                errors.append("ImplementationSlice semantic_closure must be an object")
            elif record.get("closure_status") == "COMPLETE":
                for key in closure_keys:
                    if closure.get(key) is not True:
                        errors.append(f"COMPLETE ImplementationSlice requires semantic_closure.{key}=true")
            for execution_id in record.get("execution_node_ids") or []:
                if execution_id not in batch_ids["execution_nodes"] and not self.store.has("execution_nodes", execution_id):
                    errors.append(f"Missing ImplementationSlice ExecutionNode reference: {execution_id}")
            for bridge_index, bridge in enumerate(record.get("technical_bridges") or []):
                if not isinstance(bridge, dict) or not bridge.get("from") or not bridge.get("to") or not bridge.get("reason"):
                    errors.append(f"Technical bridge {bridge_index} requires from, to, and reason")

        if collection == "coverage_gates":
            if record.get("priority") not in {"G0", "G1", "G2", "G3", "G4"}:
                errors.append("CoverageGate priority must be G0, G1, G2, G3, or G4")
            if record.get("status") == "CLOSED" and not record.get("evidence_ids"):
                errors.append("CLOSED CoverageGate requires evidence_ids")
            if record.get("status") == "GAP_ACCEPTED" and not record.get("gap_ids"):
                errors.append("GAP_ACCEPTED CoverageGate requires gap_ids")

        if collection == "field_inventory":
            if record.get("tracking_status") == "EXCLUDED" and not record.get("exclusion_reason"):
                errors.append("EXCLUDED field requires exclusion_reason")
            if record.get("tracking_status") == "TRACKED" and record.get("priority") in {"P0", "P1"} and not record.get("expected_sinks"):
                errors.append("Tracked P0/P1 field requires expected_sinks")

        if collection == "field_lineage_steps":
            if not execution_node_id:
                errors.append("FieldLineageStep requires execution_node_id")
            previous_step_ids = record.get("previous_step_ids")
            if record.get("lineage_role") == "ORIGIN":
                if previous_step_ids not in (None, []):
                    errors.append("ORIGIN FieldLineageStep cannot have previous_step_ids")
            elif not previous_step_ids:
                errors.append("Non-origin FieldLineageStep requires previous_step_ids")
            else:
                for previous_id in previous_step_ids:
                    if previous_id not in batch_ids["field_lineage_steps"] and not self.store.has("field_lineage_steps", previous_id):
                        errors.append(f"Missing previous FieldLineageStep reference: {previous_id}")

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

        if collection == "next_work_units" and record.get("protocol_version") == "0.9.6":
            errors.extend(f"v0.9.6 WorkUnit: {error}" for error in validate_task_capsule(record))
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
            "method_definitions", "fragments", "trace_stages", "coverage_gates",
            "execution_nodes", "implementation_slices", "field_inventory",
            "route_decisions", "field_lineage_steps",
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
