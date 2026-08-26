from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .core import canonical_hash, new_id, now_iso
from .store import FactStore


MODE_BUDGETS = {
    "QUICK": {
        "max_business_blocks": 5,
        "max_detail_blocks": 1,
        "max_model_tasks": 3,
        "max_elapsed_minutes": 10,
        "max_context_tokens_per_worker": 8000,
    },
    "STANDARD": {
        "max_business_blocks": 7,
        "max_detail_blocks": 2,
        "max_model_tasks": 4,
        "max_elapsed_minutes": 20,
        "max_context_tokens_per_worker": 10000,
    },
    "DEEP": {
        "max_business_blocks": 10,
        "max_detail_blocks": 4,
        "max_model_tasks": 6,
        "max_elapsed_minutes": 35,
        "max_context_tokens_per_worker": 12000,
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
MAX_SUBMISSION_ATTEMPTS = 2


class SubmissionContractError(ValueError):
    """Compact, machine-readable feedback for one bounded correction."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        path: str,
        expected: str,
        received: Any = None,
        hint: str = "Copy the task capsule output_contract.payload_template and change only its values.",
    ):
        super().__init__(message)
        self.issue = {
            "code": code,
            "path": path,
            "expected": expected,
            "received": received,
            "hint": hint,
        }
        self.corrections_remaining: int | None = None
        self.task_status: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "ERROR",
            "error_type": "SUBMISSION_CONTRACT",
            "error": self.issue,
            "corrections_remaining": self.corrections_remaining,
            "task_status": self.task_status,
        }


def _contract_error(
    message: str,
    *,
    code: str,
    path: str,
    expected: str,
    received: Any = None,
    hint: str = "Copy the task capsule output_contract.payload_template and change only its values.",
) -> None:
    raise SubmissionContractError(
        message,
        code=code,
        path=path,
        expected=expected,
        received=received,
        hint=hint,
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

    def _insert_run(self, run: dict[str, Any]) -> None:
        ts = now_iso()
        self.store.conn.execute(
            "INSERT INTO analysis_runs(run_id,scenario_id,mode,status,started_at,deadline_at,payload_json,content_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                run["run_id"], run["scenario_id"], run["mode"], run["status"],
                run["started_at"], run["deadline_at"], json.dumps(run, ensure_ascii=False),
                canonical_hash(run), ts, ts,
            ),
        )

    def _continuation_plan(self, previous: dict[str, Any]) -> dict[str, Any] | None:
        plan_id = previous.get("plan_id")
        if plan_id:
            plan = self.store.get("scenario_plans", str(plan_id))
            if plan:
                return plan
        row = self.store.conn.execute(
            "SELECT payload_json FROM scenario_plans WHERE scenario_id=? AND run_id=? AND status='COMPLETE' "
            "ORDER BY updated_at DESC LIMIT 1",
            (previous["scenario_id"], previous["run_id"]),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def _continue_stopped_run(
        self,
        previous: dict[str, Any],
        mode: str,
    ) -> dict[str, Any] | None:
        if previous.get("stop_reason") != "HARD_TIME_BUDGET_REACHED":
            return None
        plan = self._continuation_plan(previous)
        if not plan:
            return None
        selected_ids = [str(value) for value in plan.get("selected_detail_block_ids") or []]
        missing_ids = []
        for block_id in selected_ids:
            block = self.store.get("business_blocks", block_id)
            if not block or block.get("status") not in {"COMPLETE", "SUMMARY_COMPLETE", "GAP"}:
                missing_ids.append(block_id)

        started = datetime.now(timezone.utc)
        budget = dict(MODE_BUDGETS[mode])
        task_capacity = max(0, budget["max_model_tasks"] - 1)
        scheduled_ids = missing_ids[:task_capacity]
        deferred_ids = missing_ids[task_capacity:]
        run = {
            "run_id": new_id("RUN"),
            "scenario_id": previous["scenario_id"],
            "mode": mode,
            "status": "EXTRACTING" if scheduled_ids else "FINALIZING",
            "started_at": started.isoformat(),
            "deadline_at": (started + timedelta(minutes=budget["max_elapsed_minutes"])).isoformat(),
            "budget": budget,
            "continued_from_run_id": previous["run_id"],
            "continuation_root_run_id": previous.get("continuation_root_run_id") or previous["run_id"],
            "continuation_no": int(previous.get("continuation_no") or 0) + 1,
            "plan_id": plan["plan_id"],
            "reused_completed_block_ids": [value for value in selected_ids if value not in missing_ids],
            "scheduled_block_ids": scheduled_ids,
            "deferred_block_ids": deferred_ids,
            "dispatch_policy": "continue the persisted plan; never dispatch another planner; only fill unfinished blocks and final overview",
        }
        self._insert_run(run)
        for sequence, block_id in enumerate(scheduled_ids, start=1):
            self._insert_task({
                "task_id": new_id("TASK"),
                "run_id": run["run_id"],
                "scenario_id": run["scenario_id"],
                "role": "BLOCK",
                "block_id": block_id,
                "plan_id": plan["plan_id"],
                "sequence_no": sequence,
                "status": "PENDING",
                "budget": {
                    "max_semantic_probes": 4,
                    "max_method_evidence": 6,
                    "context_tokens": budget["max_context_tokens_per_worker"],
                    "max_followups": 0,
                },
                "acceptance": "Complete only this unfinished block from the persisted plan",
            })
        for block_id in deferred_ids:
            block = self.store.get("business_blocks", block_id)
            if block:
                block["status"] = "GAP"
                block["why_current"] = str(block.get("why_current") or "") + "；本轮恢复预算未继续深挖。"
                self.store.upsert("business_blocks", block, "RUNTIME-CONTINUATION-BUDGET")
            self.store.upsert("gaps", {
                "gap_id": new_id("GAP"),
                "scenario_id": run["scenario_id"],
                "run_id": run["run_id"],
                "category": "CONTINUATION_BUDGET",
                "severity": "LOW",
                "question": f"业务块 {block_id} 未在恢复轮的硬预算内继续深挖。",
                "status": "OPEN",
                "auto_generated": True,
            }, "RUNTIME-CONTINUATION-BUDGET")
        finalizer = {
            "task_id": new_id("TASK"),
            "run_id": run["run_id"],
            "scenario_id": run["scenario_id"],
            "role": "FINALIZER",
            "plan_id": plan["plan_id"],
            "sequence_no": 99,
            "status": "WAITING" if scheduled_ids else "PENDING",
            "budget": {"context_tokens": 6000, "max_source_reads": 0},
            "acceptance": "Summarize persisted blocks after a continuation; do not reread source code",
        }
        self._insert_task(finalizer)
        self.store.commit()
        return {
            "status": "CONTINUED",
            "run": run,
            "continued_from_run_id": previous["run_id"],
            "reused_completed_block_ids": run["reused_completed_block_ids"],
            "scheduled_block_ids": scheduled_ids,
            "first_task_id": (self.store.conn.execute(
                "SELECT task_id FROM analysis_tasks WHERE run_id=? AND status='PENDING' ORDER BY sequence_no LIMIT 1",
                (run["run_id"],),
            ).fetchone() or {"task_id": None})["task_id"],
        }

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
            active_run = self._run(json.loads(active["payload_json"])["run_id"])
            if active_run.get("status") not in {"COMPLETE", "STOPPED"}:
                return {"status": "EXISTING", "run": active_run}
        latest_row = self.store.conn.execute(
            "SELECT payload_json FROM analysis_runs WHERE scenario_id=? ORDER BY created_at DESC LIMIT 1",
            (scenario_id,),
        ).fetchone()
        if latest_row:
            latest_run = json.loads(latest_row["payload_json"])
            continued = self._continue_stopped_run(latest_run, mode) if latest_run.get("status") == "STOPPED" else None
            if continued:
                return continued
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
        self._insert_run(run)
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

    def _output_contract(
        self,
        run: dict[str, Any],
        task: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        role = task["role"]
        common = {
            "contract_version": "1",
            "runtime_injects": ["scenario_id", "run_id", "generated artifact id"],
            "presentation": {
                "language": "zh-CN",
                "rule": "所有面向读者的标题、目的、原因、步骤和结果使用简体中文；类名、方法名、字段名、枚举和配置键保持源码原文。",
                "format": "填写结构化字段，不要在文本中嵌入 JSON、Markdown 表格或 HTML。",
            },
            "correction_policy": {
                "max_attempts": MAX_SUBMISSION_ATTEMPTS,
                "corrections_remaining": int(
                    task.get("corrections_remaining", MAX_SUBMISSION_ATTEMPTS - 1)
                ),
            },
            "instruction": "按模板一次性填写并调用指定提交工具。面向读者的说明使用简体中文；不要读取脚本、Schema 或示例文件。",
        }
        if role == "PLANNER":
            return {
                **common,
                "submit_tool": "ucef_submit_plan",
                "required_fields": ["critical_fields", "terminal_outcome", "business_blocks"],
                "limits": {
                    "business_blocks": task["budget"]["max_business_blocks"],
                    "detail_blocks": run["budget"]["max_detail_blocks"],
                },
                "payload_template": {
                    "critical_fields": ["<关键业务字段名，保留源码原文>"],
                    "terminal_outcome": "<最终业务结果，使用中文>",
                    "business_blocks": [{
                        "block_id": "BLOCK-<stable-id>",
                        "logical_key": "<stable.business.key>",
                        "sequence_no": 10,
                        "title": "<中文业务标题>",
                        "business_goal": "<这一块解决什么业务问题，使用中文>",
                        "depth": "SUMMARY|STANDARD|CRITICAL",
                        "reason": "<为什么需要或不需要深挖，使用中文>",
                        "inputs": [],
                        "decision": {},
                        "expected_output": {},
                        "evidence_refs": [],
                    }],
                },
            }
        if role == "BLOCK":
            planned = context["planned_block"]
            return {
                **common,
                "submit_tool": "ucef_submit_block",
                "required_fields": [
                    "block_id", "logical_key", "sequence_no", "title", "business_goal",
                    "why_current", "inputs", "decision", "implementation_steps",
                    "field_changes", "external_calls", "persistence", "output",
                    "error_behavior", "method_evidence", "evidence_refs", "reuse", "status",
                ],
                "limits": {"implementation_steps": 7, "method_evidence": 6},
                "payload_template": {
                    "block_id": task["block_id"],
                    "logical_key": planned["logical_key"],
                    "sequence_no": planned["sequence_no"],
                    "title": planned["title"],
                    "business_goal": planned["business_goal"],
                    "why_current": "<由什么配置、请求条件或上一步结果进入这里，使用中文>",
                    "inputs": [],
                    "decision": planned.get("decision") or {},
                    "implementation_steps": [],
                    "field_changes": [],
                    "external_calls": [],
                    "persistence": [],
                    "output": planned.get("expected_output") or {},
                    "error_behavior": [],
                    "method_evidence": [],
                    "evidence_refs": planned.get("evidence_refs") or [],
                    "reuse": {"decision": "NEW|EXACT_REUSE|PARTIAL_REUSE", "basis": "<复用判断依据，使用中文>"},
                    "status": "COMPLETE|GAP",
                },
            }
        block_ids = [str(block["block_id"]) for block in context["business_blocks"]]
        return {
            **common,
            "submit_tool": "ucef_submit_overview",
            "required_fields": [
                "one_sentence", "business_context", "selected_route", "ordered_block_ids",
                "key_field_journeys", "external_effects", "persistence_effects",
                "failure_outcomes", "open_gaps",
            ],
            "payload_template": {
                "one_sentence": "<一句中文说明完整链路和最终结果>",
                "business_context": "<何时、为何触发本场景，使用中文>",
                "selected_route": {},
                "ordered_block_ids": block_ids,
                "key_field_journeys": [],
                "external_effects": [],
                "persistence_effects": [],
                "failure_outcomes": [],
                "open_gaps": [],
            },
        }

    def _release_finalizer_if_ready(self, run: dict[str, Any]) -> None:
        remaining = self.store.conn.execute(
            "SELECT COUNT(*) AS n FROM analysis_tasks WHERE run_id=? AND role='BLOCK' "
            "AND status NOT IN ('COMPLETE','FAILED','SKIPPED')",
            (run["run_id"],),
        ).fetchone()["n"]
        if remaining:
            return
        rows = self.store.conn.execute(
            "SELECT payload_json FROM analysis_tasks WHERE run_id=? AND role='FINALIZER'", (run["run_id"],)
        ).fetchall()
        for row in rows:
            finalizer = json.loads(row["payload_json"])
            if finalizer.get("status") == "WAITING":
                finalizer["status"] = "PENDING"
                self._update_task(finalizer)
        run["status"] = "FINALIZING"
        self._update_run(run)

    def _record_contract_failure(
        self,
        run: dict[str, Any],
        task: dict[str, Any],
        error: SubmissionContractError,
    ) -> None:
        failures = int(task.get("validation_failures") or 0) + 1
        task["validation_failures"] = failures
        task["last_validation_error"] = error.issue
        task["last_validation_error_at"] = now_iso()
        corrections_remaining = max(0, MAX_SUBMISSION_ATTEMPTS - failures)
        task["corrections_remaining"] = corrections_remaining
        if failures < MAX_SUBMISSION_ATTEMPTS:
            task["status"] = "CLAIMED"
        elif task.get("role") == "BLOCK":
            task["status"] = "FAILED"
            task["stop_reason"] = "SUBMISSION_CORRECTION_BUDGET_EXHAUSTED"
            outline = self.store.get("business_blocks", str(task.get("block_id")))
            if outline:
                outline["status"] = "GAP"
                self.store.upsert("business_blocks", outline, task["task_id"])
            self.store.upsert("gaps", {
                "gap_id": new_id("GAP"),
                "scenario_id": run["scenario_id"],
                "run_id": run["run_id"],
                "category": "SUBMISSION_VALIDATION",
                "severity": "MEDIUM",
                "question": f"业务块 {task.get('block_id')} 在一次修正后仍未通过结构校验。",
                "missing_evidence": [],
                "status": "OPEN",
                "auto_generated": True,
                "source_task_id": task["task_id"],
            }, task["task_id"])
        else:
            task["status"] = "FAILED"
            task["stop_reason"] = "SUBMISSION_CORRECTION_BUDGET_EXHAUSTED"
            run["status"] = "STOPPED"
            run["stop_reason"] = "SUBMISSION_CORRECTION_BUDGET_EXHAUSTED"
            self._update_run(run)
        self._update_task(task)
        if task.get("role") == "BLOCK" and task.get("status") == "FAILED":
            self._release_finalizer_if_ready(run)
        self.store.commit()
        error.corrections_remaining = corrections_remaining
        error.task_status = task["status"]

    def next_task(self, run_id: str) -> dict[str, Any]:
        run = self._run(run_id)
        row = self.store.conn.execute(
            "SELECT payload_json FROM analysis_tasks WHERE run_id=? AND status IN ('CLAIMED','PENDING') "
            "ORDER BY CASE status WHEN 'CLAIMED' THEN 0 ELSE 1 END,sequence_no,task_id LIMIT 1",
            (run_id,),
        ).fetchone()
        if not row:
            return {"status": "NO_PENDING_TASK", **self.status(run_id)}
        task = json.loads(row["payload_json"])
        if task["status"] == "PENDING":
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
            plan_id = task.get("plan_id") or run.get("plan_id")
            plan = self.store.get("scenario_plans", str(plan_id)) if plan_id else None
            planned_ids = [
                str(item["block_id"])
                for item in (plan or {}).get("business_blocks") or []
                if item.get("block_id")
            ]
            if planned_ids:
                current_blocks = [self.store.get("business_blocks", block_id) for block_id in planned_ids]
                current_blocks = [block for block in current_blocks if block]
            else:
                current_blocks = self.store.list_collection("business_blocks", run["scenario_id"])
            context["business_blocks"] = [
                {
                    key: block.get(key)
                    for key in (
                        "block_id", "sequence_no", "title", "business_goal", "why_current",
                        "decision", "field_changes", "external_calls", "persistence", "output",
                        "error_behavior", "status",
                    )
                }
                for block in current_blocks
            ]
        context["output_contract"] = self._output_contract(run, task, context)
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
            _contract_error(
                "Direct submission must be a JSON object",
                code="TYPE_MISMATCH", path="$", expected="object", received=type(payload).__name__,
            )
        if len(json.dumps(payload, ensure_ascii=False)) > 100000:
            _contract_error(
                "Direct submission exceeds 100000 characters; submit one bounded final artifact",
                code="PAYLOAD_TOO_LARGE", path="$", expected="at most 100000 characters",
                received="over-limit payload",
            )
        run = self._run(run_id)
        if payload.get("run_id") not in {None, run_id}:
            _contract_error(
                "payload run_id does not match active run",
                code="IDENTITY_MISMATCH", path="$.run_id", expected=run_id,
                received="different run_id", hint="Omit run_id; Runtime injects it.",
            )
        if payload.get("scenario_id") not in {None, run["scenario_id"]}:
            _contract_error(
                "payload scenario_id does not match active run",
                code="IDENTITY_MISMATCH", path="$.scenario_id", expected=run["scenario_id"],
                received="different scenario_id", hint="Omit scenario_id; Runtime injects it.",
            )
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
        except SubmissionContractError as exc:
            self.store.conn.rollback()
            self._record_contract_failure(run, task, exc)
            raise
        except Exception:
            self.store.conn.rollback()
            raise

    def _submit_plan(self, run: dict[str, Any], task: dict[str, Any], payload: dict[str, Any]) -> None:
        missing = _required(payload, ("plan_id", "business_blocks", "critical_fields", "terminal_outcome"))
        if missing:
            _contract_error(
                "Plan missing required fields: " + ", ".join(missing),
                code="MISSING_REQUIRED_FIELDS", path="$", expected="all required ScenarioPlan fields",
                received={"missing": missing},
            )
        blocks = payload.get("business_blocks")
        if not isinstance(blocks, list) or not blocks:
            _contract_error(
                "business_blocks must be a non-empty array",
                code="TYPE_MISMATCH", path="$.business_blocks", expected="non-empty array",
                received=type(blocks).__name__,
            )
        budget = run["budget"]
        if len(blocks) > budget["max_business_blocks"]:
            _contract_error(
                "Plan exceeds hard business-block budget",
                code="HARD_BUDGET_EXCEEDED", path="$.business_blocks",
                expected=f"at most {budget['max_business_blocks']} blocks", received={"count": len(blocks)},
                hint="Merge transparent handoffs; do not request more tasks.",
            )
        seen: set[str] = set()
        for index, block in enumerate(blocks):
            missing_block = _required(block, ("block_id", "logical_key", "sequence_no", "title", "business_goal", "depth", "reason"))
            if missing_block:
                _contract_error(
                    f"business_blocks[{index}] missing: {', '.join(missing_block)}",
                    code="MISSING_REQUIRED_FIELDS", path=f"$.business_blocks[{index}]",
                    expected="all required block-outline fields", received={"missing": missing_block},
                )
            if block["depth"] not in {"SUMMARY", "STANDARD", "CRITICAL"}:
                _contract_error(
                    f"business_blocks[{index}].depth must be SUMMARY, STANDARD, or CRITICAL",
                    code="INVALID_ENUM", path=f"$.business_blocks[{index}].depth",
                    expected="SUMMARY|STANDARD|CRITICAL", received=str(block.get("depth")),
                )
            if block["block_id"] in seen:
                _contract_error(
                    "Plan contains duplicate block_id",
                    code="DUPLICATE_ID", path=f"$.business_blocks[{index}].block_id",
                    expected="unique block_id", received=str(block.get("block_id")),
                )
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
                    "max_semantic_probes": 4,
                    "max_method_evidence": 6,
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
            "plan_id": payload["plan_id"],
            "sequence_no": 99,
            "status": "WAITING" if detail else "PENDING",
            "budget": {"context_tokens": 6000, "max_source_reads": 0},
            "acceptance": "Write only the ScenarioOverview from stored BusinessBlocks",
        }
        self._insert_task(finalizer)
        task["status"] = "COMPLETE"
        self._update_task(task)
        run["status"] = "EXTRACTING" if detail else "FINALIZING"
        run["plan_id"] = payload["plan_id"]
        self._update_run(run)

    def _submit_block(self, run: dict[str, Any], task: dict[str, Any], payload: dict[str, Any]) -> None:
        missing = _required(
            payload,
            ("block_id", "logical_key", "sequence_no", "title", "business_goal", "why_current", "decision", "output", "reuse"),
        )
        if missing:
            _contract_error(
                "BusinessBlock missing required fields: " + ", ".join(missing),
                code="MISSING_REQUIRED_FIELDS", path="$", expected="all required BusinessBlock fields",
                received={"missing": missing},
            )
        if payload["block_id"] != task.get("block_id"):
            _contract_error(
                "BusinessBlock does not match claimed task",
                code="IDENTITY_MISMATCH", path="$.block_id", expected=str(task.get("block_id")),
                received=str(payload.get("block_id")),
            )
        for field in REQUIRED_BLOCK_ARRAYS:
            if not isinstance(payload.get(field), list):
                _contract_error(
                    f"BusinessBlock requires explicit {field} array",
                    code="TYPE_MISMATCH", path=f"$.{field}", expected="array; use [] when empty",
                    received=type(payload.get(field)).__name__,
                )
        normalized_steps = []
        for index, raw_step in enumerate(payload["implementation_steps"], start=1):
            if isinstance(raw_step, dict):
                step = dict(raw_step)
                if not any(step.get(key) for key in ("name", "action", "processing", "description")):
                    step["action"] = f"业务步骤 {index}"
            else:
                step = {"step": index, "action": str(raw_step)}
            step.setdefault("step", index)
            normalized_steps.append(step)
        payload["implementation_steps"] = normalized_steps
        if len(payload["method_evidence"]) > 6:
            _contract_error(
                "BusinessBlock exceeds six method-evidence references",
                code="HARD_BUDGET_EXCEEDED", path="$.method_evidence", expected="at most 6 items",
                received={"count": len(payload["method_evidence"])},
            )
        if len(payload["implementation_steps"]) > 7:
            _contract_error(
                "BusinessBlock exceeds seven reader-relevant implementation steps",
                code="HARD_BUDGET_EXCEEDED", path="$.implementation_steps", expected="at most 7 items",
                received={"count": len(payload["implementation_steps"])},
            )
        if not str(payload.get("business_goal") or "").strip() or not str(payload.get("why_current") or "").strip():
            _contract_error(
                "BusinessBlock requires reader-ready business explanation",
                code="EMPTY_EXPLANATION", path="$.business_goal|$.why_current",
                expected="non-empty reader-facing text", received="empty text",
            )
        reuse = payload.get("reuse")
        if not isinstance(reuse, dict) or reuse.get("decision") not in {"NEW", "EXACT_REUSE", "PARTIAL_REUSE"} or not reuse.get("basis"):
            _contract_error(
                "BusinessBlock reuse requires decision NEW/EXACT_REUSE/PARTIAL_REUSE and a basis",
                code="INVALID_REUSE", path="$.reuse",
                expected="{decision: NEW|EXACT_REUSE|PARTIAL_REUSE, basis: non-empty}",
                received={"keys": sorted(reuse) if isinstance(reuse, dict) else []},
            )
        outline = self.store.get("business_blocks", payload["block_id"])
        if outline and payload["logical_key"] != outline.get("logical_key"):
            _contract_error(
                "BusinessBlock logical_key does not match its plan",
                code="IDENTITY_MISMATCH", path="$.logical_key", expected=str(outline.get("logical_key")),
                received=str(payload.get("logical_key")),
            )
        payload["depth"] = (outline or {}).get("depth", "STANDARD")
        payload["status"] = payload.get("status", "COMPLETE")
        if payload["status"] not in {"COMPLETE", "GAP"}:
            _contract_error(
                "Submitted BusinessBlock status must be COMPLETE or GAP",
                code="INVALID_ENUM", path="$.status", expected="COMPLETE|GAP",
                received=str(payload.get("status")),
            )
        task["status"] = "COMPLETE"
        self._update_task(task)
        self._release_finalizer_if_ready(run)

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
            _contract_error(
                "ScenarioOverview missing required fields: " + ", ".join(missing),
                code="MISSING_REQUIRED_FIELDS", path="$", expected="all required ScenarioOverview fields",
                received={"missing": missing},
            )
        plan_id = task.get("plan_id") or run.get("plan_id")
        plan = self.store.get("scenario_plans", str(plan_id)) if plan_id else None
        valid_ids = [
            str(block["block_id"])
            for block in (plan or {}).get("business_blocks") or []
            if block.get("block_id")
        ]
        if not valid_ids:
            valid_ids = [
                str(block["block_id"])
                for block in self.store.list_collection("business_blocks", run["scenario_id"])
            ]
        if not isinstance(payload["ordered_block_ids"], list) or payload["ordered_block_ids"] != valid_ids:
            _contract_error(
                "ScenarioOverview ordered_block_ids must contain every BusinessBlock exactly once",
                code="COVERAGE_MISMATCH", path="$.ordered_block_ids",
                expected=valid_ids,
                received=payload.get("ordered_block_ids") if isinstance(payload.get("ordered_block_ids"), list) else type(payload.get("ordered_block_ids")).__name__,
                hint="Use output_contract.payload_template.ordered_block_ids unchanged.",
            )
        for field in ("key_field_journeys", "external_effects", "persistence_effects", "failure_outcomes", "open_gaps"):
            if not isinstance(payload[field], list):
                _contract_error(
                    f"ScenarioOverview {field} must be an array",
                    code="TYPE_MISMATCH", path=f"$.{field}", expected="array; use [] when empty",
                    received=type(payload.get(field)).__name__,
                )
        payload["status"] = "COMPLETE"
        task["status"] = "COMPLETE"
        self._update_task(task)
        run["status"] = "COMPLETE"
        run["completed_at"] = now_iso()
        self._update_run(run)

    def _submit_gap(self, run: dict[str, Any], task: dict[str, Any], payload: dict[str, Any]) -> None:
        missing = _required(payload, ("gap_id", "category", "severity", "question"))
        if missing:
            _contract_error(
                "Gap missing required fields: " + ", ".join(missing),
                code="MISSING_REQUIRED_FIELDS", path="$", expected="category, severity, and question",
                received={"missing": missing},
            )
        payload.setdefault("status", "OPEN")
        payload.setdefault("auto_generated", False)
        payload["source_task_id"] = task["task_id"]
