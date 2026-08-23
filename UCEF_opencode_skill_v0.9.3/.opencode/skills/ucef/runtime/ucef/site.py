from __future__ import annotations

import html
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .audit import audit_scenario
from .core import safe_name
from .store import FactStore


CSS = r'''
:root{--bg:#f4f7fb;--card:#fff;--ink:#172033;--muted:#667085;--line:#d9e1ec;--brand:#2457d6;--good:#147a51;--warn:#a05a00;--bad:#b42318;--soft:#eef3ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 Inter,Segoe UI,Arial,sans-serif}a{color:var(--brand);text-decoration:none}a:hover{text-decoration:underline}
.top{background:#101828;color:#fff;padding:16px 28px;display:flex;gap:24px;align-items:center}.top strong{font-size:19px}.top a{color:#dbe6ff}.wrap{max-width:1380px;margin:0 auto;padding:26px}.hero,.card,.stage{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:0 4px 16px #1018280b}.hero{padding:24px}.hero h1{margin:0 0 8px;font-size:28px}.muted{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:16px}.span4{grid-column:span 4}.span6{grid-column:span 6}.span8{grid-column:span 8}.span12{grid-column:span 12}.card{padding:18px}.card h2,.card h3{margin-top:0}.section{margin-top:24px}.section-title{display:flex;justify-content:space-between;align-items:end;margin:0 0 12px}.section-title h2{margin:0}
.chips{display:flex;gap:7px;flex-wrap:wrap}.chip,.badge{border-radius:999px;padding:3px 9px;font-size:12px;background:#edf2f7;color:#344054}.good{background:#e7f6ef;color:var(--good)}.warn{background:#fff3df;color:var(--warn)}.bad{background:#ffebe9;color:var(--bad)}.reuse{background:#e8edff;color:#3546a8}
.kv{display:grid;grid-template-columns:150px 1fr;gap:8px 14px}.kv b{color:#344054}.value{white-space:pre-wrap;overflow-wrap:anywhere}.timeline{position:relative;margin-left:18px}.timeline:before{content:"";position:absolute;left:19px;top:28px;bottom:28px;width:2px;background:#b7c7e8}.stage{position:relative;margin:0 0 18px 58px;padding:20px}.stage:before{content:attr(data-n);position:absolute;left:-58px;top:20px;width:40px;height:40px;border-radius:50%;display:grid;place-items:center;background:var(--brand);color:white;font-weight:700;box-shadow:0 0 0 5px var(--bg)}.stage h3{margin:0 0 4px;font-size:19px}.stage-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:14px}.stage-cell{border:1px solid var(--line);border-radius:10px;padding:11px;background:#fbfcfe}.stage-cell b{display:block;margin-bottom:4px;color:#344054}.handoff{margin-top:12px;padding:9px 12px;background:var(--soft);border-radius:9px}.fragment{margin-top:12px;border-left:4px solid #7c8dde;padding:10px 12px;background:#f6f7ff}.fragment h4{margin:0 0 5px}.why{margin-top:10px;padding:10px 12px;background:#fff8e8;border-left:4px solid #f0a020}
table{width:100%;border-collapse:collapse;background:white}th,td{padding:10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{background:#f7f9fc;color:#344054;font-size:13px}.scroll{overflow:auto;border:1px solid var(--line);border-radius:10px}.field-group{margin-bottom:20px}.gap{border-left:4px solid var(--bad);padding:10px 12px;background:#fff5f4;margin:8px 0}.evidence{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;background:#f7f8fa;border-radius:8px;padding:9px;margin:6px 0;overflow-wrap:anywhere}.empty{padding:18px;color:var(--muted);text-align:center;border:1px dashed var(--line);border-radius:10px}
.scenario-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}.scenario-card{display:block;color:inherit}.scenario-card:hover{text-decoration:none;border-color:#9ab2ee;transform:translateY(-1px)}.scenario-card h2{font-size:18px}.footer{padding:30px;text-align:center;color:var(--muted)}select,button{font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:white}button{background:var(--brand);color:#fff;border-color:var(--brand);cursor:pointer}.compare-controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
@media(max-width:850px){.span4,.span6,.span8{grid-column:span 12}.stage-grid{grid-template-columns:1fr}.kv{grid-template-columns:1fr}.wrap{padding:15px}.stage{margin-left:48px}.timeline{margin-left:0}}
'''


def esc(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, indent=2)
    return html.escape(str(value))


def preview(value: Any, max_chars: int = 1200) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value or "")
    return text if len(text) <= max_chars else text[:max_chars] + " … [memory-query 查看完整事实]"


def shell(title: str, body: str, relative_root: str = "") -> str:
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{CSS}</style></head><body>
<nav class="top"><strong>UCEF</strong><a href="{relative_root}index.html">业务链路</a><a href="{relative_root}compare.html">横向对比</a><a href="{relative_root}memory.html">分析记忆</a></nav>
<main class="wrap">{body}</main><footer class="footer">Generated from evidence-backed UCEF facts · source links are evidence, not the narrative</footer></body></html>'''


def kv_rows(items: list[tuple[str, Any]]) -> str:
    return '<div class="kv">' + "".join(f"<b>{esc(k)}</b><div class=\"value\">{esc(v)}</div>" for k, v in items) + "</div>"


def badge(status: str | None) -> str:
    value = status or "UNKNOWN"
    cls = "good" if value in {"COMPLETE", "READABLE_COMPLETE", "CONFIRMED", "SCENARIO_CONFIRMED", "STATIC_VERIFIED"} else "bad" if value in {"INCOMPLETE", "UNKNOWN", "STALE"} else "warn"
    return f'<span class="badge {cls}">{esc(value)}</span>'


def table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return '<div class="empty">暂无已确认内容</div>'
    head = "".join(f"<th>{esc(x)}</th>" for x in headers)
    body = "".join("<tr>" + "".join(f"<td>{esc(x)}</td>" for x in row) + "</tr>" for row in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


class DossierSiteBuilder:
    def __init__(self, store: FactStore, config: dict[str, Any], workspace_root: str | Path):
        self.store = store
        self.config = config
        self.workspace_root = Path(workspace_root)
        output = (config.get("site") or {}).get("output", "site")
        self.output = (Path(output) if Path(output).is_absolute() else self.workspace_root / output).resolve()
        try:
            self.output.relative_to(self.workspace_root.resolve())
        except ValueError as exc:
            raise ValueError(f"Generated site must stay inside UCEF workspace: {self.output}") from exc

    def build(self) -> dict[str, Any]:
        self.output.mkdir(parents=True, exist_ok=True)
        scenario_dir = self.output / "scenarios"
        scenario_dir.mkdir(parents=True, exist_ok=True)
        scenarios = self.store.list_scenarios()
        dossiers = []
        for scenario in scenarios:
            scenario_id = scenario["scenario_id"]
            dossier = self.store.scenario_dossier(scenario_id)
            audit = audit_scenario(self.store, scenario_id, persist=False)
            dossier["audit"] = audit
            dossiers.append(dossier)
            target = scenario_dir / f"{safe_name(scenario_id)}.html"
            target.write_text(self._scenario_page(dossier), encoding="utf-8")
        (self.output / "index.html").write_text(self._index_page(dossiers), encoding="utf-8")
        (self.output / "compare.html").write_text(self._compare_page(dossiers), encoding="utf-8")
        (self.output / "memory.html").write_text(self._memory_page(), encoding="utf-8")
        return {"output": str(self.output), "scenarios": len(scenarios), "files": len(scenarios) + 3}

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
            cards.append(f'''<section class="card section"><div class="chips">{badge(work_unit.get('status'))}<span class="chip">{esc(work_unit_id)}</span><span class="chip">{memory.get('checkpoint_count')} checkpoints</span><span class="chip">{memory['observation_counts']['pending_assembly']} pending assembly</span><span class="chip">{memory['observation_counts']['evidenced']} evidenced</span><span class="chip">{memory['observation_counts']['assembled']} assembled</span></div><h2>{esc(work_unit.get('objective') or work_unit_id)}</h2>{kv_rows([('当前焦点',latest.get('current_focus')),('恢复摘要',latest.get('resume_summary')),('唯一下一探查',latest.get('next_probe')),('未决问题',latest.get('unresolved_questions')),('观察索引',memory.get('observation_index'))])}<h3>最近待装配事实</h3>{table(['类型','数据源','主题','事实','置信度'],rows)}{f'<div class="muted">另有 {memory.get("omitted_pending_observations")} 条未在本页展开，可用 memory-query 检索。</div>' if memory.get('omitted_pending_observations') else ''}</section>''')
        content = f'''<section class="hero"><h1>分析记忆</h1><p class="muted">这里展示未完成 Work Unit 的持久化 Checkpoint 和 Observation 前沿。它们不会进入业务主叙事，直到被晋升为正式事实。</p></section>{''.join(cards) if cards else '<section class="section empty">尚无 Checkpoint。</section>'}'''
        return shell("UCEF Analysis Memory", content)

    def _index_page(self, dossiers: list[dict[str, Any]]) -> str:
        cards = []
        for dossier in dossiers:
            scenario = dossier["scenario"]
            audit = dossier["audit"]
            scope = scenario.get("scope") or {}
            cards.append(f'''<a class="card scenario-card" href="scenarios/{safe_name(scenario['scenario_id'])}.html">
<div class="chips">{badge(audit['readability_status'])}<span class="chip">{esc(scope.get('environment'))}</span></div>
<h2>{esc(scenario.get('name'))}</h2><p>{esc(scenario.get('business_goal'))}</p>
<div class="muted">{esc(scenario.get('business_operation'))} · {esc(scope.get('source_ids') or scope.get('project') or scope.get('repository'))}</div>
<div class="chips" style="margin-top:12px"><span class="chip">{len(dossier['trace_stages'])} 阶段</span><span class="chip">{len(dossier['field_lineage_steps'])} 字段步骤</span><span class="chip">{len(dossier['external_interactions'])} 外部交互</span><span class="chip">{len([x for x in dossier['gaps'] if x.get('status','OPEN')=='OPEN'])} 缺口</span></div></a>''')
        content = f'''<section class="hero"><h1>{esc((self.config.get('site') or {}).get('title','UCEF Business Execution Dossiers'))}</h1><p class="muted">面向不了解系统的 Java 开发者：从业务目标进入，沿配置路由、字段演化、落库和外部交互阅读完整执行链。</p></section>
<section class="section"><div class="section-title"><h2>业务场景</h2><a href="compare.html">进入横向对比 →</a></div><div class="scenario-list">{''.join(cards) if cards else '<div class="empty">尚无 Scenario。先创建场景并 ingest 第一个业务阶段。</div>'}</div></section>'''
        return shell("UCEF Business Execution Dossiers", content)

    def _scenario_page(self, dossier: dict[str, Any]) -> str:
        scenario = dossier["scenario"]
        audit = dossier["audit"]
        scope = scenario.get("scope") or {}
        trigger = scenario.get("trigger") or {}
        fragments = {x.get("fragment_id"): x for x in dossier["fragments"]}
        evidences = {x.get("evidence_id"): x for x in dossier["evidences"]}
        decisions_by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in dossier["route_decisions"]:
            decisions_by_stage[str(item.get("stage_id"))].append(item)

        dimension_badges = "".join(f'<span class="chip">{esc(k)} {badge(v)}</span>' for k, v in audit["dimensions"].items())
        hero = f'''<section class="hero"><div class="chips">{badge(audit['readability_status'])}<span class="chip">{esc(scenario.get('scenario_id'))}</span></div><h1>{esc(scenario.get('name'))}</h1><p>{esc(scenario.get('business_goal'))}</p><div class="chips">{dimension_badges}</div></section>
<section class="section grid"><div class="card span6"><h2>业务入口与结果</h2>{kv_rows([('业务操作',scenario.get('business_operation')),('入口类型',trigger.get('kind')),('入口符号',trigger.get('symbol')),('输入类型',trigger.get('input_type')),('预期结果',scenario.get('expected_outcome'))])}</div><div class="card span6"><h2>适用范围</h2>{kv_rows([('数据源',scope.get('source_ids')),('数据源版本',scope.get('source_revisions')),('环境',scope.get('environment')),('配置快照',scope.get('config_snapshot_id')),('请求约束',scope.get('request_constraints'))])}</div></section>'''

        stage_html = []
        for index, stage in enumerate(dossier["trace_stages"], 1):
            fragment = fragments.get(stage.get("fragment_id"))
            fragment_html = ""
            if fragment:
                fragment_html = f'''<div class="fragment"><div class="chips"><span class="badge reuse">复用行为片段</span>{badge(fragment.get('status'))}</div><h4>{esc(fragment.get('name'))}</h4><p>{esc(fragment.get('business_purpose'))}</p>{kv_rows([('适用条件',fragment.get('applicability')),('入口契约',fragment.get('entry_contract')),('出口契约',fragment.get('exit_contract')),('副作用',fragment.get('side_effects')),('交接',fragment.get('handoffs'))])}</div>'''
            stage_decisions = decisions_by_stage.get(str(stage.get("stage_id")), [])
            decision_html = "".join(f'''<div class="why"><b>路由决策：{esc(x.get('question'))}</b><div>{esc(x.get('reason'))}</div><div class="chips"><span class="chip">输入 {esc(x.get('inputs'))}</span><span class="chip">结果 {esc(x.get('current_outcome'))}</span></div></div>''' for x in stage_decisions)
            evidence_html = "".join(self._evidence_line(evidences.get(eid), eid) for eid in stage.get("evidence_ids") or [])
            stage_html.append(f'''<article class="stage" data-n="{index}"><div class="chips"><span class="chip">{esc(stage.get('source_id'))}</span><span class="chip">{esc(stage.get('stage_type'))}</span>{badge(stage.get('status'))}</div><h3>{esc(stage.get('name'))}</h3><p>{esc(stage.get('business_purpose'))}</p>{f'<div class="why"><b>当前场景为什么执行：</b> {esc(stage.get("why_current"))}</div>' if stage.get('why_current') else ''}<div class="stage-grid"><div class="stage-cell"><b>输入</b>{esc(stage.get('input'))}</div><div class="stage-cell"><b>处理</b>{esc(stage.get('processing'))}</div><div class="stage-cell"><b>输出</b>{esc(stage.get('output'))}</div></div>{decision_html}{fragment_html}<div class="handoff"><b>{'业务终点' if stage.get('terminal') else '下一步交接'}：</b> {esc(stage.get('terminal_outcome') if stage.get('terminal') else stage.get('next_handoff'))}</div>{f'<details><summary>源码与配置证据</summary>{evidence_html}</details>' if evidence_html else ''}</article>''')
        timeline = f'''<section class="section"><div class="section-title"><h2>完整业务执行故事</h2><span class="muted">按当前项目、生产配置和请求约束展开</span></div><div class="timeline">{''.join(stage_html) if stage_html else '<div class="empty">尚未形成业务阶段。</div>'}</div></section>'''

        field_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for step in dossier["field_lineage_steps"]:
            field_groups[str(step.get("canonical_field"))].append(step)
        field_html = "".join(f'''<div class="field-group"><h3>{esc(name)}</h3>{table(['顺序','数据源','角色','Java 位置','来源','操作/转换','目标','条件','业务用途'],[[x.get('sequence_no'),x.get('source_id'),x.get('lineage_role'),x.get('java_location'),x.get('source'),f"{x.get('operation')} · {x.get('transformation') or ''}",x.get('target'),x.get('condition'),x.get('business_use')] for x in steps])}</div>''' for name, steps in field_groups.items())
        fields = f'''<section class="section"><div class="section-title"><h2>字段全生命周期</h2><span class="muted">从入口、转换、外部映射到落库/返回</span></div>{field_html if field_html else '<div class="empty">尚无字段溯源；审计会将关键字段标记为缺口。</div>'}</section>'''

        persistence_html = "".join(f'''<div class="card span6"><div class="chips">{badge(x.get('status'))}<span class="chip">{esc(x.get('source_id'))}</span><span class="chip">{esc(x.get('operation'))}</span></div><h3>{esc(x.get('store'))}</h3><p>{esc(x.get('business_effect'))}</p>{kv_rows([('执行条件',x.get('condition')),('事务上下文',x.get('transaction_context')),('业务键',x.get('key_fields'))])}{table(['目标字段','值来源','转换','业务用途'],[[m.get('target'),m.get('value_source'),m.get('transformation'),m.get('business_use')] for m in x.get('mappings') or []])}</div>''' for x in dossier["persistence_effects"])
        persistence_section = f'''<section class="section"><div class="section-title"><h2>持久化影响</h2></div><div class="grid">{persistence_html if persistence_html else '<div class="empty span12">当前链路没有已确认的持久化动作。</div>'}</div></section>'''

        external_html = "".join(self._external_card(x) for x in dossier["external_interactions"])
        external_section = f'''<section class="section"><div class="section-title"><h2>外部系统交互</h2></div><div class="grid">{external_html if external_html else '<div class="empty span12">当前链路没有已确认的外部交互。</div>'}</div></section>'''

        open_gaps = [x for x in dossier["gaps"] if x.get("status", "OPEN") == "OPEN"]
        gap_html = "".join(f'''<div class="gap"><div class="chips"><span class="badge bad">{esc(x.get('severity'))}</span><span class="chip">{esc(x.get('category'))}</span></div><b>{esc(x.get('question'))}</b><div class="muted">建议：{esc(x.get('suggested_work_type'))}</div></div>''' for x in open_gaps)
        gaps = f'''<section class="section"><div class="section-title"><h2>已知缺口</h2><span class="muted">缺失内容不会被静默隐藏</span></div>{gap_html if gap_html else '<div class="card">没有开放缺口。</div>'}</section>'''

        return shell(str(scenario.get("name")), hero + timeline + fields + persistence_section + external_section + gaps, "../")

    def _evidence_line(self, evidence: dict[str, Any] | None, evidence_id: str) -> str:
        if not evidence:
            return f'<div class="evidence bad">缺失 Evidence：{esc(evidence_id)}</div>'
        source = evidence.get("source") or {}
        if isinstance(source, dict):
            source_name = source.get('source_id') or source.get('repository') or source.get('source_type') or ''
            location = f"{source_name}:{source.get('file') or source.get('key') or ''}:{source.get('line_start') or ''}"
        else:
            location = str(source)
        return f'<div class="evidence"><b>{esc(evidence_id)}</b> · {esc(evidence.get("evidence_kind"))}<br>{esc(location)}<br>{esc(evidence.get("observation"))}</div>'

    def _external_card(self, item: dict[str, Any]) -> str:
        request = [[x.get("external_name"), x.get("internal_origin"), x.get("transformation"), x.get("business_use")] for x in item.get("request_params") or []]
        response = [[x.get("external_name"), x.get("internal_target") if x.get("consumed", True) else "未消费", x.get("transformation"), x.get("business_use")] for x in item.get("response_params") or []]
        return f'''<div class="card span12"><div class="chips">{badge(item.get('status'))}<span class="chip">{esc(item.get('source_id'))}</span><span class="chip">{esc(item.get('protocol'))}</span></div><h3>{esc(item.get('target_system'))} · {esc(item.get('operation'))}</h3><p>{esc(item.get('business_purpose'))}</p>{kv_rows([('触发条件',item.get('trigger_condition')),('超时/重试/降级',item.get('error_behavior')),('调用方式',item.get('call_mode'))])}<h4>请求参数来源</h4>{table(['外部参数','内部来源','转换','业务用途'],request)}<h4>响应参数去向</h4>{table(['外部参数','内部去向','转换','后续业务用途'],response)}</div>'''

    def _compare_page(self, dossiers: list[dict[str, Any]]) -> str:
        compact = []
        for dossier in dossiers:
            compact.append({key: dossier[key] for key in ("scenario", "trace_stages", "route_decisions", "field_lineage_steps", "persistence_effects", "external_interactions")})
        data = json.dumps(compact, ensure_ascii=False).replace("</", "<\\/")
        body = '''<section class="hero"><h1>链路横向对比</h1><p class="muted">按业务阶段、首个分叉、字段演化、落库和外部交互对齐两个场景。</p><div class="compare-controls"><select id="left"></select><select id="right"></select><button id="run">比较</button></div></section><div id="result" class="section"></div>
<script>const D=__DATA__;
const $=s=>document.querySelector(s), e=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function key(x){return x.stage_key||x.fragment_id||x.name||x.stage_id}function rows(a,b,k){const A=new Map(a.map(x=>[k(x),x])),B=new Map(b.map(x=>[k(x),x]));return [...new Set([...A.keys(),...B.keys()])].map(x=>[x,A.get(x),B.get(x)])}
function tbl(h,rs){return `<div class="scroll"><table><thead><tr>${h.map(x=>`<th>${e(x)}</th>`).join('')}</tr></thead><tbody>${rs.map(r=>`<tr>${r.map(x=>`<td>${e(x)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}
function run(){const a=D[$('#left').value],b=D[$('#right').value];if(!a||!b)return;const stages=rows(a.trace_stages,b.trace_stages,key);const first=stages.find(x=>!x[1]||!x[2]||JSON.stringify(x[1].output)!==JSON.stringify(x[2].output)||x[1].why_current!==x[2].why_current);const dec=rows(a.route_decisions,b.route_decisions,x=>x.question);const ext=rows(a.external_interactions,b.external_interactions,x=>`${x.target_system}|${x.operation}`);const db=rows(a.persistence_effects,b.persistence_effects,x=>`${x.store}|${x.operation}`);$('#result').innerHTML=`<div class="card"><h2>首个分叉</h2>${first?`<b>${e(first[0])}</b><p>${e(first[1]?.why_current||first[1]?.output)} ↔ ${e(first[2]?.why_current||first[2]?.output)}</p>`:'<p>尚未发现已记录的分叉。</p>'}</div><section class="section"><h2>业务阶段</h2>${tbl(['对齐键',a.scenario.name,b.scenario.name],stages.map(x=>[x[0],x[1]?.business_purpose||'缺失',x[2]?.business_purpose||'缺失']))}</section><section class="section"><h2>路由决策</h2>${tbl(['决策',a.scenario.name,b.scenario.name],dec.map(x=>[x[0],`${x[1]?.current_outcome||'—'} · ${x[1]?.reason||''}`,`${x[2]?.current_outcome||'—'} · ${x[2]?.reason||''}`]))}</section><section class="section"><h2>外部交互</h2>${tbl(['交互',a.scenario.name,b.scenario.name],ext.map(x=>[x[0],x[1]?.business_purpose||'无',x[2]?.business_purpose||'无']))}</section><section class="section"><h2>持久化</h2>${tbl(['存储动作',a.scenario.name,b.scenario.name],db.map(x=>[x[0],x[1]?.business_effect||'无',x[2]?.business_effect||'无']))}</section>`}
for(const id of ['left','right'])D.forEach((x,i)=>$('#'+id).insertAdjacentHTML('beforeend',`<option value="${i}">${e(x.scenario.name)}</option>`));if(D.length>1)$('#right').value='1';$('#run').onclick=run;run();</script>'''.replace("__DATA__", data)
        return shell("UCEF 链路横向对比", body)
