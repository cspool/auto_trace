#!/usr/bin/env python3
"""Index validated R032 evidence and write the requested serial handoff."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def file_record(path: Path, role: str) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise RuntimeError(f"required evidence file missing: {resolved}")
    return {
        "path": str(resolved),
        "role": role,
        "sha256": sha256_file(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def directory_record(path: Path, role: str) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_dir():
        raise RuntimeError(f"required evidence directory missing: {resolved}")
    files = sorted(item for item in resolved.rglob("*") if item.is_file())
    digest = hashlib.sha256()
    for item in files:
        relative = item.relative_to(resolved).as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(sha256_file(item).encode())
        digest.update(b"\n")
    return {
        "path": str(resolved),
        "role": role,
        "file_count": len(files),
        "tree_sha256": digest.hexdigest(),
    }


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--pipeline-run-id", required=True)
    parser.add_argument("--fx-root", required=True, type=Path)
    parser.add_argument("--r02-handoff", required=True, type=Path)
    parser.add_argument("--validation", required=True, type=Path)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--runtime-patch", required=True, type=Path)
    parser.add_argument("--sitecustomize", required=True, type=Path)
    parser.add_argument("--service-entry", required=True, type=Path)
    parser.add_argument("--request-runner", required=True, type=Path)
    parser.add_argument("--validator", required=True, type=Path)
    parser.add_argument("--service-log", required=True, type=Path)
    parser.add_argument("--handoff-output", required=True, type=Path)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    fx_root = args.fx_root.resolve()
    r02_handoff_path = args.r02_handoff.resolve()
    validation_path = args.validation.resolve()
    artifact_dir = args.artifact_dir.resolve()
    handoff_output = args.handoff_output.resolve()
    runtime_patch = args.runtime_patch.resolve()
    sitecustomize = args.sitecustomize.resolve()
    service_entry = args.service_entry.resolve()
    request_runner = args.request_runner.resolve()
    validator = args.validator.resolve()
    service_log = args.service_log.resolve()

    validation = load_json(validation_path)
    if validation.get("result") != "PASS":
        raise RuntimeError("R032 validation must PASS before finalization")
    if not all(validation.get("validations", {}).values()):
        raise RuntimeError("one or more R032 completion validations are false")
    r02 = load_json(r02_handoff_path)
    if r02.get("status") != "complete":
        raise RuntimeError("R02 handoff is not complete")
    metadata = load_json(fx_root / "run_metadata.json")
    manifest = load_csv(fx_root / "fx_layer_trace_manifest.csv")
    layers = load_csv(fx_root / "fx_layer_events.csv")
    selected_rows = load_csv(
        Path(r02["downstream_contract"]["canonical_selected_manifest"])
    )
    if (
        metadata.get("status") != "complete"
        or metadata.get("fx_sample_count") != 9
        or metadata.get("fx_trace_count") != 9
        or metadata.get("fx_trace_error_count") != 0
        or len(manifest) != 9
        or len(layers) != 1856
        or any(row.get("status") != "ok" for row in manifest)
    ):
        raise RuntimeError("R032 run metadata/manifests are not complete")

    artifact_dir.mkdir(parents=True, exist_ok=True)
    source_request_ids = sorted({row["request_id"] for row in selected_rows})
    observed_request_ids = sorted({row["request_id"] for row in manifest})
    source_trace_run_ids = sorted({row["run_id"] for row in selected_rows})
    observed_stage_trace_run_ids = sorted({row["run_id"] for row in manifest})
    if (
        len(source_request_ids) != 1
        or len(observed_request_ids) != 1
        or source_trace_run_ids != [f"{args.pipeline_run_id}-R02"]
        or observed_stage_trace_run_ids != [f"{args.pipeline_run_id}-R032"]
    ):
        raise RuntimeError(
            "R032 source-to-stage event identity is not one source run/request "
            "ID to one observed stage run/request ID"
        )
    source_request_id = source_request_ids[0]
    observed_request_id = observed_request_ids[0]
    source_trace_run_id = source_trace_run_ids[0]
    observed_stage_trace_run_id = observed_stage_trace_run_ids[0]
    if (
        metadata.get("run_id") != observed_stage_trace_run_id
        or any(
            row["source_run_id"] != source_trace_run_id for row in manifest
        )
    ):
        raise RuntimeError(
            "R032 manifest does not preserve its source and stage trace-run "
            "identities"
        )
    request_id_match = re.fullmatch(
        rf"{re.escape(source_request_id)}-([0-9a-f]{{8}})",
        observed_request_id,
    )
    if request_id_match is None:
        raise RuntimeError(
            "R032 observed request ID is not the source ID plus the expected "
            "vLLM V1 8-hex instance suffix"
        )
    input_processor_path = (
        Path(r02["source_identity"]["repository"])
        / "vllm"
        / "v1"
        / "engine"
        / "input_processor.py"
    ).resolve()
    source_event_identity_mapping = {
        "schema_version": 1,
        "runtime_goal": "R032",
        "mapping_type": "r02_source_event_to_r032_fresh_runtime_event",
        "logical_pipeline_run_id": args.pipeline_run_id,
        "source_r02_trace_run_id": source_trace_run_id,
        "observed_r032_trace_run_id": observed_stage_trace_run_id,
        "source_external_request_id": source_request_id,
        "observed_internal_request_id": observed_request_id,
        "internal_random_suffix": request_id_match.group(1),
        "relation": (
            "observed_internal_request_id = source_external_request_id + "
            "'-' + 8 lowercase hex characters"
        ),
        "mechanism": (
            "vLLM V1 InputProcessor.assign_request_id preserves the external "
            "ID in external_req_id and randomizes the internal scheduler ID"
        ),
        "mechanism_source": file_record(
            input_processor_path,
            "vllm_v1_request_id_randomization_source",
        ),
        "selected_event_count": len(manifest),
        "ordered_selection_ids": [row["selection_id"] for row in manifest],
        "ordered_source_event_ids": [
            row["source_event_id"] for row in manifest
        ],
        "ordered_fx_event_ids": [row["event_id"] for row in manifest],
        "bijective_for_this_single_request": True,
        "scope_guard": (
            "Join R032 to R02 through source_event_id, source_run_id, and this "
            "explicit single-request identity mapping; never rewrite the R032 "
            "stage trace-run ID or observed internal scheduler request ID as "
            "if either were the R02 source identity."
        ),
    }
    source_event_identity_mapping_path = (
        artifact_dir / "source_event_identity_mapping.json"
    )
    write_json_atomic(
        source_event_identity_mapping_path,
        source_event_identity_mapping,
    )
    run_level = {
        "run_metadata": file_record(
            fx_root / "run_metadata.json", "resolved_runtime_and_fx_metadata"
        ),
        "fx_layer_events": file_record(
            fx_root / "fx_layer_events.csv", "full_observed_decoder_layer_event_log"
        ),
        "fx_layer_trace_manifest": file_record(
            fx_root / "fx_layer_trace_manifest.csv",
            "canonical_selected_event_fx_status_manifest",
        ),
        "request_result": file_record(
            fx_root / "request" / "result.json",
            "fresh_eager_request_result_and_output_equivalence",
        ),
        "request_contract": file_record(
            fx_root / "request" / "request_contract.json",
            "resolved_external_request_contract",
        ),
        "source_event_identity_mapping": file_record(
            source_event_identity_mapping_path,
            "r02_source_to_r032_stage_event_identity_mapping",
        ),
        "finalize_done": file_record(
            fx_root / "FINALIZE_DONE.json",
            "worker_post_request_finalize_completion",
        ),
        "validation": file_record(
            validation_path, "independent_r032_completion_validation"
        ),
        "service_log": file_record(
            service_log, "current_runtime_service_and_offline_replay_log"
        ),
    }
    event_artifacts: list[dict[str, Any]] = []
    for row in manifest:
        event_id = row["event_id"]
        event_dir = fx_root / event_id
        event_artifacts.append(
            {
                "event_id": event_id,
                "selection_id": row["selection_id"],
                "source_event_id": row["source_event_id"],
                "layer_type": row["layer_type"],
                "node_count": int(row["node_count"]),
                "trace_dir": directory_record(
                    event_dir, "fixed_input_fx_event_artifact_directory"
                ),
                "fx_graph_py": file_record(
                    event_dir / "fx_graph.py", "generated_fx_python"
                ),
                "fx_graph_txt": file_record(
                    event_dir / "fx_graph.txt", "generated_fx_graph_text"
                ),
                "fx_nodes": file_record(
                    event_dir / "fx_nodes.json", "normalized_fx_node_manifest"
                ),
                "fx_graph_module_pt": file_record(
                    event_dir / "fx_graph_module.pt",
                    "serialized_meta_storage_graph_module",
                ),
                "fx_graph_module_dir": directory_record(
                    event_dir / "fx_graph_module",
                    "exported_fx_graph_module_folder",
                ),
                "fx_trace_metadata": file_record(
                    event_dir / "fx_trace_metadata.json",
                    "per_event_capture_replay_and_boundary_metadata",
                ),
            }
        )
    event_streams = [
        file_record(path, "raw_r032_runtime_or_finalize_event_stream")
        for path in sorted(fx_root.glob("events.*.jsonl"))
    ]
    instrumentation = {
        "runtime_patch": file_record(
            runtime_patch, "r032_current_runtime_sample_then_replay_tracer"
        ),
        "sitecustomize": file_record(
            sitecustomize, "opt_in_runtime_patch_bootstrap"
        ),
        "service_entry": file_record(
            service_entry, "resolved_reproducible_eager_service_entry"
        ),
        "request_runner": file_record(
            request_runner, "source_external_request_id_client"
        ),
        "validator": file_record(
            validator, "independent_r032_validator"
        ),
    }
    source_evidence = {
        "r02_handoff": file_record(
            r02_handoff_path, "upstream_runtime_handoff"
        ),
        "canonical_selected_manifest": file_record(
            Path(r02["downstream_contract"]["canonical_selected_manifest"]),
            "upstream_canonical_selected_events",
        ),
        "selection_handoff": file_record(
            Path(r02["downstream_contract"]["selection_handoff"]),
            "upstream_selection_only_handoff",
        ),
        "algorithmic_trace": file_record(
            Path(r02["downstream_contract"]["algorithmic_trace"]),
            "upstream_algorithmic_trace",
        ),
        "layer_trace": file_record(
            Path(r02["downstream_contract"]["layer_trace"]),
            "upstream_layer_trace",
        ),
        "operator_flops": file_record(
            Path(r02["downstream_contract"]["operator_flops"]),
            "upstream_theoretical_flops_not_latency",
        ),
    }
    evidence_manifest = {
        "schema_version": 1,
        "runtime_goal": "R032",
        "pipeline_run_id": args.pipeline_run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "complete",
        "fx_root": str(fx_root),
        "run_level": run_level,
        "event_artifacts": event_artifacts,
        "raw_event_streams": event_streams,
        "instrumentation": instrumentation,
        "source_evidence": source_evidence,
        "evidence_boundary": metadata["evidence_boundary"],
        "scope_guards": metadata["scope_guards"],
    }
    evidence_manifest_path = artifact_dir / "evidence_manifest.json"
    write_json_atomic(evidence_manifest_path, evidence_manifest)

    node_lines = "\n".join(
        f"- `{item['event_id']}` / `{item['source_event_id']}`: "
        f"{item['layer_type']}, {item['node_count']} nodes"
        for item in event_artifacts
    )
    completion_report = f"""# R032 completion report

R032 completed the selected-layer Qwen3.5-27B FX trace stage for pipeline run
`{args.pipeline_run_id}` on HCU0. A fresh eager vLLM V1 request reproduced the
R02 request output. The client reused the exact R02 external request ID; vLLM
V1 then applied its normal 8-hex internal scheduler-instance suffix. Both IDs
and their verified one-to-one mapping are preserved.

The evidence boundary is strict: nine selected decoder-layer inputs and their
replay-relevant forward-context/cache state were cloned at live layer entry;
the real response came only from the original eager forward. After the request
client returned, the worker observed the finalize marker, reached zero active
model executions, restored both R032 wrappers, and only then ran fixed-input
`make_fx` replay.

Counts:

- 29 effective forwards and 1,856 observed loaded-layer calls
- 9 uniquely sampled selected events
- 9 successful FX traces
- 0 FX trace errors
- 0 patch, capture, serialization, or wrapper-restoration errors

Selected artifacts:

{node_lines}

ROCm/DCU GDN and unified-attention custom operations remain opaque FX nodes.
These graphs do not expose their internal kernels, do not constitute measured
latency, do not prove unobserved branches, and do not extend this single-request
TP/PP/DP=1 evidence to concurrent or distributed execution. No reconstruction
or visualization stage was run. The GraphModule serialization intentionally
uses meta storage instead of duplicating model weights; it is structural FX
evidence, not a directly executable decoder-layer checkpoint.
"""
    completion_report_path = artifact_dir / "completion_report.md"
    write_text_atomic(completion_report_path, completion_report)

    evidence_manifest_record = file_record(
        evidence_manifest_path, "complete_r032_evidence_index"
    )
    completion_report_record = file_record(
        completion_report_path, "human_readable_r032_completion_report"
    )
    validation_record = file_record(
        validation_path, "independent_r032_completion_validation"
    )
    handoff = {
        "schema_version": 1,
        "handoff_id": f"{args.pipeline_run_id}:R032",
        "source_goal": "R032",
        "skill": "qwen-dcu-fx-trace",
        "status": "complete",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "project_root": str(project_root),
            "branch": "fx",
            "run_id": args.pipeline_run_id,
            "runtime_goal": "R032",
            "previous_handoff": str(r02_handoff_path),
            "user_parameters": {},
        },
        "source_identity": metadata["source_identity"],
        "trace_contract": {
            "run_id": metadata["run_id"],
            "contract_id": metadata["contract_id"],
            "trace_mode": "enforce_eager",
            "run_mode": "FRESH_RUN",
            "runtime_role": "current_optimized_runtime_algorithm_structure",
            "device": metadata["device"],
            "trace_strategy": metadata["trace_strategy"],
            "evidence_boundary": metadata["evidence_boundary"],
            "request": load_json(fx_root / "request" / "request_contract.json"),
            "request_result_equivalent_to_r02_eager_source": True,
            "source_event_identity_mapping": source_event_identity_mapping,
            "selected_event_count": 9,
            "observed_layer_event_count": 1856,
            "effective_forward_count": 29,
        },
        "selection": {
            "canonical_selected_manifest": str(
                Path(r02["downstream_contract"]["canonical_selected_manifest"])
            ),
            "ordered_selection_ids": [
                row["selection_id"] for row in selected_rows
            ],
            "ordered_source_event_ids": [
                row["source_event_id"] for row in selected_rows
            ],
            "ordered_fx_event_ids": [row["event_id"] for row in manifest],
            "join_key": r02["selection"]["join_key"],
            "every_event_maps_exactly_once": True,
            "source_event_identity_mapping": {
                "logical_pipeline_run_id": args.pipeline_run_id,
                "source_r02_trace_run_id": source_trace_run_id,
                "observed_r032_trace_run_id": observed_stage_trace_run_id,
                "source_external_request_id": source_request_id,
                "observed_internal_request_id": observed_request_id,
                "mapping_artifact": str(
                    source_event_identity_mapping_path
                ),
                "bijective_for_this_single_request": True,
            },
        },
        "validation": {
            "result": "PASS_FOR_R032_SELECTED_LAYER_FX_TRACE",
            "counts": validation["counts"],
            "node_counts": validation["node_counts"],
            "completion_checks": validation["validations"],
        },
        "completion_conditions": {
            "fresh_real_eager_request_completed": True,
            "real_response_used_only_original_layer_outputs": True,
            "every_requested_event_sampled_once": True,
            "every_selected_event_preserves_selection_id_and_source_event_id": True,
            "all_source_join_and_sequence_fields_except_internal_request_id_match": True,
            "fresh_internal_request_id_difference_is_explicitly_bijective": True,
            "all_29_effective_forwards_cover_all_64_loaded_layers": True,
            "selected_forward_context_and_external_cache_state_cloned_at_entry": True,
            "request_return_precedes_wrapper_restoration_and_offline_fx": True,
            "all_runtime_wrappers_restored_before_offline_replay": True,
            "all_nine_fixed_input_fx_traces_succeeded": True,
            "every_event_has_all_required_fx_artifact_roles": True,
            "run_level_metadata_and_manifests_agree": True,
            "no_fx_trace_error_was_dropped": True,
            "opaque_custom_op_boundary_and_claim_guards_explicit": True,
            "current_runtime_source_and_device_identity_explicit": True,
            "no_disallowed_downstream_work_executed": True,
            "theoretical_flops_not_reported_as_measured_latency": True,
            "runtime_handoff_written_to_requested_absolute_path": True,
        },
        "outputs": {
            "fx_root": directory_record(
                fx_root, "complete_fresh_r032_selected_layer_fx_trace"
            ),
            "run_metadata": run_level["run_metadata"],
            "fx_layer_events": run_level["fx_layer_events"],
            "fx_layer_trace_manifest": run_level["fx_layer_trace_manifest"],
            "request_result": run_level["request_result"],
            "source_event_identity_mapping": run_level[
                "source_event_identity_mapping"
            ],
            "event_artifacts": event_artifacts,
            "raw_event_streams": event_streams,
            "instrumentation": instrumentation,
            "evidence_manifest": evidence_manifest_record,
            "validation_report": validation_record,
            "completion_report": completion_report_record,
        },
        "known_nonblocking_limits": [
            {
                "id": "L01_fixed_input_fx_path",
                "fact": (
                    "Each FX GraphModule represents exactly one cloned fixed-input "
                    "path from a real selected layer call."
                ),
                "scope_guard": (
                    "Do not infer unobserved Python branches or whole-model "
                    "coverage from a selected fixed-input graph."
                ),
            },
            {
                "id": "L02_opaque_custom_ops",
                "fact": (
                    "ROCm/DCU GDN core, KV-cache update, and unified attention "
                    "remain opaque custom-op nodes."
                ),
                "scope_guard": (
                    "Do not claim their internal kernels, ownership, or latency "
                    "from FX evidence."
                ),
            },
            {
                "id": "L03_single_request_rank",
                "fact": "The request used max_concurrency=1 and TP/PP/DP=1 on HCU0.",
                "scope_guard": "Do not claim concurrent or distributed coverage.",
            },
            {
                "id": "L04_enforce_eager_not_compiled_timing",
                "fact": (
                    "R032 used enforce_eager for live Python-layer sampling and "
                    "post-request fixed-input replay."
                ),
                "scope_guard": (
                    "Keep this algorithm-structure evidence separate from R01 "
                    "compiled production timing evidence."
                ),
            },
            {
                "id": "L05_theoretical_flops",
                "fact": "R02 operator_flops.csv contains theoretical FLOPs.",
                "scope_guard": "Never report those values as measured ROCm/DCU latency.",
            },
            {
                "id": "L06_no_pruning_or_early_exit",
                "fact": "No multimodal pruning or early-exit path was observed for Qwen3.5.",
                "scope_guard": "Do not fabricate pruning or early-exit decisions.",
            },
            {
                "id": "L07_internal_request_instance_id",
                "fact": (
                    "The exact R02 external request ID was supplied, while "
                    "vLLM V1 assigned the live scheduler request its normal "
                    "8-hex uniqueness suffix."
                ),
                "scope_guard": (
                    "Preserve both IDs and use "
                    "source_event_identity_mapping.json for the bijective "
                    "R02-to-R032 join."
                ),
            },
            {
                "id": "L08_stage_trace_run_id",
                "fact": (
                    "R02 and R032 use stage-qualified trace-run IDs ending in "
                    "-R02 and -R032 under one logical pipeline run ID."
                ),
                "scope_guard": (
                    "Preserve source_run_id and run_id separately; do not "
                    "rewrite the R032 stage identity as the R02 source identity."
                ),
            },
            {
                "id": "L09_meta_storage_graph_module",
                "fact": (
                    "fx_graph_module.pt and the exported state_dict use meta "
                    "storage so the trace does not duplicate Qwen3.5-27B "
                    "parameter data; HCU device semantics remain in the FX "
                    "nodes."
                ),
                "scope_guard": (
                    "Treat these as structural GraphModule artifacts, not "
                    "runnable layer checkpoints. For portable graph inspection "
                    "consume fx_graph.py, fx_graph.txt, fx_nodes.json, and "
                    "fx_trace_metadata.json; do not claim generic CPU "
                    "torch.load execution was validated."
                ),
            },
        ],
        "downstream_contract": {
            "consume_as_is": True,
            "fx_root": str(fx_root),
            "run_metadata": str(fx_root / "run_metadata.json"),
            "fx_layer_events": str(fx_root / "fx_layer_events.csv"),
            "fx_layer_trace_manifest": str(
                fx_root / "fx_layer_trace_manifest.csv"
            ),
            "canonical_selected_manifest": r02["downstream_contract"][
                "canonical_selected_manifest"
            ],
            "source_algorithmic_trace": r02["downstream_contract"][
                "algorithmic_trace"
            ],
            "selection_handoff": r02["downstream_contract"]["selection_handoff"],
            "source_event_identity_mapping": str(
                source_event_identity_mapping_path
            ),
            "ordered_fx_event_ids": [row["event_id"] for row in manifest],
            "ordered_source_event_ids": [
                row["source_event_id"] for row in manifest
            ],
            "event_trace_dirs": {
                row["source_event_id"]: row["trace_dir"] for row in manifest
            },
            "join_key": r02["selection"]["join_key"],
            "evidence_manifest": str(evidence_manifest_path),
            "validation_report": str(validation_path),
            "must_preserve": [
                "Use exact manifest order, selection IDs, and source event IDs.",
                (
                    "Preserve the observed internal request ID and use the "
                    "explicit external-to-internal request-instance mapping."
                ),
                (
                    "Treat meta-storage GraphModule outputs as structural FX "
                    "evidence, not executable model checkpoints."
                ),
                "Treat every FX graph as one fixed-input path.",
                "Keep GDN and unified-attention custom-op internals opaque.",
                "Do not reinterpret FX nodes or theoretical FLOPs as measured latency.",
                "Do not claim concurrent, distributed, pruning, or early-exit coverage.",
                "Do not rerun or alter R032 evidence before reconstruction unless validation is repeated.",
            ],
        },
    }
    write_json_atomic(handoff_output, handoff)
    print(json.dumps(handoff, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
