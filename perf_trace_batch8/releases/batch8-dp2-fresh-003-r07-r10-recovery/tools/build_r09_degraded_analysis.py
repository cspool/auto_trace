#!/usr/bin/env python3
"""Build the CPU-only R09 twelve-table observed-subset recovery analysis.

This is deliberately not a strict scheduler R09 implementation: the sealed
R07 source contains only 31.25% of the declared marker target universe.  The
builder preserves that evidence boundary while producing deterministic,
offline-consumable tables from the available R07 clock and R08 replay-
projected attributes.
"""

from __future__ import annotations

import argparse
import csv
import functools
import gzip
import hashlib
import io
import json
import math
import os
import re
import shutil
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


RUN_ID = "batch8-dp2-fresh-003"
LINEAGE_ID = RUN_ID
TRACE_PROFILE_SHA256 = "3b4c952063f48ae662b48b5ce9d8fd76e0ac4d74e170bdb1839ae8b1aaa23cce"
RUNTIME_ATTEMPT_ID = f"{RUN_ID}-R07-attempt-020"
SCHEMA_VERSION = 1
NULL_ENCODING = ""

RUN_ROOT = Path(
    "/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/runtime/"
    f"workflow01-10-fresh-e2e/{RUN_ID}"
)
R07_NORM = RUN_ROOT / "artifacts/R07/recovery/db_first_normalization_003"
R07_POST = RUN_ROOT / "artifacts/R07/recovery/db_first_postprocess_001"
R08_NORM = RUN_ROOT / "artifacts/R08/observed_subset_replay_001/normalized_003"
R07_ANCHORS = RUN_ROOT / "artifacts/R07/resume-019/live_utilization/clock_anchors.json"

REQUESTS = R07_NORM / "trace/request_ranges.csv"
PROCESSES = R07_NORM / "trace/process_ranges.csv"
KERNELS = R07_NORM / "trace/strict_owned_kernels.csv"
LIVE_SAMPLES = R07_POST / "alignment/r07_live_utilization_aligned.csv"
LIVE_GAPS = R07_POST / "alignment/r07_live_utilization_gaps.csv"
PROCESS_LIVE = R07_POST / "alignment/r07_process_live_utilization.csv"
DEPENDENCY = R07_POST / "dependency/fresh_run_dependency_adapter.csv"
R07_SUMMARY = R07_NORM / "trace/process_trace_summary.json"
R07_LIVE_SUMMARY = R07_POST / "alignment/live_utilization_summary.json"
R07_RECOVERY = R07_POST / "DB_FIRST_R07_RECOVERY_COMPLETE.json"
R07_LINEAGE = R07_POST / "lineage/DB_FIRST_R07_SOURCE_LINEAGE.json"
R08_HANDOFF = R08_NORM / "R08_DEGRADED_HANDOFF.json"
R08_METRICS = R08_NORM / "kernel_metrics.csv"
R08_METHODOLOGY = R08_NORM / "methodology.json"
R08_SEMANTIC_MISSINGNESS = R08_NORM / "semantic_missingness.json"

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

R08_METRIC_MODE = {
    "GPUBusy_pct": "pmc",
    "VALUBusy_pct": "pmc",
    "LDSBankConflict_pct": "pmc",
    "MemUnitStalled_pct": "pmc",
    "MemUnitBusy_pct": "pmc",
    "WriteUnitStalled_pct": "pmc",
    "L2CacheHit_pct": "pmc",
    "L2_hit_count": "pmc",
    "L2_miss_count": "pmc",
    "SQ_INSTS_VALU_sum": "pmc",
    "SQ_INSTS_VMEM_RD_sum": "pmc",
    "SQ_INSTS_VMEM_WR_sum": "pmc",
    "SQ_INSTS_LDS_sum": "pmc",
    "flat_read_wavefronts_sum": "pmc_read",
    "read_requests_sum": "pmc_read",
    "read_requests_32B_subset_sum": "pmc_read",
    "flat_write_wavefronts_sum": "pmc_write",
    "write_requests_sum": "pmc_write",
    "write_requests_64B_subset_sum": "pmc_write",
}

R08_METRIC_UNIT = {
    name: ("percent" if name.endswith("_pct") else "counter_sum")
    for name in R08_METRIC_MODE
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


@functools.lru_cache(maxsize=None)
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def stable_id(prefix: str, *values: Any) -> str:
    payload = "\0".join(str(value) for value in values).encode()
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()}"


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists(), f"immutable output already exists: {path}")
    temporary = path.with_name(f".{path.name}.partial.{os.getpid()}")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames is not None, f"missing CSV header: {path}")
        return list(reader.fieldnames), list(reader)


def write_csv_atomic(
    path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]
) -> tuple[int, Counter[str]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists(), f"immutable output already exists: {path}")
    temporary = path.with_name(f".{path.name}.partial.{os.getpid()}")
    count = 0
    availability: Counter[str] = Counter()
    with temporary.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
            if "availability_state" in row:
                availability[str(row["availability_state"])] += 1
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return count, availability


def file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def request_ordinal(request_id: str) -> str:
    match = re.search(r"-req-(\d{3})-", request_id)
    return str(int(match.group(1))) if match else ""


def kernel_family(name: str) -> str:
    if name == "_gqa6":
        return "gqa6"
    if name == "triton_red_fused__to_copy_add_mean_mul_pow_rsqrt_0":
        return "triton_rmsnorm"
    if name.startswith("chunk_"):
        return "chunk_group"
    if name.startswith("Cijk_"):
        return "gemm"
    if "elementwise" in name or name.startswith("triton_poi_"):
        return "elementwise"
    if "conv1d" in name:
        return "convolution"
    return "other"


def common_fields(source_path: Path, source_sha: str, source_row_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "runtime_run_id": RUN_ID,
        "lineage_id": LINEAGE_ID,
        "trace_profile_sha256": TRACE_PROFILE_SHA256,
        "source_path": str(source_path),
        "source_sha256": source_sha,
        "source_row_id": source_row_id,
    }


def table_record(
    name: str,
    path: Path,
    row_count: int,
    schema: list[str],
    availability: Counter[str],
    stable_sort_key: list[str],
    evidence_classes: list[str],
) -> dict[str, Any]:
    return {
        "logical_name": name,
        **file_record(path),
        "row_count": row_count,
        "ordered_schema": schema,
        "schema_sha256": canonical_sha256(schema),
        "stable_sort_key": stable_sort_key,
        "encoding": "UTF-8",
        "line_ending": "LF",
        "csv_null_encoding": NULL_ENCODING,
        "lineage_id": LINEAGE_ID,
        "evidence_classes": evidence_classes,
        "availability_counts": dict(sorted(availability.items())),
    }


def build_request_table(
    output: Path, source_sha: str
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    source_header, source_rows = read_csv_rows(REQUESTS)
    occurrence: Counter[tuple[str, str, str]] = Counter()
    rows = []
    for source in sorted(
        source_rows,
        key=lambda row: (int(row["begin_ns"]), int(row["dp_rank"]), row["range_id"]),
    ):
        key = (source["request_id"], source["dp_rank"], source["native_device"])
        occurrence[key] += 1
        rows.append(
            {
                **common_fields(REQUESTS, source_sha, source["range_id"]),
                "source_record_kind": "repeated_layer_scope_request_marker",
                "measured_request_ordinal": request_ordinal(source["request_id"]),
                "request_marker_occurrence": occurrence[key],
                "availability_state": "available_observed_subset",
                "availability_reason": "R07 contains repeated layer-scope request markers for 5 of 8 request identities",
                **source,
            }
        )
    fields = [
        "schema_version",
        "runtime_run_id",
        "lineage_id",
        "trace_profile_sha256",
        "source_path",
        "source_sha256",
        "source_row_id",
        "source_record_kind",
        "measured_request_ordinal",
        "request_marker_occurrence",
        "availability_state",
        "availability_reason",
        *source_header,
    ]
    count, availability = write_csv_atomic(output, fields, rows)
    require(count == 320, f"request row denominator drift: {count}")
    require(len({row["request_id"] for row in rows}) == 5, "request identity denominator drift")
    return (
        table_record(
            "request_timeline",
            output,
            count,
            fields,
            availability,
            ["begin_ns", "dp_rank", "range_id"],
            ["observed_r07_timing", "degraded_observed_subset"],
        ),
        source_rows,
    )


def build_process_table(
    output: Path, source_sha: str
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    source_header, source_rows = read_csv_rows(PROCESSES)
    source_rows.sort(key=lambda row: (int(row["begin_ns"]), -int(row["depth"]), row["process_range_id"]))
    rows = []
    for source in source_rows:
        rows.append(
            {
                **common_fields(PROCESSES, source_sha, source["process_range_id"]),
                "source_record_kind": source["target_kind"],
                "measured_request_ordinal": request_ordinal(source["request_id"]),
                "no_direct_kernel_state": (
                    "explicit_no_direct_kernel"
                    if source["explicit_no_kernel_target"] == "True"
                    else "kernel_expectation_present"
                ),
                "availability_state": "available_observed_subset",
                "availability_reason": "",
                **source,
            }
        )
    fields = [
        "schema_version",
        "runtime_run_id",
        "lineage_id",
        "trace_profile_sha256",
        "source_path",
        "source_sha256",
        "source_row_id",
        "source_record_kind",
        "measured_request_ordinal",
        "no_direct_kernel_state",
        "availability_state",
        "availability_reason",
        *source_header,
    ]
    count, availability = write_csv_atomic(output, fields, rows)
    require(count == 3920, f"process row denominator drift: {count}")
    return (
        table_record(
            "process_timeline",
            output,
            count,
            fields,
            availability,
            ["begin_ns", "depth desc", "process_range_id"],
            ["observed_r07_timing", "degraded_observed_subset"],
        ),
        source_rows,
    )


def load_r08_metrics() -> tuple[dict[tuple[str, str], dict[str, str]], str, dict[str, Any]]:
    source_sha = sha256_file(R08_METRICS)
    _, rows = read_csv_rows(R08_METRICS)
    selected = {
        (row["kernel_name"], row["gpu_id"]): row
        for row in rows
        if row["scope_kind"] == "kernel" and row["gpu_id"] in {"0", "1"}
    }
    methodology = json.loads(R08_METHODOLOGY.read_text(encoding="utf-8"))
    return selected, source_sha, methodology


def build_kernel_table(
    output: Path,
    source_sha: str,
    r08_metrics: dict[tuple[str, str], dict[str, str]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    source_header, source_rows = read_csv_rows(KERNELS)
    source_rows.sort(
        key=lambda row: (
            int(row["begin_ns"]),
            int(row["native_device"]),
            int(row["hip_runtime_index"]),
            row["kernel_instance_id"],
        )
    )
    rows = []
    for source in source_rows:
        match = r08_metrics.get((source["native_kernel_name"], source["native_device"]))
        rows.append(
            {
                **common_fields(KERNELS, source_sha, source["kernel_instance_id"]),
                "source_record_kind": "strict_owned_kernel",
                "measured_request_ordinal": request_ordinal(source["request_id"]),
                "kernel_family": kernel_family(source["native_kernel_name"]),
                "r08_attribute_join_state": (
                    "matched_replay_projected_exact_kernel_name_device"
                    if match
                    else "unavailable_no_exact_R08_kernel_name_device_match"
                ),
                "r08_physical_capture_id": (
                    f"{match['group_id']}|{source['native_kernel_name']}|gpu{source['native_device']}"
                    if match
                    else ""
                ),
                "availability_state": "available_observed_subset",
                "availability_reason": "",
                **source,
            }
        )
    fields = [
        "schema_version",
        "runtime_run_id",
        "lineage_id",
        "trace_profile_sha256",
        "source_path",
        "source_sha256",
        "source_row_id",
        "source_record_kind",
        "measured_request_ordinal",
        "kernel_family",
        "r08_attribute_join_state",
        "r08_physical_capture_id",
        "availability_state",
        "availability_reason",
        *source_header,
    ]
    count, availability = write_csv_atomic(output, fields, rows)
    require(count == 6520, f"kernel row denominator drift: {count}")
    require(len({row["kernel_instance_id"] for row in rows}) == count, "duplicate kernel identity")
    return (
        table_record(
            "kernel_timeline",
            output,
            count,
            fields,
            availability,
            ["begin_ns", "native_device", "hip_runtime_index", "kernel_instance_id"],
            ["observed_r07_timing", "replay_projected_R08_join_state"],
        ),
        source_rows,
    )


LIVE_FIELDS = [
    "schema_version",
    "runtime_run_id",
    "runtime_attempt_id",
    "lineage_id",
    "trace_profile_sha256",
    "record_kind_order",
    "record_kind",
    "source_record_id",
    "dp_rank",
    "native_device",
    "sequence",
    "begin_monotonic_ns",
    "end_monotonic_ns",
    "midpoint_monotonic_ns",
    "begin_realtime_ns",
    "end_realtime_ns",
    "midpoint_realtime_ns",
    "call_latency_ns",
    "se_active_cu_pct",
    "alignment_uncertainty_ns",
    "rsmi_status",
    "timing_eligible",
    "availability_state",
    "availability_reason",
    "previous_sequence",
    "next_sequence",
    "unobserved_gap_ns",
    "gap_threshold_ns",
    "anchor_kind",
    "pair_uncertainty_ns",
    "source_path",
    "source_sha256",
    "evidence_class",
]


def live_records(source_hashes: dict[Path, str]) -> Iterator[dict[str, Any]]:
    with LIVE_SAMPLES.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            yield {
                "schema_version": SCHEMA_VERSION,
                "runtime_run_id": row["runtime_run_id"],
                "runtime_attempt_id": row["runtime_attempt_id"],
                "lineage_id": row["lineage_id"],
                "trace_profile_sha256": TRACE_PROFILE_SHA256,
                "record_kind_order": 0,
                "record_kind": "sample",
                "source_record_id": f"sample:{row['sequence']}:{row['dp_rank']}:{row['native_device']}",
                "dp_rank": row["dp_rank"],
                "native_device": row["native_device"],
                "sequence": row["sequence"],
                "begin_monotonic_ns": row["call_begin_monotonic_ns"],
                "end_monotonic_ns": row["call_end_monotonic_ns"],
                "midpoint_monotonic_ns": row["sample_midpoint_monotonic_ns"],
                "begin_realtime_ns": row["call_begin_realtime_ns"],
                "end_realtime_ns": row["call_end_realtime_ns"],
                "midpoint_realtime_ns": row["sample_midpoint_realtime_ns"],
                "call_latency_ns": row["call_latency_ns"],
                "se_active_cu_pct": row["se_active_cu_pct"],
                "alignment_uncertainty_ns": row["alignment_uncertainty_ns"],
                "rsmi_status": row["rsmi_status"],
                "timing_eligible": row["timing_eligible"],
                "availability_state": row["sample_availability_state"],
                "availability_reason": "" if row["timing_eligible"] == "True" else "sample_not_timing_eligible",
                "previous_sequence": "",
                "next_sequence": "",
                "unobserved_gap_ns": "",
                "gap_threshold_ns": "",
                "anchor_kind": "",
                "pair_uncertainty_ns": "",
                "source_path": str(LIVE_SAMPLES),
                "source_sha256": source_hashes[LIVE_SAMPLES],
                "evidence_class": "observed_r07_live_utilization",
            }
    with LIVE_GAPS.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            yield {
                "schema_version": SCHEMA_VERSION,
                "runtime_run_id": row["runtime_run_id"],
                "runtime_attempt_id": row["runtime_attempt_id"],
                "lineage_id": row["lineage_id"],
                "trace_profile_sha256": TRACE_PROFILE_SHA256,
                "record_kind_order": 1,
                "record_kind": "gap",
                "source_record_id": f"gap:{row['dp_rank']}:{row['native_device']}:{row['previous_sequence']}:{row['next_sequence']}",
                "dp_rank": row["dp_rank"],
                "native_device": row["native_device"],
                "sequence": "",
                "begin_monotonic_ns": row["gap_begin_monotonic_ns"],
                "end_monotonic_ns": row["gap_end_monotonic_ns"],
                "midpoint_monotonic_ns": "",
                "begin_realtime_ns": "",
                "end_realtime_ns": "",
                "midpoint_realtime_ns": "",
                "call_latency_ns": row["adjacent_sample_begin_delta_ns"],
                "se_active_cu_pct": "",
                "alignment_uncertainty_ns": "",
                "rsmi_status": "",
                "timing_eligible": "False",
                "availability_state": "unavailable_sampling_gap",
                "availability_reason": "collector interval exceeded the sealed gap threshold",
                "previous_sequence": row["previous_sequence"],
                "next_sequence": row["next_sequence"],
                "unobserved_gap_ns": row["unobserved_gap_ns"],
                "gap_threshold_ns": row["gap_threshold_ns"],
                "anchor_kind": "",
                "pair_uncertainty_ns": "",
                "source_path": str(LIVE_GAPS),
                "source_sha256": source_hashes[LIVE_GAPS],
                "evidence_class": "observed_r07_live_utilization_gap",
            }
    anchors = json.loads(R07_ANCHORS.read_text(encoding="utf-8"))
    for order, kind in enumerate(("start", "end"), 2):
        anchor = anchors[kind]
        yield {
            "schema_version": SCHEMA_VERSION,
            "runtime_run_id": anchors["runtime_run_id"],
            "runtime_attempt_id": anchors["runtime_attempt_id"],
            "lineage_id": anchors["lineage_id"],
            "trace_profile_sha256": TRACE_PROFILE_SHA256,
            "record_kind_order": order,
            "record_kind": "anchor",
            "source_record_id": f"anchor:{kind}",
            "dp_rank": "",
            "native_device": "",
            "sequence": "",
            "begin_monotonic_ns": anchor["monotonic_before_ns"],
            "end_monotonic_ns": anchor["monotonic_after_ns"],
            "midpoint_monotonic_ns": anchor["monotonic_midpoint_ns"],
            "begin_realtime_ns": anchor["realtime_ns"],
            "end_realtime_ns": anchor["realtime_ns"],
            "midpoint_realtime_ns": anchor["realtime_ns"],
            "call_latency_ns": anchor["monotonic_after_ns"] - anchor["monotonic_before_ns"],
            "se_active_cu_pct": "",
            "alignment_uncertainty_ns": anchor["pair_uncertainty_ns"],
            "rsmi_status": "",
            "timing_eligible": "True",
            "availability_state": "available_anchor",
            "availability_reason": "",
            "previous_sequence": "",
            "next_sequence": "",
            "unobserved_gap_ns": "",
            "gap_threshold_ns": anchors["gap_threshold_ns"],
            "anchor_kind": kind,
            "pair_uncertainty_ns": anchor["pair_uncertainty_ns"],
            "source_path": str(R07_ANCHORS),
            "source_sha256": source_hashes[R07_ANCHORS],
            "evidence_class": "observed_r07_clock_anchor",
        }


def write_gzip_part(
    path: Path, rows: list[dict[str, Any]], ordinal: int, part_root: Path
) -> dict[str, Any]:
    marker = part_root / f"part-{ordinal:04d}.complete.json"
    if path.exists() and marker.exists():
        record = json.loads(marker.read_text(encoding="utf-8"))
        require(record["sha256"] == sha256_file(path), f"live part hash drift: {path}")
        require(record["row_count"] == len(rows), f"live part row drift: {path}")
        return record
    require(not path.exists() and not marker.exists(), f"incomplete immutable live part collision: {path}")
    temporary = path.with_name(f".{path.name}.partial.{os.getpid()}")
    with temporary.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=6, mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(text, fieldnames=LIVE_FIELDS, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
        raw.flush()
        os.fsync(raw.fileno())
    os.replace(temporary, path)
    record = {
        "schema_version": 1,
        "status": "complete",
        "part_ordinal": ordinal,
        "path": str(path),
        "row_count": len(rows),
        "first_source_record_id": rows[0]["source_record_id"],
        "last_source_record_id": rows[-1]["source_record_id"],
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    write_json_atomic(marker, record)
    record["marker_path"] = str(marker)
    record["marker_sha256"] = sha256_file(marker)
    return record


def build_live_table(
    output: Path, recovery_root: Path, source_hashes: dict[Path, str]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    part_root = recovery_root / "live_utilization_parts"
    part_root.mkdir(parents=True, exist_ok=True)
    part_size = 100000
    parts: list[dict[str, Any]] = []
    batch: list[dict[str, Any]] = []
    availability: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    total = 0
    for row in live_records(source_hashes):
        batch.append(row)
        availability[row["availability_state"]] += 1
        kind_counts[row["record_kind"]] += 1
        total += 1
        if len(batch) == part_size:
            ordinal = len(parts) + 1
            part_path = part_root / f"part-{ordinal:04d}.csv.gz"
            parts.append(write_gzip_part(part_path, batch, ordinal, part_root))
            print(f"R09 live part={ordinal} cumulative_rows={total}", flush=True)
            batch = []
    if batch:
        ordinal = len(parts) + 1
        part_path = part_root / f"part-{ordinal:04d}.csv.gz"
        parts.append(write_gzip_part(part_path, batch, ordinal, part_root))
        print(f"R09 live part={ordinal} cumulative_rows={total}", flush=True)
    require(total == 2357674, f"live utilization combined denominator drift: {total}")
    require(kind_counts == {"sample": 2357298, "gap": 374, "anchor": 2}, f"live kinds drift: {kind_counts}")
    require(sum(part["row_count"] for part in parts) == total, "live part row conservation failed")
    require(not output.exists(), f"immutable output already exists: {output}")
    temporary = output.with_name(f".{output.name}.partial.{os.getpid()}")
    with temporary.open("x", encoding="utf-8", newline="") as destination:
        destination.write(",".join(LIVE_FIELDS) + "\n")
        for part in parts:
            with gzip.open(part["path"], "rt", encoding="utf-8", newline="") as source:
                require(source.readline().rstrip("\r\n") == ",".join(LIVE_FIELDS), "live part header drift")
                shutil.copyfileobj(source, destination, length=8 * 1024 * 1024)
        destination.flush()
        os.fsync(destination.fileno())
    os.replace(temporary, output)
    return (
        table_record(
            "live_utilization_aligned",
            output,
            total,
            LIVE_FIELDS,
            availability,
            ["record_kind_order", "source source-order"],
            [
                "observed_r07_live_utilization",
                "observed_r07_live_utilization_gap",
                "observed_r07_clock_anchor",
            ],
        ),
        parts,
    )


def build_process_live_table(output: Path, source_sha: str) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    source_header, source_rows = read_csv_rows(PROCESS_LIVE)
    source_rows.sort(key=lambda row: row["process_range_id"])
    rows = []
    mapping = {}
    for source in source_rows:
        state = source["availability_state"]
        require((state == "available") == bool(source["se_active_cu_pct_mean"]), "process live null policy drift")
        row = {
            **common_fields(PROCESS_LIVE, source_sha, source["process_range_id"]),
            "source_record_kind": "process_live_utilization",
            "availability_reason": "" if state == "available" else state,
            **source,
        }
        rows.append(row)
        mapping[source["process_range_id"]] = row
    fields = [
        "schema_version",
        "runtime_run_id",
        "lineage_id",
        "trace_profile_sha256",
        "source_path",
        "source_sha256",
        "source_row_id",
        "source_record_kind",
        "availability_reason",
        *source_header,
    ]
    count, availability = write_csv_atomic(output, fields, rows)
    require(count == 3920, f"process live denominator drift: {count}")
    require(availability == {"available": 1318, "unavailable_intrinsic_short_window": 2586, "unavailable_sampling_gap": 16}, f"process live availability drift: {availability}")
    return (
        table_record(
            "process_live_utilization",
            output,
            count,
            fields,
            availability,
            ["process_range_id"],
            ["observed_r07_live_utilization", "unavailable"],
        ),
        mapping,
    )


def sweep_segments(
    kernels: list[dict[str, str]], include_queues: bool
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in kernels:
        groups[(row["request_id"], row["dp_rank"], row["native_device"])].append(row)
    result: list[dict[str, Any]] = []
    for (request_id, rank, device), group in sorted(groups.items()):
        by_time: dict[int, dict[str, list[str]]] = defaultdict(lambda: {"start": [], "end": []})
        lookup = {row["kernel_instance_id"]: row for row in group}
        for row in group:
            by_time[int(row["begin_ns"])]["start"].append(row["kernel_instance_id"])
            by_time[int(row["end_ns"])]["end"].append(row["kernel_instance_id"])
        times = sorted(by_time)
        active: set[str] = set()
        for index, current in enumerate(times[:-1]):
            for kernel_id in sorted(by_time[current]["end"]):
                active.discard(kernel_id)
            for kernel_id in sorted(by_time[current]["start"]):
                active.add(kernel_id)
            following = times[index + 1]
            if not active or following <= current:
                continue
            active_ids = sorted(active)
            active_hash = canonical_sha256(active_ids)
            queues = sorted({f"{lookup[k]['queue_id']}:{lookup[k]['stream_id']}" for k in active_ids})
            prefix = "queue-concurrency" if include_queues else "kernel-concurrency"
            result.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "runtime_run_id": RUN_ID,
                    "lineage_id": LINEAGE_ID,
                    "trace_profile_sha256": TRACE_PROFILE_SHA256,
                    "source_record_kind": "observed_sweep_segment",
                    "source_path": str(KERNELS),
                    "source_sha256": sha256_file(KERNELS),
                    "source_row_id": active_hash,
                    "concurrency_segment_id": stable_id(prefix, request_id, rank, device, current, following, active_hash),
                    "scope_kind": "per_rank_native_device",
                    "request_id": request_id,
                    "measured_request_ordinal": request_ordinal(request_id),
                    "dp_rank": rank,
                    "native_device": device,
                    "begin_ns": current,
                    "end_ns": following,
                    "duration_ns": following - current,
                    "active_kernel_count": len(active_ids),
                    "active_queue_count": len(queues),
                    "active_kernel_ids_json": json.dumps(active_ids, separators=(",", ":")),
                    "active_queue_ids_json": json.dumps(queues, separators=(",", ":")),
                    "active_membership_sha256": active_hash,
                    "tie_rule": "half_open_end_before_start",
                    "availability_state": "available_observed_subset",
                    "availability_reason": "",
                    "evidence_class": "derived_from_observed_r07_timing",
                }
            )
    for request_id in sorted({row["request_id"] for row in kernels}):
        prefix = "queue-concurrency" if include_queues else "kernel-concurrency"
        result.append(
            {
                "schema_version": SCHEMA_VERSION,
                "runtime_run_id": RUN_ID,
                "lineage_id": LINEAGE_ID,
                "trace_profile_sha256": TRACE_PROFILE_SHA256,
                "source_record_kind": "cross_device_scope_sentinel",
                "source_path": str(KERNELS),
                "source_sha256": sha256_file(KERNELS),
                "source_row_id": request_id,
                "concurrency_segment_id": stable_id(prefix, request_id, "cross-device-unavailable"),
                "scope_kind": "cross_device",
                "request_id": request_id,
                "measured_request_ordinal": request_ordinal(request_id),
                "dp_rank": "",
                "native_device": "",
                "begin_ns": "",
                "end_ns": "",
                "duration_ns": "",
                "active_kernel_count": "",
                "active_queue_count": "",
                "active_kernel_ids_json": "",
                "active_queue_ids_json": "",
                "active_membership_sha256": "",
                "tie_rule": "half_open_end_before_start",
                "availability_state": "unavailable_cross_device_clock_alignment_not_proven",
                "availability_reason": "R07 recovery does not contain an independent cross-device alignment proof",
                "evidence_class": "unavailable",
            }
        )
    result.sort(
        key=lambda row: (
            row["request_id"],
            row["scope_kind"],
            int(row["native_device"]) if row["native_device"] != "" else 99,
            int(row["begin_ns"]) if row["begin_ns"] != "" else 2**63,
            row["concurrency_segment_id"],
        )
    )
    return result


CONCURRENCY_FIELDS = [
    "schema_version", "runtime_run_id", "lineage_id", "trace_profile_sha256",
    "source_record_kind", "source_path", "source_sha256", "source_row_id",
    "concurrency_segment_id", "scope_kind", "request_id", "measured_request_ordinal",
    "dp_rank", "native_device", "begin_ns", "end_ns", "duration_ns",
    "active_kernel_count", "active_queue_count", "active_kernel_ids_json",
    "active_queue_ids_json", "active_membership_sha256", "tie_rule",
    "availability_state", "availability_reason", "evidence_class",
]


def build_concurrency_table(output: Path, kernels: list[dict[str, str]], name: str) -> dict[str, Any]:
    rows = sweep_segments(kernels, name == "queue_concurrency")
    count, availability = write_csv_atomic(output, CONCURRENCY_FIELDS, rows)
    require(count > 5, f"empty concurrency table: {name}")
    return table_record(
        name,
        output,
        count,
        CONCURRENCY_FIELDS,
        availability,
        ["request_id", "scope_kind", "native_device", "begin_ns", "concurrency_segment_id"],
        ["derived_from_observed_r07_timing", "unavailable"],
    )


def build_launch_gaps(output: Path, kernels: list[dict[str, str]]) -> dict[str, Any]:
    groups: dict[tuple[str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in kernels:
        groups[(row["request_id"], row["dp_rank"], row["native_device"], row["queue_id"], row["stream_id"])].append(row)
    rows = []
    for key, group in sorted(groups.items()):
        group.sort(key=lambda row: (int(row["hip_runtime_index"]), int(row["begin_ns"]), row["kernel_instance_id"]))
        for previous, following in zip(group, group[1:]):
            previous_end = int(previous["end_ns"])
            next_begin = int(following["begin_ns"])
            rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "runtime_run_id": RUN_ID,
                    "lineage_id": LINEAGE_ID,
                    "trace_profile_sha256": TRACE_PROFILE_SHA256,
                    "source_record_kind": "adjacent_correlated_launch_pair",
                    "source_path": str(KERNELS),
                    "source_sha256": sha256_file(KERNELS),
                    "source_row_id": f"{previous['kernel_instance_id']}->{following['kernel_instance_id']}",
                    "launch_gap_id": stable_id("launch-gap", previous["kernel_instance_id"], following["kernel_instance_id"]),
                    "request_id": key[0],
                    "measured_request_ordinal": request_ordinal(key[0]),
                    "dp_rank": key[1],
                    "native_device": key[2],
                    "queue_id": key[3],
                    "stream_id": key[4],
                    "previous_kernel_instance_id": previous["kernel_instance_id"],
                    "next_kernel_instance_id": following["kernel_instance_id"],
                    "previous_owner_process_range_id": previous["owner_process_range_id"],
                    "next_owner_process_range_id": following["owner_process_range_id"],
                    "previous_hip_runtime_index": previous["hip_runtime_index"],
                    "next_hip_runtime_index": following["hip_runtime_index"],
                    "previous_end_ns": previous_end,
                    "next_begin_ns": next_begin,
                    "gap_ns": max(0, next_begin - previous_end),
                    "overlap_ns": max(0, previous_end - next_begin),
                    "sequence_rule": "strict_runtime_launch_index_then_begin_ns",
                    "availability_state": "available_observed_subset",
                    "availability_reason": "",
                    "evidence_class": "derived_from_observed_r07_timing",
                }
            )
    rows.sort(key=lambda row: (row["request_id"], int(row["dp_rank"]), int(row["native_device"]), int(row["queue_id"]), int(row["previous_hip_runtime_index"])))
    fields = [
        "schema_version", "runtime_run_id", "lineage_id", "trace_profile_sha256",
        "source_record_kind", "source_path", "source_sha256", "source_row_id",
        "launch_gap_id", "request_id", "measured_request_ordinal", "dp_rank",
        "native_device", "queue_id", "stream_id", "previous_kernel_instance_id",
        "next_kernel_instance_id", "previous_owner_process_range_id",
        "next_owner_process_range_id", "previous_hip_runtime_index",
        "next_hip_runtime_index", "previous_end_ns", "next_begin_ns", "gap_ns",
        "overlap_ns", "sequence_rule", "availability_state", "availability_reason",
        "evidence_class",
    ]
    count, availability = write_csv_atomic(output, fields, rows)
    require(count == len(kernels) - len(groups), "launch gap pair conservation failed")
    return table_record(
        "launch_gaps", output, count, fields, availability,
        ["request_id", "dp_rank", "native_device", "queue_id", "previous_hip_runtime_index"],
        ["derived_from_observed_r07_timing"],
    )


def nearest_rank_p95(values: list[int]) -> int:
    require(values, "cannot calculate p95 of empty values")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def build_high_latency(output: Path, processes: list[dict[str, str]]) -> tuple[dict[str, Any], set[str]]:
    global_threshold = nearest_rank_p95([int(row["duration_ns"]) for row in processes])
    peer_groups: dict[tuple[str, str, str, str], list[int]] = defaultdict(list)
    for row in processes:
        peer_groups[(row["phase"], row["process_id"], row["fragment_id"], row["target_kind"])].append(int(row["duration_ns"]))
    peer_thresholds = {key: nearest_rank_p95(values) for key, values in peer_groups.items()}
    rows = []
    selected: set[str] = set()
    process_sha = sha256_file(PROCESSES)
    for source in processes:
        duration = int(source["duration_ns"])
        peer_key = (source["phase"], source["process_id"], source["fragment_id"], source["target_kind"])
        global_flag = duration >= global_threshold
        peer_flag = duration >= peer_thresholds[peer_key]
        if not (global_flag or peer_flag):
            continue
        selected.add(source["process_range_id"])
        rows.append(
            {
                **common_fields(PROCESSES, process_sha, source["process_range_id"]),
                "source_record_kind": "observed_process_p95_classification",
                "classification_id": stable_id("high-latency", source["process_range_id"]),
                "process_range_id": source["process_range_id"],
                "canonical_target_id": source["canonical_target_id"],
                "request_id": source["request_id"],
                "measured_request_ordinal": request_ordinal(source["request_id"]),
                "forward_id": source["forward_id"],
                "layer_idx": source["layer_idx"],
                "phase": source["phase"],
                "process_id": source["process_id"],
                "fragment_id": source["fragment_id"],
                "target_kind": source["target_kind"],
                "dp_rank": source["dp_rank"],
                "native_device": source["native_device"],
                "begin_ns": source["begin_ns"],
                "end_ns": source["end_ns"],
                "duration_ns": duration,
                "global_denominator": len(processes),
                "global_p95_threshold_ns": global_threshold,
                "global_p95_or_tie": global_flag,
                "peer_group_key": json.dumps(peer_key, separators=(",", ":")),
                "peer_group_denominator": len(peer_groups[peer_key]),
                "peer_group_p95_threshold_ns": peer_thresholds[peer_key],
                "peer_group_p95_or_tie": peer_flag,
                "percentile_rule": "nearest_rank_ceil_0.95N_all_ties",
                "availability_state": "available_observed_subset",
                "availability_reason": "",
                "evidence_class": "derived_from_observed_r07_timing",
            }
        )
    rows.sort(key=lambda row: (-int(row["duration_ns"]), row["process_range_id"]))
    fields = list(rows[0])
    count, availability = write_csv_atomic(output, fields, rows)
    require(count == len(selected), "high latency identity conservation failed")
    return (
        table_record(
            "high_latency_processes", output, count, fields, availability,
            ["duration_ns desc", "process_range_id"],
            ["derived_from_observed_r07_timing"],
        ),
        selected,
    )


def build_dependency(output: Path, source_sha: str) -> tuple[dict[str, Any], dict[str, int]]:
    source_header, source_rows = read_csv_rows(DEPENDENCY)
    source_rows.sort(key=lambda row: row["dependency_edge_id"])
    rows = []
    per_process: Counter[str] = Counter()
    for source in source_rows:
        per_process[source["process_range_id"]] += 1
        state = source["dependency_state"]
        rows.append(
            {
                **common_fields(DEPENDENCY, source_sha, source["dependency_edge_id"]),
                "record_kind": "dependency_edge",
                "availability_state": "available_observed_subset" if state == "observed" else f"unknown_{state}",
                "availability_reason": "" if state == "observed" else state,
                "evidence_class": "derived_from_observed_r07_dependency_adapter",
                **source,
            }
        )
    fields = [
        "schema_version", "runtime_run_id", "lineage_id", "trace_profile_sha256",
        "source_path", "source_sha256", "source_row_id", "record_kind",
        "availability_state", "availability_reason", "evidence_class", *source_header,
    ]
    count, availability = write_csv_atomic(output, fields, rows)
    require(count == 9352, f"dependency denominator drift: {count}")
    return (
        table_record(
            "dependency_state", output, count, fields, availability,
            ["dependency_edge_id"],
            ["derived_from_observed_r07_dependency_adapter", "unavailable"],
        ),
        dict(per_process),
    )


def build_traffic_attachment(
    output: Path,
    kernels: list[dict[str, str]],
    r08_metrics: dict[tuple[str, str], dict[str, str]],
    r08_sha: str,
    methodology: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, list[dict[str, str]]]]:
    rows = []
    per_process: dict[str, list[dict[str, str]]] = defaultdict(list)
    for kernel in kernels:
        match = r08_metrics.get((kernel["native_kernel_name"], kernel["native_device"]))
        if not match:
            row = {
                "schema_version": SCHEMA_VERSION,
                "runtime_run_id": RUN_ID,
                "lineage_id": LINEAGE_ID,
                "trace_profile_sha256": TRACE_PROFILE_SHA256,
                "attachment_id": stable_id("traffic-resource", kernel["kernel_instance_id"], "unavailable"),
                "logical_source_row_id": kernel["kernel_instance_id"],
                "process_range_id": kernel["owner_process_range_id"],
                "canonical_target_id": kernel["owner_canonical_target_id"],
                "request_id": kernel["request_id"],
                "measured_request_ordinal": request_ordinal(kernel["request_id"]),
                "dp_rank": kernel["dp_rank"],
                "native_device": kernel["native_device"],
                "kernel_name": kernel["native_kernel_name"],
                "kernel_family": kernel_family(kernel["native_kernel_name"]),
                "physical_capture_id": "",
                "metric_name": "r08_hardware_attributes",
                "metric_value": "",
                "metric_unit": "",
                "metric_formula": "",
                "metric_mode": "",
                "counter_numeric_row_fraction": "",
                "aggregation_rule": "no_exact_join_no_imputation",
                "shared_physical_capture": "",
                "availability_state": "unavailable_no_exact_R08_kernel_name_device_match",
                "availability_reason": "R08 measured only a bounded kernel subset",
                "evidence_class": "unavailable",
                "logical_source_path": str(KERNELS),
                "logical_source_sha256": sha256_file(KERNELS),
                "physical_source_path": str(R08_METRICS),
                "physical_source_sha256": r08_sha,
            }
            rows.append(row)
            per_process[kernel["owner_process_range_id"]].append(row)
            continue
        physical_capture_id = f"{match['group_id']}|{kernel['native_kernel_name']}|gpu{kernel['native_device']}"
        for metric_name, mode in R08_METRIC_MODE.items():
            value = match.get(metric_name, "")
            if value == "":
                continue
            coverage = match[f"{mode}_counter_numeric_row_fraction"]
            partial = float(coverage) < 1.0
            row = {
                "schema_version": SCHEMA_VERSION,
                "runtime_run_id": RUN_ID,
                "lineage_id": LINEAGE_ID,
                "trace_profile_sha256": TRACE_PROFILE_SHA256,
                "attachment_id": stable_id("traffic-resource", kernel["kernel_instance_id"], physical_capture_id, metric_name),
                "logical_source_row_id": kernel["kernel_instance_id"],
                "process_range_id": kernel["owner_process_range_id"],
                "canonical_target_id": kernel["owner_canonical_target_id"],
                "request_id": kernel["request_id"],
                "measured_request_ordinal": request_ordinal(kernel["request_id"]),
                "dp_rank": kernel["dp_rank"],
                "native_device": kernel["native_device"],
                "kernel_name": kernel["native_kernel_name"],
                "kernel_family": kernel_family(kernel["native_kernel_name"]),
                "physical_capture_id": physical_capture_id,
                "metric_name": metric_name,
                "metric_value": value,
                "metric_unit": R08_METRIC_UNIT[metric_name],
                "metric_formula": methodology.get("formulas", {}).get(metric_name, "sum of named replay counters"),
                "metric_mode": mode,
                "counter_numeric_row_fraction": coverage,
                "aggregation_rule": "shared_replay_projected_attribute_reference_not_additive",
                "shared_physical_capture": "True",
                "availability_state": "available_replay_projected_partial" if partial else "available_replay_projected",
                "availability_reason": "all-NONE replay payloads excluded" if partial else "",
                "evidence_class": "replay_projected_R08_hardware_attribute",
                "logical_source_path": str(KERNELS),
                "logical_source_sha256": sha256_file(KERNELS),
                "physical_source_path": str(R08_METRICS),
                "physical_source_sha256": r08_sha,
            }
            rows.append(row)
            per_process[kernel["owner_process_range_id"]].append(row)
    rows.sort(key=lambda row: (row["logical_source_row_id"], row["metric_name"], row["attachment_id"]))
    fields = list(rows[0])
    count, availability = write_csv_atomic(output, fields, rows)
    require(count > len(kernels), "traffic/resource long form unexpectedly empty")
    return (
        table_record(
            "traffic_resource_attachment", output, count, fields, availability,
            ["logical_source_row_id", "metric_name", "attachment_id"],
            ["replay_projected_R08_hardware_attribute", "unavailable"],
        ),
        per_process,
    )


def interval_stats(rows: list[dict[str, str]]) -> tuple[int, int, int, int]:
    if not rows:
        return 0, 0, 0, 0
    intervals = sorted((int(row["begin_ns"]), int(row["end_ns"])) for row in rows)
    duration_sum = sum(end - begin for begin, end in intervals)
    union = 0
    current_begin, current_end = intervals[0]
    events = []
    for begin, end in intervals:
        events.extend(((begin, 1), (end, -1)))
        if begin > current_end:
            union += current_end - current_begin
            current_begin, current_end = begin, end
        else:
            current_end = max(current_end, end)
    union += current_end - current_begin
    active = maximum = 0
    for _, delta in sorted(events, key=lambda event: (event[0], event[1])):
        active += delta
        maximum = max(maximum, active)
    positive_gap_sum = sum(max(0, following[0] - previous[1]) for previous, following in zip(intervals, intervals[1:]))
    return duration_sum, union, maximum, positive_gap_sum


def build_opportunities(
    output: Path,
    processes: list[dict[str, str]],
    kernels: list[dict[str, str]],
    process_live: dict[str, dict[str, str]],
    high_ids: set[str],
    dependencies: dict[str, int],
    attachments: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    by_process: dict[str, list[dict[str, str]]] = defaultdict(list)
    for kernel in kernels:
        by_process[kernel["owner_process_range_id"]].append(kernel)
    rows = []
    process_sha = sha256_file(PROCESSES)
    for process in processes:
        process_id = process["process_range_id"]
        owned = by_process.get(process_id, [])
        duration_sum, union, max_active, gap_sum = interval_stats(owned)
        live = process_live[process_id]
        resource_rows = attachments.get(process_id, [])
        exact_resource_rows = [row for row in resource_rows if row["evidence_class"] == "replay_projected_R08_hardware_attribute"]
        l2_values = [float(row["metric_value"]) for row in exact_resource_rows if row["metric_name"] == "L2CacheHit_pct"]
        signals = []
        if live["availability_state"] == "available" and float(live["se_active_cu_pct_mean"]) < 50.0:
            signals.append("observed_live_utilization_below_50pct")
        if not owned:
            signals.append("observed_no_direct_kernel")
        if l2_values and min(l2_values) < 50.0:
            signals.append("replay_projected_L2_hit_below_50pct_hypothesis")
        if len(owned) >= 2 and max_active <= 1:
            signals.append("observed_kernel_serialization")
        high = process_id in high_ids
        if not high:
            state = "non_candidate"
            reason = "not_global_or_peer_p95"
        elif signals:
            state = "candidate"
            reason = ";".join(signals)
        elif live["availability_state"] != "available" and not exact_resource_rows:
            state = "blocked_by_unavailable"
            reason = "high_latency_but_live_utilization_and_exact_R08_attributes_unavailable"
        else:
            state = "non_candidate"
            reason = "high_latency_without_versioned_opportunity_signal"
        rows.append(
            {
                **common_fields(PROCESSES, process_sha, process_id),
                "source_record_kind": "observed_process_opportunity_evaluation",
                "opportunity_id": stable_id("opportunity", process_id),
                "process_range_id": process_id,
                "canonical_target_id": process["canonical_target_id"],
                "request_id": process["request_id"],
                "measured_request_ordinal": request_ordinal(process["request_id"]),
                "phase": process["phase"],
                "process_id": process["process_id"],
                "fragment_id": process["fragment_id"],
                "dp_rank": process["dp_rank"],
                "native_device": process["native_device"],
                "observed_duration_ns": process["duration_ns"],
                "high_latency_global_or_peer_p95": high,
                "live_utilization_state": live["availability_state"],
                "live_se_active_cu_pct_mean": live["se_active_cu_pct_mean"],
                "owned_kernel_count": len(owned),
                "owned_kernel_duration_sum_ns": duration_sum,
                "owned_kernel_union_ns": union,
                "observed_max_active_kernel_count": max_active,
                "positive_launch_gap_ns_sum": gap_sum,
                "dependency_edge_count": dependencies.get(process_id, 0),
                "exact_R08_attachment_row_count": len(exact_resource_rows),
                "minimum_replay_projected_L2_hit_pct": min(l2_values) if l2_values else "",
                "candidate_state": state,
                "rule_inputs_json": json.dumps(signals, separators=(",", ":")),
                "rule_version": "degraded-opportunity-v1-p95-util50-l2hit50-serialization",
                "availability_state": "available_observed_subset" if state != "blocked_by_unavailable" else "blocked_by_unavailable",
                "availability_reason": reason,
                "claim_scope": "investigation_hypothesis_not_root_cause_or_speedup_prediction",
                "evidence_class": "derived_degraded_observed_subset",
            }
        )
    rows.append(
        {
            **common_fields(R07_SUMMARY, sha256_file(R07_SUMMARY), "__MISSING_DECLARED_PROCESS_UNIVERSE__"),
            "source_record_kind": "missing_declared_process_universe_sentinel",
            "opportunity_id": stable_id("opportunity", "missing-declared-process-universe"),
            "process_range_id": "",
            "canonical_target_id": "",
            "request_id": "",
            "measured_request_ordinal": "",
            "phase": "",
            "process_id": "",
            "fragment_id": "",
            "dp_rank": "",
            "native_device": "",
            "observed_duration_ns": "",
            "high_latency_global_or_peer_p95": "",
            "live_utilization_state": "unavailable_missing_marker",
            "live_se_active_cu_pct_mean": "",
            "owned_kernel_count": "",
            "owned_kernel_duration_sum_ns": "",
            "owned_kernel_union_ns": "",
            "observed_max_active_kernel_count": "",
            "positive_launch_gap_ns_sum": "",
            "dependency_edge_count": "",
            "exact_R08_attachment_row_count": "",
            "minimum_replay_projected_L2_hit_pct": "",
            "candidate_state": "blocked_by_unavailable",
            "rule_inputs_json": "[]",
            "rule_version": "degraded-opportunity-v1-p95-util50-l2hit50-serialization",
            "availability_state": "blocked_by_unavailable",
            "availability_reason": "8624 declared process markers are absent from R07 and cannot be evaluated",
            "claim_scope": "coverage_sentinel_not_a_logical_process",
            "evidence_class": "unavailable",
        }
    )
    rows.sort(key=lambda row: (row["source_record_kind"] == "missing_declared_process_universe_sentinel", row["process_range_id"]))
    fields = list(rows[0])
    count, availability = write_csv_atomic(output, fields, rows)
    require(count == 3921, f"opportunity denominator drift: {count}")
    return table_record(
        "opportunity_candidates", output, count, fields, availability,
        ["coverage sentinel last", "process_range_id"],
        ["derived_degraded_observed_subset", "unavailable"],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True, type=Path)
    args = parser.parse_args()
    artifact_root = args.artifact_root.resolve()
    require(artifact_root == Path(__file__).resolve().parents[1], "artifact root/tool location mismatch")
    require(not (artifact_root / "analysis/fresh_e2e_analysis.json").exists(), "immutable R09 analysis already exists")
    started = time.monotonic()
    table_root = artifact_root / "analysis/tables"
    table_root.mkdir(parents=True, exist_ok=True)
    recovery_root = artifact_root / "recovery"
    recovery_root.mkdir(parents=True, exist_ok=True)

    source_paths = [
        REQUESTS, PROCESSES, KERNELS, LIVE_SAMPLES, LIVE_GAPS, PROCESS_LIVE,
        DEPENDENCY, R07_ANCHORS, R07_SUMMARY, R07_LIVE_SUMMARY, R07_RECOVERY,
        R07_LINEAGE, R08_HANDOFF, R08_METRICS, R08_METHODOLOGY,
        R08_SEMANTIC_MISSINGNESS,
    ]
    for path in source_paths:
        require(path.is_file(), f"missing R09 source: {path}")
    source_hashes = {path: sha256_file(path) for path in source_paths}
    r07_summary = json.loads(R07_SUMMARY.read_text(encoding="utf-8"))
    r07_live = json.loads(R07_LIVE_SUMMARY.read_text(encoding="utf-8"))
    r07_complete = json.loads(R07_RECOVERY.read_text(encoding="utf-8"))
    r08_handoff = json.loads(R08_HANDOFF.read_text(encoding="utf-8"))
    require(r07_summary["coverage_target_met"] is False, "unexpected strict R07 coverage")
    require(r07_complete["strict_scheduler_handoff_created"] is False, "unexpected strict R07 handoff")
    require(r08_handoff["strict_R09_authorized"] is False, "unexpected strict R08 authorization")
    require(r08_handoff["dcu_required_after_this_handoff"] is False, "R08 offline boundary drift")

    r08_metrics, r08_metrics_sha, r08_methodology = load_r08_metrics()
    records: list[dict[str, Any]] = []
    request_record, request_rows = build_request_table(table_root / "request_timeline.csv", source_hashes[REQUESTS])
    records.append(request_record)
    print("R09 table=request_timeline complete", flush=True)
    process_record, process_rows = build_process_table(table_root / "process_timeline.csv", source_hashes[PROCESSES])
    records.append(process_record)
    print("R09 table=process_timeline complete", flush=True)
    kernel_record, kernel_rows = build_kernel_table(table_root / "kernel_timeline.csv", source_hashes[KERNELS], r08_metrics)
    records.append(kernel_record)
    print("R09 table=kernel_timeline complete", flush=True)
    live_record, live_parts = build_live_table(table_root / "live_utilization_aligned.csv", recovery_root, source_hashes)
    records.append(live_record)
    print("R09 table=live_utilization_aligned complete", flush=True)
    process_live_record, process_live = build_process_live_table(table_root / "process_live_utilization.csv", source_hashes[PROCESS_LIVE])
    records.append(process_live_record)
    kernel_concurrency_record = build_concurrency_table(table_root / "kernel_concurrency.csv", kernel_rows, "kernel_concurrency")
    records.append(kernel_concurrency_record)
    queue_concurrency_record = build_concurrency_table(table_root / "queue_concurrency.csv", kernel_rows, "queue_concurrency")
    records.append(queue_concurrency_record)
    launch_record = build_launch_gaps(table_root / "launch_gaps.csv", kernel_rows)
    records.append(launch_record)
    high_record, high_ids = build_high_latency(table_root / "high_latency_processes.csv", process_rows)
    records.append(high_record)
    dependency_record, dependencies = build_dependency(table_root / "dependency_state.csv", source_hashes[DEPENDENCY])
    records.append(dependency_record)
    traffic_record, attachments = build_traffic_attachment(
        table_root / "traffic_resource_attachment.csv",
        kernel_rows,
        r08_metrics,
        r08_metrics_sha,
        r08_methodology,
    )
    records.append(traffic_record)
    opportunity_record = build_opportunities(
        table_root / "opportunity_candidates.csv",
        process_rows,
        kernel_rows,
        process_live,
        high_ids,
        dependencies,
        attachments,
    )
    records.append(opportunity_record)
    require([record["logical_name"] for record in records] == TABLE_ORDER, "R09 twelve-table order drift")

    source_records = [{**file_record(path), "role": path.name} for path in source_paths]
    analysis = {
        "schema_version": 1,
        "analysis_algorithm_version": "degraded-observed-subset-r09-v1",
        "status": "complete",
        "execution_status": "complete",
        "evidence_status": "degraded_R07_observed_subset",
        "runtime_branch": "workflow01-10-fresh-e2e",
        "runtime_goal": "R09-degraded-recovery",
        "runtime_run_id": RUN_ID,
        "lineage_id": LINEAGE_ID,
        "trace_profile_sha256": TRACE_PROFILE_SHA256,
        "strict_R09_handoff_eligible": False,
        "strict_R10_authorized": False,
        "degraded_R10_offline_reporting_authorized_by_user_request": True,
        "formal_scheduler_handoff_created": False,
        "table_count": len(records),
        "ordered_tables": records,
        "coverage": {
            "declared_measured_request_count": 8,
            "observed_unique_request_identity_count": len({row["request_id"] for row in request_rows}),
            "request_range_row_count": len(request_rows),
            "declared_process_marker_count": 12544,
            "observed_process_marker_count": len(process_rows),
            "missing_process_marker_count": 8624,
            "declared_target_count": 13568,
            "observed_target_count": 4240,
            "missing_target_count": 9328,
            "target_coverage_fraction": 0.3125,
            "strict_owned_kernel_count": len(kernel_rows),
            "dp_ranks": [0, 1],
            "native_devices": [0, 1],
        },
        "clock_and_evidence_semantics": {
            "unique_latency_clock": "R07 observed HIPTX/HIP/HIPOPS nanosecond clock",
            "R08_replay_time_used_as_latency": False,
            "R08_attributes": "replay_projected_only",
            "cross_device_concurrency": "unavailable_without_independent_alignment_proof",
            "PMC_GPUBusy_is_production_utilization": False,
            "live_utilization_imputation_performed": False,
        },
        "live_utilization": {
            "sample_count": r07_live["aligned_sample_count"],
            "gap_count": r07_live["aligned_gap_interval_count"],
            "anchor_count": 2,
            "process_availability_counts": r07_live["availability_counts"],
            "recovery_part_count": len(live_parts),
            "recovery_parts": live_parts,
        },
        "r08_semantic_missingness": json.loads(R08_SEMANTIC_MISSINGNESS.read_text(encoding="utf-8")),
        "complete_timeline": False,
        "complete_observed_subset_timeline": True,
        "complete_declared_target_timeline": False,
        "sampling_performed": False,
        "top_n_truncation_performed": False,
        "fixed_event_budget_used": False,
        "imputation_performed": False,
        "source_inputs": source_records,
        "limitations": [
            "This is an observed-subset recovery analysis, not a strict R09 scheduler result.",
            "Only five of eight request identities and 31.25% of the declared R07 target universe are observed.",
            "R08 metrics cover a bounded exact-kernel subset and are shared replay-projected attributes, never observed latency or additive per-logical-kernel counts.",
            "Opportunity rows are investigation hypotheses and are not root-cause or speedup claims.",
        ],
        "dcu_accessed": False,
    }
    analysis_path = artifact_root / "analysis/fresh_e2e_analysis.json"
    write_json_atomic(analysis_path, analysis)
    lineage = {
        "schema_version": 1,
        "status": "complete",
        "evidence_status": "degraded_R07_observed_subset",
        "runtime_run_id": RUN_ID,
        "lineage_id": LINEAGE_ID,
        "trace_profile_sha256": TRACE_PROFILE_SHA256,
        "recovery_scope": "user_authorized_cap_db_observed_subset_offline_continuation",
        "source_capture_database_sha256": "7e71f7977d7b67781d588cc9560bd25850cb501c803286f2494d2ad5e983b15d",
        "prepared_database_sha256": "0d61e55e04c4010c144ae7d6c308ce09fa0c413e289be4f5e6ce5358292db3bf",
        "R07_source_lineage": file_record(R07_LINEAGE),
        "R07_recovery_complete": file_record(R07_RECOVERY),
        "R08_degraded_handoff": file_record(R08_HANDOFF),
        "full_request_analysis": file_record(analysis_path),
        "source_inputs": source_records,
        "strict_R09_handoff_created": False,
        "predecessor_artifacts_modified": False,
        "model_execution_performed": False,
        "gpu_dcu_execution_performed": False,
        "profiler_execution_performed": False,
        "trace_collection_performed": False,
        "pmc_collection_performed": False,
    }
    lineage_path = artifact_root / "lineage/R09_SOURCE_LINEAGE.json"
    write_json_atomic(lineage_path, lineage)
    business_paths = [Path(record["path"]) for record in records] + [analysis_path, lineage_path]
    manifest = {
        "schema_version": 1,
        "status": "complete",
        "artifact_scope": "R09_degraded_observed_subset_business_outputs",
        "runtime_run_id": RUN_ID,
        "lineage_id": LINEAGE_ID,
        "strict_scheduler_handoff_included": False,
        "artifacts": [file_record(path) for path in business_paths],
        "recovery_parts": live_parts,
    }
    manifest_path = artifact_root / "artifact_manifest.json"
    write_json_atomic(manifest_path, manifest)
    complete = {
        "schema_version": 1,
        "status": "builder_complete_pending_independent_audit",
        "finished_utc": utc_now(),
        "elapsed_seconds": time.monotonic() - started,
        "table_count": 12,
        "table_row_counts": {record["logical_name"]: record["row_count"] for record in records},
        "full_request_analysis": file_record(analysis_path),
        "source_lineage": file_record(lineage_path),
        "artifact_manifest": file_record(manifest_path),
        "strict_R09_handoff_created": False,
        "dcu_accessed": False,
    }
    write_json_atomic(artifact_root / "R09_BUILDER_COMPLETE.json", complete)
    print(json.dumps(complete, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
