from __future__ import annotations

from collections import defaultdict
from typing import Any

from .core import short_hash
from .store import FactStore


DIMENSIONS = (
    "TOPOLOGY", "ROUTING", "FIELD_LINEAGE", "PERSISTENCE",
    "EXTERNAL_INTERACTIONS", "ERROR_HANDLING", "EVIDENCE",
)


def _gap(
    scenario_id: str,
    category: str,
    code: str,
    question: str,
    severity: str = "HIGH",
    stage_id: str | None = None,
    work_type: str = "SCENARIO_AUDIT_REPAIR",
) -> dict[str, Any]:
    identity = {"scenario_id": scenario_id, "category": category, "code": code, "stage_id": stage_id}
    return {
        "gap_id": f"GAP-AUDIT-{short_hash(identity, 14)}",
        "scenario_id": scenario_id,
        "stage_id": stage_id,
        "category": category,
        "severity": severity,
        "status": "OPEN",
        "auto_generated": True,
        "code": code,
        "question": question,
        "suggested_work_type": work_type,
    }


def audit_scenario(store: FactStore, scenario_id: str, persist: bool = False) -> dict[str, Any]:
    dossier = store.scenario_dossier(scenario_id)
    scenario = dossier["scenario"]
    stages = dossier["trace_stages"]
    decisions = dossier["route_decisions"]
    lineage = dossier["field_lineage_steps"]
    persistence = dossier["persistence_effects"]
    interactions = dossier["external_interactions"]
    generated: list[dict[str, Any]] = []

    if not stages:
        generated.append(_gap(scenario_id, "TOPOLOGY", "NO_STAGES", "链路尚未形成任何可阅读的业务阶段。"))
    else:
        first = stages[0]
        if first.get("stage_type") != "ENTRY":
            generated.append(_gap(scenario_id, "TOPOLOGY", "NO_ENTRY", "第一个阶段没有明确标记为 ENTRY。", stage_id=first.get("stage_id")))
        terminals = [x for x in stages if x.get("terminal") or x.get("stage_type") == "TERMINAL"]
        if not terminals:
            generated.append(_gap(scenario_id, "TOPOLOGY", "NO_TERMINAL", "链路没有明确的业务终点或最终结果。"))
        for stage in stages:
            sid = stage.get("stage_id")
            for field, label in (("business_purpose", "业务目的"), ("input", "输入"), ("processing", "处理"), ("output", "输出")):
                if not stage.get(field):
                    generated.append(_gap(scenario_id, "TOPOLOGY", f"STAGE_{field.upper()}_{sid}", f"阶段 {stage.get('name') or sid} 缺少{label}。", stage_id=sid))
            if not stage.get("terminal") and not stage.get("next_handoff"):
                generated.append(_gap(scenario_id, "TOPOLOGY", f"NO_HANDOFF_{sid}", f"阶段 {stage.get('name') or sid} 缺少下一步交接。", stage_id=sid))
            if stage.get("stage_type") != "ENTRY" and not stage.get("why_current"):
                generated.append(_gap(scenario_id, "TOPOLOGY", f"NO_REASON_{sid}", f"阶段 {stage.get('name') or sid} 没有解释当前场景为什么会执行到这里。", stage_id=sid))

    for decision in decisions:
        did = decision.get("decision_id")
        if not decision.get("current_outcome"):
            generated.append(_gap(scenario_id, "ROUTING", f"OUTCOME_{did}", f"路由决策 {decision.get('question') or did} 缺少当前场景结果。", stage_id=decision.get("stage_id"), work_type="ROUTE_DECISION_ANALYSIS"))
        if not decision.get("inputs") or not decision.get("reason"):
            generated.append(_gap(scenario_id, "ROUTING", f"INPUT_{did}", f"路由决策 {decision.get('question') or did} 缺少输入来源或选择原因。", stage_id=decision.get("stage_id"), work_type="ROUTE_DECISION_ANALYSIS"))
    decision_stage_ids = {x.get("stage_id") for x in decisions}
    for stage in stages:
        if stage.get("stage_type") == "ROUTE" and stage.get("stage_id") not in decision_stage_ids:
            generated.append(_gap(scenario_id, "ROUTING", f"MISSING_DECISION_{stage.get('stage_id')}", f"路由阶段 {stage.get('name')} 没有结构化的当前决策结果。", stage_id=stage.get("stage_id"), work_type="ROUTE_DECISION_ANALYSIS"))

    by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for step in lineage:
        by_field[str(step.get("canonical_field"))].append(step)
        lid = step.get("lineage_step_id")
        if not step.get("source"):
            generated.append(_gap(scenario_id, "FIELD_LINEAGE", f"SOURCE_{lid}", f"字段步骤 {lid} 缺少值来源。", stage_id=step.get("stage_id"), work_type="FIELD_LINEAGE"))
        if not step.get("business_use"):
            generated.append(_gap(scenario_id, "FIELD_LINEAGE", f"USE_{lid}", f"字段步骤 {lid} 缺少业务用途。", stage_id=step.get("stage_id"), work_type="FIELD_LINEAGE"))
    external_sinks = {
        str(param.get("canonical_field"))
        for interaction in interactions
        for param in interaction.get("request_params") or []
        if param.get("canonical_field")
    }
    persistence_sinks = {
        str(mapping.get("canonical_field"))
        for effect in persistence
        for mapping in effect.get("mappings") or []
        if mapping.get("canonical_field")
    }
    for field in scenario.get("critical_fields") or []:
        field = str(field)
        steps = by_field.get(field) or []
        if not steps:
            generated.append(_gap(scenario_id, "FIELD_LINEAGE", f"MISSING_{field}", f"关键字段 {field} 尚无贯穿链路的溯源。", work_type="FIELD_LINEAGE"))
            continue
        if not any(x.get("lineage_role") == "ORIGIN" for x in steps):
            generated.append(_gap(scenario_id, "FIELD_LINEAGE", f"NO_ORIGIN_{field}", f"关键字段 {field} 没有明确的原始来源。", work_type="FIELD_LINEAGE"))
        has_sink = any(x.get("lineage_role") == "SINK" for x in steps) or field in external_sinks or field in persistence_sinks
        if not has_sink:
            generated.append(_gap(scenario_id, "FIELD_LINEAGE", f"NO_SINK_{field}", f"关键字段 {field} 没有明确的最终消费、外部发送或落库位置。", work_type="FIELD_LINEAGE"))

    persistence_stage_ids = {x.get("stage_id") for x in persistence}
    for stage in stages:
        if stage.get("stage_type") == "PERSIST" and stage.get("stage_id") not in persistence_stage_ids:
            generated.append(_gap(scenario_id, "PERSISTENCE", f"MISSING_EFFECT_{stage.get('stage_id')}", f"持久化阶段 {stage.get('name')} 没有结构化的表/字段写入信息。", stage_id=stage.get("stage_id"), work_type="PERSISTENCE_TRACE"))

    for effect in persistence:
        eid = effect.get("effect_id")
        mappings = effect.get("mappings") or []
        if not mappings:
            generated.append(_gap(scenario_id, "PERSISTENCE", f"MAP_{eid}", f"持久化动作 {eid} 没有字段映射。", stage_id=effect.get("stage_id"), work_type="PERSISTENCE_TRACE"))
        for index, mapping in enumerate(mappings):
            if not mapping.get("value_source") or not mapping.get("business_use"):
                generated.append(_gap(scenario_id, "PERSISTENCE", f"MAP_{eid}_{index}", f"持久化字段 {mapping.get('target') or index} 缺少来源或业务用途。", stage_id=effect.get("stage_id"), work_type="PERSISTENCE_TRACE"))

    for interaction in interactions:
        iid = interaction.get("interaction_id")
        for index, param in enumerate(interaction.get("request_params") or []):
            if not param.get("internal_origin") or not param.get("business_use"):
                generated.append(_gap(scenario_id, "EXTERNAL_INTERACTIONS", f"REQ_{iid}_{index}", f"外部请求参数 {param.get('external_name') or index} 缺少内部来源或业务用途。", stage_id=interaction.get("stage_id"), work_type="EXTERNAL_INTERACTION_TRACE"))
        for index, param in enumerate(interaction.get("response_params") or []):
            if param.get("consumed", True) and (not param.get("internal_target") or not param.get("business_use")):
                generated.append(_gap(scenario_id, "EXTERNAL_INTERACTIONS", f"RESP_{iid}_{index}", f"外部响应参数 {param.get('external_name') or index} 缺少内部去向或业务用途。", stage_id=interaction.get("stage_id"), work_type="EXTERNAL_INTERACTION_TRACE"))
        if not interaction.get("error_behavior"):
            generated.append(_gap(scenario_id, "ERROR_HANDLING", f"ERROR_{iid}", f"外部交互 {interaction.get('target_system') or iid} 缺少超时、异常、重试或降级说明。", stage_id=interaction.get("stage_id"), work_type="EXTERNAL_INTERACTION_TRACE"))
    interaction_stage_ids = {x.get("stage_id") for x in interactions}
    for stage in stages:
        if stage.get("stage_type") == "EXTERNAL" and stage.get("stage_id") not in interaction_stage_ids:
            generated.append(_gap(scenario_id, "EXTERNAL_INTERACTIONS", f"MISSING_INTERACTION_{stage.get('stage_id')}", f"外部交互阶段 {stage.get('name')} 没有结构化的请求/响应契约。", stage_id=stage.get("stage_id"), work_type="EXTERNAL_INTERACTION_TRACE"))

    evidence_ids = {x.get("evidence_id") for x in dossier["evidences"]}
    for collection in ("fragments", "trace_stages", "route_decisions", "field_lineage_steps", "persistence_effects", "external_interactions"):
        for item in dossier[collection]:
            if collection == "trace_stages" and item.get("fragment_id") and not item.get("evidence_ids"):
                continue
            for evidence_id in item.get("evidence_ids") or []:
                if evidence_id not in evidence_ids:
                    generated.append(_gap(scenario_id, "EVIDENCE", f"MISSING_{collection}_{evidence_id}", f"{collection} 引用了不存在的 Evidence {evidence_id}。", stage_id=item.get("stage_id")))

    status_by_dimension: dict[str, str] = {}
    for dimension in DIMENSIONS:
        dimension_gaps = [x for x in generated if x["category"] == dimension]
        if not dimension_gaps:
            if dimension == "ROUTING" and not decisions:
                status_by_dimension[dimension] = "NOT_APPLICABLE"
            elif dimension == "PERSISTENCE" and not persistence:
                status_by_dimension[dimension] = "NOT_APPLICABLE"
            elif dimension in {"EXTERNAL_INTERACTIONS", "ERROR_HANDLING"} and not interactions:
                status_by_dimension[dimension] = "NOT_APPLICABLE"
            elif dimension == "FIELD_LINEAGE" and not lineage and not scenario.get("critical_fields"):
                status_by_dimension[dimension] = "UNKNOWN"
            else:
                status_by_dimension[dimension] = "COMPLETE"
        else:
            status_by_dimension[dimension] = "INCOMPLETE" if any(x["severity"] == "HIGH" for x in dimension_gaps) else "PARTIAL"

    readability = "READABLE_COMPLETE" if all(x in {"COMPLETE", "NOT_APPLICABLE"} for x in status_by_dimension.values()) else "PARTIAL"
    report = {
        "scenario_id": scenario_id,
        "readability_status": readability,
        "dimensions": status_by_dimension,
        "generated_gaps": generated,
    }
    if persist:
        scenario["readability_status"] = readability
        scenario["completeness"] = status_by_dimension
        store.upsert("scenarios", scenario, "AUDIT")
        store.sync_audit_gaps(scenario_id, generated)
    return report
