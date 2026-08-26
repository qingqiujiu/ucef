"""Adaptive, offline-first HTML projections of the shared UCEF fact graph.

The shell and diagram geometry are deterministic. Business facts determine
which components appear; empty sections and invented narratives never render.
"""

from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .core import safe_name
from .graph import KnowledgeGraphService


CSS = r"""
:root{color-scheme:light;--paper:#f6f5f1;--panel:#fff;--ink:#182331;--quiet:#687483;--line:#e2e5e8;--navy:#12243a;--accent:#e65f24;--blue:#245caa;--green:#197557;--yellow:#96620a;--red:#aa3f36;--soft-blue:#eef4fb;--soft-orange:#fff4ed;--soft-green:#eaf6f0;--shadow:0 10px 36px rgba(22,35,49,.065)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.65 Inter,"Aptos","Microsoft YaHei UI","Noto Sans SC",sans-serif}a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}button,input{font:inherit}.top{position:sticky;top:0;z-index:8;display:flex;align-items:center;gap:24px;padding:14px 7vw;color:white;background:var(--navy);border-bottom:3px solid var(--accent)}.top a{color:#d6e1ee}.brand{color:white!important;font-weight:850;letter-spacing:.18em}.edition{font-size:11px;color:#a9bad0}.topnav{display:flex;gap:18px;flex-wrap:wrap}.layout{max-width:1560px;margin:0 auto;padding:30px 42px 90px}.hero{position:relative;overflow:hidden;border:1px solid var(--line);border-left:5px solid var(--accent);border-radius:12px;padding:26px 30px;background:var(--panel);box-shadow:var(--shadow)}.hero:after{position:absolute;right:-35px;top:-100px;width:210px;height:210px;border:30px solid #f4f0e8;border-radius:50%;content:"";opacity:.8}.hero>*{position:relative;z-index:1}.eyebrow{text-transform:uppercase;letter-spacing:.15em;font-size:11px;font-weight:800;color:var(--accent)}h1,h2,h3,h4{line-height:1.25;letter-spacing:-.02em}h1{font-size:32px;margin:8px 0}h2{font-size:21px;margin:0}h3{font-size:17px;margin:0}.lead,.quiet{color:var(--quiet)}.lead{font-size:15px;max-width:960px}.chips{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.chip{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--line);border-radius:999px;padding:3px 10px;color:var(--quiet);background:#fff;font-size:12px}.chip.p0,.chip.warn{color:var(--yellow);background:#fff7e8;border-color:#f4dfae}.chip.good{color:var(--green);background:var(--soft-green);border-color:#cde6d8}.chip.bad{color:var(--red);background:#fdf0ee;border-color:#f0d1cd}.chip.blue{color:var(--blue);background:var(--soft-blue);border-color:#d4e1f2}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:12px;margin-top:20px}.metric{padding:12px 15px;background:#fbfaf8;border:1px solid var(--line);border-radius:9px}.metric strong{display:block;font-size:24px;line-height:1.15}.metric span{font-size:12px;color:var(--quiet)}.section{margin-top:30px}.section-head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:13px}.section-head p{margin:3px 0 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}.card,.component,.diagram,.rail,.notice{background:var(--panel);border:1px solid var(--line);border-radius:11px;box-shadow:var(--shadow)}.card{display:block;padding:18px;color:var(--ink)}.card h3{margin:11px 0 5px}.card p{margin:5px 0 10px;color:var(--quiet)}.card:hover{border-color:#b8cce7;text-decoration:none}.scenario-grid{display:grid;grid-template-columns:minmax(0,1fr) 295px;gap:20px;align-items:start}.story{display:grid;gap:13px}.component{padding:18px 20px}.component-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}.component-copy{margin:7px 0;color:var(--quiet)}.component-meta{margin-top:10px}.step-line{position:relative;margin:2px 0 2px 14px;padding:5px 10px 5px 17px;border-left:2px solid #d4dae0;color:var(--quiet)}.step-line:before{position:absolute;left:-5px;top:13px;width:8px;height:8px;border-radius:50%;background:#9ca9b7;content:""}.branches{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-top:13px}.branch{padding:12px;border:1px solid var(--line);border-left:3px solid #b4becb;border-radius:8px;background:#fbfbfa}.branch.active{border-left-color:var(--green);background:#f2faf6}.branch.pending{border-left-color:#daa02e;background:#fffaf0}.branch.inactive{opacity:.6}.branch h4{margin:5px 0}.branch p{margin:4px 0;font-size:12px;color:var(--quiet)}.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:13px}.fact{padding:10px;background:#f8f9fa;border-radius:7px}.fact span{display:block;font-size:11px;color:var(--quiet)}.fact strong{overflow-wrap:anywhere}.table{width:100%;margin-top:12px;border-collapse:collapse}.table th,.table td{text-align:left;padding:8px 9px;border-bottom:1px solid var(--line);font-size:12px}.table th{color:var(--quiet);font-weight:650}.rail{position:sticky;top:83px;padding:16px}.rail h3{margin-bottom:10px}.rail-section+.rail-section{margin-top:20px;padding-top:17px;border-top:1px solid var(--line)}.rail-list{display:grid;gap:8px}.notice{padding:13px 16px;border-left:4px solid #daa02e;background:#fffbf3}.notice p{margin:5px 0 0}.diagram{padding:15px 16px;overflow:auto}.diagram svg{display:block;max-width:100%;height:auto}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}.tab,.button{padding:6px 11px;border:1px solid var(--line);border-radius:7px;color:var(--quiet);background:#fff;cursor:pointer}.tab.active,.button.active{color:var(--blue);border-color:#cbdcf0;background:var(--soft-blue)}.tab-panel[hidden]{display:none}.search{width:min(360px,100%);padding:9px 12px;border:1px solid var(--line);border-radius:8px;background:#fff}.lineage{display:grid;gap:9px}.lineage-item{padding:12px;border-left:3px solid var(--blue);background:#f7f9fc;border-radius:0 7px 7px 0}.lineage-item.copy{border-left-color:#b8c0ca;color:var(--quiet);background:#f8f8f7}.lineage-route{display:block;font-size:12px;color:var(--quiet);overflow-wrap:anywhere}.evidence-link{padding:0;border:0;color:var(--blue);background:transparent;cursor:pointer}.drawer{position:fixed;z-index:12;top:0;right:0;width:min(480px,100vw);height:100vh;padding:20px;overflow:auto;background:#fff;border-left:1px solid var(--line);box-shadow:-12px 0 44px #12243a20}.drawer[hidden]{display:none}.drawer-close{float:right}.crumb{margin-bottom:13px;color:var(--quiet)}.empty{padding:18px;color:var(--quiet);border:1px dashed var(--line);border-radius:9px}.pair{display:flex;justify-content:space-between;gap:8px;padding:6px 0}.pair strong{text-align:right;overflow-wrap:anywhere}.footer{margin-top:30px;color:var(--quiet);font-size:12px}.mono{font-family:ui-monospace,"Cascadia Code",Consolas,monospace;font-size:12px;overflow-wrap:anywhere}.response{margin-top:11px;padding-top:10px;border-top:1px dashed var(--line)}@media(max-width:900px){.top{padding:12px 18px;gap:12px}.layout{padding:20px 16px 60px}.scenario-grid{grid-template-columns:1fr}.rail{position:static}.hero{padding:20px}.hero:after{display:none}h1{font-size:27px}}@media(max-width:600px){.top{align-items:flex-start}.topnav{gap:9px}.edition{display:none}.section-head{display:block}.section-head .search{margin-top:10px}.component-head{display:block}.component-head>.chips{margin-top:9px}}
"""


SCRIPT = r"""
document.addEventListener('click',function(event){
  const tab=event.target.closest('[data-tab]');
  if(tab){const box=tab.closest('[data-tab-group]');box.querySelectorAll('[data-tab]').forEach(item=>item.classList.toggle('active',item===tab));box.querySelectorAll('[data-panel]').forEach(item=>item.hidden=item.dataset.panel!==tab.dataset.tab);}
  const filter=event.target.closest('[data-branch-view]');
  if(filter){const box=filter.closest('[data-decision]');box.querySelectorAll('[data-branch-view]').forEach(item=>item.classList.toggle('active',item===filter));box.querySelectorAll('[data-branch]').forEach(item=>item.hidden=filter.dataset.branchView==='active'&&item.dataset.branch==='INACTIVE');}
  const evidence=event.target.closest('[data-evidence]');
  if(evidence){const drawer=document.getElementById('evidence-drawer');const item=(window.UCEF_EVIDENCE||{})[evidence.dataset.evidence]||{name:'代码证据引用',key:evidence.dataset.evidence,summary:evidence.dataset.evidence};if(drawer){drawer.querySelector('[data-evidence-title]').textContent=item.name||item.key||'代码证据';drawer.querySelector('[data-evidence-content]').textContent=[item.source_id,item.path,item.symbol,item.lines,item.summary].filter(Boolean).join('\n');drawer.hidden=false;}}
  if(event.target.closest('[data-close-drawer]')){const drawer=document.getElementById('evidence-drawer');if(drawer)drawer.hidden=true;}
});
document.addEventListener('input',function(event){if(!event.target.matches('[data-search]'))return;const value=event.target.value.trim().toLowerCase();const scope=document.getElementById(event.target.dataset.search);if(!scope)return;scope.querySelectorAll('[data-searchable]').forEach(card=>card.hidden=value&&!card.textContent.toLowerCase().includes(value));});
document.addEventListener('keydown',function(event){if(event.key==='Escape'){const drawer=document.getElementById('evidence-drawer');if(drawer)drawer.hidden=true;}});
"""


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def compact(value: Any, limit: int = 150) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def status_label(value: Any) -> str:
    return {
        "ACTIVE": "已命中", "INACTIVE": "未命中", "POSSIBLE": "可能路径",
        "CONFIG_UNRESOLVED": "配置待确认", "CONFIG_CONFIRMED": "配置已确认",
        "SOURCE_CONFIRMED": "代码已确认", "COMPLETE": "已完成", "PARTIAL": "部分完成",
        "STOPPED": "已暂停", "CLOSED": "已关闭", "RESOLVED": "已解决",
    }.get(str(value or ""), str(value or "已记录"))


def badge(value: Any, *, priority: str | None = None) -> str:
    text = str(priority or value or "")
    css = "p0" if text == "P0" else "good" if text in {"ACTIVE", "COMPLETE", "CONFIG_CONFIRMED", "RESOLVED"} else "warn" if text in {"CONFIG_UNRESOLVED", "PARTIAL", "POSSIBLE"} else "bad" if text in {"ERROR", "BLOCKED"} else "blue" if text == "P1" else ""
    return f'<span class="chip {css}">{esc(text if priority else status_label(text))}</span>'


def attrs(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("attributes")
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [] if value is None else [value]


class AdaptiveExperience:
    """Render scenario/system/module/decision/field/table projections."""

    def __init__(self, store: Any, config: dict[str, Any], output: Path):
        self.store = store
        self.config = config
        self.output = output
        self.graph = KnowledgeGraphService(store, config=config)
        self.graphs: dict[str, dict[str, Any]] = {}

    def build(self, scenarios: Iterable[dict[str, Any]]) -> dict[str, Any]:
        graph_scenarios = []
        for scenario in scenarios:
            scenario_id = str(scenario["scenario_id"])
            count = self.store.conn.execute(
                "SELECT COUNT(*) FROM knowledge_memberships WHERE scenario_id=?", (scenario_id,)
            ).fetchone()[0]
            if count or self.graph.latest_session(scenario_id):
                graph_scenarios.append(scenario)
                self.graphs[scenario_id] = self.graph.scenario_graph(scenario_id)
        if not graph_scenarios:
            return {"adaptive_scenarios": 0, "perspectives": 0}

        for dirname in ("systems", "modules", "decisions", "fields", "tables"):
            (self.output / dirname).mkdir(parents=True, exist_ok=True)
        for scenario in graph_scenarios:
            scenario_id = scenario["scenario_id"]
            target = self.output / "scenarios" / f"{safe_name(scenario_id)}.html"
            target.write_text(self._scenario_page(self.graphs[scenario_id]), encoding="utf-8")

        # Rendering is program-side work, not model context. Never apply the
        # bounded model-retrieval limit to perspective-page generation.
        all_entities = [
            json.loads(row["payload_json"])
            for row in self.store.conn.execute(
                "SELECT payload_json FROM knowledge_entities ORDER BY "
                "CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END,updated_at DESC"
            ).fetchall()
        ]
        perspective_types = {
            "SYSTEM": ("systems", self._system_page),
            "MODULE": ("modules", self._module_page),
            "DECISION": ("decisions", self._decision_page),
            "FIELD": ("fields", self._field_page),
            "TABLE": ("tables", self._table_page),
        }
        page_count = 0
        for item in all_entities:
            route = perspective_types.get(item["entity_type"])
            if not route:
                continue
            directory, renderer = route
            target = self.output / directory / f"{safe_name(item['entity_id'])}.html"
            target.write_text(renderer(item), encoding="utf-8")
            page_count += 1

        self._write("index.html", self._index_page(list(scenarios), all_entities))
        self._write("systems.html", self._collection_page("系统视角", "SYSTEM", all_entities))
        self._write("fields.html", self._collection_page("字段视角", "FIELD", all_entities))
        self._write("decisions.html", self._collection_page("决策视角", "DECISION", all_entities))
        return {"adaptive_scenarios": len(graph_scenarios), "perspectives": page_count + 4}

    def _write(self, name: str, body: str) -> None:
        (self.output / name).write_text(body, encoding="utf-8")

    def _href(self, entity: dict[str, Any], root: str = "../") -> str:
        directory = {
            "SYSTEM": "systems", "MODULE": "modules", "DECISION": "decisions",
            "FIELD": "fields", "TABLE": "tables",
        }.get(entity.get("entity_type"))
        return f"{root}{directory}/{safe_name(str(entity['entity_id']))}.html" if directory else "#"

    def _scenario_href(self, scenario: dict[str, Any], root: str = "../") -> str:
        return f"{root}scenarios/{safe_name(str(scenario['scenario_id']))}.html"

    def _shell(self, title: str, body: str, *, root: str = "../", graph: dict[str, Any] | None = None) -> str:
        evidence = {}
        if graph:
            for item in graph["entities"]:
                if item["entity_type"] == "EVIDENCE":
                    detail = attrs(item)
                    evidence[item["entity_id"]] = {
                        "name": item["display_name"], "key": item["logical_key"],
                        "source_id": detail.get("source_id"), "path": detail.get("path") or detail.get("file"),
                        "symbol": detail.get("symbol"),
                        "lines": detail.get("line_range") or detail.get("lines") or (
                            f'{detail.get("line_start")}–{detail.get("line_end")}'
                            if detail.get("line_start") and detail.get("line_end") else detail.get("line_start")
                        ),
                        "summary": item.get("summary"),
                    }
        encoded = json.dumps(evidence, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
        site_title = esc((self.config.get("site") or {}).get("title") or "UCEF 业务知识图谱")
        return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · {site_title}</title><style>{CSS}</style></head><body><header class="top"><a class="brand" href="{root}index.html">UCEF</a><span class="edition">1.0 · BUSINESS ATLAS</span><nav class="topnav"><a href="{root}index.html">场景</a><a href="{root}systems.html">系统</a><a href="{root}decisions.html">决策</a><a href="{root}fields.html">字段</a><a href="{root}artifacts.html">制品</a></nav></header><main class="layout">{body}<footer class="footer">UCEF 1.0 · 统一事实图生成 · 仅展示已记录的代码证据与配置状态</footer></main><aside id="evidence-drawer" class="drawer" hidden><button class="button drawer-close" data-close-drawer>关闭</button><div class="eyebrow">Code evidence</div><h2 data-evidence-title></h2><pre class="mono" data-evidence-content></pre></aside><script>window.UCEF_EVIDENCE={encoded};{SCRIPT}</script></body></html>'''

    def _groups(self, graph: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in graph["entities"]:
            result[item["entity_type"]].append(item)
        return result

    def _related(self, graph: dict[str, Any], item: dict[str, Any], relation: str, outgoing: bool = True) -> list[dict[str, Any]]:
        lookup = {entry["entity_id"]: entry for entry in graph["entities"]}
        key = "source_entity_id" if outgoing else "target_entity_id"
        other = "target_entity_id" if outgoing else "source_entity_id"
        edges = [edge for edge in graph["edges"] if edge.get("relation_type") == relation and edge.get(key) == item["entity_id"]]
        return [lookup[edge[other]] for edge in edges if edge.get(other) in lookup]

    def _entity_link(self, item: dict[str, Any], *, root: str = "../", label: str | None = None) -> str:
        text = esc(label or item["display_name"])
        href = self._href(item, root)
        return f'<a href="{esc(href)}">{text}</a>' if href != "#" else text

    def _scenario_card(self, scenario: dict[str, Any], *, root: str = "") -> str:
        graph = self.graphs.get(str(scenario["scenario_id"]))
        coverage = graph.get("coverage", {}) if graph else {}
        state = (graph.get("session") or {}).get("status") if graph else scenario.get("status")
        chips = []
        for key, label in (("decisions", "个决策"), ("interactions", "次系统交互"), ("priority_fields", "个关键字段")):
            if coverage.get(key):
                chips.append(f'<span class="chip">{coverage[key]} {label}</span>')
        if coverage.get("unresolved_configurations"):
            chips.append(f'<span class="chip warn">{coverage["unresolved_configurations"]} 项配置待确认</span>')
        return f'''<a class="card" data-searchable href="{self._scenario_href(scenario, root)}"><div class="chips">{badge(state)}<span class="chip mono">{esc(scenario['scenario_id'])}</span></div><h3>{esc(scenario.get('name') or scenario['scenario_id'])}</h3><p>{esc(compact(scenario.get('business_goal') or scenario.get('business_operation'), 130))}</p><div class="chips">{''.join(chips)}</div></a>'''

    def _entity_card(self, item: dict[str, Any], *, root: str = "") -> str:
        scenarios = self.graph.entity_scenarios(item["entity_id"])
        tags = badge(item.get("priority"), priority=item.get("priority")) if item.get("priority") == "P0" else ""
        if item.get("status") == "CONFIG_UNRESOLVED":
            tags += badge(item["status"])
        description = item.get("summary") or attrs(item).get("business_effect") or item["logical_key"]
        return f'''<a class="card" data-searchable href="{self._href(item, root)}"><div class="chips">{tags}<span class="chip">{len(scenarios)} 个场景</span></div><h3>{esc(item['display_name'])}</h3><p>{esc(compact(description, 145))}</p><span class="mono quiet">{esc(item['logical_key'])}</span></a>'''

    def _index_page(self, scenarios: list[dict[str, Any]], entities: list[dict[str, Any]]) -> str:
        counts = Counter(item["entity_type"] for item in entities)
        unresolved = sum(item["entity_type"] == "CONFIG" and item.get("status") != "CONFIG_CONFIRMED" for item in entities)
        metrics = self._metrics([
            (len(scenarios), "业务场景"), (counts["SYSTEM"], "关联系统"),
            (counts["DECISION"], "业务决策"), (counts["FIELD"], "关联字段"),
            (unresolved, "待确认配置"),
        ])
        hero = f'''<section class="hero"><div class="eyebrow">One graph · many reading paths</div><h1>业务不是一份长报告，而是一张可以探索的地图</h1><p class="lead">从场景读完整链路，也可以从系统、关键字段、分支决策或数据库表反向进入；所有视角引用同一份业务事实。</p>{metrics}</section>'''
        cards = "".join(self._scenario_card(item) for item in scenarios)
        body = hero + self._section("业务场景", "按业务目标进入，按需展开条件、调用与字段变化。", f'<div id="scenario-search" class="cards">{cards}</div>', searchable="scenario-search")
        systems = [item for item in entities if item["entity_type"] == "SYSTEM"]
        if systems:
            body += self._section("系统与模块", "同一系统在不同业务场景中保持统一身份。", f'<div class="cards">{"".join(self._entity_card(item) for item in systems[:8])}</div>')
        priority = [item for item in entities if item["entity_type"] == "FIELD" and item.get("priority") == "P0"]
        if priority:
            body += self._section("关键字段", "保留语义变化，折叠无意义的 DTO 复制。", f'<div class="cards">{"".join(self._entity_card(item) for item in priority[:8])}</div>')
        return self._shell("业务地图", body, root="")

    def _collection_page(self, title: str, kind: str, entities: list[dict[str, Any]]) -> str:
        selected = [item for item in entities if item["entity_type"] == kind]
        descriptions = {
            "SYSTEM": "跨场景查看系统职责、对外调用、内部模块和关联关键字段。",
            "FIELD": "从请求、决策、落库到外部报文追踪关键字段；普通复制自动折叠。",
            "DECISION": "识别真正改变业务行为的判断条件、可选路径和待确认生产配置。",
        }
        hero = f'<section class="hero"><div class="eyebrow">Shared business entities</div><h1>{esc(title)}</h1><p class="lead">{esc(descriptions[kind])}</p></section>'
        cards = "".join(self._entity_card(item) for item in selected) or '<div class="empty">目前没有已确认的相关事实。</div>'
        return self._shell(title, hero + self._section(f"已记录 {len(selected)} 项", "支持按名称、逻辑标识和摘要过滤。", f'<div id="entity-search" class="cards">{cards}</div>', searchable="entity-search"), root="")

    def _section(self, title: str, description: str, body: str, *, searchable: str | None = None) -> str:
        control = f'<input class="search" type="search" placeholder="搜索当前视角" data-search="{esc(searchable)}">' if searchable else ""
        return f'<section class="section"><header class="section-head"><div><h2>{esc(title)}</h2><p class="quiet">{esc(description)}</p></div>{control}</header>{body}</section>'

    def _metrics(self, pairs: Iterable[tuple[Any, str]]) -> str:
        return '<div class="metrics">' + "".join(f'<div class="metric"><strong>{esc(value)}</strong><span>{esc(label)}</span></div>' for value, label in pairs) + "</div>"

    def _scenario_page(self, graph: dict[str, Any]) -> str:
        scenario = graph["scenario"]
        groups = self._groups(graph)
        coverage = graph["coverage"]
        session = graph.get("session") or {}
        trigger = scenario.get("trigger") or {}
        chips = badge(session.get("status") or scenario.get("status"))
        if trigger.get("symbol"):
            chips += f'<span class="chip mono">{esc(trigger["symbol"])}</span>'
        hero = f'''<div class="crumb"><a href="../index.html">业务场景</a> / {esc(scenario.get('name'))}</div><section class="hero"><div class="eyebrow">Scenario · adaptive business story</div><h1>{esc(scenario.get('name') or scenario['scenario_id'])}</h1><p class="lead">{esc(session.get('digest') or scenario.get('business_goal') or '')}</p><div class="chips">{chips}</div>{self._metrics([(coverage['systems'],'关联系统'),(coverage['decisions'],'决策点'),(coverage['branches'],'业务分支'),(coverage['priority_fields'],'关键字段'),(coverage['interactions'],'系统交互')])}</section>'''
        notices = ""
        unresolved = [item for item in groups.get("CONFIG", []) if item.get("status") != "CONFIG_CONFIRMED"]
        if unresolved:
            keys = "、".join(item["logical_key"] for item in unresolved)
            notices += f'<div class="notice section"><strong>生产配置尚未确认</strong><p class="quiet">{esc(keys)}。当前只展示代码存在的可选分支，不猜测生产环境实际取值；后续可通过 PADB 或人工证据补齐。</p></div>'
        gaps = [item for item in groups.get("GAP", []) if item.get("status") not in {"CLOSED", "RESOLVED"}]
        if gaps:
            notices += "".join(f'<div class="notice section"><strong>待继续确认：{esc(item["display_name"])}</strong><p>{esc(item.get("summary"))}</p></div>' for item in gaps)
        diagrams = self._diagrams(graph)
        story = self._story(graph)
        rail = self._scenario_rail(graph)
        narrative = self._section("业务链路", "组件只在事实需要时出现：决策、外部调用、落库和关键字段各有自己的表达。", f'<div class="scenario-grid"><div class="story">{story}</div>{rail}</div>')
        return self._shell(str(scenario.get("name")), hero + notices + diagrams + narrative, graph=graph)

    def _diagrams(self, graph: dict[str, Any]) -> str:
        groups = self._groups(graph)
        choices: list[tuple[str, str, str]] = []
        if groups.get("INTERACTION") or (len(groups.get("SYSTEM", [])) > 1 and groups.get("PERSISTENCE")):
            choices.append(("sequence", "系统时序", self._sequence_svg(graph)))
        if groups.get("DECISION") or len(groups.get("BUSINESS_STEP", [])) >= 3:
            choices.append(("flow", "业务流程", self._flow_svg(graph)))
        if len(groups.get("SYSTEM", [])) >= 3:
            choices.append(("systems", "系统关系", self._systems_svg(graph)))
        if len(groups.get("STATE", [])) >= 2:
            choices.append(("states", "状态流转", self._states_svg(graph)))
        choices = [item for item in choices if item[2]]
        if not choices:
            return ""
        tabs = "".join(f'<button class="tab {"active" if index == 0 else ""}" data-tab="{esc(key)}">{esc(label)}</button>' for index, (key, label, _) in enumerate(choices))
        panels = "".join(f'<div class="diagram tab-panel" data-panel="{esc(key)}" {"hidden" if index else ""}>{svg}</div>' for index, (key, _, svg) in enumerate(choices))
        return self._section("换一种方式看链路", "图由统一事实自动排版；任何新增分支、交互或命名更新都会同步反映。", f'<div data-tab-group><div class="tabs">{tabs}</div>{panels}</div>')

    def _story(self, graph: dict[str, Any]) -> str:
        groups = self._groups(graph)
        items = [item for item in graph["entities"] if item["entity_type"] in {"BUSINESS_STEP", "DECISION", "INTERACTION", "PERSISTENCE"}]
        order = {"BUSINESS_STEP": 0, "DECISION": 1, "INTERACTION": 2, "PERSISTENCE": 3}
        items.sort(key=lambda item: (float(item.get("sequence_no") or attrs(item).get("sequence_no") or 0), order[item["entity_type"]], item["display_name"]))
        components = []
        for item in items:
            kind = item["entity_type"]
            if kind == "DECISION":
                components.append(self._decision_component(item, graph))
            elif kind == "INTERACTION":
                components.append(self._interaction_component(item, graph))
            elif kind == "PERSISTENCE":
                components.append(self._persistence_component(item, graph))
            else:
                detail = attrs(item)
                if detail.get("handoff") or detail.get("importance") == "LOW" or item.get("priority") == "P2":
                    components.append(f'<div class="step-line"><strong>{esc(item["display_name"])}</strong> {esc(item.get("summary"))}</div>')
                else:
                    chips = self._evidence(item) + (badge(item.get("priority"), priority="P0") if item.get("priority") == "P0" else "")
                    components.append(f'<article class="component"><div class="eyebrow">业务动作</div><div class="component-head"><h3>{esc(item["display_name"])}</h3><div class="chips">{chips}</div></div>{self._copy(item.get("summary"))}{self._attribute_facts(detail, ("business_effect", "symbol", "condition"))}</article>')
        fields = [item for item in groups.get("FIELD", []) if item.get("priority") == "P0"]
        if fields:
            components.append(self._priority_fields_component(fields, graph["scenario"]["scenario_id"]))
        return "".join(components) or '<div class="empty">分析会话已建立；主模型记录第一个业务里程碑后，这里会自动组织成可阅读链路。</div>'

    def _copy(self, value: Any) -> str:
        return f'<p class="component-copy">{esc(value)}</p>' if value else ""

    def _attribute_facts(self, detail: dict[str, Any], names: Iterable[str]) -> str:
        labels = {"business_effect": "业务影响", "symbol": "代码入口", "condition": "触发条件", "protocol": "调用方式", "operation": "操作", "timeout": "超时", "topic": "消息主题", "table": "数据库表", "mode": "写入方式", "environment": "环境"}
        facts = []
        for name in names:
            value = detail.get(name)
            if isinstance(value, (dict, list)) or value is None or value == "":
                continue
            facts.append(f'<div class="fact"><span>{esc(labels.get(name,name))}</span><strong>{esc(compact(value,110))}</strong></div>')
        return f'<div class="facts">{"".join(facts)}</div>' if facts else ""

    def _decision_component(self, item: dict[str, Any], graph: dict[str, Any]) -> str:
        detail = attrs(item)
        branches = self._related(graph, item, "BRANCHES_TO")
        configs = self._related(graph, item, "DEPENDS_ON")
        branch_cards = []
        for branch in branches:
            data = attrs(branch)
            state = str(branch.get("status") or "POSSIBLE")
            css = "active" if state == "ACTIVE" else "inactive" if state == "INACTIVE" else "pending" if state == "CONFIG_UNRESOLVED" else ""
            condition = data.get("condition") or data.get("when")
            effect = data.get("business_effect") or branch.get("summary")
            destinations = self._related(graph, branch, "LEADS_TO")
            target = f'<p>后续：{"、".join(self._entity_link(entry) for entry in destinations)}</p>' if destinations else ""
            branch_cards.append(f'<div class="branch {css}" data-branch="{esc(state)}">{badge(state)}<h4>{esc(branch["display_name"])}</h4>{f"<p>条件：{esc(condition)}</p>" if condition else ""}{f"<p>{esc(effect)}</p>" if effect else ""}{target}</div>')
        config_chips = "".join(f'<span class="chip {"warn" if cfg.get("status")!="CONFIG_CONFIRMED" else "good"}">{esc(cfg["logical_key"])} · {esc(status_label(cfg.get("status")))}</span>' for cfg in configs)
        toggle = '<div class="chips"><button class="button active" data-branch-view="all">全部分支</button><button class="button" data-branch-view="active">当前可能路径</button></div>' if any(branch.get("status") == "INACTIVE" for branch in branches) else ""
        heading = self._entity_link(item)
        return f'''<article class="component" data-decision="{esc(item['entity_id'])}"><div class="eyebrow">业务决策 · {len(branches)} 条路径</div><div class="component-head"><h3>{heading}</h3><div class="chips">{badge(item.get('priority'),priority='P0') if item.get('priority')=='P0' else ''}{self._evidence(item)}</div></div>{self._copy(item.get('summary'))}{self._attribute_facts(detail,('condition','business_effect','symbol'))}<div class="component-meta chips">{config_chips}</div>{f'<div class="component-meta">{toggle}</div>' if toggle else ''}{f'<div class="branches">{"".join(branch_cards)}</div>' if branch_cards else ''}</article>'''

    def _interaction_component(self, item: dict[str, Any], graph: dict[str, Any]) -> str:
        detail = attrs(item)
        sources = self._related(graph, item, "INITIATES", outgoing=False)
        targets = self._related(graph, item, "TARGETS")
        source = "、".join(self._entity_link(entry) for entry in sources) or esc(detail.get("source_system") or detail.get("caller") or "当前系统")
        target = "、".join(self._entity_link(entry) for entry in targets) or esc(detail.get("target_system") or detail.get("callee") or "外部系统")
        request = self._mapping_table(detail.get("request_fields") or detail.get("request_mapping"), "请求字段", "来源 / 含义")
        response = self._mapping_table(detail.get("response_fields") or detail.get("response_mapping"), "响应字段", "消费位置 / 业务含义")
        response_block = f'<div class="response"><strong>返回值如何被使用</strong>{response}</div>' if response else ""
        return f'''<article class="component"><div class="eyebrow">系统交互</div><div class="component-head"><h3>{esc(item['display_name'])}</h3><div class="chips">{self._evidence(item)}</div></div>{self._copy(item.get('summary'))}<div class="component-meta"><strong>{source}</strong> → <strong>{target}</strong></div>{self._attribute_facts(detail,('protocol','operation','condition','timeout','topic'))}{request}{response_block}</article>'''

    def _mapping_table(self, value: Any, left: str, right: str) -> str:
        if isinstance(value, dict):
            rows = list(value.items())
        elif isinstance(value, list):
            rows = []
            for item in value:
                if isinstance(item, dict):
                    rows.append((item.get("field") or item.get("column") or item.get("target") or item.get("name"), item.get("source") or item.get("meaning") or item.get("value") or item.get("summary")))
                else:
                    rows.append((item, ""))
        else:
            return ""
        rows = [(key, value) for key, value in rows if key]
        if not rows:
            return ""
        body = "".join(f'<tr><td class="mono">{esc(key)}</td><td>{esc(compact(value,140))}</td></tr>' for key, value in rows[:20])
        return f'<table class="table"><thead><tr><th>{esc(left)}</th><th>{esc(right)}</th></tr></thead><tbody>{body}</tbody></table>'

    def _persistence_component(self, item: dict[str, Any], graph: dict[str, Any]) -> str:
        detail = attrs(item)
        tables = self._related(graph, item, "WRITES_TABLE")
        table = "、".join(self._entity_link(entry) for entry in tables) or esc(detail.get("table") or "数据库")
        mappings = self._mapping_table(detail.get("field_mappings") or detail.get("columns") or detail.get("mappings"), "落库字段", "来源 / 处理规则")
        return f'''<article class="component"><div class="eyebrow">数据库落库</div><div class="component-head"><h3>{esc(item['display_name'])}</h3><div class="chips">{self._evidence(item)}</div></div>{self._copy(item.get('summary'))}<div class="component-meta">目标表：<strong>{table}</strong></div>{self._attribute_facts(detail,('operation','condition','symbol'))}{mappings}</article>'''

    def _priority_fields_component(self, fields: list[dict[str, Any]], scenario_id: str) -> str:
        lines = []
        for field in fields:
            projection = self.graph.field_projection(scenario_id, field["entity_id"])
            changes = sum(event["kind"] == "SEMANTIC_CHANGE" for event in projection["events"])
            collapsed = projection["collapsed_copy_count"]
            detail = f"{changes} 次语义变化" + (f"，折叠 {collapsed} 次普通复制" if collapsed else "")
            lines.append(f'<div class="pair"><strong>{self._entity_link(field)}</strong><span class="quiet">{esc(detail)}</span></div>')
        return f'<article class="component"><div class="eyebrow">P0 关键字段</div><h3>重点字段从哪里来、改变了什么、去了哪里</h3><div class="component-meta">{"".join(lines)}</div></article>'

    def _evidence(self, item: dict[str, Any]) -> str:
        values = item.get("evidence_refs") or []
        return "".join(f'<button class="evidence-link chip" data-evidence="{esc(value)}">查看代码证据</button>' for value in values[:2])

    def _scenario_rail(self, graph: dict[str, Any]) -> str:
        groups = self._groups(graph)
        sections = []
        systems = groups.get("SYSTEM", [])
        if systems:
            sections.append(f'<div class="rail-section"><h3>关联系统</h3><div class="rail-list">{"".join(self._entity_link(item) for item in systems)}</div></div>')
        fields = sorted(groups.get("FIELD", []), key=lambda item: (item.get("priority", "P2"), item["display_name"]))
        if fields:
            entries = "".join(f'<div>{badge(item.get("priority"),priority="P0") if item.get("priority")=="P0" else ""} {self._entity_link(item)}</div>' for item in fields[:12])
            sections.append(f'<div class="rail-section"><h3>相关字段</h3><div class="rail-list">{entries}</div></div>')
        tables = groups.get("TABLE", [])
        if tables:
            sections.append(f'<div class="rail-section"><h3>数据库表</h3><div class="rail-list">{"".join(self._entity_link(item) for item in tables)}</div></div>')
        states = groups.get("STATE", [])
        if states:
            state_labels = "".join(f'<span class="chip">{esc(item["display_name"])}</span>' for item in states[:10])
            sections.append(f'<div class="rail-section"><h3>业务状态</h3><div class="chips">{state_labels}</div></div>')
        session = graph.get("session") or {}
        if session:
            pairs = [(session.get("milestone_count", 0), "已记录里程碑"), (session.get("estimated_tokens_used", 0), "估算分析 token")]
            rows = "".join(f'<div class="pair"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>' for value, label in pairs)
            sections.append(f'<div class="rail-section"><h3>探索进度</h3>{rows}</div>')
        return f'<aside class="rail">{"".join(sections)}</aside>' if sections else ""

    def _entity_hero(self, item: dict[str, Any], title: str, description: str | None = None) -> str:
        scenarios = self.graph.entity_scenarios(item["entity_id"])
        priority = badge(item.get("priority"), priority="P0") if item.get("priority") == "P0" else ""
        return f'''<div class="crumb"><a href="../index.html">业务地图</a> / {esc(title)}</div><section class="hero"><div class="eyebrow">{esc(title)} · shared identity</div><h1>{esc(item['display_name'])}</h1><p class="lead">{esc(description or item.get('summary') or item['logical_key'])}</p><div class="chips">{priority}{badge(item.get('status'))}<span class="chip">{len(scenarios)} 个关联场景</span><span class="chip mono">{esc(item['logical_key'])}</span></div></section>'''

    def _related_scenarios(self, item: dict[str, Any]) -> str:
        scenarios = self.graph.entity_scenarios(item["entity_id"])
        if not scenarios:
            return ""
        cards = "".join(self._scenario_card(scenario, root="../") for scenario in scenarios)
        return self._section("关联业务场景", "不同阅读视角始终跳回同一份业务事实。", f'<div class="cards">{cards}</div>')

    def _system_page(self, item: dict[str, Any]) -> str:
        scenarios = self.graph.entity_scenarios(item["entity_id"])
        neighbors = self.graph.entity_neighbors(item["entity_id"])
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for neighbor in neighbors:
            groups[neighbor["entity_type"]].append(neighbor)
        counts = Counter(entry["entity_type"] for scenario in scenarios for entry in self.graphs.get(scenario["scenario_id"], {}).get("entities", []))
        hero = self._entity_hero(item, "系统视角") + self._metrics([(len(scenarios),"关联场景"),(len(groups['MODULE']),"直属模块"),(len(groups['INTERACTION']),"直接交互"),(counts['DECISION'],"关联决策")])
        body = hero
        if groups.get("SYSTEM"):
            body += self._section("协作系统", "跨系统调用关系来自已记录的交互事实。", f'<div class="cards">{"".join(self._entity_card(entry,root="../") for entry in groups["SYSTEM"])}</div>')
        if groups.get("MODULE"):
            body += self._section("系统模块", "模块与系统共享全局稳定身份。", f'<div class="cards">{"".join(self._entity_card(entry,root="../") for entry in groups["MODULE"])}</div>')
        interactions = groups.get("INTERACTION", [])
        if interactions:
            cards = "".join(f'<article class="component"><h3>{esc(entry["display_name"])}</h3>{self._copy(entry.get("summary"))}{self._attribute_facts(attrs(entry),("protocol","operation","condition"))}</article>' for entry in interactions)
            body += self._section("系统边界交互", "只展示影响本系统边界的请求、响应或消息。", f'<div class="story">{cards}</div>')
        body += self._related_scenarios(item)
        return self._shell(item["display_name"], body)

    def _module_page(self, item: dict[str, Any]) -> str:
        neighbors = self.graph.entity_neighbors(item["entity_id"])
        system = [entry for entry in neighbors if entry["entity_type"] == "SYSTEM"]
        body = self._entity_hero(item, "模块视角")
        if system:
            body += self._section("所属系统", "模块名称与职责在所有场景中保持统一。", f'<div class="cards">{"".join(self._entity_card(entry,root="../") for entry in system)}</div>')
        return self._shell(item["display_name"], body + self._related_scenarios(item))

    def _decision_page(self, item: dict[str, Any]) -> str:
        scenarios = self.graph.entity_scenarios(item["entity_id"])
        body = self._entity_hero(item, "决策视角")
        if scenarios:
            graph = self.graphs.get(scenarios[0]["scenario_id"]) or self.graph.scenario_graph(scenarios[0]["scenario_id"])
            body += self._section("判断条件与分支", "代码存在的分支与生产环境实际命中的分支明确区分。", self._decision_component(item, graph))
        return self._shell(item["display_name"], body + self._related_scenarios(item), graph=graph if scenarios else None)

    def _field_page(self, item: dict[str, Any]) -> str:
        scenarios = self.graph.entity_scenarios(item["entity_id"])
        body = self._entity_hero(item, "字段视角", item.get("summary") or "追踪请求输入、关键判断、语义转换、数据库落点与外部系统边界。")
        for scenario in scenarios:
            projection = self.graph.field_projection(scenario["scenario_id"], item["entity_id"])
            events = projection["events"]
            if not events:
                continue
            visual = self._lineage_svg(projection)
            rows = []
            for event in events:
                if event["kind"] == "COLLAPSED_COPY":
                    rows.append(f'<div class="lineage-item copy"><strong>{esc(event["summary"])}</strong><span class="lineage-route">{esc(event.get("source"))} → {esc(event.get("target"))}</span></div>')
                else:
                    condition = f' · 条件：{esc(event["condition"])}' if event.get("condition") else ""
                    rows.append(f'<div class="lineage-item"><strong>{esc(event.get("operation") or "语义变化")}</strong> {esc(event.get("summary"))}{condition}<span class="lineage-route">{esc(event.get("source"))} → {esc(event.get("target"))}</span></div>')
            diagram = f'<div class="diagram">{visual}</div>' if visual else ""
            intro = f'{projection["raw_event_count"]} 个原始流转点；其中 {projection["collapsed_copy_count"]} 个普通复制被折叠。'
            body += self._section(f'{scenario.get("name") or scenario["scenario_id"]} · 字段旅程', intro, diagram + f'<div class="lineage section">{"".join(rows)}</div>')
        return self._shell(item["display_name"], body + self._related_scenarios(item))

    def _table_page(self, item: dict[str, Any]) -> str:
        neighbors = self.graph.entity_neighbors(item["entity_id"])
        writes = [entry for entry in neighbors if entry["entity_type"] == "PERSISTENCE"]
        body = self._entity_hero(item, "数据库表视角")
        if writes:
            parts = []
            for entry in writes:
                detail = attrs(entry)
                mapping = self._mapping_table(detail.get("field_mappings") or detail.get("columns") or detail.get("mappings"),"数据库字段","业务来源 / 处理规则")
                parts.append(f'<article class="component"><h3>{esc(entry["display_name"])}</h3>{self._copy(entry.get("summary"))}{self._attribute_facts(detail,("operation","condition","symbol"))}{mapping}</article>')
            body += self._section("落库路径", "按场景理解这个表为什么被写入，以及关键列从哪里来。", f'<div class="story">{"".join(parts)}</div>')
        return self._shell(item["display_name"], body + self._related_scenarios(item))

    def _svg(self, width: int, height: int, content: str, name: str) -> str:
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(name)}"><defs><marker id="arrow-{esc(name)}" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8Z" fill="#68809a"/></marker></defs><rect width="{width}" height="{height}" rx="8" fill="#fff"/>{content}</svg>'''

    def _svg_text(self, x: float, y: float, value: Any, *, size: int = 12, color: str = "#33445a", anchor: str = "middle", weight: int = 450) -> str:
        return f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="{color}" font-size="{size}" font-weight="{weight}" font-family="Inter,Microsoft YaHei UI,Noto Sans SC,sans-serif">{esc(compact(value,44))}</text>'

    def _sequence_svg(self, graph: dict[str, Any]) -> str:
        groups = self._groups(graph)
        systems = groups.get("SYSTEM", [])[:8]
        if len(systems) < 2:
            return ""
        interactions = sorted(groups.get("INTERACTION", []), key=lambda item: float(item.get("sequence_no") or 0))[:18]
        if not interactions:
            return ""
        gap = max(155, min(220, 1050 // max(1, len(systems) - 1)))
        width = max(560, gap * (len(systems) - 1) + 170)
        height = 112 + len(interactions) * 78
        positions = {item["entity_id"]: 85 + index * gap for index, item in enumerate(systems)}
        chunks = []
        for item in systems:
            x = positions[item["entity_id"]]
            chunks.append(f'<a href="{esc(self._href(item))}"><rect x="{x-66}" y="16" width="132" height="35" rx="7" fill="#eef4fb" stroke="#d5e1f0"/>{self._svg_text(x,38,item["display_name"],size=11,weight=650)}</a><line x1="{x}" y1="57" x2="{x}" y2="{height-22}" stroke="#d8dfe8" stroke-dasharray="4 5"/>')
        for index, item in enumerate(interactions):
            callers = self._related(graph, item, "INITIATES", outgoing=False)
            targets = self._related(graph, item, "TARGETS")
            if not callers or not targets or callers[0]["entity_id"] not in positions or targets[0]["entity_id"] not in positions:
                continue
            x1, x2 = positions[callers[0]["entity_id"]], positions[targets[0]["entity_id"]]
            if x1 == x2:
                continue
            y = 91 + index * 78
            dashed = ' stroke-dasharray="5 4"' if str(attrs(item).get("protocol", "")).upper() in {"MQ", "EVENT", "ASYNC", "KAFKA"} else ""
            chunks.append(self._svg_text((x1+x2)/2,y-9,item["display_name"],size=11))
            chunks.append(f'<line x1="{x1}" y1="{y}" x2="{x2-7 if x2>x1 else x2+7}" y2="{y}" stroke="#68809a" stroke-width="1.6" marker-end="url(#arrow-sequence)"{dashed}/>')
            response = attrs(item).get("response_summary") or attrs(item).get("response_effect")
            if response:
                chunks.append(f'<line x1="{x2}" y1="{y+24}" x2="{x1+7 if x2>x1 else x1-7}" y2="{y+24}" stroke="#a4afbd" stroke-dasharray="4 4" marker-end="url(#arrow-sequence)"/>')
                chunks.append(self._svg_text((x1+x2)/2,y+39,response,size=10,color="#718094"))
        return self._svg(width, height, "".join(chunks), "sequence")

    def _flow_svg(self, graph: dict[str, Any]) -> str:
        items = [item for item in graph["entities"] if item["entity_type"] in {"BUSINESS_STEP", "DECISION", "INTERACTION", "PERSISTENCE"}]
        items.sort(key=lambda item: float(item.get("sequence_no") or 0))
        items = items[:16]
        if len(items) < 2:
            return ""
        height = 55
        chunks = []
        width, center = 860, 430
        for index, item in enumerate(items):
            kind = item["entity_type"]
            connect_next = True
            if kind == "DECISION":
                branches = self._related(graph, item, "BRANCHES_TO")[:4]
                chunks.append(f'<a href="{esc(self._href(item))}"><rect x="{center-150}" y="{height}" width="300" height="40" rx="8" fill="#fff5eb" stroke="#efcfb8"/>{self._svg_text(center,height+25,item["display_name"],weight=650)}</a>')
                if branches:
                    branch_targets = [
                        {target["entity_id"] for target in self._related(graph, branch, "LEADS_TO")}
                        for branch in branches
                    ]
                    common_targets = set.intersection(*branch_targets) if branch_targets and all(branch_targets) else set()
                    explicit_rejoin = attrs(item).get("rejoins_at") or attrs(item).get("merge_target")
                    confirmed_rejoin = bool(common_targets or explicit_rejoin)
                    branch_y = height + 69
                    spacing = min(190, 730 // max(1, len(branches)))
                    start = center - spacing * (len(branches)-1) / 2
                    for branch_index, branch in enumerate(branches):
                        x = start + branch_index * spacing
                        state = branch.get("status")
                        fill = "#eaf6f0" if state == "ACTIVE" else "#fff8e9" if state == "CONFIG_UNRESOLVED" else "#f3f5f7"
                        chunks.append(f'<path d="M{center} {height+40}L{x} {branch_y}" fill="none" stroke="#9aaabd"/>')
                        chunks.append(f'<rect x="{x-79}" y="{branch_y}" width="158" height="34" rx="7" fill="{fill}" stroke="#dfe4e9"/>{self._svg_text(x,branch_y+22,branch["display_name"],size=10)}')
                        if confirmed_rejoin:
                            chunks.append(f'<path d="M{x} {branch_y+34}L{center} {branch_y+58}" fill="none" stroke="#aab5c2"/>')
                        else:
                            destinations = self._related(graph, branch, "LEADS_TO")
                            if destinations:
                                chunks.append(self._svg_text(x,branch_y+49,destinations[0]["display_name"],size=9,color="#6c7b8b"))
                    if confirmed_rejoin:
                        height = branch_y + 58
                    else:
                        chunks.append(self._svg_text(center,branch_y+70,"分支后续尚未确认汇合",size=10,color="#96620a"))
                        height = branch_y + 76
                        connect_next = False
                else:
                    height += 53
            else:
                palette = {"BUSINESS_STEP": ("#eef4fb", "#d1e0f1"), "INTERACTION": ("#f0f7f6", "#d1e4de"), "PERSISTENCE": ("#f3f0fb", "#ded7ef")}
                fill, stroke = palette[kind]
                chunks.append(f'<rect x="{center-160}" y="{height}" width="320" height="38" rx="8" fill="{fill}" stroke="{stroke}"/>{self._svg_text(center,height+24,item["display_name"],size=11,weight=600)}')
                height += 38
            if index < len(items)-1 and connect_next:
                chunks.append(f'<line x1="{center}" y1="{height+2}" x2="{center}" y2="{height+25}" stroke="#8092a6" marker-end="url(#arrow-flow)"/>')
                height += 30
            elif index < len(items)-1:
                height += 18
        return self._svg(width, height + 32, "".join(chunks), "flow")

    def _systems_svg(self, graph: dict[str, Any]) -> str:
        systems = self._groups(graph).get("SYSTEM", [])[:7]
        if len(systems) < 3:
            return ""
        center = systems[0]
        positions = {center["entity_id"]: (420, 175)}
        points = [(180, 60), (420, 48), (665, 66), (685, 275), (425, 302), (175, 276)]
        for item, point in zip(systems[1:], points):
            positions[item["entity_id"]] = point
        chunks = []
        for edge in graph["edges"]:
            if edge.get("relation_type") != "INTERACTS_WITH":
                continue
            x1y1, x2y2 = positions.get(edge.get("source_entity_id")), positions.get(edge.get("target_entity_id"))
            if not x1y1 or not x2y2:
                continue
            x1,y1 = x1y1
            x2,y2 = x2y2
            chunks.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#a4b4c6" stroke-width="1.5"/>')
            label = attrs(edge).get("label") or edge.get("label")
            if label:
                chunks.append(self._svg_text((x1+x2)/2,(y1+y2)/2-5,label,size=9,color="#6c7b8b"))
        for item in systems:
            x,y = positions[item["entity_id"]]
            main = item["entity_id"] == center["entity_id"]
            fill = "#12243a" if main else "#eef4fb"
            text = "#fff" if main else "#33445a"
            chunks.append(f'<a href="{esc(self._href(item))}"><rect x="{x-77}" y="{y-20}" width="154" height="40" rx="9" fill="{fill}" stroke="#d3ddea"/>{self._svg_text(x,y+5,item["display_name"],size=11,color=text,weight=650)}</a>')
        return self._svg(850, 360, "".join(chunks), "systems")

    def _lineage_svg(self, projection: dict[str, Any]) -> str:
        events = projection.get("events") or []
        if not events:
            return ""
        events = events[:14]
        width = 850
        row_height = 66
        height = 30 + row_height * len(events)
        chunks = []
        for index,event in enumerate(events):
            y = 35 + index * row_height
            plain = event["kind"] == "COLLAPSED_COPY"
            fill, stroke = ("#f4f5f5", "#dfe3e5") if plain else ("#eef4fb", "#d3e0ef")
            chunks.append(f'<rect x="32" y="{y}" width="780" height="43" rx="7" fill="{fill}" stroke="{stroke}"/>')
            label = event.get("summary") if plain else event.get("operation")
            chunks.append(self._svg_text(45,y+17,label,size=11,anchor="start",weight=650))
            route = f'{event.get("source") or "?"} → {event.get("target") or "?"}'
            chunks.append(self._svg_text(45,y+34,route,size=10,color="#6e7d8e",anchor="start"))
            if index < len(events)-1:
                chunks.append(f'<line x1="420" y1="{y+44}" x2="420" y2="{y+61}" stroke="#95a5b6" marker-end="url(#arrow-lineage)"/>')
        return self._svg(width, height+25, "".join(chunks), "lineage")

    def _states_svg(self, graph: dict[str, Any]) -> str:
        states = sorted(
            self._groups(graph).get("STATE", []),
            key=lambda item: (float(item.get("sequence_no") or 0), item["display_name"]),
        )[:12]
        if len(states) < 2:
            return ""
        center = 430
        gap = 80
        positions = {item["entity_id"]: 38 + index * gap for index, item in enumerate(states)}
        chunks = []
        transition_types = {"TRANSITIONS_TO", "NEXT_STATE", "STATE_TRANSITION"}
        for edge in graph["edges"]:
            if edge.get("relation_type") not in transition_types:
                continue
            start = positions.get(edge.get("source_entity_id"))
            end = positions.get(edge.get("target_entity_id"))
            if start is None or end is None:
                continue
            if end > start:
                chunks.append(f'<line x1="{center}" y1="{start+36}" x2="{center}" y2="{end-6}" stroke="#68809a" stroke-width="1.5" marker-end="url(#arrow-states)"/>')
            else:
                bend = center + 225
                chunks.append(f'<path d="M{center+140} {start+17}L{bend} {start+17}L{bend} {end+17}L{center+147} {end+17}" fill="none" stroke="#a47d3b" marker-end="url(#arrow-states)"/>')
            label = edge.get("label") or edge.get("condition_ref")
            if label:
                chunks.append(self._svg_text(center+18,(start+end)/2+15,label,size=10,anchor="start",color="#687483"))
        for index,item in enumerate(states):
            y = positions[item["entity_id"]]
            fill = "#eaf6f0" if index == len(states)-1 else "#eef4fb"
            chunks.append(f'<rect x="{center-140}" y="{y}" width="280" height="36" rx="17" fill="{fill}" stroke="#d4e1ed"/>{self._svg_text(center,y+23,item["display_name"],size=11,weight=650)}')
        return self._svg(860, positions[states[-1]["entity_id"]] + 66, "".join(chunks), "states")
