from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core import approx_tokens
from .store import FactStore


def _json(value: Any) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def _compact_stage(stage: dict[str, Any]) -> dict[str, Any]:
    return {
        key: stage.get(key)
        for key in (
            "stage_id", "sequence_no", "source_id", "stage_type", "name",
            "business_purpose", "input", "output", "next_handoff",
            "terminal", "terminal_outcome", "status", "fragment_id",
        )
        if stage.get(key) is not None
    }


def _compact_execution_node(node: dict[str, Any]) -> dict[str, Any]:
    return {
        key: node.get(key)
        for key in (
            "execution_node_id", "parent_node_id", "node_type", "source_id", "stage_id",
            "method_definition_id", "sequence_no", "name", "business_purpose", "step_kind",
            "condition", "field_reads", "field_writes", "status",
        )
        if node.get(key) is not None
    }


def _compact_observation(observation: dict[str, Any], max_chars: int) -> dict[str, Any]:
    compact = {
        key: observation.get(key)
        for key in (
            "observation_id", "observation_kind", "source_id", "subject_key",
            "claim", "evidence", "confidence", "tags",
        )
        if observation.get(key) is not None
    }
    serialized = json.dumps(compact, ensure_ascii=False)
    if len(serialized) <= max_chars:
        return compact
    return {
        "observation_id": observation.get("observation_id"),
        "observation_kind": observation.get("observation_kind"),
        "source_id": observation.get("source_id"),
        "subject_key": observation.get("subject_key"),
        "confidence": observation.get("confidence"),
        "context_preview": serialized[:max_chars],
        "preview_truncated": True,
        "recovery": "Use memory-query with this observation_id or subject_key for the full durable record.",
    }


def _compact_checkpoint(checkpoint: dict[str, Any] | None, max_spine: int = 40) -> dict[str, Any] | None:
    if checkpoint is None:
        return None
    spine = checkpoint.get("chain_spine") or []
    if len(spine) > max_spine:
        head_count = min(3, max_spine)
        selected_spine = spine[:head_count] + spine[-(max_spine - head_count):]
    else:
        selected_spine = spine
    return {
        "checkpoint_id": checkpoint.get("checkpoint_id"),
        "sequence_no": checkpoint.get("sequence_no"),
        "status": checkpoint.get("status"),
        "current_focus": checkpoint.get("current_focus"),
        "resume_summary": checkpoint.get("resume_summary"),
        "next_probe": checkpoint.get("next_probe"),
        "unresolved_questions": (checkpoint.get("unresolved_questions") or [])[:30],
        "chain_spine": selected_spine,
        "execution_frontier": (checkpoint.get("execution_frontier") or [])[:40],
        "field_frontier": (checkpoint.get("field_frontier") or [])[:60],
        "omitted_chain_spine_items": max(0, len(spine) - len(selected_spine)),
        "checkpoint_observation_count": len(checkpoint.get("observation_ids") or []),
    }


def _compact_visited_ref(ref: dict[str, Any]) -> dict[str, Any]:
    result = {
        key: ref.get(key)
        for key in ("source_id", "kind", "symbol", "config_key", "outcome")
        if ref.get(key) is not None
    }
    if len(str(result.get("outcome") or "")) > 600:
        result["outcome"] = str(result["outcome"])[:600] + " [preview]"
    return result


class ContextBuilder:
    def __init__(
        self,
        framework_root: str | Path,
        store: FactStore,
        config: dict[str, Any],
        sources: list[dict[str, Any]] | None = None,
    ):
        self.root = Path(framework_root)
        self.store = store
        self.config = config
        self.sources = sources or []

    def _bounded_stages(
        self,
        stages: list[dict[str, Any]],
        work_unit: dict[str, Any],
        limit: int,
    ) -> dict[str, Any]:
        compact = [_compact_stage(stage) for stage in stages]
        if len(compact) <= limit:
            return {"total": len(compact), "omitted": 0, "stages": compact}
        scope = work_unit.get("context_scope") or {}
        anchor_id = scope.get("anchor_stage_id")
        anchor_index = next(
            (index for index, stage in enumerate(compact) if stage.get("stage_id") == anchor_id),
            None,
        )
        if anchor_index is not None:
            before = max(1, limit // 2)
            start = max(0, anchor_index - before)
            selected = compact[start : start + limit]
        else:
            head_count = min(3, limit)
            selected = compact[:head_count] + compact[-(limit - head_count):]
        return {"total": len(compact), "omitted": len(compact) - len(selected), "stages": selected}

    def build(self, scenario: dict[str, Any], work_unit: dict[str, Any]) -> str:
        cfg = self.config.get("context") or {}
        total = int(cfg.get("max_total_tokens", 90000))
        reserved = int(cfg.get("reserved_output_tokens", 16000))
        input_budget = max(8000, total - reserved)
        max_observations = int(cfg.get("max_pending_observations", 60))
        max_observation_preview = int(cfg.get("max_chars_per_observation_preview", 2000))
        max_stages = int(cfg.get("max_stage_records", 16))
        sections: list[str] = []
        used = 0
        omitted_sections: list[str] = []

        def add(title: str, body: str, required: bool = False) -> None:
            nonlocal used
            section = f"\n## {title}\n\n{body}\n"
            cost = approx_tokens(section)
            if required or used + cost <= input_budget:
                sections.append(section)
                used += cost
            else:
                omitted_sections.append(title)

        header = (
            "# UCEF RESUMABLE WORK UNIT CONTEXT\n\n"
            "> Chat history is not durable analysis memory. Resume from the latest Checkpoint and "
            "persist every bounded probe as Observations before retrieving another symbol or configuration.\n"
        )
        sections.append(header)
        used += approx_tokens(header)

        work_unit_id = str(work_unit.get("work_unit_id") or "")
        if not work_unit_id:
            raise ValueError("Work Unit requires work_unit_id")
        memory = self.store.work_unit_memory(work_unit_id, max_observations)
        memory["latest_checkpoint"] = _compact_checkpoint(memory.get("latest_checkpoint"))
        memory["visited_refs"] = [
            _compact_visited_ref(ref) for ref in memory.get("visited_refs") or []
        ]
        memory["pending_observations"] = [
            _compact_observation(observation, max_observation_preview)
            for observation in memory["pending_observations"]
        ]
        memory["memory_query_hint"] = (
            "Use `ucef.py --workspace <workspace> memory-query --work-unit "
            f"{work_unit_id} --status PENDING --subject <symbol-or-field>` when omitted_pending_observations > 0."
        )
        add("DURABLE RESUME STATE — READ FIRST", _json(memory), required=True)
        add("ACTIVE SCENARIO", _json(scenario), required=True)
        add("ACTIVE WORK UNIT", _json(work_unit), required=True)

        requested_source_ids = set((scenario.get("scope") or {}).get("source_ids") or [])
        requested_source_ids.update(work_unit.get("source_ids") or [])
        for entry_ref in work_unit.get("entry_refs") or []:
            if isinstance(entry_ref, dict) and entry_ref.get("source_id"):
                requested_source_ids.add(str(entry_ref["source_id"]))
        active_sources = [
            source for source in self.sources
            if not requested_source_ids or source.get("source_id") in requested_source_ids
        ]
        add("REGISTERED READ-ONLY JAVA SOURCES", _json(active_sources), required=True)

        for title, filename in (
            ("ANTI-LOSS CHECKPOINT CONTRACT", "../references/CHECKPOINT_CONTRACT.md"),
            ("RULES", "UCEF_RULES.md"),
            ("FINAL OUTPUT CONTRACT", "../references/OUTPUT_CONTRACT.md"),
        ):
            path = (self.root / filename).resolve()
            if path.exists():
                add(title, path.read_text(encoding="utf-8"))

        scenario_id = scenario["scenario_id"]
        try:
            dossier = self.store.scenario_dossier(scenario_id)
        except KeyError:
            dossier = {"trace_stages": [], "gaps": []}
        existing = self._bounded_stages(dossier.get("trace_stages", []), work_unit, max_stages)
        max_nodes = int(cfg.get("max_execution_nodes", 60))
        nodes = dossier.get("execution_nodes", [])
        existing["execution_tree"] = {
            "total": len(nodes),
            "omitted": max(0, len(nodes) - max_nodes),
            "nodes": [_compact_execution_node(node) for node in nodes[:max_nodes]],
        }
        max_fields = int(cfg.get("max_field_inventory", 80))
        inventory = dossier.get("field_inventory", [])
        existing["field_inventory"] = {
            "total": len(inventory),
            "omitted": max(0, len(inventory) - max_fields),
            "items": inventory[:max_fields],
        }
        existing["open_gaps"] = [
            gap for gap in dossier.get("gaps", []) if gap.get("status", "OPEN") == "OPEN"
        ][: int(cfg.get("max_gap_records", 20))]
        add("COMPACT SCENARIO ASSEMBLY", _json(existing))

        reuse_cfg = work_unit.get("reuse") or {}
        candidates: list[dict[str, Any]] = []
        for logical_key in reuse_cfg.get("logical_keys") or []:
            candidates.extend(self.store.find_fragments(
                str(logical_key),
                reuse_cfg.get("repository"),
                None if reuse_cfg.get("code_hash") in {None, "", "UNKNOWN"} else reuse_cfg.get("code_hash"),
                None if reuse_cfg.get("binding_hash") in {None, "", "UNKNOWN"} else reuse_cfg.get("binding_hash"),
                reuse_cfg.get("source_id"),
            ))
        method_candidates: list[dict[str, Any]] = []
        for symbol in reuse_cfg.get("method_symbols") or []:
            method_candidates.extend(self.store.find_method_definitions(
                str(reuse_cfg.get("source_id") or ""),
                str(symbol),
                None if reuse_cfg.get("code_hash") in {None, "", "UNKNOWN"} else reuse_cfg.get("code_hash"),
            ))
        add(
            "REUSE CANDIDATES",
            _json({
                "behavior_fragments": candidates[: int(cfg.get("max_fragment_records", 20))],
                "method_definitions": method_candidates[: int(cfg.get("max_method_records", 30))],
            }),
        )

        if omitted_sections:
            sections.append(
                "\n## CONTEXT BUDGET NOTICE\n\n"
                + _json({
                    "omitted_sections": omitted_sections,
                    "reason": "Section omitted as a whole; no durable record was truncated.",
                    "recovery": "Query the SQLite-backed ledger or rebuild a narrower context pack.",
                })
                + "\n"
            )
        return "\n".join(sections)
