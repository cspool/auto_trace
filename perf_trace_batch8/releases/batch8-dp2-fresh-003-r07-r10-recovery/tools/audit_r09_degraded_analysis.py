#!/usr/bin/env python3
"""Independently audit the degraded R09 twelve-table analysis."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TABLE_ORDER = [
    "request_timeline",
    "process_timeline",
    "kernel_timeline",
    "live_utilization_aligned",
    "process_live_utilization",
    "kernel_concurrency",
    "queue_concurrency",
    "launch_gaps",
    "high_latency_processes",
    "dependency_state",
    "traffic_resource_attachment",
    "opportunity_candidates",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    return {"path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def write_json_x(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists(), f"immutable audit output exists: {path}")
    temporary = path.with_name(f".{path.name}.partial.{os.getpid()}")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def scan_table(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(record["path"])
    require(path.is_file(), f"table missing: {path}")
    require(path.stat().st_size == record["size_bytes"], f"table size drift: {path}")
    require(sha256_file(path) == record["sha256"], f"table hash drift: {path}")
    availability: Counter[str] = Counter()
    facts: dict[str, Any] = {}
    rows = 0
    request_ids: Counter[str] = Counter()
    source_ids: set[str] | None = set() if record["logical_name"] != "live_utilization_aligned" else None
    record_kinds: Counter[str] = Counter()
    candidate_states: Counter[str] = Counter()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == record["ordered_schema"], f"schema drift: {path}")
        for row in reader:
            rows += 1
            state = row.get("availability_state", "")
            if state:
                availability[state] += 1
            request_id = row.get("request_id", "")
            if request_id:
                request_ids[request_id] += 1
            kind = row.get("record_kind", row.get("source_record_kind", ""))
            if kind:
                record_kinds[kind] += 1
            if source_ids is not None:
                identity = row.get("source_row_id", "")
                if identity:
                    require(identity not in source_ids or record["logical_name"] in {"traffic_resource_attachment"}, f"unexpected duplicate source identity: {record['logical_name']}/{identity}")
                    source_ids.add(identity)
            name = record["logical_name"]
            if name == "kernel_timeline":
                require(int(row["begin_ns"]) < int(row["end_ns"]), "non-positive kernel interval")
            elif name == "live_utilization_aligned":
                require(row["record_kind"] in {"sample", "gap", "anchor"}, "unknown live record kind")
                if row["record_kind"] == "sample":
                    require(row["se_active_cu_pct"] != "", "sample utilization missing")
                else:
                    require(row["se_active_cu_pct"] == "", "non-sample utilization fabricated")
            elif name in {"kernel_concurrency", "queue_concurrency"}:
                if row["scope_kind"] == "per_rank_native_device":
                    active_ids = json.loads(row["active_kernel_ids_json"])
                    queues = json.loads(row["active_queue_ids_json"])
                    require(len(active_ids) == int(row["active_kernel_count"]), "active kernel membership drift")
                    require(len(queues) == int(row["active_queue_count"]), "active queue membership drift")
                    require(int(row["begin_ns"]) < int(row["end_ns"]), "non-positive concurrency interval")
                else:
                    require(row["availability_state"].startswith("unavailable_"), "cross-device sentinel promoted")
            elif name == "launch_gaps":
                gap = int(row["gap_ns"])
                overlap = int(row["overlap_ns"])
                require(gap == 0 or overlap == 0, "launch gap/overlap double counted")
            elif name == "traffic_resource_attachment":
                if row["metric_value"]:
                    float(row["metric_value"])
                    require(row["evidence_class"] == "replay_projected_R08_hardware_attribute", "numeric traffic attribute evidence drift")
                    require(row["shared_physical_capture"] == "True", "shared capture flag missing")
                else:
                    require(row["availability_state"].startswith("unavailable_"), "missing metric not unavailable")
            elif name == "opportunity_candidates":
                candidate_states[row["candidate_state"]] += 1
                require(row["claim_scope"] in {"investigation_hypothesis_not_root_cause_or_speedup_prediction", "coverage_sentinel_not_a_logical_process"}, "opportunity claim scope drift")
    require(rows == record["row_count"], f"row count drift: {record['logical_name']} {rows}")
    require(dict(sorted(availability.items())) == record["availability_counts"], f"availability count drift: {record['logical_name']}")
    facts.update(
        {
            "row_count": rows,
            "availability_counts": dict(sorted(availability.items())),
            "request_identity_count": len(request_ids),
            "record_kind_counts": dict(sorted(record_kinds.items())),
        }
    )
    if candidate_states:
        facts["candidate_state_counts"] = dict(sorted(candidate_states.items()))
    return file_record(path), facts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.artifact_root.resolve()
    require(root == Path(__file__).resolve().parents[1], "artifact root/tool location mismatch")
    started = time.monotonic()
    builder_path = root / "R09_BUILDER_COMPLETE.json"
    analysis_path = root / "analysis/fresh_e2e_analysis.json"
    lineage_path = root / "lineage/R09_SOURCE_LINEAGE.json"
    manifest_path = root / "artifact_manifest.json"
    for path in (builder_path, analysis_path, lineage_path, manifest_path):
        require(path.is_file(), f"R09 builder output missing: {path}")
    builder = json.loads(builder_path.read_text(encoding="utf-8"))
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(builder["status"] == "builder_complete_pending_independent_audit", "builder state drift")
    require(analysis["evidence_status"] == "degraded_R07_observed_subset", "evidence boundary drift")
    require(analysis["strict_R09_handoff_eligible"] is False, "strict R09 eligibility fabricated")
    require(analysis["formal_scheduler_handoff_created"] is False, "formal R09 handoff fabricated")
    require(analysis["complete_timeline"] is False, "declared-complete timeline fabricated")
    require(analysis["complete_observed_subset_timeline"] is True, "observed-subset completeness missing")
    require(analysis["sampling_performed"] is False, "sampling unexpectedly enabled")
    require(analysis["top_n_truncation_performed"] is False, "Top-N unexpectedly enabled")
    records = analysis["ordered_tables"]
    require(len(records) == 12, "R09 table count drift")
    require([record["logical_name"] for record in records] == TABLE_ORDER, "R09 table order drift")
    results = {}
    for record in records:
        _, facts = scan_table(record)
        results[record["logical_name"]] = facts
        print(f"R09 audit table={record['logical_name']} rows={facts['row_count']}", flush=True)
    expected_rows = {
        "request_timeline": 320,
        "process_timeline": 3920,
        "kernel_timeline": 6520,
        "live_utilization_aligned": 2357674,
        "process_live_utilization": 3920,
        "kernel_concurrency": 6526,
        "queue_concurrency": 6526,
        "launch_gaps": 6515,
        "high_latency_processes": 391,
        "dependency_state": 9352,
        "traffic_resource_attachment": 30712,
        "opportunity_candidates": 3921,
    }
    require({name: facts["row_count"] for name, facts in results.items()} == expected_rows, "R09 denominator map drift")
    require(results["request_timeline"]["request_identity_count"] == 5, "request identity count drift")
    require(results["live_utilization_aligned"]["record_kind_counts"] == {"anchor": 2, "gap": 374, "sample": 2357298}, "live record conservation failed")
    require(results["process_live_utilization"]["availability_counts"] == {"available": 1318, "unavailable_intrinsic_short_window": 2586, "unavailable_sampling_gap": 16}, "process utilization availability drift")
    require(results["kernel_concurrency"]["availability_counts"]["unavailable_cross_device_clock_alignment_not_proven"] == 5, "kernel concurrency sentinel drift")
    require(results["queue_concurrency"]["availability_counts"]["unavailable_cross_device_clock_alignment_not_proven"] == 5, "queue concurrency sentinel drift")
    require(lineage["strict_R09_handoff_created"] is False, "lineage strict handoff drift")
    require(lineage["predecessor_artifacts_modified"] is False, "predecessor mutation declared")
    require(manifest["strict_scheduler_handoff_included"] is False, "scheduler handoff entered manifest")
    require(not (root.parents[2] / "handoffs/R09.json").exists(), "formal R09 handoff unexpectedly exists")
    audit = {
        "schema_version": 1,
        "status": "complete",
        "audit_scope": "R09_degraded_observed_subset_not_strict_scheduler_R09",
        "finished_utc": utc_now(),
        "elapsed_seconds": time.monotonic() - started,
        "runtime_run_id": analysis["runtime_run_id"],
        "lineage_id": analysis["lineage_id"],
        "evidence_status": analysis["evidence_status"],
        "strict_R09_handoff_eligible": False,
        "formal_scheduler_handoff_created": False,
        "table_count": 12,
        "table_audits": results,
        "full_request_analysis": file_record(analysis_path),
        "source_lineage": file_record(lineage_path),
        "artifact_manifest": file_record(manifest_path),
        "builder_marker": file_record(builder_path),
        "coverage": analysis["coverage"],
        "observed_subset_table_conservation": True,
        "declared_target_coverage_complete": False,
        "sampling_performed": False,
        "top_n_truncation_performed": False,
        "dcu_accessed": False,
    }
    audit_path = root / "validation/R09_COMPLETION_AUDIT.json"
    write_json_x(audit_path, audit)
    complete = {
        "schema_version": 1,
        "status": "complete",
        "execution_status": "complete",
        "evidence_status": "degraded_R07_observed_subset",
        "finished_utc": utc_now(),
        "table_count": 12,
        "table_row_counts": expected_rows,
        "full_request_analysis": file_record(analysis_path),
        "source_lineage": file_record(lineage_path),
        "artifact_manifest": file_record(manifest_path),
        "completion_audit": file_record(audit_path),
        "strict_R09_handoff_created": False,
        "strict_R10_authorized": False,
        "degraded_R10_offline_reporting_authorized_by_user_request": True,
        "dcu_accessed": False,
    }
    complete_path = root / "R09_DEGRADED_ANALYSIS_COMPLETE.json"
    write_json_x(complete_path, complete)
    print(json.dumps(complete, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
