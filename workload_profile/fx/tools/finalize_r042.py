#!/usr/bin/env python3
"""Index validated R042 evidence and write the requested serial handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        digest.update(item.relative_to(resolved).as_posix().encode())
        digest.update(b"\0")
        digest.update(sha256_file(item).encode())
        digest.update(b"\n")
    return {
        "path": str(resolved),
        "role": role,
        "file_count": len(files),
        "tree_sha256": digest.hexdigest(),
    }


def check_record(record: dict[str, Any], label: str) -> None:
    path = Path(record["path"]).resolve()
    if not path.is_file():
        raise RuntimeError(f"{label}: missing {path}")
    if sha256_file(path) != record.get("sha256"):
        raise RuntimeError(f"{label}: SHA-256 mismatch")
    if path.stat().st_size != record.get("size_bytes"):
        raise RuntimeError(f"{label}: size mismatch")


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--pipeline-run-id", required=True)
    parser.add_argument("--fx-root", type=Path, required=True)
    parser.add_argument("--r032-handoff", type=Path, required=True)
    parser.add_argument(
        "--pre-reconstruction-r032-validation",
        type=Path,
        required=True,
    )
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--reconstructor", type=Path, required=True)
    parser.add_argument("--validator", type=Path, required=True)
    parser.add_argument("--handoff-output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.handoff_output.is_absolute():
        raise RuntimeError("--handoff-output must be the requested absolute path")

    project_root = args.project_root.resolve()
    fx_root = args.fx_root.resolve()
    r032_handoff_path = args.r032_handoff.resolve()
    prevalidation_input = args.pre_reconstruction_r032_validation.resolve()
    validation_path = args.validation.resolve()
    artifact_dir = args.artifact_dir.resolve()
    reconstructor_path = args.reconstructor.resolve()
    validator_path = args.validator.resolve()
    handoff_output = args.handoff_output.resolve()

    if project_root != Path(
        "/public/home/tangyu408/Qwen_DCU_Worker_0"
    ).resolve():
        raise RuntimeError("unexpected R042 project root")
    if args.branch != "fx":
        raise RuntimeError("unexpected R042 branch")
    if args.pipeline_run_id != "20260729T050800Z-fx-89687ae2":
        raise RuntimeError("unexpected R042 logical pipeline run ID")

    r032 = load_json(r032_handoff_path)
    downstream = r032.get("downstream_contract", {})
    if (
        r032.get("status") != "complete"
        or r032.get("source_goal") != "R032"
        or downstream.get("consume_as_is") is not True
        or r032.get("runtime", {}).get("run_id") != args.pipeline_run_id
        or Path(downstream.get("fx_root", "")).resolve() != fx_root
    ):
        raise RuntimeError("R032 handoff is not complete or does not match R042")

    manifest_json_path = fx_root / "fx_process_reconstruction_manifest.json"
    manifest_csv_path = fx_root / "fx_process_reconstruction_manifest.csv"
    reconstruction_manifest = load_json(manifest_json_path)
    expected_event_ids = list(downstream["ordered_fx_event_ids"])
    expected_source_ids = list(downstream["ordered_source_event_ids"])
    expected_selection_ids = list(
        r032.get("selection", {}).get("ordered_selection_ids", [])
    )
    manifest_results = reconstruction_manifest.get("results", [])
    if (
        reconstruction_manifest.get("runtime_goal") != "R042"
        or reconstruction_manifest.get("logical_pipeline_run_id")
        != args.pipeline_run_id
        or reconstruction_manifest.get("processed") != 9
        or reconstruction_manifest.get("ordered_event_ids")
        != expected_event_ids
        or reconstruction_manifest.get("ordered_source_event_ids")
        != expected_source_ids
        or reconstruction_manifest.get("ordered_selection_ids")
        != expected_selection_ids
        or [item.get("event_id") for item in manifest_results]
        != expected_event_ids
        or not all(
            reconstruction_manifest.get("completion_checks", {}).values()
        )
    ):
        raise RuntimeError("R042 reconstruction manifest contract failed")
    check_record(
        reconstruction_manifest["source_handoff"],
        "reconstruction manifest source handoff",
    )
    if (
        Path(reconstruction_manifest["source_handoff"]["path"]).resolve()
        != r032_handoff_path
    ):
        raise RuntimeError("reconstruction consumed a different R032 handoff")

    validation = load_json(validation_path)
    if (
        validation.get("result")
        != "PASS_FOR_R042_RECONSTRUCTION_AND_VISUALIZATION"
        or validation.get("logical_pipeline_run_id") != args.pipeline_run_id
        or validation.get("ordered_event_ids") != expected_event_ids
        or validation.get("counts")
        != {
            "events": 9,
            "nodes": 1079,
            "processes": 86,
            "visualizations": 9,
        }
        or not all(validation.get("checks", {}).values())
        or validation.get("errors")
    ):
        raise RuntimeError("R042 final validation did not fully pass")
    check_record(validation["source_handoff"], "validation source handoff")
    for record in validation["reconstruction_manifests"].values():
        check_record(record, "validation reconstruction manifest")

    prevalidation = load_json(prevalidation_input)
    if (
        prevalidation.get("runtime_goal") != "R032"
        or prevalidation.get("result") != "PASS"
        or prevalidation.get("run_id") != f"{args.pipeline_run_id}-R032"
        or Path(prevalidation.get("fx_root", "")).resolve() != fx_root
        or prevalidation.get("downstream_outputs") != []
        or not all(prevalidation.get("validations", {}).values())
        or prevalidation.get("errors")
    ):
        raise RuntimeError("pre-reconstruction R032 revalidation did not pass")
    prevalidation_time = datetime.fromisoformat(prevalidation["generated_at"])
    reconstruction_time = datetime.fromisoformat(
        reconstruction_manifest["created_at"]
    )
    if prevalidation_time >= reconstruction_time:
        raise RuntimeError("R032 revalidation did not precede reconstruction")

    reconstructor_source = reconstructor_path.read_text(encoding="utf-8")
    if (
        "torch.load" in reconstructor_source
        or "no_manual_explanation_or_visualization_generated" not in reconstructor_source
    ):
        raise RuntimeError(
            "reconstructor source violates structural/manual separation"
        )

    artifact_dir.mkdir(parents=True, exist_ok=True)
    prevalidation_path = (
        artifact_dir / "pre_reconstruction_r032_revalidation.json"
    )
    write_json_atomic(prevalidation_path, prevalidation)

    validation_events = {
        item["event_id"]: item for item in validation.get("events", [])
    }
    event_artifacts: list[dict[str, Any]] = []
    event_outputs_by_source_id: dict[str, dict[str, Any]] = {}
    total_nodes = 0
    total_processes = 0
    for ordinal, result in enumerate(manifest_results):
        event_id = expected_event_ids[ordinal]
        event_dir = fx_root / event_id
        reconstruction_path = event_dir / "fx_process_reconstruction.json"
        reconstruction = load_json(reconstruction_path)
        identity = reconstruction["event_identity"]
        if (
            result.get("status") != "ok"
            or result.get("selection_id") != expected_selection_ids[ordinal]
            or result.get("source_event_id") != expected_source_ids[ordinal]
            or identity.get("event_id") != event_id
            or identity.get("selection_id") != expected_selection_ids[ordinal]
            or identity.get("source_event_id") != expected_source_ids[ordinal]
        ):
            raise RuntimeError(f"{event_id}: event identity mismatch")
        for role in ("json", "markdown", "csv"):
            check_record(result[role], f"{event_id}/{role}")
        for source_name, source_record in reconstruction[
            "source_artifacts"
        ].items():
            check_record(source_record, f"{event_id}/source/{source_name}")
        guards = reconstruction["evidence_guards"]
        if not (
            guards.get("fixed_input_path_only") is True
            and guards.get("graph_module_not_executed") is True
            and guards.get("meta_storage_is_structural_evidence") is True
            and guards.get("process_labels_are_rule_derived") is True
            and guards.get("opaque_custom_op_internals_reconstructed") is False
            and guards.get("measured_latency_reported") is False
            and guards.get("pruning_or_early_exit_claimed") is False
            and guards.get("concurrent_or_distributed_coverage_claimed")
            is False
        ):
            raise RuntimeError(f"{event_id}: evidence guards are incomplete")

        validation_event = validation_events.get(event_id, {})
        if validation_event.get("visualization_ok") is not True:
            raise RuntimeError(f"{event_id}: visualization validation failed")
        visualization = file_record(
            event_dir / "fx_process_visualization.md",
            "manual_chinese_process_explanation_and_english_tensor_diagrams",
        )
        if (
            validation_event.get("visualization", {}).get("sha256")
            != visualization["sha256"]
        ):
            raise RuntimeError(f"{event_id}: visualization changed after validation")

        processes = [
            {
                "stage": stage["stage"],
                "title": stage["title"],
                "start_index": stage["start_index"],
                "end_index": stage["end_index"],
                "node_count": stage["node_count"],
                "reconstruction_rule": stage["reconstruction_rule"],
            }
            for stage in reconstruction["stages"]
        ]
        event_record = {
            "ordinal": ordinal + 1,
            "event_id": event_id,
            "selection_id": expected_selection_ids[ordinal],
            "source_event_id": expected_source_ids[ordinal],
            "layer_type": identity["layer_type"],
            "phase": identity["phase"],
            "q_len": identity["q_len"],
            "past_len": identity["past_len"],
            "kv_len": identity["kv_len"],
            "node_count": reconstruction["node_count"],
            "process_count": reconstruction["stage_count"],
            "reconstruction_rule": result["reconstruction_rule"],
            "processes": processes,
            "outputs": {
                "reconstruction_json": result["json"],
                "reconstruction_markdown": result["markdown"],
                "process_node_csv": result["csv"],
                "manual_visualization": visualization,
            },
            "source_fx_artifacts": reconstruction["source_artifacts"],
            "opaque_custom_ops": guards["opaque_custom_ops"],
        }
        event_artifacts.append(event_record)
        event_outputs_by_source_id[expected_source_ids[ordinal]] = {
            "event_id": event_id,
            "selection_id": expected_selection_ids[ordinal],
            "reconstruction_json": result["json"]["path"],
            "reconstruction_markdown": result["markdown"]["path"],
            "process_node_csv": result["csv"]["path"],
            "manual_visualization": visualization["path"],
        }
        total_nodes += reconstruction["node_count"]
        total_processes += reconstruction["stage_count"]

    if total_nodes != 1079 or total_processes != 86:
        raise RuntimeError("R042 aggregate reconstruction counts differ")

    upstream_validation_path = Path(
        r032["outputs"]["validation_report"]["path"]
    ).resolve()
    upstream_evidence_manifest_path = Path(
        r032["outputs"]["evidence_manifest"]["path"]
    ).resolve()
    source_evidence = {
        "r032_handoff": file_record(
            r032_handoff_path, "complete_upstream_r032_runtime_handoff"
        ),
        "r032_validation_report": file_record(
            upstream_validation_path,
            "upstream_r032_completion_validation",
        ),
        "r032_evidence_manifest": file_record(
            upstream_evidence_manifest_path,
            "upstream_r032_complete_evidence_index",
        ),
        "pre_reconstruction_r032_revalidation": file_record(
            prevalidation_path,
            "fresh_pass_recorded_before_r042_reconstruction",
        ),
        "canonical_selected_manifest": file_record(
            Path(downstream["canonical_selected_manifest"]),
            "canonical_selected_event_order",
        ),
    }
    instrumentation = {
        "reconstructor": file_record(
            reconstructor_path,
            "deterministic_fixed_input_fx_process_reconstructor",
        ),
        "validator": file_record(
            validator_path,
            "independent_r042_reconstruction_and_manual_visualization_validator",
        ),
    }
    reconstruction_manifests = {
        "json": file_record(
            manifest_json_path,
            "ordered_r042_fx_process_reconstruction_manifest",
        ),
        "csv": file_record(
            manifest_csv_path,
            "ordered_r042_fx_process_reconstruction_manifest_table",
        ),
    }
    final_validation_record = file_record(
        validation_path,
        "independent_r042_completion_validation",
    )
    reconstruction_only_validation_path = (
        artifact_dir / "reconstruction_validation_report.json"
    )

    evidence_manifest = {
        "schema_version": 1,
        "runtime_goal": "R042",
        "pipeline_run_id": args.pipeline_run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "complete",
        "skill": "qwen-dcu-fx-reconstruct-visualize",
        "fx_root": str(fx_root),
        "counts": {
            "events": 9,
            "linear_attention_events": 4,
            "full_attention_events": 5,
            "prefill_events": 5,
            "decode_events": 4,
            "fx_nodes": total_nodes,
            "processes": total_processes,
            "manual_visualizations": 9,
        },
        "ordered_event_ids": expected_event_ids,
        "ordered_selection_ids": expected_selection_ids,
        "ordered_source_event_ids": expected_source_ids,
        "reconstruction_manifests": reconstruction_manifests,
        "event_artifacts": event_artifacts,
        "source_evidence": source_evidence,
        "instrumentation": instrumentation,
        "validation": {
            "final": final_validation_record,
            "reconstruction_only": file_record(
                reconstruction_only_validation_path,
                "r042_reconstruction_only_validation_before_manual_companions",
            ),
        },
        "evidence_boundary": {
            "fixed_input_fx_dags": (
                "Each reconstruction covers exactly one R032 cloned fixed-input "
                "FX path and does not imply unobserved Python branches."
            ),
            "process_semantics": (
                "Process labels are dependency-ordered, rule-derived regions "
                "of the observed ATen/custom-op DAG, not recovered nn.Module "
                "ownership."
            ),
            "custom_ops": (
                "ROCm/DCU GDN core, KV-cache mutation, and unified attention "
                "remain opaque observed call boundaries."
            ),
            "manual_visualization": (
                "Chinese explanations and English tensor/region diagrams were "
                "written manually in companions separate from generated "
                "reconstruction artifacts."
            ),
        },
        "scope_guards": {
            "graph_modules_loaded_or_executed": False,
            "custom_op_internals_reconstructed": False,
            "measured_latency_reported": False,
            "module_ownership_claimed": False,
            "concurrent_or_distributed_coverage_claimed": False,
            "pruning_or_early_exit_claimed": False,
            "unobserved_branches_claimed": False,
        },
    }
    evidence_manifest_path = artifact_dir / "evidence_manifest.json"
    write_json_atomic(evidence_manifest_path, evidence_manifest)

    event_lines = "\n".join(
        (
            f"- `{item['event_id']}` / `{item['selection_id']}`："
            f"{item['layer_type']}，{item['phase']}，"
            f"{item['node_count']} nodes / {item['process_count']} processes，"
            f"`q/past/kv={item['q_len']}/{item['past_len']}/{item['kv_len']}`"
        )
        for item in event_artifacts
    )
    completion_report = f"""# R042 完成报告

R042 已按 R032 handoff 的原始顺序完成 9 个 Qwen3.5-27B 固定输入 FX DAG
的 process 重建与手工可视化。共覆盖 1,079 个 FX 节点，严格且无重叠地
划分为 86 个 dependency-ordered processes；每个事件均同时提供机器可读
JSON、生成式重建 Markdown、逐节点 CSV，以及独立的手工
`fx_process_visualization.md` companion。

每个 process 的 companion 均以中文回答“是什么 / 为什么需要 /
怎么做/计算”，并在英文字符图中标出真实观测 shape、轴起止、代表元素、
数据流指针及平齐的 tensor/region 边界。最终独立验证逐项检查了 9 个事件、
86 个 process 的完整 FX 节点引用，以及所有图示的语言、shape、指针、
轴端点和矩形/内部 region 几何。

事件清单：

{event_lines}

证据边界保持不变：这些是固定输入路径的 ATen/custom-op DAG；process 名称
是规则推导的结构分区，不是恢复出的模块所有权。GDN core、KV-cache mutation
和 unified attention 的内部 kernel/计算仍然不透明。R042 未加载或执行
meta-storage GraphModule，未把理论 FLOPs 或 FX 节点解释为实测延迟，也未
声称并发、分布式、剪枝、early-exit 或未观测分支覆盖。
"""
    completion_report_path = artifact_dir / "completion_report.md"
    write_text_atomic(completion_report_path, completion_report)

    evidence_manifest_record = file_record(
        evidence_manifest_path, "complete_r042_evidence_index"
    )
    completion_report_record = file_record(
        completion_report_path, "human_readable_r042_completion_report"
    )
    known_limits = [
        {
            "id": "L01_fixed_input_path_only",
            "fact": (
                "Every reconstruction is one observed cloned fixed-input FX "
                "path from R032."
            ),
            "scope_guard": (
                "Do not infer unobserved Python branches or whole-model path "
                "coverage."
            ),
        },
        {
            "id": "L02_rule_derived_process_labels",
            "fact": (
                "Process boundaries and labels are derived from ordered DAG "
                "dependencies and current Qwen3.5 landmarks."
            ),
            "scope_guard": (
                "Do not reinterpret them as recovered nn.Module ownership."
            ),
        },
        {
            "id": "L03_opaque_custom_ops",
            "fact": (
                "GDN core, KV-cache mutation, and unified attention remain "
                "opaque custom-op boundaries."
            ),
            "scope_guard": (
                "Do not claim internal kernels, arithmetic, ownership, or "
                "latency from R042."
            ),
        },
        {
            "id": "L04_no_measured_latency",
            "fact": "R042 reconstructed structure and drew tensor layouts only.",
            "scope_guard": (
                "Do not report FX nodes or upstream theoretical FLOPs as "
                "measured ROCm/DCU latency."
            ),
        },
        {
            "id": "L05_single_request_single_rank",
            "fact": (
                "The source evidence is the R032 max_concurrency=1, "
                "TP/PP/DP=1 HCU0 request."
            ),
            "scope_guard": "Do not claim concurrent or distributed coverage.",
        },
        {
            "id": "L06_meta_storage_structural_only",
            "fact": (
                "The R032 GraphModule artifacts use meta storage and were not "
                "loaded or executed by R042."
            ),
            "scope_guard": (
                "Treat them as structural evidence, not executable layer "
                "checkpoints."
            ),
        },
        {
            "id": "L07_no_pruning_or_early_exit",
            "fact": "No pruning or early-exit path was observed.",
            "scope_guard": "Do not fabricate such decisions from R042.",
        },
        {
            "id": "L08_stage_and_request_identity",
            "fact": (
                "R042 preserves the R032 stage run ID, internal request ID, "
                "source event IDs, selection IDs, and manifest order."
            ),
            "scope_guard": (
                "Use the upstream R032 identity mapping; do not rewrite stage "
                "or request-instance identity."
            ),
        },
    ]
    completion_conditions = {
        "r032_handoff_complete_and_consumed_as_is": True,
        "r032_revalidated_before_reconstruction": True,
        "exact_nine_event_order_and_identities_preserved": True,
        "all_1079_fx_nodes_partitioned_exactly_once": True,
        "all_86_processes_dependency_ordered": True,
        "generated_reconstruction_separate_from_manual_companions": True,
        "manual_visualizations_not_bulk_generated": True,
        "every_process_has_three_required_chinese_explanations": True,
        "every_process_explains_all_grouped_fx_nodes": True,
        "every_process_has_english_tensor_or_region_diagram": True,
        "every_diagram_uses_observed_tensor_shapes": True,
        "every_diagram_has_axes_endpoints_and_explicit_pointers": True,
        "all_rectangle_and_internal_region_borders_align": True,
        "no_chinese_or_raw_fx_targets_inside_diagrams": True,
        "opaque_custom_op_boundaries_and_claim_guards_explicit": True,
        "process_labels_not_claimed_as_module_ownership": True,
        "meta_storage_graph_modules_not_loaded_or_executed": True,
        "no_measured_latency_or_theoretical_flops_claim": True,
        "no_concurrent_distributed_pruning_or_early_exit_claim": True,
        "original_r032_source_artifact_hashes_unchanged": True,
        "all_real_outputs_indexed_for_serial_consumption": True,
        "runtime_handoff_written_to_requested_absolute_path": True,
    }
    handoff = {
        "schema_version": 1,
        "handoff_id": f"{args.pipeline_run_id}:R042",
        "source_goal": "R042",
        "skill": "qwen-dcu-fx-reconstruct-visualize",
        "status": "complete",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "project_root": str(project_root),
            "branch": args.branch,
            "run_id": args.pipeline_run_id,
            "runtime_goal": "R042",
            "previous_handoff": str(r032_handoff_path),
            "user_parameters": {},
        },
        "source_identity": r032["source_identity"],
        "input_contract": {
            "source_goal": "R032",
            "source_handoff": source_evidence["r032_handoff"],
            "source_trace_run_id": r032["trace_contract"]["run_id"],
            "contract_id": r032["trace_contract"]["contract_id"],
            "fx_root": str(fx_root),
            "consume_as_is": True,
            "ordered_event_ids": expected_event_ids,
            "ordered_selection_ids": expected_selection_ids,
            "ordered_source_event_ids": expected_source_ids,
            "join_key": downstream["join_key"],
        },
        "process_contract": {
            "analysis_type": (
                "qwen35_fixed_input_fx_process_reconstruction_and_manual_"
                "tensor_visualization"
            ),
            "fixed_input_path_only": True,
            "process_labels_are_rule_derived": True,
            "generated_and_manual_artifacts_separate": True,
            "opaque_custom_op_internals_reconstructed": False,
            "counts": evidence_manifest["counts"],
            "ordered_event_ids": expected_event_ids,
            "ordered_selection_ids": expected_selection_ids,
            "ordered_source_event_ids": expected_source_ids,
        },
        "validation": {
            "result": validation["result"],
            "counts": validation["counts"],
            "completion_checks": validation["checks"],
            "errors": validation["errors"],
        },
        "completion_conditions": completion_conditions,
        "outputs": {
            "fx_root": directory_record(
                fx_root,
                "r032_fx_evidence_with_complete_r042_process_companions",
            ),
            "reconstruction_manifests": reconstruction_manifests,
            "event_artifacts": event_artifacts,
            "instrumentation": instrumentation,
            "source_evidence": source_evidence,
            "validation_report": final_validation_record,
            "evidence_manifest": evidence_manifest_record,
            "completion_report": completion_report_record,
        },
        "known_nonblocking_limits": known_limits,
        "downstream_contract": {
            "consume_as_is": True,
            "logical_pipeline_run_id": args.pipeline_run_id,
            "source_r032_trace_run_id": r032["trace_contract"]["run_id"],
            "fx_root": str(fx_root),
            "reconstruction_manifest": str(manifest_json_path),
            "reconstruction_manifest_csv": str(manifest_csv_path),
            "validation_report": str(validation_path),
            "evidence_manifest": str(evidence_manifest_path),
            "completion_report": str(completion_report_path),
            "ordered_event_ids": expected_event_ids,
            "ordered_selection_ids": expected_selection_ids,
            "ordered_source_event_ids": expected_source_ids,
            "join_key": downstream["join_key"],
            "event_outputs_by_source_event_id": event_outputs_by_source_id,
            "must_preserve": [
                "Consume all nine events in exact manifest order.",
                (
                    "Preserve selection_id, source_event_id, R032 stage run ID, "
                    "and the upstream request-instance identity mapping."
                ),
                (
                    "Treat every reconstruction as one fixed-input FX path and "
                    "every process label as a rule-derived DAG region."
                ),
                (
                    "Keep generated reconstruction artifacts separate from the "
                    "manual fx_process_visualization.md companions."
                ),
                (
                    "Keep GDN core, KV-cache mutation, and unified-attention "
                    "custom-op internals opaque."
                ),
                (
                    "Do not load meta-storage GraphModules as executable model "
                    "checkpoints."
                ),
                (
                    "Do not reinterpret process regions, FX nodes, or upstream "
                    "theoretical FLOPs as measured latency."
                ),
                (
                    "Do not claim module ownership, unobserved branches, "
                    "concurrent/distributed execution, pruning, or early exit."
                ),
            ],
        },
    }
    write_json_atomic(handoff_output, handoff)

    written_handoff = load_json(handoff_output)
    if (
        written_handoff.get("status") != "complete"
        or written_handoff.get("handoff_id")
        != f"{args.pipeline_run_id}:R042"
        or not all(
            written_handoff.get("completion_conditions", {}).values()
        )
    ):
        raise RuntimeError("written R042 handoff did not round-trip")
    print(
        json.dumps(
            {
                "status": "complete",
                "runtime_goal": "R042",
                "handoff": file_record(
                    handoff_output, "complete_r042_runtime_handoff"
                ),
                "counts": validation["counts"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
