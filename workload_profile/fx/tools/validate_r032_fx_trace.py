#!/usr/bin/env python3
"""Independently validate all R032 selected-layer FX completion conditions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_EVENT_FILES = (
    "fx_graph.py",
    "fx_graph.txt",
    "fx_nodes.json",
    "fx_graph_module.pt",
    "fx_trace_metadata.json",
)


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


def truth(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def integer(value: Any) -> int:
    return int(str(value))


def run_git(repository: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repository), *args],
        text=True,
    ).strip()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def expected_opaque_ops(layer_type: str) -> list[str]:
    if layer_type == "linear_attention":
        return ["vllm.gdn_attention_core.default"]
    return [
        "vllm.unified_kv_cache_update.default",
        "vllm.unified_attention_with_output.default",
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fx-root", required=True, type=Path)
    parser.add_argument("--r02-handoff", required=True, type=Path)
    parser.add_argument("--source-result", required=True, type=Path)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--runtime-patch", required=True, type=Path)
    parser.add_argument("--service-entry", required=True, type=Path)
    parser.add_argument("--request-runner", required=True, type=Path)
    parser.add_argument("--service-log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mirror-output", type=Path)
    parser.add_argument("--expected-run-id", required=True)
    args = parser.parse_args()

    root = args.fx_root.resolve()
    r02_handoff_path = args.r02_handoff.resolve()
    source_result_path = args.source_result.resolve()
    repository = args.repository.resolve()
    runtime_patch = args.runtime_patch.resolve()
    service_entry = args.service_entry.resolve()
    request_runner = args.request_runner.resolve()
    service_log = args.service_log.resolve()

    errors: list[str] = []
    artifact_errors: list[str] = []
    source_mapping_errors: list[str] = []
    request_instance_mapping_errors: list[str] = []
    state_snapshot_errors: list[str] = []
    lifecycle_errors: list[str] = []

    r02 = load_json(r02_handoff_path)
    selected_path = Path(
        r02["downstream_contract"]["canonical_selected_manifest"]
    ).resolve()
    selection_handoff_path = Path(
        r02["downstream_contract"]["selection_handoff"]
    ).resolve()
    source_trace_path = Path(
        r02["downstream_contract"]["algorithmic_trace"]
    ).resolve()
    selected = load_csv(selected_path)
    expected_ids = [
        f"input{row['forward_id']}_layer{row['layer_idx']}" for row in selected
    ]
    expected_source_ids = [row["source_event_id"] for row in selected]
    expected_selection_ids = [row["selection_id"] for row in selected]
    expected_source_request_ids = sorted(
        {row["request_id"] for row in selected}
    )
    source_by_event = {
        f"input{row['forward_id']}_layer{row['layer_idx']}": row
        for row in selected
    }

    metadata_path = root / "run_metadata.json"
    layer_path = root / "fx_layer_events.csv"
    manifest_path = root / "fx_layer_trace_manifest.csv"
    done_path = root / "FINALIZE_DONE.json"
    request_result_path = root / "request" / "result.json"
    request_contract_path = root / "request" / "request_contract.json"
    for path in (
        selected_path,
        selection_handoff_path,
        source_trace_path,
        metadata_path,
        layer_path,
        manifest_path,
        done_path,
        request_result_path,
        request_contract_path,
        source_result_path,
        runtime_patch,
        service_entry,
        request_runner,
        service_log,
    ):
        if not path.is_file():
            errors.append(f"required file missing: {path}")
    if errors:
        review = {
            "schema_version": 1,
            "runtime_goal": "R032",
            "result": "FAIL",
            "errors": errors,
        }
        write_json_atomic(args.output.resolve(), review)
        if args.mirror_output:
            write_json_atomic(args.mirror_output.resolve(), review)
        raise SystemExit(1)

    metadata = load_json(metadata_path)
    done = load_json(done_path)
    request_result = load_json(request_result_path)
    request_contract = load_json(request_contract_path)
    source_result = load_json(source_result_path)
    layers = load_csv(layer_path)
    manifest = load_csv(manifest_path)
    selected_layers = [row for row in layers if truth(row.get("matched"))]
    selected_layer_by_event = {
        row["event_id"]: row for row in selected_layers
    }

    # Source and event identity.
    source_hash_checks = {
        "r02_handoff": sha256_file(r02_handoff_path),
        "canonical_selected_manifest": sha256_file(selected_path),
        "selection_handoff": sha256_file(selection_handoff_path),
        "source_algorithmic_trace": sha256_file(source_trace_path),
    }
    expected_source_hashes = {
        "canonical_selected_manifest": r02["outputs"][
            "canonical_selected_manifest"
        ]["sha256"],
        "selection_handoff": r02["outputs"]["selection_handoff"]["sha256"],
        "source_algorithmic_trace": r02["outputs"]["required_semantic_artifacts"][
            "algorithmic_trace"
        ]["sha256"],
    }
    source_hashes_unchanged = all(
        source_hash_checks[key] == value
        for key, value in expected_source_hashes.items()
    )
    if not source_hashes_unchanged:
        errors.append("one or more R02 source evidence hashes changed")

    manifest_ids = [row["event_id"] for row in manifest]
    selected_layer_ids = [row["event_id"] for row in selected_layers]
    if manifest_ids != expected_ids:
        source_mapping_errors.append(
            f"manifest event order differs: {manifest_ids!r} != {expected_ids!r}"
        )
    if selected_layer_ids != expected_ids:
        source_mapping_errors.append(
            "selected layer event order differs from canonical selection"
        )

    join_fields = (
        ("contract_id", "contract_id", str),
        ("rank", "rank", integer),
        ("worker_id", "worker_id", str),
        ("engine_step_id", "engine_step_id", integer),
        ("forward_id", "forward_id", integer),
        ("layer_id", "layer_idx", integer),
        ("layer_occurrence", "layer_occurrence", integer),
        ("phase", "phase", str),
        ("q_len", "q_len", integer),
        ("past_len", "past_len", integer),
        ("kv_len", "kv_len", integer),
        ("layer_type", "layer_type", str),
    )
    for row in manifest:
        event_id = row["event_id"]
        source = source_by_event.get(event_id)
        if source is None:
            source_mapping_errors.append(f"unexpected manifest event: {event_id}")
            continue
        if row.get("selection_id") != source["selection_id"]:
            source_mapping_errors.append(f"{event_id}: selection_id mismatch")
        if row.get("source_event_id") != source["source_event_id"]:
            source_mapping_errors.append(f"{event_id}: source_event_id mismatch")
        if row.get("source_run_id") != source["run_id"]:
            source_mapping_errors.append(f"{event_id}: source_run_id mismatch")
        for actual_name, source_name, convert in join_fields:
            actual: Any = row.get(actual_name)
            expected: Any = source.get(source_name)
            try:
                if convert is integer:
                    actual = integer(actual)
                    expected = integer(expected)
                else:
                    actual = convert(actual)
                    expected = convert(expected)
            except Exception as exc:
                source_mapping_errors.append(
                    f"{event_id}: cannot parse {actual_name}: {exc!r}"
                )
                continue
            if actual != expected:
                source_mapping_errors.append(
                    f"{event_id}: {actual_name} {actual!r} != {expected!r}"
                )

    # vLLM V1 intentionally replaces the externally supplied request ID with
    # "<external_req_id>-<8 random hex chars>" inside InputProcessor. Preserve
    # both identities and require one documented, bijective instance mapping;
    # do not rewrite the observed scheduler ID to look identical to R02.
    observed_request_ids = sorted({row["request_id"] for row in manifest})
    source_request_id = (
        expected_source_request_ids[0]
        if len(expected_source_request_ids) == 1
        else ""
    )
    observed_request_id = (
        observed_request_ids[0] if len(observed_request_ids) == 1 else ""
    )
    request_suffix = (
        observed_request_id[len(source_request_id) + 1 :]
        if source_request_id
        and observed_request_id.startswith(f"{source_request_id}-")
        else ""
    )
    request_instance_pattern_match = bool(
        source_request_id
        and re.fullmatch(
            rf"{re.escape(source_request_id)}-[0-9a-f]{{8}}",
            observed_request_id,
        )
    )
    if len(expected_source_request_ids) != 1:
        request_instance_mapping_errors.append(
            f"canonical selection has source request IDs "
            f"{expected_source_request_ids!r}, expected exactly one"
        )
    if len(observed_request_ids) != 1:
        request_instance_mapping_errors.append(
            f"runtime manifest has request IDs {observed_request_ids!r}, "
            "expected exactly one"
        )
    if not request_instance_pattern_match:
        request_instance_mapping_errors.append(
            f"observed internal request ID {observed_request_id!r} is not "
            f"{source_request_id!r} plus one 8-hex vLLM instance suffix"
        )
    for row in manifest:
        event_id = row["event_id"]
        layer_row = selected_layer_by_event.get(event_id)
        expected_direct_error = (
            f"request_id:{row['request_id']!r}!={source_request_id!r}"
        )
        if truth(row.get("source_contract_match")):
            request_instance_mapping_errors.append(
                f"{event_id}: direct source_contract_match unexpectedly true "
                "despite the preserved internal request instance suffix"
            )
        if layer_row is None:
            request_instance_mapping_errors.append(
                f"{event_id}: selected runtime layer row is missing"
            )
            continue
        if truth(layer_row.get("source_contract_match")):
            request_instance_mapping_errors.append(
                f"{event_id}: layer-row direct source_contract_match "
                "unexpectedly true despite the request instance suffix"
            )
        if layer_row.get("source_mapping_error") != expected_direct_error:
            request_instance_mapping_errors.append(
                f"{event_id}: layer-row source_mapping_error differs from the "
                "single expected internal request-instance difference"
            )

    source_trace_run_ids = sorted({row["run_id"] for row in selected})
    observed_stage_trace_run_ids = sorted({row["run_id"] for row in manifest})
    source_trace_run_id = (
        source_trace_run_ids[0] if len(source_trace_run_ids) == 1 else ""
    )
    observed_stage_trace_run_id = (
        observed_stage_trace_run_ids[0]
        if len(observed_stage_trace_run_ids) == 1
        else ""
    )
    run_identity_mapping_valid = (
        source_trace_run_ids == [f"{args.expected_run_id}-R02"]
        and observed_stage_trace_run_ids == [f"{args.expected_run_id}-R032"]
        and metadata.get("run_id") == observed_stage_trace_run_id
        and all(
            row["source_run_id"] == source_trace_run_id for row in manifest
        )
        and all(
            row["source_run_id"] == source_trace_run_id
            and row["run_id"] == observed_stage_trace_run_id
            for row in selected_layers
        )
    )
    if not run_identity_mapping_valid:
        source_mapping_errors.append(
            "logical pipeline, R02 source-trace, and R032 stage-trace run IDs "
            "do not have the required explicit one-to-one relation"
        )

    # Full observed runtime layer coverage and occurrence uniqueness.
    forward_layers: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in layers:
        forward_layers[integer(row["forward_id"])].append(row)
    full_forward_coverage = (
        len(layers) == 1856
        and sorted(forward_layers) == list(range(1, 30))
        and all(len(rows) == 64 for rows in forward_layers.values())
        and all(
            sorted(integer(row["layer_id"]) for row in rows) == list(range(64))
            for rows in forward_layers.values()
        )
        and all(
            integer(row["layer_occurrence"]) == 0
            for rows in forward_layers.values()
            for row in rows
        )
    )
    if not full_forward_coverage:
        errors.append("observed layer events do not cover 29 complete 64-layer forwards")
    phase_shape_consistency = all(
        len({row["phase"] for row in rows}) == 1
        and len({integer(row["q_len"]) for row in rows}) == 1
        and len({integer(row["past_len"]) for row in rows}) == 1
        and len({integer(row["kv_len"]) for row in rows}) == 1
        for rows in forward_layers.values()
    )
    if not phase_shape_consistency:
        errors.append("per-forward phase or q/past/kv lengths are inconsistent")

    layer_type_pattern = [
        "full_attention" if index % 4 == 3 else "linear_attention"
        for index in range(64)
    ]
    loaded_layer_types_consistent = all(
        [row["layer_type"] for row in sorted(rows, key=lambda item: integer(item["layer_id"]))]
        == layer_type_pattern
        for rows in forward_layers.values()
    )
    if not loaded_layer_types_consistent:
        errors.append("loaded Qwen3.5 layer type pattern is inconsistent")

    selected_unique = (
        len(selected_layers) == 9
        and len({row["source_event_id"] for row in selected_layers}) == 9
        and all(truth(row["fx_sampled"]) for row in selected_layers)
        and all(truth(row["fx_traced"]) for row in selected_layers)
        and all(row["fx_trace_status"] == "ok" for row in selected_layers)
    )
    if not selected_unique:
        errors.append("selected layer sampling/tracing is not unique and fully successful")

    # Per-event artifacts, metadata, node counts, and opaque operation boundary.
    node_counts: dict[str, int] = {}
    event_artifacts: dict[str, dict[str, Any]] = {}
    for row in manifest:
        event_id = row["event_id"]
        event_dir = Path(row["trace_dir"]).resolve()
        if event_dir != root / event_id:
            artifact_errors.append(f"{event_id}: trace_dir is not root/event_id")
        files = {}
        for name in REQUIRED_EVENT_FILES:
            path = event_dir / name
            if not path.is_file() or path.stat().st_size == 0:
                artifact_errors.append(f"{event_id}: missing or empty {name}")
            else:
                files[name] = {
                    "path": str(path),
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
        graph_dir = event_dir / "fx_graph_module"
        if not graph_dir.is_dir():
            artifact_errors.append(f"{event_id}: missing fx_graph_module directory")
        else:
            for name in ("module.py", "state_dict.pt"):
                if not (graph_dir / name).is_file():
                    artifact_errors.append(
                        f"{event_id}: fx_graph_module missing {name}"
                    )
        if row.get("status") != "ok":
            artifact_errors.append(f"{event_id}: manifest status is not ok")
            continue
        if json.loads(row.get("save_errors") or "[]"):
            artifact_errors.append(f"{event_id}: save_errors is non-empty")
        node_count = integer(row["node_count"])
        node_counts[event_id] = node_count
        nodes = load_json(event_dir / "fx_nodes.json")
        event_metadata = load_json(event_dir / "fx_trace_metadata.json")
        if len(nodes) != node_count or integer(event_metadata["node_count"]) != node_count:
            artifact_errors.append(f"{event_id}: node counts disagree")
        targets = [str(node["target"]) for node in nodes]
        expected_ops = expected_opaque_ops(row["layer_type"])
        if not all(name in targets for name in expected_ops):
            artifact_errors.append(
                f"{event_id}: missing expected opaque custom ops {expected_ops}"
            )
        if json.loads(row["opaque_custom_ops"]) != expected_ops:
            artifact_errors.append(f"{event_id}: opaque op manifest mismatch")
        specialization = json.loads(row["specialization"])
        if event_metadata.get("specialization") != specialization:
            artifact_errors.append(
                f"{event_id}: event metadata specialization differs from manifest"
            )
        lifecycle = specialization.get("lifecycle", {})
        if lifecycle.get("fx_graph_used_for_runtime_response") is not False:
            artifact_errors.append(
                f"{event_id}: runtime response boundary is not explicit"
            )
        if (
            lifecycle.get("wrappers_restored_ns")
            is None
            or lifecycle.get("offline_trace_start_ns") is None
            or integer(lifecycle["wrappers_restored_ns"])
            > integer(lifecycle["offline_trace_start_ns"])
        ):
            lifecycle_errors.append(
                f"{event_id}: wrappers were not restored before offline trace"
            )
        context_snapshot = specialization.get("forward_context_snapshot", {})
        if not context_snapshot.get("selected_context_keys"):
            state_snapshot_errors.append(
                f"{event_id}: selected forward-context keys are empty"
            )
        if integer(context_snapshot.get("metadata_tensor_count", 0)) <= 0:
            state_snapshot_errors.append(
                f"{event_id}: forward-context metadata tensors were not cloned"
            )
        state_snapshot = specialization.get("external_state_snapshot", {})
        if integer(state_snapshot.get("snapshot_tensor_count", 0)) <= 0:
            state_snapshot_errors.append(
                f"{event_id}: active external state snapshot is empty"
            )
        for snapshot in state_snapshot.get("snapshot_tensors", []):
            if not snapshot.get("snapshot_sha256") or not snapshot.get(
                "snapshot_shape"
            ):
                state_snapshot_errors.append(
                    f"{event_id}: external state snapshot lacks shape/hash"
                )
        event_artifacts[event_id] = {
            "trace_dir": str(event_dir),
            "node_count": node_count,
            "opaque_custom_ops": expected_ops,
            "files": files,
        }

    event_dirs = sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir() and re.fullmatch(r"input\d+_layer\d+", path.name)
    )
    exact_event_directories = set(event_dirs) == set(expected_ids)
    if not exact_event_directories:
        artifact_errors.append(
            f"event directories differ: {event_dirs!r} != {expected_ids!r}"
        )

    # Runtime lifecycle boundary.
    lifecycle = metadata.get("lifecycle", {})
    lifecycle_values = [
        lifecycle.get("capture_last_ns"),
        lifecycle.get("finalize_marker_observed_ns"),
        lifecycle.get("wrappers_restored_ns"),
        lifecycle.get("offline_first_start_ns"),
        lifecycle.get("offline_last_end_ns"),
    ]
    lifecycle_ordered = (
        all(value is not None for value in lifecycle_values)
        and integer(lifecycle_values[0])
        < integer(lifecycle_values[1])
        <= integer(lifecycle_values[2])
        <= integer(lifecycle_values[3])
        <= integer(lifecycle_values[4])
        and lifecycle.get("active_execute_count_at_finalize") == 0
        and lifecycle.get("wrappers_restored_before_offline_fx") is True
        and lifecycle.get("wrapper_restore_errors") == []
    )
    if not lifecycle_ordered:
        lifecycle_errors.append("run-level capture/finalize/restore/offline order failed")

    # Request output equivalence and external-to-internal request identity.
    output_fields = (
        "completed",
        "failed",
        "input_lens",
        "output_lens",
        "generated_texts",
    )
    request_output_equivalent = all(
        request_result.get(field) == source_result.get(field)
        for field in output_fields
    )
    request_instance_mapping_valid = (
        request_instance_pattern_match
        and not request_instance_mapping_errors
        and request_result.get("request_id") == source_request_id
        and request_result.get("request_header_id")
        == request_contract.get("x_request_id")
        and request_contract.get("source_request_id") == source_request_id
        and metadata.get("captured_request_ids") == [observed_request_id]
        and all(
            row["request_id"] == observed_request_id for row in selected_layers
        )
    )
    if not request_output_equivalent:
        errors.append("R032 request output differs from the R02 eager source request")
    if not request_instance_mapping_valid:
        errors.append(
            "R032 external source request ID to internal vLLM request-instance "
            "mapping is not uniquely preserved"
        )

    # Installed source identity and clean repository.
    repository_revision = run_git(repository, "rev-parse", "HEAD")
    repository_branch = run_git(repository, "branch", "--show-current")
    repository_status = run_git(repository, "status", "--porcelain")
    installed_source_matches: dict[str, bool] = {}
    for name, record in metadata["source_identity"]["installed_sources"].items():
        installed = Path(record["path"]).resolve()
        marker = "/vllm/"
        if marker not in str(installed):
            installed_source_matches[name] = False
            continue
        relative = str(installed).split(marker, 1)[1]
        repository_file = repository / "vllm" / relative
        installed_source_matches[name] = (
            repository_file.is_file()
            and sha256_file(repository_file) == record["sha256"]
            and sha256_file(installed) == record["sha256"]
        )
    source_identity_valid = (
        repository_revision == r02["source_identity"]["revision"]
        and repository_branch == "pra"
        and repository_status == ""
        and metadata["source_identity"]["revision"] == repository_revision
        and metadata["source_identity"]["installed_vllm_version"]
        == "0.18.1+das.dtk2604"
        and all(installed_source_matches.values())
    )
    if not source_identity_valid:
        errors.append("installed/repository source identity validation failed")

    # Event-stream lifecycle and absence of downstream work.
    raw_events: list[dict[str, Any]] = []
    event_streams = sorted(root.glob("events.*.jsonl"))
    for path in event_streams:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                raw_events.append(json.loads(line))
    captured_event_counts = Counter(
        event.get("event_id")
        for event in raw_events
        if event.get("event_type") == "selected_sample_captured"
    )
    event_stream_capture_unique = all(
        captured_event_counts[event_id] == 1 for event_id in expected_ids
    ) and sum(captured_event_counts.values()) == 9
    if not event_stream_capture_unique:
        errors.append("raw event streams do not show one capture per selected event")
    downstream_patterns = (
        "fx_process_reconstruction",
        "fx_process_visualization",
        "fx_process_nodes",
        "reconstruction_manifest",
    )
    downstream_outputs = [
        str(path)
        for path in root.rglob("*")
        if path.is_file() and any(pattern in path.name for pattern in downstream_patterns)
    ]
    no_downstream_work = not downstream_outputs
    if not no_downstream_work:
        errors.append(f"disallowed downstream outputs exist: {downstream_outputs}")

    validations = {
        "r02_handoff_complete": r02.get("status") == "complete",
        "source_evidence_hashes_unchanged": source_hashes_unchanged,
        "exactly_nine_canonical_events": len(selected) == 9
        and len(set(expected_ids)) == 9,
        "canonical_event_order_and_source_ids_preserved": (
            manifest_ids == expected_ids
            and selected_layer_ids == expected_ids
            and [row["source_event_id"] for row in manifest]
            == expected_source_ids
            and [row["selection_id"] for row in manifest]
            == expected_selection_ids
        ),
        "source_join_and_sequence_fields_except_internal_request_id_match": (
            not source_mapping_errors
        ),
        "external_source_to_internal_request_instance_mapping_bijective": (
            request_instance_mapping_valid
        ),
        "full_29x64_layer_coverage": full_forward_coverage,
        "per_forward_phase_and_lengths_consistent": phase_shape_consistency,
        "loaded_layer_types_consistent": loaded_layer_types_consistent,
        "selected_samples_unique_and_successful": selected_unique,
        "run_metadata_counts": (
            metadata.get("fx_sample_count") == 9
            and metadata.get("fx_trace_count") == 9
            and metadata.get("fx_trace_error_count") == 0
            and metadata.get("observed_layer_event_count") == 1856
            and metadata.get("observed_forward_count") == 29
        ),
        "done_status_complete": done.get("status") == "complete",
        "no_patch_capture_or_restore_errors": (
            metadata.get("patch_errors") == []
            and metadata.get("capture_errors") == []
            and lifecycle.get("wrapper_restore_errors") == []
        ),
        "request_return_restore_offline_order": lifecycle_ordered
        and not lifecycle_errors,
        "all_event_artifacts_complete": not artifact_errors
        and len(event_artifacts) == 9,
        "event_directories_exact": exact_event_directories,
        "forward_context_and_external_state_cloned": not state_snapshot_errors
        and metadata.get("external_state_snapshot_bytes_retained", 0) > 0,
        "opaque_custom_op_boundary_present": all(
            set(expected_opaque_ops(row["layer_type"]))
            <= {
                str(node["target"])
                for node in load_json(root / row["event_id"] / "fx_nodes.json")
            }
            for row in manifest
        ),
        "request_output_matches_r02_eager_source": request_output_equivalent,
        "installed_sources_match_clean_repository": source_identity_valid,
        "raw_event_capture_unique": event_stream_capture_unique,
        "no_downstream_reconstruction_or_visualization": no_downstream_work,
        "single_request_single_rank_scope_explicit": any(
            "max_concurrency=1 TP=PP=DP=1" in guard
            for guard in metadata.get("scope_guards", [])
        ),
        "fixed_input_and_custom_op_claim_guards_explicit": (
            "custom_ops" in metadata.get("evidence_boundary", {})
            and any(
                "fixed-input" in guard
                for guard in metadata.get("scope_guards", [])
            )
        ),
        "theoretical_flops_not_reported_as_latency": any(
            "theoretical FLOPs are not measured latency" in guard
            for guard in metadata.get("scope_guards", [])
        ),
        "logical_source_and_stage_run_identity_mapping_explicit": (
            run_identity_mapping_valid
        ),
    }
    passed = (
        all(validations.values())
        and not errors
        and not artifact_errors
        and not source_mapping_errors
        and not request_instance_mapping_errors
        and not state_snapshot_errors
        and not lifecycle_errors
    )
    review = {
        "schema_version": 1,
        "runtime_goal": "R032",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "result": "PASS" if passed else "FAIL",
        "fx_root": str(root),
        "run_id": metadata.get("run_id"),
        "contract_id": metadata.get("contract_id"),
        "source_revision": repository_revision,
        "source_hashes": source_hash_checks,
        "runtime_tracer": {
            "path": str(runtime_patch),
            "sha256": sha256_file(runtime_patch),
            "size_bytes": runtime_patch.stat().st_size,
        },
        "service_entry": {
            "path": str(service_entry),
            "sha256": sha256_file(service_entry),
            "size_bytes": service_entry.stat().st_size,
        },
        "request_runner": {
            "path": str(request_runner),
            "sha256": sha256_file(request_runner),
            "size_bytes": request_runner.stat().st_size,
        },
        "service_log": {
            "path": str(service_log),
            "sha256": sha256_file(service_log),
            "size_bytes": service_log.stat().st_size,
        },
        "repository": {
            "path": str(repository),
            "branch": repository_branch,
            "revision": repository_revision,
            "clean": repository_status == "",
            "installed_source_matches": installed_source_matches,
        },
        "counts": {
            "canonical_selected_events": len(selected),
            "layer_events": len(layers),
            "effective_forwards": len(forward_layers),
            "selected_layer_events": len(selected_layers),
            "manifest_rows": len(manifest),
            "successful_fx_traces": sum(row.get("status") == "ok" for row in manifest),
            "raw_event_rows": len(raw_events),
            "raw_event_streams": len(event_streams),
        },
        "expected_event_ids": expected_ids,
        "expected_source_event_ids": expected_source_ids,
        "source_event_identity_mapping": {
            "logical_pipeline_run_id": args.expected_run_id,
            "source_r02_trace_run_id": source_trace_run_id,
            "observed_r032_trace_run_id": observed_stage_trace_run_id,
            "source_external_request_id": source_request_id,
            "observed_internal_request_id": observed_request_id,
            "internal_random_suffix": request_suffix,
            "relation": (
                "observed_internal_request_id = "
                "source_external_request_id + '-' + 8 lowercase hex characters"
            ),
            "mechanism": (
                "vLLM V1 InputProcessor.assign_request_id request-ID "
                "randomization"
            ),
            "bijective_for_this_single_request": request_instance_mapping_valid,
        },
        "node_counts": node_counts,
        "event_artifacts": event_artifacts,
        "request_result": {
            "path": str(request_result_path),
            "sha256": sha256_file(request_result_path),
            "equivalent_to_source": request_output_equivalent,
        },
        "validations": validations,
        "errors": errors,
        "artifact_errors": artifact_errors,
        "source_mapping_errors": source_mapping_errors,
        "request_instance_mapping_errors": request_instance_mapping_errors,
        "state_snapshot_errors": state_snapshot_errors,
        "lifecycle_errors": lifecycle_errors,
        "downstream_outputs": downstream_outputs,
    }
    write_json_atomic(args.output.resolve(), review)
    if args.mirror_output:
        write_json_atomic(args.mirror_output.resolve(), review)
    print(json.dumps(review, indent=2, ensure_ascii=False, sort_keys=True))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
