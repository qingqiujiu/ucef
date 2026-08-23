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


def _compact_method_definition(method: dict[str, Any]) -> dict[str, Any]:
    return {
        key: method.get(key)
        for key in (
            "method_definition_id", "source_id", "symbol", "module", "signature",
            "code_hash", "input_contract", "output_contract", "throws", "status",
        )
        if method.get(key) is not None
    }


def _compact_field_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "field_id", "canonical_field", "priority", "tracking_status",
            "entry_locations", "expected_sinks", "business_use", "exclusion_reason", "status",
        )
        if item.get(key) is not None
    }


def _prioritize_observations(
    observations: list[dict[str, Any]],
    active_terms: set[str],
    limit: int,
) -> list[dict[str, Any]]:
    if len(observations) <= limit:
        return observations
    lowered_terms = {term.lower() for term in active_terms if term}

    def score(item: dict[str, Any]) -> int:
        searchable = " ".join(str(item.get(key) or "") for key in ("subject_key", "claim", "observation_kind", "source_id")).lower()
        return sum(1 for term in lowered_terms if term in searchable)

    ranked = sorted(enumerate(observations), key=lambda pair: (-score(pair[1]), pair[0]))
    selected_indexes = sorted(index for index, _ in ranked[:limit])
    return [observations[index] for index in selected_indexes]


def _markdown_section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return ""
    next_heading = text.find("\n## ", start + len(marker))
    return text[start:] if next_heading < 0 else text[start:next_heading]


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

    def _execution_neighborhood(
        self,
        dossier: dict[str, Any],
        work_unit: dict[str, Any],
        latest_checkpoint: dict[str, Any] | None,
        limit: int,
    ) -> dict[str, Any]:
        nodes = dossier.get("execution_nodes") or []
        node_by_id = {str(node.get("execution_node_id")): node for node in nodes}
        children: dict[str, list[str]] = {}
        for node in nodes:
            parent = node.get("parent_node_id")
            if parent:
                children.setdefault(str(parent), []).append(str(node.get("execution_node_id")))
        scope = work_unit.get("context_scope") or {}
        anchor_id = str(scope.get("anchor_execution_node_id") or "")
        anchor_stage_id = str(scope.get("anchor_stage_id") or "")
        if anchor_id not in node_by_id:
            anchor_id = ""
        if not anchor_id and anchor_stage_id:
            anchor_id = next(
                (str(node.get("execution_node_id")) for node in nodes if str(node.get("stage_id") or "") == anchor_stage_id),
                "",
            )
        if not anchor_id:
            focus = (latest_checkpoint or {}).get("current_focus") or {}
            symbol = str(focus.get("symbol") or "").lower()
            if symbol:
                methods = {str(item.get("method_definition_id")): item for item in dossier.get("method_definitions") or []}
                anchor_id = next((
                    str(node.get("execution_node_id"))
                    for node in nodes
                    if symbol in str((methods.get(str(node.get("method_definition_id"))) or {}).get("symbol") or node.get("name") or "").lower()
                ), "")

        selected: list[str] = []

        def add(node_id: str) -> None:
            if node_id in node_by_id and node_id not in selected and len(selected) < limit:
                selected.append(node_id)

        if anchor_id:
            ancestors: list[str] = []
            cursor = anchor_id
            seen: set[str] = set()
            while cursor in node_by_id and cursor not in seen:
                seen.add(cursor)
                ancestors.append(cursor)
                cursor = str(node_by_id[cursor].get("parent_node_id") or "")
            root_to_anchor = list(reversed(ancestors))
            if len(root_to_anchor) > limit:
                root_to_anchor = (
                    [root_to_anchor[0]] + root_to_anchor[-(limit - 1):]
                    if limit > 1 else [anchor_id]
                )
            for node_id in root_to_anchor:
                add(node_id)
            frontier = [anchor_id]
            depth = 0
            while frontier and len(selected) < limit and depth < 2:
                next_frontier: list[str] = []
                for parent in frontier:
                    for child in children.get(parent, []):
                        add(child)
                        next_frontier.append(child)
                frontier = next_frontier
                depth += 1
        else:
            roots = [str(node.get("execution_node_id")) for node in nodes if not node.get("parent_node_id")]
            frontier = roots
            while frontier and len(selected) < limit:
                next_frontier = []
                for node_id in frontier:
                    add(node_id)
                    next_frontier.extend(children.get(node_id, []))
                frontier = next_frontier

        selected_nodes = [node_by_id[node_id] for node_id in selected]
        method_ids = {
            str(node.get("method_definition_id"))
            for node in selected_nodes if node.get("method_definition_id")
        }
        method_definitions = [
            _compact_method_definition(method)
            for method in dossier.get("method_definitions") or []
            if str(method.get("method_definition_id")) in method_ids
        ]
        return {
            "anchor_execution_node_id": anchor_id or None,
            "total_nodes": len(nodes),
            "selected_nodes": len(selected_nodes),
            "omitted_nodes": max(0, len(nodes) - len(selected_nodes)),
            "nodes": [_compact_execution_node(node) for node in selected_nodes],
            "method_definitions": method_definitions,
            "recovery": "Use query --collection execution_nodes --scenario <id> or set context_scope.anchor_execution_node_id to load another neighborhood.",
        }

    def _active_field_context(
        self,
        dossier: dict[str, Any],
        work_unit: dict[str, Any],
        latest_checkpoint: dict[str, Any] | None,
        selected_nodes: list[dict[str, Any]],
        limit: int,
        max_lineage_steps: int,
    ) -> dict[str, Any]:
        inventory = dossier.get("field_inventory") or []
        scope = work_unit.get("context_scope") or {}
        active_order: list[str] = []

        def add_active(value: Any) -> None:
            name = str(value or "")
            if name and name not in active_order:
                active_order.append(name)

        for value in work_unit.get("target_fields") or []:
            add_active(value)
        for value in scope.get("active_fields") or []:
            add_active(value)
        for node in selected_nodes:
            for value in (node.get("field_reads") or []) + (node.get("field_writes") or []):
                add_active(value)
        for item in (latest_checkpoint or {}).get("field_frontier") or []:
            if isinstance(item, dict) and item.get("canonical_field"):
                add_active(item["canonical_field"])

        by_name = {str(item.get("canonical_field")): item for item in inventory}
        selected_names = [name for name in active_order if name in by_name]
        if not selected_names:
            selected_names = [
                str(item.get("canonical_field")) for item in inventory if item.get("priority") == "P0"
            ]
        if len(selected_names) < limit:
            for item in inventory:
                name = str(item.get("canonical_field"))
                if item.get("tracking_status") == "GAP" and name not in selected_names:
                    selected_names.append(name)
                if len(selected_names) >= limit:
                    break
        selected_names = selected_names[:limit]
        selected_set = set(selected_names)
        selected_inventory = [_compact_field_item(by_name[name]) for name in selected_names]
        lineage = [
            step for step in dossier.get("field_lineage_steps") or []
            if str(step.get("canonical_field")) in selected_set
        ]
        lineage = lineage[:max_lineage_steps]
        counts: dict[str, int] = {}
        for item in inventory:
            key = f"{item.get('priority')}:{item.get('tracking_status')}"
            counts[key] = counts.get(key, 0) + 1
        return {
            "requested_fields": active_order,
            "inventory_total": len(inventory),
            "inventory_selected": len(selected_inventory),
            "inventory_omitted": max(0, len(inventory) - len(selected_inventory)),
            "inventory_counts": counts,
            "inventory": selected_inventory,
            "lineage_total_for_selected_fields": len([
                step for step in dossier.get("field_lineage_steps") or []
                if str(step.get("canonical_field")) in selected_set
            ]),
            "lineage_omitted": max(0, len([
                step for step in dossier.get("field_lineage_steps") or []
                if str(step.get("canonical_field")) in selected_set
            ]) - len(lineage)),
            "lineage_steps": lineage,
            "recovery": "Use query --collection field_inventory / field_lineage_steps, or set context_scope.active_fields for another field group.",
        }

    def build(self, scenario: dict[str, Any], work_unit: dict[str, Any]) -> str:
        cfg = self.config.get("context") or {}
        total = int(cfg.get("max_total_tokens", 52000))
        reserved = int(cfg.get("reserved_output_tokens", 16000))
        input_budget = max(8000, total - reserved)
        max_observations = int(cfg.get("max_pending_observations", 24))
        observation_pool = int(cfg.get("observation_priority_pool", max(80, max_observations * 4)))
        max_observation_preview = int(cfg.get("max_chars_per_observation_preview", 2000))
        max_stages = int(cfg.get("max_stage_records", 10))
        max_nodes = int(cfg.get("max_execution_nodes", 24))
        max_fields = int(cfg.get("max_field_inventory", 12))
        max_lineage_steps = int(cfg.get("max_active_lineage_steps", 40))
        phase = str(work_unit.get("phase") or "EXCAVATE").upper()
        work_type = str(work_unit.get("work_type") or "")
        scope = work_unit.get("context_scope") or {}
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
        memory = self.store.work_unit_memory(work_unit_id, observation_pool)
        latest_checkpoint = memory.get("latest_checkpoint")
        active_field_terms = {
            str(value)
            for value in (scope.get("active_fields") or []) + (work_unit.get("target_fields") or [])
            if value
        }
        active_terms = set(active_field_terms)
        for checkpoint_key in ("current_focus", "next_probe"):
            checkpoint_part = (latest_checkpoint or {}).get(checkpoint_key) or {}
            for key in ("symbol", "config_key", "canonical_field"):
                if checkpoint_part.get(key):
                    active_terms.add(str(checkpoint_part[key]))
        for key in ("anchor_execution_node_id", "anchor_stage_id"):
            if scope.get(key):
                active_terms.add(str(scope[key]))
        observation_candidates = list(memory.get("pending_observations") or [])
        candidate_ids = {str(item.get("observation_id")) for item in observation_candidates}
        for term in active_terms:
            for item in self.store.list_observations(
                work_unit_id=work_unit_id,
                subject=term,
                promotion_status="PENDING",
                limit=max_observations,
            ):
                observation_id = str(item.get("observation_id"))
                if observation_id not in candidate_ids:
                    candidate_ids.add(observation_id)
                    observation_candidates.append(item)
        prioritized_observations = _prioritize_observations(
            observation_candidates, active_terms, max_observations
        )
        pending_total = int((memory.get("observation_counts") or {}).get("pending_assembly") or 0)
        memory["latest_checkpoint"] = _compact_checkpoint(latest_checkpoint)
        memory["visited_refs"] = [
            _compact_visited_ref(ref) for ref in memory.get("visited_refs") or []
        ]
        memory["pending_observations"] = [
            _compact_observation(observation, max_observation_preview)
            for observation in prioritized_observations
        ]
        memory["omitted_pending_observations"] = max(0, pending_total - len(prioritized_observations))
        memory["observation_selection"] = {
            "loaded_pool": len(observation_candidates),
            "selected": len(prioritized_observations),
            "active_terms": sorted(active_terms),
            "policy": "active-field/focus matches first; recover other facts from durable memory on demand",
        }
        memory["memory_query_hint"] = (
            "Use `ucef.py --workspace <workspace> memory-query --work-unit "
            f"{work_unit_id} --status PENDING --subject <symbol-or-field>` when omitted_pending_observations > 0."
        )
        add("DURABLE RESUME STATE — READ FIRST", _json(memory), required=True)
        add("ACTIVE SCENARIO", _json(scenario), required=True)
        add("ACTIVE WORK UNIT", _json(work_unit), required=True)
        add("CONTEXT LOAD PLAN", _json({
            "phase": phase,
            "work_type": work_type,
            "ucef_context_budget_ceiling": total,
            "reserved_for_reasoning_and_output": reserved,
            "context_pack_input_budget": input_budget,
            "anchor_execution_node_id": scope.get("anchor_execution_node_id"),
            "anchor_stage_id": scope.get("anchor_stage_id"),
            "active_fields": sorted(active_field_terms),
            "observation_priority_terms": sorted(active_terms),
            "policy": "SQLite keeps the complete dossier; this pack loads only the current neighborhood and active field slice.",
        }), required=True)

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
        ):
            path = (self.root / filename).resolve()
            if path.exists():
                add(title, path.read_text(encoding="utf-8"))

        execution_work_types = {
            "ENTRY_AND_OUTCOME", "BUSINESS_STAGE_TRACE", "METHOD_EXECUTION_TRACE",
            "METHOD_STEP_DECOMPOSITION", "FIELD_INVENTORY", "FIELD_LINEAGE",
            "ROUTE_DECISION_ANALYSIS", "PERSISTENCE_TRACE",
            "EXTERNAL_INTERACTION_TRACE", "FRAGMENT_GAP_FILL",
        }
        if work_type in execution_work_types:
            path = (self.root / "../references/EXECUTION_TREE_CONTRACT.md").resolve()
            if path.exists():
                add("METHOD EXECUTION TREE AND FIELD CONTRACT", path.read_text(encoding="utf-8"))

        output_path = (self.root / "../references/OUTPUT_CONTRACT.md").resolve()
        output_text = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
        if phase in {"PROMOTE", "ASSEMBLE", "PUBLISH"} or work_type == "SCENARIO_AUDIT_REPAIR":
            add("FINAL OUTPUT CONTRACT", output_text)
            reader_path = (self.root / "../references/READER_CONTRACT.md").resolve()
            if reader_path.exists():
                add("READER CONTRACT", reader_path.read_text(encoding="utf-8"))
        elif work_type == "PERSISTENCE_TRACE":
            add("PERSISTENCE OUTPUT SLICE", _markdown_section(output_text, "Persistence"))
        elif work_type == "EXTERNAL_INTERACTION_TRACE":
            add("EXTERNAL INTERACTION OUTPUT SLICE", _markdown_section(output_text, "External interaction"))

        scenario_id = scenario["scenario_id"]
        try:
            dossier = self.store.scenario_dossier(scenario_id)
        except KeyError:
            dossier = {
                "trace_stages": [], "execution_nodes": [], "method_definitions": [],
                "field_inventory": [], "field_lineage_steps": [], "gaps": [],
            }
        existing = self._bounded_stages(dossier.get("trace_stages", []), work_unit, max_stages)
        execution_neighborhood = self._execution_neighborhood(
            dossier, work_unit, latest_checkpoint, max_nodes
        )
        existing["execution_neighborhood"] = execution_neighborhood
        existing["active_field_context"] = self._active_field_context(
            dossier,
            work_unit,
            latest_checkpoint,
            execution_neighborhood["nodes"],
            max_fields,
            max_lineage_steps,
        )
        open_gaps = [
            gap for gap in dossier.get("gaps", []) if gap.get("status", "OPEN") == "OPEN"
        ]
        anchor_terms = {str(value).lower() for value in active_terms if value}

        def gap_score(gap: dict[str, Any]) -> int:
            searchable = json.dumps(gap, ensure_ascii=False).lower()
            return (
                sum(2 for term in anchor_terms if term in searchable)
                + (2 if gap.get("execution_node_id") == scope.get("anchor_execution_node_id") else 0)
                + (2 if gap.get("stage_id") == scope.get("anchor_stage_id") else 0)
                + (1 if str(gap.get("impact") or "").upper() == "HIGH" else 0)
            )

        max_gaps = int(cfg.get("max_gap_records", 12))
        prioritized_gaps = sorted(open_gaps, key=gap_score, reverse=True)[:max_gaps]
        existing["open_gaps"] = {
            "total": len(open_gaps),
            "selected": len(prioritized_gaps),
            "omitted": max(0, len(open_gaps) - len(prioritized_gaps)),
            "items": prioritized_gaps,
            "recovery": "Use query --collection gaps --scenario <id> for the full gap ledger.",
        }
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
                "method_definitions": [
                    {
                        "reuse": item.get("reuse"),
                        "method_definition": _compact_method_definition(item.get("method_definition") or {}),
                    }
                    for item in method_candidates[: int(cfg.get("max_method_records", 12))]
                ],
            }),
        )

        if omitted_sections:
            sections.append(
                "\n## CONTEXT BUDGET NOTICE\n\n"
                + _json({
                    "omitted_sections": omitted_sections,
                    "reason": "Section omitted as a whole; no durable record was truncated.",
                    "recovery": "Query the SQLite-backed ledger or rebuild a narrower context pack.",
                    "estimated_loaded_tokens_before_notice": used,
                    "input_budget": input_budget,
                })
                + "\n"
            )
        return "\n".join(sections)
