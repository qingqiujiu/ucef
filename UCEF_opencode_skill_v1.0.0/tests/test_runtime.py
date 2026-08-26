from __future__ import annotations

import json
import io
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PACKAGE_ROOT / ".opencode" / "skills" / "ucef"
AGENT_PATH = PACKAGE_ROOT / ".opencode" / "agents" / "ucef-java-chain.md"
sys.path.insert(0, str(SKILL_ROOT / "runtime"))

from ucef.audit import audit_scenario
from ucef.artifacts import ArtifactStore
from ucef.cli import main as cli_main
from ucef.compare import compare_scenarios
from ucef.context import ContextBuilder
from ucef.direct import DirectAnalysisService, MODE_BUDGETS, SubmissionContractError
from ucef.graph import GraphContractError, KnowledgeGraphService
from ucef.ledger import CheckpointLedger
from ucef.site import DossierSiteBuilder
from ucef.store import FactStore
from ucef.validator import IngestionValidator
from ucef.workspace import AnalysisWorkspace


class OpenCodeAgentPackagingTests(unittest.TestCase):
    def test_adaptive_agent_keeps_global_understanding_and_read_only_tool_boundaries(self):
        text = AGENT_PATH.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---", 2)[1]
        self.assertIn("mode: primary", frontmatter)
        self.assertIn("permission:", frontmatter)
        self.assertIn('"*": deny', frontmatter)
        self.assertNotIn("steps:", frontmatter)
        self.assertIn('"index-mcp_*": allow', frontmatter)
        self.assertIn('"ucef_analysis_*": allow', frontmatter)
        self.assertIn('"ucef_knowledge_*": allow', frontmatter)
        self.assertIn('"ucef_configuration_*": allow', frontmatter)
        self.assertIn('"ucef_workspace_*": allow', frontmatter)
        self.assertIn('"ucef_scenario_*": allow', frontmatter)
        self.assertIn("ucef-probe: allow", frontmatter)
        self.assertNotIn('"ucef_control_*": allow', frontmatter)
        self.assertNotIn("ucef-planner: allow", frontmatter)
        self.assertNotIn("ucef-block: allow", frontmatter)
        self.assertNotIn("ucef-finalizer: allow", frontmatter)
        self.assertNotIn("tools:", frontmatter)
        self.assertNotIn('"ucef_submit_*": allow', frontmatter)
        self.assertIn("加载 `ucef`", text)
        self.assertIn("Java 项目只读", text)
        self.assertIn("CONFIG_UNRESOLVED", text)
        self.assertIn("普通 DTO 复制", text)
        probe = (PACKAGE_ROOT / ".opencode" / "agents" / "ucef-probe.md").read_text(encoding="utf-8")
        probe_frontmatter = probe.split("---", 2)[1]
        self.assertIn("mode: subagent", probe_frontmatter)
        self.assertIn('"*": deny', probe_frontmatter)
        self.assertIn("task: deny", probe_frontmatter)
        self.assertIn('"index-mcp_*": allow', probe_frontmatter)
        for removed in ("ucef-planner.md", "ucef-block.md", "ucef-finalizer.md"):
            self.assertFalse((PACKAGE_ROOT / ".opencode" / "agents" / removed).exists())

        tool_text = (PACKAGE_ROOT / ".opencode" / "tools" / "ucef.ts").read_text(encoding="utf-8")
        self.assertIn("Bun.spawn", tool_text)
        self.assertIn("payload", tool_text)
        self.assertIn("tool.schema.object({}).passthrough()", tool_text)
        self.assertNotIn("JSON.parse(args.payload)", tool_text)
        self.assertIn('PYTHONUTF8: "1"', tool_text)
        self.assertIn('PYTHONIOENCODING: "utf-8"', tool_text)
        self.assertIn("new TextEncoder().encode(payload)", tool_text)
        self.assertIn('new TextDecoder("utf-8", { fatal: true })', tool_text)
        for operation in (
            "workspace_bootstrap", "source_register", "scenario_register",
            "artifact_register", "site_build", "analysis_start", "analysis_record",
            "analysis_context", "analysis_status", "analysis_finish", "knowledge_query",
            "knowledge_lineage", "configuration_resolve", "entity_rename",
        ):
            self.assertIn(f"export const {operation}", tool_text)

    def test_skill_frontmatter_is_small_and_release_versions_agree(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = skill.split("---", 2)[1]
        keys = [line.split(":", 1)[0] for line in frontmatter.splitlines() if line.strip()]
        self.assertEqual(["name", "description"], keys)
        self.assertIn("references/ADAPTIVE_ANALYSIS_CONTRACT.md", skill)
        self.assertNotIn("references/DIRECT_ANALYSIS_CONTRACT.md", skill)
        self.assertEqual("1.0.0", (SKILL_ROOT / "VERSION").read_text(encoding="utf-8").strip())
        config = json.loads((SKILL_ROOT / "templates" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual("1.0.0", config["workspace"]["format_version"])
        self.assertFalse(config["adaptive_analysis"]["include_logs"])


class AdaptiveKnowledgeGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = FactStore(self.root / "ucef.db")
        self.sample = json.loads((SKILL_ROOT / "templates" / "result.example.json").read_text(encoding="utf-8"))
        report = IngestionValidator(self.store).ingest(
            {"scenario": self.sample["scenario"]}, work_unit_id="ADAPTIVE-BOOTSTRAP"
        )
        self.assertFalse(report["errors"])
        self.delta = json.loads((SKILL_ROOT / "templates" / "adaptive_delta.example.json").read_text(encoding="utf-8"))
        self.service = KnowledgeGraphService(
            self.store,
            registered_sources={"order-service"},
            config={"adaptive_analysis": {"context_target_tokens": 1200, "total_token_budget": 5000}},
        )
        self.session = self.service.start_session(
            "SCN-DEMO-PREPAID", priority_fields=["amount"]
        )["session"]

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def record_example(self):
        return self.service.record_delta(self.session["session_id"], self.delta)

    def test_adaptive_milestone_records_shared_graph_without_planner_or_fixed_blocks(self):
        receipt = self.record_example()
        self.assertEqual("RECORDED", receipt["status"])
        self.assertEqual(1, self.service.summary(self.session["session_id"])["session"]["milestone_count"])
        self.assertNotIn("payload", receipt)
        graph = self.service.scenario_graph("SCN-DEMO-PREPAID")
        self.assertEqual(2, graph["coverage"]["systems"])
        self.assertEqual(1, graph["coverage"]["decisions"])
        self.assertEqual(2, graph["coverage"]["branches"])
        self.assertEqual(1, graph["coverage"]["unresolved_configurations"])
        configuration = self.service.find_entity("CONFIG:payment.channel.mode", "SCN-DEMO-PREPAID")
        self.assertEqual("CONFIG_UNRESOLVED", configuration["status"])
        self.assertEqual([], self.store.list_collection("analysis_tasks", "SCN-DEMO-PREPAID"))
        self.assertEqual([], self.store.list_collection("business_blocks", "SCN-DEMO-PREPAID"))

    def test_field_projection_collapses_dto_copies_and_preserves_meaningful_transformations(self):
        self.record_example()
        projection = self.service.field_projection("SCN-DEMO-PREPAID", "amount")
        self.assertEqual("P0", projection["priority"])
        self.assertEqual(6, projection["raw_event_count"])
        self.assertEqual(2, projection["collapsed_copy_count"])
        self.assertEqual("COLLAPSED_COPY", projection["events"][0]["kind"])
        operations = [item.get("operation") for item in projection["events"]]
        self.assertIn("UNIT_CONVERSION", operations)
        self.assertIn("PERSIST", operations)
        self.assertIn("OUTBOUND", operations)
        self.assertIn("RESPONSE_CONSUME", operations)

    def test_configuration_resolution_selects_confirmed_branch_without_guessing(self):
        self.record_example()
        resolved = self.service.resolve_configuration(
            "SCN-DEMO-PREPAID", "payment.channel.mode", "DIRECT", evidence="padb://payment.channel.mode"
        )
        self.assertEqual("CONFIG_CONFIRMED", resolved["status"])
        self.assertEqual(1, len(resolved["selected_branch_ids"]))
        branches = self.service.list_entities(entity_type="BRANCH", scenario_id="SCN-DEMO-PREPAID")
        states = {item["display_name"]: item["status"] for item in branches}
        self.assertEqual("ACTIVE", states["直连支付"])
        self.assertEqual("INACTIVE", states["异步支付"])
        self.assertEqual(0, self.service.coverage("SCN-DEMO-PREPAID")["unresolved_configurations"])

    def test_multiple_decisions_can_share_one_configuration_without_mixing_selected_branches(self):
        self.record_example()
        self.service.record_delta(self.session["session_id"], {
            "summary": "同一渠道配置还决定支付结果通知方式",
            "decisions": [{
                "key": "payment.notification.route",
                "name": "选择支付通知方式",
                "config_keys": ["payment.channel.mode"],
                "branches": [
                    {"name": "同步通知", "expected_value": "DIRECT"},
                    {"name": "异步通知", "expected_value": "ASYNC"},
                ],
            }],
        })
        resolved = self.service.resolve_configuration(
            "SCN-DEMO-PREPAID", "payment.channel.mode", "DIRECT"
        )
        self.assertEqual(2, len(resolved["selected_branch_ids"]))
        for key in ("payment.channel.route", "payment.notification.route"):
            decision = self.service.find_entity(f"DECISION:{key}", "SCN-DEMO-PREPAID")
            self.assertEqual(1, len(decision["attributes"]["selected_branch_ids"]))

    def test_verified_branch_remains_selected_when_the_decision_is_observed_again(self):
        self.record_example()
        self.service.resolve_configuration("SCN-DEMO-PREPAID", "payment.channel.mode", "DIRECT")
        self.service.record_delta(self.session["session_id"], {
            "summary": "重新确认既有支付渠道判断",
            "decisions": [self.delta["decisions"][0]],
        })
        branches = self.service.list_entities(entity_type="BRANCH", scenario_id="SCN-DEMO-PREPAID")
        self.assertEqual(
            {"直连支付": "ACTIVE", "异步支付": "INACTIVE"},
            {item["display_name"]: item["status"] for item in branches},
        )

    def test_field_events_from_multiple_milestones_are_appended_without_overwriting(self):
        self.service.record_delta(self.session["session_id"], {
            "summary": "先确认金额来自请求",
            "field_journeys": [{
                "key": "amount", "name": "支付金额", "priority": "P0",
                "events": [{"kind": "COPY", "from": "Request.amount", "to": "Command.amount"}],
            }],
        })
        self.service.record_delta(self.session["session_id"], {
            "summary": "随后确认金额单位转换和外发",
            "field_journeys": [{
                "key": "amount", "name": "支付金额", "priority": "P0",
                "events": [
                    {"kind": "UNIT_CONVERSION", "from": "Command.amount", "to": "Payment.amountFen"},
                    {"kind": "OUTBOUND", "from": "Payment.amountFen", "to": "PaymentApi.amount"},
                ],
            }],
        })
        projection = self.service.field_projection("SCN-DEMO-PREPAID", "amount")
        self.assertEqual(3, projection["raw_event_count"])
        self.assertEqual(
            ["COLLAPSED_COPY", "SEMANTIC_CHANGE", "SEMANTIC_CHANGE"],
            [item["kind"] for item in projection["events"]],
        )
        self.assertEqual("UNIT_CONVERSION", projection["events"][1]["operation"])

    def test_repeated_identical_milestone_does_not_duplicate_semantic_history(self):
        self.record_example()
        first = self.service.summary(self.session["session_id"])["session"]["milestone_count"]
        replay = self.service.record_delta(self.session["session_id"], self.delta)
        self.assertEqual("NO_CHANGE", replay["status"])
        self.assertIsNone(replay["milestone_id"])
        self.assertEqual(first, self.service.summary(self.session["session_id"])["session"]["milestone_count"])

    def test_open_business_gap_marks_finished_analysis_partial(self):
        self.service.record_delta(self.session["session_id"], {
            "summary": "第三方失败补偿未能从现有代码确认",
            "gaps": [{
                "key": "payment.compensation.unknown",
                "name": "支付失败补偿路径",
                "summary": "缺少第三方回调服务源码，无法确认退款补偿。",
                "status": "OPEN",
            }],
        })
        result = self.service.finish_session(self.session["session_id"], summary="支付主链已确认，补偿路径待补齐")
        self.assertEqual("PARTIAL", result["status"])
        self.assertEqual(1, result["coverage"]["open_gaps"])

    def test_cross_scenario_entities_share_identity_and_rename_updates_every_projection(self):
        self.record_example()
        another = json.loads(json.dumps(self.sample["scenario"], ensure_ascii=False))
        another["scenario_id"] = "SCN-DEMO-REFUND"
        another["name"] = "订单退款"
        report = IngestionValidator(self.store).ingest({"scenario": another}, work_unit_id="SECOND-SCENARIO")
        self.assertFalse(report["errors"])
        session = self.service.start_session("SCN-DEMO-REFUND")["session"]
        self.service.record_delta(session["session_id"], {
            "summary": "退款场景复用订单系统和支付金额字段",
            "systems": [{"key": "order-service", "name": "订单系统"}],
            "fields": [{"key": "amount", "name": "支付金额", "priority": "P0"}],
        })
        system = self.service.find_entity("SYSTEM:order-service")
        self.assertEqual(2, len(self.service.entity_scenarios(system["entity_id"])))
        renamed = self.service.rename_entity(system["entity_id"], "订单核心系统")
        self.assertEqual({"SCN-DEMO-PREPAID", "SCN-DEMO-REFUND"}, set(renamed["affected_scenario_ids"]))
        site = DossierSiteBuilder(self.store, {"site": {"output": "site"}}, self.root).build()
        self.assertEqual(2, site["adaptive_scenarios"])
        for scenario_id in ("SCN-DEMO-PREPAID", "SCN-DEMO-REFUND"):
            page = (self.root / "site" / "scenarios" / f"{scenario_id}.html").read_text(encoding="utf-8")
            self.assertIn("订单核心系统", page)

    def test_confirmed_configuration_does_not_leak_branch_outcome_into_another_scenario(self):
        self.record_example()
        another = json.loads(json.dumps(self.sample["scenario"], ensure_ascii=False))
        another["scenario_id"] = "SCN-DEMO-TENANT-B"
        another["name"] = "另一租户支付"
        another["scope"]["environment"] = "tenant-b"
        report = IngestionValidator(self.store).ingest({"scenario": another}, work_unit_id="TENANT-B")
        self.assertFalse(report["errors"])
        session = self.service.start_session("SCN-DEMO-TENANT-B")["session"]
        self.service.record_delta(session["session_id"], {
            "summary": "另一租户复用渠道判断，但生产取值尚未查询",
            "decisions": [self.delta["decisions"][0]],
        })
        self.service.resolve_configuration("SCN-DEMO-PREPAID", "payment.channel.mode", "DIRECT")
        confirmed = self.service.scenario_graph("SCN-DEMO-PREPAID")
        unresolved = self.service.scenario_graph("SCN-DEMO-TENANT-B")
        self.assertEqual(0, confirmed["coverage"]["unresolved_configurations"])
        self.assertEqual(1, unresolved["coverage"]["unresolved_configurations"])
        branches = {
            item["display_name"]: item["status"]
            for item in unresolved["entities"] if item["entity_type"] == "BRANCH"
        }
        self.assertEqual({"直连支付": "CONFIG_UNRESOLVED", "异步支付": "CONFIG_UNRESOLVED"}, branches)
        self.service.resolve_configuration(
            "SCN-DEMO-TENANT-B", "payment.channel.mode", "ASYNC", environment="tenant-b"
        )
        first = self.service.scenario_graph("SCN-DEMO-PREPAID")
        second = self.service.scenario_graph("SCN-DEMO-TENANT-B")
        first_paths = {item["display_name"]: item["status"] for item in first["entities"] if item["entity_type"] == "BRANCH"}
        second_paths = {item["display_name"]: item["status"] for item in second["entities"] if item["entity_type"] == "BRANCH"}
        self.assertEqual({"直连支付": "ACTIVE", "异步支付": "INACTIVE"}, first_paths)
        self.assertEqual({"直连支付": "INACTIVE", "异步支付": "ACTIVE"}, second_paths)
        first_config = self.service.find_entity("CONFIG:payment.channel.mode", "SCN-DEMO-PREPAID")
        second_config = self.service.find_entity("CONFIG:payment.channel.mode", "SCN-DEMO-TENANT-B")
        self.assertEqual("DIRECT", first_config["attributes"]["value"])
        self.assertEqual("ASYNC", second_config["attributes"]["value"])

    def test_reusing_shared_entity_in_new_scenario_counts_as_a_real_state_change(self):
        self.record_example()
        another = json.loads(json.dumps(self.sample["scenario"], ensure_ascii=False))
        another["scenario_id"] = "SCN-REUSE-ONLY"
        another["name"] = "仅复用共享系统"
        self.assertFalse(IngestionValidator(self.store).ingest({"scenario": another}, work_unit_id="REUSE-ONLY")["errors"])
        session = self.service.start_session("SCN-REUSE-ONLY")["session"]
        existing = self.service.find_entity("SYSTEM:order-service", "SCN-DEMO-PREPAID")
        receipt = self.service.record_delta(session["session_id"], {
            "systems": [{
                "key": existing["logical_key"], "name": existing["display_name"],
                "summary": existing.get("summary"),
            }],
        })
        self.assertEqual("RECORDED", receipt["status"])
        self.assertEqual(1, receipt["changed_entities"])
        self.assertEqual(1, self.service.summary(session["session_id"])["session"]["milestone_count"])

    def test_adaptive_site_is_cross_linked_offline_and_fact_driven(self):
        self.record_example()
        result = DossierSiteBuilder(self.store, {"site": {"output": "site", "title": "Demo Atlas"}}, self.root).build()
        self.assertEqual(1, result["adaptive_scenarios"])
        page = (self.root / "site" / "scenarios" / "SCN-DEMO-PREPAID.html").read_text(encoding="utf-8")
        for phrase in (
            "系统时序", "业务流程", "选择支付渠道", "直连支付", "异步支付",
            "生产配置尚未确认", "提交支付扣款", "返回值如何被使用", "保存订单支付信息",
            "请求对象透传", "普通复制", "分支后续尚未确认汇合", "<svg",
            "../systems/", "../fields/", "../tables/",
        ):
            self.assertIn(phrase, page)
        self.assertNotIn("cdn.jsdelivr", page)
        self.assertNotIn("https://", page)
        field = self.service.find_entity("FIELD:amount")
        field_page = (self.root / "site" / "fields" / f'{field["entity_id"]}.html').read_text(encoding="utf-8")
        self.assertIn("UNIT_CONVERSION", field_page)
        self.assertIn("2 次普通复制已折叠", field_page)
        self.assertIn("PaymentRequest.amountFen", field_page)
        self.assertTrue((self.root / "site" / "systems.html").exists())
        self.assertTrue((self.root / "site" / "decisions.html").exists())

    def test_flow_only_rejoins_branches_after_the_shared_destination_is_evidenced(self):
        self.record_example()
        DossierSiteBuilder(self.store, {"site": {"output": "site"}}, self.root).build()
        target = self.root / "site" / "scenarios" / "SCN-DEMO-PREPAID.html"
        self.assertIn("分支后续尚未确认汇合", target.read_text(encoding="utf-8"))

        branches = self.service.list_entities(entity_type="BRANCH", scenario_id="SCN-DEMO-PREPAID")
        persistence = self.service.find_entity("PERSISTENCE:order.persist", "SCN-DEMO-PREPAID")
        self.service.record_delta(self.session["session_id"], {
            "summary": "确认两个支付渠道最终都汇入同一订单支付信息落库节点",
            "relations": [{
                "from": branch["entity_id"],
                "to": persistence["entity_id"],
                "type": "LEADS_TO",
            } for branch in branches],
        })
        DossierSiteBuilder(self.store, {"site": {"output": "site"}}, self.root).build()
        self.assertNotIn("分支后续尚未确认汇合", target.read_text(encoding="utf-8"))

    def test_html_perspectives_do_not_depend_on_bounded_model_context_queries(self):
        self.record_example()
        with patch.object(
            KnowledgeGraphService,
            "list_entities",
            side_effect=AssertionError("Model-context query limits must not truncate reader pages"),
        ):
            result = DossierSiteBuilder(
                self.store, {"site": {"output": "site"}}, self.root
            ).build()
        self.assertEqual(1, result["adaptive_scenarios"])
        self.assertGreater(result["perspectives"], 4)
        self.assertTrue((self.root / "site" / "systems.html").exists())

    def test_state_transitions_and_multisystem_relations_generate_contextual_diagrams(self):
        self.record_example()
        self.service.record_delta(self.session["session_id"], {
            "summary": "支付结果推动订单状态变更并异步通知履约系统",
            "systems": [{"key": "fulfillment-service", "name": "履约系统"}],
            "states": [
                {"key": "order.CREATED", "name": "订单已创建", "sequence_no": 1},
                {"key": "order.PAYING", "name": "支付处理中", "sequence_no": 2},
                {"key": "order.PAID", "name": "订单已支付", "sequence_no": 3},
            ],
            "interactions": [{
                "key": "order.fulfillment.notice",
                "name": "发送订单履约通知",
                "source_system": "order-service",
                "target_system": "fulfillment-service",
                "protocol": "MQ",
                "sequence_no": 50,
            }],
            "relations": [
                {"from": "STATE:order.CREATED", "to": "STATE:order.PAYING", "type": "TRANSITIONS_TO", "label": "提交支付"},
                {"from": "STATE:order.PAYING", "to": "STATE:order.PAID", "type": "TRANSITIONS_TO", "label": "支付成功"},
            ],
        })
        DossierSiteBuilder(self.store, {"site": {"output": "site"}}, self.root).build()
        page = (self.root / "site" / "scenarios" / "SCN-DEMO-PREPAID.html").read_text(encoding="utf-8")
        for expected in ("系统关系", "状态流转", "业务状态", "订单已创建", "订单已支付", "履约系统", "stroke-dasharray"):
            self.assertIn(expected, page)
        self.assertIn('aria-label="states"', page)

    def test_source_evidence_references_are_resolved_and_reader_html_escapes_untrusted_text(self):
        self.service.record_delta(self.session["session_id"], {
            "summary": "为渠道判断登记可追溯源码证据",
            "evidences": [{
                "key": "router-evidence",
                "name": "支付路由代码",
                "source_id": "order-service",
                "file": "src/main/java/PaymentRouter.java",
                "symbol": "PaymentRouter#route",
                "line_start": 42,
                "line_end": 58,
            }],
            "decisions": [{
                "key": "safe.route",
                "name": "<script>alert(1)</script>",
                "summary": "按代码证据选择安全路径",
                "evidence_refs": ["EVIDENCE:router-evidence"],
                "branches": [{"name": "可信路径"}],
            }],
        })
        evidence = self.service.find_entity("EVIDENCE:router-evidence", "SCN-DEMO-PREPAID")
        decision = self.service.find_entity("DECISION:safe.route", "SCN-DEMO-PREPAID")
        self.assertEqual([evidence["entity_id"]], decision["evidence_refs"])
        DossierSiteBuilder(self.store, {"site": {"output": "site"}}, self.root).build()
        page = (self.root / "site" / "scenarios" / "SCN-DEMO-PREPAID.html").read_text(encoding="utf-8")
        self.assertIn(f'data-evidence="{evidence["entity_id"]}"', page)
        self.assertIn("src/main/java/PaymentRouter.java", page)
        self.assertIn("42–58", page)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)

    def test_context_is_bounded_focus_aware_and_tracks_configuration_gaps(self):
        self.record_example()
        context = self.service.build_context(
            self.session["session_id"], focus="amount", fields=["amount"], max_tokens=650
        )
        encoded = json.dumps(context, ensure_ascii=False)
        self.assertIn("amount", encoded)
        self.assertIn("CONFIG_UNRESOLVED", encoded)
        self.assertLess(len(encoded), 9000)
        self.assertIn("omitted_fact_count", context)
        self.assertLessEqual(context["approx_context_tokens"], context["context_budget_tokens"])
        self.assertEqual("SCN-DEMO-PREPAID", context["scenario"]["scenario_id"])

    def test_many_configuration_questions_cannot_bypass_the_complete_context_budget(self):
        self.service.record_delta(self.session["session_id"], {
            "summary": "记录大量租户相关配置与待核实问题",
            "configurations": [
                {"key": f"tenant.payment.channel.setting.{index}", "summary": "需检查生产租户渠道配置" * 5}
                for index in range(28)
            ],
            "gaps": [
                {"key": f"tenant-gap-{index}", "name": f"租户分支缺口 {index}", "summary": "仍需检查第三方配置来源" * 6}
                for index in range(28)
            ],
        })
        context = self.service.build_context(self.session["session_id"], focus="amount", max_tokens=600)
        self.assertLessEqual(context["approx_context_tokens"], 600)
        self.assertGreater(context["coverage"]["omitted_configuration_keys"], 0)
        self.assertGreater(context["coverage"]["omitted_gap_questions"], 0)
        self.assertEqual(28, context["coverage"]["unresolved_configurations"])

    def test_user_selected_priority_field_is_promoted_even_when_delta_omits_priority(self):
        self.service.record_delta(self.session["session_id"], {
            "summary": "用户指定的金额字段必须成为重点溯源对象",
            "fields": [{"key": "amount", "name": "支付金额", "priority": "P2"}],
        })
        field = self.service.find_entity("FIELD:amount", "SCN-DEMO-PREPAID")
        self.assertEqual("P0", field["priority"])

    def test_source_relative_evidence_is_validated_and_invalid_delta_rolls_back(self):
        before = self.service.coverage("SCN-DEMO-PREPAID")
        with self.assertRaises(GraphContractError):
            self.service.record_delta(self.session["session_id"], {
                "evidences": [{"key": "unsafe", "source_id": "order-service", "path": "../secrets.java"}],
                "systems": [{"key": "should-not-persist", "name": "禁止落库"}],
            })
        after = self.service.coverage("SCN-DEMO-PREPAID")
        self.assertEqual(before, after)
        with self.assertRaises(GraphContractError):
            self.service.record_delta(self.session["session_id"], {
                "evidences": [{"key": "unregistered", "source_id": "unknown-service", "path": "Demo.java"}]
            })

    def test_sensitive_configuration_values_are_redacted(self):
        self.service.record_delta(self.session["session_id"], {
            "summary": "识别鉴权配置但不记录明文",
            "configurations": [{"key": "payment.api.secret", "value": "super-secret-value"}],
        })
        config = self.service.find_entity("CONFIG:payment.api.secret", "SCN-DEMO-PREPAID")
        self.assertEqual("***REDACTED***", config["attributes"]["value"])
        self.assertNotIn("super-secret-value", json.dumps(self.service.scenario_graph("SCN-DEMO-PREPAID")))

    def test_replaying_session_resumes_and_soft_budget_does_not_invent_task_limits(self):
        resumed = self.service.start_session("SCN-DEMO-PREPAID")
        self.assertEqual("RESUMED", resumed["status"])
        payload = {"summary": "达到预算后仍保留已有业务结论", "observed_tokens": 5100}
        receipt = self.service.record_delta(self.session["session_id"], payload)
        self.assertEqual("SOFT_TOKEN_BUDGET_REACHED", receipt["budget_notice"])
        finished = self.service.finish_session(self.session["session_id"], summary="保留可确认业务链路")
        self.assertEqual("COMPLETE", finished["status"])


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
        planner_context = self.service.next_task(run_id)["context"]
        planner = planner_context["task"]
        planner_contract = planner_context["output_contract"]
        self.assertEqual("ucef_submit_plan", planner_contract["submit_tool"])
        self.assertEqual("zh-CN", planner_contract["presentation"]["language"])
        self.assertIn("business_blocks", planner_contract["payload_template"])
        self.assertLess(len(json.dumps(planner_contract, ensure_ascii=False)), 5000)
        plan = self.plan_payload(run_id)
        accepted = self.service.submit("plan", run_id, planner["task_id"], plan)
        self.assertEqual("ACCEPTED", accepted["status"])
        self.assertEqual("ALREADY_ACCEPTED", self.service.submit("plan", run_id, planner["task_id"], plan)["status"])

        status = self.service.status(run_id)
        self.assertLessEqual(len(status["tasks"]), MODE_BUDGETS["STANDARD"]["max_model_tasks"])
        self.assertEqual(2, len([task for task in status["tasks"] if task["role"] == "BLOCK"]))

        while True:
            claimed = self.service.next_task(run_id)
            if claimed["status"] != "TASK" or claimed["context"]["task"]["role"] != "BLOCK":
                break
            block_context = claimed["context"]
            task = block_context["task"]
            self.assertNotIn("business_blocks", claimed["context"])
            self.assertEqual("ucef_submit_block", block_context["output_contract"]["submit_tool"])
            self.assertEqual(task["block_id"], block_context["output_contract"]["payload_template"]["block_id"])
            self.service.submit("block", run_id, task["task_id"], self.block_payload(task, run_id))

        finalizer = claimed["context"]
        self.assertEqual("FINALIZER", finalizer["task"]["role"])
        self.assertNotIn("scenario_plans", finalizer)
        self.assertEqual(5, len(finalizer["business_blocks"]))
        self.assertEqual("ucef_submit_overview", finalizer["output_contract"]["submit_tool"])
        self.assertEqual(
            [f"BLOCK-DIRECT-{index}" for index in range(1, 6)],
            finalizer["output_contract"]["payload_template"]["ordered_block_ids"],
        )
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
        for expected in ("请求按生产配置选择预付通道", "业务执行过程", "业务时序图", "业务主线", "查看技术依据", "字段如何走完整条链", "外部系统与业务副作用", "技术证据附录", "读取并转换金额", artifact["artifact_id"]):
            self.assertIn(expected, page)
        self.assertNotIn("Evidence drawer", page)
        self.assertIn('class="sequence-step"', page)
        artifact_page = (self.root / "site" / "artifacts" / f"{artifact['artifact_id']}.html").read_text(encoding="utf-8")
        self.assertIn("原始制品", artifact_page)
        self.assertIn("***REDACTED***", artifact_page)
        self.assertNotIn("do-not-render", artifact_page)
        self.assertNotIn("</SCRIPT><script>", artifact_page)
        self.assertIn("\\u003c/SCRIPT>", artifact_page)
        index = (self.root / "site" / "index.html").read_text(encoding="utf-8")
        self.assertIn("可完整阅读", index)
        self.assertIn("UCEF 业务执行档案", index)

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

    def test_claimed_task_is_replayed_and_structured_error_stops_retry_loop(self):
        started = self.service.start("SCN-DEMO-PREPAID", "QUICK")
        run_id = started["run"]["run_id"]
        first = self.service.next_task(run_id)["context"]
        invalid = {"critical_fields": [], "terminal_outcome": "结果", "business_blocks": []}
        with self.assertRaises(SubmissionContractError) as first_error:
            self.service.submit("plan", run_id, first["task"]["task_id"], invalid)
        self.assertEqual("$.business_blocks", first_error.exception.issue["path"])
        self.assertEqual(1, first_error.exception.corrections_remaining)
        replay = self.service.next_task(run_id)["context"]
        self.assertEqual(first["task"]["task_id"], replay["task"]["task_id"])
        self.assertEqual(1, replay["output_contract"]["correction_policy"]["corrections_remaining"])
        with self.assertRaises(SubmissionContractError) as second_error:
            self.service.submit("plan", run_id, first["task"]["task_id"], invalid)
        self.assertEqual(0, second_error.exception.corrections_remaining)
        self.assertEqual("FAILED", second_error.exception.task_status)
        stopped = self.service.status(run_id)
        self.assertEqual("STOPPED", stopped["run"]["status"])
        self.assertEqual("SUBMISSION_CORRECTION_BUDGET_EXHAUSTED", stopped["run"]["stop_reason"])

    def test_block_validation_exhaustion_becomes_visible_gap_and_continues(self):
        started = self.service.start("SCN-DEMO-PREPAID", "STANDARD")
        run_id = started["run"]["run_id"]
        planner = self.service.next_task(run_id)["context"]["task"]
        self.service.submit("plan", run_id, planner["task_id"], self.plan_payload(run_id))
        block = self.service.next_task(run_id)["context"]["task"]
        for expected_remaining in (1, 0):
            with self.assertRaises(SubmissionContractError) as error:
                self.service.submit("block", run_id, block["task_id"], {})
            self.assertEqual(expected_remaining, error.exception.corrections_remaining)
        status = self.service.status(run_id)
        failed = next(task for task in status["tasks"] if task["task_id"] == block["task_id"])
        self.assertEqual("FAILED", failed["status"])
        gaps = self.store.list_collection("gaps", "SCN-DEMO-PREPAID")
        self.assertEqual("SUBMISSION_VALIDATION", gaps[0]["category"])
        next_block = self.service.next_task(run_id)["context"]["task"]
        self.assertEqual("BLOCK", next_block["role"])
        self.assertNotEqual(block["task_id"], next_block["task_id"])

    def test_stopped_run_continues_persisted_plan_without_another_planner(self):
        started = self.service.start("SCN-DEMO-PREPAID", "STANDARD")
        run_id = started["run"]["run_id"]
        planner = self.service.next_task(run_id)["context"]["task"]
        self.service.submit("plan", run_id, planner["task_id"], self.plan_payload(run_id))
        first_block = self.service.next_task(run_id)["context"]["task"]
        self.service.submit("block", run_id, first_block["task_id"], self.block_payload(first_block, run_id))
        stale = self.store.get("business_blocks", first_block["block_id"])
        stale.update({"block_id": "BLOCK-STALE-HISTORY", "logical_key": "demo.stale", "sequence_no": 99})
        self.store.upsert("business_blocks", stale, "TEST-STALE-HISTORY")
        self.store.commit()

        run = self.service.status(run_id)["run"]
        run["deadline_at"] = "2000-01-01T00:00:00+00:00"
        self.store.conn.execute(
            "UPDATE analysis_runs SET deadline_at=?,payload_json=? WHERE run_id=?",
            (run["deadline_at"], json.dumps(run, ensure_ascii=False), run_id),
        )
        self.store.commit()
        self.assertEqual("STOPPED", self.service.status(run_id)["run"]["status"])

        continued = self.service.start("SCN-DEMO-PREPAID", "STANDARD")
        self.assertEqual("CONTINUED", continued["status"])
        self.assertEqual(run_id, continued["continued_from_run_id"])
        self.assertEqual([first_block["block_id"]], continued["reused_completed_block_ids"])
        continued_status = self.service.status(continued["run"]["run_id"])
        self.assertNotIn("PLANNER", {task["role"] for task in continued_status["tasks"]})
        self.assertEqual({"BLOCK", "FINALIZER"}, {task["role"] for task in continued_status["tasks"]})
        self.assertEqual(1, len(self.store.list_collection("scenario_plans", "SCN-DEMO-PREPAID")))

        continued_run_id = continued["run"]["run_id"]
        remaining = self.service.next_task(continued_run_id)["context"]["task"]
        self.service.submit("block", continued_run_id, remaining["task_id"], self.block_payload(remaining, continued_run_id))
        finalizer = self.service.next_task(continued_run_id)["context"]
        self.assertEqual("FINALIZER", finalizer["task"]["role"])
        ordered_ids = finalizer["output_contract"]["payload_template"]["ordered_block_ids"]
        self.assertEqual([f"BLOCK-DIRECT-{index}" for index in range(1, 6)], ordered_ids)
        self.assertNotIn("BLOCK-STALE-HISTORY", ordered_ids)
        self.service.submit("overview", continued_run_id, finalizer["task"]["task_id"], {
            "overview_id": "OVERVIEW-CONTINUED",
            "one_sentence": "恢复未完成业务块后形成完整链路。",
            "business_context": "验证超时恢复不会重新规划。",
            "selected_route": {},
            "ordered_block_ids": ordered_ids,
            "key_field_journeys": [],
            "external_effects": [],
            "persistence_effects": [],
            "failure_outcomes": [],
            "open_gaps": [],
        })
        self.assertEqual("COMPLETE", self.service.status(continued_run_id)["run"]["status"])
        DossierSiteBuilder(self.store, {"site": {"output": "site"}}, self.root).build()
        page = (self.root / "site" / "scenarios" / "SCN-DEMO-PREPAID.html").read_text(encoding="utf-8")
        self.assertNotIn("BLOCK-STALE-HISTORY", page)
        fresh = self.service.start("SCN-DEMO-PREPAID", "STANDARD")
        self.assertEqual("STARTED", fresh["status"])
        self.assertEqual("PLANNER", self.service.next_task(fresh["run"]["run_id"])["context"]["task"]["role"])

    def test_direct_site_tolerates_string_steps_and_hides_technical_panel_by_default(self):
        started = self.service.start("SCN-DEMO-PREPAID", "STANDARD")
        run_id = started["run"]["run_id"]
        planner = self.service.next_task(run_id)["context"]["task"]
        self.service.submit("plan", run_id, planner["task_id"], self.plan_payload(run_id))
        block = self.store.get("business_blocks", "BLOCK-DIRECT-2")
        block.update({
            "implementation_steps": ["读取扩展配置", {"action": "选择清算规则", "fields": ["cstcType"]}],
            "inputs": [{"name": "stepModel.ext", "business_use": "选择清算规则"}],
            "decision": {"condition": "ext != null", "selected": "清算扩展点"},
            "external_calls": ["调用清算扩展点"],
            "persistence": ["记录清算状态"],
            "method_evidence": ["ClearingNoticeTask.java:42 execTask"],
            "status": "COMPLETE",
        })
        self.store.upsert("business_blocks", block, "TEST-LEGACY-STRING")
        self.store.commit()
        DossierSiteBuilder(self.store, {"site": {"output": "site"}}, self.root).build()
        page = (self.root / "site" / "scenarios" / "SCN-DEMO-PREPAID.html").read_text(encoding="utf-8")
        self.assertIn("读取扩展配置", page)
        self.assertIn("<dt>名称</dt>", page)
        self.assertIn("查看技术依据", page)
        self.assertIn('class="evidence-dialog"', page)
        self.assertNotIn('class="evidence-drawer"', page)
        self.assertNotIn("Evidence drawer", page)
        self.assertNotIn("Scenario control room", page)
        self.assertNotIn("{&quot;name&quot;", page)

    def test_submit_block_process_boundary_forces_utf8_under_legacy_windows_codepage(self):
        (self.root / "workspace.json").write_text(
            json.dumps({"database": {"path": "ucef.db"}, "site": {"output": "site"}}),
            encoding="utf-8",
        )
        started = self.service.start("SCN-DEMO-PREPAID", "STANDARD")
        run_id = started["run"]["run_id"]
        planner = self.service.next_task(run_id)["context"]["task"]
        self.service.submit("plan", run_id, planner["task_id"], self.plan_payload(run_id))
        task = self.service.next_task(run_id)["context"]["task"]
        payload = self.block_payload(task, run_id)
        payload["title"] = "金额💰进入支付链路✅"
        payload["business_goal"] = "保留中文、箭头→、引号“测试”和 emoji"
        self.store.commit()

        environment = os.environ.copy()
        environment.update({"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp936"})
        result = subprocess.run(
            [
                sys.executable,
                str(SKILL_ROOT / "scripts" / "ucef.py"),
                "--workspace", str(self.root),
                "submit-direct", "--kind", "block",
                "--run-id", run_id,
                "--task-id", task["task_id"],
            ],
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr.decode("utf-8", errors="replace"))
        receipt = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual("ACCEPTED", receipt["status"])
        persisted = self.store.get("business_blocks", task["block_id"])
        self.assertEqual("金额💰进入支付链路✅", persisted["title"])
        self.assertIn("箭头→", persisted["business_goal"])

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

    def test_cli_bootstrap_and_stdin_scenario_registration_need_no_agent_files(self):
        workspace_root = self.root / "agent-prepared-workspace"
        output = io.StringIO()
        with redirect_stdout(output):
            result = cli_main(["--workspace", str(workspace_root), "bootstrap"])
        self.assertEqual(0, result)
        receipt = json.loads(output.getvalue())
        self.assertEqual("bootstrapped", receipt["status"])
        self.assertTrue((workspace_root / "workspace.json").exists())
        self.assertTrue((workspace_root / "artifacts" / "index.json").exists())

        with redirect_stdout(io.StringIO()):
            self.assertEqual(0, cli_main([
                "--workspace", str(workspace_root), "source-add",
                "--source-id", "gateway", "--path", str(self.source_a),
            ]))
        scenario = {
            "scenario_id": "SCN-TOOL-PREPARED",
            "name": "工具准备场景",
            "business_operation": "CREATE",
            "business_goal": "验证 Agent 无需创建场景文件",
            "trigger": {"kind": "METHOD", "symbol": "Gateway#create", "input_type": "Request"},
            "scope": {"source_ids": ["gateway"], "environment": "prod"},
            "expected_outcome": "场景已登记",
        }
        prior_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(json.dumps(scenario, ensure_ascii=False))
            with redirect_stdout(io.StringIO()):
                result = cli_main(["--workspace", str(workspace_root), "scenario-put"])
        finally:
            sys.stdin = prior_stdin
        self.assertEqual(0, result)
        store = FactStore(workspace_root / "ucef.db")
        try:
            self.assertTrue(store.has("scenarios", "SCN-TOOL-PREPARED"))
        finally:
            store.close()

    def test_cli_adaptive_session_runs_end_to_end_and_refreshes_cross_linked_pages(self):
        self.workspace.add_source("order-service", self.source_a)
        sample = json.loads((SKILL_ROOT / "templates" / "result.example.json").read_text(encoding="utf-8"))
        delta = json.loads((SKILL_ROOT / "templates" / "adaptive_delta.example.json").read_text(encoding="utf-8"))
        prefix = ["--workspace", str(self.workspace_root)]

        def invoke(arguments, stdin=None):
            output = io.StringIO()
            previous = sys.stdin
            try:
                if stdin is not None:
                    sys.stdin = io.StringIO(json.dumps(stdin, ensure_ascii=False))
                with redirect_stdout(output):
                    exit_code = cli_main(prefix + arguments)
            finally:
                sys.stdin = previous
            self.assertEqual(0, exit_code, output.getvalue())
            return json.loads(output.getvalue())

        invoke(["scenario-put"], sample["scenario"])
        doctor = invoke(["doctor"])
        self.assertEqual("OK", doctor["status"])
        started = invoke([
            "session-start", "--scenario", "SCN-DEMO-PREPAID",
            "--priority-fields", "amount,paymentChannel", "--context-target", "1500",
        ])
        session_id = started["session"]["session_id"]
        receipt = invoke(["session-delta", "--session-id", session_id], delta)
        self.assertEqual("RECORDED", receipt["status"])
        self.assertNotIn("site", receipt)

        context = invoke(["session-context", "--session-id", session_id, "--focus", "amount"])
        self.assertEqual("amount", context["focus"])
        decisions = invoke([
            "graph-query", "--scenario", "SCN-DEMO-PREPAID", "--type", "DECISION",
        ])
        self.assertEqual(1, decisions["count"])
        lineage = invoke([
            "field-lineage", "--scenario", "SCN-DEMO-PREPAID", "--field", "amount",
        ])
        self.assertEqual(2, lineage["collapsed_copy_count"])
        configuration = invoke([
            "config-resolve", "--scenario", "SCN-DEMO-PREPAID",
            "--key", "payment.channel.mode", "--value", "DIRECT",
            "--evidence", "padb://payment.channel.mode",
        ])
        self.assertEqual("CONFIG_CONFIRMED", configuration["status"])

        systems = invoke(["graph-query", "--type", "SYSTEM", "--search", "order-service"])
        renamed = invoke([
            "entity-rename", "--entity-id", systems["entities"][0]["entity_id"],
            "--name", "订单统一核心",
        ])
        self.assertEqual("RENAMED", renamed["status"])
        finished = invoke([
            "session-finish", "--session-id", session_id,
            "--summary", "确认直连支付路径、金额转换与订单落库",
        ])
        self.assertEqual("COMPLETE", finished["status"])
        page = (self.workspace_root / "site" / "scenarios" / "SCN-DEMO-PREPAID.html").read_text(encoding="utf-8")
        self.assertIn("订单统一核心", page)
        self.assertIn("配置已确认", page)
        self.assertIn("已命中", page)
        self.assertNotIn("生产配置尚未确认", page)

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

    def test_workspace_and_artifact_json_accept_utf8_bom(self):
        bom_root = self.root / "bom-workspace"
        bom_root.mkdir()
        (bom_root / "workspace.json").write_text(
            json.dumps({"database": {"path": "ucef.db"}, "site": {"output": "site"}}),
            encoding="utf-8-sig",
        )
        workspace = AnalysisWorkspace.open(bom_root)
        workspace.initialize_directories()
        artifact_source = bom_root / "配置快照.json"
        artifact_source.write_text(
            json.dumps({"模式": "预付💰", "token": "secret"}, ensure_ascii=False),
            encoding="utf-8-sig",
        )
        artifact_store = ArtifactStore(bom_root)
        artifact = artifact_store.add_json(artifact_source)
        stored = artifact_store.read_display_json(artifact)
        self.assertEqual("预付💰", stored["模式"])
        self.assertEqual("***REDACTED***", stored["token"])

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
