from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .core import canonical_hash, new_id, now_iso
from .store import FactStore


MODE_BUDGETS = {
    "QUICK": {
        "max_business_blocks": 5,
        "max_detail_blocks": 2,
        "max_model_tasks": 4,
        "max_elapsed_minutes": 15,
        "max_context_tokens_per_worker": 10000,
    },
    "STANDARD": {
        "max_business_blocks": 8,
        "max_detail_blocks": 4,
        "max_model_tasks": 6,
        "max_elapsed_minutes": 30,
        "max_context_tokens_per_worker": 12000,
    },
    "DEEP": {
        "max_business_blocks": 12,
        "max_detail_blocks": 6,
        "max_model_tasks": 8,
        "max_elapsed_minutes": 45,
        "max_context_tokens_per_worker": 16000,
    },
}

REQUIRED_BLOCK_ARRAYS = (
    "inputs",
    "implementation_steps",
    "field_changes",
    "external_calls",
    "persistence",
    "error_behavior",
    "method_evidence",
    "evidence_refs",
)


def _required(payload: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [field for field in fields if field not in payload or payload[field] in (None, "")]


class DirectAnalysisService:
    def __init__(self, store: FactStore):
        self.store = store

    def _insert_task(self, task: dict[str, Any]) -> None:
        ts = now_iso()
        data = dict(task)
        content_hash = canonical_hash(data)
        self.store.conn.execute(
            "INSERT INTO analysis_tasks(task_id,run_id,scenario_id,role,block_id,sequence_no,status,payload_json,content_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                data["task_id"], data["run_id"], data["scenario_id"], data["role"],
                data.get("block_id"), float(data.get("sequence_no") or 0), data["status"],
                json.dumps(data, ensure_ascii=False), content_hash, ts, ts,
            ),
        )

    def _update_task(self, task: dict[str, Any]) -> None:
        ts = now_iso()
        content_hash = canonical_hash(task)
        self.store.conn.execute(
            "UPDATE analysis_tasks SET status=?,payload_json=?,content_hash=?,updated_at=? WHERE task_id=?",
            (task["status"], json.dumps(task, ensure_ascii=False), content_hash, ts, task["task_id"]),
        )

    def _update_run(self, run: dict[str, Any]) -> None:
        ts = now_iso()
        self.store.conn.execute(
            "UPDATE analysis_runs SET status=?,payload_json=?,content_hash=?,updated_at=? WHERE run_id=?",
            (run["status"], json.dumps(run, ensure_ascii=False), canonical_hash(run), ts, run["run_id"]),
        )

    def _known_block_index(self) -> list[dict[str, Any]]:
        rows = self.store.conn.execute(
            "SELECT payload_json FROM business_blocks WHERE status IN ('COMPLETE','SUMMARY_COMPLETE') ORDER BY updated_at DESC"
        ).fetchall()
        seen: set[str] = set()
        result = []
        for row in rows:
            block = json.loads(row["payload_json"])
            key = str(block.get("logical_key") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            result.append({
                "logical_key": key,
                "title": block.get("title"),
                "business_goal": block.get("business_goal"),
                "scenario_id": block.get("scenario_id"),
                "applicability": (block.get("reuse") or {}).get("basis"),
            })
            if len(result) >= 30:
                break
        return result

    def _reuse_candidates(self, logical_key: str, run_id: str) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        rows = self.store.conn.execute(
            "SELECT payload_json FROM business_blocks WHERE run_id!=? AND status IN ('COMPLETE','SUMMARY_COMPLETE') ORDER BY updated_at DESC",
            (run_id,),
        ).fetchall()
        payloads.extend(json.loads(row["payload_json"]) for row in rows)
        revision_rows = self.store.conn.execute(
            "SELECT payload_json FROM entity_revisions WHERE entity_type='business_blocks' ORDER BY created_at DESC"
        ).fetchall()
        payloads.extend(json.loads(row["payload_json"]) for row in revision_rows)
        result = []
        seen: set[str] = set()
        for block in payloads:
            if block.get("logical_key") != logical_key or block.get("status") not in {"COMPLETE", "SUMMARY_COMPLETE"}:
                continue
            identity = f"{block.get('scenario_id')}|{block.get('block_id')}|{canonical_hash(block)}"
            if identity in seen:
                continue
            seen.add(identity)
            result.append({
                key: block.get(key)
                for key in (
                    "block_id", "scenario_id", "logical_key", "title", "business_goal",
                    "why_current", "inputs", "decision", "implementation_steps",
                    "field_changes", "external_calls", "persistence", "output",
                    "error_behavior", "method_evidence", "evidence_refs", "reuse", "status",
                )
            })
            if len(result) >= 3:
                break
        return result

    def _run(self, run_id: str) -> dict[str, Any]:
        row = self.store.conn.execute(
            "SELECT payload_json FROM analysis_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Unknown analysis run: {run_id}")
        run = json.loads(row["payload_json"])
        deadline = datetime.fromisoformat(run["deadline_at"])
        if datetime.now(timezone.utc) >= deadline and run["status"] not in {"COMPLETE", "STOPPED"}:
            run["status"] = "STOPPED"
            run["stop_reason"] = "HARD_TIME_BUDGET_REACHED"
            self._update_run(run)
            rows = self.store.conn.execute(
                "SELECT payload_json FROM analysis_tasks WHERE run_id=? AND status IN ('PENDING','WAITING','CLAIMED')",
                (run_id,),
            ).fetchall()
            for row in rows:
                task = json.loads(row["payload_json"])
                task["status"] = "SKIPPED"
                task["stop_reason"] = "HARD_TIME_BUDGET_REACHED"
                self._update_task(task)
            self.store.commit()
        return run

    def _task(self, run_id: str, task_id: str, role: str | None = None) -> dict[str, Any]:
        row = self.store.conn.execute(
            "SELECT payload_json FROM analysis_tasks WHERE run_id=? AND task_id=?", (run_id, task_id)
        ).fetchone()
        if not row:
            raise ValueError(f"Unknown task for run: {task_id}")
        task = json.loads(row["payload_json"])
        if role and task.get("role") != role:
            raise ValueError(f"Task {task_id} belongs to {task.get('role')}, not {role}")
        if task.get("status") not in {"PENDING", "CLAIMED"}:
            raise ValueError(f"Task {task_id} cannot accept a submission in status {task.get('status')}")
        return task

    def start(self, scenario_id: str, mode: str = "STANDARD") -> dict[str, Any]:
        mode = mode.upper()
        if mode not in MODE_BUDGETS:
            raise ValueError("mode must be QUICK, STANDARD, or DEEP")
        if not self.store.has("scenarios", scenario_id):
            raise ValueError("Persist the Scenario before starting direct analysis")
        active = self.store.conn.execute(
            "SELECT payload_json FROM analysis_runs WHERE scenario_id=? AND status NOT IN ('COMPLETE','STOPPED') ORDER BY created_at DESC LIMIT 1",
            (scenario_id,),
        ).fetchone()
        if active:
            return {"status": "EXISTING", "run": json.loads(active["payload_json"])}
        started = datetime.now(timezone.utc)
        budget = dict(MODE_BUDGETS[mode])
        run = {
            "run_id": new_id("RUN"),
            "scenario_id": scenario_id,
            "mode": mode,
            "status": "PLANNING",
            "started_at": started.isoformat(),
            "deadline_at": (started + timedelta(minutes=budget["max_elapsed_minutes"])).isoformat(),
            "budget": budget,
            "dispatch_policy": "one planner, bounded block workers, one finalizer; no recursive task creation",
        }
        ts = now_iso()
        self.store.conn.execute(
            "INSERT INTO analysis_runs(run_id,scenario_id,mode,status,started_at,deadline_at,payload_json,content_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                run["run_id"], scenario_id, mode, run["status"], run["started_at"], run["deadline_at"],
                json.dumps(run, ensure_ascii=False), canonical_hash(run), ts, ts,
            ),
        )
        task = {
            "task_id": new_id("TASK"),
            "run_id": run["run_id"],
            "scenario_id": scenario_id,
            "role": "PLANNER",
            "sequence_no": 0,
            "status": "PENDING",
            "budget": {
                "max_business_blocks": budget["max_business_blocks"],
                "context_tokens": min(8000, budget["max_context_tokens_per_worker"]),
            },
            "acceptance": "Produce the complete business outline and mark only business-impact blocks for detail",
        }
        self._insert_task(task)
        self.store.commit()
        return {"status": "STARTED", "run": run, "first_task_id": task["task_id"]}

    def status(self, run_id: str) -> dict[str, Any]:
        run = self._run(run_id)
        rows = self.store.conn.execute(
            "SELECT payload_json FROM analysis_tasks WHERE run_id=? ORDER BY sequence_no,task_id", (run_id,)
        ).fetchall()
        tasks = [json.loads(row["payload_json"]) for row in rows]
        counts: dict[str, int] = {}
        for task in tasks:
            counts[task["status"]] = counts.get(task["status"], 0) + 1
        return {"run": run, "task_counts": counts, "tasks": tasks}

    def next_task(self, run_id: str) -> dict[str, Any]:
        run = self._run(run_id)
        row = self.store.conn.execute(
            "SELECT payload_json FROM analysis_tasks WHERE run_id=? AND status='PENDING' ORDER BY sequence_no,task_id LIMIT 1",
            (run_id,),
        ).fetchone()
        if not row:
            return {"status": "NO_PENDING_TASK", **self.status(run_id)}
        task = json.loads(row["payload_json"])
        task["status"] = "CLAIMED"
        task["claimed_at"] = now_iso()
        self._update_task(task)
        self.store.commit()
        context: dict[str, Any] = {
            "scenario": self.store.get("scenarios", run["scenario_id"]),
            "task": task,
            "hard_stop": run["deadline_at"],
        }
        if task["role"] == "PLANNER":
            context["reuse_index"] = self._known_block_index()
        elif task["role"] == "BLOCK":
            plan = self.store.get("scenario_plans", task["plan_id"])
            planned = next(
                item for item in plan["business_blocks"] if item["block_id"] == task["block_id"]
            )
            context["planned_block"] = planned
            context["reuse_candidates"] = self._reuse_candidates(
                str(planned.get("logical_key") or ""), run_id
            )
        elif task["role"] == "FINALIZER":
            context["business_blocks"] = [
                {
                    key: block.get(key)
                    for key in (
                        "block_id", "sequence_no", "title", "business_goal", "why_current",
                        "decision", "field_changes", "external_calls", "persistence", "output",
                        "error_behavior", "status",
                    )
                }
                for block in self.store.list_collection("business_blocks", run["scenario_id"])
            ]
        return {"status": "TASK", "context": context}

    def _receipt(self, run_id: str, task_id: str, kind: str, entity_id: str, payload_hash: str) -> dict[str, Any] | None:
        row = self.store.conn.execute(
            "SELECT receipt_id,entity_id,created_at FROM submission_receipts WHERE run_id=? AND task_id=? AND payload_hash=?",
            (run_id, task_id, payload_hash),
        ).fetchone()
        if row:
            return {
                "status": "ALREADY_ACCEPTED",
                "receipt_id": row["receipt_id"],
                "entity_id": row["entity_id"],
                "accepted_at": row["created_at"],
            }
        return None

    def _record_receipt(self, run_id: str, task_id: str, kind: str, entity_id: str, payload_hash: str) -> dict[str, Any]:
        receipt = {
            "receipt_id": new_id("RCPT"),
            "run_id": run_id,
            "task_id": task_id,
            "kind": kind,
            "entity_id": entity_id,
            "payload_hash": payload_hash,
            "accepted_at": now_iso(),
        }
        self.store.conn.execute(
            "INSERT INTO submission_receipts(receipt_id,run_id,task_id,kind,entity_id,payload_hash,created_at) VALUES(?,?,?,?,?,?,?)",
            (
                receipt["receipt_id"], run_id, task_id, kind, entity_id,
                payload_hash, receipt["accepted_at"],
            ),
        )
        return {"status": "ACCEPTED", **receipt}

    def submit(self, kind: str, run_id: str, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Direct submission must be a JSON object")
        if len(json.dumps(payload, ensure_ascii=False)) > 100000:
            raise ValueError("Direct submission exceeds 100000 characters; submit one bounded final artifact")
        run = self._run(run_id)
        if payload.get("run_id") not in {None, run_id}:
            raise ValueError("payload run_id does not match active run")
        if payload.get("scenario_id") not in {None, run["scenario_id"]}:
            raise ValueError("payload scenario_id does not match active run")
        role = {"plan": "PLANNER", "block": "BLOCK", "overview": "FINALIZER", "gap": None}.get(kind)
        if kind not in {"plan", "block", "overview", "gap"}:
            raise ValueError("kind must be plan, block, overview, or gap")
        payload = dict(payload)
        payload["run_id"] = run_id
        payload["scenario_id"] = run["scenario_id"]
        payload_hash = canonical_hash(payload)

        id_field = {"plan": "plan_id", "block": "block_id", "overview": "overview_id", "gap": "gap_id"}[kind]
        if not payload.get(id_field):
            payload[id_field] = new_id({"plan": "PLAN", "block": "BLOCK", "overview": "OVERVIEW", "gap": "GAP"}[kind])
        prior = self._receipt(run_id, task_id, kind, str(payload[id_field]), payload_hash)
        if prior:
            return prior
        if run["status"] in {"COMPLETE", "STOPPED"}:
            raise ValueError(f"Analysis run cannot accept submissions in status {run['status']}")
        task = self._task(run_id, task_id, role) if role else self._task(run_id, task_id)

        self.store.conn.execute("BEGIN IMMEDIATE")
        try:
            if kind == "plan":
                self._submit_plan(run, task, payload)
                collection = "scenario_plans"
            elif kind == "block":
                self._submit_block(run, task, payload)
                collection = "business_blocks"
            elif kind == "overview":
                self._submit_overview(run, task, payload)
                collection = "scenario_overviews"
            else:
                self._submit_gap(run, task, payload)
                collection = "gaps"
            self.store.upsert(collection, payload, task_id)
            receipt = self._record_receipt(run_id, task_id, kind, str(payload[id_field]), payload_hash)
            self.store.commit()
            return receipt
        except Exception:
            self.store.conn.rollback()
            raise

    def _submit_plan(self, run: dict[str, Any], task: dict[str, Any], payload: dict[str, Any]) -> None:
        missing = _required(payload, ("plan_id", "business_blocks", "critical_fields", "terminal_outcome"))
        if missing:
            raise ValueError("Plan missing required fields: " + ", ".join(missing))
        blocks = payload.get("business_blocks")
        if not isinstance(blocks, list) or not blocks:
            raise ValueError("business_blocks must be a non-empty array")
        budget = run["budget"]
        if len(blocks) > budget["max_business_blocks"]:
            raise ValueError("Plan exceeds hard business-block budget")
        seen: set[str] = set()
        for index, block in enumerate(blocks):
            missing_block = _required(block, ("block_id", "logical_key", "sequence_no", "title", "business_goal", "depth", "reason"))
            if missing_block:
                raise ValueError(f"business_blocks[{index}] missing: {', '.join(missing_block)}")
            if block["depth"] not in {"SUMMARY", "STANDARD", "CRITICAL"}:
                raise ValueError(f"business_blocks[{index}].depth must be SUMMARY, STANDARD, or CRITICAL")
            if block["block_id"] in seen:
                raise ValueError("Plan contains duplicate block_id")
            seen.add(block["block_id"])
        detail = [block for block in blocks if block["depth"] in {"STANDARD", "CRITICAL"}]
        detail.sort(key=lambda block: (0 if block["depth"] == "CRITICAL" else 1, float(block["sequence_no"])))
        detail = detail[: budget["max_detail_blocks"]]
        selected_ids = {block["block_id"] for block in detail}
        payload["selected_detail_block_ids"] = [block["block_id"] for block in detail]
        payload["status"] = "COMPLETE"

        for block in blocks:
            outline = {
                "block_id": block["block_id"],
                "logical_key": block["logical_key"],
                "scenario_id": run["scenario_id"],
                "run_id": run["run_id"],
                "sequence_no": block["sequence_no"],
                "title": block["title"],
                "business_goal": block["business_goal"],
                "why_current": block["reason"],
                "depth": block["depth"] if block["block_id"] in selected_ids else "SUMMARY",
                "inputs": block.get("inputs") or [],
                "decision": block.get("decision") or {},
                "implementation_steps": [],
                "field_changes": [],
                "external_calls": [],
                "persistence": [],
                "output": block.get("expected_output") or {},
                "error_behavior": [],
                "method_evidence": [],
                "evidence_refs": block.get("evidence_refs") or [],
                "status": "OUTLINE" if block["block_id"] in selected_ids else "SUMMARY_COMPLETE",
            }
            self.store.upsert("business_blocks", outline, task["task_id"])

        max_block_tasks = max(0, budget["max_model_tasks"] - 2)
        for index, block in enumerate(detail[:max_block_tasks], start=1):
            block_task = {
                "task_id": new_id("TASK"),
                "run_id": run["run_id"],
                "scenario_id": run["scenario_id"],
                "role": "BLOCK",
                "block_id": block["block_id"],
                "plan_id": payload["plan_id"],
                "sequence_no": index,
                "status": "PENDING",
                "budget": {
                    "max_semantic_probes": 6,
                    "max_method_evidence": 8,
                    "context_tokens": budget["max_context_tokens_per_worker"],
                    "max_followups": 0,
                },
                "acceptance": "Submit one reader-ready BusinessBlock; do not create child tasks",
            }
            self._insert_task(block_task)
        finalizer = {
            "task_id": new_id("TASK"),
            "run_id": run["run_id"],
            "scenario_id": run["scenario_id"],
            "role": "FINALIZER",
            "sequence_no": 99,
            "status": "WAITING" if detail else "PENDING",
            "budget": {"context_tokens": 8000, "max_source_reads": 0},
            "acceptance": "Write only the ScenarioOverview from stored BusinessBlocks",
        }
        self._insert_task(finalizer)
        task["status"] = "COMPLETE"
        self._update_task(task)
        run["status"] = "EXTRACTING" if detail else "FINALIZING"
        self._update_run(run)

    def _submit_block(self, run: dict[str, Any], task: dict[str, Any], payload: dict[str, Any]) -> None:
        missing = _required(
            payload,
            ("block_id", "logical_key", "sequence_no", "title", "business_goal", "why_current", "decision", "output", "reuse"),
        )
        if missing:
            raise ValueError("BusinessBlock missing required fields: " + ", ".join(missing))
        if payload["block_id"] != task.get("block_id"):
            raise ValueError("BusinessBlock does not match claimed task")
        for field in REQUIRED_BLOCK_ARRAYS:
            if not isinstance(payload.get(field), list):
                raise ValueError(f"BusinessBlock requires explicit {field} array")
        if len(payload["method_evidence"]) > 8:
            raise ValueError("BusinessBlock exceeds eight method-evidence references")
        if len(payload["implementation_steps"]) > 10:
            raise ValueError("BusinessBlock exceeds ten reader-relevant implementation steps")
        if not str(payload.get("business_goal") or "").strip() or not str(payload.get("why_current") or "").strip():
            raise ValueError("BusinessBlock requires reader-ready business explanation")
        reuse = payload.get("reuse")
        if not isinstance(reuse, dict) or reuse.get("decision") not in {"NEW", "EXACT_REUSE", "PARTIAL_REUSE"} or not reuse.get("basis"):
            raise ValueError("BusinessBlock reuse requires decision NEW/EXACT_REUSE/PARTIAL_REUSE and a basis")
        outline = self.store.get("business_blocks", payload["block_id"])
        if outline and payload["logical_key"] != outline.get("logical_key"):
            raise ValueError("BusinessBlock logical_key does not match its plan")
        payload["depth"] = (outline or {}).get("depth", "STANDARD")
        payload["status"] = payload.get("status", "COMPLETE")
        if payload["status"] not in {"COMPLETE", "GAP"}:
            raise ValueError("Submitted BusinessBlock status must be COMPLETE or GAP")
        task["status"] = "COMPLETE"
        self._update_task(task)
        remaining = self.store.conn.execute(
            "SELECT COUNT(*) AS n FROM analysis_tasks WHERE run_id=? AND role='BLOCK' AND status!='COMPLETE'",
            (run["run_id"],),
        ).fetchone()["n"]
        if remaining == 0:
            rows = self.store.conn.execute(
                "SELECT payload_json FROM analysis_tasks WHERE run_id=? AND role='FINALIZER'", (run["run_id"],)
            ).fetchall()
            for row in rows:
                finalizer = json.loads(row["payload_json"])
                finalizer["status"] = "PENDING"
                self._update_task(finalizer)
            run["status"] = "FINALIZING"
            self._update_run(run)

    def _submit_overview(self, run: dict[str, Any], task: dict[str, Any], payload: dict[str, Any]) -> None:
        missing = _required(
            payload,
            (
                "overview_id", "one_sentence", "business_context", "selected_route",
                "ordered_block_ids", "key_field_journeys", "external_effects",
                "persistence_effects", "failure_outcomes", "open_gaps",
            ),
        )
        if missing:
            raise ValueError("ScenarioOverview missing required fields: " + ", ".join(missing))
        valid_ids = {
            block["block_id"] for block in self.store.list_collection("business_blocks", run["scenario_id"])
        }
        if not isinstance(payload["ordered_block_ids"], list) or set(payload["ordered_block_ids"]) != valid_ids:
            raise ValueError("ScenarioOverview ordered_block_ids must contain every BusinessBlock exactly once")
        for field in ("key_field_journeys", "external_effects", "persistence_effects", "failure_outcomes", "open_gaps"):
            if not isinstance(payload[field], list):
                raise ValueError(f"ScenarioOverview {field} must be an array")
        payload["status"] = "COMPLETE"
        task["status"] = "COMPLETE"
        self._update_task(task)
        run["status"] = "COMPLETE"
        run["completed_at"] = now_iso()
        self._update_run(run)

    def _submit_gap(self, run: dict[str, Any], task: dict[str, Any], payload: dict[str, Any]) -> None:
        missing = _required(payload, ("gap_id", "category", "severity", "question"))
        if missing:
            raise ValueError("Gap missing required fields: " + ", ".join(missing))
        payload.setdefault("status", "OPEN")
        payload.setdefault("auto_generated", False)
        payload["source_task_id"] = task["task_id"]
