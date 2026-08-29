#!/usr/bin/env python3
"""Run the fresh Qwen/DCU R01-R10 workflow as serial Codex Goals."""

from __future__ import annotations

import argparse
import csv
import copy
import hashlib
import json
import os
import queue
import re
import secrets
import signal
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FRESH_E2E_BRANCH = "workflow01-10-fresh-e2e"
UPSTREAM_GOAL_IDS = ("R01", "R02", "R03", "R04", "R05")
UPSTREAM_SOURCE_ROOT_FIELDS = {
    "R01": ("source", "source_root"),
    "R02": ("source", "source_root"),
    "R03": ("source", "source_root"),
    "R04": ("live_toolchain", "source_root"),
    "R05": ("source", "source_root"),
}
RUNTIME_BINDINGS = {
    "R01": {"skill": "qwen-dcu-same-input-layer-wise-workflow"},
    "R02": {"skill": "qwen-dcu-fx-process-nvtx-instrumentation"},
    "R03": {"skill": "qwen-dcu-process-performance-breakdown"},
    "R04": {"skill": "qwen-dcu-process-gpu-hardware-trace"},
    "R05": {"skill": "qwen-dcu-segmented-process-attribution"},
    "R06": {"skill": "qwen-dcu-workflow05-evidence-planning"},
    "R07": {"skill": "qwen-dcu-workflow05-full-request-process-trace"},
    "R08": {"skill": "qwen-dcu-workflow05-targeted-hardware-gap-analysis"},
    "R09": {"skill": "qwen-dcu-workflow05-utilization-concurrency-analysis"},
    "R10": {"skill": "qwen-dcu-workflow05-trace-visualization-reporting"},
}
STOPPED_RUNTIME_SKILL_ALIASES: dict[str, tuple[str, ...]] = {}
BRANCHES = {
    FRESH_E2E_BRANCH: {
        "manifest": "perf_trace/manifests/workflow01_10_fresh_e2e_pipeline.json",
        "payload": {
            "schema_version": 1,
            "branch": FRESH_E2E_BRANCH,
            "goals": [f"R{value:02d}" for value in range(1, 11)],
            "bindings": RUNTIME_BINDINGS,
            "requires": [
                "one continuous fresh R01-R10 lineage; external runtime evidence is forbidden",
                "every stage may add audited trace instrumentation without source-hash equality gates",
                "all GPU work runs serially on physical DCU 1",
                "R07 captures one full-request process timeline with live SE utilization",
                "R07 and R08 generate the dependency and traffic/resource models",
                "R10 emits a self-contained offline acceptance bundle",
            ],
        },
    },
}
EXPECTED_SKILL_TREE_SHA256 = {
    "qwen-dcu-same-input-layer-wise-workflow": (
        "92477c192c4e7a09da95fd0dfe2aaf1697365f54c75a8dd94bda6c20f6600961"
    ),
    "qwen-dcu-fx-process-nvtx-instrumentation": (
        "ba17c940523721a8074394d2440cef63951c2b8fceb7c3d9d00009bcc328d1b2"
    ),
    "qwen-dcu-process-performance-breakdown": (
        "53b06aec19f8b122b0afff8102730b6cb0bb6ac464ec41e01cdd8ad484923f2b"
    ),
    "qwen-dcu-process-gpu-hardware-trace": (
        "7f7c1c0bb9d007e2480336c81933d93f0d0f6cf11f7d3764f325912bc75ae98f"
    ),
    "qwen-dcu-segmented-process-attribution": (
        "05e3289dc27ec18482fc12d379e0615115b3a19345f9a8bce9723be18bd5038c"
    ),
    "qwen-dcu-workflow05-evidence-planning": (
        "1db65a06d41ad790c030fd7c1e6bdc7642d5c5c13844f9830124f20612400e36"
    ),
    "qwen-dcu-workflow05-full-request-process-trace": (
        "acb8bee9364a72f7e12e3ae29a7102685aa5d367629b277cc1cb21ebfecdba67"
    ),
    "qwen-dcu-workflow05-targeted-hardware-gap-analysis": (
        "8b33cbfb884da47df3f6f333308b35e12979a33c82d2dd62f1b3beeb1818c87a"
    ),
    "qwen-dcu-workflow05-utilization-concurrency-analysis": (
        "20b17096e0d4cf1f349cda98365ffb2caf8551d3d525be39a9a84663df6dbba3"
    ),
    "qwen-dcu-workflow05-trace-visualization-reporting": (
        "845742956f97d565693b60b9815a682caffbd5e8e264735e9b34d37c50d28e6b"
    ),
}
EXPECTED_SKILL_FILES = ("SKILL.md", "agents/openai.yaml")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
TERMINAL_GOAL_STATUSES = {
    "blocked",
    "usageLimited",
    "budgetLimited",
    "failed",
    "interrupted",
    "cancelled",
    "complete",
}
STOP_GOAL_STATUSES = TERMINAL_GOAL_STATUSES | {"paused"}
APPROVAL_POLICY = "never"
SANDBOX_POLICY = "danger-full-access"
TURN_SANDBOX_POLICY = {"type": "dangerFullAccess"}
# app-server rejects a turn when the combined text input exceeds this limit.
# Keep a margin for protocol-side accounting and stop inlining a cumulative
# ledger well before it consumes the whole initial context.
APP_SERVER_INPUT_MAX_CHARS = 1_048_576
APP_SERVER_INPUT_SAFE_CHARS = 1_000_000
MAX_INLINE_LEDGER_CHARS = 700_000
LOW_COST_TIMELINE_POLICY_VERSION = "workflow05-low-cost-timeline-v4"
OPEN_SOURCE_TRACE_BACKEND_ORDER = (
    "perfetto_trace_processor_python_api",
    "perfetto_trace_processor_cli",
    "perfetto_ui_local_file",
    "custom_plotly_timeline_fallback",
)
OBSERVED_TRACE_SOURCE_PRIORITY = (
    "hipprof_bounded_native_pftrace",
    "hipprof_bounded_native_chrome_json_plus_exact_db_marker_overlay",
    "normalized_perfetto_chrome_overlay",
    "custom_plotly_timeline_fallback",
)
NATIVE_HIPPROF_EXPORT_FORMAT_ORDER = ("pftrace", "chrome-json")
REQUIRED_LAYER2_TRACK_GROUPS = (
    "observed_process",
    "hip_runtime",
    "gpu_queue",
    "hardware_attributes",
    "evidence",
)
TOP_LATENCY_PROCESS_COLOR_COUNT = 10
TOP_LATENCY_PROCESS_PALETTE = (
    "#4E79A7",
    "#F28E2B",
    "#E15759",
    "#76B7B2",
    "#59A14F",
    "#EDC948",
    "#B07AA1",
    "#FF9DA7",
    "#9C755F",
    "#BAB0AC",
)
REQUIRED_FEATURE_DIVERSITY_AXES = (
    "process_semantic_class",
    "phase_layer_type_shape_class",
    "template_kernel_family_mix",
    "host_to_gpu_exposure_quantile",
    "kernel_count_launch_density_quantile",
    "r4_compute_memory_occupancy_stall_signature",
    "hardware_evidence_risk_state",
)
WORKFLOW05_EVIDENCE_STATUSES = {
    "complete",
    "degraded",
    "insufficient",
    "unknown",
}
WORKFLOW05_GOALS = {"R06", "R07", "R08", "R09", "R10"}
WORKFLOW05_EXTENSION_GOALS = {"R06", "R07", "R08", "R09"}
PROCESS_RANGE_RE = re.compile(
    r"^pra\.fx_process\.input[0-9]+_layer[0-9]+\.[A-Za-z0-9_.-]+$"
)
UTILIZATION_CLASSIFICATION_THRESHOLD_DEFAULTS: dict[str, Any] = {
    "schema_version": 1,
    "observed_se_active_cu_low_pct": None,
    "observed_hcu_utilization_low_pct": None,
    "observed_cu_utilization_low_pct": None,
    "observed_wave_utilization_low_pct": None,
    "observed_memory_bandwidth_low_gbps": None,
    "replay_projected_alu_activity_low_pct": None,
    "low_kernel_concurrency_max_active_kernels": 1,
    "runtime_launch_gap_min_ns": None,
}
DEPENDENCY_COVERAGE_THRESHOLD_DEFAULT: dict[str, Any] = {
    "policy": "verified_dependency_fraction",
    "value": None,
}
OPPORTUNITY_GATE_THRESHOLD_DEFAULTS: dict[str, Any] = {
    "schema_version": 1,
    "minimum_exposed_duration_ns": None,
    "minimum_exposed_fraction": None,
    "slack_tolerance_ns": None,
    "require_all_seven_gates": True,
}
LIVE_HARDWARE_SAMPLING_DEFAULTS: dict[str, Any] = {
    "schema_version": 1,
    "mode": "disabled",
    "collector": None,
    "sample_interval_ms": None,
    "metrics": [],
    "minimum_samples_per_process": 3,
    "maximum_clock_alignment_error_ns": None,
    "require_resolution_finer_than_process_window": True,
}
LIVE_HARDWARE_SAMPLING_METRICS = {
    "hcu_utilization_pct",
    "cu_utilization_pct",
    "wave_utilization_pct",
    "memory_read_bandwidth_gbps",
    "memory_write_bandwidth_gbps",
    "se_active_cu_pct",
}
EXTENSION_MUTABLE_PARAMETER_KEYS = {
    "selection_batch_id",
    "escalation_reason",
    "authorized_additional_process_targets",
    "authorized_process_remeasurements",
    "authorized_additional_hardware_family_keys",
    "target_cumulative_latency_coverage",
    "feature_diversity_budget_fraction",
    "maximum_selected_layer_input_count",
    "maximum_selected_process_count",
    "maximum_targeted_pmc_family_count",
    "maximum_profiling_wall_time_seconds",
    "maximum_trace_export_interval_count",
    "maximum_trace_bundle_bytes",
    "minimum_expected_evidence_value",
    "utilization_classification_thresholds",
    "dependency_coverage_threshold",
    "opportunity_gate_thresholds",
    "dependency_adapter",
    "traffic_resource_model",
    "live_hardware_sampling",
}
DEFAULT_WORKFLOW05_USER_PARAMETERS: dict[str, Any] = {
    "workflow05_policy_version": LOW_COST_TIMELINE_POLICY_VERSION,
    "evidence_acquisition_mode": "fresh_no_prior_runtime_reuse",
    "analysis_strategy": "fresh_run_full_request_e2e_timeline",
    "fresh_e2e_contract": None,
    "selected_ranking_metric": "hiptx_host_range_duration_ms",
    "secondary_ranking_metrics": [
        "hipprof_launch_owned_kernel_busy_union_ms",
        "hipprof_launch_owned_kernel_sum_ms",
    ],
    "candidate_selection_policy": (
        "latency_coverage_with_feature_diversity"
    ),
    "feature_diversity_budget_fraction": 0.25,
    "feature_diversity_latency_guard_band_ratio": 0.90,
    "minimum_feature_novelty_axes": 1,
    "feature_diversity_axes": list(REQUIRED_FEATURE_DIVERSITY_AXES),
    "target_cumulative_latency_coverage": 0.80,
    "maximum_selected_layer_input_count": 32,
    "maximum_selected_process_count": 64,
    "maximum_targeted_pmc_family_count": 16,
    "maximum_profiling_wall_time_seconds": 7200,
    "selection_batch_id": "fresh-e2e-dcu1",
    "escalation_reason": "fresh_full_request_e2e_process_hardware_acceptance",
    "maximum_trace_export_interval_count": 64,
    "maximum_trace_bundle_bytes": 2 * 1024 * 1024 * 1024,
    "trace_processor_mode": "auto",
    "visualization_backend_policy": (
        "open_source_first_with_labeled_custom_fallback"
    ),
    "perfetto_interface_preference": list(OPEN_SOURCE_TRACE_BACKEND_ORDER),
    "observed_trace_source_priority": list(OBSERVED_TRACE_SOURCE_PRIORITY),
    "native_hipprof_export_format_order": list(
        NATIVE_HIPPROF_EXPORT_FORMAT_ORDER
    ),
    "native_hipprof_window_export_manifest_required": True,
    "native_chrome_exact_db_marker_overlay_required": True,
    "real_machine_test_device_policy": "physical_dcu_1_only",
    "physical_dcu_device": 1,
    "hip_visible_devices": "1",
    "cuda_visible_devices": "1",
    "perfetto_ui_delivery_interface": (
        "localhost_http_ping_pong_postmessage_arraybuffer"
    ),
    "open_source_trace_attempt_manifest_required": True,
    "perfetto_compatible_trace_required": True,
    "custom_timeline_fallback_must_be_labeled": True,
    "allow_open_source_tool_network_download": False,
    "measurement_contract_policy": "same_run_same_request",
    "base_evidence_role_on_execution_path_change": (
        "preserve_semantically_valid_stage_evidence"
    ),
    "exact_process_range_filter_required": True,
    "pmc_collection_policy": (
        "bounded_family_superset_exact_post_attribution"
    ),
    "collector_side_process_window_filter_required": False,
    "final_process_family_hardware_attribution_required": True,
    "pmc_filtered_match_policy": (
        "same_replay_pid_exact_name_subsequence_dispatch_order_then_"
        "strict_hiptx_runtime_hipops_ownership"
    ),
    "one_literal_kernel_name_filter_per_capture_batch": True,
    "minimum_pmc_filtered_name_order_match_rate": 0.99,
    "cross_capture_timeline_policy": "separate_clock_axes_no_merge",
    "selected_process_overlap_schema_version": 1,
    "high_risk_threshold": {
        "policy": "evidence_quantile",
        "value": 0.75,
    },
    "template_shape_distance_threshold": {
        "policy": "evidence_quantile",
        "value": 0.90,
    },
    "owner_ambiguity_threshold": {
        "policy": "observed_duration_fraction",
        "value": 0.05,
    },
    "hardware_evidence_gap_threshold": {
        "policy": "request_latency_fraction",
        "value": 0.01,
    },
    "minimum_expected_evidence_value": {
        "policy": "marginal_request_latency_fraction",
        "value": 0.005,
    },
    "authorized_additional_process_targets": [],
    "authorized_process_remeasurements": [],
    "authorized_additional_hardware_family_keys": [],
    "utilization_classification_thresholds": copy.deepcopy(
        UTILIZATION_CLASSIFICATION_THRESHOLD_DEFAULTS
    ),
    "dependency_coverage_threshold": copy.deepcopy(
        DEPENDENCY_COVERAGE_THRESHOLD_DEFAULT
    ),
    "opportunity_gate_thresholds": copy.deepcopy(
        OPPORTUNITY_GATE_THRESHOLD_DEFAULTS
    ),
    "dependency_adapter": None,
    "traffic_resource_model": None,
    "live_hardware_sampling": copy.deepcopy(
        LIVE_HARDWARE_SAMPLING_DEFAULTS
    ),
    "timeline_visualization": {
        "required": True,
        "layer1_output": "E2E_PROCESS_TIMELINE.html",
        "layer1_timing_semantics": (
            "observed_fresh_run_request_process_and_device_timeline"
        ),
        "layer2_track_groups": list(REQUIRED_LAYER2_TRACK_GROUPS),
        "hardware_counter_semantics": (
            "observed_se_active_cu_samples_plus_replay_projected_pmc"
        ),
        "top_latency_process_color_count": TOP_LATENCY_PROCESS_COLOR_COUNT,
        "top_latency_process_palette": list(TOP_LATENCY_PROCESS_PALETTE),
        "show_process_name_when_zoomed": True,
    },
}
ALLOWED_RANKING_METRICS = {
    "hiptx_host_range_duration_ms",
    "hipprof_launch_owned_kernel_sum_ms",
    "hipprof_launch_owned_kernel_busy_union_ms",
}
COUNT_PARAMETER_KEYS = (
    "maximum_selected_layer_input_count",
    "maximum_selected_process_count",
    "maximum_targeted_pmc_family_count",
    "maximum_profiling_wall_time_seconds",
    "maximum_trace_export_interval_count",
    "maximum_trace_bundle_bytes",
)
THRESHOLD_PARAMETER_POLICIES = {
    "high_risk_threshold": "evidence_quantile",
    "template_shape_distance_threshold": "evidence_quantile",
    "owner_ambiguity_threshold": "observed_duration_fraction",
    "hardware_evidence_gap_threshold": "request_latency_fraction",
    "minimum_expected_evidence_value": "marginal_request_latency_fraction",
}
FRESH_E2E_CONTRACT = {
    "schema_version": 1,
    "prior_runtime_evidence_policy": "forbidden_for_measurement_or_attribution",
    "process_capture_scope": "one_fresh_run_request_all_process_ranges",
    "process_target_transport": "newline_file",
    "dependency_adapter_policy": "r07_generate_same_lineage_stage_fx",
    "traffic_resource_model_policy": "r08_generate_same_lineage_pmc_and_fx",
    "live_utilization_policy": "r07_rsmi_se_snapshot_empirical_cadence",
    "clock_alignment_policy": "same_run_request_realtime_and_monotonic_anchors",
    "acceptance_policy": "r10_self_contained_offline_e2e_hardware_views",
    "source_change_policy": "stage_trace_instrumentation_allowed",
    "source_hash_equality_required": False,
    "lineage_split_on_source_change": False,
}


class SchedulerError(RuntimeError):
    """A deterministic runtime scheduling failure."""


class SchedulerSignalInterrupt(KeyboardInterrupt):
    """A catchable process signal used to checkpoint an active runtime."""

    def __init__(self, signum: int) -> None:
        try:
            signal_name = signal.Signals(signum).name
        except ValueError:
            signal_name = str(signum)
        super().__init__(f"received {signal_name}")
        self.signum = signum


class RpcError(SchedulerError):
    """An app-server JSON-RPC failure."""


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


def skill_tree_sha256(root: Path) -> tuple[str, list[str]]:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    relative_files = [path.relative_to(root).as_posix() for path in files]
    digest = hashlib.sha256()
    for path, relative in zip(files, relative_files):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest(), relative_files


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


def load_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise SchedulerError(f"required JSON file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SchedulerError(f"invalid JSON in {path}: {exc}") from exc


def _process_ancestor_pids(pid: int) -> set[int]:
    """Return pid and its Linux /proc parent chain for self-exclusion."""
    ancestors: set[int] = set()
    current = pid
    while current > 0 and current not in ancestors:
        ancestors.add(current)
        try:
            status = (Path("/proc") / str(current) / "status").read_text(
                encoding="utf-8",
                errors="replace",
            )
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            break
        match = re.search(r"^PPid:\s+([0-9]+)\s*$", status, re.MULTILINE)
        if match is None:
            break
        current = int(match.group(1))
    return ancestors


def find_live_runtime_processes(
    run_dir: Path,
    run_id: str,
    *,
    exclude_pids: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Find live scheduler/profile processes that can still mutate one run."""
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        raise SchedulerError(
            "stale-running recovery requires Linux /proc process validation"
        )
    excluded = set(exclude_pids or ())
    excluded.update(_process_ancestor_pids(os.getpid()))
    scope_markers = (str(run_dir), run_id)
    process_markers = (
        "run_perf_trace_01_05.py",
        "codex app-server",
        "codex-app-server",
        "run_qwen_hardware_profile_single_request.sh",
        "hipprof",
        "rsmi_live_utilization_collector.py",
    )
    live: list[dict[str, Any]] = []
    for candidate in proc_root.iterdir():
        if not candidate.name.isdigit():
            continue
        pid = int(candidate.name)
        if pid in excluded:
            continue
        try:
            raw = (candidate / "cmdline").read_bytes()
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        command = raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
        if not command:
            continue
        if not any(marker in command for marker in scope_markers):
            continue
        if not any(marker in command for marker in process_markers):
            continue
        live.append({"pid": pid, "command": command})
    return sorted(live, key=lambda item: item["pid"])


def recover_stale_running_state(
    *,
    project_root: Path,
    branch: str,
    manifest_path: Path,
    manifest: dict[str, Any],
    run_id: str,
    requested_goal: str | None,
) -> dict[str, Any] | None:
    """Atomically convert a proven-orphaned running state into stopped."""
    validate_run_id(run_id)
    runtime_root = require_under(
        project_root / "perf_trace" / "runtime" / branch,
        project_root,
    )
    run_dir = require_under(runtime_root / run_id, project_root)
    state_path = run_dir / "state.json"
    ledger_path = run_dir / "runtime_handoff_ledger.json"
    state = load_json(state_path)
    ledger = load_json(ledger_path)
    if not isinstance(state, dict) or not isinstance(ledger, dict):
        raise SchedulerError("stale recovery state and ledger must be JSON objects")
    expected_state = {
        "schema_version": 1,
        "branch": branch,
        "manifest": str(manifest_path.relative_to(project_root)),
        "run_id": run_id,
        "ledger": str(ledger_path.relative_to(project_root)),
    }
    for key, expected in expected_state.items():
        if state.get(key) != expected:
            raise SchedulerError(
                f"stale recovery state {key} mismatch: expected {expected!r}, "
                f"observed {state.get(key)!r}"
            )
    for key, expected in {
        "schema_version": 1,
        "branch": branch,
        "run_id": run_id,
    }.items():
        if ledger.get(key) != expected:
            raise SchedulerError(
                f"stale recovery ledger {key} mismatch: expected {expected!r}, "
                f"observed {ledger.get(key)!r}"
            )
    state_status = state.get("status")
    if state_status == "stopped":
        return None
    if state_status != "running":
        raise SchedulerError(
            "--recover-stale-running accepts only state.status=running "
            "(or is a no-op for stopped)"
        )
    goals = list(manifest["goals"])
    records = state.get("goals")
    if not isinstance(records, dict) or set(records) != set(goals):
        raise SchedulerError("stale recovery Goal set does not match the manifest")
    first_incomplete_index = next(
        (
            index
            for index, goal_id in enumerate(goals)
            if not isinstance(records.get(goal_id), dict)
            or records[goal_id].get("status") != "complete"
        ),
        len(goals),
    )
    if first_incomplete_index == len(goals):
        raise SchedulerError(
            "stale running state has no incomplete Goal; refusing recovery"
        )
    first_incomplete = goals[first_incomplete_index]
    if state.get("current_goal") != first_incomplete:
        raise SchedulerError(
            "stale recovery current_goal does not equal the first incomplete "
            f"Goal {first_incomplete}"
        )
    if requested_goal is not None and requested_goal != first_incomplete:
        raise SchedulerError(
            f"stale recovery must resume from {first_incomplete}; requested "
            f"{requested_goal}"
        )
    for goal_id in goals[first_incomplete_index + 1 :]:
        record = records.get(goal_id)
        if not isinstance(record, dict) or record.get("status") == "complete":
            raise SchedulerError(
                f"stale runtime state is non-serial after {first_incomplete}"
            )
    handoffs = ledger.get("handoffs")
    if not isinstance(handoffs, list):
        raise SchedulerError("stale recovery ledger handoffs must be a list")
    inherited_count = 0
    if len(handoffs) != inherited_count + first_incomplete_index:
        raise SchedulerError(
            "stale recovery ledger length does not match the completed prefix"
        )
    live_processes = find_live_runtime_processes(run_dir, run_id)
    if live_processes:
        summary = ", ".join(str(item["pid"]) for item in live_processes)
        raise SchedulerError(
            "stale-running recovery refused because runtime processes are "
            f"still alive: pids {summary}"
        )
    recovery_root = run_dir / "recovery"
    snapshot_dir: Path | None = None
    recovery_id: str | None = None
    for attempt in range(1, 1000):
        candidate_id = f"stale-running-{attempt:03d}"
        candidate = recovery_root / candidate_id
        try:
            candidate.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        recovery_id = candidate_id
        snapshot_dir = candidate
        break
    if snapshot_dir is None or recovery_id is None:
        raise SchedulerError("no available stale-running recovery namespace")
    prior_state_sha256 = sha256_file(state_path)
    prior_ledger_sha256 = sha256_file(ledger_path)
    state_snapshot = snapshot_dir / "state.before.json"
    ledger_snapshot = snapshot_dir / "runtime_handoff_ledger.before.json"
    shutil.copy2(state_path, state_snapshot)
    shutil.copy2(ledger_path, ledger_snapshot)
    if sha256_file(state_snapshot) != prior_state_sha256:
        raise SchedulerError("stale recovery state snapshot hash mismatch")
    if sha256_file(ledger_snapshot) != prior_ledger_sha256:
        raise SchedulerError("stale recovery ledger snapshot hash mismatch")
    recovered_at = utc_now()
    reason = (
        "recovered orphaned running state after external termination; no live "
        "scheduler or profiling process was found"
    )
    current_record = records[first_incomplete]
    current_record["status"] = "stopped"
    current_record["error"] = reason
    state["status"] = "stopped"
    state["execution_status"] = "stopped"
    state["last_error"] = reason
    history = state.setdefault("stale_recovery_history", [])
    if not isinstance(history, list):
        raise SchedulerError("stale_recovery_history must be a list when present")
    recovery_record = {
        "recovery_id": recovery_id,
        "recovered_at": recovered_at,
        "from_goal": first_incomplete,
        "prior_state_sha256": prior_state_sha256,
        "prior_ledger_sha256": prior_ledger_sha256,
        "state_snapshot": str(state_snapshot.relative_to(project_root)),
        "ledger_snapshot": str(ledger_snapshot.relative_to(project_root)),
        "live_runtime_processes": [],
        "reason": reason,
    }
    history.append(recovery_record)
    state["updated_at"] = recovered_at
    atomic_write_json(state_path, state)
    return recovery_record


def install_termination_signal_handlers() -> None:
    """Translate terminal/session termination into a checkpointable interrupt."""

    def handle(signum: int, _frame: Any) -> None:
        raise SchedulerSignalInterrupt(signum)

    for signal_name in ("SIGTERM", "SIGHUP"):
        signum = getattr(signal, signal_name, None)
        if signum is not None:
            signal.signal(signum, handle)


def require_under(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise SchedulerError(f"path escapes the project root: {resolved}") from exc
    return resolved


def project_path(value: str, project_root: Path) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return require_under(candidate, project_root)


def parse_user_parameters(
    inline_value: str,
    file_value: str | None,
) -> dict[str, Any]:
    if file_value:
        payload = load_json(Path(file_value).expanduser().resolve())
    else:
        try:
            payload = json.loads(inline_value)
        except json.JSONDecodeError as exc:
            raise SchedulerError(
                f"--user-parameters must be a JSON object: {exc}"
            ) from exc
    if not isinstance(payload, dict):
        raise SchedulerError("user parameters must be a JSON object")
    return payload


def _validate_unique_string_list(
    value: Any,
    *,
    name: str,
    pattern: re.Pattern[str] | None = None,
) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise SchedulerError(f"{name} must be a list of nonempty strings")
    if len(value) != len(set(value)):
        raise SchedulerError(f"{name} must not contain duplicates")
    if pattern is not None:
        invalid = [item for item in value if pattern.fullmatch(item) is None]
        if invalid:
            raise SchedulerError(
                f"{name} contains invalid exact process ranges: {invalid}"
            )
    return value


def _validate_optional_number(
    value: Any,
    *,
    name: str,
    minimum: float = 0.0,
    maximum: float | None = None,
    integer: bool = False,
) -> None:
    if value is None:
        return
    expected_type = int if integer else (int, float)
    if isinstance(value, bool) or not isinstance(value, expected_type):
        kind = "integer" if integer else "number"
        raise SchedulerError(f"{name} must be null or a {kind}")
    numeric = float(value)
    if numeric < minimum or (maximum is not None and numeric > maximum):
        upper = f", {maximum}" if maximum is not None else ""
        raise SchedulerError(f"{name} must be in [{minimum}{upper}]")


def _validate_hashed_reference(
    value: Any,
    *,
    name: str,
    project_root: Path,
    allow_external: bool = False,
) -> None:
    if value is None:
        return
    required = {"schema_version", "path", "sha256"}
    if not isinstance(value, dict) or set(value) != required:
        raise SchedulerError(
            f"{name} must be null or contain exactly {sorted(required)}"
        )
    if value.get("schema_version") != 1:
        raise SchedulerError(f"{name}.schema_version must equal 1")
    path_value = value.get("path")
    digest = value.get("sha256")
    if not isinstance(path_value, str) or not path_value.strip():
        raise SchedulerError(f"{name}.path must be a nonempty string")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise SchedulerError(f"{name}.sha256 must be a lowercase SHA-256")
    candidate = Path(path_value).expanduser()
    if not candidate.is_absolute():
        candidate = project_root / candidate
    path = candidate.resolve()
    if not allow_external:
        path = require_under(path, project_root)
    if not path.is_file():
        raise SchedulerError(f"{name}.path is not a file: {path}")
    if sha256_file(path) != digest:
        raise SchedulerError(f"{name}.sha256 does not match {path}")


def _validate_workflow05_gap_controls(
    resolved: dict[str, Any],
    *,
    project_root: Path,
) -> None:
    _validate_unique_string_list(
        resolved.get("authorized_additional_process_targets"),
        name="authorized_additional_process_targets",
        pattern=PROCESS_RANGE_RE,
    )
    _validate_unique_string_list(
        resolved.get("authorized_process_remeasurements"),
        name="authorized_process_remeasurements",
        pattern=PROCESS_RANGE_RE,
    )
    _validate_unique_string_list(
        resolved.get("authorized_additional_hardware_family_keys"),
        name="authorized_additional_hardware_family_keys",
    )

    utilization = resolved.get("utilization_classification_thresholds")
    if (
        not isinstance(utilization, dict)
        or set(utilization) != set(UTILIZATION_CLASSIFICATION_THRESHOLD_DEFAULTS)
        or utilization.get("schema_version") != 1
    ):
        raise SchedulerError(
            "utilization_classification_thresholds has an invalid schema"
        )
    for key in (
        "observed_se_active_cu_low_pct",
        "observed_hcu_utilization_low_pct",
        "observed_cu_utilization_low_pct",
        "observed_wave_utilization_low_pct",
        "replay_projected_alu_activity_low_pct",
    ):
        _validate_optional_number(
            utilization.get(key),
            name=f"utilization_classification_thresholds.{key}",
            maximum=100.0,
        )
    _validate_optional_number(
        utilization.get("observed_memory_bandwidth_low_gbps"),
        name=(
            "utilization_classification_thresholds."
            "observed_memory_bandwidth_low_gbps"
        ),
    )
    _validate_optional_number(
        utilization.get("low_kernel_concurrency_max_active_kernels"),
        name=(
            "utilization_classification_thresholds."
            "low_kernel_concurrency_max_active_kernels"
        ),
        minimum=1,
        integer=True,
    )
    _validate_optional_number(
        utilization.get("runtime_launch_gap_min_ns"),
        name="utilization_classification_thresholds.runtime_launch_gap_min_ns",
        integer=True,
    )

    dependency = resolved.get("dependency_coverage_threshold")
    if (
        not isinstance(dependency, dict)
        or set(dependency) != {"policy", "value"}
        or dependency.get("policy") != "verified_dependency_fraction"
    ):
        raise SchedulerError("dependency_coverage_threshold has an invalid schema")
    _validate_optional_number(
        dependency.get("value"),
        name="dependency_coverage_threshold.value",
        maximum=1.0,
    )

    opportunity = resolved.get("opportunity_gate_thresholds")
    if (
        not isinstance(opportunity, dict)
        or set(opportunity) != set(OPPORTUNITY_GATE_THRESHOLD_DEFAULTS)
        or opportunity.get("schema_version") != 1
        or opportunity.get("require_all_seven_gates") is not True
    ):
        raise SchedulerError("opportunity_gate_thresholds has an invalid schema")
    _validate_optional_number(
        opportunity.get("minimum_exposed_duration_ns"),
        name="opportunity_gate_thresholds.minimum_exposed_duration_ns",
        integer=True,
    )
    _validate_optional_number(
        opportunity.get("minimum_exposed_fraction"),
        name="opportunity_gate_thresholds.minimum_exposed_fraction",
        maximum=1.0,
    )
    _validate_optional_number(
        opportunity.get("slack_tolerance_ns"),
        name="opportunity_gate_thresholds.slack_tolerance_ns",
        integer=True,
    )

    _validate_hashed_reference(
        resolved.get("dependency_adapter"),
        name="dependency_adapter",
        project_root=project_root,
    )
    _validate_hashed_reference(
        resolved.get("traffic_resource_model"),
        name="traffic_resource_model",
        project_root=project_root,
    )

    sampling = resolved.get("live_hardware_sampling")
    if (
        not isinstance(sampling, dict)
        or set(sampling) != set(LIVE_HARDWARE_SAMPLING_DEFAULTS)
        or sampling.get("schema_version") != 1
        or sampling.get("mode")
        not in {
            "disabled",
            "hy_smi_sidecar",
            "vendor_high_resolution",
            "rsmi_se_snapshot",
        }
        or sampling.get("require_resolution_finer_than_process_window") is not True
    ):
        raise SchedulerError("live_hardware_sampling has an invalid schema")
    metrics = _validate_unique_string_list(
        sampling.get("metrics"),
        name="live_hardware_sampling.metrics",
    )
    if any(metric not in LIVE_HARDWARE_SAMPLING_METRICS for metric in metrics):
        raise SchedulerError("live_hardware_sampling.metrics contains an unknown metric")
    _validate_optional_number(
        sampling.get("sample_interval_ms"),
        name="live_hardware_sampling.sample_interval_ms",
        minimum=1e-9,
    )
    _validate_optional_number(
        sampling.get("minimum_samples_per_process"),
        name="live_hardware_sampling.minimum_samples_per_process",
        minimum=1,
        integer=True,
    )
    _validate_optional_number(
        sampling.get("maximum_clock_alignment_error_ns"),
        name="live_hardware_sampling.maximum_clock_alignment_error_ns",
        integer=True,
    )
    mode = sampling["mode"]
    if mode == "disabled":
        if sampling.get("collector") is not None or metrics:
            raise SchedulerError(
                "disabled live_hardware_sampling cannot configure a collector or metrics"
            )
    else:
        _validate_hashed_reference(
            sampling.get("collector"),
            name="live_hardware_sampling.collector",
            project_root=project_root,
            allow_external=True,
        )
        if sampling.get("sample_interval_ms") is None or not metrics:
            raise SchedulerError(
                "enabled live_hardware_sampling requires sample_interval_ms and metrics"
            )
        if sampling.get("maximum_clock_alignment_error_ns") is None:
            raise SchedulerError(
                "enabled live_hardware_sampling requires maximum_clock_alignment_error_ns"
            )


def validate_timeline_visualization_contract(timeline: Any) -> None:
    """Fail closed when the single-batch timeline presentation policy drifts."""
    valid = (
        isinstance(timeline, dict)
        and timeline.get("required") is True
        and timeline.get("layer1_output") == "E2E_PROCESS_TIMELINE.html"
        and timeline.get("layer1_timing_semantics")
        == "observed_fresh_run_request_process_and_device_timeline"
        and timeline.get("layer2_track_groups")
        == list(REQUIRED_LAYER2_TRACK_GROUPS)
        and timeline.get("hardware_counter_semantics")
        == "observed_se_active_cu_samples_plus_replay_projected_pmc"
        and timeline.get("top_latency_process_color_count")
        == TOP_LATENCY_PROCESS_COLOR_COUNT
        and timeline.get("top_latency_process_palette")
        == list(TOP_LATENCY_PROCESS_PALETTE)
        and timeline.get("show_process_name_when_zoomed") is True
    )
    if not valid:
        raise SchedulerError("timeline_visualization contract is invalid")


def resolve_user_parameters(
    project_root: Path,
    supplied: dict[str, Any],
) -> dict[str, Any]:
    """Merge the audited fresh R01-R10 configuration with explicit overrides."""
    resolved = copy.deepcopy(DEFAULT_WORKFLOW05_USER_PARAMETERS)
    fresh_config_path = (
        project_root / "perf_trace/configs/workflow01_10_fresh_e2e_dcu1.json"
    )
    fresh_defaults = load_json(fresh_config_path)
    if fresh_defaults.get("fresh_e2e_contract") != FRESH_E2E_CONTRACT:
        raise SchedulerError(
            f"fresh configuration contract mismatch: {fresh_config_path}"
        )
    resolved.update(fresh_defaults)
    resolved.update(supplied)

    trace_target = (project_root / "pra2026-bh408").resolve()
    try:
        trace_target.relative_to(project_root.resolve())
    except ValueError as exc:
        raise SchedulerError("trace target escapes the project root") from exc
    if not trace_target.is_dir():
        raise SchedulerError(f"trace target is not a directory: {trace_target}")
    supplied_target = supplied.get("trace_target_root")
    if supplied_target is not None:
        if not isinstance(supplied_target, str):
            raise SchedulerError("trace_target_root must be a string")
        if Path(supplied_target).expanduser().resolve() != trace_target:
            raise SchedulerError(
                "trace_target_root is fixed to project_root/pra2026-bh408"
            )
    resolved["trace_target_root"] = str(trace_target)

    if resolved.get("workflow05_policy_version") != LOW_COST_TIMELINE_POLICY_VERSION:
        raise SchedulerError(
            "workflow05_policy_version must be "
            f"{LOW_COST_TIMELINE_POLICY_VERSION}"
        )
    acquisition_mode = resolved.get("evidence_acquisition_mode")
    if acquisition_mode != "fresh_no_prior_runtime_reuse":
        raise SchedulerError(
            "Workflow 05 only supports fresh_no_prior_runtime_reuse"
        )
    analysis_strategy = resolved.get("analysis_strategy")
    if analysis_strategy != "fresh_run_full_request_e2e_timeline":
        raise SchedulerError(
            "Workflow 05 requires the fresh full-request E2E strategy"
        )
    if resolved.get("fresh_e2e_contract") != FRESH_E2E_CONTRACT:
        raise SchedulerError("fresh_e2e_contract must match the audited contract")
    if resolved.get("candidate_selection_policy") != (
        "latency_coverage_with_feature_diversity"
    ):
        raise SchedulerError("unsupported Workflow05 candidate_selection_policy")
    ranking_metric = resolved.get("selected_ranking_metric")
    if ranking_metric not in ALLOWED_RANKING_METRICS:
        raise SchedulerError(
            "selected_ranking_metric must be one of "
            + ", ".join(sorted(ALLOWED_RANKING_METRICS))
        )
    secondary = resolved.get("secondary_ranking_metrics")
    if (
        not isinstance(secondary, list)
        or not secondary
        or any(value not in ALLOWED_RANKING_METRICS for value in secondary)
        or len(secondary) != len(set(secondary))
    ):
        raise SchedulerError(
            "secondary_ranking_metrics must be a nonempty unique list of "
            "supported metrics"
        )
    coverage = resolved.get("target_cumulative_latency_coverage")
    if (
        isinstance(coverage, bool)
        or not isinstance(coverage, (int, float))
        or not 0 < float(coverage) <= 1
    ):
        raise SchedulerError(
            "target_cumulative_latency_coverage must be in (0, 1]"
        )
    diversity_fraction = resolved.get("feature_diversity_budget_fraction")
    if (
        isinstance(diversity_fraction, bool)
        or not isinstance(diversity_fraction, (int, float))
        or not 0 <= float(diversity_fraction) <= 0.5
    ):
        raise SchedulerError(
            "feature_diversity_budget_fraction must be in [0, 0.5]"
        )
    guard_band = resolved.get("feature_diversity_latency_guard_band_ratio")
    if (
        isinstance(guard_band, bool)
        or not isinstance(guard_band, (int, float))
        or not 0 < float(guard_band) <= 1
    ):
        raise SchedulerError(
            "feature_diversity_latency_guard_band_ratio must be in (0, 1]"
        )
    axes = resolved.get("feature_diversity_axes")
    if axes != list(REQUIRED_FEATURE_DIVERSITY_AXES):
        raise SchedulerError("feature_diversity_axes contract is invalid")
    novelty_axes = resolved.get("minimum_feature_novelty_axes")
    if (
        isinstance(novelty_axes, bool)
        or not isinstance(novelty_axes, int)
        or not 1 <= novelty_axes <= len(REQUIRED_FEATURE_DIVERSITY_AXES)
    ):
        raise SchedulerError(
            "minimum_feature_novelty_axes is outside the available axes"
        )
    for key in COUNT_PARAMETER_KEYS:
        value = resolved.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise SchedulerError(f"{key} must be a positive integer")
    if (
        resolved["maximum_targeted_pmc_family_count"]
        > resolved["maximum_selected_process_count"]
    ):
        raise SchedulerError(
            "maximum_targeted_pmc_family_count cannot exceed "
            "maximum_selected_process_count"
        )
    for key in ("selection_batch_id", "escalation_reason"):
        value = resolved.get(key)
        if not isinstance(value, str) or not value.strip():
            raise SchedulerError(f"{key} must be a nonempty string")
    if resolved.get("trace_processor_mode") not in {"auto", "native", "browser"}:
        raise SchedulerError(
            "trace_processor_mode must be auto, native, or browser"
        )
    if not isinstance(
        resolved.get("allow_open_source_tool_network_download"), bool
    ):
        raise SchedulerError(
            "allow_open_source_tool_network_download must be boolean"
        )
    fixed_contract_controls = {
        "exact_process_range_filter_required": True,
        "pmc_collection_policy": (
            "bounded_family_superset_exact_post_attribution"
        ),
        "collector_side_process_window_filter_required": False,
        "final_process_family_hardware_attribution_required": True,
        "pmc_filtered_match_policy": (
            "same_replay_pid_exact_name_subsequence_dispatch_order_then_"
            "strict_hiptx_runtime_hipops_ownership"
        ),
        "one_literal_kernel_name_filter_per_capture_batch": True,
        "minimum_pmc_filtered_name_order_match_rate": 0.99,
        "cross_capture_timeline_policy": "separate_clock_axes_no_merge",
        "selected_process_overlap_schema_version": 1,
        "visualization_backend_policy": (
            "open_source_first_with_labeled_custom_fallback"
        ),
        "perfetto_interface_preference": list(
            OPEN_SOURCE_TRACE_BACKEND_ORDER
        ),
        "observed_trace_source_priority": list(
            OBSERVED_TRACE_SOURCE_PRIORITY
        ),
        "native_hipprof_export_format_order": list(
            NATIVE_HIPPROF_EXPORT_FORMAT_ORDER
        ),
        "native_hipprof_window_export_manifest_required": True,
        "native_chrome_exact_db_marker_overlay_required": True,
        "real_machine_test_device_policy": "physical_dcu_1_only",
        "physical_dcu_device": 1,
        "hip_visible_devices": "1",
        "cuda_visible_devices": "1",
        "perfetto_ui_delivery_interface": (
            "localhost_http_ping_pong_postmessage_arraybuffer"
        ),
        "open_source_trace_attempt_manifest_required": True,
        "perfetto_compatible_trace_required": True,
        "custom_timeline_fallback_must_be_labeled": True,
    }
    for key, value in fixed_contract_controls.items():
        if resolved.get(key) != value:
            raise SchedulerError(f"{key} must equal {value!r}")
    mode_contract_controls = {
        "measurement_contract_policy": "same_run_same_request",
        "base_evidence_role_on_execution_path_change": (
            "preserve_semantically_valid_stage_evidence"
        ),
    }
    for key, value in mode_contract_controls.items():
        if resolved.get(key) != value:
            raise SchedulerError(
                f"{acquisition_mode} requires {key}={value!r}"
            )
    for key, expected_policy in THRESHOLD_PARAMETER_POLICIES.items():
        threshold = resolved.get(key)
        if not isinstance(threshold, dict) or set(threshold) != {"policy", "value"}:
            raise SchedulerError(
                f"{key} must contain exactly policy and value"
            )
        value = threshold.get("value")
        if (
            threshold.get("policy") != expected_policy
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 <= float(value) <= 1
        ):
            raise SchedulerError(
                f"{key} must use policy={expected_policy} with value in [0, 1]"
            )
    validate_timeline_visualization_contract(
        resolved.get("timeline_visualization")
    )
    _validate_workflow05_gap_controls(resolved, project_root=project_root)
    if resolved.get("dependency_adapter") is not None:
        raise SchedulerError(
            "fresh mode does not accept a prebuilt dependency adapter; "
            "R07 generates the same-lineage adapter"
        )
    if resolved.get("traffic_resource_model") is not None:
        raise SchedulerError(
            "fresh mode generates traffic_resource_model in R08"
        )
    if float(resolved["target_cumulative_latency_coverage"]) != 1.0:
        raise SchedulerError("fresh full-request mode requires target coverage 1.0")
    sampling = resolved["live_hardware_sampling"]
    if (
        sampling.get("mode") != "rsmi_se_snapshot"
        or sampling.get("metrics") != ["se_active_cu_pct"]
        or not isinstance(sampling.get("sample_interval_ms"), (int, float))
        or isinstance(sampling.get("sample_interval_ms"), bool)
        or not 0 < float(sampling["sample_interval_ms"]) < 1.0
    ):
        raise SchedulerError(
            "fresh mode requires sub-millisecond rsmi_se_snapshot "
            "se_active_cu_pct sampling"
        )
    return resolved


def canonicalize_stored_user_parameters(
    project_root: Path,
    stored: dict[str, Any],
) -> dict[str, Any]:
    """Revalidate stored fresh parameters without semantic migration."""
    canonical = resolve_user_parameters(project_root, stored)
    for key, value in stored.items():
        if canonical.get(key) != value:
            raise SchedulerError(
                f"resume user parameter {key} is not canonical"
            )
    return canonical


def validate_branch_user_parameters(
    branch: str,
    parameters: dict[str, Any],
) -> None:
    """Bind the no-reuse contract to the fresh R01-R10 branch."""
    mode = parameters.get("evidence_acquisition_mode")
    if branch != FRESH_E2E_BRANCH or mode != "fresh_no_prior_runtime_reuse":
        raise SchedulerError(
            f"{FRESH_E2E_BRANCH} requires fresh_no_prior_runtime_reuse"
        )


def resolve_extension_user_parameters(
    project_root: Path,
    stored: dict[str, Any],
    supplied: dict[str, Any],
    *,
    start_goal: str,
) -> dict[str, Any]:
    """Validate one explicitly authorized, non-destructive evidence extension."""
    if start_goal not in WORKFLOW05_EXTENSION_GOALS:
        raise SchedulerError(
            f"evidence extension must start at R06-R09, observed {start_goal}"
        )
    unknown = sorted(set(supplied) - EXTENSION_MUTABLE_PARAMETER_KEYS)
    if unknown:
        raise SchedulerError(
            "extension parameters may not change fixed controls: "
            + ", ".join(unknown)
        )
    required = {"selection_batch_id", "escalation_reason"}
    missing = sorted(required - set(supplied))
    if missing:
        raise SchedulerError(
            "extension parameters must explicitly set " + ", ".join(missing)
        )
    if supplied["selection_batch_id"] == stored.get("selection_batch_id"):
        raise SchedulerError("extension selection_batch_id must be new")
    if supplied["escalation_reason"] == stored.get("escalation_reason"):
        raise SchedulerError("extension escalation_reason must be new")

    action_keys = set(supplied) - required
    if not action_keys:
        raise SchedulerError(
            "extension parameters must authorize at least one evidence action"
        )
    process_targets = supplied.get("authorized_additional_process_targets", [])
    process_remeasurements = supplied.get(
        "authorized_process_remeasurements", []
    )
    hardware_targets = supplied.get(
        "authorized_additional_hardware_family_keys", []
    )
    if (process_targets or process_remeasurements) and int(start_goal[1:]) > 7:
        raise SchedulerError(
            "additional process targets require --extend-from R06 or R07"
        )
    if hardware_targets and int(start_goal[1:]) > 8:
        raise SchedulerError(
            "additional hardware families require --extend-from R06-R08"
        )
    live_sampling = supplied.get("live_hardware_sampling")
    if (
        isinstance(live_sampling, dict)
        and live_sampling.get("mode") != "disabled"
        and int(start_goal[1:]) > 7
    ):
        raise SchedulerError(
            "live hardware sampling requires --extend-from R06 or R07"
        )
    if (
        isinstance(live_sampling, dict)
        and live_sampling.get("mode") != "disabled"
        and not (process_targets or process_remeasurements)
    ):
        raise SchedulerError(
            "enabled live hardware sampling requires explicitly authorized "
            "process targets or remeasurements"
        )

    merged = copy.deepcopy(stored)
    merged.update(copy.deepcopy(supplied))
    canonical = resolve_user_parameters(project_root, merged)

    for key in COUNT_PARAMETER_KEYS:
        if canonical[key] < stored[key]:
            raise SchedulerError(f"extension may not decrease {key}")
    if (
        canonical["target_cumulative_latency_coverage"]
        < stored["target_cumulative_latency_coverage"]
    ):
        raise SchedulerError(
            "extension may not decrease target_cumulative_latency_coverage"
        )
    if (
        canonical["feature_diversity_budget_fraction"]
        < stored["feature_diversity_budget_fraction"]
    ):
        raise SchedulerError(
            "extension may not decrease feature_diversity_budget_fraction"
        )
    if (
        canonical["minimum_expected_evidence_value"]["value"]
        > stored["minimum_expected_evidence_value"]["value"]
    ):
        raise SchedulerError(
            "extension may not raise minimum_expected_evidence_value"
        )
    return canonical


def resolve_codex_binary(value: str | None) -> Path:
    if value is None:
        discovered = shutil.which("codex")
        if discovered is None:
            raise SchedulerError(
                "Codex executable was not found; pass --codex-bin at runtime"
            )
        candidate = Path(discovered)
    elif "/" in value:
        candidate = Path(value).expanduser()
    else:
        discovered = shutil.which(value)
        if discovered is None:
            raise SchedulerError(f"Codex executable was not found: {value}")
        candidate = Path(discovered)
    resolved = candidate.resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise SchedulerError(f"Codex executable is not runnable: {resolved}")
    return resolved


def contract_identity(payload: dict[str, Any]) -> tuple[str, str]:
    candidates = [payload.get("contract"), payload.get("same_input_parent")]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        contract_id = candidate.get("contract_id")
        canonical_sha256 = candidate.get("canonical_sha256")
        if canonical_sha256 is None:
            canonical_sha256 = candidate.get("contract_canonical_sha256")
        if isinstance(contract_id, str) and isinstance(canonical_sha256, str):
            if contract_id and re.fullmatch(r"[0-9a-f]{64}", canonical_sha256):
                return contract_id, canonical_sha256
    raise SchedulerError(
        "runtime handoff does not expose a contract_id and canonical SHA-256"
    )


def validate_upstream_ledger(
    project_root: Path,
    ledger_value: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ledger_path = project_path(ledger_value, project_root)
    payload = load_json(ledger_path)
    if not isinstance(payload, dict):
        raise SchedulerError("upstream ledger must be a JSON object")
    entries = payload.get("handoffs")
    if not isinstance(entries, list) or len(entries) != len(UPSTREAM_GOAL_IDS):
        raise SchedulerError(
            "upstream ledger must contain exactly the completed R01-R05 handoffs"
        )
    contract: tuple[str, str] | None = None
    expected_trace_target = (project_root / "pra2026-bh408").resolve()
    for index, goal_id in enumerate(UPSTREAM_GOAL_IDS):
        entry = entries[index]
        expected_skill = RUNTIME_BINDINGS[goal_id]["skill"]
        if not isinstance(entry, dict):
            raise SchedulerError(f"upstream ledger entry {goal_id} is not an object")
        if entry.get("source_goal") != goal_id:
            raise SchedulerError(
                f"upstream ledger order mismatch: expected {goal_id} at index {index}"
            )
        if entry.get("skill") != expected_skill:
            raise SchedulerError(f"upstream ledger Skill mismatch for {goal_id}")
        if entry.get("status") not in (None, "complete"):
            raise SchedulerError(f"upstream ledger entry {goal_id} is not complete")
        handoff_value = entry.get("path")
        handoff_payload = entry.get("payload")
        if not isinstance(handoff_value, str) or not isinstance(
            handoff_payload, dict
        ):
            raise SchedulerError(f"upstream ledger entry {goal_id} is incomplete")
        handoff_path = project_path(handoff_value, project_root)
        decoded = load_json(handoff_path)
        if decoded != handoff_payload:
            raise SchedulerError(
                f"upstream ledger payload differs from handoff file for {goal_id}"
            )
        if handoff_payload.get("runtime_goal") != goal_id:
            raise SchedulerError(f"runtime Goal mismatch in {goal_id} handoff")
        if handoff_payload.get("status") != "complete":
            raise SchedulerError(f"runtime handoff {goal_id} is not complete")
        if handoff_payload.get("skill") != expected_skill:
            raise SchedulerError(f"runtime handoff Skill mismatch for {goal_id}")
        source_root: Any = handoff_payload
        for field in UPSTREAM_SOURCE_ROOT_FIELDS[goal_id]:
            source_root = source_root.get(field) if isinstance(source_root, dict) else None
        if not isinstance(source_root, str):
            raise SchedulerError(
                f"runtime handoff {goal_id} does not expose its source_root"
            )
        resolved_source_root = project_path(source_root, project_root)
        if resolved_source_root != expected_trace_target:
            raise SchedulerError(
                f"runtime handoff {goal_id} source_root is not the fixed "
                "project_root/pra2026-bh408 trace target"
            )
        current_contract = contract_identity(handoff_payload)
        if contract is None:
            contract = current_contract
        elif current_contract != contract:
            raise SchedulerError(
                "R01-R05 upstream handoffs do not share one SAME_INPUT contract"
            )
        recorded_hash = entry.get("sha256") or entry.get("handoff_sha256")
        actual_hash = sha256_file(handoff_path)
        if recorded_hash is not None and recorded_hash != actual_hash:
            raise SchedulerError(f"upstream handoff hash mismatch for {goal_id}")
    assert contract is not None
    provenance = {
        "path": str(ledger_path),
        "sha256": sha256_file(ledger_path),
        "source_branch": payload.get("branch"),
        "source_run_id": payload.get("run_id"),
        "contract_id": contract[0],
        "contract_canonical_sha256": contract[1],
        "trace_target_root": str(expected_trace_target),
        "validated_goal_order": list(UPSTREAM_GOAL_IDS),
        "status": "compatible_complete_r01_r05",
    }
    return payload, provenance


def validate_runtime_inputs(
    project_root: Path,
    branch: str,
) -> tuple[Path, dict[str, Any], dict[str, str]]:
    if not project_root.is_dir():
        raise SchedulerError(f"project root is not a directory: {project_root}")
    branch_contract = BRANCHES[branch]
    manifest_path = project_path(branch_contract["manifest"], project_root)
    manifest = load_json(manifest_path)
    if manifest != branch_contract["payload"]:
        raise SchedulerError(
            f"runtime manifest does not match the {branch} contract: {manifest_path}"
        )
    observed_hashes: dict[str, str] = {}
    for goal_id in manifest["goals"]:
        skill_name = manifest["bindings"][goal_id]["skill"]
        skill_root = project_path(
            f"perf_trace/skills/{skill_name}",
            project_root,
        )
        digest, files = skill_tree_sha256(skill_root)
        if files != list(EXPECTED_SKILL_FILES):
            raise SchedulerError(
                f"runtime Skill file set mismatch: {skill_name}: {files}"
            )
        expected_digest = EXPECTED_SKILL_TREE_SHA256[skill_name]
        if digest != expected_digest:
            raise SchedulerError(
                f"committed runtime Skill tree hash mismatch: {skill_name}"
            )
        observed_hashes[skill_name] = digest
    return manifest_path, manifest, observed_hashes


def validate_run_id(value: str) -> None:
    if not RUN_ID_RE.fullmatch(value):
        raise SchedulerError(
            "run id must start with an alphanumeric character, use only "
            "letters, digits, dot, underscore, or hyphen, and contain at "
            "most 128 characters"
        )


def validate_runtime_handoff_entry(
    project_root: Path,
    entry: Any,
    *,
    goal_id: str,
    expected_skill: str,
    expected_path: Path | None = None,
    require_recorded_hash: bool = True,
) -> Path:
    """Revalidate one immutable cumulative-ledger entry for resume."""
    if not isinstance(entry, dict):
        raise SchedulerError(f"resume ledger entry {goal_id} is not an object")
    if entry.get("source_goal") != goal_id:
        raise SchedulerError(f"resume ledger Goal mismatch for {goal_id}")
    if entry.get("status") not in (None, "complete"):
        raise SchedulerError(f"resume ledger entry {goal_id} is not complete")
    if not runtime_skill_name_matches(entry.get("skill"), expected_skill):
        raise SchedulerError(f"resume ledger Skill mismatch for {goal_id}")
    path_value = entry.get("path")
    payload = entry.get("payload")
    if not isinstance(path_value, str) or not isinstance(payload, dict):
        raise SchedulerError(f"resume ledger entry {goal_id} is incomplete")
    path = project_path(path_value, project_root)
    if expected_path is not None and path != expected_path.resolve():
        raise SchedulerError(
            f"resume handoff path mismatch for {goal_id}: {path}"
        )
    decoded = load_json(path)
    if decoded != payload:
        raise SchedulerError(
            f"resume ledger payload differs from handoff file for {goal_id}"
        )
    if decoded.get("runtime_goal") != goal_id:
        raise SchedulerError(f"resume handoff Goal mismatch for {goal_id}")
    if decoded.get("status") != "complete":
        raise SchedulerError(f"resume handoff {goal_id} is not complete")
    if not runtime_skill_name_matches(decoded.get("skill"), expected_skill):
        raise SchedulerError(f"resume handoff Skill mismatch for {goal_id}")
    recorded_hash = entry.get("sha256") or entry.get("handoff_sha256")
    if require_recorded_hash and not isinstance(recorded_hash, str):
        raise SchedulerError(f"resume ledger hash is missing for {goal_id}")
    if isinstance(recorded_hash, str) and sha256_file(path) != recorded_hash:
        raise SchedulerError(f"resume handoff hash mismatch for {goal_id}")
    return path


def runtime_skill_name_matches(value: Any, expected: str) -> bool:
    if value == expected:
        return True
    if not isinstance(value, str):
        return False
    return expected in STOPPED_RUNTIME_SKILL_ALIASES.get(value, ())


def expected_resume_skill(
    goal_id: str,
    *,
    manifest: dict[str, Any],
    completed_manifest_goals: list[str],
) -> str:
    if goal_id in completed_manifest_goals:
        return str(manifest["bindings"][goal_id]["skill"])
    if goal_id in UPSTREAM_GOAL_IDS:
        return str(RUNTIME_BINDINGS[goal_id]["skill"])
    raise SchedulerError(f"resume ledger contains an undeclared Goal: {goal_id}")


def load_resume_context(
    *,
    project_root: Path,
    branch: str,
    manifest_path: Path,
    manifest: dict[str, Any],
    run_id: str,
    requested_goal: str | None,
    replay: bool = False,
    extend: bool = False,
    continue_current_goal: bool = False,
    extension_parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail-closed validation for resume, replay, or evidence extension."""
    if replay and extend:
        raise SchedulerError("replay and evidence extension are mutually exclusive")
    if continue_current_goal and (replay or extend):
        raise SchedulerError(
            "current-Goal continuation is valid only for a normal resume"
        )
    if continue_current_goal and requested_goal is None:
        raise SchedulerError(
            "current-Goal continuation requires an explicit --resume-from Goal"
        )
    validate_run_id(run_id)
    runtime_root = require_under(
        project_root / "perf_trace" / "runtime" / branch,
        project_root,
    )
    run_dir = require_under(runtime_root / run_id, project_root)
    if not run_dir.is_dir():
        raise SchedulerError(f"resume runtime directory is missing: {run_dir}")
    state_path = run_dir / "state.json"
    ledger_path = run_dir / "runtime_handoff_ledger.json"
    state = load_json(state_path)
    ledger = load_json(ledger_path)
    if not isinstance(state, dict) or not isinstance(ledger, dict):
        raise SchedulerError("resume state and ledger must be JSON objects")
    expected_manifest = str(manifest_path.relative_to(project_root))
    expected_ledger = str(ledger_path.relative_to(project_root))
    state_contract = {
        "schema_version": 1,
        "branch": branch,
        "manifest": expected_manifest,
        "run_id": run_id,
        "ledger": expected_ledger,
    }
    for key, expected in state_contract.items():
        if state.get(key) != expected:
            raise SchedulerError(
                f"resume state {key} mismatch: expected {expected!r}, "
                f"observed {state.get(key)!r}"
            )
    state_status = state.get("status")
    if extend:
        if state_status != "complete":
            raise SchedulerError(
                "evidence extension requires state.status=complete"
            )
        if requested_goal is None:
            raise SchedulerError(
                "evidence extension requires an explicit --extend-from Goal"
            )
        if extension_parameters is None:
            raise SchedulerError(
                "evidence extension requires explicit extension parameters"
            )
    elif replay:
        if state_status not in {"stopped", "complete"}:
            raise SchedulerError(
                "replay requires state.status=stopped or complete; refusing "
                "a running runtime"
            )
        if requested_goal is None:
            raise SchedulerError("replay requires an explicit --replay-from Goal")
    elif state_status != "stopped":
        raise SchedulerError(
            "resume requires state.status=stopped; refusing a running or "
            "already-complete runtime (use --replay-from to recompute a "
            "completed suffix or --extend-from for authorized new evidence)"
        )
    for key, expected in {
        "schema_version": 1,
        "branch": branch,
        "run_id": run_id,
    }.items():
        if ledger.get(key) != expected:
            raise SchedulerError(
                f"resume ledger {key} mismatch: expected {expected!r}, "
                f"observed {ledger.get(key)!r}"
            )

    stored_parameters = state.get("user_parameters")
    if not isinstance(stored_parameters, dict):
        raise SchedulerError("resume state does not contain user parameters")
    canonical_stored_parameters = canonicalize_stored_user_parameters(
        project_root,
        stored_parameters,
    )

    goals = list(manifest["goals"])
    records = state.get("goals")
    if not isinstance(records, dict) or set(records) != set(goals):
        raise SchedulerError("resume state Goal set does not match the manifest")
    skill_name_aliases_applied: list[dict[str, str]] = []
    for goal_id in goals:
        record = records.get(goal_id)
        expected_skill = manifest["bindings"][goal_id]["skill"]
        if not isinstance(record, dict):
            raise SchedulerError(f"resume state record is invalid for {goal_id}")
        observed_skill = record.get("skill")
        if not runtime_skill_name_matches(observed_skill, expected_skill):
            raise SchedulerError(f"resume state Skill mismatch for {goal_id}")
        if observed_skill != expected_skill:
            skill_name_aliases_applied.append(
                {
                    "location": "state",
                    "goal": goal_id,
                    "stored": str(observed_skill),
                    "current": str(expected_skill),
                }
            )

    first_incomplete_index = next(
        (
            index
            for index, goal_id in enumerate(goals)
            if records[goal_id].get("status") != "complete"
        ),
        len(goals),
    )
    for goal_id in goals[first_incomplete_index:]:
        if records[goal_id].get("status") == "complete":
            raise SchedulerError(
                f"runtime state is non-serial: {goal_id} is complete after "
                "an incomplete Goal"
            )
    if not replay and not extend and first_incomplete_index == len(goals):
        raise SchedulerError("runtime is already complete; there is nothing to resume")
    first_incomplete = (
        goals[first_incomplete_index]
        if first_incomplete_index < len(goals)
        else None
    )
    start_goal = (
        requested_goal
        if replay or extend
        else (requested_goal or first_incomplete)
    )
    assert start_goal is not None
    if start_goal not in goals:
        raise SchedulerError(
            f"resume Goal {start_goal!r} is not in branch {branch}: {goals}"
        )
    start_index = goals.index(start_goal)
    if replay and start_index > first_incomplete_index:
        blocking_goal = goals[first_incomplete_index]
        raise SchedulerError(
            f"cannot replay {start_goal}: predecessor chain is incomplete at "
            f"{blocking_goal}"
        )
    if not replay and not extend and start_goal != first_incomplete:
        raise SchedulerError(
            f"resume must start at the first incomplete Goal {first_incomplete}; "
            f"requested {start_goal}"
        )
    for goal_id in goals[:start_index]:
        if records[goal_id].get("status") != "complete":
            raise SchedulerError(
                f"cannot resume {start_goal}: predecessor {goal_id} is not complete"
            )
    resolved_parameters = canonical_stored_parameters
    if extend:
        assert extension_parameters is not None
        extension_history = state.get("extension_history", [])
        if not isinstance(extension_history, list):
            raise SchedulerError("extension_history must be a list when present")
        previous_batch_ids = {
            canonical_stored_parameters.get("selection_batch_id")
        }
        for record in extension_history:
            if not isinstance(record, dict):
                raise SchedulerError("extension_history contains an invalid record")
            prior_parameters = record.get("extension_parameters")
            if prior_parameters is None:
                continue
            if not isinstance(prior_parameters, dict):
                raise SchedulerError(
                    "extension_history extension_parameters are invalid"
                )
            previous_batch_ids.add(prior_parameters.get("selection_batch_id"))
        if (
            extension_parameters.get("selection_batch_id")
            in previous_batch_ids
        ):
            raise SchedulerError(
                "extension selection_batch_id must be globally new for the run"
            )
        resolved_parameters = resolve_extension_user_parameters(
            project_root,
            canonical_stored_parameters,
            extension_parameters,
            start_goal=start_goal,
        )
    handoff_root = (run_dir / "handoffs").resolve()
    active_handoff_value = state.get("active_handoff_dir")
    if active_handoff_value is None:
        active_handoff_dir = handoff_root
    elif isinstance(active_handoff_value, str):
        active_handoff_dir = project_path(active_handoff_value, project_root)
        if (
            active_handoff_dir != handoff_root
            and not active_handoff_dir.is_relative_to(handoff_root)
        ):
            raise SchedulerError(
                "resume active_handoff_dir escapes the run handoff root"
            )
    else:
        raise SchedulerError("resume active_handoff_dir must be a path string")
    promotable_handoff: Path | None = None
    if not replay and not extend:
        for goal_id in goals[start_index:]:
            pending_handoff = active_handoff_dir / f"{goal_id}.json"
            if pending_handoff.exists():
                if continue_current_goal and goal_id == start_goal:
                    promotable_handoff = pending_handoff
                    continue
                raise SchedulerError(
                    f"refusing to overwrite uncommitted resume handoff: "
                    f"{pending_handoff}"
                )

    continued_goal: dict[str, Any] | None = None
    if continue_current_goal:
        if state.get("current_goal") != start_goal:
            raise SchedulerError(
                "current-Goal continuation requires state.current_goal to "
                f"equal {start_goal}"
            )
        record = records[start_goal]
        if record.get("status") != "stopped":
            raise SchedulerError(
                f"current-Goal continuation requires {start_goal}.status=stopped"
            )
        thread_id = record.get("thread_id")
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise SchedulerError(
                f"current-Goal continuation requires a persistent thread id "
                f"for {start_goal}"
            )
        artifact_value = record.get("runtime_artifact_root")
        if not isinstance(artifact_value, str):
            raise SchedulerError(
                f"current-Goal continuation requires the prior artifact root "
                f"for {start_goal}"
            )
        artifact_root = project_path(artifact_value, project_root)
        canonical_artifact_root = (
            run_dir / "artifacts" / start_goal
        ).resolve()
        if (
            artifact_root != canonical_artifact_root
            and not artifact_root.is_relative_to(canonical_artifact_root)
        ):
            raise SchedulerError(
                f"current-Goal artifact root escapes {canonical_artifact_root}"
            )
        if not artifact_root.is_dir():
            raise SchedulerError(
                f"current-Goal artifact root is missing: {artifact_root}"
            )
        recorded_goal = record.get("goal")
        recorded_goal_status = (
            recorded_goal.get("status")
            if isinstance(recorded_goal, dict)
            else None
        )
        promote_existing_handoff = recorded_goal_status == "complete"
        if promote_existing_handoff:
            if promotable_handoff is None:
                raise SchedulerError(
                    f"current-Goal continuation found {start_goal} complete "
                    "without its uncommitted runtime handoff"
                )
            pending_payload = load_json(promotable_handoff)
            validate_scheduler_handoff_payload(
                start_goal,
                pending_payload,
                expected_skill=manifest["bindings"][start_goal]["skill"],
                project_root=project_root,
                run_dir=run_dir,
                branch=branch,
                run_id=run_id,
                ledger=ledger,
                user_parameters=resolved_parameters,
            )
        elif recorded_goal_status in {"paused", "active"}:
            if promotable_handoff is not None:
                raise SchedulerError(
                    f"current-Goal continuation refuses an uncommitted "
                    f"handoff while the saved Goal is {recorded_goal_status}"
                )
        else:
            raise SchedulerError(
                f"current-Goal continuation requires a saved paused/active "
                "Goal or a complete Goal with a validated uncommitted "
                f"handoff; observed {recorded_goal_status!r}"
            )
        continued_goal = {
            "goal_id": start_goal,
            "thread_id": thread_id,
            "artifact_root": artifact_root,
            "saved_goal_status": recorded_goal_status,
            "promote_existing_handoff": promote_existing_handoff,
        }
        if promotable_handoff is not None:
            continued_goal["existing_handoff"] = promotable_handoff
            continued_goal["existing_handoff_sha256"] = sha256_file(
                promotable_handoff
            )

    upstream_provenance = state.get("upstream_ledger")
    if upstream_provenance is not None or ledger.get("upstream_ledger") is not None:
        raise SchedulerError(
            "fresh R01-R10 resume refuses an external upstream ledger"
        )
    upstream_provenance = None

    handoffs = ledger.get("handoffs")
    if not isinstance(handoffs, list):
        raise SchedulerError("resume cumulative ledger handoffs must be a list")
    completed_manifest_goals = goals[:first_incomplete_index]
    expected_goal_order = completed_manifest_goals
    if len(handoffs) != len(expected_goal_order):
        raise SchedulerError(
            "resume cumulative ledger length does not match the completed prefix"
    )
    for index, goal_id in enumerate(expected_goal_order):
        expected_skill = expected_resume_skill(
            goal_id,
            manifest=manifest,
            completed_manifest_goals=completed_manifest_goals,
        )
        expected_path = None
        if goal_id in completed_manifest_goals:
            recorded_path = records[goal_id].get("runtime_handoff")
            expected_path = (
                project_path(recorded_path, project_root)
                if isinstance(recorded_path, str)
                else run_dir / "handoffs" / f"{goal_id}.json"
            )
        entry = handoffs[index]
        validate_runtime_handoff_entry(
            project_root,
            entry,
            goal_id=goal_id,
            expected_skill=expected_skill,
            expected_path=expected_path,
            require_recorded_hash=True,
        )
        observed_skill = entry.get("skill") if isinstance(entry, dict) else None
        if observed_skill != expected_skill:
            skill_name_aliases_applied.append(
                {
                    "location": "ledger",
                    "goal": goal_id,
                    "stored": str(observed_skill),
                    "current": str(expected_skill),
                }
            )
    inherited_count = 0
    return {
        "run_dir": run_dir,
        "state_path": state_path,
        "ledger_path": ledger_path,
        "state": state,
        "ledger": ledger,
        "state_sha256": sha256_file(state_path),
        "ledger_sha256": sha256_file(ledger_path),
        "start_goal": start_goal,
        "goal_ids": goals[start_index:],
        "mode": "extend" if extend else ("replay" if replay else "resume"),
        "handoff_dir": active_handoff_dir,
        "ledger_prefix_length": inherited_count + start_index,
        "user_parameters": resolved_parameters,
        "base_user_parameters": canonical_stored_parameters,
        "extension_parameters": (
            copy.deepcopy(extension_parameters) if extend else None
        ),
        "continue_current_goal": continue_current_goal,
        "continued_goal": continued_goal,
        "upstream_provenance": upstream_provenance,
        "skill_name_aliases_applied": skill_name_aliases_applied,
    }


def derive_workflow05_evidence_summary(
    ledger: dict[str, Any],
) -> dict[str, Any]:
    """Derive user-facing evidence state independently of execution state."""
    summary: dict[str, Any] = {
        "schema_version": 1,
        "evidence_status": "unknown",
        "coverage_target_met": None,
        "next_authorization_required": False,
        "source_goal": None,
        "unresolved_binding_count": None,
    }
    handoffs = ledger.get("handoffs")
    if not isinstance(handoffs, list):
        return summary
    r09_entry = next(
        (
            entry
            for entry in reversed(handoffs)
            if isinstance(entry, dict) and entry.get("source_goal") == "R09"
        ),
        None,
    )
    if not isinstance(r09_entry, dict):
        return summary
    payload = r09_entry.get("payload")
    if not isinstance(payload, dict):
        return summary
    coverage_root = payload.get("coverage_and_risk")
    if not isinstance(coverage_root, dict):
        coverage_root = payload
    target_state = coverage_root.get("target_state")
    if not isinstance(target_state, dict):
        target_state = payload.get("target_state")
    if not isinstance(target_state, dict):
        target_state = {}
    coverage_target_met = target_state.get(
        "coverage_target_met",
        payload.get("coverage_target_met"),
    )
    if coverage_target_met is not None and not isinstance(
        coverage_target_met, bool
    ):
        coverage_target_met = None

    terminal = coverage_root.get("terminal_sampling_decision")
    if not isinstance(terminal, dict):
        terminal = payload.get("terminal_sampling_decision")
    if not isinstance(terminal, dict):
        terminal = {}
    deferred = terminal.get("deferred_next_r07_batch")
    next_authorization_required = bool(
        isinstance(deferred, dict)
        and deferred.get("requested") is True
        and deferred.get("authorized_or_executed_by_this_goal") is not True
    )
    unresolved = coverage_root.get("unresolved_bindings")
    if not isinstance(unresolved, dict):
        unresolved = payload.get("unresolved_bindings")
    unresolved_count = len(unresolved) if isinstance(unresolved, dict) else None

    explicit_status = payload.get("evidence_status")
    if explicit_status not in WORKFLOW05_EVIDENCE_STATUSES:
        explicit_status = None
    if coverage_target_met is True and not next_authorization_required:
        evidence_status = (
            "degraded" if explicit_status == "degraded" else "complete"
        )
    elif coverage_target_met is False or next_authorization_required:
        evidence_status = (
            explicit_status
            if explicit_status in {"degraded", "insufficient"}
            else (
                "insufficient"
                if next_authorization_required
                else "degraded"
            )
        )
    else:
        evidence_status = explicit_status or "unknown"

    risk_summary = coverage_root.get("risk_summary")
    if not isinstance(risk_summary, dict):
        risk_summary = {}
    summary.update(
        {
            "evidence_status": evidence_status,
            "coverage_target_met": coverage_target_met,
            "next_authorization_required": next_authorization_required,
            "source_goal": "R09",
            "source_handoff_sha256": r09_entry.get("sha256")
            or r09_entry.get("handoff_sha256"),
            "unresolved_binding_count": unresolved_count,
            "confirmed_concurrency_opportunities": risk_summary.get(
                "confirmed_concurrency_opportunities"
            ),
            "candidate_only_opportunities": risk_summary.get(
                "candidate_only_opportunities"
            ),
            "terminal_decision": terminal.get("decision"),
        }
    )
    return summary


def validate_workflow05_handoff_state(
    goal_id: str,
    payload: dict[str, Any],
) -> None:
    """Keep execution completion distinct from evidence sufficiency."""
    if payload.get("execution_status") != "complete":
        raise SchedulerError(
            f"{goal_id}: runtime handoff execution_status is not complete"
        )
    evidence_status = payload.get("evidence_status")
    if evidence_status not in WORKFLOW05_EVIDENCE_STATUSES:
        raise SchedulerError(
            f"{goal_id}: runtime handoff evidence_status is invalid"
        )
    coverage_target_met = payload.get("coverage_target_met")
    if coverage_target_met is not None and not isinstance(
        coverage_target_met, bool
    ):
        raise SchedulerError(
            f"{goal_id}: runtime handoff coverage_target_met is invalid"
        )
    next_authorization_required = payload.get("next_authorization_required")
    if not isinstance(next_authorization_required, bool):
        raise SchedulerError(
            f"{goal_id}: runtime handoff next_authorization_required "
            "must be boolean"
        )
    if evidence_status == "complete" and (
        coverage_target_met is not True or next_authorization_required
    ):
        raise SchedulerError(
            f"{goal_id}: evidence_status=complete requires "
            "coverage_target_met=true and no next authorization"
        )
    if evidence_status == "unknown" and coverage_target_met is not None:
        raise SchedulerError(
            f"{goal_id}: evidence_status=unknown requires "
            "coverage_target_met=null"
        )
    if evidence_status == "insufficient" and coverage_target_met is True:
        raise SchedulerError(
            f"{goal_id}: evidence_status=insufficient conflicts with "
            "coverage_target_met=true"
        )
    if next_authorization_required and coverage_target_met is not False:
        raise SchedulerError(
            f"{goal_id}: next authorization requires "
            "coverage_target_met=false"
        )


FRESH_HANDOFF_ARTIFACT_KEYS = {
    "R06": ("fresh_run_lineage_manifest", "full_request_target_manifest"),
    "R07": (
        "full_request_profile_metadata",
        "process_trace_summary",
        "fresh_run_dependency_adapter",
        "live_utilization_summary",
        "source_lineage",
    ),
    "R08": ("device_capabilities", "traffic_resource_model", "source_lineage"),
    "R09": ("full_request_analysis", "source_lineage"),
    "R10": ("offline_acceptance_manifest", "source_lineage"),
}


def validate_fresh_e2e_handoff(
    goal_id: str,
    payload: dict[str, Any],
    *,
    project_root: Path,
    run_dir: Path,
    branch: str,
    ledger: dict[str, Any],
    user_parameters: dict[str, Any],
) -> None:
    """Validate same-lineage fresh Workflow05 evidence and pinned artifacts."""
    if branch != FRESH_E2E_BRANCH:
        raise SchedulerError(f"{goal_id}: fresh handoff has the wrong branch")
    if user_parameters.get("evidence_acquisition_mode") != (
        "fresh_no_prior_runtime_reuse"
    ):
        raise SchedulerError(f"{goal_id}: fresh no-reuse mode is missing")
    evidence = payload.get("fresh_e2e_evidence")
    if (
        not isinstance(evidence, dict)
        or evidence.get("schema_version") != 1
        or evidence.get("status") != "complete"
    ):
        raise SchedulerError(f"{goal_id}: fresh_e2e_evidence is incomplete")
    lineage_id = evidence.get("lineage_id")
    if not isinstance(lineage_id, str) or not lineage_id.strip():
        raise SchedulerError(f"{goal_id}: fresh lineage_id is missing")

    prior_lineages: list[str] = []
    handoffs = ledger.get("handoffs")
    if not isinstance(handoffs, list):
        raise SchedulerError(f"{goal_id}: cumulative ledger is invalid")
    for entry in handoffs:
        if not isinstance(entry, dict):
            continue
        prior_payload = entry.get("payload")
        if not isinstance(prior_payload, dict):
            continue
        prior_evidence = prior_payload.get("fresh_e2e_evidence")
        if isinstance(prior_evidence, dict):
            prior_lineage = prior_evidence.get("lineage_id")
            if isinstance(prior_lineage, str) and prior_lineage:
                prior_lineages.append(prior_lineage)
    if prior_lineages and any(value != lineage_id for value in prior_lineages):
        raise SchedulerError(f"{goal_id}: fresh lineage_id changed")

    for key in FRESH_HANDOFF_ARTIFACT_KEYS[goal_id]:
        reference = evidence.get(key)
        if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
            raise SchedulerError(f"{goal_id}: invalid fresh artifact reference {key}")
        path_value = reference.get("path")
        digest = reference.get("sha256")
        if (
            not isinstance(path_value, str)
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise SchedulerError(f"{goal_id}: invalid fresh artifact record {key}")
        path = project_path(path_value, project_root)
        try:
            path.relative_to(run_dir.resolve())
        except ValueError as exc:
            raise SchedulerError(
                f"{goal_id}: fresh artifact escapes the active run: {key}"
            ) from exc
        if not path.is_file() or sha256_file(path) != digest:
            raise SchedulerError(f"{goal_id}: fresh artifact hash mismatch: {key}")


def validate_scheduler_handoff_payload(
    goal_id: str,
    payload: Any,
    *,
    expected_skill: str,
    project_root: Path,
    run_dir: Path,
    branch: str,
    run_id: str,
    ledger: dict[str, Any],
    user_parameters: dict[str, Any],
) -> dict[str, Any]:
    """Apply the same fail-closed handoff checks before or during commit."""
    if not isinstance(payload, dict) or not payload:
        raise SchedulerError(
            f"{goal_id}: runtime handoff must be a non-empty JSON object"
        )
    if payload.get("runtime_goal") != goal_id:
        raise SchedulerError(f"{goal_id}: runtime handoff Goal mismatch")
    if payload.get("status") != "complete":
        raise SchedulerError(f"{goal_id}: runtime handoff is not complete")
    if payload.get("skill") != expected_skill:
        raise SchedulerError(f"{goal_id}: runtime handoff Skill mismatch")
    if goal_id in WORKFLOW05_GOALS:
        validate_workflow05_handoff_state(goal_id, payload)
        validate_fresh_e2e_handoff(
            goal_id,
            payload,
            project_root=project_root,
            run_dir=run_dir,
            branch=branch,
            ledger=ledger,
            user_parameters=user_parameters,
        )
    return payload


class AppServerClient:
    """Thread-safe JSONL client for one Codex app-server process."""

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
        stdout_thread = threading.Thread(
            target=self._read_stdout,
            name="perf-trace-01-05-app-server-stdout",
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._read_stderr,
            name="perf-trace-01-05-app-server-stderr",
            daemon=True,
        )
        self._threads = [stdout_thread, stderr_thread]
        for thread in self._threads:
            thread.start()

    def _log(self, direction: str, message: Any) -> None:
        if self._raw_log is None:
            return
        record = {
            "observed_at": utc_now(),
            "direction": direction,
            "message": message,
        }
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
                self.reader_errors.put(
                    f"invalid app-server JSON: {exc}: {stripped}"
                )
                continue
            self._log("server", message)
            if not isinstance(message, dict):
                self.reader_errors.put(
                    f"app-server message is not an object: {message!r}"
                )
                continue
            if "id" in message and ("result" in message or "error" in message):
                with self._pending_lock:
                    waiter = self._pending.get(message["id"])
                if waiter is None:
                    self.reader_errors.put(
                        f"response for unknown request id {message.get('id')}"
                    )
                else:
                    waiter.put(message)
            elif "id" in message and "method" in message:
                self.server_requests.put(message)
                self._reject_server_request(message)
            else:
                self.notifications.put(message)
        self.reader_errors.put(
            "app-server stdout closed with exit code "
            f"{self.process.returncode}"
        )

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
            raise RpcError(
                f"app-server exited with code {self.process.returncode}"
            )
        encoded = json.dumps(message, ensure_ascii=False)
        self._log("client", message)
        with self._write_lock:
            self.process.stdin.write(encoded + "\n")
            self.process.stdin.flush()

    def _reject_server_request(self, message: dict[str, Any]) -> None:
        response = {
            "id": message["id"],
            "error": {
                "code": -32000,
                "message": (
                    "The non-interactive perf-trace scheduler cannot answer "
                    f"server request {message.get('method')}"
                ),
            },
        }
        try:
            self._write(response)
        except RpcError as exc:
            self.reader_errors.put(str(exc))

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

    def check_health(self) -> None:
        if not self.reader_errors.empty():
            raise RpcError(self.reader_errors.get_nowait())
        if self.process is not None and self.process.poll() is not None:
            raise RpcError(
                f"app-server exited with code {self.process.returncode}"
            )

    def notify(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = params
        self._write(message)

    def initialize(self) -> Any:
        result = self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "qwen_dcu_perf_trace_01_05_runtime",
                    "title": "Qwen DCU Fresh R01-R10 Runtime",
                    "version": "1.0.0",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        self.notify("initialized", {})
        return result

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


class RuntimeScheduler:
    """Run one non-ephemeral-thread Goal at a time in manifest order."""

    def __init__(
        self,
        *,
        project_root: Path,
        branch: str,
        manifest_path: Path,
        manifest: dict[str, Any],
        user_parameters: dict[str, Any],
        upstream_ledger: dict[str, Any] | None,
        upstream_provenance: dict[str, Any] | None,
        codex_bin: Path,
        model: str | None,
        run_id: str,
        poll_seconds: float,
        request_timeout: float,
        goal_timeout_seconds: float,
        idle_timeout_seconds: float,
        resume_context: dict[str, Any] | None = None,
    ) -> None:
        self.project_root = project_root
        self.branch = branch
        self.manifest_path = manifest_path
        self.manifest = manifest
        self.user_parameters = user_parameters
        self.upstream_ledger = upstream_ledger
        self.upstream_provenance = upstream_provenance
        self.codex_bin = codex_bin
        self.model = model
        self.run_id = run_id
        self.poll_seconds = poll_seconds
        self.request_timeout = request_timeout
        self.goal_timeout_seconds = goal_timeout_seconds
        self.idle_timeout_seconds = idle_timeout_seconds
        self.resume_context = resume_context
        runtime_root = require_under(
            project_root / "perf_trace" / "runtime" / branch,
            project_root,
        )
        self.run_dir = runtime_root / run_id
        self.handoff_dir = self.run_dir / "handoffs"
        self.state_path = self.run_dir / "state.json"
        self.ledger_path = self.run_dir / "runtime_handoff_ledger.json"
        self.client: AppServerClient | None = None
        self.current_goal_id: str | None = None
        self.state: dict[str, Any] = {}
        self.ledger: dict[str, Any] = {}
        self.execution_goal_ids: list[str] = list(self.manifest["goals"])
        self.artifact_attempt_name: str | None = None

    def _thread_start_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "cwd": str(self.project_root),
            "approvalPolicy": APPROVAL_POLICY,
            "sandbox": SANDBOX_POLICY,
            "ephemeral": False,
        }
        if self.model:
            params["model"] = self.model
        return params

    def _thread_resume_params(self, thread_id: str) -> dict[str, Any]:
        params: dict[str, Any] = {
            "threadId": thread_id,
            "cwd": str(self.project_root),
            "approvalPolicy": APPROVAL_POLICY,
            "sandbox": SANDBOX_POLICY,
            "excludeTurns": False,
        }
        if self.model:
            params["model"] = self.model
        return params

    def _turn_overrides(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "cwd": str(self.project_root),
            "approvalPolicy": APPROVAL_POLICY,
            "sandboxPolicy": TURN_SANDBOX_POLICY,
            "effort": "max",
            "summary": "concise",
        }
        if self.model:
            params["model"] = self.model
        return params

    def _skill_md(self, goal_id: str) -> Path:
        skill_name = self.manifest["bindings"][goal_id]["skill"]
        path = require_under(
            self.project_root
            / "perf_trace"
            / "skills"
            / skill_name
            / "SKILL.md",
            self.project_root,
        )
        if not path.is_file():
            raise SchedulerError(f"runtime Skill is missing: {path}")
        return path

    def _prompt(
        self,
        goal_id: str,
        output_handoff: Path,
        artifact_root: Path,
    ) -> str:
        skill_name = self.manifest["bindings"][goal_id]["skill"]
        stage_parameters = {
            "project_root": str(self.project_root),
            "branch": self.branch,
            "run_id": self.run_id,
            "runtime_goal": goal_id,
            "runtime_root": str(self.run_dir),
            "runtime_artifact_root": str(artifact_root),
            "runtime_handoff_output": str(output_handoff),
            "user": self.user_parameters,
        }
        prompt_ledger = self.ledger
        ledger_semantic_view = "source_exact"
        active_extension = getattr(self, "state", {}).get("active_extension")
        if isinstance(active_extension, dict):
            stage_parameters["evidence_extension"] = copy.deepcopy(
                active_extension
            )
        ledger_path = require_under(self.ledger_path, self.project_root)
        disk_ledger = load_json(ledger_path)
        if disk_ledger != self.ledger:
            raise SchedulerError(
                f"{goal_id}: cumulative ledger on disk differs from the "
                "scheduler checkpoint"
            )
        ledger_sha256 = sha256_file(ledger_path)
        ledger_handoffs = self.ledger.get("handoffs")
        if not isinstance(ledger_handoffs, list):
            raise SchedulerError(
                f"{goal_id}: cumulative ledger handoffs must be a list"
            )

        prefix = [
            f"${skill_name}",
            "",
            f"你现在只执行运行 Goal {goal_id}。",
            (
                f"已附加的 {skill_name} Skill 是本 Goal 的完整能力约束；"
                "严格遵循其方法、顺序、I/O、验证、失败、停止、证据边界"
                "和完成条件。"
            ),
            "用户参数与调度器分配的本阶段运行位置：",
            json.dumps(stage_parameters, ensure_ascii=False, indent=2),
        ]
        suffix = [
            (
                "本 Goal 输入仅由这个 target Skill、上述用户/运行参数和"
                "累计 ledger 构成。不得调用其他 Skill，不得重写累计前序"
                "产物或 handoff。"
            ),
            (
                "业务运行产物写入 runtime_artifact_root，调度 handoff "
                "只写入 runtime_handoff_output；运行 state、log、handoff "
                "和 artifacts 均不得写入 Skill 目录。Skill 明确要求的当前"
                "项目源码修改仍按 Skill 边界处理。"
            ),
            (
                "只有完成 Skill 的全部完成条件后才写 runtime handoff。"
                "handoff 必须是非空 JSON 对象，至少含 runtime_goal="
                f"{goal_id}、status=complete、skill={skill_name}，并索引"
                "本次真实产物、证据和验证。之后才可将 Goal 标记 complete；"
                "受阻、暂停、受限、失败或中断时如实进入对应状态并停止。"
            ),
            (
                "Workflow05 的 runtime handoff 还必须包含 "
                "execution_status=complete、evidence_status="
                "complete|degraded|insufficient|unknown、"
                "coverage_target_met=true|false|null、"
                "next_authorization_required=true|false。status=complete 只表示"
                "本阶段执行完成，不得据此宣称证据覆盖完成。"
            ),
        ]
        if isinstance(active_extension, dict):
            prefix.extend(
                [
                    "这是显式授权的 Workflow05 增量补证据运行。",
                    (
                        "必须先读取并核验 evidence_extension.base_ledger 的"
                        "不可变完整旧 ledger，再读取当前累计 ledger；只采集"
                        "授权 delta，按稳定语义键去重旧 process/family，绝不"
                        "覆盖旧产物或合并不同 capture 的绝对时钟。"
                    ),
                ]
            )

        compact_ledger = json.dumps(
            prompt_ledger,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        inline_prompt = "\n".join(
            prefix
            + [
                (
                    "累计前序 runtime handoff ledger（紧凑 JSON 内联；"
                    f"语义视图={ledger_semantic_view}）："
                ),
                compact_ledger,
            ]
            + suffix
        )
        if (
            len(compact_ledger) <= MAX_INLINE_LEDGER_CHARS
            and len(inline_prompt) <= APP_SERVER_INPUT_SAFE_CHARS
        ):
            prompt = inline_prompt
            delivery = "inline_compact_json"
        else:
            source_goals = [
                entry.get("source_goal")
                for entry in ledger_handoffs
                if isinstance(entry, dict)
                and isinstance(entry.get("source_goal"), str)
            ]
            ledger_reference = {
                "delivery": "immutable_filesystem_json",
                "path": str(ledger_path),
                "sha256": ledger_sha256,
                "byte_size": ledger_path.stat().st_size,
                "schema_version": self.ledger.get("schema_version"),
                "branch": self.ledger.get("branch"),
                "run_id": self.ledger.get("run_id"),
                "handoff_count": len(ledger_handoffs),
                "source_goals": source_goals,
            }
            prompt = "\n".join(
                prefix
                + [
                    (
                        "累计前序 runtime handoff ledger（因输入长度上限，"
                        "以不可变文件引用交付）："
                    ),
                    json.dumps(
                        ledger_reference,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    (
                        "开始分析前必须完整读取上述 JSON 文件，并先按给定 "
                        "SHA-256 核验原始文件字节；哈希、schema、branch、"
                        "run_id、handoff_count 或 source_goals 任一不符即停止。"
                        "该文件引用只是累计 ledger 的传输形式，仍是本 Goal "
                        "的必需输入，不是可选的运行时发现或额外输入源。"
                    ),
                    (
                        "若 ledger_semantic_compatibility 存在，只对其中列出的"
                        "精确旧值应用 prompt 语义别名；不得修改已完成 handoff，"
                        "不得改写路径、哈希或测量证据。"
                    ),
                ]
                + suffix
            )
            delivery = "immutable_filesystem_json"

        if len(prompt) > APP_SERVER_INPUT_SAFE_CHARS:
            raise SchedulerError(
                f"{goal_id}: prompt remains too large after ledger "
                f"compaction/reference ({len(prompt)} chars; safe limit "
                f"{APP_SERVER_INPUT_SAFE_CHARS})"
            )
        self._last_prompt_metadata = {
            "text_chars": len(prompt),
            "app_server_max_chars": APP_SERVER_INPUT_MAX_CHARS,
            "safe_chars": APP_SERVER_INPUT_SAFE_CHARS,
            "ledger_delivery": delivery,
            "ledger_sha256": ledger_sha256,
            "ledger_byte_size": ledger_path.stat().st_size,
            "ledger_handoff_count": len(ledger_handoffs),
            "ledger_semantic_view": ledger_semantic_view,
        }
        return prompt

    def _goal_objective(self, goal_id: str) -> str:
        skill_name = self.manifest["bindings"][goal_id]["skill"]
        return (
            f"Execute runtime stage {goal_id} with ${skill_name}, the supplied "
            "user parameters, and the cumulative prior runtime handoff ledger; "
            "reach complete only after the Skill completion conditions hold."
        )

    def _initialize_runtime_files(self) -> None:
        validate_run_id(self.run_id)
        if self.resume_context is not None:
            self._initialize_resume_runtime_files()
            return
        if self.run_dir.exists():
            raise SchedulerError(
                f"runtime output directory already exists: {self.run_dir}"
            )
        self.handoff_dir.mkdir(parents=True)
        created_at = utc_now()
        initial_handoffs: list[dict[str, Any]] = []
        if self.upstream_ledger is not None:
            initial_handoffs = copy.deepcopy(self.upstream_ledger["handoffs"])
        self.state = {
            "schema_version": 1,
            "branch": self.branch,
            "manifest": str(self.manifest_path.relative_to(self.project_root)),
            "run_id": self.run_id,
            "status": "running",
            "execution_status": "running",
            "evidence_status": "unknown",
            "coverage_target_met": None,
            "next_authorization_required": False,
            "created_at": created_at,
            "updated_at": created_at,
            "current_goal": None,
            "user_parameters": self.user_parameters,
            "upstream_ledger": self.upstream_provenance,
            "ledger": str(self.ledger_path.relative_to(self.project_root)),
            "goals": {
                goal_id: {
                    "skill": self.manifest["bindings"][goal_id]["skill"],
                    "status": "pending",
                    "thread_id": None,
                    "turn_ids": [],
                    "goal": None,
                    "error": None,
                }
                for goal_id in self.manifest["goals"]
            },
        }
        self.ledger = {
            "schema_version": 1,
            "branch": self.branch,
            "run_id": self.run_id,
            "upstream_ledger": self.upstream_provenance,
            "handoffs": initial_handoffs,
        }
        self._checkpoint()
        atomic_write_json(self.ledger_path, self.ledger)

    @staticmethod
    def _previous_attempt_snapshot(record: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "status",
            "thread_id",
            "turn_ids",
            "goal",
            "error",
            "runtime_artifact_root",
            "runtime_handoff",
            "handoff_index",
            "thread_status",
            "initial_turn_id",
            "initial_turn_input",
            "initial_turn_start_response",
            "last_turn",
            "thread_resume",
            "continuing_existing_thread",
            "transport_status",
            "transport_recovered_at",
            "transport_failed_at",
            "last_retryable_transport_error",
            "retryable_transport_error_history",
        )
        return {
            key: copy.deepcopy(record[key])
            for key in keys
            if key in record
        }

    def _new_goal_record(
        self,
        goal_id: str,
        *,
        attempt_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "skill": self.manifest["bindings"][goal_id]["skill"],
            "status": "pending",
            "thread_id": None,
            "turn_ids": [],
            "goal": None,
            "error": None,
        }
        if attempt_history:
            record["attempt_history"] = attempt_history
        return record

    def _initialize_resume_runtime_files(self) -> None:
        assert self.resume_context is not None
        context = self.resume_context
        if self.run_dir != context["run_dir"]:
            raise SchedulerError("resume runtime directory changed after validation")
        if sha256_file(self.state_path) != context["state_sha256"]:
            raise SchedulerError("resume state changed after validation")
        if sha256_file(self.ledger_path) != context["ledger_sha256"]:
            raise SchedulerError("resume ledger changed after validation")
        self.state = copy.deepcopy(context["state"])
        self.ledger = copy.deepcopy(context["ledger"])
        self.execution_goal_ids = list(context["goal_ids"])
        resumed_at = utc_now()
        operation = context.get("mode", "resume")
        prior_run_status = self.state.get("status")
        prior_current_goal = self.state.get("current_goal")
        if operation in {"replay", "extend"}:
            attempt_id = (
                self._allocate_replay_namespace()
                if operation == "replay"
                else self._allocate_extension_namespace()
            )
            self.artifact_attempt_name = attempt_id
            history_dir_name = (
                "replay_history" if operation == "replay" else "extension_history"
            )
            snapshot_dir = self.run_dir / history_dir_name / attempt_id
            self.handoff_dir = self.run_dir / "handoffs" / attempt_id
            snapshot_dir.mkdir(parents=True)
            self.handoff_dir.mkdir(parents=True)
            snapshot_state = snapshot_dir / "state.before.json"
            snapshot_ledger = snapshot_dir / "runtime_handoff_ledger.before.json"
            shutil.copy2(self.state_path, snapshot_state)
            shutil.copy2(self.ledger_path, snapshot_ledger)
            if sha256_file(snapshot_state) != context["state_sha256"]:
                raise SchedulerError(f"{operation} state snapshot hash mismatch")
            if sha256_file(snapshot_ledger) != context["ledger_sha256"]:
                raise SchedulerError(f"{operation} ledger snapshot hash mismatch")
            original_handoffs = self.ledger.get("handoffs")
            if not isinstance(original_handoffs, list):
                raise SchedulerError(
                    f"{operation} cumulative ledger handoffs are invalid"
                )
            prefix_length = context["ledger_prefix_length"]
            superseded_entries = original_handoffs[prefix_length:]
            history_key = (
                "replay_history" if operation == "replay" else "extension_history"
            )
            history = self.state.setdefault(history_key, [])
            if not isinstance(history, list):
                raise SchedulerError(f"{history_key} must be a list when present")
            history_record = {
                (
                    "replay_id" if operation == "replay" else "extension_id"
                ): attempt_id,
                (
                    "replayed_at" if operation == "replay" else "extended_at"
                ): resumed_at,
                "from_goal": context["start_goal"],
                "execution_goals": list(self.execution_goal_ids),
                "prior_run_status": prior_run_status,
                "prior_current_goal": prior_current_goal,
                "prior_state_sha256": context["state_sha256"],
                "prior_ledger_sha256": context["ledger_sha256"],
                "skill_name_aliases_applied": copy.deepcopy(
                    context.get("skill_name_aliases_applied", [])
                ),
                "state_snapshot": str(
                    snapshot_state.relative_to(self.project_root)
                ),
                "ledger_snapshot": str(
                    snapshot_ledger.relative_to(self.project_root)
                ),
                "new_handoff_dir": str(
                    self.handoff_dir.relative_to(self.project_root)
                ),
                (
                    "superseded_handoffs"
                    if operation == "replay"
                    else "base_suffix_handoffs"
                ): [
                    {
                        "source_goal": entry.get("source_goal"),
                        "path": entry.get("path"),
                        "sha256": entry.get("sha256")
                        or entry.get("handoff_sha256"),
                    }
                    for entry in superseded_entries
                    if isinstance(entry, dict)
                ],
                "model": self.model,
            }
            if operation == "extend":
                extension_parameters = context.get("extension_parameters")
                if not isinstance(extension_parameters, dict):
                    raise SchedulerError(
                        "extension context lacks explicit extension parameters"
                    )
                extension_parameters_sha256 = hashlib.sha256(
                    json.dumps(
                        extension_parameters,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                base_ledger = {
                    "path": str(snapshot_ledger.relative_to(self.project_root)),
                    "sha256": context["ledger_sha256"],
                    "state_path": str(snapshot_state.relative_to(self.project_root)),
                    "state_sha256": context["state_sha256"],
                    "run_id": self.run_id,
                    "handoff_count": len(original_handoffs),
                }
                active_extension = {
                    "schema_version": 1,
                    "extension_id": attempt_id,
                    "from_goal": context["start_goal"],
                    "base_ledger": base_ledger,
                    "extension_parameters": copy.deepcopy(extension_parameters),
                    "extension_parameters_sha256": extension_parameters_sha256,
                    "deduplication_key": (
                        "contract_relation/semantic_key/process_or_family_identity"
                    ),
                    "clock_policy": "separate_capture_clock_axes_no_merge",
                }
                history_record["base_ledger"] = copy.deepcopy(base_ledger)
                history_record["extension_parameters"] = copy.deepcopy(
                    extension_parameters
                )
                history_record["extension_parameters_sha256"] = (
                    extension_parameters_sha256
                )
                self.state["active_extension"] = active_extension
                self.ledger["extension_base"] = copy.deepcopy(active_extension)
            else:
                self.state.pop("active_extension", None)
                self.ledger.pop("extension_base", None)
            history.append(history_record)
            self.ledger["handoffs"] = copy.deepcopy(
                original_handoffs[:prefix_length]
            )
            atomic_write_json(self.ledger_path, self.ledger)
        elif operation == "resume":
            self.handoff_dir = context["handoff_dir"]
            resume_history = self.state.setdefault("resume_history", [])
            if not isinstance(resume_history, list):
                raise SchedulerError("resume_history must be a list when present")
            resume_history.append(
                {
                    "resumed_at": resumed_at,
                    "from_goal": context["start_goal"],
                    "execution_goals": list(self.execution_goal_ids),
                    "prior_run_status": prior_run_status,
                    "prior_current_goal": prior_current_goal,
                    "prior_state_sha256": context["state_sha256"],
                    "prior_ledger_sha256": context["ledger_sha256"],
                    "skill_name_aliases_applied": copy.deepcopy(
                        context.get("skill_name_aliases_applied", [])
                    ),
                    "model": self.model,
                    "continue_current_goal": bool(
                        context.get("continue_current_goal")
                    ),
                }
            )
        else:
            raise SchedulerError(f"unsupported recovery operation: {operation}")
        for goal_id in self.execution_goal_ids:
            previous = self._goal_record(goal_id)
            if (
                context.get("continue_current_goal")
                and goal_id == context["start_goal"]
            ):
                continuation_history = previous.setdefault(
                    "continuation_history", []
                )
                if not isinstance(continuation_history, list):
                    raise SchedulerError(
                        f"{goal_id}: continuation_history must be a list "
                        "when present"
                    )
                continuation_history.append(
                    {
                        "continued_at": resumed_at,
                        "operation": (
                            "promote_existing_handoff"
                            if context.get("continued_goal", {}).get(
                                "promote_existing_handoff"
                            )
                            else "continue_existing_thread"
                        ),
                        "prior_status": previous.get("status"),
                        "prior_error": previous.get("error"),
                        "thread_id": previous.get("thread_id"),
                        "runtime_artifact_root": previous.get(
                            "runtime_artifact_root"
                        ),
                        "prior_state_sha256": context["state_sha256"],
                        "prior_ledger_sha256": context["ledger_sha256"],
                    }
                )
                previous["status"] = "pending"
                previous["error"] = None
                if context.get("continued_goal", {}).get(
                    "promote_existing_handoff"
                ):
                    previous["promoting_existing_handoff"] = True
                    previous.pop("continuing_existing_thread", None)
                else:
                    previous["continuing_existing_thread"] = True
                continue
            attempt_history = copy.deepcopy(previous.get("attempt_history", []))
            if not isinstance(attempt_history, list):
                raise SchedulerError(
                    f"{goal_id}: attempt_history must be a list when present"
                )
            meaningful_attempt = any(
                previous.get(key) not in (None, [], "pending")
                for key in (
                    "status",
                    "thread_id",
                    "turn_ids",
                    "goal",
                    "error",
                    "runtime_artifact_root",
                    "runtime_handoff",
                    "handoff_index",
                    "initial_turn_id",
                    "last_turn",
                )
            )
            if meaningful_attempt:
                snapshot = self._previous_attempt_snapshot(previous)
                snapshot["superseded_at"] = resumed_at
                attempt_history.append(snapshot)
            self.state["goals"][goal_id] = self._new_goal_record(
                goal_id,
                attempt_history=attempt_history,
            )
        self.state["status"] = "running"
        self.state["execution_status"] = "running"
        self.state["user_parameters"] = copy.deepcopy(
            context["user_parameters"]
        )
        self.state["current_goal"] = None
        self.state["resumed_at"] = resumed_at
        self.state["active_handoff_dir"] = str(
            self.handoff_dir.relative_to(self.project_root)
        )
        self.state["recovery_operation"] = operation
        self.state.pop("last_error", None)
        self.state.pop("completed_at", None)
        self._checkpoint()

    def _allocate_replay_namespace(self) -> str:
        for attempt in range(1, 1000):
            replay_id = f"replay-{attempt:03d}"
            candidates = [
                self.run_dir / "handoffs" / replay_id,
                self.run_dir / "replay_history" / replay_id,
            ]
            candidates.extend(
                self.run_dir / "artifacts" / goal_id / replay_id
                for goal_id in self.execution_goal_ids
            )
            if not any(path.exists() for path in candidates):
                return replay_id
        raise SchedulerError("no available replay namespace")

    def _allocate_extension_namespace(self) -> str:
        for attempt in range(1, 1000):
            extension_id = f"extension-{attempt:03d}"
            candidates = [
                self.run_dir / "handoffs" / extension_id,
                self.run_dir / "extension_history" / extension_id,
            ]
            candidates.extend(
                self.run_dir / "artifacts" / goal_id / extension_id
                for goal_id in self.execution_goal_ids
            )
            if not any(path.exists() for path in candidates):
                return extension_id
        raise SchedulerError("no available evidence-extension namespace")

    def _select_artifact_root(self, goal_id: str) -> Path:
        canonical = self.run_dir / "artifacts" / goal_id
        if not canonical.exists():
            canonical.mkdir(parents=True)
            return canonical
        if not canonical.is_dir():
            raise SchedulerError(
                f"{goal_id}: runtime artifact root is not a directory: {canonical}"
            )
        if not any(canonical.iterdir()):
            return canonical
        if self.resume_context is None:
            raise SchedulerError(
                f"{goal_id}: runtime artifact root already contains files: "
                f"{canonical}"
            )
        artifact_attempt_name = getattr(self, "artifact_attempt_name", None)
        if artifact_attempt_name is not None:
            candidate = canonical / artifact_attempt_name
            if candidate.exists():
                raise SchedulerError(
                    f"{goal_id}: replay artifact root already exists: {candidate}"
                )
            candidate.mkdir()
            return candidate
        for attempt in range(1, 1000):
            candidate = canonical / f"resume-{attempt:03d}"
            if not candidate.exists():
                candidate.mkdir()
                return candidate
        raise SchedulerError(
            f"{goal_id}: no available resume artifact directory under {canonical}"
        )

    def _checkpoint(self) -> None:
        if self.state:
            self.state["updated_at"] = utc_now()
            atomic_write_json(self.state_path, self.state)

    def _goal_record(self, goal_id: str) -> dict[str, Any]:
        return self.state["goals"][goal_id]

    def _transition(
        self,
        goal_id: str,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        record = self._goal_record(goal_id)
        record["status"] = status
        record["error"] = error
        self.state["current_goal"] = goal_id
        self._checkpoint()

    def _start_client(self) -> None:
        self.client = AppServerClient(
            codex_bin=self.codex_bin,
            cwd=self.project_root,
            raw_log_path=self.run_dir / "app_server.jsonl",
            stderr_log_path=self.run_dir / "app_server.stderr.log",
            request_timeout=self.request_timeout,
        )
        self.client.start()
        self.client.initialize()
        skill_root = self.project_root / "perf_trace" / "skills"
        self.client.request(
            "skills/extraRoots/set",
            {"extraRoots": [str(skill_root)]},
        )
        result = self.client.request(
            "skills/list",
            {"cwds": [str(self.project_root)], "forceReload": True},
        )
        discovered: dict[str, Path] = {}
        for entry in result.get("data", []):
            for skill in entry.get("skills", []):
                name = skill.get("name")
                path = skill.get("path")
                if (
                    isinstance(name, str)
                    and isinstance(path, str)
                    and skill.get("enabled", True)
                ):
                    discovered.setdefault(name, Path(path).resolve())
        for goal_id in self.manifest["goals"]:
            name = self.manifest["bindings"][goal_id]["skill"]
            expected = self._skill_md(goal_id)
            actual = discovered.get(name)
            if actual != expected:
                raise SchedulerError(
                    "runtime Skill discovery mismatch: "
                    f"name={name} actual={actual} expected={expected}"
                )

    def _get_goal(self, thread_id: str) -> dict[str, Any]:
        assert self.client is not None
        result = self.client.request(
            "thread/goal/get",
            {"threadId": thread_id},
        )
        goal = result.get("goal")
        if not isinstance(goal, dict):
            raise SchedulerError(
                f"thread/goal/get returned no Goal for {thread_id}"
            )
        return goal

    def _set_goal_status(self, goal_id: str, status: str) -> dict[str, Any]:
        assert self.client is not None
        record = self._goal_record(goal_id)
        result = self.client.request(
            "thread/goal/set",
            {"threadId": record["thread_id"], "status": status},
        )
        goal = result.get("goal")
        if not isinstance(goal, dict):
            raise SchedulerError(f"{goal_id}: thread/goal/set returned no Goal")
        record["goal"] = goal
        self._checkpoint()
        return goal

    def _get_thread(
        self,
        thread_id: str,
        *,
        include_turns: bool,
    ) -> dict[str, Any]:
        assert self.client is not None
        result = self.client.request(
            "thread/read",
            {"threadId": thread_id, "includeTurns": include_turns},
        )
        thread = result.get("thread")
        if not isinstance(thread, dict):
            raise SchedulerError(f"thread/read returned no thread for {thread_id}")
        return thread

    def _resume_persistent_thread(
        self,
        goal_id: str,
        thread_id: str,
    ) -> dict[str, Any]:
        """Load or rejoin a persistent thread before using its Goal."""
        assert self.client is not None
        result = self.client.request(
            "thread/resume",
            self._thread_resume_params(thread_id),
        )
        thread = result.get("thread")
        if not isinstance(thread, dict):
            raise SchedulerError(
                f"{goal_id}: thread/resume returned no persistent thread"
            )
        if thread.get("id") != thread_id:
            raise SchedulerError(
                f"{goal_id}: thread/resume returned a different thread"
            )
        status = self._thread_status_type(thread)
        if status == "notLoaded":
            raise SchedulerError(
                f"{goal_id}: thread/resume did not load the persistent thread"
            )
        record = self._goal_record(goal_id)
        record["thread_resume"] = {
            "resumed_at": utc_now(),
            "thread_id": thread_id,
            "status": copy.deepcopy(thread.get("status")),
            "path": thread.get("path"),
        }
        self._record_thread(goal_id, thread)
        return thread

    @staticmethod
    def _thread_status_type(thread: dict[str, Any]) -> str | None:
        status = thread.get("status")
        if isinstance(status, dict):
            value = status.get("type")
            return value if isinstance(value, str) else None
        return status if isinstance(status, str) else None

    def _record_thread(self, goal_id: str, thread: dict[str, Any]) -> None:
        record = self._goal_record(goal_id)
        turn_ids: list[str] = []
        for turn in thread.get("turns", []):
            if isinstance(turn, dict) and isinstance(turn.get("id"), str):
                turn_ids.append(turn["id"])
        record["turn_ids"] = turn_ids
        record["thread_status"] = thread.get("status")
        self._checkpoint()

    def _drain_event(
        self,
        goal_id: str,
        *,
        timeout: float,
    ) -> dict[str, Any] | None:
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
            return None
        method = message.get("method")
        params = message.get("params", {})
        if not isinstance(params, dict):
            return message
        record = self._goal_record(goal_id)
        if params.get("threadId") not in (None, record.get("thread_id")):
            return message
        if (
            method in {"item/started", "item/completed", "turn/started"}
            and record.get("transport_status") == "retrying"
        ):
            record["transport_status"] = "connected"
            record["transport_recovered_at"] = utc_now()
            self._checkpoint()
        if method == "turn/started":
            turn_id = params.get("turn", {}).get("id")
            if isinstance(turn_id, str) and turn_id not in record["turn_ids"]:
                record["turn_ids"].append(turn_id)
                self._checkpoint()
        elif method == "turn/completed":
            turn = params.get("turn", {})
            turn_id = turn.get("id")
            status = turn.get("status")
            record["last_turn"] = {
                "id": turn_id,
                "status": status,
                "error": turn.get("error"),
            }
            self._checkpoint()
            if status in {"failed", "interrupted"}:
                raise SchedulerError(
                    f"{goal_id}: Turn {turn_id} ended with {status}"
                )
        elif method == "thread/goal/updated":
            goal = params.get("goal")
            if isinstance(goal, dict):
                record["goal"] = goal
                self._checkpoint()
        elif method == "thread/status/changed":
            record["thread_status"] = params.get("status")
            self._checkpoint()
        elif method == "error":
            if params.get("willRetry") is True:
                retry_record = {
                    "observed_at": utc_now(),
                    "thread_id": params.get("threadId"),
                    "turn_id": params.get("turnId"),
                    "error": copy.deepcopy(params.get("error")),
                }
                history = record.setdefault(
                    "retryable_transport_error_history", []
                )
                if not isinstance(history, list):
                    raise SchedulerError(
                        f"{goal_id}: retryable transport history is invalid"
                    )
                history.append(retry_record)
                del history[:-20]
                record["transport_status"] = "retrying"
                record["last_retryable_transport_error"] = retry_record
                self._checkpoint()
                return message
            record["transport_status"] = "failed"
            record["transport_failed_at"] = utc_now()
            self._checkpoint()
            raise SchedulerError(
                f"{goal_id}: app-server error notification: {params}"
            )
        return message

    def _start_initial_turn(
        self,
        goal_id: str,
        output_handoff: Path,
        artifact_root: Path,
    ) -> str:
        assert self.client is not None
        record = self._goal_record(goal_id)
        skill_name = self.manifest["bindings"][goal_id]["skill"]
        prompt = self._prompt(goal_id, output_handoff, artifact_root)
        record["initial_turn_input"] = copy.deepcopy(
            getattr(
                self,
                "_last_prompt_metadata",
                {
                    "text_chars": len(prompt),
                    "ledger_delivery": "test_or_custom_prompt",
                },
            )
        )
        self._checkpoint()
        params = {
            "threadId": record["thread_id"],
            "input": [
                {
                    "type": "text",
                    "text": prompt,
                },
                {
                    "type": "skill",
                    "name": skill_name,
                    "path": str(self._skill_md(goal_id)),
                },
            ],
            **self._turn_overrides(),
        }
        result = self.client.request("turn/start", params)
        turn = result.get("turn", {})
        turn_id = turn.get("id")
        if not isinstance(turn_id, str):
            raise SchedulerError(f"{goal_id}: turn/start returned no Turn id")
        turn_status = turn.get("status")
        if turn_status in {"failed", "interrupted"}:
            raise SchedulerError(
                f"{goal_id}: turn/start returned terminal status {turn_status}"
            )
        record["initial_turn_id"] = turn_id
        record["initial_turn_start_response"] = {
            "id": turn_id,
            "status": turn_status,
        }
        if turn_id not in record["turn_ids"]:
            record["turn_ids"].append(turn_id)
        self._transition(goal_id, "running")
        return turn_id

    def _wait_until_idle(self, goal_id: str) -> dict[str, Any]:
        record = self._goal_record(goal_id)
        deadline = (
            time.monotonic() + self.idle_timeout_seconds
            if self.idle_timeout_seconds > 0
            else None
        )
        while deadline is None or time.monotonic() < deadline:
            self._drain_event(goal_id, timeout=0.2)
            thread = self._get_thread(record["thread_id"], include_turns=True)
            if (
                self._thread_status_type(thread) == "notLoaded"
                and record.get("continuing_existing_thread")
            ):
                thread = self._resume_persistent_thread(
                    goal_id, record["thread_id"]
                )
            self._record_thread(goal_id, thread)
            active_turn = any(
                isinstance(turn, dict) and turn.get("status") == "inProgress"
                for turn in thread.get("turns", [])
            )
            if self._thread_status_type(thread) == "idle" and not active_turn:
                return thread
            time.sleep(0.2)
        raise SchedulerError(
            f"{goal_id}: thread did not become idle after Goal completion"
        )

    def _read_handoff(self, goal_id: str, path: Path) -> dict[str, Any]:
        payload = load_json(path)
        expected_skill = self.manifest["bindings"][goal_id]["skill"]
        try:
            return validate_scheduler_handoff_payload(
                goal_id,
                payload,
                expected_skill=expected_skill,
                project_root=self.project_root,
                run_dir=self.run_dir,
                branch=self.branch,
                run_id=self.run_id,
                ledger=getattr(self, "ledger", {}),
                user_parameters=self.user_parameters,
            )
        except SchedulerError as exc:
            raise SchedulerError(f"{exc}: {path}") from exc

    def _append_handoff(self, goal_id: str, path: Path) -> None:
        record = self._goal_record(goal_id)
        if load_json(self.ledger_path) != self.ledger:
            raise SchedulerError(
                f"{goal_id}: cumulative ledger changed while the Goal was "
                "running"
            )
        payload = self._read_handoff(goal_id, path)
        entry = {
            "source_goal": goal_id,
            "status": "complete",
            "skill": self.manifest["bindings"][goal_id]["skill"],
            "path": str(path),
            "sha256": sha256_file(path),
            "payload": payload,
        }
        self.ledger["handoffs"].append(entry)
        atomic_write_json(self.ledger_path, self.ledger)
        record["handoff_index"] = len(self.ledger["handoffs"]) - 1
        record["runtime_handoff"] = str(path.relative_to(self.project_root))
        if goal_id in WORKFLOW05_GOALS:
            self.state["evidence_status"] = payload["evidence_status"]
            self.state["coverage_target_met"] = payload[
                "coverage_target_met"
            ]
            self.state["next_authorization_required"] = payload[
                "next_authorization_required"
            ]
            if goal_id in {"R09", "R10"}:
                summary = derive_workflow05_evidence_summary(self.ledger)
                self.state["evidence_summary"] = summary
                self.state["evidence_status"] = summary["evidence_status"]
                self.state["coverage_target_met"] = summary[
                    "coverage_target_met"
                ]
                self.state["next_authorization_required"] = summary[
                    "next_authorization_required"
                ]
        self._transition(goal_id, "complete")

    def _wait_for_goal_complete(self, goal_id: str) -> None:
        record = self._goal_record(goal_id)
        deadline = (
            time.monotonic() + self.goal_timeout_seconds
            if self.goal_timeout_seconds > 0
            else None
        )
        last_poll = 0.0
        while deadline is None or time.monotonic() < deadline:
            self._drain_event(goal_id, timeout=0.5)
            now = time.monotonic()
            if now - last_poll < self.poll_seconds:
                continue
            goal = self._get_goal(record["thread_id"])
            record["goal"] = goal
            self._checkpoint()
            status = goal.get("status")
            if status == "complete":
                return
            if status in STOP_GOAL_STATUSES:
                raise SchedulerError(
                    f"{goal_id}: Goal reached stop status {status}"
                )
            if status != "active":
                raise SchedulerError(
                    f"{goal_id}: inconsistent Goal status {status}"
                )
            thread = self._get_thread(record["thread_id"], include_turns=False)
            thread_status = self._thread_status_type(thread)
            if (
                thread_status == "notLoaded"
                and record.get("continuing_existing_thread")
            ):
                thread = self._resume_persistent_thread(
                    goal_id, record["thread_id"]
                )
                thread_status = self._thread_status_type(thread)
            if thread_status not in {"active", "idle"}:
                raise SchedulerError(
                    f"{goal_id}: inconsistent thread status {thread_status}"
                )
            last_poll = now
        raise SchedulerError(
            f"{goal_id}: Goal exceeded {self.goal_timeout_seconds} seconds"
        )

    def _continue_existing_goal(self, goal_id: str) -> None:
        """Reattach to one paused persistent Goal without repeating its work."""
        assert self.resume_context is not None
        continued = self.resume_context.get("continued_goal")
        if not isinstance(continued, dict) or continued.get("goal_id") != goal_id:
            raise SchedulerError(
                f"{goal_id}: current-Goal continuation context is invalid"
            )
        record = self._goal_record(goal_id)
        thread_id = continued.get("thread_id")
        if not isinstance(thread_id, str) or record.get("thread_id") != thread_id:
            raise SchedulerError(
                f"{goal_id}: persistent thread changed before continuation"
            )
        artifact_root = continued.get("artifact_root")
        if not isinstance(artifact_root, Path) or not artifact_root.is_dir():
            raise SchedulerError(
                f"{goal_id}: prior runtime artifact root is unavailable"
            )
        if record.get("runtime_artifact_root") != str(
            artifact_root.relative_to(self.project_root)
        ):
            raise SchedulerError(
                f"{goal_id}: prior runtime artifact root changed before "
                "continuation"
            )
        output_handoff = self.handoff_dir / f"{goal_id}.json"
        if continued.get("promote_existing_handoff"):
            expected_handoff = continued.get("existing_handoff")
            expected_hash = continued.get("existing_handoff_sha256")
            if (
                continued.get("saved_goal_status") != "complete"
                or not isinstance(expected_handoff, Path)
                or expected_handoff != output_handoff
                or not output_handoff.is_file()
                or not isinstance(expected_hash, str)
                or sha256_file(output_handoff) != expected_hash
            ):
                raise SchedulerError(
                    f"{goal_id}: completed uncommitted handoff changed before "
                    "promotion"
                )
            record["promoting_existing_handoff"] = True
            self._checkpoint()
            self._append_handoff(goal_id, output_handoff)
            record.pop("promoting_existing_handoff", None)
            self._checkpoint()
            return
        if output_handoff.exists():
            raise SchedulerError(
                f"{goal_id}: refusing to reuse uncommitted runtime handoff "
                f"{output_handoff}"
            )

        assert self.client is not None
        thread = self._resume_persistent_thread(goal_id, thread_id)
        active_turns = [
            turn
            for turn in thread.get("turns", [])
            if isinstance(turn, dict) and turn.get("status") == "inProgress"
        ]
        goal = self._get_goal(thread_id)
        record["goal"] = goal
        record["continuing_existing_thread"] = True
        record["transport_status"] = "connected"
        record["transport_recovered_at"] = utc_now()
        self._checkpoint()
        status = goal.get("status")
        if status == "complete":
            self._wait_until_idle(goal_id)
            self._append_handoff(goal_id, output_handoff)
            record.pop("continuing_existing_thread", None)
            self._checkpoint()
            return
        if status in TERMINAL_GOAL_STATUSES:
            raise SchedulerError(
                f"{goal_id}: persisted Goal cannot continue from status {status}"
            )
        if status == "paused":
            if active_turns:
                raise SchedulerError(
                    f"{goal_id}: paused Goal still has an in-progress Turn; "
                    "refusing an ambiguous continuation"
                )
            self._transition(goal_id, "running")
            self._set_goal_status(goal_id, "active")
        elif status == "active":
            self._transition(goal_id, "running")
        else:
            raise SchedulerError(
                f"{goal_id}: persisted Goal has inconsistent status {status}"
            )
        self._wait_for_goal_complete(goal_id)
        self._wait_until_idle(goal_id)
        self._append_handoff(goal_id, output_handoff)
        record.pop("continuing_existing_thread", None)
        self._checkpoint()

    def _run_goal(self, goal_id: str) -> None:
        assert self.client is not None
        if (
            self.resume_context is not None
            and self.resume_context.get("continue_current_goal")
            and goal_id == self.resume_context.get("start_goal")
        ):
            self._continue_existing_goal(goal_id)
            return
        record = self._goal_record(goal_id)
        output_handoff = self.handoff_dir / f"{goal_id}.json"
        if output_handoff.exists():
            raise SchedulerError(
                f"{goal_id}: refusing to reuse runtime handoff {output_handoff}"
            )
        artifact_root = self._select_artifact_root(goal_id)
        record["runtime_artifact_root"] = str(
            artifact_root.relative_to(self.project_root)
        )
        self._checkpoint()
        result = self.client.request("thread/start", self._thread_start_params())
        thread = result.get("thread")
        thread_id = thread.get("id") if isinstance(thread, dict) else None
        if not isinstance(thread_id, str):
            raise SchedulerError(f"{goal_id}: thread/start returned no thread id")
        record["thread_id"] = thread_id
        record["thread_status"] = thread.get("status")
        self._transition(goal_id, "thread_created")
        goal_result = self.client.request(
            "thread/goal/set",
            {
                "threadId": thread_id,
                "objective": self._goal_objective(goal_id),
                "status": "paused",
            },
        )
        goal = goal_result.get("goal")
        if not isinstance(goal, dict):
            raise SchedulerError(f"{goal_id}: thread/goal/set returned no Goal")
        record["goal"] = goal
        self._checkpoint()
        self._start_initial_turn(goal_id, output_handoff, artifact_root)
        goal = self._get_goal(thread_id)
        record["goal"] = goal
        self._checkpoint()
        status = goal.get("status")
        if status == "complete":
            self._wait_until_idle(goal_id)
            self._append_handoff(goal_id, output_handoff)
            return
        if status in TERMINAL_GOAL_STATUSES:
            raise SchedulerError(f"{goal_id}: Goal reached stop status {status}")
        if status == "paused":
            self._set_goal_status(goal_id, "active")
        elif status != "active":
            raise SchedulerError(
                f"{goal_id}: unexpected Goal status after initial Turn: {status}"
            )
        self._wait_for_goal_complete(goal_id)
        self._wait_until_idle(goal_id)
        self._append_handoff(goal_id, output_handoff)

    def _pause_current_goal(self) -> None:
        if self.client is None or self.current_goal_id is None:
            return
        goal_id = self.current_goal_id
        record = self._goal_record(goal_id)
        thread_id = record.get("thread_id")
        if not isinstance(thread_id, str):
            return
        try:
            goal = self._get_goal(thread_id)
            if goal.get("status") == "active":
                self._set_goal_status(goal_id, "paused")
        except SchedulerError:
            pass
        try:
            thread = self._get_thread(thread_id, include_turns=True)
            for turn in thread.get("turns", []):
                if (
                    isinstance(turn, dict)
                    and turn.get("status") == "inProgress"
                    and isinstance(turn.get("id"), str)
                ):
                    try:
                        self.client.request(
                            "turn/interrupt",
                            {"threadId": thread_id, "turnId": turn["id"]},
                            timeout=30,
                        )
                    except SchedulerError:
                        pass
        except SchedulerError:
            pass

    def run(self) -> dict[str, Any]:
        try:
            self._initialize_runtime_files()
            if (
                self.resume_context is not None
                and self.resume_context.get("continue_current_goal")
            ):
                self.current_goal_id = self.resume_context["start_goal"]
            self._start_client()
            manifest_goals = list(self.manifest["goals"])
            for goal_id in self.execution_goal_ids:
                index = manifest_goals.index(goal_id)
                if index:
                    predecessor = manifest_goals[index - 1]
                    if self._goal_record(predecessor)["status"] != "complete":
                        raise SchedulerError(
                            f"{goal_id}: predecessor {predecessor} is not complete"
                        )
                self.current_goal_id = goal_id
                self._run_goal(goal_id)
            self.current_goal_id = None
            self.state["current_goal"] = None
            self.state["status"] = "complete"
            self.state["execution_status"] = "complete"
            evidence_summary = derive_workflow05_evidence_summary(self.ledger)
            if any(
                goal_id in WORKFLOW05_GOALS
                for goal_id in self.manifest["goals"]
            ):
                self.state["evidence_summary"] = evidence_summary
                self.state["evidence_status"] = evidence_summary[
                    "evidence_status"
                ]
                self.state["coverage_target_met"] = evidence_summary[
                    "coverage_target_met"
                ]
                self.state["next_authorization_required"] = evidence_summary[
                    "next_authorization_required"
                ]
            self.state["completed_at"] = utc_now()
            self._checkpoint()
            return {
                "status": "complete",
                "execution_status": "complete",
                "evidence_status": self.state.get("evidence_status"),
                "coverage_target_met": self.state.get("coverage_target_met"),
                "next_authorization_required": self.state.get(
                    "next_authorization_required"
                ),
                "branch": self.branch,
                "run_id": self.run_id,
                "run_dir": str(self.run_dir),
                "goals": list(self.execution_goal_ids),
                "ledger": str(self.ledger_path),
                "resumed": self.resume_context is not None,
                "recovery_operation": (
                    self.resume_context.get("mode")
                    if self.resume_context is not None
                    else None
                ),
                "started_from_goal": self.execution_goal_ids[0],
            }
        except BaseException as exc:
            if self.state:
                self._pause_current_goal()
                self.state["status"] = "stopped"
                self.state["execution_status"] = "stopped"
                self.state["last_error"] = str(exc)
                if self.current_goal_id is not None:
                    self.state["current_goal"] = self.current_goal_id
                    record = self._goal_record(self.current_goal_id)
                    if record["status"] != "complete":
                        record["status"] = "stopped"
                        record["error"] = str(exc)
                self._checkpoint()
            raise
        finally:
            if self.client is not None:
                self.client.close()


def dry_run_payload(
    *,
    project_root: Path,
    branch: str,
    manifest_path: Path,
    manifest: dict[str, Any],
    skill_hashes: dict[str, str],
    user_parameters: dict[str, Any],
    upstream_provenance: dict[str, Any] | None,
    upstream_was_supplied: bool,
    run_id: str | None,
    model: str | None,
    resume_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    goals: list[dict[str, Any]] = []
    inherited: list[str] = []
    execution_goals = (
        list(resume_context["goal_ids"])
        if resume_context is not None
        else list(manifest["goals"])
    )
    recovery_mode = (
        resume_context.get("mode") if resume_context is not None else None
    )
    attempt_namespace = {
        "replay": "<replay-NNN>",
        "extend": "<extension-NNN>",
    }.get(recovery_mode)
    run_token = run_id or "<run-id>"
    for goal_id in execution_goals:
        index = manifest["goals"].index(goal_id)
        goal_plan = {
                "id": goal_id,
                "skill": manifest["bindings"][goal_id]["skill"],
                "predecessors": inherited + list(manifest["goals"][:index]),
                "persistent_thread": True,
                "ephemeral": False,
                "advance_only_after": "complete",
                "input_sources": [
                    "target_skill",
                    "user_parameters",
                    "cumulative_prior_runtime_handoff_ledger",
                ],
                "runtime_handoff": (
                    f"perf_trace/runtime/{branch}/{run_token}/handoffs/"
                    + (
                        f"{attempt_namespace}/{goal_id}.json"
                        if attempt_namespace is not None
                        else f"{goal_id}.json"
                    )
                ),
                "runtime_artifact_root": (
                    f"perf_trace/runtime/{branch}/{run_token}/artifacts/{goal_id}"
                    + (
                        f"/{attempt_namespace}"
                        if attempt_namespace is not None
                        else ""
                    )
                ),
            }
        continued = (
            resume_context.get("continued_goal")
            if resume_context is not None
            and resume_context.get("continue_current_goal")
            and goal_id == resume_context.get("start_goal")
            else None
        )
        if isinstance(continued, dict):
            artifact_root = continued.get("artifact_root")
            goal_plan["continue_existing_thread"] = not bool(
                continued.get("promote_existing_handoff")
            )
            goal_plan["promote_existing_handoff"] = bool(
                continued.get("promote_existing_handoff")
            )
            goal_plan["persistent_thread_id"] = continued.get("thread_id")
            goal_plan["runtime_artifact_root"] = (
                str(artifact_root.relative_to(project_root))
                if isinstance(artifact_root, Path)
                else str(artifact_root)
            )
            goal_plan["work_repeated"] = False
        goals.append(goal_plan)
    ledger_state: dict[str, Any] = {
        "required_for_execution": False,
        "provided": upstream_was_supplied,
        "validated": upstream_provenance is not None,
    }
    if upstream_provenance is not None:
        ledger_state["provenance"] = upstream_provenance
    payload = {
        "schema_version": 1,
        "status": "dry_run",
        "dry_run": True,
        "app_server_contacted": False,
        "goal_created": False,
        "branch": branch,
        "project_root": str(project_root),
        "manifest": str(manifest_path.relative_to(project_root)),
        "requires": manifest["requires"],
        "model": model,
        "run_id": run_id or "<generated-at-runtime>",
        "runtime_root": str(project_root / "perf_trace" / "runtime" / branch),
        "user_parameters": user_parameters,
        "upstream_ledger": ledger_state,
        "skill_tree_sha256": skill_hashes,
        "goals": goals,
    }
    if resume_context is not None:
        base_state = resume_context["state"]
        evidence_summary = base_state.get("evidence_summary")
        if not isinstance(evidence_summary, dict):
            evidence_summary = derive_workflow05_evidence_summary(
                resume_context["ledger"]
            )
        payload["resume"] = {
            "validated": True,
            "in_place": True,
            "operation": resume_context.get("mode", "resume"),
            "from_goal": resume_context["start_goal"],
            "execution_goals": list(resume_context["goal_ids"]),
            "source_state_sha256": resume_context["state_sha256"],
            "source_ledger_sha256": resume_context["ledger_sha256"],
            "writes_performed": False,
            "continue_current_goal": bool(
                resume_context.get("continue_current_goal")
            ),
            "skill_name_aliases_applied": copy.deepcopy(
                resume_context.get("skill_name_aliases_applied", [])
            ),
            "base_run_state": {
                "status": base_state.get("status"),
                "execution_status": base_state.get("execution_status")
                or base_state.get("status"),
                "evidence_status": evidence_summary.get("evidence_status"),
                "coverage_target_met": evidence_summary.get(
                    "coverage_target_met"
                ),
                "next_authorization_required": evidence_summary.get(
                    "next_authorization_required"
                ),
                "unresolved_binding_count": evidence_summary.get(
                    "unresolved_binding_count"
                ),
            },
        }
        if resume_context.get("mode") == "extend":
            payload["resume"]["extension_parameters"] = copy.deepcopy(
                resume_context.get("extension_parameters")
            )
            payload["resume"]["base_handoff_count"] = len(
                resume_context["ledger"].get("handoffs", [])
            )
            for goal in goals:
                goal["input_sources"].append(
                    "immutable_complete_extension_base_ledger"
                )
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Qwen3.5-27B vLLM/PRA ROCm/DCU/HIP fresh R01-R10 "
            "Goals serially in one lineage."
        )
    )
    default_root = Path(__file__).resolve().parents[2]
    parser.add_argument(
        "--project-root",
        default=str(default_root),
        help="Qwen_DCU_Worker_0 project root.",
    )
    parser.add_argument(
        "--branch",
        required=True,
        choices=list(BRANCHES),
        help="Explicit runtime branch selection.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print the validated serial plan without contacting app-server, "
            "creating a Goal, or writing runtime state."
        ),
    )
    parameter_group = parser.add_mutually_exclusive_group()
    parameter_group.add_argument(
        "--user-parameters",
        default=None,
        help=(
            "Runtime user-parameter overrides as one JSON object. The audited "
            "fresh R01-R10 configuration is applied first."
        ),
    )
    parameter_group.add_argument(
        "--user-parameters-file",
        help=(
            "Path to a JSON object containing runtime user-parameter "
            "overrides; omitted keys retain the audited defaults."
        ),
    )
    run_group = parser.add_mutually_exclusive_group()
    run_group.add_argument(
        "--run-id",
        help="New run directory name under perf_trace/runtime/<branch>.",
    )
    run_group.add_argument(
        "--resume-run-id",
        help=(
            "Existing stopped or complete run id. Use --resume-from for an "
            "incomplete suffix, --replay-from for a non-destructive rerun, "
            "or --extend-from for an authorized evidence delta."
        ),
    )
    recovery_goal_group = parser.add_mutually_exclusive_group()
    recovery_goal_group.add_argument(
        "--resume-from",
        "--start-goal",
        dest="resume_from",
        help=(
            "Resume at this Rxx Goal. It must be the existing run's first "
            "incomplete Goal; omit to select that Goal automatically."
        ),
    )
    recovery_goal_group.add_argument(
        "--replay-from",
        help=(
            "Non-destructively rerun any branch Rxx Goal and every successor from "
            "a stopped or complete run. The predecessor prefix must be "
            "complete; prior state/ledger/handoffs/artifacts are preserved "
            "and new outputs use a replay-NNN namespace."
        ),
    )
    recovery_goal_group.add_argument(
        "--extend-from",
        help=(
            "Start a non-destructive Workflow05 evidence extension at R06-R09. "
            "Use replay for a presentation-only R10 rerun. The complete prior "
            "ledger is frozen as extension-base "
            "evidence, the active serial suffix is rebuilt in an "
            "extension-NNN namespace, and explicit extension parameters are "
            "required."
        ),
    )
    extension_parameter_group = parser.add_mutually_exclusive_group()
    extension_parameter_group.add_argument(
        "--extension-parameters",
        default=None,
        help=(
            "Authorized Workflow05 extension overrides as one JSON object. "
            "A new selection_batch_id and escalation_reason are mandatory."
        ),
    )
    extension_parameter_group.add_argument(
        "--extension-parameters-file",
        help=(
            "Path to the authorized Workflow05 extension JSON object. The "
            "base run parameters remain immutable except for the audited "
            "extension allowlist."
        ),
    )
    parser.add_argument(
        "--codex-bin",
        help="Codex executable path or command name; resolved only for real runs.",
    )
    parser.add_argument(
        "--model",
        help=(
            "Optional Codex model override for every runtime Goal; the "
            "configured default is used when omitted."
        ),
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=2.0,
        help="Goal status polling interval (default: 2).",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=120.0,
        help="App-server request timeout (default: 120).",
    )
    parser.add_argument(
        "--goal-timeout-seconds",
        type=float,
        default=0.0,
        help="Per-Goal timeout; 0 waits without a scheduler deadline.",
    )
    parser.add_argument(
        "--idle-timeout-seconds",
        type=float,
        default=0.0,
        help=(
            "Wait for a complete Goal thread to become idle; 0 waits without "
            "a scheduler deadline."
        ),
    )
    parser.add_argument(
        "--recover-stale-running",
        action="store_true",
        help=(
            "Before a normal resume, convert a proven-orphaned running state "
            "to stopped. Recovery is refused while any scoped scheduler or "
            "profiling process is alive, and immutable state/ledger snapshots "
            "are written under runtime/<branch>/<run-id>/recovery/."
        ),
    )
    parser.add_argument(
        "--continue-current-goal",
        action="store_true",
        help=(
            "With an explicit normal --resume-from, reattach to that stopped "
            "Goal's existing persistent thread and artifact root instead of "
            "starting a new Goal attempt. Validation is fail-closed and this "
            "cannot be combined with replay or evidence extension."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        install_termination_signal_handlers()
        args = parse_args(argv)
        if args.poll_seconds <= 0:
            raise SchedulerError("--poll-seconds must be greater than zero")
        if args.request_timeout_seconds <= 0:
            raise SchedulerError(
                "--request-timeout-seconds must be greater than zero"
            )
        if args.goal_timeout_seconds < 0:
            raise SchedulerError(
                "--goal-timeout-seconds must be zero or greater"
            )
        if args.idle_timeout_seconds < 0:
            raise SchedulerError(
                "--idle-timeout-seconds must be zero or greater"
            )
        if (
            args.resume_from or args.replay_from or args.extend_from
        ) and not args.resume_run_id:
            raise SchedulerError(
                "--resume-from/--replay-from/--extend-from requires "
                "--resume-run-id"
            )
        if args.recover_stale_running and not args.resume_run_id:
            raise SchedulerError(
                "--recover-stale-running requires --resume-run-id"
            )
        if args.recover_stale_running and args.dry_run:
            raise SchedulerError(
                "--recover-stale-running performs an audited state repair and "
                "therefore cannot be combined with --dry-run"
            )
        if args.recover_stale_running and (
            args.replay_from or args.extend_from
        ):
            raise SchedulerError(
                "--recover-stale-running is valid only for a normal resume, "
                "not replay or evidence extension"
            )
        if args.continue_current_goal and not args.resume_run_id:
            raise SchedulerError(
                "--continue-current-goal requires --resume-run-id"
            )
        if args.continue_current_goal and not args.resume_from:
            raise SchedulerError(
                "--continue-current-goal requires an explicit --resume-from Goal"
            )
        if args.continue_current_goal and (
            args.replay_from or args.extend_from
        ):
            raise SchedulerError(
                "--continue-current-goal is valid only for a normal resume"
            )
        if args.continue_current_goal and args.recover_stale_running:
            raise SchedulerError(
                "--continue-current-goal cannot be combined with "
                "--recover-stale-running"
            )
        extension_parameters_supplied = (
            args.extension_parameters is not None
            or args.extension_parameters_file is not None
        )
        if args.extend_from and not extension_parameters_supplied:
            raise SchedulerError(
                "--extend-from requires --extension-parameters or "
                "--extension-parameters-file"
            )
        if extension_parameters_supplied and not args.extend_from:
            raise SchedulerError(
                "extension parameters are accepted only with --extend-from"
            )
        if args.resume_run_id and (
            args.user_parameters is not None or args.user_parameters_file
        ):
            raise SchedulerError(
                "user-parameter overrides are not accepted during resume; "
                "the existing run's canonical parameters are reused"
            )
        project_root = Path(args.project_root).expanduser().resolve()
        manifest_path, manifest, skill_hashes = validate_runtime_inputs(
            project_root,
            args.branch,
        )
        upstream_ledger: dict[str, Any] | None = None
        upstream_provenance: dict[str, Any] | None = None
        resume_context: dict[str, Any] | None = None
        if args.resume_run_id:
            extension_parameters = (
                parse_user_parameters(
                    args.extension_parameters or "{}",
                    args.extension_parameters_file,
                )
                if args.extend_from
                else None
            )
            if args.recover_stale_running:
                recover_stale_running_state(
                    project_root=project_root,
                    branch=args.branch,
                    manifest_path=manifest_path,
                    manifest=manifest,
                    run_id=args.resume_run_id,
                    requested_goal=args.resume_from,
                )
            resume_context = load_resume_context(
                project_root=project_root,
                branch=args.branch,
                manifest_path=manifest_path,
                manifest=manifest,
                run_id=args.resume_run_id,
                requested_goal=(
                    args.extend_from or args.replay_from or args.resume_from
                ),
                replay=args.replay_from is not None,
                extend=args.extend_from is not None,
                continue_current_goal=args.continue_current_goal,
                extension_parameters=extension_parameters,
            )
            user_parameters = resume_context["user_parameters"]
            upstream_provenance = resume_context["upstream_provenance"]
            run_id = args.resume_run_id
        else:
            supplied_user_parameters = parse_user_parameters(
                args.user_parameters or "{}",
                args.user_parameters_file,
            )
            user_parameters = resolve_user_parameters(
                project_root,
                supplied_user_parameters,
            )
            run_id = args.run_id or default_run_id()
        validate_branch_user_parameters(args.branch, user_parameters)
        if args.dry_run:
            print(
                json.dumps(
                    dry_run_payload(
                        project_root=project_root,
                        branch=args.branch,
                        manifest_path=manifest_path,
                        manifest=manifest,
                        skill_hashes=skill_hashes,
                        user_parameters=user_parameters,
                        upstream_provenance=upstream_provenance,
                        upstream_was_supplied=False,
                        run_id=(run_id if args.resume_run_id else args.run_id),
                        model=args.model,
                        resume_context=resume_context,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        codex_bin = resolve_codex_binary(args.codex_bin)
        scheduler = RuntimeScheduler(
            project_root=project_root,
            branch=args.branch,
            manifest_path=manifest_path,
            manifest=manifest,
            user_parameters=user_parameters,
            upstream_ledger=upstream_ledger,
            upstream_provenance=upstream_provenance,
            codex_bin=codex_bin,
            model=args.model,
            run_id=run_id,
            poll_seconds=args.poll_seconds,
            request_timeout=args.request_timeout_seconds,
            goal_timeout_seconds=args.goal_timeout_seconds,
            idle_timeout_seconds=args.idle_timeout_seconds,
            resume_context=resume_context,
        )
        print(json.dumps(scheduler.run(), ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        print("perf-trace scheduler interrupted", file=sys.stderr)
        return 130
    except SchedulerError as exc:
        print(f"perf-trace scheduler failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
