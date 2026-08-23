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
sys.path.insert(0, str(SKILL_ROOT / "runtime"))

from ucef.audit import audit_scenario
from ucef.cli import main as cli_main
from ucef.compare import compare_scenarios
from ucef.context import ContextBuilder
from ucef.site import DossierSiteBuilder
from ucef.store import FactStore
from ucef.validator import IngestionValidator
from ucef.workspace import AnalysisWorkspace


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

        config = {"site": {"output": "site", "title": "Test Dossiers"}}
        result = DossierSiteBuilder(self.store, config, self.root).build()
        self.assertEqual(1, result["scenarios"])
        page = (self.root / "site" / "scenarios" / "SCN-DEMO-PREPAID.html").read_text(encoding="utf-8")
        for expected in ("预付订单创建", "完整业务执行故事", "字段全生命周期", "PaymentSystem", "请求参数来源", "复用行为片段"):
            self.assertIn(expected, page)

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
        for collection in ("evidences", "trace_stages", "route_decisions", "field_lineage_steps", "persistence_effects", "external_interactions"):
            for item in other[collection]:
                item["scenario_id"] = "SCN-DEMO-POSTPAID"
        for item in other["trace_stages"]:
            item["stage_id"] += "-B"
        stage_map = {x["stage_id"].removesuffix("-B"): x["stage_id"] for x in other["trace_stages"]}
        for collection in ("route_decisions", "field_lineage_steps", "persistence_effects", "external_interactions"):
            for item in other[collection]:
                if item.get("stage_id") in stage_map:
                    item["stage_id"] = stage_map[item["stage_id"]]
        other["route_decisions"][0]["current_outcome"] = "CreditPaymentService"
        other["route_decisions"][0]["reason"] = "生产配置 payment.mode=POSTPAID"
        other["trace_stages"][1]["why_current"] = "CFG-PROD-002 中 payment.mode=POSTPAID"
        other["fragments"] = []
        other["trace_stages"][2].pop("fragment_id", None)
        IngestionValidator(self.store).ingest(other, work_unit_id="WU-B")
        comparison = compare_scenarios(self.store, "SCN-DEMO-PREPAID", "SCN-DEMO-POSTPAID")
        self.assertIsNotNone(comparison["first_divergence"])
        self.assertEqual(5, len(comparison["stages"]))

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
        self.assertIn("CURRENT SCENARIO ASSEMBLY", context)
        self.assertIn("EXACT_REUSE", context)
        self.assertIn("Work Unit Output Contract", context)


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


if __name__ == "__main__":
    unittest.main()
