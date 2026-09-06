#!/usr/bin/env python3
"""Normalize the sealed current-attempt hipprof database with strict ownership."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import stat
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from r07_common import (
    ARTIFACT_ROOT,
    ATTEMPT_ID,
    BULK_AUTH_PATH,
    BULK_ENTRYPOINTS,
    BULK_PATHS,
    BULK_ROOT,
    DURABLE_NFS_PATHS,
    DURABLE_NFS_ROOT,
    EXPECTED,
    LINEAGE_ID,
    R07_BOUND_TARGET_SIDECAR_PATH,
    R07_RUNTIME_BINDING_ROOT,
    RUN_ID,
    TRACE_PROFILE_ATTESTATION,
    audit_aot_seed_delta,
    bulk_object_identity,
    canonical_sha256,
    contained,
    require,
    require_equal,
    sha256_path,
    write_json_x,
)
from r07_marker_contract import exact_forward_name, exact_request_name, parse_name


CAPTURE_ROOT = ARTIFACT_ROOT / "capture"
RAW_ROOT = CAPTURE_ROOT / "raw"
HIPPROF_TMP = CAPTURE_ROOT / "hipprof_tmp"
RAW_INVENTORY_PATH = CAPTURE_ROOT / "raw_inventory.json"
LIFECYCLE_PATH = CAPTURE_ROOT / "lifecycle.json"
TRACE_ROOT = ARTIFACT_ROOT / "trace"
VALIDATION_ROOT = ARTIFACT_ROOT / "validation"
PROFILE_METADATA_PATH = CAPTURE_ROOT / "full_request_profile_metadata.json"
SUMMARY_PATH = TRACE_ROOT / "process_trace_summary.json"
COPY_MANIFEST_PATH = ARTIFACT_ROOT / "contract/r01_aot_cache_copy_manifest.json"
PREPOSTPROCESS_NATIVE_SEAL_PATH = (
    CAPTURE_ROOT / "prepostprocess_native_capture_seal.json"
)
DURABLE_COPY_MANIFEST_PATH = CAPTURE_ROOT / "durable_raw_copy_manifest.json"
DURABLE_COMPLETION_MARKER_PATH = DURABLE_NFS_ROOT / "DURABLE_COPY_COMPLETE.json"

REQUEST_CSV = TRACE_ROOT / "request_ranges.csv"
FORWARD_CSV = TRACE_ROOT / "forward_ranges.csv"
LAYER_CSV = TRACE_ROOT / "layer_ranges.csv"
PROCESS_CSV = TRACE_ROOT / "process_ranges.csv"
RUNTIME_CSV = TRACE_ROOT / "hip_runtime_calls.csv"
KERNEL_CSV = TRACE_ROOT / "strict_owned_kernels.csv"
QUEUE_CSV = TRACE_ROOT / "queue_stream_timeline.csv"
BUSY_CSV = TRACE_ROOT / "gpu_busy_union.csv"

PROVEN_LAUNCH_APIS = {
    "hipLaunchKernel",
    "hipModuleLaunchKernel",
    "hipExtModuleLaunchKernel",
}
PERF_COUNTER_PREFIXES = (
    "SQ_", "TCP_", "TCC_", "TA_", "TD_", "GRBM_", "CPC_", "SPI_",
    "GL1_", "GL2_", "LDS_", "VALU_", "SALU_",
)

PROCESS_FIELDS = [
    "process_range_id", "canonical_target_id", "canonical_target_sha256",
    "target_kind", "range_name", "parent_range_name", "request_id",
    "forward_id", "layer_idx", "layer_occurrence", "layer_type", "phase",
    "q_len", "kv_len", "process_id", "fragment_id", "aggregation_key",
    "dp_rank", "native_device", "pid", "tid", "config_key", "hiptx_table",
    "hiptx_rowid", "hiptx_range_index", "begin_ns", "end_ns", "duration_ns",
    "begin_runtime_index", "end_runtime_index", "depth",
    "explicit_no_kernel_target", "strict_kernel_owner",
    "sidecar_start_monotonic_ns", "sidecar_end_monotonic_ns",
    "sidecar_start_realtime_ns", "sidecar_end_realtime_ns",
    "sidecar_alignment_uncertainty_ns", "owned_runtime_call_count",
    "owned_kernel_count", "ownership_state", "evidence_class",
    "raw_database_sha256",
]

RANGE_FIELDS = [
    "range_id", "range_kind", "range_name", "request_id", "forward_id",
    "layer_idx", "layer_occurrence", "layer_type", "phase", "q_len", "kv_len",
    "dp_rank", "native_device", "pid", "tid", "config_key", "hiptx_table",
    "hiptx_rowid", "hiptx_range_index", "begin_ns", "end_ns", "duration_ns",
    "begin_runtime_index", "end_runtime_index", "evidence_class",
    "raw_database_sha256",
]

RUNTIME_FIELDS = [
    "runtime_call_id", "owner_process_range_id", "owner_canonical_target_id",
    "request_id", "forward_id", "layer_idx", "layer_occurrence", "process_id",
    "fragment_id", "dp_rank", "native_device", "pid", "tid", "config_key",
    "hip_runtime_table", "hip_runtime_rowid", "hip_runtime_index", "hip_runtime_api",
    "hip_runtime_args", "begin_ns", "end_ns", "duration_ns", "is_kernel_launch",
    "launch_correlation_state", "evidence_class", "raw_database_sha256",
]

KERNEL_FIELDS = [
    "kernel_instance_id", "owner_process_range_id", "owner_canonical_target_id",
    "request_id", "forward_id", "layer_idx", "layer_occurrence", "process_id",
    "fragment_id", "dp_rank", "native_device", "pid", "config_key",
    "hip_runtime_table", "hip_runtime_rowid", "hip_runtime_index", "hip_runtime_api",
    "native_device_table", "native_device_rowid", "native_device_index",
    "begin_ns", "end_ns", "duration_ns", "queue_id", "stream_id",
    "native_kernel_name", "ownership_depth", "ownership_chain",
    "evidence_class", "raw_database_sha256",
]


def select_deepest_owner(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Require one strict ancestry chain and return its unique deepest member."""
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("strict ownership candidate set is empty")

    def ancestor(left: dict[str, Any], right: dict[str, Any]) -> bool:
        return str(left["range_name"]) in {str(value) for value in right.get("ancestry", [])}

    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            left_contains = (
                int(left["begin_ns"]) <= int(right["begin_ns"])
                and int(right["end_ns"]) <= int(left["end_ns"])
            )
            right_contains = (
                int(right["begin_ns"]) <= int(left["begin_ns"])
                and int(left["end_ns"]) <= int(right["end_ns"])
            )
            if not ((ancestor(left, right) and left_contains) or (ancestor(right, left) and right_contains)):
                raise RuntimeError(
                    "strict ownership ambiguity: non-ancestor overlapping candidates "
                    f"{left['range_name']!r} and {right['range_name']!r}"
                )
    deepest_depth = max(int(row.get("depth", 0)) for row in candidates)
    deepest = [row for row in candidates if int(row.get("depth", 0)) == deepest_depth]
    if len(deepest) != 1:
        raise RuntimeError("strict ownership has no unique deepest candidate")
    return deepest[0]


def classify_trace_counter_semantics(metadata: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise RuntimeError("trace-counter metadata must be an object")
    trace_types = metadata.get("trace_types")
    category = metadata.get("semantic_category")
    counter_columns = metadata.get("counter_columns")
    if (
        not isinstance(trace_types, list)
        or not trace_types
        or not all(isinstance(value, str) and value for value in trace_types)
        or not isinstance(category, str)
        or not isinstance(counter_columns, list)
        or not all(isinstance(value, str) for value in counter_columns)
    ):
        raise RuntimeError("malformed trace-counter semantic metadata")
    actual_counter_columns = [
        value for value in counter_columns
        if value.upper().startswith(PERF_COUNTER_PREFIXES)
    ]
    pmc_type = any("PMC" in value.upper() for value in trace_types)
    if category == "pmc" and pmc_type and actual_counter_columns:
        return {
            "is_pmc_evidence": True,
            "trace_types": sorted(set(trace_types)),
            "counter_columns": sorted(actual_counter_columns),
            "classification_basis": "explicit_pmc_category_type_and_counter_columns",
        }
    if category in {"timeline", "trace_metadata"} and not actual_counter_columns and not pmc_type:
        return {
            "is_pmc_evidence": False,
            "trace_types": sorted(set(trace_types)),
            "counter_columns": [],
            "classification_basis": "timeline_schema_without_pmc_semantics",
        }
    raise RuntimeError("unknown trace-counter semantics")


EVENT_REQUIRED_FIELDS = {
    "kind", "marker_kind", "record_kind", "range_name", "range_identity",
    "parent_name", "depth", "pid", "tid", "start_realtime_ns",
    "end_realtime_ns", "start_monotonic_ns", "end_monotonic_ns",
    "request_id", "forward_id", "layer_idx", "layer_occurrence", "layer_type",
    "phase", "q_len", "kv_len", "process_id", "fragment_id", "aggregation_key",
    "target_kind", "canonical_target_id", "canonical_target_sha256", "dp_rank",
    "physical_device_id", "strict_kernel_owner", "explicit_no_kernel_target",
    "canonical_logical_selection_id", "canonical_logical_selection_sha256",
    "canonical_bound_selection_id", "canonical_bound_selection_sha256",
    "phase_occurrence", "runtime_execution_id",
}


def validate_sidecar_event(event: dict[str, Any]) -> None:
    if not isinstance(event, dict):
        raise RuntimeError("sidecar event must be an object")
    missing = sorted(EVENT_REQUIRED_FIELDS - set(event))
    if missing:
        raise RuntimeError(f"sidecar event missing fields: {missing}")
    if event["kind"] != "r07_exact_range" or event["marker_kind"] != "process":
        raise RuntimeError("sidecar event kind mismatch")
    if event["record_kind"] != "r07_process_range":
        raise RuntimeError("sidecar record kind mismatch")
    for prefix in ("start", "end"):
        for clock in ("realtime", "monotonic"):
            value = event[f"{prefix}_{clock}_ns"]
            if not isinstance(value, int) or value <= 0:
                raise RuntimeError(f"invalid sidecar clock: {prefix}_{clock}_ns")
    if int(event["end_realtime_ns"]) <= int(event["start_realtime_ns"]):
        raise RuntimeError("non-positive sidecar realtime interval")
    if int(event["end_monotonic_ns"]) <= int(event["start_monotonic_ns"]):
        raise RuntimeError("non-positive sidecar monotonic interval")
    if int(event["dp_rank"]) not in {0, 1} or int(event["physical_device_id"]) != int(event["dp_rank"]):
        raise RuntimeError("sidecar rank/device mapping mismatch")
    if hashlib.sha256(str(event["range_name"]).encode("utf-8")).hexdigest() != event["range_identity"]:
        raise RuntimeError("sidecar range identity mismatch")


def _write_csv_x(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    contained(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _column(row: dict[str, Any], *names: str) -> Any:
    by_lower = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        if name in row:
            return row[name]
        if name.lower() in by_lower:
            return by_lower[name.lower()]
    raise RuntimeError(f"native schema missing columns {names}")


def _optional_column(row: dict[str, Any], *names: str, default: Any = "") -> Any:
    try:
        return _column(row, *names)
    except RuntimeError:
        return default


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _api_name(arguments: Any) -> str:
    if arguments is None:
        return ""
    try:
        value = json.loads(str(arguments))
    except json.JSONDecodeError:
        value = str(arguments)
    if isinstance(value, dict):
        value = str(value.get("Name") or value.get("name") or "")
    else:
        value = str(value)
    # attempt-043 stores the API name and its rendered arguments in one field,
    # while the launch allowlist is intentionally keyed by the bare API name.
    return value.split("(", 1)[0].strip()


def _discover_pftrace(raw_root: Path) -> tuple[str, list[Path]]:
    members = sorted(raw_root.glob("*.pftrace"), key=lambda path: path.name)
    single = raw_root / "capture.pftrace"
    segmented: list[tuple[int, Path]] = []
    unexpected = []
    pattern = re.compile(r"capture_([1-9][0-9]*)\.pftrace")
    for path in members:
        if path == single:
            continue
        match = pattern.fullmatch(path.name)
        if match is None:
            unexpected.append(path.name)
        else:
            segmented.append((int(match.group(1)), path))
    require_equal("unexpected PFTrace members", unexpected, [])
    if single.is_file():
        require_equal("segmented members beside single PFTrace", segmented, [])
        require(single.stat().st_size > 0, "single PFTrace is empty")
        return "single_file", [single]
    require(segmented, "logical PFTrace family missing")
    segmented.sort()
    require_equal("PFTrace segment sequence", [item[0] for item in segmented], list(range(1, len(segmented) + 1)))
    require(all(path.stat().st_size > 0 for _, path in segmented), "empty PFTrace segment")
    return "native_segmented", [path for _, path in segmented]


def _bulk_file_identity(entrypoint_root: Path, storage_root: Path, path: Path, role: str) -> dict[str, Any]:
    row = bulk_object_identity(entrypoint_root, storage_root, path, role)
    require_equal(f"bulk regular object kind {path}", row["object_kind"], "regular_file")
    row["attempt_and_storage_identity_equal"] = True
    return row


def _validate_prepostprocess_native_seal(
    lifecycle: dict[str, Any],
) -> dict[str, Any]:
    require(
        PREPOSTPROCESS_NATIVE_SEAL_PATH.is_file()
        and not PREPOSTPROCESS_NATIVE_SEAL_PATH.is_symlink(),
        "pre-postprocess native capture seal missing/nonregular",
    )
    seal_sha256 = sha256_path(PREPOSTPROCESS_NATIVE_SEAL_PATH)
    lifecycle_ref = lifecycle.get("prepostprocess_native_capture_seal")
    require(isinstance(lifecycle_ref, dict), "lifecycle native seal reference missing")
    require_equal(
        "lifecycle native seal path",
        lifecycle_ref.get("path"),
        str(PREPOSTPROCESS_NATIVE_SEAL_PATH),
    )
    require_equal(
        "lifecycle native seal SHA-256",
        lifecycle_ref.get("sha256"),
        seal_sha256,
    )
    seal = json.loads(PREPOSTPROCESS_NATIVE_SEAL_PATH.read_text(encoding="utf-8"))
    require_equal("native seal status", seal.get("status"), "complete")
    require_equal("native seal run", seal.get("runtime_run_id"), RUN_ID)
    require_equal("native seal attempt", seal.get("runtime_attempt_id"), ATTEMPT_ID)
    require_equal("native seal lineage", seal.get("lineage_id"), LINEAGE_ID)
    require_equal(
        "native seal phase",
        seal.get("seal_phase"),
        "after_all_capture_workers_exited_before_any_postprocess",
    )
    require_equal(
        "native seal preexisting postprocess outputs",
        seal.get("postprocess_outputs_present_at_seal"),
        [],
    )

    regular_refs = [seal.get("database"), *seal.get("pftrace_members", [])]
    regular_refs.extend(seal.get("binding_logs", []))
    regular_refs.append(seal.get("bound_target_sidecar"))
    for row in regular_refs:
        require(isinstance(row, dict), "native seal regular-file row malformed")
        path = Path(str(row.get("path", "")))
        require(path.is_file() and not path.is_symlink(), f"sealed file missing/nonregular: {path}")
        require_equal(f"sealed file size {path}", path.stat().st_size, int(row["size"]))
        require_equal(f"sealed file SHA-256 {path}", sha256_path(path), row["sha256"])

    require_equal(
        "bound target sidecar seal path",
        seal["bound_target_sidecar"]["path"],
        str(R07_BOUND_TARGET_SIDECAR_PATH),
    )
    require_equal(
        "bound target sidecar seal SHA-256",
        seal["bound_target_sidecar"]["sha256"],
        sha256_path(R07_BOUND_TARGET_SIDECAR_PATH),
    )
    binding_paths = {
        Path(str(row["path"])) for row in seal.get("binding_logs", [])
    }
    require_equal(
        "native seal rank binding paths",
        binding_paths,
        {R07_RUNTIME_BINDING_ROOT / "rank0.jsonl", R07_RUNTIME_BINDING_ROOT / "rank1.jsonl"},
    )

    for row in seal.get("raw_objects", []):
        require(isinstance(row, dict), "native seal raw-object row malformed")
        path = RAW_ROOT / str(row["attempt_entrypoint_relative_path"])
        observed = bulk_object_identity(
            RAW_ROOT,
            BULK_PATHS["raw"],
            path,
            "prepostprocess_native_raw_object_revalidation",
        )
        for field in (
            "attempt_entrypoint_path",
            "attempt_entrypoint_relative_path",
            "storage_relative_path",
            "storage_path",
            "object_kind",
            "attempt_lstat",
            "storage_lstat",
            "filesystem_device",
            "inode",
            "mode",
            "size",
            "sha256",
        ):
            require_equal(
                f"native seal raw object {field} {path}",
                observed.get(field),
                row.get(field),
            )
        if row["object_kind"] != "regular_file":
            require(row.get("sha256") is None, "nonregular native object has content SHA-256")
    return {
        "path": str(PREPOSTPROCESS_NATIVE_SEAL_PATH),
        "sha256": seal_sha256,
        "database_sha256": seal["database"]["sha256"],
        "pftrace_mode": seal["pftrace_mode"],
        "pftrace_member_count": int(seal["pftrace_member_count"]),
        "bound_target_sidecar_sha256": seal["bound_target_sidecar"]["sha256"],
        "validated_before_postprocess": True,
    }


def _validate_durable_copy_before_postprocess(
    lifecycle: dict[str, Any], native_seal: dict[str, Any],
) -> dict[str, Any]:
    """Independently rehash the marker-complete same-attempt durable surface."""
    authorization = json.loads(BULK_AUTH_PATH.read_text(encoding="utf-8"))
    durable = authorization.get("durable_nfs_storage")
    require(isinstance(durable, dict), "signed durable NFS storage contract missing")
    require_equal(
        "durable NFS storage canonical identity",
        canonical_sha256(durable),
        EXPECTED["durable_nfs_storage_sha256"],
    )
    require_equal("durable NFS root contract", Path(durable["root"]), DURABLE_NFS_ROOT)
    require_equal(
        "durable NFS path contract",
        {name: Path(path) for name, path in durable["paths"].items()},
        DURABLE_NFS_PATHS,
    )
    require(DURABLE_NFS_ROOT.is_dir() and not DURABLE_NFS_ROOT.is_symlink(), "durable NFS root invalid")
    require_equal("durable NFS filesystem device", DURABLE_NFS_ROOT.stat().st_dev, int(durable["filesystem_device"]))
    require(DURABLE_NFS_PATHS["raw"].is_dir() and not DURABLE_NFS_PATHS["raw"].is_symlink(), "durable raw root invalid")
    require(DURABLE_COPY_MANIFEST_PATH.is_file() and not DURABLE_COPY_MANIFEST_PATH.is_symlink(), "durable copy manifest missing/nonregular")
    require(DURABLE_COMPLETION_MARKER_PATH.is_file() and not DURABLE_COMPLETION_MARKER_PATH.is_symlink(), "durable completion marker missing/nonregular")

    completion = lifecycle.get("durable_raw_completion")
    require(isinstance(completion, dict), "lifecycle durable completion reference missing")
    for label, path, reference in (
        ("manifest", DURABLE_COPY_MANIFEST_PATH, completion.get("manifest")),
        ("completion marker", DURABLE_COMPLETION_MARKER_PATH, completion.get("completion_marker")),
    ):
        require(isinstance(reference, dict), f"lifecycle durable {label} reference malformed")
        require_equal(f"lifecycle durable {label} path", reference.get("path"), str(path))
        require_equal(f"lifecycle durable {label} size", int(reference.get("size", -1)), path.stat().st_size)
        require_equal(f"lifecycle durable {label} SHA-256", reference.get("sha256"), sha256_path(path))

    manifest = json.loads(DURABLE_COPY_MANIFEST_PATH.read_text(encoding="utf-8"))
    marker = json.loads(DURABLE_COMPLETION_MARKER_PATH.read_text(encoding="utf-8"))
    for label, document in (("durable manifest", manifest), ("durable marker", marker)):
        require_equal(f"{label} status", document.get("status"), "complete")
        require_equal(f"{label} run", document.get("runtime_run_id"), RUN_ID)
        require_equal(f"{label} attempt", document.get("runtime_attempt_id"), ATTEMPT_ID)
        require_equal(f"{label} lineage", document.get("lineage_id"), LINEAGE_ID)
        require_equal(f"{label} profile", document.get("trace_profile_sha256"), EXPECTED["profile_sha256"])
    require_equal("durable manifest copy phase", manifest.get("copy_phase"), durable["copy_phase"])
    require_equal("durable manifest source root", manifest.get("source_root"), str(ARTIFACT_ROOT))
    require_equal("durable manifest destination root", manifest.get("destination_root"), str(DURABLE_NFS_PATHS["raw"]))
    require_equal("durable marker destination root", marker.get("destination_root"), str(DURABLE_NFS_PATHS["raw"]))
    require_equal("durable native-seal reference", manifest.get("source_native_prepostprocess_seal"), lifecycle["prepostprocess_native_capture_seal"])
    require_equal("durable native-seal hash", manifest["source_native_prepostprocess_seal"]["sha256"], native_seal["sha256"])

    source_rows = manifest.get("source_rows")
    copy_rows = manifest.get("copy_rows")
    sealed_destination_rows = manifest.get("destination_rows")
    require(isinstance(source_rows, list) and isinstance(copy_rows, list) and isinstance(sealed_destination_rows, list), "durable manifest row arrays malformed")
    observed_source_rows = []
    for row in source_rows:
        source = Path(str(row["source_path"]))
        contained(source, must_exist=True)
        require(source.is_file() and not source.is_symlink(), f"durable source missing/nonregular: {source}")
        require_equal("durable source relative path", source.relative_to(ARTIFACT_ROOT).as_posix(), row["relative_path"])
        observed_source_rows.append({
            "relative_path": row["relative_path"],
            "size": source.stat().st_size,
            "sha256": sha256_path(source),
            "mode": stat.S_IMODE(source.lstat().st_mode),
        })
    observed_source_rows.sort(key=lambda row: row["relative_path"])
    require_equal("durable source relative-path uniqueness", len({row["relative_path"] for row in observed_source_rows}), len(observed_source_rows))

    observed_destination_rows = []
    destination_mtimes = []
    for path in sorted(DURABLE_NFS_PATHS["raw"].rglob("*"), key=lambda item: item.relative_to(DURABLE_NFS_PATHS["raw"]).as_posix()):
        mode = path.lstat().st_mode
        require(not stat.S_ISLNK(mode), f"durable destination symlink forbidden: {path}")
        if stat.S_ISDIR(mode):
            continue
        require(stat.S_ISREG(mode), f"durable destination nonregular object forbidden: {path}")
        require(".r07-attempt-043.partial" not in path.name, f"durable partial file remained: {path}")
        observed_destination_rows.append({
            "relative_path": path.relative_to(DURABLE_NFS_PATHS["raw"]).as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256_path(path),
            "mode": stat.S_IMODE(mode),
        })
        destination_mtimes.append(path.stat().st_mtime_ns)
    require_equal("durable source/destination regular-file surface", observed_destination_rows, observed_source_rows)
    require_equal("durable sealed destination rows", sealed_destination_rows, observed_destination_rows)
    require_equal("durable row counts", len(copy_rows), len(observed_source_rows))
    for source_row, copy_row in zip(source_rows, copy_rows):
        for field in ("relative_path", "size", "sha256", "mode", "source_path", "source_role"):
            require_equal(f"durable copy row {field}", copy_row.get(field), source_row.get(field))
        require_equal(
            "durable copy destination path",
            copy_row.get("destination_path"),
            str(DURABLE_NFS_PATHS["raw"] / source_row["relative_path"]),
        )
        require(copy_row.get("copy_state") in {"temporary_verified_then_atomic_rename", "existing_destination_revalidated"}, "durable copy state invalid")

    surface_identity = canonical_sha256(observed_source_rows)
    total_bytes = sum(int(row["size"]) for row in observed_source_rows)
    require_equal("durable manifest source identity", manifest.get("source_surface_canonical_sha256"), surface_identity)
    require_equal("durable manifest destination identity", manifest.get("destination_surface_canonical_sha256"), surface_identity)
    require_equal("durable manifest file count", int(manifest.get("regular_file_count", -1)), len(observed_source_rows))
    require_equal("durable manifest total bytes", int(manifest.get("regular_file_total_bytes", -1)), total_bytes)
    require_equal("durable marker manifest reference path", marker["manifest"]["path"], str(DURABLE_COPY_MANIFEST_PATH))
    require_equal("durable marker manifest reference size", int(marker["manifest"]["size"]), DURABLE_COPY_MANIFEST_PATH.stat().st_size)
    require_equal("durable marker manifest reference hash", marker["manifest"]["sha256"], sha256_path(DURABLE_COPY_MANIFEST_PATH))
    require_equal("durable marker surface identity", marker.get("destination_surface_canonical_sha256"), surface_identity)
    require_equal("durable marker file count", int(marker.get("regular_file_count", -1)), len(observed_source_rows))
    require_equal("durable marker total bytes", int(marker.get("regular_file_total_bytes", -1)), total_bytes)
    require(marker.get("completion_marker_written_last") is True, "durable marker-last flag missing")
    require(marker.get("staging_preserved") is True and manifest.get("staging_deleted") is False, "durable staging preservation gate failed")
    require(manifest.get("every_destination_size_and_sha256_verified") is True, "durable per-file verification gate missing")
    require(manifest.get("destination_surface_independently_rehashed") is True, "durable destination rehash gate missing")
    require(manifest.get("nonregular_objects_copied") is False, "durable nonregular object copied")
    require_equal("durable root final entries", {path.name for path in DURABLE_NFS_ROOT.iterdir()}, {"raw", DURABLE_COMPLETION_MARKER_PATH.name})
    marker_mtime = DURABLE_COMPLETION_MARKER_PATH.stat().st_mtime_ns
    require(marker_mtime >= DURABLE_COPY_MANIFEST_PATH.stat().st_mtime_ns, "durable marker predates its manifest")
    require(not destination_mtimes or marker_mtime >= max(destination_mtimes), "durable marker predates a destination member")
    require_equal("lifecycle durable surface identity", completion.get("destination_surface_canonical_sha256"), surface_identity)
    require_equal("lifecycle durable file count", int(completion.get("regular_file_count", -1)), len(observed_source_rows))
    require_equal("lifecycle durable total bytes", int(completion.get("regular_file_total_bytes", -1)), total_bytes)
    return {
        "status": "complete",
        "manifest_path": str(DURABLE_COPY_MANIFEST_PATH),
        "manifest_sha256": sha256_path(DURABLE_COPY_MANIFEST_PATH),
        "completion_marker_path": str(DURABLE_COMPLETION_MARKER_PATH),
        "completion_marker_sha256": sha256_path(DURABLE_COMPLETION_MARKER_PATH),
        "destination_root": str(DURABLE_NFS_PATHS["raw"]),
        "regular_file_count": len(observed_source_rows),
        "regular_file_total_bytes": total_bytes,
        "surface_canonical_sha256": surface_identity,
        "source_and_destination_independently_rehashed": True,
        "completion_marker_verified_last": True,
        "staging_preserved": True,
        "validated_before_postprocess": True,
    }


def inventory_raw() -> dict[str, Any]:
    require(not RAW_INVENTORY_PATH.exists(), "raw inventory already exists")
    require_equal("bulk authorization hash", sha256_path(BULK_AUTH_PATH), EXPECTED["bulk_storage_authorization_sha256"])
    authorization = json.loads(BULK_AUTH_PATH.read_text(encoding="utf-8"))
    require_equal("bulk authorization status", authorization["status"], "authorized")
    for name, entrypoint in BULK_ENTRYPOINTS.items():
        require(entrypoint.is_symlink(), f"bulk entrypoint is not a symlink: {name}")
        require_equal(f"bulk link text {name}", os.readlink(entrypoint), str(BULK_PATHS[name]))
        require_equal(f"bulk target {name}", entrypoint.resolve(strict=True), BULK_PATHS[name].resolve(strict=True))
    lifecycle = json.loads(LIFECYCLE_PATH.read_text(encoding="utf-8"))
    require_equal("capture lifecycle status", lifecycle["status"], "complete")
    require(lifecycle["all_started_processes_terminated"] is True, "capture processes not terminated before raw sealing")
    native_seal = _validate_prepostprocess_native_seal(lifecycle)
    durable_copy = _validate_durable_copy_before_postprocess(lifecycle, native_seal)
    primary_db = sorted(RAW_ROOT.glob("*.db"))
    require_equal("primary database count", len(primary_db), 1)
    require_equal("primary database name", primary_db[0].name, "capture.db")
    require(primary_db[0].stat().st_size > 0, "capture database is empty")
    pftrace_mode, pftrace_members = _discover_pftrace(RAW_ROOT)
    allowed_plain = {"capture.log", "service.log", "service_start_validation.json"}
    auxiliary_pattern = re.compile(r"capture(?:\.db)?\.(?:hipkernel|hiptrace|hsatrace)\.csv")
    pftrace_names = {path.name for path in pftrace_members}
    nonregular_rows = []
    directory_counts: dict[str, int] = {}
    for name, root in BULK_ENTRYPOINTS.items():
        directory_count = 0
        for path in root.rglob("*"):
            mode = path.lstat().st_mode
            require(not stat.S_ISLNK(mode), f"nested symlink forbidden in authorized bulk entrypoint {name}: {path}")
            if stat.S_ISDIR(mode):
                directory_count += 1
                continue
            if stat.S_ISREG(mode):
                continue
            nonregular_rows.append(
                bulk_object_identity(
                    root,
                    BULK_PATHS[name],
                    path,
                    f"preserved_nonregular_{name}",
                )
            )
        directory_counts[name] = directory_count
    raw_files = sorted((path for path in RAW_ROOT.rglob("*") if path.is_file()), key=lambda path: path.relative_to(RAW_ROOT).as_posix())
    unknown = []
    rows = []
    for path in raw_files:
        require(not path.is_symlink(), f"raw nested symlink forbidden: {path}")
        relative = path.relative_to(RAW_ROOT).as_posix()
        require("/" not in relative, f"unexpected nested raw file: {relative}")
        if path.name == "capture.db":
            role = "required_primary_database"
        elif path.name in pftrace_names:
            role = "required_primary_pftrace" if pftrace_mode == "single_file" else "required_primary_pftrace_segment"
        elif auxiliary_pattern.fullmatch(path.name):
            role = "known_auxiliary_" + path.name.rsplit(".", 2)[-2]
        elif path.name in allowed_plain:
            role = path.name.replace(".", "_")
        else:
            unknown.append(relative)
            continue
        rows.append(_bulk_file_identity(RAW_ROOT, BULK_PATHS["raw"], path, role))
    require_equal("unknown raw types", unknown, [])
    tmp_rows = []
    for path in sorted((item for item in HIPPROF_TMP.rglob("*") if item.is_file()), key=lambda item: item.relative_to(HIPPROF_TMP).as_posix()):
        require(not path.is_symlink(), f"hipprof temporary nested symlink forbidden: {path}")
        tmp_rows.append(_bulk_file_identity(HIPPROF_TMP, BULK_PATHS["hipprof_tmp"], path, "known_hipprof_temporary"))

    copy_manifest = json.loads(COPY_MANIFEST_PATH.read_text(encoding="utf-8"))
    require_equal("R01 AOT copy manifest status", copy_manifest["status"], "complete")
    initial_cache = {row["relative_path"]: row for row in copy_manifest["files"]}
    cache_rows = []
    observed_initial_cache = set()
    for path in sorted((item for item in BULK_ENTRYPOINTS["aot_cache"].rglob("*") if item.is_file()), key=lambda item: item.relative_to(BULK_ENTRYPOINTS["aot_cache"]).as_posix()):
        relative = path.relative_to(BULK_ENTRYPOINTS["aot_cache"]).as_posix()
        initial = initial_cache.get(relative)
        role = "same_lineage_R01_direct_copy" if initial is not None else "current_R07_runtime_cache_output"
        row = _bulk_file_identity(BULK_ENTRYPOINTS["aot_cache"], BULK_PATHS["aot_cache"], path, role)
        if initial is not None:
            require_equal(f"initial AOT cache size after capture {relative}", row["size"], int(initial["size"]))
            require_equal(f"initial AOT cache hash after capture {relative}", row["sha256"], initial["sha256"])
            observed_initial_cache.add(relative)
        cache_rows.append(row)
    require_equal("all initial R01 cache members preserved", observed_initial_cache, set(initial_cache))
    current_cache = {
        row["attempt_entrypoint_relative_path"]: {
            "relative_path": row["attempt_entrypoint_relative_path"],
            "size": int(row["size"]),
            "sha256": row["sha256"],
        }
        for row in cache_rows
    }
    aot_delta = audit_aot_seed_delta(
        initial_cache,
        current_cache,
        added_provenance="current_attempt_runtime_derivation",
        seed_identity=copy_manifest["aot_seed_identity"],
    )
    service_validation = json.loads(
        (RAW_ROOT / "service_start_validation.json").read_text(encoding="utf-8")
    )
    if service_validation["aot_load_mode"] == "current_attempt_runtime_derivation":
        require(aot_delta["derived_identity_count"] >= 1, "service derived AOT but no derived identity was sealed")
        derived_identities = {row["identity"] for row in aot_delta["derived_identities"]}
        require(
            service_validation["aot_cache_identity"] in derived_identities,
            "service-selected derived AOT identity absent from current-attempt delta",
        )
    cache_tree_identity = canonical_sha256([
        {
            "relative_path": row["attempt_entrypoint_relative_path"],
            "size": row["size"],
            "sha256": row["sha256"],
            "role": row["role"],
        }
        for row in cache_rows
    ])

    sealed_sidecars = []
    sidecar_roots = [ARTIFACT_ROOT / "live_utilization", CAPTURE_ROOT / "workload", CAPTURE_ROOT / "control"]
    for root in sidecar_roots:
        require(root.is_dir(), f"capture sidecar root missing: {root}")
        for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.relative_to(ARTIFACT_ROOT).as_posix()):
            require(not path.is_symlink(), f"sidecar symlink forbidden: {path}")
            sealed_sidecars.append({
                "relative_path": path.relative_to(ARTIFACT_ROOT).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_path(path),
                "role": "sealed_current_capture_sidecar",
            })
    for path in (
        LIFECYCLE_PATH,
        PREPOSTPROCESS_NATIVE_SEAL_PATH,
        R07_BOUND_TARGET_SIDECAR_PATH,
        R07_RUNTIME_BINDING_ROOT / "rank0.jsonl",
        R07_RUNTIME_BINDING_ROOT / "rank1.jsonl",
    ):
        require(path.is_file() and not path.is_symlink(), f"sealed capture sidecar missing/nonregular: {path}")
        sealed_sidecars.append({
            "relative_path": path.relative_to(ARTIFACT_ROOT).as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256_path(path),
            "role": "sealed_capture_lifecycle",
        })
    anchors_path = ARTIFACT_ROOT / "live_utilization/clock_anchors.json"
    anchors = json.loads(anchors_path.read_text(encoding="utf-8"))
    require_equal("collector status", anchors["status"], "complete")
    require_equal("collector sample hash", anchors["raw_samples_sha256"], sha256_path(ARTIFACT_ROOT / "live_utilization/raw_samples.csv"))
    require_equal("collector gap hash", anchors["raw_gap_intervals_sha256"], sha256_path(ARTIFACT_ROOT / "live_utilization/raw_gap_intervals.csv"))
    document = {
        "schema_version": 1,
        "status": "complete",
        "runtime_run_id": RUN_ID,
        "runtime_attempt_id": ATTEMPT_ID,
        "lineage_id": LINEAGE_ID,
        "trace_profile_sha256": EXPECTED["profile_sha256"],
        "bulk_storage_authorization_path": str(BULK_AUTH_PATH),
        "bulk_storage_authorization_sha256": EXPECTED["bulk_storage_authorization_sha256"],
        "bulk_storage_root": str(BULK_ROOT),
        "raw_entrypoint": str(RAW_ROOT),
        "hipprof_tmp_entrypoint": str(HIPPROF_TMP),
        "required_primary_database_count": 1,
        "required_primary_pftrace_logical_family_count": 1,
        "required_primary_pftrace_mode": pftrace_mode,
        "required_primary_pftrace_file_count": len(pftrace_members),
        "required_primary_pftrace_ordered_paths": [path.relative_to(RAW_ROOT).as_posix() for path in pftrace_members],
        "required_primary_pftrace_total_size": sum(path.stat().st_size for path in pftrace_members),
        "unknown_raw_files": [],
        "unknown_raw_file_count": 0,
        "raw_files": rows,
        "hipprof_temporary_files": tmp_rows,
        "aot_cache_files": cache_rows,
        "nonregular_bulk_objects": nonregular_rows,
        "nonregular_bulk_object_count": len(nonregular_rows),
        "nonregular_bulk_object_kind_counts": dict(sorted(Counter(
            row["object_kind"] for row in nonregular_rows
        ).items())),
        "bulk_directory_counts": directory_counts,
        "aot_cache_file_count": len(cache_rows),
        "aot_cache_total_bytes": sum(int(row["size"]) for row in cache_rows),
        "aot_cache_tree_identity_sha256": cache_tree_identity,
        "initial_R01_direct_copy_cache_file_count": len(initial_cache),
        "current_R07_runtime_cache_output_file_count": sum(row["role"] == "current_R07_runtime_cache_output" for row in cache_rows),
        "aot_seed_and_current_attempt_derivation": aot_delta,
        "all_three_bulk_entrypoints_fully_inventoried": True,
        "sealed_sidecars": sealed_sidecars,
        "prepostprocess_native_capture_seal": native_seal,
        "durable_raw_copy": durable_copy,
        "raw_sample_count": int(anchors["sample_count"]),
        "raw_gap_interval_count": int(anchors["gap_interval_count"]),
        "all_raw_bytes_sealed": True,
        "all_external_bulk_bytes_sealed": True,
        "all_bulk_files_hashed_through_both_paths": True,
        "all_nonregular_objects_sealed_by_dual_path_lstat": True,
        "all_nonregular_objects_preserved_without_deletion": True,
        "nonregular_objects_have_no_fabricated_content_sha256": all(
            row["sha256"] is None for row in nonregular_rows
        ),
        "raw_bytes_renamed_rewritten_or_deleted": False,
        "external_or_historical_runtime_evidence_consumed": False,
    }
    write_json_x(RAW_INVENTORY_PATH, document)
    return document


def _load_process_events() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    sidecar = json.loads(R07_BOUND_TARGET_SIDECAR_PATH.read_text(encoding="utf-8"))
    selection = [
        row for row in sidecar["records"] if row["target_kind"] == "layer_parent"
    ]
    expected_process = Counter(sidecar["ordered_exact_name_multiset"])
    expected_layer = Counter(row["layer_marker_utf8"] for row in selection)
    expected_request = Counter(exact_request_name(row) for row in selection)
    expected_forward = Counter(exact_forward_name(row) for row in selection)
    observed: dict[str, Counter[str]] = defaultdict(Counter)
    process_by_name: dict[str, dict[str, Any]] = {}
    files = []
    event_paths = sorted((CAPTURE_ROOT / "workload/overlay_events").glob("rank*/events.*.jsonl"))
    require(event_paths, "overlay event files missing")
    for path in event_paths:
        count = 0
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                require_equal("event attempt", row["runtime_attempt_id"], ATTEMPT_ID)
                require_equal("event lineage", row["lineage_id"], LINEAGE_ID)
                kind = str(row["marker_kind"])
                observed[kind][str(row["range_name"])] += 1
                if kind == "process":
                    validate_sidecar_event(row)
                    require(row["range_name"] not in process_by_name, f"duplicate process event: {row['range_name']}")
                    process_by_name[row["range_name"]] = row
                count += 1
        files.append({"path": str(path), "sha256": sha256_path(path), "size": path.stat().st_size, "row_count": count})
    require_equal("process event multiset", observed["process"], expected_process)
    require_equal("layer event multiset", observed["layer"], expected_layer)
    require_equal("request event multiset", observed["request"], expected_request)
    require_equal("forward event multiset", observed["forward"], expected_forward)
    require_equal("process event count", len(process_by_name), EXPECTED["process_target_count"])
    return process_by_name, {
        "files": files,
        "counts": {kind: sum(counter.values()) for kind, counter in observed.items()},
        "exact_process_multiset_match": True,
        "request_forward_layer_multisets_match": True,
    }


def _schema(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    result = []
    for object_type, name, sql in connection.execute("SELECT type,name,sql FROM sqlite_master WHERE type IN ('table','view') ORDER BY type,name"):
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({_quoted(name)})")]
        result.append({"object_type": object_type, "name": name, "sql": sql, "columns": columns})
    return result


def _range_row(raw: dict[str, Any], *, kind: str, table: str, config_key: str, database_sha: str) -> dict[str, Any]:
    parsed = parse_name(str(raw["message"]))
    return {
        "range_id": hashlib.sha256(f"{table}:{raw['raw_rowid']}".encode()).hexdigest(),
        "range_kind": kind,
        "range_name": raw["message"],
        "request_id": parsed.get("request_id", ""),
        "forward_id": parsed.get("forward_id", ""),
        "layer_idx": parsed.get("layer_idx", ""),
        "layer_occurrence": parsed.get("layer_occurrence", ""),
        "layer_type": parsed.get("layer_type", ""),
        "phase": parsed.get("phase", ""),
        "q_len": parsed.get("q_len", ""),
        "kv_len": parsed.get("kv_len", ""),
        "dp_rank": parsed["dp_rank"],
        "native_device": parsed["physical_device_id"],
        "pid": int(_column(raw, "pid")),
        "tid": int(_column(raw, "tid")),
        "config_key": config_key,
        "hiptx_table": table,
        "hiptx_rowid": int(raw["raw_rowid"]),
        "hiptx_range_index": int(_column(raw, "_Index")),
        "begin_ns": int(_column(raw, "BeginNs")),
        "end_ns": int(_column(raw, "EndNs")),
        "duration_ns": int(_column(raw, "EndNs")) - int(_column(raw, "BeginNs")),
        "begin_runtime_index": int(_column(raw, "begin_Index", "BeginIndex", "begin_index")),
        "end_runtime_index": int(_column(raw, "end_Index", "EndIndex", "end_index")),
        "evidence_class": "observed_r07_timing",
        "raw_database_sha256": database_sha,
    }


def normalize(database: Path, raw_inventory: dict[str, Any]) -> dict[str, Any]:
    sidecar = json.loads(R07_BOUND_TARGET_SIDECAR_PATH.read_text(encoding="utf-8"))
    require_equal("bound sidecar status", sidecar.get("status"), "complete")
    require_equal("bound sidecar target count", sidecar.get("target_count"), EXPECTED["target_count"])
    selection = [
        row for row in sidecar["records"] if row["target_kind"] == "layer_parent"
    ]
    process_inventory = [
        row for row in sidecar["records"] if row["target_kind"] != "layer_parent"
    ]
    inventory_by_name = {row["hiptx_marker_utf8"]: row for row in process_inventory}
    require_equal("process inventory unique names", len(inventory_by_name), EXPECTED["process_target_count"])
    expected_process = Counter(sidecar["ordered_exact_name_multiset"])
    expected_layer = Counter(row["layer_marker_utf8"] for row in selection)
    expected_request = Counter(exact_request_name(row) for row in selection)
    expected_forward = Counter(exact_forward_name(row) for row in selection)
    process_events, event_audit = _load_process_events()
    database_sha = next(row["sha256"] for row in raw_inventory["raw_files"] if row["role"] == "required_primary_database")
    require_equal("database hash after seal", sha256_path(database), database_sha)
    uri = database.resolve().as_uri() + "?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    request_rows: list[dict[str, Any]] = []
    forward_rows: list[dict[str, Any]] = []
    layer_rows: list[dict[str, Any]] = []
    process_rows: list[dict[str, Any]] = []
    runtime_rows: list[dict[str, Any]] = []
    kernel_rows: list[dict[str, Any]] = []
    worker_records: list[dict[str, Any]] = []
    try:
        connection.execute("PRAGMA query_only=ON")
        schema = _schema(connection)
        schema_names = {row["name"] for row in schema}
        require({"CONFIG", "STR_TABLE"}.issubset(schema_names), "native database metadata missing")
        counter_objects = [row for row in schema if "COUNTER" in row["name"].upper()]
        counter_columns = sorted({column for row in counter_objects for column in row["columns"] if column.upper().startswith(PERF_COUNTER_PREFIXES)})
        trace_counter = classify_trace_counter_semantics({
            "trace_types": [row["name"] for row in counter_objects] or ["TRACE_COUNTER"],
            "semantic_category": "pmc" if counter_columns else "trace_metadata",
            "counter_columns": counter_columns,
        })
        require(trace_counter["is_pmc_evidence"] is False, "R07 database unexpectedly contains PMC evidence")
        observed_process: Counter[str] = Counter()
        observed_layer: Counter[str] = Counter()
        observed_request: Counter[str] = Counter()
        observed_forward: Counter[str] = Counter()
        configs = [dict(row) for row in connection.execute("SELECT * FROM CONFIG ORDER BY PID,KEY")]
        for config in configs:
            key = str(config["KEY"])
            require(re.fullmatch(r"[A-Za-z0-9_.:-]+", key) is not None, "unsafe native config key")
            tables = {"hiptx": f"HIPTX_{key}", "hiptxops": f"HIPTXOPS_{key}", "runtime": f"HIP_{key}", "device": f"HIPOPS_{key}"}
            if tables["hiptx"] not in schema_names:
                continue
            tx = [dict(row) for row in connection.execute(f"SELECT rowid AS raw_rowid,* FROM {_quoted(tables['hiptx'])}")]
            measured = [row for row in tx if str(row.get("message") or "") in expected_process or str(row.get("message") or "") in expected_layer or str(row.get("message") or "") in expected_request or str(row.get("message") or "") in expected_forward]
            if not measured:
                continue
            for table in tables.values():
                require(table in schema_names, f"native worker table missing: {table}")
            ranks = {int(parse_name(str(row["message"]))["dp_rank"]) for row in measured}
            devices = {int(parse_name(str(row["message"]))["physical_device_id"]) for row in measured}
            require_equal("worker rank cardinality", len(ranks), 1)
            require_equal("worker device cardinality", len(devices), 1)
            rank = next(iter(ranks)); device = next(iter(devices))
            require_equal("worker rank/device map", rank, device)
            worker_process: list[dict[str, Any]] = []
            layer_by_name: dict[str, dict[str, Any]] = {}
            for raw in measured:
                message = str(raw["message"])
                if message in expected_process:
                    observed_process[message] += 1
                    meta = inventory_by_name[message]
                    event = process_events[message]
                    require_equal("event/DB PID", int(event["pid"]), int(_column(raw, "pid")))
                    require_equal("event/DB TID", int(event["tid"]), int(_column(raw, "tid")))
                    for field in (
                        "canonical_target_id",
                        "canonical_target_sha256",
                        "canonical_logical_selection_id",
                        "canonical_logical_selection_sha256",
                        "canonical_bound_selection_id",
                        "canonical_bound_selection_sha256",
                        "request_id",
                        "forward_id",
                        "layer_idx",
                        "layer_occurrence",
                        "layer_type",
                        "phase",
                        "phase_occurrence",
                        "q_len",
                        "kv_len",
                        "runtime_execution_id",
                        "process_id",
                        "fragment_id",
                        "aggregation_key",
                        "target_kind",
                        "dp_rank",
                        "physical_device_id",
                    ):
                        require_equal(
                            f"event/bound-sidecar {field} {message}",
                            event[field],
                            meta[field],
                        )
                    if meta.get("range_parent") is not None:
                        require_equal(
                            f"event fragment parent {message}",
                            event["parent_name"],
                            meta["range_parent"],
                        )
                    base = _range_row(raw, kind="process", table=tables["hiptx"], config_key=key, database_sha=database_sha)
                    require(int(base["end_ns"]) > int(base["begin_ns"]), "non-positive process range")
                    uncertainty = abs(
                        (int(event["end_realtime_ns"]) - int(event["start_realtime_ns"]))
                        - (int(event["end_monotonic_ns"]) - int(event["start_monotonic_ns"]))
                    )
                    row = {
                        "process_range_id": base["range_id"],
                        "canonical_target_id": meta["canonical_target_id"],
                        "canonical_target_sha256": meta["canonical_target_sha256"],
                        "target_kind": meta["target_kind"],
                        "range_name": message,
                        "parent_range_name": "" if meta.get("range_parent") is None else meta["range_parent"],
                        "request_id": meta["request_id"], "forward_id": meta["forward_id"],
                        "layer_idx": int(meta["layer_idx"]), "layer_occurrence": int(meta["layer_occurrence"]),
                        "layer_type": meta["layer_type"], "phase": meta["phase"],
                        "q_len": int(meta["q_len"]), "kv_len": int(meta["kv_len"]),
                        "process_id": meta["process_id"], "fragment_id": meta["fragment_id"],
                        "aggregation_key": meta["aggregation_key"], "dp_rank": rank,
                        "native_device": device, "pid": base["pid"], "tid": base["tid"],
                        "config_key": key, "hiptx_table": tables["hiptx"],
                        "hiptx_rowid": base["hiptx_rowid"], "hiptx_range_index": base["hiptx_range_index"],
                        "begin_ns": base["begin_ns"], "end_ns": base["end_ns"], "duration_ns": base["duration_ns"],
                        "begin_runtime_index": base["begin_runtime_index"], "end_runtime_index": base["end_runtime_index"],
                        "depth": 0, "explicit_no_kernel_target": bool(event["explicit_no_kernel_target"]),
                        "strict_kernel_owner": bool(event["strict_kernel_owner"]),
                        "sidecar_start_monotonic_ns": int(event["start_monotonic_ns"]),
                        "sidecar_end_monotonic_ns": int(event["end_monotonic_ns"]),
                        "sidecar_start_realtime_ns": int(event["start_realtime_ns"]),
                        "sidecar_end_realtime_ns": int(event["end_realtime_ns"]),
                        "sidecar_alignment_uncertainty_ns": uncertainty,
                        "owned_runtime_call_count": 0, "owned_kernel_count": 0,
                        "ownership_state": "pending", "evidence_class": "observed_r07_timing",
                        "raw_database_sha256": database_sha, "ancestry": [],
                    }
                    worker_process.append(row)
                    process_rows.append(row)
                elif message in expected_layer:
                    observed_layer[message] += 1
                    row = _range_row(raw, kind="layer", table=tables["hiptx"], config_key=key, database_sha=database_sha)
                    layer_rows.append(row); layer_by_name[message] = row
                elif message in expected_request:
                    observed_request[message] += 1
                    request_rows.append(_range_row(raw, kind="request", table=tables["hiptx"], config_key=key, database_sha=database_sha))
                elif message in expected_forward:
                    observed_forward[message] += 1
                    forward_rows.append(_range_row(raw, kind="forward", table=tables["hiptx"], config_key=key, database_sha=database_sha))
            by_name = {row["range_name"]: row for row in worker_process}
            require_equal("worker process names unique", len(by_name), len(worker_process))
            for row in worker_process:
                ancestry = []
                parent_name = row["parent_range_name"]
                while parent_name:
                    require(parent_name not in ancestry, "process ancestry cycle")
                    parent = by_name.get(parent_name)
                    require(parent is not None, f"process parent absent: {parent_name}")
                    require(int(parent["begin_ns"]) <= int(row["begin_ns"]) and int(row["end_ns"]) <= int(parent["end_ns"]), "fragment time escapes parent")
                    require(int(parent["begin_runtime_index"]) <= int(row["begin_runtime_index"]) and int(row["end_runtime_index"]) <= int(parent["end_runtime_index"]), "fragment runtime-index escapes parent")
                    ancestry.append(parent_name)
                    parent_name = parent["parent_range_name"]
                row["ancestry"] = ancestry
                row["depth"] = len(ancestry)
                selection_key = (row["request_id"], row["forward_id"], int(row["layer_idx"]), int(row["layer_occurrence"]), int(row["dp_rank"]))
                selected = next((item for item in selection if (item["request_id"], item["forward_id"], int(item["layer_idx"]), int(item["layer_occurrence"]), int(item["dp_rank"])) == selection_key), None)
                require(selected is not None, f"process selection parent absent: {selection_key}")
                layer = layer_by_name.get(selected["layer_marker_utf8"])
                require(layer is not None, "process layer range absent")
                require(int(layer["begin_ns"]) <= int(row["begin_ns"]) and int(row["end_ns"]) <= int(layer["end_ns"]), "process time escapes layer")
                require(int(layer["begin_runtime_index"]) <= int(row["begin_runtime_index"]) and int(row["end_runtime_index"]) <= int(layer["end_runtime_index"]), "process runtime index escapes layer")
            ranges_by_tid: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for row in worker_process:
                ranges_by_tid[int(row["tid"])].append(row)
            for rows in ranges_by_tid.values():
                rows.sort(key=lambda item: (int(item["begin_ns"]), -int(item["end_ns"]), int(item["depth"])))
            lo = min(int(row["begin_ns"]) for row in worker_process)
            hi = max(int(row["end_ns"]) for row in worker_process)
            range_state = {tid: {"rows": rows, "cursor": 0, "active": []} for tid, rows in ranges_by_tid.items()}
            launches: dict[int, dict[str, Any]] = {}
            unsupported = []
            runtime_query = f"SELECT rowid AS raw_rowid,* FROM {_quoted(tables['runtime'])} WHERE BeginNs>=? AND BeginNs<? ORDER BY BeginNs,EndNs,_Index"
            for raw_runtime in connection.execute(runtime_query, (lo, hi)):
                raw = dict(raw_runtime)
                tid = int(_column(raw, "tid"))
                state = range_state.get(tid)
                if state is None:
                    continue
                begin = int(_column(raw, "BeginNs")); end = int(_column(raw, "EndNs")); index = int(_column(raw, "_Index"))
                rows = state["rows"]
                while state["cursor"] < len(rows) and int(rows[state["cursor"]]["begin_ns"]) <= begin:
                    state["active"].append(rows[state["cursor"]]); state["cursor"] += 1
                state["active"] = [item for item in state["active"] if int(item["end_ns"]) >= end]
                candidates = [item for item in state["active"] if int(item["begin_ns"]) <= begin and end <= int(item["end_ns"]) and int(item["begin_runtime_index"]) <= index <= int(item["end_runtime_index"])]
                if not candidates:
                    continue
                owner = select_deepest_owner(candidates)
                owner["owned_runtime_call_count"] += 1
                api = _api_name(_optional_column(raw, "args", default=""))
                is_launch = api in PROVEN_LAUNCH_APIS
                if "launch" in api.lower() and "kernel" in api.lower() and not is_launch:
                    unsupported.append({"api": api, "runtime_index": index, "table": tables["runtime"]})
                row = {
                    "runtime_call_id": hashlib.sha256(f"{tables['runtime']}:{raw['raw_rowid']}".encode()).hexdigest(),
                    "owner_process_range_id": owner["process_range_id"], "owner_canonical_target_id": owner["canonical_target_id"],
                    "request_id": owner["request_id"], "forward_id": owner["forward_id"],
                    "layer_idx": owner["layer_idx"], "layer_occurrence": owner["layer_occurrence"],
                    "process_id": owner["process_id"], "fragment_id": owner["fragment_id"],
                    "dp_rank": rank, "native_device": device, "pid": int(_column(raw, "pid")), "tid": tid,
                    "config_key": key, "hip_runtime_table": tables["runtime"],
                    "hip_runtime_rowid": int(raw["raw_rowid"]), "hip_runtime_index": index,
                    "hip_runtime_api": api, "hip_runtime_args": _optional_column(raw, "args", default=""),
                    "begin_ns": begin, "end_ns": end, "duration_ns": end - begin,
                    "is_kernel_launch": is_launch, "launch_correlation_state": "pending" if is_launch else "host_runtime_not_a_kernel_launch",
                    "evidence_class": "observed_r07_timing", "raw_database_sha256": database_sha,
                }
                runtime_rows.append(row)
                if is_launch:
                    require(index not in launches, f"duplicate runtime launch correlation: {index}")
                    launches[index] = {"runtime": row, "owner": owner}
            require_equal("unsupported launch-like runtime APIs", unsupported, [])
            require(launches, f"worker rank {rank} has no strict-owned launches")
            kernel_names = {int(row[0]): str(row[1]) for row in connection.execute("SELECT STR_ID,STR_NAME FROM STR_TABLE WHERE PID=? AND CONFIG_KEY=? AND TYPE=6", (int(config["PID"]), key))}
            require(kernel_names, f"kernel string table missing for rank {rank}")
            matched: dict[int, list[dict[str, Any]]] = defaultdict(list)
            minimum = min(launches); maximum = max(launches)
            device_query = f"SELECT rowid AS raw_rowid,* FROM {_quoted(tables['device'])} WHERE _Index>=? AND _Index<=? ORDER BY _Index,BeginNs,rowid"
            for raw_device in connection.execute(device_query, (minimum, maximum)):
                raw = dict(raw_device); correlation = int(_column(raw, "_Index"))
                if correlation in launches:
                    matched[correlation].append(raw)
            for correlation, launch in launches.items():
                rows = matched.get(correlation, [])
                require_equal(f"native kernel correlation {correlation}", len(rows), 1)
                raw = rows[0]; owner = launch["owner"]; runtime = launch["runtime"]
                require_equal("native kernel PID", int(_column(raw, "pid")), int(runtime["pid"]))
                require_equal("native physical device", int(_column(raw, "dev_id")), device)
                name_value = _column(raw, "Name")
                kernel_name = kernel_names.get(int(name_value), str(name_value)) if str(name_value).lstrip("-").isdigit() else str(name_value)
                begin = int(_column(raw, "BeginNs")); end = int(_column(raw, "EndNs"))
                queue = _optional_column(raw, "queue_id", "queue", default="")
                stream = _optional_column(raw, "stream_id", "stream", default=queue)
                owner["owned_kernel_count"] += 1
                runtime["launch_correlation_state"] = "complete_one_native_HIPOPS_row"
                kernel_rows.append({
                    "kernel_instance_id": hashlib.sha256(f"{tables['device']}:{raw['raw_rowid']}".encode()).hexdigest(),
                    "owner_process_range_id": owner["process_range_id"], "owner_canonical_target_id": owner["canonical_target_id"],
                    "request_id": owner["request_id"], "forward_id": owner["forward_id"], "layer_idx": owner["layer_idx"],
                    "layer_occurrence": owner["layer_occurrence"], "process_id": owner["process_id"], "fragment_id": owner["fragment_id"],
                    "dp_rank": rank, "native_device": device, "pid": runtime["pid"], "config_key": key,
                    "hip_runtime_table": runtime["hip_runtime_table"], "hip_runtime_rowid": runtime["hip_runtime_rowid"],
                    "hip_runtime_index": correlation, "hip_runtime_api": runtime["hip_runtime_api"],
                    "native_device_table": tables["device"], "native_device_rowid": int(raw["raw_rowid"]),
                    "native_device_index": int(_column(raw, "_Index")), "begin_ns": begin, "end_ns": end,
                    "duration_ns": end - begin, "queue_id": queue, "stream_id": stream,
                    "native_kernel_name": kernel_name, "ownership_depth": owner["depth"],
                    "ownership_chain": json.dumps(list(reversed(owner["ancestry"])) + [owner["range_name"]], ensure_ascii=False, separators=(",", ":")),
                    "evidence_class": "observed_r07_timing", "raw_database_sha256": database_sha,
                })
            worker_records.append({
                "pid": int(config["PID"]), "config_key": key, "dp_rank": rank,
                "native_device": device, "process_range_count": len(worker_process),
                "runtime_call_count": sum(1 for row in runtime_rows if row["config_key"] == key),
                "strict_owned_kernel_count": len(launches), "launch_correlation_complete": True,
            })
        require_equal("DB process marker multiset", observed_process, expected_process)
        require_equal("DB layer marker multiset", observed_layer, expected_layer)
        require_equal("DB request marker multiset", observed_request, expected_request)
        require_equal("DB forward marker multiset", observed_forward, expected_forward)
        require_equal("measured worker count", len(worker_records), 2)
        require_equal("rank coverage", sorted(row["dp_rank"] for row in worker_records), [0, 1])
        require_equal("native device coverage", sorted(row["native_device"] for row in worker_records), [0, 1])
    finally:
        connection.close()

    for row in process_rows:
        has_direct_kernel = int(row["owned_kernel_count"]) > 0
        row["ownership_state"] = "strict_owned" if has_direct_kernel else "explicit_no_direct_kernel"
        row["strict_kernel_owner"] = has_direct_kernel
        row["explicit_no_kernel_target"] = not has_direct_kernel
        row.pop("ancestry", None)
    require_equal("normalized process rows", len(process_rows), EXPECTED["process_target_count"])
    require(runtime_rows, "no strict-owned HIP runtime rows")
    require(kernel_rows, "no strict-owned HIPOPS kernels")
    require_equal("launch/kernel conservation", sum(row["is_kernel_launch"] is True for row in runtime_rows), len(kernel_rows))
    require_equal("process/kernel conservation", sum(int(row["owned_kernel_count"]) for row in process_rows), len(kernel_rows))
    require_equal("kernel unique native rows", len({(row["native_device_table"], row["native_device_rowid"]) for row in kernel_rows}), len(kernel_rows))

    queue_rows = [dict(row) for row in kernel_rows]
    busy_rows = []
    for device in (0, 1):
        intervals = sorted((int(row["begin_ns"]), int(row["end_ns"])) for row in kernel_rows if int(row["native_device"]) == device)
        require(intervals, f"device {device} has no kernel intervals")
        merged: list[list[int]] = []
        for begin, end in intervals:
            if not merged or begin > merged[-1][1]:
                merged.append([begin, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)
        for index, (begin, end) in enumerate(merged, 1):
            busy_rows.append({
                "busy_interval_id": f"device-{device}-busy-{index:06d}", "dp_rank": device,
                "native_device": device, "begin_ns": begin, "end_ns": end,
                "duration_ns": end - begin, "evidence_class": "derived_from_observed_r07",
                "raw_database_sha256": database_sha,
            })

    _write_csv_x(REQUEST_CSV, RANGE_FIELDS, request_rows)
    _write_csv_x(FORWARD_CSV, RANGE_FIELDS, forward_rows)
    _write_csv_x(LAYER_CSV, RANGE_FIELDS, layer_rows)
    _write_csv_x(PROCESS_CSV, PROCESS_FIELDS, process_rows)
    _write_csv_x(RUNTIME_CSV, RUNTIME_FIELDS, runtime_rows)
    _write_csv_x(KERNEL_CSV, KERNEL_FIELDS, kernel_rows)
    _write_csv_x(QUEUE_CSV, KERNEL_FIELDS, queue_rows)
    _write_csv_x(BUSY_CSV, ["busy_interval_id", "dp_rank", "native_device", "begin_ns", "end_ns", "duration_ns", "evidence_class", "raw_database_sha256"], busy_rows)

    marker_audit = {
        "schema_version": 1, "status": "complete", "runtime_run_id": RUN_ID,
        "runtime_attempt_id": ATTEMPT_ID, "lineage_id": LINEAGE_ID,
        "producer_schema_fingerprint_sha256": EXPECTED["producer_schema_fingerprint_sha256"],
        "ordered_process_marker_bytes_sha256": sidecar["ordered_exact_name_multiset_length_prefixed_sha256"],
        "expected_process_target_count": EXPECTED["process_target_count"],
        "observed_process_target_count": len(process_rows), "layer_target_count": len(layer_rows),
        "request_range_count": len(request_rows), "forward_range_count": len(forward_rows),
        "all_visible_process_bytes_exact": True, "forward_id_visible": True,
        "request_forward_layer_process_coverage_complete": True,
        "event_transport_audit": event_audit, "historical_schema_used_as_authority": False,
    }
    write_json_x(VALIDATION_ROOT / "marker_transport_audit.json", marker_audit)
    explicit_no_kernel = sum(int(row["owned_kernel_count"]) == 0 for row in process_rows)
    ownership_audit = {
        "schema_version": 1, "status": "complete", "runtime_run_id": RUN_ID,
        "runtime_attempt_id": ATTEMPT_ID, "lineage_id": LINEAGE_ID,
        "process_row_count": len(process_rows), "runtime_call_count": len(runtime_rows),
        "true_kernel_launch_count": sum(row["is_kernel_launch"] is True for row in runtime_rows),
        "strict_owned_kernel_count": len(kernel_rows), "explicit_no_direct_kernel_row_count": explicit_no_kernel,
        "ambiguous_owner_count": 0, "unmatched_true_launch_count": 0,
        "parent_fragment_double_count": 0, "runtime_conservation": True,
        "kernel_conservation": True, "busy_union_conservation": True,
        "deepest_range_ownership": True, "full_time_and_runtime_index_containment": True,
    }
    write_json_x(VALIDATION_ROOT / "strict_ownership_audit.json", ownership_audit)
    coverage = {
        "schema_version": 1, "status": "complete", "runtime_run_id": RUN_ID,
        "runtime_attempt_id": ATTEMPT_ID, "lineage_id": LINEAGE_ID,
        "request_ids": sorted({row["request_id"] for row in process_rows}),
        "measured_request_count": len({row["request_id"] for row in process_rows}),
        "dp_ranks": sorted({int(row["dp_rank"]) for row in process_rows}),
        "native_devices": sorted({int(row["native_device"]) for row in process_rows}),
        "rank_to_physical_device": {"0": 0, "1": 1},
        "layer_parent_count": len(layer_rows), "process_parent_count": sum(row["target_kind"] == "process_parent" for row in process_rows),
        "fragment_count": sum(row["target_kind"] == "fragment" for row in process_rows),
        "unique_target_count": len(layer_rows) + len(process_rows),
        "request_target_rank_device_coverage_fraction": 1.0,
        "single_device_promotion_performed": False, "coverage_target_met": True,
    }
    require_equal("measured request coverage", coverage["measured_request_count"], 8)
    require_equal("full target coverage", coverage["unique_target_count"], EXPECTED["target_count"])
    write_json_x(VALIDATION_ROOT / "rank_device_coverage.json", coverage)

    lifecycle = json.loads(LIFECYCLE_PATH.read_text(encoding="utf-8"))
    metadata = {
        "schema_version": 1, "status": "complete", "runtime_branch": "workflow01-10-fresh-e2e",
        "runtime_goal": "R07", "runtime_run_id": RUN_ID, "runtime_attempt_id": ATTEMPT_ID,
        "lineage_id": LINEAGE_ID, "trace_profile_sha256": EXPECTED["profile_sha256"],
        "workload": TRACE_PROFILE_ATTESTATION["workload"], "topology": TRACE_PROFILE_ATTESTATION["topology"],
        "coverage_gate": TRACE_PROFILE_ATTESTATION["coverage_gate"], "capture_lifecycle": lifecycle,
        "raw_inventory_path": str(RAW_INVENTORY_PATH), "raw_inventory_sha256": sha256_path(RAW_INVENTORY_PATH),
        "database_path": str(database), "database_sha256": database_sha,
        "pftrace_family": {"mode": raw_inventory["required_primary_pftrace_mode"], "members": raw_inventory["required_primary_pftrace_ordered_paths"]},
        "model_initialization_count": 1, "warmup_request_count": 2,
        "measured_workload_count": 1, "measured_request_count": 8,
        "rank_coverage": [0, 1], "native_device_coverage": [0, 1],
        "rank_to_physical_device": {"0": 0, "1": 1},
        "model_execution_performed": True, "gpu_dcu_execution_performed": True,
        "profiler_execution_performed": True, "trace_collection_performed": True,
        "live_utilization_collection_performed": True, "pmc_collection_performed": False,
        "replay_performed": False, "report_generation_performed": False,
        "evidence_class": "observed_r07_timing",
    }
    write_json_x(PROFILE_METADATA_PATH, metadata)
    outputs = {
        "request_ranges": REQUEST_CSV, "forward_ranges": FORWARD_CSV, "layer_ranges": LAYER_CSV,
        "process_ranges": PROCESS_CSV, "hip_runtime_calls": RUNTIME_CSV,
        "strict_owned_kernels": KERNEL_CSV, "queue_stream_timeline": QUEUE_CSV,
        "gpu_busy_union": BUSY_CSV,
    }
    summary = {
        "schema_version": 1, "status": "complete", "runtime_run_id": RUN_ID,
        "runtime_attempt_id": ATTEMPT_ID, "lineage_id": LINEAGE_ID,
        "trace_profile_sha256": EXPECTED["profile_sha256"], "raw_database_sha256": database_sha,
        "counts": {
            "request_ranges": len(request_rows), "forward_ranges": len(forward_rows),
            "layer_ranges": len(layer_rows), "process_ranges": len(process_rows),
            "hip_runtime_calls": len(runtime_rows), "strict_owned_kernels": len(kernel_rows),
            "explicit_no_direct_kernel_rows": explicit_no_kernel, "gpu_busy_union_intervals": len(busy_rows),
        },
        "worker_coverage": worker_records, "rank_coverage": [0, 1], "native_device_coverage": [0, 1],
        "rank_to_physical_device": {"0": 0, "1": 1}, "target_coverage_fraction": 1.0,
        "runtime_launch_correlation_fraction": 1.0, "ambiguous_owner_count": 0,
        "parent_fragment_double_count": 0, "trace_counter_semantics": trace_counter,
        "outputs": {name: {"path": str(path), "size": path.stat().st_size, "sha256": sha256_path(path)} for name, path in outputs.items()},
        "audits": {
            "marker_transport_sha256": sha256_path(VALIDATION_ROOT / "marker_transport_audit.json"),
            "strict_ownership_sha256": sha256_path(VALIDATION_ROOT / "strict_ownership_audit.json"),
            "rank_device_coverage_sha256": sha256_path(VALIDATION_ROOT / "rank_device_coverage.json"),
        },
        "evidence_class": "derived_from_observed_r07", "external_runtime_evidence_consumed": False,
    }
    write_json_x(SUMMARY_PATH, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True)
    args = parser.parse_args()
    require_equal("artifact root argv", Path(args.artifact_root).resolve(), ARTIFACT_ROOT.resolve())
    raw_inventory = inventory_raw()
    database = RAW_ROOT / "capture.db"
    summary = normalize(database, raw_inventory)
    print(json.dumps({
        "status": "complete", "process_ranges": summary["counts"]["process_ranges"],
        "strict_owned_kernels": summary["counts"]["strict_owned_kernels"],
        "rank_coverage": summary["rank_coverage"], "native_device_coverage": summary["native_device_coverage"],
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
