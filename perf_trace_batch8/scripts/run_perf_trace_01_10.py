#!/usr/bin/env python3
"""Run the pinned batch8 dual-DCU DP2 R01-R10 workflow as serial Codex Goals.

The control plane is project-local and standalone.  Its dry run is deliberately
side-effect free: it validates only files, hashes, the Git identity, stage
order, profile topology, and handoff gates.  It does not resolve or start
Codex app-server until a non-dry runtime run is explicitly requested.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BRANCH = "workflow01-10-fresh-e2e"
GOAL_IDS = tuple(f"R{value:02d}" for value in range(1, 11))
PROJECT_ROOT = Path("/public/home/tangyu408/Qwen_DCU_Worker_0")
PERF_TRACE_ROOT = PROJECT_ROOT / "perf_trace_batch8"
MANIFEST_PATH = PERF_TRACE_ROOT / "manifests/workflow01_10_fresh_e2e_pipeline.json"
MANIFEST_SHA256 = "49b37f32991c3070a91bbafa39d3dd40d3ecd81d8f8109b2525d2f84ded1726f"
CONFIG_PATH = PERF_TRACE_ROOT / "configs/workflow01_10_fresh_e2e_batch8_dual_dcu_dp2.json"
CONFIG_SHA256 = "89d4455bd89c5f59aeea9f082353507565264ac30881faaad8f8ef966ba48ad7"
TRACE_PROFILE_PATH = PERF_TRACE_ROOT / "configs/trace_targets/batch8_dual_dcu_dp2.json"
TRACE_PROFILE_ID = "batch8-dual-dcu-dp2"
TRACE_PROFILE_SHA256 = "3b4c952063f48ae662b48b5ce9d8fd76e0ac4d74e170bdb1839ae8b1aaa23cce"
TRACE_TARGET_ROOT = PROJECT_ROOT / "pra2026-bh408-gqa-page784-k5120-batch8"
TRACE_TARGET_COMMIT = "2b4b2119ae3cc2c4c626dc5690ef9593c1477f66"
PROJECT_SKILL_ROOT = PERF_TRACE_ROOT / "skills"
RUNTIME_ROOT = PERF_TRACE_ROOT / "runtime" / BRANCH
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_EVIDENCE_STATUSES = {"complete", "degraded", "insufficient", "unknown"}
TERMINAL_GOAL_STATUSES = {
    "blocked",
    "usageLimited",
    "budgetLimited",
    "failed",
    "interrupted",
    "cancelled",
    "complete",
}
APPROVAL_POLICY = "never"
SANDBOX_POLICY = "danger-full-access"
TURN_SANDBOX_POLICY = {"type": "dangerFullAccess"}


class SchedulerError(RuntimeError):
    """A deterministic scheduler or validation failure."""


class RpcError(SchedulerError):
    """A Codex app-server JSON-RPC failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{secrets.token_hex(4)}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def json_document_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    return sha256_bytes(encoded)


def skill_tree_sha256(root: Path) -> tuple[str, list[str]]:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise SchedulerError(f"project skill tree is empty: {root}")
    digest = hashlib.sha256()
    relative_files: list[str] = []
    for path in files:
        if path.is_symlink():
            raise SchedulerError(f"project skill tree contains a symlink: {path}")
        relative = path.relative_to(root).as_posix()
        relative_files.append(relative)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest(), relative_files


def load_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise SchedulerError(f"required JSON file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SchedulerError(f"invalid JSON in {path}: {exc}") from exc


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    )
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def require_under(path: Path, root: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise SchedulerError(f"path escapes the allowed root: {resolved}") from exc
    return resolved


def project_path(value: str, project_root: Path) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return require_under(candidate, project_root)


def validate_run_id(value: str) -> None:
    if RUN_ID_RE.fullmatch(value) is None:
        raise SchedulerError(
            "run id must start with an alphanumeric character, contain only "
            "letters, digits, dot, underscore, or hyphen, and be at most 128 "
            "characters"
        )


def git_output(args: list[str]) -> str:
    git_environment = os.environ.copy()
    git_environment["GIT_OPTIONAL_LOCKS"] = "0"
    result = subprocess.run(
        ["git", "-C", str(TRACE_TARGET_ROOT), *args],
        check=False,
        capture_output=True,
        text=True,
        env=git_environment,
    )
    if result.returncode != 0:
        raise SchedulerError(
            f"target Git inspection failed ({' '.join(args)}): "
            f"{result.stderr.strip()}"
        )
    return result.stdout.strip()


def validate_target_checkout(*, require_clean: bool) -> dict[str, Any]:
    if not TRACE_TARGET_ROOT.is_dir():
        raise SchedulerError(f"fixed trace target is missing: {TRACE_TARGET_ROOT}")
    head = git_output(["rev-parse", "HEAD"])
    if head != TRACE_TARGET_COMMIT:
        raise SchedulerError(
            f"trace target commit mismatch: expected {TRACE_TARGET_COMMIT}, "
            f"observed {head}"
        )
    branch = git_output(["rev-parse", "--abbrev-ref", "HEAD"])
    status = git_output(["status", "--porcelain=v1", "--untracked-files=all"])
    if require_clean and status:
        raise SchedulerError("trace target must be clean before a fresh runtime")
    return {
        "path": str(TRACE_TARGET_ROOT),
        "git_commit": head,
        "git_branch": branch,
        "git_clean": not bool(status),
        "inspection_only": True,
    }


def parse_serial_contract(text: str, skill_name: str) -> dict[str, Any]:
    if "## Serial Runtime Contract" not in text:
        raise SchedulerError(f"project skill lacks Serial Runtime Contract: {skill_name}")
    values: dict[str, str] = {}
    for key in (
        "runtime_branch",
        "runtime_goal",
        "runtime_predecessors",
        "required_handoff_fields",
        "runtime_artifact_root",
        "runtime_handoff_output",
        "advance_only_after",
    ):
        match = re.search(rf"^{re.escape(key)}=(.+)$", text, re.MULTILINE)
        if match is None:
            raise SchedulerError(f"project skill contract lacks {key}: {skill_name}")
        values[key] = match.group(1).strip()
    fields = [item for item in values["required_handoff_fields"].split(",") if item]
    if len(fields) != len(set(fields)):
        raise SchedulerError(f"duplicate required handoff fields: {skill_name}")
    values["required_handoff_fields_list"] = fields
    return values


def validate_r01_bootstrap(
    config: dict[str, Any],
    profile: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    bootstrap = config.get("r01_bootstrap")
    if not isinstance(bootstrap, dict) or bootstrap.get("schema_version") != 1:
        raise SchedulerError("R01 bootstrap configuration is missing or invalid")
    if bootstrap.get("required_before_r01_goal_creation") is not True:
        raise SchedulerError("R01 bootstrap must precede formal Goal creation")

    selection = bootstrap.get("request_selection")
    workload = profile.get("workload")
    if not isinstance(selection, dict) or not isinstance(workload, dict):
        raise SchedulerError("R01 request selection or profile workload is missing")
    exact_selection = {
        "schema_version": 1,
        "dataset_path": workload.get("dataset_path"),
        "selection_policy": "first_8_records_in_original_file_order_no_expansion",
        "request_count": 8,
        "selected_line_numbers": list(range(1, 9)),
        "request_id_policy": "{trace_profile_id}-req-{ordinal:03d}-{canonical_json_sha256_prefix_16}",
        "raw_line_hash_policy": "sha256_exact_raw_line_bytes_including_original_line_terminator",
        "canonical_json_policy": "utf8_json_sort_keys_true_ensure_ascii_false_compact_separators",
        "ordered_sequence_hash_policy": "sha256_canonical_utf8_json_array_of_the_eight_parsed_request_objects",
        "dataset_search_allowed": False,
        "request_expansion_allowed": False,
        "request_oversampling_allowed": False,
        "request_shuffle_allowed": False,
        "prompt_synthesis_allowed": False,
    }
    for key, expected in exact_selection.items():
        if selection.get(key) != expected:
            raise SchedulerError(f"R01 request-selection {key} mismatch")
    if workload.get("request_count") != 8:
        raise SchedulerError("R01 request selection must equal the profile count of eight")

    dataset_path = Path(str(selection.get("dataset_path"))).expanduser().resolve()
    if dataset_path != Path("/home/testdata/16-32K_throughput.jsonl"):
        raise SchedulerError("R01 dataset path is not the fixed batch8 dataset")
    if not dataset_path.is_file():
        raise SchedulerError(f"R01 dataset is missing: {dataset_path}")
    dataset_hash = sha256_file(dataset_path)
    if dataset_hash != selection.get("dataset_file_sha256"):
        raise SchedulerError("R01 dataset file hash mismatch")
    if dataset_hash != "633ba4c8b4f500d2ab28094de42698c5494e5232f40eafcd119c0a314b44b936":
        raise SchedulerError("R01 dataset is not the hash-pinned batch8 input")

    raw_lines = dataset_path.read_bytes().splitlines(keepends=True)
    if len(raw_lines) < 8:
        raise SchedulerError("R01 dataset contains fewer than eight records")
    parsed_requests: list[Any] = []
    computed_records: list[dict[str, Any]] = []
    for ordinal, line_number in enumerate(range(1, 9), start=1):
        raw_line = raw_lines[line_number - 1]
        if raw_line.endswith(b"\r\n"):
            terminator = "CRLF"
        elif raw_line.endswith(b"\n"):
            terminator = "LF"
        elif raw_line.endswith(b"\r"):
            terminator = "CR"
        else:
            terminator = "NONE"
        try:
            request = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SchedulerError(
                f"R01 dataset line {line_number} is not valid UTF-8 JSON"
            ) from exc
        if not isinstance(request, dict):
            raise SchedulerError(f"R01 dataset line {line_number} is not a JSON object")
        canonical = canonical_json_bytes(request)
        canonical_hash = sha256_bytes(canonical)
        request_id = (
            f"{TRACE_PROFILE_ID}-req-{ordinal:03d}-{canonical_hash[:16]}"
        )
        parsed_requests.append(request)
        computed_records.append(
            {
                "ordinal": ordinal,
                "line_number": line_number,
                "row_index": line_number - 1,
                "request_id": request_id,
                "raw_line_byte_length": len(raw_line),
                "raw_line_terminator": terminator,
                "raw_line_sha256": sha256_bytes(raw_line),
                "canonical_json_byte_length": len(canonical),
                "canonical_json_sha256": canonical_hash,
            }
        )
    if selection.get("records") != computed_records:
        raise SchedulerError("R01 per-record request-selection bindings mismatch")
    sequence_bytes = canonical_json_bytes(parsed_requests)
    sequence_hash = sha256_bytes(sequence_bytes)
    if selection.get("ordered_sequence_canonical_byte_length") != len(sequence_bytes):
        raise SchedulerError("R01 ordered request-sequence byte length mismatch")
    if selection.get("ordered_sequence_canonical_sha256") != sequence_hash:
        raise SchedulerError("R01 ordered request-sequence hash mismatch")

    target_evidence = bootstrap.get("target_evidence")
    profile_evidence = profile.get("target_evidence")
    if not isinstance(target_evidence, dict) or not isinstance(profile_evidence, dict):
        raise SchedulerError("R01 target evidence binding is missing")
    resolved_target_evidence: dict[str, dict[str, Any]] = {}
    for role in ("service_launcher", "benchmark_launcher", "design_document"):
        entry = target_evidence.get(role)
        relative_path = profile_evidence.get(role)
        if not isinstance(entry, dict) or entry.get("path") != relative_path:
            raise SchedulerError(f"R01 target evidence path mismatch: {role}")
        evidence_path = require_under(
            TRACE_TARGET_ROOT / str(relative_path), TRACE_TARGET_ROOT
        )
        if not evidence_path.is_file() or sha256_file(evidence_path) != entry.get("sha256"):
            raise SchedulerError(f"R01 target evidence hash mismatch: {role}")
        resolved_target_evidence[role] = {
            "path": str(evidence_path),
            "target_relative_path": str(relative_path),
            "sha256": entry["sha256"],
        }

    model = bootstrap.get("model")
    if not isinstance(model, dict):
        raise SchedulerError("R01 model binding is missing")
    model_directory = Path(str(model.get("directory"))).expanduser().resolve()
    model_config = Path(str(model.get("config_path"))).expanduser().resolve()
    if not model_directory.is_dir() or model_config != model_directory / "config.json":
        raise SchedulerError("R01 model directory/config binding is invalid")
    if not model_config.is_file() or sha256_file(model_config) != model.get("config_sha256"):
        raise SchedulerError("R01 model config hash mismatch")

    runtime = bootstrap.get("runtime_executable")
    if not isinstance(runtime, dict):
        raise SchedulerError("R01 runtime executable binding is missing")
    executable = Path(str(runtime.get("path"))).expanduser().resolve()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise SchedulerError("R01 runtime executable is missing or not executable")
    if sha256_file(executable) != runtime.get("sha256"):
        raise SchedulerError("R01 runtime executable hash mismatch")
    executable_text = executable.read_text(encoding="utf-8")
    if "from vllm.entrypoints.cli.main import main" not in executable_text:
        raise SchedulerError("R01 runtime executable entry point is unexpected")
    version_evidence = runtime.get("version_evidence")
    if not isinstance(version_evidence, dict) or (
        version_evidence.get("source")
        != "installed_distribution_metadata_without_importing_or_executing_vllm"
        or version_evidence.get("distribution_name") != "vllm"
    ):
        raise SchedulerError("R01 runtime version evidence is invalid")
    metadata_path = Path(str(version_evidence.get("metadata_path"))).resolve()
    entry_points_path = Path(str(version_evidence.get("entry_points_path"))).resolve()
    for evidence_path, expected_hash, label in (
        (metadata_path, version_evidence.get("metadata_sha256"), "metadata"),
        (entry_points_path, version_evidence.get("entry_points_sha256"), "entry points"),
    ):
        if not evidence_path.is_file() or sha256_file(evidence_path) != expected_hash:
            raise SchedulerError(f"R01 runtime {label} hash mismatch")
    version_match = re.search(
        r"^Version:\s*(\S+)\s*$",
        metadata_path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if version_match is None or version_match.group(1) != runtime.get("version"):
        raise SchedulerError("R01 runtime version metadata mismatch")
    entry_points_text = entry_points_path.read_text(encoding="utf-8")
    if version_evidence.get("console_script") not in entry_points_text:
        raise SchedulerError("R01 runtime console-script evidence mismatch")

    service = bootstrap.get("service")
    if service != {"port": 8001, "port_policy": "fixed_no_dynamic_selection"}:
        raise SchedulerError("R01 fixed service-port binding mismatch")
    attempt_policy = bootstrap.get("attempt_id_policy")
    if attempt_policy != {
        "format": "{runtime_run_id}-R01-attempt-{attempt_ordinal:03d}",
        "initial_attempt_ordinal": 1,
        "resume_attempt_ordinal_policy": "resume_directory_index_plus_one",
        "must_be_nonempty": True,
        "reuse_allowed": False,
    }:
        raise SchedulerError("R01 attempt-ID policy mismatch")
    assignment_policy = bootstrap.get("assignment_policy")
    if assignment_policy != {
        "generated_and_validated_before_formal_r01_goal_creation": True,
        "complete_bootstrap_injected_into_formal_r01_goal_objective": False,
        "compact_hash_verifiable_identity_summary_injected_into_formal_r01_goal_objective": True,
        "injected_into_r01_turn_assignment": True,
        "clock_and_hipprof_use_identical_request_manifest": True,
        "runtime_discovery_allowed": False,
    }:
        raise SchedulerError("R01 assignment policy mismatch")

    manifest_gate = manifest.get("r01_bootstrap_gate")
    expected_manifest_gate = {
        "schema_version": 1,
        "required_before_formal_goal_creation": True,
        "request_selection": {
            "dataset_path": str(dataset_path),
            "dataset_file_sha256": dataset_hash,
            "selection_policy": selection["selection_policy"],
            "request_count": 8,
            "selected_line_numbers": list(range(1, 9)),
            "ordered_sequence_canonical_sha256": sequence_hash,
        },
        "target_evidence_sha256": {
            value["target_relative_path"]: value["sha256"]
            for value in resolved_target_evidence.values()
        },
        "model": copy.deepcopy(model),
        "runtime_executable": {
            "path": str(executable),
            "sha256": runtime["sha256"],
            "version": runtime["version"],
            "version_metadata_sha256": version_evidence["metadata_sha256"],
        },
        "service_port": 8001,
        "attempt_id_generated_by_scheduler": True,
        "request_expansion_allowed": False,
        "runtime_discovery_allowed": False,
    }
    if manifest_gate != expected_manifest_gate:
        raise SchedulerError("runtime manifest R01 bootstrap gate mismatch")

    request_manifest = {
        "schema_version": 1,
        "generated_by": "project_local_runtime_scheduler",
        "generation_source": "hash_pinned_profile_dataset_and_target_bindings",
        "dataset_path": str(dataset_path),
        "dataset_file_sha256": dataset_hash,
        "selection_policy": selection["selection_policy"],
        "request_count": 8,
        "selected_line_numbers": list(range(1, 9)),
        "request_locator_kind": "one_based_dataset_line_number",
        "request_id_policy": selection["request_id_policy"],
        "raw_line_hash_policy": selection["raw_line_hash_policy"],
        "canonical_json_policy": selection["canonical_json_policy"],
        "ordered_sequence_hash_policy": selection["ordered_sequence_hash_policy"],
        "records": computed_records,
        "ordered_sequence_canonical_byte_length": len(sequence_bytes),
        "ordered_sequence_canonical_sha256": sequence_hash,
        "complete": True,
        "request_expansion_performed": False,
        "request_oversampling_performed": False,
        "request_shuffle_performed": False,
        "prompt_synthesis_performed": False,
        "clock_and_hipprof_manifest_identity_required": True,
    }
    return {
        "request_selection_manifest": request_manifest,
        "request_selection_manifest_sha256": sha256_bytes(
            canonical_json_bytes(request_manifest)
        ),
        "target_evidence": resolved_target_evidence,
        "model": {
            "directory": str(model_directory),
            "config_path": str(model_config),
            "config_sha256": model["config_sha256"],
        },
        "runtime_executable": copy.deepcopy(runtime),
        "service": copy.deepcopy(service),
        "attempt_id_policy": copy.deepcopy(attempt_policy),
        "assignment_policy": copy.deepcopy(assignment_policy),
    }


def validate_fixed_bundle(
    project_root: Path,
    branch: str,
    *,
    require_target_clean: bool,
    user_parameters_file: str | None,
) -> dict[str, Any]:
    if project_root.resolve() != PROJECT_ROOT.resolve():
        raise SchedulerError(f"project root is fixed to {PROJECT_ROOT}")
    if branch != BRANCH:
        raise SchedulerError(f"runtime branch is fixed to {BRANCH}")
    for path, expected, role in (
        (MANIFEST_PATH, MANIFEST_SHA256, "runtime manifest"),
        (CONFIG_PATH, CONFIG_SHA256, "runtime configuration"),
        (TRACE_PROFILE_PATH, TRACE_PROFILE_SHA256, "trace profile"),
    ):
        if not path.is_file():
            raise SchedulerError(f"{role} is missing: {path}")
        observed = sha256_file(path)
        if observed != expected:
            raise SchedulerError(
                f"{role} hash mismatch: expected {expected}, observed {observed}"
            )
    if user_parameters_file is not None:
        supplied = Path(user_parameters_file).expanduser().resolve()
        if supplied != CONFIG_PATH.resolve():
            raise SchedulerError(
                f"--user-parameters-file is fixed to {CONFIG_PATH}"
            )

    manifest = load_json(MANIFEST_PATH)
    config = load_json(CONFIG_PATH)
    profile = load_json(TRACE_PROFILE_PATH)
    if not all(isinstance(item, dict) for item in (manifest, config, profile)):
        raise SchedulerError("manifest, configuration, and profile must be JSON objects")
    if manifest.get("schema_version") != 1 or manifest.get("branch") != BRANCH:
        raise SchedulerError("runtime manifest identity is invalid")
    if manifest.get("goals") != list(GOAL_IDS):
        raise SchedulerError("runtime manifest Goal order is not R01-R10")
    if manifest.get("project_skill_root") != str(PROJECT_SKILL_ROOT):
        raise SchedulerError("runtime manifest project skill root mismatch")
    if manifest.get("runtime_root") != str(RUNTIME_ROOT):
        raise SchedulerError("runtime manifest runtime root mismatch")
    manifest_config = manifest.get("runtime_config")
    if manifest_config != {"path": str(CONFIG_PATH), "sha256": CONFIG_SHA256}:
        raise SchedulerError("runtime manifest configuration binding mismatch")
    manifest_profile = manifest.get("trace_profile")
    if manifest_profile != {
        "profile_id": TRACE_PROFILE_ID,
        "path": str(TRACE_PROFILE_PATH),
        "sha256": TRACE_PROFILE_SHA256,
    }:
        raise SchedulerError("runtime manifest trace-profile binding mismatch")
    target_binding = manifest.get("trace_target")
    if not isinstance(target_binding, dict) or (
        target_binding.get("path") != str(TRACE_TARGET_ROOT)
        or target_binding.get("git_commit") != TRACE_TARGET_COMMIT
    ):
        raise SchedulerError("runtime manifest target binding mismatch")

    if config.get("schema_version") != 1 or config.get("branch") != BRANCH:
        raise SchedulerError("runtime configuration identity is invalid")
    expected_config_identity = {
        "trace_target_root": str(TRACE_TARGET_ROOT),
        "trace_target_git_commit": TRACE_TARGET_COMMIT,
        "trace_profile_id": TRACE_PROFILE_ID,
        "trace_profile_path": str(TRACE_PROFILE_PATH),
        "trace_profile_sha256": TRACE_PROFILE_SHA256,
    }
    for key, expected in expected_config_identity.items():
        if config.get(key) != expected:
            raise SchedulerError(f"runtime configuration {key} mismatch")
    if profile.get("schema_version") != 1 or profile.get("profile_id") != TRACE_PROFILE_ID:
        raise SchedulerError("trace profile identity is invalid")
    if profile.get("trace_target_root") != str(TRACE_TARGET_ROOT):
        raise SchedulerError("trace profile target binding mismatch")
    for key in ("workload", "topology", "coverage_gate", "serial_semantics"):
        if config.get(key) != profile.get(key):
            raise SchedulerError(f"configuration does not preserve trace profile {key}")
    topology = profile.get("topology")
    coverage = profile.get("coverage_gate")
    if not isinstance(topology, dict) or not isinstance(coverage, dict):
        raise SchedulerError("trace profile topology or coverage gate is missing")
    exact_topology = {
        "physical_devices": [0, 1],
        "hip_visible_devices": "0,1",
        "cuda_visible_devices": "0,1",
        "world_size": 2,
        "tensor_parallel_size": 1,
        "pipeline_parallel_size": 1,
        "data_parallel_size": 2,
        "data_parallel_backend": "mp",
        "rank_to_physical_device": {"0": 0, "1": 1},
    }
    for key, expected in exact_topology.items():
        if topology.get(key) != expected:
            raise SchedulerError(f"trace profile topology {key} mismatch")
    if coverage.get("required_physical_devices") != [0, 1]:
        raise SchedulerError("trace profile must cover physical devices 0 and 1")
    if coverage.get("required_dp_ranks") != [0, 1]:
        raise SchedulerError("trace profile must cover DP ranks 0 and 1")
    if coverage.get("forbid_single_device_promotion") is not True:
        raise SchedulerError("trace profile must forbid single-device promotion")

    bindings = manifest.get("bindings")
    if not isinstance(bindings, dict) or list(bindings) != list(GOAL_IDS):
        raise SchedulerError("runtime manifest bindings are missing or out of order")
    required_literals = profile.get("required_skill_literals")
    forbidden_literals = profile.get("forbidden_skill_literals")
    if not isinstance(required_literals, list) or not isinstance(forbidden_literals, list):
        raise SchedulerError("trace profile skill literal gates are invalid")
    skill_tree_hashes: dict[str, str] = {}
    skill_file_hashes: dict[str, str] = {}
    skill_paths: dict[str, Path] = {}
    required_handoff_fields: dict[str, list[str]] = {}
    for index, goal_id in enumerate(GOAL_IDS):
        binding = bindings.get(goal_id)
        if not isinstance(binding, dict):
            raise SchedulerError(f"runtime binding is missing for {goal_id}")
        skill_name = binding.get("skill")
        if not isinstance(skill_name, str) or not skill_name:
            raise SchedulerError(f"runtime skill name is invalid for {goal_id}")
        expected_path = PROJECT_SKILL_ROOT / skill_name / "SKILL.md"
        skill_path = project_path(str(binding.get("skill_path")), project_root)
        if skill_path != expected_path.resolve() or not skill_path.is_file():
            raise SchedulerError(f"runtime skill path mismatch for {goal_id}")
        file_hash = sha256_file(skill_path)
        if file_hash != binding.get("skill_file_sha256"):
            raise SchedulerError(f"runtime skill file hash mismatch for {goal_id}")
        tree_hash, tree_files = skill_tree_sha256(skill_path.parent)
        if tree_hash != binding.get("skill_tree_sha256"):
            raise SchedulerError(f"runtime skill tree hash mismatch for {goal_id}")
        if tree_files != binding.get("skill_tree_files"):
            raise SchedulerError(f"runtime skill file inventory mismatch for {goal_id}")
        predecessors = list(GOAL_IDS[:index])
        if binding.get("predecessors") != predecessors:
            raise SchedulerError(f"runtime predecessor binding mismatch for {goal_id}")
        text = skill_path.read_text(encoding="utf-8")
        missing = [literal for literal in required_literals if literal not in text]
        forbidden = [literal for literal in forbidden_literals if literal in text]
        if missing or forbidden:
            raise SchedulerError(
                f"runtime skill profile literals invalid for {goal_id}: "
                f"missing={missing}, forbidden={forbidden}"
            )
        contract = parse_serial_contract(text, skill_name)
        expected_predecessors = ",".join(predecessors) if predecessors else "none"
        exact_contract = {
            "runtime_branch": BRANCH,
            "runtime_goal": goal_id,
            "runtime_predecessors": expected_predecessors,
            "runtime_artifact_root": "<scheduler-assigned>",
            "runtime_handoff_output": "<scheduler-assigned>",
            "advance_only_after": "complete",
        }
        for key, expected in exact_contract.items():
            if contract.get(key) != expected:
                raise SchedulerError(f"runtime skill {key} mismatch for {goal_id}")
        skill_tree_hashes[skill_name] = tree_hash
        skill_file_hashes[skill_name] = file_hash
        skill_paths[goal_id] = skill_path
        required_handoff_fields[goal_id] = list(
            contract["required_handoff_fields_list"]
        )

    target = validate_target_checkout(require_clean=require_target_clean)
    scheduler_contract = config.get("scheduler_contract")
    if not isinstance(scheduler_contract, dict) or (
        scheduler_contract.get("project_skill_root") != str(PROJECT_SKILL_ROOT)
        or scheduler_contract.get("runtime_root") != str(RUNTIME_ROOT)
        or scheduler_contract.get("runtime_goal_order") != list(GOAL_IDS)
        or scheduler_contract.get("maximum_concurrent_runtime_stages") != 1
        or scheduler_contract.get("external_upstream_ledger_allowed") is not False
        or scheduler_contract.get("full_dp2_profile_attestation_required_in_every_handoff") is not True
    ):
        raise SchedulerError("runtime configuration scheduler contract mismatch")
    r01_bootstrap = validate_r01_bootstrap(config, profile, manifest)
    return {
        "manifest": manifest,
        "config": config,
        "profile": profile,
        "target": target,
        "skill_tree_sha256": skill_tree_hashes,
        "skill_file_sha256": skill_file_hashes,
        "skill_paths": skill_paths,
        "required_handoff_fields": required_handoff_fields,
        "r01_bootstrap": r01_bootstrap,
    }


def runtime_ledger_template(run_id: str) -> dict[str, Any]:
    validate_run_id(run_id)
    return {
        "schema_version": 1,
        "branch": BRANCH,
        "run_id": run_id,
        "trace_profile_id": TRACE_PROFILE_ID,
        "trace_profile_sha256": TRACE_PROFILE_SHA256,
        "external_runtime_ledger": None,
        "handoffs": [],
    }


def r01_attempt_ordinal(run_id: str, artifact_root: Path) -> int:
    run_dir = require_under(RUNTIME_ROOT / run_id, RUNTIME_ROOT)
    canonical = (run_dir / "artifacts" / "R01").resolve()
    selected = artifact_root.resolve()
    if selected == canonical:
        return 1
    try:
        relative = selected.relative_to(canonical)
    except ValueError as exc:
        raise SchedulerError("R01 artifact root cannot produce a bound attempt ID") from exc
    if len(relative.parts) != 1:
        raise SchedulerError("R01 resume artifact root nesting is invalid")
    match = re.fullmatch(r"resume-(\d{3})", relative.name)
    if match is None:
        raise SchedulerError("R01 resume artifact root cannot produce a stable attempt ID")
    return int(match.group(1)) + 1


def build_r01_bootstrap_assignment(
    bundle: dict[str, Any],
    *,
    run_id: str,
    artifact_root: Path,
    output_handoff: Path,
    ledger_path: Path,
    ledger_sha256: str,
) -> dict[str, Any]:
    validate_run_id(run_id)
    ordinal = r01_attempt_ordinal(run_id, artifact_root)
    attempt_id = f"{run_id}-R01-attempt-{ordinal:03d}"
    if not attempt_id.strip():
        raise SchedulerError("R01 scheduler-generated attempt ID is empty")
    static = bundle["r01_bootstrap"]
    payload = {
        "schema_version": 1,
        "generated_and_validated_before_formal_r01_goal_creation": True,
        "request_selection_manifest": copy.deepcopy(
            static["request_selection_manifest"]
        ),
        "request_selection_manifest_sha256": static[
            "request_selection_manifest_sha256"
        ],
        "target_evidence": copy.deepcopy(static["target_evidence"]),
        "model": copy.deepcopy(static["model"]),
        "runtime_executable": copy.deepcopy(static["runtime_executable"]),
        "service": copy.deepcopy(static["service"]),
        "runtime_binding": {
            "runtime_run_id": run_id,
            "runtime_attempt_id": attempt_id,
            "attempt_ordinal": ordinal,
            "runtime_branch": BRANCH,
            "runtime_goal": "R01",
            "formal_goal_label": "R01",
            "runtime_artifact_root": str(artifact_root),
            "runtime_handoff_output": str(output_handoff),
            "cumulative_runtime_ledger_path": str(ledger_path),
            "cumulative_runtime_ledger_sha256": ledger_sha256,
        },
        "identity_gates": {
            "trace_target_root": str(TRACE_TARGET_ROOT),
            "trace_target_git_commit": TRACE_TARGET_COMMIT,
            "trace_profile_id": TRACE_PROFILE_ID,
            "trace_profile_path": str(TRACE_PROFILE_PATH),
            "trace_profile_sha256": TRACE_PROFILE_SHA256,
            "service_port_fixed": True,
            "attempt_id_nonempty": True,
            "request_count_exactly_eight": True,
            "single_request_expansion_forbidden": True,
            "clock_and_hipprof_manifest_identity_required": True,
        },
    }
    payload["binding_payload_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    return payload


def r01_formal_goal_objective(
    *, skill: str, bootstrap: dict[str, Any]
) -> str:
    """Build a compact Goal identity; the complete bootstrap stays in turn input."""
    selection = bootstrap["request_selection_manifest"]
    summary = {
        "binding_payload_sha256": bootstrap["binding_payload_sha256"],
        "request_selection_manifest_sha256": bootstrap[
            "request_selection_manifest_sha256"
        ],
        "ordered_sequence_canonical_sha256": selection[
            "ordered_sequence_canonical_sha256"
        ],
        "request_ids": [record["request_id"] for record in selection["records"]],
        "model_config_sha256": bootstrap["model"]["config_sha256"],
        "runtime_executable_sha256": bootstrap["runtime_executable"]["sha256"],
        "runtime_executable_version": bootstrap["runtime_executable"]["version"],
        "runtime_attempt_id": bootstrap["runtime_binding"]["runtime_attempt_id"],
        "service_port": bootstrap["service"]["port"],
        "trace_profile_id": TRACE_PROFILE_ID,
        "trace_profile_sha256": TRACE_PROFILE_SHA256,
        "physical_devices": [0, 1],
        "data_parallel_size": 2,
    }
    objective = (
        f"Execute only runtime stage R01 with ${skill} in the fixed "
        f"{TRACE_PROFILE_ID} fresh lineage; complete only after the "
        "scheduler-assigned handoff passes every stage and DP2 gate.\n"
        "The complete R01 bootstrap was generated and hash-validated before "
        "formal Goal creation and is injected in the R01 turn assignment. "
        "Compact bootstrap identity:\n"
        + json.dumps(
            summary,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    if len(objective) > 4000:
        raise SchedulerError(
            f"R01 formal Goal objective exceeds 4000 characters: {len(objective)}"
        )
    return objective


def profile_attestation(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "trace_profile_id": TRACE_PROFILE_ID,
        "trace_profile_path": str(TRACE_PROFILE_PATH),
        "trace_profile_sha256": TRACE_PROFILE_SHA256,
        "workload": copy.deepcopy(profile["workload"]),
        "topology": copy.deepcopy(profile["topology"]),
        "coverage_gate": copy.deepcopy(profile["coverage_gate"]),
        "serial_stage_reduces_device_topology": False,
    }


def dry_run_payload(bundle: dict[str, Any], *, run_id: str | None) -> dict[str, Any]:
    token = run_id or "dry-run-validation"
    validate_run_id(token)
    preview_run_dir = require_under(RUNTIME_ROOT / token, RUNTIME_ROOT)
    preview_ledger_path = preview_run_dir / "runtime_handoff_ledger.json"
    preview_ledger = runtime_ledger_template(token)
    preview_ledger_sha256 = json_document_sha256(preview_ledger)
    r01_bootstrap = build_r01_bootstrap_assignment(
        bundle,
        run_id=token,
        artifact_root=preview_run_dir / "artifacts" / "R01",
        output_handoff=preview_run_dir / "handoffs" / "R01.json",
        ledger_path=preview_ledger_path,
        ledger_sha256=preview_ledger_sha256,
    )
    r01_objective = r01_formal_goal_objective(
        skill=bundle["manifest"]["bindings"]["R01"]["skill"],
        bootstrap=r01_bootstrap,
    )
    goals: list[dict[str, Any]] = []
    for index, goal_id in enumerate(GOAL_IDS):
        binding = bundle["manifest"]["bindings"][goal_id]
        goals.append(
            {
                "id": goal_id,
                "adapt_goal": binding["adapt_goal"],
                "skill": binding["skill"],
                "skill_path": str(bundle["skill_paths"][goal_id]),
                "predecessors": list(GOAL_IDS[:index]),
                "persistent_thread": True,
                "ephemeral": False,
                "formal_goal_created_by_scheduler": True,
                "nested_goal_creation_allowed": False,
                "runtime_artifact_root": str(
                    RUNTIME_ROOT / token / "artifacts" / goal_id
                ),
                "runtime_handoff": str(
                    RUNTIME_ROOT / token / "handoffs" / f"{goal_id}.json"
                ),
                "advance_only_after": "validated_complete_handoff",
                "full_profile_preserved": True,
                "physical_devices": [0, 1],
                "dp_ranks": [0, 1],
                "data_parallel_size": 2,
                "r01_bootstrap_prepared_before_goal_creation": (
                    goal_id == "R01"
                ),
                "runtime_attempt_id": (
                    r01_bootstrap["runtime_binding"]["runtime_attempt_id"]
                    if goal_id == "R01"
                    else None
                ),
            }
        )
    return {
        "schema_version": 1,
        "status": "dry_run",
        "dry_run": True,
        "app_server_contacted": False,
        "goal_created": False,
        "workflow_execution_performed": False,
        "project_skill_execution_performed": False,
        "model_execution_performed": False,
        "gpu_dcu_execution_performed": False,
        "profiler_execution_performed": False,
        "trace_collection_performed": False,
        "pmc_collection_performed": False,
        "report_generation_performed": False,
        "runtime_state_written": False,
        "branch": BRANCH,
        "project_root": str(PROJECT_ROOT),
        "manifest": str(MANIFEST_PATH),
        "manifest_sha256": MANIFEST_SHA256,
        "config": str(CONFIG_PATH),
        "config_sha256": CONFIG_SHA256,
        "trace_target_root": str(TRACE_TARGET_ROOT),
        "trace_target_git_commit": TRACE_TARGET_COMMIT,
        "trace_profile_id": TRACE_PROFILE_ID,
        "trace_profile_path": str(TRACE_PROFILE_PATH),
        "trace_profile_sha256": TRACE_PROFILE_SHA256,
        "project_skill_root": str(PROJECT_SKILL_ROOT),
        "runtime_root": str(RUNTIME_ROOT),
        "run_id": token,
        "run_id_source": "explicit" if run_id is not None else "dry_run_default",
        "workload": copy.deepcopy(bundle["profile"]["workload"]),
        "topology": copy.deepcopy(bundle["profile"]["topology"]),
        "coverage_gate": copy.deepcopy(bundle["profile"]["coverage_gate"]),
        "profile_attestation": profile_attestation(bundle["profile"]),
        "skill_file_sha256": bundle["skill_file_sha256"],
        "skill_tree_sha256": bundle["skill_tree_sha256"],
        "handoff_gate": copy.deepcopy(bundle["manifest"]["handoff_policy"]),
        "r01_bootstrap": r01_bootstrap,
        "r01_bootstrap_validation": {
            "complete_ordered_request_selection_manifest_valid": True,
            "stable_request_ids_and_per_record_hashes_valid": True,
            "ordered_sequence_hash_valid": True,
            "model_directory_and_config_hash_valid": True,
            "runtime_executable_hash_and_version_valid": True,
            "attempt_id_nonempty_and_scheduler_generated": True,
            "service_port_fixed": True,
            "generated_before_formal_goal_creation": True,
            "request_expansion_performed": False,
            "complete_bootstrap_injected_into_r01_turn_assignment": True,
            "complete_bootstrap_serialized_in_formal_goal_objective": False,
            "compact_hash_verifiable_identity_summary_in_formal_goal_objective": True,
            "formal_goal_objective_character_count": len(r01_objective),
            "formal_goal_objective_character_limit": 4000,
            "formal_goal_objective_within_4000_characters": len(r01_objective)
            <= 4000,
        },
        "runtime_ledger_preview": {
            "path": str(preview_ledger_path),
            "sha256": preview_ledger_sha256,
            "payload": preview_ledger,
            "materialized": False,
        },
        "requires": copy.deepcopy(bundle["manifest"]["requires"]),
        "goals": goals,
    }


class AppServerClient:
    """Minimal thread-safe JSONL client for one Codex app-server process."""

    def __init__(
        self,
        *,
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
        self._raw_log: Any = None
        self._stderr_log: Any = None
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
        self._threads = [
            threading.Thread(target=self._read_stdout, daemon=True),
            threading.Thread(target=self._read_stderr, daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def _log(self, direction: str, message: Any) -> None:
        if self._raw_log is None:
            return
        record = {"observed_at": utc_now(), "direction": direction, "message": message}
        with self._log_lock:
            self._raw_log.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._raw_log.flush()

    def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        for line in self.process.stdout:
            stripped = line.rstrip("\n")
            if not stripped:
                continue
            try:
                message = json.loads(stripped)
            except json.JSONDecodeError as exc:
                self._log("server-invalid-json", stripped)
                self.reader_errors.put(f"invalid app-server JSON: {exc}")
                continue
            self._log("server", message)
            if not isinstance(message, dict):
                self.reader_errors.put("app-server message is not an object")
                continue
            if "id" in message and ("result" in message or "error" in message):
                with self._pending_lock:
                    waiter = self._pending.get(message["id"])
                if waiter is None:
                    self.reader_errors.put("response for unknown request id")
                else:
                    waiter.put(message)
            elif "id" in message and "method" in message:
                self.server_requests.put(message)
                self._reject_server_request(message)
            else:
                self.notifications.put(message)
        self.reader_errors.put("app-server stdout closed")

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
        try:
            self._write(
                {
                    "id": message["id"],
                    "error": {
                        "code": -32000,
                        "message": "The serial runtime scheduler is non-interactive.",
                    },
                }
            )
        except RpcError as exc:
            self.reader_errors.put(str(exc))

    def check_health(self) -> None:
        if not self.reader_errors.empty():
            raise RpcError(self.reader_errors.get_nowait())
        if self.process is not None and self.process.poll() is not None:
            raise RpcError(f"app-server exited with code {self.process.returncode}")

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        self.check_health()
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

    def initialize(self) -> None:
        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "qwen_batch8_dp2_perf_trace_runtime",
                    "title": "Qwen batch8 dual-DCU DP2 R01-R10 runtime",
                    "version": "1.0.0",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        self.notify("initialized", {})

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


def resolve_codex_binary(value: str | None) -> Path:
    if value is None:
        discovered = shutil.which("codex")
    elif "/" in value:
        discovered = value
    else:
        discovered = shutil.which(value)
    if discovered is None:
        raise SchedulerError("Codex executable was not found")
    resolved = Path(discovered).expanduser().resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise SchedulerError(f"Codex executable is not runnable: {resolved}")
    return resolved


class RuntimeScheduler:
    """Execute exactly one persistent formal runtime Goal at a time."""

    def __init__(
        self,
        *,
        bundle: dict[str, Any],
        run_id: str,
        codex_bin: Path,
        model: str | None,
        poll_seconds: float,
        request_timeout: float,
        goal_timeout_seconds: float,
        resume: bool,
        resume_from: str | None,
        resume_artifact_root: str | None,
        continue_current_goal: bool,
    ) -> None:
        self.bundle = bundle
        self.run_id = run_id
        self.codex_bin = codex_bin
        self.model = model
        self.poll_seconds = poll_seconds
        self.request_timeout = request_timeout
        self.goal_timeout_seconds = goal_timeout_seconds
        self.resume = resume
        self.resume_from = resume_from
        self.resume_artifact_root = resume_artifact_root
        self.continue_current_goal = continue_current_goal
        self.run_dir = require_under(RUNTIME_ROOT / run_id, RUNTIME_ROOT)
        self.handoff_dir = self.run_dir / "handoffs"
        self.state_path = self.run_dir / "state.json"
        self.ledger_path = self.run_dir / "runtime_handoff_ledger.json"
        self.state: dict[str, Any] = {}
        self.ledger: dict[str, Any] = {}
        self.execution_goal_ids: list[str] = list(GOAL_IDS)
        self.client: AppServerClient | None = None
        self.current_goal_id: str | None = None

    def _checkpoint(self) -> None:
        self.state["updated_at"] = utc_now()
        atomic_write_json(self.state_path, self.state)

    def _new_goal_record(self, goal_id: str) -> dict[str, Any]:
        return {
            "skill": self.bundle["manifest"]["bindings"][goal_id]["skill"],
            "status": "pending",
            "thread_id": None,
            "turn_ids": [],
            "goal": None,
            "runtime_artifact_root": None,
            "runtime_handoff": None,
            "error": None,
        }

    def _initialize_new(self) -> None:
        if self.run_dir.exists():
            raise SchedulerError(f"runtime output directory already exists: {self.run_dir}")
        self.handoff_dir.mkdir(parents=True)
        created = utc_now()
        self.state = {
            "schema_version": 1,
            "branch": BRANCH,
            "run_id": self.run_id,
            "status": "running",
            "execution_status": "running",
            "current_goal": None,
            "created_at": created,
            "updated_at": created,
            "manifest": str(MANIFEST_PATH.relative_to(PROJECT_ROOT)),
            "manifest_sha256": MANIFEST_SHA256,
            "config": str(CONFIG_PATH.relative_to(PROJECT_ROOT)),
            "config_sha256": CONFIG_SHA256,
            "trace_target_root": str(TRACE_TARGET_ROOT),
            "trace_target_git_commit": TRACE_TARGET_COMMIT,
            "trace_profile_id": TRACE_PROFILE_ID,
            "trace_profile_sha256": TRACE_PROFILE_SHA256,
            "external_runtime_ledger": None,
            "ledger": str(self.ledger_path.relative_to(PROJECT_ROOT)),
            "goals": {goal_id: self._new_goal_record(goal_id) for goal_id in GOAL_IDS},
        }
        self.ledger = runtime_ledger_template(self.run_id)
        atomic_write_json(self.ledger_path, self.ledger)
        self._checkpoint()

    def _validate_ledger_prefix(self, expected_goals: list[str]) -> None:
        disk = load_json(self.ledger_path)
        if disk != self.ledger:
            raise SchedulerError("cumulative runtime ledger changed outside scheduler")
        exact = {
            "schema_version": 1,
            "branch": BRANCH,
            "run_id": self.run_id,
            "trace_profile_id": TRACE_PROFILE_ID,
            "trace_profile_sha256": TRACE_PROFILE_SHA256,
            "external_runtime_ledger": None,
        }
        for key, expected in exact.items():
            if self.ledger.get(key) != expected:
                raise SchedulerError(f"cumulative runtime ledger {key} mismatch")
        entries = self.ledger.get("handoffs")
        if not isinstance(entries, list) or len(entries) != len(expected_goals):
            raise SchedulerError("cumulative runtime ledger prefix length mismatch")
        attestation = profile_attestation(self.bundle["profile"])
        for goal_id, entry in zip(expected_goals, entries):
            binding = self.bundle["manifest"]["bindings"][goal_id]
            if not isinstance(entry, dict) or (
                entry.get("source_goal") != goal_id
                or entry.get("status") != "complete"
                or entry.get("skill") != binding["skill"]
                or entry.get("skill_tree_sha256") != binding["skill_tree_sha256"]
            ):
                raise SchedulerError(f"cumulative runtime ledger entry mismatch: {goal_id}")
            path = project_path(str(entry.get("path")), PROJECT_ROOT)
            expected_path = self.handoff_dir / f"{goal_id}.json"
            if path != expected_path.resolve() or not path.is_file():
                raise SchedulerError(f"runtime handoff path mismatch: {goal_id}")
            digest = sha256_file(path)
            if entry.get("sha256") != digest:
                raise SchedulerError(f"runtime handoff hash mismatch: {goal_id}")
            payload = load_json(path)
            if payload != entry.get("payload"):
                raise SchedulerError(f"runtime handoff payload drift: {goal_id}")
            if payload.get("scheduler_profile_attestation") != attestation:
                raise SchedulerError(f"runtime profile attestation mismatch: {goal_id}")

    def _initialize_resume(self) -> None:
        if not self.run_dir.is_dir():
            raise SchedulerError(f"resume runtime directory is missing: {self.run_dir}")
        self.state = load_json(self.state_path)
        self.ledger = load_json(self.ledger_path)
        if not isinstance(self.state, dict) or not isinstance(self.ledger, dict):
            raise SchedulerError("resume state and ledger must be JSON objects")
        exact_state = {
            "schema_version": 1,
            "branch": BRANCH,
            "run_id": self.run_id,
            "manifest_sha256": MANIFEST_SHA256,
            "config_sha256": CONFIG_SHA256,
            "trace_target_root": str(TRACE_TARGET_ROOT),
            "trace_target_git_commit": TRACE_TARGET_COMMIT,
            "trace_profile_id": TRACE_PROFILE_ID,
            "trace_profile_sha256": TRACE_PROFILE_SHA256,
            "external_runtime_ledger": None,
        }
        for key, expected in exact_state.items():
            if self.state.get(key) != expected:
                raise SchedulerError(f"resume state {key} mismatch")
        if self.state.get("status") != "stopped":
            raise SchedulerError("resume requires state.status=stopped")
        records = self.state.get("goals")
        if not isinstance(records, dict) or list(records) != list(GOAL_IDS):
            raise SchedulerError("resume state Goal set mismatch")
        first_index = next(
            (
                index
                for index, goal_id in enumerate(GOAL_IDS)
                if not isinstance(records.get(goal_id), dict)
                or records[goal_id].get("status") != "complete"
            ),
            len(GOAL_IDS),
        )
        if first_index == len(GOAL_IDS):
            raise SchedulerError("runtime is already complete")
        first_goal = GOAL_IDS[first_index]
        if self.resume_from is not None and self.resume_from != first_goal:
            raise SchedulerError(
                f"resume must start at first incomplete Goal {first_goal}"
            )
        self.execution_goal_ids = list(GOAL_IDS[first_index:])
        self._validate_ledger_prefix(list(GOAL_IDS[:first_index]))
        for goal_id in self.execution_goal_ids[1:]:
            if records[goal_id].get("status") == "complete":
                raise SchedulerError("resume state contains a non-serial complete suffix")
        for goal_id in self.execution_goal_ids:
            path = self.handoff_dir / f"{goal_id}.json"
            if path.exists():
                raise SchedulerError(f"refusing uncommitted suffix handoff: {path}")
        if self.continue_current_goal:
            record = records[first_goal]
            goal = record.get("goal")
            goal_status = goal.get("status") if isinstance(goal, dict) else None
            if (
                record.get("status") != "stopped"
                or not isinstance(record.get("thread_id"), str)
                or goal_status not in {"active", "paused"}
            ):
                raise SchedulerError(
                    "--continue-current-goal accepts only a saved active/paused "
                    "persistent Goal; blocked or terminal Goals require a new attempt"
                )
        else:
            for goal_id in self.execution_goal_ids:
                previous = copy.deepcopy(records[goal_id])
                history = previous.get("attempt_history", [])
                if not isinstance(history, list):
                    raise SchedulerError(f"invalid attempt history for {goal_id}")
                if any(value not in (None, [], "pending") for value in previous.values()):
                    history.append({"superseded_at": utc_now(), "record": previous})
                records[goal_id] = self._new_goal_record(goal_id)
                if history:
                    records[goal_id]["attempt_history"] = history
        history = self.state.setdefault("resume_history", [])
        if not isinstance(history, list):
            raise SchedulerError("resume_history must be a list")
        history.append(
            {
                "resumed_at": utc_now(),
                "from_goal": first_goal,
                "execution_goals": self.execution_goal_ids,
                "continue_current_goal": self.continue_current_goal,
                "resume_artifact_root": self.resume_artifact_root,
                "source_state_sha256": sha256_file(self.state_path),
                "source_ledger_sha256": sha256_file(self.ledger_path),
            }
        )
        self.state["status"] = "running"
        self.state["execution_status"] = "running"
        self.state["current_goal"] = None
        self.state.pop("last_error", None)
        self._checkpoint()

    def _initialize_runtime(self) -> None:
        validate_run_id(self.run_id)
        if self.resume:
            self._initialize_resume()
        else:
            self._initialize_new()

    def _start_client(self) -> None:
        self.client = AppServerClient(
            codex_bin=self.codex_bin,
            cwd=PROJECT_ROOT,
            raw_log_path=self.run_dir / "app_server.jsonl",
            stderr_log_path=self.run_dir / "app_server.stderr.log",
            request_timeout=self.request_timeout,
        )
        self.client.start()
        self.client.initialize()
        self.client.request(
            "skills/extraRoots/set", {"extraRoots": [str(PROJECT_SKILL_ROOT)]}
        )
        result = self.client.request(
            "skills/list", {"cwds": [str(PROJECT_ROOT)], "forceReload": True}
        )
        discovered: dict[str, Path] = {}
        if isinstance(result, dict):
            for entry in result.get("data", []):
                if not isinstance(entry, dict):
                    continue
                for skill in entry.get("skills", []):
                    if not isinstance(skill, dict) or skill.get("enabled", True) is not True:
                        continue
                    name = skill.get("name")
                    path = skill.get("path")
                    if isinstance(name, str) and isinstance(path, str):
                        discovered.setdefault(name, Path(path).resolve())
        for goal_id in GOAL_IDS:
            binding = self.bundle["manifest"]["bindings"][goal_id]
            expected = self.bundle["skill_paths"][goal_id]
            if discovered.get(binding["skill"]) != expected:
                raise SchedulerError(
                    f"runtime skill discovery mismatch for {goal_id}: "
                    f"{discovered.get(binding['skill'])} != {expected}"
                )

    def _select_artifact_root(self, goal_id: str) -> Path:
        canonical = self.run_dir / "artifacts" / goal_id
        if (
            self.resume
            and goal_id == self.execution_goal_ids[0]
            and self.resume_artifact_root is not None
        ):
            selected = require_under(Path(self.resume_artifact_root), canonical)
            if not selected.is_dir():
                raise SchedulerError(f"resume artifact root is missing: {selected}")
            return selected
        if not canonical.exists():
            canonical.mkdir(parents=True)
            return canonical
        if not canonical.is_dir():
            raise SchedulerError(f"artifact root is not a directory: {canonical}")
        if not any(canonical.iterdir()):
            return canonical
        if not self.resume:
            raise SchedulerError(f"artifact root already contains files: {canonical}")
        for attempt in range(1, 1000):
            candidate = canonical / f"resume-{attempt:03d}"
            try:
                candidate.mkdir()
            except FileExistsError:
                continue
            return candidate
        raise SchedulerError(f"no available resume artifact root under {canonical}")

    def _profile_stage_assignment(
        self,
        goal_id: str,
        artifact_root: Path,
        output_handoff: Path,
    ) -> dict[str, Any]:
        index = GOAL_IDS.index(goal_id)
        self._validate_ledger_prefix(list(GOAL_IDS[:index]))
        ledger_hash = sha256_file(self.ledger_path)
        predecessor_entries = [
            {
                "runtime_goal": entry["source_goal"],
                "path": entry["path"],
                "sha256": entry["sha256"],
            }
            for entry in self.ledger["handoffs"]
        ]
        static_bootstrap = self.bundle["r01_bootstrap"]
        assignment = {
            "schema_version": 1,
            "project_root": str(PROJECT_ROOT),
            "runtime_branch": BRANCH,
            "runtime_goal": goal_id,
            "runtime_run_id": self.run_id,
            "runtime_root": str(self.run_dir),
            "runtime_artifact_root": str(artifact_root),
            "runtime_handoff_output": str(output_handoff),
            "runtime_config": {"path": str(CONFIG_PATH), "sha256": CONFIG_SHA256},
            "trace_target_root": str(TRACE_TARGET_ROOT),
            "trace_target_git_commit": TRACE_TARGET_COMMIT,
            "trace_profile": profile_attestation(self.bundle["profile"]),
            "request_selection_manifest": copy.deepcopy(
                static_bootstrap["request_selection_manifest"]
            ),
            "request_selection_manifest_sha256": static_bootstrap[
                "request_selection_manifest_sha256"
            ],
            "target_evidence": copy.deepcopy(static_bootstrap["target_evidence"]),
            "model": copy.deepcopy(static_bootstrap["model"]),
            "runtime_executable": copy.deepcopy(
                static_bootstrap["runtime_executable"]
            ),
            "service": copy.deepcopy(static_bootstrap["service"]),
            "cumulative_runtime_ledger": {
                "path": str(self.ledger_path),
                "sha256": ledger_hash,
                "validated_prefix": list(GOAL_IDS[:index]),
            },
            "predecessor_handoffs": predecessor_entries,
            "advance_only_after": "validated_complete_handoff",
            "formal_goal_owner": "outer_serial_runtime_scheduler",
            "nested_goal_creation_allowed": False,
            "external_runtime_evidence_allowed": False,
        }
        if goal_id == "R01":
            r01_bootstrap = build_r01_bootstrap_assignment(
                self.bundle,
                run_id=self.run_id,
                artifact_root=artifact_root,
                output_handoff=output_handoff,
                ledger_path=self.ledger_path,
                ledger_sha256=ledger_hash,
            )
            assignment["r01_bootstrap"] = r01_bootstrap
            assignment["runtime_attempt_id"] = r01_bootstrap["runtime_binding"][
                "runtime_attempt_id"
            ]
            assignment["service_port"] = r01_bootstrap["service"]["port"]
        return assignment

    def _prompt(
        self,
        goal_id: str,
        assignment: dict[str, Any],
    ) -> str:
        binding = self.bundle["manifest"]["bindings"][goal_id]
        predecessors = list(GOAL_IDS[: GOAL_IDS.index(goal_id)])
        predecessor_fields = [f"{goal.lower()}_handoff_sha256" for goal in predecessors]
        required_fields = list(self.bundle["required_handoff_fields"][goal_id])
        for field in (
            "status",
            "execution_status",
            "evidence_status",
            "coverage_target_met",
            "next_authorization_required",
            "runtime_branch",
            "runtime_goal",
            "runtime_run_id",
            "skill",
            "trace_profile_sha256",
            "cumulative_runtime_ledger_sha256",
            "runtime_artifact_root",
            "runtime_handoff_output",
            "scheduler_profile_attestation",
            *predecessor_fields,
        ):
            if field not in required_fields:
                required_fields.append(field)
        if goal_id == "R01":
            for field in (
                "runtime_attempt_id",
                "request_selection_manifest_sha256",
                "request_selection_canonical_sha256",
                "dataset_file_sha256",
                "model_config_sha256",
                "runtime_executable_sha256",
                "runtime_executable_version",
                "service_port",
                "r01_bootstrap_binding_sha256",
            ):
                if field not in required_fields:
                    required_fields.append(field)
        return "\n".join(
            [
                f"${binding['skill']}",
                "",
                f"只执行 runtime Goal {goal_id}。正式 Goal 已由外层串行 scheduler 创建；不得调用 create_goal、不得建立嵌套 Goal、不得执行 Adapt Goal。",
                f"完整遵循已附加的 {binding['skill']} project skill。只消费本次 run 的精确前驱 prefix，不得导入外部 runtime ledger、历史 timing、trace、PMC、device mapping 或报告。",
                "串行只约束 R01-R10 的 stage 顺序；任何模型执行、采集或硬件属性都必须保持下述完整 batch8 dual-DCU DP2 workload/topology，绝不能缩成单卡。",
                "业务产物只能写入 runtime_artifact_root；scheduler handoff 只能写入 runtime_handoff_output，且必须在本 stage 全部检查完成后写。不得修改任何前驱 handoff、ledger 或 artifact。",
                "R01 必须逐字段消费 scheduler 已在正式 Goal 创建前生成并注入的 r01_bootstrap；只能读取 manifest 指定的 8 个原始行，禁止从单条 request 扩增、oversample、shuffle、合成 prompt、扫描模型或动态选择 executable/port。" if goal_id == "R01" else "沿用 R01 固定的 ordered request-selection、model/runtime/service 绑定，不得改变 workload 或完整 DP2 拓扑。",
                "handoff 必须包含 scheduler_profile_attestation，逐字段等于 assignment.trace_profile；必须包含下列 top-level 字段，并把所有前驱 handoff SHA-256、当前累计 ledger SHA-256、profile SHA-256、路径和 run/branch identity 写成精确值。",
                json.dumps(required_fields, ensure_ascii=False, indent=2),
                "只有 execution_status=complete、evidence_status=complete、coverage_target_met=true、next_authorization_required=false 且 fresh lineage/profile/hashes/outputs 全部通过时，才可写 status=complete 并把正式 Goal 标记 complete；否则如实停止，绝不能伪造 handoff。",
                "scheduler assignment（hash-pinned control-plane input）：",
                json.dumps(assignment, ensure_ascii=False, indent=2),
            ]
        )

    def _thread_start_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "cwd": str(PROJECT_ROOT),
            "approvalPolicy": APPROVAL_POLICY,
            "sandbox": SANDBOX_POLICY,
            "ephemeral": False,
        }
        if self.model:
            params["model"] = self.model
        return params

    def _turn_overrides(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "cwd": str(PROJECT_ROOT),
            "approvalPolicy": APPROVAL_POLICY,
            "sandboxPolicy": TURN_SANDBOX_POLICY,
            "effort": "max",
            "summary": "concise",
        }
        if self.model:
            params["model"] = self.model
        return params

    def _goal_record(self, goal_id: str) -> dict[str, Any]:
        return self.state["goals"][goal_id]

    def _get_goal(self, thread_id: str) -> dict[str, Any]:
        assert self.client is not None
        result = self.client.request("thread/goal/get", {"threadId": thread_id})
        goal = result.get("goal") if isinstance(result, dict) else None
        if not isinstance(goal, dict):
            raise SchedulerError(f"thread/goal/get returned no Goal for {thread_id}")
        return goal

    def _get_thread(self, thread_id: str, *, include_turns: bool) -> dict[str, Any]:
        assert self.client is not None
        result = self.client.request(
            "thread/read", {"threadId": thread_id, "includeTurns": include_turns}
        )
        thread = result.get("thread") if isinstance(result, dict) else None
        if not isinstance(thread, dict):
            raise SchedulerError(f"thread/read returned no thread for {thread_id}")
        return thread

    @staticmethod
    def _thread_status(thread: dict[str, Any]) -> str | None:
        status = thread.get("status")
        if isinstance(status, dict):
            value = status.get("type")
            return value if isinstance(value, str) else None
        return status if isinstance(status, str) else None

    def _drain_notification(self, goal_id: str, timeout: float) -> None:
        assert self.client is not None
        if not self.client.reader_errors.empty():
            raise SchedulerError(self.client.reader_errors.get_nowait())
        if not self.client.server_requests.empty():
            request = self.client.server_requests.get_nowait()
            raise SchedulerError(
                f"{goal_id}: app-server requested interactive action "
                f"{request.get('method')}"
            )
        try:
            message = self.client.notifications.get(timeout=timeout)
        except queue.Empty:
            return
        if not isinstance(message, dict):
            return
        params = message.get("params")
        if not isinstance(params, dict):
            return
        record = self._goal_record(goal_id)
        if params.get("threadId") not in (None, record.get("thread_id")):
            return
        method = message.get("method")
        if method == "turn/started":
            turn = params.get("turn")
            turn_id = turn.get("id") if isinstance(turn, dict) else None
            if isinstance(turn_id, str) and turn_id not in record["turn_ids"]:
                record["turn_ids"].append(turn_id)
                self._checkpoint()
        elif method == "thread/goal/updated":
            goal = params.get("goal")
            if isinstance(goal, dict):
                record["goal"] = goal
                self._checkpoint()
        elif method == "error" and params.get("willRetry") is not True:
            raise SchedulerError(f"{goal_id}: app-server error: {params}")

    def _wait_for_goal_complete(self, goal_id: str) -> None:
        record = self._goal_record(goal_id)
        thread_id = record.get("thread_id")
        if not isinstance(thread_id, str):
            raise SchedulerError(f"{goal_id}: persistent thread id is missing")
        deadline = (
            time.monotonic() + self.goal_timeout_seconds
            if self.goal_timeout_seconds > 0
            else None
        )
        last_poll = 0.0
        while deadline is None or time.monotonic() < deadline:
            self._drain_notification(goal_id, 0.5)
            now = time.monotonic()
            if now - last_poll < self.poll_seconds:
                continue
            goal = self._get_goal(thread_id)
            record["goal"] = goal
            self._checkpoint()
            status = goal.get("status")
            if status == "complete":
                return
            if status in TERMINAL_GOAL_STATUSES:
                raise SchedulerError(f"{goal_id}: formal Goal stopped as {status}")
            if status != "active":
                raise SchedulerError(f"{goal_id}: unexpected formal Goal status {status}")
            last_poll = now
        raise SchedulerError(f"{goal_id}: formal Goal exceeded scheduler timeout")

    def _wait_until_idle(self, goal_id: str) -> None:
        record = self._goal_record(goal_id)
        thread_id = record.get("thread_id")
        assert isinstance(thread_id, str)
        while True:
            self._drain_notification(goal_id, 0.2)
            thread = self._get_thread(thread_id, include_turns=True)
            active = any(
                isinstance(turn, dict) and turn.get("status") == "inProgress"
                for turn in thread.get("turns", [])
            )
            if self._thread_status(thread) == "idle" and not active:
                return
            time.sleep(0.2)

    def _set_goal_status(self, goal_id: str, status: str) -> None:
        assert self.client is not None
        record = self._goal_record(goal_id)
        result = self.client.request(
            "thread/goal/set", {"threadId": record["thread_id"], "status": status}
        )
        goal = result.get("goal") if isinstance(result, dict) else None
        if not isinstance(goal, dict):
            raise SchedulerError(f"{goal_id}: thread/goal/set returned no Goal")
        record["goal"] = goal
        self._checkpoint()

    def _start_new_goal(
        self, goal_id: str, artifact_root: Path, output_handoff: Path
    ) -> None:
        assert self.client is not None
        record = self._goal_record(goal_id)
        binding = self.bundle["manifest"]["bindings"][goal_id]
        assignment = self._profile_stage_assignment(
            goal_id, artifact_root, output_handoff
        )
        prompt = self._prompt(goal_id, assignment)
        objective = (
            f"Execute only runtime stage {goal_id} with ${binding['skill']} in "
            f"the fixed {TRACE_PROFILE_ID} fresh lineage; complete only after "
            "the scheduler-assigned handoff passes every stage and DP2 gate."
        )
        if goal_id == "R01":
            objective = r01_formal_goal_objective(
                skill=binding["skill"],
                bootstrap=assignment["r01_bootstrap"],
            )
        if len(objective) > 4000:
            raise SchedulerError(
                f"{goal_id}: formal Goal objective exceeds 4000 characters: "
                f"{len(objective)}"
            )
        result = self.client.request("thread/start", self._thread_start_params())
        thread = result.get("thread") if isinstance(result, dict) else None
        thread_id = thread.get("id") if isinstance(thread, dict) else None
        if not isinstance(thread_id, str):
            raise SchedulerError(f"{goal_id}: thread/start returned no thread id")
        record["thread_id"] = thread_id
        record["status"] = "thread_created"
        self._checkpoint()
        goal_result = self.client.request(
            "thread/goal/set",
            {"threadId": thread_id, "objective": objective, "status": "paused"},
        )
        goal = goal_result.get("goal") if isinstance(goal_result, dict) else None
        if not isinstance(goal, dict):
            raise SchedulerError(f"{goal_id}: formal Goal creation failed")
        record["goal"] = goal
        turn_result = self.client.request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "skill",
                        "name": binding["skill"],
                        "path": str(self.bundle["skill_paths"][goal_id]),
                    },
                ],
                **self._turn_overrides(),
            },
        )
        turn = turn_result.get("turn") if isinstance(turn_result, dict) else None
        turn_id = turn.get("id") if isinstance(turn, dict) else None
        if not isinstance(turn_id, str):
            raise SchedulerError(f"{goal_id}: turn/start returned no Turn id")
        record["turn_ids"].append(turn_id)
        record["status"] = "running"
        self._checkpoint()
        observed_goal = self._get_goal(thread_id)
        record["goal"] = observed_goal
        self._checkpoint()
        status = observed_goal.get("status")
        if status == "complete":
            self._wait_until_idle(goal_id)
            return
        if status in TERMINAL_GOAL_STATUSES:
            raise SchedulerError(f"{goal_id}: formal Goal stopped as {status}")
        if status == "paused":
            self._set_goal_status(goal_id, "active")
        elif status != "active":
            raise SchedulerError(f"{goal_id}: unexpected formal Goal status {status}")
        self._wait_for_goal_complete(goal_id)
        self._wait_until_idle(goal_id)

    def _continue_goal(self, goal_id: str) -> None:
        assert self.client is not None
        record = self._goal_record(goal_id)
        thread_id = record.get("thread_id")
        if not isinstance(thread_id, str):
            raise SchedulerError(f"{goal_id}: continuation thread id is missing")
        params: dict[str, Any] = {
            "threadId": thread_id,
            "cwd": str(PROJECT_ROOT),
            "approvalPolicy": APPROVAL_POLICY,
            "sandbox": SANDBOX_POLICY,
            "excludeTurns": False,
        }
        if self.model:
            params["model"] = self.model
        result = self.client.request("thread/resume", params)
        thread = result.get("thread") if isinstance(result, dict) else None
        if not isinstance(thread, dict) or thread.get("id") != thread_id:
            raise SchedulerError(f"{goal_id}: persistent thread resume failed")
        goal = self._get_goal(thread_id)
        record["goal"] = goal
        record["status"] = "running"
        self._checkpoint()
        status = goal.get("status")
        if status == "paused":
            self._set_goal_status(goal_id, "active")
        elif status != "active":
            raise SchedulerError(f"{goal_id}: continuation status is {status}")
        self._wait_for_goal_complete(goal_id)
        self._wait_until_idle(goal_id)

    def _validate_handoff(
        self,
        goal_id: str,
        path: Path,
        artifact_root: Path,
        ledger_hash_before_stage: str,
    ) -> dict[str, Any]:
        payload = load_json(path)
        if not isinstance(payload, dict) or not payload:
            raise SchedulerError(f"{goal_id}: runtime handoff is empty")
        binding = self.bundle["manifest"]["bindings"][goal_id]
        exact = {
            "runtime_goal": goal_id,
            "runtime_branch": BRANCH,
            "runtime_run_id": self.run_id,
            "status": "complete",
            "execution_status": "complete",
            "evidence_status": "complete",
            "coverage_target_met": True,
            "next_authorization_required": False,
            "skill": binding["skill"],
            "trace_profile_sha256": TRACE_PROFILE_SHA256,
            "cumulative_runtime_ledger_sha256": ledger_hash_before_stage,
            "runtime_artifact_root": str(artifact_root),
            "runtime_handoff_output": str(path),
            "scheduler_profile_attestation": profile_attestation(
                self.bundle["profile"]
            ),
        }
        if goal_id == "R01":
            bootstrap = build_r01_bootstrap_assignment(
                self.bundle,
                run_id=self.run_id,
                artifact_root=artifact_root,
                output_handoff=path,
                ledger_path=self.ledger_path,
                ledger_sha256=ledger_hash_before_stage,
            )
            request_manifest = bootstrap["request_selection_manifest"]
            exact.update(
                {
                    "runtime_attempt_id": bootstrap["runtime_binding"][
                        "runtime_attempt_id"
                    ],
                    "request_selection_manifest_sha256": bootstrap[
                        "request_selection_manifest_sha256"
                    ],
                    "request_selection_canonical_sha256": request_manifest[
                        "ordered_sequence_canonical_sha256"
                    ],
                    "dataset_file_sha256": request_manifest[
                        "dataset_file_sha256"
                    ],
                    "model_config_sha256": bootstrap["model"]["config_sha256"],
                    "runtime_executable_sha256": bootstrap[
                        "runtime_executable"
                    ]["sha256"],
                    "runtime_executable_version": bootstrap[
                        "runtime_executable"
                    ]["version"],
                    "service_port": bootstrap["service"]["port"],
                    "r01_bootstrap_binding_sha256": bootstrap[
                        "binding_payload_sha256"
                    ],
                }
            )
        for key, expected in exact.items():
            if payload.get(key) != expected:
                raise SchedulerError(
                    f"{goal_id}: runtime handoff {key} mismatch; expected "
                    f"{expected!r}, observed {payload.get(key)!r}"
                )
        required_fields = self.bundle["required_handoff_fields"][goal_id]
        missing = [field for field in required_fields if field not in payload]
        if missing:
            raise SchedulerError(f"{goal_id}: missing required handoff fields: {missing}")
        index = GOAL_IDS.index(goal_id)
        entries = self.ledger["handoffs"]
        for predecessor, entry in zip(GOAL_IDS[:index], entries):
            field = f"{predecessor.lower()}_handoff_sha256"
            if payload.get(field) != entry["sha256"]:
                raise SchedulerError(f"{goal_id}: predecessor hash mismatch in {field}")
        if index and "predecessor_handoff_sha256" in payload:
            if payload["predecessor_handoff_sha256"] != entries[-1]["sha256"]:
                raise SchedulerError(f"{goal_id}: immediate predecessor hash mismatch")
        for field in required_fields:
            if field.endswith("_sha256"):
                value = payload.get(field)
                if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
                    raise SchedulerError(f"{goal_id}: invalid SHA-256 field {field}")
        if goal_id in GOAL_IDS[5:]:
            evidence = payload.get("fresh_e2e_evidence")
            if not isinstance(evidence, dict) or (
                evidence.get("schema_version") != 1
                or evidence.get("status") != "complete"
                or not isinstance(evidence.get("lineage_id"), str)
                or not evidence["lineage_id"].strip()
            ):
                raise SchedulerError(f"{goal_id}: fresh lineage evidence is incomplete")
            prior_lineages = []
            for entry in entries:
                prior = entry.get("payload", {}).get("fresh_e2e_evidence")
                if isinstance(prior, dict) and isinstance(prior.get("lineage_id"), str):
                    prior_lineages.append(prior["lineage_id"])
            if prior_lineages and any(
                lineage != evidence["lineage_id"] for lineage in prior_lineages
            ):
                raise SchedulerError(f"{goal_id}: fresh lineage changed")
        return payload

    def _commit_handoff(
        self,
        goal_id: str,
        output_handoff: Path,
        artifact_root: Path,
        ledger_hash_before_stage: str,
    ) -> None:
        if sha256_file(self.ledger_path) != ledger_hash_before_stage:
            raise SchedulerError(f"{goal_id}: cumulative ledger changed during Goal")
        payload = self._validate_handoff(
            goal_id, output_handoff, artifact_root, ledger_hash_before_stage
        )
        binding = self.bundle["manifest"]["bindings"][goal_id]
        entry = {
            "source_goal": goal_id,
            "status": "complete",
            "skill": binding["skill"],
            "skill_tree_sha256": binding["skill_tree_sha256"],
            "path": str(output_handoff),
            "sha256": sha256_file(output_handoff),
            "payload": payload,
        }
        self.ledger["handoffs"].append(entry)
        atomic_write_json(self.ledger_path, self.ledger)
        record = self._goal_record(goal_id)
        record["status"] = "complete"
        record["runtime_handoff"] = str(output_handoff.relative_to(PROJECT_ROOT))
        record["handoff_sha256"] = entry["sha256"]
        record["error"] = None
        self._checkpoint()

    def _run_goal(self, goal_id: str) -> None:
        index = GOAL_IDS.index(goal_id)
        self._validate_ledger_prefix(list(GOAL_IDS[:index]))
        output_handoff = self.handoff_dir / f"{goal_id}.json"
        if output_handoff.exists():
            raise SchedulerError(f"refusing to overwrite runtime handoff: {output_handoff}")
        record = self._goal_record(goal_id)
        continuing = (
            self.resume
            and self.continue_current_goal
            and goal_id == self.execution_goal_ids[0]
        )
        if continuing:
            artifact_value = record.get("runtime_artifact_root")
            if not isinstance(artifact_value, str):
                raise SchedulerError(f"{goal_id}: continuation artifact root missing")
            artifact_root = project_path(artifact_value, PROJECT_ROOT)
        else:
            artifact_root = self._select_artifact_root(goal_id)
            record["runtime_artifact_root"] = str(
                artifact_root.relative_to(PROJECT_ROOT)
            )
        record["runtime_handoff"] = str(output_handoff.relative_to(PROJECT_ROOT))
        record["status"] = "running"
        self.state["current_goal"] = goal_id
        self.current_goal_id = goal_id
        self._checkpoint()
        ledger_hash = sha256_file(self.ledger_path)
        if continuing:
            self._continue_goal(goal_id)
        else:
            self._start_new_goal(goal_id, artifact_root, output_handoff)
        self._commit_handoff(
            goal_id, output_handoff, artifact_root, ledger_hash
        )

    def _pause_current_goal(self) -> None:
        if self.client is None or self.current_goal_id is None:
            return
        record = self._goal_record(self.current_goal_id)
        thread_id = record.get("thread_id")
        if not isinstance(thread_id, str):
            return
        try:
            goal = self._get_goal(thread_id)
            if goal.get("status") == "active":
                self._set_goal_status(self.current_goal_id, "paused")
        except SchedulerError:
            pass

    def run(self) -> dict[str, Any]:
        try:
            self._initialize_runtime()
            self._start_client()
            for goal_id in self.execution_goal_ids:
                self._run_goal(goal_id)
            self.current_goal_id = None
            self.state["current_goal"] = None
            self.state["status"] = "complete"
            self.state["execution_status"] = "complete"
            self.state["completed_at"] = utc_now()
            self._checkpoint()
            return {
                "status": "complete",
                "execution_status": "complete",
                "branch": BRANCH,
                "run_id": self.run_id,
                "run_dir": str(self.run_dir),
                "goals": self.execution_goal_ids,
                "ledger": str(self.ledger_path),
                "trace_profile_id": TRACE_PROFILE_ID,
                "physical_devices": [0, 1],
                "data_parallel_size": 2,
            }
        except BaseException as exc:
            if self.state:
                self._pause_current_goal()
                self.state["status"] = "stopped"
                self.state["execution_status"] = "stopped"
                self.state["last_error"] = str(exc)
                if self.current_goal_id is not None:
                    record = self._goal_record(self.current_goal_id)
                    if record.get("status") != "complete":
                        record["status"] = "stopped"
                        record["error"] = str(exc)
                self._checkpoint()
            raise
        finally:
            if self.client is not None:
                self.client.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the fixed batch8 dual-DCU DP2 R01-R10 runtime as serial "
            "persistent Codex Goals."
        )
    )
    parser.add_argument(
        "--project-root", default=str(PROJECT_ROOT), help="Fixed project root."
    )
    parser.add_argument(
        "--branch", required=True, choices=[BRANCH], help="Fixed runtime branch."
    )
    parser.add_argument(
        "--user-parameters-file",
        help="Must resolve to the fixed hash-pinned batch8 DP2 configuration.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate and print the control-plane plan without app-server, "
            "Goal creation, project-skill execution, or runtime-state writes."
        ),
    )
    run_group = parser.add_mutually_exclusive_group()
    run_group.add_argument("--run-id", help="New runtime run id.")
    run_group.add_argument("--resume-run-id", help="Existing stopped runtime run id.")
    parser.add_argument(
        "--resume-from",
        choices=list(GOAL_IDS),
        help="Must equal the first incomplete Goal of --resume-run-id.",
    )
    parser.add_argument(
        "--resume-artifact-root",
        help=(
            "Reuse an explicitly audited artifact root under the first "
            "incomplete Goal's canonical artifact directory."
        ),
    )
    parser.add_argument(
        "--continue-current-goal",
        action="store_true",
        help=(
            "Reattach only to a saved active/paused persistent Goal. Blocked "
            "or terminal Goals are rejected."
        ),
    )
    parser.add_argument("--codex-bin", help="Codex executable for non-dry runs.")
    parser.add_argument("--model", help="Optional Codex model override.")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--request-timeout-seconds", type=float, default=120.0)
    parser.add_argument(
        "--goal-timeout-seconds",
        type=float,
        default=0.0,
        help="Per-Goal timeout; zero means no scheduler deadline.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if args.poll_seconds <= 0 or args.request_timeout_seconds <= 0:
            raise SchedulerError("poll and request timeout values must be positive")
        if args.goal_timeout_seconds < 0:
            raise SchedulerError("Goal timeout must be zero or positive")
        if args.resume_from and not args.resume_run_id:
            raise SchedulerError("--resume-from requires --resume-run-id")
        if args.resume_artifact_root and not args.resume_run_id:
            raise SchedulerError("--resume-artifact-root requires --resume-run-id")
        if args.continue_current_goal and not args.resume_run_id:
            raise SchedulerError("--continue-current-goal requires --resume-run-id")
        project_root = Path(args.project_root).expanduser().resolve()
        bundle = validate_fixed_bundle(
            project_root,
            args.branch,
            require_target_clean=(args.dry_run or not args.resume_run_id),
            user_parameters_file=args.user_parameters_file,
        )
        if args.dry_run:
            print(
                json.dumps(
                    dry_run_payload(bundle, run_id=args.run_id),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        codex_bin = resolve_codex_binary(args.codex_bin)
        run_id = args.resume_run_id or args.run_id or default_run_id()
        scheduler = RuntimeScheduler(
            bundle=bundle,
            run_id=run_id,
            codex_bin=codex_bin,
            model=args.model,
            poll_seconds=args.poll_seconds,
            request_timeout=args.request_timeout_seconds,
            goal_timeout_seconds=args.goal_timeout_seconds,
            resume=args.resume_run_id is not None,
            resume_from=args.resume_from,
            resume_artifact_root=args.resume_artifact_root,
            continue_current_goal=args.continue_current_goal,
        )
        print(json.dumps(scheduler.run(), ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        print("batch8 DP2 runtime scheduler interrupted", file=sys.stderr)
        return 130
    except SchedulerError as exc:
        print(f"batch8 DP2 runtime scheduler failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
