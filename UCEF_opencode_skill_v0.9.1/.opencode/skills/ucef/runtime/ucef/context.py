from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core import approx_tokens
from .store import FactStore


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

    def build(self, scenario: dict[str, Any], work_unit: dict[str, Any]) -> str:
        cfg = self.config.get("context") or {}
        total = int(cfg.get("max_total_tokens", 90000))
        reserved = int(cfg.get("reserved_output_tokens", 16000))
        input_budget = max(8000, total - reserved)
        parts: list[str] = ["# UCEF WORK UNIT CONTEXT\n"]

        for title, filename in (
            ("RULES", "UCEF_RULES.md"),
            ("OUTPUT CONTRACT", "../references/OUTPUT_CONTRACT.md"),
        ):
            path = (self.root / filename).resolve()
            if path.exists():
                parts.append(f"\n## {title}\n\n{path.read_text(encoding='utf-8')}\n")

        parts.append("\n## ACTIVE SCENARIO\n\n```json\n" + json.dumps(scenario, ensure_ascii=False, indent=2) + "\n```\n")
        parts.append("\n## ACTIVE WORK UNIT\n\n```json\n" + json.dumps(work_unit, ensure_ascii=False, indent=2) + "\n```\n")

        requested_source_ids = set((scenario.get("scope") or {}).get("source_ids") or [])
        requested_source_ids.update(work_unit.get("source_ids") or [])
        for entry_ref in work_unit.get("entry_refs") or []:
            if isinstance(entry_ref, dict) and entry_ref.get("source_id"):
                requested_source_ids.add(str(entry_ref["source_id"]))
        active_sources = [
            source for source in self.sources
            if not requested_source_ids or source.get("source_id") in requested_source_ids
        ]
        parts.append("\n## REGISTERED READ-ONLY JAVA SOURCES\n\n```json\n" + json.dumps(active_sources, ensure_ascii=False, indent=2) + "\n```\n")

        scenario_id = scenario["scenario_id"]
        try:
            dossier = self.store.scenario_dossier(scenario_id)
        except KeyError:
            dossier = {"trace_stages": [], "gaps": []}
        existing = {
            "trace_stages": dossier.get("trace_stages", []),
            "open_gaps": [x for x in dossier.get("gaps", []) if x.get("status", "OPEN") == "OPEN"][: int(cfg.get("max_gap_records", 20))],
        }
        parts.append("\n## CURRENT SCENARIO ASSEMBLY\n\n```json\n" + json.dumps(existing, ensure_ascii=False, indent=2) + "\n```\n")

        reuse_cfg = work_unit.get("reuse") or {}
        logical_keys = reuse_cfg.get("logical_keys") or []
        candidates: list[dict[str, Any]] = []
        for logical_key in logical_keys:
            candidates.extend(self.store.find_fragments(
                str(logical_key),
                reuse_cfg.get("repository"),
                None if reuse_cfg.get("code_hash") in {None, "", "UNKNOWN"} else reuse_cfg.get("code_hash"),
                None if reuse_cfg.get("binding_hash") in {None, "", "UNKNOWN"} else reuse_cfg.get("binding_hash"),
                reuse_cfg.get("source_id"),
            ))
        candidates = candidates[: int(cfg.get("max_fragment_records", 20))]
        parts.append("\n## REUSE CANDIDATES\n\n```json\n" + json.dumps(candidates, ensure_ascii=False, indent=2) + "\n```\n")

        final = "\n".join(parts)
        if approx_tokens(final) > input_budget:
            final = final[: input_budget * 4] + "\n\n[UCEF CONTEXT TRUNCATED AT CONFIGURED BUDGET]\n"
        return final
