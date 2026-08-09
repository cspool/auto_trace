#!/usr/bin/env python3
"""Bootstrap source-Skill, Workflow-gap, and scheduler-generation Goals.

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
    "A00",
    "A01",
    "A02",
    "A031",
    "A041",
    "A051",
    "A032",
    "A033",
    "A042",
    "A052",
    "A07",
)
EXPECTED_STAGE_KINDS = {
    "A00": "workflow_gap_skill_generation",
    "A01": "source_skill_text_alignment",
    "A02": "source_skill_text_alignment",
    "A031": "source_skill_text_alignment",
    "A041": "source_skill_text_alignment",
    "A051": "workflow_gap_skill_generation",
    "A032": "source_skill_text_alignment",
    "A033": "workflow_gap_skill_generation",
    "A042": "source_skill_text_alignment",
    "A052": "workflow_gap_skill_generation",
    "A07": "scheduler_generation",
}
STATE_SCHEMA_VERSION = 7
ORCHESTRATION_PROTOCOL = "goal-owned-turns-v7-workflow-capability-complete"
WORKLOAD_PROFILE_RELATIVE_ROOT = Path("workload_profile")
ADAPTATION_RELATIVE_ROOT = (
    WORKLOAD_PROFILE_RELATIVE_ROOT / "workflows" / "project_adaptation"
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


def tree_file_set(root: Path) -> list[str]:
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


def workload_profile_root(project_root: Path) -> Path:
    resolved_project_root = project_root.resolve()
    resolved = (resolved_project_root / WORKLOAD_PROFILE_RELATIVE_ROOT).resolve()
    try:
        resolved.relative_to(resolved_project_root)
    except ValueError as exc:
        raise OrchestrationError(
            "workload_profile root escapes project root: "
            f"{resolved_project_root / WORKLOAD_PROFILE_RELATIVE_ROOT}"
        ) from exc
    return resolved


def workload_profile_path(project_root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    resolved = candidate.resolve()
    allowed_root = workload_profile_root(project_root)
    try:
        resolved.relative_to(allowed_root)
    except ValueError as exc:
        raise OrchestrationError(
            f"Path escapes workload_profile root {allowed_root}: {value}"
        ) from exc
    return resolved


def project_path(project_root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    resolved_project_root = project_root.resolve()
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
            handoff_ready = workload_profile_path(
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
    return {
        "schema_version": 1,
        "observed_at": utc_now(),
        "state_file": str(state_path),
        "run_id": state.get("run_id"),
        "orchestration_status": state.get("status"),
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
            f"{marker} {row.get('ordinal', 0):>2}/{len(EXPECTED_STAGE_ORDER)} "
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
    workload_profile_path(project_root, plan_path)
    if plan.get("schema_version") != 5:
        raise OrchestrationError("adaptation plan schema_version must be 5")
    if plan.get("adaptation_mode") != "workflow-capability-complete-adaptation":
        raise OrchestrationError(
            "adaptation plan must use workflow-capability-complete-adaptation mode"
        )
    if (
        plan.get("adaptation_scope")
        != "source-preserving-plus-mandatory-workflow-gap-skills"
    ):
        raise OrchestrationError(
            "adaptation plan must preserve source Skills and all Workflow gaps"
        )
    if plan.get("phase") != "control-plane-only":
        raise OrchestrationError("adaptation plan phase must be control-plane-only")
    if "token_budget" in plan or "tokenBudget" in plan:
        raise OrchestrationError(
            "adaptation plan must omit token_budget/tokenBudget; "
            "Goal requests do not set an explicit token budget"
        )

    stage_order = plan.get("stage_order")
    if tuple(stage_order or ()) != EXPECTED_STAGE_ORDER:
        raise OrchestrationError(
            f"stage_order must be {EXPECTED_STAGE_ORDER}, got {stage_order}"
        )
    stages = plan.get("stages")
    if not isinstance(stages, list):
        raise OrchestrationError("adaptation plan stages must be a list")
    order = tuple(stage.get("id") for stage in stages if isinstance(stage, dict))
    if order != EXPECTED_STAGE_ORDER:
        raise OrchestrationError(
            f"stage order must be {EXPECTED_STAGE_ORDER}, got {order}"
        )
    stage_ids = set(EXPECTED_STAGE_ORDER)
    seen: set[str] = set()
    skill_stage_ids: set[str] = set()
    for stage in stages:
        stage_id = stage["id"]
        expected_kind = EXPECTED_STAGE_KINDS[stage_id]
        if stage.get("kind") != expected_kind:
            raise OrchestrationError(
                f"{stage_id}: kind must be {expected_kind}"
            )
        objective = stage.get("objective")
        if not isinstance(objective, str) or not objective.strip():
            raise OrchestrationError(f"{stage_id}: objective is empty")
        if len(objective) > 4000:
            raise OrchestrationError(f"{stage_id}: objective exceeds 4,000 characters")
        dependencies = stage.get("depends_on")
        if not isinstance(dependencies, list) or any(
            dependency not in seen for dependency in dependencies
        ):
            raise OrchestrationError(
                f"{stage_id}: dependencies must refer to earlier stages: {dependencies}"
            )
        seen.add(stage_id)
        for key in ("goal_template", "artifact_dir", "handoff"):
            value = stage.get(key)
            if not isinstance(value, str):
                raise OrchestrationError(f"{stage_id}: missing {key}")
            workload_profile_path(project_root, value)
        workflow_requirements = stage.get("workflow_requirements")
        if not isinstance(workflow_requirements, list) or not all(
            isinstance(value, str) for value in workflow_requirements
        ):
            raise OrchestrationError(
                f"{stage_id}: workflow_requirements must be a string list"
            )
        required_files = [stage["goal_template"], *workflow_requirements]
        for value in required_files:
            path = workload_profile_path(project_root, value)
            if not path.is_file():
                raise OrchestrationError(f"{stage_id}: required file is missing: {path}")

        final_gate = stage.get("final_gate")
        if not isinstance(final_gate, list) or not final_gate or not all(
            isinstance(part, str) and part for part in final_gate
        ):
            raise OrchestrationError(f"{stage_id}: final_gate must be a string list")

        if expected_kind != "scheduler_generation":
            skill_stage_ids.add(stage_id)
            output_skill = stage.get("output_skill")
            if not isinstance(output_skill, dict):
                raise OrchestrationError(f"{stage_id}: output_skill is required")
            output_name = output_skill.get("name")
            output_skill_path = output_skill.get("path")
            output_file_set = output_skill.get("file_set")
            if not isinstance(output_name, str) or not output_name:
                raise OrchestrationError(f"{stage_id}: output_skill.name is required")
            if not isinstance(output_skill_path, str):
                raise OrchestrationError(f"{stage_id}: output_skill.path is required")
            workload_profile_path(project_root, output_skill_path)
            if (
                not isinstance(output_file_set, list)
                or not output_file_set
                or len(output_file_set) != len(set(output_file_set))
                or not all(
                    isinstance(value, str)
                    and value
                    and not Path(value).is_absolute()
                    and ".." not in Path(value).parts
                    for value in output_file_set
                )
            ):
                raise OrchestrationError(
                    f"{stage_id}: output_skill.file_set must be unique safe paths"
                )

        if expected_kind == "source_skill_text_alignment":
            source_skill = stage.get("source_skill")
            if not isinstance(source_skill, dict):
                raise OrchestrationError(f"{stage_id}: source_skill is required")
            source_name = source_skill.get("name")
            source_scope = source_skill.get("scope")
            if not isinstance(source_name, str) or not source_name:
                raise OrchestrationError(
                    f"{stage_id}: source_skill.name is required"
                )
            if not isinstance(source_scope, str) or not source_scope:
                raise OrchestrationError(
                    f"{stage_id}: source_skill.scope is required"
                )
            source_hash = source_skill.get("tree_sha256")
            if not isinstance(source_hash, str) or not re.fullmatch(
                r"[0-9a-f]{64}", source_hash
            ):
                raise OrchestrationError(
                    f"{stage_id}: source_skill.tree_sha256 is invalid"
                )
            source_file_set = source_skill.get("file_set")
            if (
                not isinstance(source_file_set, list)
                or source_file_set != stage["output_skill"]["file_set"]
            ):
                raise OrchestrationError(
                    f"{stage_id}: source/output Skill file_set must match"
                )
            if "workflow_authority" in stage or "binding_evidence" in stage:
                raise OrchestrationError(
                    f"{stage_id}: source stage must not declare gap authority/evidence"
                )
            if "{source_skill_root}" not in final_gate:
                raise OrchestrationError(
                    f"{stage_id}: source final_gate must bind source_skill_root"
                )

        elif expected_kind == "workflow_gap_skill_generation":
            if stage.get("source_skill") is not None:
                raise OrchestrationError(
                    f"{stage_id}: Workflow-gap stage must not declare source_skill"
                )
            authority = stage.get("workflow_authority")
            if not isinstance(authority, dict):
                raise OrchestrationError(
                    f"{stage_id}: workflow_authority is required"
                )
            authority_path_value = authority.get("path")
            sections = authority.get("sections")
            authority_hash = authority.get("sha256")
            if not isinstance(authority_path_value, str):
                raise OrchestrationError(
                    f"{stage_id}: workflow_authority.path is required"
                )
            authority_path = workload_profile_path(
                project_root, authority_path_value
            )
            if not authority_path.is_file():
                raise OrchestrationError(
                    f"{stage_id}: authority file is missing: {authority_path}"
                )
            if authority_path_value not in workflow_requirements:
                raise OrchestrationError(
                    f"{stage_id}: authority must be a workflow requirement"
                )
            if (
                not isinstance(sections, list)
                or not sections
                or not all(isinstance(value, str) and value for value in sections)
            ):
                raise OrchestrationError(
                    f"{stage_id}: workflow_authority.sections is required"
                )
            if authority_hash != sha256_file(authority_path):
                raise OrchestrationError(
                    f"{stage_id}: workflow authority hash drift: "
                    f"declared={authority_hash} actual={sha256_file(authority_path)}"
                )
            evidence = stage.get("binding_evidence")
            if not isinstance(evidence, list):
                raise OrchestrationError(
                    f"{stage_id}: binding_evidence must be a list"
                )
            evidence_paths: set[str] = set()
            for item in evidence:
                if not isinstance(item, dict):
                    raise OrchestrationError(
                        f"{stage_id}: binding_evidence entries must be objects"
                    )
                value = item.get("path")
                if not isinstance(value, str) or value in evidence_paths:
                    raise OrchestrationError(
                        f"{stage_id}: duplicate/invalid binding evidence path {value}"
                    )
                evidence_paths.add(value)
                path = project_path(project_root, value)
                if not path.is_file():
                    raise OrchestrationError(
                        f"{stage_id}: binding evidence is missing: {path}"
                    )
                actual_hash = sha256_file(path)
                if item.get("sha256") != actual_hash:
                    raise OrchestrationError(
                        f"{stage_id}: binding evidence hash drift for {value}: "
                        f"declared={item.get('sha256')} actual={actual_hash}"
                    )
            unresolved = stage.get("unresolved_bindings")
            if (
                not isinstance(unresolved, list)
                or not all(isinstance(value, str) and value for value in unresolved)
            ):
                raise OrchestrationError(
                    f"{stage_id}: unresolved_bindings must be a string list"
                )
            markers = stage.get("required_markers")
            if (
                not isinstance(markers, list)
                or not markers
                or not all(isinstance(value, str) and value for value in markers)
            ):
                raise OrchestrationError(
                    f"{stage_id}: required_markers must be a non-empty string list"
                )
            if stage["output_skill"]["file_set"] != [
                "SKILL.md",
                "agents/openai.yaml",
            ]:
                raise OrchestrationError(
                    f"{stage_id}: gap Skill file_set must be SKILL.md + agents/openai.yaml"
                )
            if "{source_skill_root}" in final_gate:
                raise OrchestrationError(
                    f"{stage_id}: gap final_gate must not bind a source Skill"
                )

        else:
            if stage.get("output_skill") is not None:
                raise OrchestrationError(
                    f"{stage_id}: scheduler must not declare an output Skill"
                )
            if stage.get("source_skill") is not None:
                raise OrchestrationError(
                    f"{stage_id}: scheduler must not declare a source Skill"
                )
            branches = stage.get("runtime_branches")
            if not isinstance(branches, dict) or set(branches) != {
                "dispatch",
                "fx",
            }:
                raise OrchestrationError(
                    f"{stage_id}: runtime_branches must contain dispatch and fx"
                )
            consumed: set[str] = set()
            for branch, entries in branches.items():
                if not isinstance(entries, list) or not entries:
                    raise OrchestrationError(
                        f"{stage_id}: {branch} runtime branch must be non-empty"
                    )
                runtime_ids: set[str] = set()
                for entry in entries:
                    if not isinstance(entry, dict) or set(entry) != {"id", "stage"}:
                        raise OrchestrationError(
                            f"{stage_id}: invalid {branch} runtime entry {entry}"
                        )
                    runtime_id = entry.get("id")
                    owner = entry.get("stage")
                    if (
                        not isinstance(runtime_id, str)
                        or runtime_id in runtime_ids
                        or owner not in skill_stage_ids
                    ):
                        raise OrchestrationError(
                            f"{stage_id}: invalid {branch} binding {entry}"
                        )
                    runtime_ids.add(runtime_id)
                    consumed.add(owner)
            if consumed != skill_stage_ids:
                raise OrchestrationError(
                    f"{stage_id}: runtime branches must consume every Skill stage; "
                    f"missing={sorted(skill_stage_ids - consumed)} "
                    f"extra={sorted(consumed - skill_stage_ids)}"
                )
            if set(stage.get("depends_on", [])) != skill_stage_ids:
                raise OrchestrationError(
                    f"{stage_id}: dependencies must include every Skill stage"
                )
            runtime_outputs = stage.get("runtime_outputs")
            if not isinstance(runtime_outputs, dict) or set(runtime_outputs) != {
                "scheduler",
                "dispatch",
                "fx",
            }:
                raise OrchestrationError(
                    f"{stage_id}: runtime_outputs must contain scheduler/dispatch/fx"
                )
            for value in runtime_outputs.values():
                if not isinstance(value, str):
                    raise OrchestrationError(
                        f"{stage_id}: runtime output paths must be strings"
                    )
                workload_profile_path(project_root, value)

    inventory = plan.get("workflow_inventory")
    if not isinstance(inventory, list) or not inventory:
        raise OrchestrationError("workflow_inventory must be a non-empty list")
    inventory_paths: set[str] = set()
    runtime_workflows: set[str] = set()
    for item in inventory:
        if not isinstance(item, dict):
            raise OrchestrationError("workflow_inventory entries must be objects")
        value = item.get("path")
        classification = item.get("classification")
        contributes = item.get("contributes_to_runtime")
        if (
            not isinstance(value, str)
            or value in inventory_paths
            or classification
            not in {
                "runtime_workflow",
                "operator_documentation",
                "superseded_control_plane_draft",
                "superseded_control_plane_design",
                "control_plane_design",
            }
            or not isinstance(contributes, bool)
        ):
            raise OrchestrationError(f"invalid workflow inventory entry: {item}")
        inventory_paths.add(value)
        path = workload_profile_path(project_root, value)
        if not path.is_file():
            raise OrchestrationError(f"inventory file is missing: {path}")
        actual_hash = sha256_file(path)
        if item.get("sha256") != actual_hash:
            raise OrchestrationError(
                f"workflow inventory hash drift for {value}: "
                f"declared={item.get('sha256')} actual={actual_hash}"
            )
        if contributes:
            runtime_workflows.add(value)

    workflow_root = workload_profile_root(project_root) / "workflows"
    discovered = {
        path.relative_to(project_root).as_posix()
        for path in workflow_root.rglob("*.md")
        if "project_adaptation" not in path.relative_to(workflow_root).parts
    }
    if inventory_paths != discovered:
        raise OrchestrationError(
            "workflow_inventory must exactly enumerate non-adaptation Markdown; "
            f"missing={sorted(discovered - inventory_paths)} "
            f"extra={sorted(inventory_paths - discovered)}"
        )

    coverage = plan.get("capability_coverage")
    if not isinstance(coverage, list) or not coverage:
        raise OrchestrationError("capability_coverage must be a non-empty list")
    coverage_ids: set[str] = set()
    covered_workflows: set[str] = set()
    gap_coverage: set[str] = set()
    for item in coverage:
        if not isinstance(item, dict):
            raise OrchestrationError("capability_coverage entries must be objects")
        capability_id = item.get("id")
        workflow = item.get("workflow")
        coverage_type = item.get("coverage_type")
        owners = item.get("stages")
        if (
            not isinstance(capability_id, str)
            or not capability_id
            or capability_id in coverage_ids
            or workflow not in inventory_paths
            or coverage_type
            not in {
                "source_skill",
                "source_skill_boundary",
                "workflow_gap",
                "scheduler_generation",
            }
            or not isinstance(owners, list)
            or not owners
            or any(owner not in stage_ids for owner in owners)
        ):
            raise OrchestrationError(f"invalid capability coverage entry: {item}")
        coverage_ids.add(capability_id)
        covered_workflows.add(workflow)
        if coverage_type == "workflow_gap":
            if len(owners) != 1 or EXPECTED_STAGE_KINDS[owners[0]] != (
                "workflow_gap_skill_generation"
            ):
                raise OrchestrationError(
                    f"{capability_id}: workflow_gap must map to one gap stage"
                )
            gap_coverage.add(owners[0])
        elif coverage_type == "scheduler_generation":
            if owners != ["A07"]:
                raise OrchestrationError(
                    f"{capability_id}: scheduler coverage must map to A07"
                )
    if runtime_workflows - covered_workflows:
        raise OrchestrationError(
            "runtime-contributing Workflows lack capability coverage: "
            f"{sorted(runtime_workflows - covered_workflows)}"
        )
    expected_gap_stages = {
        stage_id
        for stage_id, kind in EXPECTED_STAGE_KINDS.items()
        if kind == "workflow_gap_skill_generation"
    }
    if gap_coverage != expected_gap_stages:
        raise OrchestrationError(
            "every Workflow-gap stage must have exactly one gap coverage row: "
            f"expected={sorted(expected_gap_stages)} got={sorted(gap_coverage)}"
        )

    for key in (
        "workflow_contract",
        "implementation_plan",
        "common_goal_contract",
    ):
        value = plan.get(key)
        if (
            not isinstance(value, str)
            or not workload_profile_path(project_root, value).is_file()
        ):
            raise OrchestrationError(f"plan {key} is missing: {value}")
    extra_skill_roots = plan.get("extra_skill_roots", [])
    if not isinstance(extra_skill_roots, list):
        raise OrchestrationError("extra_skill_roots must be a list")
    for value in extra_skill_roots:
        if not isinstance(value, str):
            raise OrchestrationError("extra_skill_roots entries must be strings")
        workload_profile_path(project_root, value)
    if plan_path != plan_path.resolve():
        raise OrchestrationError("plan path must resolve to an absolute path")


def contract_file_hashes(
    plan: dict[str, Any],
    project_root: Path,
    plan_path: Path,
) -> dict[str, str]:
    paths = {plan_path.resolve()}
    for key in (
        "workflow_contract",
        "implementation_plan",
        "common_goal_contract",
    ):
        paths.add(workload_profile_path(project_root, plan[key]))
    for item in plan.get("workflow_inventory", []):
        paths.add(workload_profile_path(project_root, item["path"]))
    for stage in plan["stages"]:
        paths.add(workload_profile_path(project_root, stage["goal_template"]))
        for value in stage.get("workflow_requirements", []):
            paths.add(workload_profile_path(project_root, value))
        authority = stage.get("workflow_authority")
        if isinstance(authority, dict):
            paths.add(workload_profile_path(project_root, authority["path"]))
        for item in stage.get("binding_evidence", []):
            paths.add(project_path(project_root, item["path"]))
    result: dict[str, str] = {}
    for path in sorted(paths):
        try:
            key = path.relative_to(project_root).as_posix()
        except ValueError:
            key = str(path)
        result[key] = sha256_file(path)
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
                    "name": "qwen_dcu_workload_profile_adapter",
                    "title": "Qwen DCU Workload Profile Adapter",
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
    """Schedule source alignment, Workflow-gap, and scheduler Goals."""

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
    ) -> None:
        self.project_root = project_root
        self.workload_profile_root = workload_profile_root(project_root)
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
                progress_log = workload_profile_path(
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
            "workload_profile_root": str(self.workload_profile_root),
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
            "status": "ACTIVE",
            "current_stage": None,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "source_skills": {},
            "stages": {
                stage["id"]: {
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
            str(workload_profile_path(self.project_root, value))
            for value in self.plan.get("extra_skill_roots", [])
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
            declarations = [
                stage["source_skill"]
                for stage in self.stages
                if isinstance(stage.get("source_skill"), dict)
                and stage["source_skill"]["name"] == name
            ]
            declared_hashes = {
                declaration["tree_sha256"] for declaration in declarations
            }
            declared_file_sets = {
                tuple(declaration["file_set"]) for declaration in declarations
            }
            if len(declared_hashes) != 1 or len(declared_file_sets) != 1:
                raise OrchestrationError(
                    f"conflicting manifest fingerprints for source Skill {name}"
                )
            actual_hash = tree_digest(skill_root)
            actual_file_set = tree_file_set(skill_root)
            declared_hash = next(iter(declared_hashes))
            declared_file_set = list(next(iter(declared_file_sets)))
            if actual_hash != declared_hash:
                raise OrchestrationError(
                    f"source Skill fingerprint drift for {name}: "
                    f"declared={declared_hash} actual={actual_hash}"
                )
            if actual_file_set != declared_file_set:
                raise OrchestrationError(
                    f"source Skill file-set drift for {name}: "
                    f"declared={declared_file_set} actual={actual_file_set}"
                )
            captured[name] = {
                "skill_md": str(skill_md),
                "root": str(skill_root),
                "sha256": actual_hash,
                "file_set": actual_file_set,
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

    def _thread_start_params(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "cwd": str(self.project_root),
            "approvalPolicy": APPROVAL_POLICY,
            "sandbox": self.sandbox_policy,
            "ephemeral": False,
            "developerInstructions": (
                "Execute exactly one manifest stage. For a source-Skill alignment, "
                "the attached source Skill and declared scope are the complete "
                "content authority: mirror its declared file set and preserve its "
                "methods, order, resources, evidence, validation, failure, stop, and "
                "completion boundaries while changing only verified project text "
                "bindings. For a Workflow-gap stage, attach no source Skill: use "
                "only the manifest-pinned Workflow sections as capability authority "
                "and the hash-pinned binding evidence for concrete Qwen3.5/vLLM/"
                "ROCm/DCU bindings; preserve every uncovered capability and defer "
                "only unresolved concrete bindings to runtime discovery. Generate "
                "only SKILL.md, agents/openai.yaml, and the minimal gap handoff. "
                "For the final scheduler stage, consume all committed target Skills "
                "and generate the manifest-declared serial runtime branches with "
                "Skill-only bindings. Never execute the runtime Workflow. Do not "
                "implement or run profiler/model/GPU/Dispatch/FX/reconstruction/"
                "ONNX/visualization/audit jobs. Do not spawn or manage agents, Codex "
                "processes, threads, or Goals. Do not edit "
                "workload_profile/workflows/project_adaptation/state, "
                "adaptation_plan.json, the bootstrap, "
                "or source Skills. Follow the on-disk stage contract and "
                "manage only this Goal's internal continuation/completion; leave "
                "serial stage order, external gates, and commit decisions "
                "to the bootstrap."
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
        kind = stage["kind"]
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
            f"适配总合同：{self.plan['workflow_contract']}",
            f"通用 Goal 合同：{self.plan['common_goal_contract']}",
            f"当前 Goal 模板：{stage['goal_template']}",
            "Workflow 需求：",
            *[f"- {path}" for path in stage.get("workflow_requirements", [])],
            "合法已提交前序：",
            json.dumps(dependencies, ensure_ascii=False, indent=2),
        ]
        skill_names: list[str] = []
        if kind == "source_skill_text_alignment":
            assert isinstance(output_skill, dict)
            assert isinstance(source_skill, dict)
            source_name = source_skill["name"]
            source_path = self.skill_paths[source_name].parent
            skill_names = [source_name]
            lines.extend(
                [
                    "阶段类型：source_skill_text_alignment",
                    f"唯一源 Skill：{source_name}",
                    f"源 Skill 根目录：{source_path}",
                    f"迁移能力范围：{source_skill['scope']}",
                    (
                        "固定源 Skill SHA-256："
                        f"{source_skill['tree_sha256']}"
                    ),
                    "固定相对文件集合：",
                    json.dumps(source_skill["file_set"], ensure_ascii=False),
                    f"目标 Skill：{output_skill['name']}",
                    f"目标 Skill 路径：{output_skill['path']}",
                    f"适配 handoff：{stage['handoff']}",
                    (
                        "Workflow 只用于理解该源 Skill 在本环节的角色，不向"
                        "目标 Skill 提供内容。源 Skill 或上述能力段是唯一、"
                        "完整且正确的目标约束；最大复用原文，只做当前项目"
                        "文本对齐。"
                    ),
                    (
                        "目标相对文件集合必须与源 Skill 完全一致：源 Skill "
                        "已有的 references/scripts/resources 必须保留，源 "
                        "Skill 没有的目录或文件不得新增。不要生成固定五个 "
                        "references、goal-spec、Workflow 摘要或其他并行合同。"
                    ),
                    (
                        "适配 handoff 的 outputs 只能包含目标 Skill 路径。"
                        "不得运行正式 Workflow；完成源结构镜像、文本对齐和"
                        "最小 handoff 后即可标记 complete。"
                    ),
                ]
            )
        elif kind == "workflow_gap_skill_generation":
            assert isinstance(output_skill, dict)
            lines.extend(
                [
                    "阶段类型：workflow_gap_skill_generation",
                    "唯一 Workflow authority：",
                    json.dumps(
                        stage["workflow_authority"],
                        ensure_ascii=False,
                        indent=2,
                    ),
                    "固定 binding evidence：",
                    json.dumps(
                        stage["binding_evidence"],
                        ensure_ascii=False,
                        indent=2,
                    ),
                    "必须保留为 runtime discovery 的未决绑定：",
                    json.dumps(
                        stage["unresolved_bindings"],
                        ensure_ascii=False,
                        indent=2,
                    ),
                    f"目标 Skill：{output_skill['name']}",
                    f"目标 Skill 路径：{output_skill['path']}",
                    "固定目标文件集合：",
                    json.dumps(output_skill["file_set"], ensure_ascii=False),
                    f"Workflow-gap handoff：{stage['handoff']}",
                    (
                        "不得附加或寻找规范性源 Skill。authority 的固定 sections "
                        "是完整能力合同；binding evidence 只能确定当前项目具体"
                        "绑定。即使 evidence 为空，也必须完整生成该 gap Skill，"
                        "只把具体绑定延迟到正式运行时发现。"
                    ),
                    (
                        "不得把 Workflow 全文、binding-evidence 业务工具、历史 "
                        "artifact、固定事件数、goal-spec 或迁移说明复制到目标 "
                        "Skill。handoff 必须声明 authority_type=workflow_gap、"
                        "固定 workflow_authority，并且 outputs 只含目标 Skill。"
                    ),
                ]
            )
        elif kind == "scheduler_generation":
            lines.extend(
                [
                    "阶段类型：scheduler_generation",
                    f"A07 handoff：{stage['handoff']}",
                    "固定 runtime branches：",
                    json.dumps(
                        stage["runtime_branches"],
                        ensure_ascii=False,
                        indent=2,
                    ),
                    "固定 runtime outputs：",
                    json.dumps(
                        stage["runtime_outputs"],
                        ensure_ascii=False,
                        indent=2,
                    ),
                    (
                        "A07 不是 Skill 适配。它消费全部已提交的 source-backed "
                        "与 gap-generated Skills，并严格按上述 branches 生成或"
                        "幂等校验运行时调度器。每一步创建独立持久 Goal，只有"
                        " complete 后继续。不要执行 Workflow。"
                    ),
                    (
                        "适配后的 Skill 本身就是运行 Goal 的完整约束。manifest "
                        "binding 只能包含 Skill 名称；运行 prompt 只组合 Skill、"
                        "用户参数和前序 runtime handoff，不读取或生成 goal-spec。"
                    ),
                    (
                        "只做 Python 语法、--help、两种 --dry-run 顺序和 manifest "
                        "绑定的轻量检查；不做 GPU、模型或业务测试。"
                    ),
                ]
            )
        else:
            raise OrchestrationError(f"{stage_id}: unsupported stage kind {kind}")
        lines.extend(
            [
                "不要只输出计划；直接完成当前 manifest stage。",
                "不得启动后继 Goal，不得修改参考 Skill 或 canonical state。",
            ]
        )
        mention = " ".join(f"${name}" for name in skill_names)
        text = (mention + "\n\n" if mention else "") + "\n".join(lines)
        return [{"type": "text", "text": text}, *self._skill_input_items(skill_names)]

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
        run_dir = Path(self.state["run_dir"])
        gate_dir = run_dir / "gate_reports"
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
        """Confirm only that the adapted Skill is discoverable at its manifest path."""
        assert self.client is not None
        stage_id = stage["id"]
        self.skill_paths = self._list_skills(force_reload=True)
        output_skill = stage["output_skill"]
        name = output_skill["name"]
        expected = (
            workload_profile_path(self.project_root, output_skill["path"])
            / "SKILL.md"
        )
        actual = self.skill_paths.get(name)
        if actual is None or actual.resolve() != expected.resolve():
            self._transition(
                stage_id,
                "GATE_FAILED",
                phase="FINAL",
                error=(
                    f"adapted Skill did not reload at expected path: "
                    f"name={name} actual={actual} expected={expected}"
                ),
            )
            raise OrchestrationError(
                f"{stage_id}: adapted Skill {name} is not discoverable at {expected}"
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
        if status in TERMINAL_GOAL_STATUSES:
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
            self.project_root
            / ADAPTATION_RELATIVE_ROOT
            / "state"
            / "adaptation_runs"
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
        migrated_legacy_contract = self._migrate_legacy_contract_if_safe()
        expected_pairs = {
            "orchestration_protocol": ORCHESTRATION_PROTOCOL,
            "plan_sha256": self.plan_sha256,
            "project_root": str(self.project_root),
            "workload_profile_root": str(self.workload_profile_root),
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
        if migrated_legacy_contract:
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
        / "adaptation_state_workflow_capability_complete_v1.json"
    )
    bounded_plan_path = workload_profile_path(project_root, plan_path)
    bounded_state_path = workload_profile_path(project_root, state_path)
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
            "workload_profile_root": str(orchestrator.workload_profile_root),
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
            "project_root": str(project_root),
            "workload_profile_root": str(workload_profile_root(project_root)),
            "plan": str(plan_path),
            "state_file": str(state_path),
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
            "workflow_inventory": plan["workflow_inventory"],
            "capability_coverage": plan["capability_coverage"],
            "stages": [
                {
                    "id": stage["id"],
                    "kind": stage["kind"],
                    "depends_on": stage["depends_on"],
                    "output_skill": stage.get("output_skill"),
                    "workflow_authority": stage.get("workflow_authority"),
                    "binding_evidence": stage.get("binding_evidence"),
                    "unresolved_bindings": stage.get("unresolved_bindings"),
                    "runtime_branches": stage.get("runtime_branches"),
                    "runtime_outputs": stage.get("runtime_outputs"),
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
                if snapshot.get("orchestration_status") in {"COMPLETE", "STOPPED"}:
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
            "Serially orchestrate source-Skill alignment, mandatory "
            "Workflow-gap Skill generation, and final scheduler generation."
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
        help=(
            "Start the complete fresh adaptation chain followed by A07 generation."
        ),
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
        help="Explicitly reactivate a paused incomplete Goal after review.",
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
