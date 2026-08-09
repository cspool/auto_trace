#!/usr/bin/env python3
"""Run the unified Workflow 01-05 Skill migration and scheduler extension.

Codex owns each Goal's internal Turn/continuation lifecycle.  This program owns
only serial Goal scheduling, canonical state, lightweight structural gates,
checkpoint/resume, and raw app-server logs.  Agents must not edit its state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EXPECTED_STAGE_ORDER = (
    "P01", "P02", "P03", "P04", "P05",
    "P07", "P08", "P09", "P10", "P11", "P12",
)
EXPECTED_DEPENDENCIES = {
    "P01": [],
    "P02": [],
    "P03": ["P02"],
    "P04": ["P01", "P03"],
    "P05": ["P02", "P03"],
    "P07": ["P01", "P02", "P03", "P04", "P05"],
    "P08": ["P02", "P03", "P07"],
    "P09": ["P05", "P07", "P08"],
    "P10": ["P01", "P02", "P03", "P04", "P05", "P07", "P08", "P09"],
    "P11": [
        "P01", "P02", "P03", "P04", "P05",
        "P07", "P08", "P09", "P10",
    ],
    "P12": [
        "P01", "P02", "P03", "P04", "P05",
        "P07", "P08", "P09", "P10", "P11",
    ],
}
SOURCE_STAGE_IDS = ("P01", "P02", "P03", "P04")
WORKFLOW_GAP_STAGE_IDS = ("P05", "P07", "P08", "P09", "P10", "P11")
WORKFLOW05_GAP_STAGE_IDS = ("P07", "P08", "P09", "P10", "P11")
SCHEDULER_STAGE_ID = "P12"
HISTORICAL_SCHEDULER_STAGE_ID = "P06"
PREDECESSOR_STAGE_ORDER = ("P01", "P02", "P03", "P04", "P05", "P06")
PRESERVED_STAGE_ORDER = ("P01", "P02", "P03", "P04", "P05")
ADDED_STAGE_ORDER = ("P07", "P08", "P09", "P10", "P11", "P12")
PREDECESSOR_PLAN_ID = "qwen-dcu-perf-trace-workflow-complete-adaptation-v3"
PREDECESSOR_PLAN_SHA256 = (
    "b4b8966805b2e2695314a53d381a4f7bf08aa6e29406505e97a08b85ad173672"
)
PREDECESSOR_CONTRACT_SHA256 = (
    "6d026760541f96db1f2025a86277eefb0e3e50d5144586ac3546c85023008fd6"
)
PREDECESSOR_STATE_SCHEMA_VERSION = 6
PREDECESSOR_ORCHESTRATION_PROTOCOL = (
    "goal-owned-turns-v6-perf-trace-source-skill-text-alignment"
)
EXPECTED_RUNTIME_OUTPUTS = [
    "perf_trace/scripts/run_perf_trace_01_05.py",
    "perf_trace/manifests/workflow01_05_full_pipeline.json",
    "perf_trace/manifests/workflow05_existing_evidence_pipeline.json",
]
EXPECTED_RUNTIME_BINDINGS = {
    "R01": {"skill": "qwen-dcu-same-input-layer-wise-workflow"},
    "R02": {"skill": "qwen-dcu-fx-process-nvtx-instrumentation"},
    "R03": {"skill": "qwen-dcu-process-performance-breakdown"},
    "R04": {"skill": "qwen-dcu-process-gpu-hardware-trace"},
    "R05": {"skill": "qwen-dcu-segmented-process-attribution"},
    "R06": {"skill": "qwen-dcu-workflow05-evidence-planning"},
    "R07": {"skill": "qwen-dcu-workflow05-selective-process-trace"},
    "R08": {"skill": "qwen-dcu-workflow05-targeted-hardware-gap-analysis"},
    "R09": {"skill": "qwen-dcu-workflow05-utilization-concurrency-analysis"},
    "R10": {"skill": "qwen-dcu-workflow05-trace-visualization-reporting"},
}
EXPECTED_RUNTIME_BRANCHES = [
    {
        "branch": "workflow01-05-full",
        "manifest": "perf_trace/manifests/workflow01_05_full_pipeline.json",
        "goals": [f"R{value:02d}" for value in range(1, 11)],
        "bindings": EXPECTED_RUNTIME_BINDINGS,
        "requires": [],
    },
    {
        "branch": "workflow05-existing-evidence",
        "manifest": "perf_trace/manifests/workflow05_existing_evidence_pipeline.json",
        "goals": [f"R{value:02d}" for value in range(6, 11)],
        "bindings": {
            goal_id: EXPECTED_RUNTIME_BINDINGS[goal_id]
            for goal_id in [f"R{value:02d}" for value in range(6, 11)]
        },
        "requires": [
            "a compatible completed R01-R05 cumulative runtime handoff ledger supplied as a user parameter",
            "no automatic rerun or modification of Workflow 01-04 products",
        ],
    },
]
EXPECTED_CAPABILITY_COVERAGE = [
    {
        "workflow": "perf_trace/workflows/01_layer_wise_end_to_end_trace.md",
        "capability": "layer_wise_same_input_timing_denominator",
        "coverage_kind": "source_skill",
        "stages": ["P01"],
        "target_skills": ["qwen-dcu-same-input-layer-wise-workflow"],
    },
    {
        "workflow": (
            "perf_trace/workflows/02_representative_fx_process_wise_trace.md"
        ),
        "capability": "representative_process_instrumentation",
        "coverage_kind": "source_skill",
        "stages": ["P02"],
        "target_skills": ["qwen-dcu-fx-process-nvtx-instrumentation"],
    },
    {
        "workflow": (
            "perf_trace/workflows/02_representative_fx_process_wise_trace.md"
        ),
        "capability": "representative_process_performance_breakdown",
        "coverage_kind": "source_skill",
        "stages": ["P03"],
        "target_skills": ["qwen-dcu-process-performance-breakdown"],
    },
    {
        "workflow": "perf_trace/workflows/03_process_gpu_hardware_trace.md",
        "capability": "process_boundary_and_non_replay_timing",
        "coverage_kind": "source_skill_boundary",
        "stages": ["P02", "P03"],
        "target_skills": [
            "qwen-dcu-fx-process-nvtx-instrumentation",
            "qwen-dcu-process-performance-breakdown",
        ],
    },
    {
        "workflow": "perf_trace/workflows/03_process_gpu_hardware_trace.md",
        "capability": "process_gpu_hardware_replay_join_and_report",
        "coverage_kind": "workflow_gap",
        "stages": ["P05"],
        "target_skills": ["qwen-dcu-process-gpu-hardware-trace"],
    },
    {
        "workflow": (
            "perf_trace/workflows/04_full_layer_fx_process_wise_estimate.md"
        ),
        "capability": "full_layer_segmented_process_attribution",
        "coverage_kind": "source_skill",
        "stages": ["P04"],
        "target_skills": ["qwen-dcu-segmented-process-attribution"],
    },
    {
        "workflow": "perf_trace/workflows/05_workflow04_guided_selective_process_trace_and_resource_gap_analysis.md",
        "capability": "workflow05_upstream_reuse_and_candidate_planning",
        "coverage_kind": "workflow_gap",
        "stages": ["P07"],
        "target_skills": ["qwen-dcu-workflow05-evidence-planning"],
    },
    {
        "workflow": "perf_trace/workflows/05_workflow04_guided_selective_process_trace_and_resource_gap_analysis.md",
        "capability": "workflow05_selective_non_replay_process_trace",
        "coverage_kind": "workflow_gap",
        "stages": ["P08"],
        "target_skills": ["qwen-dcu-workflow05-selective-process-trace"],
    },
    {
        "workflow": "perf_trace/workflows/05_workflow04_guided_selective_process_trace_and_resource_gap_analysis.md",
        "capability": "workflow05_targeted_hardware_gap_analysis",
        "coverage_kind": "workflow_gap",
        "stages": ["P09"],
        "target_skills": ["qwen-dcu-workflow05-targeted-hardware-gap-analysis"],
    },
    {
        "workflow": "perf_trace/workflows/05_workflow04_guided_selective_process_trace_and_resource_gap_analysis.md",
        "capability": "workflow05_utilization_and_concurrency_opportunity_analysis",
        "coverage_kind": "workflow_gap",
        "stages": ["P10"],
        "target_skills": ["qwen-dcu-workflow05-utilization-concurrency-analysis"],
    },
    {
        "workflow": "perf_trace/workflows/05_workflow04_guided_selective_process_trace_and_resource_gap_analysis.md",
        "capability": "workflow05_linked_trace_visualization_and_reporting",
        "coverage_kind": "workflow_gap",
        "stages": ["P11"],
        "target_skills": ["qwen-dcu-workflow05-trace-visualization-reporting"],
    },
]
STATE_SCHEMA_VERSION = 7
ORCHESTRATION_PROTOCOL = (
    "goal-owned-turns-v7-perf-trace-workflow01-05-extension"
)
PERF_TRACE_RELATIVE_ROOT = Path("perf_trace")
ADAPTATION_RELATIVE_ROOT = (
    PERF_TRACE_RELATIVE_ROOT / "workflows" / "project_adaptation"
)
GOAL_TOKEN_BUDGET_POLICY = "unset"
DEFAULT_PROGRESS_INTERVAL_SECONDS = 10.0
DEFAULT_SANDBOX_POLICY = "danger-full-access"
APPROVAL_POLICY = "never"
TERMINAL_GOAL_STATUSES = {
    "blocked",
    "usageLimited",
    "budgetLimited",
    "complete",
}
STOP_GOAL_STATUS_TO_STAGE = {
    "blocked": "GOAL_BLOCKED",
    "usageLimited": "USAGE_LIMITED",
    "budgetLimited": "BUDGET_LIMITED",
    "paused": "PAUSED",
}
class OrchestrationError(RuntimeError):
    """A deterministic orchestration failure."""


class RpcError(OrchestrationError):
    """An app-server JSON-RPC error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_stage_state_record() -> dict[str, Any]:
    return {
        "status": "NOT_STARTED",
        "phase": "NOT_STARTED",
        "thread_id": None,
        "turn_ids": [],
        "requested_turn_ids": [],
        "active_turn_ids": [],
        "initial_turn_id": None,
        "expected_interrupt_ids": [],
        "goal": None,
        "thread_status": None,
        "final_gate": None,
        "last_error": None,
        "last_activity": None,
        "last_agent_message": None,
        "last_command": None,
        "last_command_output": None,
        "activity_counts": {},
        "history": [],
    }


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_canonical_json(path: Path) -> str:
    payload = load_json(path)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(canonical)


def tree_digest(root: Path) -> str:
    if not root.is_dir():
        raise OrchestrationError(f"Skill directory is missing: {root}")
    digest = hashlib.sha256()
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def relative_file_set(root: Path) -> list[str]:
    if not root.is_dir():
        raise OrchestrationError(f"Skill directory is missing: {root}")
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OrchestrationError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise OrchestrationError(f"Invalid JSON file {path}: {exc}") from exc


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(encoded + "\n", encoding="utf-8")
    os.replace(temporary, path)


def perf_trace_root(project_root: Path) -> Path:
    resolved_project_root = project_root.resolve()
    resolved = (resolved_project_root / PERF_TRACE_RELATIVE_ROOT).resolve()
    try:
        resolved.relative_to(resolved_project_root)
    except ValueError as exc:
        raise OrchestrationError(
            "perf_trace root escapes project root: "
            f"{resolved_project_root / PERF_TRACE_RELATIVE_ROOT}"
        ) from exc
    return resolved


def perf_trace_path(project_root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    resolved = candidate.resolve()
    allowed_root = perf_trace_root(project_root)
    try:
        resolved.relative_to(allowed_root)
    except ValueError as exc:
        raise OrchestrationError(
            f"Path escapes perf_trace root {allowed_root}: {value}"
        ) from exc
    return resolved


def project_path(project_root: Path, value: str | Path) -> Path:
    resolved_project_root = project_root.resolve()
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = resolved_project_root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_project_root)
    except ValueError as exc:
        raise OrchestrationError(
            f"Path escapes project root {resolved_project_root}: {value}"
        ) from exc
    return resolved


def timestamp_age_seconds(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def thread_status_type(value: Any) -> str | None:
    if isinstance(value, dict):
        kind = value.get("type")
        return kind if isinstance(kind, str) else None
    return value if isinstance(value, str) else None


def build_progress_snapshot(
    state: dict[str, Any],
    plan: dict[str, Any],
    project_root: Path,
    state_path: Path,
) -> dict[str, Any]:
    stage_plans = {
        stage.get("id"): stage
        for stage in plan.get("stages", [])
        if isinstance(stage, dict) and isinstance(stage.get("id"), str)
    }
    state_stages = state.get("stages", {})
    if not isinstance(state_stages, dict):
        state_stages = {}
    rows: list[dict[str, Any]] = []
    committed = 0
    started = 0
    for index, stage_id in enumerate(EXPECTED_STAGE_ORDER, start=1):
        record = state_stages.get(stage_id, {})
        if not isinstance(record, dict):
            record = {}
        status = record.get("status") or "NOT_STARTED"
        phase = record.get("phase") or "NOT_STARTED"
        if status == "COMMITTED":
            committed += 1
        if status not in (None, "NOT_STARTED"):
            started += 1
        goal = record.get("goal")
        if not isinstance(goal, dict):
            goal = {}
        stage_plan = stage_plans.get(stage_id, {})
        handoff_value = (
            stage_plan.get("handoff")
            if isinstance(stage_plan, dict)
            else None
        )
        handoff_ready = False
        if (
            status != "NOT_STARTED"
            and isinstance(handoff_value, str)
            and handoff_value
        ):
            handoff_ready = perf_trace_path(
                project_root, handoff_value
            ).is_file()
        final_gate = record.get("final_gate")
        rows.append(
            {
                "id": stage_id,
                "ordinal": index,
                "status": status,
                "phase": phase,
                "thread_id": record.get("thread_id"),
                "thread_status": thread_status_type(record.get("thread_status")),
                "goal_status": goal.get("status"),
                "goal_token_budget": goal.get("tokenBudget"),
                "tokens_used": goal.get("tokensUsed"),
                "goal_time_seconds": goal.get("timeUsedSeconds"),
                "turn_count": len(record.get("turn_ids") or []),
                "active_turn_count": len(record.get("active_turn_ids") or []),
                "handoff_ready": handoff_ready,
                "final_gate": (
                    final_gate.get("status")
                    if isinstance(final_gate, dict)
                    else None
                ),
                "last_error": record.get("last_error"),
                "last_activity": record.get("last_activity"),
                "last_agent_message": record.get("last_agent_message"),
                "last_command": record.get("last_command"),
                "last_command_output": record.get("last_command_output"),
                "activity_counts": record.get("activity_counts", {}),
                "updated_at": record.get("updated_at"),
            }
        )
    total = len(EXPECTED_STAGE_ORDER)
    workflow05_extension = plan.get("workflow05_extension")
    added_stages = (
        workflow05_extension.get("added_stages", [])
        if isinstance(workflow05_extension, dict)
        else []
    )
    extension_pending = (
        isinstance(workflow05_extension, dict)
        and state.get("plan_sha256")
        == workflow05_extension.get("predecessor_plan_sha256")
        and any(stage_id not in state_stages for stage_id in added_stages)
    )
    return {
        "schema_version": 1,
        "observed_at": utc_now(),
        "state_file": str(state_path),
        "run_id": state.get("run_id"),
        "orchestration_status": (
            "EXTENSION_PENDING" if extension_pending else state.get("status")
        ),
        "canonical_state_status": state.get("status"),
        "workflow05_extension_pending": extension_pending,
        "state_plan_id": state.get("plan_id"),
        "current_plan_id": plan.get("plan_id"),
        "orchestration_protocol": state.get("orchestration_protocol"),
        "goal_token_budget_policy": state.get("goal_token_budget_policy"),
        "sandbox_policy": state.get("sandbox_policy"),
        "approval_policy": state.get("approval_policy"),
        "network_access": state.get("network_access"),
        "current_stage": state.get("current_stage"),
        "committed_stages": committed,
        "started_stages": started,
        "total_stages": total,
        "committed_percent": round(100.0 * committed / total, 1),
        "state_updated_at": state.get("updated_at"),
        "state_age_seconds": timestamp_age_seconds(state.get("updated_at")),
        "stages": rows,
    }


def format_duration(value: Any) -> str:
    if not isinstance(value, (int, float)) or value < 0:
        return "-"
    seconds = int(value)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{seconds:02d}s"
    if minutes:
        return f"{minutes}m{seconds:02d}s"
    return f"{seconds}s"


def compact_output(value: Any, limit: int = 500) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            text = str(value)
    text = " ".join(text.split())
    if not text:
        return None
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def current_progress_row(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    current = snapshot.get("current_stage")
    rows = snapshot.get("stages", [])
    if isinstance(current, str):
        selected = next(
            (
                row
                for row in rows
                if isinstance(row, dict) and row.get("id") == current
            ),
            None,
        )
        if selected is not None:
            return selected
    return next(
        (
            row
            for row in rows
            if isinstance(row, dict) and row.get("status") != "COMMITTED"
        ),
        None,
    )


def format_progress_compact(snapshot: dict[str, Any]) -> str:
    age = snapshot.get("state_age_seconds")
    age_text = format_duration(age) if age is not None else "-"
    parts = [
        f"run={snapshot.get('run_id') or '-'}",
        f"status={snapshot.get('orchestration_status') or '-'}",
        (
            f"committed={snapshot.get('committed_stages', 0)}/"
            f"{snapshot.get('total_stages', len(EXPECTED_STAGE_ORDER))}"
        ),
    ]
    row = current_progress_row(snapshot)
    if row is not None:
        parts.extend(
            [
                f"stage={row.get('id')}",
                f"stage_status={row.get('status') or '-'}",
                f"phase={row.get('phase') or '-'}",
                f"goal={row.get('goal_status') or '-'}",
                f"thread={row.get('thread_status') or '-'}",
                (
                    f"turns={row.get('turn_count', 0)}"
                    f"(active={row.get('active_turn_count', 0)})"
                ),
                f"tokens={row.get('tokens_used') or 0}",
                f"goal_time={format_duration(row.get('goal_time_seconds'))}",
                f"handoff={'ready' if row.get('handoff_ready') else '-'}",
            ]
        )
        activity = row.get("last_activity")
        if isinstance(activity, dict):
            parts.append(
                "activity="
                + str(
                    activity.get("summary")
                    or activity.get("method")
                    or activity.get("item_type")
                    or "-"
                )
            )
        message = compact_output(row.get("last_agent_message"), limit=120)
        if message:
            parts.append(f"message={json.dumps(message, ensure_ascii=False)}")
    parts.append(f"state_age={age_text}")
    return " ".join(parts)


def format_progress_human(snapshot: dict[str, Any]) -> str:
    lines = [
        (
            f"Run {snapshot.get('run_id') or '-'} | "
            f"{snapshot.get('orchestration_status') or '-'} | "
            f"committed {snapshot.get('committed_stages', 0)}/"
            f"{snapshot.get('total_stages', len(EXPECTED_STAGE_ORDER))} "
            f"({snapshot.get('committed_percent', 0.0):.1f}%)"
        ),
        (
            f"Current: {snapshot.get('current_stage') or '-'} | "
            f"state updated {format_duration(snapshot.get('state_age_seconds'))} ago | "
            f"token budget policy: "
            f"{snapshot.get('goal_token_budget_policy') or 'legacy/unknown'}"
        ),
        (
            f"Permissions: sandbox={snapshot.get('sandbox_policy') or '-'} | "
            f"approval={snapshot.get('approval_policy') or '-'} | "
            f"network={snapshot.get('network_access')}"
        ),
        (
            "Lifecycle: "
            f"{snapshot.get('orchestration_protocol') or 'legacy/unknown'}"
        ),
        "",
        "     Stage  Status                Phase             Goal          "
        "Thread    Turns      Tokens     Goal time  Handoff    Gate",
    ]
    current = snapshot.get("current_stage")
    for row in snapshot.get("stages", []):
        marker = ">" if row.get("id") == current else " "
        gate = row.get("final_gate") or "-"
        turns = f"{row.get('turn_count', 0)}/{row.get('active_turn_count', 0)}"
        lines.append(
            f"{marker} {row.get('ordinal', 0):>2}/"
            f"{snapshot.get('total_stages', len(EXPECTED_STAGE_ORDER))} "
            f"{str(row.get('id') or '-'):6} "
            f"{str(row.get('status') or '-'):21} "
            f"{str(row.get('phase') or '-'):17} "
            f"{str(row.get('goal_status') or '-'):13} "
            f"{str(row.get('thread_status') or '-'):9} "
            f"{turns:10} "
            f"{str(row.get('tokens_used') or 0):10} "
            f"{format_duration(row.get('goal_time_seconds')):10} "
            f"{('yes' if row.get('handoff_ready') else '-'):10} "
            f"{gate}"
        )
        if row.get("last_error"):
            lines.append(f"       error: {row['last_error']}")
        if row.get("id") == current:
            activity = row.get("last_activity")
            if isinstance(activity, dict):
                lines.append(
                    "       activity: "
                    + str(
                        activity.get("summary")
                        or activity.get("method")
                        or activity.get("item_type")
                        or "-"
                    )
                )
            message = compact_output(row.get("last_agent_message"), limit=300)
            if message:
                lines.append(f"       agent: {message}")
            command = compact_output(row.get("last_command"), limit=300)
            if command:
                lines.append(f"       command: {command}")
    return "\n".join(lines)


def parse_semver(text: str) -> tuple[int, int, int]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        raise OrchestrationError(f"Cannot parse Codex version from: {text!r}")
    return tuple(int(part) for part in match.groups())


def discover_codex(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    environment_value = os.environ.get("CODEX_BIN")
    if environment_value:
        candidates.append(Path(environment_value))
    path_value = shutil.which("codex")
    if path_value:
        candidates.append(Path(path_value))
    release_root = Path.home() / ".codex" / "packages" / "standalone" / "releases"
    if release_root.is_dir():
        discovered = sorted(
            release_root.glob("*/bin/codex"),
            key=lambda path: parse_semver(path.parents[1].name),
            reverse=True,
        )
        candidates.extend(discovered)
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    raise OrchestrationError(
        "Cannot find an executable Codex binary. Pass --codex-bin or set CODEX_BIN."
    )


def read_codex_version(codex_bin: Path) -> tuple[str, tuple[int, int, int]]:
    completed = subprocess.run(
        [str(codex_bin), "--version"],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    output = (completed.stdout or completed.stderr).strip()
    if completed.returncode != 0:
        raise OrchestrationError(
            f"Codex version check failed ({completed.returncode}): {output}"
        )
    return output, parse_semver(output)


def generate_protocol_schema(codex_bin: Path, output_dir: Path) -> tuple[Path, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            str(codex_bin),
            "app-server",
            "generate-json-schema",
            "--out",
            str(output_dir),
        ],
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise OrchestrationError(
            "Codex schema generation failed "
            f"({completed.returncode}): {completed.stderr.strip()}"
        )
    bundle = output_dir / "codex_app_server_protocol.v2.schemas.json"
    if not bundle.is_file():
        raise OrchestrationError(f"Generated protocol bundle is missing: {bundle}")
    return bundle, sha256_canonical_json(bundle)


def validate_plan(
    plan: dict[str, Any],
    project_root: Path,
    plan_path: Path,
) -> None:
    perf_trace_path(project_root, plan_path)
    if plan.get("schema_version") != 5:
        raise OrchestrationError("adaptation plan schema_version must be 5")
    if plan.get("adaptation_mode") != "workflow-capability-complete-adaptation":
        raise OrchestrationError(
            "adaptation plan must use workflow-capability-complete-adaptation"
        )
    if (
        plan.get("adaptation_scope")
        != "source-preserving-alignment-workflow-gap-synthesis-and-workflow01-05-scheduler"
    ):
        raise OrchestrationError("adaptation_scope must describe the unified Workflow 01-05 control plane")
    if "token_budget" in plan or "tokenBudget" in plan:
        raise OrchestrationError("Goal requests must not set an explicit token budget")

    stages = plan.get("stages")
    if not isinstance(stages, list):
        raise OrchestrationError("adaptation plan stages must be a list")
    order = tuple(stage.get("id") for stage in stages if isinstance(stage, dict))
    if order != EXPECTED_STAGE_ORDER or plan.get("stage_order") != list(EXPECTED_STAGE_ORDER):
        raise OrchestrationError(
            f"stage order must be {EXPECTED_STAGE_ORDER}, got {order}"
        )

    for key in (
        "workflow_contract",
        "implementation_plan",
        "common_goal_contract",
        "runner",
        "verifier",
    ):
        value = plan.get(key)
        if not isinstance(value, str) or not perf_trace_path(project_root, value).is_file():
            raise OrchestrationError(f"plan {key} is missing: {value}")
    for key in (
        "canonical_state",
        "run_log_root",
        "gate_report_root",
        "artifact_root",
        "handoff_root",
        "target_skill_root",
    ):
        value = plan.get(key)
        if not isinstance(value, str):
            raise OrchestrationError(f"plan {key} is missing")
        perf_trace_path(project_root, value)

    adaptation_root = perf_trace_path(project_root, ADAPTATION_RELATIVE_ROOT)
    control_files = plan.get("control_plane_files")
    if not isinstance(control_files, list) or not control_files:
        raise OrchestrationError("control_plane_files must be a nonempty list")
    if control_files != sorted(set(control_files)):
        raise OrchestrationError("control_plane_files must be sorted and unique")
    for relative in control_files:
        if not isinstance(relative, str):
            raise OrchestrationError("control_plane_files entries must be strings")
        path = (adaptation_root / relative).resolve()
        try:
            path.relative_to(adaptation_root)
        except ValueError as exc:
            raise OrchestrationError(f"control-plane path escapes adaptation root: {relative}") from exc
        if not path.is_file() or path.stat().st_size == 0:
            raise OrchestrationError(f"control-plane file is missing or empty: {path}")

    expected_extension = {
        "predecessor_plan_id": PREDECESSOR_PLAN_ID,
        "predecessor_plan_sha256": PREDECESSOR_PLAN_SHA256,
        "predecessor_contract_sha256": PREDECESSOR_CONTRACT_SHA256,
        "predecessor_state_schema_version": PREDECESSOR_STATE_SCHEMA_VERSION,
        "predecessor_orchestration_protocol": PREDECESSOR_ORCHESTRATION_PROTOCOL,
        "predecessor_stage_order": list(PREDECESSOR_STAGE_ORDER),
        "preserved_committed_stages": list(PRESERVED_STAGE_ORDER),
        "superseded_scheduler_stage": HISTORICAL_SCHEDULER_STAGE_ID,
        "added_stages": list(ADDED_STAGE_ORDER),
        "workflow05_gap_stages": list(WORKFLOW05_GAP_STAGE_IDS),
        "scheduler_stage": SCHEDULER_STAGE_ID,
        "adoption_flag": "--adopt-workflow05-extension",
    }
    if plan.get("workflow05_extension") != expected_extension:
        raise OrchestrationError(
            "workflow05_extension must exactly identify the completed P01-P06 "
            "predecessor and P07-P12 extension"
        )

    target_evidence = plan.get("target_project_evidence")
    if not isinstance(target_evidence, list) or not target_evidence:
        raise OrchestrationError("target_project_evidence must be a nonempty list")
    evidence_paths: set[str] = set()
    for record in target_evidence:
        if not isinstance(record, dict) or set(record) != {"path", "sha256", "role"}:
            raise OrchestrationError("malformed target-project evidence record")
        value = record["path"]
        if value in evidence_paths:
            raise OrchestrationError(f"duplicate target-project evidence: {value}")
        evidence_paths.add(value)
        path = project_path(project_root, value)
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise OrchestrationError(f"target-project evidence changed: {value}")
        if not isinstance(record["role"], str) or not record["role"].strip():
            raise OrchestrationError(f"target-project evidence role is empty: {value}")

    workflows = plan.get("reference_workflows")
    if not isinstance(workflows, list) or len(workflows) != 5:
        raise OrchestrationError("reference_workflows must contain exactly Workflow 01-05")
    workflow_paths: set[str] = set()
    for record in workflows:
        if not isinstance(record, dict) or set(record) != {"path", "sha256", "role"}:
            raise OrchestrationError("malformed reference Workflow record")
        value = record["path"]
        path = perf_trace_path(project_root, value)
        if value in workflow_paths or not path.is_file() or sha256_file(path) != record["sha256"]:
            raise OrchestrationError(f"reference Workflow is duplicate, missing, or changed: {value}")
        workflow_paths.add(value)
    if plan.get("supplied_workflow_roots") != [record["path"] for record in workflows]:
        raise OrchestrationError("supplied_workflow_roots must enumerate Workflow 01-05")

    if plan.get("capability_coverage") != EXPECTED_CAPABILITY_COVERAGE:
        raise OrchestrationError("capability_coverage must exactly cover every Workflow 01-05 capability")
    if {record["workflow"] for record in EXPECTED_CAPABILITY_COVERAGE} != workflow_paths:
        raise OrchestrationError("capability_coverage omits a reference Workflow")
    serialized_plan = json.dumps(plan, ensure_ascii=False, sort_keys=True).lower()
    if any(marker in serialized_plan for marker in (
        "unscheduled_workflows", "no_authoritative_target_skill", '"coverage_kind": "ignored"',
        '"coverage_kind": "unsupported"', '"coverage_kind": "unscheduled"',
    )):
        raise OrchestrationError("every Workflow capability must remain scheduled")

    reference_runner = plan.get("reference_runner")
    if not isinstance(reference_runner, dict):
        raise OrchestrationError("reference_runner contract is missing")
    reference_path = Path(reference_runner.get("path", "")).resolve()
    if not reference_path.is_file() or sha256_file(reference_path) != reference_runner.get("sha256"):
        raise OrchestrationError("byte-preserved reference runner is missing or changed")

    precommitted = plan.get("precommitted_upstream_skills")
    if not isinstance(precommitted, list) or len(precommitted) != 7:
        raise OrchestrationError("seven precommitted upstream/boundary Skills are required")
    precommitted_names: set[str] = set()
    for skill in precommitted:
        if not isinstance(skill, dict) or skill.get("immutable") is not True:
            raise OrchestrationError("precommitted Skill entries must be immutable objects")
        name = skill.get("name")
        if not isinstance(name, str) or name in precommitted_names:
            raise OrchestrationError("precommitted Skill names must be unique")
        precommitted_names.add(name)
        skill_root = project_path(project_root, skill["path"])
        if tree_digest(skill_root) != skill.get("tree_sha256"):
            raise OrchestrationError(f"precommitted upstream Skill changed: {name}")

    predecessor_runtime_paths = {
        "perf_trace/scripts/run_perf_trace.py",
        "perf_trace/manifests/core_attribution_pipeline.json",
        "perf_trace/workflows/project_adaptation/artifacts/P06/handoff.json",
    }
    predecessor_runtime = plan.get("predecessor_runtime_products")
    if not isinstance(predecessor_runtime, list) or {
        item.get("path") for item in predecessor_runtime if isinstance(item, dict)
    } != predecessor_runtime_paths:
        raise OrchestrationError("predecessor_runtime_products set is incomplete")
    for item in predecessor_runtime:
        path = project_path(project_root, item["path"])
        if not path.is_file() or sha256_file(path) != item.get("sha256"):
            raise OrchestrationError(f"predecessor runtime product changed: {item['path']}")

    predecessor_handoffs = plan.get("predecessor_skill_handoffs")
    if not isinstance(predecessor_handoffs, list) or [
        item.get("stage") for item in predecessor_handoffs if isinstance(item, dict)
    ] != list(PRESERVED_STAGE_ORDER):
        raise OrchestrationError("predecessor_skill_handoffs must pin P01-P05")
    for item in predecessor_handoffs:
        path = perf_trace_path(project_root, item["path"])
        if not path.is_file() or sha256_file(path) != item.get("sha256"):
            raise OrchestrationError(f"predecessor handoff changed: {item['path']}")

    if plan.get("runtime_outputs") != EXPECTED_RUNTIME_OUTPUTS:
        raise OrchestrationError("top-level runtime_outputs mismatch")
    if plan.get("runtime_branches") != EXPECTED_RUNTIME_BRANCHES:
        raise OrchestrationError("top-level runtime_branches mismatch")
    for path_value in EXPECTED_RUNTIME_OUTPUTS:
        perf_trace_path(project_root, path_value)

    seen: set[str] = set()
    source_names: set[str] = set()
    output_names: set[str] = set()
    for stage in stages:
        if not isinstance(stage, dict):
            raise OrchestrationError("all stages must be objects")
        stage_id = stage["id"]
        expected_kind = (
            "source_skill_text_alignment" if stage_id in SOURCE_STAGE_IDS
            else "workflow_gap_skill_generation" if stage_id in WORKFLOW_GAP_STAGE_IDS
            else "scheduler_generation" if stage_id == SCHEDULER_STAGE_ID
            else None
        )
        if expected_kind is None or stage.get("kind") != expected_kind:
            raise OrchestrationError(f"{stage_id}: invalid stage kind")
        dependencies = stage.get("depends_on")
        if dependencies != EXPECTED_DEPENDENCIES[stage_id] or any(dep not in seen for dep in dependencies):
            raise OrchestrationError(f"{stage_id}: dependency graph mismatch")
        seen.add(stage_id)
        objective = stage.get("objective")
        if not isinstance(objective, str) or not objective.strip() or len(objective) > 4000:
            raise OrchestrationError(f"{stage_id}: objective is missing or too long")
        goal = stage.get("goal_template")
        requirements = stage.get("workflow_requirements")
        if not isinstance(goal, str) or not perf_trace_path(project_root, goal).is_file():
            raise OrchestrationError(f"{stage_id}: Goal template is missing")
        if not isinstance(requirements, list) or not requirements or any(value not in workflow_paths for value in requirements):
            raise OrchestrationError(f"{stage_id}: workflow_requirements is not fully pinned")
        for key in ("artifact_dir", "handoff"):
            if not isinstance(stage.get(key), str):
                raise OrchestrationError(f"{stage_id}: missing {key}")
            perf_trace_path(project_root, stage[key])

        expected_gate = [
            "python3", f"{{project_root}}/{plan['verifier']}",
            "--project-root", "{project_root}", "--plan", "{plan_path}",
            "--stage", "{stage_id}",
        ]
        if stage_id in SOURCE_STAGE_IDS:
            expected_gate += ["--source-skill-root", "{source_skill_root}"]
        if stage.get("final_gate") != expected_gate:
            raise OrchestrationError(f"{stage_id}: final_gate interface mismatch")

        if stage_id == SCHEDULER_STAGE_ID:
            if "source_skill" in stage or stage.get("output_skill") is not None:
                raise OrchestrationError("P12 must have neither source_skill nor output_skill")
            if stage.get("runtime_outputs") != EXPECTED_RUNTIME_OUTPUTS or stage.get("runtime_branches") != EXPECTED_RUNTIME_BRANCHES:
                raise OrchestrationError("P12 runtime contract mismatch")
            expected_skills = [EXPECTED_RUNTIME_BINDINGS[f"R{i:02d}"]["skill"] for i in range(1, 11)]
            if stage.get("consumes_target_skills") != expected_skills:
                raise OrchestrationError("P12 must consume all ten target Skills")
            goal_text = perf_trace_path(project_root, goal).read_text(encoding="utf-8")
            markers = [*EXPECTED_RUNTIME_OUTPUTS, *expected_skills, "workflow01-05-full", "workflow05-existing-evidence", "ephemeral=false"]
            missing = [marker for marker in markers if marker not in goal_text]
            if missing:
                raise OrchestrationError(f"P12 Goal omits scheduler markers: {missing}")
            continue

        if stage_id in WORKFLOW_GAP_STAGE_IDS:
            if "source_skill" in stage:
                raise OrchestrationError(f"{stage_id}: gap Goal must not attach a source Skill")
            authority = stage.get("workflow_authority")
            if not isinstance(authority, dict) or set(authority) != {"path", "sha256", "scope"} or not authority["scope"].strip():
                raise OrchestrationError(f"{stage_id}: malformed Workflow authority")
            authority_path = perf_trace_path(project_root, authority["path"])
            if sha256_file(authority_path) != authority["sha256"]:
                raise OrchestrationError(f"{stage_id}: Workflow authority changed")
            evidence = stage.get("binding_evidence")
            if not isinstance(evidence, list) or not evidence:
                raise OrchestrationError(f"{stage_id}: binding_evidence is empty")
            evidence_seen: set[str] = set()
            for record in evidence:
                if not isinstance(record, dict) or set(record) != {"path", "sha256", "role"}:
                    raise OrchestrationError(f"{stage_id}: malformed binding evidence")
                if record["path"] in evidence_seen:
                    raise OrchestrationError(f"{stage_id}: duplicate binding evidence")
                evidence_seen.add(record["path"])
                path = project_path(project_root, record["path"])
                if not path.is_file() or sha256_file(path) != record["sha256"]:
                    raise OrchestrationError(f"{stage_id}: binding evidence changed: {record['path']}")
            output = stage.get("output_skill")
            if not isinstance(output, dict) or output.get("file_set") != ["SKILL.md", "agents/openai.yaml"]:
                raise OrchestrationError(f"{stage_id}: gap Skill must declare the exact two-file set")
            if output.get("name") in output_names:
                raise OrchestrationError(f"{stage_id}: duplicate output Skill")
            output_names.add(output["name"])
            output_path = perf_trace_path(project_root, output["path"])
            try:
                output_path.relative_to(perf_trace_path(project_root, plan["target_skill_root"]))
            except ValueError as exc:
                raise OrchestrationError(f"{stage_id}: output Skill escapes target root") from exc
            if stage_id == "P05":
                if authority["path"] != "perf_trace/workflows/03_process_gpu_hardware_trace.md":
                    raise OrchestrationError("P05 must retain Workflow 03 authority")
            else:
                if authority["path"] != "perf_trace/workflows/05_workflow04_guided_selective_process_trace_and_resource_gap_analysis.md":
                    raise OrchestrationError(f"{stage_id}: must use Workflow 05 authority")
                unresolved = stage.get("unresolved_bindings")
                boundaries = stage.get("boundary_skills")
                if not isinstance(unresolved, list) or not unresolved or not all(isinstance(item, str) and item.strip() for item in unresolved):
                    raise OrchestrationError(f"{stage_id}: unresolved_bindings must be explicit")
                if not isinstance(boundaries, list) or not boundaries:
                    raise OrchestrationError(f"{stage_id}: boundary_skills must be explicit")
                for field in ("required_sections", "required_markers"):
                    if not isinstance(stage.get(field), list) or not stage[field]:
                        raise OrchestrationError(f"{stage_id}: missing {field}")
            goal_text = perf_trace_path(project_root, goal).read_text(encoding="utf-8")
            for marker in (output["name"], authority["path"], stage["handoff"]):
                if marker not in goal_text:
                    raise OrchestrationError(f"{stage_id}: Goal template omits {marker}")
            continue

        source = stage.get("source_skill")
        output = stage.get("output_skill")
        if not isinstance(source, dict) or not isinstance(output, dict):
            raise OrchestrationError(f"{stage_id}: source/output Skill contract is missing")
        name = source.get("name")
        if not isinstance(name, str) or name in source_names or source.get("scope") != "full":
            raise OrchestrationError(f"{stage_id}: invalid source Skill identity/scope")
        source_names.add(name)
        source_root = Path(source.get("path", "")).resolve()
        if not source_root.is_dir() or tree_digest(source_root) != source.get("sha256"):
            raise OrchestrationError(f"{stage_id}: source Skill is missing or changed")
        if source.get("file_set") != relative_file_set(source_root):
            raise OrchestrationError(f"{stage_id}: source Skill file_set mismatch")
        output_name = output.get("name")
        if not isinstance(output_name, str) or output_name in output_names:
            raise OrchestrationError(f"{stage_id}: duplicate or invalid output Skill")
        output_names.add(output_name)
        perf_trace_path(project_root, output["path"])

    expected_output_names = {binding["skill"] for binding in EXPECTED_RUNTIME_BINDINGS.values()}
    if output_names != expected_output_names:
        raise OrchestrationError("Skill-producing stages do not match runtime bindings")

    extra_skill_roots = plan.get("extra_skill_roots", [])
    if not isinstance(extra_skill_roots, list) or not extra_skill_roots:
        raise OrchestrationError("extra_skill_roots must be a nonempty list")
    for value in extra_skill_roots:
        if not isinstance(value, str):
            raise OrchestrationError("extra_skill_roots entries must be strings")
        project_path(project_root, value)
    if plan_path != plan_path.resolve():
        raise OrchestrationError("plan path must resolve to an absolute path")

def contract_file_hashes(
    plan: dict[str, Any],
    project_root: Path,
    plan_path: Path,
) -> dict[str, str]:
    paths = {plan_path.resolve()}
    adaptation_root = perf_trace_path(project_root, ADAPTATION_RELATIVE_ROOT)
    for relative in plan.get("control_plane_files", []):
        paths.add((adaptation_root / relative).resolve())
    for key in (
        "workflow_contract",
        "implementation_plan",
        "common_goal_contract",
        "runner",
        "verifier",
    ):
        paths.add(perf_trace_path(project_root, plan[key]))
    for stage in plan["stages"]:
        paths.add(perf_trace_path(project_root, stage["goal_template"]))
        for value in stage.get("workflow_requirements", []):
            paths.add(perf_trace_path(project_root, value))
        authority = stage.get("workflow_authority")
        if isinstance(authority, dict):
            paths.add(perf_trace_path(project_root, authority["path"]))
        for record in stage.get("binding_evidence", []):
            paths.add(project_path(project_root, record["path"]))
    for record in plan.get("target_project_evidence", []):
        paths.add(project_path(project_root, record["path"]))
    for record in plan.get("predecessor_runtime_products", []):
        paths.add(project_path(project_root, record["path"]))
    for record in plan.get("predecessor_skill_handoffs", []):
        paths.add(perf_trace_path(project_root, record["path"]))

    result: dict[str, str] = {}
    for path in sorted(paths):
        try:
            key = path.relative_to(project_root).as_posix()
        except ValueError:
            key = str(path)
        result[key] = sha256_file(path)
    for stage in plan["stages"]:
        source = stage.get("source_skill")
        if isinstance(source, dict):
            result[f"source-skill-tree:{source['path']}"] = tree_digest(
                Path(source["path"]).resolve()
            )
    for skill in plan.get("precommitted_upstream_skills", []):
        result[f"upstream-skill-tree:{skill['path']}"] = tree_digest(
            project_path(project_root, skill["path"])
        )
    reference = plan.get("reference_runner", {})
    if isinstance(reference, dict) and isinstance(reference.get("path"), str):
        reference_path = Path(reference["path"]).resolve()
        result[f"reference-runner:{reference_path}"] = sha256_file(reference_path)
    return result

def contract_digest(hashes: dict[str, str]) -> str:
    canonical = json.dumps(
        hashes,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(canonical)


class AppServerClient:
    """Thread-safe JSONL client for one Codex app-server process."""

    def __init__(
        self,
        codex_bin: Path,
        cwd: Path,
        raw_log_path: Path,
        stderr_log_path: Path,
        request_timeout: float,
    ) -> None:
        self.codex_bin = codex_bin
        self.cwd = cwd
        self.raw_log_path = raw_log_path
        self.stderr_log_path = stderr_log_path
        self.request_timeout = request_timeout
        self.process: subprocess.Popen[str] | None = None
        self.notifications: queue.Queue[dict[str, Any]] = queue.Queue()
        self.server_requests: queue.Queue[dict[str, Any]] = queue.Queue()
        self.reader_errors: queue.Queue[str] = queue.Queue()
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._next_id = 1
        self._raw_log = None
        self._stderr_log = None
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        self.raw_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.stderr_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._raw_log = self.raw_log_path.open("a", encoding="utf-8")
        self._stderr_log = self.stderr_log_path.open("a", encoding="utf-8")
        self.process = subprocess.Popen(
            [str(self.codex_bin), "app-server", "--listen", "stdio://"],
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            # Keep terminal SIGINT on the orchestrator so it can pause the
            # authoritative Goal before closing the app-server.
            start_new_session=True,
        )
        stdout_thread = threading.Thread(
            target=self._read_stdout,
            name="codex-app-server-stdout",
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._read_stderr,
            name="codex-app-server-stderr",
            daemon=True,
        )
        self._threads = [stdout_thread, stderr_thread]
        for thread in self._threads:
            thread.start()

    def _log(self, direction: str, message: Any) -> None:
        if self._raw_log is None:
            return
        record = {
            "observed_at": utc_now(),
            "direction": direction,
            "message": message,
        }
        with self._log_lock:
            self._raw_log.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._raw_log.flush()

    def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        for line in self.process.stdout:
            stripped = line.rstrip("\n")
            try:
                message = json.loads(stripped)
            except json.JSONDecodeError as exc:
                self._log("server-invalid-json", stripped)
                self.reader_errors.put(f"invalid app-server JSON: {exc}: {stripped}")
                continue
            self._log("server", message)
            if not isinstance(message, dict):
                self.reader_errors.put(f"app-server message is not an object: {message!r}")
                continue
            if "id" in message and ("result" in message or "error" in message):
                with self._pending_lock:
                    waiter = self._pending.get(message["id"])
                if waiter is not None:
                    waiter.put(message)
                else:
                    self.reader_errors.put(
                        f"response for unknown request id {message.get('id')}"
                    )
            elif "id" in message and "method" in message:
                self.server_requests.put(message)
                self._reject_server_request(message)
            else:
                self.notifications.put(message)
        if self.process.poll() not in (None, 0):
            self.reader_errors.put(
                f"app-server stdout closed with exit code {self.process.returncode}"
            )

    def _read_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        for line in self.process.stderr:
            if self._stderr_log is not None:
                self._stderr_log.write(f"{utc_now()} {line}")
                self._stderr_log.flush()

    def _write(self, message: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise RpcError("app-server is not running")
        if self.process.poll() is not None:
            raise RpcError(f"app-server exited with code {self.process.returncode}")
        encoded = json.dumps(message, ensure_ascii=False)
        self._log("client", message)
        with self._write_lock:
            self.process.stdin.write(encoded + "\n")
            self.process.stdin.flush()

    def _reject_server_request(self, message: dict[str, Any]) -> None:
        response = {
            "id": message["id"],
            "error": {
                "code": -32000,
                "message": (
                    "Non-interactive adaptation orchestrator does not answer "
                    f"server request {message.get('method')}"
                ),
            },
        }
        try:
            self._write(response)
        except RpcError as exc:
            self.reader_errors.put(str(exc))

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        with self._pending_lock:
            request_id = self._next_id
            self._next_id += 1
            waiter: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self._pending[request_id] = waiter
        message: dict[str, Any] = {"method": method, "id": request_id}
        if params is not None:
            message["params"] = params
        self._write(message)
        try:
            response = waiter.get(timeout=timeout or self.request_timeout)
        except queue.Empty as exc:
            raise RpcError(f"timeout waiting for {method} response") from exc
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)
        if "error" in response:
            raise RpcError(f"{method} failed: {response['error']}")
        return response.get("result")

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = params
        self._write(message)

    def initialize(self) -> Any:
        result = self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "qwen_dcu_perf_trace_adapter",
                    "title": "Qwen DCU Perf Trace Adapter",
                    "version": "1.0.0",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        self.notify("initialized", {})
        return result

    def close(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            try:
                if process.stdin is not None:
                    process.stdin.close()
            except OSError:
                pass
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for thread in self._threads:
            thread.join(timeout=1)
        if self._raw_log is not None:
            self._raw_log.close()
        if self._stderr_log is not None:
            self._stderr_log.close()


class AdaptationOrchestrator:
    """Schedule the unified Workflow 01-05 Skill and scheduler stages."""

    def __init__(
        self,
        *,
        project_root: Path,
        plan_path: Path,
        plan: dict[str, Any],
        state_path: Path,
        codex_bin: Path,
        codex_version: str,
        model: str,
        effort: str,
        stage_timeout: float,
        request_timeout: float,
        sandbox_policy: str,
        network_access: bool,
        progress_interval: float,
        progress_enabled: bool,
        reactivate: bool = False,
        adopt_control_plane_repair: bool = False,
        adopt_workflow05_extension: bool = False,
    ) -> None:
        self.project_root = project_root
        self.perf_trace_root = perf_trace_root(project_root)
        self.plan_path = plan_path
        self.plan = plan
        self.state_path = state_path
        self.codex_bin = codex_bin
        self.codex_version = codex_version
        self.model = model
        self.effort = effort
        self.stage_timeout = stage_timeout
        self.request_timeout = request_timeout
        self.sandbox_policy = sandbox_policy
        self.network_access = network_access
        self.progress_interval = progress_interval
        self.progress_enabled = progress_enabled
        self.reactivate = reactivate
        self.adopt_control_plane_repair = adopt_control_plane_repair
        self.adopt_workflow05_extension = adopt_workflow05_extension
        self.plan_sha256 = sha256_file(plan_path)
        self.contract_files = contract_file_hashes(plan, project_root, plan_path)
        self.contract_sha256 = contract_digest(self.contract_files)
        self.state: dict[str, Any] = {}
        self.client: AppServerClient | None = None
        self.skill_paths: dict[str, Path] = {}
        self.stop_requested = False
        self.current_stage_id: str | None = None
        self._last_progress_emit = 0.0

    @property
    def stages(self) -> list[dict[str, Any]]:
        return self.plan["stages"]

    def _stage(self, stage_id: str) -> dict[str, Any]:
        return next(stage for stage in self.stages if stage["id"] == stage_id)

    def _record(self, stage_id: str) -> dict[str, Any]:
        return self.state["stages"][stage_id]

    def _emit_progress(
        self,
        *,
        force: bool = False,
        event: str | None = None,
    ) -> None:
        if not self.state:
            return
        now = time.monotonic()
        if not force and now - self._last_progress_emit < self.progress_interval:
            return
        snapshot = build_progress_snapshot(
            self.state,
            self.plan,
            self.project_root,
            self.state_path,
        )
        prefix = "[progress]"
        if event:
            prefix += f"[{event}]"
        summary = format_progress_compact(snapshot)
        if self.progress_enabled:
            print(
                f"{prefix} {summary}",
                file=sys.stderr,
                flush=True,
            )
        progress_log_value = self.state.get("progress_log")
        if isinstance(progress_log_value, str):
            try:
                progress_log = perf_trace_path(
                    self.project_root, progress_log_value
                )
                progress_log.parent.mkdir(parents=True, exist_ok=True)
                entry = {
                    "observed_at": snapshot["observed_at"],
                    "event": event,
                    "summary": summary,
                    "run_id": snapshot.get("run_id"),
                    "orchestration_status": snapshot.get(
                        "orchestration_status"
                    ),
                    "committed_stages": snapshot.get("committed_stages"),
                    "total_stages": snapshot.get("total_stages"),
                    "current_stage": current_progress_row(snapshot),
                }
                with progress_log.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(entry, ensure_ascii=False, sort_keys=True)
                        + "\n"
                    )
            except OSError as exc:
                if self.progress_enabled:
                    print(
                        f"[progress][warning] cannot append progress log: {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
        self._last_progress_emit = now

    def _checkpoint(self, *, emit_progress: bool = True) -> None:
        self.state["updated_at"] = utc_now()
        atomic_write_json(self.state_path, self.state)
        if emit_progress:
            self._emit_progress()

    def _transition(
        self,
        stage_id: str,
        status: str,
        *,
        phase: str | None = None,
        error: str | None = None,
    ) -> None:
        record = self._record(stage_id)
        record["status"] = status
        if phase is not None:
            record["phase"] = phase
        record["updated_at"] = utc_now()
        if error is not None:
            record["last_error"] = error
        elif status in {
            "THREAD_CREATED",
            "RUNNING",
            "VALIDATING",
            "FINAL_VALIDATING",
            "COMMITTED",
        }:
            record["last_error"] = None
        history = record.setdefault("history", [])
        history.append(
            {
                "at": utc_now(),
                "status": status,
                "phase": record.get("phase"),
                "error": error,
            }
        )
        self.state["current_stage"] = stage_id
        self._checkpoint(emit_progress=False)
        self._emit_progress(force=True, event=f"{stage_id}:{status}")

    def _create_initial_state(
        self,
        run_id: str,
        run_dir: Path,
        protocol_bundle: Path,
        protocol_sha256: str,
    ) -> None:
        self.state = {
            "schema_version": STATE_SCHEMA_VERSION,
            "orchestration_protocol": ORCHESTRATION_PROTOCOL,
            "run_id": run_id,
            "plan_id": self.plan["plan_id"],
            "plan_path": str(self.plan_path),
            "plan_sha256": self.plan_sha256,
            "contract_files": self.contract_files,
            "contract_sha256": self.contract_sha256,
            "project_root": str(self.project_root),
            "perf_trace_root": str(self.perf_trace_root),
            "codex_bin": str(self.codex_bin),
            "codex_version": self.codex_version,
            "protocol_schema": str(protocol_bundle),
            "protocol_schema_sha256": protocol_sha256,
            "model": self.model,
            "effort": self.effort,
            "goal_token_budget_policy": GOAL_TOKEN_BUDGET_POLICY,
            "sandbox_policy": self.sandbox_policy,
            "approval_policy": APPROVAL_POLICY,
            "network_access": self.network_access,
            "run_dir": str(run_dir),
            "raw_log": str(run_dir / "app_server.jsonl"),
            "stderr_log": str(run_dir / "app_server.stderr.log"),
            "progress_log": str(run_dir / "progress.jsonl"),
            "gate_report_dir": str(
                perf_trace_path(
                    self.project_root,
                    self.plan["gate_report_root"],
                )
                / run_id
            ),
            "status": "ACTIVE",
            "current_stage": None,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "source_skills": {},
            "stages": {
                stage["id"]: new_stage_state_record()
                for stage in self.stages
            },
        }
        self._checkpoint()

    def _start_client(self) -> None:
        run_dir = Path(self.state["run_dir"])
        self.client = AppServerClient(
            self.codex_bin,
            self.project_root,
            run_dir / "app_server.jsonl",
            run_dir / "app_server.stderr.log",
            self.request_timeout,
        )
        self.client.start()
        self.client.initialize()
        extra_roots = [
            str(project_path(self.project_root, value))
            for value in self.plan.get("extra_skill_roots", [])
            if project_path(self.project_root, value).is_dir()
        ]
        if extra_roots:
            self.client.request("skills/extraRoots/set", {"extraRoots": extra_roots})

    def _model_catalog(self) -> list[dict[str, Any]]:
        assert self.client is not None
        models: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"limit": 100, "includeHidden": True}
            if cursor:
                params["cursor"] = cursor
            result = self.client.request("model/list", params)
            models.extend(result.get("data", []))
            cursor = result.get("nextCursor")
            if not cursor:
                return models

    def _list_skills(self, force_reload: bool) -> dict[str, Path]:
        assert self.client is not None
        result = self.client.request(
            "skills/list",
            {"cwds": [str(self.project_root)], "forceReload": force_reload},
        )
        found: dict[str, Path] = {}
        errors: list[str] = []
        for entry in result.get("data", []):
            for item in entry.get("errors", []):
                errors.append(f"{item.get('path')}: {item.get('message')}")
            for skill in entry.get("skills", []):
                if not skill.get("enabled", True):
                    continue
                name = skill.get("name")
                path = skill.get("path")
                if isinstance(name, str) and isinstance(path, str) and name not in found:
                    found[name] = Path(path).resolve()
        if errors:
            raise OrchestrationError("skills/list reported errors: " + "; ".join(errors))
        return found

    def _doctor_rpc(self) -> dict[str, Any]:
        assert self.client is not None
        models = self._model_catalog()
        selected = next(
            (
                item
                for item in models
                if item.get("id") == self.model or item.get("model") == self.model
            ),
            None,
        )
        if selected is None:
            available = sorted(
                {
                    str(item.get("id") or item.get("model"))
                    for item in models
                    if item.get("id") or item.get("model")
                }
            )
            raise OrchestrationError(
                f"model/list does not expose {self.model}; available={available}"
            )
        efforts = {
            option.get("reasoningEffort")
            for option in selected.get("supportedReasoningEfforts", [])
            if isinstance(option, dict)
        }
        if self.effort not in efforts:
            raise OrchestrationError(
                f"model {self.model} does not advertise effort={self.effort}; "
                f"supported={sorted(value for value in efforts if value)}"
            )
        account = self.client.request("account/read", {"refreshToken": False})
        if account.get("requiresOpenaiAuth") and account.get("account") is None:
            raise OrchestrationError("Codex account authentication is required")
        self.skill_paths = self._list_skills(force_reload=True)
        required = {
            stage["source_skill"]["name"]
            for stage in self.stages
            if isinstance(stage.get("source_skill"), dict)
        }
        missing = sorted(required - self.skill_paths.keys())
        if missing:
            raise OrchestrationError(f"required Skills are not discoverable: {missing}")
        for stage in self.stages:
            source = stage.get("source_skill")
            if not isinstance(source, dict):
                continue
            name = source["name"]
            expected_root = Path(source["path"]).resolve()
            discovered_skill_md = self.skill_paths[name].resolve()
            expected_skill_md = expected_root / "SKILL.md"
            if discovered_skill_md != expected_skill_md:
                raise OrchestrationError(
                    f"{stage['id']}: discovered source Skill path differs from "
                    f"manifest: actual={discovered_skill_md} "
                    f"expected={expected_skill_md}"
                )
            actual_hash = tree_digest(expected_root)
            if actual_hash != source["sha256"]:
                raise OrchestrationError(
                    f"{stage['id']}: discovered source Skill hash differs from "
                    f"manifest: actual={actual_hash} expected={source['sha256']}"
                )
        return {
            "model": selected.get("id") or selected.get("model"),
            "supported_efforts": sorted(value for value in efforts if value),
            "account_type": (
                account.get("account", {}).get("type")
                if isinstance(account.get("account"), dict)
                else None
            ),
            "skills": {name: str(self.skill_paths[name]) for name in sorted(required)},
        }

    def _capture_source_hashes(self) -> None:
        sources = sorted(
            {
                stage["source_skill"]["name"]
                for stage in self.stages
                if isinstance(stage.get("source_skill"), dict)
            }
        )
        captured: dict[str, Any] = {}
        for name in sources:
            skill_md = self.skill_paths[name]
            skill_root = skill_md.parent
            stage = next(
                item
                for item in self.stages
                if isinstance(item.get("source_skill"), dict)
                and item["source_skill"]["name"] == name
            )
            declared_root = Path(stage["source_skill"]["path"]).resolve()
            if skill_root.resolve() != declared_root:
                raise OrchestrationError(
                    f"source Skill root changed before adaptation: {name} "
                    f"declared={declared_root} discovered={skill_root}"
                )
            actual_hash = tree_digest(skill_root)
            if actual_hash != stage["source_skill"]["sha256"]:
                raise OrchestrationError(
                    f"source Skill hash changed before adaptation: {name} "
                    f"declared={stage['source_skill']['sha256']} "
                    f"actual={actual_hash}"
                )
            captured[name] = {
                "skill_md": str(skill_md),
                "root": str(skill_root),
                "sha256": actual_hash,
            }
        self.state["source_skills"] = captured
        self._checkpoint()

    def _verify_source_hashes(self) -> None:
        for name, expected in self.state.get("source_skills", {}).items():
            root = Path(expected["root"])
            actual = tree_digest(root)
            if actual != expected["sha256"]:
                raise OrchestrationError(
                    f"source Skill changed during adaptation: {name} "
                    f"expected={expected['sha256']} actual={actual}"
                )

    def _verify_contract_hashes(self) -> None:
        actual = contract_file_hashes(
            self.plan,
            self.project_root,
            self.plan_path,
        )
        if actual != self.contract_files:
            changed = sorted(
                key
                for key in set(actual) | set(self.contract_files)
                if actual.get(key) != self.contract_files.get(key)
            )
            raise OrchestrationError(
                "adaptation contract changed during the run: "
                + ", ".join(changed)
            )

    def _thread_start_params(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "cwd": str(self.project_root),
            "approvalPolicy": APPROVAL_POLICY,
            "sandbox": self.sandbox_policy,
            "ephemeral": False,
            "developerInstructions": (
                "Execute exactly one source-Skill text-alignment, Workflow-gap "
                "Skill-generation, or final scheduler-generation stage from the "
                "unified Workflow 01-05 adaptation plan. For P01-P04, the attached "
                "complete source Skill is the sole normative capability authority; "
                "preserve its exact file set, methods, ordering, I/O, evidence, "
                "validation, failures, stops, and completion conditions, and align "
                "only verified Qwen3.5-27B, pra2026-bh408, vLLM/PRA and ROCm/DCU/HIP "
                "bindings. For P05 and P07-P11, attach no source Skill: use only the "
                "manifest-pinned Workflow scope as capability authority and only "
                "that stage's pinned binding evidence for concrete paths, tools, "
                "schemas and hardware bindings. Adjacent Skills are interface "
                "boundaries only. Preserve every unresolved binding as runtime "
                "discovery; do not omit, guess or weaken a capability. For P12, "
                "consume all ten committed target Skills and generate the declared "
                "Workflow 01-05 runtime runner and two Skill-only manifests without "
                "modifying Skills or historical P06 products. No capability may be "
                "ignored, unsupported or unscheduled. Do not run a model, GPU, "
                "profiler, PMC, formal Workflow, dashboard, optimization experiment, "
                "or non-dry-run generated scheduler. Do not spawn or manage agents, "
                "Codex processes, threads, or Goals. Do not edit canonical state, "
                "the adaptation manifest, runner, verifier, another stage, a source "
                "Skill, a committed upstream Skill, or historical P06 products. "
                "Manage only this Goal's internal continuation and completion; leave "
                "serial order, external gates and commit decisions to the runner."
            ),
        }

    def _turn_overrides(self) -> dict[str, Any]:
        if self.sandbox_policy == "danger-full-access":
            sandbox: dict[str, Any] = {"type": "dangerFullAccess"}
        else:
            sandbox = {
                "type": "workspaceWrite",
                "writableRoots": [str(self.project_root)],
                "networkAccess": self.network_access,
            }
        return {
            "cwd": str(self.project_root),
            "approvalPolicy": APPROVAL_POLICY,
            "sandboxPolicy": sandbox,
            "model": self.model,
            "effort": self.effort,
            "summary": "concise",
        }

    def _skill_input_items(self, names: Iterable[str]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for name in names:
            path = self.skill_paths.get(name)
            if path is None:
                raise OrchestrationError(f"Skill is not resolved: {name}")
            items.append({"type": "skill", "name": name, "path": str(path)})
        return items

    def _goal_input(self, stage: dict[str, Any]) -> list[dict[str, Any]]:
        stage_id = stage["id"]
        dependencies = [
            {
                "stage": dependency,
                "artifact_dir": self._stage(dependency)["artifact_dir"],
                "handoff": self._stage(dependency)["handoff"],
            }
            for dependency in stage.get("depends_on", [])
        ]
        output_skill = stage.get("output_skill")
        source_skill = stage.get("source_skill")
        lines = [
            f"你现在只执行完整的产出阶段 Goal {stage_id}。",
            f"当前项目根目录：{self.project_root}",
            f"统一适配总合同：{self.plan['workflow_contract']}",
            f"通用 Goal 合同：{self.plan['common_goal_contract']}",
            f"当前 Goal 模板：{stage['goal_template']}",
            "Workflow 需求：",
            *[f"- {path}" for path in stage.get("workflow_requirements", [])],
            "合法已提交前序：",
            json.dumps(dependencies, ensure_ascii=False, indent=2),
        ]
        if isinstance(source_skill, dict) and isinstance(output_skill, dict):
            source_name = source_skill["name"]
            source_path = self.skill_paths[source_name].parent
            lines.extend(
                [
                    f"唯一源 Skill：{source_name}",
                    f"源 Skill 根目录：{source_path}",
                    f"源目录固定 hash：{source_skill['sha256']}",
                    "源相对文件集合：" + json.dumps(source_skill["file_set"], ensure_ascii=False),
                    f"迁移能力范围：{source_skill['scope']}",
                    f"目标 Skill：{output_skill['name']}",
                    f"目标 Skill 路径：{output_skill['path']}",
                    f"适配 handoff：{stage['handoff']}",
                    "完整源 Skill 是唯一能力约束；Workflow 只定义角色、依赖和 handoff。",
                    "精确镜像源相对文件集合，最大复用原文，只对齐有证据的当前项目文本绑定。",
                    "未知工具、路径或 schema 必须推迟到 runtime discovery，不得猜测或削弱约束。",
                    "不得运行正式 Workflow；只生成目标 Skill 与最小 handoff。",
                    "不要只输出计划；直接完成当前源 Skill 对齐。",
                ]
            )
            skill_names = [source_name]
        elif stage_id in WORKFLOW_GAP_STAGE_IDS:
            if not isinstance(output_skill, dict):
                raise OrchestrationError(f"{stage_id}: output Skill contract is missing")
            authority = stage["workflow_authority"]
            evidence = stage["binding_evidence"]
            boundaries = stage.get("boundary_skills", [])
            unresolved = stage.get("unresolved_bindings", [])
            dependency_skills = [
                self._stage(dependency).get("output_skill")
                for dependency in stage["depends_on"]
                if isinstance(self._stage(dependency).get("output_skill"), dict)
            ]
            lines.extend(
                [
                    f"{stage_id} 没有可附加的规范源 Skill；该 capability 必须生成独立 Workflow-gap Skill，不能忽略或标记为未调度。",
                    f"唯一能力权威 Workflow：{authority['path']}",
                    f"唯一能力权威范围：{authority['scope']}",
                    f"能力权威固定 hash：{authority['sha256']}",
                    "具体实现绑定证据（固定文件、固定 hash，只读）：",
                    json.dumps(evidence, ensure_ascii=False, indent=2),
                    "明确未解析绑定（必须保留为 runtime discovery）：",
                    json.dumps(unresolved, ensure_ascii=False, indent=2),
                    "边界 Skills（只定义接口/所有权，不是能力权威）：",
                    json.dumps(boundaries, ensure_ascii=False, indent=2),
                    "已提交依赖 Skill 输出（只作接口边界）：",
                    json.dumps(dependency_skills, ensure_ascii=False, indent=2),
                    f"目标 Skill：{output_skill['name']}",
                    f"目标 Skill 路径：{output_skill['path']}",
                    "目标相对文件集合：" + json.dumps(output_skill["file_set"], ensure_ascii=False),
                    f"最小 handoff：{stage['handoff']}",
                    "完整保留当前 authority scope 的方法、顺序、I/O、证据边界、validation、failure、stop、escalation 和 completion 条件。",
                    "具体命令、路径、schema 和硬件字段只能来自本阶段 binding evidence；未证实项不得猜测。",
                    "不得执行 Workflow、profiling、PMC、dashboard 或优化实验；不得把归档证据冒充本轮测量。",
                    f"不要只输出计划；直接完成 {stage_id} Workflow-gap Skill。",
                ]
            )
            skill_names = []
        elif stage_id == SCHEDULER_STAGE_ID:
            skill_names = list(stage["consumes_target_skills"])
            output_paths_by_name = {
                dependency_stage["output_skill"]["name"]: dependency_stage["output_skill"]["path"]
                for dependency_stage in self.stages
                if isinstance(dependency_stage.get("output_skill"), dict)
            }
            for name in skill_names:
                path_value = output_paths_by_name.get(name)
                if not isinstance(path_value, str):
                    raise OrchestrationError(f"P12 has no producing stage for {name}")
                skill_md = perf_trace_path(self.project_root, path_value) / "SKILL.md"
                if not skill_md.is_file():
                    raise OrchestrationError(f"P12 committed target Skill is missing: {skill_md}")
                self.skill_paths[name] = skill_md
            lines.extend(
                [
                    f"P12 handoff：{stage['handoff']}",
                    "P12 不是 Skill 适配。它消费十个 committed target Skills，只生成统一 Workflow 01-05 runtime Goal runner 与两个 Skill-only manifests。",
                    "运行时输出：",
                    *[f"- {path}" for path in stage["runtime_outputs"]],
                    "运行时分支合同：",
                    json.dumps(stage["runtime_branches"], ensure_ascii=False, indent=2),
                    "完整分支必须严格执行 R01 到 R10；existing-evidence 分支必须要求用户提供兼容的 R01-R05 cumulative handoff ledger 后才执行 R06 到 R10。",
                    "每个 runtime Goal prompt 只能组合其 target Skill、用户参数和累计前序 runtime handoff ledger；使用 non-ephemeral thread，只有 complete 才继续。",
                    "不得修改任何 Skill、历史 P06 handoff/gate、run_perf_trace.py 或 core_attribution_pipeline.json。",
                    "只执行 Python AST、--help 和两个分支的 --dry-run；不得执行非 dry-run runtime。",
                    "不要只输出计划；直接完成 P12 scheduler generation。",
                ]
            )
        else:
            raise OrchestrationError(f"{stage_id}: unsupported stage contract for Goal input")
        lines.append("不得启动后继 Goal，不得修改 canonical state 或其他 stage 产物。")
        mention = " ".join(f"${name}" for name in skill_names)
        payload = (mention + "\n\n" if mention else "") + "\n".join(lines)
        return [
            {"type": "text", "text": payload},
            *self._skill_input_items(skill_names),
        ]

    def _start_initial_turn(
        self,
        stage_id: str,
        input_items: list[dict[str, Any]],
    ) -> str:
        assert self.client is not None
        record = self._record(stage_id)
        params = {
            "threadId": record["thread_id"],
            "input": input_items,
            **self._turn_overrides(),
        }
        result = self.client.request("turn/start", params)
        turn_id = result.get("turn", {}).get("id")
        if not isinstance(turn_id, str):
            raise OrchestrationError(f"{stage_id}: turn/start returned no Turn id")
        requested = record.setdefault("requested_turn_ids", [])
        if turn_id not in requested:
            requested.append(turn_id)
        record["initial_turn_id"] = turn_id
        self._transition(stage_id, "RUNNING", phase="RUNNING")
        self._wait_for_turn_observation(stage_id, turn_id)
        return turn_id

    def _get_goal(self, thread_id: str) -> dict[str, Any] | None:
        assert self.client is not None
        result = self.client.request("thread/goal/get", {"threadId": thread_id})
        goal = result.get("goal")
        return goal if isinstance(goal, dict) else None

    def _set_goal_status(
        self,
        stage_id: str,
        status: str,
    ) -> dict[str, Any] | None:
        assert self.client is not None
        record = self._record(stage_id)
        result = self.client.request(
            "thread/goal/set",
            {"threadId": record["thread_id"], "status": status},
        )
        goal = result.get("goal")
        if isinstance(goal, dict):
            record["goal"] = goal
            self._checkpoint()
            return goal
        return None

    def _get_thread(self, thread_id: str, include_turns: bool) -> dict[str, Any]:
        assert self.client is not None
        result = self.client.request(
            "thread/read",
            {"threadId": thread_id, "includeTurns": include_turns},
        )
        thread = result.get("thread")
        if not isinstance(thread, dict):
            raise OrchestrationError(f"thread/read returned no thread for {thread_id}")
        return thread

    @staticmethod
    def _thread_status_type(thread: dict[str, Any]) -> str | None:
        status = thread.get("status")
        if isinstance(status, dict):
            value = status.get("type")
            return value if isinstance(value, str) else None
        return status if isinstance(status, str) else None

    def _reconcile_thread(self, stage_id: str) -> dict[str, Any]:
        """Refresh display/diagnostic Turn state from authoritative thread/read."""
        record = self._record(stage_id)
        thread = self._get_thread(record["thread_id"], include_turns=True)
        turn_ids: list[str] = []
        active_turn_ids: list[str] = []
        for turn in thread.get("turns", []):
            if not isinstance(turn, dict):
                continue
            turn_id = turn.get("id")
            if not isinstance(turn_id, str):
                continue
            turn_ids.append(turn_id)
            if turn.get("status") == "inProgress":
                active_turn_ids.append(turn_id)
        record["turn_ids"] = turn_ids
        record["active_turn_ids"] = active_turn_ids
        record["thread_status"] = thread.get("status")
        initial_turn_id = record.get("initial_turn_id")
        if turn_ids and initial_turn_id not in turn_ids:
            if isinstance(initial_turn_id, str):
                record["legacy_unobserved_turn_response_id"] = initial_turn_id
            record["initial_turn_id"] = turn_ids[0]
        self._checkpoint()
        return thread

    def _wait_for_turn_observation(
        self,
        stage_id: str,
        turn_id: str,
        timeout: float = 30.0,
    ) -> None:
        """Confirm that the explicit initial Turn exists before activating Goal."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._drain_event(stage_id, timeout=0.1)
            thread = self._reconcile_thread(stage_id)
            for turn in thread.get("turns", []):
                if not isinstance(turn, dict) or turn.get("id") != turn_id:
                    continue
                status = turn.get("status")
                if status in {"failed", "interrupted"}:
                    self._transition(
                        stage_id,
                        "TURN_FAILED",
                        error=f"Initial Turn {turn_id} ended with {status}",
                    )
                    raise OrchestrationError(
                        f"{stage_id}: initial Turn {turn_id} ended with {status}"
                    )
                return
            if self._thread_status_type(thread) == "idle":
                time.sleep(0.1)
        raise OrchestrationError(
            f"{stage_id}: initial Turn {turn_id} was not observable via thread/read"
        )

    def _capture_item_activity(
        self,
        stage_id: str,
        method: str,
        params: dict[str, Any],
    ) -> None:
        record = self._record(stage_id)
        item = params.get("item")
        if not isinstance(item, dict):
            return
        item_type = str(item.get("type") or "unknown")
        item_status = item.get("status")
        activity = {
            "at": utc_now(),
            "method": method,
            "item_id": item.get("id"),
            "item_type": item_type,
            "item_status": item_status,
        }
        state_word = "started" if method == "item/started" else "completed"
        summary = f"{item_type} {state_word}"
        if item_type == "agentMessage":
            message = compact_output(
                item.get("text") or item.get("content"),
                limit=1000,
            )
            if message:
                record["last_agent_message"] = message
                summary = f"agent message: {compact_output(message, limit=160)}"
        elif item_type == "commandExecution":
            command = compact_output(item.get("command"), limit=1000)
            output = compact_output(
                item.get("aggregatedOutput") or item.get("output"),
                limit=1000,
            )
            if command:
                record["last_command"] = command
                summary = (
                    f"command {state_word}: "
                    f"{compact_output(command, limit=160)}"
                )
            if output:
                record["last_command_output"] = output
            activity["exit_code"] = item.get("exitCode")
        elif item_type == "fileChange":
            changes = item.get("changes")
            count = len(changes) if isinstance(changes, list) else None
            summary = (
                f"file change {state_word}"
                + (f" ({count} changes)" if count is not None else "")
            )
        elif item_type == "mcpToolCall":
            tool = compact_output(
                item.get("tool") or item.get("name"),
                limit=160,
            )
            summary = f"MCP tool {state_word}" + (f": {tool}" if tool else "")
        activity["summary"] = summary
        record["last_activity"] = activity
        if method == "item/completed":
            counts = record.setdefault("activity_counts", {})
            counts[item_type] = int(counts.get(item_type, 0)) + 1
        self._checkpoint()

    def _drain_event(self, stage_id: str, timeout: float) -> dict[str, Any] | None:
        assert self.client is not None
        if not self.client.reader_errors.empty():
            raise OrchestrationError(self.client.reader_errors.get_nowait())
        if not self.client.server_requests.empty():
            request = self.client.server_requests.get_nowait()
            method = request.get("method")
            self._transition(
                stage_id,
                "WAITING_USER",
                error=f"non-interactive server request rejected: {method}",
            )
            raise OrchestrationError(
                f"{stage_id}: app-server requested interactive action {method}"
            )
        try:
            message = self.client.notifications.get(timeout=timeout)
        except queue.Empty:
            return None
        method = message.get("method")
        params = message.get("params", {})
        record = self._record(stage_id)
        if params.get("threadId") not in (None, record.get("thread_id")):
            return message
        if method in {"item/started", "item/completed"}:
            self._capture_item_activity(stage_id, method, params)
        elif method == "turn/started":
            turn_id = params.get("turn", {}).get("id")
            if isinstance(turn_id, str):
                active = set(record.get("active_turn_ids", []))
                active.add(turn_id)
                record["active_turn_ids"] = sorted(active)
                if turn_id not in record.setdefault("turn_ids", []):
                    record["turn_ids"].append(turn_id)
                self._checkpoint()
        elif method == "turn/completed":
            turn = params.get("turn", {})
            turn_id = turn.get("id")
            active = set(record.get("active_turn_ids", []))
            active.discard(turn_id)
            record["active_turn_ids"] = sorted(active)
            record["last_turn"] = {
                "id": turn_id,
                "status": turn.get("status"),
                "error": turn.get("error"),
            }
            self._checkpoint()
            expected_interrupts = set(record.get("expected_interrupt_ids", []))
            expected_interruption = (
                turn.get("status") == "interrupted" and turn_id in expected_interrupts
            )
            if expected_interruption:
                expected_interrupts.discard(turn_id)
                record["expected_interrupt_ids"] = sorted(expected_interrupts)
                self._checkpoint()
            elif turn.get("status") in {"failed", "interrupted"}:
                self._transition(
                    stage_id,
                    "TURN_FAILED",
                    error=f"Turn {turn_id} ended with {turn.get('status')}",
                )
                raise OrchestrationError(
                    f"{stage_id}: Turn {turn_id} ended with {turn.get('status')}"
                )
        elif method == "thread/goal/updated":
            goal = params.get("goal")
            if isinstance(goal, dict):
                record["goal"] = goal
                self._checkpoint()
        elif method == "thread/status/changed":
            record["thread_status"] = params.get("status")
            self._checkpoint()
        return message

    def _interrupt_in_progress(self, stage_id: str) -> None:
        assert self.client is not None
        record = self._record(stage_id)
        thread_id = record["thread_id"]
        thread = self._reconcile_thread(stage_id)
        active_ids: set[str] = set()
        for turn in thread.get("turns", []):
            if isinstance(turn, dict) and turn.get("status") == "inProgress":
                turn_id = turn.get("id")
                if isinstance(turn_id, str):
                    active_ids.add(turn_id)
        for turn_id in sorted(active_ids):
            expected = set(record.get("expected_interrupt_ids", []))
            expected.add(turn_id)
            record["expected_interrupt_ids"] = sorted(expected)
            self._checkpoint()
            try:
                self.client.request(
                    "turn/interrupt",
                    {"threadId": thread_id, "turnId": turn_id},
                    timeout=30,
                )
            except RpcError:
                continue
        record["active_turn_ids"] = []
        self._checkpoint()

    def _wait_until_idle(self, stage_id: str, timeout: float = 60) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._drain_event(stage_id, timeout=0.2)
            thread = self._reconcile_thread(stage_id)
            status = self._thread_status_type(thread)
            if status == "idle" and not self._record(stage_id).get(
                "active_turn_ids"
            ):
                while self._drain_event(stage_id, timeout=0.0) is not None:
                    pass
                self._reconcile_thread(stage_id)
                return
            time.sleep(0.2)
        raise OrchestrationError(f"{stage_id}: thread did not become idle")

    def _run_gate(
        self,
        stage: dict[str, Any],
        phase: str,
    ) -> bool:
        stage_id = stage["id"]
        command_template = stage[f"{phase}_gate"]
        replacements = {
            "project_root": str(self.project_root),
            "plan_path": str(self.plan_path),
            "stage_id": stage_id,
            "source_skill_root": "",
        }
        source_skill = stage.get("source_skill")
        if isinstance(source_skill, dict):
            source_name = source_skill["name"]
            source_skill_md = self.skill_paths.get(source_name)
            if source_skill_md is None:
                raise OrchestrationError(
                    f"{stage_id}: source Skill is not resolved: {source_name}"
                )
            replacements["source_skill_root"] = str(source_skill_md.parent)
        command = [
            str(part).format_map(replacements) for part in command_template
        ]
        if self.stop_requested:
            self._transition(
                stage_id,
                "PAUSED",
                phase=phase.upper(),
                error=f"operator interruption before {phase} gate",
            )
            raise OrchestrationError(
                f"{stage_id}: interrupted before {phase} gate"
            )
        started_at = utc_now()
        process = subprocess.Popen(
            command,
            cwd=self.project_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            # Let the orchestrator classify and checkpoint operator
            # interruption instead of allowing the gate child to die first.
            start_new_session=True,
        )
        deadline = time.monotonic() + 900
        interrupted = False
        timed_out = False
        stdout = ""
        stderr = ""
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                self._emit_progress()
                if self.stop_requested:
                    interrupted = True
                elif time.monotonic() >= deadline:
                    timed_out = True
                else:
                    continue
                if process.poll() is None:
                    process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                break
        if interrupted:
            gate_status = "interrupted"
        elif timed_out:
            gate_status = "timeout"
        else:
            gate_status = "pass" if process.returncode == 0 else "fail"
        report = {
            "stage_id": stage_id,
            "phase": phase,
            "command": command,
            "started_at": started_at,
            "completed_at": utc_now(),
            "returncode": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "status": gate_status,
        }
        gate_dir = Path(self.state["gate_report_dir"])
        gate_dir.mkdir(parents=True, exist_ok=True)
        record = self._record(stage_id)
        history = record.setdefault("gate_history", [])
        attempt = 1 + sum(
            1 for item in history if item.get("phase") == phase
        )
        gate_path = gate_dir / f"{stage_id}_{phase}_{attempt:03d}.json"
        atomic_write_json(gate_path, report)
        record[f"{phase}_gate"] = {
            "status": report["status"],
            "report": str(gate_path),
        }
        history.append(
            {
                "phase": phase,
                "attempt": attempt,
                "status": report["status"],
                "report": str(gate_path),
            }
        )
        self._checkpoint()
        if interrupted:
            self._transition(
                stage_id,
                "PAUSED",
                phase=phase.upper(),
                error=f"operator interrupted {phase} gate",
            )
            raise OrchestrationError(
                f"{stage_id}: operator interrupted {phase} gate"
            )
        if timed_out:
            self._transition(
                stage_id,
                "TIMED_OUT",
                phase=phase.upper(),
                error=f"{phase} gate exceeded 900 seconds",
            )
            raise OrchestrationError(f"{stage_id}: {phase} gate timed out")
        return process.returncode == 0

    def _reload_output_skill(self, stage: dict[str, Any]) -> Path:
        """Confirm the source-aligned or gap-generated Skill is discoverable."""
        assert self.client is not None
        stage_id = stage["id"]
        extra_roots = [
            str(project_path(self.project_root, value))
            for value in self.plan.get("extra_skill_roots", [])
            if project_path(self.project_root, value).is_dir()
        ]
        if extra_roots:
            self.client.request(
                "skills/extraRoots/set",
                {"extraRoots": extra_roots},
            )
        self.skill_paths = self._list_skills(force_reload=True)
        output_skill = stage["output_skill"]
        name = output_skill["name"]
        expected = (
            perf_trace_path(self.project_root, output_skill["path"])
            / "SKILL.md"
        )
        actual = self.skill_paths.get(name)
        if actual is None or actual.resolve() != expected.resolve():
            self._transition(
                stage_id,
                "GATE_FAILED",
                phase="FINAL",
                error=(
                    f"target Skill did not reload at expected path: "
                    f"name={name} actual={actual} expected={expected}"
                ),
            )
            raise OrchestrationError(
                f"{stage_id}: target Skill {name} is not discoverable at {expected}"
            )
        return actual

    def _handle_terminal_goal(
        self,
        stage: dict[str, Any],
        goal: dict[str, Any],
    ) -> None:
        stage_id = stage["id"]
        status = goal.get("status")
        self._record(stage_id)["goal"] = goal
        self._checkpoint()
        if status != "complete":
            stage_status = STOP_GOAL_STATUS_TO_STAGE.get(
                str(status), "PROTOCOL_FAILED"
            )
            self._transition(
                stage_id,
                stage_status,
                error=f"Goal reached terminal status {status}",
            )
            raise OrchestrationError(
                f"{stage_id}: Goal reached terminal status {status}"
            )
        self._wait_until_idle(stage_id)
        if stage.get("output_skill"):
            self._reload_output_skill(stage)
        self._verify_source_hashes()
        self._verify_contract_hashes()
        self._transition(
            stage_id,
            "FINAL_VALIDATING",
            phase="FINAL",
        )
        if not self._run_gate(stage, "final"):
            self._transition(
                stage_id,
                "GATE_FAILED",
                phase="FINAL",
                error="final gate failed",
            )
            raise OrchestrationError(f"{stage_id}: final gate failed")
        self._transition(stage_id, "COMMITTED", phase="COMMITTED")

    def _pause_goal_execution(self, stage_id: str) -> None:
        """Pause Goal first, then interrupt only server-confirmed active Turns."""
        record = self._record(stage_id)
        goal = self._get_goal(record["thread_id"])
        if isinstance(goal, dict):
            record["goal"] = goal
            if goal.get("status") == "complete":
                self._wait_until_idle(stage_id, timeout=30.0)
                return
            if goal.get("status") == "active":
                self._set_goal_status(stage_id, "paused")
        self._interrupt_in_progress(stage_id)

    def _wait_for_goal_terminal(self, stage: dict[str, Any]) -> None:
        assert self.client is not None
        stage_id = stage["id"]
        record = self._record(stage_id)
        deadline = time.monotonic() + self.stage_timeout
        last_poll = 0.0
        while time.monotonic() < deadline:
            if self.stop_requested:
                self._pause_goal_execution(stage_id)
                self._transition(stage_id, "PAUSED", error="operator interruption")
                raise OrchestrationError(f"{stage_id}: interrupted")
            self._drain_event(stage_id, timeout=0.5)
            now = time.monotonic()
            if now - last_poll < float(self.plan.get("poll_seconds", 2.0)):
                continue
            goal = self._get_goal(record["thread_id"])
            if goal is None:
                raise OrchestrationError(f"{stage_id}: Goal disappeared")
            record["goal"] = goal
            self._reconcile_thread(stage_id)
            self._checkpoint()
            status = goal.get("status")
            if status in TERMINAL_GOAL_STATUSES:
                self._handle_terminal_goal(stage, goal)
                return
            if status == "paused":
                self._transition(
                    stage_id,
                    "PAUSED",
                    error="Goal paused before completion",
                )
                raise OrchestrationError(f"{stage_id}: Goal paused")
            last_poll = now
        self._pause_goal_execution(stage_id)
        self._transition(
            stage_id,
            "TIMED_OUT",
            error=f"Goal exceeded {self.stage_timeout} seconds",
        )
        raise OrchestrationError(f"{stage_id}: Goal timed out")

    def _create_stage(self, stage: dict[str, Any]) -> None:
        assert self.client is not None
        stage_id = stage["id"]
        for dependency in stage.get("depends_on", []):
            if self._record(dependency)["status"] != "COMMITTED":
                raise OrchestrationError(
                    f"{stage_id}: dependency {dependency} is not COMMITTED"
                )
        result = self.client.request("thread/start", self._thread_start_params())
        thread_id = result.get("thread", {}).get("id")
        if not isinstance(thread_id, str):
            raise OrchestrationError(f"{stage_id}: thread/start returned no id")
        record = self._record(stage_id)
        record["thread_id"] = thread_id
        record["thread_status"] = result.get("thread", {}).get("status")
        self._transition(stage_id, "THREAD_CREATED", phase="THREAD_CREATED")
        goal_result = self.client.request(
            "thread/goal/set",
            {
                "threadId": thread_id,
                "objective": stage["objective"],
                # Keep Goal paused until the one explicit initial Turn is
                # observable.  This prevents Goal auto-continuation from racing
                # the client turn/start request.
                "status": "paused",
            },
        )
        record["goal"] = goal_result.get("goal")
        self._checkpoint()
        self._start_initial_turn(stage_id, self._goal_input(stage))
        goal = self._get_goal(thread_id)
        if goal is None:
            raise OrchestrationError(f"{stage_id}: Goal disappeared after initial Turn")
        record["goal"] = goal
        self._checkpoint()
        status = goal.get("status")
        if status in TERMINAL_GOAL_STATUSES:
            self._handle_terminal_goal(stage, goal)
            return
        if status == "paused":
            self._set_goal_status(stage_id, "active")
        elif status != "active":
            raise OrchestrationError(
                f"{stage_id}: unexpected Goal status after initial Turn: {status}"
            )
        self._wait_for_goal_terminal(stage)

    def _resume_stage(self, stage: dict[str, Any]) -> None:
        assert self.client is not None
        stage_id = stage["id"]
        record = self._record(stage_id)
        if record["status"] == "COMMITTED":
            return
        thread_id = record.get("thread_id")
        if not isinstance(thread_id, str):
            self._create_stage(stage)
            return
        self.client.request("thread/resume", {"threadId": thread_id})
        self._reconcile_thread(stage_id)
        goal = self._get_goal(thread_id)
        if goal is None:
            raise OrchestrationError(f"{stage_id}: no Goal exists after thread/resume")
        record["goal"] = goal
        self._checkpoint()
        status = goal.get("status")
        if status == "blocked" and self.reactivate:
            goal = self._set_goal_status(stage_id, "active")
            if not isinstance(goal, dict) or goal.get("status") != "active":
                raise OrchestrationError(
                    f"{stage_id}: blocked Goal did not reactivate"
                )
            status = "active"
        elif status in TERMINAL_GOAL_STATUSES:
            # A completed Goal is never re-run.  Missing bootstrap evidence or
            # gates are reconciled externally and then the stage is committed.
            self._handle_terminal_goal(stage, goal)
            return
        if status == "paused":
            if not self.reactivate:
                self._transition(
                    stage_id,
                    "PAUSED",
                    error="resume requires --reactivate for a paused Goal",
                )
                raise OrchestrationError(
                    f"{stage_id}: Goal is paused; rerun resume with --reactivate "
                    "after reviewing the blocker"
                )
            self._set_goal_status(stage_id, "active")
        elif status != "active":
            raise OrchestrationError(
                f"{stage_id}: unexpected Goal status on resume: {status}"
            )
        self._transition(stage_id, "RUNNING", phase="RUNNING")
        self._wait_for_goal_terminal(stage)

    def _migrate_legacy_contract_if_safe(self) -> bool:
        """Adopt v2 only when every already-created legacy Goal is complete.

        This narrow migration exists to preserve completed work from the
        original two-Turn bootstrap.  It never reactivates or re-runs a legacy
        Goal, and it rejects changes to workflow requirements or the manifest.
        """
        protocol = self.state.get("orchestration_protocol")
        if protocol == ORCHESTRATION_PROTOCOL:
            if self.state.get("schema_version") != STATE_SCHEMA_VERSION:
                raise OrchestrationError(
                    "Resume compatibility check failed: state schema/protocol mismatch"
                )
            return False
        if protocol is not None or self.state.get("schema_version") != 1:
            raise OrchestrationError(
                f"Unsupported orchestration protocol in state: {protocol!r}"
            )
        if self.state.get("plan_sha256") != self.plan_sha256:
            raise OrchestrationError(
                "Legacy state cannot migrate because adaptation_plan.json changed"
            )

        previous_files = self.state.get("contract_files")
        if not isinstance(previous_files, dict):
            raise OrchestrationError(
                "Legacy state cannot migrate without contract file hashes"
            )
        changed_files = sorted(
            key
            for key in set(previous_files) | set(self.contract_files)
            if previous_files.get(key) != self.contract_files.get(key)
        )
        allowed_changes = {
            self.plan["implementation_plan"],
            self.plan["common_goal_contract"],
            *(stage["goal_template"] for stage in self.stages),
        }
        unexpected = sorted(set(changed_files) - allowed_changes)
        if unexpected:
            raise OrchestrationError(
                "Legacy state contract migration rejected changed files: "
                + ", ".join(unexpected)
            )

        for stage in self.stages:
            record = self._record(stage["id"])
            if not record.get("thread_id"):
                continue
            goal = record.get("goal")
            if not isinstance(goal, dict) or goal.get("status") != "complete":
                raise OrchestrationError(
                    "Legacy state migration would require re-running a non-complete "
                    f"Goal: {stage['id']}"
                )

        migration = {
            "at": utc_now(),
            "from_schema_version": 1,
            "from_protocol": "bootstrap-owned-two-turns-v1",
            "from_contract_sha256": self.state.get("contract_sha256"),
            "to_schema_version": STATE_SCHEMA_VERSION,
            "to_protocol": ORCHESTRATION_PROTOCOL,
            "to_contract_sha256": self.contract_sha256,
            "changed_files": changed_files,
            "file_hash_changes": {
                key: {
                    "from": previous_files.get(key),
                    "to": self.contract_files.get(key),
                }
                for key in changed_files
            },
            "policy": (
                "preserve complete Goals; reconcile authoritative thread state; "
                "run the lightweight final structural gate without starting "
                "another Turn"
            ),
        }
        self.state.setdefault("contract_migrations", []).append(migration)
        self.state["schema_version"] = STATE_SCHEMA_VERSION
        self.state["orchestration_protocol"] = ORCHESTRATION_PROTOCOL
        self.state["contract_files"] = self.contract_files
        self.state["contract_sha256"] = self.contract_sha256
        for stage in self.stages:
            record = self._record(stage["id"])
            record.setdefault("requested_turn_ids", [])
            record.setdefault("active_turn_ids", [])
            record.setdefault("initial_turn_id", None)
        return True

    def _reconcile_already_adopted_workflow05_extension(self) -> bool | None:
        """Make a repeated extension-adoption request safe after interruption."""
        expected_identity = {
            "schema_version": STATE_SCHEMA_VERSION,
            "orchestration_protocol": ORCHESTRATION_PROTOCOL,
            "plan_id": self.plan["plan_id"],
            "plan_sha256": self.plan_sha256,
        }
        matches = {
            key: self.state.get(key) == value
            for key, value in expected_identity.items()
        }
        if not any(matches.values()):
            return None
        if not all(matches.values()):
            mismatches = {
                key: {"state": self.state.get(key), "expected": value}
                for key, value in expected_identity.items()
                if self.state.get(key) != value
            }
            raise OrchestrationError(
                "Workflow05 extension has a partially adopted identity: "
                + json.dumps(mismatches, ensure_ascii=False, sort_keys=True)
            )

        status = self.state.get("status")
        current_stage = self.state.get("current_stage")
        if status not in {"STOPPED", "COMPLETE"}:
            raise OrchestrationError(
                "Repeated Workflow05 extension adoption requires STOPPED or "
                f"COMPLETE state, got {status!r}"
            )
        if status == "COMPLETE" and current_stage is not None:
            raise OrchestrationError(
                "Completed Workflow05 extension state must not have current_stage"
            )
        if status == "STOPPED" and current_stage is not None and current_stage not in EXPECTED_STAGE_ORDER:
            raise OrchestrationError(
                f"Stopped Workflow05 extension has invalid current_stage: {current_stage}"
            )

        state_stages = self.state.get("stages")
        if not isinstance(state_stages, dict) or set(state_stages) != set(EXPECTED_STAGE_ORDER):
            raise OrchestrationError(
                "Already-adopted Workflow05 extension must contain the current stage set"
            )
        for stage_id in PRESERVED_STAGE_ORDER:
            record = state_stages.get(stage_id)
            if not isinstance(record, dict) or record.get("status") != "COMMITTED":
                raise OrchestrationError(
                    f"Already-adopted Workflow05 extension lost committed {stage_id}"
                )
        superseded = self.state.get("superseded_scheduler_stages")
        if not isinstance(superseded, dict) or HISTORICAL_SCHEDULER_STAGE_ID not in superseded:
            raise OrchestrationError(
                "Already-adopted Workflow05 extension has no historical P06 record"
            )
        extensions = self.state.get("workflow05_extensions")
        if not isinstance(extensions, list) or not any(
            isinstance(item, dict)
            and item.get("to_plan_id") == self.plan["plan_id"]
            for item in extensions
        ):
            raise OrchestrationError(
                "Already-adopted Workflow05 extension has no adoption audit record"
            )

        previous_files = self.state.get("contract_files")
        previous_digest = self.state.get("contract_sha256")
        if not isinstance(previous_files, dict) or not isinstance(previous_digest, str):
            raise OrchestrationError(
                "Already-adopted Workflow05 extension has no contract inventory"
            )
        if contract_digest(previous_files) != previous_digest:
            raise OrchestrationError(
                "Already-adopted Workflow05 extension contract inventory is corrupt"
            )
        changed_files = sorted(
            key
            for key in set(previous_files) | set(self.contract_files)
            if previous_files.get(key) != self.contract_files.get(key)
        )
        allowed_repairs = {self.plan["runner"], self.plan["verifier"]}
        unexpected = sorted(set(changed_files) - allowed_repairs)
        if unexpected:
            raise OrchestrationError(
                "Repeated Workflow05 extension adoption found non-control-plane "
                "changes: " + ", ".join(unexpected)
            )
        if not changed_files:
            return False

        now = utc_now()
        self.state.setdefault("workflow05_extension_reconciliations", []).append(
            {
                "at": now,
                "reason": "idempotent extension resume after operator interruption",
                "stage": current_stage,
                "from_contract_sha256": previous_digest,
                "to_contract_sha256": self.contract_sha256,
                "changed_files": changed_files,
                "file_hash_changes": {
                    key: {
                        "from": previous_files.get(key),
                        "to": self.contract_files.get(key),
                    }
                    for key in changed_files
                },
            }
        )
        self.state["contract_files"] = self.contract_files
        self.state["contract_sha256"] = self.contract_sha256
        self._checkpoint(emit_progress=False)
        return True

    def _adopt_workflow05_extension_if_requested(self) -> bool:
        """Audit COMPLETE P01-P06, preserve P01-P05, and append P07-P12."""
        if not self.adopt_workflow05_extension:
            return False
        if self.adopt_control_plane_repair:
            raise OrchestrationError(
                "--adopt-workflow05-extension cannot be combined with "
                "--adopt-control-plane-repair"
            )
        extension = self.plan.get("workflow05_extension")
        if not isinstance(extension, dict):
            raise OrchestrationError("Manifest does not declare workflow05_extension")
        reconciled = self._reconcile_already_adopted_workflow05_extension()
        if reconciled is not None:
            return reconciled
        expected_predecessor = {
            "schema_version": PREDECESSOR_STATE_SCHEMA_VERSION,
            "orchestration_protocol": PREDECESSOR_ORCHESTRATION_PROTOCOL,
            "plan_id": extension["predecessor_plan_id"],
            "plan_sha256": extension["predecessor_plan_sha256"],
            "contract_sha256": extension["predecessor_contract_sha256"],
            "status": "COMPLETE",
            "current_stage": None,
        }
        mismatches = {
            key: {"state": self.state.get(key), "expected": value}
            for key, value in expected_predecessor.items()
            if self.state.get(key) != value
        }
        if mismatches:
            raise OrchestrationError(
                "Workflow05 extension predecessor mismatch: "
                + json.dumps(mismatches, ensure_ascii=False, sort_keys=True)
            )
        previous_files = self.state.get("contract_files")
        previous_digest = self.state.get("contract_sha256")
        if not isinstance(previous_files, dict) or not isinstance(previous_digest, str):
            raise OrchestrationError("Canonical state has no valid predecessor contract inventory")
        if contract_digest(previous_files) != previous_digest:
            raise OrchestrationError("Stored predecessor contract inventory digest mismatch")

        protected_control_exceptions = {
            self.plan["workflow_contract"],
            self.plan["implementation_plan"],
            self.plan["common_goal_contract"],
            self.plan["runner"],
            self.plan["verifier"],
            str(self.plan_path.relative_to(self.project_root)),
            # P05's prompt was rebound from retired perf_trace_bk evidence;
            # its committed Skill and handoff are hash-checked independently.
            "perf_trace/workflows/project_adaptation/goals/P05.md",
            *(
                item["path"]
                for item in self.plan.get("retired_predecessor_binding_evidence", [])
            ),
        }
        protected_drift: list[str] = []
        for value, expected_hash in previous_files.items():
            if value in protected_control_exceptions:
                continue
            candidate = Path(value)
            path = candidate if candidate.is_absolute() else self.project_root / candidate
            if not path.is_file() or sha256_file(path) != expected_hash:
                protected_drift.append(value)
        if protected_drift:
            raise OrchestrationError(
                "Workflow05 extension changed protected predecessor files: "
                + ", ".join(sorted(protected_drift))
            )

        state_stages = self.state.get("stages")
        if not isinstance(state_stages, dict) or set(state_stages) != set(PREDECESSOR_STAGE_ORDER):
            raise OrchestrationError("Workflow05 extension requires exactly predecessor P01-P06 state")
        for stage_id in PREDECESSOR_STAGE_ORDER:
            record = state_stages.get(stage_id)
            goal = record.get("goal") if isinstance(record, dict) else None
            final_gate = record.get("final_gate") if isinstance(record, dict) else None
            if (
                not isinstance(record, dict)
                or record.get("status") != "COMMITTED"
                or not isinstance(goal, dict)
                or goal.get("status") != "complete"
                or not isinstance(final_gate, dict)
                or final_gate.get("status") != "pass"
            ):
                raise OrchestrationError(
                    f"Workflow05 extension requires {stage_id}=COMMITTED/complete/pass"
                )

        precommitted_by_name = {
            item["name"]: item for item in self.plan["precommitted_upstream_skills"]
        }
        handoff_by_stage = {
            item["stage"]: item for item in self.plan["predecessor_skill_handoffs"]
        }
        for stage_id in PRESERVED_STAGE_ORDER:
            stage = self._stage(stage_id)
            output = stage["output_skill"]
            skill_record = precommitted_by_name.get(output["name"])
            if not isinstance(skill_record, dict):
                raise OrchestrationError(f"{stage_id}: missing precommitted Skill record")
            skill_root = perf_trace_path(self.project_root, output["path"])
            if tree_digest(skill_root) != skill_record["tree_sha256"]:
                raise OrchestrationError(f"{stage_id}: committed target Skill changed")
            handoff_record = handoff_by_stage.get(stage_id)
            handoff_path = perf_trace_path(self.project_root, stage["handoff"])
            if (
                not isinstance(handoff_record, dict)
                or not handoff_path.is_file()
                or sha256_file(handoff_path) != handoff_record["sha256"]
            ):
                raise OrchestrationError(f"{stage_id}: committed handoff changed")
        for product in self.plan["predecessor_runtime_products"]:
            product_path = project_path(self.project_root, product["path"])
            if not product_path.is_file() or sha256_file(product_path) != product["sha256"]:
                raise OrchestrationError(f"historical P06 product changed: {product['path']}")
        self._verify_source_hashes()

        future_paths: list[str] = []
        for stage_id in WORKFLOW05_GAP_STAGE_IDS:
            stage = self._stage(stage_id)
            future_paths.extend([stage["output_skill"]["path"], stage["artifact_dir"], stage["handoff"]])
        scheduler = self._stage(SCHEDULER_STAGE_ID)
        future_paths.extend([scheduler["artifact_dir"], scheduler["handoff"], *scheduler["runtime_outputs"]])
        existing = [
            value for value in future_paths
            if perf_trace_path(self.project_root, value).exists()
        ]
        if existing:
            raise OrchestrationError(
                "Workflow05 extension refuses pre-existing P07-P12 outputs: "
                + ", ".join(existing)
            )

        changed_files = sorted(
            key for key in set(previous_files) | set(self.contract_files)
            if previous_files.get(key) != self.contract_files.get(key)
        )
        now = utc_now()
        historical_record = state_stages.pop(HISTORICAL_SCHEDULER_STAGE_ID)
        self.state.setdefault("superseded_scheduler_stages", {})[
            HISTORICAL_SCHEDULER_STAGE_ID
        ] = {
            "superseded_at": now,
            "reason": "P12 is the final Workflow 01-05 scheduler-generation stage",
            "record": historical_record,
            "runtime_products": self.plan["predecessor_runtime_products"],
        }
        for stage_id in ADDED_STAGE_ORDER:
            state_stages[stage_id] = new_stage_state_record()
        adoption = {
            "at": now,
            "from_plan_id": self.state.get("plan_id"),
            "to_plan_id": self.plan["plan_id"],
            "from_plan_sha256": self.state.get("plan_sha256"),
            "to_plan_sha256": self.plan_sha256,
            "from_contract_sha256": previous_digest,
            "to_contract_sha256": self.contract_sha256,
            "preserved_stages": list(PRESERVED_STAGE_ORDER),
            "superseded_scheduler_stage": HISTORICAL_SCHEDULER_STAGE_ID,
            "added_stages": list(ADDED_STAGE_ORDER),
            "changed_files": changed_files,
            "policy": (
                "preserve committed P01-P05 without rerunning; retain P06 as "
                "historical audit evidence; append P07-P11 Workflow05 gap Skills "
                "and final P12 Workflow01-05 scheduler"
            ),
        }
        self.state.setdefault("workflow05_extensions", []).append(adoption)
        self.state["schema_version"] = STATE_SCHEMA_VERSION
        self.state["orchestration_protocol"] = ORCHESTRATION_PROTOCOL
        self.state["plan_id"] = self.plan["plan_id"]
        self.state["plan_sha256"] = self.plan_sha256
        self.state["contract_files"] = self.contract_files
        self.state["contract_sha256"] = self.contract_sha256
        self.state["status"] = "STOPPED"
        self.state["current_stage"] = None
        self._checkpoint(emit_progress=False)
        return True

    def _adopt_control_plane_repair_if_requested(self) -> bool:
        """Audit and adopt a runner/verifier-only repair for a stopped blocked run."""
        previous_files = self.state.get("contract_files")
        previous_digest = self.state.get("contract_sha256")
        if not isinstance(previous_files, dict) or not isinstance(
            previous_digest, str
        ):
            raise OrchestrationError(
                "Canonical state has no valid contract hash inventory"
            )
        changed_files = sorted(
            key
            for key in set(previous_files) | set(self.contract_files)
            if previous_files.get(key) != self.contract_files.get(key)
        )
        if not changed_files:
            return False
        if not self.adopt_control_plane_repair:
            return False
        if not self.reactivate:
            raise OrchestrationError(
                "--adopt-control-plane-repair requires --reactivate"
            )
        if self.state.get("status") != "STOPPED":
            raise OrchestrationError(
                "Control-plane repair can be adopted only from STOPPED state"
            )
        if self.state.get("plan_sha256") != self.plan_sha256:
            raise OrchestrationError(
                "Control-plane repair rejected because the manifest changed"
            )
        if contract_digest(previous_files) != previous_digest:
            raise OrchestrationError(
                "Control-plane repair rejected because stored contract hashes "
                "do not match the stored digest"
            )
        allowed_changes = {
            self.plan["runner"],
            self.plan["verifier"],
        }
        unexpected = sorted(set(changed_files) - allowed_changes)
        if unexpected:
            raise OrchestrationError(
                "Control-plane repair may change only runner/verifier; changed: "
                + ", ".join(unexpected)
            )
        current_stage = self.state.get("current_stage")
        if current_stage not in EXPECTED_STAGE_ORDER:
            raise OrchestrationError(
                "Control-plane repair requires one current blocked stage"
            )
        current_record = self._record(str(current_stage))
        current_goal = current_record.get("goal")
        if (
            current_record.get("status") != "GOAL_BLOCKED"
            or not isinstance(current_goal, dict)
            or current_goal.get("status") != "blocked"
        ):
            raise OrchestrationError(
                "Control-plane repair requires a GOAL_BLOCKED stage whose "
                "authoritative Goal status is blocked"
            )
        self._verify_source_hashes()
        repair = {
            "at": utc_now(),
            "reason": (
                "operator-authorized deterministic runner/verifier repair "
                "after a blocked migration Goal"
            ),
            "stage": current_stage,
            "from_contract_sha256": previous_digest,
            "to_contract_sha256": self.contract_sha256,
            "changed_files": changed_files,
            "file_hash_changes": {
                key: {
                    "from": previous_files.get(key),
                    "to": self.contract_files.get(key),
                }
                for key in changed_files
            },
        }
        self.state.setdefault("control_plane_repairs", []).append(repair)
        self.state["contract_files"] = self.contract_files
        self.state["contract_sha256"] = self.contract_sha256
        self._checkpoint(emit_progress=False)
        return True

    def run_new(self) -> None:
        if self.state_path.exists():
            raise OrchestrationError(
                f"State already exists: {self.state_path}. Use resume or a new --state-file."
            )
        run_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + self.contract_sha256[:8]
        )
        run_dir = (
            perf_trace_path(
                self.project_root,
                self.plan["run_log_root"],
            )
            / run_id
        )
        if run_dir.exists():
            raise OrchestrationError(f"Refusing to reuse run directory: {run_dir}")
        run_dir.mkdir(parents=True)
        protocol_bundle, protocol_sha256 = generate_protocol_schema(
            self.codex_bin,
            run_dir / "protocol_schema",
        )
        self._create_initial_state(
            run_id,
            run_dir,
            protocol_bundle,
            protocol_sha256,
        )
        try:
            self._start_client()
            doctor = self._doctor_rpc()
            self.state["doctor"] = doctor
            self._capture_source_hashes()
            for stage in self.stages:
                self.current_stage_id = stage["id"]
                self._create_stage(stage)
            self.state["status"] = "COMPLETE"
            self.state["current_stage"] = None
            self._checkpoint(emit_progress=False)
            self._emit_progress(force=True, event="run:COMPLETE")
        except Exception:
            self.state["status"] = "STOPPED"
            self._checkpoint(emit_progress=False)
            self._emit_progress(force=True, event="run:STOPPED")
            raise
        finally:
            if self.client is not None:
                self.client.close()

    def resume(self) -> None:
        state = load_json(self.state_path)
        if not isinstance(state, dict):
            raise OrchestrationError(f"Invalid state object: {self.state_path}")
        self.state = state
        adopted_workflow05_extension = (
            self._adopt_workflow05_extension_if_requested()
        )
        migrated_legacy_contract = (
            False
            if adopted_workflow05_extension
            else self._migrate_legacy_contract_if_safe()
        )
        adopted_control_plane_repair = (
            self._adopt_control_plane_repair_if_requested()
        )
        expected_pairs = {
            "orchestration_protocol": ORCHESTRATION_PROTOCOL,
            "plan_sha256": self.plan_sha256,
            "project_root": str(self.project_root),
            "perf_trace_root": str(self.perf_trace_root),
            "codex_version": self.codex_version,
            "model": self.model,
            "effort": self.effort,
            "goal_token_budget_policy": GOAL_TOKEN_BUDGET_POLICY,
            "sandbox_policy": self.sandbox_policy,
            "approval_policy": APPROVAL_POLICY,
            "network_access": self.network_access,
        }
        mismatches = {
            key: {"state": self.state.get(key), "current": value}
            for key, value in expected_pairs.items()
            if self.state.get(key) != value
        }
        if mismatches:
            raise OrchestrationError(
                "Resume compatibility check failed: "
                + json.dumps(mismatches, ensure_ascii=False)
            )
        if self.state.get("contract_files") != self.contract_files or self.state.get(
            "contract_sha256"
        ) != self.contract_sha256:
            raise OrchestrationError(
                "Resume compatibility check failed: adaptation contract files changed"
            )
        bundle = Path(self.state["protocol_schema"])
        if not bundle.is_file() or sha256_canonical_json(bundle) != self.state.get(
            "protocol_schema_sha256"
        ):
            raise OrchestrationError("Stored app-server protocol schema hash mismatch")
        if (
            migrated_legacy_contract
            or adopted_workflow05_extension
            or adopted_control_plane_repair
        ):
            self._checkpoint(emit_progress=False)
        try:
            self._start_client()
            self._doctor_rpc()
            self._verify_source_hashes()
            self.state["status"] = "ACTIVE"
            self._checkpoint()
            for stage in self.stages:
                self.current_stage_id = stage["id"]
                if self._record(stage["id"])["status"] == "COMMITTED":
                    continue
                self._resume_stage(stage)
            self.state["status"] = "COMPLETE"
            self.state["current_stage"] = None
            self._checkpoint(emit_progress=False)
            self._emit_progress(force=True, event="resume:COMPLETE")
        except Exception:
            self.state["status"] = "STOPPED"
            self._checkpoint(emit_progress=False)
            self._emit_progress(force=True, event="resume:STOPPED")
            raise
        finally:
            if self.client is not None:
                self.client.close()

    def request_stop(self, _signum: int, _frame: Any) -> None:
        self.stop_requested = True


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    default_root = Path(__file__).resolve().parents[4]
    project_root = Path(args.project_root or default_root).resolve()
    if not project_root.is_dir():
        raise OrchestrationError(f"Project root is not a directory: {project_root}")
    plan_path = (
        Path(args.plan).resolve()
        if args.plan
        else project_root
        / ADAPTATION_RELATIVE_ROOT
        / "manifests"
        / "adaptation_plan.json"
    )
    state_path = (
        Path(args.state_file).resolve()
        if args.state_file
        else project_root
        / ADAPTATION_RELATIVE_ROOT
        / "state"
        / "adaptation_state_source_skill_text_alignment.json"
    )
    bounded_plan_path = perf_trace_path(project_root, plan_path)
    bounded_state_path = perf_trace_path(project_root, state_path)
    return project_root, bounded_plan_path, bounded_state_path


def runtime_settings(
    args: argparse.Namespace,
    plan: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = state or {}
    sandbox_policy = (
        args.sandbox_policy
        or source.get("sandbox_policy")
        or DEFAULT_SANDBOX_POLICY
    )
    if sandbox_policy == "danger-full-access":
        if args.network_access is False:
            raise OrchestrationError(
                "--no-network-access conflicts with danger-full-access; "
                "use --sandbox-policy workspace-write to restrict network access"
            )
        network_access = True
    else:
        network_access = (
            args.network_access
            if args.network_access is not None
            else bool(source.get("network_access", False))
        )
    return {
        "model": args.model or source.get("model") or plan["default_model"],
        "effort": args.effort or source.get("effort") or plan["effort"],
        "stage_timeout": (
            args.stage_timeout
            if args.stage_timeout is not None
            else float(plan["stage_timeout_seconds"])
        ),
        "request_timeout": args.request_timeout,
        "sandbox_policy": sandbox_policy,
        "network_access": network_access,
        "progress_interval": args.progress_interval,
        "progress_enabled": args.progress,
    }


def make_orchestrator(
    args: argparse.Namespace,
    *,
    state_for_defaults: dict[str, Any] | None = None,
) -> AdaptationOrchestrator:
    project_root, plan_path, state_path = resolve_paths(args)
    plan = load_json(plan_path)
    if not isinstance(plan, dict):
        raise OrchestrationError(f"Plan must be a JSON object: {plan_path}")
    validate_plan(plan, project_root, plan_path)
    codex_bin = discover_codex(args.codex_bin)
    version_text, version_tuple = read_codex_version(codex_bin)
    minimum = parse_semver(plan["min_codex_version"])
    if version_tuple < minimum:
        raise OrchestrationError(
            f"Codex {version_text} is older than required {plan['min_codex_version']}"
        )
    settings = runtime_settings(args, plan, state_for_defaults)
    if settings["effort"] != "max":
        raise OrchestrationError("This adaptation contract requires effort=max")
    if float(settings["progress_interval"]) <= 0:
        raise OrchestrationError("progress interval must be positive")
    return AdaptationOrchestrator(
        project_root=project_root,
        plan_path=plan_path,
        plan=plan,
        state_path=state_path,
        codex_bin=codex_bin,
        codex_version=version_text,
        reactivate=getattr(args, "reactivate", False),
        adopt_control_plane_repair=getattr(
            args,
            "adopt_control_plane_repair",
            False,
        ),
        adopt_workflow05_extension=getattr(
            args,
            "adopt_workflow05_extension",
            False,
        ),
        **settings,
    )


def command_doctor(args: argparse.Namespace) -> int:
    orchestrator = make_orchestrator(args)
    with tempfile.TemporaryDirectory(prefix="qwen-dcu-adaptation-doctor-") as temp:
        temporary = Path(temp)
        _bundle, schema_hash = generate_protocol_schema(
            orchestrator.codex_bin,
            temporary / "schema",
        )
        orchestrator.state = {
            "run_dir": str(temporary),
        }
        orchestrator._start_client()
        try:
            rpc = orchestrator._doctor_rpc()
        finally:
            if orchestrator.client is not None:
                orchestrator.client.close()
        result = {
            "status": "pass",
            "project_root": str(orchestrator.project_root),
            "perf_trace_root": str(orchestrator.perf_trace_root),
            "plan": str(orchestrator.plan_path),
            "codex_bin": str(orchestrator.codex_bin),
            "codex_version": orchestrator.codex_version,
            "goal_token_budget_policy": GOAL_TOKEN_BUDGET_POLICY,
            "orchestration_protocol": ORCHESTRATION_PROTOCOL,
            "sandbox_policy": orchestrator.sandbox_policy,
            "approval_policy": APPROVAL_POLICY,
            "network_access": orchestrator.network_access,
            "protocol_schema_generation": "ephemeral doctor output",
            "protocol_schema_sha256": schema_hash,
            **rpc,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_run(args: argparse.Namespace) -> int:
    project_root, plan_path, state_path = resolve_paths(args)
    plan = load_json(plan_path)
    if not isinstance(plan, dict):
        raise OrchestrationError("Plan must be an object")
    validate_plan(plan, project_root, plan_path)
    settings = runtime_settings(args, plan)
    if args.dry_run:
        if settings["effort"] != "max":
            raise OrchestrationError("This adaptation contract requires effort=max")
        result = {
            "status": "dry_run",
            "app_server_contacted": False,
            "thread_created": False,
            "turn_created": False,
            "goal_created": False,
            "canonical_state_modified": False,
            "handoff_created": False,
            "target_skill_created": False,
            "runtime_output_created": False,
            "project_root": str(project_root),
            "perf_trace_root": str(perf_trace_root(project_root)),
            "plan": str(plan_path),
            "runner": str(perf_trace_path(project_root, plan["runner"])),
            "verifier": str(perf_trace_path(project_root, plan["verifier"])),
            "state_file": str(state_path),
            "run_log_root": str(
                perf_trace_path(project_root, plan["run_log_root"])
            ),
            "gate_report_root": str(
                perf_trace_path(project_root, plan["gate_report_root"])
            ),
            "artifact_root": str(
                perf_trace_path(project_root, plan["artifact_root"])
            ),
            "handoff_root": str(
                perf_trace_path(project_root, plan["handoff_root"])
            ),
            "target_project_evidence": plan["target_project_evidence"],
            "capability_coverage": plan["capability_coverage"],
            "workflow05_extension": plan["workflow05_extension"],
            "runtime_outputs": plan["runtime_outputs"],
            "runtime_branches": plan["runtime_branches"],
            "model": settings["model"],
            "effort": settings["effort"],
            "goal_token_budget_policy": GOAL_TOKEN_BUDGET_POLICY,
            "orchestration_protocol": ORCHESTRATION_PROTOCOL,
            "sandbox_policy": settings["sandbox_policy"],
            "approval_policy": APPROVAL_POLICY,
            "network_access": settings["network_access"],
            "progress_enabled": settings["progress_enabled"],
            "progress_interval_seconds": settings["progress_interval"],
            "contract_sha256": contract_digest(
                contract_file_hashes(plan, project_root, plan_path)
            ),
            "stages": [
                {
                    "id": stage["id"],
                    "kind": stage["kind"],
                    "depends_on": stage["depends_on"],
                    "goal_template": stage["goal_template"],
                    "workflow_requirements": stage["workflow_requirements"],
                    "source_skill": stage.get("source_skill"),
                    "workflow_authority": stage.get("workflow_authority"),
                    "binding_evidence": stage.get("binding_evidence", []),
                    "output_skill": stage.get("output_skill"),
                    "runtime_outputs": stage.get("runtime_outputs", []),
                    "runtime_branches": stage.get("runtime_branches", []),
                    "artifact_dir": stage["artifact_dir"],
                    "handoff": stage["handoff"],
                    "final_gate": stage["final_gate"],
                }
                for stage in plan["stages"]
            ],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    orchestrator = make_orchestrator(args)
    signal.signal(signal.SIGINT, orchestrator.request_stop)
    signal.signal(signal.SIGTERM, orchestrator.request_stop)
    orchestrator.run_new()
    print(
        json.dumps(
            {
                "status": orchestrator.state["status"],
                "state_file": str(orchestrator.state_path),
                "run_dir": orchestrator.state["run_dir"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_resume(args: argparse.Namespace) -> int:
    _project_root, _plan_path, state_path = resolve_paths(args)
    existing = load_json(state_path)
    if not isinstance(existing, dict):
        raise OrchestrationError("State must be an object")
    orchestrator = make_orchestrator(args, state_for_defaults=existing)
    signal.signal(signal.SIGINT, orchestrator.request_stop)
    signal.signal(signal.SIGTERM, orchestrator.request_stop)
    orchestrator.resume()
    print(
        json.dumps(
            {
                "status": orchestrator.state["status"],
                "state_file": str(orchestrator.state_path),
                "run_dir": orchestrator.state["run_dir"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_status(args: argparse.Namespace) -> int:
    project_root, plan_path, state_path = resolve_paths(args)
    plan = load_json(plan_path)
    if not isinstance(plan, dict):
        raise OrchestrationError(f"Plan must be a JSON object: {plan_path}")
    if args.interval < 0.2:
        raise OrchestrationError("status watch interval must be at least 0.2 seconds")

    def read_snapshot() -> dict[str, Any]:
        if not state_path.is_file():
            state = {
                "status": "NOT_STARTED",
                "run_id": None,
                "current_stage": None,
                "goal_token_budget_policy": GOAL_TOKEN_BUDGET_POLICY,
                "orchestration_protocol": ORCHESTRATION_PROTOCOL,
                "sandbox_policy": DEFAULT_SANDBOX_POLICY,
                "approval_policy": APPROVAL_POLICY,
                "network_access": True,
                "updated_at": None,
                "stages": {},
            }
            return build_progress_snapshot(
                state, plan, project_root, state_path
            )
        state = load_json(state_path)
        if not isinstance(state, dict):
            raise OrchestrationError(f"State must be a JSON object: {state_path}")
        return build_progress_snapshot(state, plan, project_root, state_path)

    def emit(snapshot: dict[str, Any]) -> None:
        if args.format == "json":
            if args.watch:
                print(
                    json.dumps(
                        snapshot,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    flush=True,
                )
            else:
                print(
                    json.dumps(snapshot, ensure_ascii=False, indent=2),
                    flush=True,
                )
        elif args.watch:
            print(format_progress_compact(snapshot), flush=True)
        else:
            print(format_progress_human(snapshot), flush=True)

    if not args.watch:
        emit(read_snapshot())
        return 0

    last_signature: tuple[int, int] | None = None
    try:
        while True:
            if state_path.is_file():
                stat = state_path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
            else:
                signature = (0, 0)
            if signature != last_signature:
                snapshot = read_snapshot()
                emit(snapshot)
                last_signature = signature
                if snapshot.get("orchestration_status") in {
                    "COMPLETE",
                    "STOPPED",
                    "EXTENSION_PENDING",
                }:
                    return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("status watch stopped; orchestration was not signalled", file=sys.stderr)
        return 130


def add_path_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root")
    parser.add_argument("--plan")
    parser.add_argument("--state-file")


def add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    add_path_arguments(parser)
    parser.add_argument("--codex-bin")
    parser.add_argument("--model")
    parser.add_argument("--effort")
    parser.add_argument("--stage-timeout", type=float)
    parser.add_argument("--request-timeout", type=float, default=120.0)
    parser.add_argument(
        "--progress-interval",
        type=float,
        default=DEFAULT_PROGRESS_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--progress",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Show throttled progress on stderr while run/resume is active.",
    )
    parser.add_argument(
        "--sandbox-policy",
        choices=("workspace-write", "danger-full-access"),
        help=(
            "Codex sandbox policy (default: danger-full-access; "
            "use workspace-write to opt down)."
        ),
    )
    parser.add_argument(
        "--network-access",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Network access for workspace-write. danger-full-access always "
            "has unrestricted network access."
        ),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Serially orchestrate the unified Workflow 01-05 source, gap-Skill, "
            "and final scheduler-generation Goals."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser(
        "doctor",
        help="Validate Codex, model=max, app-server schema, and source Skills.",
    )
    add_runtime_arguments(doctor)
    doctor.set_defaults(handler=command_doctor)

    run = subparsers.add_parser(
        "run",
        help="Start a fresh unified P01-P05, P07-P12 adaptation chain.",
    )
    add_runtime_arguments(run)
    run.add_argument("--dry-run", action="store_true")
    run.set_defaults(handler=command_run)

    resume = subparsers.add_parser(
        "resume",
        help="Resume the first non-committed stage from canonical state.",
    )
    add_runtime_arguments(resume)
    resume.add_argument(
        "--reactivate",
        action="store_true",
        help=(
            "Explicitly reactivate a paused or blocked incomplete Goal after "
            "the external blocker has been reviewed and corrected."
        ),
    )
    resume.add_argument(
        "--adopt-control-plane-repair",
        action="store_true",
        help=(
            "Audit and adopt runner/verifier-only contract changes for a "
            "STOPPED GOAL_BLOCKED run; requires --reactivate."
        ),
    )
    resume.add_argument(
        "--adopt-workflow05-extension",
        action="store_true",
        help=(
            "Audit the COMPLETE P01-P06 predecessor, preserve P01-P05, "
            "supersede historical P06, and append P07-P12; repeated use after "
            "an interrupted adopted run is idempotent."
        ),
    )
    resume.set_defaults(handler=command_resume)

    status = subparsers.add_parser(
        "status",
        help="Read canonical progress without contacting Codex app-server.",
    )
    add_path_arguments(status)
    status.add_argument(
        "--format",
        choices=("human", "json"),
        default="json",
    )
    status.add_argument(
        "--watch",
        action="store_true",
        help="Print updates until canonical state becomes COMPLETE or STOPPED.",
    )
    status.add_argument("--interval", type=float, default=2.0)
    status.set_defaults(handler=command_status)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return int(args.handler(args))
    except (OrchestrationError, subprocess.TimeoutExpired) as exc:
        print(f"adaptation orchestration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
