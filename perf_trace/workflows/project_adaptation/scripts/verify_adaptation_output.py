#!/usr/bin/env python3
"""Verify the unified Workflow 01-05 adaptation control plane and stages."""

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


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
EXPECTED_SOURCE_FILES = ("SKILL.md", "agents/openai.yaml")
EXPECTED_HANDOFF_KEYS = {
    "stage",
    "status",
    "source_skill",
    "output_skill",
    "outputs",
    "validation",
    "completed_at",
}
EXPECTED_VALIDATION_KEYS = {"command", "status"}
EXPECTED_GAP_HANDOFF_KEYS = {
    "stage",
    "status",
    "authority_type",
    "workflow_authority",
    "output_skill",
    "outputs",
    "validation",
    "completed_at",
}


class VerificationError(RuntimeError):
    """A deterministic static verification failure."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def contract_digest(hashes: dict[str, str]) -> str:
    canonical = json.dumps(
        hashes,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def tree_digest(root: Path) -> str:
    if not root.is_dir():
        raise VerificationError(f"Skill directory is missing: {root}")
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
        raise VerificationError(f"directory is missing: {root}")
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def contract_file_hashes(
    plan: dict[str, Any],
    project_root: Path,
    plan_path: Path,
) -> dict[str, str]:
    paths = {plan_path.resolve()}
    adaptation_root = (project_root / "perf_trace/workflows/project_adaptation").resolve()
    for relative in plan.get("control_plane_files", []):
        paths.add((adaptation_root / relative).resolve())
    for key in ("workflow_contract", "implementation_plan", "common_goal_contract", "runner", "verifier"):
        paths.add(bounded_path(project_root, plan[key]))
    for stage in plan["stages"]:
        paths.add(bounded_path(project_root, stage["goal_template"]))
        for value in stage.get("workflow_requirements", []):
            paths.add(bounded_path(project_root, value))
        authority = stage.get("workflow_authority")
        if isinstance(authority, dict):
            paths.add(bounded_path(project_root, authority["path"]))
        for record in stage.get("binding_evidence", []):
            paths.add(project_path(project_root, record["path"]))
    for record in plan.get("target_project_evidence", []):
        paths.add(project_path(project_root, record["path"]))
    for record in plan.get("predecessor_runtime_products", []):
        paths.add(project_path(project_root, record["path"]))
    for record in plan.get("predecessor_skill_handoffs", []):
        paths.add(bounded_path(project_root, record["path"]))

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


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise VerificationError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise VerificationError(f"invalid JSON file {path}: {exc}") from exc


def bounded_path(project_root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    resolved = candidate.resolve()
    perf_trace_root = (project_root / "perf_trace").resolve()
    try:
        resolved.relative_to(perf_trace_root)
    except ValueError as exc:
        raise VerificationError(
            f"path escapes perf_trace root {perf_trace_root}: {value}"
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
        raise VerificationError(
            f"path escapes project root {resolved_project_root}: {value}"
        ) from exc
    return resolved


def require_file(project_root: Path, value: str) -> Path:
    path = bounded_path(project_root, value)
    if not path.is_file():
        raise VerificationError(f"required file is missing: {path}")
    return path


def validate_manifest_shape(
    plan: dict[str, Any],
    project_root: Path,
) -> list[dict[str, Any]]:
    if plan.get("schema_version") != 5:
        raise VerificationError("manifest schema_version must be 5")
    if plan.get("adaptation_mode") != "workflow-capability-complete-adaptation":
        raise VerificationError("manifest adaptation_mode is invalid")
    if (
        plan.get("adaptation_scope")
        != "source-preserving-alignment-workflow-gap-synthesis-and-workflow01-05-scheduler"
    ):
        raise VerificationError("manifest adaptation_scope is invalid")
    if "token_budget" in plan or "tokenBudget" in plan:
        raise VerificationError("manifest must not set a Goal token budget")

    for key in ("workflow_contract", "implementation_plan", "common_goal_contract", "runner", "verifier"):
        value = plan.get(key)
        if not isinstance(value, str):
            raise VerificationError(f"manifest {key} is missing")
        require_file(project_root, value)
    for key in ("canonical_state", "run_log_root", "gate_report_root", "artifact_root", "handoff_root", "target_skill_root"):
        value = plan.get(key)
        if not isinstance(value, str):
            raise VerificationError(f"manifest {key} is missing")
        bounded_path(project_root, value)

    adaptation_root = (project_root / "perf_trace/workflows/project_adaptation").resolve()
    control_files = plan.get("control_plane_files")
    if not isinstance(control_files, list) or not control_files or control_files != sorted(set(control_files)):
        raise VerificationError("control_plane_files must be a sorted unique nonempty list")
    for relative in control_files:
        if not isinstance(relative, str):
            raise VerificationError("control_plane_files entries must be strings")
        path = (adaptation_root / relative).resolve()
        try:
            path.relative_to(adaptation_root)
        except ValueError as exc:
            raise VerificationError(f"control-plane path escapes adaptation root: {relative}") from exc
        if not path.is_file() or path.stat().st_size == 0:
            raise VerificationError(f"control-plane file is missing or empty: {path}")

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
        raise VerificationError("workflow05_extension contract mismatch")

    retired = plan.get("retired_predecessor_binding_evidence")
    if not isinstance(retired, list) or len(retired) != 5:
        raise VerificationError("five retired predecessor evidence records are required")
    for record in retired:
        if not isinstance(record, dict) or set(record) != {"path", "sha256", "role", "reason"}:
            raise VerificationError("malformed retired predecessor evidence record")
        if not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
            raise VerificationError("retired predecessor evidence hash is invalid")

    evidence = plan.get("target_project_evidence")
    if not isinstance(evidence, list) or not evidence:
        raise VerificationError("target_project_evidence must be nonempty")
    evidence_paths: set[str] = set()
    for record in evidence:
        if not isinstance(record, dict) or set(record) != {"path", "sha256", "role"}:
            raise VerificationError("malformed target-project evidence record")
        value = record["path"]
        if value in evidence_paths:
            raise VerificationError(f"duplicate target-project evidence: {value}")
        evidence_paths.add(value)
        path = project_path(project_root, value)
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise VerificationError(f"target-project evidence is missing or changed: {value}")

    workflows = plan.get("reference_workflows")
    if not isinstance(workflows, list) or len(workflows) != 5:
        raise VerificationError("manifest must pin exactly Workflow 01-05")
    workflow_paths: set[str] = set()
    for record in workflows:
        if not isinstance(record, dict) or set(record) != {"path", "sha256", "role"}:
            raise VerificationError("malformed reference Workflow record")
        value = record["path"]
        path = require_file(project_root, value)
        if value in workflow_paths or sha256_file(path) != record["sha256"]:
            raise VerificationError(f"reference Workflow is duplicate or changed: {value}")
        workflow_paths.add(value)
    if plan.get("supplied_workflow_roots") != [record["path"] for record in workflows]:
        raise VerificationError("supplied_workflow_roots must enumerate Workflow 01-05")

    if plan.get("capability_coverage") != EXPECTED_CAPABILITY_COVERAGE:
        raise VerificationError("capability_coverage does not exactly cover Workflow 01-05")
    if {record["workflow"] for record in EXPECTED_CAPABILITY_COVERAGE} != workflow_paths:
        raise VerificationError("capability_coverage omits a Workflow")
    serialized = json.dumps(plan, ensure_ascii=False, sort_keys=True).lower()
    if any(marker in serialized for marker in (
        "unscheduled_workflows", "no_authoritative_target_skill", '"coverage_kind": "ignored"',
        '"coverage_kind": "unsupported"', '"coverage_kind": "unscheduled"',
    )):
        raise VerificationError("manifest contains a forbidden omission state")

    reference = plan.get("reference_runner")
    if not isinstance(reference, dict):
        raise VerificationError("reference_runner is missing")
    reference_path = Path(reference.get("path", "")).resolve()
    if not reference_path.is_file() or sha256_file(reference_path) != reference.get("sha256"):
        raise VerificationError("byte-preserved reference runner is missing or changed")

    skills = plan.get("precommitted_upstream_skills")
    if not isinstance(skills, list) or len(skills) != 7:
        raise VerificationError("seven immutable upstream Skill records are required")
    skill_names: set[str] = set()
    for skill in skills:
        if not isinstance(skill, dict) or skill.get("immutable") is not True:
            raise VerificationError("precommitted Skill record is malformed")
        name = skill.get("name")
        if not isinstance(name, str) or name in skill_names:
            raise VerificationError("precommitted Skill names must be unique")
        skill_names.add(name)
        root = project_path(project_root, skill["path"])
        if tree_digest(root) != skill.get("tree_sha256"):
            raise VerificationError(f"precommitted upstream Skill changed: {name}")

    predecessor_paths = {
        "perf_trace/scripts/run_perf_trace.py",
        "perf_trace/manifests/core_attribution_pipeline.json",
        "perf_trace/workflows/project_adaptation/artifacts/P06/handoff.json",
    }
    predecessor = plan.get("predecessor_runtime_products")
    if not isinstance(predecessor, list) or {
        item.get("path") for item in predecessor if isinstance(item, dict)
    } != predecessor_paths:
        raise VerificationError("predecessor runtime product set is incomplete")
    for item in predecessor:
        path = project_path(project_root, item["path"])
        if not path.is_file() or sha256_file(path) != item.get("sha256"):
            raise VerificationError(f"predecessor runtime product changed: {item['path']}")

    handoffs = plan.get("predecessor_skill_handoffs")
    if not isinstance(handoffs, list) or [
        item.get("stage") for item in handoffs if isinstance(item, dict)
    ] != list(PRESERVED_STAGE_ORDER):
        raise VerificationError("predecessor_skill_handoffs must pin P01-P05")
    for item in handoffs:
        path = require_file(project_root, item["path"])
        if sha256_file(path) != item.get("sha256"):
            raise VerificationError(f"predecessor handoff changed: {item['path']}")

    if plan.get("runtime_outputs") != EXPECTED_RUNTIME_OUTPUTS:
        raise VerificationError("top-level runtime_outputs mismatch")
    if plan.get("runtime_branches") != EXPECTED_RUNTIME_BRANCHES:
        raise VerificationError("top-level runtime_branches mismatch")

    stages = plan.get("stages")
    if not isinstance(stages, list):
        raise VerificationError("manifest stages must be a list")
    order = tuple(stage.get("id") for stage in stages if isinstance(stage, dict))
    if order != EXPECTED_STAGE_ORDER or plan.get("stage_order") != list(EXPECTED_STAGE_ORDER):
        raise VerificationError(f"stage order must be {EXPECTED_STAGE_ORDER}, got {order}")

    seen: set[str] = set()
    source_names: set[str] = set()
    output_names: set[str] = set()
    for stage in stages:
        if not isinstance(stage, dict):
            raise VerificationError("stage must be an object")
        stage_id = stage["id"]
        expected_kind = (
            "source_skill_text_alignment" if stage_id in SOURCE_STAGE_IDS
            else "workflow_gap_skill_generation" if stage_id in WORKFLOW_GAP_STAGE_IDS
            else "scheduler_generation" if stage_id == SCHEDULER_STAGE_ID
            else None
        )
        if expected_kind is None or stage.get("kind") != expected_kind:
            raise VerificationError(f"{stage_id}: invalid kind")
        dependencies = stage.get("depends_on")
        if dependencies != EXPECTED_DEPENDENCIES[stage_id] or any(dep not in seen for dep in dependencies):
            raise VerificationError(f"{stage_id}: dependency graph mismatch")
        seen.add(stage_id)
        goal = stage.get("goal_template")
        requirements = stage.get("workflow_requirements")
        if not isinstance(goal, str):
            raise VerificationError(f"{stage_id}: goal_template is missing")
        goal_path = require_file(project_root, goal)
        if not isinstance(requirements, list) or not requirements or any(value not in workflow_paths for value in requirements):
            raise VerificationError(f"{stage_id}: workflow_requirements is not fully pinned")
        for key in ("artifact_dir", "handoff"):
            if not isinstance(stage.get(key), str):
                raise VerificationError(f"{stage_id}: {key} is missing")
            bounded_path(project_root, stage[key])
        expected_gate = [
            "python3", f"{{project_root}}/{plan['verifier']}",
            "--project-root", "{project_root}", "--plan", "{plan_path}",
            "--stage", "{stage_id}",
        ]
        if stage_id in SOURCE_STAGE_IDS:
            expected_gate += ["--source-skill-root", "{source_skill_root}"]
        if stage.get("final_gate") != expected_gate:
            raise VerificationError(f"{stage_id}: final_gate interface mismatch")

        if stage_id == SCHEDULER_STAGE_ID:
            if "source_skill" in stage or stage.get("output_skill") is not None:
                raise VerificationError("P12 must not declare source/output Skill")
            if stage.get("runtime_outputs") != EXPECTED_RUNTIME_OUTPUTS or stage.get("runtime_branches") != EXPECTED_RUNTIME_BRANCHES:
                raise VerificationError("P12 runtime contract mismatch")
            expected_targets = [EXPECTED_RUNTIME_BINDINGS[f"R{i:02d}"]["skill"] for i in range(1, 11)]
            if stage.get("consumes_target_skills") != expected_targets:
                raise VerificationError("P12 must consume all ten target Skills")
            goal_text = goal_path.read_text(encoding="utf-8")
            missing = [marker for marker in [*EXPECTED_RUNTIME_OUTPUTS, *expected_targets, "workflow01-05-full", "workflow05-existing-evidence", "ephemeral=false"] if marker not in goal_text]
            if missing:
                raise VerificationError(f"P12 Goal omits scheduler markers: {missing}")
            continue

        if stage_id in WORKFLOW_GAP_STAGE_IDS:
            if "source_skill" in stage:
                raise VerificationError(f"{stage_id}: gap Goal must not attach source_skill")
            authority = stage.get("workflow_authority")
            if not isinstance(authority, dict) or set(authority) != {"path", "sha256", "scope"} or not authority["scope"].strip():
                raise VerificationError(f"{stage_id}: malformed Workflow authority")
            authority_path = require_file(project_root, authority["path"])
            if sha256_file(authority_path) != authority["sha256"]:
                raise VerificationError(f"{stage_id}: Workflow authority changed")
            binding_evidence = stage.get("binding_evidence")
            if not isinstance(binding_evidence, list) or not binding_evidence:
                raise VerificationError(f"{stage_id}: binding evidence is empty")
            evidence_seen: set[str] = set()
            for record in binding_evidence:
                if not isinstance(record, dict) or set(record) != {"path", "sha256", "role"}:
                    raise VerificationError(f"{stage_id}: malformed binding evidence")
                if record["path"] in evidence_seen:
                    raise VerificationError(f"{stage_id}: duplicate binding evidence")
                evidence_seen.add(record["path"])
                path = project_path(project_root, record["path"])
                if not path.is_file() or sha256_file(path) != record["sha256"]:
                    raise VerificationError(f"{stage_id}: binding evidence changed: {record['path']}")
            output = stage.get("output_skill")
            if not isinstance(output, dict) or output.get("file_set") != ["SKILL.md", "agents/openai.yaml"]:
                raise VerificationError(f"{stage_id}: exact two-file output Skill is required")
            if output.get("name") in output_names:
                raise VerificationError(f"{stage_id}: duplicate output Skill")
            output_names.add(output["name"])
            output_path = bounded_path(project_root, output["path"])
            try:
                output_path.relative_to(bounded_path(project_root, plan["target_skill_root"]))
            except ValueError as exc:
                raise VerificationError(f"{stage_id}: output Skill escapes target root") from exc
            if stage_id == "P05":
                if authority["path"] != "perf_trace/workflows/03_process_gpu_hardware_trace.md":
                    raise VerificationError("P05 must retain Workflow 03 authority")
            else:
                if authority["path"] != "perf_trace/workflows/05_workflow04_guided_selective_process_trace_and_resource_gap_analysis.md":
                    raise VerificationError(f"{stage_id}: must use Workflow 05 authority")
                if not isinstance(stage.get("unresolved_bindings"), list) or not stage["unresolved_bindings"]:
                    raise VerificationError(f"{stage_id}: unresolved_bindings must be explicit")
                if not isinstance(stage.get("boundary_skills"), list) or not stage["boundary_skills"]:
                    raise VerificationError(f"{stage_id}: boundary_skills must be explicit")
                for field in ("required_sections", "required_markers"):
                    if not isinstance(stage.get(field), list) or not stage[field]:
                        raise VerificationError(f"{stage_id}: missing {field}")
            goal_text = goal_path.read_text(encoding="utf-8")
            for marker in (output["name"], authority["path"], stage["handoff"]):
                if marker not in goal_text:
                    raise VerificationError(f"{stage_id}: Goal template omits {marker}")
            continue

        source = stage.get("source_skill")
        output = stage.get("output_skill")
        if not isinstance(source, dict) or not isinstance(output, dict):
            raise VerificationError(f"{stage_id}: source/output Skill contract is missing")
        name = source.get("name")
        if not isinstance(name, str) or name in source_names or source.get("scope") != "full":
            raise VerificationError(f"{stage_id}: invalid source Skill identity/scope")
        source_names.add(name)
        source_root = Path(source.get("path", "")).resolve()
        if not source_root.is_dir() or tree_digest(source_root) != source.get("sha256"):
            raise VerificationError(f"{stage_id}: source Skill is missing or changed")
        if source.get("file_set") != relative_file_set(source_root):
            raise VerificationError(f"{stage_id}: source Skill file_set mismatch")
        output_name = output.get("name")
        if not isinstance(output_name, str) or output_name in output_names:
            raise VerificationError(f"{stage_id}: duplicate output Skill")
        output_names.add(output_name)
        bounded_path(project_root, output["path"])

    if output_names != {binding["skill"] for binding in EXPECTED_RUNTIME_BINDINGS.values()}:
        raise VerificationError("Skill-producing stages do not match runtime bindings")
    return stages

def parse_frontmatter(skill_md: Path) -> dict[str, str]:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise VerificationError(f"SKILL.md has no YAML frontmatter: {skill_md}")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise VerificationError(f"SKILL.md frontmatter is not closed: {skill_md}")
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"([A-Za-z0-9_-]+):\s*(.*)", line)
        if match is None:
            raise VerificationError(
                f"unsupported frontmatter line in {skill_md}: {line}"
            )
        fields[match.group(1)] = match.group(2).strip().strip("\"'")
    return fields


def markdown_h2_spans(text: str) -> list[tuple[str, int, int]]:
    """Return real H2 spans while ignoring headings inside fenced code blocks."""
    spans: list[tuple[str, int, int]] = []
    fence_character: str | None = None
    fence_length = 0
    offset = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        if fence_character is not None:
            close = re.fullmatch(
                rf"[ ]{{0,3}}{re.escape(fence_character)}"
                rf"{{{fence_length},}}[ \t]*",
                content,
            )
            if close is not None:
                fence_character = None
                fence_length = 0
            offset += len(line)
            continue
        opening = re.match(r"^[ ]{0,3}(`{3,}|~{3,})", content)
        if opening is not None:
            delimiter = opening.group(1)
            fence_character = delimiter[0]
            fence_length = len(delimiter)
            offset += len(line)
            continue
        heading = re.fullmatch(r"[ ]{0,3}##[ \t]+(.+?)[ \t]*", content)
        if heading is not None:
            spans.append(
                (
                    heading.group(1).strip(),
                    offset,
                    offset + len(line),
                )
            )
        offset += len(line)
    return spans


def heading_sequence(skill_md: Path) -> list[str]:
    return [
        heading
        for heading, _start, _body_start in markdown_h2_spans(
            skill_md.read_text(encoding="utf-8")
        )
    ]


def h2_sections(text: str) -> list[tuple[str, str]]:
    spans = markdown_h2_spans(text)
    sections: list[tuple[str, str]] = []
    for index, (heading, _start, body_start) in enumerate(spans):
        end = spans[index + 1][1] if index + 1 < len(spans) else len(text)
        sections.append((heading, text[body_start:end].strip()))
    return sections


def normalized_fidelity_text(text: str) -> str:
    normalized = text.casefold()
    normalized = re.sub(r"/[^\s`\"')]+", " <path> ", normalized)
    normalized = re.sub(
        r"\b(?:visipruner|qwen(?:3\.5)?|pra2026-bh408|vllm|rocm|dcu|hip|"
        r"cuda|nsight|cupti|nvtx)\b",
        " <binding> ",
        normalized,
    )
    normalized = re.sub(r"\b\d+(?:\.\d+)?\b", " <number> ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def fidelity_ratio(source: str, target: str) -> float:
    return difflib.SequenceMatcher(
        None,
        normalized_fidelity_text(source),
        normalized_fidelity_text(target),
        autojunk=False,
    ).ratio()


def constraint_count(text: str) -> int:
    return len(
        re.findall(
            r"\b(?:must(?:\s+not)?|do\s+not|never|only|"
            r"require(?:d|s)?|reject(?:ed|s)?|fail(?:ed|s|ure)?|cannot)\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def validate_local_links(skill_md: Path) -> None:
    text = skill_md.read_text(encoding="utf-8")
    missing: list[str] = []
    for value in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        target = value.strip().split(maxsplit=1)[0].strip("<>")
        if (
            not target
            or target.startswith(("#", "http://", "https://", "mailto:"))
        ):
            continue
        relative = target.split("#", 1)[0]
        if relative and not (skill_md.parent / relative).resolve().exists():
            missing.append(value)
    if missing:
        raise VerificationError(
            f"{skill_md}: unresolved local resource links: {missing}"
        )


def verify_control_plane(
    plan: dict[str, Any],
    project_root: Path,
    plan_path: Path,
) -> dict[str, Any]:
    """Validate a fresh unified plan whose future outputs do not yet exist."""
    stages = validate_manifest_shape(plan, project_root)
    unexpected: list[str] = []
    for stage in stages:
        values = [stage["artifact_dir"], stage["handoff"]]
        output = stage.get("output_skill")
        if isinstance(output, dict):
            values.append(output["path"])
        values.extend(stage.get("runtime_outputs", []))
        for value in values:
            path = bounded_path(project_root, value)
            if path.exists():
                unexpected.append(str(path))
    for key in ("canonical_state", "run_log_root", "gate_report_root", "artifact_root", "handoff_root"):
        path = bounded_path(project_root, plan[key])
        if path.exists():
            unexpected.append(str(path))
    if unexpected:
        raise VerificationError(
            "fresh Phase-1 boundary violated; output/state paths exist: "
            + ", ".join(sorted(set(unexpected)))
        )
    hashes = contract_file_hashes(plan, project_root, plan_path)
    return {
        "mode": "control_plane",
        "stage_order": list(EXPECTED_STAGE_ORDER),
        "workflow_count": 5,
        "capability_count": len(EXPECTED_CAPABILITY_COVERAGE),
        "source_skill_count": len(SOURCE_STAGE_IDS),
        "workflow_gap_stages": list(WORKFLOW_GAP_STAGE_IDS),
        "scheduler_stage": SCHEDULER_STAGE_ID,
        "contract_sha256": contract_digest(hashes),
        "phase_1_boundary": "fresh-clean",
    }


def verify_control_plane_extension(
    plan: dict[str, Any],
    project_root: Path,
    plan_path: Path,
) -> dict[str, Any]:
    """Verify COMPLETE P01-P06 can become the P01-P05,P07-P12 chain."""
    stages = validate_manifest_shape(plan, project_root)
    extension = plan["workflow05_extension"]
    state_path = bounded_path(project_root, plan["canonical_state"])
    state = load_json(state_path)
    if not isinstance(state, dict):
        raise VerificationError("canonical predecessor state must be an object")
    expected_state = {
        "schema_version": extension["predecessor_state_schema_version"],
        "orchestration_protocol": extension["predecessor_orchestration_protocol"],
        "plan_id": extension["predecessor_plan_id"],
        "plan_sha256": extension["predecessor_plan_sha256"],
        "contract_sha256": extension["predecessor_contract_sha256"],
        "status": "COMPLETE",
        "current_stage": None,
    }
    mismatches = {
        key: {"expected": value, "actual": state.get(key)}
        for key, value in expected_state.items()
        if state.get(key) != value
    }
    if mismatches:
        raise VerificationError(
            "canonical predecessor state mismatch: "
            + json.dumps(mismatches, ensure_ascii=False, sort_keys=True)
        )
    previous_files = state.get("contract_files")
    if not isinstance(previous_files, dict) or contract_digest(previous_files) != state["contract_sha256"]:
        raise VerificationError("canonical predecessor contract inventory mismatch")

    allowed_changes = {
        plan["workflow_contract"],
        plan["implementation_plan"],
        plan["common_goal_contract"],
        plan["runner"],
        plan["verifier"],
        "perf_trace/workflows/project_adaptation/manifests/adaptation_plan.json",
        "perf_trace/workflows/project_adaptation/goals/P05.md",
        *(item["path"] for item in plan["retired_predecessor_binding_evidence"]),
    }
    protected_drift: list[str] = []
    for value, expected_hash in previous_files.items():
        if value in allowed_changes:
            continue
        candidate = Path(value)
        path = candidate if candidate.is_absolute() else project_root / candidate
        if not path.is_file() or sha256_file(path) != expected_hash:
            protected_drift.append(value)
    if protected_drift:
        raise VerificationError(
            "Workflow05 extension changed protected predecessor files: "
            + ", ".join(sorted(protected_drift))
        )

    state_stages = state.get("stages")
    if not isinstance(state_stages, dict) or set(state_stages) != set(PREDECESSOR_STAGE_ORDER):
        raise VerificationError("canonical predecessor must contain exactly P01-P06")
    state_checks: list[dict[str, str]] = []
    for stage_id in PREDECESSOR_STAGE_ORDER:
        record = state_stages.get(stage_id)
        goal = record.get("goal") if isinstance(record, dict) else None
        gate = record.get("final_gate") if isinstance(record, dict) else None
        if (
            not isinstance(record, dict)
            or record.get("status") != "COMMITTED"
            or not isinstance(goal, dict)
            or goal.get("status") != "complete"
            or not isinstance(gate, dict)
            or gate.get("status") != "pass"
        ):
            raise VerificationError(f"{stage_id}: predecessor must be COMMITTED/complete/pass")
        state_checks.append({"stage": stage_id, "status": "preserved" if stage_id in PRESERVED_STAGE_ORDER else "historical-superseded"})

    precommitted = {item["name"]: item for item in plan["precommitted_upstream_skills"]}
    handoffs = {item["stage"]: item for item in plan["predecessor_skill_handoffs"]}
    for stage_id in PRESERVED_STAGE_ORDER:
        stage = next(item for item in stages if item["id"] == stage_id)
        output = stage["output_skill"]
        skill_record = precommitted.get(output["name"])
        if not isinstance(skill_record, dict):
            raise VerificationError(f"{stage_id}: precommitted target Skill record is missing")
        if tree_digest(bounded_path(project_root, output["path"])) != skill_record["tree_sha256"]:
            raise VerificationError(f"{stage_id}: committed target Skill changed")
        handoff_record = handoffs.get(stage_id)
        handoff_path = require_file(project_root, stage["handoff"])
        if not isinstance(handoff_record, dict) or sha256_file(handoff_path) != handoff_record["sha256"]:
            raise VerificationError(f"{stage_id}: committed handoff changed")

    forbidden_now: list[str] = []
    for stage_id in WORKFLOW05_GAP_STAGE_IDS:
        stage = next(item for item in stages if item["id"] == stage_id)
        forbidden_now.extend([stage["output_skill"]["path"], stage["artifact_dir"], stage["handoff"]])
    scheduler = next(item for item in stages if item["id"] == SCHEDULER_STAGE_ID)
    forbidden_now.extend([scheduler["artifact_dir"], scheduler["handoff"], *scheduler["runtime_outputs"]])
    present = [value for value in forbidden_now if bounded_path(project_root, value).exists()]
    if present:
        raise VerificationError(
            "Phase-1 P07-P12 output boundary violated: " + ", ".join(present)
        )

    runner = require_file(project_root, plan["runner"])
    verifier = require_file(project_root, plan["verifier"])
    for path in (runner, verifier):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            raise VerificationError(f"Python syntax failure in {path}: {exc}") from exc
    runner_text = runner.read_text(encoding="utf-8")
    for marker in (
        '"ephemeral": False', "thread/goal/set", "thread/goal/get",
        "atomic_write_json", "--dry-run", "--adopt-workflow05-extension",
        "workflow_gap_skill_generation", "scheduler_generation",
    ):
        if marker not in runner_text:
            raise VerificationError(f"derived runner lacks invariant marker: {marker}")

    hashes = contract_file_hashes(plan, project_root, plan_path)
    return {
        "mode": "control_plane_extension",
        "stage_order": list(EXPECTED_STAGE_ORDER),
        "workflow_count": 5,
        "capability_count": len(EXPECTED_CAPABILITY_COVERAGE),
        "preserved_stages": list(PRESERVED_STAGE_ORDER),
        "superseded_scheduler_stage": HISTORICAL_SCHEDULER_STAGE_ID,
        "workflow05_gap_stages": list(WORKFLOW05_GAP_STAGE_IDS),
        "scheduler_stage": SCHEDULER_STAGE_ID,
        "runtime_branches": [branch["branch"] for branch in EXPECTED_RUNTIME_BRANCHES],
        "predecessor_state": str(state_path),
        "predecessor_stage_checks": state_checks,
        "contract_sha256": contract_digest(hashes),
        "phase_1_boundary": "P01-P05-preserved; P06-historical; P07-P12-not-generated",
    }

def verify_handoff(
    handoff_path: Path,
    stage: dict[str, Any],
) -> None:
    handoff = load_json(handoff_path)
    if not isinstance(handoff, dict):
        raise VerificationError(f"handoff must be an object: {handoff_path}")
    if set(handoff) != EXPECTED_HANDOFF_KEYS:
        raise VerificationError(
            f"{stage['id']}: handoff keys must be exactly "
            f"{sorted(EXPECTED_HANDOFF_KEYS)}, got {sorted(handoff)}"
        )
    expected = {
        "stage": stage["id"],
        "status": "complete",
        "source_skill": stage["source_skill"]["name"],
        "output_skill": stage["output_skill"]["name"],
        "outputs": [stage["output_skill"]["path"]],
    }
    for key, value in expected.items():
        if handoff.get(key) != value:
            raise VerificationError(
                f"{stage['id']}: handoff {key} mismatch: "
                f"expected={value!r} actual={handoff.get(key)!r}"
            )
    validation = handoff.get("validation")
    if not isinstance(validation, dict) or set(validation) != EXPECTED_VALIDATION_KEYS:
        raise VerificationError(
            f"{stage['id']}: validation keys must be exactly "
            f"{sorted(EXPECTED_VALIDATION_KEYS)}"
        )
    command = validation.get("command")
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(value, str) for value in command)
        or validation.get("status") != "pass"
    ):
        raise VerificationError(
            f"{stage['id']}: handoff validation must contain a passing command"
        )
    completed_at = handoff.get("completed_at")
    if not isinstance(completed_at, str):
        raise VerificationError(f"{stage['id']}: completed_at must be a string")
    try:
        datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise VerificationError(
            f"{stage['id']}: completed_at is not ISO-8601"
        ) from exc


def verify_stage(
    plan: dict[str, Any],
    project_root: Path,
    stage_id: str,
    source_skill_root: Path,
) -> dict[str, Any]:
    stages = validate_manifest_shape(plan, project_root)
    stage = next((item for item in stages if item["id"] == stage_id), None)
    if stage is None:
        raise VerificationError(f"unknown stage: {stage_id}")

    declared_source = Path(stage["source_skill"]["path"]).resolve()
    actual_source = source_skill_root.resolve()
    if actual_source != declared_source:
        raise VerificationError(
            f"{stage_id}: --source-skill-root differs from manifest: "
            f"actual={actual_source} expected={declared_source}"
        )
    actual_source_hash = tree_digest(actual_source)
    if actual_source_hash != stage["source_skill"]["sha256"]:
        raise VerificationError(
            f"{stage_id}: source Skill changed before final gate"
        )

    target_root = bounded_path(project_root, stage["output_skill"]["path"])
    source_files = relative_file_set(actual_source)
    target_files = relative_file_set(target_root)
    if source_files != target_files:
        raise VerificationError(
            f"{stage_id}: target file set differs from source: "
            f"source={source_files} target={target_files}"
        )
    empty_files = [
        value for value in target_files if (target_root / value).stat().st_size == 0
    ]
    if empty_files:
        raise VerificationError(f"{stage_id}: target has empty files: {empty_files}")

    source_md = actual_source / "SKILL.md"
    target_md = target_root / "SKILL.md"
    frontmatter = parse_frontmatter(target_md)
    if set(frontmatter) != {"name", "description"}:
        raise VerificationError(
            f"{stage_id}: target frontmatter keys must be name and description only"
        )
    target_name = stage["output_skill"]["name"]
    if frontmatter["name"] != target_name:
        raise VerificationError(
            f"{stage_id}: target frontmatter name must be {target_name}"
        )
    if not frontmatter["description"]:
        raise VerificationError(f"{stage_id}: target description is empty")

    source_text = source_md.read_text(encoding="utf-8")
    target_text = target_md.read_text(encoding="utf-8")
    source_headings = heading_sequence(source_md)
    target_headings = heading_sequence(target_md)
    if target_headings != source_headings:
        raise VerificationError(
            f"{stage_id}: ordered H2 headings differ from source: "
            f"source={source_headings} target={target_headings}"
        )
    source_size = source_md.stat().st_size
    target_size = target_md.stat().st_size
    ratio = target_size / max(source_size, 1)
    anomaly_signals: list[str] = []
    if ratio < 0.65 or ratio > 1.50:
        anomaly_signals.append(
            f"SKILL.md size ratio {ratio:.3f} is outside [0.65, 1.50]"
        )
    overall_fidelity = fidelity_ratio(source_text, target_text)
    if overall_fidelity < 0.50:
        anomaly_signals.append(
            f"normalized source-text fidelity {overall_fidelity:.3f} "
            "is below 0.50"
        )
    source_sections = h2_sections(source_text)
    target_sections = h2_sections(target_text)
    section_fidelity: list[dict[str, Any]] = []
    for (source_heading, source_body), (target_heading, target_body) in zip(
        source_sections,
        target_sections,
        strict=True,
    ):
        if not target_body:
            raise VerificationError(
                f"{stage_id}: target section is empty: {target_heading}"
            )
        section_size_ratio = len(target_body) / max(len(source_body), 1)
        section_ratio = fidelity_ratio(source_body, target_body)
        if section_size_ratio < 0.35 or section_size_ratio > 1.80:
            anomaly_signals.append(
                f"section {target_heading!r} size ratio "
                f"{section_size_ratio:.3f} is outside [0.35, 1.80]"
            )
        if section_ratio < 0.30:
            anomaly_signals.append(
                f"section {target_heading!r} normalized fidelity "
                f"{section_ratio:.3f} is below 0.30"
            )
        section_fidelity.append(
            {
                "heading": source_heading,
                "size_ratio": round(section_size_ratio, 4),
                "fidelity": round(section_ratio, 4),
            }
        )
    source_fences = len(re.findall(r"^```", source_text, flags=re.MULTILINE))
    target_fences = len(re.findall(r"^```", target_text, flags=re.MULTILINE))
    if target_fences != source_fences:
        raise VerificationError(
            f"{stage_id}: fenced-block delimiter count differs from source: "
            f"source={source_fences} target={target_fences}"
        )
    source_constraints = constraint_count(source_text)
    target_constraints = constraint_count(target_text)
    minimum_constraints = max(1, (source_constraints * 2 + 2) // 3)
    if target_constraints < minimum_constraints:
        raise VerificationError(
            f"{stage_id}: target weakens explicit constraint density: "
            f"source={source_constraints} target={target_constraints} "
            f"minimum={minimum_constraints}"
        )
    validate_local_links(target_md)

    agent_text = (target_root / "agents/openai.yaml").read_text(encoding="utf-8")
    for key in (
        "interface:",
        "display_name:",
        "short_description:",
        "default_prompt:",
    ):
        if key not in agent_text:
            raise VerificationError(
                f"{stage_id}: agents/openai.yaml is missing {key}"
            )
    if f"${target_name}" not in agent_text:
        raise VerificationError(
            f"{stage_id}: agents/openai.yaml does not invoke ${target_name}"
        )

    combined = target_text + "\n" + agent_text
    required_groups = {
        "project source": ("pra2026-bh408",),
        "model": ("Qwen3.5", "Qwen"),
        "runtime": ("vLLM", "PRA"),
        "accelerator": ("ROCm", "DCU", "HIP"),
    }
    missing_groups = [
        label
        for label, markers in required_groups.items()
        if not any(marker in combined for marker in markers)
    ]
    if missing_groups:
        raise VerificationError(
            f"{stage_id}: target lacks current-project bindings: {missing_groups}"
        )
    if "/workspace/VisiPrune" in combined:
        raise VerificationError(
            f"{stage_id}: target retains forbidden old absolute path"
        )
    source_invocation = f"${stage['source_skill']['name']}"
    if source_invocation in combined:
        raise VerificationError(
            f"{stage_id}: target still invokes source Skill {source_invocation}"
        )
    unresolved_legacy_tools = [
        marker
        for marker in ("Nsight", "CUPTI", "NVTX", "CUDA")
        if marker in combined
    ]
    if unresolved_legacy_tools and not re.search(
        r"\b(?:runtime|discover|resolve|locate\s+equivalent|"
        r"verify\s+(?:an\s+)?equivalent|unresolved)\b",
        combined,
        flags=re.IGNORECASE,
    ):
        raise VerificationError(
            f"{stage_id}: legacy tool concepts remain without explicit runtime "
            f"resolution: {unresolved_legacy_tools}"
        )

    handoff_path = bounded_path(project_root, stage["handoff"])
    verify_handoff(handoff_path, stage)
    return {
        "mode": "stage",
        "stage": stage_id,
        "source_skill": stage["source_skill"]["name"],
        "output_skill": target_name,
        "file_set": target_files,
        "skill_md_size_ratio": round(ratio, 4),
        "normalized_fidelity": round(overall_fidelity, 4),
        "section_fidelity": section_fidelity,
        "anomaly_signals": anomaly_signals,
        "constraint_counts": {
            "source": source_constraints,
            "target": target_constraints,
        },
        "handoff": str(handoff_path),
    }


def verify_gap_handoff(
    handoff_path: Path,
    stage: dict[str, Any],
) -> None:
    handoff = load_json(handoff_path)
    if not isinstance(handoff, dict):
        raise VerificationError(
            f"P05 handoff must be an object: {handoff_path}"
        )
    if set(handoff) != EXPECTED_GAP_HANDOFF_KEYS:
        raise VerificationError(
            "P05 gap handoff keys must be exactly "
            f"{sorted(EXPECTED_GAP_HANDOFF_KEYS)}, got {sorted(handoff)}"
        )
    expected = {
        "stage": "P05",
        "status": "complete",
        "authority_type": "workflow_gap",
        "workflow_authority": stage["workflow_authority"]["path"],
        "output_skill": stage["output_skill"]["name"],
        "outputs": [stage["output_skill"]["path"]],
    }
    for key, value in expected.items():
        if handoff.get(key) != value:
            raise VerificationError(
                f"P05 gap handoff {key} mismatch: "
                f"expected={value!r} actual={handoff.get(key)!r}"
            )
    validation = handoff.get("validation")
    if (
        not isinstance(validation, dict)
        or set(validation) != EXPECTED_VALIDATION_KEYS
        or not isinstance(validation.get("command"), list)
        or not validation["command"]
        or any(
            not isinstance(value, str)
            for value in validation["command"]
        )
        or validation.get("status") != "pass"
    ):
        raise VerificationError(
            "P05 gap handoff validation must contain only a passing command"
        )
    completed_at = handoff.get("completed_at")
    if not isinstance(completed_at, str):
        raise VerificationError("P05 completed_at must be a string")
    try:
        datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise VerificationError(
            "P05 completed_at is not ISO-8601"
        ) from exc


def verify_gap_stage(
    plan: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    stages = validate_manifest_shape(plan, project_root)
    stage = next(
        item for item in stages if item["id"] == "P05"
    )
    output = stage["output_skill"]
    target_root = bounded_path(project_root, output["path"])
    target_files = relative_file_set(target_root)
    if target_files != output["file_set"]:
        raise VerificationError(
            "P05 target file set must exactly match the declared standalone "
            f"Skill set: expected={output['file_set']} actual={target_files}"
        )
    empty_files = [
        value
        for value in target_files
        if (target_root / value).stat().st_size == 0
    ]
    if empty_files:
        raise VerificationError(f"P05 target has empty files: {empty_files}")

    skill_md = target_root / "SKILL.md"
    agent_yaml = target_root / "agents/openai.yaml"
    frontmatter = parse_frontmatter(skill_md)
    if set(frontmatter) != {"name", "description"}:
        raise VerificationError(
            "P05 Skill frontmatter keys must be name and description only"
        )
    if frontmatter["name"] != output["name"]:
        raise VerificationError(
            f"P05 Skill frontmatter name must be {output['name']}"
        )
    if not frontmatter["description"]:
        raise VerificationError("P05 Skill description is empty")
    validate_local_links(skill_md)

    skill_text = skill_md.read_text(encoding="utf-8")
    agent_text = agent_yaml.read_text(encoding="utf-8")
    for marker in (
        "interface:",
        "display_name:",
        "short_description:",
        "default_prompt:",
    ):
        if marker not in agent_text:
            raise VerificationError(
                f"P05 agents/openai.yaml is missing {marker}"
            )
    if f"${output['name']}" not in agent_text:
        raise VerificationError(
            "P05 agents/openai.yaml must invoke the generated hardware Skill"
        )

    combined = skill_text + "\n" + agent_text
    required_groups: dict[str, tuple[str, ...]] = {
        "Qwen model": ("Qwen3.5", "Qwen"),
        "ROCm/DCU/HIP accelerator": ("ROCm", "DCU", "HIP"),
        "hipprof implementation": ("hipprof",),
        "PMC replay modes": ("pmc-read", "pmc-write"),
        "representative process scope": ("representative", "代表"),
        "ownership chain": ("HIPTX", "HIPOPS"),
        "strict event join": ("event_id",),
        "kernel-family projection": ("matched_kernel_family",),
        "replay boundary": ("replay",),
        "coverage": ("coverage", "覆盖"),
        "partial failure state": ("partial",),
        "missing failure state": ("missing",),
        "activity metric": ("activity",),
        "matrix-core proxy": ("matrix", "Matrix"),
        "L2 metric": ("L2",),
        "occupancy bound": ("occupancy",),
        "stall proxy": ("stall",),
        "current binding evidence": ("pra2026-bh408",),
    }
    missing_groups = [
        label
        for label, markers in required_groups.items()
        if not any(marker in combined for marker in markers)
    ]
    if missing_groups:
        raise VerificationError(
            "P05 generated Skill omits required Workflow-gap semantics: "
            f"{missing_groups}"
        )
    required_exact_markers = (
        "pmc",
        "pmc-read",
        "pmc-write",
        "HIPTX",
        "HIPOPS",
        "event_id",
        "matched_kernel_family",
    )
    missing_exact_markers = [
        marker for marker in required_exact_markers if marker not in combined
    ]
    if missing_exact_markers:
        raise VerificationError(
            "P05 generated Skill omits required exact hardware/join markers: "
            f"{missing_exact_markers}"
        )
    if not re.search(
        r"(?:non[- ]?replay|非\s*replay).{0,120}(?:timing|latency|计时|时延)"
        r"|(?:timing|latency|计时|时延).{0,120}(?:non[- ]?replay|非\s*replay)",
        combined,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        raise VerificationError(
            "P05 must preserve the non-replay timing/latency boundary"
        )
    if not re.search(
        r"(?:not|never|不得|不能|不是).{0,100}"
        r"(?:fresh|new run|本轮|本次|新运行).{0,40}(?:evidence|证据|结果)"
        r"|(?:fresh|new run|本轮|本次|新运行).{0,40}"
        r"(?:evidence|证据|结果).{0,100}(?:not|never|不得|不能|不是)",
        combined,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        raise VerificationError(
            "P05 must forbid treating binding/example evidence as fresh run evidence"
        )
    if not re.search(
        r"(?:当次|current|runtime|handoff).{0,160}(?:分母|denominator|expected)"
        r"|(?:分母|denominator|expected).{0,160}(?:当次|current|runtime|handoff)",
        combined,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        raise VerificationError(
            "P05 must derive completion denominators from the current handoff"
        )
    for forbidden in (
        "/workspace/VisiPrune",
        "CUDA_VISIBLE_DEVICES",
        "--nvtx-include",
    ):
        if forbidden in combined:
            raise VerificationError(
                f"P05 retains forbidden old-project binding: {forbidden}"
            )
    forbidden_invocations = re.findall(
        r"\$(?:visipruner-[a-z0-9-]+|"
        r"qwen-dcu-process-performance-breakdown)\b",
        combined,
        flags=re.IGNORECASE,
    )
    if forbidden_invocations:
        raise VerificationError(
            "P05 must not invoke a source/P03 Skill in place of the hardware "
            f"capability: {sorted(set(forbidden_invocations))}"
        )

    authority = stage["workflow_authority"]
    authority_path = require_file(project_root, authority["path"])
    if sha256_file(authority_path) != authority["sha256"]:
        raise VerificationError("P05 Workflow authority changed before gate")
    for record in stage["binding_evidence"]:
        evidence_path = project_path(project_root, record["path"])
        if (
            not evidence_path.is_file()
            or sha256_file(evidence_path) != record["sha256"]
        ):
            raise VerificationError(
                "P05 binding evidence changed before gate: "
                f"{record['path']}"
            )

    handoff_path = bounded_path(project_root, stage["handoff"])
    verify_gap_handoff(handoff_path, stage)
    return {
        "mode": "stage",
        "stage": "P05",
        "kind": "workflow_gap_skill_generation",
        "authority_type": "workflow_gap",
        "workflow_authority": authority["path"],
        "output_skill": output["name"],
        "file_set": target_files,
        "binding_evidence_count": len(stage["binding_evidence"]),
        "handoff": str(handoff_path),
    }


def verify_workflow05_gap_stage(
    plan: dict[str, Any],
    project_root: Path,
    stage_id: str,
) -> dict[str, Any]:
    stages = validate_manifest_shape(plan, project_root)
    stage = next(item for item in stages if item["id"] == stage_id)
    output = stage["output_skill"]
    target_root = bounded_path(project_root, output["path"])
    target_files = relative_file_set(target_root)
    if target_files != output["file_set"]:
        raise VerificationError(
            f"{stage_id}: exact Skill file set mismatch: {target_files}"
        )
    empty = [
        value for value in target_files
        if (target_root / value).stat().st_size == 0
    ]
    if empty:
        raise VerificationError(f"{stage_id}: empty target files: {empty}")

    skill_md = target_root / "SKILL.md"
    agent_yaml = target_root / "agents/openai.yaml"
    frontmatter = parse_frontmatter(skill_md)
    if set(frontmatter) != {"name", "description"}:
        raise VerificationError(f"{stage_id}: frontmatter keys must be name/description")
    if frontmatter.get("name") != output["name"] or not frontmatter.get("description"):
        raise VerificationError(f"{stage_id}: frontmatter metadata mismatch")
    validate_local_links(skill_md)

    skill_text = skill_md.read_text(encoding="utf-8")
    lower = skill_text.casefold()
    headings = {
        match.group(1).strip().casefold()
        for match in re.finditer(r"^##\s+(.+?)\s*$", skill_text, re.MULTILINE)
    }
    missing_sections = [
        section for section in stage["required_sections"]
        if section.casefold() not in headings
    ]
    if missing_sections:
        raise VerificationError(
            f"{stage_id}: missing required sections: {missing_sections}"
        )
    missing_markers = [
        marker for marker in stage["required_markers"]
        if marker.casefold() not in lower
    ]
    if missing_markers:
        raise VerificationError(
            f"{stage_id}: missing capability markers: {missing_markers}"
        )
    if not ("runtime discovery" in lower or "runtime-resolved" in lower):
        raise VerificationError(f"{stage_id}: unresolved bindings are not runtime-deferred")
    for forbidden in (
        "/workspace/visiprune",
        "qwen35-core-attribution-20260729-01",
        "unscheduled_workflows",
        "no_authoritative_target_skill",
    ):
        if forbidden in lower:
            raise VerificationError(f"{stage_id}: forbidden stale/omission marker: {forbidden}")
    if re.search(r"\b(?:todo|tbd|placeholder)\b", lower):
        raise VerificationError(f"{stage_id}: placeholder text remains")

    agent_text = agent_yaml.read_text(encoding="utf-8")
    for marker in ("interface:", "display_name:", "short_description:", "default_prompt:"):
        if marker not in agent_text:
            raise VerificationError(f"{stage_id}: agents/openai.yaml omits {marker}")
    if f"${output['name']}" not in agent_text:
        raise VerificationError(f"{stage_id}: agent default_prompt does not invoke target Skill")

    authority = stage["workflow_authority"]
    if sha256_file(require_file(project_root, authority["path"])) != authority["sha256"]:
        raise VerificationError(f"{stage_id}: Workflow authority changed before gate")
    for record in stage["binding_evidence"]:
        path = project_path(project_root, record["path"])
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise VerificationError(f"{stage_id}: binding evidence changed: {record['path']}")

    handoff_path = require_file(project_root, stage["handoff"])
    handoff = load_json(handoff_path)
    if not isinstance(handoff, dict) or set(handoff) != EXPECTED_GAP_HANDOFF_KEYS:
        raise VerificationError(f"{stage_id}: minimal gap handoff schema mismatch")
    expected = {
        "stage": stage_id,
        "status": "complete",
        "authority_type": "workflow_gap",
        "workflow_authority": authority,
        "output_skill": output["name"],
        "outputs": [output["path"]],
    }
    for key, value in expected.items():
        if handoff.get(key) != value:
            raise VerificationError(f"{stage_id}: handoff {key} mismatch")
    validation = handoff.get("validation")
    if (
        not isinstance(validation, dict)
        or set(validation) != EXPECTED_VALIDATION_KEYS
        or validation.get("status") != "pass"
        or not isinstance(validation.get("command"), list)
        or not validation["command"]
    ):
        raise VerificationError(f"{stage_id}: handoff validation is not passing")
    completed_at = handoff.get("completed_at")
    if not isinstance(completed_at, str):
        raise VerificationError(f"{stage_id}: completed_at is missing")
    try:
        datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise VerificationError(f"{stage_id}: completed_at is not ISO-8601") from exc
    return {
        "mode": "stage",
        "stage": stage_id,
        "kind": "workflow_gap_skill_generation",
        "workflow_authority": authority,
        "output_skill": output["name"],
        "file_set": target_files,
        "binding_evidence_count": len(stage["binding_evidence"]),
        "handoff": str(handoff_path),
    }


def runtime_goal_ids(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    goals = payload.get("goals")
    if not isinstance(goals, list):
        return []
    result: list[str] = []
    for goal in goals:
        if isinstance(goal, str):
            result.append(goal)
        elif isinstance(goal, dict) and isinstance(goal.get("id"), str):
            result.append(goal["id"])
    return result


def runtime_snapshot(project_root: Path) -> set[str]:
    root = project_root / "perf_trace/runtime"
    if not root.exists():
        return set()
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def verify_scheduler_handoff(handoff_path: Path) -> None:
    handoff = load_json(handoff_path)
    expected = {
        "schema_version": 1,
        "stage_id": SCHEDULER_STAGE_ID,
        "status": "complete",
        "outputs": {
            "scheduler": EXPECTED_RUNTIME_OUTPUTS[0],
            "workflow01_05_full": EXPECTED_RUNTIME_OUTPUTS[1],
            "workflow05_existing_evidence": EXPECTED_RUNTIME_OUTPUTS[2],
        },
    }
    if handoff != expected:
        raise VerificationError(f"P12 handoff must exactly match scheduler schema: {handoff_path}")


def verify_scheduler_stage(
    plan: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    stages = validate_manifest_shape(plan, project_root)
    stage = next(item for item in stages if item["id"] == SCHEDULER_STAGE_ID)
    scheduler = require_file(project_root, EXPECTED_RUNTIME_OUTPUTS[0])
    manifests = [require_file(project_root, value) for value in EXPECTED_RUNTIME_OUTPUTS[1:]]
    handoff_path = require_file(project_root, stage["handoff"])
    verify_scheduler_handoff(handoff_path)

    scheduler_text = scheduler.read_text(encoding="utf-8")
    if re.search(r"goal[-_]spec", scheduler_text, flags=re.IGNORECASE):
        raise VerificationError(f"{scheduler}: must use target Skills directly without goal-spec")
    if re.search(r"unscheduled_workflows|no_authoritative_target_skill", scheduler_text, flags=re.IGNORECASE):
        raise VerificationError(f"{scheduler}: contains an omitted-capability marker")
    try:
        module = ast.parse(scheduler_text, filename=str(scheduler))
    except SyntaxError as exc:
        raise VerificationError(f"{scheduler}: Python syntax error: {exc}") from exc
    persistent = False
    for node in ast.walk(module):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if (
                isinstance(key, ast.Constant)
                and key.value == "ephemeral"
                and isinstance(value, ast.Constant)
                and value.value is False
            ):
                persistent = True
    if not persistent:
        raise VerificationError(f"{scheduler}: must create non-ephemeral runtime threads")

    expected_manifests = {
        branch["manifest"]: {
            "schema_version": 1,
            "branch": branch["branch"],
            "goals": branch["goals"],
            "bindings": branch["bindings"],
            "requires": branch["requires"],
        }
        for branch in EXPECTED_RUNTIME_BRANCHES
    }
    for manifest_path in manifests:
        relative = manifest_path.relative_to(project_root).as_posix()
        payload = load_json(manifest_path)
        if payload != expected_manifests[relative]:
            raise VerificationError(f"{manifest_path}: runtime manifest contract mismatch")
        for binding in payload["bindings"].values():
            if not isinstance(binding, dict) or set(binding) != {"skill"}:
                raise VerificationError(f"{manifest_path}: binding must contain only skill")
            skill_md = project_root / "perf_trace/skills" / binding["skill"] / "SKILL.md"
            if not skill_md.is_file():
                raise VerificationError(f"runtime manifest Skill is missing: {skill_md}")

    help_result = subprocess.run(
        [sys.executable, str(scheduler), "--help"],
        cwd=project_root,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if help_result.returncode != 0 or "dry-run" not in help_result.stdout or "branch" not in help_result.stdout:
        raise VerificationError(f"{scheduler}: --help failed or omits branch/dry-run")

    before_runtime = runtime_snapshot(project_root)
    before_outputs = {
        value: sha256_file(project_root / value)
        for value in EXPECTED_RUNTIME_OUTPUTS
    }
    dry_runs: dict[str, Any] = {}
    for branch in EXPECTED_RUNTIME_BRANCHES:
        completed = subprocess.run(
            [
                sys.executable,
                str(scheduler),
                "--project-root",
                str(project_root),
                "--branch",
                branch["branch"],
                "--dry-run",
            ],
            cwd=project_root,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            raise VerificationError(
                f"{scheduler}: {branch['branch']} --dry-run failed: {completed.stderr.strip()}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise VerificationError(f"{scheduler}: dry-run output is not JSON") from exc
        if payload.get("status") != "dry_run" or runtime_goal_ids(payload) != branch["goals"]:
            raise VerificationError(f"{scheduler}: dry-run resolved wrong goals for {branch['branch']}")
        if payload.get("app_server_contacted") not in (None, False) or payload.get("goal_created") not in (None, False):
            raise VerificationError(f"{scheduler}: dry-run reports an app-server/Goal side effect")
        dry_runs[branch["branch"]] = payload
    if runtime_snapshot(project_root) != before_runtime:
        raise VerificationError(f"{scheduler}: dry-run changed perf_trace/runtime")
    after_outputs = {
        value: sha256_file(project_root / value)
        for value in EXPECTED_RUNTIME_OUTPUTS
    }
    if after_outputs != before_outputs:
        raise VerificationError(f"{scheduler}: dry-run changed scheduler outputs")
    return {
        "mode": "stage",
        "stage": SCHEDULER_STAGE_ID,
        "kind": "scheduler_generation",
        "scheduler": str(scheduler),
        "manifests": [str(path) for path in manifests],
        "runtime_branches": {
            branch: runtime_goal_ids(payload) for branch, payload in dry_runs.items()
        },
        "persistent_goal_threads": True,
        "handoff": str(handoff_path),
    }

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Statically verify the perf_trace migration control plane, one "
            "adapted/gap Skill, or the P12 Workflow 01-05 runtime scheduler."
        )
    )
    default_root = Path(__file__).resolve().parents[4]
    parser.add_argument("--project-root", default=str(default_root))
    parser.add_argument("--plan")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--control-plane",
        action="store_true",
        help="Validate Phase-1 files and assert that no runtime outputs exist.",
    )
    mode.add_argument(
        "--control-plane-extension",
        action="store_true",
        help=(
            "Validate COMPLETE predecessor P01-P06, preserve P01-P05, and "
            "assert that P07-P12 outputs do not yet exist."
        ),
    )
    mode.add_argument(
        "--stage",
        choices=EXPECTED_STAGE_ORDER,
        help="Validate one completed target Skill and its minimal handoff.",
    )
    parser.add_argument(
        "--source-skill-root",
        help=(
            "Required with P01-P04 --stage; forbidden for gap/P12 stages."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        project_root = Path(args.project_root).resolve()
        if not project_root.is_dir():
            raise VerificationError(
                f"project root is not a directory: {project_root}"
            )
        plan_path = (
            Path(args.plan).resolve()
            if args.plan
            else project_root
            / "perf_trace"
            / "workflows"
            / "project_adaptation"
            / "manifests"
            / "adaptation_plan.json"
        )
        bounded_path(project_root, plan_path)
        plan = load_json(plan_path)
        if not isinstance(plan, dict):
            raise VerificationError("manifest must be a JSON object")
        if args.control_plane:
            details = verify_control_plane(plan, project_root, plan_path)
        elif args.control_plane_extension:
            details = verify_control_plane_extension(plan, project_root, plan_path)
        elif args.stage == "P05":
            if args.source_skill_root:
                raise VerificationError(
                    "--source-skill-root is not valid for P05"
                )
            details = verify_gap_stage(plan, project_root)
        elif args.stage in WORKFLOW05_GAP_STAGE_IDS:
            if args.source_skill_root:
                raise VerificationError(
                    f"--source-skill-root is not valid for {args.stage}"
                )
            details = verify_workflow05_gap_stage(
                plan, project_root, args.stage
            )
        elif args.stage == SCHEDULER_STAGE_ID:
            if args.source_skill_root:
                raise VerificationError(
                    "--source-skill-root is not valid for P12"
                )
            details = verify_scheduler_stage(plan, project_root)
        else:
            if args.stage not in SOURCE_STAGE_IDS or not args.source_skill_root:
                raise VerificationError(
                    "--source-skill-root is required with P01-P04 --stage"
                )
            details = verify_stage(
                plan,
                project_root,
                args.stage,
                Path(args.source_skill_root),
            )
        print(
            json.dumps(
                {"status": "pass", "plan": str(plan_path), **details},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except VerificationError as exc:
        print(
            json.dumps(
                {"status": "fail", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
