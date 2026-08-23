#!/usr/bin/env python3
"""Run migration-only perf-trace Adapt Goals in strict serial order."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AdaptError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdaptError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AdaptError(f"JSON root must be an object: {path}")
    return value


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def validate_run_id(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise AdaptError(f"invalid run id: {value!r}")


def default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def verify_plan(plan: dict[str, Any], project_root: Path) -> list[str]:
    if plan.get("schema_version") != 1:
        raise AdaptError("unsupported Adapt plan schema")
    if Path(str(plan.get("project_root"))).resolve() != project_root:
        raise AdaptError("Adapt plan project_root does not match --project-root")
    policy = plan.get("execution_policy")
    if not isinstance(policy, dict):
        raise AdaptError("Adapt plan execution policy is missing")
    if policy.get("workflow_execution_allowed") is not False:
        raise AdaptError("Adapt plan must forbid workflow execution")
    if policy.get("project_skill_execution_allowed") is not False:
        raise AdaptError("Adapt plan must forbid project-skill execution")
    goals = plan.get("goals")
    if not isinstance(goals, list) or not goals:
        raise AdaptError("Adapt plan contains no goals")
    unresolved: list[str] = []
    for index, goal in enumerate(goals, 1):
        if not isinstance(goal, dict) or goal.get("id") != f"A{index:02d}":
            raise AdaptError("Adapt Goal IDs are not a contiguous serial chain")
        expected_predecessor = None if index == 1 else f"A{index - 1:02d}"
        if goal.get("adapt_predecessor") != expected_predecessor:
            raise AdaptError(f"{goal.get('id')}: Adapt predecessor mismatch")
        workflow = goal.get("workflow_input")
        if not isinstance(workflow, dict):
            raise AdaptError(f"{goal.get('id')}: workflow input is missing")
        verify_pinned_file(workflow, f"{goal.get('id')} workflow")
        references = goal.get("reference_skill_inputs")
        if not isinstance(references, list):
            raise AdaptError(f"{goal.get('id')}: reference inputs are malformed")
        for reference in references:
            if not isinstance(reference, dict):
                raise AdaptError(f"{goal.get('id')}: reference input is malformed")
            if reference.get("resolution") == "unresolved":
                unresolved.append(
                    f"{goal.get('id')}:{reference.get('requested_name')}"
                )
            else:
                verify_pinned_file(reference, f"{goal.get('id')} reference skill")
    adapt_skill = plan.get("adapt_skill")
    if not isinstance(adapt_skill, dict):
        raise AdaptError("Adapt skill provenance is missing")
    verify_pinned_file(adapt_skill, "adapt-workflows skill")
    adapt_contracts = plan.get("adapt_contracts")
    if not isinstance(adapt_contracts, list) or len(adapt_contracts) != 2:
        raise AdaptError("Adapt contract provenance is missing")
    for contract in adapt_contracts:
        if not isinstance(contract, dict):
            raise AdaptError("Adapt contract provenance is malformed")
        verify_pinned_file(contract, "Adapt contract")
    source_goal_map = plan.get("source_goal_map")
    scheduler_template = plan.get("scheduler_template")
    if not isinstance(source_goal_map, dict) or not isinstance(
        scheduler_template, dict
    ):
        raise AdaptError("generator provenance is missing")
    verify_pinned_file(source_goal_map, "source goal map")
    verify_pinned_file(scheduler_template, "scheduler template")
    scheduler_output = {
        "path": plan.get("scheduler_output"),
        "sha256": plan.get("scheduler_output_sha256"),
    }
    verify_pinned_file(scheduler_output, "generated Adapt scheduler")
    runner = Path(str(plan.get("runtime_scheduler_source"))).resolve()
    if not runner.is_file():
        raise AdaptError(f"runtime scheduler source is missing: {runner}")
    if sha256_file(runner) != plan.get("runtime_scheduler_source_sha256"):
        raise AdaptError(
            "runtime scheduler support changed; regenerate adapt_goals.json"
        )
    return unresolved


def verify_pinned_file(record: dict[str, Any], label: str) -> None:
    path_value = record.get("path")
    expected = record.get("sha256")
    if not isinstance(path_value, str) or not isinstance(expected, str):
        raise AdaptError(f"{label} has no pinned path/hash")
    path = Path(path_value).resolve()
    if not path.is_file():
        raise AdaptError(f"{label} is missing: {path}")
    observed = sha256_file(path)
    if observed != expected:
        raise AdaptError(
            f"{label} hash changed; regenerate adapt_goals.json: "
            f"expected {expected}, observed {observed}"
        )


def import_runtime_support(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("perf_trace_runtime_support", path)
    if spec is None or spec.loader is None:
        raise AdaptError(f"cannot load app-server support from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    required = [
        "AppServerClient",
        "APPROVAL_POLICY",
        "SANDBOX_POLICY",
        "TURN_SANDBOX_POLICY",
    ]
    missing = [name for name in required if not hasattr(module, name)]
    if missing:
        raise AdaptError(f"runtime scheduler support is missing: {missing}")
    return module


def validate_project_skill(goal: dict[str, Any]) -> tuple[Path, str]:
    path = Path(str(goal["output_skill_path"])).resolve()
    if not path.is_file():
        raise AdaptError(f"{goal['id']}: output project skill is missing: {path}")
    text = path.read_text(encoding="utf-8")
    expected_name = goal["output_skill"]
    if not re.search(
        rf"(?m)^name:\s*{re.escape(expected_name)}\s*$", text
    ):
        raise AdaptError(f"{goal['id']}: project skill name is incorrect")
    required_literals = [
        "## Serial Runtime Contract",
        f"runtime_branch={goal['runtime_branch']}",
        f"runtime_goal={goal['runtime_goal']}",
        "runtime_artifact_root=<scheduler-assigned>",
        "runtime_handoff_output=<scheduler-assigned>",
        "advance_only_after=complete",
    ]
    predecessor_value = (
        ",".join(goal["runtime_predecessors"])
        if goal["runtime_predecessors"]
        else "none"
    )
    required_literals.append(f"runtime_predecessors={predecessor_value}")
    missing = [value for value in required_literals if value not in text]
    if missing:
        raise AdaptError(
            f"{goal['id']}: project skill lacks serial runtime contract: {missing}"
        )
    return path, sha256_file(path)


def validate_handoff(
    *, goal: dict[str, Any], handoff_path: Path, run_id: str
) -> dict[str, Any]:
    handoff = load_json(handoff_path)
    exact = {
        "schema_version": 1,
        "adapt_run_id": run_id,
        "adapt_goal": goal["id"],
        "status": "complete",
        "mode": goal["mode"],
        "workflow_execution_performed": False,
        "project_skill_execution_performed": False,
    }
    for key, expected in exact.items():
        if handoff.get(key) != expected:
            raise AdaptError(
                f"{goal['id']}: handoff {key} mismatch; expected {expected!r}, "
                f"observed {handoff.get(key)!r}"
            )
    skill_path, skill_hash = validate_project_skill(goal)
    project_skill = handoff.get("project_skill")
    if not isinstance(project_skill, dict):
        raise AdaptError(f"{goal['id']}: handoff project_skill is missing")
    if (
        project_skill.get("name") != goal["output_skill"]
        or Path(str(project_skill.get("path"))).resolve() != skill_path
        or project_skill.get("sha256") != skill_hash
    ):
        raise AdaptError(f"{goal['id']}: handoff project-skill provenance mismatch")
    inputs = handoff.get("inputs")
    if not isinstance(inputs, dict):
        raise AdaptError(f"{goal['id']}: handoff inputs are missing")
    workflow_files = inputs.get("workflow_files")
    expected_workflow = goal["workflow_input"]
    if not isinstance(workflow_files, list) or not any(
        isinstance(item, dict)
        and Path(str(item.get("path"))).resolve()
        == Path(expected_workflow["path"]).resolve()
        and item.get("sha256") == expected_workflow["sha256"]
        for item in workflow_files
    ):
        raise AdaptError(f"{goal['id']}: workflow input provenance mismatch")
    reference_skills = inputs.get("reference_skills")
    if not isinstance(reference_skills, list):
        raise AdaptError(f"{goal['id']}: reference-skill provenance is missing")
    for expected_reference in goal["reference_skill_inputs"]:
        if not any(
            isinstance(item, dict)
            and item.get("requested_name")
            == expected_reference["requested_name"]
            and item.get("resolved_name") == expected_reference["resolved_name"]
            and Path(str(item.get("path"))).resolve()
            == Path(str(expected_reference["path"])).resolve()
            and item.get("sha256") == expected_reference["sha256"]
            and item.get("resolution") == expected_reference["resolution"]
            for item in reference_skills
        ):
            raise AdaptError(f"{goal['id']}: reference-skill provenance mismatch")
    previous = inputs.get("previous_adapt_handoff")
    if goal.get("adapt_predecessor") is None:
        if previous is not None:
            raise AdaptError(f"{goal['id']}: unexpected predecessor handoff")
    else:
        expected_previous_path = handoff_path.parent / (
            f"{goal['adapt_predecessor']}.json"
        )
        if (
            not isinstance(previous, dict)
            or Path(str(previous.get("path"))).resolve()
            != expected_previous_path.resolve()
            or previous.get("sha256") != sha256_file(expected_previous_path)
        ):
            raise AdaptError(f"{goal['id']}: predecessor handoff provenance mismatch")
    migrations = handoff.get("text_migrations")
    uncovered = handoff.get("uncovered_constraints_packaged")
    if not isinstance(migrations, list):
        raise AdaptError(f"{goal['id']}: text migration inventory is missing")
    if not isinstance(uncovered, list):
        raise AdaptError(f"{goal['id']}: uncovered-constraint inventory is missing")
    if goal["mode"] == "reference_migration" and not migrations:
        raise AdaptError(f"{goal['id']}: reference migration inventory is empty")
    if (
        goal["mode"] == "synthesize_uncovered"
        or any(
            item["resolution"] == "semantic_fallback"
            for item in goal["reference_skill_inputs"]
        )
    ) and not uncovered:
        raise AdaptError(f"{goal['id']}: uncovered constraints were not recorded")
    runtime = handoff.get("runtime_contract")
    if not isinstance(runtime, dict):
        raise AdaptError(f"{goal['id']}: runtime contract is missing")
    expected_runtime = {
        "branch": goal["runtime_branch"],
        "runtime_goal": goal["runtime_goal"],
        "runtime_predecessors": goal["runtime_predecessors"],
        "advance_only_after": "complete",
    }
    for key, expected in expected_runtime.items():
        if runtime.get(key) != expected:
            raise AdaptError(f"{goal['id']}: runtime contract {key} mismatch")
    validation = handoff.get("validation")
    if not isinstance(validation, dict) or not all(
        validation.get(key) is True
        for key in (
            "skill_structure_valid",
            "serial_runtime_contract_valid",
            "source_hashes_valid",
        )
    ):
        raise AdaptError(f"{goal['id']}: handoff validation is incomplete")
    return handoff


def goal_prompt(
    *,
    goal: dict[str, Any],
    plan_path: Path,
    ledger_path: Path,
    ledger_hash: str,
    handoff_path: Path,
    artifact_root: Path,
    run_id: str,
) -> str:
    predecessor = goal.get("adapt_predecessor")
    predecessor_handoff = None
    if predecessor:
        predecessor_path = handoff_path.parent / f"{predecessor}.json"
        predecessor_handoff = {
            "path": str(predecessor_path),
            "sha256": sha256_file(predecessor_path),
        }
    assignment = {
        "adapt_run_id": run_id,
        "adapt_goal": goal["id"],
        "mode": goal["mode"],
        "plan_path": str(plan_path),
        "plan_goal": goal,
        "cumulative_adapt_ledger": {
            "path": str(ledger_path),
            "sha256": ledger_hash,
        },
        "immediate_predecessor_handoff": predecessor_handoff,
        "adapt_artifact_root": str(artifact_root),
        "adapt_handoff_output": str(handoff_path),
    }
    return "\n".join(
        [
            "$adapt-workflows",
            "",
            f"只执行迁移 Goal {goal['id']}，不要执行被迁移的 workflow。",
            "这是文本/skill 迁移任务，不是性能实验。禁止运行模型、GPU/DCU、profiler、trace、PMC、报告生成器，也禁止调用产出的 project skill。",
            "完整读取 hash 锁定的 workflow 和 reference SKILL.md；reference skill 只是源文本，不得作为能力调用。",
            "先校验累计 Adapt ledger 和直接前驱 handoff，再迁移项目、模型、运行时、设备、路径、工具、产物和证据文字。",
            "参考 skill 未覆盖而 workflow 明确要求的过程与约束，封装进本 Goal 指定的新 project skill；不得删减或模糊化。",
            "产出的 project skill 必须包含 references/project-skill-runtime-contract.md 规定的 `## Serial Runtime Contract`，明确串行 runtime predecessor handoff 和 advance gate。",
            "只能修改 plan_goal.output_skill_path 所属 skill 目录，并写 adapt_artifact_root 与 adapt_handoff_output；不得改写前序 skill/handoff/ledger。",
            "完成结构、内容、source hash 和串行 runtime contract 校验后，按 references/adapt-goal-contract.md 写 handoff；两个 execution_performed 字段必须为 false。",
            "handoff 写成且自检通过后才能把当前正式 Goal 标记 complete；受阻时不得伪造 handoff 或跳过。",
            "",
            json.dumps(assignment, ensure_ascii=False, indent=2),
        ]
    )


class SerialAdaptScheduler:
    def __init__(
        self,
        *,
        project_root: Path,
        plan_path: Path,
        plan: dict[str, Any],
        run_id: str,
        codex_bin: Path,
        model: str | None,
        poll_seconds: float,
        timeout_seconds: float,
        idle_timeout_seconds: float,
        resume: bool,
    ) -> None:
        self.project_root = project_root
        self.plan_path = plan_path
        self.plan = plan
        self.run_id = run_id
        self.codex_bin = codex_bin
        self.model = model
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self.idle_timeout_seconds = idle_timeout_seconds
        self.resume = resume
        self.run_dir = project_root / "perf_trace/adaptation/runtime" / run_id
        self.handoff_dir = self.run_dir / "handoffs"
        self.artifact_dir = self.run_dir / "artifacts"
        self.state_path = self.run_dir / "state.json"
        self.ledger_path = self.run_dir / "adapt_handoff_ledger.json"
        self.runtime = import_runtime_support(
            Path(str(plan["runtime_scheduler_source"])).resolve()
        )
        self.client: Any = None
        self.state: dict[str, Any] = {}
        self.ledger: dict[str, Any] = {}
        self.current_thread_id: str | None = None

    def initialize(self) -> int:
        goals = self.plan["goals"]
        if self.resume:
            if not self.run_dir.is_dir():
                raise AdaptError(f"resume run does not exist: {self.run_dir}")
            self.state = load_json(self.state_path)
            self.ledger = load_json(self.ledger_path)
            snapshot = self.run_dir / "adapt_goals.snapshot.json"
            if sha256_file(snapshot) != self.state.get("plan_snapshot_sha256"):
                raise AdaptError("resume plan snapshot hash mismatch")
            if load_json(snapshot) != self.plan:
                raise AdaptError("current Adapt plan differs from the run snapshot")
        else:
            if self.run_dir.exists():
                raise AdaptError(f"run already exists: {self.run_dir}")
            self.handoff_dir.mkdir(parents=True)
            self.artifact_dir.mkdir()
            snapshot = self.run_dir / "adapt_goals.snapshot.json"
            atomic_json(snapshot, self.plan)
            self.ledger = {
                "schema_version": 1,
                "adapt_run_id": self.run_id,
                "mode": "serial_migration_only",
                "workflow_execution_performed": False,
                "project_skill_execution_performed": False,
                "handoffs": [],
            }
            self.state = {
                "schema_version": 1,
                "adapt_run_id": self.run_id,
                "status": "pending",
                "current_goal": None,
                "plan_snapshot_sha256": sha256_file(snapshot),
                "goals": {
                    goal["id"]: {"status": "pending"} for goal in goals
                },
            }
            atomic_json(self.ledger_path, self.ledger)
            atomic_json(self.state_path, self.state)
        entries = self.ledger.get("handoffs")
        if not isinstance(entries, list):
            raise AdaptError("Adapt ledger handoffs must be a list")
        for index, entry in enumerate(entries):
            goal = goals[index]
            if not isinstance(entry, dict) or entry.get("source_goal") != goal["id"]:
                raise AdaptError("Adapt ledger is not a valid completed prefix")
            handoff_path = Path(str(entry.get("path"))).resolve()
            if sha256_file(handoff_path) != entry.get("sha256"):
                raise AdaptError(f"{goal['id']}: committed handoff hash mismatch")
            validate_handoff(goal=goal, handoff_path=handoff_path, run_id=self.run_id)
        while len(entries) < len(goals):
            next_goal = goals[len(entries)]
            pending_handoff = self.handoff_dir / f"{next_goal['id']}.json"
            if not pending_handoff.is_file():
                break
            handoff = validate_handoff(
                goal=next_goal,
                handoff_path=pending_handoff,
                run_id=self.run_id,
            )
            entry = {
                "source_goal": next_goal["id"],
                "status": "complete",
                "path": str(pending_handoff),
                "sha256": sha256_file(pending_handoff),
                "project_skill": handoff["project_skill"],
                "committed_at": utc_now(),
                "promoted_during_resume": True,
            }
            entries.append(entry)
            self.state["goals"][next_goal["id"]]["status"] = "complete"
            atomic_json(self.ledger_path, self.ledger)
            self.checkpoint()
        if len(entries) == len(goals):
            return len(goals)
        return len(entries)

    def checkpoint(self) -> None:
        self.state["updated_at"] = utc_now()
        atomic_json(self.state_path, self.state)

    def start_client(self) -> None:
        self.client = self.runtime.AppServerClient(
            codex_bin=self.codex_bin,
            cwd=self.project_root,
            raw_log_path=self.run_dir / "app_server.jsonl",
            stderr_log_path=self.run_dir / "app_server.stderr.log",
            request_timeout=60.0,
        )
        self.client.start()
        self.client.initialize()
        adapt_skill_path = Path(str(self.plan["adapt_skill"]["path"])).resolve()
        self.client.request(
            "skills/extraRoots/set", {"extraRoots": [str(adapt_skill_path.parent.parent)]}
        )

    def thread_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "cwd": str(self.project_root),
            "approvalPolicy": self.runtime.APPROVAL_POLICY,
            "sandbox": self.runtime.SANDBOX_POLICY,
            "ephemeral": False,
        }
        if self.model:
            params["model"] = self.model
        return params

    def turn_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "cwd": str(self.project_root),
            "approvalPolicy": self.runtime.APPROVAL_POLICY,
            "sandboxPolicy": self.runtime.TURN_SANDBOX_POLICY,
            "effort": "max",
            "summary": "concise",
        }
        if self.model:
            params["model"] = self.model
        return params

    def wait_for_complete(self, goal_id: str, thread_id: str) -> None:
        deadline = (
            time.monotonic() + self.timeout_seconds
            if self.timeout_seconds > 0
            else None
        )
        while deadline is None or time.monotonic() < deadline:
            if not self.client.reader_errors.empty():
                raise AdaptError(self.client.reader_errors.get_nowait())
            if not self.client.server_requests.empty():
                request = self.client.server_requests.get_nowait()
                raise AdaptError(
                    f"{goal_id}: interactive app-server request rejected: "
                    f"{request.get('method')}"
                )
            result = self.client.request("thread/goal/get", {"threadId": thread_id})
            goal = result.get("goal")
            if not isinstance(goal, dict):
                raise AdaptError(f"{goal_id}: app-server returned no Goal")
            status = goal.get("status")
            self.state["goals"][goal_id]["formal_goal"] = goal
            self.checkpoint()
            if status == "complete":
                return
            if status in {"blocked", "cancelled", "failed"}:
                raise AdaptError(f"{goal_id}: formal Goal stopped as {status}")
            if status != "active":
                raise AdaptError(f"{goal_id}: unexpected formal Goal status {status}")
            time.sleep(self.poll_seconds)
        raise AdaptError(f"{goal_id}: formal Goal exceeded timeout")

    def wait_for_idle(self, goal_id: str, thread_id: str) -> None:
        deadline = time.monotonic() + self.idle_timeout_seconds
        while time.monotonic() < deadline:
            result = self.client.request(
                "thread/read", {"threadId": thread_id, "includeTurns": False}
            )
            thread = result.get("thread")
            if not isinstance(thread, dict):
                raise AdaptError(f"{goal_id}: thread/read returned no thread")
            status = thread.get("status")
            status_type = status.get("type") if isinstance(status, dict) else status
            if status_type == "idle":
                return
            if status_type not in {"active", "idle"}:
                raise AdaptError(
                    f"{goal_id}: unexpected thread status after completion: "
                    f"{status_type}"
                )
            time.sleep(min(self.poll_seconds, 1.0))
        raise AdaptError(f"{goal_id}: thread did not become idle")

    def run_goal(self, goal: dict[str, Any]) -> None:
        goal_id = goal["id"]
        handoff_path = self.handoff_dir / f"{goal_id}.json"
        if handoff_path.exists():
            raise AdaptError(f"{goal_id}: uncommitted handoff already exists")
        artifact_root = self.artifact_dir / goal_id
        if artifact_root.exists():
            if not self.resume or not artifact_root.is_dir():
                raise AdaptError(f"{goal_id}: artifact root already exists")
        else:
            artifact_root.mkdir()
        ledger_hash = sha256_file(self.ledger_path)
        prompt = goal_prompt(
            goal=goal,
            plan_path=self.plan_path,
            ledger_path=self.ledger_path,
            ledger_hash=ledger_hash,
            handoff_path=handoff_path,
            artifact_root=artifact_root,
            run_id=self.run_id,
        )
        result = self.client.request("thread/start", self.thread_params())
        thread = result.get("thread")
        thread_id = thread.get("id") if isinstance(thread, dict) else None
        if not isinstance(thread_id, str):
            raise AdaptError(f"{goal_id}: thread/start returned no thread")
        self.current_thread_id = thread_id
        record = self.state["goals"][goal_id]
        record.update(
            {
                "status": "running",
                "thread_id": thread_id,
                "artifact_root": str(artifact_root),
                "handoff_output": str(handoff_path),
            }
        )
        self.state["status"] = "running"
        self.state["current_goal"] = goal_id
        self.checkpoint()
        objective = (
            f"Complete migration-only Adapt Goal {goal_id}: create or update "
            f"${goal['output_skill']} from the pinned workflow/reference text, "
            "write its validated Adapt handoff, and do not execute any runtime workflow."
        )
        goal_result = self.client.request(
            "thread/goal/set",
            {"threadId": thread_id, "objective": objective, "status": "paused"},
        )
        if not isinstance(goal_result.get("goal"), dict):
            raise AdaptError(f"{goal_id}: thread/goal/set returned no Goal")
        inputs = [
            {"type": "text", "text": prompt},
            {
                "type": "skill",
                "name": "adapt-workflows",
                "path": str(Path(self.plan["adapt_skill"]["path"]).resolve()),
            },
        ]
        turn = self.client.request(
            "turn/start", {"threadId": thread_id, "input": inputs, **self.turn_params()}
        ).get("turn")
        if not isinstance(turn, dict) or turn.get("status") in {"failed", "interrupted"}:
            raise AdaptError(f"{goal_id}: initial turn failed")
        current = self.client.request(
            "thread/goal/get", {"threadId": thread_id}
        ).get("goal")
        if not isinstance(current, dict):
            raise AdaptError(f"{goal_id}: cannot read formal Goal")
        if current.get("status") == "paused":
            self.client.request(
                "thread/goal/set", {"threadId": thread_id, "status": "active"}
            )
        elif current.get("status") != "complete":
            raise AdaptError(
                f"{goal_id}: unexpected Goal status after first turn: "
                f"{current.get('status')}"
            )
        if current.get("status") != "complete":
            self.wait_for_complete(goal_id, thread_id)
        self.wait_for_idle(goal_id, thread_id)
        handoff = validate_handoff(
            goal=goal, handoff_path=handoff_path, run_id=self.run_id
        )
        if sha256_file(self.ledger_path) != ledger_hash:
            raise AdaptError(f"{goal_id}: ledger changed while Goal was running")
        entry = {
            "source_goal": goal_id,
            "status": "complete",
            "path": str(handoff_path),
            "sha256": sha256_file(handoff_path),
            "project_skill": handoff["project_skill"],
            "committed_at": utc_now(),
        }
        self.ledger["handoffs"].append(entry)
        atomic_json(self.ledger_path, self.ledger)
        record["status"] = "complete"
        record["handoff_sha256"] = entry["sha256"]
        self.current_thread_id = None
        self.checkpoint()

    def run(self) -> None:
        start_index = self.initialize()
        goals = self.plan["goals"]
        if start_index == len(goals):
            self.state["status"] = "complete"
            self.state["current_goal"] = None
            self.checkpoint()
            return
        self.start_client()
        try:
            for goal in goals[start_index:]:
                self.run_goal(goal)
            self.state["status"] = "complete"
            self.state["current_goal"] = None
            self.state["completed_at"] = utc_now()
            self.checkpoint()
        except BaseException as exc:
            self.state["status"] = "stopped"
            self.state["error"] = str(exc)
            self.checkpoint()
            if self.current_thread_id is not None:
                try:
                    self.client.request(
                        "thread/goal/set",
                        {"threadId": self.current_thread_id, "status": "paused"},
                    )
                except Exception:
                    pass
            raise
        finally:
            if self.client is not None:
                self.client.close()


def dry_run(plan: dict[str, Any], plan_path: Path, unresolved: list[str]) -> None:
    payload = {
        "schema_version": 1,
        "status": "dry_run",
        "plan": str(plan_path),
        "goal_count": len(plan["goals"]),
        "strict_serial": True,
        "workflow_execution_performed": False,
        "project_skill_execution_performed": False,
        "unresolved_reference_skills": unresolved,
        "goals": [
            {
                "id": goal["id"],
                "adapt_predecessor": goal["adapt_predecessor"],
                "mode": goal["mode"],
                "workflow": goal["workflow_input"],
                "reference_skills": goal["reference_skill_inputs"],
                "output_skill": goal["output_skill"],
                "output_skill_path": goal["output_skill_path"],
                "runtime_branch": goal["runtime_branch"],
                "runtime_goal": goal["runtime_goal"],
                "runtime_predecessors": goal["runtime_predecessors"],
                "advance_only_after": "validated Adapt handoff commit",
            }
            for goal in plan["goals"]
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run perf-trace workflow-to-project-skill migration Goals serially."
    )
    parser.add_argument("--project-root", default=str(default_project_root()))
    parser.add_argument("--plan")
    parser.add_argument("--dry-run", action="store_true")
    run_group = parser.add_mutually_exclusive_group()
    run_group.add_argument("--run-id")
    run_group.add_argument("--resume-run-id")
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--goal-timeout-seconds", type=float, default=0.0)
    parser.add_argument("--idle-timeout-seconds", type=float, default=300.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        project_root = Path(args.project_root).expanduser().resolve()
        plan_path = (
            Path(args.plan).expanduser().resolve()
            if args.plan
            else project_root / "perf_trace/adaptation/adapt_goals.json"
        )
        plan = load_json(plan_path)
        unresolved = verify_plan(plan, project_root)
        if args.dry_run:
            dry_run(plan, plan_path, unresolved)
            return 0
        if unresolved:
            raise AdaptError(
                "cannot execute with unresolved reference skills: "
                + ", ".join(unresolved)
            )
        if (
            args.poll_seconds <= 0
            or args.goal_timeout_seconds < 0
            or args.idle_timeout_seconds <= 0
        ):
            raise AdaptError(
                "poll/idle timeout must be positive and Goal timeout non-negative"
            )
        resume = args.resume_run_id is not None
        run_id = args.resume_run_id or args.run_id or (
            "adapt-perf-trace-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        )
        validate_run_id(run_id)
        codex_bin = Path(args.codex_bin)
        if not codex_bin.is_absolute():
            import shutil

            resolved = shutil.which(args.codex_bin)
            if resolved is None:
                raise AdaptError(f"Codex executable not found: {args.codex_bin}")
            codex_bin = Path(resolved)
        scheduler = SerialAdaptScheduler(
            project_root=project_root,
            plan_path=plan_path,
            plan=plan,
            run_id=run_id,
            codex_bin=codex_bin.resolve(),
            model=args.model,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.goal_timeout_seconds,
            idle_timeout_seconds=args.idle_timeout_seconds,
            resume=resume,
        )
        scheduler.run()
        print(
            json.dumps(
                {
                    "status": "complete",
                    "adapt_run_id": run_id,
                    "ledger": str(scheduler.ledger_path),
                    "project_skill_root": plan["project_skill_root"],
                    "workflow_execution_performed": False,
                    "project_skill_execution_performed": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (AdaptError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
