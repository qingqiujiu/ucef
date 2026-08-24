from __future__ import annotations

from collections import defaultdict
from typing import Any

from .core import short_hash
from .store import FactStore


DIMENSIONS = (
    "TOPOLOGY", "IMPLEMENTATION_LAYER", "COVERAGE_GATES", "EXECUTION_TREE", "ROUTING", "FIELD_LINEAGE", "PERSISTENCE",
    "EXTERNAL_INTERACTIONS", "ERROR_HANDLING", "EVIDENCE", "MEMORY_ASSEMBLY",
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
    implementation_slices = dossier["implementation_slices"]
    coverage_gates = dossier["coverage_gates"]
    execution_nodes = dossier["execution_nodes"]
    method_definitions = {
        str(item.get("method_definition_id")): item for item in dossier["method_definitions"]
    }
    field_inventory = dossier["field_inventory"]
    decisions = dossier["route_decisions"]
    lineage = dossier["field_lineage_steps"]
    persistence = dossier["persistence_effects"]
    interactions = dossier["external_interactions"]
    generated: list[dict[str, Any]] = []
    layered = bool((scenario.get("analysis_profile") or {}).get("layered") or implementation_slices or coverage_gates)

    pending_observations = store.scenario_pending_observation_count(scenario_id)
    if pending_observations:
        generated.append(_gap(
            scenario_id,
            "MEMORY_ASSEMBLY",
            "UNASSEMBLED_OBSERVATIONS",
            f"仍有 {pending_observations} 条已持久化 Observation 尚未装配进正式业务链路。",
            work_type="SCENARIO_AUDIT_REPAIR",
        ))

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

    node_by_id = {str(node.get("execution_node_id")): node for node in execution_nodes}

    if layered:
        slices_by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in implementation_slices:
            slices_by_stage[str(item.get("stage_id"))].append(item)
            if item.get("closure_status") not in {"COMPLETE", "GAP"}:
                generated.append(_gap(
                    scenario_id,
                    "IMPLEMENTATION_LAYER",
                    f"OPEN_SLICE_{item.get('slice_id')}",
                    f"实现切片 {item.get('name') or item.get('slice_id')} 尚未达到语义闭合，也未转成 Gap。",
                    stage_id=item.get("stage_id"),
                    work_type="BUSINESS_STAGE_TRACE",
                ))
        for stage in stages:
            if stage.get("implementation_required", False) and not slices_by_stage.get(str(stage.get("stage_id"))):
                generated.append(_gap(
                    scenario_id,
                    "IMPLEMENTATION_LAYER",
                    f"NO_SLICE_{stage.get('stage_id')}",
                    f"业务步骤 {stage.get('name') or stage.get('stage_id')} 没有实现切片，读者只能看到表面描述。",
                    stage_id=stage.get("stage_id"),
                    work_type="BUSINESS_STAGE_TRACE",
                ))
        for gate in coverage_gates:
            if gate.get("status") == "OPEN" and gate.get("priority") in {"G0", "G1"}:
                generated.append(_gap(
                    scenario_id,
                    "COVERAGE_GATES",
                    f"BLOCKING_GATE_{gate.get('gate_id')}",
                    f"{gate.get('priority')} 门槛尚未关闭：{gate.get('question')}",
                    stage_id=gate.get("stage_id"),
                    work_type="BUSINESS_STAGE_TRACE",
                ))
    children: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in execution_nodes:
        parent_id = node.get("parent_node_id")
        if parent_id:
            children[str(parent_id)].append(node)

    if not execution_nodes:
        generated.append(_gap(
            scenario_id, "EXECUTION_TREE", "NO_EXECUTION_TREE",
            "尚未形成项目/模块 → 方法调用 → 方法内部步骤的执行树。",
            work_type="METHOD_EXECUTION_TRACE",
        ))
    else:
        roots = [node for node in execution_nodes if not node.get("parent_node_id")]
        if not any(node.get("node_type") == "MODULE" for node in roots):
            generated.append(_gap(
                scenario_id, "EXECUTION_TREE", "NO_MODULE_ROOT",
                "执行树没有 MODULE 根节点，无法按项目/模块组织方法调用。",
                work_type="METHOD_EXECUTION_TRACE",
            ))
        for node in execution_nodes:
            node_id = str(node.get("execution_node_id"))
            parent_id = node.get("parent_node_id")
            if parent_id and str(parent_id) not in node_by_id:
                generated.append(_gap(
                    scenario_id, "EXECUTION_TREE", f"ORPHAN_{node_id}",
                    f"执行节点 {node.get('name') or node_id} 的父节点不存在。",
                    stage_id=node.get("stage_id"), work_type="METHOD_EXECUTION_TRACE",
                ))
            if node.get("node_type") == "METHOD_INVOCATION":
                method_id = str(node.get("method_definition_id") or "")
                if method_id not in method_definitions:
                    generated.append(_gap(
                        scenario_id, "EXECUTION_TREE", f"METHOD_DEF_{node_id}",
                        f"方法调用 {node.get('name') or node_id} 没有关联可复用的方法定义。",
                        stage_id=node.get("stage_id"), work_type="METHOD_EXECUTION_TRACE",
                    ))
                direct_steps = [child for child in children.get(node_id, []) if child.get("node_type") == "STEP"]
                if not direct_steps:
                    generated.append(_gap(
                        scenario_id, "EXECUTION_TREE", f"METHOD_OPAQUE_{node_id}",
                        f"方法调用 {node.get('name') or node_id} 只有方法/对象事实，没有拆出方法内部步骤。",
                        stage_id=node.get("stage_id"), work_type="METHOD_STEP_DECOMPOSITION",
                    ))
            if node.get("node_type") == "STEP":
                for field in ("field_reads", "field_writes"):
                    if field not in node or not isinstance(node.get(field), list):
                        generated.append(_gap(
                            scenario_id, "EXECUTION_TREE", f"STEP_{field.upper()}_{node_id}",
                            f"方法步骤 {node.get('name') or node_id} 未明确记录 {field}，可能静默忽略字段。",
                            stage_id=node.get("stage_id"), work_type="METHOD_STEP_DECOMPOSITION",
                        ))

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> bool:
            if node_id in visiting:
                return True
            if node_id in visited:
                return False
            visiting.add(node_id)
            has_cycle = any(visit(str(child.get("execution_node_id"))) for child in children.get(node_id, []))
            visiting.remove(node_id)
            visited.add(node_id)
            return has_cycle

        if any(visit(str(node.get("execution_node_id"))) for node in execution_nodes):
            generated.append(_gap(
                scenario_id, "EXECUTION_TREE", "PARENT_CYCLE",
                "执行树 parent_node_id 形成循环；递归必须使用 RECURSION 回指节点，不能形成真实父子环。",
                work_type="METHOD_EXECUTION_TRACE",
            ))

        covered_stage_ids = {node.get("stage_id") for node in execution_nodes if node.get("stage_id")}
        for stage in stages:
            if stage.get("stage_id") not in covered_stage_ids:
                generated.append(_gap(
                    scenario_id, "EXECUTION_TREE", f"UNMAPPED_STAGE_{stage.get('stage_id')}",
                    f"业务阶段 {stage.get('name')} 尚未落到具体方法调用或内部步骤。",
                    stage_id=stage.get("stage_id"), work_type="METHOD_EXECUTION_TRACE",
                ))

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
        if not step.get("execution_node_id") or str(step.get("execution_node_id")) not in node_by_id:
            generated.append(_gap(scenario_id, "FIELD_LINEAGE", f"NODE_{lid}", f"字段步骤 {lid} 没有定位到方法内部执行节点。", stage_id=step.get("stage_id"), work_type="FIELD_LINEAGE"))

    inventory_by_field = {str(item.get("canonical_field")): item for item in field_inventory}
    if not field_inventory:
        generated.append(_gap(
            scenario_id, "FIELD_LINEAGE", "NO_FIELD_INVENTORY",
            "入口字段尚未盘点；无法判断哪些字段被追踪、排除或遗漏。",
            work_type="FIELD_INVENTORY",
        ))
    for item in field_inventory:
        field = str(item.get("canonical_field"))
        tracking = item.get("tracking_status")
        if tracking == "GAP":
            generated.append(_gap(
                scenario_id, "FIELD_LINEAGE", f"INVENTORY_GAP_{field}",
                f"字段 {field} 已发现但尚未决定追踪范围。", work_type="FIELD_INVENTORY",
            ))
        if tracking == "EXCLUDED" and not item.get("exclusion_reason"):
            generated.append(_gap(
                scenario_id, "FIELD_LINEAGE", f"EXCLUSION_{field}",
                f"字段 {field} 被排除但没有说明原因。", work_type="FIELD_INVENTORY",
            ))

    fields_used_by_steps = {
        str(field)
        for node in execution_nodes
        for key in ("field_reads", "field_writes")
        for field in (node.get(key) or [])
    }
    for field in sorted(fields_used_by_steps - set(inventory_by_field)):
        generated.append(_gap(
            scenario_id, "FIELD_LINEAGE", f"SILENT_FIELD_{field}",
            f"方法步骤读写了字段 {field}，但字段清单没有记录它；禁止静默忽略。",
            work_type="FIELD_INVENTORY",
        ))
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
        inventory_item = inventory_by_field.get(field)
        if not inventory_item:
            generated.append(_gap(scenario_id, "FIELD_LINEAGE", f"NO_INVENTORY_{field}", f"关键字段 {field} 未进入字段清单。", work_type="FIELD_INVENTORY"))
        elif inventory_item.get("tracking_status") != "TRACKED":
            generated.append(_gap(scenario_id, "FIELD_LINEAGE", f"NOT_TRACKED_{field}", f"关键字段 {field} 必须完整追踪，不能标记为排除或待定。", work_type="FIELD_INVENTORY"))
        steps = by_field.get(field) or []
        if not steps:
            generated.append(_gap(scenario_id, "FIELD_LINEAGE", f"MISSING_{field}", f"关键字段 {field} 尚无贯穿链路的溯源。", work_type="FIELD_LINEAGE"))
            continue
        if not any(x.get("lineage_role") == "ORIGIN" for x in steps):
            generated.append(_gap(scenario_id, "FIELD_LINEAGE", f"NO_ORIGIN_{field}", f"关键字段 {field} 没有明确的原始来源。", work_type="FIELD_LINEAGE"))
        has_sink = any(x.get("lineage_role") == "SINK" for x in steps) or field in external_sinks or field in persistence_sinks
        if not has_sink:
            generated.append(_gap(scenario_id, "FIELD_LINEAGE", f"NO_SINK_{field}", f"关键字段 {field} 没有明确的最终消费、外部发送或落库位置。", work_type="FIELD_LINEAGE"))

    for field, item in inventory_by_field.items():
        if item.get("tracking_status") != "TRACKED":
            continue
        steps = by_field.get(field) or []
        if not steps:
            generated.append(_gap(scenario_id, "FIELD_LINEAGE", f"TRACKED_EMPTY_{field}", f"字段清单要求追踪 {field}，但没有任何字段步骤。", work_type="FIELD_LINEAGE"))
            continue
        if not any(step.get("lineage_role") == "ORIGIN" for step in steps):
            generated.append(_gap(
                scenario_id, "FIELD_LINEAGE", f"TRACKED_NO_ORIGIN_{field}",
                f"字段清单要求追踪 {field}，但没有原始来源。", work_type="FIELD_LINEAGE",
            ))
        actual_sinks = {
            str(step.get("target")) for step in steps if step.get("lineage_role") == "SINK"
        }
        for expected_sink in item.get("expected_sinks") or []:
            if str(expected_sink) not in actual_sinks:
                generated.append(_gap(
                    scenario_id, "FIELD_LINEAGE", f"EXPECTED_SINK_{field}_{short_hash(expected_sink, 8)}",
                    f"字段 {field} 的预期终点 {expected_sink} 尚未由字段步骤证实。",
                    work_type="FIELD_LINEAGE",
                ))
        step_by_id = {str(step.get("lineage_step_id")): step for step in steps}
        origins = {step_id for step_id, step in step_by_id.items() if step.get("lineage_role") == "ORIGIN"}
        reachable = set(origins)
        changed = True
        while changed:
            changed = False
            for step_id, step in step_by_id.items():
                previous = {str(value) for value in step.get("previous_step_ids") or []}
                if step_id not in reachable and previous and previous.issubset(reachable):
                    reachable.add(step_id)
                    changed = True
        for step_id, step in step_by_id.items():
            for previous_id in step.get("previous_step_ids") or []:
                if str(previous_id) not in step_by_id:
                    generated.append(_gap(
                        scenario_id, "FIELD_LINEAGE", f"BROKEN_EDGE_{field}_{step_id}",
                        f"字段 {field} 的步骤 {step_id} 引用了缺失或其他字段的前序步骤 {previous_id}。",
                        stage_id=step.get("stage_id"), work_type="FIELD_LINEAGE",
                    ))
        unreachable_sinks = [
            step_id for step_id, step in step_by_id.items()
            if step.get("lineage_role") == "SINK" and step_id not in reachable
        ]
        if unreachable_sinks:
            generated.append(_gap(
                scenario_id, "FIELD_LINEAGE", f"DISCONTINUOUS_{field}",
                f"字段 {field} 虽有起点和终点，但中间链路不连续：{', '.join(unreachable_sinks)}。",
                work_type="FIELD_LINEAGE",
            ))

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
    for collection in (
        "fragments", "method_definitions", "trace_stages", "implementation_slices", "coverage_gates", "execution_nodes", "field_inventory",
        "route_decisions", "field_lineage_steps", "persistence_effects", "external_interactions",
    ):
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
            if dimension in {"IMPLEMENTATION_LAYER", "COVERAGE_GATES"} and not layered:
                status_by_dimension[dimension] = "NOT_APPLICABLE"
            elif dimension == "ROUTING" and not decisions:
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
