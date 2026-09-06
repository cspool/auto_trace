#!/usr/bin/env python3
"""Independent fail-closed R07 audit, manifest, lineage, and handoff writer."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import bisect
import csv
import hashlib
import json
import os
import stat
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from r07_common import (
    ARTIFACT_ROOT,
    ATTEMPT_ID,
    BRANCH,
    BULK_AUTH_PATH,
    BULK_ENTRYPOINTS,
    BULK_PATHS,
    BULK_ROOT,
    CAPTURE_DB_CHECKPOINT_HELPER,
    CAPTURE_DB_DURABLE_MARKER,
    DURABLE_NFS_PATHS,
    DURABLE_NFS_ROOT,
    EXPECTED,
    HANDOFF_OUTPUT,
    LEDGER_PATH,
    LINEAGE_ID,
    PREDECESSOR_VALIDATION_PATH,
    PROFILE_PATH,
    PROJECT_ROOT,
    R01_ROOT,
    R01_REQUEST_MANIFEST_PATH,
    R02_SOURCE_MANIFEST_PATH,
    R07_BOUND_TARGET_SIDECAR_PATH,
    R07_RUNTIME_BINDING_ROOT,
    R06_TARGETS_PATH,
    RESOLVED_CONTRACT_PATH,
    RUN_ID,
    RUNTIME_CONFIG_PATH,
    TARGET_ROOT,
    TRACE_PROFILE_ATTESTATION,
    canonical_sha256,
    git_output,
    load_request_manifest,
    open_device_fds,
    port_is_listening,
    process_identity_alive,
    require,
    require_equal,
    sha256_path,
    tool_manifest_path,
    validate_frozen_tools,
    write_json_x,
)


TOOLS_ROOT = ARTIFACT_ROOT / "tools"
VALIDATION_ROOT = ARTIFACT_ROOT / "validation"
CAPTURE_ROOT = ARTIFACT_ROOT / "capture"
RAW_ROOT = CAPTURE_ROOT / "raw"
HIPPROF_TMP = CAPTURE_ROOT / "hipprof_tmp"
TRACE_ROOT = ARTIFACT_ROOT / "trace"
ALIGNMENT_ROOT = ARTIFACT_ROOT / "alignment"
DEPENDENCY_ROOT = ARTIFACT_ROOT / "dependency"

PROCESS_PATH = TRACE_ROOT / "process_ranges.csv"
RUNTIME_PATH = TRACE_ROOT / "hip_runtime_calls.csv"
KERNEL_PATH = TRACE_ROOT / "strict_owned_kernels.csv"
QUEUE_PATH = TRACE_ROOT / "queue_stream_timeline.csv"
BUSY_PATH = TRACE_ROOT / "gpu_busy_union.csv"
PROCESS_ALIGNMENT_PATH = ALIGNMENT_ROOT / "r07_process_live_utilization.csv"
GAP_ALIGNMENT_PATH = ALIGNMENT_ROOT / "r07_live_utilization_gaps.csv"
ALIGNED_SAMPLE_PATH = ALIGNMENT_ROOT / "r07_live_utilization_aligned.csv"
LIVE_SUMMARY_PATH = ALIGNMENT_ROOT / "live_utilization_summary.json"
PROFILE_METADATA_PATH = CAPTURE_ROOT / "full_request_profile_metadata.json"
PROCESS_SUMMARY_PATH = TRACE_ROOT / "process_trace_summary.json"
DEPENDENCY_PATH = DEPENDENCY_ROOT / "fresh_run_dependency_adapter.json"
DEPENDENCY_CSV_PATH = DEPENDENCY_ROOT / "fresh_run_dependency_adapter.csv"
SOURCE_LINEAGE_PATH = ARTIFACT_ROOT / "lineage/R07_SOURCE_LINEAGE.json"
SOURCE_IMMUTABILITY_PATH = VALIDATION_ROOT / "source_immutability.json"
COMPLETION_AUDIT_PATH = VALIDATION_ROOT / "r07_completion_audit.json"
ARTIFACT_MANIFEST_PATH = ARTIFACT_ROOT / "manifests/artifact_manifest.json"
RAW_INVENTORY_PATH = CAPTURE_ROOT / "raw_inventory.json"
LIFECYCLE_PATH = CAPTURE_ROOT / "lifecycle.json"
DRIVER_PATH = CAPTURE_ROOT / "workload/driver.json"
ANCHOR_PATH = ARTIFACT_ROOT / "live_utilization/clock_anchors.json"
RAW_SAMPLE_PATH = ARTIFACT_ROOT / "live_utilization/raw_samples.csv"
RAW_GAP_PATH = ARTIFACT_ROOT / "live_utilization/raw_gap_intervals.csv"
COPY_MANIFEST_PATH = ARTIFACT_ROOT / "contract/r01_aot_cache_copy_manifest.json"
SOURCE_DELTA_PATH = ARTIFACT_ROOT / "revisions/stage_source_delta.json"
ATTEMPT_HISTORY_PATH = ARTIFACT_ROOT / "attempt_history.json"
PREFREEZE_MARKER_REGRESSION_PATH = VALIDATION_ROOT / "pre_freeze_marker_denominator_regression.json"
PREFREEZE_POSTDEVICE_REGRESSION_PATH = VALIDATION_ROOT / "pre_freeze_postdevice_recovery_regressions.json"
PREFREEZE_BULK_REGRESSION_PATH = VALIDATION_ROOT / "pre_freeze_bulk_preparation_regression.json"
PREFREEZE_REQUEST_HASH_REGRESSION_PATH = VALIDATION_ROOT / "pre_freeze_request_manifest_hash_regression.json"
PREFREEZE_COLLECTOR_SHUTDOWN_REGRESSION_PATH = VALIDATION_ROOT / "pre_freeze_collector_shutdown_fixture/collector_shutdown_regression.json"
PREFREEZE_DURABLE_COPY_REGRESSION_PATH = VALIDATION_ROOT / "pre_freeze_durable_copy_fixture/durable_copy_regression.json"
PREFREEZE_RUNTIME_PATCH_REGRESSION_PATH = VALIDATION_ROOT / "pre_freeze_runtime_patch_path_regression.json"
PREFREEZE_BYTECODE_SURFACE_REGRESSION_PATH = VALIDATION_ROOT / "pre_freeze_bytecode_surface_regression.json"
PREFREEZE_FIXTURE_ROOT = VALIDATION_ROOT / "prefreeze_nonregular_fixture"
PREFREEZE_FIXTURE_STORAGE = PREFREEZE_FIXTURE_ROOT / "storage"
PREFREEZE_FIXTURE_ENTRYPOINT = PREFREEZE_FIXTURE_ROOT / "entrypoint"
PREFREEZE_FIXTURE_SOCKET = PREFREEZE_FIXTURE_STORAGE / "preserved.sock"
PREFREEZE_FIXTURE_SOCKET_ENTRYPOINT = PREFREEZE_FIXTURE_ENTRYPOINT / "preserved.sock"
QUARANTINE_RECORD_PATH = (
    ARTIFACT_ROOT / "quarantine/pre_freeze_python_bytecode/quarantine_record.json"
)
SKILL_PATH = PROJECT_ROOT / "perf_trace_batch8/skills/qwen-dcu-workflow05-full-request-process-trace/SKILL.md"
PREPOSTPROCESS_NATIVE_SEAL_PATH = CAPTURE_ROOT / "prepostprocess_native_capture_seal.json"
DURABLE_COPY_MANIFEST_PATH = CAPTURE_ROOT / "durable_raw_copy_manifest.json"
DURABLE_COMPLETION_MARKER_PATH = DURABLE_NFS_ROOT / "DURABLE_COPY_COMPLETE.json"
DB_CHECKPOINT_INVOCATION_PATH = (
    ARTIFACT_ROOT / "attempts/capture_db_checkpoint_invocation.json"
)
DB_CHECKPOINT_STDOUT_PATH = (
    ARTIFACT_ROOT / "attempts/capture_db_checkpoint.stdout.txt"
)
DB_CHECKPOINT_STDERR_PATH = (
    ARTIFACT_ROOT / "attempts/capture_db_checkpoint.stderr.txt"
)
OFFLINE_EXPORT_INVOCATION_PATH = (
    ARTIFACT_ROOT / "attempts/offline_pftrace_export_invocation.json"
)
OFFLINE_EXPORT_STDOUT_PATH = (
    ARTIFACT_ROOT / "attempts/offline_pftrace_export.stdout.txt"
)
OFFLINE_EXPORT_STDERR_PATH = (
    ARTIFACT_ROOT / "attempts/offline_pftrace_export.stderr.txt"
)
R06_REQUEST_PHASE_SELECTION_REVISION_SHA256 = (
    "032b7e5bf71acbf538e3602b48306edddadf66e17d3a3c6b710d35d56b542415"
)

HANDOFF_HASHES = {
    "R01": "f28cb9274151c5b08f15964e9645cbcaa41b90fb6f867607472028e993b774d6",
    "R02": "9c1b908430fe9757935d029e8f423192652f21675aeffd77bc6a0f5d48d2e7e6",
    "R03": "f7e6066bd72272cee9e96d2ac31596bd20f01841157bda4d0c2eb56092f99885",
    "R04": "403af982ff2f70f89fce2cfda59074a9b014a32e95c53e9e05e292dc843e6719",
    "R05": "db08474f64a999428287388a949762274716df125132cbccbabe3ec23c1aec66",
    "R06": "0da6d692f1d69194ab02f4de0993c7aaca2381793eeb61ce33ffeb52ec058976",
}
SOURCE_HASHES = {
    "vllm/model_executor/models/qwen3_5.py": "f3c0479dbc37a8794c4d6b1c4c01906ae341b3276ed43e588c17d92b1ddb94d6",
    "vllm/model_executor/models/qwen3_next.py": "5a14b14a40fcf6382f9a20be4ca0f850b2b19b2840a3c57488821f0952d96053",
    "vllm/v1/worker/gpu_model_runner.py": "d63424d3cbe81bfaa2c0967a5c81b8c980c2d76bc7eb3b2f8fe2a079af825bce",
    "vllm/utils/nvtx_pytorch_hooks.py": "e9711444f33242ce1864d6a32d051bbf0ba0b37b5f17965de6e5dbba0c0c75ff",
    "vllm/compilation/wrapper.py": "b4dca93456e945ce8231e9a954792c8f687d5d48b427ed38bfb96011015d4090",
    "scripts/serve_cscc_dp2.sh": "233bb2ce6fee3654bc870e37e65b7ecf4de6874cb6c7fd1a6bd5687a40783699",
    "scripts/bench_cscc_multi_request.sh": "9b5e02116911729e901077866389e448c0e4a055e8bb901ed160dcdc7664a595",
    "scripts/cscc_gfx936_env.sh": "58d483450c23e9c4fa87fb981b5e63cf4babf5e8d230fe93e400563596dfc18a",
    "docs/cscc/DP2_MULTI_REQUEST.md": "f83ebea84fd570908be0df58255eca371ad4c28c4dc9d70ec3db0401b1143569",
}
PROVEN_LAUNCH_APIS = {"hipLaunchKernel", "hipModuleLaunchKernel", "hipExtModuleLaunchKernel"}

# This constant is exercised by the production pre-device gate.
REQUIRED_BUSINESS_ARTIFACTS = frozenset({
    "contract/resolved_input_contract.json",
    "contract/r01_r02_r03_r04_r05_r06_predecessor_validation.json",
    "contract/r01_aot_cache_copy_manifest.json",
    "contract/r07_full_request_selection.json",
    "contract/r07_full_request_hiptx_sidecar.json",
    "contract/r07_process_range_inventory.json",
    "contract/r07_bound_target_sidecar.json",
    "contract/r07_runtime_contract_hashes.json",
    "contract/frozen_tool_manifest.json",
    "authorization/retry_authorization.json",
    "authorization/monitor_advisory.json",
    "authorization/bulk_storage_authorization.json",
    "revisions/stage_source_delta.json",
    "revisions/tool_template_lineage.json",
    "quarantine/pre_freeze_python_bytecode/quarantine_record.json",
    "attempt_history.json",
    "attempts/bulk_storage_preparation_invocation.json",
    "attempts/predevice_gate_invocation.json",
    "attempts/predevice_gate.stdout.txt",
    "attempts/predevice_gate.stderr.txt",
    "attempts/capture_db_checkpoint_invocation.json",
    "attempts/capture_db_checkpoint.stdout.txt",
    "attempts/capture_db_checkpoint.stderr.txt",
    "attempts/offline_pftrace_export_invocation.json",
    "attempts/offline_pftrace_export.stdout.txt",
    "attempts/offline_pftrace_export.stderr.txt",
    "validation/pre_freeze_admission_schema_regression.json",
    "validation/pre_freeze_bulk_preparation_regression.json",
    "validation/pre_freeze_request_manifest_hash_regression.json",
    "validation/pre_freeze_collector_shutdown_fixture/collector_shutdown_regression.json",
    "validation/pre_freeze_durable_copy_fixture/durable_copy_regression.json",
    "validation/pre_freeze_marker_denominator_regression.json",
    "validation/pre_freeze_postdevice_recovery_regressions.json",
    "validation/pre_freeze_runtime_patch_path_regression.json",
    "validation/pre_freeze_bytecode_surface_regression.json",
    "validation/pre_bulk_production_selector_regression.json",
    "validation/predevice_gate_report.json",
    "validation/formal_device_preflight.json",
    "validation/marker_transport_audit.json",
    "validation/strict_ownership_audit.json",
    "validation/live_utilization_losslessness_audit.json",
    "validation/rank_device_coverage.json",
    "validation/source_immutability.json",
    "validation/r07_completion_audit.json",
    "capture/lifecycle.json",
    "capture/prepostprocess_native_capture_seal.json",
    "capture/durable_raw_copy_manifest.json",
    "capture/raw_inventory.json",
    "capture/full_request_profile_metadata.json",
    "capture/workload/driver.json",
    "capture/workload/request_results.json",
    "capture/workload/warmup_results.json",
    "capture/workload/runtime_bindings/rank0.jsonl",
    "capture/workload/runtime_bindings/rank1.jsonl",
    "capture/control/all_processes_termination.json",
    "capture/control/post_capture_process_verification.json",
    "trace/request_ranges.csv",
    "trace/forward_ranges.csv",
    "trace/layer_ranges.csv",
    "trace/process_ranges.csv",
    "trace/hip_runtime_calls.csv",
    "trace/strict_owned_kernels.csv",
    "trace/queue_stream_timeline.csv",
    "trace/gpu_busy_union.csv",
    "trace/process_trace_summary.json",
    "live_utilization/raw_samples.csv",
    "live_utilization/raw_gap_intervals.csv",
    "live_utilization/clock_anchors.json",
    "alignment/r07_live_utilization_aligned.csv",
    "alignment/r07_process_live_utilization.csv",
    "alignment/r07_live_utilization_gaps.csv",
    "alignment/live_utilization_summary.json",
    "dependency/fresh_run_dependency_adapter.csv",
    "dependency/fresh_run_dependency_adapter.json",
    "lineage/R07_SOURCE_LINEAGE.json",
    "manifests/artifact_manifest.json",
    *{f"tools/{name}" for name in (
        "build_r07_capture_contract.py", "run_r07_full_request.py",
        "collect_r07_live_utilization.py", "normalize_r07_process_trace.py",
        "align_r07_live_utilization.py", "build_r07_dependency_adapter.py",
        "audit_r07_capture.py", "freeze_r07_tools.py", "materialize_r07_runtime_contracts.py",
        "prepare_r07_bulk_storage.py", "r07_common.py", "r07_hiptx_adapter.py",
        "r07_marker_contract.py", "r07_runtime_patch_loader.py", "r07_workload_driver.py",
        "sitecustomize.py", "vllm_r07_contract_shim.sh",
    )},
})


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON document is not an object: {path}")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    require(str(value).lower() in {"true", "false"}, f"invalid boolean value: {value!r}")
    return str(value).lower() == "true"


def _file_record(path: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"required regular file absent: {path}")
    return {"path": str(path), "size": path.stat().st_size, "sha256": sha256_path(path)}


def _lstat_record(path: Path, relative_path: str) -> dict[str, Any]:
    observed = path.lstat()
    mode = observed.st_mode
    object_kind = (
        "regular_file" if stat.S_ISREG(mode)
        else "directory" if stat.S_ISDIR(mode)
        else "symbolic_link" if stat.S_ISLNK(mode)
        else "unix_domain_socket" if stat.S_ISSOCK(mode)
        else "fifo" if stat.S_ISFIFO(mode)
        else "character_device" if stat.S_ISCHR(mode)
        else "block_device" if stat.S_ISBLK(mode)
        else "unknown_nonregular"
    )
    return {
        "object_kind": object_kind,
        "filesystem_device": observed.st_dev,
        "inode": observed.st_ino,
        "mode": mode,
        "size": observed.st_size,
        "relative_path": relative_path,
    }


def _canonical_file(path: Path) -> bytes:
    return (json.dumps(_read_json(path), ensure_ascii=False, sort_keys=True, separators=(",", ":"))).encode("utf-8")


def _validate_identity(document: dict[str, Any], label: str) -> None:
    require_equal(f"{label} status", document.get("status"), "complete")
    require_equal(f"{label} run", document.get("runtime_run_id"), RUN_ID)
    require_equal(f"{label} attempt", document.get("runtime_attempt_id"), ATTEMPT_ID)
    require_equal(f"{label} lineage", document.get("lineage_id"), LINEAGE_ID)


def _audit_static_and_source() -> dict[str, Any]:
    require_equal("trace profile hash", sha256_path(PROFILE_PATH), EXPECTED["profile_sha256"])
    require_equal("runtime config hash", sha256_path(RUNTIME_CONFIG_PATH), EXPECTED["runtime_config_sha256"])
    require_equal("ledger hash", sha256_path(LEDGER_PATH), EXPECTED["ledger_sha256"])
    retry_path = ARTIFACT_ROOT / "authorization/retry_authorization.json"
    monitor_path = ARTIFACT_ROOT / "authorization/monitor_advisory.json"
    require_equal("retry authorization hash", sha256_path(retry_path), EXPECTED["retry_authorization_sha256"])
    require_equal("monitor advisory hash", sha256_path(monitor_path), EXPECTED["monitor_advisory_sha256"])
    require_equal("bulk authorization hash", sha256_path(BULK_AUTH_PATH), EXPECTED["bulk_storage_authorization_sha256"])
    require_equal("skill hash", sha256_path(SKILL_PATH), "50f5985cdb91765f452fd607fab630b4d268f36e539a419823b0550609acbc9f")
    require_equal("target commit", git_output("rev-parse", "HEAD"), EXPECTED["target_commit"])
    require_equal("target branch", git_output("branch", "--show-current"), "repro-gqa-page784-k5120-batch8-final")
    require_equal("target staged delta", git_output("diff", "--cached", "--name-only"), "")
    require_equal("target worktree delta", git_output("diff", "--name-only"), "")
    require_equal("target untracked", git_output("ls-files", "--others", "--exclude-standard"), "")
    source_rows = []
    for relative, expected in SOURCE_HASHES.items():
        path = TARGET_ROOT / relative
        observed = sha256_path(path)
        require_equal(f"source hash {relative}", observed, expected)
        source_rows.append({"relative_path": relative, "path": str(path), "size": path.stat().st_size, "sha256": observed})
    direct = {}
    for goal, expected in HANDOFF_HASHES.items():
        path = LEDGER_PATH.parent / f"handoffs/{goal}.json"
        require_equal(f"{goal} direct handoff", sha256_path(path), expected)
        direct[goal] = {"path": str(path), "sha256": expected}
    predecessor = _read_json(PREDECESSOR_VALIDATION_PATH)
    resolved = _read_json(RESOLVED_CONTRACT_PATH)
    retry = _read_json(retry_path)
    require_equal("predecessor admission", predecessor["status"], "complete")
    require_equal("resolved contract", resolved["status"], "complete")
    require_equal("admitted control binding", predecessor["r07_control_plane_binding_sha256"], EXPECTED["control_plane_binding_sha256"])
    require_equal("resolved attestation", resolved["scheduler_profile_attestation"], TRACE_PROFILE_ATTESTATION)
    recovery_fields = (
        "marker_denominator_recovery",
        "postdevice_preworkload_recovery",
        "service_gate_recovery",
        "admission_schema_recovery",
        "bulk_preparation_recovery",
        "bulk_identity_schema_recovery",
        "socket_fixture_recovery",
        "service_validation_path_recovery",
        "request_manifest_hash_recovery",
        "postmeasurement_storage_recovery",
        "predecessor_storage_relocation",
        "worker_rebuild_recovery",
        "runtime_patch_path_recovery",
        "bulk_input_binding_recovery",
        "runtime_patch_fixture_recovery",
        "attempt024_schema_nfs_recovery",
        "attempt025_dynamic_capacity_recovery",
        "attempt026_abi_runtime_recovery",
        "attempt027_historical_identity_recovery",
        "attempt028_bytecode_surface_recovery",
        "attempt029_bytecode_empty_set_recovery",
        "attempt030_sidecar_fixture_recovery",
        "attempt031_prior_attempt_count_recovery",
        "attempt036_preformal_ordinal_binding_recovery",
        "attempt037_preformal_historical_validator_ordinal_recovery",
        "attempt038_preformal_field_value_identity_recovery",
        "attempt039_predevice_bulk_helper_identity_recovery",
        "attempt040_predevice_historical_successor_role_recovery",
        "attempt041_predevice_tool_freeze_dependency_recovery",
        "attempt042_predevice_admission_reference_key_recovery",
    )
    for field in recovery_fields:
        require_equal(f"predecessor {field}", predecessor[field], retry[field])
        require_equal(f"resolved {field}", resolved[field], retry[field])
    for field, expected_key in (
        ("request_manifest_hash_recovery", "request_manifest_hash_recovery_sha256"),
        ("postmeasurement_storage_recovery", "postmeasurement_storage_recovery_sha256"),
        ("predecessor_storage_relocation", "predecessor_storage_relocation_sha256"),
        ("worker_rebuild_recovery", "worker_rebuild_recovery_sha256"),
        ("runtime_patch_path_recovery", "runtime_patch_path_recovery_sha256"),
        ("bulk_input_binding_recovery", "bulk_input_binding_recovery_sha256"),
        ("runtime_patch_fixture_recovery", "runtime_patch_fixture_recovery_sha256"),
        ("attempt024_schema_nfs_recovery", "attempt024_schema_nfs_recovery_sha256"),
        ("attempt025_dynamic_capacity_recovery", "attempt025_dynamic_capacity_recovery_sha256"),
        ("attempt026_abi_runtime_recovery", "attempt026_abi_runtime_recovery_sha256"),
        ("attempt027_historical_identity_recovery", "attempt027_historical_identity_recovery_sha256"),
        ("attempt028_bytecode_surface_recovery", "attempt028_bytecode_surface_recovery_sha256"),
        ("attempt029_bytecode_empty_set_recovery", "attempt029_bytecode_empty_set_recovery_sha256"),
        ("attempt030_sidecar_fixture_recovery", "attempt030_sidecar_fixture_recovery_sha256"),
        ("attempt031_prior_attempt_count_recovery", "attempt031_prior_attempt_count_recovery_sha256"),
        ("attempt036_preformal_ordinal_binding_recovery", "attempt036_preformal_ordinal_binding_recovery_sha256"),
        ("attempt037_preformal_historical_validator_ordinal_recovery", "attempt037_preformal_historical_validator_ordinal_recovery_sha256"),
        ("attempt038_preformal_field_value_identity_recovery", "attempt038_preformal_field_value_identity_recovery_sha256"),
        ("attempt039_predevice_bulk_helper_identity_recovery", "attempt039_predevice_bulk_helper_identity_recovery_sha256"),
        ("attempt040_predevice_historical_successor_role_recovery", "attempt040_predevice_historical_successor_role_recovery_sha256"),
        ("attempt041_predevice_tool_freeze_dependency_recovery", "attempt041_predevice_tool_freeze_dependency_recovery_sha256"),
        ("attempt042_predevice_admission_reference_key_recovery", "attempt042_predevice_admission_reference_key_recovery_sha256"),
    ):
        require_equal(
            f"signed canonical recovery identity {field}",
            canonical_sha256(retry[field]),
            EXPECTED[expected_key],
        )
    request_manifest, selected_requests, request_manifest_identity = load_request_manifest(
        request_manifest_hash_recovery=retry["request_manifest_hash_recovery"]
    )
    require_equal("completion production request-manifest count", len(selected_requests), 8)
    require_equal(
        "completion production request sequence identity",
        request_manifest["ordered_sequence_canonical_sha256"],
        EXPECTED["request_sequence_sha256"],
    )
    for audit_name in (
        "request_manifest_hash_recovery_audit",
        "postmeasurement_storage_recovery_audit",
        "predecessor_storage_relocation_audit",
        "worker_rebuild_recovery_audit",
        "runtime_patch_path_recovery_audit",
        "bulk_input_binding_recovery_audit",
        "runtime_patch_fixture_recovery_audit",
        "attempt026_abi_runtime_recovery_audit",
        "attempt027_historical_identity_recovery_audit",
        "attempt028_bytecode_surface_recovery_audit",
        "attempt029_bytecode_empty_set_recovery_audit",
        "attempt030_sidecar_fixture_recovery_audit",
        "attempt031_prior_attempt_count_recovery_audit",
        "attempt038_preformal_field_value_identity_recovery_audit",
        "attempt039_predevice_bulk_helper_identity_recovery_audit",
        "attempt040_predevice_historical_successor_role_recovery_audit",
        "attempt041_predevice_tool_freeze_dependency_recovery_audit",
        "attempt042_predevice_admission_reference_key_recovery_audit",
        "preproduction_cross_helper_recovery_identity_audit",
        "post_attempt031_worker_recovery_audit",
        "capture_db_checkpoint_audit",
    ):
        require(isinstance(predecessor[audit_name], dict), f"predecessor {audit_name} missing")
        require_equal(f"resolved {audit_name}", resolved[audit_name], predecessor[audit_name])
    relocation_audit = predecessor["predecessor_storage_relocation_audit"]
    require_equal("relocated surface entry count rehashed", relocation_audit["surface_entry_count_rehashed"], 155319)
    require_equal("relocated surface logical bytes rehashed", relocation_audit["surface_logical_bytes_rehashed"], 43362488683)
    require(relocation_audit["all_materialized_regular_files_rehashed"] is True, "relocated regular-file rehash audit missing")
    require(relocation_audit["only_exact_parent_symlinks_allowed"] is True, "relocation parent-symlink gate missing")
    require(relocation_audit["r03_retained_as_real_directory"] is True, "R03 real-directory retention gate missing")
    worker_rebuild_audit = predecessor["worker_rebuild_recovery_audit"]
    require(worker_rebuild_audit["all_fields_consumed"] is True, "worker rebuild all-field audit missing")
    require(worker_rebuild_audit["nonpromotable_deleted_paths_remain_absent"] is True, "nonpromotable deleted paths were recreated")
    require(worker_rebuild_audit["prior_attempt_runtime_bytes_consumed"] is False, "prior failed-attempt runtime bytes were consumed")
    bulk_input_audit = predecessor["bulk_input_binding_recovery_audit"]
    require(bulk_input_audit["all_fields_consumed"] is True, "bulk-input all-field audit missing")
    require(bulk_input_audit["cold_and_admission_digest_roles_distinct"] is True, "bulk-input digest roles were collapsed")
    require(bulk_input_audit["deleted_attempt_018_bulk_root_remains_absent"] is True, "attempt-018 bulk root was recreated")
    require(bulk_input_audit["prior_attempt_runtime_or_bulk_bytes_consumed"] is False, "attempt-018 runtime or bulk bytes were consumed")
    runtime_fixture_audit = predecessor["runtime_patch_fixture_recovery_audit"]
    require(runtime_fixture_audit["all_fields_consumed"] is True, "runtime-patch fixture all-field audit missing")
    require(runtime_fixture_audit["deleted_attempt_019_bulk_root_remains_absent"] is True, "attempt-019 bulk root was recreated")
    require(
        runtime_fixture_audit[
            "prior_attempt_runtime_bulk_control_diagnostic_or_partial_freeze_bytes_consumed"
        ]
        is False,
        "attempt-019 forbidden bytes were consumed",
    )
    abi_recovery_audit = predecessor["attempt026_abi_runtime_recovery_audit"]
    require(
        abi_recovery_audit.get("status") == "complete"
        and abi_recovery_audit.get("scheduler_projection_exact") is True
        and abi_recovery_audit.get("signed_controls_exact") is True
        and abi_recovery_audit.get("vllm_import_count") == 0
        and abi_recovery_audit.get("all_regressions_before_bulk_or_device") is True,
        "attempt-026 ABI admission audit incomplete",
    )
    require_equal(
        "attempt-026 ABI negative case set",
        set(abi_recovery_audit.get("negative_cases", {})),
        {"filesystem_missing_rocm_C", "RECORD_missing_rocm_C", "frozen_member_drift"},
    )
    historical_identity_audit = predecessor[
        "attempt027_historical_identity_recovery_audit"
    ]
    require(
        historical_identity_audit.get("status") == "complete"
        and historical_identity_audit.get("scheduler_projection_exact") is True
        and historical_identity_audit.get("signed_controls_exact") is True
        and historical_identity_audit.get("device_query_count") == 0
        and historical_identity_audit.get("bulk_side_effect_count") == 0
        and historical_identity_audit.get("all_regressions_before_bulk_or_device")
        is True,
        "attempt-027 historical-identity admission audit incomplete",
    )
    require_equal(
        "attempt-027 historical-identity positives",
        historical_identity_audit.get("positive_cases"),
        {
            "attempt025_historical_identity_exact": True,
            "attempt026_historical_identity_exact": True,
            "historical_attempt028_identity_exact": True,
        },
    )
    require_equal(
        "attempt-027 historical-identity negative case set",
        set(historical_identity_audit.get("negative_cases", {})),
        {
            "attempt025_historical_identity_substituted_with_current",
            "attempt025_attempt026_roles_swapped",
            "attempt027_recovery_field_drift",
        },
    )
    require(
        all(
            row.get("status") == "rejected_as_required"
            for row in historical_identity_audit["negative_cases"].values()
        ),
        "attempt-027 historical-identity negative not rejected",
    )
    bytecode_surface_audit = predecessor[
        "attempt028_bytecode_surface_recovery_audit"
    ]
    require(
        bytecode_surface_audit.get("status") == "complete"
        and bytecode_surface_audit.get("scheduler_projection_exact") is True
        and bytecode_surface_audit.get("signed_controls_exact") is True
        and bytecode_surface_audit.get("historical_attempt027_identity_exact")
        is True
        and bytecode_surface_audit.get("historical_attempt029_identity_exact")
        is True
        and len(bytecode_surface_audit.get("generated_bytecode_evidence", [])) == 2
        and bytecode_surface_audit.get(
            "sealed_attempt028_bytecode_surface_negative"
        )
        and bytecode_surface_audit.get("device_query_count") == 0
        and bytecode_surface_audit.get("bulk_side_effect_count") == 0
        and bytecode_surface_audit.get(
            "all_regressions_before_bulk_or_device"
        )
        is True,
        "attempt-028 bytecode-surface admission audit incomplete",
    )
    bytecode_empty_set_audit = predecessor[
        "attempt029_bytecode_empty_set_recovery_audit"
    ]
    require(
        bytecode_empty_set_audit.get("status") == "complete"
        and bytecode_empty_set_audit.get("scheduler_projection_exact") is True
        and bytecode_empty_set_audit.get("signed_controls_exact") is True
        and bytecode_empty_set_audit.get("historical_attempt028_identity_exact")
        is True
        and bytecode_empty_set_audit.get("historical_attempt030_identity_exact")
        is True
        and bytecode_empty_set_audit.get(
            "sealed_attempt029_bytecode_member_count"
        )
        == 0
        and bytecode_empty_set_audit.get(
            "empty_positive_completed_without_first_member_access"
        )
        is True
        and bytecode_empty_set_audit.get("device_query_count") == 0
        and bytecode_empty_set_audit.get("bulk_side_effect_count") == 0
        and bytecode_empty_set_audit.get(
            "all_regressions_before_bulk_or_device"
        )
        is True,
        "attempt-029 bytecode-empty-set admission audit incomplete",
    )
    sidecar_fixture_audit = predecessor[
        "attempt030_sidecar_fixture_recovery_audit"
    ]
    require(
        sidecar_fixture_audit.get("status") == "complete"
        and sidecar_fixture_audit.get("scheduler_projection_exact") is True
        and sidecar_fixture_audit.get("signed_controls_exact") is True
        and sidecar_fixture_audit.get("historical_attempt030_identity_exact")
        is True
        and sidecar_fixture_audit.get("historical_attempt031_identity_exact")
        is True
        and sidecar_fixture_audit.get("all_fields_consumed") is True
        and sidecar_fixture_audit.get("required_complete_event_fields")
        == [
            "canonical_bound_selection_id",
            "canonical_bound_selection_sha256",
            "canonical_logical_selection_id",
            "canonical_logical_selection_sha256",
            "phase_occurrence",
            "runtime_execution_id",
        ]
        and sidecar_fixture_audit.get("device_query_count") == 0
        and sidecar_fixture_audit.get("bulk_side_effect_count") == 0
        and sidecar_fixture_audit.get("all_regressions_before_bulk_or_device")
        is True,
        "attempt-030 sidecar-fixture admission audit incomplete",
    )
    prior_attempt_count_audit = predecessor[
        "attempt031_prior_attempt_count_recovery_audit"
    ]
    require(
        prior_attempt_count_audit.get("status") == "complete"
        and prior_attempt_count_audit.get("scheduler_projection_exact") is True
        and prior_attempt_count_audit.get("signed_controls_exact") is True
        and prior_attempt_count_audit.get("historical_attempt031_identity_exact")
        is True
        and prior_attempt_count_audit.get("historical_attempt032_identity_exact")
        is True
        and len(prior_attempt_count_audit.get("method_template_files_verified", []))
        == 17
        and prior_attempt_count_audit.get("all_fields_consumed") is True
        and prior_attempt_count_audit.get("device_query_count") == 0
        and prior_attempt_count_audit.get("bulk_side_effect_count") == 0
        and prior_attempt_count_audit.get(
            "all_regressions_before_bulk_or_device"
        )
        is True,
        "attempt-031 prior-attempt-count admission audit incomplete",
    )
    post_attempt031_audit = predecessor[
        "post_attempt031_worker_recovery_audit"
    ]
    require(
        post_attempt031_audit.get("status") == "complete"
        and post_attempt031_audit.get("runtime_attempt_id") == ATTEMPT_ID
        and post_attempt031_audit.get("current_attempt_ordinal") == 43
        and post_attempt031_audit.get("prior_formal_goal_attempt_count") == 42
        and post_attempt031_audit.get("attempt031_historical_identity_preserved")
        is True
        and post_attempt031_audit.get("attempt032_runtime_payload_promoted")
        is False
        and post_attempt031_audit.get("attempt032_user_reported_capture_db_role")
        == "diagnostic_only"
        and post_attempt031_audit.get("segment017_pair_jointly_absent") is True
        and post_attempt031_audit.get(
            "segment028_and_segment029_are_provenance_only"
        )
        is True
        and post_attempt031_audit.get("segment018_pair_jointly_absent") is True
        and post_attempt031_audit.get("segment030_is_failure_provenance_only")
        is True
        and post_attempt031_audit.get(
            "resume032_resume033_resume034_slots_reusable"
        )
        is False
        and post_attempt031_audit.get(
            "current_worker_reconstruction_004_verified"
        )
        is True
        and post_attempt031_audit.get(
            "current_controls_authorize_only_resume042_attempt043"
        )
        is True
        and post_attempt031_audit.get(
            "attempt036_ordinal_binding_recovery_consumed"
        )
        is True
        and post_attempt031_audit.get("attempt036_failed_bytes_promoted")
        is False
        and post_attempt031_audit.get(
            "attempt037_historical_validator_ordinal_recovery_consumed"
        )
        is True
        and post_attempt031_audit.get("attempt037_failed_bytes_promoted")
        is False
        and post_attempt031_audit.get("attempt037_exact_evidence_count") == 12
        and set(post_attempt031_audit.get("attempt037_exact_evidence", {}))
        == {
            "recovery",
            "dataflow_diagnostic",
            "lifecycle_failure",
            "empty_bulk_seal",
            "artifact_seal",
            "terminal_seal",
            "blocked_audit",
            "admission_invocation",
            "admission_failure_output",
            "failure_sealer",
            "tool_template_lineage",
            "postfailure_diagnostic_bytecode",
        }
        and post_attempt031_audit.get(
            "attempt038_field_value_identity_recovery_consumed"
        )
        is True
        and post_attempt031_audit.get("attempt038_failed_bytes_promoted")
        is False
        and post_attempt031_audit.get("attempt038_exact_evidence_count") == 11
        and set(post_attempt031_audit.get("attempt038_exact_evidence", {}))
        == {
            "recovery",
            "diagnostic",
            "lifecycle_failure",
            "empty_bulk_seal",
            "artifact_seal",
            "terminal_seal",
            "blocked_audit",
            "admission_invocation",
            "admission_failure_output",
            "failure_sealer",
            "tool_template_lineage",
        }
        and post_attempt031_audit.get(
            "attempt039_bulk_helper_identity_recovery_consumed"
        )
        is True
        and post_attempt031_audit.get("attempt039_failed_bytes_promoted")
        is False
        and post_attempt031_audit.get("attempt039_exact_evidence_count") == 21
        and post_attempt031_audit.get(
            "attempt040_historical_successor_role_recovery_consumed"
        )
        is True
        and post_attempt031_audit.get("attempt040_failed_bytes_promoted")
        is False
        and post_attempt031_audit.get("attempt040_exact_evidence_count") == 22
        and post_attempt031_audit.get(
            "attempt041_freezer_dependency_recovery_consumed"
        )
        is True
        and post_attempt031_audit.get("attempt041_failed_bytes_promoted")
        is False
        and post_attempt031_audit.get("attempt041_exact_evidence_count") == 39
        and post_attempt031_audit.get(
            "attempt042_reference_key_recovery_consumed"
        )
        is True
        and post_attempt031_audit.get("attempt042_failed_bytes_promoted")
        is False
        and post_attempt031_audit.get("attempt042_exact_evidence_count") == 34
        and post_attempt031_audit.get(
            "attempt038_historical_successor_identity_preserved"
        )
        is True
        and post_attempt031_audit.get(
            "attempt039_historical_successor_identity_preserved"
        )
        is True
        and post_attempt031_audit.get(
            "current_attempt_identity_derived_only_from_attempt042_recovery"
        )
        is True
        and post_attempt031_audit.get(
            "attempt029_attempt030_positive_projections_use_signed_current_ordinal"
        )
        is True
        and post_attempt031_audit.get(
            "signed_current_ordinal_maintenance_projections_passed"
        )
        is True
        and post_attempt031_audit.get(
            "stale_ordinal_29_maintenance_projections_rejected"
        )
        is True
        and post_attempt031_audit.get("bulk_side_effect_count") == 0
        and post_attempt031_audit.get("device_query_count") == 0
        and post_attempt031_audit.get(
            "prior_runtime_or_payload_bytes_consumed"
        )
        is False
        and post_attempt031_audit.get("all_fields_consumed") is True,
        "post-attempt031 worker recovery-chain audit incomplete",
    )
    require_equal(
        "post-attempt031 recovery reference set",
        set(post_attempt031_audit.get("recovery_references", {})),
        {
            "attempt032_export_disconnect",
            "attempt033_segment017_loss",
            "attempt034_segment018_loss",
            "attempt035_predecessor_loss",
            "attempt036_ordinal_binding",
            "attempt037_historical_validator_ordinal",
            "attempt038_field_value_identity",
            "attempt039_bulk_helper_identity",
            "attempt040_historical_successor_role",
            "attempt041_tool_freeze_dependency",
        },
    )
    preproduction_recovery_identity_audit = predecessor[
        "preproduction_recovery_identity_audit"
    ]
    require(
        preproduction_recovery_identity_audit.get("status") == "complete"
        and preproduction_recovery_identity_audit.get(
            "signed_recovery_object_count"
        )
        == 29
        and preproduction_recovery_identity_audit.get(
            "retry_authorization_recovery_object_count"
        )
        == 29
        and preproduction_recovery_identity_audit.get(
            "bulk_authorization_recovery_object_count"
        )
        == 15
        and preproduction_recovery_identity_audit.get(
            "static_recovery_file_count"
        )
        == 4
        and preproduction_recovery_identity_audit.get(
            "canonical_identity_mismatch_constants"
        )
        == []
        and preproduction_recovery_identity_audit.get(
            "field_path_identity_mismatch_constants"
        )
        == []
        and preproduction_recovery_identity_audit.get(
            "field_value_identity_mismatch_constants"
        )
        == []
        and preproduction_recovery_identity_audit.get("attempt038_recovery_bound")
        is True
        and preproduction_recovery_identity_audit.get("attempt039_recovery_bound")
        is True
        and preproduction_recovery_identity_audit.get("attempt040_recovery_bound")
        is True
        and preproduction_recovery_identity_audit.get("attempt041_recovery_bound")
        is True
        and preproduction_recovery_identity_audit.get("attempt042_recovery_bound")
        is True
        and preproduction_recovery_identity_audit.get(
            "all_current_control_recoveries_audited"
        )
        is True
        and preproduction_recovery_identity_audit.get("bulk_side_effect_count")
        == 0
        and preproduction_recovery_identity_audit.get("device_query_count") == 0,
        "preproduction recovery-identity audit incomplete",
    )
    attempt039_recovery_audit = predecessor[
        "attempt039_predevice_bulk_helper_identity_recovery_audit"
    ]
    require(
        attempt039_recovery_audit.get("status") == "complete"
        and attempt039_recovery_audit.get("runtime_attempt_id") == ATTEMPT_ID
        and attempt039_recovery_audit.get("canonical_sha256")
        == EXPECTED["attempt039_predevice_bulk_helper_identity_recovery_sha256"]
        and attempt039_recovery_audit.get("leaf_count") == 60
        and attempt039_recovery_audit.get("exact_evidence_count") == 21
        and attempt039_recovery_audit.get("failed_attempt_bytes_promoted")
        is False
        and attempt039_recovery_audit.get("all_fields_consumed") is True
        and attempt039_recovery_audit.get("bulk_side_effect_count") == 0
        and attempt039_recovery_audit.get("device_query_count") == 0,
        "attempt-039 bulk-helper recovery audit incomplete",
    )
    attempt040_recovery_audit = predecessor[
        "attempt040_predevice_historical_successor_role_recovery_audit"
    ]
    require(
        attempt040_recovery_audit.get("status") == "complete"
        and attempt040_recovery_audit.get("runtime_attempt_id") == ATTEMPT_ID
        and attempt040_recovery_audit.get("canonical_sha256")
        == EXPECTED[
            "attempt040_predevice_historical_successor_role_recovery_sha256"
        ]
        and attempt040_recovery_audit.get("leaf_count") == 80
        and attempt040_recovery_audit.get("exact_evidence_count") == 22
        and attempt040_recovery_audit.get("failed_attempt_bytes_promoted")
        is False
        and attempt040_recovery_audit.get("historical_successor_roles_preserved")
        is True
        and attempt040_recovery_audit.get(
            "current_attempt_identity_derived_only_from_attempt040_recovery"
        )
        is True
        and attempt040_recovery_audit.get("all_fields_consumed") is True
        and attempt040_recovery_audit.get("bulk_side_effect_count") == 0
        and attempt040_recovery_audit.get("device_query_count") == 0,
        "attempt-040 historical-successor-role recovery audit incomplete",
    )
    attempt041_recovery_audit = predecessor[
        "attempt041_predevice_tool_freeze_dependency_recovery_audit"
    ]
    require(
        attempt041_recovery_audit.get("status") == "complete"
        and attempt041_recovery_audit.get("runtime_attempt_id") == ATTEMPT_ID
        and attempt041_recovery_audit.get("canonical_sha256")
        == EXPECTED[
            "attempt041_predevice_tool_freeze_dependency_recovery_sha256"
        ]
        and attempt041_recovery_audit.get("leaf_count") == 123
        and attempt041_recovery_audit.get("exact_evidence_count") == 39
        and attempt041_recovery_audit.get("failed_attempt_bytes_promoted")
        is False
        and attempt041_recovery_audit.get(
            "production_freezer_predecessor_validation_dependency_explicitly_bound"
        )
        is True
        and attempt041_recovery_audit.get(
            "missing_freezer_dependency_rejected_before_bulk_or_device"
        )
        is True
        and attempt041_recovery_audit.get(
            "current_attempt_identity_derived_only_from_attempt041_recovery"
        )
        is True
        and attempt041_recovery_audit.get("all_fields_consumed") is True
        and attempt041_recovery_audit.get("bulk_side_effect_count") == 0
        and attempt041_recovery_audit.get("device_query_count") == 0,
        "attempt-041 freezer-dependency recovery audit incomplete",
    )
    attempt042_recovery_audit = predecessor[
        "attempt042_predevice_admission_reference_key_recovery_audit"
    ]
    require(
        attempt042_recovery_audit.get("status") == "complete"
        and attempt042_recovery_audit.get("runtime_attempt_id") == ATTEMPT_ID
        and attempt042_recovery_audit.get("canonical_sha256")
        == EXPECTED[
            "attempt042_predevice_admission_reference_key_recovery_sha256"
        ]
        and attempt042_recovery_audit.get("leaf_count") == 140
        and attempt042_recovery_audit.get("exact_evidence_count") == 34
        and attempt042_recovery_audit.get("failed_attempt_bytes_promoted")
        is False
        and attempt042_recovery_audit.get(
            "reference_key_positive_exact_namespaced_path_passed"
        )
        is True
        and attempt042_recovery_audit.get(
            "reference_key_legacy_unqualified_negative_rejected"
        )
        is True
        and attempt042_recovery_audit.get(
            "reference_key_missing_exact_negative_rejected"
        )
        is True
        and attempt042_recovery_audit.get(
            "current_attempt_identity_derived_only_from_attempt042_recovery"
        )
        is True
        and attempt042_recovery_audit.get("all_fields_consumed") is True
        and attempt042_recovery_audit.get("bulk_side_effect_count") == 0
        and attempt042_recovery_audit.get("device_query_count") == 0,
        "attempt-042 reference-key recovery audit incomplete",
    )
    preproduction_cross_helper_recovery_identity_audit = predecessor[
        "preproduction_cross_helper_recovery_identity_audit"
    ]
    require(
        preproduction_cross_helper_recovery_identity_audit.get("status")
        == "complete"
        and preproduction_cross_helper_recovery_identity_audit.get(
            "runtime_attempt_id"
        )
        == ATTEMPT_ID
        and preproduction_cross_helper_recovery_identity_audit.get(
            "production_helper_count"
        )
        == 5
        and preproduction_cross_helper_recovery_identity_audit.get(
            "all_executable_recovery_identity_constants_recomputed"
        )
        is True
        and preproduction_cross_helper_recovery_identity_audit.get(
            "attempt041_recovery_canonical_sha256"
        )
        == EXPECTED[
            "attempt041_predevice_tool_freeze_dependency_recovery_sha256"
        ]
        and preproduction_cross_helper_recovery_identity_audit.get(
            "attempt042_recovery_canonical_sha256"
        )
        == EXPECTED[
            "attempt042_predevice_admission_reference_key_recovery_sha256"
        ]
        and preproduction_cross_helper_recovery_identity_audit.get(
            "historical_successor_roles_preserved"
        )
        is True
        and preproduction_cross_helper_recovery_identity_audit.get(
            "current_attempt_identity_derived_only_from_attempt042_recovery"
        )
        is True
        and preproduction_cross_helper_recovery_identity_audit.get(
            "production_freezer_predecessor_validation_dependency_explicitly_bound"
        )
        is True
        and preproduction_cross_helper_recovery_identity_audit.get(
            "freezer_dependency_positive_exact_production_path_passed"
        )
        is True
        and preproduction_cross_helper_recovery_identity_audit.get(
            "freezer_dependency_missing_negative_rejected"
        )
        is True
        and preproduction_cross_helper_recovery_identity_audit.get(
            "reference_key_positive_exact_namespaced_path_passed"
        )
        is True
        and preproduction_cross_helper_recovery_identity_audit.get(
            "reference_key_legacy_unqualified_negative_rejected"
        )
        is True
        and preproduction_cross_helper_recovery_identity_audit.get(
            "reference_key_missing_exact_negative_rejected"
        )
        is True
        and preproduction_cross_helper_recovery_identity_audit.get(
            "audit_completed_before_formal_production_admission"
        )
        is True
        and preproduction_cross_helper_recovery_identity_audit.get(
            "bulk_side_effect_count"
        )
        == 0
        and preproduction_cross_helper_recovery_identity_audit.get(
            "device_query_count"
        )
        == 0,
        "preproduction cross-helper recovery identity audit incomplete",
    )
    checkpoint_admission_audit = predecessor["capture_db_checkpoint_audit"]
    require(
        checkpoint_admission_audit.get("status") == "complete"
        and checkpoint_admission_audit.get("runtime_attempt_id") == ATTEMPT_ID
        and checkpoint_admission_audit.get("helper_path")
        == str(CAPTURE_DB_CHECKPOINT_HELPER)
        and checkpoint_admission_audit.get("helper_sha256")
        == EXPECTED["capture_db_checkpoint_helper_sha256"]
        and checkpoint_admission_audit.get("active_sqlite_on_durable_nfs")
        is False
        and checkpoint_admission_audit.get("checkpoint_precedes_offline_export")
        is True
        and checkpoint_admission_audit.get(
            "full_raw_copy_must_reverify_checkpointed_database"
        )
        is True
        and checkpoint_admission_audit.get("bulk_side_effect_count") == 0
        and checkpoint_admission_audit.get("device_query_count") == 0,
        "capture DB checkpoint admission audit incomplete",
    )
    bulk_authorization = _read_json(BULK_AUTH_PATH)
    durable_nfs_storage = bulk_authorization.get("durable_nfs_storage")
    require(isinstance(durable_nfs_storage, dict), "signed durable NFS storage missing")
    require_equal(
        "durable NFS storage canonical identity",
        canonical_sha256(durable_nfs_storage),
        EXPECTED["durable_nfs_storage_sha256"],
    )
    require_equal("predecessor durable NFS storage", predecessor["durable_nfs_storage"], durable_nfs_storage)
    require_equal("resolved durable NFS storage", resolved["durable_nfs_storage"], durable_nfs_storage)
    attempt024_025_026_maintenance = predecessor.get(
        "attempt_024_025_026_027_028_029_030_031_maintenance_inputs"
    )
    require(
        isinstance(attempt024_025_026_maintenance, dict),
        "attempt-024/025/026 maintenance admission audit missing",
    )
    require_equal(
        "resolved attempt-024/025/026 maintenance audit",
        resolved["attempt_024_025_026_027_028_029_030_031_maintenance_inputs"],
        attempt024_025_026_maintenance,
    )
    require_equal(
        "attempt-024/025/026 maintenance status",
        attempt024_025_026_maintenance.get("status"),
        "complete",
    )
    require(
        attempt024_025_026_maintenance.get("five_maintenance_inputs_verified")
        is True,
        "five attempt-024/025/026 maintenance inputs not verified",
    )
    require_equal(
        "attempt-024 maintenance recovery",
        attempt024_025_026_maintenance.get("attempt024_schema_nfs_recovery"),
        retry["attempt024_schema_nfs_recovery"],
    )
    require_equal(
        "attempt-025 dynamic-capacity recovery",
        attempt024_025_026_maintenance.get("attempt025_dynamic_capacity_recovery"),
        retry["attempt025_dynamic_capacity_recovery"],
    )
    require_equal(
        "attempt-026 ABI-runtime recovery",
        attempt024_025_026_maintenance.get("attempt026_abi_runtime_recovery"),
        retry["attempt026_abi_runtime_recovery"],
    )
    require_equal(
        "attempt-027 historical-identity recovery",
        attempt024_025_026_maintenance.get(
            "attempt027_historical_identity_recovery"
        ),
        retry["attempt027_historical_identity_recovery"],
    )
    require_equal(
        "attempt-027 historical-identity maintenance audit",
        attempt024_025_026_maintenance.get(
            "attempt027_historical_identity_recovery_audit"
        ),
        historical_identity_audit,
    )
    require_equal(
        "attempt-028 bytecode-surface recovery",
        attempt024_025_026_maintenance.get(
            "attempt028_bytecode_surface_recovery"
        ),
        retry["attempt028_bytecode_surface_recovery"],
    )
    require_equal(
        "attempt-028 bytecode-surface maintenance audit",
        attempt024_025_026_maintenance.get(
            "attempt028_bytecode_surface_recovery_audit"
        ),
        bytecode_surface_audit,
    )
    require_equal(
        "attempt-029 bytecode-empty-set recovery",
        attempt024_025_026_maintenance.get(
            "attempt029_bytecode_empty_set_recovery"
        ),
        retry["attempt029_bytecode_empty_set_recovery"],
    )
    require_equal(
        "attempt-029 bytecode-empty-set maintenance audit",
        attempt024_025_026_maintenance.get(
            "attempt029_bytecode_empty_set_recovery_audit"
        ),
        bytecode_empty_set_audit,
    )
    require_equal(
        "attempt-030 sidecar-fixture recovery",
        attempt024_025_026_maintenance.get(
            "attempt030_sidecar_fixture_recovery"
        ),
        retry["attempt030_sidecar_fixture_recovery"],
    )
    require_equal(
        "attempt-030 sidecar-fixture maintenance audit",
        attempt024_025_026_maintenance.get(
            "attempt030_sidecar_fixture_recovery_audit"
        ),
        sidecar_fixture_audit,
    )
    require_equal(
        "attempt-031 prior-attempt-count recovery",
        attempt024_025_026_maintenance.get(
            "attempt031_prior_attempt_count_recovery"
        ),
        retry["attempt031_prior_attempt_count_recovery"],
    )
    require_equal(
        "attempt-031 prior-attempt-count maintenance audit",
        attempt024_025_026_maintenance.get(
            "attempt031_prior_attempt_count_recovery_audit"
        ),
        prior_attempt_count_audit,
    )
    require_equal(
        "attempt-024/025/026 maintenance durable contract",
        attempt024_025_026_maintenance.get("durable_nfs_storage"),
        durable_nfs_storage,
    )
    dynamic_capacity_regressions = attempt024_025_026_maintenance.get(
        "dynamic_capacity_regressions"
    )
    require(
        isinstance(dynamic_capacity_regressions, dict)
        and dynamic_capacity_regressions.get(
            "signed_issue_time_control_bytes_exact_positive"
        )
        is True
        and dynamic_capacity_regressions.get(
            "stable_recovery_projection_exact_positive"
        )
        is True
        and dynamic_capacity_regressions.get(
            "changed_above_floor_capacity_positive"
        )
        is True
        and isinstance(
            dynamic_capacity_regressions.get("below_floor_capacity_negative"),
            str,
        )
        and isinstance(
            dynamic_capacity_regressions.get(
                "stable_projection_field_drift_negative"
            ),
            str,
        )
        and dynamic_capacity_regressions.get(
            "mutable_capacity_byte_equality_forbidden"
        )
        is True
        and dynamic_capacity_regressions.get("all_run_before_bulk_or_device")
        is True,
        "attempt-025 dynamic-capacity regression set incomplete",
    )
    schema_regressions = attempt024_025_026_maintenance.get(
        "raw_maintenance_schema_and_projection_regressions"
    )
    require(isinstance(schema_regressions, dict) and len(schema_regressions) == 2, "raw/projection maintenance schema regressions incomplete")
    for label, regression in schema_regressions.items():
        require(regression.get("raw_without_projection_status_positive") is True, f"raw native-schema positive missing: {label}")
        require(regression.get("scheduler_projection_complete_positive") is True, f"projection-complete positive missing: {label}")
        require_equal(
            f"maintenance negative case set {label}",
            set(regression.get("negative_cases", {})),
            {"raw_hash_drift", "raw_schema_drift", "projection_status_missing", "projection_status_noncomplete"},
        )
        require(
            all(case.get("status") == "rejected_as_required" for case in regression["negative_cases"].values()),
            f"maintenance schema negative not rejected: {label}",
        )
    required_audits = bulk_authorization["required_audits"]
    require_equal(
        "bulk required audits canonical hash",
        canonical_sha256(required_audits),
        EXPECTED["bulk_storage_required_audits_sha256"],
    )
    require_equal("predecessor bulk required audits", predecessor["bulk_storage_required_audits"], required_audits)
    require_equal("resolved bulk required audits", resolved["bulk_storage_required_audits"], required_audits)
    recovery = retry["marker_denominator_recovery"]
    expected_denominators = {
        "full_r06_target_universe": {
            "count": EXPECTED["target_count"],
            "ordered_length_prefixed_sha256": EXPECTED["full_target_ordered_marker_bytes_sha256"],
            "validation_role": "full_R06_target_universe_only",
        },
        "r06_layer_parent_subset": {
            "count": EXPECTED["layer_target_count"],
            "ordered_length_prefixed_sha256": EXPECTED["layer_parent_ordered_marker_bytes_sha256"],
            "validation_role": "parent_layer_subset_only",
        },
        "r07_process_fragment_subset": {
            "count": EXPECTED["process_target_count"],
            "ordered_length_prefixed_sha256": EXPECTED["process_fragment_ordered_marker_bytes_sha256"],
            "validation_role": "ordered_process_transport_gate",
        },
    }
    require_equal("named marker denominators", recovery["denominators"], expected_denominators)
    require_equal(
        "ordered process transport gate",
        recovery["ordered_process_transport_gate"],
        {
            "denominator_field": "denominators.r07_process_fragment_subset",
            "count_field": "denominators.r07_process_fragment_subset.count",
            "sha256_field": "denominators.r07_process_fragment_subset.ordered_length_prefixed_sha256",
            "expected_count": EXPECTED["process_target_count"],
            "expected_sha256": EXPECTED["process_fragment_ordered_marker_bytes_sha256"],
            "full_universe_field_forbidden": "denominators.full_r06_target_universe.ordered_length_prefixed_sha256",
        },
    )
    prefreeze = _read_json(PREFREEZE_MARKER_REGRESSION_PATH)
    _validate_identity(prefreeze, "pre-freeze marker regression")
    require_equal("pre-freeze marker profile", prefreeze["trace_profile_sha256"], EXPECTED["profile_sha256"])
    require_equal("independently recomputed denominators", prefreeze["independently_recomputed_denominators"], {
        name: {"count": row["count"], "ordered_length_prefixed_sha256": row["ordered_length_prefixed_sha256"]}
        for name, row in expected_denominators.items()
    })
    require(prefreeze["process_gate_references_process_fragment_subset_fields"] is True, "process marker gate field regression failed")
    require(prefreeze["full_universe_hash_does_not_bind_process_gate"] is True, "full-universe hash bound process marker gate")
    postdevice_prefreeze = _read_json(PREFREEZE_POSTDEVICE_REGRESSION_PATH)
    _validate_identity(postdevice_prefreeze, "pre-freeze postdevice recovery regression")
    require_equal(
        "pre-freeze postdevice recovery binding",
        postdevice_prefreeze["postdevice_preworkload_recovery"],
        retry["postdevice_preworkload_recovery"],
    )
    require(postdevice_prefreeze["authorized_bulk_symlink_service_log"]["resolved_target_equals_authorized_raw_target"] is True, "authorized external raw target regression failed")
    require(postdevice_prefreeze["authorized_bulk_symlink_service_log"]["changed_target_negative_rejected"] is True, "changed bulk target regression failed")
    require(postdevice_prefreeze["process_tracker_proc_toctou"]["captured_identity_appended_without_pid_relookup"] is True, "process TOCTOU regression failed")
    require(postdevice_prefreeze["process_tracker_proc_toctou"]["pid_reuse_identity_mismatch_rejected"] is True, "PID reuse regression failed")
    require(postdevice_prefreeze["aot_seed_and_current_attempt_derivation"]["failed_attempt_provenance_rejected"] is True, "foreign AOT provenance regression failed")
    require(postdevice_prefreeze["aot_seed_and_current_attempt_derivation"]["seed_modification_rejected"] is True, "AOT seed modification regression failed")
    require(postdevice_prefreeze["service_gate_recovery_regression"]["cache_both_ranks_plus_log_single_save_message_plus_DP2_runtime_markers_passes"] is True, "service-gate positive regression failed")
    require(postdevice_prefreeze["service_gate_recovery_regression"]["cache_missing_either_rank_fails"] is True, "service-gate cache-rank negative failed")
    require(postdevice_prefreeze["service_gate_recovery_regression"]["runtime_readiness_missing_either_DP_rank_or_device_fails"] is True, "service-gate runtime-readiness negative failed")
    require(postdevice_prefreeze["nonregular_bulk_object_regression"]["unix_domain_socket_lstat_inventory_passes_without_content_hash_or_deletion"] is True, "nonregular bulk-object regression failed")
    require_equal(
        "pre-freeze service-validation-path recovery binding",
        postdevice_prefreeze["service_validation_path_recovery"],
        retry["service_validation_path_recovery"],
    )
    for field in (
        "request_manifest_hash_recovery",
        "postmeasurement_storage_recovery",
        "predecessor_storage_relocation",
        "worker_rebuild_recovery",
        "runtime_patch_path_recovery",
        "bulk_input_binding_recovery",
        "runtime_patch_fixture_recovery",
        "attempt024_schema_nfs_recovery",
        "attempt025_dynamic_capacity_recovery",
        "attempt026_abi_runtime_recovery",
        "attempt027_historical_identity_recovery",
        "attempt028_bytecode_surface_recovery",
        "attempt029_bytecode_empty_set_recovery",
        "attempt030_sidecar_fixture_recovery",
        "attempt031_prior_attempt_count_recovery",
        "attempt036_preformal_ordinal_binding_recovery",
        "attempt037_preformal_historical_validator_ordinal_recovery",
        "attempt038_preformal_field_value_identity_recovery",
        "attempt039_predevice_bulk_helper_identity_recovery",
        "attempt040_predevice_historical_successor_role_recovery",
        "attempt041_predevice_tool_freeze_dependency_recovery",
        "attempt042_predevice_admission_reference_key_recovery",
    ):
        require_equal(f"pre-freeze postdevice {field}", postdevice_prefreeze[field], retry[field])
    require_equal("pre-freeze postdevice durable NFS storage", postdevice_prefreeze["durable_nfs_storage"], durable_nfs_storage)
    require(postdevice_prefreeze["production_request_manifest_loader_invoked_before_freeze"] is True, "freeze did not invoke production request loader")
    postdevice_service_path_regression = postdevice_prefreeze[
        "service_validation_path_recovery_regression"
    ]
    require_equal(
        "pre-freeze service-validation regression status",
        postdevice_service_path_regression["status"],
        "complete",
    )
    require(
        postdevice_service_path_regression[
            "production_check_service_callsite_uses_lexical_writer_argument"
        ]
        is True,
        "check-service lexical writer callsite regression failed",
    )
    require(
        postdevice_service_path_regression[
            "diagnostic_sealer_nested_storage_lstat_positive"
        ]
        is True,
        "diagnostic sealer nested storage_lstat.object_kind positive failed",
    )
    require(postdevice_prefreeze["all_started_processes_terminated"] is True, "pre-freeze regression process cleanup incomplete")
    bulk_prefreeze = _read_json(PREFREEZE_BULK_REGRESSION_PATH)
    _validate_identity(bulk_prefreeze, "pre-freeze bulk preparation regression")
    require_equal(
        "pre-freeze socket recovery binding",
        bulk_prefreeze["socket_fixture_recovery"],
        retry["socket_fixture_recovery"],
    )
    require_equal(
        "pre-freeze service-validation-path recovery binding from bulk helper",
        bulk_prefreeze["service_validation_path_recovery"],
        retry["service_validation_path_recovery"],
    )
    for field in (
        "request_manifest_hash_recovery",
        "postmeasurement_storage_recovery",
        "predecessor_storage_relocation",
        "worker_rebuild_recovery",
        "runtime_patch_path_recovery",
        "bulk_input_binding_recovery",
        "runtime_patch_fixture_recovery",
        "attempt024_schema_nfs_recovery",
        "attempt025_dynamic_capacity_recovery",
        "attempt026_abi_runtime_recovery",
        "attempt027_historical_identity_recovery",
        "attempt028_bytecode_surface_recovery",
        "attempt029_bytecode_empty_set_recovery",
        "attempt030_sidecar_fixture_recovery",
        "attempt031_prior_attempt_count_recovery",
        "attempt036_preformal_ordinal_binding_recovery",
        "attempt037_preformal_historical_validator_ordinal_recovery",
        "attempt038_preformal_field_value_identity_recovery",
        "attempt039_predevice_bulk_helper_identity_recovery",
        "attempt040_predevice_historical_successor_role_recovery",
        "attempt041_predevice_tool_freeze_dependency_recovery",
        "attempt042_predevice_admission_reference_key_recovery",
    ):
        require_equal(f"pre-freeze bulk-helper {field}", bulk_prefreeze[field], retry[field])
    require_equal("pre-freeze bulk-helper durable NFS storage", bulk_prefreeze["durable_nfs_storage"], durable_nfs_storage)
    runtime_patch_prefreeze = _read_json(PREFREEZE_RUNTIME_PATCH_REGRESSION_PATH)
    require_equal(
        "runtime-patch subprocess regression status",
        runtime_patch_prefreeze["status"],
        "complete",
    )
    require_equal(
        "runtime-patch subprocess fixture recovery",
        runtime_patch_prefreeze["runtime_patch_fixture_recovery"],
        retry["runtime_patch_fixture_recovery"],
    )
    require(
        runtime_patch_prefreeze[
            "every_child_argv_environment_delta_exit_stdout_stderr_and_hashes_persisted_before_assertion"
        ]
        is True,
        "runtime-patch subprocess diagnostics persistence gate failed",
    )
    require(
        runtime_patch_prefreeze[
            "every_case_started_from_complete_R01_baseline_before_single_mutation"
        ]
        is True,
        "runtime-patch subprocess baseline gate failed",
    )
    require_equal(
        "runtime-patch subprocess negative case set",
        set(runtime_patch_prefreeze["negative_cases"]),
        {
            "missing_R01_fixture_environment",
            "missing_R07_patch_environment",
            "lexical_target_drift",
            "resolved_target_drift",
            "unregistered_op",
        },
    )
    for case_name, case in {
        "positive": runtime_patch_prefreeze["positive"],
        **runtime_patch_prefreeze["negative_cases"],
    }.items():
        require(case["diagnostics_persisted_before_parent_assertion"] is True, f"runtime-patch case diagnostics ordering missing: {case_name}")
        for stream_name in ("stdout", "stderr"):
            stream = case[stream_name]
            stream_path = Path(stream["path"])
            require_equal(f"runtime-patch {case_name} {stream_name} size", stream_path.stat().st_size, stream["size"])
            require_equal(f"runtime-patch {case_name} {stream_name} hash", sha256_path(stream_path), stream["sha256"])
        invocation = case["invocation"]
        invocation_path = Path(invocation["path"])
        require_equal(f"runtime-patch {case_name} invocation size", invocation_path.stat().st_size, invocation["size"])
        require_equal(f"runtime-patch {case_name} invocation hash", sha256_path(invocation_path), invocation["sha256"])
    request_hash_regression = _read_json(PREFREEZE_REQUEST_HASH_REGRESSION_PATH)
    require_equal("request dual-hash regression status", request_hash_regression["status"], "complete")
    require(request_hash_regression["all_negative_cases_rejected"] is True, "request dual-hash negative coverage incomplete")
    require_equal("bulk embedded request dual-hash regression", bulk_prefreeze["request_manifest_hash_regression"], request_hash_regression)
    require(bulk_prefreeze["all_request_manifest_hash_regressions_complete_before_first_bulk_side_effect"] is True, "request dual-hash regressions were not pre-side-effect")
    collector_shutdown_regression = _read_json(PREFREEZE_COLLECTOR_SHUTDOWN_REGRESSION_PATH)
    require_equal("collector shutdown regression status", collector_shutdown_regression["status"], "complete")
    require(collector_shutdown_regression["negative_unreleased_exported_pointer_reproduced"] is True, "collector shutdown negative not reproduced")
    require(collector_shutdown_regression["positive_explicitly_released_every_exported_view"] is True, "collector shutdown view release positive missing")
    require(collector_shutdown_regression["samples_gaps_anchors_sealed_before_backing_close"] is True, "collector shutdown seal-before-close missing")
    require_equal("collector shutdown regression subprocess exit", bulk_prefreeze["collector_shutdown_subprocess_exit_status"], 0)
    require(bulk_prefreeze["collector_shutdown_regression_complete_before_first_bulk_side_effect"] is True, "collector shutdown regression was not pre-side-effect")
    durable_copy_regression = _read_json(
        PREFREEZE_DURABLE_COPY_REGRESSION_PATH
    )
    require_equal(
        "durable-copy regression status",
        durable_copy_regression["status"],
        "complete",
    )
    require_equal(
        "bulk embedded durable-copy regression",
        bulk_prefreeze["durable_copy_regression"],
        durable_copy_regression,
    )
    require(
        durable_copy_regression["completion_marker_absent_during_regression"]
        is True
        and durable_copy_regression["bulk_side_effects_started"] is False
        and durable_copy_regression["device_or_runtime_action_count"] == 0,
        "durable-copy regression crossed the pre-side-effect boundary",
    )
    require(
        bulk_prefreeze[
            "resumable_durable_copy_regression_complete_before_first_bulk_side_effect"
        ]
        is True
        and bulk_prefreeze[
            "resumable_durable_copy_regression_used_production_runner_helpers"
        ]
        is True,
        "durable-copy production regression ordering gate failed",
    )
    service_path_regression = bulk_prefreeze["service_validation_path_regression"]
    require_equal(
        "bulk-helper service-validation regression status",
        service_path_regression["status"],
        "complete",
    )
    require(
        service_path_regression[
            "all_service_validation_regressions_complete_before_first_bulk_side_effect"
        ]
        is True,
        "service-validation regressions did not precede bulk side effects",
    )
    socket_regression = bulk_prefreeze["socket_fixture_regression"]
    require(socket_regression["absolute_bind_negative"]["failed_as_required"] is True, "199-byte absolute socket bind negative failed")
    require(socket_regression["absolute_bind_negative"]["socket_side_effect_created"] is False, "absolute socket bind left a side effect")
    require(socket_regression["relative_bind_positive"]["cwd_restored_with_fchdir_in_finally"] is True, "socket success cwd restoration failed")
    require(socket_regression["relative_bind_injected_failure"]["cwd_restored_with_fchdir_in_finally"] is True, "socket failure cwd restoration failed")
    require(socket_regression["socket_content_hash_performed"] is False, "socket content hashing is forbidden")
    require(socket_regression["socket_preserved_without_deletion"] is True, "socket fixture was not preserved")
    require(bulk_prefreeze["all_socket_regressions_complete_before_first_bulk_side_effect"] is True, "socket regressions did not precede bulk side effects")
    left = PREFREEZE_FIXTURE_SOCKET.lstat()
    right = PREFREEZE_FIXTURE_SOCKET_ENTRYPOINT.lstat()
    require(stat.S_ISSOCK(left.st_mode) and stat.S_ISSOCK(right.st_mode), "preserved fixture is not a socket through both paths")
    for field in ("st_dev", "st_ino", "st_mode", "st_size"):
        require_equal(f"preserved socket dual-path {field}", getattr(left, field), getattr(right, field))
    frozen = validate_frozen_tools()
    require_equal("frozen run", frozen["runtime_run_id"], RUN_ID)
    require_equal("frozen attempt", frozen["runtime_attempt_id"], ATTEMPT_ID)
    for field in recovery_fields:
        require_equal(f"frozen {field}", frozen[field], retry[field])
    require_equal(
        "frozen attempt-040 historical-successor-role recovery audit",
        frozen["attempt040_predevice_historical_successor_role_recovery_audit"],
        attempt040_recovery_audit,
    )
    require_equal(
        "frozen attempt-041 freezer-dependency recovery audit",
        frozen["attempt041_predevice_tool_freeze_dependency_recovery_audit"],
        attempt041_recovery_audit,
    )
    require_equal(
        "frozen attempt-042 reference-key recovery audit",
        frozen["attempt042_predevice_admission_reference_key_recovery_audit"],
        attempt042_recovery_audit,
    )
    require_equal(
        "frozen preproduction cross-helper recovery audit",
        frozen["preproduction_cross_helper_recovery_identity_audit"],
        preproduction_cross_helper_recovery_identity_audit,
    )
    require_equal("frozen durable NFS storage", frozen["durable_nfs_storage"], durable_nfs_storage)
    require_equal("frozen bulk required audits", frozen["bulk_storage_required_audits"], required_audits)
    require_equal("frozen bulk required audits hash", frozen["bulk_storage_required_audits_sha256"], EXPECTED["bulk_storage_required_audits_sha256"])
    require_equal("source delta status", _read_json(SOURCE_DELTA_PATH)["status"], "complete")
    require_equal("attempt history status", _read_json(ATTEMPT_HISTORY_PATH)["status"], "complete")
    bytecode_prefreeze = _read_json(PREFREEZE_BYTECODE_SURFACE_REGRESSION_PATH)
    require_equal("bytecode-surface regression status", bytecode_prefreeze["status"], "complete")
    require(
        bytecode_prefreeze["current_surface_bytecode_free"] is True
        and bytecode_prefreeze["bulk_side_effect_count"] == 0
        and bytecode_prefreeze[
            "all_regressions_complete_before_bulk_or_device"
        ]
        is True,
        "bytecode-surface regression did not fail closed before bulk/device",
    )
    require_equal(
        "bytecode-surface positive case set",
        set(bytecode_prefreeze["positive_cases"]),
        {"explicit_environment", "missing_environment_internal_guard"},
    )
    require(bytecode_prefreeze["sealed_attempt028___pycache___and_pyc_negative"], "attempt-028 bytecode negative missing")
    quarantine = _read_json(QUARANTINE_RECORD_PATH)
    require_equal("bytecode quarantine status", quarantine["status"], "complete")
    require_equal("bytecode quarantine attempt", quarantine["runtime_attempt_id"], ATTEMPT_ID)
    require_equal("bytecode quarantine file count", quarantine["file_count"], 0)
    require_equal("bytecode quarantine rows", quarantine["files"], [])
    current_bytecode = sorted(
        path.relative_to(ARTIFACT_ROOT).as_posix()
        for path in ARTIFACT_ROOT.rglob("*")
        if path.suffix == ".pyc" or "__pycache__" in path.parts
    )
    require_equal("completion current bytecode surface", current_bytecode, [])
    selector_regression = _read_json(
        VALIDATION_ROOT / "pre_bulk_production_selector_regression.json"
    )
    _validate_identity(selector_regression, "pre-bulk production selector regression")
    require_equal(
        "selector revision SHA-256",
        selector_regression["selector_revision_sha256"],
        R06_REQUEST_PHASE_SELECTION_REVISION_SHA256,
    )
    require_equal(
        "production selector match fields",
        selector_regression["selector_match_fields"],
        ["request_id", "phase", "phase_occurrence"],
    )
    require_equal(
        "production selector forbidden predicate fields",
        selector_regression["forbidden_participant_predicate_fields"],
        ["q_len", "kv_len", "forward_id"],
    )
    require_equal("production selector request-phase coverage", selector_regression["bound_request_phase_count"], 16)
    require_equal("production selector target coverage", selector_regression["bound_target_count"], 13_568)
    require_equal("production selector layer coverage", selector_regression["bound_layer_target_count"], 1_024)
    require_equal("production selector process coverage", selector_regression["bound_process_target_count"], 12_544)
    require_equal("production selector bulk side effects", selector_regression["bulk_side_effect_count"], 0)
    require_equal("production selector formal device queries", selector_regression["formal_device_query_count"], 0)
    require(all(selector_regression["regressions"].values()), "production selector regression set incomplete")
    frozen_hashes = {row["relative_path"]: row["sha256"] for row in frozen["files"]}
    require_equal(
        "production selector frozen binder source",
        selector_regression["production_binder_source_sha256"],
        frozen_hashes["tools/r07_common.py"],
    )
    document = {
        "schema_version": 1,
        "status": "complete",
        "runtime_run_id": RUN_ID,
        "runtime_attempt_id": ATTEMPT_ID,
        "lineage_id": LINEAGE_ID,
        "trace_profile_sha256": EXPECTED["profile_sha256"],
        "target_root": str(TARGET_ROOT),
        "target_git_commit": EXPECTED["target_commit"],
        "target_git_branch": "repro-gqa-page784-k5120-batch8-final",
        "clean_index_worktree_and_untracked": True,
        "source_files": source_rows,
        "frozen_tool_manifest_path": str(tool_manifest_path()),
        "frozen_tool_manifest_sha256": sha256_path(tool_manifest_path()),
        "frozen_tool_count": len(frozen["files"]),
        "stage_source_delta_path": str(SOURCE_DELTA_PATH),
        "stage_source_delta_sha256": sha256_path(SOURCE_DELTA_PATH),
        "cumulative_runtime_ledger_path": str(LEDGER_PATH),
        "cumulative_runtime_ledger_sha256": EXPECTED["ledger_sha256"],
        "direct_handoffs": direct,
        "predecessor_validation_sha256": sha256_path(PREDECESSOR_VALIDATION_PATH),
        "resolved_input_contract_sha256": sha256_path(RESOLVED_CONTRACT_PATH),
        "pre_freeze_postdevice_recovery_regressions_sha256": sha256_path(PREFREEZE_POSTDEVICE_REGRESSION_PATH),
        "pre_freeze_bulk_preparation_regression_sha256": sha256_path(PREFREEZE_BULK_REGRESSION_PATH),
        "pre_freeze_runtime_patch_regression_sha256": sha256_path(PREFREEZE_RUNTIME_PATCH_REGRESSION_PATH),
        "pre_freeze_bytecode_surface_regression_sha256": sha256_path(
            PREFREEZE_BYTECODE_SURFACE_REGRESSION_PATH
        ),
        "pre_freeze_python_bytecode_quarantine_sha256": sha256_path(QUARANTINE_RECORD_PATH),
        "pre_freeze_python_bytecode_file_count": quarantine["file_count"],
        "service_validation_path_recovery": retry["service_validation_path_recovery"],
        "request_manifest_hash_recovery": retry["request_manifest_hash_recovery"],
        "postmeasurement_storage_recovery": retry["postmeasurement_storage_recovery"],
        "predecessor_storage_relocation": retry["predecessor_storage_relocation"],
        "worker_rebuild_recovery": retry["worker_rebuild_recovery"],
        "runtime_patch_path_recovery": retry["runtime_patch_path_recovery"],
        "bulk_input_binding_recovery": retry["bulk_input_binding_recovery"],
        "runtime_patch_fixture_recovery": retry["runtime_patch_fixture_recovery"],
        "attempt024_schema_nfs_recovery": retry["attempt024_schema_nfs_recovery"],
        "attempt025_dynamic_capacity_recovery": retry[
            "attempt025_dynamic_capacity_recovery"
        ],
        "attempt026_abi_runtime_recovery": retry[
            "attempt026_abi_runtime_recovery"
        ],
        "attempt026_abi_runtime_recovery_audit": abi_recovery_audit,
        "attempt027_historical_identity_recovery": retry[
            "attempt027_historical_identity_recovery"
        ],
        "attempt027_historical_identity_recovery_audit": historical_identity_audit,
        "attempt028_bytecode_surface_recovery": retry[
            "attempt028_bytecode_surface_recovery"
        ],
        "attempt028_bytecode_surface_recovery_audit": bytecode_surface_audit,
        "attempt029_bytecode_empty_set_recovery": retry[
            "attempt029_bytecode_empty_set_recovery"
        ],
        "attempt029_bytecode_empty_set_recovery_audit": bytecode_empty_set_audit,
        "attempt030_sidecar_fixture_recovery": retry[
            "attempt030_sidecar_fixture_recovery"
        ],
        "attempt030_sidecar_fixture_recovery_audit": sidecar_fixture_audit,
        "attempt031_prior_attempt_count_recovery": retry[
            "attempt031_prior_attempt_count_recovery"
        ],
        "attempt031_prior_attempt_count_recovery_audit": prior_attempt_count_audit,
        "attempt036_preformal_ordinal_binding_recovery": retry[
            "attempt036_preformal_ordinal_binding_recovery"
        ],
        "attempt037_preformal_historical_validator_ordinal_recovery": retry[
            "attempt037_preformal_historical_validator_ordinal_recovery"
        ],
        "attempt038_preformal_field_value_identity_recovery": retry[
            "attempt038_preformal_field_value_identity_recovery"
        ],
        "attempt038_preformal_field_value_identity_recovery_audit": predecessor[
            "attempt038_preformal_field_value_identity_recovery_audit"
        ],
        "attempt039_predevice_bulk_helper_identity_recovery": retry[
            "attempt039_predevice_bulk_helper_identity_recovery"
        ],
        "attempt039_predevice_bulk_helper_identity_recovery_audit": attempt039_recovery_audit,
        "attempt040_predevice_historical_successor_role_recovery": retry[
            "attempt040_predevice_historical_successor_role_recovery"
        ],
        "attempt040_predevice_historical_successor_role_recovery_audit": attempt040_recovery_audit,
        "attempt041_predevice_tool_freeze_dependency_recovery": retry[
            "attempt041_predevice_tool_freeze_dependency_recovery"
        ],
        "attempt041_predevice_tool_freeze_dependency_recovery_audit": attempt041_recovery_audit,
        "attempt042_predevice_admission_reference_key_recovery": retry[
            "attempt042_predevice_admission_reference_key_recovery"
        ],
        "attempt042_predevice_admission_reference_key_recovery_audit": attempt042_recovery_audit,
        "post_attempt031_worker_recovery_audit": post_attempt031_audit,
        "preproduction_recovery_identity_audit": preproduction_recovery_identity_audit,
        "preproduction_cross_helper_recovery_identity_audit": preproduction_cross_helper_recovery_identity_audit,
        "attempt_024_025_026_027_028_029_030_031_maintenance_inputs": attempt024_025_026_maintenance,
        "pre_freeze_durable_copy_regression_sha256": sha256_path(
            PREFREEZE_DURABLE_COPY_REGRESSION_PATH
        ),
        "durable_nfs_storage": durable_nfs_storage,
        "worker_rebuild_recovery_audit": worker_rebuild_audit,
        "bulk_input_binding_recovery_audit": bulk_input_audit,
        "runtime_patch_fixture_recovery_audit": runtime_fixture_audit,
        "request_manifest_identity": request_manifest_identity,
        "predecessor_storage_relocation_audit": relocation_audit,
        "external_runtime_evidence_consumed": False,
    }
    write_json_x(SOURCE_IMMUTABILITY_PATH, document)
    return document


def _audit_aot_copy() -> dict[str, Any]:
    manifest = _read_json(COPY_MANIFEST_PATH)
    require_equal("AOT copy status", manifest["status"], "complete")
    require_equal("AOT copy attempt", manifest["runtime_attempt_id"], ATTEMPT_ID)
    require_equal("AOT tree row count", len(manifest["files"]), 17062)
    total = 0
    for row in manifest["files"]:
        relative = row["relative_path"]
        source = R01_ROOT / "cache" / relative
        copied = BULK_PATHS["aot_cache"] / relative
        require(source.is_file() and copied.is_file(), f"AOT member missing: {relative}")
        require_equal(f"AOT source size {relative}", source.stat().st_size, int(row["size"]))
        require_equal(f"AOT copy size {relative}", copied.stat().st_size, int(row["size"]))
        require_equal(f"AOT source hash {relative}", sha256_path(source), row["sha256"])
        require_equal(f"AOT copy hash {relative}", sha256_path(copied), row["sha256"])
        require(os.stat(source).st_ino != os.stat(copied).st_ino, f"AOT source/copy hardlink forbidden: {relative}")
        total += int(row["size"])
    require_equal("AOT total bytes", total, int(manifest["copied_cache_total_bytes"]))
    return {
        "status": "complete",
        "file_count": len(manifest["files"]),
        "total_bytes": total,
        "regular_content_tree_v1_sha256": manifest["copied_cache_regular_content_tree_v1_sha256"],
        "mode_inclusive_manifest_v1_sha256": manifest["copied_cache_mode_inclusive_manifest_v1_sha256"],
        "manifest_sha256": sha256_path(COPY_MANIFEST_PATH),
        "all_source_and_current_copy_bytes_rehashed": True,
        "all_source_copy_inodes_distinct": True,
    }


def _audit_raw() -> dict[str, Any]:
    inventory = _read_json(RAW_INVENTORY_PATH)
    _validate_identity(inventory, "raw inventory")
    require_equal("raw database count", inventory["required_primary_database_count"], 1)
    require_equal("raw PFTrace family count", inventory["required_primary_pftrace_logical_family_count"], 1)
    require_equal("unknown raw files", inventory["unknown_raw_files"], [])
    require(inventory["all_raw_bytes_sealed"] is True, "raw inventory is not sealed")
    require(inventory["all_external_bulk_bytes_sealed"] is True, "bulk inventory is not fully sealed")
    require(inventory["all_three_bulk_entrypoints_fully_inventoried"] is True, "bulk entrypoint inventory incomplete")
    native_seal = inventory.get("prepostprocess_native_capture_seal")
    require(isinstance(native_seal, dict), "pre-postprocess native seal audit missing")
    require(native_seal.get("validated_before_postprocess") is True, "native bytes were not validated before postprocess")
    require_equal(
        "pre-postprocess native seal path",
        native_seal.get("path"),
        str(PREPOSTPROCESS_NATIVE_SEAL_PATH),
    )
    require_equal(
        "pre-postprocess native seal hash",
        native_seal.get("sha256"),
        sha256_path(PREPOSTPROCESS_NATIVE_SEAL_PATH),
    )
    require_equal(
        "pre-postprocess bound sidecar hash",
        native_seal.get("bound_target_sidecar_sha256"),
        sha256_path(R07_BOUND_TARGET_SIDECAR_PATH),
    )
    observed_entrypoint_files = set()
    for row in [*inventory["raw_files"], *inventory["hipprof_temporary_files"], *inventory["aot_cache_files"]]:
        entrypoint = Path(row["attempt_entrypoint_path"])
        storage = BULK_ROOT / row["storage_relative_path"]
        require(entrypoint.is_file() and storage.is_file(), f"sealed bulk file absent: {entrypoint}")
        left = entrypoint.stat(); right = storage.stat()
        require_equal(f"bulk inode {entrypoint}", left.st_ino, right.st_ino)
        require_equal(f"bulk device {entrypoint}", left.st_dev, EXPECTED["bulk_filesystem_device"])
        require_equal(f"bulk storage device {entrypoint}", right.st_dev, EXPECTED["bulk_filesystem_device"])
        require_equal(f"bulk size {entrypoint}", left.st_size, int(row["size"]))
        require_equal(f"bulk attempt hash {entrypoint}", sha256_path(entrypoint), row["sha256"])
        require_equal(f"bulk storage hash {entrypoint}", sha256_path(storage), row["sha256"])
        observed_entrypoint_files.add(str(entrypoint))
    observed_nonregular_objects = set()
    for row in inventory["nonregular_bulk_objects"]:
        entrypoint = Path(row["attempt_entrypoint_path"])
        storage = BULK_ROOT / row["storage_relative_path"]
        left = entrypoint.lstat()
        right = storage.lstat()
        require(not stat.S_ISREG(left.st_mode), f"sealed nonregular object became regular: {entrypoint}")
        require(not stat.S_ISLNK(left.st_mode), f"sealed nonregular object became symlink: {entrypoint}")
        require_equal(f"nonregular kind {entrypoint}", row["object_kind"], row["attempt_lstat"]["object_kind"])
        require_equal(f"nonregular storage kind {entrypoint}", row["object_kind"], row["storage_lstat"]["object_kind"])
        for field, observed_left, observed_right in (
            ("filesystem_device", left.st_dev, right.st_dev),
            ("inode", left.st_ino, right.st_ino),
            ("mode", left.st_mode, right.st_mode),
            ("size", left.st_size, right.st_size),
        ):
            require_equal(f"nonregular dual-view {field} {entrypoint}", observed_left, observed_right)
            require_equal(f"nonregular sealed attempt {field} {entrypoint}", observed_left, int(row["attempt_lstat"][field]))
            require_equal(f"nonregular sealed storage {field} {entrypoint}", observed_right, int(row["storage_lstat"][field]))
        require_equal(f"nonregular null content hash {entrypoint}", row["sha256"], None)
        require(row["preserved_without_deletion"] is True, f"nonregular preservation flag absent: {entrypoint}")
        observed_nonregular_objects.add(str(entrypoint))
    for name, root in BULK_ENTRYPOINTS.items():
        for path in root.rglob("*"):
            require(not path.is_symlink(), f"nested symlink appeared after bulk seal {name}: {path}")
    current = {
        str(path) for root in (RAW_ROOT, HIPPROF_TMP, BULK_ENTRYPOINTS["aot_cache"])
        for path in root.rglob("*") if path.is_file()
    }
    require_equal("sealed cache/raw/tmp file set", current, observed_entrypoint_files)
    current_nonregular = {
        str(path) for root in (RAW_ROOT, HIPPROF_TMP, BULK_ENTRYPOINTS["aot_cache"])
        for path in root.rglob("*")
        if not stat.S_ISDIR(path.lstat().st_mode)
        and not stat.S_ISREG(path.lstat().st_mode)
    }
    require_equal("sealed bulk nonregular object set", current_nonregular, observed_nonregular_objects)
    require_equal("nonregular bulk count", len(inventory["nonregular_bulk_objects"]), int(inventory["nonregular_bulk_object_count"]))
    require(inventory["all_nonregular_objects_sealed_by_dual_path_lstat"] is True, "nonregular dual-path lstat seal missing")
    require(inventory["all_nonregular_objects_preserved_without_deletion"] is True, "nonregular object deletion flag")
    require(inventory["nonregular_objects_have_no_fabricated_content_sha256"] is True, "nonregular fabricated hash flag")
    require_equal("cache inventory file count", len(inventory["aot_cache_files"]), int(inventory["aot_cache_file_count"]))
    require_equal("cache inventory total bytes", sum(int(row["size"]) for row in inventory["aot_cache_files"]), int(inventory["aot_cache_total_bytes"]))
    require_equal("cache inventory tree identity", canonical_sha256([
        {
            "relative_path": row["attempt_entrypoint_relative_path"],
            "size": row["size"],
            "sha256": row["sha256"],
            "role": row["role"],
        }
        for row in inventory["aot_cache_files"]
    ]), inventory["aot_cache_tree_identity_sha256"])
    aot_delta = inventory["aot_seed_and_current_attempt_derivation"]
    require_equal("AOT seed/delta audit status", aot_delta["status"], "complete")
    require_equal("AOT seed missing count", aot_delta["seed_missing_file_count"], 0)
    require_equal("AOT seed modified count", aot_delta["seed_modified_file_count"], 0)
    require(aot_delta["seed_files_byte_identical"] is True, "AOT seed bytes changed")
    require(aot_delta["all_derived_identities_cover_both_ranks"] is True, "derived AOT lacks both-rank coverage")
    require(aot_delta["direct_load_of_seed_identity_required"] is False, "forbidden direct-seed-load requirement reappeared")
    require(aot_delta["failed_attempt_derived_aot_consumed"] is False, "failed-attempt derived AOT was consumed")
    require_equal(
        "AOT current-output delta count",
        aot_delta["added_file_count"],
        int(inventory["current_R07_runtime_cache_output_file_count"]),
    )
    database = [row for row in inventory["raw_files"] if row["role"] == "required_primary_database"]
    require_equal("one sealed database row", len(database), 1)
    pftrace = [row for row in inventory["raw_files"] if row["role"].startswith("required_primary_pftrace")]
    require_equal("PFTrace member count", len(pftrace), int(inventory["required_primary_pftrace_file_count"]))
    require_equal("PFTrace total bytes", sum(int(row["size"]) for row in pftrace), int(inventory["required_primary_pftrace_total_size"]))
    return {
        "status": "complete",
        "inventory": inventory,
        "inventory_sha256": sha256_path(RAW_INVENTORY_PATH),
        "database_sha256": database[0]["sha256"],
        "raw_file_count": len(inventory["raw_files"]),
        "hipprof_temporary_file_count": len(inventory["hipprof_temporary_files"]),
        "aot_cache_file_count": len(inventory["aot_cache_files"]),
        "nonregular_bulk_object_count": len(inventory["nonregular_bulk_objects"]),
        "nonregular_bulk_object_kind_counts": inventory["nonregular_bulk_object_kind_counts"],
        "current_R07_runtime_cache_output_file_count": int(inventory["current_R07_runtime_cache_output_file_count"]),
        "aot_seed_and_current_attempt_derivation": aot_delta,
        "PFTrace_member_count": len(pftrace),
        "all_bulk_files_independently_rehashed_through_both_paths": True,
        "all_nonregular_bulk_objects_independently_revalidated_by_dual_path_lstat": True,
        "all_nonregular_bulk_objects_preserved_without_deletion": True,
        "all_three_bulk_entrypoints_fully_inventoried": True,
        "prepostprocess_native_capture_seal": native_seal,
    }


def _audit_durable_copy(raw_audit: dict[str, Any], lifecycle_audit: dict[str, Any]) -> dict[str, Any]:
    """Independently rehash the complete marker-authorized durable copy."""
    authorization = _read_json(BULK_AUTH_PATH)
    durable = authorization.get("durable_nfs_storage")
    require(isinstance(durable, dict), "signed durable NFS storage missing")
    require_equal("durable contract canonical identity", canonical_sha256(durable), EXPECTED["durable_nfs_storage_sha256"])
    checkpoint_contract = durable.get("capture_db_checkpoint")
    require(
        isinstance(checkpoint_contract, dict)
        and checkpoint_contract.get("status") == "required"
        and checkpoint_contract.get("helper_path")
        == str(CAPTURE_DB_CHECKPOINT_HELPER)
        and checkpoint_contract.get("helper_sha256")
        == EXPECTED["capture_db_checkpoint_helper_sha256"]
        and checkpoint_contract.get("marker_path")
        == str(CAPTURE_DB_DURABLE_MARKER)
        and checkpoint_contract.get("offline_export_before_checkpoint_allowed")
        is False
        and checkpoint_contract.get("later_full_raw_copy_must_reverify_database")
        is True,
        "signed capture DB checkpoint contract drift",
    )
    require_equal(
        "capture DB checkpoint helper hash in completion audit",
        sha256_path(CAPTURE_DB_CHECKPOINT_HELPER),
        EXPECTED["capture_db_checkpoint_helper_sha256"],
    )
    require(
        CAPTURE_DB_DURABLE_MARKER.is_file()
        and not CAPTURE_DB_DURABLE_MARKER.is_symlink(),
        "capture DB durable marker missing/nonregular",
    )
    checkpoint_marker = _read_json(CAPTURE_DB_DURABLE_MARKER)
    checkpoint_payload = dict(checkpoint_marker)
    checkpoint_payload_sha256 = checkpoint_payload.pop(
        "record_payload_sha256", None
    )
    require_equal(
        "capture DB checkpoint marker payload hash",
        checkpoint_payload_sha256,
        canonical_sha256(checkpoint_payload),
    )
    active_database = RAW_ROOT / "capture.db"
    durable_database = DURABLE_NFS_PATHS["raw"] / "capture.db"
    for label, path in (
        ("active checkpoint database", active_database),
        ("durable checkpoint database", durable_database),
    ):
        require(
            path.is_file() and not path.is_symlink(),
            f"{label} missing/nonregular",
        )
    active_database_identity = {
        "path": str(BULK_PATHS["raw"] / "capture.db"),
        "size": active_database.stat().st_size,
        "sha256": sha256_path(active_database),
    }
    durable_database_identity = {
        "path": str(durable_database),
        "size": durable_database.stat().st_size,
        "sha256": sha256_path(durable_database),
    }
    require_equal(
        "checkpoint marker active DB identity",
        {
            key: checkpoint_marker["source_database"][key]
            for key in ("path", "size", "sha256")
        },
        active_database_identity,
    )
    require_equal(
        "checkpoint marker durable DB identity",
        {
            key: checkpoint_marker["durable_database"][key]
            for key in ("path", "size", "sha256")
        },
        durable_database_identity,
    )
    require_equal(
        "checkpointed active/durable DB byte identity",
        {key: active_database_identity[key] for key in ("size", "sha256")},
        {key: durable_database_identity[key] for key in ("size", "sha256")},
    )
    require(
        checkpoint_marker.get("status") == "complete"
        and checkpoint_marker.get("record_type")
        == "r07_capture_db_durable_nfs_checkpoint"
        and checkpoint_marker.get("run_id") == RUN_ID
        and checkpoint_marker.get("attempt_id") == ATTEMPT_ID
        and checkpoint_marker.get("offline_export_started_before_checkpoint")
        is False
        and checkpoint_marker.get("full_raw_durable_completion_claimed")
        is False
        and checkpoint_marker.get(
            "later_full_raw_copy_must_reverify_this_database"
        )
        is True,
        "capture DB checkpoint marker semantic drift",
    )
    require_equal("durable root contract", Path(durable["root"]), DURABLE_NFS_ROOT)
    require_equal("durable path contract", {name: Path(path) for name, path in durable["paths"].items()}, DURABLE_NFS_PATHS)
    require(DURABLE_NFS_ROOT.is_dir() and not DURABLE_NFS_ROOT.is_symlink(), "durable root invalid")
    require_equal("durable filesystem device", DURABLE_NFS_ROOT.stat().st_dev, int(durable["filesystem_device"]))
    require(DURABLE_NFS_PATHS["raw"].is_dir() and not DURABLE_NFS_PATHS["raw"].is_symlink(), "durable raw root invalid")
    require(DURABLE_COPY_MANIFEST_PATH.is_file() and not DURABLE_COPY_MANIFEST_PATH.is_symlink(), "durable copy manifest missing/nonregular")
    require(DURABLE_COMPLETION_MARKER_PATH.is_file() and not DURABLE_COMPLETION_MARKER_PATH.is_symlink(), "durable completion marker missing/nonregular")
    manifest = _read_json(DURABLE_COPY_MANIFEST_PATH)
    marker = _read_json(DURABLE_COMPLETION_MARKER_PATH)
    for label, document in (("durable manifest", manifest), ("durable marker", marker)):
        require_equal(f"{label} status", document.get("status"), "complete")
        require_equal(f"{label} run", document.get("runtime_run_id"), RUN_ID)
        require_equal(f"{label} attempt", document.get("runtime_attempt_id"), ATTEMPT_ID)
        require_equal(f"{label} lineage", document.get("lineage_id"), LINEAGE_ID)
        require_equal(f"{label} profile", document.get("trace_profile_sha256"), EXPECTED["profile_sha256"])
    require_equal("durable copy phase", manifest.get("copy_phase"), durable["copy_phase"])
    require_equal("durable manifest source root", manifest.get("source_root"), str(ARTIFACT_ROOT))
    require_equal("durable manifest destination root", manifest.get("destination_root"), str(DURABLE_NFS_PATHS["raw"]))
    require_equal("durable marker destination root", marker.get("destination_root"), str(DURABLE_NFS_PATHS["raw"]))
    require_equal("durable marker manifest path", marker["manifest"]["path"], str(DURABLE_COPY_MANIFEST_PATH))
    require_equal("durable marker manifest size", int(marker["manifest"]["size"]), DURABLE_COPY_MANIFEST_PATH.stat().st_size)
    require_equal("durable marker manifest hash", marker["manifest"]["sha256"], sha256_path(DURABLE_COPY_MANIFEST_PATH))

    lifecycle = lifecycle_audit["lifecycle"]
    completion = lifecycle.get("durable_raw_completion")
    require(isinstance(completion, dict), "lifecycle durable completion missing")
    for label, path, reference in (
        ("manifest", DURABLE_COPY_MANIFEST_PATH, completion.get("manifest")),
        ("marker", DURABLE_COMPLETION_MARKER_PATH, completion.get("completion_marker")),
    ):
        require(isinstance(reference, dict), f"lifecycle durable {label} reference malformed")
        require_equal(f"lifecycle durable {label} path", reference["path"], str(path))
        require_equal(f"lifecycle durable {label} size", int(reference["size"]), path.stat().st_size)
        require_equal(f"lifecycle durable {label} hash", reference["sha256"], sha256_path(path))
    require_equal("lifecycle durable contract", lifecycle.get("durable_nfs_storage"), durable)
    require_equal("raw inventory durable audit status", raw_audit["inventory"]["durable_raw_copy"]["status"], "complete")
    require(raw_audit["inventory"]["durable_raw_copy"]["validated_before_postprocess"] is True, "raw inventory durable pre-postprocess gate missing")

    source_rows = manifest.get("source_rows")
    copy_rows = manifest.get("copy_rows")
    destination_rows = manifest.get("destination_rows")
    require(isinstance(source_rows, list) and isinstance(copy_rows, list) and isinstance(destination_rows, list), "durable manifest row arrays malformed")
    observed_sources = []
    for row in source_rows:
        source = Path(str(row["source_path"]))
        require(source.is_absolute(), f"durable source is not absolute: {source}")
        try:
            artifact_relative = source.relative_to(ARTIFACT_ROOT).as_posix()
        except ValueError as exc:
            raise RuntimeError(f"durable source escapes artifact root: {source}") from exc
        relative = (
            "capture.db"
            if artifact_relative == "capture/raw/capture.db"
            else artifact_relative
        )
        require_equal(
            "durable source artifact-relative path",
            row.get("artifact_relative_path"),
            artifact_relative,
        )
        require_equal("durable source destination relative path", relative, row["relative_path"])
        require(source.is_file() and not source.is_symlink(), f"durable source missing/nonregular: {source}")
        observed_sources.append({
            "relative_path": relative,
            "size": source.stat().st_size,
            "sha256": sha256_path(source),
            "mode": stat.S_IMODE(source.lstat().st_mode),
        })
    observed_sources.sort(key=lambda row: row["relative_path"])
    require_equal("durable source relative-path uniqueness", len({row["relative_path"] for row in observed_sources}), len(observed_sources))

    observed_destinations = []
    destination_mtimes = []
    for path in sorted(DURABLE_NFS_PATHS["raw"].rglob("*"), key=lambda item: item.relative_to(DURABLE_NFS_PATHS["raw"]).as_posix()):
        mode = path.lstat().st_mode
        require(not stat.S_ISLNK(mode), f"durable destination symlink forbidden: {path}")
        if stat.S_ISDIR(mode):
            continue
        require(stat.S_ISREG(mode), f"durable destination nonregular object forbidden: {path}")
        require(".r07-attempt-043.partial" not in path.name, f"durable partial member remained: {path}")
        observed_destinations.append({
            "relative_path": path.relative_to(DURABLE_NFS_PATHS["raw"]).as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256_path(path),
            "mode": stat.S_IMODE(mode),
        })
        destination_mtimes.append(path.stat().st_mtime_ns)
    require_equal("durable independently rehashed destination surface", observed_destinations, observed_sources)
    require_equal("durable sealed destination rows", destination_rows, observed_destinations)
    require_equal("durable copy row count", len(copy_rows), len(observed_sources))
    for source_row, copy_row in zip(source_rows, copy_rows):
        for field in ("relative_path", "size", "sha256", "mode", "source_path", "source_role"):
            require_equal(f"durable copy row {field}", copy_row.get(field), source_row.get(field))
        require_equal("durable copy destination", copy_row.get("destination_path"), str(DURABLE_NFS_PATHS["raw"] / source_row["relative_path"]))
        require(copy_row.get("copy_state") in {"temporary_verified_then_atomic_rename", "existing_complete_file_revalidated"}, "durable copy state invalid")
    identity = canonical_sha256(observed_sources)
    total_bytes = sum(int(row["size"]) for row in observed_sources)
    for label, observed in (
        ("manifest source", manifest.get("source_surface_canonical_sha256")),
        ("manifest destination", manifest.get("destination_surface_canonical_sha256")),
        ("marker destination", marker.get("destination_surface_canonical_sha256")),
        ("lifecycle destination", completion.get("destination_surface_canonical_sha256")),
    ):
        require_equal(f"durable {label} identity", observed, identity)
    require_equal("durable manifest file count", int(manifest.get("regular_file_count", -1)), len(observed_sources))
    require_equal("durable marker file count", int(marker.get("regular_file_count", -1)), len(observed_sources))
    require_equal("durable lifecycle file count", int(completion.get("regular_file_count", -1)), len(observed_sources))
    require_equal("durable manifest total bytes", int(manifest.get("regular_file_total_bytes", -1)), total_bytes)
    require_equal("durable marker total bytes", int(marker.get("regular_file_total_bytes", -1)), total_bytes)
    require_equal("durable lifecycle total bytes", int(completion.get("regular_file_total_bytes", -1)), total_bytes)
    require(marker.get("completion_marker_written_last") is True, "durable marker-last flag missing")
    require(marker.get("staging_preserved") is True and manifest.get("staging_deleted") is False, "durable staging was not preserved")
    require(manifest.get("temporary_files_verified_before_atomic_rename") is True, "durable atomic publication gate missing")
    require(manifest.get("every_destination_size_and_sha256_verified") is True, "durable per-file hash gate missing")
    require(
        manifest.get("checkpointed_database_reverified_during_full_raw_copy")
        is True,
        "full raw copy did not reverify the checkpointed database",
    )
    require(manifest.get("destination_surface_independently_rehashed") is True, "durable destination surface rehash gate missing")
    require(manifest.get("nonregular_objects_copied") is False, "durable nonregular object copy occurred")
    require_equal("durable root final entry set", {path.name for path in DURABLE_NFS_ROOT.iterdir()}, {"raw", CAPTURE_DB_DURABLE_MARKER.name, DURABLE_COMPLETION_MARKER_PATH.name})
    marker_mtime = DURABLE_COMPLETION_MARKER_PATH.stat().st_mtime_ns
    require(marker_mtime >= DURABLE_COPY_MANIFEST_PATH.stat().st_mtime_ns, "durable marker predates manifest")
    require(
        marker_mtime >= CAPTURE_DB_DURABLE_MARKER.stat().st_mtime_ns,
        "full durable completion marker predates capture DB checkpoint marker",
    )
    require(not destination_mtimes or marker_mtime >= max(destination_mtimes), "durable marker predates destination data")
    require(all(Path(str(row["source_path"])).is_file() for row in source_rows), "durable staging source disappeared")
    return {
        "status": "complete",
        "durable_nfs_storage": durable,
        "manifest": _file_record(DURABLE_COPY_MANIFEST_PATH),
        "completion_marker": _file_record(DURABLE_COMPLETION_MARKER_PATH),
        "capture_db_checkpoint_marker": _file_record(
            CAPTURE_DB_DURABLE_MARKER
        ),
        "capture_db_checkpoint_record_payload_sha256": checkpoint_payload_sha256,
        "destination_root": str(DURABLE_NFS_PATHS["raw"]),
        "regular_file_count": len(observed_sources),
        "regular_file_total_bytes": total_bytes,
        "surface_canonical_sha256": identity,
        "all_sources_and_destinations_independently_rehashed": True,
        "completion_marker_verified_last": True,
        "staging_preserved": True,
        "active_sqlite_or_profiler_staging_on_nfs": False,
        "nonregular_objects_copied": False,
    }


def _registry_rows() -> list[dict[str, Any]]:
    path = CAPTURE_ROOT / "control/process_registry.jsonl"
    require(path.is_file(), "process registry absent")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(rows, "process registry empty")
    require(all(row.get("runtime_attempt_id") == ATTEMPT_ID for row in rows), "foreign attempt in process registry")
    unique: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        key = (int(row["pid"]), int(row["starttime_ticks"]))
        if key not in unique:
            unique[key] = row
    return [unique[key] for key in sorted(unique)]


def _audit_lifecycle() -> dict[str, Any]:
    predevice = _read_json(VALIDATION_ROOT / "predevice_gate_report.json")
    formal = _read_json(VALIDATION_ROOT / "formal_device_preflight.json")
    lifecycle = _read_json(LIFECYCLE_PATH)
    driver = _read_json(DRIVER_PATH)
    termination = _read_json(CAPTURE_ROOT / "control/all_processes_termination.json")
    post_capture = _read_json(CAPTURE_ROOT / "control/post_capture_process_verification.json")
    retry = _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")
    predevice_invocation_path = (
        ARTIFACT_ROOT / "attempts/predevice_gate_invocation.json"
    )
    predevice_stdout_path = ARTIFACT_ROOT / "attempts/predevice_gate.stdout.txt"
    predevice_stderr_path = ARTIFACT_ROOT / "attempts/predevice_gate.stderr.txt"
    predevice_invocation = _read_json(predevice_invocation_path)
    checkpoint_invocation = _read_json(DB_CHECKPOINT_INVOCATION_PATH)
    offline_export_invocation = _read_json(OFFLINE_EXPORT_INVOCATION_PATH)
    require_equal(
        "predevice invocation attempt",
        predevice_invocation["runtime_attempt_id"],
        ATTEMPT_ID,
    )
    require_equal(
        "predevice invocation command suffix",
        predevice_invocation["argv"][-2:],
        [str(TOOLS_ROOT / "run_r07_full_request.py"), "predevice-gate"],
    )
    require_equal(
        "predevice invocation bytecode environment",
        predevice_invocation["environment_delta"]["PYTHONDONTWRITEBYTECODE"],
        "1",
    )
    require_equal(
        "predevice invocation return code",
        predevice_invocation["returncode"],
        0,
    )
    require(
        predevice_invocation.get("stdout_and_stderr_persisted_before_returncode_assertion")
        is True,
        "predevice invocation output was not persisted before exit assertion",
    )
    require_equal(
        "predevice invocation stdout path",
        predevice_invocation["stdout_path"],
        str(predevice_stdout_path),
    )
    require_equal(
        "predevice invocation stderr path",
        predevice_invocation["stderr_path"],
        str(predevice_stderr_path),
    )
    require_equal(
        "predevice invocation stdout hash",
        predevice_invocation["stdout_sha256"],
        sha256_path(predevice_stdout_path),
    )
    require_equal(
        "predevice invocation stderr hash",
        predevice_invocation["stderr_sha256"],
        sha256_path(predevice_stderr_path),
    )
    require_equal("predevice status", predevice["status"], "complete")
    require_equal("predevice formal query count", predevice["formal_device_query_count"], 0)
    require_equal("predevice model count", predevice["model_initialization_count"], 0)
    require_equal("formal status", formal["status"], "complete")
    require_equal("formal query count", formal["formal_device_query_count"], 1)
    require_equal("formal device ranks", formal["device_binding"]["rank_to_physical_device"], {"0": 0, "1": 1})
    for field in (
        "marker_denominator_recovery",
        "postdevice_preworkload_recovery",
        "service_gate_recovery",
        "admission_schema_recovery",
        "bulk_preparation_recovery",
        "bulk_identity_schema_recovery",
        "socket_fixture_recovery",
        "service_validation_path_recovery",
        "request_manifest_hash_recovery",
        "postmeasurement_storage_recovery",
        "predecessor_storage_relocation",
        "worker_rebuild_recovery",
        "runtime_patch_path_recovery",
        "bulk_input_binding_recovery",
        "runtime_patch_fixture_recovery",
        "attempt024_schema_nfs_recovery",
        "attempt025_dynamic_capacity_recovery",
        "attempt026_abi_runtime_recovery",
        "attempt027_historical_identity_recovery",
        "attempt028_bytecode_surface_recovery",
        "attempt029_bytecode_empty_set_recovery",
        "attempt030_sidecar_fixture_recovery",
        "attempt031_prior_attempt_count_recovery",
        "attempt036_preformal_ordinal_binding_recovery",
        "attempt037_preformal_historical_validator_ordinal_recovery",
        "attempt038_preformal_field_value_identity_recovery",
        "attempt039_predevice_bulk_helper_identity_recovery",
        "attempt040_predevice_historical_successor_role_recovery",
        "attempt041_predevice_tool_freeze_dependency_recovery",
        "attempt042_predevice_admission_reference_key_recovery",
    ):
        require_equal(f"predevice {field}", predevice[field], retry[field])
        require_equal(f"formal {field}", formal[field], retry[field])
        require_equal(f"lifecycle {field}", lifecycle[field], retry[field])
    predecessor_validation = _read_json(PREDECESSOR_VALIDATION_PATH)
    abi_admission_audit = predecessor_validation[
        "attempt026_abi_runtime_recovery_audit"
    ]
    historical_identity_admission_audit = predecessor_validation[
        "attempt027_historical_identity_recovery_audit"
    ]
    bytecode_surface_admission_audit = predecessor_validation[
        "attempt028_bytecode_surface_recovery_audit"
    ]
    bytecode_empty_set_admission_audit = predecessor_validation[
        "attempt029_bytecode_empty_set_recovery_audit"
    ]
    sidecar_fixture_admission_audit = predecessor_validation[
        "attempt030_sidecar_fixture_recovery_audit"
    ]
    prior_attempt_count_admission_audit = predecessor_validation[
        "attempt031_prior_attempt_count_recovery_audit"
    ]
    post_attempt031_worker_recovery_audit = predecessor_validation[
        "post_attempt031_worker_recovery_audit"
    ]
    attempt038_recovery_admission_audit = predecessor_validation[
        "attempt038_preformal_field_value_identity_recovery_audit"
    ]
    attempt039_recovery_admission_audit = predecessor_validation[
        "attempt039_predevice_bulk_helper_identity_recovery_audit"
    ]
    attempt040_recovery_admission_audit = predecessor_validation[
        "attempt040_predevice_historical_successor_role_recovery_audit"
    ]
    attempt041_recovery_admission_audit = predecessor_validation[
        "attempt041_predevice_tool_freeze_dependency_recovery_audit"
    ]
    attempt042_recovery_admission_audit = predecessor_validation[
        "attempt042_predevice_admission_reference_key_recovery_audit"
    ]
    preproduction_recovery_identity_audit = predecessor_validation[
        "preproduction_recovery_identity_audit"
    ]
    preproduction_cross_helper_recovery_identity_audit = predecessor_validation[
        "preproduction_cross_helper_recovery_identity_audit"
    ]
    capture_db_checkpoint_audit = predecessor_validation[
        "capture_db_checkpoint_audit"
    ]
    for document, label in (
        (predevice, "predevice"),
        (formal, "formal"),
        (lifecycle, "lifecycle"),
    ):
        require_equal(
            f"{label} attempt-026 ABI admission audit",
            document["attempt026_abi_runtime_recovery_audit"],
            abi_admission_audit,
        )
        require_equal(
            f"{label} attempt-027 historical-identity admission audit",
            document["attempt027_historical_identity_recovery_audit"],
            historical_identity_admission_audit,
        )
        require_equal(
            f"{label} attempt-028 bytecode-surface admission audit",
            document["attempt028_bytecode_surface_recovery_audit"],
            bytecode_surface_admission_audit,
        )
        require_equal(
            f"{label} attempt-029 bytecode-empty-set admission audit",
            document["attempt029_bytecode_empty_set_recovery_audit"],
            bytecode_empty_set_admission_audit,
        )
        require_equal(
            f"{label} attempt-030 sidecar-fixture admission audit",
            document["attempt030_sidecar_fixture_recovery_audit"],
            sidecar_fixture_admission_audit,
        )
        require_equal(
            f"{label} attempt-031 prior-attempt-count admission audit",
            document["attempt031_prior_attempt_count_recovery_audit"],
            prior_attempt_count_admission_audit,
        )
        require_equal(
            f"{label} post-attempt031 worker recovery audit",
            document["post_attempt031_worker_recovery_audit"],
            post_attempt031_worker_recovery_audit,
        )
        require_equal(
            f"{label} attempt-038 field-value recovery audit",
            document[
                "attempt038_preformal_field_value_identity_recovery_audit"
            ],
            attempt038_recovery_admission_audit,
        )
        require_equal(
            f"{label} attempt-039 bulk-helper recovery audit",
            document[
                "attempt039_predevice_bulk_helper_identity_recovery_audit"
            ],
            attempt039_recovery_admission_audit,
        )
        require_equal(
            f"{label} attempt-040 historical-successor-role recovery audit",
            document[
                "attempt040_predevice_historical_successor_role_recovery_audit"
            ],
            attempt040_recovery_admission_audit,
        )
        require_equal(
            f"{label} attempt-041 freezer-dependency recovery audit",
            document[
                "attempt041_predevice_tool_freeze_dependency_recovery_audit"
            ],
            attempt041_recovery_admission_audit,
        )
        require_equal(
            f"{label} attempt-042 reference-key recovery audit",
            document[
                "attempt042_predevice_admission_reference_key_recovery_audit"
            ],
            attempt042_recovery_admission_audit,
        )
        require_equal(
            f"{label} preproduction recovery-identity audit",
            document["preproduction_recovery_identity_audit"],
            preproduction_recovery_identity_audit,
        )
        require_equal(
            f"{label} preproduction cross-helper recovery-identity audit",
            document["preproduction_cross_helper_recovery_identity_audit"],
            preproduction_cross_helper_recovery_identity_audit,
        )
        require_equal(
            f"{label} capture DB checkpoint admission audit",
            document["capture_db_checkpoint_audit"],
            capture_db_checkpoint_audit,
        )
        sidecar_regression = document.get("sidecar_fixture_schema_regression")
        require(
            isinstance(sidecar_regression, dict)
            and sidecar_regression.get("status") == "complete"
            and sidecar_regression.get("production_frozen_normalizer_invoked")
            is True
            and sidecar_regression.get("positive_complete_event_validated")
            is True
            and sidecar_regression.get(
                "complete_event_fields_copied_from_bound_fixture_source"
            )
            is True
            and sidecar_regression.get(
                "each_required_field_omission_failed_closed"
            )
            is True
            and set(sidecar_regression.get("omission_negatives", {}))
            == set(sidecar_fixture_admission_audit["required_complete_event_fields"])
            and sidecar_regression.get("device_query_count") == 0
            and sidecar_regression.get("bulk_side_effect_count") == 0
            and sidecar_regression.get("completed_before_device_access") is True,
            f"{label} attempt-030 sidecar fixture regression incomplete",
        )
    durable = _read_json(BULK_AUTH_PATH)["durable_nfs_storage"]
    require_equal("predevice durable NFS storage", predevice["durable_nfs_storage"], durable)
    require_equal("formal durable NFS storage", formal["durable_nfs_storage"], durable)
    require_equal("lifecycle durable NFS storage", lifecycle["durable_nfs_storage"], durable)
    require_equal("lifecycle status", lifecycle["status"], "complete")
    expected_counts = {
        "model_initialization_count": 1,
        "collector_start_count": 1,
        "collector_stop_count": 1,
        "profiler_process_start_count": 1,
        "profiler_session_start_count": 1,
        "profiler_session_stop_count": 1,
        "profiler_session_flush_count": 1,
        "capture_database_durable_checkpoint_count": 1,
        "offline_database_export_count": 1,
        "warmup_request_count": 2,
        "measured_workload_count": 1,
        "measured_request_count": 8,
        "measured_output_token_count": 8192,
        "formal_device_query_count": 1,
    }
    for key, expected in expected_counts.items():
        require_equal(f"lifecycle {key}", lifecycle[key], expected)
    require(
        lifecycle.get("capture_database_only_no_export") is True,
        "live HIPProf capture was not database-only",
    )
    require(
        "--no-export" in lifecycle["hipprof_command"]
        and "--db" not in lifecycle["hipprof_command"],
        "live HIPProf command did not preserve DB-only capture semantics",
    )
    require(
        lifecycle.get("offline_database_export_process_reaped") is True,
        "offline PFTrace export process was not reaped",
    )
    for label, invocation, stdout_path, stderr_path in (
        (
            "capture DB checkpoint",
            checkpoint_invocation,
            DB_CHECKPOINT_STDOUT_PATH,
            DB_CHECKPOINT_STDERR_PATH,
        ),
        (
            "offline PFTrace export",
            offline_export_invocation,
            OFFLINE_EXPORT_STDOUT_PATH,
            OFFLINE_EXPORT_STDERR_PATH,
        ),
    ):
        require_equal(f"{label} status", invocation.get("status"), "complete")
        require_equal(
            f"{label} run", invocation.get("runtime_run_id"), RUN_ID
        )
        require_equal(
            f"{label} attempt", invocation.get("runtime_attempt_id"), ATTEMPT_ID
        )
        require_equal(f"{label} return code", invocation.get("returncode"), 0)
        require_equal(f"{label} start error", invocation.get("start_error"), None)
        require(
            invocation.get(
                "assertions_performed_after_stdout_stderr_persistence"
            )
            is True,
            f"{label} asserted before persisting stdout/stderr",
        )
        for stream_name, path in (("stdout", stdout_path), ("stderr", stderr_path)):
            reference = invocation.get(stream_name)
            require(isinstance(reference, dict), f"{label} {stream_name} reference malformed")
            require_equal(f"{label} {stream_name} path", reference.get("path"), str(path))
            require_equal(f"{label} {stream_name} size", int(reference.get("size", -1)), path.stat().st_size)
            require_equal(f"{label} {stream_name} hash", reference.get("sha256"), sha256_path(path))
    durable_checkpoint_contract = durable["capture_db_checkpoint"]
    require_equal(
        "checkpoint invocation signed contract",
        checkpoint_invocation.get("signed_contract"),
        durable_checkpoint_contract,
    )
    require_equal(
        "checkpoint invocation exact signed argv",
        checkpoint_invocation.get("argv"),
        durable_checkpoint_contract["argv"],
    )
    require_equal(
        "checkpoint invocation helper hash",
        checkpoint_invocation.get("helper_sha256"),
        EXPECTED["capture_db_checkpoint_helper_sha256"],
    )
    require_equal(
        "checkpoint invocation bytecode environment",
        checkpoint_invocation.get("PYTHONDONTWRITEBYTECODE"),
        "1",
    )
    offline_argv = offline_export_invocation.get("argv")
    require(isinstance(offline_argv, list), "offline PFTrace export argv malformed")
    require_equal("offline PFTrace export executable", offline_argv[0], str(Path("/opt/dtk/bin/hipprof")))
    require_equal("offline PFTrace export DB flag count", offline_argv.count("--db"), 1)
    db_index = offline_argv.index("--db")
    require_equal(
        "offline PFTrace export database",
        offline_argv[db_index + 1],
        str(BULK_PATHS["raw"] / "capture.db"),
    )
    require("--no-export" not in offline_argv, "offline export unexpectedly disabled")
    checkpoint_lifecycle = lifecycle.get("capture_db_durable_checkpoint")
    offline_lifecycle = lifecycle.get("offline_pftrace_export")
    require(isinstance(checkpoint_lifecycle, dict), "lifecycle checkpoint evidence missing")
    require(isinstance(offline_lifecycle, dict), "lifecycle offline-export evidence missing")
    require_equal(
        "lifecycle checkpoint invocation hash",
        checkpoint_lifecycle["invocation"]["sha256"],
        sha256_path(DB_CHECKPOINT_INVOCATION_PATH),
    )
    require_equal(
        "lifecycle checkpoint marker hash",
        checkpoint_lifecycle["marker"]["sha256"],
        sha256_path(CAPTURE_DB_DURABLE_MARKER),
    )
    require_equal(
        "lifecycle offline-export invocation hash",
        offline_lifecycle["invocation"]["sha256"],
        sha256_path(OFFLINE_EXPORT_INVOCATION_PATH),
    )
    require_equal(
        "offline export binds checkpoint marker",
        offline_export_invocation.get("checkpoint_marker_sha256"),
        sha256_path(CAPTURE_DB_DURABLE_MARKER),
    )
    require_equal("lifecycle rank coverage", lifecycle["rank_coverage"], [0, 1])
    require_equal("lifecycle device coverage", lifecycle["physical_device_coverage"], [0, 1])
    require_equal("lifecycle rank/device mapping", lifecycle["rank_to_physical_device"], {"0": 0, "1": 1})
    require(lifecycle["all_started_processes_terminated"] is True, "lifecycle cleanup incomplete")
    require(lifecycle["short_runtime_symlink_removed"] is True, "short runtime symlink cleanup false")
    require(
        not Path("/tmp/qdr07a36").exists()
        and not Path("/tmp/qdr07a36").is_symlink(),
        "short current-attempt runtime symlink remains at audit",
    )
    require_equal("driver status", driver["status"], "complete")
    require_equal("driver completed", driver["completed"], 8)
    require_equal("driver failed", driver["failed"], 0)
    require_equal("driver completion tokens", driver["total_completion_tokens"], 8192)
    require(
        driver["r07_bound_target_sidecar_created_after_worker_exit"] is True,
        "driver did not preserve post-exit bound-sidecar ordering",
    )
    require_equal("driver request-manifest recovery", driver["request_manifest_hash_recovery"], retry["request_manifest_hash_recovery"])
    require_equal("driver raw request-manifest identity", driver["r01_request_manifest_file_byte_sha256"], EXPECTED["r01_request_manifest_file_byte_sha256"])
    require_equal("driver canonical request-manifest identity", driver["r01_request_manifest_canonical_json_sha256"], EXPECTED["r01_request_manifest_canonical_json_sha256"])
    require(predevice["production_request_manifest_loader_invoked_predevice"] is True, "predevice production request loader not invoked")
    require_equal("predevice request identity", predevice["request_manifest_identity"], driver["request_manifest_identity"])
    request_manifest = _read_json(R01_REQUEST_MANIFEST_PATH)
    expected_ids = [row["request_id"] for row in request_manifest["records"]]
    require_equal("driver request order", driver["request_ids"], expected_ids)
    require_equal("driver dispatch order", driver["dispatch"]["observed_request_write_order"], expected_ids)
    require_equal("driver rank map keys", set(driver["request_rank_map"]), set(expected_ids))
    require_equal("driver rank coverage", sorted(set(int(value) for value in driver["request_rank_map"].values())), [0, 1])
    require_equal("profiler controls", [row["action"] for row in driver["profiler_control_events"]], ["start", "stop", "flush"])
    require(driver["dispatch"]["all_request_bodies_prestaged_before_profiler_start"] is True, "request prestage gate failed")
    require(driver["dispatch"]["inter_request_sleep_performed"] is False, "request-rate contract drift")
    require_equal("termination status", termination["status"], "complete")
    require(termination["all_started_processes_terminated"] is True, "registered process termination false")
    require(termination["all_profiler_tracees_and_tracers_terminated"] is True, "profiler cleanup false")
    require_equal("post-capture verification status", post_capture["status"], "complete")
    require(post_capture["all_started_processes_terminated"] is True, "post-capture process verification false")
    require(post_capture["all_profiler_tracees_and_tracers_terminated"] is True, "post-capture profiler verification false")
    require_equal("post-capture token processes", post_capture["attempt_or_profiler_session_token_processes"], [])
    require_equal("post-capture device owners", post_capture["open_device_fds_after_capture"], [])
    require(post_capture["port_8001_listening_after_capture"] is False, "post-capture service port remained active")
    registry = _registry_rows()
    alive = [row for row in registry if process_identity_alive(row)]
    require_equal("live registered identities at completion", alive, [])
    require_equal("post-audit device file owners", open_device_fds(), [])
    require_equal("post-audit service port", port_is_listening(8001), False)
    require(lifecycle["replay_performed"] is False, "replay occurred")
    require(lifecycle["pmc_collection_performed"] is False, "PMC occurred")
    require(lifecycle["report_generation_performed"] is False, "report occurred")
    return {
        "status": "complete",
        "predevice": _file_record(VALIDATION_ROOT / "predevice_gate_report.json"),
        "predevice_invocation": _file_record(predevice_invocation_path),
        "predevice_stdout": _file_record(predevice_stdout_path),
        "predevice_stderr": _file_record(predevice_stderr_path),
        "predevice_stdout_and_stderr_persisted_before_returncode_assertion": True,
        "formal_device_preflight": _file_record(VALIDATION_ROOT / "formal_device_preflight.json"),
        "capture_db_checkpoint_invocation": _file_record(DB_CHECKPOINT_INVOCATION_PATH),
        "capture_db_checkpoint_stdout": _file_record(DB_CHECKPOINT_STDOUT_PATH),
        "capture_db_checkpoint_stderr": _file_record(DB_CHECKPOINT_STDERR_PATH),
        "offline_pftrace_export_invocation": _file_record(OFFLINE_EXPORT_INVOCATION_PATH),
        "offline_pftrace_export_stdout": _file_record(OFFLINE_EXPORT_STDOUT_PATH),
        "offline_pftrace_export_stderr": _file_record(OFFLINE_EXPORT_STDERR_PATH),
        "capture_db_checkpoint_marker": _file_record(CAPTURE_DB_DURABLE_MARKER),
        "lifecycle": lifecycle,
        "driver_sha256": sha256_path(DRIVER_PATH),
        "post_capture_process_verification": _file_record(CAPTURE_ROOT / "control/post_capture_process_verification.json"),
        "registered_identity_count": len(registry),
        "alive_registered_identity_count": 0,
        "all_started_processes_terminated": True,
        "all_profiler_tracees_and_tracers_terminated": True,
        "device_file_owner_count_after_capture": 0,
        "service_port_released": True,
    }


def _independent_busy_union(kernels: list[dict[str, str]]) -> list[dict[str, int | str]]:
    result: list[dict[str, int | str]] = []
    for device in (0, 1):
        intervals = sorted(
            (int(row["begin_ns"]), int(row["end_ns"]))
            for row in kernels if int(row["native_device"]) == device
        )
        require(intervals, f"no kernel intervals on device {device}")
        merged: list[list[int]] = []
        for begin, end in intervals:
            require(end > begin, "non-positive kernel interval")
            if not merged or begin > merged[-1][1]:
                merged.append([begin, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)
        for ordinal, (begin, end) in enumerate(merged, 1):
            result.append({
                "busy_interval_id": f"device-{device}-busy-{ordinal:06d}",
                "dp_rank": device,
                "native_device": device,
                "begin_ns": begin,
                "end_ns": end,
                "duration_ns": end - begin,
            })
    return result


def _audit_trace(raw_audit: dict[str, Any]) -> dict[str, Any]:
    request_rows = _read_csv(TRACE_ROOT / "request_ranges.csv")
    forward_rows = _read_csv(TRACE_ROOT / "forward_ranges.csv")
    layer_rows = _read_csv(TRACE_ROOT / "layer_ranges.csv")
    processes = _read_csv(PROCESS_PATH)
    runtimes = _read_csv(RUNTIME_PATH)
    kernels = _read_csv(KERNEL_PATH)
    queues = _read_csv(QUEUE_PATH)
    busy = _read_csv(BUSY_PATH)
    targets = _read_json(R06_TARGETS_PATH)
    process_targets = [row for row in targets["rows"] if row["target_kind"] != "layer_parent"]
    source_process_target_ids = {row["canonical_target_id"] for row in process_targets}
    bound_sidecar = _read_json(R07_BOUND_TARGET_SIDECAR_PATH)
    _validate_identity(bound_sidecar, "bound target sidecar")
    require_equal(
        "bound target sidecar profile",
        bound_sidecar["trace_profile_sha256"],
        EXPECTED["profile_sha256"],
    )
    require_equal(
        "bound selector match fields",
        bound_sidecar["selector"]["match_fields"],
        ["request_id", "phase", "phase_occurrence"],
    )
    require_equal(
        "bound selector occurrence",
        bound_sidecar["selector"]["selected_phase_occurrence"],
        1,
    )
    require_equal(
        "bound selector forbidden fields",
        bound_sidecar["selector"]["forbidden_match_fields"],
        ["q_len", "kv_len", "forward_id"],
    )
    require_equal(
        "bound selector execution dedup",
        bound_sidecar["selector"]["execution_dedup_fields"],
        ["dp_rank", "runtime_execution_id"],
    )
    require_equal("bound target denominator", bound_sidecar["target_count"], 13_568)
    require_equal("bound process denominator", bound_sidecar["process_target_count"], 12_544)
    require_equal("bound layer denominator", bound_sidecar["layer_target_count"], 1_024)
    require_equal("bound request-phase denominator", bound_sidecar["bound_request_phase_count"], 16)
    require_equal("bound request-phase coverage", bound_sidecar["request_phase_coverage_fraction"], 1.0)
    require_equal("bound marker coverage", bound_sidecar["marker_coverage_fraction"], 1.0)
    bound_process_records = [
        row for row in bound_sidecar["records"] if row["target_kind"] != "layer_parent"
    ]
    bound_process_target_ids = {
        row["canonical_target_id"] for row in bound_process_records
    }
    require_equal(
        "bound process source R06 target coverage",
        {row["source_r06_target_id"] for row in bound_process_records},
        source_process_target_ids,
    )
    require_equal(
        "bound process marker names unique",
        len({row["hiptx_marker_utf8"] for row in bound_process_records}),
        12_544,
    )
    require_equal(
        "bound sidecar binding logs",
        {Path(row["path"]) for row in bound_sidecar["binding_logs"]},
        {
            R07_RUNTIME_BINDING_ROOT / "rank0.jsonl",
            R07_RUNTIME_BINDING_ROOT / "rank1.jsonl",
        },
    )
    for row in bound_sidecar["binding_logs"]:
        path = Path(row["path"])
        require_equal(f"bound log size {path}", path.stat().st_size, int(row["size"]))
        require_equal(f"bound log hash {path}", sha256_path(path), row["sha256"])
        require_equal(f"bound log row count {path}", int(row["row_count"]), 6_784)
    process_by_id = {row["process_range_id"]: row for row in processes}
    require_equal("request range count", len(request_rows), 1024)
    require_equal("forward range count", len(forward_rows), 1024)
    require_equal("layer range count", len(layer_rows), 1024)
    require_equal("process range count", len(processes), 12544)
    require_equal("process range IDs unique", len(process_by_id), len(processes))
    require_equal(
        "process canonical IDs",
        {row["canonical_target_id"] for row in processes},
        bound_process_target_ids,
    )
    require_equal(
        "process marker names",
        {row["range_name"] for row in processes},
        {row["hiptx_marker_utf8"] for row in bound_process_records},
    )
    require_equal("process canonical IDs unique", len({row["canonical_target_id"] for row in processes}), len(processes))
    require_equal("process target kinds", Counter(row["target_kind"] for row in processes), Counter({"process_parent": 8448, "fragment": 4096}))
    require_equal("process rank counts", Counter(int(row["dp_rank"]) for row in processes), Counter({0: 6272, 1: 6272}))
    require_equal("process device counts", Counter(int(row["native_device"]) for row in processes), Counter({0: 6272, 1: 6272}))
    require(all(int(row["dp_rank"]) == int(row["native_device"]) for row in processes), "process rank/device identity collapsed")
    request_ids = {row["request_id"] for row in processes}
    require_equal("measured request IDs", request_ids, {row["request_id"] for row in _read_json(R01_REQUEST_MANIFEST_PATH)["records"]})
    require_equal("measured request count", len(request_ids), 8)

    runtime_by_id = {row["runtime_call_id"]: row for row in runtimes}
    require_equal("runtime IDs unique", len(runtime_by_id), len(runtimes))
    runtime_by_native = {(row["hip_runtime_table"], row["hip_runtime_rowid"]): row for row in runtimes}
    require_equal("runtime native rows unique", len(runtime_by_native), len(runtimes))
    kernels_by_owner: Counter[str] = Counter()
    kernel_by_native = {}
    for kernel in kernels:
        owner = process_by_id.get(kernel["owner_process_range_id"])
        require(owner is not None, "kernel owner absent")
        require_equal("kernel owner canonical target", kernel["owner_canonical_target_id"], owner["canonical_target_id"])
        runtime = runtime_by_native.get((kernel["hip_runtime_table"], kernel["hip_runtime_rowid"]))
        require(runtime is not None, "kernel runtime row absent")
        require(_bool(runtime["is_kernel_launch"]), "native kernel joined to non-launch runtime")
        require_equal("kernel/runtime correlation index", int(kernel["native_device_index"]), int(runtime["hip_runtime_index"]))
        require_equal("kernel/runtime owner", runtime["owner_process_range_id"], owner["process_range_id"])
        require_equal("kernel/runtime rank", int(kernel["dp_rank"]), int(runtime["dp_rank"]))
        require_equal("kernel/runtime device", int(kernel["native_device"]), int(runtime["native_device"]))
        native_key = (kernel["native_device_table"], kernel["native_device_rowid"])
        require(native_key not in kernel_by_native, "native kernel row double counted")
        kernel_by_native[native_key] = kernel
        kernels_by_owner[owner["process_range_id"]] += 1
    launch_rows = [row for row in runtimes if _bool(row["is_kernel_launch"])]
    require_equal("launch/kernel conservation", len(launch_rows), len(kernels))
    require_equal("kernel native identity uniqueness", len(kernel_by_native), len(kernels))
    for runtime in runtimes:
        owner = process_by_id.get(runtime["owner_process_range_id"])
        require(owner is not None, "runtime owner absent")
        require_equal("runtime canonical owner", runtime["owner_canonical_target_id"], owner["canonical_target_id"])
        for key in ("config_key", "pid", "tid", "dp_rank", "native_device"):
            require_equal(f"runtime/process {key}", str(runtime[key]), str(owner[key]))
        require(int(owner["begin_ns"]) <= int(runtime["begin_ns"]) and int(runtime["end_ns"]) <= int(owner["end_ns"]), "runtime violates full time containment")
        require(int(owner["begin_runtime_index"]) <= int(runtime["hip_runtime_index"]) <= int(owner["end_runtime_index"]), "runtime violates full index containment")
        api = runtime["hip_runtime_api"]
        expected_launch = api in PROVEN_LAUNCH_APIS
        require_equal("runtime launch classification", _bool(runtime["is_kernel_launch"]), expected_launch)
        require("launch" not in api.lower() or "kernel" not in api.lower() or expected_launch, f"unsupported launch-like API: {api}")
        expected_state = "complete_one_native_HIPOPS_row" if expected_launch else "host_runtime_not_a_kernel_launch"
        require_equal("runtime correlation state", runtime["launch_correlation_state"], expected_state)

    # Independently replay the active-range selection by config/TID and require
    # the unique deepest declared owner for every exported runtime call.
    process_groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    runtime_groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in processes:
        process_groups[(row["config_key"], row["tid"])].append(row)
    for row in runtimes:
        runtime_groups[(row["config_key"], row["tid"])].append(row)
    by_range_name = {row["range_name"]: row for row in processes}
    for key, runtime_group in runtime_groups.items():
        ranges = sorted(process_groups[key], key=lambda row: (int(row["begin_ns"]), -int(row["end_ns"]), int(row["depth"])))
        calls = sorted(runtime_group, key=lambda row: (int(row["begin_ns"]), int(row["end_ns"]), int(row["hip_runtime_index"])))
        cursor = 0; active: list[dict[str, str]] = []
        for call in calls:
            begin = int(call["begin_ns"]); end = int(call["end_ns"]); index = int(call["hip_runtime_index"])
            while cursor < len(ranges) and int(ranges[cursor]["begin_ns"]) <= begin:
                active.append(ranges[cursor]); cursor += 1
            active = [row for row in active if int(row["end_ns"]) >= end]
            candidates = [row for row in active if end <= int(row["end_ns"]) and int(row["begin_runtime_index"]) <= index <= int(row["end_runtime_index"])]
            require(candidates, "independent owner candidate set empty")
            deepest = max(int(row["depth"]) for row in candidates)
            winners = [row for row in candidates if int(row["depth"]) == deepest]
            require_equal("independent unique deepest owner", len(winners), 1)
            require_equal("independent deepest owner ID", winners[0]["process_range_id"], call["owner_process_range_id"])
            winner_names = {row["range_name"] for row in candidates}
            for row in candidates:
                parent = row["parent_range_name"]
                while parent:
                    require(parent in by_range_name, "candidate ancestry parent absent")
                    parent = by_range_name[parent]["parent_range_name"]
            require(winners[0]["range_name"] in winner_names, "deepest owner chain invalid")

    for process in processes:
        owned = kernels_by_owner[process["process_range_id"]]
        require_equal("process owned kernel count", int(process["owned_kernel_count"]), owned)
        require_equal("process no-kernel state", process["ownership_state"], "strict_owned" if owned else "explicit_no_direct_kernel")
        if owned:
            require(_bool(process["strict_kernel_owner"]), "kernel owner not declared strict")
            require(not _bool(process["explicit_no_kernel_target"]), "kernel assigned to explicit no-kernel target")
        else:
            require(_bool(process["explicit_no_kernel_target"]), "hidden no-kernel target")
    require_equal("queue/kernel rows", queues, kernels)
    expected_busy = _independent_busy_union(kernels)
    observed_busy = [{
        "busy_interval_id": row["busy_interval_id"], "dp_rank": int(row["dp_rank"]),
        "native_device": int(row["native_device"]), "begin_ns": int(row["begin_ns"]),
        "end_ns": int(row["end_ns"]), "duration_ns": int(row["duration_ns"]),
    } for row in busy]
    require_equal("independent busy union", observed_busy, expected_busy)
    summary = _read_json(PROCESS_SUMMARY_PATH)
    _validate_identity(summary, "process summary")
    require_equal("summary process count", summary["counts"]["process_ranges"], len(processes))
    require_equal("summary runtime count", summary["counts"]["hip_runtime_calls"], len(runtimes))
    require_equal("summary kernel count", summary["counts"]["strict_owned_kernels"], len(kernels))
    require_equal("summary database seal", summary["raw_database_sha256"], raw_audit["database_sha256"])
    require(summary["trace_counter_semantics"]["is_pmc_evidence"] is False, "trace metadata promoted to PMC")
    marker = _read_json(VALIDATION_ROOT / "marker_transport_audit.json")
    ownership = _read_json(VALIDATION_ROOT / "strict_ownership_audit.json")
    coverage = _read_json(VALIDATION_ROOT / "rank_device_coverage.json")
    require_equal("marker target count", marker["observed_process_target_count"], 12544)
    require_equal(
        "marker transport hash",
        marker["ordered_process_marker_bytes_sha256"],
        bound_sidecar["ordered_exact_name_multiset_length_prefixed_sha256"],
    )
    require_equal("ownership ambiguity", ownership["ambiguous_owner_count"], 0)
    require_equal("ownership double count", ownership["parent_fragment_double_count"], 0)
    require(coverage["coverage_target_met"] is True, "rank/device target coverage incomplete")
    return {
        "status": "complete",
        "request_range_count": len(request_rows), "forward_range_count": len(forward_rows),
        "layer_range_count": len(layer_rows), "process_range_count": len(processes),
        "runtime_call_count": len(runtimes), "true_kernel_launch_count": len(launch_rows),
        "strict_owned_kernel_count": len(kernels),
        "explicit_no_direct_kernel_count": sum(not kernels_by_owner[row["process_range_id"]] for row in processes),
        "busy_union_interval_count": len(busy), "measured_request_count": len(request_ids),
        "rank_coverage": [0, 1], "native_device_coverage": [0, 1],
        "rank_to_physical_device": {"0": 0, "1": 1},
        "target_count": len(layer_rows) + len(processes),
        "coverage_target_met": True, "ambiguous_owner_count": 0,
        "parent_fragment_double_count": 0, "runtime_launch_correlation_fraction": 1.0,
        "full_time_and_runtime_index_containment": True,
        "busy_union_independently_recomputed": True,
        "bound_target_sidecar_sha256": sha256_path(R07_BOUND_TARGET_SIDECAR_PATH),
        "bound_request_phase_coverage_fraction": 1.0,
        "bound_marker_coverage_fraction": 1.0,
    }


def _audit_live_utilization() -> dict[str, Any]:
    anchors = _read_json(ANCHOR_PATH)
    process_source_sha256 = sha256_path(PROCESS_PATH)
    raw_sample_source_sha256 = sha256_path(RAW_SAMPLE_PATH)
    raw_gap_source_sha256 = sha256_path(RAW_GAP_PATH)
    anchor_source_sha256 = sha256_path(ANCHOR_PATH)
    require_equal("collector anchor status", anchors["status"], "complete")
    require_equal("raw sample seal", anchors["raw_samples_sha256"], raw_sample_source_sha256)
    require_equal("raw gap seal", anchors["raw_gap_intervals_sha256"], raw_gap_source_sha256)
    raw_samples = _read_csv(RAW_SAMPLE_PATH)
    raw_gaps = _read_csv(RAW_GAP_PATH)
    aligned = _read_csv(ALIGNED_SAMPLE_PATH)
    gaps = _read_csv(GAP_ALIGNMENT_PATH)
    process_alignments = _read_csv(PROCESS_ALIGNMENT_PATH)
    processes = _read_csv(PROCESS_PATH)
    require_equal("raw sample count", len(raw_samples), int(anchors["sample_count"]))
    require_equal("raw gap count", len(raw_gaps), int(anchors["gap_interval_count"]))
    require_equal("aligned sample conservation", len(aligned), len(raw_samples))
    require_equal("aligned gap conservation", len(gaps), len(raw_gaps))
    require_equal("process alignment conservation", len(process_alignments), len(processes))
    require_equal("process alignment IDs", {row["process_range_id"] for row in process_alignments}, {row["process_range_id"] for row in processes})
    require_equal("sample sequences", {int(row["sequence"]) for row in raw_samples}, set(range(1, len(raw_samples) + 1)))
    require_equal("aligned sample sequences", {int(row["sequence"]) for row in aligned}, set(range(1, len(raw_samples) + 1)))
    raw_by_sequence = {int(row["sequence"]): row for row in raw_samples}
    samples_by_device: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in aligned:
        sequence = int(row["sequence"]); raw = raw_by_sequence[sequence]
        for key in (
            "runtime_run_id", "runtime_attempt_id", "lineage_id", "dp_rank", "native_device",
            "call_begin_monotonic_ns", "call_end_monotonic_ns", "call_begin_realtime_ns",
            "call_end_realtime_ns", "call_latency_ns", "se_active_cu_pct", "alignment_uncertainty_ns",
            "rsmi_status",
        ):
            require_equal(f"lossless aligned sample {sequence} {key}", str(row[key]), str(raw[key]))
        device = int(row["native_device"]); rank = int(row["dp_rank"])
        require_equal("sample rank/device map", rank, device)
        require(device in {0, 1}, "sample device outside DP2")
        require_equal("sample status", int(row["rsmi_status"]), 0)
        value = int(row["se_active_cu_pct"])
        require(0 <= value <= 100, "utilization value outside [0,100]")
        begin = int(row["call_begin_monotonic_ns"]); end = int(row["call_end_monotonic_ns"])
        begin_real = int(row["call_begin_realtime_ns"]); end_real = int(row["call_end_realtime_ns"])
        require_equal("sample monotonic midpoint", int(row["sample_midpoint_monotonic_ns"]), (begin + end) // 2)
        require_equal("sample realtime midpoint", int(row["sample_midpoint_realtime_ns"]), (begin_real + end_real) // 2)
        eligible = int(row["alignment_uncertainty_ns"]) <= 1_000_000
        require_equal("sample eligibility", _bool(row["timing_eligible"]), eligible)
        require_equal("sample availability", row["sample_availability_state"], "available_sample" if eligible else "unavailable_alignment_error")
        samples_by_device[device].append({**row, "timing_eligible_bool": eligible})
    require_equal("sample device coverage", sorted(samples_by_device), [0, 1])
    for rows in samples_by_device.values():
        rows.sort(key=lambda row: (int(row["sample_midpoint_monotonic_ns"]), int(row["sequence"])))
    positions = {device: [int(row["sample_midpoint_monotonic_ns"]) for row in rows] for device, rows in samples_by_device.items()}

    expected_gap_rows = []
    raw_gap_by_key = {}
    for row in raw_gaps:
        key = (int(row["native_device"]), int(row["previous_sequence"]), int(row["next_sequence"]))
        require(key not in raw_gap_by_key, "duplicate raw gap identity")
        raw_gap_by_key[key] = row
    for row in gaps:
        key = (int(row["native_device"]), int(row["previous_sequence"]), int(row["next_sequence"]))
        raw = raw_gap_by_key.get(key)
        require(raw is not None, "aligned gap lacks raw gap")
        for field in (
            "runtime_run_id", "runtime_attempt_id", "lineage_id", "dp_rank", "native_device",
            "previous_sequence", "next_sequence", "gap_begin_monotonic_ns", "gap_end_monotonic_ns",
            "unobserved_gap_ns", "adjacent_sample_begin_delta_ns", "gap_threshold_ns",
        ):
            require_equal(f"lossless gap {key} {field}", str(row[field]), str(raw[field]))
        require_equal("gap source hash", row["source_raw_gap_intervals_sha256"], raw_gap_source_sha256)
        require_equal("gap evidence class", row["evidence_class"], "observed_r07_live_utilization")
        expected_gap_rows.append(row)
    require_equal("raw/aligned gap key set", {key for key in raw_gap_by_key}, {
        (int(row["native_device"]), int(row["previous_sequence"]), int(row["next_sequence"])) for row in gaps
    })
    gaps_by_device: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in gaps:
        gaps_by_device[int(row["native_device"])].append(row)

    process_by_id = {row["process_range_id"]: row for row in processes}
    states: Counter[str] = Counter()
    for output in process_alignments:
        process = process_by_id[output["process_range_id"]]
        device = int(process["native_device"])
        require_equal("alignment process device", int(output["native_device"]), device)
        require_equal("alignment process rank", int(output["dp_rank"]), int(process["dp_rank"]))
        begin = int(process["sidecar_start_monotonic_ns"]); end = int(process["sidecar_end_monotonic_ns"])
        rows = samples_by_device[device]
        left = bisect.bisect_left(positions[device], begin)
        right = bisect.bisect_right(positions[device], end)
        inside = rows[left:right]
        eligible = [row for row in inside if row["timing_eligible_bool"]]
        overlimit = [row for row in inside if not row["timing_eligible_bool"]]
        intersecting = [
            row for row in gaps_by_device.get(device, [])
            if int(row["gap_begin_monotonic_ns"]) < end and begin < int(row["gap_end_monotonic_ns"])
        ]
        sidecar_uncertainty = int(process["sidecar_alignment_uncertainty_ns"])
        if sidecar_uncertainty > 1_000_000:
            expected_state = "unavailable_alignment_error"; expected_value = ""
        elif intersecting:
            expected_state = "unavailable_sampling_gap"; expected_value = ""
        elif len(eligible) >= 3:
            expected_state = "available"
            expected_value = f"{sum(int(row['se_active_cu_pct']) for row in eligible) / len(eligible):.9f}"
        elif overlimit:
            expected_state = "unavailable_alignment_error"; expected_value = ""
        else:
            expected_state = "unavailable_intrinsic_short_window"; expected_value = ""
        require_equal("process sample count", int(output["real_sample_count_inside"]), len(inside))
        require_equal("process eligible count", int(output["timing_eligible_sample_count"]), len(eligible))
        require_equal("process alignment error count", int(output["alignment_error_sample_count"]), len(overlimit))
        require_equal("process intersecting gap count", int(output["intersecting_gap_count"]), len(intersecting))
        require_equal("process availability state", output["availability_state"], expected_state)
        require_equal("process utilization value", output["se_active_cu_pct_mean"], expected_value)
        require_equal("process source hash", output["source_process_ranges_sha256"], process_source_sha256)
        require_equal("sample source hash", output["source_raw_samples_sha256"], raw_sample_source_sha256)
        require_equal("gap source hash", output["source_raw_gap_intervals_sha256"], raw_gap_source_sha256)
        require_equal("anchor source hash", output["source_clock_anchors_sha256"], anchor_source_sha256)
        states[expected_state] += 1
    summary = _read_json(LIVE_SUMMARY_PATH)
    _validate_identity(summary, "live utilization summary")
    require_equal("live summary raw samples", summary["raw_sample_count"], len(raw_samples))
    require_equal("live summary aligned samples", summary["aligned_sample_count"], len(aligned))
    require_equal("live summary raw gaps", summary["raw_gap_interval_count"], len(raw_gaps))
    require_equal("live summary process denominator", summary["process_denominator"], len(processes))
    require_equal("live summary states", summary["availability_counts"], dict(sorted(states.items())))
    for key in ("interpolation_performed", "resampling_performed", "imputation_performed", "zero_fill_performed"):
        require(summary[key] is False, f"forbidden live-utilization operation: {key}")
    lossless = _read_json(VALIDATION_ROOT / "live_utilization_losslessness_audit.json")
    require_equal("lossless audit status", lossless["status"], "complete")
    require(lossless["no_interpolation_resampling_imputation_or_zero_fill"] is True, "losslessness audit failed")
    return {
        "status": "complete", "raw_sample_count": len(raw_samples),
        "raw_gap_interval_count": len(raw_gaps), "aligned_sample_count": len(aligned),
        "process_denominator": len(processes), "availability_counts": dict(sorted(states.items())),
        "available_process_count": states.get("available", 0),
        "unavailable_process_count": len(processes) - states.get("available", 0),
        "rank_coverage": [0, 1], "native_device_coverage": [0, 1],
        "all_real_samples_preserved": True, "all_gaps_preserved": True,
        "no_interpolation_resampling_imputation_or_zero_fill": True,
    }


def _audit_dependency() -> dict[str, Any]:
    document = _read_json(DEPENDENCY_PATH)
    _validate_identity(document, "dependency adapter")
    rows = _read_csv(DEPENDENCY_CSV_PATH)
    require_equal("dependency JSON/CSV edge count", document["edge_count"], len(rows))
    require_equal("dependency embedded rows", document["rows"], [
        {key: (
            int(value) if key in {"layer_idx", "layer_occurrence", "dp_rank", "native_device"} and value != ""
            else _bool(value) if key == "external_runtime_evidence_consumed"
            else value
        )
         for key, value in row.items()} for row in rows
    ])
    require_equal("dependency target count", document["target_count"], EXPECTED["process_target_count"])
    require_equal("dependency rank coverage", document["rank_coverage"], [0, 1])
    require_equal("dependency device coverage", document["native_device_coverage"], [0, 1])
    require(document["audit"]["every_current_target_preserved"] is True, "dependency target coverage false")
    require(document["audit"]["kernel_edge_conservation"] is True, "dependency kernel conservation false")
    require(document["audit"]["external_runtime_evidence_consumed"] is False, "dependency imported external evidence")
    require(document["audit"]["replay_duration_consumed"] is False, "dependency imported replay duration")
    targets = Counter(row["canonical_target_id"] for row in rows)
    require_equal("dependency target identities", set(targets), {row["canonical_target_id"] for row in _read_csv(PROCESS_PATH)})
    require(all(count >= 1 for count in targets.values()), "dependency lost a target")
    states = Counter(row["dependency_state"] for row in rows)
    require(set(states).issubset({"observed", "deterministically_derived", "unavailable", "unknown"}), "unknown dependency state")
    kernel_edges = [row for row in rows if row["dependency_state"] == "observed"]
    require_equal("dependency kernel edge count", len(kernel_edges), len(_read_csv(KERNEL_PATH)))
    process_sha = sha256_path(PROCESS_PATH); runtime_sha = sha256_path(RUNTIME_PATH)
    kernel_sha = sha256_path(KERNEL_PATH); alignment_sha = sha256_path(PROCESS_ALIGNMENT_PATH)
    for row in rows:
        require_equal("dependency process source", row["source_process_ranges_sha256"], process_sha)
        require_equal("dependency runtime source", row["source_runtime_calls_sha256"], runtime_sha)
        require_equal("dependency kernel source", row["source_strict_owned_kernels_sha256"], kernel_sha)
        require_equal("dependency alignment source", row["source_process_alignment_sha256"], alignment_sha)
        require_equal("dependency R06 source", row["source_r06_targets_sha256"], EXPECTED["r06_targets_sha256"])
        require_equal("dependency R03 identity", row["source_r03_identity_context_sha256"], HANDOFF_HASHES["R03"])
        require(not _bool(row["external_runtime_evidence_consumed"]), "dependency row uses external evidence")
    return {
        "status": "complete", "edge_count": len(rows), "target_count": len(targets),
        "kernel_edge_count": len(kernel_edges), "dependency_state_counts": dict(sorted(states.items())),
        "rank_coverage": [0, 1], "native_device_coverage": [0, 1],
        "every_current_target_preserved": True, "kernel_edge_conservation": True,
        "external_runtime_evidence_consumed": False,
    }


def _logical_output(path: Path, evidence_class: str) -> dict[str, Any]:
    document = _read_json(path)
    _validate_identity(document, path.name)
    require_equal(f"{path.name} profile", document.get("trace_profile_sha256"), EXPECTED["profile_sha256"])
    return {
        "path": str(path), "relative_path": path.relative_to(ARTIFACT_ROOT).as_posix(),
        "size": path.stat().st_size, "sha256": sha256_path(path),
        "schema_version": document["schema_version"], "status": document["status"],
        "runtime_run_id": RUN_ID, "runtime_attempt_id": ATTEMPT_ID,
        "lineage_id": LINEAGE_ID, "trace_profile_sha256": EXPECTED["profile_sha256"],
        "rank_coverage": document.get("rank_coverage", [0, 1]),
        "native_device_coverage": document.get("native_device_coverage", [0, 1]),
        "evidence_class": document.get("evidence_class", evidence_class),
    }


def _write_source_lineage(
    source_audit: dict[str, Any], raw_audit: dict[str, Any], trace_audit: dict[str, Any],
    live_audit: dict[str, Any], dependency_audit: dict[str, Any], aot_audit: dict[str, Any],
    durable_audit: dict[str, Any],
) -> dict[str, Any]:
    resolved = _read_json(RESOLVED_CONTRACT_PATH)
    retry = _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")
    outputs = {
        "full_request_profile_metadata": _logical_output(PROFILE_METADATA_PATH, "observed_r07_timing"),
        "process_trace_summary": _logical_output(PROCESS_SUMMARY_PATH, "derived_from_observed_r07"),
        "fresh_run_dependency_adapter": _logical_output(DEPENDENCY_PATH, "derived_from_observed_r07"),
        "live_utilization_summary": _logical_output(LIVE_SUMMARY_PATH, "derived_from_observed_r07"),
    }
    document = {
        "schema_version": 1,
        "status": "complete",
        "runtime_branch": BRANCH,
        "runtime_goal": "R07",
        "runtime_run_id": RUN_ID,
        "runtime_attempt_id": ATTEMPT_ID,
        "lineage_id": LINEAGE_ID,
        "trace_profile_sha256": EXPECTED["profile_sha256"],
        "cumulative_runtime_ledger_path": str(LEDGER_PATH),
        "cumulative_runtime_ledger_sha256": EXPECTED["ledger_sha256"],
        "runtime_predecessors": ["R01", "R02", "R03", "R04", "R05", "R06"],
        "direct_handoffs": source_audit["direct_handoffs"],
        "predecessor_artifact_manifests": resolved["predecessor_artifact_manifests"],
        "consumed_business_inputs": resolved["consumed_business_inputs"],
        "selected_request_manifest": {
            "path": str(R01_REQUEST_MANIFEST_PATH),
            "r01_request_manifest_file_byte_sha256": EXPECTED["r01_request_manifest_file_byte_sha256"],
            "r01_request_manifest_canonical_json_sha256": EXPECTED["r01_request_manifest_canonical_json_sha256"],
            "ordered_sequence_canonical_sha256": EXPECTED["request_sequence_sha256"],
            "cross_representation_digest_equality_compared": False,
        },
        "target": {
            "root": str(TARGET_ROOT), "git_commit": EXPECTED["target_commit"],
            "git_branch": "repro-gqa-page784-k5120-batch8-final", "clean": True,
            "source_files": source_audit["source_files"],
        },
        "runtime_contract": {
            "model_directory": "/home/Qwen3.5-27B", "runtime_executable": "/usr/local/bin/vllm",
            "service_port": 8001, "workload": TRACE_PROFILE_ATTESTATION["workload"],
            "topology": TRACE_PROFILE_ATTESTATION["topology"],
        },
        "current_attempt_observed_sources": {
            "raw_inventory_path": str(RAW_INVENTORY_PATH),
            "raw_inventory_sha256": raw_audit["inventory_sha256"],
            "raw_database_sha256": raw_audit["database_sha256"],
            "raw_samples_sha256": sha256_path(RAW_SAMPLE_PATH),
            "raw_gap_intervals_sha256": sha256_path(RAW_GAP_PATH),
            "clock_anchors_sha256": sha256_path(ANCHOR_PATH),
            "bound_target_sidecar_sha256": sha256_path(R07_BOUND_TARGET_SIDECAR_PATH),
            "prepostprocess_native_capture_seal_sha256": sha256_path(
                PREPOSTPROCESS_NATIVE_SEAL_PATH
            ),
            "capture_db_checkpoint_invocation_sha256": sha256_path(
                DB_CHECKPOINT_INVOCATION_PATH
            ),
            "capture_db_checkpoint_marker_sha256": durable_audit[
                "capture_db_checkpoint_marker"
            ]["sha256"],
            "offline_pftrace_export_invocation_sha256": sha256_path(
                OFFLINE_EXPORT_INVOCATION_PATH
            ),
            "durable_copy_manifest_sha256": durable_audit["manifest"]["sha256"],
            "durable_completion_marker_sha256": durable_audit["completion_marker"]["sha256"],
            "durable_surface_canonical_sha256": durable_audit["surface_canonical_sha256"],
        },
        "current_attempt_derived_sources": {
            "process_ranges_sha256": sha256_path(PROCESS_PATH),
            "runtime_calls_sha256": sha256_path(RUNTIME_PATH),
            "strict_owned_kernels_sha256": sha256_path(KERNEL_PATH),
            "process_alignment_sha256": sha256_path(PROCESS_ALIGNMENT_PATH),
            "dependency_adapter_csv_sha256": sha256_path(DEPENDENCY_CSV_PATH),
        },
        "same_run_compilation_dependency": aot_audit,
        "coverage": trace_audit,
        "live_utilization_accounting": live_audit,
        "dependency_conservation": dependency_audit,
        "required_logical_outputs_excluding_this_self_describing_record": outputs,
        "source_immutability_path": str(SOURCE_IMMUTABILITY_PATH),
        "source_immutability_sha256": sha256_path(SOURCE_IMMUTABILITY_PATH),
        "stage_source_delta_path": str(SOURCE_DELTA_PATH),
        "stage_source_delta_sha256": sha256_path(SOURCE_DELTA_PATH),
        "retry_authorization_path": str(ARTIFACT_ROOT / "authorization/retry_authorization.json"),
        "retry_authorization_sha256": EXPECTED["retry_authorization_sha256"],
        "monitor_advisory_path": str(ARTIFACT_ROOT / "authorization/monitor_advisory.json"),
        "monitor_advisory_sha256": EXPECTED["monitor_advisory_sha256"],
        "bulk_storage_authorization_path": str(BULK_AUTH_PATH),
        "bulk_storage_authorization_sha256": EXPECTED["bulk_storage_authorization_sha256"],
        "r07_control_plane_binding_sha256": EXPECTED["control_plane_binding_sha256"],
        "marker_denominator_recovery": retry["marker_denominator_recovery"],
        "postdevice_preworkload_recovery": retry["postdevice_preworkload_recovery"],
        "service_gate_recovery": retry["service_gate_recovery"],
        "admission_schema_recovery": retry["admission_schema_recovery"],
        "bulk_preparation_recovery": retry["bulk_preparation_recovery"],
        "bulk_identity_schema_recovery": retry["bulk_identity_schema_recovery"],
        "socket_fixture_recovery": retry["socket_fixture_recovery"],
        "service_validation_path_recovery": retry["service_validation_path_recovery"],
        "request_manifest_hash_recovery": retry["request_manifest_hash_recovery"],
        "postmeasurement_storage_recovery": retry["postmeasurement_storage_recovery"],
        "predecessor_storage_relocation": retry["predecessor_storage_relocation"],
        "worker_rebuild_recovery": retry["worker_rebuild_recovery"],
        "runtime_patch_path_recovery": retry["runtime_patch_path_recovery"],
        "bulk_input_binding_recovery": retry["bulk_input_binding_recovery"],
        "runtime_patch_fixture_recovery": retry["runtime_patch_fixture_recovery"],
        "attempt024_schema_nfs_recovery": retry["attempt024_schema_nfs_recovery"],
        "attempt025_dynamic_capacity_recovery": retry[
            "attempt025_dynamic_capacity_recovery"
        ],
        "attempt026_abi_runtime_recovery": retry[
            "attempt026_abi_runtime_recovery"
        ],
        "attempt026_abi_runtime_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt026_abi_runtime_recovery_audit"],
        "attempt027_historical_identity_recovery": retry[
            "attempt027_historical_identity_recovery"
        ],
        "attempt027_historical_identity_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt027_historical_identity_recovery_audit"],
        "attempt028_bytecode_surface_recovery": retry[
            "attempt028_bytecode_surface_recovery"
        ],
        "attempt028_bytecode_surface_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt028_bytecode_surface_recovery_audit"],
        "attempt029_bytecode_empty_set_recovery": retry[
            "attempt029_bytecode_empty_set_recovery"
        ],
        "attempt029_bytecode_empty_set_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt029_bytecode_empty_set_recovery_audit"],
        "attempt030_sidecar_fixture_recovery": retry[
            "attempt030_sidecar_fixture_recovery"
        ],
        "attempt030_sidecar_fixture_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt030_sidecar_fixture_recovery_audit"],
        "attempt031_prior_attempt_count_recovery": retry[
            "attempt031_prior_attempt_count_recovery"
        ],
        "attempt031_prior_attempt_count_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt031_prior_attempt_count_recovery_audit"],
        "attempt036_preformal_ordinal_binding_recovery": retry[
            "attempt036_preformal_ordinal_binding_recovery"
        ],
        "attempt037_preformal_historical_validator_ordinal_recovery": retry[
            "attempt037_preformal_historical_validator_ordinal_recovery"
        ],
        "attempt038_preformal_field_value_identity_recovery": retry[
            "attempt038_preformal_field_value_identity_recovery"
        ],
        "attempt038_preformal_field_value_identity_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt038_preformal_field_value_identity_recovery_audit"],
        "attempt039_predevice_bulk_helper_identity_recovery": _read_json(
            ARTIFACT_ROOT / "authorization/retry_authorization.json"
        )["attempt039_predevice_bulk_helper_identity_recovery"],
        "attempt039_predevice_bulk_helper_identity_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt039_predevice_bulk_helper_identity_recovery_audit"],
        "attempt040_predevice_historical_successor_role_recovery": _read_json(
            ARTIFACT_ROOT / "authorization/retry_authorization.json"
        )["attempt040_predevice_historical_successor_role_recovery"],
        "attempt040_predevice_historical_successor_role_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt040_predevice_historical_successor_role_recovery_audit"],
        "attempt041_predevice_tool_freeze_dependency_recovery": _read_json(
            ARTIFACT_ROOT / "authorization/retry_authorization.json"
        )["attempt041_predevice_tool_freeze_dependency_recovery"],
        "attempt041_predevice_tool_freeze_dependency_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt041_predevice_tool_freeze_dependency_recovery_audit"],
        "attempt042_predevice_admission_reference_key_recovery": _read_json(
            ARTIFACT_ROOT / "authorization/retry_authorization.json"
        )["attempt042_predevice_admission_reference_key_recovery"],
        "attempt042_predevice_admission_reference_key_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt042_predevice_admission_reference_key_recovery_audit"],
        "preproduction_cross_helper_recovery_identity_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["preproduction_cross_helper_recovery_identity_audit"],
        "preproduction_recovery_identity_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["preproduction_recovery_identity_audit"],
        "post_attempt031_worker_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["post_attempt031_worker_recovery_audit"],
        "capture_db_checkpoint_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["capture_db_checkpoint_audit"],
        "durable_nfs_storage": _read_json(BULK_AUTH_PATH)["durable_nfs_storage"],
        "durable_copy_audit": durable_audit,
        "bulk_storage_required_audits": _read_json(BULK_AUTH_PATH)["required_audits"],
        "bulk_storage_required_audits_sha256": EXPECTED["bulk_storage_required_audits_sha256"],
        "method_template_scope": "scheduler-signed recovery-authorized prior tool sources only; no prior runtime bytes",
        "prior_attempt_runtime_bytes_consumed": False,
        "external_runtime_ledger_consumed": False,
        "external_runtime_evidence_consumed": False,
        "fresh_non_replay_current_attempt_capture_only": True,
        "evidence_class": "derived_from_observed_r07",
    }
    write_json_x(SOURCE_LINEAGE_PATH, document)
    return document


def _producer_for(relative: str, frozen_hashes: dict[str, str]) -> str:
    if relative.startswith("quarantine/pre_freeze_python_bytecode/"):
        return sha256_path(QUARANTINE_RECORD_PATH)
    if relative.startswith("tools/"):
        return frozen_hashes[relative]
    if relative.startswith("trace/") or relative in {
        "capture/raw_inventory.json", "capture/full_request_profile_metadata.json",
        "validation/marker_transport_audit.json", "validation/strict_ownership_audit.json",
        "validation/rank_device_coverage.json",
    }:
        return frozen_hashes["tools/normalize_r07_process_trace.py"]
    if relative.startswith("alignment/") or relative == "validation/live_utilization_losslessness_audit.json":
        return frozen_hashes["tools/align_r07_live_utilization.py"]
    if relative.startswith("dependency/"):
        return frozen_hashes["tools/build_r07_dependency_adapter.py"]
    if relative.startswith("live_utilization/"):
        return frozen_hashes["tools/collect_r07_live_utilization.py"]
    if relative == "capture/control/post_capture_process_verification.json":
        return frozen_hashes["tools/r07_workload_driver.py"]
    if relative.startswith("capture/") or relative in {
        "validation/predevice_gate_report.json", "validation/formal_device_preflight.json",
    }:
        return frozen_hashes["tools/run_r07_full_request.py"]
    if relative.startswith("lineage/") or relative in {
        "validation/source_immutability.json", "validation/r07_completion_audit.json",
    }:
        return frozen_hashes["tools/audit_r07_capture.py"]
    if relative.startswith("authorization/"):
        return EXPECTED["control_plane_binding_sha256"]
    if relative == "validation/pre_bulk_production_selector_regression.json":
        return frozen_hashes["tools/build_r07_capture_contract.py"]
    if relative in {"contract/resolved_input_contract.json", "contract/r01_r02_r03_r04_r05_r06_predecessor_validation.json"}:
        return frozen_hashes["tools/build_r07_capture_contract.py"]
    if relative == "contract/r01_aot_cache_copy_manifest.json":
        return frozen_hashes["tools/prepare_r07_bulk_storage.py"]
    if relative == "contract/r07_bound_target_sidecar.json":
        return frozen_hashes["tools/run_r07_full_request.py"]
    if relative.startswith("contract/r07_full_request_") or relative == "contract/r07_process_range_inventory.json":
        return frozen_hashes["tools/materialize_r07_runtime_contracts.py"]
    return frozen_hashes["tools/freeze_r07_tools.py"]


def _evidence_class(relative: str) -> str:
    if relative.startswith("live_utilization/") or relative.startswith("capture/control/live_collector"):
        return "observed_r07_live_utilization"
    if relative.startswith("capture/raw") or relative in {
        "contract/r07_bound_target_sidecar.json",
        "capture/lifecycle.json", "capture/prepostprocess_native_capture_seal.json",
        "capture/workload/driver.json", "capture/workload/request_results.json",
        "capture/workload/warmup_results.json", "trace/request_ranges.csv", "trace/forward_ranges.csv",
        "trace/layer_ranges.csv", "trace/process_ranges.csv", "trace/hip_runtime_calls.csv",
        "trace/strict_owned_kernels.csv", "trace/queue_stream_timeline.csv",
    } or relative.startswith("capture/workload/runtime_bindings/"):
        return "observed_r07_timing"
    if relative.startswith("trace/") or relative.startswith("alignment/") or relative.startswith("dependency/") or relative.startswith("lineage/"):
        return "derived_from_observed_r07"
    return "diagnostic_only"


def _write_artifact_manifest(raw_audit: dict[str, Any]) -> dict[str, Any]:
    frozen = validate_frozen_tools()
    frozen_hashes = {row["relative_path"]: row["sha256"] for row in frozen["files"]}
    missing = sorted(
        relative for relative in REQUIRED_BUSINESS_ARTIFACTS
        if relative != "manifests/artifact_manifest.json" and not (ARTIFACT_ROOT / relative).is_file()
    )
    require_equal("required business artifacts before manifest", missing, [])
    require(not ARTIFACT_MANIFEST_PATH.exists(), "artifact manifest already exists")
    entries = []
    for path in sorted(ARTIFACT_ROOT.rglob("*"), key=lambda value: value.relative_to(ARTIFACT_ROOT).as_posix()):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or stat.S_ISDIR(mode):
            continue
        relative = path.relative_to(ARTIFACT_ROOT).as_posix()
        if relative == "cache" or relative.startswith("cache/") or relative.startswith("capture/raw/") or relative.startswith("capture/hipprof_tmp/"):
            continue
        require(relative != "manifests/artifact_manifest.json", "manifest self appeared before creation")
        if "__pycache__" in Path(relative).parts or relative.endswith(".pyc"):
            raise RuntimeError(f"forbidden current-attempt bytecode artifact: {relative}")
        if not stat.S_ISREG(mode):
            nonregular_row = {
                "relative_path": relative,
                "size": path.lstat().st_size,
                "sha256": None,
                "object_kind": (
                    "unix_domain_socket" if stat.S_ISSOCK(mode)
                    else "fifo" if stat.S_ISFIFO(mode)
                    else "character_device" if stat.S_ISCHR(mode)
                    else "block_device" if stat.S_ISBLK(mode)
                    else "unknown_nonregular"
                ),
                "mode": mode,
                "filesystem_device": path.lstat().st_dev,
                "inode": path.lstat().st_ino,
                "regular_content_sha256_present": False,
                "no_regular_byte_stream_reason": "nonregular_object_has_no_regular_content_byte_stream",
                "producer_sha256": frozen_hashes["tools/freeze_r07_tools.py"],
                "input_hashes": {
                    "trace_profile_sha256": EXPECTED["profile_sha256"],
                    "frozen_tool_manifest_sha256": sha256_path(tool_manifest_path()),
                },
                "runtime_run_id": RUN_ID, "runtime_attempt_id": ATTEMPT_ID,
                "lineage_id": LINEAGE_ID, "trace_profile_sha256": EXPECTED["profile_sha256"],
                "rank_coverage": [0, 1], "native_device_coverage": [0, 1],
                "evidence_class": "diagnostic_only", "storage_class": "runtime_artifact_root",
                "preserved_without_deletion": True, "validation_state": "complete",
            }
            if path == PREFREEZE_FIXTURE_SOCKET:
                storage_lstat = _lstat_record(
                    PREFREEZE_FIXTURE_SOCKET,
                    PREFREEZE_FIXTURE_SOCKET.relative_to(PREFREEZE_FIXTURE_ROOT).as_posix(),
                )
                entrypoint_lstat = _lstat_record(
                    PREFREEZE_FIXTURE_SOCKET_ENTRYPOINT,
                    PREFREEZE_FIXTURE_SOCKET_ENTRYPOINT.relative_to(PREFREEZE_FIXTURE_ROOT).as_posix(),
                )
                require_equal("fixture socket dual-path lstat", storage_lstat | {"relative_path": None}, entrypoint_lstat | {"relative_path": None})
                nonregular_row.update({
                    "dual_path_lstat_required": True,
                    "storage_lstat": storage_lstat,
                    "attempt_lstat": entrypoint_lstat,
                    "attempt_and_storage_lstat_identity_equal": True,
                    "socket_content_hash_performed": False,
                })
            entries.append(nonregular_row)
            continue
        entries.append({
            "relative_path": relative, "size": path.stat().st_size, "sha256": sha256_path(path),
            "producer_sha256": _producer_for(relative, frozen_hashes),
            "input_hashes": {
                "trace_profile_sha256": EXPECTED["profile_sha256"],
                "cumulative_runtime_ledger_sha256": EXPECTED["ledger_sha256"],
                "frozen_tool_manifest_sha256": sha256_path(tool_manifest_path()),
            },
            "runtime_run_id": RUN_ID, "runtime_attempt_id": ATTEMPT_ID,
            "lineage_id": LINEAGE_ID, "trace_profile_sha256": EXPECTED["profile_sha256"],
            "rank_coverage": [0, 1], "native_device_coverage": [0, 1],
            "evidence_class": _evidence_class(relative), "storage_class": "runtime_artifact_root",
            "validation_state": "complete",
        })
    symlink_specs: dict[Path, Path] = {
        PREFREEZE_FIXTURE_ENTRYPOINT: PREFREEZE_FIXTURE_STORAGE,
        BULK_ENTRYPOINTS["hipprof_tmp"]: BULK_PATHS["hipprof_tmp"],
        BULK_ENTRYPOINTS["raw"]: BULK_PATHS["raw"],
    }
    approved_external_symlinks = {
        BULK_ENTRYPOINTS["aot_cache"],
        BULK_ENTRYPOINTS["hipprof_tmp"],
        BULK_ENTRYPOINTS["raw"],
    }
    for link_path in sorted(
        (
            path
            for path in ARTIFACT_ROOT.rglob("*")
            if path.is_symlink() and path != BULK_ENTRYPOINTS["aot_cache"]
        ),
        key=lambda path: path.relative_to(ARTIFACT_ROOT).as_posix(),
    ):
        if link_path not in symlink_specs:
            link_text = os.readlink(link_path)
            immediate_target = Path(link_text)
            if not immediate_target.is_absolute():
                immediate_target = link_path.parent / immediate_target
            require(
                immediate_target.resolve(strict=True).is_relative_to(
                    ARTIFACT_ROOT.resolve(strict=True)
                ),
                f"unapproved artifact symlink escape: {link_path}",
            )
            symlink_specs[link_path] = immediate_target
    require_equal(
        "all artifact symlinks classified",
        {
            path
            for path in ARTIFACT_ROOT.rglob("*")
            if path.is_symlink()
        },
        set(symlink_specs) | {BULK_ENTRYPOINTS["aot_cache"]},
    )
    for external_link in approved_external_symlinks:
        require_equal(
            f"authorized external symlink exact target {external_link}",
            os.readlink(external_link),
            str(
                BULK_PATHS[
                    next(
                        name
                        for name, entrypoint in BULK_ENTRYPOINTS.items()
                        if entrypoint == external_link
                    )
                ]
            ),
        )
    for link_path, expected_target in symlink_specs.items():
        relative = link_path.relative_to(ARTIFACT_ROOT).as_posix()
        link_lstat = _lstat_record(link_path, relative)
        require_equal(f"manifest symlink type {relative}", link_lstat["object_kind"], "symbolic_link")
        require_equal(f"manifest symlink target {relative}", os.readlink(link_path), str(expected_target))
        require_equal(f"manifest symlink resolved target {relative}", link_path.resolve(), expected_target.resolve())
        entries.append({
            "relative_path": relative,
            "size": link_lstat["size"],
            "sha256": None,
            "object_kind": "symbolic_link",
            "mode": link_lstat["mode"],
            "filesystem_device": link_lstat["filesystem_device"],
            "inode": link_lstat["inode"],
            "lstat": link_lstat,
            "symlink_target": str(expected_target),
            "resolved_target": str(expected_target.resolve()),
            "exact_symlink_target_verified": True,
            "regular_content_sha256_present": False,
            "no_regular_byte_stream_reason": "symbolic_link_has_no_regular_content_byte_stream",
            "producer_sha256": frozen_hashes["tools/prepare_r07_bulk_storage.py"],
            "input_hashes": {"bulk_storage_authorization_sha256": EXPECTED["bulk_storage_authorization_sha256"]},
            "runtime_run_id": RUN_ID, "runtime_attempt_id": ATTEMPT_ID,
            "lineage_id": LINEAGE_ID, "trace_profile_sha256": EXPECTED["profile_sha256"],
            "rank_coverage": [0, 1], "native_device_coverage": [0, 1],
            "evidence_class": "diagnostic_only", "storage_class": "runtime_artifact_root",
            "preserved_without_deletion": True, "validation_state": "complete",
        })
    for row in [*raw_audit["inventory"]["raw_files"], *raw_audit["inventory"]["hipprof_temporary_files"], *raw_audit["inventory"]["aot_cache_files"]]:
        relative = Path(row["attempt_entrypoint_path"]).relative_to(ARTIFACT_ROOT).as_posix()
        producer = (
            frozen_hashes["tools/prepare_r07_bulk_storage.py"]
            if row["role"] == "same_lineage_R01_direct_copy"
            else frozen_hashes["tools/run_r07_full_request.py"]
        )
        entries.append({
            "relative_path": relative, "size": int(row["size"]), "sha256": row["sha256"],
            "producer_sha256": producer,
            "input_hashes": {"bulk_storage_authorization_sha256": EXPECTED["bulk_storage_authorization_sha256"]},
            "runtime_run_id": RUN_ID, "runtime_attempt_id": ATTEMPT_ID, "lineage_id": LINEAGE_ID,
            "trace_profile_sha256": EXPECTED["profile_sha256"], "rank_coverage": [0, 1],
            "native_device_coverage": [0, 1], "evidence_class": (
                "observed_r07_timing" if relative.startswith("capture/raw/") else "diagnostic_only"
            ),
            "storage_class": "scheduler_authorized_current_attempt_bulk",
            "attempt_entrypoint": relative,
            "bulk_root_relative_path": row["storage_relative_path"],
            "filesystem_device": int(row["filesystem_device"]), "inode": int(row["inode"]),
            "attempt_and_storage_identity_equal": True, "validation_state": "complete",
        })
    for row in raw_audit["inventory"]["nonregular_bulk_objects"]:
        relative = Path(row["attempt_entrypoint_path"]).relative_to(ARTIFACT_ROOT).as_posix()
        entries.append({
            "relative_path": relative,
            "size": int(row["size"]),
            "sha256": None,
            "object_kind": row["object_kind"],
            "regular_content_sha256_present": False,
            "no_regular_byte_stream_reason": row["no_regular_byte_stream_reason"],
            "producer_sha256": frozen_hashes["tools/run_r07_full_request.py"],
            "input_hashes": {"bulk_storage_authorization_sha256": EXPECTED["bulk_storage_authorization_sha256"]},
            "runtime_run_id": RUN_ID, "runtime_attempt_id": ATTEMPT_ID, "lineage_id": LINEAGE_ID,
            "trace_profile_sha256": EXPECTED["profile_sha256"], "rank_coverage": [0, 1],
            "native_device_coverage": [0, 1], "evidence_class": "diagnostic_only",
            "storage_class": "scheduler_authorized_current_attempt_bulk",
            "attempt_entrypoint": relative,
            "bulk_root_relative_path": row["storage_relative_path"],
            "filesystem_device": int(row["filesystem_device"]),
            "inode": int(row["inode"]),
            "mode": int(row["mode"]),
            "attempt_lstat": row["attempt_lstat"],
            "storage_lstat": row["storage_lstat"],
            "attempt_and_storage_lstat_identity_equal": True,
            "preserved_without_deletion": True,
            "validation_state": "complete",
        })
    copy_manifest = _read_json(COPY_MANIFEST_PATH)
    cache_link_lstat = _lstat_record(BULK_ENTRYPOINTS["aot_cache"], "cache")
    require_equal("cache entrypoint symlink type", cache_link_lstat["object_kind"], "symbolic_link")
    require_equal("cache entrypoint exact target", os.readlink(BULK_ENTRYPOINTS["aot_cache"]), str(BULK_PATHS["aot_cache"]))
    require_equal("cache entrypoint resolved target", BULK_ENTRYPOINTS["aot_cache"].resolve(), BULK_PATHS["aot_cache"].resolve())
    entries.append({
        "relative_path": "cache", "size": int(raw_audit["inventory"]["aot_cache_total_bytes"]),
        "sha256": raw_audit["inventory"]["aot_cache_tree_identity_sha256"],
        "producer_sha256": frozen_hashes["tools/run_r07_full_request.py"],
        "input_hashes": {
            "r01_regular_content_tree_v1_sha256": copy_manifest["source_cache_regular_content_tree_v1_sha256"],
            "initial_direct_copy_regular_content_tree_v1_sha256": copy_manifest["copied_cache_regular_content_tree_v1_sha256"],
            "r01_mode_inclusive_manifest_v1_sha256": copy_manifest["source_cache_mode_inclusive_manifest_v1_sha256"],
            "initial_direct_copy_mode_inclusive_manifest_v1_sha256": copy_manifest["copied_cache_mode_inclusive_manifest_v1_sha256"],
        },
        "runtime_run_id": RUN_ID, "runtime_attempt_id": ATTEMPT_ID, "lineage_id": LINEAGE_ID,
        "trace_profile_sha256": EXPECTED["profile_sha256"], "rank_coverage": [0, 1],
        "native_device_coverage": [0, 1], "evidence_class": "diagnostic_only",
        "storage_class": "scheduler_authorized_current_attempt_bulk",
        "attempt_entrypoint": "cache", "bulk_root_relative_path": "aot_cache",
        "filesystem_device": EXPECTED["bulk_filesystem_device"], "file_count": int(raw_audit["inventory"]["aot_cache_file_count"]),
        "entrypoint_object_kind": "symbolic_link",
        "entrypoint_lstat": cache_link_lstat,
        "entrypoint_symlink_target": str(BULK_PATHS["aot_cache"]),
        "entrypoint_resolved_target": str(BULK_PATHS["aot_cache"].resolve()),
        "entrypoint_exact_symlink_target_verified": True,
        "initial_direct_copy_file_count": int(copy_manifest["copied_cache_file_count"]),
        "attempt_and_storage_identity_equal": True, "validation_state": "complete",
    })
    relative_paths = [row["relative_path"] for row in entries]
    require_equal("manifest entry identity uniqueness", len(relative_paths), len(set(relative_paths)))
    require_equal("handoff excluded from artifact manifest", str(HANDOFF_OUTPUT) in relative_paths, False)
    document = {
        "schema_version": 1, "status": "complete", "runtime_branch": BRANCH,
        "runtime_goal": "R07", "runtime_run_id": RUN_ID, "runtime_attempt_id": ATTEMPT_ID,
        "lineage_id": LINEAGE_ID, "trace_profile_sha256": EXPECTED["profile_sha256"],
        "entry_count": len(entries), "entries": sorted(entries, key=lambda row: row["relative_path"]),
        "required_business_artifacts": sorted(REQUIRED_BUSINESS_ARTIFACTS),
        "required_business_artifacts_present": True,
        "self_path": str(ARTIFACT_MANIFEST_PATH),
        "self_excluded_from_entries_to_avoid_recursive_hash_definition": True,
        "runtime_handoff_output": str(HANDOFF_OUTPUT), "runtime_handoff_excluded": True,
        "bulk_storage_root": str(BULK_ROOT),
        "bulk_storage_paths": {name: str(path) for name, path in BULK_PATHS.items()},
        "bulk_storage_attempt_entrypoints": {name: str(path) for name, path in BULK_ENTRYPOINTS.items()},
        "durable_nfs_storage": _read_json(BULK_AUTH_PATH)["durable_nfs_storage"],
        "durable_copy_manifest": _file_record(DURABLE_COPY_MANIFEST_PATH),
        "durable_completion_marker": _file_record(DURABLE_COMPLETION_MARKER_PATH),
        "bulk_storage_required_audits": _read_json(BULK_AUTH_PATH)["required_audits"],
        "bulk_storage_required_audits_sha256": EXPECTED["bulk_storage_required_audits_sha256"],
        "marker_denominator_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["marker_denominator_recovery"],
        "postdevice_preworkload_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["postdevice_preworkload_recovery"],
        "service_gate_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["service_gate_recovery"],
        "admission_schema_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["admission_schema_recovery"],
        "bulk_preparation_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["bulk_preparation_recovery"],
        "bulk_identity_schema_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["bulk_identity_schema_recovery"],
        "socket_fixture_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["socket_fixture_recovery"],
        "service_validation_path_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["service_validation_path_recovery"],
        "request_manifest_hash_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["request_manifest_hash_recovery"],
        "postmeasurement_storage_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["postmeasurement_storage_recovery"],
        "predecessor_storage_relocation": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["predecessor_storage_relocation"],
        "worker_rebuild_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["worker_rebuild_recovery"],
        "runtime_patch_path_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["runtime_patch_path_recovery"],
        "bulk_input_binding_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["bulk_input_binding_recovery"],
        "runtime_patch_fixture_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["runtime_patch_fixture_recovery"],
        "attempt024_schema_nfs_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["attempt024_schema_nfs_recovery"],
        "attempt025_dynamic_capacity_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["attempt025_dynamic_capacity_recovery"],
        "attempt026_abi_runtime_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["attempt026_abi_runtime_recovery"],
        "attempt027_historical_identity_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["attempt027_historical_identity_recovery"],
        "attempt028_bytecode_surface_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["attempt028_bytecode_surface_recovery"],
        "attempt029_bytecode_empty_set_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["attempt029_bytecode_empty_set_recovery"],
        "attempt030_sidecar_fixture_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["attempt030_sidecar_fixture_recovery"],
        "attempt031_prior_attempt_count_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["attempt031_prior_attempt_count_recovery"],
        "attempt036_preformal_ordinal_binding_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["attempt036_preformal_ordinal_binding_recovery"],
        "attempt037_preformal_historical_validator_ordinal_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["attempt037_preformal_historical_validator_ordinal_recovery"],
        "attempt038_preformal_field_value_identity_recovery": _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")["attempt038_preformal_field_value_identity_recovery"],
        "attempt038_preformal_field_value_identity_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt038_preformal_field_value_identity_recovery_audit"],
        "attempt039_predevice_bulk_helper_identity_recovery": _read_json(
            ARTIFACT_ROOT / "authorization/retry_authorization.json"
        )["attempt039_predevice_bulk_helper_identity_recovery"],
        "attempt039_predevice_bulk_helper_identity_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt039_predevice_bulk_helper_identity_recovery_audit"],
        "attempt040_predevice_historical_successor_role_recovery": _read_json(
            ARTIFACT_ROOT / "authorization/retry_authorization.json"
        )["attempt040_predevice_historical_successor_role_recovery"],
        "attempt040_predevice_historical_successor_role_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt040_predevice_historical_successor_role_recovery_audit"],
        "attempt041_predevice_tool_freeze_dependency_recovery": _read_json(
            ARTIFACT_ROOT / "authorization/retry_authorization.json"
        )["attempt041_predevice_tool_freeze_dependency_recovery"],
        "attempt041_predevice_tool_freeze_dependency_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt041_predevice_tool_freeze_dependency_recovery_audit"],
        "attempt042_predevice_admission_reference_key_recovery": _read_json(
            ARTIFACT_ROOT / "authorization/retry_authorization.json"
        )["attempt042_predevice_admission_reference_key_recovery"],
        "attempt042_predevice_admission_reference_key_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt042_predevice_admission_reference_key_recovery_audit"],
        "preproduction_cross_helper_recovery_identity_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["preproduction_cross_helper_recovery_identity_audit"],
        "preproduction_recovery_identity_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["preproduction_recovery_identity_audit"],
        "bulk_entries_use_only_attempt_entrypoint_and_pinned_root_relative_identity": True,
        "external_runtime_evidence_consumed": False,
    }
    write_json_x(ARTIFACT_MANIFEST_PATH, document)
    return document


def _write_completion_audit(
    source_audit: dict[str, Any], aot_audit: dict[str, Any], raw_audit: dict[str, Any],
    lifecycle_audit: dict[str, Any], trace_audit: dict[str, Any], live_audit: dict[str, Any],
    dependency_audit: dict[str, Any], durable_audit: dict[str, Any],
) -> dict[str, Any]:
    logical = {
        "full_request_profile_metadata": _logical_output(PROFILE_METADATA_PATH, "observed_r07_timing"),
        "process_trace_summary": _logical_output(PROCESS_SUMMARY_PATH, "derived_from_observed_r07"),
        "fresh_run_dependency_adapter": _logical_output(DEPENDENCY_PATH, "derived_from_observed_r07"),
        "live_utilization_summary": _logical_output(LIVE_SUMMARY_PATH, "derived_from_observed_r07"),
        "source_lineage": _logical_output(SOURCE_LINEAGE_PATH, "derived_from_observed_r07"),
    }
    missing = sorted(
        relative for relative in REQUIRED_BUSINESS_ARTIFACTS
        if relative not in {"validation/r07_completion_audit.json", "manifests/artifact_manifest.json"}
        and not (ARTIFACT_ROOT / relative).is_file()
    )
    require_equal("required business artifacts before completion audit", missing, [])
    require(lifecycle_audit["all_started_processes_terminated"] is True, "completion process cleanup failed")
    require(trace_audit["coverage_target_met"] is True, "completion target coverage failed")
    require_equal("completion target count", trace_audit["target_count"], EXPECTED["target_count"])
    require_equal("completion dependency target count", dependency_audit["target_count"], EXPECTED["process_target_count"])
    require_equal("completion durable-copy status", durable_audit["status"], "complete")
    require(durable_audit["completion_marker_verified_last"] is True, "durable completion marker ordering failed")
    require(durable_audit["staging_preserved"] is True, "active staging was not preserved through durable completion")
    retry = _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")
    document = {
        "schema_version": 1, "status": "complete", "execution_status": "complete",
        "evidence_status": "complete", "coverage_target_met": True,
        "next_authorization_required": False, "runtime_branch": BRANCH, "runtime_goal": "R07",
        "runtime_run_id": RUN_ID, "runtime_attempt_id": ATTEMPT_ID, "lineage_id": LINEAGE_ID,
        "trace_profile_sha256": EXPECTED["profile_sha256"],
        "checks": {
            "exact_R01_R06_prefix_and_direct_transitive_hashes": True,
            "target_source_and_frozen_tools_immutable": True,
            "current_attempt_AOT_copy_rehashed_against_same_run_R01": True,
            "one_formal_device_preflight": True,
            "one_model_initialization": True, "one_live_collector": True,
            "one_profiler_capture": True, "two_warmups": True,
            "one_eight_request_measured_workload": True,
            "complete_dual_DCU_DP2_rank_device_mapping": True,
            "one_valid_database_and_one_complete_logical_PFTrace_family": True,
            "all_cache_raw_and_temporary_bytes_sealed_through_both_bulk_paths": True,
            "all_nonregular_bulk_objects_dual_path_lstat_sealed_without_deletion": True,
            "exact_request_forward_layer_process_marker_transport": True,
            "full_time_and_runtime_index_containment": True,
            "unique_deepest_ownership": True, "launch_kernel_correlation_complete": True,
            "parent_fragment_double_count_zero": True, "explicit_no_kernel_rows_preserved": True,
            "queue_stream_and_busy_union_conserved": True,
            "live_samples_and_gaps_lossless": True,
            "live_utilization_unavailable_states_honest": True,
            "no_interpolation_resampling_imputation_or_zero_fill": True,
            "dependency_adapter_conserved_without_guessing": True,
            "no_external_runtime_evidence": True, "no_PMC_replay_report_or_successor": True,
            "all_started_processes_terminated_and_reaped": True,
            "request_manifest_raw_and_canonical_identities_separately_validated": True,
            "collector_exported_views_released_before_backing_close": True,
            "predecessor_relocation_full_surface_admission_consumed": True,
            "attempt024_raw_schema_and_scheduler_projection_separately_validated": True,
            "attempt025_dynamic_capacity_recomputed_as_floor_only_gate": True,
            "attempt026_ABI_runtime_provenance_and_frozen_members_revalidated": True,
            "attempt027_historical_and_current_identity_roles_separately_validated": True,
            "attempt028_bytecode_surface_recovery_and_fail_closed_regressions_validated": True,
            "attempt029_empty_bytecode_surface_and_nonempty_fail_closed_regressions_validated": True,
            "attempt038_all_recovery_identity_constants_recomputed_before_production_admission": True,
            "attempt038_canonical_field_path_and_field_value_identities_validated": True,
            "attempt039_cross_helper_identity_audit_completed_before_production_admission": True,
            "attempt039_signed_recovery_propagated_through_bulk_freeze_run_and_final_audit": True,
            "attempt040_historical_successor_roles_preserved": True,
            "attempt040_current_identity_derived_only_from_signed_recovery": True,
            "attempt040_signed_recovery_propagated_through_bulk_freeze_run_and_final_audit": True,
            "resumable_durable_copy_production_regression_passed_pre_side_effect": True,
            "closed_native_surface_durably_copied_before_normalization": True,
            "closed_capture_database_checkpointed_before_offline_export": True,
            "offline_pftrace_export_started_only_after_durable_database_checkpoint": True,
            "checkpointed_database_reverified_during_full_raw_copy": True,
            "durable_destination_surface_independently_rehashed": True,
            "durable_completion_marker_written_last": True,
            "active_sqlite_and_profiler_staging_never_ran_on_nfs": True,
            "staging_preserved_through_durable_completion": True,
            "handoff_business_output_separation": True,
        },
        "source_immutability": source_audit, "aot_copy_audit": aot_audit,
        "raw_audit": {key: value for key, value in raw_audit.items() if key != "inventory"},
        "lifecycle_audit": lifecycle_audit, "trace_audit": trace_audit,
        "live_utilization_audit": live_audit, "dependency_audit": dependency_audit,
        "durable_copy_audit": durable_audit,
        "logical_outputs": logical,
        "required_business_artifact_count": len(REQUIRED_BUSINESS_ARTIFACTS),
        "required_business_artifacts_present_before_self_and_manifest": True,
        "artifact_manifest_path": str(ARTIFACT_MANIFEST_PATH),
        "artifact_manifest_validation_deferred_until_exclusive_write": True,
        "scheduler_profile_attestation": TRACE_PROFILE_ATTESTATION,
        "marker_denominator_recovery": retry["marker_denominator_recovery"],
        "postdevice_preworkload_recovery": retry["postdevice_preworkload_recovery"],
        "service_gate_recovery": retry["service_gate_recovery"],
        "admission_schema_recovery": retry["admission_schema_recovery"],
        "bulk_preparation_recovery": retry["bulk_preparation_recovery"],
        "bulk_identity_schema_recovery": retry["bulk_identity_schema_recovery"],
        "socket_fixture_recovery": retry["socket_fixture_recovery"],
        "service_validation_path_recovery": retry["service_validation_path_recovery"],
        "request_manifest_hash_recovery": retry["request_manifest_hash_recovery"],
        "postmeasurement_storage_recovery": retry["postmeasurement_storage_recovery"],
        "predecessor_storage_relocation": retry["predecessor_storage_relocation"],
        "worker_rebuild_recovery": retry["worker_rebuild_recovery"],
        "runtime_patch_path_recovery": retry["runtime_patch_path_recovery"],
        "bulk_input_binding_recovery": retry["bulk_input_binding_recovery"],
        "runtime_patch_fixture_recovery": retry["runtime_patch_fixture_recovery"],
        "attempt024_schema_nfs_recovery": retry["attempt024_schema_nfs_recovery"],
        "attempt025_dynamic_capacity_recovery": retry[
            "attempt025_dynamic_capacity_recovery"
        ],
        "attempt026_abi_runtime_recovery": retry[
            "attempt026_abi_runtime_recovery"
        ],
        "attempt026_abi_runtime_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt026_abi_runtime_recovery_audit"],
        "attempt027_historical_identity_recovery": retry[
            "attempt027_historical_identity_recovery"
        ],
        "attempt027_historical_identity_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt027_historical_identity_recovery_audit"],
        "attempt028_bytecode_surface_recovery": retry[
            "attempt028_bytecode_surface_recovery"
        ],
        "attempt028_bytecode_surface_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt028_bytecode_surface_recovery_audit"],
        "attempt029_bytecode_empty_set_recovery": retry[
            "attempt029_bytecode_empty_set_recovery"
        ],
        "attempt029_bytecode_empty_set_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt029_bytecode_empty_set_recovery_audit"],
        "attempt030_sidecar_fixture_recovery": retry[
            "attempt030_sidecar_fixture_recovery"
        ],
        "attempt030_sidecar_fixture_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt030_sidecar_fixture_recovery_audit"],
        "attempt031_prior_attempt_count_recovery": retry[
            "attempt031_prior_attempt_count_recovery"
        ],
        "attempt031_prior_attempt_count_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt031_prior_attempt_count_recovery_audit"],
        "attempt036_preformal_ordinal_binding_recovery": retry[
            "attempt036_preformal_ordinal_binding_recovery"
        ],
        "attempt037_preformal_historical_validator_ordinal_recovery": retry[
            "attempt037_preformal_historical_validator_ordinal_recovery"
        ],
        "attempt038_preformal_field_value_identity_recovery": retry[
            "attempt038_preformal_field_value_identity_recovery"
        ],
        "attempt038_preformal_field_value_identity_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt038_preformal_field_value_identity_recovery_audit"],
        "attempt039_predevice_bulk_helper_identity_recovery": _read_json(
            ARTIFACT_ROOT / "authorization/retry_authorization.json"
        )["attempt039_predevice_bulk_helper_identity_recovery"],
        "attempt039_predevice_bulk_helper_identity_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt039_predevice_bulk_helper_identity_recovery_audit"],
        "attempt040_predevice_historical_successor_role_recovery": retry[
            "attempt040_predevice_historical_successor_role_recovery"
        ],
        "attempt040_predevice_historical_successor_role_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt040_predevice_historical_successor_role_recovery_audit"],
        "attempt041_predevice_tool_freeze_dependency_recovery": retry[
            "attempt041_predevice_tool_freeze_dependency_recovery"
        ],
        "attempt041_predevice_tool_freeze_dependency_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt041_predevice_tool_freeze_dependency_recovery_audit"],
        "attempt042_predevice_admission_reference_key_recovery": _read_json(
            ARTIFACT_ROOT / "authorization/retry_authorization.json"
        )["attempt042_predevice_admission_reference_key_recovery"],
        "attempt042_predevice_admission_reference_key_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt042_predevice_admission_reference_key_recovery_audit"],
        "preproduction_cross_helper_recovery_identity_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["preproduction_cross_helper_recovery_identity_audit"],
        "preproduction_recovery_identity_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["preproduction_recovery_identity_audit"],
        "post_attempt031_worker_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["post_attempt031_worker_recovery_audit"],
        "capture_db_checkpoint_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["capture_db_checkpoint_audit"],
        "durable_nfs_storage": _read_json(BULK_AUTH_PATH)["durable_nfs_storage"],
        "bulk_storage_required_audits": _read_json(BULK_AUTH_PATH)["required_audits"],
        "bulk_storage_required_audits_sha256": EXPECTED["bulk_storage_required_audits_sha256"],
        "all_started_processes_terminated": True,
        "external_runtime_evidence_consumed": False,
    }
    write_json_x(COMPLETION_AUDIT_PATH, document)
    return document


def _verify_manifest(document: dict[str, Any], raw_audit: dict[str, Any]) -> None:
    require_equal("manifest status", document["status"], "complete")
    require_equal("manifest entry count", document["entry_count"], len(document["entries"]))
    paths = {row["relative_path"] for row in document["entries"]}
    require_equal("manifest paths unique", len(paths), len(document["entries"]))
    require(REQUIRED_BUSINESS_ARTIFACTS - {"manifests/artifact_manifest.json"} <= paths, "manifest misses required business artifacts")
    require("manifests/artifact_manifest.json" not in paths, "manifest recursive self-entry forbidden")
    require_equal("manifest durable NFS storage", document["durable_nfs_storage"], _read_json(BULK_AUTH_PATH)["durable_nfs_storage"])
    require_equal("manifest durable copy-manifest reference", document["durable_copy_manifest"], _file_record(DURABLE_COPY_MANIFEST_PATH))
    require_equal("manifest durable completion-marker reference", document["durable_completion_marker"], _file_record(DURABLE_COMPLETION_MARKER_PATH))
    for row in document["entries"]:
        relative = row["relative_path"]
        if row["storage_class"] == "runtime_artifact_root":
            path = ARTIFACT_ROOT / relative
            if row.get("object_kind") and row["object_kind"] != "regular_file":
                observed = path.lstat()
                require_equal(f"manifest nonregular artifact size {relative}", observed.st_size, int(row["size"]))
                require_equal(f"manifest nonregular artifact mode {relative}", observed.st_mode, int(row["mode"]))
                require_equal(f"manifest nonregular artifact inode {relative}", observed.st_ino, int(row["inode"]))
                require_equal(f"manifest nonregular artifact null hash {relative}", row["sha256"], None)
                require(row["preserved_without_deletion"] is True, f"manifest artifact nonregular preservation missing {relative}")
                if row["object_kind"] == "symbolic_link":
                    require_equal(f"manifest symbolic-link target {relative}", os.readlink(path), row["symlink_target"])
                    require_equal(f"manifest symbolic-link resolved target {relative}", str(path.resolve()), row["resolved_target"])
                if row.get("dual_path_lstat_required"):
                    left = PREFREEZE_FIXTURE_SOCKET_ENTRYPOINT.lstat()
                    right = PREFREEZE_FIXTURE_SOCKET.lstat()
                    for field, attribute in (
                        ("filesystem_device", "st_dev"), ("inode", "st_ino"),
                        ("mode", "st_mode"), ("size", "st_size"),
                    ):
                        require_equal(f"manifest fixture dual-path current {field}", getattr(left, attribute), getattr(right, attribute))
                        require_equal(f"manifest fixture attempt lstat {field}", getattr(left, attribute), int(row["attempt_lstat"][field]))
                        require_equal(f"manifest fixture storage lstat {field}", getattr(right, attribute), int(row["storage_lstat"][field]))
            else:
                require_equal(f"manifest size {relative}", path.stat().st_size, int(row["size"]))
                require_equal(f"manifest hash {relative}", sha256_path(path), row["sha256"])
        elif relative == "cache":
            require_equal("manifest current cache tree identity", row["sha256"], raw_audit["inventory"]["aot_cache_tree_identity_sha256"])
            require_equal("manifest current cache total bytes", int(row["size"]), int(raw_audit["inventory"]["aot_cache_total_bytes"]))
            cache_link = BULK_ENTRYPOINTS["aot_cache"]
            cache_lstat = cache_link.lstat()
            require(stat.S_ISLNK(cache_lstat.st_mode), "manifest cache entrypoint is not a symbolic link")
            require_equal("manifest cache link mode", cache_lstat.st_mode, int(row["entrypoint_lstat"]["mode"]))
            require_equal("manifest cache link inode", cache_lstat.st_ino, int(row["entrypoint_lstat"]["inode"]))
            require_equal("manifest cache link target", os.readlink(cache_link), row["entrypoint_symlink_target"])
            require_equal("manifest cache resolved target", str(cache_link.resolve()), row["entrypoint_resolved_target"])
        else:
            entrypoint = ARTIFACT_ROOT / row["attempt_entrypoint"]
            storage = BULK_ROOT / row["bulk_root_relative_path"]
            if row.get("object_kind") and row["object_kind"] != "regular_file":
                left = entrypoint.lstat(); right = storage.lstat()
                require_equal(f"manifest nonregular inode {relative}", left.st_ino, right.st_ino)
                require_equal(f"manifest nonregular mode {relative}", left.st_mode, right.st_mode)
                require_equal(f"manifest nonregular size {relative}", left.st_size, int(row["size"]))
                require_equal(f"manifest nonregular null hash {relative}", row["sha256"], None)
                require(row["preserved_without_deletion"] is True, f"manifest nonregular preservation missing {relative}")
            else:
                require_equal(f"manifest bulk size {relative}", entrypoint.stat().st_size, int(row["size"]))
                require_equal(f"manifest bulk inode {relative}", entrypoint.stat().st_ino, storage.stat().st_ino)
                require_equal(f"manifest bulk hash {relative}", sha256_path(entrypoint), row["sha256"])
    raw_manifest_paths = {
        Path(row["attempt_entrypoint_path"]).relative_to(ARTIFACT_ROOT).as_posix()
        for row in [*raw_audit["inventory"]["raw_files"], *raw_audit["inventory"]["hipprof_temporary_files"], *raw_audit["inventory"]["aot_cache_files"], *raw_audit["inventory"]["nonregular_bulk_objects"]]
    }
    require(raw_manifest_paths <= paths, "manifest omits sealed bulk cache/raw/tmp member")


def _write_handoff(
    raw_audit: dict[str, Any], lifecycle_audit: dict[str, Any], trace_audit: dict[str, Any],
    live_audit: dict[str, Any], dependency_audit: dict[str, Any], durable_audit: dict[str, Any],
) -> dict[str, Any]:
    require(not HANDOFF_OUTPUT.exists(), "R07 handoff already exists")
    require_equal("handoff parent", HANDOFF_OUTPUT.parent, LEDGER_PATH.parent / "handoffs")
    logical = {
        "full_request_profile_metadata": _logical_output(PROFILE_METADATA_PATH, "observed_r07_timing"),
        "process_trace_summary": _logical_output(PROCESS_SUMMARY_PATH, "derived_from_observed_r07"),
        "fresh_run_dependency_adapter": _logical_output(DEPENDENCY_PATH, "derived_from_observed_r07"),
        "live_utilization_summary": _logical_output(LIVE_SUMMARY_PATH, "derived_from_observed_r07"),
        "source_lineage": _logical_output(SOURCE_LINEAGE_PATH, "derived_from_observed_r07"),
    }
    direct = {goal: {"path": str(LEDGER_PATH.parent / f"handoffs/{goal}.json"), "sha256": value} for goal, value in HANDOFF_HASHES.items()}
    retry = _read_json(ARTIFACT_ROOT / "authorization/retry_authorization.json")
    document = {
        "status": "complete", "execution_status": "complete", "evidence_status": "complete",
        "coverage_target_met": True, "next_authorization_required": False,
        "runtime_branch": BRANCH, "runtime_goal": "R07", "runtime_run_id": RUN_ID,
        "runtime_attempt_id": ATTEMPT_ID, "lineage_id": LINEAGE_ID,
        "trace_profile_sha256": EXPECTED["profile_sha256"],
        "cumulative_runtime_ledger_sha256": EXPECTED["ledger_sha256"],
        "r01_handoff_sha256": HANDOFF_HASHES["R01"], "r02_handoff_sha256": HANDOFF_HASHES["R02"],
        "r03_handoff_sha256": HANDOFF_HASHES["R03"], "r04_handoff_sha256": HANDOFF_HASHES["R04"],
        "r05_handoff_sha256": HANDOFF_HASHES["R05"], "r06_handoff_sha256": HANDOFF_HASHES["R06"],
        "r06_request_phase_selection_revision_sha256": R06_REQUEST_PHASE_SELECTION_REVISION_SHA256,
        "bound_target_sidecar_sha256": sha256_path(R07_BOUND_TARGET_SIDECAR_PATH),
        "retry_authorization_path": str(ARTIFACT_ROOT / "authorization/retry_authorization.json"),
        "retry_authorization_sha256": EXPECTED["retry_authorization_sha256"],
        "monitor_advisory_path": str(ARTIFACT_ROOT / "authorization/monitor_advisory.json"),
        "monitor_advisory_sha256": EXPECTED["monitor_advisory_sha256"],
        "bulk_storage_authorization_path": str(BULK_AUTH_PATH),
        "bulk_storage_authorization_sha256": EXPECTED["bulk_storage_authorization_sha256"],
        "bulk_storage_root": str(BULK_ROOT),
        "bulk_storage_paths": {name: str(path) for name, path in BULK_PATHS.items()},
        "bulk_storage_attempt_entrypoints": {name: str(path) for name, path in BULK_ENTRYPOINTS.items()},
        "durable_nfs_storage": _read_json(BULK_AUTH_PATH)["durable_nfs_storage"],
        "capture_db_checkpoint_invocation_path": str(
            DB_CHECKPOINT_INVOCATION_PATH
        ),
        "capture_db_checkpoint_invocation_sha256": sha256_path(
            DB_CHECKPOINT_INVOCATION_PATH
        ),
        "capture_db_checkpoint_marker_path": str(CAPTURE_DB_DURABLE_MARKER),
        "capture_db_checkpoint_marker_sha256": durable_audit[
            "capture_db_checkpoint_marker"
        ]["sha256"],
        "offline_pftrace_export_invocation_path": str(
            OFFLINE_EXPORT_INVOCATION_PATH
        ),
        "offline_pftrace_export_invocation_sha256": sha256_path(
            OFFLINE_EXPORT_INVOCATION_PATH
        ),
        "durable_copy_manifest_path": str(DURABLE_COPY_MANIFEST_PATH),
        "durable_copy_manifest_sha256": durable_audit["manifest"]["sha256"],
        "durable_completion_marker_path": str(DURABLE_COMPLETION_MARKER_PATH),
        "durable_completion_marker_sha256": durable_audit["completion_marker"]["sha256"],
        "durable_surface_canonical_sha256": durable_audit["surface_canonical_sha256"],
        "bulk_storage_required_audits": _read_json(BULK_AUTH_PATH)["required_audits"],
        "bulk_storage_required_audits_sha256": EXPECTED["bulk_storage_required_audits_sha256"],
        "r07_control_plane_binding_sha256": EXPECTED["control_plane_binding_sha256"],
        "marker_denominator_recovery": retry["marker_denominator_recovery"],
        "postdevice_preworkload_recovery": retry["postdevice_preworkload_recovery"],
        "service_gate_recovery": retry["service_gate_recovery"],
        "admission_schema_recovery": retry["admission_schema_recovery"],
        "bulk_preparation_recovery": retry["bulk_preparation_recovery"],
        "bulk_identity_schema_recovery": retry["bulk_identity_schema_recovery"],
        "socket_fixture_recovery": retry["socket_fixture_recovery"],
        "service_validation_path_recovery": retry["service_validation_path_recovery"],
        "request_manifest_hash_recovery": retry["request_manifest_hash_recovery"],
        "postmeasurement_storage_recovery": retry["postmeasurement_storage_recovery"],
        "predecessor_storage_relocation": retry["predecessor_storage_relocation"],
        "worker_rebuild_recovery": retry["worker_rebuild_recovery"],
        "runtime_patch_path_recovery": retry["runtime_patch_path_recovery"],
        "bulk_input_binding_recovery": retry["bulk_input_binding_recovery"],
        "runtime_patch_fixture_recovery": retry["runtime_patch_fixture_recovery"],
        "attempt024_schema_nfs_recovery": retry["attempt024_schema_nfs_recovery"],
        "attempt025_dynamic_capacity_recovery": retry[
            "attempt025_dynamic_capacity_recovery"
        ],
        "attempt026_abi_runtime_recovery": retry[
            "attempt026_abi_runtime_recovery"
        ],
        "attempt026_abi_runtime_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt026_abi_runtime_recovery_audit"],
        "attempt027_historical_identity_recovery": retry[
            "attempt027_historical_identity_recovery"
        ],
        "attempt027_historical_identity_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt027_historical_identity_recovery_audit"],
        "attempt028_bytecode_surface_recovery": retry[
            "attempt028_bytecode_surface_recovery"
        ],
        "attempt028_bytecode_surface_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt028_bytecode_surface_recovery_audit"],
        "attempt029_bytecode_empty_set_recovery": retry[
            "attempt029_bytecode_empty_set_recovery"
        ],
        "attempt029_bytecode_empty_set_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt029_bytecode_empty_set_recovery_audit"],
        "attempt030_sidecar_fixture_recovery": retry[
            "attempt030_sidecar_fixture_recovery"
        ],
        "attempt030_sidecar_fixture_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt030_sidecar_fixture_recovery_audit"],
        "attempt031_prior_attempt_count_recovery": retry[
            "attempt031_prior_attempt_count_recovery"
        ],
        "attempt031_prior_attempt_count_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt031_prior_attempt_count_recovery_audit"],
        "attempt036_preformal_ordinal_binding_recovery": retry[
            "attempt036_preformal_ordinal_binding_recovery"
        ],
        "attempt037_preformal_historical_validator_ordinal_recovery": retry[
            "attempt037_preformal_historical_validator_ordinal_recovery"
        ],
        "attempt038_preformal_field_value_identity_recovery": retry[
            "attempt038_preformal_field_value_identity_recovery"
        ],
        "attempt038_preformal_field_value_identity_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt038_preformal_field_value_identity_recovery_audit"],
        "attempt039_predevice_bulk_helper_identity_recovery": _read_json(
            ARTIFACT_ROOT / "authorization/retry_authorization.json"
        )["attempt039_predevice_bulk_helper_identity_recovery"],
        "attempt039_predevice_bulk_helper_identity_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt039_predevice_bulk_helper_identity_recovery_audit"],
        "attempt040_predevice_historical_successor_role_recovery": retry[
            "attempt040_predevice_historical_successor_role_recovery"
        ],
        "attempt040_predevice_historical_successor_role_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt040_predevice_historical_successor_role_recovery_audit"],
        "attempt041_predevice_tool_freeze_dependency_recovery": retry[
            "attempt041_predevice_tool_freeze_dependency_recovery"
        ],
        "attempt041_predevice_tool_freeze_dependency_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt041_predevice_tool_freeze_dependency_recovery_audit"],
        "attempt042_predevice_admission_reference_key_recovery": _read_json(
            ARTIFACT_ROOT / "authorization/retry_authorization.json"
        )["attempt042_predevice_admission_reference_key_recovery"],
        "attempt042_predevice_admission_reference_key_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["attempt042_predevice_admission_reference_key_recovery_audit"],
        "preproduction_cross_helper_recovery_identity_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["preproduction_cross_helper_recovery_identity_audit"],
        "preproduction_recovery_identity_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["preproduction_recovery_identity_audit"],
        "post_attempt031_worker_recovery_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["post_attempt031_worker_recovery_audit"],
        "capture_db_checkpoint_audit": _read_json(
            PREDECESSOR_VALIDATION_PATH
        )["capture_db_checkpoint_audit"],
        "full_request_profile_metadata_sha256": logical["full_request_profile_metadata"]["sha256"],
        "process_trace_summary_sha256": logical["process_trace_summary"]["sha256"],
        "fresh_run_dependency_adapter_sha256": logical["fresh_run_dependency_adapter"]["sha256"],
        "live_utilization_summary_sha256": logical["live_utilization_summary"]["sha256"],
        "source_lineage_sha256": logical["source_lineage"]["sha256"],
        "artifact_manifest_sha256": sha256_path(ARTIFACT_MANIFEST_PATH),
        "completion_audit_sha256": sha256_path(COMPLETION_AUDIT_PATH),
        "all_started_processes_terminated": True,
        "skill": "qwen-dcu-workflow05-full-request-process-trace",
        "runtime_artifact_root": str(ARTIFACT_ROOT), "runtime_handoff_output": str(HANDOFF_OUTPUT),
        "scheduler_profile_attestation": TRACE_PROFILE_ATTESTATION,
        "schema_version": 1, "runtime_predecessors": ["R01", "R02", "R03", "R04", "R05", "R06"],
        "cumulative_runtime_ledger_path": str(LEDGER_PATH), "direct_predecessor_handoffs": direct,
        "trace_profile_path": str(PROFILE_PATH), "runtime_config_path": str(RUNTIME_CONFIG_PATH),
        "runtime_config_sha256": EXPECTED["runtime_config_sha256"],
        "request_selection_manifest_path": str(R01_REQUEST_MANIFEST_PATH),
        "request_selection_manifest_file_byte_sha256": EXPECTED["r01_request_manifest_file_byte_sha256"],
        "request_selection_manifest_canonical_json_sha256": EXPECTED["r01_request_manifest_canonical_json_sha256"],
        "request_selection_ordered_sequence_sha256": EXPECTED["request_sequence_sha256"],
        "target_root": str(TARGET_ROOT), "target_git_commit": EXPECTED["target_commit"],
        "target_git_branch": "repro-gqa-page784-k5120-batch8-final", "target_source_clean": True,
        "frozen_tool_manifest_path": str(tool_manifest_path()),
        "frozen_tool_manifest_sha256": sha256_path(tool_manifest_path()),
        "source_immutability_path": str(SOURCE_IMMUTABILITY_PATH),
        "source_immutability_sha256": sha256_path(SOURCE_IMMUTABILITY_PATH),
        "raw_inventory_path": str(RAW_INVENTORY_PATH), "raw_inventory_sha256": raw_audit["inventory_sha256"],
        "logical_outputs": logical, "lifecycle": lifecycle_audit["lifecycle"],
        "trace_coverage_and_ownership": trace_audit, "live_utilization_accounting": live_audit,
        "dependency_adapter_audit": dependency_audit,
        "artifact_manifest_path": str(ARTIFACT_MANIFEST_PATH),
        "completion_audit_path": str(COMPLETION_AUDIT_PATH),
        "model_execution_performed": True, "gpu_dcu_execution_performed": True,
        "profiler_execution_performed": True, "trace_collection_performed": True,
        "live_utilization_collection_performed": True, "dependency_adapter_performed": True,
        "pmc_collection_performed": False, "replay_performed": False,
        "report_generation_performed": False, "successor_execution_performed": False,
        "fresh_e2e_evidence": {
            "schema_version": 1, "status": "complete", "runtime_branch": BRANCH,
            "runtime_goal": "R07", "runtime_run_id": RUN_ID,
            "runtime_attempt_id": ATTEMPT_ID, "lineage_id": LINEAGE_ID,
            "trace_profile_sha256": EXPECTED["profile_sha256"],
            "fresh_non_replay_current_attempt_only": True,
            "external_runtime_evidence_consumed": False,
        },
        "advance_decision": {"next_runtime_goal": "R08", "authorized": True, "reason": "all_R07_execution_evidence_coverage_and_cleanup_gates_complete"},
    }
    payload = (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    HANDOFF_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with HANDOFF_OUTPUT.open("xb") as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    require_equal("handoff bytes", HANDOFF_OUTPUT.read_bytes(), payload)
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--runtime-handoff-output", required=True)
    args = parser.parse_args()
    require_equal("artifact root argv", Path(args.artifact_root).resolve(), ARTIFACT_ROOT.resolve())
    require_equal("handoff argv", Path(args.runtime_handoff_output).resolve(), HANDOFF_OUTPUT.resolve())
    require(not SOURCE_IMMUTABILITY_PATH.exists(), "source immutability output already exists")
    require(not SOURCE_LINEAGE_PATH.exists(), "source lineage output already exists")
    require(not COMPLETION_AUDIT_PATH.exists(), "completion audit output already exists")
    require(not ARTIFACT_MANIFEST_PATH.exists(), "artifact manifest output already exists")
    require(not HANDOFF_OUTPUT.exists(), "R07 handoff already exists")
    source_audit = _audit_static_and_source()
    aot_audit = _audit_aot_copy()
    lifecycle_audit = _audit_lifecycle()
    raw_audit = _audit_raw()
    durable_audit = _audit_durable_copy(raw_audit, lifecycle_audit)
    trace_audit = _audit_trace(raw_audit)
    live_audit = _audit_live_utilization()
    dependency_audit = _audit_dependency()
    _write_source_lineage(source_audit, raw_audit, trace_audit, live_audit, dependency_audit, aot_audit, durable_audit)
    completion = _write_completion_audit(source_audit, aot_audit, raw_audit, lifecycle_audit, trace_audit, live_audit, dependency_audit, durable_audit)
    manifest = _write_artifact_manifest(raw_audit)
    _verify_manifest(manifest, raw_audit)
    require_equal("completion audit status", completion["status"], "complete")
    handoff = _write_handoff(raw_audit, lifecycle_audit, trace_audit, live_audit, dependency_audit, durable_audit)
    required_top_level = {
        "status", "execution_status", "evidence_status", "coverage_target_met", "next_authorization_required",
        "runtime_branch", "runtime_goal", "runtime_run_id", "runtime_attempt_id", "lineage_id",
        "trace_profile_sha256", "cumulative_runtime_ledger_sha256", "r01_handoff_sha256",
        "r02_handoff_sha256", "r03_handoff_sha256", "r04_handoff_sha256", "r05_handoff_sha256",
        "r06_handoff_sha256", "r06_request_phase_selection_revision_sha256",
        "bound_target_sidecar_sha256", "retry_authorization_path", "retry_authorization_sha256",
        "monitor_advisory_path", "monitor_advisory_sha256", "bulk_storage_authorization_path",
        "bulk_storage_authorization_sha256", "bulk_storage_root", "bulk_storage_paths",
        "bulk_storage_attempt_entrypoints", "bulk_storage_required_audits",
        "bulk_storage_required_audits_sha256", "r07_control_plane_binding_sha256",
        "marker_denominator_recovery",
        "postdevice_preworkload_recovery",
        "service_gate_recovery", "admission_schema_recovery",
        "bulk_preparation_recovery", "bulk_identity_schema_recovery", "socket_fixture_recovery",
        "service_validation_path_recovery",
        "request_manifest_hash_recovery", "postmeasurement_storage_recovery",
        "predecessor_storage_relocation", "worker_rebuild_recovery",
        "runtime_patch_path_recovery", "bulk_input_binding_recovery",
        "runtime_patch_fixture_recovery",
        "attempt024_schema_nfs_recovery", "attempt025_dynamic_capacity_recovery",
        "attempt026_abi_runtime_recovery", "attempt026_abi_runtime_recovery_audit",
        "attempt027_historical_identity_recovery",
        "attempt027_historical_identity_recovery_audit",
        "attempt028_bytecode_surface_recovery",
        "attempt028_bytecode_surface_recovery_audit",
        "attempt029_bytecode_empty_set_recovery",
        "attempt029_bytecode_empty_set_recovery_audit",
        "attempt030_sidecar_fixture_recovery",
        "attempt030_sidecar_fixture_recovery_audit",
        "attempt031_prior_attempt_count_recovery",
        "attempt031_prior_attempt_count_recovery_audit",
        "attempt036_preformal_ordinal_binding_recovery",
        "attempt037_preformal_historical_validator_ordinal_recovery",
        "attempt038_preformal_field_value_identity_recovery",
        "attempt038_preformal_field_value_identity_recovery_audit",
        "attempt039_predevice_bulk_helper_identity_recovery",
        "attempt039_predevice_bulk_helper_identity_recovery_audit",
        "attempt040_predevice_historical_successor_role_recovery",
        "attempt040_predevice_historical_successor_role_recovery_audit",
        "attempt041_predevice_tool_freeze_dependency_recovery",
        "attempt041_predevice_tool_freeze_dependency_recovery_audit",
        "attempt042_predevice_admission_reference_key_recovery",
        "attempt042_predevice_admission_reference_key_recovery_audit",
        "preproduction_cross_helper_recovery_identity_audit",
        "preproduction_recovery_identity_audit",
        "post_attempt031_worker_recovery_audit",
        "capture_db_checkpoint_audit",
        "durable_nfs_storage",
        "capture_db_checkpoint_invocation_path",
        "capture_db_checkpoint_invocation_sha256",
        "capture_db_checkpoint_marker_path",
        "capture_db_checkpoint_marker_sha256",
        "offline_pftrace_export_invocation_path",
        "offline_pftrace_export_invocation_sha256",
        "durable_copy_manifest_path", "durable_copy_manifest_sha256",
        "durable_completion_marker_path", "durable_completion_marker_sha256",
        "durable_surface_canonical_sha256",
        "full_request_profile_metadata_sha256", "process_trace_summary_sha256",
        "fresh_run_dependency_adapter_sha256", "live_utilization_summary_sha256",
        "source_lineage_sha256", "artifact_manifest_sha256", "completion_audit_sha256",
        "all_started_processes_terminated", "skill", "runtime_artifact_root", "runtime_handoff_output",
        "scheduler_profile_attestation",
    }
    require_equal("handoff required top-level fields", required_top_level - set(handoff), set())
    require_equal("handoff scheduler attestation", handoff["scheduler_profile_attestation"], TRACE_PROFILE_ATTESTATION)
    print(json.dumps({
        "status": "complete", "execution_status": "complete", "evidence_status": "complete",
        "coverage_target_met": True, "next_authorization_required": False,
        "handoff_sha256": sha256_path(HANDOFF_OUTPUT), "all_started_processes_terminated": True,
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
