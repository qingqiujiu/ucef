from __future__ import annotations

import html
import json
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .artifacts import ArtifactStore
from .audit import audit_scenario
from .core import safe_name
from .store import FactStore


CSS = r'''
:root{--bg:#eeece5;--paper:#fbfaf5;--card:#fffef9;--ink:#17211f;--muted:#66706d;--line:#cfd3ca;--brand:#0d6a58;--brand-dark:#103d35;--accent:#ed6a32;--good:#146847;--warn:#9a5b06;--bad:#a83329;--soft:#e4f0eb;--grid:#d8d9d0}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background-color:var(--bg);background-image:linear-gradient(#ffffff50 1px,transparent 1px),linear-gradient(90deg,#ffffff50 1px,transparent 1px);background-size:24px 24px;color:var(--ink);font:15px/1.58 "Aptos","Microsoft YaHei UI","Noto Sans SC",sans-serif}h1,h2,h3,.top strong,.metric strong{font-family:"Bahnschrift SemiCondensed","DIN Alternate","Microsoft YaHei UI",sans-serif;letter-spacing:.015em}a{color:var(--brand);text-decoration:none}a:hover{text-decoration:underline}
.top{position:sticky;top:0;z-index:50;background:var(--brand-dark);color:#fff;padding:13px 28px;display:flex;gap:22px;align-items:center;border-bottom:3px solid var(--accent)}.top strong{font-size:21px;letter-spacing:.14em}.top a{color:#dcebe5}.wrap{max-width:1560px;margin:0 auto;padding:24px}.hero,.card,.stage{background:var(--card);border:1px solid var(--line);border-radius:8px;box-shadow:5px 5px 0 #1c302b12}.hero{padding:24px;border-top:5px solid var(--brand)}.hero h1{margin:0 0 8px;font-size:31px}.muted{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:16px}.span4{grid-column:span 4}.span6{grid-column:span 6}.span8{grid-column:span 8}.span12{grid-column:span 12}.card{padding:18px}.card h2,.card h3{margin-top:0}.section{margin-top:24px}.section-title{display:flex;justify-content:space-between;align-items:end;gap:16px;margin:0 0 12px}.section-title h2{margin:0}.section-kicker{text-transform:uppercase;letter-spacing:.16em;font-size:11px;color:var(--brand);font-weight:800}
.chips{display:flex;gap:7px;flex-wrap:wrap}.chip,.badge{border-radius:3px;padding:3px 8px;font-size:12px;background:#e9ece8;color:#34423e;border:1px solid #d5d9d3}.good{background:#e2f1e9;color:var(--good);border-color:#b8d8c8}.warn{background:#fff0d8;color:var(--warn);border-color:#e7ca99}.bad{background:#fde7e3;color:var(--bad);border-color:#e8bbb4}.reuse{background:#e4ebe9;color:#275b51}
.kv{display:grid;grid-template-columns:150px 1fr;gap:8px 14px}.kv b{color:#33413d}.value{white-space:pre-wrap;overflow-wrap:anywhere}.timeline{position:relative;margin-left:18px}.timeline:before{content:"";position:absolute;left:19px;top:28px;bottom:28px;width:2px;background:#b7c7bd}.stage{position:relative;margin:0 0 18px 58px;padding:20px}.stage:before{content:attr(data-n);position:absolute;left:-58px;top:20px;width:40px;height:40px;border-radius:4px;display:grid;place-items:center;background:var(--brand);color:white;font-weight:700;box-shadow:0 0 0 5px var(--bg)}.stage h3{margin:0 0 4px;font-size:19px}.stage-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:14px}.stage-cell{border:1px solid var(--line);border-radius:6px;padding:11px;background:#fbfcf7}.stage-cell b{display:block;margin-bottom:4px;color:#344054}.handoff{margin-top:12px;padding:9px 12px;background:var(--soft);border-radius:5px}.fragment{margin-top:12px;border-left:4px solid var(--brand);padding:10px 12px;background:#edf5f2}.fragment h4{margin:0 0 5px}.why{margin-top:10px;padding:10px 12px;background:#fff4df;border-left:4px solid var(--accent)}
table{width:100%;border-collapse:collapse;background:var(--card)}th,td{padding:10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{background:#e9ece7;color:#34413d;font-size:13px}.scroll{overflow:auto;border:1px solid var(--line);border-radius:6px}.field-group{margin-bottom:20px}.gap{border-left:4px solid var(--bad);padding:10px 12px;background:#fff1ee;margin:8px 0}.evidence{font-family:"Cascadia Code","SFMono-Regular",Consolas,monospace;font-size:12px;background:#eef0eb;border-radius:5px;padding:9px;margin:6px 0;overflow-wrap:anywhere}.empty{padding:18px;color:var(--muted);text-align:center;border:1px dashed var(--line);border-radius:6px}
.scenario-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}.scenario-card{display:block;color:inherit;transition:transform .18s ease,border-color .18s ease}.scenario-card:hover{text-decoration:none;border-color:#7eaa9f;transform:translate(-2px,-2px)}.scenario-card h2{font-size:20px}.footer{padding:30px;text-align:center;color:var(--muted)}select,button,input{font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:5px;background:white}button{background:var(--brand);color:#fff;border-color:var(--brand);cursor:pointer}.compare-controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.overview-grid{display:grid;grid-template-columns:1.25fr .75fr;gap:16px}.business-flow{counter-reset:block;display:grid;gap:16px}.business-block{scroll-margin-top:80px;background:var(--card);border:1px solid var(--line);border-left:6px solid var(--brand);border-radius:8px;padding:20px;box-shadow:4px 4px 0 #1c302b12;transition:border-color .2s ease,transform .2s ease}.business-block.focused{border-color:var(--accent);transform:translateX(3px)}.business-block.outline{border-left-color:#d1912c}.block-head{display:grid;grid-template-columns:48px 1fr auto;gap:13px;align-items:start}.block-number{width:42px;height:42px;border-radius:4px;background:var(--brand-dark);color:#fff;display:grid;place-items:center;font-weight:800}.block-head h2{margin:0 0 4px;font-size:22px}.block-why{margin:13px 0;padding:11px 13px;background:#fff3de;border-radius:5px;border-left:3px solid var(--accent)}.block-contract{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.mini-panel{border:1px solid var(--line);border-radius:6px;padding:12px;background:#f7f8f3}.mini-panel b{display:block;color:#34413d;margin-bottom:5px}.business-steps{margin:14px 0 0;padding-left:24px}.business-steps li{margin:8px 0;padding-left:4px}.cross-cutting{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}.technical-appendix{margin-top:14px;padding:12px;border:1px solid var(--line);border-radius:6px;background:#f3f4ef}
.cockpit-metrics{display:grid;grid-template-columns:repeat(5,minmax(120px,1fr));gap:1px;margin-top:18px;background:var(--line);border:1px solid var(--line)}.metric{background:#f7f6f0;padding:12px}.metric span{display:block;color:var(--muted);font-size:11px;letter-spacing:.08em}.metric strong{font-size:20px}.scenario-console{display:grid;grid-template-columns:220px minmax(0,1fr);gap:18px;align-items:start}.flow-rail{position:sticky;top:72px;max-height:calc(100vh - 90px);overflow:auto;background:var(--card);border:1px solid var(--line);border-radius:8px;box-shadow:4px 4px 0 #1c302b12}.panel-title{padding:13px 14px;border-bottom:1px solid var(--line);background:#e8ebe6}.panel-title h3{margin:0;font-size:17px}.flow-nav{padding:8px}.block-nav{display:grid;grid-template-columns:30px 1fr;gap:8px;align-items:center;width:100%;text-align:left;background:transparent;color:var(--ink);border-color:transparent;margin:2px 0}.block-nav:hover,.block-nav.active{background:var(--soft);border-color:#b6cec6}.block-nav .nav-index{font-family:"Bahnschrift SemiCondensed",sans-serif;color:var(--brand);font-weight:800}.story-canvas{min-width:0}.sequence-board{background:#17231f;color:#eef7f3;border-radius:8px;padding:16px;box-shadow:5px 5px 0 #ed6a3233;overflow:auto}.sequence-board h2{margin:0;color:#fff}.sequence-board .muted{color:#adc0b9}.sequence-board svg{display:block;min-width:720px;width:100%;height:auto;margin-top:14px}.sequence-step{cursor:pointer}.sequence-step:hover path,.sequence-step:hover line{stroke:#fff}.business-value{color:#28332f;overflow-wrap:anywhere}.business-list{margin:0;padding-left:19px}.business-list li{margin:5px 0}.business-kv{display:grid;grid-template-columns:minmax(72px,auto) 1fr;gap:5px 10px;margin:0}.business-kv dt{color:var(--muted);font-size:12px}.business-kv dd{margin:0;min-width:0}.business-empty{color:var(--muted)}.evidence-open{background:#fff;color:var(--brand);border-color:#9ebbb2}.evidence-dialog{position:fixed;inset:0 0 0 auto;width:min(460px,92vw);height:100vh;max-height:none;margin:0;border:0;border-left:1px solid var(--line);padding:0;background:var(--card);color:var(--ink);box-shadow:-18px 0 48px #102f2740}.evidence-dialog::backdrop{background:#102f2745;backdrop-filter:blur(2px)}.dialog-head{position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;gap:16px;align-items:start;padding:16px;border-bottom:1px solid var(--line);background:#e8ebe6}.dialog-head h3{margin:2px 0 0}.dialog-close{background:#fff;color:var(--ink);border-color:var(--line)}.evidence-body{padding:18px}.evidence-body h4{margin:18px 0 6px}.evidence-list{margin:8px 0;padding:0;list-style:none}.evidence-list li{padding:8px 0;border-bottom:1px solid var(--line)}.artifact-link{display:block;padding:9px;border:1px solid var(--line);border-radius:5px;margin:7px 0;background:#f6f7f2}.artifact-link:hover{border-color:var(--brand);text-decoration:none}.artifact-link code{display:block;color:var(--muted);font-size:11px;overflow-wrap:anywhere}
.execution-workspace{display:grid;grid-template-columns:minmax(280px,34%) minmax(420px,1fr) minmax(280px,30%);gap:14px;align-items:start}.execution-panel{background:#fff;border:1px solid var(--line);border-radius:8px;min-width:0;overflow:hidden}.execution-panel>h3{margin:0;padding:14px 16px;border-bottom:1px solid var(--line);background:#e9ece7}.panel-body{padding:12px;max-height:78vh;overflow:auto}.execution-tree,.execution-tree ul{list-style:none;margin:0;padding-left:15px}.execution-tree{padding-left:0}.tree-node{margin:5px 0}.tree-node>summary{cursor:pointer}.tree-leaf{margin:5px 0 5px 18px}.node-select,.field-select,.node-jump{width:100%;text-align:left;background:#fff;color:var(--ink);border-color:transparent;padding:6px 8px}.node-select:hover,.field-select:hover,.node-jump:hover{background:var(--soft);text-decoration:none}.node-select.active,.field-select.active{background:#dcece6;border-color:#9fbfb4;color:#153f36}.node-select.field-hit{box-shadow:inset 3px 0 var(--accent)}.node-type{display:inline-block;min-width:68px;margin-right:6px;color:var(--muted);font-size:11px;font-weight:700}.node-detail,.field-detail{display:none}.node-detail.active,.field-detail.active{display:block}.node-detail h2,.field-detail h3{margin-top:0}.detail-section{margin-top:16px;padding-top:12px;border-top:1px solid var(--line)}.field-path{margin:8px 0;padding-left:20px}.field-path li{margin:7px 0}.field-meta{padding:9px;border:1px solid var(--line);border-radius:6px;margin-bottom:8px}.stage-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px}.stage-summary .card{box-shadow:none;padding:13px}.tree-note{font-size:12px;color:var(--muted);padding:8px 12px;background:#eef3ef;border-radius:5px;margin-bottom:10px}
.artifact-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}.artifact-shell{display:grid;grid-template-columns:300px minmax(0,1fr);gap:16px}.artifact-sidebar{position:sticky;top:72px;align-self:start}.artifact-meta{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px}.artifact-viewer{background:#111916;color:#d9e8e2;border-radius:8px;min-height:620px;overflow:hidden}.artifact-toolbar{position:sticky;top:0;z-index:2;display:flex;gap:8px;padding:12px;background:#1b2a25;border-bottom:1px solid #385048}.artifact-toolbar input{flex:1;background:#f6f8f4}.json-tree{padding:16px;font:13px/1.65 "Cascadia Code",Consolas,monospace;overflow:auto}.json-tree details{margin-left:16px}.json-tree summary{cursor:pointer;color:#c5ddd4}.json-key{color:#8dd6c2}.json-string{color:#f3bd86}.json-number{color:#8eb9ff}.json-boolean{color:#e49be8}.json-null{color:#9ba7a3}.search-results{max-height:220px;overflow:auto}.search-hit{display:block;width:100%;text-align:left;background:#f4f6f1;color:var(--ink);border-color:transparent;margin:3px 0;font:12px/1.4 "Cascadia Code",Consolas,monospace}.search-hit:hover{border-color:var(--brand)}
@media(max-width:1250px){.scenario-console{grid-template-columns:210px minmax(480px,1fr)}.cockpit-metrics{grid-template-columns:repeat(3,1fr)}}
@media(max-width:1100px){.execution-workspace{grid-template-columns:320px 1fr}.execution-panel.field-panel{grid-column:1/-1}.field-panel .panel-body{max-height:none;display:grid;grid-template-columns:260px 1fr;gap:12px}.artifact-shell{grid-template-columns:1fr}.artifact-sidebar{position:relative;top:auto}}
@media(max-width:850px){.span4,.span6,.span8{grid-column:span 12}.stage-grid{grid-template-columns:1fr}.kv{grid-template-columns:1fr}.wrap{padding:14px}.stage{margin-left:48px}.timeline{margin-left:0}.execution-workspace,.scenario-console{grid-template-columns:1fr}.flow-rail{position:relative;top:auto;max-height:none}.flow-nav{display:grid;grid-template-columns:repeat(2,1fr)}.execution-panel.field-panel{grid-column:auto}.field-panel .panel-body{display:block}.panel-body{max-height:none}.cockpit-metrics{grid-template-columns:repeat(2,1fr)}}
@media(max-width:850px){.overview-grid,.cross-cutting,.block-contract{grid-template-columns:1fr}.block-head{grid-template-columns:42px 1fr}.block-head>.chips{grid-column:1/-1}}
'''


def esc(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, indent=2)
    return html.escape(str(value))


FIELD_LABELS = {
    "name": "名称", "type": "类型", "field": "字段", "source": "来源", "origin": "来源",
    "from": "原值", "to": "去向", "detail": "说明", "description": "说明", "business_use": "业务用途",
    "condition": "条件", "selected": "当前选择", "route": "当前路由", "reason": "原因",
    "operation": "动作", "request": "请求", "response": "响应", "result": "结果", "state": "状态",
    "transformation": "转换", "change": "变化", "fields": "涉及字段", "field_effect": "字段影响",
    "system": "外部系统", "target_system": "目标系统", "store": "存储", "table": "数据表",
    "step": "步骤", "action": "处理动作", "processing": "处理过程", "business_reason": "业务原因",
    "business_effect": "业务效果", "expected_output": "预期结果", "outcome": "业务结果",
}

STATUS_LABELS = {
    "COMPLETE": "已完成", "SUMMARY_COMPLETE": "概要已完成", "READABLE_COMPLETE": "可完整阅读",
    "OUTLINE": "待补充", "ANALYZING": "分析中", "PLANNING": "规划中", "EXTRACTING": "分析重点块",
    "FINALIZING": "生成总览", "STOPPED": "已停止", "GAP": "存在缺口", "FAILED": "失败",
    "PENDING": "等待处理", "CLAIMED": "处理中", "SKIPPED": "已跳过", "QUICK": "快速",
    "STANDARD": "标准", "DEEP": "深度", "NEW": "本次新分析", "EXACT_REUSE": "完整复用",
    "PARTIAL_REUSE": "部分复用", "SUMMARY": "概要", "CRITICAL": "重点",
}


def status_text(value: Any) -> str:
    text = str(value or "UNKNOWN")
    return STATUS_LABELS.get(text, text)


def item_dict(value: Any, fallback_key: str = "description") -> dict[str, Any]:
    return value if isinstance(value, dict) else {fallback_key: value}


def item_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    return value if isinstance(value, list) else [value]


def business_value(value: Any, depth: int = 0) -> str:
    if value in (None, "", [], {}):
        return '<span class="business-empty">暂无</span>'
    if isinstance(value, list):
        visible = value[:8]
        suffix = f'<li class="muted">另有 {len(value) - 8} 项，见技术证据</li>' if len(value) > 8 else ""
        return '<ul class="business-list">' + "".join(f"<li>{business_value(item, depth + 1)}</li>" for item in visible) + suffix + "</ul>"
    if isinstance(value, dict):
        visible = [(key, child) for key, child in value.items() if child not in (None, "", [], {})][:10]
        if not visible:
            return '<span class="business-empty">暂无</span>'
        return '<dl class="business-kv">' + "".join(
            f"<dt>{esc(FIELD_LABELS.get(str(key), str(key)))}</dt><dd>{business_value(child, depth + 1)}</dd>"
            for key, child in visible
        ) + "</dl>"
    return f'<span class="business-value">{esc(value)}</span>'


def summary_text(value: Any, max_chars: int = 34) -> str:
    if isinstance(value, dict):
        preferred = next((value.get(key) for key in ("selected", "route", "name", "result", "reason") if value.get(key)), None)
        value = preferred or "已形成判断，详情见业务块"
    elif isinstance(value, list):
        value = "、".join(str(item) for item in value[:3])
    return short_text(value, max_chars)


def preview(value: Any, max_chars: int = 1200) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value or "")
    return text if len(text) <= max_chars else text[:max_chars] + " … [memory-query 查看完整事实]"


def short_text(value: Any, max_chars: int = 34) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if isinstance(value, (dict, list)) else str(value or "")
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def shell(title: str, body: str, relative_root: str = "") -> str:
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{CSS}</style></head><body>
<nav class="top"><strong>UCEF</strong><a href="{relative_root}index.html">业务链路</a><a href="{relative_root}compare.html">横向对比</a><a href="{relative_root}artifacts.html">原始制品</a><a href="{relative_root}memory.html">分析记忆</a></nav>
<main class="wrap">{body}</main><footer class="footer">由 UCEF 已确认事实生成 · 源码位置用于核查，不代替业务说明</footer></body></html>'''


def kv_rows(items: list[tuple[str, Any]]) -> str:
    return '<div class="kv">' + "".join(f"<b>{esc(k)}</b><div class=\"value\">{business_value(v)}</div>" for k, v in items) + "</div>"


def badge(status: str | None) -> str:
    value = status or "UNKNOWN"
    cls = "good" if value in {"COMPLETE", "READABLE_COMPLETE", "CONFIRMED", "SCENARIO_CONFIRMED", "STATIC_VERIFIED"} else "bad" if value in {"INCOMPLETE", "UNKNOWN", "STALE"} else "warn"
    return f'<span class="badge {cls}">{esc(status_text(value))}</span>'


def table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return '<div class="empty">暂无已确认内容</div>'
    head = "".join(f"<th>{esc(x)}</th>" for x in headers)
    body = "".join("<tr>" + "".join(f"<td>{business_value(x)}</td>" for x in row) + "</tr>" for row in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


class DossierSiteBuilder:
    def __init__(self, store: FactStore, config: dict[str, Any], workspace_root: str | Path):
        self.store = store
        self.config = config
        self.workspace_root = Path(workspace_root)
        self.artifacts = ArtifactStore(self.workspace_root)
        output = (config.get("site") or {}).get("output", "site")
        self.output = (Path(output) if Path(output).is_absolute() else self.workspace_root / output).resolve()
        try:
            self.output.relative_to(self.workspace_root.resolve())
        except ValueError as exc:
            raise ValueError(f"Generated site must stay inside UCEF workspace: {self.output}") from exc

    def build(self) -> dict[str, Any]:
        self.output.mkdir(parents=True, exist_ok=True)
        scenario_dir = self.output / "scenarios"
        artifact_dir = self.output / "artifacts"
        scenario_dir.mkdir(parents=True, exist_ok=True)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        scenarios = self.store.list_scenarios()
        dossiers = []
        for scenario in scenarios:
            scenario_id = scenario["scenario_id"]
            dossier = self.store.scenario_dossier(scenario_id)
            if dossier.get("business_blocks"):
                latest_run = (dossier.get("analysis_runs") or [{}])[-1]
                plan_id = latest_run.get("plan_id")
                current_plan = next(
                    (item for item in reversed(dossier.get("scenario_plans") or []) if item.get("plan_id") == plan_id),
                    (dossier.get("scenario_plans") or [None])[-1],
                )
                dossier["current_plan"] = current_plan
                if current_plan:
                    block_index = {str(item.get("block_id")): item for item in dossier["business_blocks"]}
                    dossier["business_blocks"] = [
                        block_index[str(item["block_id"])]
                        for item in current_plan.get("business_blocks") or []
                        if str(item.get("block_id")) in block_index
                    ]
                blocks = dossier["business_blocks"]
                overview = (dossier.get("scenario_overviews") or [{}])[-1]
                completed = all(
                    block.get("status") in {"COMPLETE", "SUMMARY_COMPLETE", "GAP"}
                    for block in blocks
                )
                readable = bool(overview.get("status") == "COMPLETE" and completed)
                audit = {
                    "readability_status": "READABLE_COMPLETE" if readable else "PARTIAL",
                    "dimensions": {
                        "DIRECT_ARTIFACTS": {
                            "status": "PASS" if readable else "PARTIAL",
                            "business_blocks": len(blocks),
                        }
                    },
                    "generated_gaps": [],
                }
            else:
                audit = audit_scenario(self.store, scenario_id, persist=False)
            dossier["audit"] = audit
            dossiers.append(dossier)
            target = scenario_dir / f"{safe_name(scenario_id)}.html"
            target.write_text(self._scenario_page(dossier), encoding="utf-8")
        artifacts = self.artifacts.list_artifacts()
        for artifact in artifacts:
            target = artifact_dir / f"{safe_name(str(artifact.get('artifact_id')))}.html"
            target.write_text(self._artifact_page(artifact), encoding="utf-8")
        (self.output / "index.html").write_text(self._index_page(dossiers), encoding="utf-8")
        (self.output / "compare.html").write_text(self._compare_page(dossiers), encoding="utf-8")
        (self.output / "artifacts.html").write_text(self._artifacts_index_page(artifacts), encoding="utf-8")
        (self.output / "memory.html").write_text(self._memory_page(), encoding="utf-8")
        return {
            "output": str(self.output),
            "scenarios": len(scenarios),
            "artifacts": len(artifacts),
            "files": len(scenarios) + len(artifacts) + 4,
        }

    def _artifact_href(self, artifact: dict[str, Any], relative_root: str = "../") -> str:
        artifact_id = safe_name(str(artifact.get("artifact_id") or "artifact"))
        return f"{relative_root}artifacts/{artifact_id}.html"

    def _artifacts_index_page(self, artifacts: list[dict[str, Any]]) -> str:
        cards = []
        for artifact in artifacts:
            cards.append(f'''<a class="card scenario-card" href="{self._artifact_href(artifact, '')}"><div class="chips"><span class="chip">{esc(artifact.get('kind'))}</span>{badge(artifact.get('redaction_status'))}</div><h2>{esc(artifact.get('artifact_id'))}</h2><p>{esc(artifact.get('source_id') or '非代码配置来源')}</p><div class="muted">{esc(artifact.get('environment'))} · {esc(artifact.get('snapshot_id'))}</div><div class="chips" style="margin-top:12px"><span class="chip">{esc(artifact.get('size_bytes'))} bytes</span><span class="chip">{esc(artifact.get('redacted_value_count'))} 项脱敏</span><span class="chip">{esc(len(artifact.get('scenario_ids') or []))} 个场景</span></div></a>''')
        body = f'''<section class="hero"><div class="section-kicker">Evidence vault</div><h1>原始制品库</h1><p class="muted">配置 JSON 以内容哈希登记，站点只展示脱敏快照。制品独立加载，不进入 Scenario 主页面或模型上下文。</p></section><section class="section artifact-grid">{''.join(cards) if cards else '<div class="empty">尚未登记原始 JSON 制品。使用 artifact-add 添加配置快照。</div>'}</section>'''
        return shell("UCEF 原始制品库", body)

    def _artifact_page(self, artifact: dict[str, Any]) -> str:
        data = json.dumps(
            self.artifacts.read_display_json(artifact),
            ensure_ascii=False,
            separators=(",", ":"),
        ).replace("<", "\\u003c")
        metadata = kv_rows([
            ("制品 ID", artifact.get("artifact_id")),
            ("类型", artifact.get("kind")),
            ("数据源", artifact.get("source_id")),
            ("环境", artifact.get("environment")),
            ("快照", artifact.get("snapshot_id")),
            ("关联场景", artifact.get("scenario_ids")),
            ("原始大小", f"{artifact.get('size_bytes')} bytes"),
            ("原始 SHA-256", artifact.get("content_hash")),
            ("展示 SHA-256", artifact.get("display_hash")),
            ("脱敏", f"{artifact.get('redaction_status')} · {artifact.get('redacted_value_count')} 项"),
            ("采集时间", artifact.get("captured_at")),
            ("来源位置", artifact.get("source_path")),
        ])
        viewer = '''<div class="artifact-viewer"><div class="artifact-toolbar"><input id="artifact-search" type="search" placeholder="搜索 JSON Pointer、键或值"><button id="artifact-download">下载脱敏快照</button></div><div id="artifact-results" class="search-results"></div><div id="json-tree" class="json-tree"></div></div>
<script type="application/json" id="artifact-data">__DATA__</script>
<script>
const ARTIFACT_DATA=JSON.parse(document.getElementById('artifact-data').textContent);
const tree=document.getElementById('json-tree'),results=document.getElementById('artifact-results'),search=document.getElementById('artifact-search');
const pointerKey=k=>String(k).replace(/~/g,'~0').split('/').join('~1');
function primitive(value){const span=document.createElement('span');span.className=value===null?'json-null':typeof value==='string'?'json-string':typeof value==='number'?'json-number':typeof value==='boolean'?'json-boolean':'';span.textContent=value===null?'null':typeof value==='string'?JSON.stringify(value):String(value);return span}
function makeNode(value,key,path,depth){const wrap=document.createElement('div');if(value===null||typeof value!=='object'){if(key!==null){const label=document.createElement('span');label.className='json-key';label.textContent=JSON.stringify(String(key))+': ';wrap.append(label)}wrap.append(primitive(value));return wrap}const details=document.createElement('details');details.dataset.pointer=path;if(depth<2)details.open=true;const summary=document.createElement('summary');const label=key===null?'root':String(key);summary.textContent=`${label} ${Array.isArray(value)?`[${value.length}]`:`{${Object.keys(value).length}}`}`;details.append(summary);let loaded=false;const load=()=>{if(loaded)return;loaded=true;for(const [childKey,child] of Object.entries(value)){const childPath=path+'/'+pointerKey(childKey);details.append(makeNode(child,childKey,childPath,depth+1))}};details.addEventListener('toggle',()=>{if(details.open)load()});if(details.open)load();wrap.append(details);return wrap}
function walk(value,path,query,hits){if(hits.length>=200)return;if(value!==null&&typeof value==='object'){for(const [key,child] of Object.entries(value)){const next=path+'/'+pointerKey(key);if((key+' '+next).toLowerCase().includes(query))hits.push([next,child]);walk(child,next,query,hits);if(hits.length>=200)return}}else if((path+' '+String(value)).toLowerCase().includes(query)){hits.push([path,value])}}
function showHits(){const query=search.value.trim().toLowerCase();results.replaceChildren();if(!query)return;const hits=[];walk(ARTIFACT_DATA,'',query,hits);for(const [path,value] of hits){const button=document.createElement('button');button.className='search-hit';button.textContent=path+' = '+(typeof value==='object'?JSON.stringify(value).slice(0,120):String(value));button.onclick=()=>{search.value=path;showHits()};results.append(button)}if(!hits.length)results.textContent='没有匹配路径或值。'}
tree.append(makeNode(ARTIFACT_DATA,null,'',0));search.addEventListener('input',showHits);const pointer=new URLSearchParams(location.hash.slice(1)).get('pointer');if(pointer){search.value=pointer;showHits()}
document.getElementById('artifact-download').onclick=()=>{const blob=new Blob([JSON.stringify(ARTIFACT_DATA,null,2)+'\\n'],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='artifact-redacted.json';a.click();URL.revokeObjectURL(url)};
</script>'''.replace("__DATA__", data)
        body = f'''<section class="hero"><div class="section-kicker">内容寻址证据</div><div class="chips"><span class="chip">{esc(artifact.get('kind'))}</span>{badge(artifact.get('redaction_status'))}</div><h1>{esc(artifact.get('artifact_id'))}</h1><p>独立加载的配置证据页面；主链路只保存引用和 JSON Pointer。</p></section><section class="section artifact-shell"><aside class="artifact-sidebar"><div class="artifact-meta"><h2>制品信息</h2>{metadata}</div></aside>{viewer}</section>'''
        return shell(str(artifact.get("artifact_id")), body, "../")

    def _memory_page(self) -> str:
        cards = []
        for work_unit in self.store.list_collection("work_units"):
            work_unit_id = str(work_unit.get("work_unit_id"))
            memory = self.store.work_unit_memory(work_unit_id, max_observations=20)
            latest = memory.get("latest_checkpoint") or {}
            observations = memory.get("pending_observations") or []
            rows = [
                [item.get("observation_kind"), item.get("source_id"), item.get("subject_key"), preview(item.get("claim")), item.get("confidence")]
                for item in observations
            ]
            cards.append(f'''<section class="card section"><div class="chips">{badge(work_unit.get('status'))}<span class="chip">{esc(work_unit_id)}</span><span class="chip">{memory.get('checkpoint_count')} 个检查点</span><span class="chip">{memory['observation_counts']['pending_assembly']} 项待装配</span><span class="chip">{memory['observation_counts']['evidenced']} 项已有证据</span><span class="chip">{memory['observation_counts']['assembled']} 项已装配</span></div><h2>{esc(work_unit.get('objective') or work_unit_id)}</h2>{kv_rows([('当前焦点',latest.get('current_focus')),('恢复摘要',latest.get('resume_summary')),('唯一下一探查',latest.get('next_probe')),('未决问题',latest.get('unresolved_questions')),('观察索引',memory.get('observation_index'))])}<h3>最近待装配事实</h3>{table(['类型','数据源','主题','事实','置信度'],rows)}{f'<div class="muted">另有 {memory.get("omitted_pending_observations")} 条未在本页展开，可用 memory-query 检索。</div>' if memory.get('omitted_pending_observations') else ''}</section>''')
        content = f'''<section class="hero"><h1>分析记忆</h1><p class="muted">这里展示未完成工作单元的持久化检查点和待处理观察记录。它们被确认前不会进入业务主叙事。</p></section>{''.join(cards) if cards else '<section class="section empty">尚无检查点。</section>'}'''
        return shell("UCEF 分析记忆", content)

    def _index_page(self, dossiers: list[dict[str, Any]]) -> str:
        cards = []
        for dossier in dossiers:
            scenario = dossier["scenario"]
            audit = dossier["audit"]
            scope = scenario.get("scope") or {}
            cards.append(f'''<a class="card scenario-card" href="scenarios/{safe_name(scenario['scenario_id'])}.html">
<div class="chips">{badge(audit['readability_status'])}<span class="chip">{esc(scope.get('environment'))}</span></div>
<h2>{esc(scenario.get('name'))}</h2><p>{esc(scenario.get('business_goal'))}</p>
<div class="muted">{esc(scenario.get('business_operation'))} · {business_value(scope.get('source_ids') or scope.get('project') or scope.get('repository'))}</div>
<div class="chips" style="margin-top:12px"><span class="chip">{len(dossier.get('business_blocks') or [])} 业务块</span><span class="chip">{len([x for x in dossier.get('business_blocks') or [] if x.get('status') in {'COMPLETE','SUMMARY_COMPLETE'}])} 已完成</span><span class="chip">{len(dossier['execution_nodes'])} 技术证据节点</span><span class="chip">{len([x for x in dossier['gaps'] if x.get('status','OPEN')=='OPEN'])} 缺口</span></div></a>''')
        content = f'''<section class="hero"><h1>{esc((self.config.get('site') or {}).get('title','UCEF 业务执行档案'))}</h1><p class="muted">面向不了解系统的 Java 开发者：从业务目标进入，沿配置路由、字段演化、落库和外部交互阅读完整执行链。</p></section>
<section class="section"><div class="section-title"><h2>业务场景</h2><a href="compare.html">进入横向对比 →</a></div><div class="scenario-list">{''.join(cards) if cards else '<div class="empty">尚无业务场景。请先创建场景并导入第一个业务阶段。</div>'}</div></section>'''
        return shell("UCEF 业务执行档案", content)

    def _scenario_page(self, dossier: dict[str, Any]) -> str:
        if dossier.get("business_blocks"):
            return self._direct_scenario_page(dossier)
        scenario = dossier["scenario"]
        audit = dossier["audit"]
        scope = scenario.get("scope") or {}
        trigger = scenario.get("trigger") or {}

        dimension_badges = "".join(f'<span class="chip">{esc(k)} {badge(v)}</span>' for k, v in audit["dimensions"].items())
        hero = f'''<section class="hero"><div class="chips">{badge(audit['readability_status'])}<span class="chip">{esc(scenario.get('scenario_id'))}</span></div><h1>{esc(scenario.get('name'))}</h1><p>{esc(scenario.get('business_goal'))}</p><div class="chips">{dimension_badges}</div></section>
<section class="section grid"><div class="card span6"><h2>业务入口与结果</h2>{kv_rows([('业务操作',scenario.get('business_operation')),('入口类型',trigger.get('kind')),('入口符号',trigger.get('symbol')),('输入类型',trigger.get('input_type')),('预期结果',scenario.get('expected_outcome'))])}</div><div class="card span6"><h2>适用范围</h2>{kv_rows([('数据源',scope.get('source_ids')),('数据源版本',scope.get('source_revisions')),('环境',scope.get('environment')),('配置快照',scope.get('config_snapshot_id')),('请求约束',scope.get('request_constraints'))])}</div></section>'''

        stage_cards = "".join(
            f'''<div class="card"><div class="chips"><span class="chip">{esc(stage.get('sequence_no'))}</span><span class="chip">{esc(stage.get('stage_type'))}</span>{badge(stage.get('status'))}</div><h3>{esc(stage.get('name'))}</h3><p>{esc(stage.get('business_purpose'))}</p><div class="muted">{esc(stage.get('why_current'))}</div></div>'''
            for stage in dossier["trace_stages"]
        )
        stages = f'''<section class="section"><div class="section-title"><h2>业务主链</h2><span class="muted">先说明发生什么和为什么；每个阶段的实现细节在下一层展开</span></div><div class="stage-summary">{stage_cards if stage_cards else '<div class="empty">尚未形成业务阶段。</div>'}</div></section>'''

        implementation = self._implementation_layers(dossier)
        execution_workspace = self._execution_workspace(dossier)
        execution = f'''<section class="section"><details><summary><b>展开完整方法执行树与字段联动证据</b>（用于代码核查，不作为默认业务导航）</summary><div style="margin-top:12px">{execution_workspace}</div></details></section>'''

        field_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for step in dossier["field_lineage_steps"]:
            field_groups[str(step.get("canonical_field"))].append(step)
        field_html = "".join(f'''<div class="field-group"><h3>{esc(name)}</h3>{table(['顺序','方法步骤','角色','来源','操作/表达式','目标','前序','空值/类型','业务用途'],[[x.get('sequence_no'),x.get('execution_node_id'),x.get('lineage_role'),x.get('source'),f"{x.get('operation')} · {x.get('expression') or x.get('transformation') or ''}",x.get('target'),x.get('previous_step_ids'),f"{x.get('null_behavior') or ''} · {x.get('data_type_before') or ''}→{x.get('data_type_after') or ''}",x.get('business_use')] for x in steps])}</div>''' for name, steps in field_groups.items())
        fields = f'''<section class="section"><details><summary><b>展开字段全生命周期总表</b>（树内右栏提供按字段联动视图）</summary><div style="margin-top:12px">{field_html if field_html else '<div class="empty">尚无字段溯源；审计会将关键字段标记为缺口。</div>'}</div></details></section>'''

        persistence_html = "".join(f'''<div class="card span6"><div class="chips">{badge(x.get('status'))}<span class="chip">{esc(x.get('source_id'))}</span><span class="chip">{esc(x.get('operation'))}</span></div><h3>{esc(x.get('store'))}</h3><p>{esc(x.get('business_effect'))}</p>{kv_rows([('执行条件',x.get('condition')),('事务上下文',x.get('transaction_context')),('业务键',x.get('key_fields'))])}{table(['目标字段','值来源','转换','业务用途'],[[m.get('target'),m.get('value_source'),m.get('transformation'),m.get('business_use')] for m in x.get('mappings') or []])}</div>''' for x in dossier["persistence_effects"])
        persistence_section = f'''<section class="section"><div class="section-title"><h2>持久化影响</h2></div><div class="grid">{persistence_html if persistence_html else '<div class="empty span12">当前链路没有已确认的持久化动作。</div>'}</div></section>'''

        external_html = "".join(self._external_card(x) for x in dossier["external_interactions"])
        external_section = f'''<section class="section"><div class="section-title"><h2>外部系统交互</h2></div><div class="grid">{external_html if external_html else '<div class="empty span12">当前链路没有已确认的外部交互。</div>'}</div></section>'''

        open_gaps = [x for x in dossier["gaps"] if x.get("status", "OPEN") == "OPEN"]
        gap_html = "".join(f'''<div class="gap"><div class="chips"><span class="badge bad">{esc(x.get('severity'))}</span><span class="chip">{esc(x.get('category'))}</span></div><b>{esc(x.get('question'))}</b><div class="muted">建议：{esc(x.get('suggested_work_type'))}</div></div>''' for x in open_gaps)
        gaps = f'''<section class="section"><div class="section-title"><h2>已知缺口</h2><span class="muted">缺失内容不会被静默隐藏</span></div>{gap_html if gap_html else '<div class="card">没有开放缺口。</div>'}</section>'''

        return shell(str(scenario.get("name")), hero + stages + implementation + execution + fields + persistence_section + external_section + gaps, "../")

    def _sequence_diagram(
        self,
        scenario: dict[str, Any],
        blocks: list[dict[str, Any]],
        plan: dict[str, Any],
    ) -> str:
        scope = scenario.get("scope") or {}
        trigger = scenario.get("trigger") or {}
        service_label = str(
            ((scope.get("source_ids") or [None])[0])
            or str(trigger.get("symbol") or "业务服务").split("#", 1)[0]
        )
        raw_messages: list[dict[str, Any]] = [{
            "from": "调用方",
            "to": service_label,
            "label": trigger.get("symbol") or scenario.get("business_operation") or "发起请求",
            "kind": "request",
            "block_id": "",
        }]
        boundary_labels: list[str] = []

        def add_boundary(label: Any) -> str:
            value = str(label or "未命名边界")
            if value not in boundary_labels:
                boundary_labels.append(value)
            return value

        for block in blocks:
            block_id = str(block.get("block_id") or "")
            external = item_list(block.get("external_calls"))
            persistence = item_list(block.get("persistence"))
            if not external and not persistence:
                raw_messages.append({
                    "from": service_label,
                    "to": service_label,
                    "label": f"{block.get('sequence_no')} · {block.get('title')}",
                    "kind": "internal",
                    "block_id": block_id,
                })
            for raw_interaction in external:
                interaction = item_dict(raw_interaction, "operation")
                target = add_boundary(interaction.get("system") or interaction.get("target_system"))
                raw_messages.append({
                    "from": service_label,
                    "to": target,
                    "label": f"{block.get('title')} · {interaction.get('operation') or '调用'}",
                    "kind": "request",
                    "block_id": block_id,
                })
                raw_messages.append({
                    "from": target,
                    "to": service_label,
                    "label": interaction.get("response") or "返回结果",
                    "kind": "response",
                    "block_id": block_id,
                })
            for raw_effect in persistence:
                effect = item_dict(raw_effect, "operation")
                target = add_boundary(effect.get("store") or effect.get("table") or "数据存储")
                raw_messages.append({
                    "from": service_label,
                    "to": target,
                    "label": f"{block.get('title')} · {effect.get('operation') or '写入'}",
                    "kind": "persistence",
                    "block_id": block_id,
                })
        raw_messages.append({
            "from": service_label,
            "to": "调用方",
            "label": plan.get("terminal_outcome") or scenario.get("expected_outcome") or "返回业务结果",
            "kind": "response",
            "block_id": "",
        })

        visible_boundaries = boundary_labels[:5]
        collapsed = len(boundary_labels) > len(visible_boundaries)
        participants = list(dict.fromkeys(
            ["调用方", service_label] + visible_boundaries + (["其他边界"] if collapsed else [])
        ))

        def visible_target(label: str) -> str:
            if label in participants:
                return label
            return "其他边界" if collapsed else label

        messages = [
            {**message, "from": visible_target(str(message["from"])), "to": visible_target(str(message["to"]))}
            for message in raw_messages[:20]
        ]
        if len(raw_messages) > 20:
            messages.append({
                "from": service_label,
                "to": service_label,
                "label": f"另有 {len(raw_messages) - 20} 条交互在业务块中展开",
                "kind": "internal",
                "block_id": "",
            })

        width = max(760, 120 + 155 * (len(participants) - 1))
        height = 112 + 58 * len(messages)
        xs = {
            label: 60 + index * ((width - 120) / max(1, len(participants) - 1))
            for index, label in enumerate(participants)
        }
        parts = [
            f'''<svg viewBox="0 0 {width} {height}" role="img" aria-label="业务时序图"><defs><marker id="ucef-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#f2b37e"/></marker></defs>'''
        ]
        for label, x in xs.items():
            parts.append(f'''<rect x="{x - 58:.1f}" y="8" width="116" height="36" rx="4" fill="#e8f2ed" stroke="#74a697"/><text x="{x:.1f}" y="31" text-anchor="middle" fill="#173f36" font-size="12" font-weight="700">{esc(short_text(label, 18))}</text><line x1="{x:.1f}" y1="44" x2="{x:.1f}" y2="{height - 24}" stroke="#69847c" stroke-width="1" stroke-dasharray="5 5"/>''')
        for index, message in enumerate(messages):
            y = 76 + index * 58
            source_x = xs[str(message["from"])]
            target_x = xs[str(message["to"])]
            block_id = esc(message.get("block_id") or "")
            css_class = "sequence-step" if message.get("block_id") else "sequence-message"
            label = esc(short_text(message.get("label"), 42))
            if source_x == target_x:
                loop_direction = 1 if source_x < width - 320 else -1
                box_x = source_x + 54 if loop_direction > 0 else source_x - 304
                text_x = box_x + 10
                parts.append(f'''<g class="{css_class}" data-block="{block_id}" tabindex="0"><path d="M {source_x:.1f} {y} h {46 * loop_direction} v 23 h {-46 * loop_direction}" fill="none" stroke="#f2b37e" stroke-width="1.6" marker-end="url(#ucef-arrow)"/><rect x="{box_x:.1f}" y="{y - 11}" width="250" height="24" rx="4" fill="#21332d" stroke="#49675e"/><text x="{text_x:.1f}" y="{y + 5}" fill="#e9f1ee" font-size="11">{label}</text></g>''')
            else:
                direction = 1 if target_x > source_x else -1
                dash = ' stroke-dasharray="5 4"' if message.get("kind") == "response" else ""
                text_x = (source_x + target_x) / 2
                parts.append(f'''<g class="{css_class}" data-block="{block_id}" tabindex="0"><line x1="{source_x + 8 * direction:.1f}" y1="{y}" x2="{target_x - 8 * direction:.1f}" y2="{y}" stroke="#f2b37e" stroke-width="1.6"{dash} marker-end="url(#ucef-arrow)"/><rect x="{text_x - 112:.1f}" y="{y - 24}" width="224" height="19" rx="3" fill="#17231f"/><text x="{text_x:.1f}" y="{y - 10}" text-anchor="middle" fill="#e8f1ed" font-size="10.5">{label}</text></g>''')
        parts.append("</svg>")
        return "".join(parts)

    def _direct_scenario_page(self, dossier: dict[str, Any]) -> str:
        scenario = dossier["scenario"]
        plan = dossier.get("current_plan") or (dossier.get("scenario_plans") or [{}])[-1]
        run = (dossier.get("analysis_runs") or [{}])[-1]
        blocks = sorted(dossier.get("business_blocks") or [], key=lambda item: float(item.get("sequence_no") or 0))
        block_ids = [str(block.get("block_id")) for block in blocks]
        overview = next(
            (
                item for item in reversed(dossier.get("scenario_overviews") or [])
                if [str(value) for value in item.get("ordered_block_ids") or []] == block_ids
            ),
            {},
        )
        scope = scenario.get("scope") or {}
        trigger = scenario.get("trigger") or {}
        one_sentence = overview.get("one_sentence") or scenario.get("business_goal") or "业务骨架正在形成"
        selected_route = overview.get("selected_route") or "尚未完成最终选路总结"
        completed_count = len([x for x in blocks if x.get("status") in {"COMPLETE", "SUMMARY_COMPLETE"}])
        open_gaps = list(overview.get("open_gaps") or []) + [x for x in dossier.get("gaps") or [] if x.get("status", "OPEN") == "OPEN"]
        artifacts = self.artifacts.list_artifacts(str(scenario.get("scenario_id")))
        hero = f'''<section class="hero"><div class="section-kicker">场景总览</div><div class="chips">{badge(overview.get('status') or run.get('status') or 'ANALYZING')}<span class="chip">{esc(scenario.get('scenario_id'))}</span><span class="chip">{esc(status_text(run.get('mode') or 'DIRECT'))}</span></div><h1>{esc(scenario.get('name'))}</h1><p>{esc(one_sentence)}</p><div class="cockpit-metrics"><div class="metric"><span>运行环境</span><strong>{esc(scope.get('environment'))}</strong></div><div class="metric"><span>当前选路</span><strong>{esc(summary_text(selected_route, 24))}</strong></div><div class="metric"><span>业务块完成度</span><strong>{completed_count}/{len(blocks)}</strong></div><div class="metric"><span>关键字段</span><strong>{esc(len(plan.get('critical_fields') or []))}</strong></div><div class="metric"><span>缺口 / 原始制品</span><strong>{len(open_gaps)} / {len(artifacts)}</strong></div></div></section>'''

        nav = "".join(f'''<button class="block-nav" data-block="{esc(block.get('block_id'))}"><span class="nav-index">{index:02d}</span><span>{esc(block.get('title'))}</span></button>''' for index, block in enumerate(blocks, start=1))
        block_html = "".join(self._business_block_card(index, block) for index, block in enumerate(blocks, start=1))
        sequence = self._sequence_diagram(scenario, blocks, plan)
        artifact_links = "".join(f'''<a class="artifact-link" href="{self._artifact_href(item)}"><b>{esc(item.get('kind'))}</b><code>{esc(item.get('artifact_id'))} · {esc(item.get('environment'))}</code></a>''' for item in artifacts)
        console = f'''<section class="section scenario-console"><aside class="flow-rail"><div class="panel-title"><div class="section-kicker">业务主线</div><h3>按执行顺序阅读</h3></div><div class="flow-nav">{nav or '<div class="empty">尚无业务块</div>'}</div></aside><div class="story-canvas"><div class="sequence-board"><div class="section-kicker">自动生成</div><h2>业务时序图</h2><p class="muted">根据已提交的业务块、外部调用和持久化事实生成；点击交互可定位到对应业务块。</p>{sequence}</div><section class="section"><div class="section-title"><div><div class="section-kicker">业务说明</div><h2>业务执行过程</h2></div><span class="muted">先读业务结论；方法和源码依据按需打开</span></div><div class="business-flow">{block_html}</div></section></div><dialog class="evidence-dialog" id="evidence-dialog"><div class="dialog-head"><div><div class="section-kicker">技术依据</div><h3 id="drawer-title">业务块依据</h3></div><button class="dialog-close" id="drawer-close" type="button">关闭</button></div><div class="evidence-body"><p id="drawer-why" class="muted"></p><h4>关键判断</h4><div id="drawer-decision"></div><h4>方法与源码位置</h4><ul id="drawer-methods" class="evidence-list"></ul><details><summary>查看证据引用</summary><div id="drawer-refs" class="evidence"></div></details><h4>场景原始制品</h4>{artifact_links or '<div class="empty">尚未登记配置 JSON。</div>'}</div></dialog></section>'''

        field_rows = []
        for raw_item in item_list(overview.get("key_field_journeys")):
            item = item_dict(raw_item, "journey")
            field_rows.append([item.get("field") or item.get("name"), item.get("origin"), item.get("journey") or item.get("steps"), item.get("sink"), item.get("business_use")])
        external_rows = [[item.get("system") or item.get("target_system"), item.get("operation"), item.get("request_origin"), item.get("response_use"), item.get("business_effect")] for item in (item_dict(raw, "business_effect") for raw in item_list(overview.get("external_effects")))]
        persistence_rows = [[item.get("store") or item.get("table"), item.get("operation"), item.get("field_mappings") or item.get("mappings"), item.get("business_effect")] for item in (item_dict(raw, "business_effect") for raw in item_list(overview.get("persistence_effects")))]
        failure_rows = [[item.get("condition") or item.get("name"), item.get("behavior"), item.get("business_outcome") or item.get("description")] for item in (item_dict(raw) for raw in item_list(overview.get("failure_outcomes")))]
        cross = f'''<section class="section cross-cutting"><div class="card"><h2>字段如何走完整条链（P0）</h2>{table(['字段','来源','变化过程','终点','业务用途'],field_rows)}</div><div class="card"><h2>外部系统与业务副作用</h2>{table(['系统','操作','请求来源','响应用途','业务效果'],external_rows)}</div><div class="card"><h2>持久化结果</h2>{table(['存储','动作','字段映射','业务效果'],persistence_rows)}</div><div class="card"><h2>失败与降级</h2>{table(['条件','系统行为','业务结果'],failure_rows)}</div></section>'''

        gaps = f'''<section class="section"><div class="section-title"><h2>明确未解决的问题</h2><span class="muted">达到预算后保留为 Gap，不自动继续挖掘</span></div>{''.join(f'<div class="gap">{esc(item.get("question") if isinstance(item,dict) else item)}</div>' for item in open_gaps) if open_gaps else '<div class="card">当前没有开放 Gap。</div>'}</section>'''

        legacy_evidence = ""
        if dossier.get("execution_nodes"):
            legacy_evidence = f'''<details><summary><b>旧版完整方法树与字段联动</b></summary><div style="margin-top:12px">{self._execution_workspace(dossier)}</div></details>'''
        appendix = f'''<section class="section"><details><summary><b>技术证据附录</b>（方法、源码、配置位置，默认折叠）</summary><div class="technical-appendix">{''.join(self._block_evidence(block) for block in blocks)}{legacy_evidence}</div></details></section>'''
        drawer_data = {
            str(block.get("block_id")): {
                "title": block.get("title"),
                "why": block.get("why_current"),
                "decision": block.get("decision"),
                "status": block.get("status"),
                "methods": [
                    {
                        "symbol": method.get("symbol") or method.get("name") or method.get("description"),
                        "location": method.get("location") or f"{method.get('source_id') or ''}:{method.get('file') or ''}:{method.get('lines') or ''}",
                        "purpose": method.get("purpose") or method.get("role"),
                    }
                    for method in (item_dict(item) for item in item_list(block.get("method_evidence")))
                ],
                "refs": block.get("evidence_refs") or [],
            }
            for block in blocks
        }
        drawer_json = json.dumps(drawer_data, ensure_ascii=False).replace("</", "<\\/")
        first_block = str(blocks[0].get("block_id")) if blocks else ""
        script = '''<script>const UCEF_BLOCKS=__DATA__,firstBlock=__FIRST__,dialog=document.getElementById('evidence-dialog'),labels={condition:'条件',selected:'当前选择',route:'当前路由',reason:'原因',result:'结果',name:'名称',source:'来源',description:'说明'};
const readable=value=>value==null||value===''?'—':typeof value==='string'||typeof value==='number'||typeof value==='boolean'?String(value):Array.isArray(value)?value.map(readable).join('、'):Object.entries(value).map(([key,item])=>`${labels[key]||key}：${readable(item)}`).join('；');
const text=(el,value)=>{if(el)el.textContent=readable(value)};
function focusBusinessBlock(id,shouldScroll=false){if(!UCEF_BLOCKS[id])return;document.querySelectorAll('.block-nav').forEach(x=>x.classList.toggle('active',x.dataset.block===id));document.querySelectorAll('.business-block').forEach(x=>x.classList.toggle('focused',x.dataset.block===id));if(shouldScroll)document.getElementById(id)?.scrollIntoView({behavior:'smooth',block:'start'})}
function openEvidence(id){const data=UCEF_BLOCKS[id];if(!data)return;focusBusinessBlock(id);text(document.getElementById('drawer-title'),data.title);text(document.getElementById('drawer-why'),data.why);text(document.getElementById('drawer-decision'),data.decision);text(document.getElementById('drawer-refs'),data.refs);const methods=document.getElementById('drawer-methods');methods.replaceChildren();for(const method of data.methods||[]){const li=document.createElement('li'),strong=document.createElement('strong'),small=document.createElement('div');strong.textContent=method.symbol||'未命名方法';small.className='muted';small.textContent=[method.location,method.purpose].filter(Boolean).join(' · ');li.append(strong,small);methods.append(li)}if(!(data.methods||[]).length)methods.textContent='当前业务块没有已登记的方法证据。';if(!dialog.open)dialog.showModal()}
document.querySelectorAll('.block-nav').forEach(x=>x.addEventListener('click',()=>focusBusinessBlock(x.dataset.block,true)));document.querySelectorAll('.sequence-step').forEach(x=>{const activate=()=>focusBusinessBlock(x.dataset.block,true);x.addEventListener('click',activate);x.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate()}})});document.querySelectorAll('.evidence-open').forEach(x=>x.addEventListener('click',()=>openEvidence(x.dataset.block)));document.getElementById('drawer-close')?.addEventListener('click',()=>dialog.close());dialog?.addEventListener('click',event=>{if(event.target===dialog)dialog.close()});if(firstBlock)focusBusinessBlock(firstBlock);</script>'''.replace("__DATA__", drawer_json).replace("__FIRST__", json.dumps(first_block, ensure_ascii=False))
        return shell(str(scenario.get("name")), hero + console + cross + gaps + appendix + script, "../")

    def _business_block_card(self, index: int, block: dict[str, Any]) -> str:
        status = str(block.get("status") or "OUTLINE")
        inputs = block.get("inputs") or []
        decision = block.get("decision") or {}
        step_parts = []
        for sequence, raw_step in enumerate(item_list(block.get("implementation_steps")), start=1):
            step = item_dict(raw_step, "action")
            action = step.get("name") or step.get("action") or step.get("processing") or step.get("description") or f"步骤 {sequence}"
            reason = step.get("business_reason") or step.get("reason") or step.get("description")
            fields = step.get("field_effect") or step.get("fields") or step.get("result")
            step_parts.append(
                f'''<li><b>{esc(action)}</b>{f' — {esc(reason)}' if reason and reason != action else ''}{f'<div class="muted">字段/结果：{business_value(fields)}</div>' if fields else ''}</li>'''
            )
        step_html = "".join(step_parts)
        field_rows = [[item.get("field") or item.get("name"), item.get("from") or item.get("source"), item.get("transformation") or item.get("change") or item.get("description"), item.get("to") or item.get("target"), item.get("business_use")] for item in (item_dict(raw) for raw in item_list(block.get("field_changes")))]
        external_rows = [[item.get("system") or item.get("target_system"), item.get("operation") or item.get("description"), item.get("request"), item.get("response"), item.get("business_effect")] for item in (item_dict(raw) for raw in item_list(block.get("external_calls")))]
        persist_rows = [[item.get("store") or item.get("table"), item.get("operation") or item.get("description"), item.get("mappings"), item.get("business_effect")] for item in (item_dict(raw) for raw in item_list(block.get("persistence")))]
        details = ""
        if field_rows or external_rows or persist_rows:
            details = f'''<details class="detail-section"><summary><b>字段、外部接口与落库细节</b></summary><div style="margin-top:10px"><h4>字段变化</h4>{table(['字段','来源','转换','去向','业务用途'],field_rows)}<h4>外部交互</h4>{table(['系统','操作','请求','响应','业务效果'],external_rows)}<h4>持久化</h4>{table(['存储','动作','映射','业务效果'],persist_rows)}</div></details>'''
        reuse = item_dict(block.get("reuse") or {}, "basis")
        reuse_chip = f'<span class="badge reuse">{esc(status_text(reuse.get("decision")))}</span>' if reuse.get("decision") else ""
        block_id = str(block.get("block_id") or f"block-{index}")
        return f'''<article id="{esc(block_id)}" data-block="{esc(block_id)}" class="business-block {'outline' if status == 'OUTLINE' else ''}"><div class="block-head"><div class="block-number">{index}</div><div><h2>{esc(block.get('title'))}</h2><p>{esc(block.get('business_goal'))}</p></div><div class="chips"><span class="chip">{esc(status_text(block.get('depth')))}</span>{reuse_chip}{badge(status)}<button class="evidence-open" type="button" data-block="{esc(block_id)}">查看技术依据</button></div></div><div class="block-why"><b>为什么执行：</b>{esc(block.get('why_current'))}</div><div class="block-contract"><div class="mini-panel"><b>收到什么</b>{business_value(inputs)}</div><div class="mini-panel"><b>关键判断</b>{business_value(decision)}</div><div class="mini-panel"><b>产生什么</b>{business_value(block.get('output'))}</div></div>{f'<ol class="business-steps">{step_html}</ol>' if step_html else '<div class="empty" style="margin-top:12px">实现细节尚未提交，当前先展示业务骨架。</div>'}{f'<div class="muted" style="margin-top:10px">复用依据：{esc(reuse.get("basis"))}</div>' if reuse.get('basis') else ''}{details}</article>'''

    def _block_evidence(self, block: dict[str, Any]) -> str:
        methods = [item_dict(item) for item in item_list(block.get("method_evidence"))]
        refs = block.get("evidence_refs") or []
        if not methods and not refs:
            return ""
        return f'''<details><summary>{esc(block.get('title'))} · {len(methods)} 个方法证据</summary>{table(['方法/桥接','源码位置','作用','为什么不再深入'],[[item.get('symbol') or item.get('description'),item.get('location') or f"{item.get('source_id') or ''}:{item.get('file') or ''}:{item.get('lines') or ''}",item.get('role') or item.get('purpose'),item.get('transparent_reason')] for item in methods])}<div class="evidence">{business_value(refs)}</div></details>'''

    def _implementation_layers(self, dossier: dict[str, Any]) -> str:
        slices_by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
        gates_by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in dossier["implementation_slices"]:
            slices_by_stage[str(item.get("stage_id"))].append(item)
        for item in dossier["coverage_gates"]:
            gates_by_stage[str(item.get("stage_id") or "SCENARIO")].append(item)

        cards: list[str] = []
        for stage in dossier["trace_stages"]:
            stage_id = str(stage.get("stage_id"))
            stage_slices = slices_by_stage.get(stage_id, [])
            stage_gates = gates_by_stage.get(stage_id, [])
            gate_html = "".join(
                f'''<span class="chip">{esc(gate.get('priority'))} · {esc(gate.get('gate_type'))} · {esc(gate.get('status'))}</span>'''
                for gate in stage_gates
            )
            slice_html = "".join(self._implementation_slice_card(item) for item in stage_slices)
            cards.append(f'''<article class="card span12"><div class="chips"><span class="chip">{esc(stage.get('sequence_no'))}</span>{badge(stage.get('status'))}{gate_html}</div><h2>{esc(stage.get('name'))}</h2><p>{esc(stage.get('business_purpose'))}</p>{slice_html if slice_html else '<div class="empty">尚无实现切片；业务概述不能替代实现证据。</div>'}</article>''')
        scenario_gates = gates_by_stage.get("SCENARIO", [])
        scenario_gate_html = "".join(
            f'''<div class="gap"><b>{esc(item.get('priority'))} · {esc(item.get('gate_type'))}</b> {esc(item.get('question'))}<div class="muted">{esc(item.get('status'))}</div></div>'''
            for item in scenario_gates
        )
        return f'''<section class="section"><div class="section-title"><h2>业务步骤的实现切片</h2><span class="muted">跨方法解释输入、判断、字段、副作用、输出和异常；透明框架桥接单独标注</span></div>{scenario_gate_html}<div class="grid">{''.join(cards) if cards else '<div class="empty span12">尚无业务阶段或实现切片。</div>'}</div></section>'''

    def _implementation_slice_card(self, item: dict[str, Any]) -> str:
        path = " → ".join(str(step.get("symbol") or step.get("name") or step) for step in item.get("method_path") or [])
        steps = table(
            ["顺序", "实现步骤", "条件", "读取字段", "写入字段"],
            [[step.get("sequence_no"), step.get("name") or step.get("processing"), step.get("condition"), step.get("field_reads"), step.get("field_writes")] for step in item.get("internal_steps") or []],
        )
        bridges = table(
            ["从", "到", "折叠原因", "框架"],
            [[bridge.get("from"), bridge.get("to"), bridge.get("reason"), bridge.get("framework")] for bridge in item.get("technical_bridges") or []],
        )
        closure = item.get("semantic_closure") or {}
        closure_html = "".join(f'<span class="chip">{esc(key)} {"✓" if value else "✗"}</span>' for key, value in closure.items())
        return f'''<details open><summary><b>{esc(item.get('name'))}</b> · {esc(item.get('focus_mode'))} · {esc(item.get('closure_status'))}</summary><div class="detail-section"><p>{esc(item.get('business_purpose'))}</p>{kv_rows([('实际方法路径',path),('路由与配置',item.get('route_and_config')),('字段变化',item.get('field_effects')),('边界',item.get('boundaries')),('异常与时序',item.get('error_and_timing'))])}<div class="chips">{closure_html}</div><h4>方法内部关键步骤</h4>{steps}<h4>透明技术桥接</h4>{bridges}</div></details>'''

    def _execution_workspace(self, dossier: dict[str, Any]) -> str:
        nodes = dossier["execution_nodes"]
        if not nodes:
            return '''<section class="section"><div class="section-title"><h2>方法执行树</h2></div><div class="empty">尚无执行树。需要按项目/模块、方法调用和方法内部步骤重新装配链路。</div></section>'''

        node_by_id = {str(item.get("execution_node_id")): item for item in nodes}
        method_by_id = {str(item.get("method_definition_id")): item for item in dossier["method_definitions"]}
        stage_by_id = {str(item.get("stage_id")): item for item in dossier["trace_stages"]}
        fragment_by_id = {str(item.get("fragment_id")): item for item in dossier["fragments"]}
        evidence_by_id = {str(item.get("evidence_id")): item for item in dossier["evidences"]}
        children: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in nodes:
            if node.get("parent_node_id"):
                children[str(node.get("parent_node_id"))].append(node)
        for values in children.values():
            values.sort(key=lambda item: (float(item.get("sequence_no") or 0), str(item.get("execution_node_id"))))
        roots = [node for node in nodes if not node.get("parent_node_id") or str(node.get("parent_node_id")) not in node_by_id]
        roots.sort(key=lambda item: (float(item.get("sequence_no") or 0), str(item.get("execution_node_id"))))

        lineage_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for step in dossier["field_lineage_steps"]:
            lineage_by_node[str(step.get("execution_node_id"))].append(step)
        decisions_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
        persistence_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
        external_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in dossier["route_decisions"]:
            decisions_by_node[str(item.get("execution_node_id"))].append(item)
        for item in dossier["persistence_effects"]:
            persistence_by_node[str(item.get("execution_node_id"))].append(item)
        for item in dossier["external_interactions"]:
            external_by_node[str(item.get("execution_node_id"))].append(item)

        def node_fields(node: dict[str, Any]) -> list[str]:
            values = set(str(value) for value in (node.get("field_reads") or []) + (node.get("field_writes") or []))
            values.update(str(item.get("canonical_field")) for item in lineage_by_node.get(str(node.get("execution_node_id")), []))
            return sorted(values)

        def render_node(node: dict[str, Any], ancestors: set[str]) -> str:
            node_id = str(node.get("execution_node_id"))
            kind = str(node.get("node_type") or "NODE")
            fields = "|".join(node_fields(node))
            button = f'''<button class="node-select" data-node="{esc(node_id)}" data-fields="{esc(fields)}"><span class="node-type">{esc(kind)}</span>{esc(node.get('name'))}</button>'''
            if node_id in ancestors:
                return f'<li class="tree-leaf bad">循环父子关系：{esc(node_id)}</li>'
            descendants = children.get(node_id, [])
            if not descendants:
                return f'<li class="tree-leaf">{button}</li>'
            next_ancestors = set(ancestors)
            next_ancestors.add(node_id)
            nested = "".join(render_node(child, next_ancestors) for child in descendants)
            opened = " open" if kind in {"MODULE", "METHOD_INVOCATION"} else ""
            return f'<li class="tree-node"><details{opened}><summary>{button}</summary><ul>{nested}</ul></details></li>'

        tree_html = '<ul class="execution-tree">' + "".join(render_node(root, set()) for root in roots) + '</ul>'
        detail_html = "".join(
            self._node_detail(
                node,
                method_by_id.get(str(node.get("method_definition_id"))),
                stage_by_id.get(str(node.get("stage_id"))),
                fragment_by_id,
                evidence_by_id,
                lineage_by_node.get(str(node.get("execution_node_id")), []),
                decisions_by_node.get(str(node.get("execution_node_id")), []),
                persistence_by_node.get(str(node.get("execution_node_id")), []),
                external_by_node.get(str(node.get("execution_node_id")), []),
            )
            for node in nodes
        )
        field_html = self._field_panel(dossier)
        first_node = str(nodes[0].get("execution_node_id"))
        first_field = str((dossier["field_inventory"] or [{}])[0].get("canonical_field") or "")
        script = f'''<script>
function ucefSelectNode(id){{document.querySelectorAll('.node-select').forEach(x=>x.classList.toggle('active',x.dataset.node===id));document.querySelectorAll('.node-detail').forEach(x=>x.classList.toggle('active',x.dataset.node===id));}}
function ucefSelectField(name){{document.querySelectorAll('.field-select').forEach(x=>x.classList.toggle('active',x.dataset.field===name));document.querySelectorAll('.field-detail').forEach(x=>x.classList.toggle('active',x.dataset.field===name));document.querySelectorAll('.node-select').forEach(x=>{{const fs=(x.dataset.fields||'').split('|');x.classList.toggle('field-hit',fs.includes(name));}});}}
document.querySelectorAll('.node-select').forEach(x=>x.addEventListener('click',e=>{{e.preventDefault();e.stopPropagation();ucefSelectNode(x.dataset.node);}}));
document.querySelectorAll('.field-select').forEach(x=>x.addEventListener('click',()=>ucefSelectField(x.dataset.field)));
document.querySelectorAll('.node-jump').forEach(x=>x.addEventListener('click',()=>ucefSelectNode(x.dataset.node)));
ucefSelectNode({json.dumps(first_node, ensure_ascii=False)});ucefSelectField({json.dumps(first_field, ensure_ascii=False)});
</script>'''
        return f'''<section class="section"><div class="section-title"><h2>方法执行树</h2><span class="muted">项目/模块 → 方法调用实例 → 方法内部步骤；点击字段可反向高亮经过的节点</span></div><div class="execution-workspace"><aside class="execution-panel"><h3>调用与步骤树</h3><div class="panel-body"><div class="tree-note">METHOD_INVOCATION 表示当前场景中的一次调用；同一方法定义可以在不同位置重复装配。</div>{tree_html}</div></aside><section class="execution-panel"><h3>节点详情</h3><div class="panel-body">{detail_html}</div></section><aside class="execution-panel field-panel"><h3>字段数据流</h3><div class="panel-body">{field_html}</div></aside></div>{script}</section>'''

    def _node_detail(
        self,
        node: dict[str, Any],
        method: dict[str, Any] | None,
        stage: dict[str, Any] | None,
        fragments: dict[str, dict[str, Any]],
        evidences: dict[str, dict[str, Any]],
        lineage: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
        persistence: list[dict[str, Any]],
        interactions: list[dict[str, Any]],
    ) -> str:
        node_id = str(node.get("execution_node_id"))
        method_html = ""
        if method:
            method_html = f'''<div class="detail-section"><h3>可复用方法定义</h3>{kv_rows([('符号',method.get('symbol')),('模块',method.get('module')),('签名',method.get('signature')),('源码',f"{method.get('file')}:{method.get('line_start')}-{method.get('line_end')}"),('代码哈希',method.get('code_hash')),('入口契约',method.get('input_contract')),('出口契约',method.get('output_contract')),('异常',method.get('throws'))])}</div>'''
        fragment = fragments.get(str((stage or {}).get("fragment_id"))) if stage else None
        fragment_html = ""
        if fragment:
            fragment_html = f'''<div class="fragment"><div class="chips"><span class="badge reuse">复用行为片段</span>{badge(fragment.get('status'))}</div><h4>{esc(fragment.get('name'))}</h4><p>{esc(fragment.get('business_purpose'))}</p>{kv_rows([('适用条件',fragment.get('applicability')),('入口契约',fragment.get('entry_contract')),('出口契约',fragment.get('exit_contract')),('副作用',fragment.get('side_effects'))])}</div>'''
        lineage_html = table(
            ["字段", "角色", "来源", "操作/表达式", "目标", "前序"],
            [[item.get("canonical_field"), item.get("lineage_role"), item.get("source"), f"{item.get('operation')} · {item.get('expression') or item.get('transformation') or ''}", item.get("target"), item.get("previous_step_ids")] for item in lineage],
        ) if lineage else '<div class="empty">此节点没有字段事件。</div>'
        decision_html = "".join(f'''<div class="why"><b>{esc(item.get('question'))}</b><div>{esc(item.get('reason'))}</div><div class="chips"><span class="chip">结果 {esc(item.get('current_outcome'))}</span></div></div>''' for item in decisions)
        persistence_html = "".join(f'''<div class="detail-section"><h3>持久化：{esc(item.get('store'))}</h3>{table(['目标字段','值来源','转换','业务用途'],[[mapping.get('target'),mapping.get('value_source'),mapping.get('transformation'),mapping.get('business_use')] for mapping in item.get('mappings') or []])}</div>''' for item in persistence)
        interaction_html = "".join(f'''<div class="detail-section"><h3>外部交互：{esc(item.get('target_system'))} · {esc(item.get('operation'))}</h3><p>{esc(item.get('business_purpose'))}</p>{table(['请求参数','内部来源','业务用途'],[[param.get('external_name'),param.get('internal_origin'),param.get('business_use')] for param in item.get('request_params') or []])}{table(['响应参数','内部去向','业务用途'],[[param.get('external_name'),param.get('internal_target') if param.get('consumed',True) else '未消费',param.get('business_use')] for param in item.get('response_params') or []])}</div>''' for item in interactions)
        evidence_ids = list(dict.fromkeys((node.get("evidence_ids") or []) + ([eid for item in lineage for eid in item.get("evidence_ids") or []])))
        evidence_html = "".join(self._evidence_line(evidences.get(str(eid)), str(eid)) for eid in evidence_ids)
        return f'''<article class="node-detail" data-node="{esc(node_id)}"><div class="chips"><span class="chip">{esc(node.get('node_type'))}</span><span class="chip">{esc(node.get('source_id'))}</span>{badge(node.get('status'))}</div><h2>{esc(node.get('name'))}</h2><p>{esc(node.get('business_purpose'))}</p>{kv_rows([('业务阶段',(stage or {}).get('name')),('步骤类型',node.get('step_kind')),('条件/当前分支',node.get('condition')),('输入',node.get('input')),('处理',node.get('processing')),('输出',node.get('output')),('读取字段',node.get('field_reads')),('写入字段',node.get('field_writes'))])}{decision_html}{fragment_html}{method_html}<div class="detail-section"><h3>本节点字段事件</h3>{lineage_html}</div>{persistence_html}{interaction_html}{f'<div class="detail-section"><details><summary>源码、配置与数据库证据</summary>{evidence_html}</details></div>' if evidence_html else ''}</article>'''

    def _field_panel(self, dossier: dict[str, Any]) -> str:
        lineage_by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for step in dossier["field_lineage_steps"]:
            lineage_by_field[str(step.get("canonical_field"))].append(step)
        inventory = dossier["field_inventory"]
        selectors = "".join(f'''<button class="field-select" data-field="{esc(item.get('canonical_field'))}"><span class="node-type">{esc(item.get('priority'))}</span>{esc(item.get('canonical_field'))} · {esc(item.get('tracking_status'))}</button>''' for item in inventory)
        details = []
        for item in inventory:
            field = str(item.get("canonical_field"))
            steps = sorted(lineage_by_field.get(field, []), key=lambda value: float(value.get("sequence_no") or 0))
            path = "".join(f'''<li><button class="node-jump" data-node="{esc(step.get('execution_node_id'))}"><b>{esc(step.get('operation'))}</b> {esc(step.get('source'))} → {esc(step.get('target'))}<br><span class="muted">{esc(step.get('expression') or step.get('transformation'))}</span></button></li>''' for step in steps)
            details.append(f'''<div class="field-detail" data-field="{esc(field)}"><div class="chips"><span class="chip">{esc(item.get('priority'))}</span>{badge(item.get('status'))}</div><h3>{esc(field)}</h3><p>{esc(item.get('business_use'))}</p>{kv_rows([('追踪决策',item.get('tracking_status')),('入口位置',item.get('entry_locations')),('预期终点',item.get('expected_sinks')),('排除原因',item.get('exclusion_reason'))])}<div class="detail-section"><b>字段路径</b>{f'<ol class="field-path">{path}</ol>' if path else '<div class="empty">没有字段步骤；这是显式缺口。</div>'}</div></div>''')
        return f'''<div>{selectors if selectors else '<div class="empty">没有字段清单；无法判断是否遗漏。</div>'}</div><div class="detail-section">{''.join(details)}</div>'''

    def _evidence_line(self, evidence: dict[str, Any] | None, evidence_id: str) -> str:
        if not evidence:
            return f'<div class="evidence bad">缺失 Evidence：{esc(evidence_id)}</div>'
        source = evidence.get("source") or {}
        if isinstance(source, dict):
            source_name = source.get('source_id') or source.get('repository') or source.get('source_type') or ''
            location = f"{source_name}:{source.get('file') or source.get('key') or ''}:{source.get('line_start') or ''}"
        else:
            location = str(source)
        artifact_id = evidence.get("artifact_id") or (source.get("artifact_id") if isinstance(source, dict) else None)
        locator = evidence.get("locator") or {}
        selector = locator.get("selector") if isinstance(locator, dict) else None
        artifact_link = ""
        if artifact_id:
            suffix = f"#pointer={quote(str(selector), safe='')}" if selector else ""
            artifact_link = f'''<br><a href="../artifacts/{safe_name(str(artifact_id))}.html{suffix}">打开原始制品{f' · {esc(selector)}' if selector else ''}</a>'''
        return f'<div class="evidence"><b>{esc(evidence_id)}</b> · {esc(evidence.get("evidence_kind"))}<br>{esc(location)}<br>{esc(evidence.get("observation"))}{artifact_link}</div>'

    def _external_card(self, item: dict[str, Any]) -> str:
        request = [[x.get("external_name"), x.get("internal_origin"), x.get("transformation"), x.get("business_use")] for x in item.get("request_params") or []]
        response = [[x.get("external_name"), x.get("internal_target") if x.get("consumed", True) else "未消费", x.get("transformation"), x.get("business_use")] for x in item.get("response_params") or []]
        return f'''<div class="card span12"><div class="chips">{badge(item.get('status'))}<span class="chip">{esc(item.get('source_id'))}</span><span class="chip">{esc(item.get('protocol'))}</span></div><h3>{esc(item.get('target_system'))} · {esc(item.get('operation'))}</h3><p>{esc(item.get('business_purpose'))}</p>{kv_rows([('触发条件',item.get('trigger_condition')),('超时/重试/降级',item.get('error_behavior')),('调用方式',item.get('call_mode'))])}<h4>请求参数来源</h4>{table(['外部参数','内部来源','转换','业务用途'],request)}<h4>响应参数去向</h4>{table(['外部参数','内部去向','转换','后续业务用途'],response)}</div>'''

    def _compare_page(self, dossiers: list[dict[str, Any]]) -> str:
        compact = []
        for dossier in dossiers:
            overview = (dossier.get("scenario_overviews") or [{}])[-1]
            blocks = dossier.get("business_blocks") or dossier["trace_stages"]
            methods = [
                {"method_definition_id": item.get("symbol"), "name": item.get("symbol"), "business_purpose": item.get("purpose") or item.get("role"), "node_type": "METHOD_INVOCATION"}
                for block in dossier.get("business_blocks") or []
                for item in (item_dict(raw) for raw in item_list(block.get("method_evidence")))
            ] or dossier["execution_nodes"]
            fields = [
                {"canonical_field": item.get("field") or item.get("name"), "priority": "P0", "tracking_status": item.get("journey") or item.get("steps")}
                for item in (item_dict(raw, "field") for raw in item_list(overview.get("key_field_journeys")))
            ] or dossier["field_inventory"]
            decisions = [
                {"question": block.get("title"), "current_outcome": block.get("decision"), "reason": block.get("why_current")}
                for block in dossier.get("business_blocks") or [] if block.get("decision")
            ] or dossier["route_decisions"]
            external = [
                {"target_system": item.get("system") or item.get("target_system"), "operation": item.get("operation"), "business_purpose": item.get("business_effect") or item.get("effect")}
                for item in (item_dict(raw, "business_effect") for raw in item_list(overview.get("external_effects")))
            ] or dossier["external_interactions"]
            persistence = [
                {"store": item.get("store") or item.get("table"), "operation": item.get("operation"), "business_effect": item.get("business_effect") or item.get("effect")}
                for item in (item_dict(raw, "business_effect") for raw in item_list(overview.get("persistence_effects")))
            ] or dossier["persistence_effects"]
            compact.append({
                "scenario": dossier["scenario"], "trace_stages": blocks,
                "execution_nodes": methods, "field_inventory": fields,
                "route_decisions": decisions, "persistence_effects": persistence,
                "external_interactions": external,
            })
        data = json.dumps(compact, ensure_ascii=False).replace("</", "<\\/")
        body = '''<section class="hero"><h1>链路横向对比</h1><p class="muted">按业务阶段、方法调用实例、字段清单与演化、落库和外部交互对齐两个场景。</p><div class="compare-controls"><select id="left"></select><select id="right"></select><button id="run">比较</button></div></section><div id="result" class="section"></div>
<script>const D=__DATA__;
const $=s=>document.querySelector(s), e=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function key(x){return x.stage_key||x.fragment_id||x.title||x.name||x.block_id||x.stage_id}function rows(a,b,k){const A=new Map(a.map(x=>[k(x),x])),B=new Map(b.map(x=>[k(x),x]));return [...new Set([...A.keys(),...B.keys()])].map(x=>[x,A.get(x),B.get(x)])}
function tbl(h,rs){return `<div class="scroll"><table><thead><tr>${h.map(x=>`<th>${e(x)}</th>`).join('')}</tr></thead><tbody>${rs.map(r=>`<tr>${r.map(x=>`<td>${e(x)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}
function run(){const a=D[$('#left').value],b=D[$('#right').value];if(!a||!b)return;const stages=rows(a.trace_stages,b.trace_stages,key);const first=stages.find(x=>!x[1]||!x[2]||JSON.stringify(x[1].output)!==JSON.stringify(x[2].output)||x[1].why_current!==x[2].why_current);const methods=rows(a.execution_nodes.filter(x=>x.node_type==='METHOD_INVOCATION'),b.execution_nodes.filter(x=>x.node_type==='METHOD_INVOCATION'),x=>x.method_definition_id||x.name);const fields=rows(a.field_inventory,b.field_inventory,x=>x.canonical_field);const dec=rows(a.route_decisions,b.route_decisions,x=>x.question);const ext=rows(a.external_interactions,b.external_interactions,x=>`${x.target_system}|${x.operation}`);const db=rows(a.persistence_effects,b.persistence_effects,x=>`${x.store}|${x.operation}`);$('#result').innerHTML=`<div class="card"><h2>首个业务分叉</h2>${first?`<b>${e(first[0])}</b><p>${e(first[1]?.why_current||first[1]?.output)} ↔ ${e(first[2]?.why_current||first[2]?.output)}</p>`:'<p>尚未发现已记录的分叉。</p>'}</div><section class="section"><h2>业务块</h2>${tbl(['对齐键',a.scenario.name,b.scenario.name],stages.map(x=>[x[0],x[1]?.business_goal||x[1]?.business_purpose||'缺失',x[2]?.business_goal||x[2]?.business_purpose||'缺失']))}</section><section class="section"><h2>方法证据</h2>${tbl(['方法定义',a.scenario.name,b.scenario.name],methods.map(x=>[x[0],x[1]?.business_purpose||'缺失',x[2]?.business_purpose||'缺失']))}</section><section class="section"><h2>字段旅程</h2>${tbl(['字段',a.scenario.name,b.scenario.name],fields.map(x=>[x[0],`${x[1]?.priority||'—'} · ${x[1]?.tracking_status||'缺失'}`,`${x[2]?.priority||'—'} · ${x[2]?.tracking_status||'缺失'}`]))}</section><section class="section"><h2>路由决策</h2>${tbl(['决策',a.scenario.name,b.scenario.name],dec.map(x=>[x[0],`${JSON.stringify(x[1]?.current_outcome)||'—'} · ${x[1]?.reason||''}`,`${JSON.stringify(x[2]?.current_outcome)||'—'} · ${x[2]?.reason||''}`]))}</section><section class="section"><h2>外部交互</h2>${tbl(['交互',a.scenario.name,b.scenario.name],ext.map(x=>[x[0],x[1]?.business_purpose||'无',x[2]?.business_purpose||'无']))}</section><section class="section"><h2>持久化</h2>${tbl(['存储动作',a.scenario.name,b.scenario.name],db.map(x=>[x[0],x[1]?.business_effect||'无',x[2]?.business_effect||'无']))}</section>`}
for(const id of ['left','right'])D.forEach((x,i)=>$('#'+id).insertAdjacentHTML('beforeend',`<option value="${i}">${e(x.scenario.name)}</option>`));if(D.length>1)$('#right').value='1';$('#run').onclick=run;run();</script>'''.replace("__DATA__", data)
        return shell("UCEF 链路横向对比", body)
