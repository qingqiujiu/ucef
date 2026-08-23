from __future__ import annotations

from typing import Any

from .store import FactStore


def compare_scenarios(store: FactStore, left_id: str, right_id: str) -> dict[str, Any]:
    left = store.scenario_dossier(left_id)
    right = store.scenario_dossier(right_id)

    def stage_key(stage: dict[str, Any]) -> str:
        return str(stage.get("stage_key") or stage.get("fragment_id") or stage.get("name") or stage.get("stage_id"))

    left_stages = {stage_key(x): x for x in left["trace_stages"]}
    right_stages = {stage_key(x): x for x in right["trace_stages"]}
    ordered_keys = []
    for item in left["trace_stages"] + right["trace_stages"]:
        key = stage_key(item)
        if key not in ordered_keys:
            ordered_keys.append(key)
    stage_rows = [{"key": key, "left": left_stages.get(key), "right": right_stages.get(key)} for key in ordered_keys]
    first_divergence = next((row for row in stage_rows if not row["left"] or not row["right"] or row["left"].get("output") != row["right"].get("output") or row["left"].get("why_current") != row["right"].get("why_current")), None)

    def by_key(items: list[dict[str, Any]], *keys: str) -> dict[str, dict[str, Any]]:
        result = {}
        for item in items:
            key = "|".join(str(item.get(x) or "") for x in keys)
            result[key] = item
        return result

    def aligned(collection: str, keys: tuple[str, ...]) -> list[dict[str, Any]]:
        a = by_key(left[collection], *keys)
        b = by_key(right[collection], *keys)
        return [{"key": key, "left": a.get(key), "right": b.get(key)} for key in sorted(set(a) | set(b))]

    return {
        "left": left["scenario"],
        "right": right["scenario"],
        "first_divergence": first_divergence,
        "stages": stage_rows,
        "decisions": aligned("route_decisions", ("question",)),
        "fields": aligned("field_lineage_steps", ("canonical_field", "sequence_no")),
        "persistence": aligned("persistence_effects", ("store", "operation")),
        "external_interactions": aligned("external_interactions", ("target_system", "operation")),
    }
