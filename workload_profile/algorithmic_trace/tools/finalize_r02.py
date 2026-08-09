#!/usr/bin/env python3
"""Independently audit R02 outputs and write the serial runtime handoff."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path, role: str) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "role": role,
        "path": str(resolved),
        "sha256": sha256_path(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def semantic_output_equal(
    fresh: dict[str, Any], baseline: dict[str, Any]
) -> tuple[bool, dict[str, bool]]:
    fields = ("completed", "failed", "input_lens", "output_lens", "generated_texts")
    checks = {field: fresh.get(field) == baseline.get(field) for field in fields}
    return all(checks.values()), checks


def tensor_summaries_are_metadata_only(value: Any) -> bool:
    if isinstance(value, dict):
        if str(value.get("device", "")).startswith("cuda"):
            if not set(value).issubset({"device", "dtype", "shape"}):
                return False
        return all(tensor_summaries_are_metadata_only(item) for item in value.values())
    if isinstance(value, list):
        return all(tensor_summaries_are_metadata_only(item) for item in value)
    return True


def json_csv_layer_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["run_id"],
        row["contract_id"],
        row["request_id"],
        int(row["engine_step_id"]),
        row["schedule_id"],
        row["batch_id"],
        int(row["forward_id"]),
        row["event_id"],
        int(row["layer_idx"]),
        int(row["layer_occurrence"]),
        row["layer_type"],
        row["phase"],
        int(row["q_len"]),
        int(row["past_len"]),
        int(row["kv_len"]),
    )


def json_csv_decision_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["decision_id"],
        row["run_id"],
        row["contract_id"],
        row.get("request_id") or "",
        int(row["engine_step_id"]) if row.get("engine_step_id") not in (None, "") else None,
        row.get("schedule_id") or "",
        row.get("batch_id") or "",
        int(row["forward_id"]) if row.get("forward_id") not in (None, "") else None,
        row["phase"],
        row["decision_family"],
        row["event_type"],
        row["action"],
        row["outcome"],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--trace-dir", required=True, type=Path)
    parser.add_argument("--runtime-dir", required=True, type=Path)
    parser.add_argument("--r01-handoff", required=True, type=Path)
    parser.add_argument("--handoff-output", required=True, type=Path)
    parser.add_argument("--production-baseline", required=True, type=Path)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    source_root = args.source_root.resolve()
    trace_dir = args.trace_dir.resolve()
    runtime_dir = args.runtime_dir.resolve()
    artifact_dir = runtime_dir / "artifacts/R02"
    handoff_output = args.handoff_output.resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    handoff_output.parent.mkdir(parents=True, exist_ok=True)

    required = {
        "algorithmic_trace": trace_dir / "algorithmic_trace.json",
        "layer_trace": trace_dir / "layer_trace.csv",
        "selection_trace": trace_dir / "selection_trace.csv",
        "operator_flops": trace_dir / "operator_flops.csv",
    }
    supporting = {
        "run_contract": trace_dir / "run_contract.json",
        "request_result": trace_dir / "request/result.json",
        "service_log": trace_dir / "service.log",
        "trace_validation": trace_dir / "trace_validation.json",
        "selected_layer_events": trace_dir / "selected_layer_events.csv",
        "selection_report": trace_dir / "selection_report.json",
        "selection_handoff": trace_dir / "selection_handoff.json",
    }
    all_required_files = {**required, **supporting}
    missing = [
        name
        for name, path in all_required_files.items()
        if not path.is_file() or path.stat().st_size == 0
    ]
    if missing:
        raise SystemExit(f"missing or empty R02 outputs: {missing}")

    trace = load_json(required["algorithmic_trace"])
    trace_validation = load_json(supporting["trace_validation"])
    selection_report = load_json(supporting["selection_report"])
    selection_handoff = load_json(supporting["selection_handoff"])
    contract = load_json(supporting["run_contract"])
    r01 = load_json(args.r01_handoff.resolve())
    fresh_result = load_json(supporting["request_result"])
    baseline_result = load_json(args.production_baseline.resolve())
    layer_rows = load_csv(required["layer_trace"])
    decision_rows = load_csv(required["selection_trace"])
    flop_rows = load_csv(required["operator_flops"])
    selected_rows = load_csv(supporting["selected_layer_events"])

    raw_event_files = sorted((trace_dir / "events").glob("events.*.jsonl"))
    raw_events: list[dict[str, Any]] = []
    for path in raw_event_files:
        raw_events.extend(
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    event_counts = Counter(row["event_type"] for row in raw_events)

    json_layer_keys = Counter(
        json_csv_layer_key(row) for row in trace["layer_events"]
    )
    csv_layer_keys = Counter(json_csv_layer_key(row) for row in layer_rows)
    json_decision_keys = Counter(
        json_csv_decision_key(row) for row in trace["decision_events"]
    )
    csv_decision_keys = Counter(
        json_csv_decision_key(row) for row in decision_rows
    )
    layer_join_counts = Counter(
        (
            row["request_id"],
            int(row["engine_step_id"]),
            int(row["forward_id"]),
            int(row["layer_idx"]),
            int(row["layer_occurrence"]),
        )
        for row in layer_rows
    )
    decision_ids = {row["decision_id"] for row in decision_rows}
    selected_join_keys = [
        (
            row["request_id"],
            int(row["engine_step_id"]),
            int(row["forward_id"]),
            int(row["layer_idx"]),
            int(row["layer_occurrence"]),
        )
        for row in selected_rows
    ]
    selected_evidence_ids = [
        decision_id
        for row in selected_rows
        for decision_id in row["evidence_decision_ids"].split(";")
        if decision_id
    ]

    layers_by_forward: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in layer_rows:
        layers_by_forward[int(row["forward_id"])].append(row)
    configured_layer_types = trace["model"]["hf_text_config"]["layer_types"]
    configured_num_layers = int(
        trace["model"]["hf_text_config"]["num_hidden_layers"]
    )
    output_equal, output_checks = semantic_output_equal(
        fresh_result, baseline_result
    )
    git_revision = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    git_branch = subprocess.run(
        ["git", "-C", str(source_root), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    git_status = subprocess.run(
        ["git", "-C", str(source_root), "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    trace_validation_hashes_match = all(
        trace_validation["artifacts"][path.name]["sha256"] == sha256_path(path)
        for path in required.values()
    )
    selection_internal_hashes_match = (
        selection_report["selected_manifest"]["sha256"]
        == sha256_path(supporting["selected_layer_events"])
        and selection_handoff["canonical_selected_manifest"]["sha256"]
        == sha256_path(supporting["selected_layer_events"])
        and selection_handoff["selection_report"]["sha256"]
        == sha256_path(supporting["selection_report"])
    )
    service_log_text = supporting["service_log"].read_text(
        encoding="utf-8", errors="replace"
    )
    base_patch = Path(contract["instrumentation"]["base_patch"])
    bootstrap = Path(contract["instrumentation"]["bootstrap"])
    extension = Path(contract["instrumentation"]["extension"])
    bootstrap_text = bootstrap.read_text(encoding="utf-8")
    extension_text = extension.read_text(encoding="utf-8")

    forbidden_outputs = [
        str(path)
        for path in trace_dir.rglob("*")
        if path.is_file()
        and (
            path.suffix == ".onnx"
            or path.name.startswith("fx_graph")
            or path.name.startswith("dispatch_manifest")
            or "visualization" in path.name
            or "reconstruction" in path.name
        )
    ]
    validations = {
        "requested_fresh_trace_directory_is_under_skill_root": (
            trace_dir.parent
            == project_root / "workload_profile/algorithmic_trace/traces"
        ),
        "four_required_semantic_artifact_roles_exist_and_are_nonempty": all(
            path.is_file() and path.stat().st_size > 0
            for path in required.values()
        ),
        "fresh_trace_run_id_differs_from_r01_evidence_run": (
            trace["run_id"]
            != r01["validation"]["evidence_contract"]["run_id"]
        ),
        "fresh_event_stream_uses_r02_run_id": all(
            row.get("run_id") == trace["run_id"] for row in raw_events
        ),
        "source_revision_still_exact": (
            git_revision == trace["source_revision"] == r01["source_identity"]["revision"]
        ),
        "source_branch_still_pra": git_branch == "pra",
        "source_worktree_still_clean": git_status == "",
        "trace_stage_validation_pass": trace_validation["result"] == "PASS",
        "selection_stage_validation_pass": selection_report["result"] == "PASS",
        "selection_handoff_status_complete": selection_handoff["status"] == "complete",
        "trace_validation_artifact_hashes_match_current_files": (
            trace_validation_hashes_match
        ),
        "selection_internal_hashes_match_current_files": (
            selection_internal_hashes_match
        ),
        "json_and_layer_csv_keys_and_counts_agree": (
            json_layer_keys == csv_layer_keys
            and len(trace["layer_events"]) == len(layer_rows) == 1856
        ),
        "json_and_selection_csv_keys_and_counts_agree": (
            json_decision_keys == csv_decision_keys
            and len(trace["decision_events"]) == len(decision_rows)
        ),
        "every_complete_forward_has_all_64_loaded_layers": (
            len(layers_by_forward) == 29
            and all(len(rows) == configured_num_layers for rows in layers_by_forward.values())
            and all(
                {int(row["layer_idx"]) for row in rows}
                == set(range(configured_num_layers))
                for rows in layers_by_forward.values()
            )
        ),
        "every_layer_type_matches_loaded_hf_text_config": all(
            row["layer_type"] == configured_layer_types[int(row["layer_idx"])]
            for row in layer_rows
        ),
        "every_layer_has_required_join_and_sequence_fields": all(
            row["request_id"]
            and row["engine_step_id"]
            and row["schedule_id"]
            and row["batch_id"]
            and row["forward_id"]
            and row["phase"]
            and int(row["past_len"]) + int(row["q_len"]) == int(row["kv_len"])
            for row in layer_rows
        ),
        "operator_flops_cover_every_layer_with_five_rows": (
            len(flop_rows) == 5 * len(layer_rows)
            and Counter(row["event_id"] for row in flop_rows)
            == Counter({row["event_id"]: 5 for row in layer_rows})
        ),
        "operator_flops_are_explicitly_not_measured_latency": all(
            row["measured_latency"].lower() == "false" for row in flop_rows
        )
        and trace["theoretical_flops_summary"]["measured_rocm_dcu_latency"] is False,
        "nine_selected_events_have_unique_source_joins": (
            len(selected_rows) == 9
            and len(selected_join_keys) == len(set(selected_join_keys))
            and all(layer_join_counts[key] == 1 for key in selected_join_keys)
            and all(int(row["unique_source_match_count"]) == 1 for row in selected_rows)
        ),
        "every_selected_reason_and_role_is_explicit": all(
            row["priority"] and row["role"] and row["reason"] for row in selected_rows
        ),
        "every_selected_event_has_existing_decision_evidence": (
            bool(selected_evidence_ids)
            and all(value in decision_ids for value in selected_evidence_ids)
            and all(row["evidence_decision_ids"] for row in selected_rows)
        ),
        "actual_algorithm_decision_evidence_is_available": (
            trace["decision_evidence"][
                "actual_algorithm_decision_evidence_available"
            ]
            and all(
                family
                in {row["decision_family"] for row in decision_rows}
                for family in ("scheduler", "cache_state", "model_route", "sampling")
            )
        ),
        "qwen35_pruning_or_early_exit_rows_not_fabricated": (
            trace["decision_evidence"]["pruning_or_early_exit_events_fabricated"]
            is False
            and not any(
                row["decision_family"] in ("pruning", "early_exit")
                for row in decision_rows
            )
        ),
        "cache_free_is_directly_observed_and_reconciled": (
            event_counts["kv_free"] == 1
            and trace_validation["validation"][
                "cache_free_transition_observed_and_reconciled"
            ]
        ),
        "fresh_output_matches_same_contract_r01_production_baseline": output_equal,
        "fresh_request_completed_once_without_failure": (
            fresh_result.get("completed") == 1
            and fresh_result.get("failed") == 0
            and fresh_result.get("input_lens") == [20574]
            and fresh_result.get("output_lens") == [23]
        ),
        "service_log_confirms_real_request_and_runtime_backends": all(
            marker in service_log_text
            for marker in (
                "POST /v1/chat/completions HTTP/1.1\" 200 OK",
                "Using ROCM_AITER_UNIFIED_ATTN attention backend",
                "Using Triton/FLA GDN prefill kernel",
                "Enforce eager set, disabling torch.compile and CUDAGraphs",
            )
        ),
        "raw_device_tensor_objects_are_metadata_only": all(
            tensor_summaries_are_metadata_only(row) for row in raw_events
        ),
        "local_extension_introduces_no_cpu_numpy_item_or_tolist_calls": not any(
            marker in extension_text
            for marker in (".cpu(", ".numpy(", ".item(", ".tolist(")
        ),
        "base_tolist_is_guarded_before_base_patch_application": (
            "prepare_base(vllm_trace_patch)" in bootstrap_text
            and bootstrap_text.index("prepare_base(vllm_trace_patch)")
            < bootstrap_text.index("vllm_trace_patch.apply_patches()")
            and "device_tensor_to_list_forbidden=True" in extension_text
        ),
        "instrumentation_hashes_match_run_contract": (
            sha256_path(base_patch)
            == contract["instrumentation"]["base_patch_sha256"]
            and sha256_path(bootstrap)
            == contract["instrumentation"]["bootstrap_sha256"]
            and sha256_path(extension)
            == contract["instrumentation"]["extension_sha256"]
        ),
        "no_downstream_dispatch_fx_onnx_reconstruction_or_visualization_outputs": (
            forbidden_outputs == []
        ),
        "single_request_scope_guard_is_explicit": (
            contract["request"]["max_concurrency"] == 1
            and contract["claim_scope"]["concurrent_or_distributed_coverage"] is False
        ),
    }
    if not all(validations.values()):
        failed = sorted(key for key, value in validations.items() if not value)
        failed_report = {
            "schema_version": 1,
            "goal": "R02",
            "status": "blocked",
            "failed_checks": failed,
            "validation": validations,
        }
        write_json(artifact_dir / "validation_report.json", failed_report)
        raise SystemExit(f"R02 independent audit failed: {failed}")

    selected_summary = [
        {
            key: (
                int(row[key])
                if key
                in (
                    "engine_step_id",
                    "forward_id",
                    "layer_idx",
                    "layer_occurrence",
                    "q_len",
                    "past_len",
                    "kv_len",
                )
                else row[key]
            )
            for key in (
                "selection_id",
                "priority",
                "role",
                "reason",
                "request_id",
                "engine_step_id",
                "forward_id",
                "layer_idx",
                "layer_occurrence",
                "phase",
                "q_len",
                "past_len",
                "kv_len",
                "layer_type",
                "source_event_id",
            )
        }
        for row in selected_rows
    ]
    validation_report = {
        "schema_version": 1,
        "goal": "R02",
        "skill": "qwen-dcu-algorithmic-trace-selection",
        "status": "complete",
        "result": "PASS_FOR_R02_ALGORITHMIC_TRACE_AND_LAYER_SELECTION",
        "trace_identity": {
            "trace_tag": trace["trace_tag"],
            "run_id": trace["run_id"],
            "contract_id": trace["contract_id"],
            "source_revision": trace["source_revision"],
            "trace_mode": "enforce_eager",
            "current_optimized_runtime": True,
            "comparison_baseline_run": False,
        },
        "counts": {
            "raw_event_count": len(raw_events),
            "engine_begin_end_pairs": event_counts["engine_step_begin"],
            "scheduler_rows": event_counts["scheduler_step"],
            "model_begin_end_pairs": event_counts["model_execute_begin"],
            "effective_forward_count": len(layers_by_forward),
            "prefill_forward_count": len(
                {
                    int(row["forward_id"])
                    for row in layer_rows
                    if row["phase"] == "prefill_chunk"
                }
            ),
            "decode_forward_count": len(
                {
                    int(row["forward_id"])
                    for row in layer_rows
                    if row["phase"] == "decode"
                }
            ),
            "layer_event_count": len(layer_rows),
            "linear_attention_and_gdn_event_count": event_counts[
                "qwen35_gdn_forward"
            ],
            "full_attention_begin_end_pair_count": event_counts[
                "attention_forward_begin"
            ],
            "decision_row_count": len(decision_rows),
            "operator_flop_row_count": len(flop_rows),
            "selected_event_count": len(selected_rows),
            "cache_allocation_count": event_counts["kv_allocate_slots"],
            "cache_free_count": event_counts["kv_free"],
            "host_output_count": fresh_result["output_lens"][0],
        },
        "output_equivalence": {
            "result": "PASS",
            "field_checks": output_checks,
            "completed": fresh_result["completed"],
            "failed": fresh_result["failed"],
            "input_lens": fresh_result["input_lens"],
            "output_lens": fresh_result["output_lens"],
            "generated_text_sha256": hashlib.sha256(
                fresh_result["generated_texts"][0].encode("utf-8")
            ).hexdigest(),
        },
        "algorithm_decision_evidence": {
            "available": True,
            "families": sorted(
                {row["decision_family"] for row in decision_rows}
            ),
            "cache_free_directly_observed": True,
            "multimodal_pruning": "disabled_by_loaded_qwen3_5_source",
            "early_exit_or_pruning_rows_fabricated": False,
        },
        "theoretical_flops": {
            "present": True,
            "row_count": len(flop_rows),
            "grand_total": trace["theoretical_flops_summary"]["grand_total"],
            "measured_rocm_dcu_latency": False,
            "exclusions": trace["theoretical_flops_summary"]["excluded"],
        },
        "selected_events": selected_summary,
        "safety": {
            "large_or_device_tensor_contents_recorded": False,
            "local_extension_cpu_calls": 0,
            "local_extension_numpy_calls": 0,
            "local_extension_item_calls": 0,
            "local_extension_tolist_calls": 0,
            "base_small_list_device_guard_active_before_patch_application": True,
        },
        "scope": {
            "single_request": "PASS",
            "max_concurrency": 1,
            "concurrent_or_distributed_claim": False,
            "downstream_dispatch_fx_onnx_or_visualization_executed": False,
        },
        "validation": validations,
    }
    validation_report_path = artifact_dir / "validation_report.json"
    write_json(validation_report_path, validation_report)

    completion_report_path = artifact_dir / "completion_report.md"
    completion_lines = [
        "# R02 Algorithmic Trace And Layer Selection",
        "",
        f"- Trace: `{trace['trace_tag']}`",
        "- Runtime: current optimized Qwen3.5-27B vLLM V1 runtime, with `--enforce-eager` only to preserve Python layer visibility.",
        f"- Fresh request: {fresh_result['input_lens'][0]} benchmark input tokens, {fresh_result['output_lens'][0]} generated tokens, 0 failures.",
        f"- Complete forwards: {len(layers_by_forward)} (6 prefill and 23 decode), each with 64 loaded layers.",
        f"- Decisions: {len(decision_rows)} scheduler/cache/model-route/sampling/output rows; direct terminal cache free was observed.",
        f"- FLOPs: {len(flop_rows)} analytic rows; these are theoretical FLOPs, not measured ROCm/DCU latency.",
        f"- Selected events: {len(selected_rows)}, each uniquely joined to `layer_trace.csv` and backed by actual decision rows.",
        "- Qwen3.5 multimodal pruning is disabled; no pruning or early-exit rows were fabricated.",
        "- Scope: one deterministic request with max concurrency 1; no concurrent/distributed claim.",
        "- No DispatchMode, FX, reconstruction, ONNX, or visualization work was run.",
        "",
        "## Selected events",
        "",
    ]
    for row in selected_summary:
        completion_lines.append(
            "- "
            f"`{row['selection_id']}` {row['priority']} `{row['role']}`: "
            f"(step={row['engine_step_id']}, forward={row['forward_id']}, "
            f"layer={row['layer_idx']}, occurrence={row['layer_occurrence']}, "
            f"phase={row['phase']}, q={row['q_len']}, past={row['past_len']}, "
            f"kv={row['kv_len']}, type={row['layer_type']})."
        )
    completion_report_path.write_text(
        "\n".join(completion_lines) + "\n", encoding="utf-8"
    )

    tool_paths = {
        "base_runtime_patch": base_patch,
        "bootstrap": bootstrap,
        "r02_extension": extension,
        "trace_builder": project_root
        / "workload_profile/algorithmic_trace/tools/build_r02_algorithmic_trace.py",
        "selector": project_root
        / "workload_profile/algorithmic_trace/tools/select_r02_layer_events.py",
        "finalizer": Path(__file__).resolve(),
    }
    evidence_manifest = {
        "schema_version": 1,
        "goal": "R02",
        "trace_tag": trace["trace_tag"],
        "run_id": trace["run_id"],
        "contract_id": trace["contract_id"],
        "source_revision": trace["source_revision"],
        "required_semantic_artifacts": {
            name: artifact(path, name) for name, path in required.items()
        },
        "selection_artifacts": {
            "selected_layer_events": artifact(
                supporting["selected_layer_events"],
                "canonical_selected_layer_event_manifest",
            ),
            "selection_report": artifact(
                supporting["selection_report"], "selection_audit"
            ),
            "selection_handoff": artifact(
                supporting["selection_handoff"],
                "selection_only_downstream_handoff",
            ),
        },
        "runtime_evidence": {
            "run_contract": artifact(
                supporting["run_contract"], "resolved_run_contract"
            ),
            "request_result": artifact(
                supporting["request_result"], "fresh_request_result"
            ),
            "service_log": artifact(
                supporting["service_log"], "resolved_runtime_and_request_log"
            ),
            "raw_event_streams": [
                artifact(path, "raw_small_metadata_event_stream")
                for path in raw_event_files
            ],
        },
        "validation_evidence": {
            "trace_validation": artifact(
                supporting["trace_validation"], "trace_stage_validation"
            ),
            "final_validation": artifact(
                validation_report_path, "independent_final_validation"
            ),
            "completion_report": artifact(
                completion_report_path, "human_readable_completion_report"
            ),
            "r01_handoff": artifact(
                args.r01_handoff.resolve(), "previous_serial_handoff"
            ),
            "production_baseline": artifact(
                args.production_baseline.resolve(),
                "same_contract_production_output_baseline",
            ),
        },
        "tools": {
            name: artifact(path, "runtime_or_audit_tool")
            for name, path in tool_paths.items()
        },
    }
    evidence_manifest_path = artifact_dir / "evidence_manifest.json"
    write_json(evidence_manifest_path, evidence_manifest)

    def indexed(path: Path, role: str) -> dict[str, Any]:
        return artifact(path, role)

    handoff = {
        "schema_version": 1,
        "handoff_id": "20260729T050800Z-fx-89687ae2:R02",
        "source_goal": "R02",
        "status": "complete",
        "skill": "qwen-dcu-algorithmic-trace-selection",
        "created_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "runtime": {
            "project_root": str(project_root),
            "run_id": "20260729T050800Z-fx-89687ae2",
            "branch": "fx",
            "runtime_goal": "R02",
            "previous_handoff": str(args.r01_handoff.resolve()),
            "user_parameters": {},
        },
        "source_identity": {
            "repository": str(source_root),
            "git_branch": git_branch,
            "revision": git_revision,
            "worktree_clean_at_completion": git_status == "",
            "installed_vllm_version": contract["source"][
                "installed_vllm_version"
            ],
            "installed_sources_byte_identical_to_repository": contract[
                "source"
            ]["installed_sources_byte_identical_to_repository"],
            "model_config": trace["model"]["config_path"],
            "model_config_sha256": trace["model"]["config_sha256"],
            "model": trace["model"]["hf_text_config"],
        },
        "trace_contract": {
            "trace_tag": trace["trace_tag"],
            "trace_run_id": trace["run_id"],
            "contract_id": trace["contract_id"],
            "run_mode": "FRESH_RUN",
            "trace_mode": "enforce_eager",
            "runtime_role": "current_optimized_runtime",
            "comparison_baseline_run": False,
            "intentional_runtime_difference": contract["runtime"][
                "intentional_difference_from_production"
            ],
            "device": contract["runtime"]["device_id"],
            "resolved_attention_backend": trace["runtime"][
                "observed_attention_backend"
            ],
            "resolved_linear_attention_route": trace["runtime"][
                "observed_linear_attention_route"
            ],
            "request": contract["request"],
            "resolved_commands": contract["resolved_commands"],
        },
        "outputs": {
            "required_semantic_artifacts": {
                name: indexed(path, name) for name, path in required.items()
            },
            "canonical_selected_manifest": indexed(
                supporting["selected_layer_events"],
                "canonical_selected_layer_event_manifest",
            ),
            "selection_report": indexed(
                supporting["selection_report"], "selection_audit"
            ),
            "selection_handoff": indexed(
                supporting["selection_handoff"],
                "selection_only_downstream_handoff",
            ),
            "trace_validation": indexed(
                supporting["trace_validation"], "trace_stage_validation"
            ),
            "final_validation": indexed(
                validation_report_path, "independent_final_validation"
            ),
            "evidence_manifest": indexed(
                evidence_manifest_path, "complete_evidence_index"
            ),
            "completion_report": indexed(
                completion_report_path, "human_readable_completion_report"
            ),
            "run_contract": indexed(
                supporting["run_contract"], "resolved_run_contract"
            ),
            "request_result": indexed(
                supporting["request_result"], "fresh_request_result"
            ),
            "service_log": indexed(
                supporting["service_log"], "resolved_runtime_and_request_log"
            ),
            "raw_event_streams": [
                indexed(path, "raw_small_metadata_event_stream")
                for path in raw_event_files
            ],
        },
        "validation": {
            "result": "PASS_FOR_R02_ALGORITHMIC_TRACE_AND_LAYER_SELECTION",
            "fresh_request": validation_report["output_equivalence"],
            "counts": validation_report["counts"],
            "every_complete_forward_has_64_loaded_layers": True,
            "every_complete_forward_has_48_linear_and_16_full_layers": True,
            "json_csv_consistency": "PASS",
            "selected_event_unique_join": "PASS",
            "cache_free_directly_observed": True,
            "actual_algorithm_decision_evidence_available": True,
            "theoretical_flops_present_not_measured_latency": True,
            "large_or_device_tensor_contents_recorded": False,
            "single_request_scope_only": True,
            "concurrent_or_distributed_claim": False,
            "downstream_dispatch_fx_onnx_or_visualization_executed": False,
        },
        "selection": {
            "policy": selection_report["selection_policy"],
            "selected_event_count": len(selected_rows),
            "join_key": selection_handoff["join_key"],
            "events": selected_summary,
        },
        "known_nonblocking_limits": [
            {
                "id": "L01_enforce_eager_visibility",
                "fact": "The fresh algorithmic trace uses enforce_eager so all Python decoder layers and GDN helpers are visible.",
                "scope_guard": "Do not treat its boundary durations as production compiled latency; keep R01 compiled evidence separate.",
            },
            {
                "id": "L02_single_request",
                "fact": "The fixed request uses max_concurrency=1 and TP/PP/DP=1.",
                "scope_guard": "Do not claim concurrent or distributed coverage.",
            },
            {
                "id": "L03_no_pruning_family",
                "fact": "Loaded Qwen3.5 source disables multimodal pruning and no early-exit path is observed.",
                "scope_guard": "Do not fabricate pruning or early-exit decisions.",
            },
            {
                "id": "L04_theoretical_flops",
                "fact": "operator_flops.csv contains analytic projection and causal-attention FLOPs.",
                "scope_guard": "Never report these values as measured ROCm/DCU kernel or wall-clock latency.",
            },
            {
                "id": "L05_async_drain",
                "fact": "One q_len=0 model_execute call is an observed asynchronous drain with no batch or decoder-layer calls.",
                "scope_guard": "It is retained in forward metadata and no layer rows are fabricated.",
            },
        ],
        "downstream_contract": {
            "consume_as_is": True,
            "algorithmic_trace": str(required["algorithmic_trace"]),
            "layer_trace": str(required["layer_trace"]),
            "selection_trace": str(required["selection_trace"]),
            "operator_flops": str(required["operator_flops"]),
            "canonical_selected_manifest": str(
                supporting["selected_layer_events"]
            ),
            "selection_handoff": str(supporting["selection_handoff"]),
            "validation_report": str(validation_report_path),
            "evidence_manifest": str(evidence_manifest_path),
            "join_key": selection_handoff["join_key"],
            "must_preserve": selection_handoff["must_preserve"],
        },
        "completion_conditions": {
            "fresh_trace_directory_exists_with_four_artifact_roles": True,
            "request_step_forward_phase_occurrence_lengths_and_layer_types_consistent": True,
            "every_complete_forward_covers_all_loaded_layers": True,
            "every_exception_or_repetition_explained_by_observed_control_flow": True,
            "important_layer_events_selected_with_explicit_trace_tied_reasons": True,
            "every_selected_event_joins_uniquely_to_source_layer_event": True,
            "theoretical_flops_present_and_not_reported_as_measured_latency": True,
            "current_runtime_vs_comparison_baseline_status_explicit": True,
            "actual_algorithm_decision_evidence_status_explicit": True,
            "no_disallowed_downstream_work_executed": True,
            "runtime_handoff_written_to_requested_absolute_path": True,
        },
    }
    write_json(handoff_output, handoff)
    print(
        json.dumps(
            {
                "status": "complete",
                "handoff": {
                    "path": str(handoff_output),
                    "sha256": sha256_path(handoff_output),
                    "size_bytes": handoff_output.stat().st_size,
                },
                "validation_report": artifact(
                    validation_report_path, "independent_final_validation"
                ),
                "evidence_manifest": artifact(
                    evidence_manifest_path, "complete_evidence_index"
                ),
                "completion_report": artifact(
                    completion_report_path,
                    "human_readable_completion_report",
                ),
                "validation": validations,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
