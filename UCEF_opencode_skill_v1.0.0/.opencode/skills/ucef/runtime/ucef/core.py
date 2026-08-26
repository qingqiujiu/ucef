from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_ROLE_ALLOWED_OPERATIONS = {
    "SKELETON": {
        "add_observation", "propose_trace_stage", "propose_coverage_gate",
        "propose_candidate_reference", "open_gap",
    },
    "SLICE": {
        "add_observation", "propose_implementation_slice", "propose_method_definition",
        "propose_execution_node", "propose_field_inventory", "propose_field_lineage",
        "propose_route_decision", "propose_persistence_effect",
        "propose_external_interaction", "propose_gate_status", "open_gap",
    },
    "INTEGRATION": {
        "propose_narrative_delta", "propose_gate_status", "open_contradiction_gap",
    },
    "REPAIR": {"propose_patch", "open_gap"},
}

TASK_BUDGET_LIMITS = {
    "max_semantic_probes": 8,
    "max_new_candidates": 5,
    "max_patch_operations": 20,
    "max_repair_attempts": 2,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return data


def write_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def short_hash(value: Any, length: int = 16) -> str:
    return canonical_hash(value)[:length].upper()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "item"


def approx_tokens(text: str, chars_per_token: int = 4) -> int:
    return max(1, len(text) // max(chars_per_token, 1)) if text else 0


def validate_task_capsule(work_unit: dict[str, Any]) -> list[str]:
    if str(work_unit.get("protocol_version") or "") != "0.9.6":
        return []
    errors: list[str] = []
    role = str(work_unit.get("role") or "")
    if role not in TASK_ROLE_ALLOWED_OPERATIONS:
        errors.append("role must be SKELETON, SLICE, INTEGRATION, or REPAIR")
    for field in ("acceptance_tests", "non_goals", "allowed_operations"):
        if not isinstance(work_unit.get(field), list) or not work_unit.get(field):
            errors.append(f"{field} must be a non-empty array")
    if role in {"SLICE", "REPAIR"} and not work_unit.get("closes_gate_ids"):
        errors.append(f"{role} requires closes_gate_ids")
    budgets = work_unit.get("budgets")
    if not isinstance(budgets, dict):
        errors.append("budgets must be an object")
    else:
        for key, maximum in TASK_BUDGET_LIMITS.items():
            value = budgets.get(key)
            if not isinstance(value, int) or value < 0 or value > maximum:
                errors.append(f"budgets.{key} must be an integer between 0 and {maximum}")
    operations = {
        str(value) for value in work_unit.get("allowed_operations") or [] if value
    }
    unexpected = sorted(operations - TASK_ROLE_ALLOWED_OPERATIONS.get(role, set()))
    if unexpected:
        errors.append(f"allowed_operations not allowed for {role or 'missing role'}: {', '.join(unexpected)}")
    return errors
