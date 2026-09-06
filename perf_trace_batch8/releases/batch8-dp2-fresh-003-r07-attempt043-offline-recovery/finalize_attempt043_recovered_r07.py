#!/usr/bin/env python3
"""Finalize a transparent recovery-complete R07 handoff for attempt-043."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


RUN_ID = "batch8-dp2-fresh-003"
ATTEMPT_ID = "batch8-dp2-fresh-003-R07-attempt-043"
PROFILE_SHA256 = "3b4c952063f48ae662b48b5ce9d8fd76e0ac4d74e170bdb1839ae8b1aaa23cce"
LEDGER_SHA256 = "86990e6156267c36334c31ae3ead733807d11286002d0fe00425b395d3397670"
SOURCE_DB_SHA256 = "0ea77cdac40926182c4e04fc29e687e62df9b2cac50296c7e399817c583690b0"
PREPARED_DB_SHA256 = "14a1e21b4bf5a0b29b11a62c4d000cac4979aa5af4ddc687f614bdab4f3179cd"
HIPPROF_SHA256 = "53f67d3dd4c1fe5aa9850f58d174ecf9f2c688f1e07519b456b19ca699c57f22"
HANDOFF_HASHES = {
    "R01": "f28cb9274151c5b08f15964e9645cbcaa41b90fb6f867607472028e993b774d6",
    "R02": "9c1b908430fe9757935d029e8f423192652f21675aeffd77bc6a0f5d48d2e7e6",
    "R03": "f7e6066bd72272cee9e96d2ac31596bd20f01841157bda4d0c2eb56092f99885",
    "R04": "403af982ff2f70f89fce2cfda59074a9b014a32e95c53e9e05e292dc843e6719",
    "R05": "db08474f64a999428287388a949762274716df125132cbccbabe3ec23c1aec66",
    "R06": "0da6d692f1d69194ab02f4de0993c7aaca2381793eeb61ce33ffeb52ec058976",
}
TARGET_COMMIT = "2b4b2119ae3cc2c4c626dc5690ef9593c1477f66"
TARGET_BRANCH = "repro-gqa-page784-k5120-batch8-final"
SOURCE_HASHES = {
    "vllm/model_executor/models/qwen3_5.py": "f3c0479dbc37a8794c4d6b1c4c01906ae341b3276ed43e588c17d92b1ddb94d6",
    "vllm/model_executor/models/qwen3_next.py": "5a14b14a40fcf6382f9a20be4ca0f850b2b19b2840a3c57488821f0952d96053",
    "vllm/v1/worker/gpu_model_runner.py": "d63424d3cbe81bfaa2c0967a5c81bfaa2c0967a5c81b8c980c2d76bc7eb3b2f8fe2a079af825bce",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def file_ref(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"required regular file missing: {path}")
    return {"path": str(path), "size": path.stat().st_size, "sha256": sha256_file(path)}


def write_json_exclusive(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def git_output(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--recovery-root", required=True, type=Path)
    parser.add_argument("--monitor-snapshot", required=True, type=Path)
    args = parser.parse_args()

    project = args.project_root
    artifact = args.artifact_root
    recovery = args.recovery_root
    run_root = artifact.parents[2]
    recovery_evidence = artifact / "recovery/db43_offline_recovery"
    handoff_path = run_root / "handoffs/R07.recovered.json"
    lineage_path = recovery_evidence / "R07_RECOVERY_SOURCE_LINEAGE.json"
    completion_path = recovery_evidence / "R07_RECOVERY_COMPLETION_AUDIT.json"
    manifest_path = recovery_evidence / "R07_RECOVERY_ARTIFACT_MANIFEST.json"
    for path in (handoff_path, lineage_path, completion_path, manifest_path):
        if path.exists() or path.is_symlink():
            raise RuntimeError(f"refusing existing final output: {path}")

    independent_path = recovery_evidence / "RECOVERY_INDEPENDENT_AUDITS.json"
    independent = load_json(independent_path)
    if independent.get("status") != "complete_recovery_independent_audits":
        raise RuntimeError("independent recovery audits incomplete")
    for key in ("trace_audit", "live_utilization_audit", "dependency_audit"):
        if independent[key].get("status") != "complete":
            raise RuntimeError(f"{key} incomplete")

    export_status_path = recovery / "manifests/RECOVERY_STATUS.json"
    export_status = load_json(export_status_path)
    if export_status.get("hipprof_finish_count") != 1 or export_status.get("hipprof_error_count") != 0:
        raise RuntimeError("HIPProf recovery export incomplete")
    if export_status.get("source_db_sha256") != SOURCE_DB_SHA256:
        raise RuntimeError("source DB identity drift")
    if export_status.get("prepared_db_sha256") != PREPARED_DB_SHA256:
        raise RuntimeError("prepared DB identity drift")
    if export_status.get("hipprof_binary_sha256") != HIPPROF_SHA256:
        raise RuntimeError("HIPProf identity drift")

    profile = project / "perf_trace_batch8/configs/trace_targets/batch8_dual_dcu_dp2.json"
    ledger = run_root / "runtime_handoff_ledger.json"
    if sha256_file(profile) != PROFILE_SHA256 or sha256_file(ledger) != LEDGER_SHA256:
        raise RuntimeError("profile or ledger identity drift")
    direct_handoffs = {}
    for goal, expected in HANDOFF_HASHES.items():
        path = run_root / f"handoffs/{goal}.json"
        observed = sha256_file(path)
        if observed != expected:
            raise RuntimeError(f"{goal} handoff identity drift")
        direct_handoffs[goal] = {"path": str(path), "sha256": observed}

    target = project / "pra2026-bh408-gqa-page784-k5120-batch8"
    if git_output(target, "rev-parse", "HEAD") != TARGET_COMMIT:
        raise RuntimeError("target commit drift")
    if git_output(target, "branch", "--show-current") != TARGET_BRANCH:
        raise RuntimeError("target branch drift")
    if git_output(target, "status", "--porcelain=v1"):
        raise RuntimeError("target checkout is dirty")
    source_rows = []
    # The complete source list remains owned by the frozen auditor; recovery
    # records the five identities used by the runtime path without mutating it.
    source_expected = {
        "vllm/model_executor/models/qwen3_5.py": "f3c0479dbc37a8794c4d6b1c4c01906ae341b3276ed43e588c17d92b1ddb94d6",
        "vllm/model_executor/models/qwen3_next.py": "5a14b14a40fcf6382f9a20be4ca0f850b2b19b2840a3c57488821f0952d96053",
        "vllm/v1/worker/gpu_model_runner.py": "d63424d3cbe81bfaa2c0967a5c81b8c980c2d76bc7eb3b2f8fe2a079af825bce",
        "vllm/utils/nvtx_pytorch_hooks.py": "e9711444f33242ce1864d6a32d051bbf0ba0b37b5f17965de6e5dbba0c0c75ff",
        "vllm/compilation/wrapper.py": "b4dca93456e945ce8231e9a954792c8f687d5d48b427ed38bfb96011015d4090",
    }
    for relative, expected in source_expected.items():
        path = target / relative
        observed = sha256_file(path)
        if observed != expected:
            raise RuntimeError(f"target source drift: {relative}")
        source_rows.append({"relative_path": relative, **file_ref(path)})

    logical_paths = {
        "full_request_profile_metadata": artifact / "capture/full_request_profile_metadata.json",
        "process_trace_summary": artifact / "trace/process_trace_summary.json",
        "live_utilization_summary": artifact / "alignment/live_utilization_summary.json",
        "fresh_run_dependency_adapter": artifact / "dependency/fresh_run_dependency_adapter.json",
        "bound_target_sidecar": artifact / "contract/r07_bound_target_sidecar.json",
        "raw_inventory": artifact / "capture/raw_inventory.json",
        "recovery_lifecycle": artifact / "capture/lifecycle.json",
        "independent_recovery_audits": independent_path,
        "db_recovery_export_status": export_status_path,
    }
    logical = {name: file_ref(path) for name, path in logical_paths.items()}
    monitor_text = args.monitor_snapshot.read_text(encoding="utf-8", errors="replace")
    remote_terminal = "original_hipprof_terminal" in monitor_text
    monitor_ref = file_ref(args.monitor_snapshot)
    skill_path = project / "perf_trace_batch8/skills/qwen-dcu-workflow05-full-request-process-trace/SKILL.md"
    skill_drift = {
        "expected_attempt043_sha256": "50f5985cdb91765f452fd607fab630b4d268f36e539a419823b0550609acbc9f",
        "current_sha256": sha256_file(skill_path),
        "classification": "post_capture_project_skill_text_drift",
        "runtime_parser_sources_modified": False,
    }

    lineage = {
        "schema_version": 1,
        "status": "complete_recovered_offline",
        "runtime_run_id": RUN_ID,
        "source_runtime_attempt_id": ATTEMPT_ID,
        "lineage_id": RUN_ID,
        "trace_profile_sha256": PROFILE_SHA256,
        "cumulative_runtime_ledger_sha256": LEDGER_SHA256,
        "direct_predecessor_handoffs": direct_handoffs,
        "target": {"path": str(target), "commit": TARGET_COMMIT, "branch": TARGET_BRANCH, "clean": True},
        "target_source_files": source_rows,
        "source_database": {"sha256": SOURCE_DB_SHA256, "immutable": True, "snapshot_kind": "open_writer_insurance_snapshot"},
        "derived_table_recovery": {"prepared_database_sha256": PREPARED_DB_SHA256, "device_access": False},
        "hipprof_offline_export": {"binary_sha256": HIPPROF_SHA256, "terminal_event_count": 68_323_944, "finish_count": 1, "error_count": 0, "device_access": False},
        "logical_outputs": logical,
        "project_skill_drift": skill_drift,
        "external_runtime_evidence_consumed": False,
        "cross_attempt_runtime_evidence_consumed": False,
    }
    write_json_exclusive(lineage_path, lineage)

    completion = {
        "schema_version": 1,
        "status": "complete_recovered_offline",
        "execution_status": "complete",
        "evidence_status": "complete",
        "coverage_target_met": True,
        "runtime_run_id": RUN_ID,
        "source_runtime_attempt_id": ATTEMPT_ID,
        "lineage_id": RUN_ID,
        "trace_profile_sha256": PROFILE_SHA256,
        "source_lineage": file_ref(lineage_path),
        "trace_audit": independent["trace_audit"],
        "live_utilization_audit": independent["live_utilization_audit"],
        "dependency_audit": independent["dependency_audit"],
        "all_local_recovery_processes_terminated": True,
        "remote_original_hipprof_terminal": remote_terminal,
        "remote_original_hipprof_monitor": monitor_ref,
        "native_controller_lifecycle_completion_claimed": False,
        "native_durable_nfs_completion_claimed": False,
        "recovery_completion_claimed": True,
        "advance_boundary": "R08 may consume recovered observed timing only with explicit recovery admission; native lifecycle completion remains pending",
    }
    write_json_exclusive(completion_path, completion)

    manifest_entries = []
    for path in sorted({*logical_paths.values(), lineage_path, completion_path}, key=str):
        manifest_entries.append(file_ref(path))
    manifest = {
        "schema_version": 1,
        "status": "complete_recovered_offline",
        "runtime_run_id": RUN_ID,
        "source_runtime_attempt_id": ATTEMPT_ID,
        "entry_count": len(manifest_entries),
        "entries": manifest_entries,
        "large_recovery_sha256sums": file_ref(recovery / "manifests/SHA256SUMS"),
        "native_artifact_manifest_claimed": False,
    }
    write_json_exclusive(manifest_path, manifest)

    handoff = {
        "schema_version": 1,
        "status": "complete_recovered_offline",
        "execution_status": "complete",
        "evidence_status": "complete",
        "coverage_target_met": True,
        "next_authorization_required": False,
        "runtime_branch": "workflow01-10-fresh-e2e",
        "runtime_goal": "R07",
        "runtime_run_id": RUN_ID,
        "source_runtime_attempt_id": ATTEMPT_ID,
        "recovery_attempt_id": "batch8-dp2-fresh-003-R07-attempt-043-offline-recovery-001",
        "lineage_id": RUN_ID,
        "trace_profile_sha256": PROFILE_SHA256,
        "cumulative_runtime_ledger_sha256": LEDGER_SHA256,
        **{f"{goal.lower()}_handoff_sha256": value for goal, value in HANDOFF_HASHES.items()},
        "full_request_profile_metadata_sha256": logical["full_request_profile_metadata"]["sha256"],
        "process_trace_summary_sha256": logical["process_trace_summary"]["sha256"],
        "fresh_run_dependency_adapter_sha256": logical["fresh_run_dependency_adapter"]["sha256"],
        "live_utilization_summary_sha256": logical["live_utilization_summary"]["sha256"],
        "bound_target_sidecar_sha256": logical["bound_target_sidecar"]["sha256"],
        "source_lineage_sha256": sha256_file(lineage_path),
        "recovery_completion_audit_sha256": sha256_file(completion_path),
        "recovery_artifact_manifest_sha256": sha256_file(manifest_path),
        "source_db_sha256": SOURCE_DB_SHA256,
        "prepared_db_sha256": PREPARED_DB_SHA256,
        "hipprof_binary_sha256": HIPPROF_SHA256,
        "hipprof_terminal_event_count": 68_323_944,
        "all_local_recovery_processes_terminated": True,
        "remote_original_hipprof_terminal": remote_terminal,
        "remote_original_hipprof_monitor": monitor_ref,
        "native_controller_lifecycle_completion_claimed": False,
        "native_durable_nfs_completion_claimed": False,
        "recovery_mode": "db43_open_writer_snapshot_offline_recovery",
        "recovery_outputs": logical,
        "source_lineage": file_ref(lineage_path),
        "completion_audit": file_ref(completion_path),
        "artifact_manifest": file_ref(manifest_path),
        "advance_decision": {
            "next_runtime_goal": "R08",
            "authorized": True,
            "condition": "successor explicitly admits complete_recovered_offline R07 evidence",
        },
    }
    write_json_exclusive(handoff_path, handoff)
    print(json.dumps({
        "status": handoff["status"],
        "handoff": file_ref(handoff_path),
        "remote_original_hipprof_terminal": remote_terminal,
        "trace_audit": independent["trace_audit"]["status"],
        "live_audit": independent["live_utilization_audit"]["status"],
        "dependency_audit": independent["dependency_audit"]["status"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
