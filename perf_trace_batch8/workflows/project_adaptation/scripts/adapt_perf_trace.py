#!/usr/bin/env python3
"""Run migration-only perf-trace Adapt Goals in strict serial order."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
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
    script = Path(__file__).resolve()
    if script.parent.name == "scripts" and script.parent.parent.name == "project_adaptation":
        return script.parents[4]
    return script.parents[2]


def git_value(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AdaptError(
            f"trace target Git query failed ({' '.join(args)}): "
            f"{result.stderr.strip()}"
        )
    return result.stdout.strip()


def verify_plan(
    plan: dict[str, Any],
    project_root: Path,
    *,
    seeded_prefix_length: int = 0,
) -> list[str]:
    if plan.get("schema_version") != 1:
        raise AdaptError("unsupported Adapt plan schema")
    if Path(str(plan.get("project_root"))).resolve() != project_root:
        raise AdaptError("Adapt plan project_root does not match --project-root")
    workflow_root = Path(str(plan.get("workflow_root"))).resolve()
    if not workflow_root.is_dir() or not workflow_root.is_relative_to(project_root):
        raise AdaptError("Adapt plan workflow_root is invalid")
    product_root = Path(str(plan.get("project_adaptation_root"))).resolve()
    expected_product_root = (workflow_root / "project_adaptation").resolve()
    if product_root != expected_product_root:
        raise AdaptError("Adapt plan project_adaptation_root is incorrect")
    trace_target = plan.get("trace_target")
    if not isinstance(trace_target, dict):
        raise AdaptError("Adapt plan trace target is missing")
    trace_target_root = Path(str(trace_target.get("path"))).resolve()
    if not trace_target_root.is_dir() or not trace_target_root.is_relative_to(
        project_root
    ):
        raise AdaptError("Adapt plan trace target root is invalid")
    if git_value(trace_target_root, "rev-parse", "HEAD") != trace_target.get(
        "git_commit"
    ):
        raise AdaptError("trace target Git commit changed; regenerate Adapt product")
    if git_value(trace_target_root, "status", "--porcelain"):
        raise AdaptError("trace target worktree is not clean")
    trace_profile = plan.get("trace_profile")
    if not isinstance(trace_profile, dict):
        raise AdaptError("Adapt plan trace profile is missing")
    verify_pinned_file(trace_profile, "trace profile")
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
    common_goal = plan.get("adapt_common_goal")
    if not isinstance(common_goal, dict):
        raise AdaptError("common Adapt Goal document is missing")
    verify_pinned_file(common_goal, "common Adapt Goal document")
    for index, goal in enumerate(goals, 1):
        if not isinstance(goal, dict) or goal.get("id") != f"A{index:02d}":
            raise AdaptError("Adapt Goal IDs are not a contiguous serial chain")
        expected_predecessor = None if index == 1 else f"A{index - 1:02d}"
        if goal.get("adapt_predecessor") != expected_predecessor:
            raise AdaptError(f"{goal.get('id')}: Adapt predecessor mismatch")
        if goal.get("trace_profile") != trace_profile:
            raise AdaptError(f"{goal.get('id')}: trace profile binding mismatch")
        goal_document = goal.get("adapt_goal_document")
        if not isinstance(goal_document, dict):
            raise AdaptError(f"{goal.get('id')}: Adapt Goal document is missing")
        verify_pinned_file(goal_document, f"{goal.get('id')} Adapt Goal document")
        workflow = goal.get("workflow_input")
        if not isinstance(workflow, dict):
            raise AdaptError(f"{goal.get('id')}: workflow input is missing")
        if index > seeded_prefix_length:
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
            elif index > seeded_prefix_length:
                verify_pinned_file(reference, f"{goal.get('id')} reference skill")
        output_kind = goal.get("output_kind", "project_skill")
        if output_kind == "project_skill":
            for key in (
                "output_skill",
                "output_skill_path",
                "runtime_branch",
                "runtime_goal",
                "runtime_predecessors",
            ):
                if key not in goal:
                    raise AdaptError(f"{goal.get('id')}: project-skill output is malformed")
        elif output_kind == "runtime_scheduler_bundle":
            if index != len(goals):
                raise AdaptError("runtime scheduler bundle must be the final Adapt Goal")
            bundle = goal.get("runtime_scheduler_bundle")
            if not isinstance(bundle, dict):
                raise AdaptError(f"{goal.get('id')}: scheduler bundle output is missing")
            for key in (
                "scheduler_path",
                "manifest_path",
                "config_path",
                "runtime_root",
                "project_skill_root",
            ):
                value = bundle.get(key)
                if not isinstance(value, str) or not Path(value).resolve().is_relative_to(
                    project_root
                ):
                    raise AdaptError(f"{goal.get('id')}: invalid scheduler bundle {key}")
            scheduled = goal.get("scheduled_runtime_goals")
            skills = goal.get("scheduled_project_skills")
            if scheduled != [f"R{value:02d}" for value in range(1, 11)]:
                raise AdaptError(f"{goal.get('id')}: runtime Goal order is invalid")
            if not isinstance(skills, list) or len(skills) != len(scheduled):
                raise AdaptError(f"{goal.get('id')}: scheduled project skills are invalid")
        else:
            raise AdaptError(
                f"{goal.get('id')}: unsupported output kind {output_kind!r}"
            )
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
        goal["trace_target_root"],
    ]
    predecessor_value = (
        ",".join(goal["runtime_predecessors"])
        if goal["runtime_predecessors"]
        else "none"
    )
    required_literals.append(f"runtime_predecessors={predecessor_value}")
    trace_profile = goal.get("trace_profile")
    if not isinstance(trace_profile, dict):
        raise AdaptError(f"{goal['id']}: trace profile is missing")
    required_literals.extend(trace_profile.get("required_skill_literals", []))
    missing = [value for value in required_literals if value not in text]
    if missing:
        raise AdaptError(
            f"{goal['id']}: project skill lacks serial runtime contract: {missing}"
        )
    forbidden = [
        value
        for value in trace_profile.get("forbidden_skill_literals", [])
        if value in text
    ]
    if forbidden:
        raise AdaptError(
            f"{goal['id']}: project skill contradicts trace profile: {forbidden}"
        )
    return path, sha256_file(path)


def skill_tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise AdaptError(f"project skill tree is empty: {root}")
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def validate_runtime_scheduler_bundle(
    *, goal: dict[str, Any], handoff: dict[str, Any]
) -> dict[str, Any]:
    planned = goal["runtime_scheduler_bundle"]
    observed = handoff.get("runtime_scheduler_bundle")
    if not isinstance(observed, dict):
        raise AdaptError(f"{goal['id']}: runtime_scheduler_bundle is missing")
    paths: dict[str, Path] = {}
    for key, plan_key in (
        ("scheduler", "scheduler_path"),
        ("manifest", "manifest_path"),
        ("config", "config_path"),
    ):
        record = observed.get(key)
        if not isinstance(record, dict):
            raise AdaptError(f"{goal['id']}: bundle {key} record is missing")
        path = Path(str(record.get("path"))).resolve()
        if path != Path(str(planned[plan_key])).resolve() or not path.is_file():
            raise AdaptError(f"{goal['id']}: bundle {key} path mismatch")
        if record.get("sha256") != sha256_file(path):
            raise AdaptError(f"{goal['id']}: bundle {key} hash mismatch")
        paths[key] = path
    if not os.access(paths["scheduler"], os.X_OK):
        raise AdaptError(f"{goal['id']}: runtime scheduler is not executable")

    prefix = handoff.get("project_skill_prefix")
    expected_skills = goal["scheduled_project_skills"]
    if not isinstance(prefix, list) or len(prefix) != len(expected_skills):
        raise AdaptError(f"{goal['id']}: project-skill prefix is missing")
    tree_hashes: dict[str, str] = {}
    for expected, record in zip(expected_skills, prefix):
        if not isinstance(record, dict):
            raise AdaptError(f"{goal['id']}: project-skill prefix is malformed")
        skill_path = Path(expected["path"]).resolve()
        if (
            record.get("adapt_goal") != expected["adapt_goal"]
            or record.get("runtime_goal") != expected["runtime_goal"]
            or record.get("name") != expected["name"]
            or Path(str(record.get("path"))).resolve() != skill_path
            or record.get("sha256") != sha256_file(skill_path)
        ):
            raise AdaptError(f"{goal['id']}: project-skill prefix provenance mismatch")
        tree_hash = skill_tree_sha256(skill_path.parent)
        if record.get("tree_sha256") != tree_hash:
            raise AdaptError(f"{goal['id']}: project-skill tree hash mismatch")
        tree_hashes[expected["name"]] = tree_hash

    manifest = load_json(paths["manifest"])
    expected_goals = goal["scheduled_runtime_goals"]
    if (
        manifest.get("branch") != goal["scheduled_runtime_branch"]
        or manifest.get("goals") != expected_goals
    ):
        raise AdaptError(f"{goal['id']}: runtime manifest branch/Goal order mismatch")
    bindings = manifest.get("bindings")
    if not isinstance(bindings, dict):
        raise AdaptError(f"{goal['id']}: runtime manifest bindings are missing")
    for expected in expected_skills:
        binding = bindings.get(expected["runtime_goal"])
        if not isinstance(binding, dict) or binding.get("skill") != expected["name"]:
            raise AdaptError(f"{goal['id']}: runtime manifest skill binding mismatch")

    config = load_json(paths["config"])
    if Path(str(config.get("trace_target_root"))).resolve() != Path(
        goal["trace_target_root"]
    ).resolve():
        raise AdaptError(f"{goal['id']}: runtime config trace target mismatch")
    trace_profile = goal["trace_profile"]
    if (
        config.get("trace_profile_id") != trace_profile["profile_id"]
        or config.get("trace_profile_sha256") != trace_profile["sha256"]
        or Path(str(config.get("trace_profile_path"))).resolve()
        != Path(trace_profile["path"]).resolve()
    ):
        raise AdaptError(f"{goal['id']}: runtime config trace profile mismatch")
    bootstrap = config.get("r01_bootstrap")
    if not isinstance(bootstrap, dict):
        raise AdaptError(f"{goal['id']}: R01 runtime bootstrap is missing")
    selection = bootstrap.get("request_selection")
    model = bootstrap.get("model")
    runtime = bootstrap.get("runtime_executable")
    service = bootstrap.get("service")
    attempt_policy = bootstrap.get("attempt_id_policy")
    assignment_policy = bootstrap.get("assignment_policy")
    selected = selection.get("records") if isinstance(selection, dict) else None
    sha256_pattern = re.compile(r"[0-9a-f]{64}")
    model_directory = (
        Path(str(model.get("directory"))).resolve()
        if isinstance(model, dict)
        else None
    )
    model_config = (
        Path(str(model.get("config_path"))).resolve()
        if isinstance(model, dict)
        else None
    )
    runtime_path = (
        Path(str(runtime.get("path"))).resolve()
        if isinstance(runtime, dict)
        else None
    )
    if (
        bootstrap.get("required_before_r01_goal_creation") is not True
        or not isinstance(selection, dict)
        or selection.get("request_count") != 8
        or selection.get("selected_line_numbers") != list(range(1, 9))
        or not isinstance(selected, list)
        or len(selected) != 8
        or not all(
            isinstance(item, dict)
            and isinstance(item.get("request_id"), str)
            and item.get("row_index") == index - 1
            and item.get("line_number") == index
            and item.get("ordinal") == index
            and sha256_pattern.fullmatch(str(item.get("raw_line_sha256")))
            is not None
            and sha256_pattern.fullmatch(str(item.get("canonical_json_sha256")))
            is not None
            for index, item in enumerate(selected, 1)
        )
        or sha256_pattern.fullmatch(
            str(selection.get("ordered_sequence_canonical_sha256"))
        )
        is None
        or selection.get("request_expansion_allowed") is not False
        or selection.get("request_oversampling_allowed") is not False
        or selection.get("request_shuffle_allowed") is not False
        or selection.get("prompt_synthesis_allowed") is not False
        or not isinstance(model, dict)
        or model_directory is None
        or not model_directory.is_dir()
        or model_config is None
        or not model_config.is_file()
        or sha256_pattern.fullmatch(str(model.get("config_sha256"))) is None
        or sha256_file(model_config) != model.get("config_sha256")
        or not isinstance(runtime, dict)
        or runtime_path is None
        or not runtime_path.is_file()
        or not os.access(runtime_path, os.X_OK)
        or sha256_pattern.fullmatch(str(runtime.get("sha256"))) is None
        or sha256_file(runtime_path) != runtime.get("sha256")
        or not isinstance(runtime.get("version"), str)
        or not runtime["version"]
        or not isinstance(service, dict)
        or not isinstance(service.get("port"), int)
        or not 1 <= service["port"] <= 65535
        or service.get("port_policy") != "fixed_no_dynamic_selection"
        or not isinstance(attempt_policy, dict)
        or not isinstance(attempt_policy.get("format"), str)
        or not attempt_policy["format"]
        or not isinstance(attempt_policy.get("initial_attempt_ordinal"), int)
        or attempt_policy.get("must_be_nonempty") is not True
        or attempt_policy.get("reuse_allowed") is not False
        or not isinstance(assignment_policy, dict)
        or assignment_policy.get(
            "generated_and_validated_before_formal_r01_goal_creation"
        )
        is not True
        or assignment_policy.get(
            "complete_bootstrap_injected_into_formal_r01_goal_objective"
        )
        is not False
        or assignment_policy.get(
            "compact_hash_verifiable_identity_summary_injected_into_formal_r01_goal_objective"
        )
        is not True
        or assignment_policy.get("injected_into_r01_turn_assignment") is not True
        or assignment_policy.get(
            "clock_and_hipprof_use_identical_request_manifest"
        )
        is not True
        or assignment_policy.get("runtime_discovery_allowed") is not False
    ):
        raise AdaptError(f"{goal['id']}: R01 runtime bootstrap is malformed")

    project_root = paths["scheduler"].parents[2]
    command = [
        str(paths["scheduler"]),
        "--project-root",
        str(project_root),
        "--branch",
        goal["scheduled_runtime_branch"],
        "--dry-run",
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise AdaptError(
            f"{goal['id']}: runtime scheduler dry run failed: {result.stderr.strip()}"
        )
    try:
        dry_run = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AdaptError(f"{goal['id']}: runtime scheduler dry run is not JSON") from exc
    if not isinstance(dry_run, dict):
        raise AdaptError(f"{goal['id']}: runtime scheduler dry run is malformed")
    dry_target = dry_run.get("trace_target_root")
    if dry_target is None and isinstance(dry_run.get("user_parameters"), dict):
        dry_target = dry_run["user_parameters"].get("trace_target_root")
    exact = {
        "status": "dry_run",
        "dry_run": True,
        "app_server_contacted": False,
        "goal_created": False,
        "branch": goal["scheduled_runtime_branch"],
        "project_skill_root": planned["project_skill_root"],
        "runtime_root": planned["runtime_root"],
    }
    for key, value in exact.items():
        if dry_run.get(key) != value:
            raise AdaptError(f"{goal['id']}: dry-run {key} mismatch")
    if Path(str(dry_target)).resolve() != Path(goal["trace_target_root"]).resolve():
        raise AdaptError(f"{goal['id']}: dry-run trace target mismatch")
    if [item.get("id") for item in dry_run.get("goals", [])] != expected_goals:
        raise AdaptError(f"{goal['id']}: dry-run runtime Goal order mismatch")
    if dry_run.get("skill_tree_sha256") != tree_hashes:
        raise AdaptError(f"{goal['id']}: dry-run project-skill hashes mismatch")
    dry_bootstrap = dry_run.get("r01_bootstrap")
    dry_validation = dry_run.get("r01_bootstrap_validation")
    expected_validation = {
        "complete_ordered_request_selection_manifest_valid": True,
        "stable_request_ids_and_per_record_hashes_valid": True,
        "ordered_sequence_hash_valid": True,
        "model_directory_and_config_hash_valid": True,
        "runtime_executable_hash_and_version_valid": True,
        "attempt_id_nonempty_and_scheduler_generated": True,
        "service_port_fixed": True,
        "generated_before_formal_goal_creation": True,
        "request_expansion_performed": False,
        "formal_goal_objective_within_4000_characters": True,
    }
    if (
        not isinstance(dry_bootstrap, dict)
        or dry_bootstrap.get(
            "generated_and_validated_before_formal_r01_goal_creation"
        )
        is not True
        or not isinstance(dry_bootstrap.get("runtime_binding"), dict)
        or not dry_bootstrap["runtime_binding"].get("runtime_attempt_id")
        or dry_bootstrap.get("request_selection_manifest", {}).get(
            "request_count"
        )
        != 8
        or dry_bootstrap.get("request_selection_manifest", {}).get(
            "request_expansion_performed"
        )
        is not False
        or not isinstance(dry_validation, dict)
        or any(dry_validation.get(key) != value for key, value in expected_validation.items())
    ):
        raise AdaptError(f"{goal['id']}: dry-run R01 runtime bootstrap mismatch")
    recorded_dry_run = observed.get("dry_run")
    if not isinstance(recorded_dry_run, dict) or any(
        recorded_dry_run.get(key) != value
        for key, value in (
            ("status", "dry_run"),
            ("app_server_contacted", False),
            ("goal_created", False),
        )
    ):
        raise AdaptError(f"{goal['id']}: recorded dry-run audit is invalid")
    return observed


def validate_handoff(
    *,
    goal: dict[str, Any],
    handoff_path: Path,
    run_id: str,
    previous_entry: dict[str, Any] | None = None,
    historical_source_provenance: bool = False,
    historical_project_skill_revision_allowed: bool = False,
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
    output_kind = goal.get("output_kind", "project_skill")
    if output_kind == "project_skill":
        skill_path, skill_hash = validate_project_skill(goal)
        project_skill = handoff.get("project_skill")
        if not isinstance(project_skill, dict):
            raise AdaptError(f"{goal['id']}: handoff project_skill is missing")
        identity_matches = (
            project_skill.get("name") == goal["output_skill"]
            and Path(str(project_skill.get("path"))).resolve() == skill_path
        )
        recorded_hash = project_skill.get("sha256")
        hash_matches = recorded_hash == skill_hash
        historical_hash_is_well_formed = (
            historical_project_skill_revision_allowed
            and isinstance(recorded_hash, str)
            and re.fullmatch(r"[0-9a-f]{64}", recorded_hash) is not None
        )
        if not identity_matches or not (hash_matches or historical_hash_is_well_formed):
            raise AdaptError(f"{goal['id']}: handoff project-skill provenance mismatch")
    else:
        validate_runtime_scheduler_bundle(goal=goal, handoff=handoff)
    inputs = handoff.get("inputs")
    if not isinstance(inputs, dict):
        raise AdaptError(f"{goal['id']}: handoff inputs are missing")
    profile_input = inputs.get("trace_profile")
    expected_profile = goal.get("trace_profile")
    if (
        not isinstance(profile_input, dict)
        or not isinstance(expected_profile, dict)
        or profile_input.get("profile_id") != expected_profile.get("profile_id")
        or profile_input.get("sha256") != expected_profile.get("sha256")
        or Path(str(profile_input.get("path"))).resolve()
        != Path(str(expected_profile.get("path"))).resolve()
    ):
        raise AdaptError(f"{goal['id']}: trace-profile provenance mismatch")
    workflow_files = inputs.get("workflow_files")
    expected_workflow = goal["workflow_input"]
    if not isinstance(workflow_files, list) or not any(
        isinstance(item, dict)
        and Path(str(item.get("path"))).resolve()
        == Path(expected_workflow["path"]).resolve()
        and (
            (
                historical_source_provenance
                and isinstance(item.get("sha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is not None
            )
            or item.get("sha256") == expected_workflow["sha256"]
        )
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
            and (
                (
                    historical_source_provenance
                    and isinstance(item.get("sha256"), str)
                    and re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
                    is not None
                )
                or item.get("sha256") == expected_reference["sha256"]
            )
            and item.get("resolution") == expected_reference["resolution"]
            for item in reference_skills
        ):
            raise AdaptError(f"{goal['id']}: reference-skill provenance mismatch")
    if output_kind == "runtime_scheduler_bundle":
        expected_source = goal.get("runtime_scheduler_source")
        observed_source = inputs.get("runtime_scheduler_source")
        if (
            not isinstance(expected_source, dict)
            or not isinstance(observed_source, dict)
            or Path(str(observed_source.get("path"))).resolve()
            != Path(str(expected_source.get("path"))).resolve()
            or observed_source.get("sha256") != expected_source.get("sha256")
        ):
            raise AdaptError(
                f"{goal['id']}: runtime scheduler source provenance mismatch"
            )
    previous = inputs.get("previous_adapt_handoff")
    if goal.get("adapt_predecessor") is None:
        if previous is not None:
            raise AdaptError(f"{goal['id']}: unexpected predecessor handoff")
    else:
        expected_previous_path = (
            Path(str(previous_entry.get("path"))).resolve()
            if isinstance(previous_entry, dict)
            else handoff_path.parent / f"{goal['adapt_predecessor']}.json"
        )
        expected_previous_hash = (
            previous_entry.get("sha256")
            if isinstance(previous_entry, dict)
            else sha256_file(expected_previous_path)
        )
        if (
            not isinstance(previous, dict)
            or Path(str(previous.get("path"))).resolve()
            != expected_previous_path.resolve()
            or previous.get("sha256") != expected_previous_hash
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
        goal["mode"] in {"synthesize_uncovered", "synthesize_runtime_scheduler"}
        or any(
            item["resolution"] == "semantic_fallback"
            for item in goal["reference_skill_inputs"]
        )
    ) and not uncovered:
        raise AdaptError(f"{goal['id']}: uncovered constraints were not recorded")
    if output_kind == "project_skill":
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
    required_validation = (
        (
            "skill_structure_valid",
            "serial_runtime_contract_valid",
            "source_hashes_valid",
        )
        if output_kind == "project_skill"
        else (
            "runtime_scheduler_structure_valid",
            "runtime_scheduler_dry_run_valid",
            "project_skill_prefix_hashes_valid",
            "source_hashes_valid",
        )
    )
    if not isinstance(validation, dict) or not all(
        validation.get(key) is True for key in required_validation
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
        ledger = load_json(ledger_path)
        entries = ledger.get("handoffs")
        if not isinstance(entries, list) or not entries:
            raise AdaptError(f"{goal['id']}: cumulative ledger has no predecessor")
        predecessor_entry = entries[-1]
        if predecessor_entry.get("source_goal") != predecessor:
            raise AdaptError(f"{goal['id']}: cumulative ledger predecessor mismatch")
        predecessor_path = Path(str(predecessor_entry.get("path"))).resolve()
        predecessor_handoff = {
            "path": str(predecessor_path),
            "sha256": predecessor_entry.get("sha256"),
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
    if goal.get("output_kind", "project_skill") == "runtime_scheduler_bundle":
        instructions = [
            "$adapt-workflows",
            "",
            f"只执行收尾迁移 Goal {goal['id']}，不要执行任何 project skill 或 runtime Goal。",
            "这是 runtime 控制面迁移任务，不是性能实验。禁止运行模型、GPU/DCU、profiler、trace、PMC 或报告生成器。",
            "完整读取 hash 锁定的 workflow、Adapt 合同和 runtime_scheduler_source；后者只是迁移源代码，不得用它启动旧项目 runtime。",
            f"目标固定为 {goal['trace_target_root']}，Git commit 固定为 {goal['trace_target_git_commit']}；Adapt 期间只读且不得修改目标 checkout。",
            f"迁移目标 profile 固定为 {goal['trace_profile']['profile_id']}，必须完整读取并 hash 校验 {goal['trace_profile']['path']}；每个 runtime stage 都必须保持该 profile 的 workload 与完整多设备拓扑，串行 stage 绝不等于缩成单卡。",
            "先校验累计 Adapt ledger 的完整 A01-A10 前缀、每个当前 project skill 的文件与 tree hash，以及 A10 直接前驱 handoff。若 seeded 历史 handoff 的 project-skill hash 与当前文件不同，只能视为 A11-only 前的已审计运行期维护；在 validation 与 handoff 中逐项记录 adapt_goal、path、historical_sha256、current_sha256 和 revision reason，绝不能改写历史 handoff。",
            "只能写 plan_goal.runtime_scheduler_bundle 声明的 scheduler/manifest/config 路径，以及 adapt_artifact_root 与 adapt_handoff_output。",
            "生成的 scheduler 必须独立绑定 batch 项目的 skill root、runtime root、固定 trace target、R01-R10 顺序和 handoff gate；不得继续硬编码旧 perf_trace profile。",
            "在创建 R01 Goal 前，scheduler 必须从 profile/target 生成并注入 R01 skill 要求的完整 ordered request-selection manifest、稳定 request IDs/逐记录与序列 hashes、model directory/config hash、runtime executable/hash/version、非空 attempt ID 和固定 service port；禁止把单条 request 在 R01 内扩增。dry-run 必须验证这些 bootstrap bindings 但不得运行模型。",
            "可以且必须只运行生成 scheduler 的 --dry-run；dry-run 不得联系 app-server、创建 Goal、执行 skill 或写 runtime state。",
            "按 adapt-goal-contract.md 写 runtime_scheduler_bundle handoff、project_skill_prefix 与四个 validation=true 字段；两个 execution_performed 字段必须为 false。",
            "handoff 写成且自检通过后才能把正式 Goal 标记 complete；受阻时不得伪造 handoff。",
        ]
    else:
        instructions = [
            "$adapt-workflows",
            "",
            f"只执行迁移 Goal {goal['id']}，不要执行被迁移的 workflow。",
            "这是文本/skill 迁移任务，不是性能实验。禁止运行模型、GPU/DCU、profiler、trace、PMC、报告生成器，也禁止调用产出的 project skill。",
            "完整读取 hash 锁定的 workflow 和 reference SKILL.md；reference skill 只是源文本，不得作为能力调用。",
            f"迁移处理目标固定为 {goal['trace_target_root']}，Git commit 固定为 {goal['trace_target_git_commit']}；只能读取该目标以证明绑定，不得在 Adapt Goal 中执行或修改目标运行时。",
            f"迁移目标 profile 固定为 {goal['trace_profile']['profile_id']}，必须完整读取并 hash 校验 {goal['trace_profile']['path']}；把 profile 的 workload、所有物理设备、rank 映射和并行参数写入 project skill。串行 Goal 只约束阶段顺序，不得缩成单卡。",
            "先校验累计 Adapt ledger 和直接前驱 handoff，再迁移项目、模型、运行时、设备、路径、工具、产物和证据文字。",
            "参考 skill 未覆盖而 workflow 明确要求的过程与约束，封装进本 Goal 指定的新 project skill；不得删减或模糊化。",
            "产出的 project skill 必须包含 references/project-skill-runtime-contract.md 规定的 `## Serial Runtime Contract`，明确串行 runtime predecessor handoff 和 advance gate。",
            "只能修改 plan_goal.output_skill_path 所属 skill 目录，并写 adapt_artifact_root 与 adapt_handoff_output；不得改写前序 skill/handoff/ledger。",
            "完成结构、内容、source hash 和串行 runtime contract 校验后，按 references/adapt-goal-contract.md 写 handoff；两个 execution_performed 字段必须为 false。",
            "handoff 写成且自检通过后才能把当前正式 Goal 标记 complete；受阻时不得伪造 handoff 或跳过。",
        ]
    return "\n".join(
        [*instructions, "", json.dumps(assignment, ensure_ascii=False, indent=2)]
    )


def handoff_ledger_output(
    goal: dict[str, Any], handoff: dict[str, Any]
) -> dict[str, Any]:
    if goal.get("output_kind", "project_skill") == "project_skill":
        return {
            "output_kind": "project_skill",
            "project_skill": handoff["project_skill"],
        }
    return {
        "output_kind": "runtime_scheduler_bundle",
        "runtime_scheduler_bundle": handoff["runtime_scheduler_bundle"],
    }


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
        seed_ledger_path: Path | None,
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
        self.seed_ledger_path = seed_ledger_path
        self.run_dir = (
            Path(str(plan["project_adaptation_root"]))
            / "state/adaptation_runs"
            / run_id
        )
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
            seed_entries: list[dict[str, Any]] = []
            seed_record: dict[str, Any] | None = None
            if self.seed_ledger_path is not None:
                seed = load_json(self.seed_ledger_path)
                raw_entries = seed.get("handoffs")
                if not isinstance(raw_entries, list) or not raw_entries:
                    raise AdaptError("seed ledger contains no completed prefix")
                if len(raw_entries) >= len(goals):
                    raise AdaptError("seed ledger must leave at least one Adapt Goal pending")
                closing_only_seed = (
                    len(raw_entries) == len(goals) - 1
                    and goals[-1].get("output_kind") == "runtime_scheduler_bundle"
                )
                for index, raw_entry in enumerate(raw_entries):
                    if (
                        not isinstance(raw_entry, dict)
                        or raw_entry.get("source_goal") != goals[index]["id"]
                    ):
                        raise AdaptError("seed ledger is not a contiguous plan prefix")
                    handoff_path = Path(str(raw_entry.get("path"))).resolve()
                    if sha256_file(handoff_path) != raw_entry.get("sha256"):
                        raise AdaptError("seed ledger handoff hash mismatch")
                    handoff_value = load_json(handoff_path)
                    validate_handoff(
                        goal=goals[index],
                        handoff_path=handoff_path,
                        run_id=str(handoff_value.get("adapt_run_id")),
                        previous_entry=(seed_entries[-1] if seed_entries else None),
                        historical_source_provenance=True,
                        historical_project_skill_revision_allowed=closing_only_seed,
                    )
                    seed_entries.append(dict(raw_entry))
                seed_record = {
                    "path": str(self.seed_ledger_path),
                    "sha256": sha256_file(self.seed_ledger_path),
                    "adapt_run_id": seed.get("adapt_run_id"),
                    "handoff_count": len(seed_entries),
                }
            self.ledger = {
                "schema_version": 1,
                "adapt_run_id": self.run_id,
                "mode": "serial_migration_only",
                "workflow_execution_performed": False,
                "project_skill_execution_performed": False,
                "handoffs": seed_entries,
            }
            if seed_record is not None:
                self.ledger["seeded_from"] = seed_record
            self.state = {
                "schema_version": 1,
                "adapt_run_id": self.run_id,
                "status": "pending",
                "current_goal": None,
                "seeded_closing_goal_current_skill_revisions_allowed": bool(
                    seed_entries
                    and len(seed_entries) == len(goals) - 1
                    and goals[-1].get("output_kind") == "runtime_scheduler_bundle"
                ),
                "plan_snapshot_sha256": sha256_file(snapshot),
                "goals": {
                    goal["id"]: {
                        "status": (
                            "complete" if index < len(seed_entries) else "pending"
                        ),
                        **({"seeded": True} if index < len(seed_entries) else {}),
                    }
                    for index, goal in enumerate(goals)
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
            handoff_value = load_json(handoff_path)
            validate_handoff(
                goal=goal,
                handoff_path=handoff_path,
                run_id=str(handoff_value.get("adapt_run_id")),
                previous_entry=(entries[index - 1] if index else None),
                historical_source_provenance=bool(
                    self.state.get("goals", {})
                    .get(goal["id"], {})
                    .get("seeded")
                ),
                historical_project_skill_revision_allowed=bool(
                    self.state.get(
                        "seeded_closing_goal_current_skill_revisions_allowed"
                    )
                    and self.state.get("goals", {})
                    .get(goal["id"], {})
                    .get("seeded")
                ),
            )
        while len(entries) < len(goals):
            next_goal = goals[len(entries)]
            pending_handoff = self.handoff_dir / f"{next_goal['id']}.json"
            if not pending_handoff.is_file():
                break
            handoff = validate_handoff(
                goal=next_goal,
                handoff_path=pending_handoff,
                run_id=self.run_id,
                previous_entry=(entries[-1] if entries else None),
            )
            entry = {
                "source_goal": next_goal["id"],
                "status": "complete",
                "path": str(pending_handoff),
                "sha256": sha256_file(pending_handoff),
                **handoff_ledger_output(next_goal, handoff),
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
        if goal.get("output_kind", "project_skill") == "runtime_scheduler_bundle":
            objective = (
                f"Complete closing migration-only Adapt Goal {goal_id}: synthesize "
                "the pinned project-local runtime scheduler bundle after validating "
                "the complete project-skill prefix, write its validated Adapt "
                "handoff, and run only the generated scheduler's no-execution dry run."
            )
        else:
            objective = (
                f"Complete migration-only Adapt Goal {goal_id}: create or update "
                f"${goal['output_skill']} from the pinned workflow/reference text, "
                "write its validated Adapt handoff, and do not execute any runtime "
                "workflow."
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
            goal=goal,
            handoff_path=handoff_path,
            run_id=self.run_id,
            previous_entry=(self.ledger["handoffs"][-1] if self.ledger["handoffs"] else None),
        )
        if sha256_file(self.ledger_path) != ledger_hash:
            raise AdaptError(f"{goal_id}: ledger changed while Goal was running")
        entry = {
            "source_goal": goal_id,
            "status": "complete",
            "path": str(handoff_path),
            "sha256": sha256_file(handoff_path),
            **handoff_ledger_output(goal, handoff),
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
    goals: list[dict[str, Any]] = []
    for goal in plan["goals"]:
        item = {
            "id": goal["id"],
            "adapt_goal_document": goal["adapt_goal_document"],
            "adapt_predecessor": goal["adapt_predecessor"],
            "mode": goal["mode"],
            "output_kind": goal.get("output_kind", "project_skill"),
            "workflow": goal["workflow_input"],
            "trace_profile": goal["trace_profile"],
            "reference_skills": goal["reference_skill_inputs"],
            "advance_only_after": "validated Adapt handoff commit",
        }
        if item["output_kind"] == "project_skill":
            item.update(
                {
                    "output_skill": goal["output_skill"],
                    "output_skill_path": goal["output_skill_path"],
                    "runtime_branch": goal["runtime_branch"],
                    "runtime_goal": goal["runtime_goal"],
                    "runtime_predecessors": goal["runtime_predecessors"],
                }
            )
        else:
            item.update(
                {
                    "runtime_scheduler_bundle": goal["runtime_scheduler_bundle"],
                    "scheduled_runtime_branch": goal["scheduled_runtime_branch"],
                    "scheduled_runtime_goals": goal["scheduled_runtime_goals"],
                    "scheduled_project_skills": goal["scheduled_project_skills"],
                }
            )
        goals.append(item)
    payload = {
        "schema_version": 1,
        "status": "dry_run",
        "plan": str(plan_path),
        "goal_count": len(plan["goals"]),
        "strict_serial": True,
        "workflow_execution_performed": False,
        "project_skill_execution_performed": False,
        "unresolved_reference_skills": unresolved,
        "trace_target": plan["trace_target"],
        "trace_profile": plan["trace_profile"],
        "goals": goals,
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
    parser.add_argument(
        "--seed-ledger",
        help="Start a new run from a verified completed Adapt-ledger prefix.",
    )
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
            else Path(__file__).resolve().parent.parent
            / "manifests/adapt_goals.json"
        )
        plan = load_json(plan_path)
        seed_ledger_path = (
            Path(args.seed_ledger).expanduser().resolve()
            if args.seed_ledger
            else None
        )
        if seed_ledger_path is not None and not seed_ledger_path.is_file():
            raise AdaptError(f"seed ledger is missing: {seed_ledger_path}")
        seeded_prefix_length = 0
        if seed_ledger_path is not None:
            seed_handoffs = load_json(seed_ledger_path).get("handoffs")
            if not isinstance(seed_handoffs, list) or not seed_handoffs:
                raise AdaptError("seed ledger contains no completed prefix")
            seeded_prefix_length = len(seed_handoffs)
        unresolved = verify_plan(
            plan,
            project_root,
            seeded_prefix_length=seeded_prefix_length,
        )
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
        if resume and args.seed_ledger:
            raise AdaptError("--seed-ledger cannot be combined with --resume-run-id")
        if args.seed_ledger and not args.run_id:
            raise AdaptError("--seed-ledger requires an explicit --run-id")
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
            seed_ledger_path=seed_ledger_path,
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
