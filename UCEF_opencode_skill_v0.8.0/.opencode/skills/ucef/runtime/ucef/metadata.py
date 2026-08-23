from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value)).strip("_") or "UNKNOWN"


def _read(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(text) or {}
    return json.loads(text)


class MetadataImporter:
    """Import system/module/database metadata without mixing it into AI facts.

    Supported top-level collections:
      systems, modules, tables, relations, assignments

    Tables may contain nested `columns` and `indexes` arrays.
    """

    def __init__(self, store):
        self.store = store

    def import_file(self, path: str | Path, source_type: str = "DB_METADATA") -> dict[str, Any]:
        p = Path(path)
        return self.import_payload(_read(p), source_type=source_type, source_ref=str(p))

    def import_payload(self, payload: dict[str, Any], source_type="DB_METADATA", source_ref=None):
        counts: dict[str, int] = {}
        keys: list[str] = []

        def put(kind: str, eid: str, obj: dict[str, Any], parent_key=None):
            key = self.store.upsert_catalog_entity(kind, eid, obj, parent_key, source_type, source_ref)
            counts[kind] = counts.get(kind, 0) + 1
            keys.append(key)
            return key

        for sys in payload.get("systems") or []:
            sid = str(sys.get("system_id") or sys.get("id") or f"SYS-{_slug(sys.get('name','system'))}")
            obj = dict(sys); obj["system_id"] = sid
            put("system", sid, obj)

        for mod in payload.get("modules") or []:
            mid = str(mod.get("module_id") or mod.get("id") or f"MOD-{_slug(mod.get('name','module'))}")
            sid = str(mod.get("system_id") or "")
            obj = dict(mod); obj["module_id"] = mid
            parent = f"system:{sid}" if sid else None
            put("module", mid, obj, parent)

        for table in payload.get("tables") or []:
            schema = str(table.get("schema") or table.get("database_schema") or "")
            name = str(table.get("name") or table.get("table_name") or "UNKNOWN_TABLE")
            tid = str(table.get("table_id") or table.get("id") or f"TABLE-{_slug((schema + '.') if schema else '')}{_slug(name)}")
            obj = dict(table)
            cols = obj.pop("columns", []) or []
            idxs = obj.pop("indexes", []) or []
            obj.update({"table_id": tid, "name": name, "schema": schema})
            put("table", tid, obj, f"module:{obj['module_id']}" if obj.get("module_id") else (f"system:{obj['system_id']}" if obj.get("system_id") else None))

            for pos, col in enumerate(cols, start=1):
                cname = str(col.get("name") or col.get("column_name") or f"column_{pos}")
                cid = str(col.get("column_id") or col.get("id") or f"{tid}.{_slug(cname)}")
                cobj = dict(col)
                cobj.update({"column_id": cid, "table_id": tid, "table_name": name, "position": col.get("position", pos)})
                put("column", cid, cobj, f"table:{tid}")

            for idx in idxs:
                iname = str(idx.get("name") or idx.get("index_name") or "INDEX")
                iid = str(idx.get("index_id") or idx.get("id") or f"{tid}.{_slug(iname)}")
                iobj = dict(idx)
                iobj.update({"index_id": iid, "table_id": tid, "table_name": name, "name": iname})
                put("index", iid, iobj, f"table:{tid}")

        for rel in payload.get("relations") or []:
            rid = str(rel.get("relation_id") or rel.get("id") or f"REL-{_slug(rel.get('from',''))}-{_slug(rel.get('to',''))}-{_slug(rel.get('kind','RELATED'))}")
            obj = dict(rel); obj["relation_id"] = rid
            put("relation", rid, obj)

        for assn in payload.get("assignments") or []:
            target = str(assn.get("entity_key") or assn.get("target") or "")
            if not target:
                continue
            aid = str(assn.get("assignment_id") or f"ASSIGN-{_slug(target)}")
            obj = dict(assn); obj.update({"assignment_id": aid, "entity_key": target})
            put("assignment", aid, obj)

        self.store.commit()
        return {"imported": counts, "total": sum(counts.values()), "entity_keys": keys[:50], "source": source_ref}
