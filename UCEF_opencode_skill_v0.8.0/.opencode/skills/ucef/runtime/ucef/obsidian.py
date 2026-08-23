# ===== obsidian_adapter.py =====

import json
from pathlib import Path
from typing import Any
import yaml

from .mcp import _render


class ObsidianMCPAdapter:
    """Map UCEF logical Obsidian operations to a concrete Obsidian MCP."""

    def __init__(self, tools_config, transport):
        self.transport = transport
        raw = yaml.safe_load(Path(tools_config).read_text(encoding="utf-8")) or {}
        self.tools = raw.get("tools", {})

    @classmethod
    def from_mapping(cls, tools, transport):
        obj = cls.__new__(cls)
        obj.transport = transport
        obj.tools = tools or {}
        return obj

    def supports(self, logical_operation: str) -> bool:
        cfg = self.tools.get(logical_operation)
        tool = cfg.get("tool") if cfg else None
        return bool(tool and "REPLACE_WITH" not in str(tool))

    def call(self, logical_operation: str, **variables: Any):
        cfg = self.tools.get(logical_operation)
        if not cfg:
            raise KeyError(f"No Obsidian MCP mapping for: {logical_operation}")
        tool = cfg.get("tool")
        if not tool or "REPLACE_WITH" in str(tool):
            raise RuntimeError(f"Obsidian MCP operation '{logical_operation}' is not configured")
        arguments = _render(cfg.get("arguments", {}), variables)
        return self.transport.call_tool(tool, arguments)


def extract_text(value: Any) -> str:
    """Best-effort extraction across common MCP result shapes."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(x for x in (extract_text(v) for v in value) if x)
    if isinstance(value, dict):
        # Prefer semantic content keys before flattening metadata.
        for key in ("markdown", "content", "text", "body", "note"):
            if key in value:
                text = extract_text(value[key])
                if text:
                    return text
        return "\n".join(
            f"{k}: {extract_text(v)}" for k, v in value.items()
            if extract_text(v)
        )
    return str(value)


def extract_paths(value: Any) -> list[str]:
    """Best-effort path extraction from search results."""
    found: list[str] = []

    def walk(v):
        if isinstance(v, dict):
            for key in ("path", "file", "filepath", "note_path"):
                item = v.get(key)
                if isinstance(item, str) and item.strip():
                    found.append(item.strip())
            for child in v.values():
                walk(child)
        elif isinstance(v, list):
            for child in v:
                walk(child)

    walk(value)
    # stable unique
    return list(dict.fromkeys(found))


# ===== obsidian_context.py =====

from dataclasses import dataclass
from typing import Any



@dataclass
class ObsidianContextNote:
    path: str
    content: str


class ObsidianContextRetriever:
    """
    Pull only explicitly requested human context from Obsidian.

    Obsidian is not a technical fact source; content is labeled accordingly
    before it is passed to the model.
    """

    def __init__(self, adapter: ObsidianMCPAdapter, runtime_config: dict[str, Any]):
        self.adapter = adapter
        self.runtime_config = runtime_config

    def execute(self, work_unit: dict[str, Any]) -> list[ObsidianContextNote]:
        human = (work_unit.get("human_context") or {}).get("obsidian") or {}
        default_enabled = bool(
            (((self.runtime_config.get("obsidian") or {}).get("context") or {}).get("default_enabled", False))
        )
        enabled = bool(human.get("enabled", default_enabled))
        if not enabled:
            return []

        cfg = ((self.runtime_config.get("obsidian") or {}).get("context") or {})
        max_notes = int(human.get("max_notes", cfg.get("max_notes", 3)))
        max_chars = int(cfg.get("max_chars_per_note", 6000))
        queries = [str(q) for q in human.get("queries") or [] if str(q).strip()]
        if not queries:
            return []

        if not self.adapter.supports("search_notes"):
            return []

        candidate_paths: list[str] = []
        direct_contents: list[ObsidianContextNote] = []

        for query in queries:
            try:
                result = self.adapter.call("search_notes", query=query, limit=max_notes)
            except Exception as exc:
                direct_contents.append(ObsidianContextNote(
                    path=f"search:{query}",
                    content=f"[Obsidian search error: {exc}]"
                ))
                continue
            paths = extract_paths(result)
            if paths:
                candidate_paths.extend(paths)
            else:
                # Some MCPs return note bodies directly from search.
                text = extract_text(result)
                if text:
                    direct_contents.append(ObsidianContextNote(
                        path=f"search:{query}", content=text[:max_chars]
                    ))

        notes: list[ObsidianContextNote] = []
        for path in list(dict.fromkeys(candidate_paths)):
            if len(notes) >= max_notes:
                break
            if not self.adapter.supports("read_note"):
                break
            try:
                result = self.adapter.call("read_note", path=path)
                text = extract_text(result)
            except Exception as exc:
                text = f"[Obsidian read error: {exc}]"
            notes.append(ObsidianContextNote(path=path, content=text[:max_chars]))

        remaining = max(0, max_notes - len(notes))
        notes.extend(direct_contents[:remaining])
        return notes[:max_notes]


# ===== obsidian_exporter.py =====

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


AUTO_START = "<!-- UCEF:AUTO:START -->"
AUTO_END = "<!-- UCEF:AUTO:END -->"


def _safe(value: Any) -> str:
    return str(value if value is not None else "UNKNOWN").replace("|", "\\|").replace("\n", " ")


def _wikilink(path: str, label: str | None = None) -> str:
    no_ext = path[:-3] if path.endswith(".md") else path
    return f"[[{no_ext}|{label}]]" if label else f"[[{no_ext}]]"


def merge_auto_region(existing: str, auto_body: str, title: str) -> str:
    block = f"{AUTO_START}\n{auto_body.rstrip()}\n{AUTO_END}"
    if AUTO_START in existing and AUTO_END in existing:
        before = existing.split(AUTO_START, 1)[0]
        after = existing.split(AUTO_END, 1)[1]
        return before.rstrip() + "\n\n" + block + after
    if existing.strip():
        return existing.rstrip() + "\n\n" + block + "\n"
    return f"# {title}\n\n{block}\n\n## 人工笔记\n\n"


class ObsidianExporter:
    """Render UCEF confirmed facts into compact human-readable Obsidian notes."""

    def __init__(self, store, adapter: ObsidianMCPAdapter, runtime_config: dict[str, Any]):
        self.store = store
        self.adapter = adapter
        self.config = runtime_config

    def sync(self, scenario_id: str, mode: str | None = None) -> dict[str, Any]:
        export_cfg = ((self.config.get("obsidian") or {}).get("export") or {})
        mode = mode or export_cfg.get("mode", "compact")
        root = str(export_cfg.get("root_path", "UCEF")).strip("/")
        preserve = bool(export_cfg.get("preserve_manual", True))
        max_entities = int(export_cfg.get("max_entity_notes", 30))

        if not self.adapter.supports("upsert_note"):
            raise RuntimeError("Obsidian upsert_note mapping is not configured")
        if preserve and not self.adapter.supports("read_note"):
            raise RuntimeError("preserve_manual=true requires Obsidian read_note mapping")

        facts = [x for x in self.store.query(scenario_id=scenario_id, limit=5000) if x.get("fact_status") == "CONFIRMED"]
        unknowns = self.store.open_unknowns(scenario_id, 100)
        conflicts = self.store.open_conflicts(scenario_id, 100)

        scenario_path = f"{root}/Scenarios/{scenario_id}.md"
        notes = {
            scenario_path: self._scenario_body(scenario_id, facts, unknowns, conflicts, mode)
        }

        if mode == "expanded":
            notes.update(self._entity_notes(root, scenario_id, facts, max_entities))

        # Index is generated from all known scenario ids in FactStore.
        scenario_ids = self.store.list_scenarios()
        if scenario_id not in scenario_ids:
            scenario_ids.append(scenario_id)
        index_path = f"{root}/00-Index.md"
        notes[index_path] = self._index_body(root, sorted(set(scenario_ids)))

        written = []
        for path, auto_body in notes.items():
            title = path.rsplit("/", 1)[-1].removesuffix(".md")
            existing = ""
            if preserve:
                try:
                    existing = extract_text(self.adapter.call("read_note", path=path))
                except Exception:
                    existing = ""
            merged = merge_auto_region(existing, auto_body, title) if preserve else (
                f"# {title}\n\n{AUTO_START}\n{auto_body.rstrip()}\n{AUTO_END}\n"
            )
            self.adapter.call("upsert_note", path=path, content=merged)
            written.append(path)

        return {"scenario_id": scenario_id, "mode": mode, "written": written}

    def _index_body(self, root: str, scenario_ids: list[str]) -> str:
        lines = [
            "> UCEF 自动生成的人类阅读索引。技术事实以 SQLite Fact Store + Evidence 为准。",
            "",
            "## Scenarios",
        ]
        for sid in scenario_ids:
            lines.append(f"- {_wikilink(f'{root}/Scenarios/{sid}.md', sid)}")
        lines += [
            "",
            "## 阅读规则",
            "- Obsidian 是知识视图，不是 Confirmed Fact 来源。",
            "- 人工内容请写在 UCEF 自动区之外。",
            "- AI 默认不读取 Vault；只有 Work Unit 显式要求时才读取少量相关笔记。",
        ]
        return "\n".join(lines)

    def _scenario_body(self, scenario_id, facts, unknowns, conflicts, mode):
        groups = defaultdict(list)
        for fact in facts:
            groups[fact.get("fact_type", "unknown")].append(fact)

        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "> 本页是 UCEF Fact Store 的聚合阅读视图，不是第二份事实数据库。",
            f"> Generated: {now} · View: {mode}",
            "",
            "## 概览",
            f"- Execution Nodes: {len(groups['execution_nodes'])}",
            f"- Execution Edges: {len(groups['execution_edges'])}",
            f"- Decisions: {len(groups['decisions'])}",
            f"- Data Mutations: {len(groups['data_mutations'])}",
            f"- Interactions: {len(groups['interactions'])}",
            f"- Open Unknowns: {len(unknowns)}",
            f"- Open Conflicts: {len(conflicts)}",
        ]

        lines += ["", "## Execution"]
        if groups["execution_nodes"]:
            lines += ["| Stage | Kind | Name | Certainty |", "|---|---|---|---|"]
            for x in groups["execution_nodes"][:100]:
                lines.append(f"| {_safe(x.get('stage'))} | {_safe(x.get('kind'))} | {_safe(x.get('name'))} | {_safe(x.get('certainty'))} |")
        else:
            lines.append("暂无 Confirmed Execution。")

        lines += ["", "## Decisions"]
        for x in groups["decisions"][:80]:
            lines.append(
                f"- **{_safe(x.get('decision_id'))}** — `{_safe(x.get('expression'))}` → "
                f"`{_safe(x.get('scenario_outcome'))}`"
            )

        lines += ["", "## Data Evolution"]
        for x in groups["data_mutations"][:100]:
            src = ", ".join(_safe(s) for s in (x.get("sources") or []))
            lines.append(
                f"- `{_safe(x.get('target'))}`: {_safe(x.get('version_before'))} → "
                f"{_safe(x.get('version_after'))} · **{_safe(x.get('operation'))}** · source: {src or 'UNKNOWN'}"
            )

        lines += ["", "## Interactions"]
        if groups["interactions"]:
            lines += ["| Type | Target | Operation | Sync |", "|---|---|---|---|"]
            for x in groups["interactions"][:100]:
                lines.append(
                    f"| {_safe(x.get('interaction_type'))} | {_safe(x.get('target'))} | "
                    f"{_safe(x.get('operation'))} | {_safe(x.get('sync_mode'))} |"
                )

        lines += ["", "## Open Unknowns"]
        for x in unknowns[:50]:
            lines.append(f"- **{_safe(x.get('unknown_id'))}** — {_safe(x.get('question'))}")
        if not unknowns:
            lines.append("无。")

        lines += ["", "## Open Conflicts"]
        for x in conflicts[:50]:
            lines.append(f"- **{_safe(x.get('conflict_id'))}** — {_safe(x.get('description'))}")
        if not conflicts:
            lines.append("无。")

        return "\n".join(lines)

    def _entity_notes(self, root, scenario_id, facts, max_entities):
        notes: dict[str, str] = {}
        fields = defaultdict(list)
        decisions = []
        interactions = []
        for fact in facts:
            t = fact.get("fact_type")
            if t == "data_mutations" and fact.get("target"):
                fields[str(fact["target"])].append(fact)
            elif t == "decisions":
                decisions.append(fact)
            elif t == "interactions":
                interactions.append(fact)

        budget = max_entities
        for field, items in sorted(fields.items(), key=lambda kv: -len(kv[1])):
            if budget <= 0:
                break
            safe_name = field.replace("/", "_")
            path = f"{root}/Fields/{safe_name}.md"
            lines = [f"> Scenario: [[{root}/Scenarios/{scenario_id}|{scenario_id}]]", "", "## 演化"]
            for x in items:
                lines.append(
                    f"- {_safe(x.get('version_before'))} → {_safe(x.get('version_after'))} · "
                    f"{_safe(x.get('operation'))} · `{_safe(x.get('mutation_id'))}`"
                )
            notes[path] = "\n".join(lines)
            budget -= 1

        for x in decisions:
            if budget <= 0:
                break
            did = str(x.get("decision_id"))
            path = f"{root}/Decisions/{did}.md"
            notes[path] = (
                f"> Scenario: [[{root}/Scenarios/{scenario_id}|{scenario_id}]]\n\n"
                f"- Expression: `{_safe(x.get('expression'))}`\n"
                f"- Outcome: `{_safe(x.get('scenario_outcome'))}`\n"
                f"- Certainty: `{_safe(x.get('certainty'))}`\n"
            )
            budget -= 1

        for x in interactions:
            if budget <= 0:
                break
            iid = str(x.get("interaction_id"))
            path = f"{root}/Interactions/{iid}.md"
            notes[path] = (
                f"> Scenario: [[{root}/Scenarios/{scenario_id}|{scenario_id}]]\n\n"
                f"- Type: `{_safe(x.get('interaction_type'))}`\n"
                f"- Target: `{_safe(x.get('target'))}`\n"
                f"- Operation: `{_safe(x.get('operation'))}`\n"
            )
            budget -= 1

        return notes
