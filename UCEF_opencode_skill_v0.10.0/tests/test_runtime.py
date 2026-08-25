from __future__ import annotations

import json
import io
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PACKAGE_ROOT / ".opencode" / "skills" / "ucef"
AGENT_PATH = PACKAGE_ROOT / ".opencode" / "agents" / "ucef-java-chain.md"
sys.path.insert(0, str(SKILL_ROOT / "runtime"))

from ucef.audit import audit_scenario
from ucef.artifacts import ArtifactStore
from ucef.cli import main as cli_main
from ucef.compare import compare_scenarios
from ucef.context import ContextBuilder
from ucef.direct import DirectAnalysisService, MODE_BUDGETS
from ucef.ledger import CheckpointLedger
from ucef.site import DossierSiteBuilder
from ucef.store import FactStore
from ucef.validator import IngestionValidator
from ucef.workspace import AnalysisWorkspace


class OpenCodeAgentPackagingTests(unittest.TestCase):
    def test_direct_agents_have_hard_step_and_tool_boundaries(self):
        text = AGENT_PATH.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---", 2)[1]
        self.assertIn("mode: primary", frontmatter)
        self.assertIn("permission: allow", frontmatter)
        self.assertIn("steps: 30", frontmatter)
        self.assertIn('"ucef_control_*": true', frontmatter)
        self.assertIn("加载 `ucef`", text)
        self.assertIn("receipt", text)
        self.assertIn("Java 项目只读", text)
        for name, role in (
            ("ucef-planner.md", "UCEF Planner"),
            ("ucef-block.md", "UCEF BusinessBlock Worker"),
            ("ucef-finalizer.md", "UCEF Finalizer"),
        ):
            worker = (PACKAGE_ROOT / ".opencode" / "agents" / name).read_text(encoding="utf-8")
            self.assertIn("mode: subagent", worker)
            self.assertIn("edit: deny", worker)
            self.assertIn(role, worker)
            self.assertIn("task: deny", worker)

        tool_text = (PACKAGE_ROOT / ".opencode" / "tools" / "ucef.ts").read_text(encoding="utf-8")
        self.assertIn("Bun.spawn", tool_text)
        self.assertIn("submit_block", tool_text)
        self.assertIn("payload", tool_text)


class UCEFv09Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = FactStore(self.root / "ucef.db")
        self.sample = json.loads((SKILL_ROOT / "templates" / "result.example.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_ingest_audit_reuse_and_site(self):
        report = IngestionValidator(self.store).ingest(self.sample, work_unit_id="WU-DEMO")
        self.assertEqual([], report["errors"])
        audit = audit_scenario(self.store, "SCN-DEMO-PREPAID", persist=True)
        self.assertEqual("READABLE_COMPLETE", audit["readability_status"])

        reuse = self.store.find_fragments(
            "payment.prepaid.submit", "demo/order-service", "hash-payment-v1", "profile-prod-payment-client-v1"
        )
        self.assertEqual("EXACT_REUSE", reuse[0]["reuse"])
        self.assertNotIn("scenario_id", reuse[0]["fragment"])
        method_reuse = self.store.find_method_definitions(
            "order-service", "PrepaidPaymentService#pay", "hash-payment-v1"
        )
        self.assertEqual("EXACT_REUSE", method_reuse[0]["reuse"])
        self.assertEqual("MDEF-DEMO-PAY", method_reuse[0]["method_definition"]["method_definition_id"])

        config = {"site": {"output": "site", "title": "Test Dossiers"}}
        result = DossierSiteBuilder(self.store, config, self.root).build()
        self.assertEqual(1, result["scenarios"])
        page = (self.root / "site" / "scenarios" / "SCN-DEMO-PREPAID.html").read_text(encoding="utf-8")
        for expected in ("预付订单创建", "方法执行树", "节点详情", "字段数据流", "PaymentSystem", "复用行为片段"):
            self.assertIn(expected, page)
        self.assertIn('data-node="NODE-DEMO-PAY"', page)
        self.assertIn('data-field="amount"', page)
        self.assertIn("OrderController#create（本次调用）", page)
        self.assertIn("构建 PaymentRequest", page)

    def test_candidate_can_upgrade_and_revision_is_kept(self):
        report = IngestionValidator(self.store).ingest(self.sample, work_unit_id="WU-1")
        self.assertFalse(report["errors"])
        upgraded = json.loads(json.dumps(self.sample))
        upgraded.pop("scenario")
        upgraded["evidences"] = []
        upgraded["trace_stages"] = []
        upgraded["route_decisions"] = []
        upgraded["field_lineage_steps"] = []
        upgraded["persistence_effects"] = []
        upgraded["external_interactions"] = []
        upgraded["fragments"][0]["status"] = "SCENARIO_CONFIRMED"
        report = IngestionValidator(self.store).ingest(upgraded, scenario_id="SCN-DEMO-PREPAID", work_unit_id="WU-2")
        self.assertFalse(report["errors"])
        current = self.store.get("fragments", "FRAG-DEMO-PAYMENT-v1")
        self.assertEqual("SCENARIO_CONFIRMED", current["status"])
        revisions = self.store.conn.execute(
            "SELECT COUNT(*) AS n FROM entity_revisions WHERE entity_type='fragments' AND entity_id='FRAG-DEMO-PAYMENT-v1'"
        ).fetchone()["n"]
        self.assertEqual(1, revisions)

    def test_compare_aligns_scenario_stages(self):
        IngestionValidator(self.store).ingest(self.sample, work_unit_id="WU-A")
        other = json.loads(json.dumps(self.sample))
        other["scenario"]["scenario_id"] = "SCN-DEMO-POSTPAID"
        other["scenario"]["name"] = "后付订单创建"
        other["scenario"]["scope"]["config_snapshot_id"] = "CFG-PROD-002"
        for collection in ("evidences", "trace_stages", "execution_nodes", "field_inventory", "route_decisions", "field_lineage_steps", "persistence_effects", "external_interactions"):
            for item in other[collection]:
                item["scenario_id"] = "SCN-DEMO-POSTPAID"
        for item in other["trace_stages"]:
            item["stage_id"] += "-B"
        stage_map = {x["stage_id"].removesuffix("-B"): x["stage_id"] for x in other["trace_stages"]}
        node_map = {}
        for item in other["execution_nodes"]:
            old_id = item["execution_node_id"]
            item["execution_node_id"] = old_id + "-B"
            node_map[old_id] = item["execution_node_id"]
        for item in other["execution_nodes"]:
            if item.get("parent_node_id") in node_map:
                item["parent_node_id"] = node_map[item["parent_node_id"]]
            if item.get("stage_id") in stage_map:
                item["stage_id"] = stage_map[item["stage_id"]]
        lineage_map = {}
        for item in other["field_lineage_steps"]:
            old_id = item["lineage_step_id"]
            item["lineage_step_id"] = old_id + "-B"
            lineage_map[old_id] = item["lineage_step_id"]
        for item in other["field_lineage_steps"]:
            item["previous_step_ids"] = [lineage_map.get(value, value) for value in item.get("previous_step_ids") or []]
        for item in other["field_inventory"]:
            item["field_id"] += "-B"
        for collection, id_field in (("route_decisions", "decision_id"), ("persistence_effects", "effect_id"), ("external_interactions", "interaction_id")):
            for item in other[collection]:
                item[id_field] += "-B"
        for collection in ("route_decisions", "field_lineage_steps", "persistence_effects", "external_interactions"):
            for item in other[collection]:
                if item.get("stage_id") in stage_map:
                    item["stage_id"] = stage_map[item["stage_id"]]
                if item.get("execution_node_id") in node_map:
                    item["execution_node_id"] = node_map[item["execution_node_id"]]
        other["route_decisions"][0]["current_outcome"] = "CreditPaymentService"
        other["route_decisions"][0]["reason"] = "生产配置 payment.mode=POSTPAID"
        other["trace_stages"][1]["why_current"] = "CFG-PROD-002 中 payment.mode=POSTPAID"
        other["fragments"] = []
        other["trace_stages"][2].pop("fragment_id", None)
        IngestionValidator(self.store).ingest(other, work_unit_id="WU-B")
        comparison = compare_scenarios(self.store, "SCN-DEMO-PREPAID", "SCN-DEMO-POSTPAID")
        self.assertIsNotNone(comparison["first_divergence"])
        self.assertEqual(5, len(comparison["stages"]))
        self.assertEqual(5, len(comparison["method_invocations"]))
        self.assertEqual(7, len(comparison["field_inventory"]))

    def test_audit_detects_opaque_method_silent_field_and_broken_lineage(self):
        broken = json.loads(json.dumps(self.sample))
        broken["execution_nodes"].append({
            "execution_node_id": "NODE-DEMO-OPAQUE",
            "scenario_id": "SCN-DEMO-PREPAID",
            "source_id": "order-service",
            "parent_node_id": "NODE-DEMO-MODULE",
            "stage_id": "STAGE-DEMO-ENTRY",
            "method_definition_id": "MDEF-DEMO-CONTROLLER",
            "node_type": "METHOD_INVOCATION",
            "sequence_no": 99,
            "name": "未拆解的方法调用",
            "business_purpose": "验证审计能够拒绝只有方法名的节点",
            "input": {"type": "CreateOrderRequest"},
            "output": {"type": "CreateOrderResponse"},
            "status": "STATIC_VERIFIED",
            "evidence_ids": ["EV-DEMO-ENTRY"],
        })
        broken["execution_nodes"][2]["field_reads"].append("silentlyIgnored")
        for step in broken["field_lineage_steps"]:
            if step["lineage_step_id"] == "FLD-DEMO-AMOUNT-3":
                step["previous_step_ids"] = ["FLD-DEMO-ORDER-2"]
        report = IngestionValidator(self.store).ingest(broken, work_unit_id="WU-BROKEN-TREE")
        self.assertFalse(report["errors"])
        codes = {gap["code"] for gap in audit_scenario(self.store, "SCN-DEMO-PREPAID")["generated_gaps"]}
        self.assertIn("METHOD_OPAQUE_NODE-DEMO-OPAQUE", codes)
        self.assertIn("SILENT_FIELD_silentlyIgnored", codes)
        self.assertIn("BROKEN_EDGE_amount_FLD-DEMO-AMOUNT-3", codes)
        self.assertIn("DISCONTINUOUS_amount", codes)

    def test_incomplete_scenario_opens_visible_repair_gaps(self):
        scenario_only = {"scenario": self.sample["scenario"]}
        report = IngestionValidator(self.store).ingest(scenario_only, work_unit_id="WU-INCOMPLETE")
        self.assertFalse(report["errors"])
        audit = audit_scenario(self.store, "SCN-DEMO-PREPAID", persist=True)
        self.assertEqual("PARTIAL", audit["readability_status"])
        self.assertTrue(any(x["code"] == "NO_STAGES" for x in audit["generated_gaps"]))
        open_gaps = [x for x in self.store.list_collection("gaps", "SCN-DEMO-PREPAID") if x.get("status") == "OPEN"]
        self.assertTrue(open_gaps)

    def test_context_pack_contains_scenario_assembly_and_reuse_contract(self):
        IngestionValidator(self.store).ingest(self.sample, work_unit_id="WU-CONTEXT")
        work_unit = json.loads((SKILL_ROOT / "templates" / "work_unit.json").read_text(encoding="utf-8"))
        work_unit["scenario_id"] = "SCN-DEMO-PREPAID"
        work_unit["target_fields"] = ["amount"]
        work_unit["context_scope"] = {
            "anchor_stage_id": "STAGE-DEMO-PAY",
            "anchor_execution_node_id": "NODE-DEMO-PAY",
            "active_fields": ["amount"],
            "load_full_scenario": False,
        }
        work_unit["reuse"] = {
            "logical_keys": ["payment.prepaid.submit"],
            "repository": "demo/order-service",
            "code_hash": "hash-payment-v1",
            "binding_hash": "profile-prod-payment-client-v1",
        }
        context = ContextBuilder(
            SKILL_ROOT / "runtime", self.store,
            {"context": {"max_execution_nodes": 8, "max_field_inventory": 1}},
        ).build(self.sample["scenario"], work_unit)
        self.assertIn("COMPACT SCENARIO ASSEMBLY", context)
        self.assertIn("DURABLE RESUME STATE", context)
        self.assertIn("CONTEXT LOAD PLAN", context)
        self.assertIn("EXACT_REUSE", context)
        self.assertIn("Method Execution Tree and Field Contract", context)
        self.assertIn("NODE-DEMO-PAY-MAP", context)
        tree_slice = context.split('"execution_neighborhood":', 1)[1].split('"active_field_context":', 1)[0]
        self.assertNotIn("NODE-DEMO-SAVE-MAP", tree_slice)
        self.assertIn("FIELD-DEMO-AMOUNT", context)
        self.assertNotIn("FIELD-DEMO-CHANNEL", context)
        self.assertNotIn("Work Unit Output Contract", context)

        work_unit["phase"] = "PROMOTE"
        promote_context = ContextBuilder(
            SKILL_ROOT / "runtime", self.store,
            {"context": {"max_execution_nodes": 8, "max_field_inventory": 1}},
        ).build(self.sample["scenario"], work_unit)
        self.assertIn("Work Unit Output Contract", promote_context)
        self.assertIn("Reader Contract", promote_context)

    def test_layered_slice_gate_context_audit_and_site(self):
        IngestionValidator(self.store).ingest(self.sample, work_unit_id="WU-LAYER-BASE")
        layered = json.loads(
            (SKILL_ROOT / "templates" / "layered_delta.example.json").read_text(encoding="utf-8")
        )
        report = IngestionValidator(self.store).ingest(
            layered, scenario_id="SCN-DEMO-PREPAID", work_unit_id="WU-LAYER"
        )
        self.assertFalse(report["errors"])
        dossier = self.store.scenario_dossier("SCN-DEMO-PREPAID")
        self.assertEqual("SLICE-DEMO-PAY", dossier["implementation_slices"][0]["slice_id"])
        self.assertEqual("GATE-DEMO-PAY-IMPLEMENTATION", dossier["coverage_gates"][0]["gate_id"])

        work_unit = json.loads((SKILL_ROOT / "templates" / "work_unit.json").read_text(encoding="utf-8"))
        work_unit["scenario_id"] = "SCN-DEMO-PREPAID"
        work_unit["role"] = "INTEGRATION"
        work_unit["phase"] = "ASSEMBLE"
        with self.assertRaisesRegex(ValueError, "not allowed for INTEGRATION"):
            ContextBuilder(SKILL_ROOT / "runtime", self.store, {"context": {}}).build(
                self.sample["scenario"], work_unit
            )
        work_unit["allowed_operations"] = [
            "propose_narrative_delta", "propose_gate_status", "open_contradiction_gap"
        ]
        context = ContextBuilder(SKILL_ROOT / "runtime", self.store, {"context": {}}).build(
            self.sample["scenario"], work_unit
        )
        self.assertIn("INTEGRATION WORKER CONTRACT", context)
        self.assertIn("SLICE-DEMO-PAY", context)
        self.assertIn("boundary_summary", context)
        self.assertNotIn('"execution_neighborhood"', context)

        audit = audit_scenario(self.store, "SCN-DEMO-PREPAID")
        self.assertFalse(any(gap["code"].startswith("NO_SLICE_") for gap in audit["generated_gaps"]))
        DossierSiteBuilder(self.store, {"site": {"output": "site"}}, self.root).build()
        page = (self.root / "site" / "scenarios" / "SCN-DEMO-PREPAID.html").read_text(encoding="utf-8")
        self.assertIn("业务主链", page)
        self.assertIn("业务步骤的实现切片", page)
        self.assertIn("构建并提交预付支付请求", page)
        self.assertIn("透明技术桥接", page)


class DirectAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = FactStore(self.root / "ucef.db")
        sample = json.loads((SKILL_ROOT / "templates" / "result.example.json").read_text(encoding="utf-8"))
        report = IngestionValidator(self.store).ingest({"scenario": sample["scenario"]}, work_unit_id="WU-DIRECT")
        self.assertFalse(report["errors"])
        self.service = DirectAnalysisService(self.store)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def plan_payload(self, run_id):
        depths = ["SUMMARY", "CRITICAL", "STANDARD", "STANDARD", "SUMMARY"]
        titles = ["接收并校验请求", "选择生产支付路由", "组装支付报文", "调用支付系统并消费响应", "保存并返回结果"]
        return {
            "plan_id": "PLAN-DIRECT",
            "run_id": run_id,
            "scenario_id": "SCN-DEMO-PREPAID",
            "critical_fields": ["amount", "paymentNo"],
            "terminal_outcome": "支付结果保存并返回",
            "business_blocks": [
                {
                    "block_id": f"BLOCK-DIRECT-{index}",
                    "logical_key": f"demo.payment.block.{index}",
                    "sequence_no": index,
                    "title": title,
                    "business_goal": title,
                    "depth": depths[index - 1],
                    "reason": "影响生产选路、字段、外部边界或最终结果" if depths[index - 1] != "SUMMARY" else "透明交接即可说明",
                    "inputs": ["CreateOrderRequest"],
                    "decision": {},
                    "expected_output": {"state": title},
                    "evidence_refs": [],
                }
                for index, title in enumerate(titles, 1)
            ],
        }

    def block_payload(self, task, run_id):
        block_id = task["block_id"]
        return {
            "block_id": block_id,
            "logical_key": f"demo.payment.block.{int(block_id.rsplit('-', 1)[1])}",
            "scenario_id": "SCN-DEMO-PREPAID",
            "run_id": run_id,
            "sequence_no": int(block_id.rsplit("-", 1)[1]),
            "title": "业务块实现",
            "business_goal": "说明这一段如何影响最终业务结果",
            "why_current": "生产配置与当前请求共同选择这条路径",
            "inputs": [{"name": "amount", "origin": "入口请求", "business_use": "支付金额"}],
            "decision": {"condition": "payment.mode=PREPAID", "selected": "prepaid"},
            "implementation_steps": [
                {"step": 1, "action": "读取并转换金额", "fields": ["amount"], "result": "PaymentRequest.amount"},
                {"step": 2, "action": "执行本块业务动作", "fields": ["paymentNo"], "result": "形成后续输入"},
            ],
            "field_changes": [{"field": "amount", "from": "CreateOrderRequest.amount", "to": "PaymentRequest.amount", "transformation": "分转元", "business_use": "外部支付金额"}],
            "external_calls": [],
            "persistence": [],
            "output": {"name": "PaymentContext", "business_use": "传给下一业务块"},
            "error_behavior": [{"condition": "转换失败", "outcome": "拒绝请求"}],
            "method_evidence": [{"source_id": "order-service", "symbol": "PaymentService#pay", "file": "src/PaymentService.java", "lines": "20-42", "purpose": "实现本块"}],
            "evidence_refs": [],
            "reuse": {"decision": "NEW", "basis": "当前测试首次分析，没有匹配候选"},
            "status": "COMPLETE",
        }

    def test_three_layer_direct_flow_is_bounded_idempotent_and_reader_ready(self):
        started = self.service.start("SCN-DEMO-PREPAID", "STANDARD")
        run_id = started["run"]["run_id"]
        planner = self.service.next_task(run_id)["context"]["task"]
        plan = self.plan_payload(run_id)
        accepted = self.service.submit("plan", run_id, planner["task_id"], plan)
        self.assertEqual("ACCEPTED", accepted["status"])
        self.assertEqual("ALREADY_ACCEPTED", self.service.submit("plan", run_id, planner["task_id"], plan)["status"])

        status = self.service.status(run_id)
        self.assertLessEqual(len(status["tasks"]), MODE_BUDGETS["STANDARD"]["max_model_tasks"])
        self.assertEqual(3, len([task for task in status["tasks"] if task["role"] == "BLOCK"]))

        while True:
            claimed = self.service.next_task(run_id)
            if claimed["status"] != "TASK" or claimed["context"]["task"]["role"] != "BLOCK":
                break
            task = claimed["context"]["task"]
            self.assertNotIn("business_blocks", claimed["context"])
            self.service.submit("block", run_id, task["task_id"], self.block_payload(task, run_id))

        finalizer = claimed["context"]
        self.assertEqual("FINALIZER", finalizer["task"]["role"])
        self.assertNotIn("scenario_plans", finalizer)
        self.assertEqual(5, len(finalizer["business_blocks"]))
        overview = {
            "overview_id": "OVERVIEW-DIRECT",
            "scenario_id": "SCN-DEMO-PREPAID",
            "run_id": run_id,
            "one_sentence": "请求按生产配置选择预付通道，转换字段后调用支付系统并保存结果。",
            "business_context": "订单创建需要同步完成预付支付。",
            "selected_route": {"route": "prepaid", "reason": "payment.mode=PREPAID"},
            "ordered_block_ids": [f"BLOCK-DIRECT-{index}" for index in range(1, 6)],
            "key_field_journeys": [{"field": "amount", "origin": "请求", "journey": "分转元后外发", "sink": "PaymentRequest.amount"}],
            "external_effects": [{"system": "PaymentSystem", "effect": "创建支付单"}],
            "persistence_effects": [{"store": "orders", "effect": "记录支付状态"}],
            "failure_outcomes": [{"condition": "支付失败", "outcome": "订单创建失败"}],
            "open_gaps": [],
        }
        overview_receipt = self.service.submit("overview", run_id, finalizer["task"]["task_id"], overview)
        self.assertEqual("COMPLETE", self.service.status(run_id)["run"]["status"])
        self.assertEqual("ALREADY_ACCEPTED", self.service.submit("overview", run_id, finalizer["task"]["task_id"], overview)["status"])

        config_path = self.root / "payment-prod.json"
        config_path.write_text(json.dumps({
            "payment": {"mode": "PREPAID", "clientSecret": "do-not-render"},
            "timeoutMs": 1500,
            "label": "</SCRIPT><script>alert('unsafe')</script>",
        }), encoding="utf-8")
        artifact = ArtifactStore(self.root).add_json(
            config_path,
            scenario_id="SCN-DEMO-PREPAID",
            source_id="order-service",
            environment="PROD",
            snapshot_id="CFG-PROD-001",
        )

        site_result = DossierSiteBuilder(self.store, {"site": {"output": "site"}}, self.root).build()
        self.assertEqual(1, site_result["artifacts"])
        page = (self.root / "site" / "scenarios" / "SCN-DEMO-PREPAID.html").read_text(encoding="utf-8")
        for expected in ("请求按生产配置选择预付通道", "业务执行过程", "业务时序图", "业务链路导航", "Evidence drawer", "字段如何走完整条链", "外部系统与业务副作用", "技术证据附录", "读取并转换金额", artifact["artifact_id"]):
            self.assertIn(expected, page)
        self.assertIn('class="sequence-step"', page)
        artifact_page = (self.root / "site" / "artifacts" / f"{artifact['artifact_id']}.html").read_text(encoding="utf-8")
        self.assertIn("原始制品", artifact_page)
        self.assertIn("***REDACTED***", artifact_page)
        self.assertNotIn("do-not-render", artifact_page)
        self.assertNotIn("</SCRIPT><script>", artifact_page)
        self.assertIn("\\u003c/SCRIPT>", artifact_page)
        index = (self.root / "site" / "index.html").read_text(encoding="utf-8")
        self.assertIn("READABLE_COMPLETE", index)

        second = self.service.start("SCN-DEMO-PREPAID", "STANDARD")
        second_run = second["run"]["run_id"]
        second_planner_context = self.service.next_task(second_run)["context"]
        self.assertIn("demo.payment.block.2", {item["logical_key"] for item in second_planner_context["reuse_index"]})
        self.service.submit("plan", second_run, second_planner_context["task"]["task_id"], self.plan_payload(second_run))
        second_block_context = self.service.next_task(second_run)["context"]
        self.assertEqual("demo.payment.block.2", second_block_context["planned_block"]["logical_key"])
        self.assertTrue(second_block_context["reuse_candidates"])

    def test_plan_budget_rejects_over_expansion_without_creating_children(self):
        started = self.service.start("SCN-DEMO-PREPAID", "QUICK")
        run_id = started["run"]["run_id"]
        planner = self.service.next_task(run_id)["context"]["task"]
        plan = self.plan_payload(run_id)
        plan["business_blocks"].append({
            "block_id": "BLOCK-DIRECT-6", "logical_key": "demo.payment.block.6", "sequence_no": 6, "title": "额外层",
            "business_goal": "不应创建", "depth": "STANDARD", "reason": "超预算",
        })
        with self.assertRaisesRegex(ValueError, "hard business-block budget"):
            self.service.submit("plan", run_id, planner["task_id"], plan)
        tasks = self.service.status(run_id)["tasks"]
        self.assertEqual(1, len(tasks))

    def test_elapsed_budget_stops_run_and_returns_publishable_status(self):
        started = self.service.start("SCN-DEMO-PREPAID", "QUICK")
        run = started["run"]
        run["deadline_at"] = "2000-01-01T00:00:00+00:00"
        self.store.conn.execute(
            "UPDATE analysis_runs SET deadline_at=?,payload_json=? WHERE run_id=?",
            (run["deadline_at"], json.dumps(run, ensure_ascii=False), run["run_id"]),
        )
        self.store.commit()
        status = self.service.status(run["run_id"])
        self.assertEqual("STOPPED", status["run"]["status"])
        self.assertEqual({"SKIPPED": 1}, status["task_counts"])
        self.assertEqual("HARD_TIME_BUDGET_REACHED", status["tasks"][0]["stop_reason"])
        self.assertEqual("NO_PENDING_TASK", self.service.next_task(run["run_id"])["status"])


class DurableMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = FactStore(self.root / "ucef.db")
        self.sample = json.loads((SKILL_ROOT / "templates" / "result.example.json").read_text(encoding="utf-8"))
        report = IngestionValidator(self.store).ingest(
            {"scenario": self.sample["scenario"]}, work_unit_id="WU-BOOTSTRAP"
        )
        self.assertFalse(report["errors"])
        self.work_unit = json.loads((SKILL_ROOT / "templates" / "work_unit.json").read_text(encoding="utf-8"))
        self.work_unit["work_unit_id"] = "WU-LONG-CHAIN"
        self.work_unit["scenario_id"] = "SCN-DEMO-PREPAID"
        self.work_unit["source_ids"] = ["order-service"]
        self.work_unit["entry_refs"] = [
            {"source_id": "order-service", "symbol": "OrderService#create", "kind": "METHOD"}
        ]
        self.ledger = CheckpointLedger(self.store, {"order-service"})

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def observation(self, subject: str = "OrderService#create", claim: str = "调用 PaymentRouter#route"):
        return {
            "observation_kind": "CALL_EDGE",
            "source_id": "order-service",
            "subject_key": subject,
            "claim": claim,
            "evidence": {
                "file": "src/main/java/demo/OrderService.java",
                "line_start": 40,
                "line_end": 46,
                "symbol": subject,
            },
            "confidence": "STATIC_VERIFIED",
        }

    def checkpoint(self, next_symbol: str = "PaymentRouter#route", visited_symbol: str = "OrderService#create"):
        return {
            "current_focus": {"source_id": "order-service", "symbol": visited_symbol},
            "visited_refs": [
                {"source_id": "order-service", "kind": "METHOD", "symbol": visited_symbol, "outcome": "checked"}
            ],
            "chain_spine": [
                {"sequence_hint": 10, "source_id": "order-service", "symbol": visited_symbol, "state": "CONFIRMED"}
            ],
            "unresolved_questions": [],
            "next_probe": {
                "source_id": "order-service",
                "symbol": next_symbol,
                "reason": "continue the business chain",
                "expected_answer": "next handoff",
            },
            "resume_summary": f"已检查 {visited_symbol}；下一步 {next_symbol}",
            "status": "ACTIVE",
        }

    def test_checkpoint_is_append_only_and_observations_are_deduplicated(self):
        payload = {"observations": [self.observation()], "checkpoint": self.checkpoint()}
        first = self.ledger.capture(payload, self.work_unit)
        second = self.ledger.capture(payload, self.work_unit)
        self.assertFalse(first["errors"])
        self.assertEqual(1, first["inserted"])
        self.assertEqual(0, second["inserted"])
        self.assertEqual(1, second["deduplicated"])
        self.assertTrue(second["no_state_delta"])
        memory = self.store.work_unit_memory("WU-LONG-CHAIN")
        self.assertEqual(1, memory["checkpoint_count"])
        self.assertEqual(1, memory["observation_counts"]["total"])
        self.assertEqual(1, memory["latest_checkpoint"]["sequence_no"])
        audit = audit_scenario(self.store, "SCN-DEMO-PREPAID")
        self.assertEqual("INCOMPLETE", audit["dimensions"]["MEMORY_ASSEMBLY"])

        changed_checkpoint = self.checkpoint("PaymentRouter#selectedHandler")
        changed_checkpoint["no_new_facts_reason"] = "Only the resumable frontier changed"
        changed = self.ledger.capture(
            {"observations": [], "checkpoint": changed_checkpoint}, self.work_unit
        )
        self.assertFalse(changed["errors"])
        self.assertFalse(changed["no_state_delta"])
        self.assertEqual(2, self.store.work_unit_memory("WU-LONG-CHAIN")["checkpoint_count"])

        complete_checkpoint = self.checkpoint()
        complete_checkpoint["status"] = "COMPLETE"
        complete_checkpoint["next_probe"] = None
        rejected = self.ledger.capture(
            {"observations": [], "checkpoint": complete_checkpoint}, self.work_unit
        )
        self.assertTrue(any("pending assembly" in error for error in rejected["errors"]))
        self.assertEqual(2, self.store.work_unit_memory("WU-LONG-CHAIN")["checkpoint_count"])

    def test_resume_context_survives_store_reopen(self):
        payload = {"observations": [self.observation()], "checkpoint": self.checkpoint()}
        self.ledger.capture(payload, self.work_unit)
        self.store.close()
        self.store = FactStore(self.root / "ucef.db")
        context = ContextBuilder(
            SKILL_ROOT / "runtime", self.store,
            {"context": {"max_pending_observations": 10}},
            [{"source_id": "order-service", "path": "D:/repos/order-service"}],
        ).build(self.sample["scenario"], self.work_unit)
        self.assertIn("DURABLE RESUME STATE", context)
        self.assertIn("PaymentRouter#route", context)
        self.assertIn("调用 PaymentRouter#route", context)
        self.assertNotIn("UCEF CONTEXT TRUNCATED", context)

    def test_observation_overflow_is_visible_and_queryable(self):
        observations = [
            self.observation(f"Mapper#field{i}", f"field{i} 映射到 Target.value{i}")
            for i in range(75)
        ]
        report = self.ledger.capture(
            {"observations": observations, "checkpoint": self.checkpoint("Mapper#field74")},
            self.work_unit,
        )
        self.assertFalse(report["errors"])
        memory = self.store.work_unit_memory("WU-LONG-CHAIN", max_observations=5)
        self.assertEqual(75, memory["observation_counts"]["pending_assembly"])
        self.assertEqual(70, memory["omitted_pending_observations"])
        queried = self.store.list_observations(
            work_unit_id="WU-LONG-CHAIN", subject="Mapper#field0", promotion_status="PENDING"
        )
        self.assertEqual("Mapper#field0", queried[0]["subject_key"])
        self.work_unit["context_scope"]["active_fields"] = ["Mapper#field0"]
        context = ContextBuilder(
            SKILL_ROOT / "runtime",
            self.store,
            {"context": {
                "max_pending_observations": 2,
                "observation_priority_pool": 5,
                "max_chars_per_observation_preview": 800,
            }},
        ).build(self.sample["scenario"], self.work_unit)
        self.assertIn('"omitted_pending_observations": 73', context)
        self.assertIn("Mapper#field0", context)
        self.assertIn("Mapper#field74", context)
        self.assertLess(len(context), 250000)
        self.assertNotIn("UCEF CONTEXT TRUNCATED", context)
        DossierSiteBuilder(self.store, {"site": {"output": "site"}}, self.root).build()
        memory_page = (self.root / "site" / "memory.html").read_text(encoding="utf-8")
        self.assertIn("分析记忆", memory_page)
        self.assertIn("Mapper#field74", memory_page)
        self.assertIn("55 条未在本页展开", memory_page)

    def test_canonical_ingestion_promotes_observation_without_deleting_it(self):
        capture = self.ledger.capture(
            {"observations": [self.observation()], "checkpoint": self.checkpoint()},
            self.work_unit,
        )
        observation_id = capture["observation_ids"][0]
        evidence = {
            "evidences": [{
                "evidence_id": "EV-PROMOTED",
                "scenario_id": "SCN-DEMO-PREPAID",
                "evidence_kind": "SOURCE",
                "source": {
                    "source_id": "order-service",
                    "file": "src/main/java/demo/OrderService.java",
                    "symbol": "OrderService#create",
                },
                "observation": "调用 PaymentRouter#route",
                "observation_ids": [observation_id],
            }]
        }
        report = IngestionValidator(self.store).ingest(
            evidence, scenario_id="SCN-DEMO-PREPAID", work_unit_id="WU-LONG-CHAIN"
        )
        self.assertFalse(report["errors"])
        memory = self.store.work_unit_memory("WU-LONG-CHAIN")
        self.assertEqual(1, memory["observation_counts"]["pending_assembly"])
        self.assertEqual(1, memory["observation_counts"]["evidenced"])
        self.assertEqual(0, memory["observation_counts"]["assembled"])

        stage_result = {"trace_stages": [{
            "stage_id": "STAGE-PROMOTED",
            "scenario_id": "SCN-DEMO-PREPAID",
            "source_id": "order-service",
            "sequence_no": 15,
            "stage_type": "PROCESS",
            "name": "进入支付路由",
            "business_purpose": "选择支付处理器",
            "input": {"type": "OrderCommand"},
            "processing": "调用 PaymentRouter#route",
            "output": {"type": "PaymentHandler"},
            "terminal": True,
            "terminal_outcome": "路由处理器已选择",
            "status": "STATIC_VERIFIED",
            "evidence_ids": ["EV-PROMOTED"],
            "observation_ids": [observation_id],
        }]}
        report = IngestionValidator(self.store).ingest(
            stage_result, scenario_id="SCN-DEMO-PREPAID", work_unit_id="WU-LONG-CHAIN"
        )
        self.assertFalse(report["errors"])
        memory = self.store.work_unit_memory("WU-LONG-CHAIN")
        self.assertEqual(0, memory["observation_counts"]["pending_assembly"])
        self.assertEqual(1, memory["observation_counts"]["assembled"])
        self.assertTrue(self.store.observation_exists(observation_id))
        promoted = self.store.list_observations(
            observation_id=observation_id, promotion_status="PROMOTED"
        )
        promoted_targets = {item["entity_id"] for item in promoted[0]["promoted_to"]}
        self.assertEqual({"EV-PROMOTED", "STAGE-PROMOTED"}, promoted_targets)


class IndependentWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace_root = self.root / "analysis" / "order-chain"
        self.source_a = self.root / "repos" / "gateway"
        self.source_b = self.root / "repos" / "order-core"
        self.source_a.mkdir(parents=True)
        self.source_b.mkdir(parents=True)
        self.workspace_root.mkdir(parents=True)
        shutil.copy2(SKILL_ROOT / "templates" / "config.json", self.workspace_root / "workspace.json")
        shutil.copy2(SKILL_ROOT / "templates" / "sources.json", self.workspace_root / "sources.json")
        self.workspace = AnalysisWorkspace.open(self.workspace_root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_multiple_sources_are_registered_outside_workspace(self):
        self.workspace.add_source("gateway", self.source_a, "company/gateway")
        self.workspace.add_source("order-core", self.source_b, "company/order-core")
        status = self.workspace.source_status()
        self.assertEqual(["gateway", "order-core"], [item["source_id"] for item in status])
        self.assertTrue(all(item["exists"] and item["workspace_separate"] for item in status))
        self.assertTrue(all(item["access"] == "READ_ONLY" for item in status))

    def test_nested_source_or_workspace_is_rejected(self):
        nested_source = self.workspace_root / "java-project"
        nested_source.mkdir()
        with self.assertRaisesRegex(ValueError, "separate directory trees"):
            self.workspace.add_source("nested", nested_source)

        repo = self.root / "large-repo"
        nested_workspace_root = repo / "analysis"
        nested_workspace_root.mkdir(parents=True)
        shutil.copy2(SKILL_ROOT / "templates" / "config.json", nested_workspace_root / "workspace.json")
        shutil.copy2(SKILL_ROOT / "templates" / "sources.json", nested_workspace_root / "sources.json")
        nested_workspace = AnalysisWorkspace.open(nested_workspace_root)
        with self.assertRaisesRegex(ValueError, "separate directory trees"):
            nested_workspace.add_source("parent-repo", repo)

    def test_workspace_artifact_path_cannot_escape(self):
        with self.assertRaisesRegex(ValueError, "must stay inside workspace"):
            self.workspace.resolve("../leaked.db")

    def test_cli_registers_redacted_json_artifact_and_builds_independent_page(self):
        source = self.workspace_root / "payment-prod.json"
        source.write_text(json.dumps({
            "payment": {"mode": "PREPAID", "token": "private-token"},
            "timeout": 1500,
        }), encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            result = cli_main([
                "--workspace", str(self.workspace_root),
                "artifact-add", "--file", "payment-prod.json",
                "--scenario", "SCN-PAY", "--source-id", "order-core",
                "--environment", "PROD", "--snapshot", "CFG-2026-08-25",
            ])
        self.assertEqual(0, result)
        receipt = json.loads(output.getvalue())
        artifact_id = receipt["artifact"]["artifact_id"]
        self.assertEqual("REDACTED", receipt["artifact"]["redaction_status"])
        page = self.workspace_root / "site" / "artifacts" / f"{artifact_id}.html"
        self.assertTrue(page.exists())
        content = page.read_text(encoding="utf-8")
        self.assertIn("***REDACTED***", content)
        self.assertNotIn("private-token", content)

    def test_cli_writes_only_to_explicit_workspace_from_arbitrary_cwd(self):
        original_cwd = Path.cwd()
        arbitrary = self.root / "somewhere-else"
        arbitrary.mkdir()
        try:
            os.chdir(arbitrary)
            with redirect_stdout(io.StringIO()):
                result = cli_main(["--workspace", str(self.workspace_root), "init"])
        finally:
            os.chdir(original_cwd)
        self.assertEqual(0, result)
        self.assertTrue((self.workspace_root / "ucef.db").exists())
        self.assertFalse((arbitrary / ".ucef").exists())
        self.assertFalse((self.source_a / ".ucef").exists())

    def test_ingestion_requires_registered_source_identity(self):
        self.workspace.add_source("order-service", self.source_a)
        store = FactStore(self.workspace.database_path)
        try:
            sample = json.loads((SKILL_ROOT / "templates" / "result.example.json").read_text(encoding="utf-8"))
            report = IngestionValidator(store, {"order-service"}, True).ingest(sample, work_unit_id="WU-SOURCE")
            self.assertFalse(report["errors"])

            invalid = json.loads(json.dumps(sample))
            invalid.pop("scenario")
            invalid["fragments"] = []
            invalid["trace_stages"] = []
            invalid["route_decisions"] = []
            invalid["field_lineage_steps"] = []
            invalid["persistence_effects"] = []
            invalid["external_interactions"] = []
            invalid["evidences"] = [dict(sample["evidences"][0])]
            invalid["evidences"][0]["evidence_id"] = "EV-UNKNOWN-SOURCE"
            invalid["evidences"][0]["source"]["source_id"] = "not-registered"
            report = IngestionValidator(store, {"order-service"}, True).ingest(
                invalid, scenario_id="SCN-DEMO-PREPAID", work_unit_id="WU-BAD-SOURCE"
            )
            self.assertTrue(any("Unknown source_id" in str(error) for error in report["errors"]))
        finally:
            store.close()

    def test_cli_checkpoint_resume_and_memory_query(self):
        self.workspace.add_source("order-service", self.source_a)
        scenario_dir = self.workspace_root / "scenarios"
        work_unit_dir = self.workspace_root / "work_units" / "pending"
        runs_dir = self.workspace_root / "runs"
        for directory in (scenario_dir, work_unit_dir, runs_dir):
            directory.mkdir(parents=True, exist_ok=True)

        sample = json.loads((SKILL_ROOT / "templates" / "result.example.json").read_text(encoding="utf-8"))
        (scenario_dir / "pay.json").write_text(
            json.dumps(sample["scenario"], ensure_ascii=False), encoding="utf-8"
        )
        work_unit = json.loads((SKILL_ROOT / "templates" / "work_unit.json").read_text(encoding="utf-8"))
        work_unit["work_unit_id"] = "WU-CLI-MEMORY"
        work_unit["scenario_id"] = "SCN-DEMO-PREPAID"
        work_unit["source_ids"] = ["order-service"]
        work_unit["entry_refs"] = [
            {"source_id": "order-service", "symbol": "OrderService#create", "kind": "METHOD"}
        ]
        work_unit["reuse"]["source_id"] = "order-service"
        (work_unit_dir / "wu.json").write_text(
            json.dumps(work_unit, ensure_ascii=False), encoding="utf-8"
        )
        checkpoint_text = (SKILL_ROOT / "templates" / "checkpoint.json").read_text(encoding="utf-8")
        (runs_dir / "cp.json").write_text(
            checkpoint_text.replace("REPLACE_WITH_REGISTERED_SOURCE_ID", "order-service"),
            encoding="utf-8",
        )

        prefix = ["--workspace", str(self.workspace_root)]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(0, cli_main(prefix + ["scenario-put", "--file", "scenarios/pay.json"]))
            self.assertEqual(0, cli_main(prefix + [
                "checkpoint", "--file", "runs/cp.json", "--work-unit", "work_units/pending/wu.json",
            ]))
            self.assertEqual(0, cli_main(prefix + [
                "resume", "--scenario", "scenarios/pay.json", "--work-unit", "work_units/pending/wu.json",
                "--output", "contexts/resume.md",
            ]))
            self.assertEqual(0, cli_main(prefix + [
                "memory-query", "--work-unit", "WU-CLI-MEMORY", "--subject", "OrderService#create",
            ]))
        resume = (self.workspace_root / "contexts" / "resume.md").read_text(encoding="utf-8")
        self.assertIn("DURABLE RESUME STATE", resume)
        self.assertIn("PaymentRouter#route", resume)


if __name__ == "__main__":
    unittest.main()
