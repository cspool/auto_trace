#!/usr/bin/env python3
"""Build truthful recovery lifecycle and raw inventory for R07 attempt-043."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time


RUN_ID = "batch8-dp2-fresh-003"
ATTEMPT_ID = "batch8-dp2-fresh-003-R07-attempt-043"
SOURCE_DB_SHA256 = "0ea77cdac40926182c4e04fc29e687e62df9b2cac50296c7e399817c583690b0"
PREPARED_DB_SHA256 = "14a1e21b4bf5a0b29b11a62c4d000cac4979aa5af4ddc687f614bdab4f3179cd"
HIPPROF_SHA256 = "53f67d3dd4c1fe5aa9850f58d174ecf9f2c688f1e07519b456b19ca699c57f22"
TERMINAL_EVENT_COUNT = 68_323_944
EXPECTED_PFTRACE_COUNT = 139
EXPECTED_PFTRACE_BYTES = 14_961_678_057


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_exclusive(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)


def file_row(path: Path, raw_root: Path, role: str) -> dict:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"raw member is not a regular file: {path}")
    return {
        "relative_path": path.relative_to(raw_root).as_posix(),
        "path": str(path),
        "size": path.stat().st_size,
        "mode": path.stat().st_mode & 0o7777,
        "sha256": sha256_file(path),
        "role": role,
        "recovery_storage_path": str(path.resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--recovery-root", required=True, type=Path)
    parser.add_argument("--monitor-log", required=True, type=Path)
    args = parser.parse_args()

    artifact_root = args.artifact_root
    recovery_root = args.recovery_root
    monitor_log = args.monitor_log
    raw_root = artifact_root / "capture/raw"
    lifecycle_path = artifact_root / "capture/lifecycle.json"
    inventory_path = artifact_root / "capture/raw_inventory.json"
    if lifecycle_path.exists() or inventory_path.exists():
        raise RuntimeError("refusing to overwrite recovery lifecycle or raw inventory")

    prepared_manifest = load_json(recovery_root / "control/prepared_db_manifest_pristine.json")
    export_status = load_json(recovery_root / "manifests/RECOVERY_STATUS.json")
    sidecar_path = artifact_root / "contract/r07_bound_target_sidecar.json"
    sidecar = load_json(sidecar_path)
    driver_path = artifact_root / "capture/workload/driver.json"
    driver = load_json(driver_path)
    anchors_path = artifact_root / "live_utilization/clock_anchors.json"
    anchors = load_json(anchors_path)

    if prepared_manifest["source_sha256_before"] != SOURCE_DB_SHA256:
        raise RuntimeError("source DB identity drift")
    if prepared_manifest["source_sha256_after"] != SOURCE_DB_SHA256:
        raise RuntimeError("source DB changed during preparation")
    if prepared_manifest["prepared_sha256"] != PREPARED_DB_SHA256:
        raise RuntimeError("prepared DB identity drift")
    if prepared_manifest["quick_check"] != "ok":
        raise RuntimeError("prepared DB quick_check failed")
    if prepared_manifest["trace_counter_rows"] != 25:
        raise RuntimeError("TRACE_COUNTER row count drift")
    if sorted(prepared_manifest["hiptxops_rows"].values()) != [234444, 234832]:
        raise RuntimeError("HIPTXOPS row counts drift")
    if export_status["source_db_sha256"] != SOURCE_DB_SHA256:
        raise RuntimeError("export source identity drift")
    if export_status["prepared_db_sha256"] != PREPARED_DB_SHA256:
        raise RuntimeError("export prepared identity drift")
    if export_status["hipprof_binary_sha256"] != HIPPROF_SHA256:
        raise RuntimeError("HIPProf binary identity drift")
    if export_status["terminal_event_count"] != TERMINAL_EVENT_COUNT:
        raise RuntimeError("terminal event count drift")
    if export_status["hipprof_finish_count"] != 1 or export_status["hipprof_error_count"] != 0:
        raise RuntimeError("HIPProf terminal status is not clean")
    if sidecar.get("status") != "complete" or sidecar.get("target_count") != 13_568:
        raise RuntimeError("bound target sidecar is incomplete")
    if sidecar.get("bound_request_phase_count") != 16 or sidecar.get("marker_coverage_fraction") != 1.0:
        raise RuntimeError("bound target sidecar coverage drift")
    if driver.get("status") != "complete" or driver.get("completed") != 8 or driver.get("failed") != 0:
        raise RuntimeError("captured workload is incomplete")
    if anchors.get("status") != "complete" or anchors.get("runtime_attempt_id") != ATTEMPT_ID:
        raise RuntimeError("live-util anchors are incomplete")
    samples_path = artifact_root / "live_utilization/raw_samples.csv"
    gaps_path = artifact_root / "live_utilization/raw_gap_intervals.csv"
    if sha256_file(samples_path) != anchors["raw_samples_sha256"]:
        raise RuntimeError("live-util sample hash drift")
    if sha256_file(gaps_path) != anchors["raw_gap_intervals_sha256"]:
        raise RuntimeError("live-util gap hash drift")

    database = raw_root / "capture.db"
    if sha256_file(database) != PREPARED_DB_SHA256:
        raise RuntimeError("canonical recovery DB is not the pristine prepared DB")
    pf_pattern = re.compile(r"capture_([1-9][0-9]*)\.pftrace")
    pftrace = []
    for path in raw_root.glob("*.pftrace"):
        match = pf_pattern.fullmatch(path.name)
        if match is None:
            raise RuntimeError(f"unexpected PFTrace name: {path.name}")
        pftrace.append((int(match.group(1)), path))
    pftrace.sort()
    if [ordinal for ordinal, _ in pftrace] != list(range(1, EXPECTED_PFTRACE_COUNT + 1)):
        raise RuntimeError("PFTrace sequence is not contiguous")
    if any(path.stat().st_size <= 0 for _, path in pftrace):
        raise RuntimeError("empty PFTrace member")
    if sum(path.stat().st_size for _, path in pftrace) != EXPECTED_PFTRACE_BYTES:
        raise RuntimeError("PFTrace byte total drift")

    roles = {
        "capture.db": "required_primary_database",
        "capture.log": "capture_log",
        "service.log": "service_log",
        "service_start_validation.json": "service_start_validation",
        "capture.db.hipkernel.csv": "known_auxiliary_hipkernel",
        "capture.db.hiptrace.csv": "known_auxiliary_hiptrace",
        "capture.db.hsatrace.csv": "known_auxiliary_hsatrace",
    }
    raw_rows = []
    for path in sorted(raw_root.iterdir(), key=lambda item: item.name):
        if path.name in roles:
            role = roles[path.name]
        elif pf_pattern.fullmatch(path.name):
            role = "required_primary_pftrace_segment"
        else:
            raise RuntimeError(f"unknown raw recovery member: {path.name}")
        raw_rows.append(file_row(path, raw_root, role))

    monitor_text = monitor_log.read_text(encoding="utf-8", errors="replace")
    remote_terminal = "original_hipprof_terminal" in monitor_text
    now_ns = time.time_ns()
    lifecycle = {
        "schema_version": 1,
        "status": "recovery_complete_remote_original_terminal" if remote_terminal else "recovery_complete_remote_original_active",
        "runtime_run_id": RUN_ID,
        "runtime_attempt_id": ATTEMPT_ID,
        "lineage_id": RUN_ID,
        "recovery_kind": "open_writer_insurance_db_derived_table_reconstruction_and_offline_pftrace_export",
        "source_db_sha256": SOURCE_DB_SHA256,
        "source_db_immutable": True,
        "prepared_db_sha256": PREPARED_DB_SHA256,
        "hipprof_binary_sha256": HIPPROF_SHA256,
        "local_recovery_processes_terminated": True,
        "remote_original_hipprof_terminal": remote_terminal,
        "all_started_processes_terminated": remote_terminal,
        "device_access_performed_by_recovery": False,
        "model_reexecution_performed": False,
        "recovery_completed_epoch_ns": now_ns,
        "workload_driver": {"path": str(driver_path), "sha256": sha256_file(driver_path)},
        "live_utilization": {
            "anchors_path": str(anchors_path),
            "sample_count": anchors["sample_count"],
            "gap_interval_count": anchors["gap_interval_count"],
            "raw_samples_sha256": anchors["raw_samples_sha256"],
            "raw_gap_intervals_sha256": anchors["raw_gap_intervals_sha256"],
        },
        "bound_target_sidecar": {
            "path": str(sidecar_path),
            "sha256": sha256_file(sidecar_path),
            "target_count": sidecar["target_count"],
        },
        "remote_monitor_log": {"path": str(monitor_log), "sha256": sha256_file(monitor_log)},
        "formal_native_lifecycle_claimed": False,
        "formal_durable_nfs_completion_claimed": False,
    }
    inventory = {
        "schema_version": 1,
        "status": "complete_recovered_offline",
        "runtime_run_id": RUN_ID,
        "runtime_attempt_id": ATTEMPT_ID,
        "lineage_id": RUN_ID,
        "recovery_kind": lifecycle["recovery_kind"],
        "raw_files": raw_rows,
        "required_primary_database_count": 1,
        "required_primary_pftrace_logical_family_count": 1,
        "required_primary_pftrace_mode": "native_segmented",
        "required_primary_pftrace_file_count": len(pftrace),
        "required_primary_pftrace_ordered_paths": [path.name for _, path in pftrace],
        "required_primary_pftrace_total_size": EXPECTED_PFTRACE_BYTES,
        "unknown_raw_files": [],
        "unknown_raw_file_count": 0,
        "raw_sample_count": anchors["sample_count"],
        "raw_gap_interval_count": anchors["gap_interval_count"],
        "bound_target_sidecar_sha256": sha256_file(sidecar_path),
        "source_db_sha256": SOURCE_DB_SHA256,
        "prepared_db_sha256": PREPARED_DB_SHA256,
        "all_recovery_bytes_hashed": True,
        "source_db_unchanged": True,
        "device_access_performed_by_recovery": False,
        "formal_native_inventory_claimed": False,
    }
    write_json_exclusive(lifecycle_path, lifecycle)
    write_json_exclusive(inventory_path, inventory)
    print(json.dumps({
        "status": inventory["status"],
        "remote_original_terminal": remote_terminal,
        "raw_file_count": len(raw_rows),
        "pftrace_count": len(pftrace),
        "pftrace_bytes": EXPECTED_PFTRACE_BYTES,
        "live_sample_count": anchors["sample_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
