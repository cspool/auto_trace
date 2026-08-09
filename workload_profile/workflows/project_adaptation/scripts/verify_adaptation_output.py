#!/usr/bin/env python3
"""Lightweight gates for source, Workflow-gap, and scheduler stages."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
WORKLOAD_PROFILE_RELATIVE_ROOT = Path("workload_profile")
TEXT_SUFFIXES = {
    ".md",
    ".markdown",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
}
CURRENT_STACK_MARKERS = ("Qwen3.5", "vLLM", "ROCm", "DCU")
LEGACY_ABSOLUTE_BINDINGS = ("/workspace/VisiPrune",)


class GateFailure(Exception):
    """Raised when a lightweight gate input is invalid."""


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateFailure(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GateFailure(f"invalid JSON file {path}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root: Path) -> str:
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


def project_path(project_root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    resolved_project_root = project_root.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_project_root)
    except ValueError as exc:
        raise GateFailure(
            f"path escapes project root {resolved_project_root}: {value}"
        ) from exc
    return resolved


def workload_profile_root(project_root: Path) -> Path:
    return project_path(project_root, WORKLOAD_PROFILE_RELATIVE_ROOT)


def within_workload_profile(project_root: Path, value: str | Path) -> Path:
    resolved = project_path(project_root, value)
    allowed_root = workload_profile_root(project_root)
    try:
        resolved.relative_to(allowed_root)
    except ValueError as exc:
        raise GateFailure(
            f"path escapes workload_profile root {allowed_root}: {value}"
        ) from exc
    return resolved


def require_file(path: Path, errors: list[str], *, nonempty: bool = True) -> None:
    if not path.is_file():
        errors.append(f"missing file: {path}")
    elif nonempty and path.stat().st_size == 0:
        errors.append(f"empty file: {path}")


def require_directory(path: Path, errors: list[str]) -> None:
    if not path.is_dir():
        errors.append(f"missing directory: {path}")


def relative_file_set(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }


def parse_skill_frontmatter(
    path: Path,
    errors: list[str],
) -> dict[str, str]:
    if not path.is_file():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        errors.append(f"{path}: missing opening YAML frontmatter delimiter")
        return {}
    try:
        end = next(
            index
            for index in range(1, len(lines))
            if lines[index].strip() == "---"
        )
    except StopIteration:
        errors.append(f"{path}: missing closing YAML frontmatter delimiter")
        return {}
    values: dict[str, str] = {}
    keys: list[str] = []
    for line in lines[1:end]:
        match = re.match(r"^([A-Za-z0-9_-]+):(?:\s*(.*))?$", line)
        if match:
            key = match.group(1)
            keys.append(key)
            values[key] = (match.group(2) or "").strip().strip("\"'")
    if set(keys) != {"name", "description"} or len(keys) != 2:
        errors.append(
            f"{path}: frontmatter must contain exactly name and description"
        )
    if not values.get("description"):
        errors.append(f"{path}: description is empty")
    return values


def validate_openai_yaml(
    path: Path,
    skill_name: str,
    errors: list[str],
) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    for key in (
        "interface:",
        "display_name:",
        "short_description:",
        "default_prompt:",
    ):
        if key not in text:
            errors.append(f"{path}: missing {key}")
    if f"${skill_name}" not in text:
        errors.append(
            f"{path}: default_prompt must explicitly mention ${skill_name}"
        )


def readable_alignment_text(skill_root: Path, files: set[str]) -> str:
    chunks: list[str] = []
    for relative in sorted(files):
        path = skill_root / relative
        if path.suffix.casefold() not in TEXT_SUFFIXES:
            continue
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
    return "\n".join(chunks)


def validate_target_skill_shell(
    project_root: Path,
    stage: dict[str, Any],
    errors: list[str],
) -> tuple[Path, set[str], str] | None:
    stage_id = stage["id"]
    output_skill = stage.get("output_skill")
    if not isinstance(output_skill, dict):
        errors.append(f"{stage_id}: output_skill is required")
        return None
    skill_name = output_skill.get("name")
    if (
        not isinstance(skill_name, str)
        or len(skill_name) > 64
        or not SKILL_NAME_RE.fullmatch(skill_name)
    ):
        errors.append(f"{stage_id}: invalid Skill name {skill_name!r}")
        return None
    skill_path = within_workload_profile(
        project_root,
        output_skill.get("path", ""),
    )
    require_directory(skill_path, errors)
    if not skill_path.is_dir():
        return None
    output_files = relative_file_set(skill_path)
    declared_files = set(output_skill.get("file_set", []))
    if output_files != declared_files:
        errors.append(
            f"{skill_path}: file set must be {sorted(declared_files)}; "
            f"got {sorted(output_files)}"
        )
    for relative in sorted(output_files):
        require_file(skill_path / relative, errors)
    skill_md = skill_path / "SKILL.md"
    openai_yaml = skill_path / "agents" / "openai.yaml"
    require_file(skill_md, errors)
    require_file(openai_yaml, errors)
    frontmatter = parse_skill_frontmatter(skill_md, errors)
    if frontmatter.get("name") != skill_name:
        errors.append(f"{skill_md}: name must match manifest {skill_name}")
    validate_openai_yaml(openai_yaml, skill_name, errors)
    text = readable_alignment_text(skill_path, output_files)
    return skill_path, output_files, text


def validate_handoff(
    project_root: Path,
    stage: dict[str, Any],
    errors: list[str],
) -> None:
    stage_id = stage["id"]
    path = within_workload_profile(project_root, stage["handoff"])
    require_file(path, errors)
    if not path.is_file():
        return
    try:
        payload = load_json(path)
    except GateFailure as exc:
        errors.append(str(exc))
        return
    if not isinstance(payload, dict):
        errors.append(f"{path}: expected an object")
        return
    if payload.get("schema_version") != 1:
        errors.append(f"{path}: schema_version must be 1")
    if payload.get("stage_id") != stage_id:
        errors.append(f"{path}: stage_id must be {stage_id}")
    if str(payload.get("status", "")).lower() != "complete":
        errors.append(f"{path}: status must be complete")
    outputs = payload.get("outputs")
    output_skill = stage.get("output_skill")
    if isinstance(output_skill, dict):
        expected_outputs = {"skill": output_skill["path"]}
    else:
        expected_outputs = stage.get("runtime_outputs")
    if outputs != expected_outputs:
        errors.append(
            f"{path}: outputs must exactly equal "
            f"{json.dumps(expected_outputs, ensure_ascii=False, sort_keys=True)}"
        )
    if stage.get("kind") == "workflow_gap_skill_generation":
        if payload.get("authority_type") != "workflow_gap":
            errors.append(f"{path}: authority_type must be workflow_gap")
        if payload.get("workflow_authority") != stage.get("workflow_authority"):
            errors.append(
                f"{path}: workflow_authority must exactly match the manifest"
            )


def validate_adapted_skill(
    project_root: Path,
    stage: dict[str, Any],
    source_skill_root: Path | None,
    errors: list[str],
) -> None:
    stage_id = stage["id"]
    source_skill = stage.get("source_skill")
    if not isinstance(source_skill, dict):
        errors.append(f"{stage_id}: source_skill is required")
        return
    if source_skill_root is None:
        errors.append(f"{stage_id}: --source-skill-root is required")
        return
    source_skill_root = source_skill_root.resolve()
    require_directory(source_skill_root, errors)
    if not source_skill_root.is_dir():
        return
    source_skill_md = source_skill_root / "SKILL.md"
    require_file(source_skill_md, errors)
    source_frontmatter = parse_skill_frontmatter(source_skill_md, errors)
    if source_frontmatter.get("name") != source_skill.get("name"):
        errors.append(
            f"{source_skill_md}: name must match manifest source "
            f"{source_skill.get('name')}"
        )
    source_files = relative_file_set(source_skill_root)
    declared_source_files = set(source_skill.get("file_set", []))
    if source_files != declared_source_files:
        errors.append(
            f"{source_skill_root}: source file set drift; "
            f"declared={sorted(declared_source_files)} got={sorted(source_files)}"
        )
    declared_hash = source_skill.get("tree_sha256")
    actual_hash = tree_digest(source_skill_root)
    if actual_hash != declared_hash:
        errors.append(
            f"{source_skill_root}: source tree hash drift; "
            f"declared={declared_hash} got={actual_hash}"
        )

    target = validate_target_skill_shell(project_root, stage, errors)
    if target is None:
        return
    skill_path, _output_files, alignment_text = target
    source_contract = source_skill_md.read_text(encoding="utf-8")
    skill_md = skill_path / "SKILL.md"
    output_contract = skill_md.read_text(encoding="utf-8")
    if len(source_contract) >= 1000:
        ratio = len(output_contract) / len(source_contract)
        if source_skill.get("scope") == "full" and not 0.65 <= ratio <= 1.50:
            errors.append(
                f"{skill_md}: full-scope text size ratio must stay within "
                f"0.65..1.50 of source; got {ratio:.2f}"
            )
        if source_skill.get("scope") != "full" and not 0.20 <= ratio <= 0.85:
            errors.append(
                f"{skill_md}: scoped text size ratio must stay within "
                f"0.20..0.85 of source; got {ratio:.2f}"
            )
    if "pra2026-bh408" not in alignment_text:
        errors.append(
            f"{skill_path}: missing current project binding pra2026-bh408"
        )
    if not any(marker in alignment_text for marker in CURRENT_STACK_MARKERS):
        errors.append(
            f"{skill_path}: missing Qwen3.5/vLLM/ROCm/DCU alignment marker"
        )
    for old_binding in LEGACY_ABSOLUTE_BINDINGS:
        if old_binding in alignment_text:
            errors.append(
                f"{skill_path}: retains legacy absolute binding {old_binding}"
            )
    validate_handoff(project_root, stage, errors)


def validate_gap_skill(
    project_root: Path,
    stage: dict[str, Any],
    errors: list[str],
) -> None:
    stage_id = stage["id"]
    authority = stage.get("workflow_authority")
    if not isinstance(authority, dict):
        errors.append(f"{stage_id}: workflow_authority is required")
        return
    authority_path = within_workload_profile(
        project_root, authority.get("path", "")
    )
    require_file(authority_path, errors)
    if authority_path.is_file():
        actual_hash = sha256_file(authority_path)
        if authority.get("sha256") != actual_hash:
            errors.append(
                f"{authority_path}: authority hash drift; "
                f"declared={authority.get('sha256')} got={actual_hash}"
            )
    for item in stage.get("binding_evidence", []):
        if not isinstance(item, dict):
            errors.append(f"{stage_id}: invalid binding evidence entry {item}")
            continue
        evidence_path = project_path(project_root, item.get("path", ""))
        require_file(evidence_path, errors)
        if evidence_path.is_file():
            actual_hash = sha256_file(evidence_path)
            if item.get("sha256") != actual_hash:
                errors.append(
                    f"{evidence_path}: evidence hash drift; "
                    f"declared={item.get('sha256')} got={actual_hash}"
                )

    target = validate_target_skill_shell(project_root, stage, errors)
    if target is None:
        return
    skill_path, output_files, alignment_text = target
    if output_files != {"SKILL.md", "agents/openai.yaml"}:
        errors.append(
            f"{skill_path}: Workflow-gap Skill must contain exactly "
            "SKILL.md and agents/openai.yaml"
        )
    casefolded = alignment_text.casefold()
    missing_markers = [
        marker
        for marker in stage.get("required_markers", [])
        if marker.casefold() not in casefolded
    ]
    if missing_markers:
        errors.append(
            f"{skill_path}: missing required capability markers: "
            f"{', '.join(missing_markers)}"
        )
    unresolved = stage.get("unresolved_bindings", [])
    if unresolved and (
        "runtime" not in casefolded
        or not any(word in casefolded for word in ("discovery", "discover", "发现"))
    ):
        errors.append(
            f"{skill_path}: unresolved bindings must remain explicit runtime discovery"
        )
    if not any(marker.casefold() in casefolded for marker in CURRENT_STACK_MARKERS):
        errors.append(
            f"{skill_path}: missing Qwen3.5/vLLM/ROCm/DCU binding context"
        )
    for old_binding in LEGACY_ABSOLUTE_BINDINGS:
        if old_binding.casefold() in casefolded:
            errors.append(
                f"{skill_path}: retains legacy absolute binding {old_binding}"
            )
    validate_handoff(project_root, stage, errors)


def goal_ids(payload: Any) -> list[str]:
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


def runtime_expectations(
    plan: dict[str, Any],
    stage: dict[str, Any],
) -> tuple[dict[str, list[str]], dict[str, str]]:
    stages = {
        item.get("id"): item
        for item in plan.get("stages", [])
        if isinstance(item, dict)
    }
    expected_pipelines: dict[str, list[str]] = {}
    expected_skills: dict[str, str] = {}
    for branch, entries in stage.get("runtime_branches", {}).items():
        expected_pipelines[branch] = []
        for entry in entries:
            runtime_id = entry["id"]
            owner = stages.get(entry["stage"])
            output_skill = (
                owner.get("output_skill") if isinstance(owner, dict) else None
            )
            if not isinstance(output_skill, dict) or not isinstance(
                output_skill.get("name"), str
            ):
                raise GateFailure(
                    f"{entry['stage']}: missing output Skill for {runtime_id}"
                )
            expected_pipelines[branch].append(runtime_id)
            previous = expected_skills.get(runtime_id)
            current = output_skill["name"]
            if previous is not None and previous != current:
                raise GateFailure(
                    f"{runtime_id}: inconsistent branch Skill bindings"
                )
            expected_skills[runtime_id] = current
    return expected_pipelines, expected_skills


def validate_pipeline_bindings(
    project_root: Path,
    path: Path,
    payload: Any,
    branch: str,
    expected_ids: list[str],
    expected_skills: dict[str, str],
    errors: list[str],
) -> None:
    if not isinstance(payload, dict):
        errors.append(f"{path}: expected an object")
        return
    if payload.get("branch") != branch:
        errors.append(f"{path}: branch must be {branch}")
    if goal_ids(payload) != expected_ids:
        errors.append(f"{path}: goals must be {','.join(expected_ids)}")
    bindings = payload.get("bindings")
    if not isinstance(bindings, dict):
        errors.append(f"{path}: bindings must be an object")
        return
    if set(bindings) != set(expected_ids):
        errors.append(f"{path}: binding keys must be {','.join(expected_ids)}")
    for goal_id in expected_ids:
        expected_skill = expected_skills[goal_id]
        if bindings.get(goal_id) != {"skill": expected_skill}:
            errors.append(
                f"{path}: {goal_id} binding must contain only "
                f"skill={expected_skill}"
            )
        require_file(
            project_root
            / "workload_profile"
            / "skills"
            / expected_skill
            / "SKILL.md",
            errors,
        )


def run_scheduler_dry_run(
    scheduler: Path,
    project_root: Path,
    branch: str,
    expected_ids: list[str],
    errors: list[str],
) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(scheduler),
            "--project-root",
            str(project_root),
            "--branch",
            branch,
            "--dry-run",
        ],
        cwd=project_root,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    if completed.returncode != 0:
        errors.append(
            f"{scheduler}: {branch} --dry-run failed "
            f"({completed.returncode}): {completed.stderr.strip()}"
        )
        return
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        errors.append(f"{scheduler}: {branch} --dry-run must emit JSON: {exc}")
        return
    observed = goal_ids(payload)
    if observed != expected_ids:
        errors.append(
            f"{scheduler}: {branch} dry-run goals must be "
            f"{','.join(expected_ids)}; got {observed}"
        )


def validate_scheduler(
    project_root: Path,
    plan: dict[str, Any],
    stage: dict[str, Any],
    errors: list[str],
) -> None:
    outputs = stage.get("runtime_outputs", {})
    scheduler = within_workload_profile(project_root, outputs.get("scheduler", ""))
    manifests = {
        "dispatch": within_workload_profile(
            project_root, outputs.get("dispatch", "")
        ),
        "fx": within_workload_profile(project_root, outputs.get("fx", "")),
    }
    require_file(scheduler, errors)
    for path in manifests.values():
        require_file(path, errors)
    validate_handoff(project_root, stage, errors)
    if not scheduler.is_file():
        return
    scheduler_text = scheduler.read_text(encoding="utf-8")
    if re.search(r"goal[-_]spec", scheduler_text, flags=re.IGNORECASE):
        errors.append(f"{scheduler}: must use target Skills without goal-spec")
    try:
        module = ast.parse(scheduler_text, filename=str(scheduler))
    except SyntaxError as exc:
        errors.append(f"{scheduler}: Python syntax error: {exc}")
        return
    thread_params = next(
        (
            child
            for node in module.body
            if isinstance(node, ast.ClassDef)
            and node.name == "RuntimeScheduler"
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            and child.name == "_thread_start_params"
        ),
        None,
    )
    persistent_goal_thread = any(
        isinstance(node, ast.Dict)
        and any(
            isinstance(key, ast.Constant)
            and key.value == "ephemeral"
            and isinstance(value, ast.Constant)
            and value.value is False
            for key, value in zip(node.keys, node.values)
        )
        for node in ast.walk(thread_params)
    ) if thread_params is not None else False
    if not persistent_goal_thread:
        errors.append(
            f"{scheduler}: RuntimeScheduler._thread_start_params must set "
            "ephemeral=False"
        )
    help_result = subprocess.run(
        [sys.executable, str(scheduler), "--help"],
        cwd=project_root,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    if help_result.returncode != 0:
        errors.append(
            f"{scheduler}: --help failed ({help_result.returncode}): "
            f"{help_result.stderr.strip()}"
        )
    expected_pipelines, expected_skills = runtime_expectations(plan, stage)
    for branch, path in manifests.items():
        if not path.is_file():
            continue
        try:
            payload = load_json(path)
        except GateFailure as exc:
            errors.append(str(exc))
            continue
        expected_ids = expected_pipelines[branch]
        validate_pipeline_bindings(
            project_root,
            path,
            payload,
            branch,
            expected_ids,
            expected_skills,
            errors,
        )
        run_scheduler_dry_run(
            scheduler,
            project_root,
            branch,
            expected_ids,
            errors,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one lightweight workload-profile adaptation gate."
    )
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--stage", required=True)
    parser.add_argument(
        "--source-skill-root",
        type=Path,
        help="Resolved source Skill root; required only for source stages.",
    )
    parser.add_argument(
        "--phase",
        choices=("final",),
        default="final",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    errors: list[str] = []
    if not project_root.is_dir():
        errors.append(f"project root is not a directory: {project_root}")
    try:
        plan_path = within_workload_profile(project_root, args.plan.resolve())
        plan = load_json(plan_path)
    except GateFailure as exc:
        errors.append(str(exc))
        plan = {}
    stages = plan.get("stages", []) if isinstance(plan, dict) else []
    stage = next(
        (
            item
            for item in stages
            if isinstance(item, dict) and item.get("id") == args.stage
        ),
        None,
    )
    gate_name = "unknown"
    try:
        if stage is None:
            errors.append(f"unknown stage {args.stage}")
        elif stage.get("kind") == "source_skill_text_alignment":
            gate_name = "source-skill-mirror-alignment"
            validate_adapted_skill(
                project_root,
                stage,
                args.source_skill_root,
                errors,
            )
        elif stage.get("kind") == "workflow_gap_skill_generation":
            gate_name = "workflow-gap-skill-synthesis"
            if args.source_skill_root is not None:
                errors.append(
                    f"{args.stage}: Workflow-gap stage must not receive a source Skill"
                )
            validate_gap_skill(project_root, stage, errors)
        elif stage.get("kind") == "scheduler_generation":
            gate_name = "runtime-scheduler-generation"
            if args.source_skill_root is not None:
                errors.append(
                    f"{args.stage}: scheduler stage must not receive a source Skill"
                )
            validate_scheduler(project_root, plan, stage, errors)
        else:
            errors.append(
                f"{args.stage}: unsupported stage kind {stage.get('kind')}"
            )
    except GateFailure as exc:
        errors.append(str(exc))
    result = {
        "schema_version": 6,
        "stage_id": args.stage,
        "phase": "final",
        "gate": gate_name,
        "status": "pass" if not errors else "fail",
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
