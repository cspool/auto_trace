#!/usr/bin/env python3
"""Read-only terminal monitor for one perf-trace scheduler runtime."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


def load_object(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a JSON object: {path}")
    return value


def print_status(run_dir: Path, *, clear: bool) -> None:
    state = load_object(run_dir / "state.json")
    ledger = load_object(run_dir / "runtime_handoff_ledger.json")
    if clear and sys.stdout.isatty():
        sys.stdout.write("\033[2J\033[H")
    print(time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()))
    print(f"run:        {run_dir.name}")
    print(f"status:     {state.get('status')}")
    print(f"execution:  {state.get('execution_status')}")
    print(f"evidence:   {state.get('evidence_status')}")
    print(f"current:    {state.get('current_goal')}")
    current = state.get("current_goal")
    current_record = state.get("goals", {}).get(current, {})
    if isinstance(current_record, dict) and current_record.get("transport_status"):
        retries = current_record.get("retryable_transport_error_history", [])
        retry_count = len(retries) if isinstance(retries, list) else "?"
        print(
            f"transport:  {current_record.get('transport_status')} "
            f"(retry notices={retry_count})"
        )
    print(f"updated:    {state.get('updated_at')}")
    print(f"handoffs:   {len(ledger.get('handoffs', []))}")
    print()
    for goal_id, record in state.get("goals", {}).items():
        error = record.get("error") or ""
        suffix = f"  error={error}" if error else ""
        print(f"{goal_id:<3}  {record.get('status', '-'):<12}{suffix}")
    sys.stdout.flush()


def watch_status(run_dir: Path, interval: float) -> None:
    while True:
        try:
            print_status(run_dir, clear=True)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"waiting for an atomic state update: {exc}", file=sys.stderr)
        time.sleep(interval)


def render_record(record: dict[str, Any]) -> None:
    timestamp = str(record.get("observed_at", ""))
    message = record.get("message")
    if not isinstance(message, dict):
        return
    method = message.get("method")
    params = message.get("params")
    if not isinstance(params, dict):
        params = {}
    item = params.get("item")
    if not isinstance(item, dict):
        item = {}
    item_type = item.get("type")
    if method == "item/started" and item_type == "commandExecution":
        command = str(item.get("command") or "").replace("\n", " ")
        print(f"\n[{timestamp}] COMMAND START\n{command[:600]}", flush=True)
    elif method == "item/completed" and item_type == "agentMessage":
        text = item.get("text")
        if isinstance(text, str) and text:
            print(f"\n[{timestamp}] GOAL MESSAGE\n{text}", flush=True)
    elif method == "item/completed" and item_type == "commandExecution":
        command = str(item.get("command") or "").replace("\n", " ")
        exit_code = item.get("exitCode")
        print(
            f"\n[{timestamp}] COMMAND END exit={exit_code}\n{command[:400]}",
            flush=True,
        )
        if exit_code not in (None, 0):
            output = str(item.get("aggregatedOutput") or "")
            if output:
                print(output[-2000:], flush=True)
    elif method in {"turn/completed", "thread/status/changed"}:
        print(f"\n[{timestamp}] {method} {params}", flush=True)


def follow_messages(run_dir: Path, history: int, interval: float) -> None:
    path = run_dir / "app_server.jsonl"
    while not path.is_file():
        time.sleep(interval)
    with path.open(encoding="utf-8") as handle:
        if history <= 0:
            handle.seek(0, os.SEEK_END)
        else:
            lines = handle.readlines()
            for line in lines[-history:]:
                try:
                    render_record(json.loads(line))
                except json.JSONDecodeError:
                    pass
        while True:
            line = handle.readline()
            if not line:
                time.sleep(interval)
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                render_record(record)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--watch", action="store_true", help="refresh state forever")
    mode.add_argument("--follow", action="store_true", help="follow Goal messages")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument(
        "--history",
        type=int,
        default=30,
        help="recent JSONL records to scan before following; use 0 for new only",
    )
    args = parser.parse_args()
    run_dir = args.run_dir.expanduser().resolve()
    if not run_dir.is_dir():
        parser.error(f"run directory is missing: {run_dir}")
    if args.interval <= 0 or args.history < 0:
        parser.error("interval must be positive and history nonnegative")
    try:
        if args.watch:
            watch_status(run_dir, args.interval)
        elif args.follow:
            follow_messages(run_dir, args.history, args.interval)
        else:
            print_status(run_dir, clear=False)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
