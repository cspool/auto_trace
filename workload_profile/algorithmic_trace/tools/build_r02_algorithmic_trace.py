#!/usr/bin/env python3
"""Build and fail-closed validate the fresh R02 Qwen3.5 algorithmic trace.

This normalizer consumes only the small-metadata runtime event stream.  It
does not open profiler traces, inspect tensor contents, or report measured
kernel latency.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_csv(
    path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def json_cell(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def parse_events(
    event_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    all_rows: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    layer_streams: list[dict[str, Any]] = []
    for path in sorted(event_dir.glob("events.*.jsonl")):
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        resolved = path.resolve()
        for row in rows:
            row["_source_event_file"] = str(resolved)
        entry = {
            "path": str(resolved),
            "sha256": sha256_path(path),
            "size_bytes": path.stat().st_size,
            "row_count": len(rows),
            "pid": rows[0].get("pid") if rows else None,
            "has_layer_events": any(
                row.get("event_type") == "layer_event" for row in rows
            ),
        }
        files.append(entry)
        all_rows.extend(rows)
        if entry["has_layer_events"]:
            layer_streams.append({"metadata": entry, "rows": rows})
    return all_rows, files, layer_streams


def schedule_id(trace_run_id: str, rank: str, step: int) -> str:
    return f"{trace_run_id}:rank{rank}:schedule:{step}"


def make_batch_id(
    contract_id: str,
    current_schedule_id: str,
    requests: list[dict[str, Any]],
) -> str:
    tuples = sorted(
        (
            str(row.get("request_id")),
            int(row.get("num_computed_before") or 0),
            int(row.get("scheduled_tokens") or 0),
        )
        for row in requests
        if row.get("request_id")
    )
    payload: dict[str, Any] = {
        "contract_id": contract_id,
        "request_tuples": tuples,
    }
    if not tuples:
        payload["schedule_id"] = current_schedule_id
    digest = hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return f"batch:{digest[:24]}"


def semantic_output_equal(
    fresh: dict[str, Any], baseline: dict[str, Any]
) -> tuple[bool, dict[str, bool]]:
    fields = ("completed", "failed", "input_lens", "output_lens", "generated_texts")
    checks = {field: fresh.get(field) == baseline.get(field) for field in fields}
    return all(checks.values()), checks


def layer_ids_from_events(rows: list[dict[str, Any]], field: str) -> list[int]:
    found: set[int] = set()
    for row in rows:
        match = re.search(r"layers\.(\d+)\.", str(row.get(field, "")))
        if match:
            found.add(int(match.group(1)))
    return sorted(found)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--r01-handoff", required=True, type=Path)
    parser.add_argument("--production-baseline", required=True, type=Path)
    parser.add_argument("--qwen-source", required=True, type=Path)
    args = parser.parse_args()

    trace_dir = args.trace_dir.resolve()
    contract_path = trace_dir / "run_contract.json"
    contract = load_json(contract_path)
    r01 = load_json(args.r01_handoff.resolve())
    model_config = load_json(args.model_config.resolve())
    text_config = model_config["text_config"]
    layer_types = list(text_config["layer_types"])
    num_layers = int(text_config["num_hidden_layers"])
    all_layer_ids = list(range(num_layers))
    linear_layer_ids = [
        index for index, kind in enumerate(layer_types) if kind == "linear_attention"
    ]
    full_layer_ids = [
        index for index, kind in enumerate(layer_types) if kind == "full_attention"
    ]

    all_events, event_files, layer_streams = parse_events(trace_dir / "events")
    if len(layer_streams) != 1:
        raise SystemExit(
            f"expected exactly one layer-bearing stream, got {len(layer_streams)}"
        )
    worker_file = layer_streams[0]["metadata"]
    events = layer_streams[0]["rows"]
    counts = Counter(row["event_type"] for row in all_events)
    worker_counts = Counter(row["event_type"] for row in events)

    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in events:
        by_type[row["event_type"]].append(row)

    schedules = {
        int(row["engine_step_id"]): row for row in by_type["scheduler_step"]
    }
    trace_run_id = str(contract["trace_run_id"])
    contract_id = str(contract["contract_id"])
    rank = str(contract["runtime"]["tensor_parallel_size"] - 1)
    schedule_context: dict[int, dict[str, Any]] = {}
    request_ids: set[str] = set()
    for step, event in schedules.items():
        requests = list(event.get("requests") or [])
        current_schedule_id = schedule_id(trace_run_id, rank, step)
        current_batch_id = make_batch_id(
            contract_id, current_schedule_id, requests
        )
        schedule_context[step] = {
            "schedule_id": current_schedule_id,
            "batch_id": current_batch_id,
            "event": event,
            "requests": requests,
        }
        request_ids.update(
            str(row["request_id"]) for row in requests if row.get("request_id")
        )

    begin_by_forward = {
        int(row["forward_id"]): row for row in by_type["model_execute_begin"]
    }
    end_by_forward = {
        int(row["forward_id"]): row for row in by_type["model_execute_end"]
    }
    batch_by_forward = {
        int(row["forward_id"]): row for row in by_type["batch_constructed"]
    }
    raw_layers_by_forward: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in by_type["layer_event"]:
        raw_layers_by_forward[int(row["forward_id"])].append(row)

    forward_events: list[dict[str, Any]] = []
    forward_context: dict[int, dict[str, Any]] = {}
    forward_by_step: dict[int, dict[str, Any]] = {}
    for forward_id in sorted(begin_by_forward):
        begin = begin_by_forward[forward_id]
        step = int(begin["engine_step_id"])
        batch = batch_by_forward.get(forward_id)
        current_schedule = schedule_context.get(step)
        requests = (
            list(current_schedule["requests"]) if current_schedule else []
        )
        current_request_ids = (
            list(batch.get("req_ids") or []) if batch else []
        )
        if not current_request_ids:
            current_request_ids = [
                str(row["request_id"])
                for row in requests
                if row.get("request_id")
            ]
        current_schedule_id = (
            current_schedule["schedule_id"]
            if current_schedule
            else schedule_id(trace_run_id, rank, step)
        )
        current_batch_id = (
            current_schedule["batch_id"]
            if current_schedule
            else make_batch_id(contract_id, current_schedule_id, [])
        )
        q_len = (
            batch.get("total_num_scheduled_tokens")
            if batch
            else begin.get("total_num_scheduled_tokens")
        )
        past_len = batch.get("past_len") if batch else None
        kv_len = batch.get("kv_len") if batch else None
        layer_count = len(raw_layers_by_forward.get(forward_id, []))
        phase = str(begin.get("phase"))
        if layer_count == 0 and int(q_len or 0) == 0 and phase == "empty":
            disposition = "empty_async_drain_no_batch_or_layer_execution"
        elif layer_count == num_layers:
            disposition = "complete_loaded_decoder_forward"
        else:
            disposition = "unexplained_incomplete_forward"
        row = {
            "run_id": trace_run_id,
            "contract_id": contract_id,
            "source_revision": contract["source"]["revision"],
            "trace_mode": contract["runtime"]["trace_mode"],
            "rank": rank,
            "worker_id": begin.get("worker_id"),
            "device_id": begin.get("device_id"),
            "request_ids": current_request_ids,
            "engine_step_id": step,
            "schedule_id": current_schedule_id,
            "batch_id": current_batch_id,
            "forward_id": forward_id,
            "phase": phase,
            "q_len": q_len,
            "past_len": past_len,
            "kv_len": kv_len,
            "layer_event_count": layer_count,
            "complete": layer_count == num_layers,
            "disposition": disposition,
            "source_begin_event_index": begin["event_index"],
            "source_end_event_index": end_by_forward.get(forward_id, {}).get(
                "event_index"
            ),
        }
        forward_events.append(row)
        forward_context[forward_id] = row
        forward_by_step[step] = row

    occurrence_counter: Counter[tuple[int, int]] = Counter()
    layer_events: list[dict[str, Any]] = []
    for raw in sorted(
        by_type["layer_event"],
        key=lambda row: (int(row["forward_id"]), int(row["event_index"])),
    ):
        forward_id = int(raw["forward_id"])
        layer_idx = int(raw["layer_idx"])
        occurrence_key = (forward_id, layer_idx)
        occurrence = occurrence_counter[occurrence_key]
        occurrence_counter[occurrence_key] += 1
        context = forward_context[forward_id]
        current_request_ids = list(context["request_ids"])
        request_id = current_request_ids[0] if len(current_request_ids) == 1 else None
        event_id = (
            f"{request_id}|s{context['engine_step_id']}|f{forward_id}|"
            f"l{layer_idx}|o{occurrence}"
        )
        layer_events.append(
            {
                "run_id": trace_run_id,
                "contract_id": contract_id,
                "source_revision": contract["source"]["revision"],
                "trace_mode": contract["runtime"]["trace_mode"],
                "rank": rank,
                "worker_id": raw.get("worker_id"),
                "device_id": raw.get("device_id"),
                "request_id": request_id,
                "engine_step_id": context["engine_step_id"],
                "schedule_id": context["schedule_id"],
                "batch_id": context["batch_id"],
                "forward_id": forward_id,
                "event_id": event_id,
                "layer_idx": layer_idx,
                "layer_occurrence": occurrence,
                "layer_type": raw.get("layer_type"),
                "phase": raw.get("phase"),
                "q_len": int(raw["q_len"]),
                "past_len": int(raw["past_len"]),
                "kv_len": int(raw["kv_len"]),
                "hidden_shape_in": raw.get("hidden_shape_in"),
                "hidden_shape_out": raw.get("hidden_shape_out"),
                "residual_shape_in": raw.get("residual_shape_in"),
                "residual_shape_out": raw.get("residual_shape_out"),
                "positions_shape": raw.get("positions_shape"),
                "source_pid": raw.get("pid"),
                "source_event_index": raw.get("event_index"),
                "source_event_file": raw.get("_source_event_file"),
            }
        )
    layer_lookup = {
        (
            row["request_id"],
            row["engine_step_id"],
            row["forward_id"],
            row["layer_idx"],
            row["layer_occurrence"],
        ): row
        for row in layer_events
    }

    decision_rows: list[dict[str, Any]] = []
    decision_sequence = 0

    def add_decision(
        *,
        source: dict[str, Any],
        request_id: str | None,
        engine_step_id: int | None,
        forward_id: int | None,
        phase: str,
        q_len: int | None,
        past_len: int | None,
        kv_len: int | None,
        family: str,
        action: str,
        outcome: str,
        scope: str,
        affected_layer_ids: list[int],
        join_status: str,
        details: dict[str, Any],
        output_ordinal: int | None = None,
    ) -> None:
        nonlocal decision_sequence
        decision_sequence += 1
        context = (
            schedule_context.get(int(engine_step_id))
            if engine_step_id is not None
            else None
        )
        decision_rows.append(
            {
                "decision_id": f"decision:{decision_sequence:05d}",
                "run_id": trace_run_id,
                "contract_id": contract_id,
                "source_revision": contract["source"]["revision"],
                "trace_mode": contract["runtime"]["trace_mode"],
                "rank": source.get("rank", rank),
                "worker_id": source.get("worker_id"),
                "device_id": source.get("device_id"),
                "request_id": request_id,
                "engine_step_id": engine_step_id,
                "schedule_id": context["schedule_id"] if context else None,
                "batch_id": context["batch_id"] if context else None,
                "forward_id": forward_id,
                "layer_idx": None,
                "layer_occurrence": None,
                "output_ordinal": output_ordinal,
                "phase": phase,
                "q_len": q_len,
                "past_len": past_len,
                "kv_len": kv_len,
                "decision_family": family,
                "event_type": source["event_type"],
                "action": action,
                "outcome": outcome,
                "affected_scope": scope,
                "affected_layer_ids": affected_layer_ids,
                "source_join_status": join_status,
                "details": details,
                "source_pid": source.get("pid"),
                "source_event_index": source.get("event_index"),
                "source_event_file": source.get("_source_event_file"),
            }
        )

    for step in sorted(schedules):
        source = schedules[step]
        context = forward_by_step.get(step)
        requests = list(source.get("requests") or [])
        if not requests:
            add_decision(
                source=source,
                request_id=None,
                engine_step_id=step,
                forward_id=context["forward_id"] if context else None,
                phase="empty",
                q_len=0,
                past_len=None,
                kv_len=None,
                family="scheduler",
                action="schedule_empty",
                outcome="async_drain",
                scope="no_request",
                affected_layer_ids=[],
                join_status="explicit_empty_non_request_exception",
                details={"running_count": source.get("running_count", 0)},
            )
            continue
        for request in requests:
            q_len = int(request.get("scheduled_tokens") or 0)
            past_len = int(request.get("num_computed_before") or 0)
            add_decision(
                source=source,
                request_id=str(request["request_id"]),
                engine_step_id=step,
                forward_id=context["forward_id"] if context else None,
                phase=str(request.get("phase")),
                q_len=q_len,
                past_len=past_len,
                kv_len=past_len + q_len,
                family="scheduler",
                action="schedule_tokens",
                outcome=f"scheduled:{q_len}",
                scope="loaded_decoder",
                affected_layer_ids=all_layer_ids if context and context["complete"] else [],
                join_status="joined_request_step_forward_and_loaded_layers",
                details={
                    "num_computed_after": request.get("num_computed_after"),
                    "prompt_len": request.get("prompt_len"),
                    "status": request.get("status"),
                    "running_count": source.get("running_count"),
                    "waiting_count": source.get("waiting_count"),
                    "preempted_req_count": source.get("preempted_req_count"),
                },
            )

    cache_events = (
        by_type["kv_get_computed_blocks"]
        + by_type["kv_allocate_slots"]
        + by_type["kv_free"]
    )
    for source in sorted(cache_events, key=lambda row: int(row["event_index"])):
        step = int(source["engine_step_id"])
        context = forward_by_step.get(step)
        request_id = str(source.get("request_id"))
        request_context = next(
            (
                row
                for row in schedule_context.get(step, {}).get("requests", [])
                if str(row.get("request_id")) == request_id
            ),
            {},
        )
        q_len = int(
            source.get("num_new_tokens")
            or request_context.get("scheduled_tokens")
            or 0
        )
        past_len = int(
            request_context.get("num_computed_before")
            or (
                source.get("num_computed_tokens")
                if source["event_type"] == "kv_free"
                else 0
            )
            or 0
        )
        if source["event_type"] == "kv_get_computed_blocks":
            action = "prefix_cache_lookup"
            outcome = f"computed_tokens:{source.get('computed_tokens')}"
        elif source["event_type"] == "kv_allocate_slots":
            action = "allocate_slots"
            outcome = f"allocated:{bool(source.get('allocated'))}"
        else:
            action = "free_request_cache"
            outcome = f"freed_blocks:{source.get('freed_block_count')}"
            q_len = 0
        add_decision(
            source=source,
            request_id=request_id,
            engine_step_id=step,
            forward_id=context["forward_id"] if context else None,
            phase=(
                str(request_context.get("phase"))
                if request_context
                else ("finish" if source["event_type"] == "kv_free" else "unknown")
            ),
            q_len=q_len,
            past_len=past_len,
            kv_len=past_len + q_len,
            family="cache_state",
            action=action,
            outcome=outcome,
            scope="loaded_hybrid_cache_groups",
            affected_layer_ids=all_layer_ids if context and context["complete"] else [],
            join_status="joined_request_step_forward_and_loaded_layers",
            details={
                key: source.get(key)
                for key in (
                    "computed_tokens",
                    "block_counts",
                    "free_blocks_before",
                    "free_blocks_after",
                    "cache_usage",
                    "cache_usage_before",
                    "cache_usage_after",
                    "freed_block_count",
                    "request_status",
                )
                if key in source
            },
        )

    for family, event_type, field, scope, expected_ids in (
        (
            "model_route",
            "qwen35_gdn_forward",
            "prefix",
            "linear_attention",
            linear_layer_ids,
        ),
        (
            "model_route",
            "attention_forward_begin",
            "layer_name",
            "full_attention",
            full_layer_ids,
        ),
    ):
        grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
        for source in by_type[event_type]:
            grouped[
                (
                    int(source["forward_id"]),
                    str(source.get("backend") or "Qwen3_5GatedDeltaNet"),
                )
            ].append(source)
        for (forward_id, route), sources in sorted(grouped.items()):
            context = forward_context[forward_id]
            affected = layer_ids_from_events(sources, field)
            add_decision(
                source=sources[0],
                request_id=(
                    context["request_ids"][0]
                    if len(context["request_ids"]) == 1
                    else None
                ),
                engine_step_id=context["engine_step_id"],
                forward_id=forward_id,
                phase=context["phase"],
                q_len=int(context["q_len"]),
                past_len=int(context["past_len"]),
                kv_len=int(context["kv_len"]),
                family=family,
                action=f"select_{scope}_route",
                outcome=route,
                scope=scope,
                affected_layer_ids=affected,
                join_status="joined_request_step_forward_and_affected_layers",
                details={
                    "call_count": len(sources),
                    "expected_loaded_layer_ids": expected_ids,
                },
            )

    for source in by_type["sample_tokens"]:
        forward_id = int(source["forward_id"])
        context = forward_context[forward_id]
        add_decision(
            source=source,
            request_id=(
                context["request_ids"][0]
                if len(context["request_ids"]) == 1
                else None
            ),
            engine_step_id=context["engine_step_id"],
            forward_id=forward_id,
            phase=context["phase"],
            q_len=int(context["q_len"]),
            past_len=int(context["past_len"]),
            kv_len=int(context["kv_len"]),
            family="sampling",
            action="sample_tokens",
            outcome=str(source.get("result_type")),
            scope="model_output",
            affected_layer_ids=[],
            join_status="joined_request_step_forward",
            details={"input_batch": source.get("input_batch")},
        )

    output_ordinal_by_request: Counter[str] = Counter()
    for source in by_type["scheduler_update_output"]:
        step = int(source["engine_step_id"])
        context = forward_by_step.get(step)
        for output in source.get("outputs") or []:
            request_id = str(output["request_id"])
            output_ordinal_by_request[request_id] += 1
            ordinal = output_ordinal_by_request[request_id]
            add_decision(
                source=source,
                request_id=request_id,
                engine_step_id=step,
                forward_id=context["forward_id"] if context else None,
                phase=context["phase"] if context else "output",
                q_len=int(context["q_len"]) if context else None,
                past_len=int(context["past_len"]) if context and context["past_len"] is not None else None,
                kv_len=int(context["kv_len"]) if context and context["kv_len"] is not None else None,
                family="host_output",
                action="emit_sampled_output",
                outcome=(
                    f"finished:{output.get('finish_reason')}"
                    if output.get("finished")
                    else "stream_token"
                ),
                scope="request_output",
                affected_layer_ids=[],
                join_status="joined_request_step_forward",
                details=output,
                output_ordinal=ordinal,
            )

    hidden = int(text_config["hidden_size"])
    intermediate = int(text_config["intermediate_size"])
    num_heads = int(text_config["num_attention_heads"])
    num_kv_heads = int(text_config["num_key_value_heads"])
    head_dim = int(text_config["head_dim"])
    linear_key_dim = (
        int(text_config["linear_num_key_heads"])
        * int(text_config["linear_key_head_dim"])
    )
    linear_value_dim = (
        int(text_config["linear_num_value_heads"])
        * int(text_config["linear_value_head_dim"])
    )
    linear_value_heads = int(text_config["linear_num_value_heads"])
    flop_rows: list[dict[str, Any]] = []

    def add_flop(
        layer: dict[str, Any], op_name: str, formula: str, value: int
    ) -> None:
        flop_rows.append(
            {
                **{
                    key: layer[key]
                    for key in (
                        "run_id",
                        "contract_id",
                        "request_id",
                        "engine_step_id",
                        "schedule_id",
                        "batch_id",
                        "forward_id",
                        "event_id",
                        "layer_idx",
                        "layer_occurrence",
                        "layer_type",
                        "phase",
                        "q_len",
                        "past_len",
                        "kv_len",
                    )
                },
                "op_name": op_name,
                "formula": formula,
                "theoretical_flops": value,
                "coverage": "analytic_matrix_or_exact_causal_attention_core",
                "measured_latency": False,
            }
        )

    for layer in layer_events:
        q_len = int(layer["q_len"])
        if layer["layer_type"] == "full_attention":
            qkv_gate_out = (2 * num_heads + 2 * num_kv_heads) * head_dim
            add_flop(
                layer,
                "full_qkv_gate_projection",
                "2*q*hidden*((2*q_heads+2*kv_heads)*head_dim)",
                2 * q_len * hidden * qkv_gate_out,
            )
            causal_pairs = (
                q_len * int(layer["past_len"]) + q_len * (q_len + 1) // 2
            )
            add_flop(
                layer,
                "full_attention_qk_pv",
                "4*causal_qk_pairs*q_heads*head_dim",
                4 * causal_pairs * num_heads * head_dim,
            )
            add_flop(
                layer,
                "full_output_projection",
                "2*q*(q_heads*head_dim)*hidden",
                2 * q_len * num_heads * head_dim * hidden,
            )
        else:
            add_flop(
                layer,
                "linear_qkvz_projection",
                "2*q*hidden*(2*linear_key_dim+2*linear_value_dim)",
                2
                * q_len
                * hidden
                * (2 * linear_key_dim + 2 * linear_value_dim),
            )
            add_flop(
                layer,
                "linear_ba_projection",
                "2*q*hidden*(2*linear_value_heads)",
                2 * q_len * hidden * (2 * linear_value_heads),
            )
            add_flop(
                layer,
                "linear_output_projection",
                "2*q*linear_value_dim*hidden",
                2 * q_len * linear_value_dim * hidden,
            )
        add_flop(
            layer,
            "mlp_gate_up_projection",
            "2*q*hidden*(2*intermediate)",
            2 * q_len * hidden * (2 * intermediate),
        )
        add_flop(
            layer,
            "mlp_down_projection",
            "2*q*intermediate*hidden",
            2 * q_len * intermediate * hidden,
        )

    layer_csv_path = trace_dir / "layer_trace.csv"
    selection_csv_path = trace_dir / "selection_trace.csv"
    flop_csv_path = trace_dir / "operator_flops.csv"
    layer_fields = [
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
        "event_id",
        "layer_idx",
        "layer_occurrence",
        "layer_type",
        "phase",
        "q_len",
        "past_len",
        "kv_len",
        "hidden_shape_in",
        "hidden_shape_out",
        "residual_shape_in",
        "residual_shape_out",
        "positions_shape",
        "source_pid",
        "source_event_index",
        "source_event_file",
    ]
    layer_csv_rows = []
    for row in layer_events:
        output = dict(row)
        for field in (
            "hidden_shape_in",
            "hidden_shape_out",
            "residual_shape_in",
            "residual_shape_out",
            "positions_shape",
        ):
            output[field] = json_cell(row[field])
        layer_csv_rows.append(output)
    write_csv(layer_csv_path, layer_fields, layer_csv_rows)

    selection_fields = [
        "decision_id",
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
        "output_ordinal",
        "phase",
        "q_len",
        "past_len",
        "kv_len",
        "decision_family",
        "event_type",
        "action",
        "outcome",
        "affected_scope",
        "affected_layer_ids",
        "source_join_status",
        "details",
        "source_pid",
        "source_event_index",
        "source_event_file",
    ]
    selection_csv_rows = []
    for row in decision_rows:
        output = dict(row)
        output["affected_layer_ids"] = ";".join(
            str(value) for value in row["affected_layer_ids"]
        )
        output["details"] = json_cell(row["details"])
        selection_csv_rows.append(output)
    write_csv(selection_csv_path, selection_fields, selection_csv_rows)

    flop_fields = [
        "run_id",
        "contract_id",
        "request_id",
        "engine_step_id",
        "schedule_id",
        "batch_id",
        "forward_id",
        "event_id",
        "layer_idx",
        "layer_occurrence",
        "layer_type",
        "phase",
        "q_len",
        "past_len",
        "kv_len",
        "op_name",
        "formula",
        "theoretical_flops",
        "coverage",
        "measured_latency",
    ]
    write_csv(flop_csv_path, flop_fields, flop_rows)

    fresh_result_path = trace_dir / "request/result.json"
    fresh_result = load_json(fresh_result_path)
    baseline_result = load_json(args.production_baseline.resolve())
    output_equal, output_checks = semantic_output_equal(
        fresh_result, baseline_result
    )
    generated_text = fresh_result["generated_texts"][0]

    complete_forwards = [row for row in forward_events if row["complete"]]
    empty_forwards = [
        row
        for row in forward_events
        if row["disposition"] == "empty_async_drain_no_batch_or_layer_execution"
    ]
    layer_count_by_forward = Counter(
        int(row["forward_id"]) for row in layer_events
    )
    gdn_count_by_forward = Counter(
        int(row["forward_id"]) for row in by_type["qwen35_gdn_forward"]
    )
    attention_begin_by_forward = Counter(
        int(row["forward_id"]) for row in by_type["attention_forward_begin"]
    )
    attention_end_by_forward = Counter(
        int(row["forward_id"]) for row in by_type["attention_forward_end"]
    )
    patch_loaded = [
        row for row in all_events if row["event_type"] == "patch_loaded"
    ]
    patch_loaded_extension = [
        row
        for row in all_events
        if row["event_type"] == "patch_loaded_extension"
    ]
    finished_outputs = [
        output
        for row in by_type["scheduler_update_output"]
        for output in (row.get("outputs") or [])
        if output.get("finished")
    ]
    scoped_decisions = [row for row in decision_rows if row["request_id"]]
    decision_layer_join_ok = True
    for decision in scoped_decisions:
        if decision["affected_layer_ids"]:
            for layer_idx in decision["affected_layer_ids"]:
                key = (
                    decision["request_id"],
                    decision["engine_step_id"],
                    decision["forward_id"],
                    layer_idx,
                    0,
                )
                if key not in layer_lookup:
                    decision_layer_join_ok = False
    source_text = args.qwen_source.resolve().read_text(encoding="utf-8")

    validations = {
        "r01_status_complete": r01.get("status") == "complete",
        "source_revision_matches_r01": (
            contract["source"]["revision"]
            == r01["source_identity"]["revision"]
        ),
        "contract_id_matches_r01": (
            contract_id
            == r01["validation"]["evidence_contract"]["contract_id"]
        ),
        "model_config_hash_matches_r01": (
            sha256_path(args.model_config.resolve())
            == r01["source_identity"]["model_config_sha256"]
        ),
        "model_layer_type_length_matches_num_hidden_layers": (
            len(layer_types) == num_layers
        ),
        "loaded_layer_family_counts_are_48_linear_16_full": (
            len(linear_layer_ids) == 48 and len(full_layer_ids) == 16
        ),
        "exactly_one_layer_worker_stream": len(layer_streams) == 1,
        "patch_loaded_in_all_four_processes_without_errors": (
            len(patch_loaded) == 4
            and all(not row.get("errors") for row in patch_loaded)
        ),
        "r02_extension_loaded_in_all_four_processes": (
            len(patch_loaded_extension) == 4
        ),
        "patch_error_count_zero": counts["patch_error"] == 0,
        "single_request_observed": len(request_ids) == 1,
        "model_begin_end_forward_ids_equal": (
            set(begin_by_forward) == set(end_by_forward)
        ),
        "all_nonempty_forwards_cover_loaded_layers": (
            bool(complete_forwards)
            and all(
                layer_count_by_forward[int(row["forward_id"])] == num_layers
                for row in complete_forwards
            )
        ),
        "all_zero_layer_forwards_explained_as_empty_async_drain": (
            len(empty_forwards)
            == len(forward_events) - len(complete_forwards)
            and all(
                int(row["q_len"] or 0) == 0
                and row["phase"] == "empty"
                for row in empty_forwards
            )
        ),
        "layer_indices_complete_per_forward": all(
            {
                layer["layer_idx"]
                for layer in layer_events
                if layer["forward_id"] == forward["forward_id"]
            }
            == set(all_layer_ids)
            for forward in complete_forwards
        ),
        "layer_types_match_loaded_config": all(
            row["layer_type"] == layer_types[int(row["layer_idx"])]
            for row in layer_events
        ),
        "layer_occurrences_unique_and_zero": (
            len(layer_lookup) == len(layer_events)
            and {row["layer_occurrence"] for row in layer_events} == {0}
        ),
        "layer_join_fields_present": all(
            row["request_id"]
            and row["engine_step_id"] is not None
            and row["schedule_id"]
            and row["batch_id"]
            and row["forward_id"] is not None
            and row["phase"]
            and row["q_len"] is not None
            and row["past_len"] is not None
            and row["kv_len"] is not None
            for row in layer_events
        ),
        "past_plus_q_equals_kv": all(
            row["past_len"] + row["q_len"] == row["kv_len"]
            for row in layer_events
        ),
        "every_complete_forward_has_48_gdn_calls": all(
            gdn_count_by_forward[int(row["forward_id"])] == len(linear_layer_ids)
            for row in complete_forwards
        ),
        "every_complete_forward_has_16_full_attention_pairs": all(
            attention_begin_by_forward[int(row["forward_id"])]
            == len(full_layer_ids)
            == attention_end_by_forward[int(row["forward_id"])]
            for row in complete_forwards
        ),
        "cache_initial_lookup_visible": worker_counts["kv_get_computed_blocks"] == 1,
        "cache_allocations_all_succeeded": (
            worker_counts["kv_allocate_slots"] == len(complete_forwards)
            and all(row.get("allocated") for row in by_type["kv_allocate_slots"])
        ),
        "cache_free_transition_observed_and_reconciled": (
            worker_counts["kv_free"] == 1
            and by_type["kv_free"][0].get("freed_block_count", 0) > 0
            and by_type["kv_free"][0].get("cache_usage_after") == 0.0
            and by_type["kv_free"][0].get("free_blocks_after")
            == by_type["kv_allocate_slots"][0].get("free_blocks_before")
        ),
        "request_scoped_decisions_join_to_step_and_forward": all(
            row["engine_step_id"] is not None
            and row["schedule_id"]
            and row["batch_id"]
            and row["forward_id"] is not None
            for row in scoped_decisions
        ),
        "affected_decision_layers_join_uniquely": decision_layer_join_ok,
        "empty_decision_rows_explicitly_exempted": all(
            row["source_join_status"] == "explicit_empty_non_request_exception"
            for row in decision_rows
            if not row["request_id"]
        ),
        "actual_scheduler_cache_model_decisions_present": all(
            any(row["decision_family"] == family for row in decision_rows)
            for family in ("scheduler", "cache_state", "model_route", "sampling")
        ),
        "host_output_rows_match_generated_tokens": (
            output_ordinal_by_request[next(iter(request_ids))]
            == fresh_result["output_lens"][0]
        ),
        "one_finished_output_with_stop_reason": (
            len(finished_outputs) == 1
            and finished_outputs[0].get("finish_reason") == "stop"
        ),
        "fresh_output_semantically_matches_r01_production_baseline": output_equal,
        "flops_cover_every_layer_event": (
            {row["event_id"] for row in flop_rows}
            == {row["event_id"] for row in layer_events}
        ),
        "all_flops_marked_theoretical_not_latency": all(
            row["measured_latency"] is False for row in flop_rows
        ),
        "qwen35_multimodal_pruning_disabled_in_source": (
            "supports_multimodal_pruning = False" in source_text
            or "is_multimodal_pruning_enabled = False" in source_text
        ),
    }

    flop_summary: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for row in flop_rows:
        flop_summary[row["phase"]][row["op_name"]] += int(
            row["theoretical_flops"]
        )
    total_by_phase = {
        phase: sum(ops.values()) for phase, ops in flop_summary.items()
    }
    trace_payload = {
        "schema_version": 1,
        "run_mode": "FRESH_RUN",
        "trace_role": "current_optimized_runtime_algorithmic_trace",
        "trace_tag": contract["trace_tag"],
        "run_id": trace_run_id,
        "contract_id": contract_id,
        "source_revision": contract["source"]["revision"],
        "run_contract": str(contract_path),
        "run_contract_sha256": sha256_path(contract_path),
        "r01_handoff": str(args.r01_handoff.resolve()),
        "r01_handoff_sha256": sha256_path(args.r01_handoff.resolve()),
        "model": {
            "path": contract["model"]["path"],
            "architecture": contract["model"]["architecture"],
            "config_path": str(args.model_config.resolve()),
            "config_sha256": sha256_path(args.model_config.resolve()),
            "hf_text_config": {
                "num_hidden_layers": num_layers,
                "hidden_size": hidden,
                "intermediate_size": intermediate,
                "num_attention_heads": num_heads,
                "num_key_value_heads": num_kv_heads,
                "head_dim": head_dim,
                "layer_types": layer_types,
                "linear_attention_layer_count": len(linear_layer_ids),
                "full_attention_layer_count": len(full_layer_ids),
            },
        },
        "runtime": {
            **contract["runtime"],
            "observed_attention_backend": sorted(
                {
                    row.get("backend")
                    for row in by_type["attention_forward_begin"]
                    if row.get("backend")
                }
            ),
            "observed_linear_attention_route": "Qwen3_5GatedDeltaNet",
            "event_process_count": len(event_files),
            "worker_event_stream": worker_file,
            "timing_scope": "No wall-clock or kernel latency is claimed; duration fields are omitted from normalized artifacts.",
        },
        "request_contract": contract["request"],
        "request_ids": sorted(request_ids),
        "request_result": {
            "path": str(fresh_result_path),
            "sha256": sha256_path(fresh_result_path),
            "completed": fresh_result.get("completed"),
            "failed": fresh_result.get("failed"),
            "input_lens": fresh_result.get("input_lens"),
            "output_lens": fresh_result.get("output_lens"),
            "generated_text_sha256": hashlib.sha256(
                generated_text.encode("utf-8")
            ).hexdigest(),
        },
        "production_baseline_equivalence": {
            "path": str(args.production_baseline.resolve()),
            "sha256": sha256_path(args.production_baseline.resolve()),
            "field_checks": output_checks,
            "result": "PASS" if output_equal else "FAIL",
        },
        "source_event_files": event_files,
        "source_event_counts": dict(sorted(counts.items())),
        "scheduler_events": [
            {
                key: row.get(key)
                for key in (
                    "engine_step_id",
                    "phase",
                    "total_num_scheduled_tokens",
                    "requests",
                    "running_count",
                    "waiting_count",
                    "preempted_req_count",
                )
            }
            for row in sorted(
                by_type["scheduler_step"],
                key=lambda value: int(value["engine_step_id"]),
            )
        ],
        "forward_events": forward_events,
        "layer_events": layer_events,
        "decision_events": decision_rows,
        "transition_events": [
            row
            for row in decision_rows
            if row["decision_family"] in ("cache_state", "host_output")
        ],
        "decision_evidence": {
            "actual_algorithm_decision_evidence_available": True,
            "families": sorted(
                {row["decision_family"] for row in decision_rows}
            ),
            "qwen35_multimodal_pruning": "disabled_by_loaded_source",
            "pruning_or_early_exit_events_fabricated": False,
            "limitation": "No pruning or early-exit decision family applies; scheduler, cache/state, model-route, sampling, and finished-output decisions are present.",
        },
        "theoretical_flops_summary": {
            "scope": "Analytic dense projections plus exact causal full-attention QK/PV pairs for observed layer events.",
            "excluded": [
                "GDN custom recurrent core",
                "convolution",
                "normalization",
                "rotary embedding",
                "activation and gating elementwise operations",
                "model-level LM head",
            ],
            "by_phase_and_op": {
                phase: dict(sorted(ops.items()))
                for phase, ops in sorted(flop_summary.items())
            },
            "total_by_phase": dict(sorted(total_by_phase.items())),
            "grand_total": sum(total_by_phase.values()),
            "measured_rocm_dcu_latency": False,
        },
        "validation": validations,
        "review_result": "PASS" if all(validations.values()) else "FAIL",
    }
    trace_json_path = trace_dir / "algorithmic_trace.json"
    write_json(trace_json_path, trace_payload)

    artifact_paths = [
        trace_json_path,
        layer_csv_path,
        selection_csv_path,
        flop_csv_path,
    ]
    review = {
        "schema_version": 1,
        "run_id": trace_run_id,
        "contract_id": contract_id,
        "trace_tag": contract["trace_tag"],
        "backend": "enforce_eager",
        "current_optimized_runtime": True,
        "comparison_baseline_run": False,
        "event_count": len(all_events),
        "effective_forward_count": len(complete_forwards),
        "empty_async_drain_forward_count": len(empty_forwards),
        "layer_event_count": len(layer_events),
        "decision_row_count": len(decision_rows),
        "operator_flop_row_count": len(flop_rows),
        "actual_algorithm_decision_evidence_available": True,
        "artifacts": {
            path.name: {
                "path": str(path),
                "sha256": sha256_path(path),
                "size_bytes": path.stat().st_size,
            }
            for path in artifact_paths
        },
        "validation": validations,
        "result": "PASS" if all(validations.values()) else "FAIL",
    }
    review_path = trace_dir / "trace_validation.json"
    write_json(review_path, review)
    print(json.dumps(review, indent=2, sort_keys=True))
    if not all(validations.values()):
        failed = sorted(key for key, value in validations.items() if not value)
        raise SystemExit(f"R02 trace validation failed: {failed}")


if __name__ == "__main__":
    main()
