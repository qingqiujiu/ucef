from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core import canonical_hash
from .store import FactStore


OBSERVATION_KINDS = {
    "CALL_EDGE",
    "ROUTE_RULE",
    "FIELD_FLOW",
    "TRANSFORMATION",
    "PERSISTENCE",
    "EXTERNAL_CALL",
    "CONFIG_VALUE",
    "ERROR_BEHAVIOR",
    "BUSINESS_RULE",
    "TYPE_BINDING",
    "TERMINAL_BEHAVIOR",
    "UNKNOWN",
}

NON_CODE_KINDS = {"CONFIG_VALUE", "UNKNOWN"}
CHECKPOINT_STATUSES = {"ACTIVE", "READY_TO_PROMOTE", "COMPLETE", "BLOCKED"}
SEMANTIC_CHECKPOINT_FIELDS = (
    "current_focus",
    "visited_refs",
    "chain_spine",
    "execution_frontier",
    "field_frontier",
    "unresolved_questions",
    "next_probe",
    "status",
)


def _missing(record: dict[str, Any], field: str) -> bool:
    return field not in record or record[field] is None or record[field] == "" or record[field] == []


def _semantic_checkpoint_hash(checkpoint: dict[str, Any] | None) -> str:
    checkpoint = checkpoint or {}
    return canonical_hash({field: checkpoint.get(field) for field in SEMANTIC_CHECKPOINT_FIELDS})


class CheckpointLedger:
    def __init__(self, store: FactStore, registered_sources: set[str]):
        self.store = store
        self.registered_sources = registered_sources

    def _validate_source_id(self, source_id: Any, scenario_sources: set[str], label: str) -> list[str]:
        errors = []
        if not source_id:
            return [f"{label} requires source_id"]
        if str(source_id) not in self.registered_sources:
            errors.append(f"Unknown source_id in {label}: {source_id}")
        if scenario_sources and str(source_id) not in scenario_sources:
            errors.append(f"source_id is not in active Scenario scope for {label}: {source_id}")
        return errors

    def _validate_observation(self, observation: Any, scenario_sources: set[str]) -> list[str]:
        if not isinstance(observation, dict):
            return ["Observation must be an object"]
        errors = []
        if len(json.dumps(observation, ensure_ascii=False)) > 12000:
            errors.append("Observation is too large; store concise claims and evidence pointers, not source dumps")
        for field in ("observation_kind", "subject_key", "claim", "evidence", "confidence"):
            if _missing(observation, field):
                errors.append(f"Observation missing required field: {field}")
        kind = observation.get("observation_kind")
        if kind and kind not in OBSERVATION_KINDS:
            errors.append(f"Unsupported observation_kind: {kind}")
        source_id = observation.get("source_id")
        if kind not in NON_CODE_KINDS:
            errors.extend(self._validate_source_id(source_id, scenario_sources, "Observation"))
        elif source_id:
            errors.extend(self._validate_source_id(source_id, scenario_sources, "Observation"))

        evidence = observation.get("evidence")
        if source_id and isinstance(evidence, dict):
            file_value = evidence.get("file") or evidence.get("relative_path")
            if file_value and Path(str(file_value)).is_absolute():
                errors.append("Observation evidence file must be relative to the registered source root")
            if kind not in NON_CODE_KINDS and not (file_value or evidence.get("symbol")):
                errors.append("Code Observation evidence requires a relative file or symbol")
        return errors

    def _validate_checkpoint(self, checkpoint: Any, observation_count: int) -> list[str]:
        if not isinstance(checkpoint, dict):
            return ["checkpoint must be an object"]
        errors = []
        if len(json.dumps(checkpoint, ensure_ascii=False)) > 60000:
            errors.append("Checkpoint is too large; keep a compact chain spine and resume state")
        for field in (
            "current_focus", "visited_refs", "chain_spine",
            "unresolved_questions", "resume_summary", "status",
        ):
            if field not in checkpoint or checkpoint[field] is None:
                errors.append(f"Checkpoint missing required field: {field}")
        for field in ("current_focus", "resume_summary", "status"):
            if field in checkpoint and (checkpoint[field] == "" or checkpoint[field] == {}):
                errors.append(f"Checkpoint field must not be empty: {field}")
        if len(str(checkpoint.get("resume_summary") or "")) > 3000:
            errors.append("resume_summary must be concise (3000 characters or fewer)")
        for field in ("current_focus", "next_probe"):
            if len(json.dumps(checkpoint.get(field), ensure_ascii=False)) > 5000:
                errors.append(f"{field} is too large; keep only the resumable decision state")
        status = checkpoint.get("status")
        if status and status not in CHECKPOINT_STATUSES:
            errors.append(f"Unsupported checkpoint status: {status}")
        if status == "ACTIVE" and _missing(checkpoint, "next_probe"):
            errors.append("ACTIVE Checkpoint requires exactly one next_probe")
        next_probe = checkpoint.get("next_probe")
        if status == "ACTIVE" and not isinstance(next_probe, dict):
            errors.append("next_probe must be an object")
        if isinstance(next_probe, list):
            errors.append("next_probe must be one object, not a list")
        if observation_count == 0 and status == "ACTIVE" and not checkpoint.get("no_new_facts_reason"):
            errors.append("An ACTIVE checkpoint without Observations requires no_new_facts_reason")
        return errors

    def capture(self, payload: dict[str, Any], work_unit: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Checkpoint payload must be an object")
        if not isinstance(work_unit, dict):
            raise ValueError("Work Unit must be an object")
        work_unit_id = str(work_unit.get("work_unit_id") or "")
        scenario_id = str(work_unit.get("scenario_id") or "")
        if not work_unit_id or not scenario_id:
            raise ValueError("Work Unit requires work_unit_id and scenario_id")
        if payload.get("work_unit_id") not in {None, "", work_unit_id}:
            raise ValueError("Checkpoint work_unit_id does not match the active Work Unit")
        if payload.get("scenario_id") not in {None, "", scenario_id}:
            raise ValueError("Checkpoint scenario_id does not match the active Work Unit")
        scenario = self.store.get("scenarios", scenario_id)
        if scenario is None:
            raise ValueError("Persist the Scenario before the first checkpoint")
        scenario_sources = set((scenario.get("scope") or {}).get("source_ids") or [])

        work_unit_errors = []
        for source_id in work_unit.get("source_ids") or []:
            work_unit_errors.extend(self._validate_source_id(source_id, scenario_sources, "Work Unit"))
        for entry_ref in work_unit.get("entry_refs") or []:
            if isinstance(entry_ref, dict) and entry_ref.get("source_id"):
                work_unit_errors.extend(
                    self._validate_source_id(entry_ref.get("source_id"), scenario_sources, "Work Unit entry_ref")
                )

        observations = payload.get("observations") or []
        if not isinstance(observations, list):
            raise ValueError("observations must be an array")
        errors = list(work_unit_errors)
        for index, observation in enumerate(observations):
            for error in self._validate_observation(observation, scenario_sources):
                errors.append(f"observations[{index}]: {error}")
        checkpoint = payload.get("checkpoint")
        errors.extend(self._validate_checkpoint(checkpoint, len(observations)))
        if isinstance(checkpoint, dict):
            for label, ref in (
                ("Checkpoint current_focus", checkpoint.get("current_focus")),
                ("Checkpoint next_probe", checkpoint.get("next_probe")),
            ):
                if isinstance(ref, dict) and ref.get("source_id"):
                    errors.extend(self._validate_source_id(ref.get("source_id"), scenario_sources, label))
            for field in ("visited_refs", "chain_spine"):
                for index, ref in enumerate(checkpoint.get(field) or []):
                    if isinstance(ref, dict) and ref.get("source_id"):
                        errors.extend(
                            self._validate_source_id(ref.get("source_id"), scenario_sources, f"Checkpoint {field}[{index}]")
                        )
        if errors:
            return {"errors": errors, "inserted": 0, "deduplicated": 0}

        self.store.upsert("work_units", work_unit)
        try:
            observation_report = self.store.append_observations(observations, work_unit_id, scenario_id)
            latest_checkpoint = self.store.latest_checkpoint(work_unit_id)
            no_state_delta = bool(
                latest_checkpoint
                and not observation_report["inserted"]
                and _semantic_checkpoint_hash(checkpoint) == _semantic_checkpoint_hash(latest_checkpoint)
            )
            if no_state_delta:
                saved_checkpoint = latest_checkpoint
            else:
                saved_checkpoint = self.store.append_checkpoint(
                    checkpoint, work_unit_id, scenario_id, observation_report["all_ids"]
                )
            if saved_checkpoint.get("status") == "COMPLETE":
                pending = self.store.work_unit_memory(work_unit_id, 1)["observation_counts"]["pending_assembly"]
                if pending:
                    self.store.conn.rollback()
                    return {
                        "errors": [
                            f"Cannot COMPLETE Work Unit while {pending} Observations remain pending assembly"
                        ],
                        "inserted": 0,
                        "deduplicated": 0,
                    }
            if saved_checkpoint.get("status") in {"COMPLETE", "BLOCKED"}:
                updated_work_unit = dict(work_unit)
                updated_work_unit["status"] = saved_checkpoint["status"]
                self.store.upsert("work_units", updated_work_unit)
            self.store.commit()
        except Exception:
            self.store.conn.rollback()
            raise
        all_ids = observation_report["all_ids"]
        checkpoint_summary = {
            key: saved_checkpoint.get(key)
            for key in (
                "checkpoint_id", "sequence_no", "status", "current_focus",
                "resume_summary", "next_probe",
            )
        }
        return {
            "errors": [],
            "inserted": len(observation_report["inserted"]),
            "deduplicated": len(observation_report["deduplicated"]),
            "no_state_delta": no_state_delta,
            "observation_ids": all_ids[:20],
            "omitted_observation_ids": max(0, len(all_ids) - 20),
            "checkpoint": checkpoint_summary,
        }
