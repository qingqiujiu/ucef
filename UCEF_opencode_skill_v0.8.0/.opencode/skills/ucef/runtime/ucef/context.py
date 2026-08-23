import json
from pathlib import Path
import yaml
from .core import approx_tokens


class ContextBuilder:
    """
    Build one compact AI workbench.

    Internal UCEF contracts/schemas are intentionally NOT exposed to the model.
    The model sees one minimal rules file + current scenario/work unit + relevant
    facts/code + optional small Obsidian human context.
    """

    def __init__(
        self, framework_root, store, runtime_config,
        retrieval=None, obsidian_context=None
    ):
        self.root = Path(framework_root)
        self.store = store
        self.config = runtime_config
        self.retrieval = retrieval
        self.obsidian_context = obsidian_context

    def build(self, scenario, work_unit):
        scenario_id = scenario["scenario_id"]
        cfg = self.config.get("context") or {}
        max_tokens = int(cfg.get("max_tokens", 60000))
        reserved = int(cfg.get("reserved_output_tokens", 12000))
        chars_per_token = int(cfg.get("approx_chars_per_token", 4))
        input_budget = max(1000, max_tokens - reserved)

        parts = ["# UCEF CONTEXT PACK\n"]

        rules = self.root / "UCEF_RULES.md"
        if rules.exists():
            parts.append("\n## RULES\n\n" + rules.read_text(encoding="utf-8") + "\n")

        parts.append(
            "\n## CURRENT SCENARIO\n\n```yaml\n"
            + yaml.safe_dump(scenario, allow_unicode=True, sort_keys=False)
            + "```\n"
        )
        parts.append(
            "\n## CURRENT WORK UNIT\n\n```yaml\n"
            + yaml.safe_dump(work_unit, allow_unicode=True, sort_keys=False)
            + "```\n"
        )

        needles = collect_needles(work_unit)
        facts = self.store.related_facts(
            scenario_id, needles, int(cfg.get("max_fact_records", 120))
        )
        parts.append(
            "\n## RELATED CONFIRMED FACTS\n\n```json\n"
            + json.dumps(facts, ensure_ascii=False, indent=2)
            + "\n```\n"
        )
        parts.append(
            "\n## OPEN UNKNOWNS\n\n```json\n"
            + json.dumps(
                self.store.open_unknowns(scenario_id, int(cfg.get("max_unknown_records", 30))),
                ensure_ascii=False, indent=2
            )
            + "\n```\n"
        )
        parts.append(
            "\n## OPEN CONFLICTS\n\n```json\n"
            + json.dumps(
                self.store.open_conflicts(scenario_id, int(cfg.get("max_conflict_records", 20))),
                ensure_ascii=False, indent=2
            )
            + "\n```\n"
        )

        if self.retrieval:
            items = self.retrieval.execute(work_unit)[:int(cfg.get("max_retrieval_items", 80))]
            parts.append("\n## IDEA INDEX MCP RETRIEVAL\n")
            for item in items:
                candidate = item.render(int(cfg.get("max_chars_per_retrieval_item", 12000)))
                if approx_tokens("\n".join(parts) + candidate, chars_per_token) > input_budget:
                    parts.append("\n> [UCEF] IDEA retrieval stopped at token budget.\n")
                    break
                parts.append(candidate)


        # Human notes are opt-in, non-authoritative, and lower priority than source retrieval.
        if self.obsidian_context:
            notes = self.obsidian_context.execute(work_unit)
            if notes:
                parts.append(
                    "\n## OPTIONAL HUMAN CONTEXT FROM OBSIDIAN\n\n"
                    "> These notes are navigation/human understanding only. "
                    "Do not treat them as CONFIRMED technical facts without Evidence.\n"
                )
                for note in notes:
                    candidate = f"\n### Obsidian: `{note.path}`\n\n{note.content}\n"
                    if approx_tokens("\n".join(parts) + candidate, chars_per_token) > input_budget:
                        parts.append("\n> [UCEF] Obsidian context stopped at token budget.\n")
                        break
                    parts.append(candidate)

        final = "\n".join(parts)
        if approx_tokens(final, chars_per_token) > input_budget:
            final = final[:input_budget * chars_per_token] + "\n\n[UCEF HARD TRUNCATION]\n"
        return final


def collect_needles(work_unit):
    values = []
    for entry in work_unit.get("entry_refs") or []:
        if isinstance(entry, str):
            values.append(entry)
        elif isinstance(entry, dict):
            values += [str(v) for v in entry.values() if isinstance(v, (str, int, float))]
    hints = work_unit.get("retrieval_hints") or {}
    for key in ("symbols", "fields", "config_keys", "text_queries"):
        values += [str(x) for x in hints.get(key) or []]
    return list(dict.fromkeys(values))
