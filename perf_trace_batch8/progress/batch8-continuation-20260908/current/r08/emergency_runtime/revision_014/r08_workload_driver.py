#!/usr/bin/env python3
"""Exact two-warmup/eight-request workload driver for each R08 PMC segment."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import http.client
import json
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_MANIFEST_RAW_SHA256 = "dc8b848a360d977d1c30adcace393459bce536aa2278ff997d6c71b9e94be280"
EXPECTED_MANIFEST_CANONICAL_SHA256 = "d4873c7474cbf1eff0029ab1620a67954802715c1471853a528bff9c237ae889"
EXPECTED_DATASET_SHA256 = "633ba4c8b4f500d2ab28094de42698c5494e5232f40eafcd119c0a314b44b936"
EXPECTED_SELECTION_SHA256 = "bd326be2f7c6f5509c98ecc75f244a3dc03d80e0951097775fbba06135aedb0c"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(encoded)


def write_json_x(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_inputs(manifest_path: Path, dataset_path: Path, selection_path: Path) -> tuple[list[str], list[str], list[int]]:
    manifest_raw = manifest_path.read_bytes()
    require(sha256_bytes(manifest_raw) == EXPECTED_MANIFEST_RAW_SHA256, "R08 request manifest raw hash mismatch")
    manifest = json.loads(manifest_raw)
    require(canonical_sha256(manifest) == EXPECTED_MANIFEST_CANONICAL_SHA256, "R08 request manifest canonical hash mismatch")
    require(sha256_file(dataset_path) == EXPECTED_DATASET_SHA256, "R08 dataset hash mismatch")
    require(sha256_file(selection_path) == EXPECTED_SELECTION_SHA256, "R08 R07 selection hash mismatch")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    rank_map = {str(key): int(value) for key, value in selection["request_rank_map"].items()}
    records = manifest["records"]
    require(len(records) == 8, "R08 request denominator is not eight")
    with dataset_path.open("rb") as handle:
        raw_lines = [next(handle) for _ in range(8)]
    request_ids: list[str] = []
    prompts: list[str] = []
    ranks: list[int] = []
    for record, raw_line in zip(records, raw_lines):
        request_id = str(record["request_id"])
        require(sha256_bytes(raw_line) == record["raw_line_sha256"], f"R08 dataset line drift: {request_id}")
        request_ids.append(request_id)
        prompts.append(str(json.loads(raw_line)["prompt"]))
        ranks.append(rank_map[request_id])
    require(set(ranks) == {0, 1} and ranks.count(0) == 4 and ranks.count(1) == 4, "R08 DP rank assignment drift")
    return request_ids, prompts, ranks


def one_request(
    *,
    port: int,
    request_id: str,
    prompt: str,
    rank: int,
    ordinal: int,
    condition: threading.Condition,
    state: dict[str, Any],
) -> dict[str, Any]:
    connection: http.client.HTTPConnection | None = None
    response_obj: dict[str, Any] | None = None
    response_headers: dict[str, str] = {}
    status: int | None = None
    error: str | None = None
    body = json.dumps(
        {
            "model": "Qwen3.5-27B",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
            "temperature": 0.0,
            "ignore_eos": True,
            "stream": False,
            "return_token_ids": True,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    start_monotonic_ns = time.perf_counter_ns()
    start_realtime_ns = time.time_ns()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=7200)
        connection.connect()
        require(connection.sock is not None, f"R08 socket missing: {request_id}")
        connection.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        connection.putrequest("POST", "/v1/chat/completions", skip_accept_encoding=True)
        for key, value in {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
            "X-Request-Id": request_id,
            "X-data-parallel-rank": str(rank),
            "Connection": "close",
        }.items():
            connection.putheader(key, value)
        connection.endheaders()
        connection.send(body[:-1])
        with condition:
            state["prestaged"].add(request_id)
            condition.notify_all()
            ready = condition.wait_for(
                lambda: state["enabled"] and state["next_ordinal"] == ordinal,
                timeout=600,
            )
            require(ready, f"R08 canonical dispatch timeout: {request_id}")
            connection.send(body[-1:])
            state["order"].append(request_id)
            state["next_ordinal"] += 1
            condition.notify_all()
        response = connection.getresponse()
        status = response.status
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        response_obj = json.loads(response.read())
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        with condition:
            state["error"] = error
            state["enabled"] = True
            state["next_ordinal"] = max(int(state["next_ordinal"]), ordinal + 1)
            condition.notify_all()
    finally:
        if connection is not None:
            connection.close()
    end_monotonic_ns = time.perf_counter_ns()
    end_realtime_ns = time.time_ns()
    usage = response_obj.get("usage", {}) if isinstance(response_obj, dict) else {}
    choices = response_obj.get("choices", []) if isinstance(response_obj, dict) else []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    token_ids = choice.get("token_ids")
    return {
        "request_id": request_id,
        "dispatch_ordinal": ordinal,
        "data_parallel_rank_requested": rank,
        "physical_device_id_expected": rank,
        "internal_request_id_expected": f"chatcmpl-{request_id}",
        "http_status": status,
        "response_id": response_obj.get("id") if isinstance(response_obj, dict) else None,
        "response_x_request_id": response_headers.get("x-request-id"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "finish_reason": choice.get("finish_reason"),
        "generated_token_ids": token_ids,
        "generated_token_ids_sha256": canonical_sha256(token_ids) if isinstance(token_ids, list) else None,
        "content_sha256": sha256_bytes(str(message.get("content", "")).encode()),
        "reasoning_sha256": sha256_bytes(str(message.get("reasoning", "")).encode()),
        "start_monotonic_ns": start_monotonic_ns,
        "end_monotonic_ns": end_monotonic_ns,
        "duration_ns": end_monotonic_ns - start_monotonic_ns,
        "start_realtime_ns": start_realtime_ns,
        "end_realtime_ns": end_realtime_ns,
        "error": error,
    }


def dispatch_batch(port: int, request_ids: list[str], prompts: list[str], ranks: list[int]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    condition = threading.Condition()
    state: dict[str, Any] = {
        "enabled": False,
        "next_ordinal": 0,
        "prestaged": set(),
        "order": [],
        "error": None,
    }
    start_monotonic_ns = time.perf_counter_ns()
    start_realtime_ns = time.time_ns()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(request_ids)) as pool:
        futures = [
            pool.submit(
                one_request,
                port=port,
                request_id=request_id,
                prompt=prompt,
                rank=rank,
                ordinal=index,
                condition=condition,
                state=state,
            )
            for index, (request_id, prompt, rank) in enumerate(zip(request_ids, prompts, ranks))
        ]
        with condition:
            ready = condition.wait_for(
                lambda: len(state["prestaged"]) == len(request_ids) or state["error"] is not None,
                timeout=600,
            )
            require(ready and state["error"] is None, f"R08 batch prestage failed: {state['error']}")
            state["enabled"] = True
            condition.notify_all()
        rows = [future.result() for future in futures]
    end_monotonic_ns = time.perf_counter_ns()
    end_realtime_ns = time.time_ns()
    rows.sort(key=lambda row: int(row["dispatch_ordinal"]))
    require(state["order"] == request_ids, "R08 canonical request write order drift")
    return rows, {
        "policy": "prestage_all_headers_and_all_but_final_body_byte_then_canonical_final_byte_commit",
        "expected_request_write_order": request_ids,
        "observed_request_write_order": state["order"],
        "all_request_bodies_prestaged_before_dispatch": True,
        "dispatch_commit_bytes_per_request": 1,
        "inter_request_sleep_performed": False,
        "batch_start_monotonic_ns": start_monotonic_ns,
        "batch_end_monotonic_ns": end_monotonic_ns,
        "batch_duration_ns": end_monotonic_ns - start_monotonic_ns,
        "batch_start_realtime_ns": start_realtime_ns,
        "batch_end_realtime_ns": end_realtime_ns,
    }


def failures(rows: list[dict[str, Any]], measured: bool) -> list[str]:
    result: list[str] = []
    for row in rows:
        request_id = row["request_id"]
        if row["http_status"] != 200:
            result.append(f"{request_id}: HTTP={row['http_status']}")
        if row["completion_tokens"] != 1024:
            result.append(f"{request_id}: completion_tokens={row['completion_tokens']}")
        if row["finish_reason"] != "length":
            result.append(f"{request_id}: finish={row['finish_reason']}")
        if len(row["generated_token_ids"] or []) != 1024:
            result.append(f"{request_id}: token_ids={len(row['generated_token_ids'] or [])}")
        if row["error"] is not None:
            result.append(f"{request_id}: {row['error']}")
        if measured and row["response_id"] != row["internal_request_id_expected"]:
            result.append(f"{request_id}: response_id={row['response_id']}")
    return result


def wait_gate_events(event_root: Path, timeout_seconds: float = 180.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        starts = sorted(event_root.glob("start.rank*.pid*.json"))
        stops = sorted(event_root.glob("stop.rank*.pid*.json"))
        start_rows = [json.loads(path.read_text(encoding="utf-8")) for path in starts]
        stop_rows = [json.loads(path.read_text(encoding="utf-8")) for path in stops]
        if {int(row["dp_rank"]) for row in start_rows} == {0, 1} and {
            int(row["dp_rank"]) for row in stop_rows
        } == {0, 1}:
            return {
                "start_events": [{"path": str(path), "sha256": sha256_file(path)} for path in starts],
                "stop_events": [{"path": str(path), "sha256": sha256_file(path)} for path in stops],
                "rank_coverage": [0, 1],
                "physical_device_coverage": [0, 1],
            }
        time.sleep(0.05)
    raise RuntimeError("R08 PMC gate did not seal start/stop events for both ranks")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--gate-stop-file", required=True, type=Path)
    parser.add_argument("--gate-event-root", required=True, type=Path)
    args = parser.parse_args()
    attempt_root = args.attempt_root.resolve()
    output_root = attempt_root / "workload"
    require(not (output_root / "driver.json").exists(), "R08 driver output already exists")
    request_ids, prompts, ranks = load_inputs(args.manifest, args.dataset, args.selection)

    warmup_ids = [f"r08-pmc-warmup-{index + 1:03d}-{request_ids[index]}" for index in range(2)]
    warmups, warmup_dispatch = dispatch_batch(args.port, warmup_ids, prompts[:2], [0, 1])
    warmup_failures = failures(warmups, measured=False)
    require(not warmup_failures, "R08 warmup failures: " + "; ".join(warmup_failures))
    write_json_x(
        output_root / "warmup_results.json",
        {
            "schema_version": 1,
            "status": "complete",
            "count": 2,
            "excluded_from_pmc_by_worker_gate": True,
            "excluded_from_canonical_pmc_by_offline_window": True,
            "profiler_collection_state": "hipProfilerStop_Start_gate_and_target_kernel_filter",
            "dispatch": warmup_dispatch,
            "results": warmups,
        },
    )

    from r08_native_health import require_pre_measured_health
    native_health=require_pre_measured_health(attempt_root)
    measured_started_utc = utc_now()
    measured, measured_dispatch = dispatch_batch(args.port, request_ids, prompts, ranks)
    measured_finished_utc = utc_now()
    measured_failures = failures(measured, measured=True)
    write_json_x(
        args.gate_stop_file,
        {
            "schema_version": 1,
            "status": "complete",
            "command": "stop",
            "reason": "eight_measured_requests_returned",
            "monotonic_ns": time.perf_counter_ns(),
            "realtime_ns": time.time_ns(),
        },
    )
    gate = wait_gate_events(args.gate_event_root)
    driver = {
        "schema_version": 1,
        "status": "complete" if not measured_failures else "failed",
        "started_utc": measured_started_utc,
        "finished_utc": measured_finished_utc,
        "workload": {
            "mode": "batch8_concurrent_requests",
            "request_count": 8,
            "max_concurrency": 8,
            "request_rate": "inf",
            "output_tokens_per_request": 1024,
            "warmup_requests": 2,
            "temperature": 0,
            "ignore_eos": True,
        },
        "pre_measured_native_pmc_health": native_health,
        "warmup_count": 2,
        "warmups_excluded_from_pmc": True,
        "warmup_exclusion_backend": "native_always_on_with_exact_marker_PID_dispatch_guard",
        "profiler_collection_state": "hipProfilerStop_Start_gate_and_target_kernel_filter",
        "measured_request_count": 8,
        "completed": sum(
            row["http_status"] == 200 and row["completion_tokens"] == 1024 and row["error"] is None
            for row in measured
        ),
        "failed": len(measured_failures),
        "total_completion_tokens": sum(int(row["completion_tokens"] or 0) for row in measured),
        "request_ids": request_ids,
        "request_rank_map": dict(zip(request_ids, ranks)),
        "rank_to_physical_device": {"0": 0, "1": 1},
        "dispatch": measured_dispatch,
        "pmc_gate": gate,
        "failures": measured_failures,
        "results": measured,
    }
    write_json_x(output_root / "request_results.json", {"results": measured})
    write_json_x(output_root / "driver.json", driver)
    require(not measured_failures, "R08 measured workload failed: " + "; ".join(measured_failures))
    print(
        json.dumps(
            {
                "status": "complete",
                "completed": 8,
                "completion_tokens": 8192,
                "pmc_gate_rank_coverage": [0, 1],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
