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
from ucef.cli import main as cli_main
from ucef.compare import compare_scenarios
from ucef.context import ContextBuilder
from ucef.ledger import CheckpointLedger
from ucef.site import DossierSiteBuilder
from ucef.store import FactStore
from ucef.validator import IngestionValidator
from ucef.workspace import AnalysisWorkspace


class OpenCodeAgentPackagingTests(unittest.TestCase):
    def test_primary_agent_loads_required_skills_and_enables_index_mcp(self):
        text = AGENT_PATH.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---", 2)[1]
        self.assertIn("mode: primary", frontmatter)
        self.assertIn("permission: allow", frontmatter)
        self.assertIn('"index-mcp_*": true', frontmatter)
        self.assertIn("加载 `ucef`", text)
        self.assertIn("加载 `padb`", text)
        self.assertIn("单探针事务", text)
        self.assertIn("Java 项目始终是 UCEF 的只读数据源", text)


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
        work_unit["reuse"] = {
            "logical_keys": ["payment.prepaid.submit"],
            "repository": "demo/order-service",
            "code_hash": "hash-payment-v1",
            "binding_hash": "profile-prod-payment-client-v1",
        }
        context = ContextBuilder(SKILL_ROOT / "runtime", self.store, {"context": {}}).build(self.sample["scenario"], work_unit)
        self.assertIn("COMPACT SCENARIO ASSEMBLY", context)
        self.assertIn("DURABLE RESUME STATE", context)
        self.assertIn("EXACT_REUSE", context)
        self.assertIn("Work Unit Output Contract", context)


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
        memory = self.store.work_unit_memory("WU-LONG-CHAIN")
        self.assertEqual(2, memory["checkpoint_count"])
        self.assertEqual(1, memory["observation_counts"]["total"])
        self.assertEqual(2, memory["latest_checkpoint"]["sequence_no"])
        audit = audit_scenario(self.store, "SCN-DEMO-PREPAID")
        self.assertEqual("INCOMPLETE", audit["dimensions"]["MEMORY_ASSEMBLY"])

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
        context = ContextBuilder(
            SKILL_ROOT / "runtime",
            self.store,
            {"context": {"max_pending_observations": 40, "max_chars_per_observation_preview": 800}},
        ).build(self.sample["scenario"], self.work_unit)
        self.assertIn('"omitted_pending_observations": 35', context)
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
