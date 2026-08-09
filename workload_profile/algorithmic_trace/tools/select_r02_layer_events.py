#!/usr/bin/env python3
"""Select a small evidence-backed R02 layer-event set from normalized traces."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def int_value(row: dict[str, str], key: str) -> int:
    return int(row[key])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", required=True, type=Path)
    args = parser.parse_args()
    trace_dir = args.trace_dir.resolve()
    layer_path = trace_dir / "layer_trace.csv"
    decision_path = trace_dir / "selection_trace.csv"
    trace_path = trace_dir / "algorithmic_trace.json"
    review_path = trace_dir / "trace_validation.json"
    layers = load_csv(layer_path)
    decisions = load_csv(decision_path)
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    trace_review = json.loads(review_path.read_text(encoding="utf-8"))

    layer_key_counts = Counter(
        (
            row["request_id"],
            int_value(row, "engine_step_id"),
            int_value(row, "forward_id"),
            int_value(row, "layer_idx"),
            int_value(row, "layer_occurrence"),
        )
        for row in layers
    )
    by_forward: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in layers:
        by_forward[int_value(row, "forward_id")].append(row)
    forward_context = {
        forward_id: {
            "phase": rows[0]["phase"],
            "q_len": int_value(rows[0], "q_len"),
            "past_len": int_value(rows[0], "past_len"),
            "kv_len": int_value(rows[0], "kv_len"),
        }
        for forward_id, rows in by_forward.items()
    }
    prefill_forwards = sorted(
        forward_id
        for forward_id, context in forward_context.items()
        if context["phase"] == "prefill_chunk"
    )
    decode_forwards = sorted(
        forward_id
        for forward_id, context in forward_context.items()
        if context["phase"] == "decode"
    )
    if not prefill_forwards or not decode_forwards:
        raise SystemExit("selection requires observed prefill and decode forwards")

    linear_ids = sorted(
        {
            int_value(row, "layer_idx")
            for row in layers
            if row["layer_type"] == "linear_attention"
        }
    )
    full_ids = sorted(
        {
            int_value(row, "layer_idx")
            for row in layers
            if row["layer_type"] == "full_attention"
        }
    )
    first_prefill = prefill_forwards[0]
    first_cached_prefill = next(
        forward_id
        for forward_id in prefill_forwards
        if forward_context[forward_id]["past_len"] > 0
    )
    tail_prefill = min(
        prefill_forwards,
        key=lambda value: (
            forward_context[value]["q_len"],
            -forward_context[value]["past_len"],
        ),
    )
    first_decode = decode_forwards[0]
    late_decode = decode_forwards[-1]
    model_midpoint = (max(linear_ids + full_ids) + 1) // 2
    middle_full = min(full_ids, key=lambda value: abs(value - model_midpoint))

    target_specs = [
        {
            "forward_id": first_prefill,
            "layer_idx": linear_ids[0],
            "priority": "P0",
            "role": "initial_prefill_early_linear",
            "reason": (
                "First loaded linear-attention layer in the initial scheduler "
                "chunk, immediately after the observed prefix-cache lookup and "
                "first successful hybrid-cache allocation."
            ),
        },
        {
            "forward_id": first_prefill,
            "layer_idx": full_ids[0],
            "priority": "P0",
            "role": "initial_prefill_early_full_attention",
            "reason": (
                "First loaded full-attention layer in the initial q_len=4096, "
                "past_len=0 chunk; pairs the first full-attention KV regime "
                "with its observed backend-route decision."
            ),
        },
        {
            "forward_id": first_cached_prefill,
            "layer_idx": middle_full,
            "priority": "P1",
            "role": "post_initial_cache_growth_boundary",
            "reason": (
                "Middle-depth full-attention representative in the first "
                "prefill forward with nonzero past_len, immediately after the "
                "initial cache-state growth boundary."
            ),
        },
        {
            "forward_id": tail_prefill,
            "layer_idx": linear_ids[-1],
            "priority": "P1",
            "role": "tail_prefill_late_linear",
            "reason": (
                "Last loaded linear-attention layer in the observed short tail "
                "prefill, where q_len changes from the full 4096-token chunks."
            ),
        },
        {
            "forward_id": tail_prefill,
            "layer_idx": full_ids[-1],
            "priority": "P1",
            "role": "tail_prefill_late_full_attention",
            "reason": (
                "Last loaded full-attention layer at the prefill tail and "
                "prefill-to-decode boundary, with the largest observed "
                "prefill past_len."
            ),
        },
        {
            "forward_id": first_decode,
            "layer_idx": linear_ids[0],
            "priority": "P3",
            "role": "first_decode_early_linear",
            "reason": (
                "First decode-step linear-attention layer after the observed "
                "phase and token-count transition from tail prefill to q_len=1."
            ),
        },
        {
            "forward_id": first_decode,
            "layer_idx": full_ids[0],
            "priority": "P3",
            "role": "first_decode_early_full_attention",
            "reason": (
                "First decode-step full-attention layer, representing the "
                "earliest observed single-token KV-cache attention regime."
            ),
        },
        {
            "forward_id": late_decode,
            "layer_idx": linear_ids[-1],
            "priority": "P3",
            "role": "late_decode_late_linear",
            "reason": (
                "Last loaded linear-attention layer in the final observed "
                "decode forward, after the full generated-prefix state has "
                "accumulated."
            ),
        },
        {
            "forward_id": late_decode,
            "layer_idx": full_ids[-1],
            "priority": "P0",
            "role": "late_decode_terminal_full_attention",
            "reason": (
                "Final loaded full-attention layer in the last decode forward; "
                "this forward is directly joined to the observed terminal "
                "KV-cache free transition."
            ),
        },
    ]

    def affected_ids(decision: dict[str, str]) -> set[int]:
        value = decision.get("affected_layer_ids", "")
        return {int(item) for item in value.split(";") if item}

    selected: list[dict[str, Any]] = []
    for spec in target_specs:
        candidates = [
            row
            for row in by_forward[spec["forward_id"]]
            if int_value(row, "layer_idx") == spec["layer_idx"]
            and int_value(row, "layer_occurrence") == 0
        ]
        if len(candidates) != 1:
            raise SystemExit(
                f"target {spec['role']} matched {len(candidates)} source rows"
            )
        source = candidates[0]
        relevant_decisions = []
        for decision in decisions:
            if not decision.get("forward_id"):
                continue
            if int(decision["forward_id"]) != spec["forward_id"]:
                continue
            ids = affected_ids(decision)
            family = decision["decision_family"]
            if (
                spec["layer_idx"] in ids
                or family in ("sampling", "host_output")
                or decision["event_type"] == "kv_free"
            ):
                relevant_decisions.append(decision["decision_id"])
        evidence_ids = relevant_decisions[:12]
        key = (
            source["request_id"],
            int_value(source, "engine_step_id"),
            int_value(source, "forward_id"),
            int_value(source, "layer_idx"),
            int_value(source, "layer_occurrence"),
        )
        selected.append(
            {
                "selection_id": f"selected:{len(selected) + 1:02d}",
                "priority": spec["priority"],
                "role": spec["role"],
                "reason": spec["reason"],
                "run_id": source["run_id"],
                "contract_id": source["contract_id"],
                "source_revision": source["source_revision"],
                "trace_mode": source["trace_mode"],
                "rank": source["rank"],
                "worker_id": source["worker_id"],
                "device_id": source["device_id"],
                "request_id": source["request_id"],
                "engine_step_id": int_value(source, "engine_step_id"),
                "schedule_id": source["schedule_id"],
                "batch_id": source["batch_id"],
                "forward_id": int_value(source, "forward_id"),
                "layer_idx": int_value(source, "layer_idx"),
                "layer_occurrence": int_value(source, "layer_occurrence"),
                "phase": source["phase"],
                "q_len": int_value(source, "q_len"),
                "past_len": int_value(source, "past_len"),
                "kv_len": int_value(source, "kv_len"),
                "layer_type": source["layer_type"],
                "source_event_id": source["event_id"],
                "source_event_index": int_value(source, "source_event_index"),
                "evidence_decision_ids": evidence_ids,
                "unique_source_match_count": layer_key_counts[key],
            }
        )

    selected_path = trace_dir / "selected_layer_events.csv"
    selected_fields = [
        "selection_id",
        "priority",
        "role",
        "reason",
        "run_id",
        "contract_id",
        "source_revision",
        "trace_mode",
        "rank",
        "worker_id",
        "device_id",
        "request_id",
        "engine_step_id",
        "schedule_id",
        "batch_id",
        "forward_id",
        "layer_idx",
        "layer_occurrence",
        "phase",
        "q_len",
        "past_len",
        "kv_len",
        "layer_type",
        "source_event_id",
        "source_event_index",
        "evidence_decision_ids",
        "unique_source_match_count",
    ]
    with selected_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=selected_fields)
        writer.writeheader()
        for row in selected:
            output = dict(row)
            output["evidence_decision_ids"] = ";".join(
                row["evidence_decision_ids"]
            )
            writer.writerow(output)

    selected_keys = [
        (
            row["request_id"],
            row["engine_step_id"],
            row["forward_id"],
            row["layer_idx"],
            row["layer_occurrence"],
        )
        for row in selected
    ]
    validations = {
        "source_trace_validation_pass": trace_review.get("result") == "PASS",
        "source_is_current_optimized_runtime": (
            trace.get("trace_role")
            == "current_optimized_runtime_algorithmic_trace"
        ),
        "actual_algorithm_decision_evidence_available": trace[
            "decision_evidence"
        ]["actual_algorithm_decision_evidence_available"],
        "small_selected_set": 0 < len(selected) < len(layers),
        "exactly_nine_representative_events": len(selected) == 9,
        "selected_keys_unique": len(selected_keys) == len(set(selected_keys)),
        "every_selected_event_joins_uniquely": all(
            row["unique_source_match_count"] == 1 for row in selected
        ),
        "every_selected_event_has_decision_evidence": all(
            row["evidence_decision_ids"] for row in selected
        ),
        "both_loaded_layer_families_covered": {
            row["layer_type"] for row in selected
        }
        == {"linear_attention", "full_attention"},
        "prefill_and_decode_covered": {row["phase"] for row in selected}
        == {"prefill_chunk", "decode"},
        "initial_and_nonzero_past_prefill_covered": any(
            row["phase"] == "prefill_chunk" and row["past_len"] == 0
            for row in selected
        )
        and any(
            row["phase"] == "prefill_chunk" and row["past_len"] > 0
            for row in selected
        ),
        "tail_prefill_token_count_boundary_covered": any(
            row["forward_id"] == tail_prefill for row in selected
        ),
        "first_and_late_decode_covered": any(
            row["forward_id"] == first_decode for row in selected
        )
        and any(row["forward_id"] == late_decode for row in selected),
        "early_and_late_loaded_depth_covered": (
            linear_ids[0] in {row["layer_idx"] for row in selected}
            and linear_ids[-1] in {row["layer_idx"] for row in selected}
            and full_ids[0] in {row["layer_idx"] for row in selected}
            and full_ids[-1] in {row["layer_idx"] for row in selected}
        ),
        "no_whole_model_selection": len(
            {row["layer_idx"] for row in selected}
        )
        < len({int_value(row, "layer_idx") for row in layers}),
    }
    report = {
        "schema_version": 1,
        "run_id": trace["run_id"],
        "contract_id": trace["contract_id"],
        "trace_tag": trace["trace_tag"],
        "selection_policy": (
            "P0 actual scheduler/cache/state decisions; P1 observed phase, "
            "token-count, and cache boundaries; P2 early/late hybrid-family "
            "representatives; P3 first/late decode state regimes."
        ),
        "authority": {
            "layer_trace": {
                "path": str(layer_path),
                "sha256": sha256_path(layer_path),
            },
            "selection_trace": {
                "path": str(decision_path),
                "sha256": sha256_path(decision_path),
            },
        },
        "selected_manifest": {
            "path": str(selected_path),
            "sha256": sha256_path(selected_path),
            "count": len(selected),
        },
        "selected_events": selected,
        "actual_algorithm_decision_evidence_available": True,
        "qwen35_pruning_or_early_exit_evidence": (
            "not_applicable_loaded_source_disables_multimodal_pruning"
        ),
        "downstream_scope": (
            "Selection only. No DispatchMode, FX, reconstruction, ONNX, or "
            "visualization work was executed."
        ),
        "validation": validations,
        "result": "PASS" if all(validations.values()) else "FAIL",
    }
    report_path = trace_dir / "selection_report.json"
    write_json(report_path, report)

    handoff = {
        "schema_version": 1,
        "kind": "r02_algorithmic_trace_selected_layer_events",
        "status": "complete" if all(validations.values()) else "failed",
        "run_id": trace["run_id"],
        "contract_id": trace["contract_id"],
        "source_revision": trace["source_revision"],
        "trace_mode": "enforce_eager",
        "current_optimized_runtime": True,
        "source_algorithmic_trace": {
            "path": str(trace_path),
            "sha256": sha256_path(trace_path),
        },
        "source_layer_trace": {
            "path": str(layer_path),
            "sha256": sha256_path(layer_path),
        },
        "source_selection_trace": {
            "path": str(decision_path),
            "sha256": sha256_path(decision_path),
        },
        "canonical_selected_manifest": {
            "path": str(selected_path),
            "sha256": sha256_path(selected_path),
            "selected_event_count": len(selected),
            "ordered_selection_ids": [
                row["selection_id"] for row in selected
            ],
            "ordered_source_event_ids": [
                row["source_event_id"] for row in selected
            ],
        },
        "selection_report": {
            "path": str(report_path),
            "sha256": sha256_path(report_path),
        },
        "join_key": [
            "run_id",
            "contract_id",
            "rank",
            "worker_id",
            "request_id",
            "engine_step_id",
            "forward_id",
            "layer_idx",
            "layer_occurrence",
        ],
        "must_preserve": [
            "Use the exact selected manifest order and source event IDs.",
            "Keep enforce_eager algorithm structure separate from production compiled timing evidence.",
            "Treat operator_flops.csv as theoretical FLOPs, never measured ROCm/DCU latency.",
            "Do not claim concurrent or distributed coverage from this max_concurrency=1 run.",
            "Do not fabricate pruning or early-exit decisions for Qwen3.5.",
        ],
        "validation": validations,
    }
    handoff_path = trace_dir / "selection_handoff.json"
    write_json(handoff_path, handoff)

    summary = {
        "result": report["result"],
        "selected_event_count": len(selected),
        "selected_manifest": {
            "path": str(selected_path),
            "sha256": sha256_path(selected_path),
        },
        "selection_report": {
            "path": str(report_path),
            "sha256": sha256_path(report_path),
        },
        "selection_handoff": {
            "path": str(handoff_path),
            "sha256": sha256_path(handoff_path),
        },
        "validation": validations,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not all(validations.values()):
        failed = sorted(key for key, value in validations.items() if not value)
        raise SystemExit(f"R02 selection validation failed: {failed}")


if __name__ == "__main__":
    main()
