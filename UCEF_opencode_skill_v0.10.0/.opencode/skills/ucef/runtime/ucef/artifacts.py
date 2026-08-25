from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SENSITIVE_KEY = re.compile(
    r"(?:password|passwd|pwd|secret|token|credential|authorization|cookie|private.?key|access.?key|api.?key|client.?secret|connection.?string)",
    re.IGNORECASE,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _redact_json(value: Any, extra_keys: set[str] | None = None) -> tuple[Any, int]:
    extra = {item.lower() for item in (extra_keys or set())}
    redacted = 0

    def walk(item: Any) -> Any:
        nonlocal redacted
        if isinstance(item, dict):
            result: dict[str, Any] = {}
            for key, child in item.items():
                key_text = str(key)
                if SENSITIVE_KEY.search(key_text) or key_text.lower() in extra:
                    result[key_text] = "***REDACTED***"
                    redacted += 1
                else:
                    result[key_text] = walk(child)
            return result
        if isinstance(item, list):
            return [walk(child) for child in item]
        return item

    return walk(value), redacted


class ArtifactStore:
    """Content-addressed, display-safe snapshots kept outside model context."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.root = self.workspace_root / "artifacts"
        self.objects = self.root / "objects"
        self.registry_path = self.root / "index.json"

    def initialize(self) -> None:
        self.objects.mkdir(parents=True, exist_ok=True)
        if not self.registry_path.exists():
            self._write_registry({"format_version": "1", "artifacts": []})

    def _read_registry(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"format_version": "1", "artifacts": []}
        value = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("artifacts"), list):
            raise ValueError(f"Invalid artifact registry: {self.registry_path}")
        return value

    def _write_registry(self, value: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.registry_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.registry_path)

    def add_json(
        self,
        source_path: str | Path,
        *,
        scenario_id: str | None = None,
        source_id: str | None = None,
        environment: str | None = None,
        snapshot_id: str | None = None,
        kind: str = "CONFIG_JSON",
        extra_redact_keys: set[str] | None = None,
    ) -> dict[str, Any]:
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Artifact source does not exist: {source}")
        raw = source.read_bytes()
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Artifact must be UTF-8 JSON: {source}") from exc

        display_value, redacted_count = _redact_json(parsed, extra_redact_keys)
        display_text = json.dumps(display_value, ensure_ascii=False, indent=2) + "\n"
        content_hash = _sha256(raw)
        display_hash = _sha256(display_text.encode("utf-8"))
        artifact_id = f"ART-{content_hash[:12].upper()}"
        relative_object = Path("artifacts") / "objects" / content_hash[:2] / f"{content_hash}.json"
        target = self.workspace_root / relative_object
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_text(encoding="utf-8") != display_text:
            target.write_text(display_text, encoding="utf-8")

        registry = self._read_registry()
        artifacts = registry["artifacts"]
        existing = next((item for item in artifacts if item.get("artifact_id") == artifact_id), None)
        scenario_ids = list(dict.fromkeys(
            [str(item) for item in ((existing or {}).get("scenario_ids") or [])]
            + ([str(scenario_id)] if scenario_id else [])
        ))
        record = {
            "artifact_id": artifact_id,
            "kind": kind,
            "scenario_ids": scenario_ids,
            "source_id": source_id,
            "environment": environment,
            "snapshot_id": snapshot_id,
            "content_type": "application/json",
            "content_hash": content_hash,
            "display_hash": display_hash,
            "storage_path": relative_object.as_posix(),
            "source_path": str(source),
            "size_bytes": len(raw),
            "redaction_status": "REDACTED" if redacted_count else "UNCHANGED",
            "redacted_value_count": redacted_count,
            "captured_at": (existing or {}).get("captured_at") or _now_iso(),
        }
        if existing is None:
            artifacts.append(record)
        else:
            artifacts[artifacts.index(existing)] = record
        artifacts.sort(key=lambda item: (str(item.get("kind")), str(item.get("artifact_id"))))
        self._write_registry(registry)
        return record

    def list_artifacts(self, scenario_id: str | None = None) -> list[dict[str, Any]]:
        artifacts = list(self._read_registry().get("artifacts") or [])
        if scenario_id:
            artifacts = [
                item for item in artifacts
                if scenario_id in {str(value) for value in item.get("scenario_ids") or []}
            ]
        return artifacts

    def read_display_json(self, artifact: dict[str, Any]) -> Any:
        relative = Path(str(artifact.get("storage_path") or ""))
        target = (self.workspace_root / relative).resolve()
        try:
            target.relative_to(self.workspace_root)
        except ValueError as exc:
            raise ValueError(f"Artifact path escapes workspace: {target}") from exc
        return json.loads(target.read_text(encoding="utf-8"))
