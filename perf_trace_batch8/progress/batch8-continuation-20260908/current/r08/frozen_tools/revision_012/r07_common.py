#!/usr/bin/env python3
"""Standard-library-only constants and integrity helpers for R07 attempt 043."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import csv
import copy
import hashlib
import json
import os
import re
import stat
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from r07_marker_contract import exact_layer_name, exact_process_name


PROJECT_ROOT = Path("/public/home/tangyu408/Qwen_DCU_Worker_0")
TARGET_ROOT = PROJECT_ROOT / "pra2026-bh408-gqa-page784-k5120-batch8"
RUNTIME_ROOT = PROJECT_ROOT / "perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003"
ARTIFACT_ROOT = RUNTIME_ROOT / "artifacts/R07/resume-042"
HANDOFF_OUTPUT = RUNTIME_ROOT / "handoffs/R07.json"
LEDGER_PATH = RUNTIME_ROOT / "runtime_handoff_ledger.json"
PROFILE_PATH = PROJECT_ROOT / "perf_trace_batch8/configs/trace_targets/batch8_dual_dcu_dp2.json"
RUNTIME_CONFIG_PATH = PROJECT_ROOT / "perf_trace_batch8/configs/workflow01_10_fresh_e2e_batch8_dual_dcu_dp2.json"
R01_ROOT = RUNTIME_ROOT / "artifacts/R01"
R02_ROOT = RUNTIME_ROOT / "artifacts/R02"
R03_ROOT = RUNTIME_ROOT / "artifacts/R03"
R04_ROOT = RUNTIME_ROOT / "artifacts/R04"
R05_ROOT = RUNTIME_ROOT / "artifacts/R05"
R06_ROOT = RUNTIME_ROOT / "artifacts/R06"
R01_REQUEST_MANIFEST_PATH = R01_ROOT / "contract/request_selection.json"
R02_SOURCE_MANIFEST_PATH = R02_ROOT / "source/source_and_ast_manifest.json"
R02_PATCH_PATH = R02_ROOT / "tools/qwen_dcu_fx_process_patch.py"
R02_ADAPTER_PATH = R02_ROOT / "tools/hiptx_adapter.py"
R03_CLIENT_PATH = R03_ROOT / "tools/profile_qwen_dcu_process_batch8.py"
R03_ANALYZER_PATH = R03_ROOT / "tools/analyze_process_hipprof.py"
R06_TARGETS_PATH = R06_ROOT / "targets/full_request_targets.json"
R06_TARGET_MANIFEST_PATH = R06_ROOT / "targets/full_request_target_manifest.json"
R07_SELECTION_PATH = ARTIFACT_ROOT / "contract/r07_full_request_selection.json"
R07_SIDECAR_PATH = ARTIFACT_ROOT / "contract/r07_full_request_hiptx_sidecar.json"
R07_BOUND_TARGET_SIDECAR_PATH = ARTIFACT_ROOT / "contract/r07_bound_target_sidecar.json"
R07_PROCESS_INVENTORY_PATH = ARTIFACT_ROOT / "contract/r07_process_range_inventory.json"
R07_RUNTIME_BINDING_ROOT = ARTIFACT_ROOT / "capture/workload/runtime_bindings"
RESOLVED_CONTRACT_PATH = ARTIFACT_ROOT / "contract/resolved_input_contract.json"
PREDECESSOR_VALIDATION_PATH = ARTIFACT_ROOT / "contract/r01_r02_r03_r04_r05_r06_predecessor_validation.json"
DATASET_PATH = Path("/home/testdata/16-32K_throughput.jsonl")
MODEL_DIR = Path("/home/Qwen3.5-27B")
MODEL_CONFIG_PATH = MODEL_DIR / "config.json"
VLLM_BIN = Path("/usr/local/bin/vllm")
HIPPROF_BIN = Path("/opt/dtk/bin/hipprof")
HY_SMI_BIN = Path("/opt/hyhal/bin/hy-smi")
RSMI_LIBRARY = Path("/opt/hyhal/lib/librocm_smi64.so.2.8")
BULK_AUTH_PATH = ARTIFACT_ROOT / "authorization/bulk_storage_authorization.json"
RETRY_AUTH_PATH = ARTIFACT_ROOT / "authorization/retry_authorization.json"
BULK_ROOT = Path(
    "/workspace/qwen_dcu_perf_trace_batch8_spill_20260901/"
    "workflow01-10-fresh-e2e/batch8-dp2-fresh-003/R07/"
    "batch8-dp2-fresh-003-R07-attempt-043"
)
BULK_PATHS = {
    "aot_cache": BULK_ROOT / "aot_cache",
    "hipprof_tmp": BULK_ROOT / "hipprof_tmp",
    "raw": BULK_ROOT / "raw",
}
BULK_ENTRYPOINTS = {
    "aot_cache": ARTIFACT_ROOT / "cache",
    "hipprof_tmp": ARTIFACT_ROOT / "capture/hipprof_tmp",
    "raw": ARTIFACT_ROOT / "capture/raw",
}
DURABLE_NFS_ROOT = PROJECT_ROOT / (
    "perf_trace_batch8/runtime_nfs_bulk/qwen_dcu_perf_trace_batch8_sealed_20260901/"
    "workflow01-10-fresh-e2e/batch8-dp2-fresh-003/R07/"
    "batch8-dp2-fresh-003-R07-attempt-043"
)
DURABLE_NFS_PATHS = {"raw": DURABLE_NFS_ROOT / "raw"}
CAPTURE_DB_CHECKPOINT_HELPER = (
    PROJECT_ROOT / "perf_trace_batch8/scripts/checkpoint_r07_capture_db_to_nfs.py"
)
CAPTURE_DB_DURABLE_MARKER = DURABLE_NFS_ROOT / "CAPTURE_DB_DURABLE.json"

BRANCH = "workflow01-10-fresh-e2e"
GOAL = "R07"
RUN_ID = "batch8-dp2-fresh-003"
ATTEMPT_ID = "batch8-dp2-fresh-003-R07-attempt-043"
LINEAGE_ID = "batch8-dp2-fresh-003"
SESSION_NAME = "r07_batch8_dp2_fresh_003_a043"
CONTROL_PROTOCOL = "r07_full_request_capture_v1"
CLEANUP_NONCE = f"{ATTEMPT_ID}:cleanup:v1"

EXPECTED = {
    "target_commit": "2b4b2119ae3cc2c4c626dc5690ef9593c1477f66",
    "profile_sha256": "3b4c952063f48ae662b48b5ce9d8fd76e0ac4d74e170bdb1839ae8b1aaa23cce",
    "runtime_config_sha256": "89d4455bd89c5f59aeea9f082353507565264ac30881faaad8f8ef966ba48ad7",
    "dataset_sha256": "633ba4c8b4f500d2ab28094de42698c5494e5232f40eafcd119c0a314b44b936",
    "r01_request_manifest_file_byte_sha256": "dc8b848a360d977d1c30adcace393459bce536aa2278ff997d6c71b9e94be280",
    "r01_request_manifest_canonical_json_sha256": "d4873c7474cbf1eff0029ab1620a67954802715c1471853a528bff9c237ae889",
    "request_manifest_hash_recovery_sha256": "4d951006247b6ca72c7ac5e45035f87ea2f0b3fe12d877e313c4895c4bab0ae4",
    "postmeasurement_storage_recovery_sha256": "5c3425da89f9ff60b3bc7ca2ddd2378e3c30f67622008e7180b1fcd95972f8fa",
    "predecessor_storage_relocation_sha256": "95f6c673ff0df6bb7e85e39485d7aca6047df8c62eac29cb33f6ded2ba1591f0",
    "worker_rebuild_recovery_sha256": "24f05655c8bbd0b0e60eab945d99041e86d851e926dbf4863cb9e3f2b606df2a",
    "runtime_patch_path_recovery_sha256": "9b555f92008c74f059287a58bf6bee206bdd827ea6db01e2eb1a7eec7631eddc",
    "bulk_input_binding_recovery_sha256": "31ce4416a43c4b06d3498c3cb60bc04f5631fc6261ee0bc06bbe34b5c70d4967",
    "runtime_patch_fixture_recovery_sha256": "9532a47c6341225d2d18ca9ea2617d00d32eca74f10b0c0794691140915c76c1",
    "attempt024_schema_nfs_recovery_sha256": "52ef76317c4ef5aaeff4854114accbac88f9e0069ef929ef329ccc75904075da",
    "attempt025_dynamic_capacity_recovery_sha256": "213958785b0307d02dde39d60715b861a294da1d5c64381272b860e9327ebcb1",
    "attempt026_abi_runtime_recovery_sha256": "339166aae19f031533da3d67617bf4bfebde7103244dffae70a26f1a56c68785",
    "attempt027_historical_identity_recovery_sha256": "74cf3707f5f51e0adb2dba717c158b6a39eb987e1d951e0264b1f05514bd43cb",
    "attempt028_bytecode_surface_recovery_sha256": "75c7b8d12315113b3c4b57e2bbd591b3231d3a3ebbaf1b22d01bf218f2c966d9",
    "attempt029_bytecode_empty_set_recovery_sha256": "393596e9f31f564b82f5321fca839cdec8184804381c0e2c26d494d0f0acadfc",
    "attempt030_sidecar_fixture_recovery_sha256": "62fc6ebdd363b6c33a530d53d926f1cbc7fd1ce63e0a476ec4f508bc3efab2eb",
    "attempt031_prior_attempt_count_recovery_sha256": "6aec8b7cb04940392a911b46d126f7b6a250eb717e2242ce4711a2a53bea3183",
    "attempt036_preformal_ordinal_binding_recovery_sha256": "40aa6e606f1199ae856c94bbd1718a59965f93581df1993b2f88b63fc291ae77",
    "attempt037_preformal_historical_validator_ordinal_recovery_sha256": "2c9eb69e93af66a12004542b233865ef0624d2d9820eb3f40cda735c0c5557bf",
    "attempt038_preformal_field_value_identity_recovery_sha256": "c96bdefe8a9445bce999af3665065c129dd585798310a2e4b698f85b78053715",
    "attempt039_predevice_bulk_helper_identity_recovery_sha256": "2cdbf25d6eb37b336affdd759772ecd46dc4898a2d25e5d37b0266cd66cd44d1",
    "attempt040_predevice_historical_successor_role_recovery_sha256": "dca9c7cab4310e3d87c6e421b3a0fb7465f1f5b837f6b0c6c5d0548935d94a73",
    "attempt041_predevice_tool_freeze_dependency_recovery_sha256": "376159a9b94b7a5621ae11c9676868bd57c1ca686e878211afa7d9135eb58979",
    "attempt042_predevice_admission_reference_key_recovery_sha256": "4f854fa0c9e7735294f710cb8875896d6b23cb6c858d2b6e6ac6ec3138d2bfde",
    "durable_nfs_storage_sha256": "ed2fc7182466945a391b7027dec351c4004ba98a2a32814e56c77f4443be5dc4",
    "capture_db_checkpoint_helper_sha256": "a0fc4fb8bc8a8ff847e81976cac16742d77521af192e9ec3630555b8a3d02d35",
    "request_sequence_sha256": "a5432b3b03bf2550577fbd21d26641e4cb8780ee7036b55ba8640a4278529b91",
    "model_config_sha256": "f8d190c5b89c1521220f935d2567a587d6e291ed69066a45a106560b05a2174c",
    "vllm_sha256": "5f96b9324e1df36d2c93e62485ca3809d09cf01a77fad1c9bb26e83fb517920c",
    "ledger_sha256": "86990e6156267c36334c31ae3ead733807d11286002d0fe00425b395d3397670",
    "r06_targets_sha256": "697d23046ff537feeef5c1cc12d4300f1e4d658bb45e76b9a4ac4a5862c3269c",
    "r06_target_manifest_sha256": "2ea72fce75f54c02ca33bb9ccc48322d6750b1c11892f533e78b7bae3e4a2d24",
    "r02_patch_sha256": "0649eae8ae3483008b37fa481046ceaa784d80487a5b1585e2f09f89fec4e2ad",
    "r02_adapter_sha256": "974318a8867e53ad99d1905331ce3a804f99e2a72d39b2163f4699fbb465a9f4",
    "full_target_ordered_marker_bytes_sha256": "f63ce9fe88c6ec53e2cf6ff6d967033ee2c2ad2114da23b429acac86e57e2c4b",
    "layer_parent_ordered_marker_bytes_sha256": "244aa7defa3a7a1f4d4229e739bd331a56f163b79d4bd51edc42d3e2d3bc87e1",
    "process_fragment_ordered_marker_bytes_sha256": "c962f8f9951b4fc994ac0a97eee45122ef2a1a34b7ec1ec4076c354b55a66f3a",
    "producer_schema_fingerprint_sha256": "81d87bd10f06cb79d6666b9b9a780a6cb60ab389f60e79e05b7bc3bf029c974a",
    "target_count": 13568,
    "layer_target_count": 1024,
    "process_target_count": 12544,
    "process_target_count_per_rank": 6272,
    "retry_authorization_sha256": "23a96899279215478f17597fa1d5375fdde439ee6324e00a7bf3dc21c43843a7",
    "monitor_advisory_sha256": "eaf5879258615716a3b7acf6356df71a02cc5faf3912636f9108f61bfc196288",
    "bulk_storage_authorization_sha256": "323f287b7f9db1bc9551cd163d27676991003ad931383e1a08a3691b92cd62d7",
    "control_plane_binding_sha256": "25190b2729176625c05fb3ab1be62815d2e5f54518af14ea595ab285bec860f0",
    "bulk_storage_required_audits_sha256": "b85792e08566befc48be95e48cd25c01e0b006d7c893eb6176fa5f27e2d988fe",
    "service_validation_path_recovery_sha256": "96e3339e713fa53fbb4c2178f696b2095302ca120e236069a6e797d964801976",
    "predevice_capacity_floor_bytes": 32 * 1024**3,
    "bulk_filesystem_device": 51,
}

TRACE_PROFILE_ATTESTATION = {
    "schema_version": 1,
    "trace_profile_id": "batch8-dual-dcu-dp2",
    "trace_profile_path": str(PROFILE_PATH),
    "trace_profile_sha256": EXPECTED["profile_sha256"],
    "workload": {
        "mode": "batch8_concurrent_requests",
        "dataset_path": str(DATASET_PATH),
        "request_count": 8,
        "max_concurrency": 8,
        "request_rate": "inf",
        "output_tokens_per_request": 1024,
        "warmup_requests": 2,
        "temperature": 0,
        "ignore_eos": True,
    },
    "topology": {
        "accelerator": "ROCm/DCU/HIP gfx936",
        "physical_devices": [0, 1],
        "hip_visible_devices": "0,1",
        "cuda_visible_devices": "0,1",
        "world_size": 2,
        "tensor_parallel_size": 1,
        "pipeline_parallel_size": 1,
        "data_parallel_size": 2,
        "data_parallel_backend": "mp",
        "rank_to_physical_device": {"0": 0, "1": 1},
    },
    "coverage_gate": {
        "required_physical_devices": [0, 1],
        "required_dp_ranks": [0, 1],
        "required_measured_request_count": 8,
        "require_per_rank_and_per_device_artifacts": True,
        "forbid_single_device_promotion": True,
    },
    "serial_stage_reduces_device_topology": False,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def require_equal(label: str, observed: Any, expected: Any) -> None:
    if observed != expected:
        raise RuntimeError(f"{label}: observed={observed!r} expected={expected!r}")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class RuntimePhaseBinder:
    """Production late binder for the first occurrence of each request/phase."""

    def __init__(
        self,
        logical_keys: Iterable[tuple[str, str]],
        *,
        expected_ranks: dict[str, int],
        selected_occurrence: int = 1,
    ) -> None:
        require(selected_occurrence == 1, "R07 selector must bind phase_occurrence=1")
        self.logical_keys = frozenset((str(request_id), str(phase)) for request_id, phase in logical_keys)
        require(len(self.logical_keys) == 16, "R07 logical request/phase denominator is not 16")
        require({phase for _, phase in self.logical_keys} == {"prefill", "decode"}, "R07 logical phase set drift")
        self.expected_ranks = {str(key): int(value) for key, value in expected_ranks.items()}
        self.selected_occurrence = selected_occurrence
        self._seen_executions: set[tuple[int, str]] = set()
        self._occurrences: dict[tuple[str, str], int] = defaultdict(int)
        self._bindings: dict[tuple[str, str, int], dict[str, Any]] = {}

    @property
    def bindings(self) -> dict[tuple[str, str, int], dict[str, Any]]:
        return {key: dict(value) for key, value in self._bindings.items()}

    @property
    def occurrence_counts(self) -> dict[tuple[str, str], int]:
        return dict(self._occurrences)

    @property
    def seen_executions(self) -> frozenset[tuple[int, str]]:
        return frozenset(self._seen_executions)

    def observe_execution(
        self,
        *,
        dp_rank: int,
        physical_device_id: int,
        runtime_execution_id: str,
        participants: Iterable[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rank = int(dp_rank)
        device = int(physical_device_id)
        require(rank in {0, 1} and device == rank, "R07 runtime rank/device drift")
        execution_key = (rank, str(runtime_execution_id))
        if execution_key in self._seen_executions:
            return []
        self._seen_executions.add(execution_key)
        participant_rows = list(participants)
        require(participant_rows, f"R07 execution has no participants: {execution_key}")
        seen_in_execution: set[tuple[str, str]] = set()
        newly_bound: list[dict[str, Any]] = []
        for participant in participant_rows:
            request_id = str(participant["request_id"])
            phase = str(participant["phase"])
            logical_key = (request_id, phase)
            if logical_key not in self.logical_keys:
                continue
            require(logical_key not in seen_in_execution, f"R07 duplicate participant in execution: {execution_key} {logical_key}")
            seen_in_execution.add(logical_key)
            require(self.expected_ranks.get(request_id) == rank, f"R07 participant rank drift: {request_id}")
            self._occurrences[logical_key] += 1
            occurrence = self._occurrences[logical_key]
            if occurrence != self.selected_occurrence:
                continue
            bound_key = (request_id, phase, occurrence)
            require(bound_key not in self._bindings, f"R07 duplicate phase binding: {bound_key}")
            bound = {
                "request_id": request_id,
                "phase": phase,
                "phase_occurrence": occurrence,
                "dp_rank": rank,
                "physical_device_id": device,
                "q_len": int(participant["q_len"]),
                "kv_len": int(participant["kv_len"]),
                "num_output_tokens_before_step": int(participant["num_output_tokens_before_step"]),
                "runtime_execution_id": str(runtime_execution_id),
            }
            self._bindings[bound_key] = bound
            newly_bound.append(dict(bound))
        return newly_bound


def serialize_bound_layer_marker(row: dict[str, Any]) -> str:
    return exact_layer_name(row)


def serialize_bound_process_marker(row: dict[str, Any]) -> str:
    return exact_process_name(row)


def _bound_identity(row: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    common = {
        "runtime_run_id": str(row["runtime_run_id"]),
        "request_id": str(row["request_id"]),
        "request_ordinal": int(row["request_ordinal"]),
        "phase": str(row["phase"]),
        "phase_occurrence": int(row["phase_occurrence"]),
        "dp_rank": int(row["dp_rank"]),
        "physical_device_id": int(row["physical_device_id"]),
        "layer_idx": int(row["layer_idx"]),
    }
    if row["target_kind"] == "layer_parent":
        common.update({
            "layer_type": str(row["layer_type"]),
            "forward_id": str(row["forward_id"]),
        })
    else:
        common.update({
            "layer_occurrence": int(row["layer_occurrence"]),
            "layer_type": str(row["layer_type"]),
            "target_kind": str(row["target_kind"]),
            "process_id": str(row["process_id"]),
            "fragment_id": str(row["fragment_id"]),
            "aggregation_key": str(row["aggregation_key"]),
        })
    common.update({
        "q_len": int(binding["q_len"]),
        "kv_len": int(binding["kv_len"]),
        "runtime_execution_id": str(binding["runtime_execution_id"]),
    })
    return common


def bind_logical_targets(
    logical_target_records: Iterable[dict[str, Any]],
    binding: dict[str, Any],
) -> list[dict[str, Any]]:
    """Bind target bytes only after the production logical predicate succeeds."""
    required_binding = {
        "request_id", "phase", "phase_occurrence", "dp_rank",
        "physical_device_id", "q_len", "kv_len",
        "num_output_tokens_before_step", "runtime_execution_id",
    }
    require(required_binding <= set(binding), "R07 runtime binding fields missing")
    require(int(binding["phase_occurrence"]) == 1, "R07 bound occurrence is not one")
    matched = []
    for source in logical_target_records:
        require(source.get("selection_key_fields") == ["request_id", "phase", "phase_occurrence"], "R07 logical selector field drift")
        require(source.get("r02_template_shape_is_selection_predicate") is False, "R07 template shape became a predicate")
        predicate = (
            str(source["request_id"]) == str(binding["request_id"])
            and str(source["phase"]) == str(binding["phase"])
            and int(source["phase_occurrence"]) == int(binding["phase_occurrence"])
        )
        if not predicate:
            continue
        require(int(source["dp_rank"]) == int(binding["dp_rank"]), "R07 selected target rank drift")
        require(int(source["physical_device_id"]) == int(binding["physical_device_id"]), "R07 selected target device drift")
        matched.append(source)
    require(len(matched) == 848, f"R07 one request/phase must bind 848 targets, got {len(matched)}")

    bound_rows: list[dict[str, Any]] = []
    parent_by_layer: dict[int, dict[str, Any]] = {}
    for source in matched:
        bound = {
            **source,
            "shape_binding_state": "bound_current_attempt_capture",
            "q_len": int(binding["q_len"]),
            "kv_len": int(binding["kv_len"]),
            "runtime_execution_id": str(binding["runtime_execution_id"]),
            "num_output_tokens_before_step": int(binding["num_output_tokens_before_step"]),
        }
        if source["target_kind"] == "layer_parent":
            bound["layer_occurrence"] = 1
            marker = serialize_bound_layer_marker(bound)
            bound["layer_marker_utf8"] = marker
            bound["layer_marker_bytes_sha256"] = hashlib.sha256(marker.encode("utf-8")).hexdigest()
        else:
            marker = serialize_bound_process_marker(bound)
            bound["process_marker_utf8"] = marker
            bound["process_marker_bytes_sha256"] = hashlib.sha256(marker.encode("utf-8")).hexdigest()
            bound["nvtx_range_name"] = marker
            layer_idx = int(bound["layer_idx"])
            if source["target_kind"] == "process_parent":
                bound["range_parent"] = None
                parent_by_layer[layer_idx] = bound
            else:
                parent = parent_by_layer.get(layer_idx)
                require(parent is not None, f"R07 fragment precedes parent at layer {layer_idx}")
                require(parent["process_id"] == bound["process_id"], f"R07 fragment parent process drift at layer {layer_idx}")
                bound["range_parent"] = parent["process_marker_utf8"]
        bound["hiptx_marker_utf8"] = marker
        bound["hiptx_marker_bytes_sha256"] = hashlib.sha256(marker.encode("utf-8")).hexdigest()
        identity_sha = canonical_sha256(_bound_identity(source, binding))
        bound["canonical_bound_selection_id"] = f"r07-bound-{identity_sha[:24]}"
        bound["canonical_bound_selection_sha256"] = identity_sha
        bound["canonical_target_id"] = bound["canonical_bound_selection_id"]
        bound["canonical_target_sha256"] = identity_sha
        bound_rows.append(bound)
    require(len({row["canonical_logical_selection_id"] for row in bound_rows}) == 848, "R07 bound logical target duplication")
    require(len({row["hiptx_marker_utf8"] for row in bound_rows}) == 848, "R07 bound marker duplication within request/phase")
    return bound_rows


def length_prefixed_sha256(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        payload = str(value).encode("utf-8")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def write_json_atomic_x(path: Path, value: Any) -> None:
    contained(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists() and not path.is_symlink(), f"R07 atomic output already exists: {path}")
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    require(not temporary.exists(), f"R07 stale atomic temporary: {temporary}")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def seal_bound_target_sidecar(
    *,
    logical_target_contract_path: Path,
    binding_root: Path = R07_RUNTIME_BINDING_ROOT,
    output_path: Path = R07_BOUND_TARGET_SIDECAR_PATH,
) -> dict[str, Any]:
    """Consolidate the two rank-owned append-only logs after worker exit."""
    logical = json.loads(logical_target_contract_path.read_text(encoding="utf-8"))
    logical_records = logical.get("records")
    require(isinstance(logical_records, list) and len(logical_records) == 13_568, "R07 logical target contract denominator drift")
    ordered_ids = [str(row["canonical_logical_selection_id"]) for row in logical_records]
    require(len(set(ordered_ids)) == 13_568, "R07 logical target IDs are not unique")
    rows_by_id: dict[str, dict[str, Any]] = {}
    log_inventory = []
    for rank in (0, 1):
        path = binding_root / f"rank{rank}.jsonl"
        require(path.is_file() and not path.is_symlink(), f"R07 rank binding log missing: {path}")
        count = 0
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                require(line.endswith("\n"), f"R07 binding log has unterminated row: {path}:{line_number}")
                row = json.loads(line)
                require(isinstance(row, dict), f"R07 binding row is not an object: {path}:{line_number}")
                require(int(row.get("dp_rank", -1)) == rank, f"R07 rank wrote another rank's binding: {path}:{line_number}")
                require(row.get("runtime_attempt_id") == ATTEMPT_ID, f"R07 binding attempt drift: {path}:{line_number}")
                logical_id = str(row["canonical_logical_selection_id"])
                require(logical_id not in rows_by_id, f"R07 duplicate bound logical target: {logical_id}")
                rows_by_id[logical_id] = row
                count += 1
        require(count == 6_784, f"R07 rank {rank} binding target count is {count}, expected 6784")
        log_inventory.append({"dp_rank": rank, "path": str(path), "size": path.stat().st_size, "sha256": sha256_path(path), "row_count": count})
    require(set(rows_by_id) == set(ordered_ids), "R07 bound target coverage differs from logical target universe")
    records = [rows_by_id[logical_id] for logical_id in ordered_ids]
    process_names = [row["hiptx_marker_utf8"] for row in records if row["target_kind"] != "layer_parent"]
    layer_names = [row["hiptx_marker_utf8"] for row in records if row["target_kind"] == "layer_parent"]
    require(len(process_names) == 12_544 and len(layer_names) == 1_024, "R07 bound target kind denominators drift")
    require(len(set(process_names)) == 12_544 and len(set(layer_names)) == 1_024, "R07 bound markers are not globally unique")
    phase_bindings: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in records:
        key = (str(row["request_id"]), str(row["phase"]), int(row["phase_occurrence"]))
        value = {
            "request_id": key[0], "phase": key[1], "phase_occurrence": key[2],
            "dp_rank": int(row["dp_rank"]), "physical_device_id": int(row["physical_device_id"]),
            "q_len": int(row["q_len"]), "kv_len": int(row["kv_len"]),
            "runtime_execution_id": str(row["runtime_execution_id"]),
            "num_output_tokens_before_step": int(row["num_output_tokens_before_step"]),
        }
        previous = phase_bindings.setdefault(key, value)
        require(previous == value, f"R07 inconsistent bound request/phase: {key}")
    require(len(phase_bindings) == 16 and all(key[2] == 1 for key in phase_bindings), "R07 bound request-phase coverage is not 16/16")
    from collections import Counter
    counts = Counter(process_names)
    entries = []
    for row in records:
        if row["target_kind"] == "layer_parent":
            continue
        entries.append({
            "exact_name": row["hiptx_marker_utf8"],
            "count": 1,
            "declared_layer_occurrences": [{
                key: row[key] for key in (
                    "request_id", "forward_id", "layer_idx", "layer_occurrence",
                    "phase", "q_len", "kv_len", "dp_rank", "physical_device_id",
                    "runtime_execution_id",
                )
            }],
            "aggregation_key": row["aggregation_key"],
            "process_id": row["process_id"],
            "fragment_id": None if row["fragment_id"] == "none" else row["fragment_id"],
            "parent_name": row.get("range_parent"),
            "source_r06_target_id": row["source_r06_target_id"],
            "source_r06_target_sha256": row["source_r06_target_sha256"],
        })
    sidecar = {
        "schema_version": 2,
        "status": "complete",
        "runtime_run_id": RUN_ID,
        "runtime_attempt_id": ATTEMPT_ID,
        "lineage_id": LINEAGE_ID,
        "trace_profile_sha256": EXPECTED["profile_sha256"],
        "producer_schema_fingerprint_sha256": EXPECTED[
            "producer_schema_fingerprint_sha256"
        ],
        "selector": {"match_fields": ["request_id", "phase", "phase_occurrence"], "selected_phase_occurrence": 1, "forbidden_match_fields": ["q_len", "kv_len", "forward_id"], "execution_dedup_fields": ["dp_rank", "runtime_execution_id"]},
        "shape_binding_policy": "bind_current_capture_participant_after_logical_match",
        "target_count": len(records),
        "layer_target_count": len(layer_names),
        "process_target_count": len(process_names),
        "bound_request_phase_count": len(phase_bindings),
        "selected_runtime_execution_count": len({(row["dp_rank"], row["runtime_execution_id"]) for row in phase_bindings.values()}),
        "request_phase_coverage_fraction": 1.0,
        "marker_coverage_fraction": 1.0,
        "rank_coverage": [0, 1],
        "physical_device_coverage": [0, 1],
        "rank_to_physical_device": {"0": 0, "1": 1},
        "ordered_exact_name_multiset": process_names,
        "ordered_exact_name_multiset_length_prefixed_sha256": length_prefixed_sha256(process_names),
        "ordered_layer_name_multiset": layer_names,
        "ordered_layer_name_multiset_length_prefixed_sha256": length_prefixed_sha256(layer_names),
        "count_per_exact_name": dict(sorted(counts.items())),
        "total_expected_event_count": len(process_names),
        "entries": entries,
        "bound_request_phases": [phase_bindings[key] for key in sorted(phase_bindings)],
        "binding_logs": log_inventory,
        "logical_target_contract_path": str(logical_target_contract_path),
        "logical_target_contract_sha256": sha256_path(logical_target_contract_path),
        "records": records,
    }
    write_json_atomic_x(output_path, sidecar)
    return {"path": str(output_path), "sha256": sha256_path(output_path), "size": output_path.stat().st_size, "target_count": len(records), "request_phase_count": len(phase_bindings), "marker_coverage_fraction": 1.0, "binding_logs": log_inventory}


def recovery_leaf_inventory(value: dict[str, Any]) -> dict[str, Any]:
    """Consume every scalar recovery field and bind its exact field path."""
    require(isinstance(value, dict), "recovery contract must be an object")
    rows: list[dict[str, Any]] = []

    def walk(node: Any, field_path: str) -> None:
        if isinstance(node, dict):
            for key in sorted(node):
                require(isinstance(key, str) and key, "recovery field name is invalid")
                walk(node[key], f"{field_path}.{key}" if field_path else key)
            return
        if isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{field_path}[{index}]")
            return
        rows.append({"field_path": field_path, "value": node})

    walk(value, "")
    field_paths = [row["field_path"] for row in rows]
    return {
        "leaf_count": len(rows),
        "field_paths_canonical_sha256": canonical_sha256(field_paths),
        "field_values_canonical_sha256": canonical_sha256(rows),
        "all_fields_consumed": True,
    }


def validate_signed_recovery_all_fields(
    recovery: dict[str, Any],
    *,
    label: str,
    expected_canonical_sha256: str,
    expected_leaf_count: int,
    expected_field_paths_sha256: str,
) -> dict[str, Any]:
    require(isinstance(recovery, dict), f"signed {label} missing")
    require_equal(
        f"{label} canonical SHA-256",
        canonical_sha256(recovery),
        expected_canonical_sha256,
    )
    inventory = recovery_leaf_inventory(recovery)
    require_equal(f"{label} leaf count", inventory["leaf_count"], expected_leaf_count)
    require_equal(
        f"{label} field-path SHA-256",
        inventory["field_paths_canonical_sha256"],
        expected_field_paths_sha256,
    )
    return inventory


def validate_request_manifest_hash_recovery(
    request_manifest_hash_recovery: dict[str, Any],
) -> dict[str, Any]:
    inventory = validate_signed_recovery_all_fields(
        request_manifest_hash_recovery,
        label="request-manifest-hash recovery",
        expected_canonical_sha256=EXPECTED["request_manifest_hash_recovery_sha256"],
        expected_leaf_count=118,
        expected_field_paths_sha256="5dd6b2bdb16566a315b0894478559f3612b2c0015a1445a1f13476e8fda788cb",
    )
    require_equal(
        "request-manifest recovery kind",
        request_manifest_hash_recovery.get("recovery_kind"),
        "postdevice_postmodel_preworkload_request_manifest_dual_hash_representation_mismatch",
    )
    contracts = request_manifest_hash_recovery.get("hash_contracts")
    require(isinstance(contracts, dict), "request-manifest hash contracts missing")
    raw_contract = contracts.get("raw_file_bytes_v1")
    canonical_contract = contracts.get("canonical_json_v1")
    require(isinstance(raw_contract, dict), "raw-file-byte hash contract missing")
    require(isinstance(canonical_contract, dict), "canonical-JSON hash contract missing")
    require_equal(
        "raw request-manifest field name",
        raw_contract.get("field_name"),
        "r01_request_manifest_file_byte_sha256",
    )
    require_equal(
        "raw request-manifest algorithm",
        raw_contract.get("algorithm"),
        "sha256_exact_regular_file_bytes",
    )
    require_equal(
        "raw request-manifest expected SHA-256",
        raw_contract.get("expected_sha256"),
        EXPECTED["r01_request_manifest_file_byte_sha256"],
    )
    require_equal(
        "canonical request-manifest field name",
        canonical_contract.get("field_name"),
        "r01_request_manifest_canonical_json_sha256",
    )
    require_equal(
        "canonical request-manifest algorithm",
        canonical_contract.get("algorithm"),
        "sha256_sort_keys_compact_utf8_ensure_ascii_false",
    )
    require_equal(
        "canonical request-manifest expected SHA-256",
        canonical_contract.get("expected_sha256"),
        EXPECTED["r01_request_manifest_canonical_json_sha256"],
    )
    invariants = contracts.get("shared_invariants")
    require(isinstance(invariants, dict), "request-manifest shared invariants missing")
    require(invariants.get("same_parsed_JSON_object") is True, "request-manifest parsed-object invariant missing")
    require(invariants.get("raw_and_canonical_digests_expected_to_equal") is False, "cross-representation equality gate forbidden")
    require(invariants.get("generic_unqualified_request_manifest_sha256_for_both_roles_allowed") is False, "ambiguous request-manifest hash field allowed")
    require(invariants.get("parse_only_after_raw_byte_hash_validation") is True, "raw-before-parse invariant missing")
    return {
        **inventory,
        "raw_file_byte_sha256": raw_contract["expected_sha256"],
        "canonical_json_sha256": canonical_contract["expected_sha256"],
        "cross_representation_digest_equality_required": False,
    }


def validate_request_manifest_bytes(
    raw_file_bytes: bytes,
    *,
    r01_request_manifest_file_byte_sha256: str,
    r01_request_manifest_canonical_json_sha256: str,
    request_manifest_hash_recovery: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate raw bytes first, then validate their parsed canonical identity."""
    recovery = validate_request_manifest_hash_recovery(request_manifest_hash_recovery)
    require_equal(
        "declared raw-file-byte SHA-256",
        r01_request_manifest_file_byte_sha256,
        recovery["raw_file_byte_sha256"],
    )
    require_equal(
        "declared canonical-JSON SHA-256",
        r01_request_manifest_canonical_json_sha256,
        recovery["canonical_json_sha256"],
    )
    observed_raw_sha256 = hashlib.sha256(raw_file_bytes).hexdigest()
    require_equal(
        "R01 request-manifest raw-file-byte SHA-256",
        observed_raw_sha256,
        r01_request_manifest_file_byte_sha256,
    )
    # Parsing is intentionally sequenced after the exact raw-byte gate above.
    manifest = json.loads(raw_file_bytes.decode("utf-8"))
    observed_canonical_sha256 = canonical_sha256(manifest)
    require_equal(
        "R01 request-manifest canonical-JSON SHA-256",
        observed_canonical_sha256,
        r01_request_manifest_canonical_json_sha256,
    )
    return manifest, {
        "r01_request_manifest_file_byte_sha256": observed_raw_sha256,
        "r01_request_manifest_canonical_json_sha256": observed_canonical_sha256,
        "raw_validation_completed_before_parse": True,
        "canonicalization": "sort_keys_compact_utf8_ensure_ascii_false",
        "cross_representation_digest_equality_compared": False,
        "request_manifest_hash_recovery_all_fields": recovery,
    }


def run_request_manifest_hash_regressions(
    request_manifest_hash_recovery: dict[str, Any],
) -> dict[str, Any]:
    raw = R01_REQUEST_MANIFEST_PATH.read_bytes()
    manifest, identity = validate_request_manifest_bytes(
        raw,
        r01_request_manifest_file_byte_sha256=EXPECTED["r01_request_manifest_file_byte_sha256"],
        r01_request_manifest_canonical_json_sha256=EXPECTED["r01_request_manifest_canonical_json_sha256"],
        request_manifest_hash_recovery=request_manifest_hash_recovery,
    )

    def rejected(label: str, call: Any) -> dict[str, Any]:
        try:
            call()
        except (RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return {"status": "rejected_as_required", "error": f"{type(exc).__name__}: {exc}"}
        raise RuntimeError(f"request-manifest negative unexpectedly passed: {label}")

    whitespace_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=False, indent=4) + "\n"
    ).encode("utf-8")
    semantic_manifest = copy.deepcopy(manifest)
    semantic_manifest["complete"] = not bool(semantic_manifest.get("complete"))
    semantic_bytes = canonical_bytes(semantic_manifest)
    whitespace_negative = rejected(
        "whitespace_or_key_order",
        lambda: validate_request_manifest_bytes(
            whitespace_bytes,
            r01_request_manifest_file_byte_sha256=EXPECTED["r01_request_manifest_file_byte_sha256"],
            r01_request_manifest_canonical_json_sha256=EXPECTED["r01_request_manifest_canonical_json_sha256"],
            request_manifest_hash_recovery=request_manifest_hash_recovery,
        ),
    )
    semantic_negative = rejected(
        "semantic_change",
        lambda: validate_request_manifest_bytes(
            semantic_bytes,
            r01_request_manifest_file_byte_sha256=hashlib.sha256(semantic_bytes).hexdigest(),
            r01_request_manifest_canonical_json_sha256=EXPECTED["r01_request_manifest_canonical_json_sha256"],
            request_manifest_hash_recovery=request_manifest_hash_recovery,
        ),
    )
    swapped_negative = rejected(
        "swapped_expected_hashes",
        lambda: validate_request_manifest_bytes(
            raw,
            r01_request_manifest_file_byte_sha256=EXPECTED["r01_request_manifest_canonical_json_sha256"],
            r01_request_manifest_canonical_json_sha256=EXPECTED["r01_request_manifest_file_byte_sha256"],
            request_manifest_hash_recovery=request_manifest_hash_recovery,
        ),
    )

    def ambiguous_single_hash_contract(**candidate: Any) -> None:
        require("request_manifest_sha256" not in candidate, "ambiguous unqualified request_manifest_sha256 rejected")
        require_equal(
            "qualified request-manifest hash fields",
            set(candidate),
            {
                "r01_request_manifest_file_byte_sha256",
                "r01_request_manifest_canonical_json_sha256",
            },
        )

    ambiguous_negative = rejected(
        "ambiguous_single_hash",
        lambda: ambiguous_single_hash_contract(
            request_manifest_sha256=EXPECTED["r01_request_manifest_canonical_json_sha256"]
        ),
    )
    return {
        "schema_version": 1,
        "status": "complete",
        "production_validator": "r07_common.validate_request_manifest_bytes",
        "production_loader": "r07_common.load_request_manifest",
        "pretty_R01_file_positive": identity,
        "whitespace_or_key_order_preserving_canonical_JSON_raw_hash_negative": whitespace_negative,
        "semantic_JSON_change_canonical_hash_negative": semantic_negative,
        "swapped_raw_and_canonical_expected_hashes_negative": swapped_negative,
        "ambiguous_single_hash_negative": ambiguous_negative,
        "all_negative_cases_rejected": True,
        "all_regressions_complete_before_device_or_model_action": True,
    }


def _lstat_object_kind(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "regular_file"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISSOCK(mode):
        return "unix_domain_socket"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISCHR(mode):
        return "character_device"
    if stat.S_ISBLK(mode):
        return "block_device"
    if stat.S_ISLNK(mode):
        return "symbolic_link"
    return "unknown_nonregular"


def bulk_object_identity(
    attempt_entrypoint_root: Path,
    storage_root: Path,
    path: Path,
    role: str,
    *,
    storage_identity_root: Path | None = None,
) -> dict[str, Any]:
    """Seal one bulk object through both lexical and storage lstat views."""
    relative = path.relative_to(attempt_entrypoint_root)
    storage_path = storage_root / relative
    identity_root = BULK_ROOT if storage_identity_root is None else storage_identity_root
    left = path.lstat()
    right = storage_path.lstat()
    left_kind = _lstat_object_kind(left.st_mode)
    right_kind = _lstat_object_kind(right.st_mode)
    require(left_kind != "symbolic_link", f"nested bulk symlink forbidden: {path}")
    require_equal("bulk dual-view object kind", left_kind, right_kind)
    require_equal("bulk dual-view filesystem device", left.st_dev, right.st_dev)
    require_equal("bulk dual-view inode", left.st_ino, right.st_ino)
    require_equal("bulk dual-view mode", left.st_mode, right.st_mode)
    require_equal("bulk dual-view size", left.st_size, right.st_size)
    common = {
        "attempt_entrypoint_path": str(path),
        "attempt_entrypoint_relative_path": relative.as_posix(),
        "storage_relative_path": storage_path.relative_to(identity_root).as_posix(),
        "storage_path": str(storage_path),
        "role": role,
        "object_kind": left_kind,
        "attempt_lstat": {
            "object_kind": left_kind,
            "filesystem_device": left.st_dev,
            "inode": left.st_ino,
            "mode": left.st_mode,
            "size": left.st_size,
            "relative_path": relative.as_posix(),
        },
        "storage_lstat": {
            "object_kind": right_kind,
            "filesystem_device": right.st_dev,
            "inode": right.st_ino,
            "mode": right.st_mode,
            "size": right.st_size,
            "relative_path": storage_path.relative_to(identity_root).as_posix(),
        },
        "attempt_and_storage_lstat_identity_equal": True,
        "deletion_performed": False,
    }
    if left_kind == "regular_file":
        attempt_hash = sha256_path(path)
        storage_hash = sha256_path(storage_path)
        require_equal("bulk dual-view regular content hash", attempt_hash, storage_hash)
        common.update(
            {
                "filesystem_device": left.st_dev,
                "inode": left.st_ino,
                "mode": left.st_mode,
                "size": left.st_size,
                "sha256": attempt_hash,
                "regular_content_sha256_present": True,
            }
        )
    else:
        common.update(
            {
                "filesystem_device": left.st_dev,
                "inode": left.st_ino,
                "mode": left.st_mode,
                "size": left.st_size,
                "sha256": None,
                "regular_content_sha256_present": False,
                "no_regular_byte_stream_reason":
                    "nonregular_object_has_no_regular_content_byte_stream",
                "preserved_without_deletion": True,
            }
        )
    return common


def contained(path: Path, *, must_exist: bool = False) -> Path:
    text = str(path)
    require(".." not in Path(text).parts, f"lexical parent escape rejected: {path}")
    lexical = Path(os.path.abspath(text))
    require(
        lexical == ARTIFACT_ROOT or ARTIFACT_ROOT in lexical.parents,
        f"lexical path escaped artifact root: {path}",
    )
    resolved = path.resolve(strict=must_exist)
    if resolved == ARTIFACT_ROOT or ARTIFACT_ROOT in resolved.parents:
        return resolved
    matched_bulk = None
    for name, entrypoint in BULK_ENTRYPOINTS.items():
        if lexical == entrypoint or entrypoint in lexical.parents:
            matched_bulk = name
            break
    require(matched_bulk is not None, f"path escaped artifact root: {path}")
    entrypoint = BULK_ENTRYPOINTS[matched_bulk]
    target = BULK_PATHS[matched_bulk]
    require(entrypoint.is_symlink(), f"authorized bulk entrypoint is not a symlink: {entrypoint}")
    require(os.readlink(entrypoint) == str(target), f"authorized bulk link text changed: {entrypoint}")
    require(entrypoint.resolve(strict=True) == target.resolve(strict=True), f"authorized bulk target changed: {entrypoint}")
    resolved_target = target.resolve(strict=True)
    require(
        resolved == resolved_target or resolved_target in resolved.parents,
        f"path escaped authorized bulk target: {path}",
    )
    require(target.stat().st_dev == EXPECTED["bulk_filesystem_device"], f"bulk filesystem device changed: {target}")
    if not must_exist:
        current = path
        while current != ARTIFACT_ROOT and not current.exists():
            current = current.parent
        require(current == entrypoint or entrypoint in current.parents or current == ARTIFACT_ROOT, f"ancestor escaped authorized root: {path}")
    return resolved


def resolve_authorized_bulk_child(
    path: Path,
    *,
    entrypoint_name: str,
    expected_relative_path: str,
    must_exist: bool,
    entrypoints: dict[str, Path] | None = None,
    bulk_paths: dict[str, Path] | None = None,
    expected_device: int | None = None,
) -> Path:
    """Validate one exact lexical child of a scheduler-authorized bulk link.

    The lexical path must remain below the attempt root, while the resolved
    path is intentionally allowed to land at the exact scheduler-pinned bulk
    target.  This is the production service-log path gate and is parameterized
    only so the same code path can exercise negative symlink fixtures before
    tool freeze.
    """
    entrypoint_map = BULK_ENTRYPOINTS if entrypoints is None else entrypoints
    bulk_path_map = BULK_PATHS if bulk_paths is None else bulk_paths
    require(entrypoint_name in entrypoint_map, f"unknown bulk entrypoint: {entrypoint_name}")
    require(entrypoint_name in bulk_path_map, f"unknown bulk target: {entrypoint_name}")
    require(".." not in path.parts, f"lexical parent escape rejected: {path}")
    lexical = Path(os.path.abspath(str(path)))
    require(
        lexical == ARTIFACT_ROOT or ARTIFACT_ROOT in lexical.parents,
        f"lexical bulk child escaped artifact root: {path}",
    )
    relative = Path(expected_relative_path)
    require(not relative.is_absolute() and ".." not in relative.parts, "invalid expected bulk child")
    entrypoint = entrypoint_map[entrypoint_name]
    target = bulk_path_map[entrypoint_name]
    require(lexical == entrypoint / relative, f"unexpected lexical bulk child: {path}")
    require(entrypoint.is_symlink(), f"authorized bulk entrypoint is not a symlink: {entrypoint}")
    require_equal(
        f"authorized bulk link text {entrypoint_name}",
        os.readlink(entrypoint),
        str(target),
    )
    require_equal(
        f"authorized bulk target {entrypoint_name}",
        entrypoint.resolve(strict=True),
        target.resolve(strict=True),
    )
    if expected_device is not None:
        require_equal(f"authorized bulk device {entrypoint_name}", target.stat().st_dev, expected_device)
    expected_resolved = (target / relative).resolve(strict=must_exist)
    observed_resolved = lexical.resolve(strict=must_exist)
    require_equal(f"authorized resolved child {entrypoint_name}", observed_resolved, expected_resolved)
    if must_exist:
        require(not lexical.is_symlink(), f"authorized bulk child cannot be a second symlink: {lexical}")
        require(lexical.is_file(), f"authorized bulk child is not a regular file: {lexical}")
    return observed_resolved


def select_authorized_bulk_child_for_exclusive_write(
    lexical_output_path: Path,
    *,
    service_validation_path_recovery: dict[str, Any],
    artifact_root: Path = ARTIFACT_ROOT,
    raw_entrypoint: Path = BULK_ENTRYPOINTS["raw"],
    authorized_raw_target: Path = BULK_PATHS["raw"],
    expected_filename: str = "service_start_validation.json",
    expected_device: int | None = EXPECTED["bulk_filesystem_device"],
    expected_resolved_child: Path | None = None,
) -> tuple[Path, Path]:
    """Select a lexical authorized-bulk child without replacing its write path.

    The returned first value is always the lexical artifact-root path.  The
    resolved value exists only for validation and must never become the writer
    argument.
    """
    require(
        isinstance(service_validation_path_recovery, dict),
        "explicit service-validation-path recovery missing",
    )
    require_equal(
        "service-validation recovery kind",
        service_validation_path_recovery.get("recovery_kind"),
        "postdevice_postmodel_preworkload_lexical_bulk_child_write_mismatch",
    )
    require_equal(
        "service-validation recovery canonical hash",
        canonical_sha256(service_validation_path_recovery),
        EXPECTED["service_validation_path_recovery_sha256"],
    )
    require(isinstance(expected_filename, str) and expected_filename, "empty output filename")
    require("/" not in expected_filename and expected_filename not in {".", ".."}, "invalid output filename")
    require(lexical_output_path.is_absolute(), "service-validation output must be absolute")
    require(".." not in lexical_output_path.parts, "lexical parent escape rejected")
    lexical = Path(os.path.abspath(str(lexical_output_path)))
    require(
        lexical == artifact_root or artifact_root in lexical.parents,
        "direct external lexical output path rejected",
    )
    require_equal(
        "service-validation exact lexical child",
        lexical,
        raw_entrypoint / expected_filename,
    )
    require_equal("service-validation lexical parent", lexical.parent, raw_entrypoint)
    require(raw_entrypoint.is_symlink(), "authorized raw entrypoint is not a symlink")
    require_equal(
        "authorized raw link text",
        os.readlink(raw_entrypoint),
        str(authorized_raw_target),
    )
    require(
        authorized_raw_target.is_dir() and not authorized_raw_target.is_symlink(),
        "authorized raw target missing, non-directory, or second-layer symlink",
    )
    require_equal(
        "authorized raw entrypoint target",
        raw_entrypoint.resolve(strict=True),
        authorized_raw_target.resolve(strict=True),
    )
    if expected_device is not None:
        require_equal(
            "authorized raw filesystem device",
            authorized_raw_target.stat().st_dev,
            expected_device,
        )
    require(not lexical.exists() and not lexical.is_symlink(), "exclusive output already exists or is symlinked")
    resolved_parent = lexical.parent.resolve(strict=True)
    require_equal(
        "service-validation resolved output parent",
        resolved_parent,
        authorized_raw_target.resolve(strict=True),
    )
    resolved_validation_path = lexical.resolve(strict=False)
    exact_storage_child = authorized_raw_target.resolve(strict=True) / expected_filename
    require_equal(
        "service-validation resolved child",
        resolved_validation_path,
        exact_storage_child,
    )
    if expected_resolved_child is not None:
        require_equal(
            "caller-declared resolved child",
            expected_resolved_child,
            exact_storage_child,
        )
    return lexical, resolved_validation_path


def write_authorized_bulk_child_json_x(
    lexical_output_path: Path,
    value: Any,
    *,
    service_validation_path_recovery: dict[str, Any],
    artifact_root: Path = ARTIFACT_ROOT,
    raw_entrypoint: Path = BULK_ENTRYPOINTS["raw"],
    authorized_raw_target: Path = BULK_PATHS["raw"],
    expected_filename: str = "service_start_validation.json",
    expected_device: int | None = EXPECTED["bulk_filesystem_device"],
    expected_resolved_child: Path | None = None,
) -> dict[str, Any]:
    """Exclusively write through the lexical path and seal both views."""
    lexical_write_path, resolved_validation_path = (
        select_authorized_bulk_child_for_exclusive_write(
            lexical_output_path,
            service_validation_path_recovery=service_validation_path_recovery,
            artifact_root=artifact_root,
            raw_entrypoint=raw_entrypoint,
            authorized_raw_target=authorized_raw_target,
            expected_filename=expected_filename,
            expected_device=expected_device,
            expected_resolved_child=expected_resolved_child,
        )
    )
    payload = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(lexical_write_path), flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    lexical_stat = lexical_write_path.stat()
    storage_stat = resolved_validation_path.stat()
    require_equal("service-validation dual-view device", lexical_stat.st_dev, storage_stat.st_dev)
    require_equal("service-validation dual-view inode", lexical_stat.st_ino, storage_stat.st_ino)
    require_equal("service-validation dual-view size", lexical_stat.st_size, storage_stat.st_size)
    lexical_hash = sha256_path(lexical_write_path)
    storage_hash = sha256_path(resolved_validation_path)
    require_equal("service-validation dual-view SHA-256", lexical_hash, storage_hash)
    return {
        "lexical_write_path": str(lexical_write_path),
        "resolved_validation_path": str(resolved_validation_path),
        "storage_path": str(authorized_raw_target / expected_filename),
        "filesystem_device": lexical_stat.st_dev,
        "inode": lexical_stat.st_ino,
        "size": lexical_stat.st_size,
        "sha256": lexical_hash,
        "lexical_and_storage_views_identical": True,
        "exclusive_create_through_lexical_path": True,
        "resolved_path_used_for_write": False,
    }


def diagnostic_nonregular_object_kind(row: dict[str, Any]) -> str:
    """Validate the diagnostic sealer schema and consume nested object kind."""
    require(isinstance(row, dict), "diagnostic bulk row is not an object")
    storage_lstat = row.get("storage_lstat")
    require(
        isinstance(storage_lstat, dict),
        "diagnostic bulk row storage_lstat missing",
    )
    object_kind = storage_lstat.get("object_kind")
    require(
        isinstance(object_kind, str) and object_kind,
        "diagnostic bulk row storage_lstat.object_kind missing",
    )
    return object_kind


def audit_aot_seed_delta(
    seed_rows: dict[str, dict[str, Any]],
    current_rows: dict[str, dict[str, Any]],
    *,
    added_provenance: str | dict[str, str],
    seed_identity: str,
) -> dict[str, Any]:
    """Prove an immutable R01 seed and current-attempt-only derived AOT delta."""
    missing = sorted(set(seed_rows) - set(current_rows))
    modified = []
    for relative in sorted(set(seed_rows) & set(current_rows)):
        seed = seed_rows[relative]
        current = current_rows[relative]
        if int(seed["size"]) != int(current["size"]) or seed["sha256"] != current["sha256"]:
            modified.append(relative)
    require_equal("AOT seed missing files", missing, [])
    require_equal("AOT seed modified files", modified, [])
    added_paths = sorted(set(current_rows) - set(seed_rows))
    provenance_map = (
        {relative: added_provenance for relative in added_paths}
        if isinstance(added_provenance, str)
        else dict(added_provenance)
    )
    require_equal("AOT added provenance paths", set(provenance_map), set(added_paths))
    allowed_provenance = "current_attempt_runtime_derivation"
    require(
        all(value == allowed_provenance for value in provenance_map.values()),
        "failed-attempt or foreign derived AOT provenance rejected",
    )
    identity_ranks: dict[str, set[int]] = {}
    pattern = re.compile(
        r"^vllm/torch_compile_cache/torch_aot_compile/([0-9a-f]{64})/rank_0_([01])/model$"
    )
    for relative in added_paths:
        match = pattern.fullmatch(relative)
        if match:
            identity_ranks.setdefault(match.group(1), set()).add(int(match.group(2)))
    for identity, ranks in identity_ranks.items():
        require_equal(f"derived AOT both-rank coverage {identity}", sorted(ranks), [0, 1])
    added = [
        {
            "relative_path": relative,
            "size": int(current_rows[relative]["size"]),
            "sha256": current_rows[relative]["sha256"],
            "provenance": provenance_map[relative],
        }
        for relative in added_paths
    ]
    return {
        "status": "complete",
        "seed_identity": seed_identity,
        "seed_file_count": len(seed_rows),
        "seed_missing_file_count": 0,
        "seed_modified_file_count": 0,
        "seed_files_byte_identical": True,
        "added_file_count": len(added),
        "added_files": added,
        "derived_identities": [
            {"identity": identity, "rank_coverage": sorted(ranks)}
            for identity, ranks in sorted(identity_ranks.items())
        ],
        "derived_identity_count": len(identity_ranks),
        "all_derived_identities_cover_both_ranks": all(ranks == {0, 1} for ranks in identity_ranks.values()),
        "direct_load_of_seed_identity_required": False,
        "failed_attempt_derived_aot_consumed": False,
    }


def write_bytes_x(path: Path, payload: bytes) -> None:
    contained(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)


def write_json_x(path: Path, value: Any) -> None:
    write_bytes_x(path, (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))


def write_bytes_reproducible(path: Path, payload: bytes) -> None:
    contained(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require_equal(f"reproduced bytes {path}", path.read_bytes(), payload)
        return
    temporary = path.with_name(f".{path.name}.tmp")
    require(not temporary.exists(), f"stale temporary: {temporary}")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def write_json_reproducible(path: Path, value: Any) -> None:
    write_bytes_reproducible(path, (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))


def csv_bytes(fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> bytes:
    import io
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=TARGET_ROOT, text=True).strip()


def process_identity(pid: int) -> dict[str, Any] | None:
    try:
        proc_root = Path("/proc") / str(pid)
        first_stat = (proc_root / "stat").read_text(encoding="utf-8")
        first_right = first_stat.rfind(")")
        first_fields = first_stat[first_right + 2 :].split()
        first_ppid = int(first_fields[1])
        first_starttime = int(first_fields[19])
        cmdline = (proc_root / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
        second_stat = (proc_root / "stat").read_text(encoding="utf-8")
        second_right = second_stat.rfind(")")
        second_fields = second_stat[second_right + 2 :].split()
        second_ppid = int(second_fields[1])
        second_starttime = int(second_fields[19])
        if (first_ppid, first_starttime) != (second_ppid, second_starttime):
            return None
        return {
            "pid": pid,
            "ppid": first_ppid,
            "proc_starttime": first_starttime,
            "starttime_ticks": first_starttime,
            "cmdline": cmdline,
            "command_line": cmdline,
        }
    except (OSError, ValueError, IndexError):
        return None


def process_identity_alive(row: dict[str, Any]) -> bool:
    current = process_identity(int(row["pid"]))
    return current is not None and int(current["starttime_ticks"]) == int(row["starttime_ticks"])


def open_device_fds(excluded_pids: set[int] | None = None) -> list[dict[str, Any]]:
    excluded = set(excluded_pids or ()) | {os.getpid()}
    rows = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name) in excluded:
            continue
        matches = []
        try:
            descriptors = list((proc / "fd").iterdir())
        except (FileNotFoundError, PermissionError, OSError):
            continue
        for descriptor in descriptors:
            try:
                target = os.readlink(descriptor)
            except (FileNotFoundError, PermissionError, OSError):
                continue
            if target == "/dev/kfd" or target.startswith("/dev/dri/card") or target.startswith("/dev/dri/renderD"):
                matches.append({"fd": descriptor.name, "target": target})
        if matches:
            rows.append({"pid": int(proc.name), "identity": process_identity(int(proc.name)), "device_fds": matches})
    return sorted(rows, key=lambda row: row["pid"])


def port_is_listening(port: int) -> bool:
    hex_port = f"{port:04X}"
    for proc_path in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        for line in proc_path.read_text(encoding="utf-8").splitlines()[1:]:
            fields = line.split()
            if fields[1].rsplit(":", 1)[-1] == hex_port and fields[3] == "0A":
                return True
    return False


def append_jsonl(path: Path, value: Any) -> None:
    contained(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()


def append_registry(path: Path, role: str, pid: int, parent_role: str) -> None:
    identity = process_identity(pid)
    require(identity is not None, f"cannot register absent PID {pid}")
    append_captured_identity(path, role, identity, parent_role)


def append_captured_identity(
    path: Path,
    role: str,
    identity: dict[str, Any],
    parent_role: str,
    *,
    observation_state: str | None = None,
) -> dict[str, Any]:
    """Append a complete immutable observation row without a PID relookup."""
    captured = dict(identity)
    for key in ("pid", "ppid", "proc_starttime", "cmdline"):
        require(key in captured, f"captured process identity missing {key}")
    require_equal("captured starttime aliases", int(captured["proc_starttime"]), int(captured["starttime_ticks"]))
    require_equal("captured cmdline aliases", captured["cmdline"], captured["command_line"])
    row = {
        "schema_version": 1,
        "runtime_attempt_id": ATTEMPT_ID,
        "role": role,
        "parent_role": parent_role,
        "registered_monotonic_ns": time.perf_counter_ns(),
        "registered_realtime_ns": time.time_ns(),
        "observation_state": observation_state or "captured_identity_appended_without_pid_relookup",
        **captured,
    }
    append_jsonl(path, row)
    return row


def load_request_manifest(
    *,
    request_manifest_hash_recovery: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    manifest, manifest_identity = validate_request_manifest_bytes(
        R01_REQUEST_MANIFEST_PATH.read_bytes(),
        r01_request_manifest_file_byte_sha256=EXPECTED[
            "r01_request_manifest_file_byte_sha256"
        ],
        r01_request_manifest_canonical_json_sha256=EXPECTED[
            "r01_request_manifest_canonical_json_sha256"
        ],
        request_manifest_hash_recovery=request_manifest_hash_recovery,
    )
    with DATASET_PATH.open("rb") as stream:
        raw_lines = [next(stream) for _ in range(8)]
    selected = []
    for record, raw in zip(manifest["records"], raw_lines):
        require_equal("selected raw line hash", hashlib.sha256(raw).hexdigest(), record["raw_line_sha256"])
        row = json.loads(raw)
        selected.append({"request_id": record["request_id"], "prompt": row["prompt"], "raw": row})
    require_equal("request order", [r["request_id"] for r in selected], [r["request_id"] for r in manifest["records"]])
    return manifest, selected, manifest_identity


def load_targets() -> dict[str, Any]:
    require_equal("R06 targets hash", sha256_path(R06_TARGETS_PATH), EXPECTED["r06_targets_sha256"])
    value = json.loads(R06_TARGETS_PATH.read_text(encoding="utf-8"))
    require_equal("R06 target count", value["row_count"], EXPECTED["target_count"])
    require_equal("R06 lineage", value["lineage_id"], LINEAGE_ID)
    return value


def tool_manifest_path() -> Path:
    return ARTIFACT_ROOT / "contract/frozen_tool_manifest.json"


def validate_frozen_tools() -> dict[str, Any]:
    path = tool_manifest_path()
    require(path.is_file(), "frozen tool manifest missing")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for row in manifest["files"]:
        file_path = ARTIFACT_ROOT / row["relative_path"]
        require_equal(f"frozen size {file_path}", file_path.stat().st_size, row["size"])
        require_equal(f"frozen hash {file_path}", sha256_path(file_path), row["sha256"])
    return manifest
