#!/usr/bin/env python3
"""Stream and normalize the nine recoverable R08 HIPProf PMC segments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SEGMENTS = ROOT / "segments"
CAPABILITY = ROOT / "preflight/device_capabilities_006/CAPABILITY_COMPLETE.json"
R07_RECOVERY = Path(
    "/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/runtime/"
    "workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R07/recovery/"
    "db_first_postprocess_001/DB_FIRST_R07_RECOVERY_COMPLETE.json"
)
R07_PROCESS_SUMMARY = Path(
    "/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/runtime/"
    "workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R07/recovery/"
    "db_first_normalization_003/trace/process_trace_summary.json"
)

GROUP_BY_ORDINAL = {
    1: "gqa6",
    2: "gqa6",
    3: "gqa6",
    4: "triton_rmsnorm",
    5: "triton_rmsnorm",
    6: "triton_rmsnorm",
    7: "chunk_group",
    8: "chunk_group",
    9: "chunk_group",
}
MODE_BY_ORDINAL = {
    1: "pmc",
    2: "pmc_read",
    3: "pmc_write",
    4: "pmc",
    5: "pmc_read",
    6: "pmc_write",
    7: "pmc",
    8: "pmc_read",
    9: "pmc_write",
}
REQUIRED_KERNELS = {
    "gqa6": {"_gqa6"},
    "triton_rmsnorm": {"triton_red_fused__to_copy_add_mean_mul_pow_rsqrt_0"},
    "chunk_group": {
        "chunk_fwd_kernel_o",
        "chunk_gated_delta_rule_fwd_kernel_h_blockdim64",
    },
}

CU_NUM = 80
SIMD_PER_CU = 4
SIMD_NUM = CU_NUM * SIMD_PER_CU
SE_NUM = 8


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def write_json_x(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def write_csv_x(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())


def union_fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for name in row:
            if name not in seen:
                seen.add(name)
                result.append(name)
    return result


def new_bucket(header: list[str]) -> dict[str, Any]:
    counter_names = header[16:-4]
    return {
        "header": header,
        "counter_names": counter_names,
        "ta_busy_indexes": [
            index for index, name in enumerate(counter_names) if name.startswith("TA_TA_BUSY[")
        ],
        "tcp_stall_indexes": [
            index
            for index, name in enumerate(counter_names)
            if name.startswith("TCP_TCP_TA_DATA_STALL_CYCLES[")
        ],
        "tcc_write_stall_indexes": [
            index
            for index, name in enumerate(counter_names)
            if name.startswith("TCC_EA_WRREQ_STALL[")
            or name.startswith("TCC_EA1_WRREQ_STALL[")
        ],
        "counter_sums": [0] * len(counter_names),
        "row_count": 0,
        "counter_numeric_row_count": 0,
        "semantic_missing_counter_row_count": 0,
        "semantic_missing_counter_cell_count": 0,
        "negative_counter_cell_count": 0,
        "profiled_kernel_duration_ns_sum": 0,
        "profiler_dispatch_to_complete_ns_sum": 0,
        "end_gt_complete_row_count": 0,
        "end_gt_complete_delta_ns_sum": 0,
        "end_gt_complete_delta_ns_max": 0,
        "ta_busy_instance_max_sum": 0,
        "ta_busy_instance_eligible_row_count": 0,
        "tcp_stall_instance_max_sum": 0,
        "tcp_stall_instance_eligible_row_count": 0,
        "tcc_write_stall_instance_max_sum": 0,
        "tcc_write_stall_instance_eligible_row_count": 0,
        "launch_signatures": Counter(),
    }


def update_bucket(bucket: dict[str, Any], row: list[str], mode: str) -> tuple[int, int]:
    """Update one aggregate and return (unavailable cells, End-Complete delta).

    HIPProf emits the literal ``NONE`` when a replay dispatch has no counter
    payload.  The observed data uses an all-or-none pattern across the 186
    counter columns.  Preserve the dispatch metadata, but never coerce NONE to
    a numerical zero.
    """

    raw_values = row[16:-4]
    missing_count = raw_values.count("NONE")
    require(
        missing_count in {0, len(raw_values)},
        "R08 unexpected partially unavailable counter row",
    )
    if missing_count:
        bucket["semantic_missing_counter_row_count"] += 1
        bucket["semantic_missing_counter_cell_count"] += missing_count
    else:
        values = [int(value) for value in raw_values]
        sums = bucket["counter_sums"]
        for index, value in enumerate(values):
            sums[index] += value
            if value < 0:
                bucket["negative_counter_cell_count"] += 1
        ta_busy = [values[index] for index in bucket["ta_busy_indexes"]]
        tcp_stall = [values[index] for index in bucket["tcp_stall_indexes"]]
        require(len(ta_busy) == 16 and len(tcp_stall) == 16, "R08 common instance counters drift")
        bucket["ta_busy_instance_max_sum"] += max(ta_busy)
        bucket["ta_busy_instance_eligible_row_count"] += 1
        bucket["tcp_stall_instance_max_sum"] += max(tcp_stall)
        bucket["tcp_stall_instance_eligible_row_count"] += 1
        if mode == "pmc":
            write_stall = [values[index] for index in bucket["tcc_write_stall_indexes"]]
            require(len(write_stall) == 64, "R08 PMC write-stall instance counters drift")
            bucket["tcc_write_stall_instance_max_sum"] += max(write_stall)
            bucket["tcc_write_stall_instance_eligible_row_count"] += 1
        bucket["counter_numeric_row_count"] += 1
    begin_ns = int(row[-3])
    end_ns = int(row[-2])
    dispatch_ns = int(row[-4])
    complete_ns = int(row[-1])
    require(dispatch_ns <= begin_ns <= end_ns, "R08 kernel timestamps are not monotonic")
    require(dispatch_ns <= complete_ns, "R08 dispatch/complete timestamps are not monotonic")
    end_gt_complete_delta = max(0, end_ns - complete_ns)
    if end_gt_complete_delta:
        bucket["end_gt_complete_row_count"] += 1
        bucket["end_gt_complete_delta_ns_sum"] += end_gt_complete_delta
        bucket["end_gt_complete_delta_ns_max"] = max(
            bucket["end_gt_complete_delta_ns_max"], end_gt_complete_delta
        )
    bucket["profiled_kernel_duration_ns_sum"] += end_ns - begin_ns
    bucket["profiler_dispatch_to_complete_ns_sum"] += complete_ns - dispatch_ns
    signature = tuple(row[index] for index in range(7, 15))
    bucket["launch_signatures"][signature] += 1
    bucket["row_count"] += 1
    return missing_count, end_gt_complete_delta


def combine_buckets(parts: list[dict[str, Any]]) -> dict[str, Any]:
    require(parts, "cannot combine an empty R08 bucket list")
    header = parts[0]["header"]
    result = new_bucket(header)
    for part in parts:
        require(part["header"] == header, "R08 bucket schema mismatch")
        for index, value in enumerate(part["counter_sums"]):
            result["counter_sums"][index] += value
        for name in (
            "row_count",
            "counter_numeric_row_count",
            "semantic_missing_counter_row_count",
            "semantic_missing_counter_cell_count",
            "negative_counter_cell_count",
            "profiled_kernel_duration_ns_sum",
            "profiler_dispatch_to_complete_ns_sum",
            "end_gt_complete_row_count",
            "end_gt_complete_delta_ns_sum",
            "ta_busy_instance_max_sum",
            "ta_busy_instance_eligible_row_count",
            "tcp_stall_instance_max_sum",
            "tcp_stall_instance_eligible_row_count",
            "tcc_write_stall_instance_max_sum",
            "tcc_write_stall_instance_eligible_row_count",
        ):
            result[name] += part[name]
        result["end_gt_complete_delta_ns_max"] = max(
            result["end_gt_complete_delta_ns_max"], part["end_gt_complete_delta_ns_max"]
        )
        result["launch_signatures"].update(part["launch_signatures"])
    return result


def counter_map(bucket: dict[str, Any]) -> dict[str, int]:
    return dict(zip(bucket["counter_names"], bucket["counter_sums"]))


def prefix_sum(counters: dict[str, int], prefix: str) -> int:
    return sum(value for name, value in counters.items() if name.startswith(prefix))


def safe_ratio(numerator: int | float, denominator: int | float, scale: float = 1.0) -> float | None:
    if denominator == 0:
        return None
    return scale * float(numerator) / float(denominator)


def mode_metrics(bucket: dict[str, Any], mode: str) -> dict[str, Any]:
    counters = counter_map(bucket)
    grbm = counters["GRBM_COUNT"]
    gui = counters["GRBM_GUI_ACTIVE"]
    numeric_rows = bucket["counter_numeric_row_count"]
    coverage = safe_ratio(numeric_rows, bucket["row_count"])
    result: dict[str, Any] = {
        "row_count": bucket["row_count"],
        "counter_numeric_row_count": numeric_rows,
        "counter_numeric_row_fraction": coverage,
        "counter_coverage_status": "complete" if numeric_rows == bucket["row_count"] else "partial",
        "semantic_missing_counter_row_count": bucket["semantic_missing_counter_row_count"],
        "semantic_missing_counter_cell_count": bucket["semantic_missing_counter_cell_count"],
        "negative_counter_cell_count": bucket["negative_counter_cell_count"],
        "profiled_kernel_duration_ns_sum_not_production_latency": bucket[
            "profiled_kernel_duration_ns_sum"
        ],
        "profiler_dispatch_to_complete_ns_sum_not_production_latency": bucket[
            "profiler_dispatch_to_complete_ns_sum"
        ],
        "end_gt_complete_row_count": bucket["end_gt_complete_row_count"],
        "end_gt_complete_delta_ns_sum": bucket["end_gt_complete_delta_ns_sum"],
        "end_gt_complete_delta_ns_max": bucket["end_gt_complete_delta_ns_max"],
        "GPUBusy_pct": safe_ratio(gui, grbm, 100.0),
        "VALUBusy_pct": safe_ratio(
            counters["SQ_ACTIVE_INST_VALU"] * SIMD_PER_CU,
            SIMD_NUM * gui,
            100.0,
        ),
        "LDSBankConflict_pct": safe_ratio(counters["SQ_LDS_BANK_CONFLICT"], CU_NUM * gui, 100.0),
        "MemUnitStalled_pct": safe_ratio(
            bucket["tcp_stall_instance_max_sum"], SE_NUM * gui, 100.0
        ),
        "MemUnitBusy_pct": safe_ratio(bucket["ta_busy_instance_max_sum"], SE_NUM * gui, 100.0),
        "MemUnitBusy_eligible_row_count": bucket["ta_busy_instance_eligible_row_count"],
        "MemUnitStalled_eligible_row_count": bucket["tcp_stall_instance_eligible_row_count"],
        "SQ_INSTS_VALU_sum": counters["SQ_INSTS_VALU"],
        "SQ_INSTS_VMEM_RD_sum": counters["SQ_INSTS_VMEM_RD"],
        "SQ_INSTS_VMEM_WR_sum": counters["SQ_INSTS_VMEM_WR"],
        "SQ_INSTS_LDS_sum": counters["SQ_INSTS_LDS"],
        "SQ_WAIT_INST_LDS_sum": counters["SQ_WAIT_INST_LDS"],
    }
    if mode == "pmc":
        hits = prefix_sum(counters, "TCC_HIT[")
        misses = prefix_sum(counters, "TCC_MISS[")
        result.update(
            {
                "L2_hit_count": hits,
                "L2_miss_count": misses,
                "L2CacheHit_pct": safe_ratio(hits, hits + misses, 100.0),
                "WriteUnitStalled_pct": safe_ratio(
                    bucket["tcc_write_stall_instance_max_sum"], gui, 100.0
                ),
                "WriteUnitStalled_eligible_row_count": bucket[
                    "tcc_write_stall_instance_eligible_row_count"
                ],
            }
        )
    elif mode == "pmc_read":
        result.update(
            {
                "flat_read_wavefronts_sum": prefix_sum(counters, "TA_FLAT_READ_WAVEFRONTS["),
                "read_requests_sum": prefix_sum(counters, "TCC_EA_RDREQ[")
                + prefix_sum(counters, "TCC_EA1_RDREQ["),
                "read_requests_32B_subset_sum": prefix_sum(counters, "TCC_EA_RDREQ_32B[")
                + prefix_sum(counters, "TCC_EA1_RDREQ_32B["),
            }
        )
    elif mode == "pmc_write":
        result.update(
            {
                "flat_write_wavefronts_sum": prefix_sum(counters, "TA_FLAT_WRITE_WAVEFRONTS["),
                "write_requests_sum": prefix_sum(counters, "TCC_EA_WRREQ[")
                + prefix_sum(counters, "TCC_EA1_WRREQ["),
                "write_requests_64B_subset_sum": prefix_sum(counters, "TCC_EA_WRREQ_64B[")
                + prefix_sum(counters, "TCC_EA1_WRREQ_64B["),
            }
        )
    else:
        raise RuntimeError(f"unknown R08 mode: {mode}")
    return result


def launch_signature_rows(
    group: str, kernel: str, gpu_id: str, bucket: dict[str, Any]
) -> list[dict[str, Any]]:
    fields = ["grd", "wgr", "lds", "scr", "arch_vgpr", "accum_vgpr", "sgpr", "wave_size"]
    result = []
    for signature, count in sorted(bucket["launch_signatures"].items()):
        row: dict[str, Any] = {
            "group_id": group,
            "kernel_name": kernel,
            "gpu_id": gpu_id,
            "row_count": count,
        }
        row.update(dict(zip(fields, signature)))
        waves = math.ceil(int(row["wgr"]) / int(row["wave_size"]))
        row["waves_per_workgroup_static"] = waves
        result.append(row)
    return result


def file_record(path: Path) -> dict[str, Any]:
    return {"path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    require(not output_root.exists(), f"immutable R08 normalization root exists: {output_root}")
    output_root.mkdir(parents=True)
    started = time.monotonic()

    require(CAPABILITY.is_file(), "R08 capability report missing")
    capability = json.loads(CAPABILITY.read_text(encoding="utf-8"))
    require(capability["full_vllm_dynamic_gate_proof"]["status"] == "complete", "R08 gate proof incomplete")
    require(R07_RECOVERY.is_file() and R07_PROCESS_SUMMARY.is_file(), "R07 degraded source lineage missing")
    r07_recovery = json.loads(R07_RECOVERY.read_text(encoding="utf-8"))
    r07_summary = json.loads(R07_PROCESS_SUMMARY.read_text(encoding="utf-8"))
    require(r07_recovery["strict_scheduler_handoff_created"] is False, "unexpected strict R07 handoff")
    require(r07_summary["coverage_target_met"] is False, "unexpected complete R07 marker coverage")

    unit_paths = sorted(SEGMENTS.glob("[0-9][0-9]_*/UNIT_COMPLETE.json"))
    require(len(unit_paths) == 9, f"R08 complete unit denominator drift: {len(unit_paths)}")
    leaves: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    segment_inventory: list[dict[str, Any]] = []
    semantic_missing_rows: list[dict[str, Any]] = []
    timestamp_order_examples: list[dict[str, Any]] = []
    headers_by_mode: dict[str, list[str]] = {}
    total_source_rows = 0
    total_semantic_missing_counter_rows = 0
    total_semantic_missing_counter_cells = 0
    total_end_gt_complete_rows = 0
    total_end_gt_complete_delta_ns = 0
    max_end_gt_complete_delta_ns = 0
    for unit_path in unit_paths:
        ordinal = int(unit_path.parent.name.split("_", 1)[0])
        group = GROUP_BY_ORDINAL[ordinal]
        mode = MODE_BY_ORDINAL[ordinal]
        unit = json.loads(unit_path.read_text(encoding="utf-8"))
        require(unit["status"] == "complete", f"R08 unit incomplete: {unit_path}")
        segment_path = Path(unit["segment_complete_path"])
        require(sha256_file(segment_path) == unit["segment_complete_sha256"], "R08 segment marker hash drift")
        segment = json.loads(segment_path.read_text(encoding="utf-8"))
        csv_path = Path(unit["csv_path"])
        require(sha256_file(csv_path) == unit["csv_sha256"], "R08 canonical CSV hash drift")
        attempt_root = Path(unit["attempt_path"])
        contract_path = attempt_root / "ATTEMPT_CONTRACT.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            header = next(reader)
            require(len(header) == 206, f"R08 normalized header width drift: {csv_path}")
            if mode in headers_by_mode:
                require(header == headers_by_mode[mode], f"R08 mode schema drift: {mode}")
            else:
                headers_by_mode[mode] = header
            observed_rows = 0
            segment_missing_counter_rows = 0
            segment_missing_counter_cells = 0
            segment_end_gt_complete_rows = 0
            segment_end_gt_complete_delta_ns = 0
            segment_end_gt_complete_delta_ns_max = 0
            segment_timestamp_example_count = 0
            for row in reader:
                require(len(row) == len(header), f"R08 CSV row width drift: {csv_path}")
                gpu_id = row[2]
                require(gpu_id in {"0", "1"}, f"R08 unexpected GPU id: {gpu_id}")
                key = (group, mode, row[1], gpu_id)
                bucket = leaves.setdefault(key, new_bucket(header))
                observed_rows += 1
                missing_count, end_gt_complete_delta = update_bucket(bucket, row, mode)
                if missing_count:
                    segment_missing_counter_rows += 1
                    segment_missing_counter_cells += missing_count
                    semantic_missing_rows.append(
                        {
                            "segment_id": segment["segment_id"],
                            "mode_id": mode,
                            "canonical_csv_path": str(csv_path),
                            "csv_data_row_1based": observed_rows,
                            "kernel_name": row[1],
                            "gpu_id": int(row[2]),
                            "queue_id": int(row[3]),
                            "pid": int(row[5]),
                            "tid": int(row[6]),
                            "missing_counter_cell_count": missing_count,
                            "dispatch_ns": int(row[-4]),
                            "begin_ns": int(row[-3]),
                            "end_ns": int(row[-2]),
                            "complete_ns": int(row[-1]),
                        }
                    )
                if end_gt_complete_delta:
                    segment_end_gt_complete_rows += 1
                    segment_end_gt_complete_delta_ns += end_gt_complete_delta
                    segment_end_gt_complete_delta_ns_max = max(
                        segment_end_gt_complete_delta_ns_max, end_gt_complete_delta
                    )
                    if segment_timestamp_example_count < 3:
                        timestamp_order_examples.append(
                            {
                                "segment_id": segment["segment_id"],
                                "csv_data_row_1based": observed_rows,
                                "kernel_name": row[1],
                                "gpu_id": int(row[2]),
                                "end_ns": int(row[-2]),
                                "complete_ns": int(row[-1]),
                                "end_gt_complete_delta_ns": end_gt_complete_delta,
                            }
                        )
                        segment_timestamp_example_count += 1
                if observed_rows % 100000 == 0:
                    print(
                        f"R08 normalize segment={segment['segment_id']} rows={observed_rows}",
                        flush=True,
                    )
        require(observed_rows == unit["row_count"], f"R08 row count drift: {segment['segment_id']}")
        total_source_rows += observed_rows
        total_semantic_missing_counter_rows += segment_missing_counter_rows
        total_semantic_missing_counter_cells += segment_missing_counter_cells
        total_end_gt_complete_rows += segment_end_gt_complete_rows
        total_end_gt_complete_delta_ns += segment_end_gt_complete_delta_ns
        max_end_gt_complete_delta_ns = max(
            max_end_gt_complete_delta_ns, segment_end_gt_complete_delta_ns_max
        )
        excluded = segment["canonical_window"]["excluded_row_counts"]
        segment_inventory.append(
            {
                "ordinal": ordinal,
                "segment_id": segment["segment_id"],
                "group_id": group,
                "mode_id": mode,
                "attempt_id": unit["attempt_path"].rsplit("/", 1)[-1],
                "capture_strategy": contract["warmup_exclusion_backend"],
                "hipprof_final_artifact_kind": segment["hipprof_final_artifact_kind"],
                "elapsed_seconds": segment["elapsed_seconds"],
                "canonical_row_count": observed_rows,
                "counter_numeric_row_count": observed_rows - segment_missing_counter_rows,
                "counter_numeric_row_fraction": safe_ratio(
                    observed_rows - segment_missing_counter_rows, observed_rows
                ),
                "semantic_missing_counter_row_count": segment_missing_counter_rows,
                "semantic_missing_counter_cell_count": segment_missing_counter_cells,
                "end_gt_complete_row_count": segment_end_gt_complete_rows,
                "end_gt_complete_row_fraction": safe_ratio(
                    segment_end_gt_complete_rows, observed_rows
                ),
                "end_gt_complete_delta_ns_sum": segment_end_gt_complete_delta_ns,
                "end_gt_complete_delta_ns_max": segment_end_gt_complete_delta_ns_max,
                "full_row_count": segment["full_csv_validation"]["row_count"],
                "before_window_rows": excluded["before_window"],
                "after_window_rows": excluded["after_window"],
                "overlap_rows": excluded["overlaps_boundary"],
                "unknown_pid_rows": excluded["unknown_pid"],
                "csv_size_bytes": csv_path.stat().st_size,
                "canonical_csv_path": str(csv_path),
                "csv_sha256": unit["csv_sha256"],
                "unit_complete_sha256": sha256_file(unit_path),
                "segment_complete_sha256": unit["segment_complete_sha256"],
            }
        )

    require(total_source_rows == 1131498, f"R08 nine-segment row denominator drift: {total_source_rows}")
    require(
        total_semantic_missing_counter_rows == 12,
        f"R08 semantic missing counter row denominator drift: {total_semantic_missing_counter_rows}",
    )
    require(
        total_semantic_missing_counter_cells == 2232,
        f"R08 semantic missing counter cell denominator drift: {total_semantic_missing_counter_cells}",
    )
    require(
        total_end_gt_complete_rows == 10047,
        f"R08 EndNs/CompleteNs ordering denominator drift: {total_end_gt_complete_rows}",
    )
    require(
        max_end_gt_complete_delta_ns == 13128,
        f"R08 EndNs/CompleteNs maximum delta drift: {max_end_gt_complete_delta_ns}",
    )
    require({key[0] for key in leaves} == set(REQUIRED_KERNELS), "R08 group coverage drift")
    for group, required in REQUIRED_KERNELS.items():
        observed = {key[2] for key in leaves if key[0] == group}
        require(required <= observed, f"R08 required kernel coverage drift for {group}: {observed}")

    expanded: dict[tuple[str, str, str, str], dict[str, Any]] = dict(leaves)
    groups = sorted({key[0] for key in leaves})
    modes = ["pmc", "pmc_read", "pmc_write"]
    for group in groups:
        kernels = sorted({key[2] for key in leaves if key[0] == group})
        for mode in modes:
            for kernel in kernels:
                parts = [leaves[(group, mode, kernel, gpu)] for gpu in ("0", "1")]
                expanded[(group, mode, kernel, "all")] = combine_buckets(parts)
            for gpu in ("0", "1", "all"):
                parts = [expanded[(group, mode, kernel, gpu)] for kernel in kernels]
                expanded[(group, mode, "__GROUP_TOTAL__", gpu)] = combine_buckets(parts)

    for group in groups:
        kernels = sorted({key[2] for key in leaves if key[0] == group}) + ["__GROUP_TOTAL__"]
        for kernel in kernels:
            for gpu in ("0", "1", "all"):
                counts = [expanded[(group, mode, kernel, gpu)]["row_count"] for mode in modes]
                require(len(set(counts)) == 1, f"R08 cross-mode row mismatch: {group}/{kernel}/{gpu}: {counts}")
                require(
                    all(expanded[(group, mode, kernel, gpu)]["negative_counter_cell_count"] == 0 for mode in modes),
                    f"R08 negative hardware counter observed: {group}/{kernel}/{gpu}",
                )

    mode_rows: list[dict[str, Any]] = []
    raw_aggregates: list[dict[str, Any]] = []
    for key in sorted(expanded):
        group, mode, kernel, gpu = key
        bucket = expanded[key]
        metrics = mode_metrics(bucket, mode)
        mode_rows.append(
            {
                "group_id": group,
                "scope_kind": "group" if kernel == "__GROUP_TOTAL__" else "kernel",
                "kernel_name": kernel,
                "gpu_id": gpu,
                "mode_id": mode,
                **metrics,
            }
        )
        raw_aggregates.append(
            {
                "group_id": group,
                "kernel_name": kernel,
                "gpu_id": gpu,
                "mode_id": mode,
                "row_count": bucket["row_count"],
                "counter_numeric_row_count": bucket["counter_numeric_row_count"],
                "semantic_missing_counter_row_count": bucket[
                    "semantic_missing_counter_row_count"
                ],
                "semantic_missing_counter_cell_count": bucket[
                    "semantic_missing_counter_cell_count"
                ],
                "end_gt_complete_row_count": bucket["end_gt_complete_row_count"],
                "end_gt_complete_delta_ns_sum": bucket["end_gt_complete_delta_ns_sum"],
                "end_gt_complete_delta_ns_max": bucket["end_gt_complete_delta_ns_max"],
                "counter_sums": counter_map(bucket),
                "ta_busy_instance_max_sum": bucket["ta_busy_instance_max_sum"],
                "ta_busy_instance_eligible_row_count": bucket[
                    "ta_busy_instance_eligible_row_count"
                ],
                "tcp_stall_instance_max_sum": bucket["tcp_stall_instance_max_sum"],
                "tcp_stall_instance_eligible_row_count": bucket[
                    "tcp_stall_instance_eligible_row_count"
                ],
                "tcc_write_stall_instance_max_sum": bucket["tcc_write_stall_instance_max_sum"],
                "tcc_write_stall_instance_eligible_row_count": bucket[
                    "tcc_write_stall_instance_eligible_row_count"
                ],
            }
        )

    kernel_rows: list[dict[str, Any]] = []
    launch_rows: list[dict[str, Any]] = []
    for group in groups:
        kernels = sorted({key[2] for key in leaves if key[0] == group}) + ["__GROUP_TOTAL__"]
        for kernel in kernels:
            for gpu in ("0", "1", "all"):
                pmc = expanded[(group, "pmc", kernel, gpu)]
                read = expanded[(group, "pmc_read", kernel, gpu)]
                write = expanded[(group, "pmc_write", kernel, gpu)]
                pmc_metrics = mode_metrics(pmc, "pmc")
                read_metrics = mode_metrics(read, "pmc_read")
                write_metrics = mode_metrics(write, "pmc_write")
                signature_sets = [set(part["launch_signatures"]) for part in (pmc, read, write)]
                kernel_rows.append(
                    {
                        "group_id": group,
                        "scope_kind": "group" if kernel == "__GROUP_TOTAL__" else "kernel",
                        "kernel_name": kernel,
                        "gpu_id": gpu,
                        "row_count_per_mode": pmc["row_count"],
                        "pmc_counter_numeric_row_count": pmc_metrics["counter_numeric_row_count"],
                        "pmc_counter_numeric_row_fraction": pmc_metrics[
                            "counter_numeric_row_fraction"
                        ],
                        "pmc_semantic_missing_counter_row_count": pmc_metrics[
                            "semantic_missing_counter_row_count"
                        ],
                        "pmc_read_counter_numeric_row_count": read_metrics[
                            "counter_numeric_row_count"
                        ],
                        "pmc_read_counter_numeric_row_fraction": read_metrics[
                            "counter_numeric_row_fraction"
                        ],
                        "pmc_read_semantic_missing_counter_row_count": read_metrics[
                            "semantic_missing_counter_row_count"
                        ],
                        "pmc_write_counter_numeric_row_count": write_metrics[
                            "counter_numeric_row_count"
                        ],
                        "pmc_write_counter_numeric_row_fraction": write_metrics[
                            "counter_numeric_row_fraction"
                        ],
                        "pmc_write_semantic_missing_counter_row_count": write_metrics[
                            "semantic_missing_counter_row_count"
                        ],
                        "GPUBusy_pct": pmc_metrics["GPUBusy_pct"],
                        "VALUBusy_pct": pmc_metrics["VALUBusy_pct"],
                        "LDSBankConflict_pct": pmc_metrics["LDSBankConflict_pct"],
                        "MemUnitStalled_pct": pmc_metrics["MemUnitStalled_pct"],
                        "MemUnitBusy_pct": pmc_metrics["MemUnitBusy_pct"],
                        "WriteUnitStalled_pct": pmc_metrics["WriteUnitStalled_pct"],
                        "L2CacheHit_pct": pmc_metrics["L2CacheHit_pct"],
                        "L2_hit_count": pmc_metrics["L2_hit_count"],
                        "L2_miss_count": pmc_metrics["L2_miss_count"],
                        "flat_read_wavefronts_sum": read_metrics["flat_read_wavefronts_sum"],
                        "read_requests_sum": read_metrics["read_requests_sum"],
                        "read_requests_32B_subset_sum": read_metrics["read_requests_32B_subset_sum"],
                        "flat_write_wavefronts_sum": write_metrics["flat_write_wavefronts_sum"],
                        "write_requests_sum": write_metrics["write_requests_sum"],
                        "write_requests_64B_subset_sum": write_metrics["write_requests_64B_subset_sum"],
                        "SQ_INSTS_VALU_sum": pmc_metrics["SQ_INSTS_VALU_sum"],
                        "SQ_INSTS_VMEM_RD_sum": pmc_metrics["SQ_INSTS_VMEM_RD_sum"],
                        "SQ_INSTS_VMEM_WR_sum": pmc_metrics["SQ_INSTS_VMEM_WR_sum"],
                        "SQ_INSTS_LDS_sum": pmc_metrics["SQ_INSTS_LDS_sum"],
                        "launch_shape_set_equal_across_modes": signature_sets[0]
                        == signature_sets[1]
                        == signature_sets[2],
                        "profiled_timing_is_production_latency": False,
                        "achieved_occupancy_available": False,
                    }
                )
                if kernel != "__GROUP_TOTAL__":
                    launch_rows.extend(launch_signature_rows(group, kernel, gpu, pmc))

    methodology = {
        "schema_version": 1,
        "status": "complete",
        "aggregation": "exclude only all-NONE counter payloads, sum available raw counters, then evaluate derived ratios; max(instance) is evaluated per eligible dispatch then summed",
        "device_constants": {
            "CU_NUM": CU_NUM,
            "SIMD_PER_CU": SIMD_PER_CU,
            "SIMD_NUM": SIMD_NUM,
            "SE_NUM": SE_NUM,
            "source": "fresh gfx936 rocminfo sealed by device_capabilities_006",
        },
        "formulas": {
            "GPUBusy_pct": "100*sum(GRBM_GUI_ACTIVE)/sum(GRBM_COUNT)",
            "VALUBusy_pct": "100*sum(SQ_ACTIVE_INST_VALU)*4/(320*sum(GRBM_GUI_ACTIVE))",
            "LDSBankConflict_pct": "100*sum(SQ_LDS_BANK_CONFLICT)/(80*sum(GRBM_GUI_ACTIVE))",
            "MemUnitStalled_pct": "100*sum(max_16(TCP_TCP_TA_DATA_STALL_CYCLES))/(8*sum(GRBM_GUI_ACTIVE))",
            "MemUnitBusy_pct": "100*sum(max_16(TA_TA_BUSY))/(8*sum(GRBM_GUI_ACTIVE))",
            "WriteUnitStalled_pct": "100*sum(max_64(TCC_EA_WRREQ_STALL,TCC_EA1_WRREQ_STALL))/sum(GRBM_GUI_ACTIVE)",
            "L2CacheHit_pct": "100*sum(TCC_HIT)/(sum(TCC_HIT)+sum(TCC_MISS))",
            "read_requests_sum": "sum(TCC_EA_RDREQ)+sum(TCC_EA1_RDREQ)",
            "write_requests_sum": "sum(TCC_EA_WRREQ)+sum(TCC_EA1_WRREQ)",
        },
        "formula_corrections": {
            "VALUBusy_pct": "Uses 320 total SIMD lanes groups (80 CU * 4 SIMD/CU); this supersedes the simplified capability-preflight note."
        },
        "semantic_missingness_policy": {
            "literal_NONE_meaning": "counter payload unavailable for that replay dispatch",
            "coerce_NONE_to_zero": False,
            "dispatch_metadata_retained": True,
            "counter_payload_excluded_from_numeric_aggregation": True,
            "coverage_fields_emitted": True,
        },
        "timestamp_semantics_policy": {
            "required_orderings": [
                "DispatchNs <= BeginNs <= EndNs",
                "DispatchNs <= CompleteNs"
            ],
            "EndNs_le_CompleteNs_required": False,
            "reason": "EndNs and CompleteNs are separately exported profiler event boundaries and show small ordering deltas; neither timing aggregate is used as production latency.",
            "counter_metrics_affected": False,
        },
        "limitations": [
            "HIPProf PMC replay serializes/replays selected kernels; exported timing columns are not production latency.",
            "Achieved occupancy samples are unavailable; launch resource signatures are retained only as a static pressure proxy.",
            "R07 marker coverage is 4240/13568 (31.25%); strict R08/R09 scheduler handoff is therefore forbidden.",
            "The chunk_ filter is an intentional bounded superset containing four observed kernel names.",
            "Twelve of 1,131,498 dispatch rows contain an all-NONE 186-counter payload; metadata is retained, counters are excluded, and every affected aggregate carries partial numeric coverage.",
            "10,047 rows have EndNs slightly greater than CompleteNs (maximum 13,128 ns); the two internally monotonic timing intervals are retained and explicitly marked non-production timing.",
        ],
    }

    semantic_missingness = {
        "schema_version": 1,
        "status": "complete",
        "source_row_count": total_source_rows,
        "counter_column_count_per_row": 186,
        "counter_numeric_complete_row_count": total_source_rows
        - total_semantic_missing_counter_rows,
        "semantic_missing_counter_row_count": total_semantic_missing_counter_rows,
        "semantic_missing_counter_cell_count": total_semantic_missing_counter_cells,
        "counter_numeric_complete_row_fraction": safe_ratio(
            total_source_rows - total_semantic_missing_counter_rows, total_source_rows
        ),
        "all_or_none_counter_payload_pattern_verified": True,
        "literal_NONE_coerced_to_zero": False,
        "handling": "retain dispatch metadata and timing; exclude unavailable counter payload from numerical sums; expose per-aggregate coverage",
        "affected_rows": semantic_missing_rows,
    }
    timestamp_semantics = {
        "schema_version": 1,
        "status": "complete",
        "source_row_count": total_source_rows,
        "required_orderings_verified": [
            "DispatchNs <= BeginNs <= EndNs",
            "DispatchNs <= CompleteNs",
        ],
        "end_gt_complete_row_count": total_end_gt_complete_rows,
        "end_gt_complete_row_fraction": safe_ratio(
            total_end_gt_complete_rows, total_source_rows
        ),
        "end_gt_complete_delta_ns_sum": total_end_gt_complete_delta_ns,
        "end_gt_complete_delta_ns_max": max_end_gt_complete_delta_ns,
        "counter_metrics_affected": False,
        "timing_is_production_latency": False,
        "examples_first_three_per_affected_segment": timestamp_order_examples,
    }

    segment_csv = output_root / "segment_inventory.csv"
    mode_csv = output_root / "mode_aggregates.csv"
    kernel_csv = output_root / "kernel_metrics.csv"
    launch_csv = output_root / "launch_signatures.csv"
    raw_json = output_root / "counter_aggregates.json"
    methodology_json = output_root / "methodology.json"
    semantic_missingness_json = output_root / "semantic_missingness.json"
    timestamp_semantics_json = output_root / "timestamp_semantics.json"
    write_csv_x(segment_csv, union_fieldnames(segment_inventory), segment_inventory)
    write_csv_x(mode_csv, union_fieldnames(mode_rows), mode_rows)
    write_csv_x(kernel_csv, union_fieldnames(kernel_rows), kernel_rows)
    write_csv_x(launch_csv, union_fieldnames(launch_rows), launch_rows)
    write_json_x(raw_json, {"schema_version": 1, "status": "complete", "aggregates": raw_aggregates})
    write_json_x(methodology_json, methodology)
    write_json_x(semantic_missingness_json, semantic_missingness)
    write_json_x(timestamp_semantics_json, timestamp_semantics)

    outputs = {
        "segment_inventory": file_record(segment_csv),
        "mode_aggregates": file_record(mode_csv),
        "kernel_metrics": file_record(kernel_csv),
        "launch_signatures": file_record(launch_csv),
        "counter_aggregates": file_record(raw_json),
        "methodology": file_record(methodology_json),
        "semantic_missingness": file_record(semantic_missingness_json),
        "timestamp_semantics": file_record(timestamp_semantics_json),
    }
    handoff = {
        "schema_version": 1,
        "status": "complete",
        "execution_status": "complete",
        "handoff_kind": "degraded_observed_subset_offline_continuation",
        "evidence_status": "degraded_R07_observed_subset",
        "strict_R08_handoff_eligible": False,
        "strict_R09_authorized": False,
        "degraded_R09_offline_analysis_authorized_by_existing_user_request": True,
        "dcu_required_after_this_handoff": False,
        "capture_segment_count": 9,
        "capture_segment_complete_count": 9,
        "source_row_count": total_source_rows,
        "counter_numeric_complete_row_count": total_source_rows
        - total_semantic_missing_counter_rows,
        "semantic_missing_counter_row_count": total_semantic_missing_counter_rows,
        "semantic_missing_counter_cell_count": total_semantic_missing_counter_cells,
        "counter_numeric_complete_row_fraction": safe_ratio(
            total_source_rows - total_semantic_missing_counter_rows, total_source_rows
        ),
        "literal_NONE_coerced_to_zero": False,
        "end_gt_complete_row_count": total_end_gt_complete_rows,
        "end_gt_complete_delta_ns_max": max_end_gt_complete_delta_ns,
        "profiled_timing_is_production_latency": False,
        "mode_count": 3,
        "group_count": 3,
        "kernel_name_count": len({key[2] for key in leaves}),
        "gpu_ids": [0, 1],
        "r07_source": {
            "path": str(R07_RECOVERY),
            "sha256": sha256_file(R07_RECOVERY),
            "coverage_target_met": False,
            "observed_target_count": r07_summary["observed_target_count"],
            "declared_target_count": r07_summary["declared_target_count"],
            "missing_target_count": r07_summary["missing_target_count"],
            "target_coverage_fraction": r07_summary["target_coverage_fraction"],
            "strict_scheduler_handoff_created": False,
        },
        "capability_report": file_record(CAPABILITY),
        "normalized_outputs": outputs,
        "limitations_sha256": canonical_sha256(methodology["limitations"]),
    }
    handoff_path = output_root / "R08_DEGRADED_HANDOFF.json"
    write_json_x(handoff_path, handoff)
    complete = {
        "schema_version": 1,
        "status": "complete",
        "finished_utc": utc_now(),
        "elapsed_seconds": time.monotonic() - started,
        "normalization_kind": "streaming_nine_segment_pmc_aggregate",
        "source_segment_count": 9,
        "source_row_count": total_source_rows,
        "counter_numeric_complete_row_count": total_source_rows
        - total_semantic_missing_counter_rows,
        "semantic_missing_counter_row_count": total_semantic_missing_counter_rows,
        "semantic_missing_counter_cell_count": total_semantic_missing_counter_cells,
        "end_gt_complete_row_count": total_end_gt_complete_rows,
        "end_gt_complete_delta_ns_max": max_end_gt_complete_delta_ns,
        "mode_aggregate_row_count": len(mode_rows),
        "kernel_metric_row_count": len(kernel_rows),
        "launch_signature_row_count": len(launch_rows),
        "outputs": outputs,
        "handoff_path": str(handoff_path),
        "handoff_sha256": sha256_file(handoff_path),
        "strict_R08_handoff_eligible": False,
        "evidence_status": "degraded_R07_observed_subset",
        "dcu_accessed": False,
    }
    write_json_x(output_root / "NORMALIZATION_COMPLETE.json", complete)
    print(
        json.dumps(
            {
                "status": "complete",
                "source_rows": total_source_rows,
                "kernel_metric_rows": len(kernel_rows),
                "elapsed_seconds": complete["elapsed_seconds"],
                "output_root": str(output_root),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
