from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import threading
import webbrowser
from collections import defaultdict
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

SITE_VERSION = "0.8.0"
STAGES = [
    "ENTRY", "ORDER_CREATE", "PAYMENT", "PAYMENT_RESULT", "FULFILLMENT",
    "AFTER_SALES", "CLEARING", "SETTLEMENT", "FINISH"
]
EDITABLE_OVERRIDE_FIELDS = {"display_name", "description", "system_id", "module_id", "order", "hidden", "tags", "business_name"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(obj: Any) -> str:
    return hashlib.sha256(_json(obj).encode("utf-8")).hexdigest()


def _safe(value: str, limit: int = 90) -> str:
    raw = str(value)
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_.-") or "entity"
    return f"{slug[:limit]}--{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:8]}"


def _read_scenarios(workspace: Path) -> dict[str, dict[str, Any]]:
    out = {}
    folder = workspace / "scenarios"
    if not folder.exists():
        return out
    for path in list(folder.glob("*.yaml")) + list(folder.glob("*.yml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        sid = data.get("scenario_id")
        if sid:
            data["_file"] = str(path)
            out[str(sid)] = data
    return out


class OverrideStore:
    def __init__(self, workspace: Path):
        self.path = workspace / "overrides.json"
        self.workspace = workspace

    def load(self):
        if not self.path.exists():
            return {"version": 1, "entities": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            data.setdefault("version", 1); data.setdefault("entities", {})
            return data
        except Exception:
            return {"version": 1, "entities": {}}

    def get(self, entity_key):
        return dict((self.load().get("entities") or {}).get(entity_key) or {})

    def update(self, entity_key: str, patch: dict[str, Any]):
        data = self.load()
        clean = {k: v for k, v in patch.items() if k in EDITABLE_OVERRIDE_FIELDS}
        current = dict((data["entities"].get(entity_key) or {}))
        for k, v in clean.items():
            if v is None or v == "":
                current.pop(k, None)
            else:
                current[k] = v
        current["updated_at"] = _now()
        data["entities"][entity_key] = current
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return current


class IncrementalSiteBuilder:
    def __init__(self, store, runtime_config: dict[str, Any], workspace: Path | str = ".ucef"):
        self.store = store
        self.config = runtime_config
        self.workspace = Path(workspace)
        scfg = runtime_config.get("site") or {}
        output = Path(scfg.get("output", ".ucef/site"))
        if not output.is_absolute():
            base = self.workspace.parent if self.workspace.name == ".ucef" else Path.cwd()
            output = base / output
        self.output = output
        self.title = str(scfg.get("title", "UCEF Business Explorer"))
        self.include_candidate = bool(scfg.get("include_candidate", True))
        self.max_search_text = int(scfg.get("max_search_text", 1800))
        self.overrides = OverrideStore(self.workspace)

    def build(self):
        return self.update(force=True)

    def update(self, force=False):
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / "assets").mkdir(exist_ok=True)
        (self.output / "data" / "entities").mkdir(parents=True, exist_ok=True)
        old = self._load_manifest()
        model = self._compile_model()
        entities = model.pop("entities")
        hashes, files, changed, unchanged = {}, {}, [], []

        for key, payload in entities.items():
            h = _hash(payload); hashes[key] = h
            kind, eid = key.split(":", 1)
            rel = f"data/entities/{kind}-{_safe(eid)}.js"; files[key] = rel
            if force or old.get("entity_hashes", {}).get(key) != h or old.get("file_map", {}).get(key) != rel or not (self.output / rel).exists():
                self._write_entity(rel, key, payload); changed.append(key)
            else:
                unchanged.append(key)

        removed = sorted(set(old.get("entity_hashes", {})) - set(hashes))
        for key in removed:
            rel = old.get("file_map", {}).get(key)
            if rel:
                try: (self.output / rel).unlink()
                except FileNotFoundError: pass

        model.update({"entity_files": files, "site_version": SITE_VERSION, "title": self.title, "generated_at": _now()})
        catalog_hash = _hash({k: v for k, v in model.items() if k != "generated_at"})
        catalog_changed = force or old.get("catalog_hash") != catalog_hash or not (self.output / "data/catalog.js").exists()
        if catalog_changed: self._write_catalog(model)

        shell_changed = force or old.get("site_version") != SITE_VERSION or not (self.output / "index.html").exists()
        if shell_changed: self._write_shell()

        manifest = {
            "site_version": SITE_VERSION, "generated_at": model["generated_at"], "catalog_hash": catalog_hash,
            "entity_hashes": hashes, "file_map": files, "stats": model["stats"]
        }
        (self.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"output": str(self.output), "entry": str(self.output / "index.html"), "entities": len(entities),
                "changed": len(changed), "unchanged": len(unchanged), "removed": len(removed),
                "catalog_changed": catalog_changed, "shell_changed": shell_changed, "changed_entities": changed[:40]}

    def stats(self):
        m = self._load_manifest()
        return {"output": str(self.output), "exists": (self.output / "index.html").exists(),
                "site_version": m.get("site_version"), "generated_at": m.get("generated_at"),
                "entities": len(m.get("entity_hashes") or {}), "stats": m.get("stats") or {}}

    def _load_manifest(self):
        p = self.output / "manifest.json"
        try: return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except Exception: return {}

    def _compile_model(self):
        scenario_defs = _read_scenarios(self.workspace)
        facts = self.store.export_fact_rows()
        evidences = self.store.export_evidence_rows()
        unknowns = self.store.export_unknown_rows()
        conflicts = self.store.export_conflict_rows()
        catalog_rows = self.store.export_catalog_entities()
        overrides = self.overrides.load().get("entities") or {}

        allowed = {"CONFIRMED", "CANDIDATE", "DISCOVERED", "UNKNOWN"} if self.include_candidate else {"CONFIRMED"}
        facts = [x for x in facts if x.get("fact_status") in allowed]
        node_by_id = {str(x.get("node_id")): x for x in facts if x.get("fact_type") == "execution_nodes"}
        by_scenario = defaultdict(list)
        for x in facts: by_scenario[str(x.get("scenario_id") or "UNSCOPED")].append(x)

        cat = defaultdict(list); cat_by_key = {}
        for x in catalog_rows:
            cat[x["entity_type"]].append(x); cat_by_key[x["entity_key"]] = x
        assignments = {}
        for x in cat["assignment"]:
            if x.get("entity_key"): assignments[str(x["entity_key"])] = x

        entities, summaries, search = {}, {}, []

        def ov(key): return dict(overrides.get(key) or {})
        def display(key, original): return ov(key).get("display_name") or ov(key).get("business_name") or original
        def belongs(key, payload):
            assn = assignments.get(key) or {}
            o = ov(key)
            return (o.get("system_id") or payload.get("system_id") or assn.get("system_id"),
                    o.get("module_id") or payload.get("module_id") or assn.get("module_id"))

        def add(kind, eid, title, payload, subtitle="", scenario_id=None, tags=None):
            key = f"{kind}:{eid}"
            o = ov(key)
            if o.get("hidden") is True: return
            system_id, module_id = belongs(key, payload)
            p = dict(payload)
            p.update({"_key": key, "_kind": kind, "_id": eid, "_title": display(key, str(title)),
                      "_original_title": str(title), "_override": o, "system_id": system_id, "module_id": module_id})
            if o.get("description") is not None: p["display_description"] = o["description"]
            entities[key] = p
            summary = {"key": key, "kind": kind, "id": eid, "title": p["_title"], "subtitle": subtitle,
                       "scenario_id": scenario_id, "system_id": system_id, "module_id": module_id,
                       "status": p.get("fact_status") or p.get("status"), "certainty": p.get("certainty"), "tags": tags or [],
                       "order": o.get("order", 9999)}
            summaries[key] = summary
            search.append({**summary, "text": self._search_blob(p)[:self.max_search_text]})

        # Systems / modules first.
        for x in cat["system"]:
            sid = str(x.get("system_id") or x.get("entity_id")); key = f"system:{sid}"
            add("system", sid, x.get("name") or sid, x, subtitle="System", tags=["system"])
        for x in cat["module"]:
            mid = str(x.get("module_id") or x.get("entity_id"));
            add("module", mid, x.get("name") or mid, x, subtitle="Module", tags=["module"])

        # Evidence.
        evidence_backrefs = defaultdict(list)
        for row in facts:
            fid = str(row.get("fact_id") or "")
            for ev in row.get("evidence_ids") or []:
                evidence_backrefs[str(ev)].append({"fact_id": fid, "fact_type": row.get("fact_type"), "scenario_id": row.get("scenario_id")})
        for ev in evidences:
            eid = str(ev.get("evidence_id")); title = ev.get("symbol") or ev.get("source") or ev.get("type") or eid
            add("evidence", eid, title, {**ev, "backrefs": evidence_backrefs.get(eid, [])}, subtitle=str(ev.get("type") or "Evidence"))

        # Facts.
        decisions_by_owner, interactions_by_owner, mutations_by_owner = defaultdict(list), defaultdict(list), defaultdict(list)
        for row in facts:
            ft = row["fact_type"]; sid = row["scenario_id"]
            if ft == "decisions": decisions_by_owner[str(row.get("owner_node_id"))].append(row)
            elif ft == "interactions": interactions_by_owner[str(row.get("owner_node_id"))].append(row)
            elif ft == "data_mutations": mutations_by_owner[str(row.get("owner_node_id"))].append(row)

        for row in facts:
            ft, sid = row["fact_type"], row["scenario_id"]
            if ft == "execution_nodes":
                eid = str(row.get("node_id")); title = row.get("name") or row.get("symbol") or eid
                payload = {**row, "decisions": decisions_by_owner[eid], "interactions": interactions_by_owner[eid], "mutations": mutations_by_owner[eid]}
                add("node", eid, title, payload, subtitle=f"{row.get('stage','UNKNOWN')} · {row.get('kind','NODE')}", scenario_id=sid)
            elif ft == "decisions":
                eid = str(row.get("decision_id")); title = row.get("expression") or f"Decision · {eid}"
                add("decision", eid, title, {**row, "owner": node_by_id.get(str(row.get("owner_node_id")))}, subtitle="Decision", scenario_id=sid)
            elif ft == "interactions":
                eid = str(row.get("interaction_id")); title = f"{row.get('interaction_type','Interaction')} · {row.get('target',eid)}"
                add("interaction", eid, title, {**row, "owner": node_by_id.get(str(row.get("owner_node_id")))}, subtitle=str(row.get("operation") or "Interaction"), scenario_id=sid)

        # Field lineage aggregate.
        mgroups = defaultdict(list)
        for m in [x for x in facts if x["fact_type"] == "data_mutations"]:
            mgroups[(m["scenario_id"], str(m.get("target")))].append(m)
        for (sid, target), muts in mgroups.items():
            def mk(m):
                stage = str((node_by_id.get(str(m.get("owner_node_id"))) or {}).get("stage") or "")
                return (STAGES.index(stage) if stage in STAGES else 99, str(m.get("_updated_at") or ""), str(m.get("mutation_id") or ""))
            muts.sort(key=mk)
            add("field", f"{sid}::{target}", target, {"scenario_id":sid,"target":target,"mutations":muts}, subtitle=f"{len(muts)} mutations", scenario_id=sid)

        for x in unknowns:
            eid = str(x.get("unknown_id")); sid = str(x.get("scenario_id") or "UNSCOPED")
            add("unknown", eid, x.get("question") or eid, x, subtitle="Unknown", scenario_id=sid)
        for x in conflicts:
            eid = str(x.get("conflict_id")); sid = str(x.get("scenario_id") or "UNSCOPED")
            add("conflict", eid, x.get("description") or eid, x, subtitle="Conflict", scenario_id=sid)

        # Database catalog, with nested children and heuristic fact references.
        table_by_id = {str(x.get("table_id") or x.get("entity_id")): x for x in cat["table"]}
        columns_by_table, indexes_by_table = defaultdict(list), defaultdict(list)
        for x in cat["column"]: columns_by_table[str(x.get("table_id"))].append(x)
        for x in cat["index"]: indexes_by_table[str(x.get("table_id"))].append(x)
        relations = cat["relation"]

        def fact_refs_for(*needles):
            nd = [str(x).lower() for x in needles if x]
            out = []
            for f in facts:
                blob = _json(f).lower()
                if nd and all(x in blob for x in nd):
                    out.append({"fact_type": f.get("fact_type"), "fact_id": f.get("fact_id"), "scenario_id": f.get("scenario_id"),
                                "match": "NAME_MATCH"})
            return out[:80]

        for tid, t in table_by_id.items():
            name = str(t.get("name") or tid)
            payload = {**t, "columns": columns_by_table[tid], "indexes": indexes_by_table[tid],
                       "relations": [r for r in relations if tid in _json(r)], "fact_references": fact_refs_for(name)}
            add("table", tid, name, payload, subtitle=f"Table · {len(columns_by_table[tid])} columns", tags=["data"])
        for x in cat["column"]:
            cid = str(x.get("column_id") or x.get("entity_id")); name = str(x.get("name") or cid); tname = str(x.get("table_name") or "")
            payload = {**x, "fact_references": fact_refs_for(name), "table": table_by_id.get(str(x.get("table_id")))}
            add("column", cid, f"{tname}.{name}" if tname else name, payload, subtitle=str(x.get("data_type") or x.get("type") or "Column"), tags=["data"])
        for x in cat["index"]:
            iid = str(x.get("index_id") or x.get("entity_id")); name = str(x.get("name") or iid); tname = str(x.get("table_name") or "")
            add("index", iid, f"{tname}.{name}" if tname else name, {**x, "table": table_by_id.get(str(x.get("table_id")))}, subtitle="Index", tags=["data"])
        for x in relations:
            rid = str(x.get("relation_id") or x.get("entity_id")); title = f"{x.get('from','?')} → {x.get('to','?')}"
            add("relation", rid, title, x, subtitle=str(x.get("kind") or "Relation"), tags=["data"])

        # Build scenario entities after all summaries so chain projection can point to system/module pages.
        scenario_ids = set(scenario_defs) | set(by_scenario)
        scenario_ids |= {str(x.get("scenario_id")) for x in unknowns + conflicts if x.get("scenario_id")}
        scenario_catalog = []
        system_scenarios, module_scenarios = defaultdict(set), defaultdict(set)
        for sid in sorted(scenario_ids):
            sfacts = by_scenario.get(sid, [])
            nodes = [x for x in sfacts if x.get("fact_type") == "execution_nodes"]
            stages = {}
            for stage in STAGES:
                xs = [x for x in nodes if x.get("stage") == stage]
                if not xs: status = "NOT_ANALYZED"
                elif all(x.get("fact_status") == "CONFIRMED" for x in xs): status = "CONFIRMED"
                else: status = "PARTIAL"
                stages[stage] = {"status": status, "count": len(xs)}

            # Order nodes from execution edges when possible, then render contiguous system hops.
            edges = [x for x in sfacts if x.get("fact_type") == "execution_edges"]
            ids = {str(n.get("node_id")) for n in nodes}
            outgoing, indeg = defaultdict(list), {nid: 0 for nid in ids}
            for e in edges:
                a, b = str(e.get("from") or ""), str(e.get("to") or "")
                if a in ids and b in ids:
                    outgoing[a].append(b); indeg[b] = indeg.get(b, 0) + 1
            byid = {str(n.get("node_id")): n for n in nodes}
            queue = sorted([nid for nid, d in indeg.items() if d == 0], key=lambda nid: (STAGES.index(str(byid[nid].get("stage"))) if str(byid[nid].get("stage")) in STAGES else 99, nid))
            ordered_ids = []
            while queue:
                nid = queue.pop(0); ordered_ids.append(nid)
                for nxt in outgoing.get(nid, []):
                    indeg[nxt] -= 1
                    if indeg[nxt] == 0: queue.append(nxt)
            if len(ordered_ids) != len(ids):
                remaining = [nid for nid in ids if nid not in ordered_ids]
                remaining.sort(key=lambda nid: (STAGES.index(str(byid[nid].get("stage"))) if str(byid[nid].get("stage")) in STAGES else 99, nid))
                ordered_ids.extend(remaining)
            ordered_nodes = [byid[nid] for nid in ordered_ids]

            touched_systems, touched_modules = set(), set()
            chain_view = []
            for n in ordered_nodes:
                key = f"node:{n.get('node_id')}"; sysid, modid = belongs(key, n)
                sysid = sysid or "UNASSIGNED"; modid = modid or "UNASSIGNED"
                if sysid != "UNASSIGNED": touched_systems.add(sysid); system_scenarios[sysid].add(sid)
                if modid != "UNASSIGNED": touched_modules.add(modid); module_scenarios[modid].add(sid)
                node_summary = {"node_id":n.get("node_id"),"name":display(key,n.get("name") or n.get("node_id")),"stage":n.get("stage"),"status":n.get("fact_status")}
                if not chain_view or chain_view[-1]["system_id"] != sysid:
                    chain_view.append({"system_id":sysid,"system_title":summaries.get(f"system:{sysid}",{}).get("title",sysid),"modules":[]})
                segment = chain_view[-1]
                if not segment["modules"] or segment["modules"][-1]["module_id"] != modid:
                    segment["modules"].append({"module_id":modid,"module_title":summaries.get(f"module:{modid}",{}).get("title",modid),"nodes":[]})
                segment["modules"][-1]["nodes"].append(node_summary)

            sdef = scenario_defs.get(sid, {})
            title = sdef.get("name") or sid
            payload = {"scenario_id":sid,"definition":sdef,"stages":stages,"chain":chain_view,
                       "touched_systems":sorted(touched_systems),"touched_modules":sorted(touched_modules),
                       "nodes":[summaries.get(f"node:{n.get('node_id')}") for n in nodes if summaries.get(f"node:{n.get('node_id')}")],
                       "decisions":[summaries.get(f"decision:{x.get('decision_id')}") for x in sfacts if x.get("fact_type")=="decisions" and summaries.get(f"decision:{x.get('decision_id')}")],
                       "interactions":[summaries.get(f"interaction:{x.get('interaction_id')}") for x in sfacts if x.get("fact_type")=="interactions" and summaries.get(f"interaction:{x.get('interaction_id')}")],
                       "fields":[summaries[k] for k in summaries if k.startswith(f"field:{sid}::")],
                       "unknowns":[x for x in unknowns if str(x.get("scenario_id"))==sid],
                       "conflicts":[x for x in conflicts if str(x.get("scenario_id"))==sid]}
            add("scenario", sid, title, payload, subtitle="Business chain", scenario_id=sid, tags=["chain"])
            scenario_catalog.append(summaries.get(f"scenario:{sid}"))

        # Enrich system/module pages with reverse projections.
        modules_by_system = defaultdict(list)
        for m in cat["module"]:
            sid = str(m.get("system_id") or "")
            mid = str(m.get("module_id") or m.get("entity_id"))
            if sid and summaries.get(f"module:{mid}"): modules_by_system[sid].append(summaries[f"module:{mid}"])
        tables_by_system, tables_by_module = defaultdict(list), defaultdict(list)
        for t in cat["table"]:
            tid = str(t.get("table_id") or t.get("entity_id")); sm = summaries.get(f"table:{tid}")
            if not sm: continue
            if t.get("system_id"): tables_by_system[str(t["system_id"])].append(sm)
            if t.get("module_id"): tables_by_module[str(t["module_id"])].append(sm)
        for key, ent in list(entities.items()):
            if ent.get("_kind") == "system":
                sid = ent["_id"]; ent["modules"] = sorted(modules_by_system[sid], key=lambda x:(x.get("order",9999),x["title"]))
                ent["scenarios"] = [summaries.get(f"scenario:{x}") for x in sorted(system_scenarios[sid]) if summaries.get(f"scenario:{x}")]
                ent["tables"] = tables_by_system[sid]
            elif ent.get("_kind") == "module":
                mid = ent["_id"]
                ent["scenarios"] = [summaries.get(f"scenario:{x}") for x in sorted(module_scenarios[mid]) if summaries.get(f"scenario:{x}")]
                ent["tables"] = tables_by_module[mid]
                ent["nodes"] = [s for s in summaries.values() if s.get("kind")=="node" and s.get("module_id")==mid]

        # Recompute summaries/search for enriched title data not necessary; payload hashes include enrichment.
        stats = {
            "scenarios": len(scenario_ids), "systems": len(cat["system"]), "modules": len(cat["module"]),
            "tables": len(cat["table"]), "columns": len(cat["column"]), "indexes": len(cat["index"]),
            "confirmed_facts": sum(1 for x in facts if x.get("fact_status")=="CONFIRMED"),
            "candidate_facts": sum(1 for x in facts if x.get("fact_status")!="CONFIRMED"),
            "unknowns": len([x for x in unknowns if x.get("status","OPEN")=="OPEN"]),
            "conflicts": len([x for x in conflicts if x.get("status","OPEN")=="OPEN"]),
        }
        return {"entities":entities,"summaries":summaries,"search":search,"stats":stats,
                "scenario_catalog":[x for x in scenario_catalog if x],
                "system_catalog":sorted([x for x in summaries.values() if x.get("kind")=="system"],key=lambda x:(x.get("order",9999),x["title"])),
                "module_catalog":sorted([x for x in summaries.values() if x.get("kind")=="module"],key=lambda x:(x.get("order",9999),x["title"])),
                "data_catalog":sorted([x for x in summaries.values() if x.get("kind")=="table"],key=lambda x:x["title"]),
                "gap_catalog":sorted([x for x in summaries.values() if x.get("kind") in {"unknown","conflict"}],key=lambda x:x["kind"])}

    def _search_blob(self, payload):
        def walk(v):
            if v is None: return []
            if isinstance(v, (str,int,float,bool)): return [str(v)]
            if isinstance(v, list):
                out=[]
                for x in v: out += walk(x)
                return out
            if isinstance(v, dict):
                out=[]
                for k,x in v.items():
                    if not str(k).startswith("_"): out += [str(k)] + walk(x)
                return out
            return [str(v)]
        return " ".join(walk(payload))

    def _write_entity(self, rel, key, payload):
        p=self.output/rel; p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text("window.UCEF_ENTITIES=window.UCEF_ENTITIES||{};window.UCEF_ENTITIES["+json.dumps(key)+"]="+json.dumps(payload,ensure_ascii=False,separators=(",",":"),default=str)+";\n",encoding="utf-8")

    def _write_catalog(self, model):
        (self.output/"data/catalog.js").write_text("window.UCEF_CATALOG="+json.dumps(model,ensure_ascii=False,separators=(",",":"),default=str)+";\n",encoding="utf-8")

    def _write_shell(self):
        (self.output/"index.html").write_text(INDEX_HTML,encoding="utf-8")
        (self.output/"assets/style.css").write_text(STYLE_CSS,encoding="utf-8")
        (self.output/"assets/app.js").write_text(APP_JS,encoding="utf-8")


class UCEFWorkbenchServer:
    def __init__(self, builder: IncrementalSiteBuilder, store, host="127.0.0.1", port=8765):
        self.builder, self.store, self.host, self.port = builder, store, host, int(port)
        self.workspace = builder.workspace
        self.overrides = builder.overrides

    def create_review_work_unit(self, body):
        entity_key = str(body.get("entity_key") or "UNKNOWN")
        reason = str(body.get("reason") or "User requested fact review")
        proposed = str(body.get("proposed_change") or "")
        sid = str(body.get("scenario_id") or "UNSCOPED")
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        wid = f"WU-REVIEW-{_safe(entity_key,40)}-{stamp}"
        wu = {
            "work_unit_id": wid, "work_type": "MANUAL_FACT_REVIEW", "scenario_id": sid,
            "objective": f"Review user correction for {entity_key}: {reason}",
            "entry_refs": [{"entity_key": entity_key}],
            "questions": [reason] + ([f"Proposed change: {proposed}"] if proposed else []),
            "verification_required": True,
            "stop_conditions": ["objective_satisfied", "source_missing", "scope_exceeded"],
            "status": "PENDING",
            "created_by": "HTML_WORKBENCH",
        }
        folder = self.workspace / "work_units" / "pending"; folder.mkdir(parents=True,exist_ok=True)
        path = folder / f"{wid}.yaml"
        path.write_text(yaml.safe_dump(wu,allow_unicode=True,sort_keys=False),encoding="utf-8")
        self.store.save_work_unit(wu); self.store.commit()
        return {"work_unit_id":wid,"path":str(path)}

    def serve(self, open_browser=False):
        self.builder.update()
        builder, store, overrides, server_obj = self.builder, self.store, self.overrides, self
        site_dir = str(builder.output)

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self,*args,**kwargs): super().__init__(*args,directory=site_dir,**kwargs)
            def log_message(self, fmt, *args): pass
            def _send_json(self,obj,status=200):
                data=json.dumps(obj,ensure_ascii=False).encode("utf-8")
                self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8")
                self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
            def _body(self):
                n=int(self.headers.get("Content-Length","0") or 0)
                return json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            def do_GET(self):
                path=urlparse(self.path).path
                if path=="/api/status": return self._send_json({"editable":True,"version":SITE_VERSION})
                if path=="/api/overrides": return self._send_json(overrides.load())
                return super().do_GET()
            def do_POST(self):
                path=urlparse(self.path).path
                try: body=self._body()
                except Exception as exc: return self._send_json({"error":str(exc)},400)
                if path=="/api/override":
                    key=str(body.get("entity_key") or "")
                    if not key: return self._send_json({"error":"entity_key required"},400)
                    current=overrides.update(key,body.get("patch") or {})
                    result=builder.update()
                    return self._send_json({"ok":True,"override":current,"site":result})
                if path=="/api/review":
                    return self._send_json({"ok":True,**server_obj.create_review_work_unit(body)})
                if path=="/api/rebuild":
                    return self._send_json({"ok":True,"site":builder.update()})
                return self._send_json({"error":"not found"},404)

        httpd=HTTPServer((self.host,self.port),Handler)
        url=f"http://{self.host}:{self.port}/"
        if open_browser: threading.Timer(0.5,lambda:webbrowser.open(url)).start()
        print(f"UCEF workbench: {url}")
        print("Ctrl+C to stop")
        try: httpd.serve_forever()
        except KeyboardInterrupt: pass
        finally: httpd.server_close()


INDEX_HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UCEF Business Explorer</title><link rel="stylesheet" href="assets/style.css"></head>
<body><div id="app"><div class="boot">Loading UCEF Explorer…</div></div>
<script>window.UCEF_ENTITIES={};</script><script src="data/catalog.js"></script><script src="assets/app.js"></script></body></html>'''

STYLE_CSS = r'''
:root{--bg:#f5f7fb;--panel:#fff;--ink:#172033;--muted:#667085;--line:#e5e9f2;--brand:#3157d5;--brand-soft:#eef2ff;--green:#138a5b;--amber:#b7791f;--red:#c2413b;--nav:#0f172a;--shadow:0 8px 28px rgba(23,32,51,.08)}*{box-sizing:border-box}body{margin:0;font:14px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",Arial;color:var(--ink);background:var(--bg)}button,input,textarea,select{font:inherit}.app{min-height:100vh;display:grid;grid-template-rows:64px 1fr}.top{background:#fff;border-bottom:1px solid var(--line);display:flex;align-items:center;padding:0 24px;gap:22px;position:sticky;top:0;z-index:20}.brand{font-weight:800;font-size:18px;letter-spacing:-.3px}.brand small{font-size:11px;color:var(--muted);font-weight:600;margin-left:8px}.tabs{display:flex;gap:4px;height:100%;align-items:center}.tab{border:0;background:transparent;padding:10px 14px;border-radius:9px;color:#475467;cursor:pointer;font-weight:650}.tab.active,.tab:hover{background:var(--brand-soft);color:var(--brand)}.search{margin-left:auto;position:relative;width:min(420px,35vw)}.search input{width:100%;padding:10px 14px 10px 36px;border:1px solid var(--line);border-radius:11px;background:#f8fafc;outline:none}.search:before{content:'⌕';position:absolute;left:12px;top:7px;color:#98a2b3;font-size:19px}.layout{display:grid;grid-template-columns:270px minmax(0,1fr);min-height:calc(100vh - 64px)}.side{background:#fff;border-right:1px solid var(--line);padding:18px 14px;overflow:auto}.side-title{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#98a2b3;font-weight:800;padding:6px 10px 10px}.side-item{display:block;width:100%;text-align:left;border:0;background:transparent;padding:9px 10px;border-radius:9px;cursor:pointer;color:#344054;margin:1px 0}.side-item:hover,.side-item.active{background:#f2f4f7;color:#101828}.side-item .k{display:block;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.side-item .s{font-size:11px;color:#98a2b3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.main{padding:28px clamp(22px,4vw,56px) 64px;overflow:auto}.crumb{font-size:12px;color:#98a2b3;margin-bottom:14px}.crumb a{color:#667085;text-decoration:none}.hero{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:24px}.eyebrow{color:var(--brand);font-weight:800;text-transform:uppercase;letter-spacing:.09em;font-size:11px}.hero h1{font-size:32px;line-height:1.15;letter-spacing:-.7px;margin:6px 0 8px}.hero p{color:var(--muted);max-width:820px;margin:0}.actions{display:flex;gap:8px;flex-wrap:wrap}.btn{border:1px solid var(--line);background:#fff;border-radius:9px;padding:8px 11px;cursor:pointer;font-weight:650;color:#344054}.btn:hover{border-color:#b6c1e7}.btn.primary{background:var(--brand);color:#fff;border-color:var(--brand)}.btn.danger{color:var(--red)}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:16px}.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 1px 2px rgba(16,24,40,.02)}.card h2,.card h3{margin:0 0 12px}.span4{grid-column:span 4}.span5{grid-column:span 5}.span6{grid-column:span 6}.span7{grid-column:span 7}.span8{grid-column:span 8}.span12{grid-column:span 12}.metric{font-size:30px;font-weight:800;letter-spacing:-.5px}.metric-label{font-size:12px;color:var(--muted)}.section{margin-top:28px}.section-head{display:flex;align-items:end;justify-content:space-between;margin-bottom:12px}.section h2{margin:0;font-size:19px}.muted{color:var(--muted)}.chips{display:flex;gap:7px;flex-wrap:wrap}.chip{border:1px solid var(--line);border-radius:999px;padding:4px 9px;background:#fff;font-size:12px;color:#475467}.chip.ok{background:#ecfdf3;color:var(--green);border-color:#abefc6}.chip.partial{background:#fffaeb;color:var(--amber);border-color:#fedf89}.chip.bad{background:#fef3f2;color:var(--red);border-color:#fecdca}.stagebar{display:grid;grid-template-columns:repeat(9,minmax(88px,1fr));gap:6px;overflow:auto}.stage{min-width:88px;padding:11px 10px;border-radius:10px;background:#f2f4f7}.stage b{display:block;font-size:11px}.stage span{font-size:11px;color:var(--muted)}.stage.confirmed{background:#ecfdf3}.stage.partial{background:#fffaeb}.chain{display:flex;gap:14px;align-items:stretch;overflow:auto;padding:8px 2px 12px}.sys-block{min-width:260px;background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px;position:relative}.sys-block:after{content:'→';position:absolute;right:-13px;top:38px;color:#98a2b3;font-size:18px}.sys-block:last-child:after{display:none}.sys-name{font-weight:800;font-size:15px;margin-bottom:10px;color:#1d2939}.module-block{background:#f8fafc;border:1px solid #eef0f5;border-radius:10px;padding:10px;margin-top:8px}.module-name{font-weight:700;font-size:12px;margin-bottom:6px}.node-pill{display:flex;justify-content:space-between;gap:8px;background:#fff;border:1px solid var(--line);padding:7px 8px;border-radius:8px;margin:5px 0;cursor:pointer}.node-pill:hover{border-color:#b6c1e7}.node-pill small{color:#98a2b3}.entity-list{display:grid;gap:8px}.entity-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:11px 12px;border:1px solid var(--line);border-radius:10px;background:#fff;cursor:pointer}.entity-row:hover{border-color:#b6c1e7;box-shadow:0 3px 12px rgba(49,87,213,.05)}.entity-row b{display:block}.entity-row small{color:#98a2b3}.badge{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.04em;padding:3px 7px;border-radius:999px;background:#f2f4f7;color:#667085;align-self:start}.badge.system{background:#eef2ff;color:#3949ab}.badge.module{background:#eef4ff;color:#175cd3}.badge.table{background:#ecfdf3;color:#067647}.badge.unknown{background:#fffaeb;color:#b54708}.badge.conflict{background:#fef3f2;color:#b42318}.columns{display:grid;grid-template-columns:1fr 1fr;gap:12px}.kv{display:grid;grid-template-columns:160px minmax(0,1fr);gap:8px;border-bottom:1px solid #f0f2f5;padding:8px 0}.kv .label{color:#667085;font-size:12px}.code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;background:#101828;color:#e4e7ec;padding:13px;border-radius:10px;white-space:pre-wrap;overflow:auto}.timeline{border-left:2px solid #d0d5dd;margin-left:7px;padding-left:18px}.timeline-item{position:relative;padding:0 0 16px}.timeline-item:before{content:'';position:absolute;left:-24px;top:5px;width:10px;height:10px;border-radius:50%;background:var(--brand);border:2px solid #fff;box-shadow:0 0 0 1px #b6c1e7}.timeline-item b{display:block}.empty{padding:26px;text-align:center;color:#98a2b3;border:1px dashed #d0d5dd;border-radius:12px}.search-results{position:absolute;top:46px;left:0;right:0;background:#fff;border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);max-height:420px;overflow:auto;z-index:99}.search-hit{padding:10px 12px;border-bottom:1px solid #f2f4f7;cursor:pointer}.search-hit:hover{background:#f8fafc}.modal-bg{position:fixed;inset:0;background:rgba(15,23,42,.48);display:flex;align-items:center;justify-content:center;z-index:100}.modal{width:min(620px,92vw);background:#fff;border-radius:16px;box-shadow:var(--shadow);padding:22px}.modal h2{margin:0 0 4px}.form-row{margin:13px 0}.form-row label{display:block;font-size:12px;font-weight:700;color:#475467;margin-bottom:5px}.form-row input,.form-row textarea,.form-row select{width:100%;border:1px solid #d0d5dd;border-radius:9px;padding:9px 10px;outline:none}.form-row textarea{min-height:90px}.form-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:18px}.notice{padding:10px 12px;border-radius:9px;background:#fffaeb;color:#854a0e;font-size:12px}.home-choice{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.choice{background:#fff;border:1px solid var(--line);border-radius:16px;padding:22px;cursor:pointer;min-height:150px}.choice:hover{border-color:#a4b4eb;box-shadow:0 8px 26px rgba(49,87,213,.08);transform:translateY(-1px)}.choice .icon{font-size:24px}.choice h2{margin:20px 0 5px}.choice p{color:var(--muted);margin:0}.data-table{width:100%;border-collapse:collapse}.data-table th,.data-table td{text-align:left;padding:9px 8px;border-bottom:1px solid #eef0f4;font-size:12px}.data-table th{color:#667085;font-weight:700}.link{color:var(--brand);cursor:pointer;text-decoration:none}.link:hover{text-decoration:underline}@media(max-width:900px){.layout{grid-template-columns:1fr}.side{display:none}.span4,.span5,.span6,.span7,.span8,.span12{grid-column:span 12}.home-choice{grid-template-columns:1fr}.stagebar{grid-template-columns:repeat(9,120px)}.search{width:40vw}.tabs .tab{padding:9px 7px;font-size:12px}.main{padding:20px 16px}.hero h1{font-size:27px}.columns{grid-template-columns:1fr}}
'''

APP_JS = r'''
(()=>{const C=window.UCEF_CATALOG||{}, E=window.UCEF_ENTITIES||{}; let editable=false;
const $=s=>document.querySelector(s), esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const route=()=>location.hash.slice(1)||'/'; const nav=(r)=>{location.hash=r};
async function api(path,opts={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts}); if(!r.ok)throw new Error(await r.text()); return r.json()}
async function detect(){if(location.protocol==='file:')return false;try{const x=await api('/api/status');return !!x.editable}catch{return false}}
function loadEntity(key){return new Promise(resolve=>scriptLoad(key,resolve))}function scriptLoad(key,cb){if(E[key])return cb(E[key]);const f=C.entity_files&&C.entity_files[key];if(!f)return cb(null);const s=document.createElement('script');s.src=f;s.onload=()=>cb(E[key]);s.onerror=()=>cb(null);document.body.appendChild(s)}
function shell(content,active='chains',side=''){const tabs=[['chains','业务链路'],['systems','系统结构'],['data','数据模型'],['gaps','待确认']];return `<div class="app"><header class="top"><div class="brand">UCEF <small>Business Explorer · v${esc(C.site_version||'')}</small></div><div class="tabs">${tabs.map(([k,n])=>`<button class="tab ${active===k?'active':''}" data-nav="/${k}">${n}</button>`).join('')}</div><div class="search"><input id="search" placeholder="搜索场景 / 模块 / 表 / 字段 / Decision…"><div id="searchResults"></div></div></header><div class="layout"><aside class="side">${side}</aside><main class="main">${content}</main></div></div>`}
function sideList(title,items){return `<div class="side-title">${esc(title)}</div>${(items||[]).map(x=>`<button class="side-item" data-entity="${esc(x.key)}"><span class="k">${esc(x.title)}</span><span class="s">${esc(x.subtitle||x.id)}</span></button>`).join('')||'<div class="empty">暂无数据</div>'}`}
function metrics(){const s=C.stats||{};return `<div class="grid"><div class="card span4"><div class="metric">${s.scenarios||0}</div><div class="metric-label">业务链路 / Scenarios</div></div><div class="card span4"><div class="metric">${s.systems||0}</div><div class="metric-label">系统 · ${s.modules||0} 模块</div></div><div class="card span4"><div class="metric">${s.tables||0}</div><div class="metric-label">数据表 · ${s.columns||0} 字段 · ${s.indexes||0} 索引</div></div></div>`}
function home(){return shell(`<div class="hero"><div><div class="eyebrow">System Knowledge Workbench</div><h1>${esc(C.title||'UCEF Explorer')}</h1><p>同一份事实，从业务链路、系统结构、数据模型三个维度理解。技术事实由 Evidence 支撑，人工调整只作用于知识组织与展示。</p></div></div>${metrics()}<div class="section"><div class="home-choice"><div class="choice" data-nav="/chains"><div class="icon">↝</div><h2>业务链路</h2><p>一条业务如何跨系统、跨模块协作；从 Scenario 一路下钻到 Decision、字段与 Evidence。</p></div><div class="choice" data-nav="/systems"><div class="icon">▦</div><h2>系统结构</h2><p>一个系统内部有哪些模块、核心入口、参与哪些链路、依赖哪些数据实体。</p></div><div class="choice" data-nav="/data"><div class="icon">▤</div><h2>数据模型</h2><p>表、字段、索引和关系，并反查哪些代码事实与业务链路正在使用它们。</p></div></div></div>`, 'chains', sideList('最近链路',(C.scenario_catalog||[]).slice(0,12)))}
function chains(){const arr=C.scenario_catalog||[];const opts=arr.map(x=>`<option value="${esc(x.id)}">${esc(x.title)}</option>`).join('');const compare=arr.length>=2?`<div class="card" style="margin-bottom:18px"><div class="section-head"><div><h2>Scenario Compare</h2><div class="muted">横向比较生命周期、跨系统范围、Decision 与字段差异</div></div><div class="actions"><select id="cmpA" class="btn">${opts}</select><select id="cmpB" class="btn">${opts}</select><button id="compareBtn" class="btn primary">比较</button></div></div></div>`:'';const body=`<div class="hero"><div><div class="eyebrow">Chain View</div><h1>业务链路</h1><p>先看跨系统协作，再按需展开系统内部模块和技术细节。</p></div></div>${compare}<div class="entity-list">${arr.map(x=>row(x,'scenario')).join('')||'<div class="empty">还没有 Scenario。先从一个真实业务场景开始挖。</div>'}</div>`;return shell(body,'chains',sideList('Scenarios',arr))}
function systems(){const arr=C.system_catalog||[];const body=`<div class="hero"><div><div class="eyebrow">System View</div><h1>系统结构</h1><p>从系统 → 模块 → 参与链路 / 数据实体 / 技术节点逐层理解。</p></div></div><div class="grid">${arr.map(x=>`<div class="card span6 entity-row" data-entity="${esc(x.key)}"><div><b>${esc(x.title)}</b><small>${esc(x.subtitle||'System')}</small></div><span class="badge system">SYSTEM</span></div>`).join('')||'<div class="empty span12">还没有 System metadata。可以导入系统/模块清单。</div>'}</div>`;return shell(body,'systems',sideList('Systems',arr))}
function data(){const arr=C.data_catalog||[];const body=`<div class="hero"><div><div class="eyebrow">Data Model</div><h1>数据模型</h1><p>数据库结构是权威元数据，不由 AI 猜。表、列、索引与关系可持续增量导入。</p></div></div><div class="entity-list">${arr.map(x=>row(x,'table')).join('')||'<div class="empty">还没有数据库 Metadata。使用 metadata import 导入表结构。</div>'}</div>`;return shell(body,'data',sideList('Tables',arr))}
function gaps(){const arr=C.gap_catalog||[];const body=`<div class="hero"><div><div class="eyebrow">Knowledge Gaps</div><h1>待确认</h1><p>Unknown 与 Conflict 是知识地图的一部分，不强迫 AI 把未知补成结论。</p></div></div><div class="entity-list">${arr.map(x=>row(x,x.kind)).join('')||'<div class="empty">目前没有未解决项。</div>'}</div>`;return shell(body,'gaps',sideList('Open gaps',arr))}
function row(x,kind){return `<div class="entity-row" data-entity="${esc(x.key)}"><div><b>${esc(x.title)}</b><small>${esc(x.subtitle||x.id)}${x.scenario_id?' · '+esc(x.scenario_id):''}</small></div><span class="badge ${esc(kind)}">${esc(kind)}</span></div>`}
function entity(key){return `<div id="entityLoading" class="empty">Loading ${esc(key)}…</div>`}
function entityHtml(x){if(!x)return `<div class="empty">实体不存在或已被隐藏。</div>`;const k=x._kind;const edit=editable?`<button class="btn" id="editBtn">编辑展示/归属</button>`:'';const review=editable&&!['system','module','table','column','index','relation','scenario'].includes(k)?`<button class="btn danger" id="reviewBtn">提交事实纠正</button>`:'';
let body='';if(k==='scenario')body=scenarioView(x);else if(k==='system')body=systemView(x);else if(k==='module')body=moduleView(x);else if(k==='table')body=tableView(x);else if(k==='column')body=columnView(x);else if(k==='index')body=indexView(x);else if(k==='field')body=fieldView(x);else if(k==='node')body=nodeView(x);else if(k==='interaction')body=interactionView(x);else body=genericView(x);
const active=k==='scenario'?'chains':['system','module'].includes(k)?'systems':['table','column','index','relation'].includes(k)?'data':['unknown','conflict'].includes(k)?'gaps':'chains';const side=active==='systems'?sideList('Systems',C.system_catalog):active==='data'?sideList('Tables',C.data_catalog):active==='gaps'?sideList('Open gaps',C.gap_catalog):sideList('Scenarios',C.scenario_catalog);return shell(`<div class="crumb"><a data-nav="/${active}">${active}</a> › ${esc(x._title)}</div><div class="hero"><div><div class="eyebrow">${esc(k)}</div><h1>${esc(x._title)}</h1><p>${esc(x.display_description||x.description||x.comment||'')}</p></div><div class="actions">${edit}${review}</div></div>${body}`,active,side)}
function scenarioView(x){const stages=Object.entries(x.stages||{}).map(([n,s])=>`<div class="stage ${s.status==='CONFIRMED'?'confirmed':s.status==='PARTIAL'?'partial':''}"><b>${esc(n)}</b><span>${s.status==='CONFIRMED'?'✓ 已确认':s.status==='PARTIAL'?'△ 部分':'○ 未分析'} · ${s.count}</span></div>`).join('');const chain=(x.chain||[]).map(sys=>`<div class="sys-block"><div class="sys-name link" data-entity="system:${esc(sys.system_id)}">${esc(sys.system_title)}</div>${sys.modules.map(m=>`<div class="module-block"><div class="module-name link" data-entity="module:${esc(m.module_id)}">${esc(m.module_title)}</div>${m.nodes.map(n=>`<div class="node-pill" data-entity="node:${esc(n.node_id)}"><span>${esc(n.name)}</span><small>${esc(n.stage||'')}</small></div>`).join('')}</div>`).join('')}</div>`).join('');return `<div class="card"><h2>生命周期覆盖</h2><div class="stagebar">${stages}</div></div><div class="section"><div class="section-head"><h2>跨系统业务链</h2><span class="muted">系统优先，模块按需展开</span></div><div class="chain">${chain||'<div class="empty">暂无已归属节点</div>'}</div></div><div class="grid section"><div class="card span6"><h3>关键 Decisions</h3>${list(x.decisions,'decision')}</div><div class="card span6"><h3>外部/数据交互</h3>${list(x.interactions,'interaction')}</div><div class="card span6"><h3>字段演化</h3>${list(x.fields,'field')}</div><div class="card span6"><h3>待确认</h3>${(x.unknowns||[]).map(u=>`<div class="entity-row" data-entity="unknown:${esc(u.unknown_id)}"><div><b>${esc(u.question)}</b></div><span class="badge unknown">UNKNOWN</span></div>`).join('')||'<div class="muted">无</div>'}</div></div>`}
function systemView(x){return `<div class="grid"><div class="card span7"><h2>模块</h2>${list(x.modules,'module')}</div><div class="card span5"><h2>参与链路</h2>${list(x.scenarios,'scenario')}</div><div class="card span12"><h2>所属数据</h2>${list(x.tables,'table')}</div></div>`}
function moduleView(x){return `<div class="grid"><div class="card span6"><h2>参与链路</h2>${list(x.scenarios,'scenario')}</div><div class="card span6"><h2>数据实体</h2>${list(x.tables,'table')}</div><div class="card span12"><h2>技术节点</h2>${list(x.nodes,'node')}</div></div>`}
function tableView(x){const cols=(x.columns||[]).map(c=>`<tr data-entity="column:${esc(c.column_id||c.entity_id)}"><td class="link">${esc(c.name)}</td><td>${esc(c.data_type||c.type||'')}</td><td>${c.nullable===false?'NOT NULL':esc(c.nullable??'')}</td><td>${esc(c.comment||'')}</td></tr>`).join('');const idx=(x.indexes||[]).map(i=>`<tr data-entity="index:${esc(i.index_id||i.entity_id)}"><td class="link">${esc(i.name)}</td><td>${esc((i.columns||[]).join(', '))}</td><td>${i.unique?'UNIQUE':''}</td></tr>`).join('');return `<div class="grid"><div class="card span12"><div class="chips"><span class="chip">physical: ${esc(x.name||x._original_title)}</span>${x.schema?`<span class="chip">schema: ${esc(x.schema)}</span>`:''}${x.system_id?`<span class="chip link" data-entity="system:${esc(x.system_id)}">system: ${esc(x.system_id)}</span>`:''}${x.module_id?`<span class="chip link" data-entity="module:${esc(x.module_id)}">module: ${esc(x.module_id)}</span>`:''}<span class="chip">source: ${esc(x.source_type||'metadata')}</span></div></div><div class="card span7"><h2>Columns</h2><table class="data-table"><thead><tr><th>Name</th><th>Type</th><th>Null</th><th>Comment</th></tr></thead><tbody>${cols}</tbody></table></div><div class="card span5"><h2>Indexes</h2><table class="data-table"><thead><tr><th>Name</th><th>Columns</th><th></th></tr></thead><tbody>${idx}</tbody></table></div><div class="card span12"><h2>代码/链路关联</h2><div class="notice">NAME_MATCH 只是辅助导航，不自动视为确认的数据血缘。</div>${refs(x.fact_references)}</div></div>`}
function columnView(x){return `<div class="grid"><div class="card span6"><h2>物理定义</h2>${kv(x,['table_name','name','data_type','type','nullable','default','comment','position'])}</div><div class="card span6"><h2>业务关联</h2>${refs(x.fact_references)}</div></div>`}
function indexView(x){return `<div class="grid"><div class="card span6"><h2>索引定义</h2>${kv(x,['table_name','name','columns','unique','type','comment'])}</div><div class="card span6"><h2>说明</h2><p class="muted">目前展示 Metadata；未来接入 SQL / Explain 后可继续追加实际命中、扫描行数和慢 SQL。</p></div></div>`}
function fieldView(x){return `<div class="card"><h2>字段演化</h2><div class="timeline">${(x.mutations||[]).map(m=>`<div class="timeline-item"><b>${esc(m.operation||'MUTATE')} · ${esc(m.version_before||'∅')} → ${esc(m.version_after||'?')}</b><div class="muted">${esc(m.condition||m.condition_ref||'')} ${m.business_effect?'· '+esc(m.business_effect):''}</div><small class="link" data-entity="node:${esc(m.owner_node_id)}">${esc(m.owner_node_id||'')}</small></div>`).join('')}</div></div>`}
function nodeView(x){const drefs=(x.data_refs||[]).map(r=>`<div class="entity-row" data-entity="table:${esc(r)}"><div><b>${esc(r)}</b><small>Data reference</small></div><span class="badge table">DATA</span></div>`).join('');return `<div class="grid"><div class="card span7"><h2>职责与位置</h2>${kv(x,['kind','stage','symbol','class','method','certainty','fact_status'])}</div><div class="card span5"><h2>归属</h2>${x.system_id?`<div class="entity-row" data-entity="system:${esc(x.system_id)}"><div><b>${esc(x.system_id)}</b><small>System</small></div></div>`:''}${x.module_id?`<div class="entity-row" data-entity="module:${esc(x.module_id)}"><div><b>${esc(x.module_id)}</b><small>Module</small></div></div>`:''}</div><div class="card span4"><h3>Decisions</h3>${(x.decisions||[]).map(d=>`<div class="entity-row" data-entity="decision:${esc(d.decision_id)}"><div><b>${esc(d.expression||d.decision_id)}</b></div></div>`).join('')||'<div class="muted">暂无</div>'}</div><div class="card span4"><h3>Interactions</h3>${(x.interactions||[]).map(i=>`<div class="entity-row" data-entity="interaction:${esc(i.interaction_id)}"><div><b>${esc(i.target||i.interaction_id)}</b><small>${esc(i.interaction_type||'')}</small></div></div>`).join('')||'<div class="muted">暂无</div>'}</div><div class="card span4"><h3>Data</h3>${drefs||'<div class="muted">暂无显式 Data Reference</div>'}</div></div>`}
function interactionView(x){const target=String(x.target||'');const table=(C.data_catalog||[]).find(t=>t.title===target||t.id===target||target.endsWith('.'+t.title));return `<div class="grid"><div class="card span7"><h2>Interaction</h2>${kv(x,['interaction_type','target','operation','direction','sync_mode','inputs','outputs','fact_status','certainty'])}</div><div class="card span5"><h2>关联数据</h2>${table?row(table,'table'):'<div class="muted">未匹配到权威表结构</div>'}</div></div>`}
function genericView(x){return `<div class="grid"><div class="card span7"><h2>核心信息</h2>${kv(x,Object.keys(x).filter(k=>!k.startsWith('_')&&!['owner','backrefs','decisions','interactions','mutations'].includes(k)).slice(0,18))}</div><div class="card span5"><h2>归属</h2>${x.system_id?`<div class="entity-row" data-entity="system:${esc(x.system_id)}"><div><b>${esc(x.system_id)}</b><small>System</small></div></div>`:''}${x.module_id?`<div class="entity-row" data-entity="module:${esc(x.module_id)}"><div><b>${esc(x.module_id)}</b><small>Module</small></div></div>`:''}</div></div>`}
function compareHtml(a,b){if(!a||!b)return shell('<div class="empty">Scenario 不存在</div>','chains',sideList('Scenarios',C.scenario_catalog));const rows=Object.keys(a.stages||{}).map(st=>`<tr><td><b>${esc(st)}</b></td><td>${esc((a.stages[st]||{}).status)}</td><td>${esc((b.stages[st]||{}).status)}</td></tr>`).join('');const sa=(a.touched_systems||[]),sb=(b.touched_systems||[]);const onlyA=sa.filter(x=>!sb.includes(x)),onlyB=sb.filter(x=>!sa.includes(x));const da=(a.decisions||[]).map(x=>x.title),db=(b.decisions||[]).map(x=>x.title);const fa=(a.fields||[]).map(x=>x.title),fb=(b.fields||[]).map(x=>x.title);return shell(`<div class="crumb"><a data-nav="/chains">chains</a> › compare</div><div class="hero"><div><div class="eyebrow">Scenario Compare</div><h1>${esc(a._title)} ↔ ${esc(b._title)}</h1><p>只比较已积累的结构化事实；未分析区域保持未知。</p></div></div><div class="grid"><div class="card span12"><h2>生命周期</h2><table class="data-table"><thead><tr><th>Stage</th><th>${esc(a._title)}</th><th>${esc(b._title)}</th></tr></thead><tbody>${rows}</tbody></table></div><div class="card span6"><h2>系统范围差异</h2><div class="kv"><div class="label">仅 A</div><div>${esc(onlyA.join(', ')||'无')}</div></div><div class="kv"><div class="label">仅 B</div><div>${esc(onlyB.join(', ')||'无')}</div></div></div><div class="card span6"><h2>Decision</h2><div class="kv"><div class="label">A</div><div>${esc(da.join(' · ')||'无')}</div></div><div class="kv"><div class="label">B</div><div>${esc(db.join(' · ')||'无')}</div></div></div><div class="card span12"><h2>Field 覆盖</h2><div class="kv"><div class="label">A</div><div>${esc(fa.join(' · ')||'无')}</div></div><div class="kv"><div class="label">B</div><div>${esc(fb.join(' · ')||'无')}</div></div></div></div>`,'chains',sideList('Scenarios',C.scenario_catalog))}
function list(arr,kind){return (arr||[]).filter(Boolean).map(x=>row(x,kind||x.kind)).join('')||'<div class="muted">暂无</div>'}function refs(arr){return (arr||[]).map(r=>`<div class="entity-row"><div><b>${esc(r.fact_id)}</b><small>${esc(r.fact_type)} · ${esc(r.scenario_id)} · ${esc(r.match||'')}</small></div></div>`).join('')||'<div class="muted">暂无关联</div>'}function kv(x,keys){return keys.map(k=>x[k]===undefined?'':`<div class="kv"><div class="label">${esc(k)}</div><div>${esc(Array.isArray(x[k])?x[k].join(', '):typeof x[k]==='object'?JSON.stringify(x[k]):x[k])}</div></div>`).join('')}
function bind(){document.querySelectorAll('[data-nav]').forEach(el=>el.onclick=()=>nav(el.dataset.nav));document.querySelectorAll('[data-entity]').forEach(el=>el.onclick=e=>{e.stopPropagation();nav('/entity/'+encodeURIComponent(el.dataset.entity))});const cb=$('#compareBtn');if(cb){const a=$('#cmpA'),b=$('#cmpB');if(b&&b.options.length>1)b.selectedIndex=1;cb.onclick=()=>{if(a.value&&b.value&&a.value!==b.value)nav('/compare/'+encodeURIComponent(a.value)+'/'+encodeURIComponent(b.value))}}const q=$('#search');if(q){q.oninput=()=>{const v=q.value.trim().toLowerCase(),box=$('#searchResults');if(!v){box.innerHTML='';return}const hits=(C.search||[]).filter(x=>(x.title+' '+x.subtitle+' '+x.text).toLowerCase().includes(v)).slice(0,16);box.innerHTML=`<div class="search-results">${hits.map(x=>`<div class="search-hit" data-entity="${esc(x.key)}"><b>${esc(x.title)}</b><div class="muted">${esc(x.kind)} · ${esc(x.subtitle||'')}</div></div>`).join('')||'<div class="search-hit muted">无结果</div>'}</div>`;box.querySelectorAll('[data-entity]').forEach(el=>el.onclick=()=>nav('/entity/'+encodeURIComponent(el.dataset.entity)))}}}
function editModal(x){const systems=C.system_catalog||[],mods=C.module_catalog||[],o=x._override||{};const html=`<div class="modal-bg" id="modal"><div class="modal"><h2>人工调整</h2><p class="muted">只改变知识组织/展示，不修改技术 Fact。</p><div class="form-row"><label>显示名称</label><input id="mName" value="${esc(o.display_name||x._title)}"></div><div class="form-row"><label>说明</label><textarea id="mDesc">${esc(o.description||x.display_description||x.description||'')}</textarea></div><div class="columns"><div class="form-row"><label>System</label><select id="mSys"><option value="">未指定</option>${systems.map(s=>`<option value="${esc(s.id)}" ${(o.system_id||x.system_id)===s.id?'selected':''}>${esc(s.title)}</option>`).join('')}</select></div><div class="form-row"><label>Module</label><select id="mMod"><option value="">未指定</option>${mods.map(m=>`<option value="${esc(m.id)}" ${(o.module_id||x.module_id)===m.id?'selected':''}>${esc(m.title)}</option>`).join('')}</select></div></div><div class="columns"><div class="form-row"><label>排序</label><input id="mOrder" type="number" value="${esc(o.order??'')}"></div><div class="form-row"><label>隐藏</label><select id="mHidden"><option value="false" ${o.hidden?'':'selected'}>否</option><option value="true" ${o.hidden?'selected':''}>是</option></select></div></div><div class="form-actions"><button class="btn" id="mCancel">取消</button><button class="btn primary" id="mSave">保存并增量刷新</button></div></div></div>`;document.body.insertAdjacentHTML('beforeend',html);$('#mCancel').onclick=()=>$('#modal').remove();$('#mSave').onclick=async()=>{const patch={display_name:$('#mName').value,description:$('#mDesc').value,system_id:$('#mSys').value,module_id:$('#mMod').value,hidden:$('#mHidden').value==='true'};if($('#mOrder').value)patch.order=Number($('#mOrder').value);await api('/api/override',{method:'POST',body:JSON.stringify({entity_key:x._key,patch})});location.reload()}}
function reviewModal(x){const html=`<div class="modal-bg" id="modal"><div class="modal"><h2>提交技术事实纠正</h2><div class="notice">不会直接改 Fact。系统会创建一个待验证 Work Unit，交给 AI + IDEA Index MCP 重新查证。</div><div class="form-row"><label>你认为哪里不对</label><textarea id="rReason"></textarea></div><div class="form-row"><label>你认为正确情况是什么（可选）</label><textarea id="rProposed"></textarea></div><div class="form-actions"><button class="btn" id="rCancel">取消</button><button class="btn primary" id="rSave">创建 Review Work Unit</button></div></div></div>`;document.body.insertAdjacentHTML('beforeend',html);$('#rCancel').onclick=()=>$('#modal').remove();$('#rSave').onclick=async()=>{const res=await api('/api/review',{method:'POST',body:JSON.stringify({entity_key:x._key,scenario_id:x.scenario_id,reason:$('#rReason').value,proposed_change:$('#rProposed').value})});alert('已创建 '+res.work_unit_id);$('#modal').remove()}}
async function render(){editable=await detect();const r=route();let html;if(r==='/')html=home();else if(r==='/chains')html=chains();else if(r==='/systems')html=systems();else if(r==='/data')html=data();else if(r==='/gaps')html=gaps();else if(r.startsWith('/compare/')){const parts=r.split('/').filter(Boolean);const a=decodeURIComponent(parts[1]||''),b=decodeURIComponent(parts[2]||'');$('#app').innerHTML=shell('<div class="empty">Loading compare…</div>','chains',sideList('Scenarios',C.scenario_catalog));bind();return Promise.all([loadEntity('scenario:'+a),loadEntity('scenario:'+b)]).then(([x,y])=>{$('#app').innerHTML=compareHtml(x,y);bind()})}else if(r.startsWith('/entity/')){const key=decodeURIComponent(r.slice(8));html=shell(entity(key));$('#app').innerHTML=html;bind();return scriptLoad(key,x=>{$('#app').innerHTML=entityHtml(x);bind();if(x&&editable){const eb=$('#editBtn');if(eb)eb.onclick=()=>editModal(x);const rb=$('#reviewBtn');if(rb)rb.onclick=()=>reviewModal(x)}})}else html=home();$('#app').innerHTML=html;bind()}
window.addEventListener('hashchange',render);render();})();
'''
