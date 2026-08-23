import json
import shlex
import subprocess
from pathlib import Path
import yaml


class NullTransport:
    def call_tool(self, tool, arguments):
        raise RuntimeError("MCP transport is disabled")


class BridgeCommandTransport:
    def __init__(self, command, timeout_seconds=60):
        self.command = command
        self.timeout_seconds = timeout_seconds

    def call_tool(self, tool, arguments):
        if not self.command.strip():
            raise RuntimeError("mcp.bridge_command is empty")
        payload = json.dumps({"tool": tool, "arguments": arguments}, ensure_ascii=False)
        proc = subprocess.run(
            shlex.split(self.command),
            input=payload,
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"MCP bridge failed: {proc.stderr.strip()}")
        text = proc.stdout.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"content": text}


def _render(value, variables):
    if isinstance(value, str):
        if value.startswith("{") and value.endswith("}") and value.count("{") == 1:
            key = value[1:-1]
            if key in variables:
                return variables[key]
        try:
            return value.format(**variables)
        except KeyError:
            return value
    if isinstance(value, dict):
        return {k: _render(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_render(v, variables) for v in value]
    return value


class IdeaIndexMCPAdapter:
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

    def supports(self, logical_operation):
        cfg = self.tools.get(logical_operation)
        tool = cfg.get("tool") if cfg else None
        return bool(tool and "REPLACE_WITH" not in str(tool))

    def call(self, logical_operation, **variables):
        cfg = self.tools.get(logical_operation)
        if not cfg:
            raise KeyError(f"No MCP mapping for: {logical_operation}")
        tool = cfg.get("tool")
        if not tool or "REPLACE_WITH" in str(tool):
            raise RuntimeError(f"MCP operation '{logical_operation}' is not configured")
        arguments = _render(cfg.get("arguments", {}), variables)
        return self.transport.call_tool(tool, arguments)


# ===== retrieval =====
import json


class RetrievalItem:
    def __init__(self, logical_operation, query, result, depth=0):
        self.logical_operation = logical_operation
        self.query = query
        self.result = result
        self.depth = depth

    def render(self, max_chars=12000):
        raw = json.dumps(self.result, ensure_ascii=False, indent=2, default=str)
        if len(raw) > max_chars:
            raw = raw[:max_chars] + "\n...[TRUNCATED]"
        return f"### MCP {self.logical_operation}: `{self.query}`\n\n```json\n{raw}\n```\n"


class RetrievalStrategy:
    def __init__(self, adapter):
        self.adapter = adapter

    def execute(self, work_unit):
        hints = work_unit.get("retrieval_hints") or {}
        limit = int(hints.get("max_results_per_query", 20))
        items = []

        symbols = []
        for entry in work_unit.get("entry_refs") or []:
            if isinstance(entry, str):
                symbols.append(entry)
            elif isinstance(entry, dict) and entry.get("symbol"):
                symbols.append(str(entry["symbol"]))
        symbols += [str(x) for x in hints.get("symbols") or []]
        symbols = list(dict.fromkeys(symbols))

        operations = [
            ("definition", True),
            ("implementations", bool(hints.get("include_implementations", True))),
            ("references", bool(hints.get("include_references", True))),
            ("callers", bool(hints.get("include_callers", True))),
            ("callees", bool(hints.get("include_callees", True))),
        ]

        for symbol in symbols:
            for op, enabled in operations:
                if enabled and self.adapter.supports(op):
                    try:
                        result = self.adapter.call(op, symbol=symbol, query=symbol, limit=limit)
                    except Exception as exc:
                        result = {"error": str(exc)}
                    items.append(RetrievalItem(op, symbol, result))

        for field in hints.get("fields") or []:
            if self.adapter.supports("references"):
                try:
                    result = self.adapter.call("references", symbol=str(field), query=str(field), limit=limit)
                except Exception as exc:
                    result = {"error": str(exc)}
                items.append(RetrievalItem("references", str(field), result))

        for query in list(hints.get("config_keys") or []) + list(hints.get("text_queries") or []):
            op = "text_search" if self.adapter.supports("text_search") else "symbol_search"
            if self.adapter.supports(op):
                try:
                    result = self.adapter.call(op, query=str(query), symbol=str(query), limit=limit)
                except Exception as exc:
                    result = {"error": str(exc)}
                items.append(RetrievalItem(op, str(query), result))

        return items
