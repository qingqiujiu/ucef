from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import load_json, write_json


DEFAULT_CONFIG = "workspace.json"
DEFAULT_SOURCES = "sources.json"
SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class AnalysisWorkspace:
    root: Path
    config_path: Path
    config: dict[str, Any]

    @classmethod
    def open(cls, root: str | Path, config: str | Path = DEFAULT_CONFIG) -> "AnalysisWorkspace":
        workspace_root = Path(root).expanduser().resolve()
        config_path = Path(config).expanduser()
        if not config_path.is_absolute():
            config_path = workspace_root / config_path
        config_path = config_path.resolve()
        if not _is_within(config_path, workspace_root):
            raise ValueError("Workspace config must be inside the UCEF analysis workspace")
        return cls(workspace_root, config_path, load_json(config_path))

    def resolve(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        resolved = path.resolve() if path.is_absolute() else (self.root / path).resolve()
        if not _is_within(resolved, self.root):
            raise ValueError(f"UCEF artifact path must stay inside workspace: {resolved}")
        return resolved

    @property
    def database_path(self) -> Path:
        return self.resolve((self.config.get("database") or {}).get("path", "ucef.db"))

    @property
    def source_registry_path(self) -> Path:
        return self.resolve((self.config.get("sources") or {}).get("registry", DEFAULT_SOURCES))

    def load_sources(self, require_existing: bool = True) -> list[dict[str, Any]]:
        path = self.source_registry_path
        if not path.exists():
            if require_existing:
                raise FileNotFoundError(f"Source registry not found: {path}")
            return []
        payload = load_json(path)
        sources = payload.get("sources")
        if not isinstance(sources, list):
            raise ValueError(f"Source registry must contain a sources array: {path}")
        validated: list[dict[str, Any]] = []
        seen: set[str] = set()
        for source in sources:
            validated.append(self.validate_source(source, seen))
        return validated

    def validate_source(self, source: Any, seen: set[str] | None = None) -> dict[str, Any]:
        if not isinstance(source, dict):
            raise ValueError("Each source registry entry must be an object")
        source_id = str(source.get("source_id") or "")
        if not SOURCE_ID_PATTERN.fullmatch(source_id):
            raise ValueError(f"Invalid source_id: {source_id!r}")
        if seen is not None:
            if source_id in seen:
                raise ValueError(f"Duplicate source_id: {source_id}")
            seen.add(source_id)
        source_path_value = source.get("path")
        if not source_path_value:
            raise ValueError(f"Source {source_id} requires path")
        source_path = Path(str(source_path_value)).expanduser()
        if not source_path.is_absolute():
            raise ValueError(f"Source {source_id} path must be absolute")
        source_path = source_path.resolve()
        if _is_within(self.root, source_path) or _is_within(source_path, self.root):
            raise ValueError(
                f"Source {source_id} and UCEF workspace must be separate directory trees: "
                f"workspace={self.root}, source={source_path}"
            )
        normalized = dict(source)
        normalized["source_id"] = source_id
        normalized["path"] = str(source_path)
        normalized.setdefault("source_type", "JAVA_PROJECT")
        normalized.setdefault("access", "READ_ONLY")
        return normalized

    def source_map(self) -> dict[str, dict[str, Any]]:
        return {source["source_id"]: source for source in self.load_sources()}

    def save_sources(self, sources: list[dict[str, Any]]) -> None:
        seen: set[str] = set()
        normalized = [self.validate_source(source, seen) for source in sources]
        write_json(self.source_registry_path, {"sources": normalized})

    def add_source(
        self,
        source_id: str,
        path: str | Path,
        repository: str | None = None,
        revision: str | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        sources = self.load_sources(require_existing=False)
        if any(source["source_id"] == source_id for source in sources):
            raise ValueError(f"source_id already exists: {source_id}")
        source: dict[str, Any] = {
            "source_id": source_id,
            "source_type": "JAVA_PROJECT",
            "path": str(Path(path).expanduser().resolve()),
            "access": "READ_ONLY",
        }
        if repository:
            source["repository"] = repository
        if revision:
            source["revision"] = revision
        if role:
            source["role"] = role
        source = self.validate_source(source)
        sources.append(source)
        self.save_sources(sources)
        return source

    def source_status(self) -> list[dict[str, Any]]:
        result = []
        for source in self.load_sources():
            path = Path(source["path"])
            item = dict(source)
            item["exists"] = path.is_dir()
            item["workspace_separate"] = not (_is_within(self.root, path) or _is_within(path, self.root))
            result.append(item)
        return result

    def initialize_directories(self) -> None:
        for relative in (
            "scenarios",
            "work_units/pending",
            "work_units/completed",
            "contexts",
            "runs",
            "artifacts/objects",
            "site",
        ):
            self.resolve(relative).mkdir(parents=True, exist_ok=True)

    def summary(self) -> dict[str, Any]:
        return {
            "workspace": str(self.root),
            "config": str(self.config_path),
            "database": str(self.database_path),
            "source_registry": str(self.source_registry_path),
        }
