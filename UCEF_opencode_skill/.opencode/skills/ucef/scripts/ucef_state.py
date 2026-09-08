#!/usr/bin/env python3
"""Minimal state and Obsidian workspace support for UCEF.

The runtime deliberately knows nothing about business entities. It only keeps a
small investigation state, refreshes the managed dashboard, and checks links.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


STATE_DIRECTORY = ".ucef"
STATE_FILENAME = "state.json"
MANAGED_START = "<!-- UCEF:STATE:START -->"
MANAGED_END = "<!-- UCEF:STATE:END -->"
COLLECTIONS = {"questions", "claims", "evidence", "artifacts", "sources"}
QUESTION_STATUSES = {
    "unexplored",
    "exploring",
    "partially_resolved",
    "resolved",
    "blocked",
    "deferred",
}
CLAIM_STATUSES = {
    "hypothesis",
    "supported",
    "uncertain",
    "contradicted",
    "superseded",
}
ARTIFACT_STATUSES = {"planned", "draft", "current", "needs_update", "blocked"}
STATUS_LABELS = {
    "unexplored": "待探索",
    "exploring": "正在探索",
    "partially_resolved": "部分明确",
    "resolved": "已明确",
    "blocked": "受阻",
    "deferred": "暂缓",
}
WIKI_LINK_RE = re.compile(r"!?\[\[([^\]]+)\]\]")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)


class StateError(ValueError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def configure_stdio() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="strict")


def workspace_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if path == Path(path.anchor):
        raise StateError("workspace must not be a filesystem root")
    return path


def state_path(workspace: Path) -> Path:
    return workspace / STATE_DIRECTORY / STATE_FILENAME


def default_state(goal: str, analysis_id: str | None = None) -> dict[str, Any]:
    timestamp = now_iso()
    generated_id = analysis_id or datetime.now().strftime("ANALYSIS-%Y%m%d-%H%M%S")
    return {
        "version": 1,
        "analysis_id": generated_id,
        "goal": goal,
        "created_at": timestamp,
        "updated_at": timestamp,
        "current_focus": [],
        "questions": [],
        "claims": [],
        "evidence": [],
        "artifacts": [],
        "sources": [],
        "checkpoint": {
            "summary": "",
            "current_focus": [],
            "next_actions": [],
            "updated_at": None,
        },
    }


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def save_state(workspace: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now_iso()
    text = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(state_path(workspace), text)


def load_state(workspace: Path) -> dict[str, Any]:
    path = state_path(workspace)
    if not path.exists():
        raise StateError(f"state file does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StateError(f"cannot read UTF-8 state JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise StateError("state JSON root must be an object")
    return value


def read_stdin_json() -> Any:
    body = sys.stdin.read().lstrip("\ufeff").strip()
    if not body:
        raise StateError("JSON payload is required on stdin")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise StateError(f"invalid JSON payload at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def ensure_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise StateError(f"{name} must be an array")
    return value


def validate_item(collection: str, item: dict[str, Any]) -> None:
    item_id = item.get("id")
    if not isinstance(item_id, str) or not item_id.strip():
        raise StateError(f"{collection} item requires a non-empty string id")
    status = item.get("status")
    allowed: set[str] | None = None
    if collection == "questions":
        allowed = QUESTION_STATUSES
    elif collection == "claims":
        allowed = CLAIM_STATUSES
    elif collection == "artifacts":
        allowed = ARTIFACT_STATUSES
    if allowed is not None and status is not None and status not in allowed:
        raise StateError(f"invalid {collection} status {status!r}; expected one of {sorted(allowed)}")


def find_item(items: list[dict[str, Any]], item_id: str) -> tuple[int, dict[str, Any]] | None:
    for index, item in enumerate(items):
        if item.get("id") == item_id:
            return index, item
    return None


def apply_operations(state: dict[str, Any], operations: list[Any]) -> list[str]:
    changed: list[str] = []
    timestamp = now_iso()
    for index, raw in enumerate(operations):
        if not isinstance(raw, dict):
            raise StateError(f"operations[{index}] must be an object")
        operation = raw.get("op")
        if operation == "set":
            field = raw.get("field")
            if field not in {"goal", "current_focus"}:
                raise StateError("set supports only goal and current_focus")
            value = raw.get("value")
            if field == "goal" and not isinstance(value, str):
                raise StateError("goal must be a string")
            if field == "current_focus":
                ensure_list(value, "current_focus")
                if not all(isinstance(item, str) for item in value):
                    raise StateError("current_focus values must be strings")
            state[field] = value
            changed.append(str(field))
            continue

        collection = raw.get("collection")
        if collection not in COLLECTIONS:
            raise StateError(f"operations[{index}].collection must be one of {sorted(COLLECTIONS)}")
        items = ensure_list(state.setdefault(collection, []), collection)

        if operation == "upsert":
            incoming = raw.get("item")
            if not isinstance(incoming, dict):
                raise StateError(f"operations[{index}].item must be an object")
            validate_item(collection, incoming)
            item_id = incoming["id"]
            existing = find_item(items, item_id)
            if existing:
                item_index, old = existing
                merged = {**old, **incoming, "updated_at": timestamp}
                merged.setdefault("created_at", timestamp)
                validate_item(collection, merged)
                items[item_index] = merged
            else:
                created = {**incoming, "created_at": timestamp, "updated_at": timestamp}
                items.append(created)
            changed.append(f"{collection}:{item_id}")
            continue

        if operation == "remove":
            item_id = raw.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise StateError(f"operations[{index}].id is required for remove")
            existing = find_item(items, item_id)
            if existing:
                del items[existing[0]]
                changed.append(f"{collection}:{item_id}")
            continue

        raise StateError(f"unsupported operation {operation!r}")
    return changed


def item_text(item: dict[str, Any]) -> str:
    return str(
        item.get("question")
        or item.get("statement")
        or item.get("subject")
        or item.get("summary")
        or item.get("name")
        or item.get("id")
    )


def item_link(item: dict[str, Any]) -> str:
    reference = item.get("note_ref")
    label = item_text(item)
    if isinstance(reference, str) and reference.strip():
        return f"{reference} — {label}"
    return f"`{item.get('id', '?')}` — {label}"


def render_dashboard(state: dict[str, Any]) -> str:
    questions = [item for item in state.get("questions", []) if isinstance(item, dict)]
    by_status: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in questions:
        by_status[str(item.get("status", "unexplored"))].append(item)

    lines = [
        MANAGED_START,
        "> [!info] UCEF 调查状态",
        f"> 最近更新：{state.get('updated_at') or '尚未记录'}",
        "",
        "## 当前焦点",
        "",
    ]
    focus_ids = state.get("current_focus", [])
    focus_items = [item for item in questions if item.get("id") in focus_ids]
    if focus_items:
        for item in focus_items:
            lines.append(f"- {item_link(item)}")
            understanding = item.get("current_understanding")
            next_action = item.get("next_action")
            if understanding:
                lines.append(f"  - 当前认识：{understanding}")
            if next_action:
                lines.append(f"  - 下一步：{next_action}")
    else:
        lines.append("- 尚未选择当前焦点。")

    for status in (
        "resolved",
        "partially_resolved",
        "exploring",
        "unexplored",
        "blocked",
        "deferred",
    ):
        items = by_status.get(status, [])
        if not items:
            continue
        lines.extend(["", f"## {STATUS_LABELS[status]}", ""])
        for item in items:
            lines.append(f"- {item_link(item)}")

    checkpoint = state.get("checkpoint") or {}
    lines.extend(["", "## 最近检查点", ""])
    summary = checkpoint.get("summary") if isinstance(checkpoint, dict) else None
    lines.append(str(summary) if summary else "尚未记录检查点。")
    actions = checkpoint.get("next_actions", []) if isinstance(checkpoint, dict) else []
    if actions:
        lines.extend(["", "### 下一步", ""])
        lines.extend(f"- {action}" for action in actions)
    lines.extend(["", MANAGED_END])
    return "\n".join(lines)


def refresh_dashboard(workspace: Path, state: dict[str, Any]) -> None:
    path = workspace / "调查工作台.md"
    managed = render_dashboard(state)
    if not path.exists():
        atomic_write_text(path, f"# 调查工作台\n\n{managed}\n")
        return
    existing = path.read_text(encoding="utf-8-sig")
    pattern = re.compile(re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END), re.DOTALL)
    if pattern.search(existing):
        updated = pattern.sub(lambda _: managed, existing, count=1)
    else:
        updated = existing.rstrip() + "\n\n" + managed + "\n"
    atomic_write_text(path, updated)


def initial_notes() -> dict[str, str]:
    return {
        "分析首页.md": """# 分析首页

> [!info] 使用说明
> 从业务结论开始阅读，并通过双链下钻到字段、方法和证据。

## 导航

- [[业务全链路]]
- [[字段生命周期]]
- [[方法明细/方法索引]]
- [[证据库]]
- [[调查工作台]]

## 核心结论

待分析。

## 重要未知

待分析。
""",
        "业务全链路.md": """# 业务全链路

从业务起点解释到业务结果。方法名链接到 `方法明细` 中的稳定块 ID。

## 主链

待分析。

## 关键差异与例外

待分析。
""",
        "字段生命周期.md": """# 字段生命周期

只追踪真正影响业务语义、路径或结果的重要字段。

待分析。
""",
        "证据库.md": """# 证据库

保存关键材料的定位、它支持或削弱的结论，以及必要的短摘要。不要复制大文件全文。

待分析。
""",
        "方法明细/方法索引.md": """# 方法索引

只收录选定业务链路内的方法。每个方法都应有稳定块 ID 和返回业务链路的链接。

待分析。
""",
    }


def command_init(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / STATE_DIRECTORY).mkdir(exist_ok=True)
    (workspace / "方法明细").mkdir(exist_ok=True)
    (workspace / "附件").mkdir(exist_ok=True)

    created: list[str] = []
    kept: list[str] = []
    path = state_path(workspace)
    if path.exists():
        state = load_state(workspace)
        kept.append(str(path))
    else:
        state = default_state(args.goal or "", args.analysis_id)
        save_state(workspace, state)
        created.append(str(path))

    for relative, content in initial_notes().items():
        note = workspace / relative
        if note.exists():
            kept.append(str(note))
        else:
            atomic_write_text(note, content)
            created.append(str(note))
    refresh_dashboard(workspace, state)
    print_json({"status": "ok", "workspace": str(workspace), "created": created, "kept": kept})


def compact_item(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "question",
        "statement",
        "subject",
        "name",
        "status",
        "importance",
        "confidence",
        "current_understanding",
        "next_action",
        "note_ref",
        "updated_at",
    )
    return {key: item[key] for key in keys if key in item}


def command_status(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state = load_state(workspace)
    if args.view == "full":
        print_json(state)
        return

    requested = {value.strip() for value in (args.ids or "").split(",") if value.strip()}
    if requested:
        found = []
        for collection in COLLECTIONS:
            for item in state.get(collection, []):
                if isinstance(item, dict) and item.get("id") in requested:
                    found.append({"collection": collection, **item})
        print_json({"analysis_id": state.get("analysis_id"), "items": found})
        return

    focus = set(state.get("current_focus", []))
    questions = [item for item in state.get("questions", []) if isinstance(item, dict)]
    active = [compact_item(item) for item in questions if item.get("id") in focus]
    open_critical = [
        compact_item(item)
        for item in questions
        if item.get("importance") == "critical"
        and item.get("status") not in {"resolved", "deferred"}
    ]
    recent = []
    for collection in ("questions", "claims", "artifacts"):
        recent.extend(
            {"collection": collection, **compact_item(item)}
            for item in state.get(collection, [])
            if isinstance(item, dict)
        )
    recent.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    print_json(
        {
            "analysis_id": state.get("analysis_id"),
            "goal": state.get("goal"),
            "updated_at": state.get("updated_at"),
            "current_focus": active,
            "open_critical_questions": open_critical,
            "recent_changes": recent[:12],
            "checkpoint": state.get("checkpoint"),
        }
    )


def command_update(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state = load_state(workspace)
    payload = read_stdin_json()
    operations = payload.get("operations") if isinstance(payload, dict) else payload
    operations = ensure_list(operations, "operations")
    changed = apply_operations(state, operations)
    save_state(workspace, state)
    refresh_dashboard(workspace, state)
    print_json({"status": "ok", "changed": changed, "updated_at": state["updated_at"]})


def command_checkpoint(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state = load_state(workspace)
    payload = read_stdin_json()
    if not isinstance(payload, dict):
        raise StateError("checkpoint payload must be an object")
    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise StateError("checkpoint summary is required")
    focus = payload.get("current_focus", state.get("current_focus", []))
    actions = payload.get("next_actions", [])
    ensure_list(focus, "current_focus")
    ensure_list(actions, "next_actions")
    if not all(isinstance(value, str) for value in focus + actions):
        raise StateError("current_focus and next_actions values must be strings")
    state["current_focus"] = focus
    state["checkpoint"] = {
        "summary": summary.strip(),
        "current_focus": focus,
        "next_actions": actions,
        "updated_at": now_iso(),
    }
    save_state(workspace, state)
    refresh_dashboard(workspace, state)
    print_json({"status": "ok", "checkpoint": state["checkpoint"]})


def link_parts(raw: str) -> tuple[str, str | None]:
    target = raw.split("|", 1)[0].strip()
    if "#" in target:
        note, anchor = target.split("#", 1)
        return note.strip(), anchor.strip() or None
    return target, None


def resolve_note(workspace: Path, current: Path, note_name: str, markdown_files: list[Path]) -> Path | None:
    if not note_name:
        return current
    normalized = note_name.replace("/", os.sep).replace("\\", os.sep)
    raw = Path(normalized)
    names = [raw] if raw.suffix else [raw.with_suffix(".md")]
    for name in names:
        for candidate in (workspace / name, current.parent / name):
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
    matches = [path for path in markdown_files if path.stem == raw.stem]
    return matches[0].resolve() if len(matches) == 1 else None


def anchor_exists(path: Path, anchor: str) -> bool:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return False
    if anchor.startswith("^"):
        block_id = re.escape(anchor[1:])
        return re.search(rf"(?<![\w-])\^{block_id}(?![\w-])", text) is not None
    headings = {match.group(1).strip() for match in HEADING_RE.finditer(text)}
    return anchor in headings


def validate_workspace(workspace: Path, state: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    required = {
        "version",
        "analysis_id",
        "goal",
        "current_focus",
        "questions",
        "claims",
        "evidence",
        "artifacts",
        "sources",
        "checkpoint",
    }
    missing = sorted(required - set(state))
    if missing:
        errors.append(f"state.json missing keys: {', '.join(missing)}")

    indexes: dict[str, dict[str, dict[str, Any]]] = {}
    for collection in COLLECTIONS:
        items = state.get(collection, [])
        if not isinstance(items, list):
            errors.append(f"{collection} must be an array")
            continue
        index: dict[str, dict[str, Any]] = {}
        for position, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"{collection}[{position}] must be an object")
                continue
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                errors.append(f"{collection}[{position}] has no string id")
                continue
            if item_id in index:
                errors.append(f"duplicate id in {collection}: {item_id}")
            index[item_id] = item
            try:
                validate_item(collection, item)
            except StateError as exc:
                errors.append(str(exc))
        indexes[collection] = index

    for focus_id in state.get("current_focus", []):
        if focus_id not in indexes.get("questions", {}):
            errors.append(f"current_focus references missing question: {focus_id}")
    for item in indexes.get("questions", {}).values():
        for claim_id in item.get("claim_refs", []):
            if claim_id not in indexes.get("claims", {}):
                warnings.append(f"{item['id']} references missing claim: {claim_id}")
    for item in indexes.get("claims", {}).values():
        for question_id in item.get("question_refs", []):
            if question_id not in indexes.get("questions", {}):
                warnings.append(f"{item['id']} references missing question: {question_id}")
        for evidence_id in item.get("evidence_refs", []):
            if evidence_id not in indexes.get("evidence", {}):
                warnings.append(f"{item['id']} references missing evidence: {evidence_id}")

    expected_notes = ["分析首页.md", "业务全链路.md", "字段生命周期.md", "证据库.md", "调查工作台.md"]
    for relative in expected_notes:
        if not (workspace / relative).exists():
            warnings.append(f"missing default note: {relative}")

    markdown_files = [path.resolve() for path in workspace.rglob("*.md") if STATE_DIRECTORY not in path.parts]
    for note in markdown_files:
        try:
            text = note.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            errors.append(f"cannot read UTF-8 note {note.relative_to(workspace)}: {exc}")
            continue
        for raw in WIKI_LINK_RE.findall(text):
            note_name, anchor = link_parts(raw)
            target = resolve_note(workspace, note, note_name, markdown_files)
            if target is None:
                warnings.append(f"broken Wikilink in {note.relative_to(workspace)}: [[{raw}]]")
                continue
            if anchor and not anchor_exists(target, anchor):
                warnings.append(
                    f"missing anchor in {note.relative_to(workspace)}: [[{raw}]]"
                )

    for collection in COLLECTIONS:
        for item in indexes.get(collection, {}).values():
            reference = item.get("note_ref")
            if not isinstance(reference, str):
                continue
            for raw in WIKI_LINK_RE.findall(reference):
                note_name, anchor = link_parts(raw)
                target = resolve_note(workspace, workspace / "调查工作台.md", note_name, markdown_files)
                if target is None:
                    warnings.append(f"{item['id']} has broken note_ref: {reference}")
                elif anchor and not anchor_exists(target, anchor):
                    warnings.append(f"{item['id']} has missing note_ref anchor: {reference}")

    for source in indexes.get("sources", {}).values():
        source_location = source.get("path")
        if isinstance(source_location, str) and source_location and not Path(source_location).expanduser().exists():
            warnings.append(f"source path is unavailable: {source.get('id')} -> {source_location}")

    return {
        "status": "error" if errors else "ok",
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "markdown_files": len(markdown_files),
    }


def command_validate(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state = load_state(workspace)
    print_json(validate_workspace(workspace, state))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UCEF lightweight state and Obsidian workspace helper")
    parser.add_argument("--workspace", required=True, help="Obsidian analysis directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create the minimal analysis workspace")
    init_parser.add_argument("--goal", default="")
    init_parser.add_argument("--analysis-id")
    init_parser.set_defaults(handler=command_init)

    status_parser = subparsers.add_parser("status", help="Read compact or full state")
    status_parser.add_argument("--view", choices=("summary", "full"), default="summary")
    status_parser.add_argument("--ids", help="Comma-separated IDs to retrieve")
    status_parser.set_defaults(handler=command_status)

    update_parser = subparsers.add_parser("update", help="Apply JSON operations from stdin")
    update_parser.set_defaults(handler=command_update)

    checkpoint_parser = subparsers.add_parser("checkpoint", help="Write a compact recovery checkpoint from stdin")
    checkpoint_parser.set_defaults(handler=command_checkpoint)

    validate_parser = subparsers.add_parser("validate", help="Check state references and Obsidian links")
    validate_parser.set_defaults(handler=command_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.handler(args)
    except StateError as exc:
        print_json({"status": "error", "message": str(exc)})
        return 2
    except OSError as exc:
        print_json({"status": "error", "message": f"filesystem error: {exc}"})
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
