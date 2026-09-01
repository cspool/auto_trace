#!/usr/bin/env python3
"""Independently audit the static R10 degraded observed-subset report."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


REQUIRED_ACCEPTANCE = [
    "index.html",
    "E2E_PROCESS_TIMELINE.html",
    "E2E_PROCESS_TIMELINE_LOSSLESS.html",
    "E2E_PROCESS_TIMELINE.full.perfetto.json",
    "full_timeline_manifest.json",
    "HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html",
    "CONCURRENCY_UTILIZATION.html",
    "offline_acceptance_manifest.json",
]
FORBIDDEN = [
    re.compile(pattern, re.I)
    for pattern in [r"https?://", r"\bfetch\s*\(", r"XMLHttpRequest", r"WebSocket", r"EventSource", r"serviceWorker", r"<script[^>]+src=", r"<link[^>]+href="]
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    return {"path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def write_json_x(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists(), f"immutable audit output exists: {path}")
    temporary = path.with_name(f".{path.name}.partial.{os.getpid()}")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def page_metadata(text: str) -> dict[str, Any]:
    match = re.search(r'<script id="report-meta" type="application/json">(.*?)</script>', text, re.S)
    require(match is not None, "page metadata block missing")
    return json.loads(match.group(1))


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.links: list[str] = []; self.external_assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.append(values["href"] or "")
        if tag in {"script", "img", "iframe", "audio", "video", "source", "link"}:
            for key in ("src", "href"):
                if values.get(key): self.external_assets.append(values[key] or "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.artifact_root.resolve()
    require(root == Path(__file__).resolve().parents[1], "artifact root/tool location mismatch")
    started = time.monotonic()
    acceptance = root / "acceptance"
    builder_path = root / "R10_BUILDER_COMPLETE.json"
    lineage_path = root / "R10_SOURCE_LINEAGE.json"
    artifact_manifest_path = root / "artifact_manifest.json"
    for path in [builder_path, lineage_path, artifact_manifest_path, *[acceptance / name for name in REQUIRED_ACCEPTANCE]]:
        require(path.is_file(), f"R10 artifact missing: {path}")
    builder = json.loads(builder_path.read_text(encoding="utf-8"))
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    artifact_manifest = json.loads(artifact_manifest_path.read_text(encoding="utf-8"))
    timeline_path = acceptance / "full_timeline_manifest.json"
    offline_path = acceptance / "offline_acceptance_manifest.json"
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    offline = json.loads(offline_path.read_text(encoding="utf-8"))
    require(builder["status"] == "builder_complete_pending_independent_audit", "builder marker state drift")
    require(builder["strict_R10_handoff_created"] is False, "strict R10 handoff fabricated")
    require(builder["strict_offline_acceptance_complete"] is False, "strict browser acceptance fabricated")
    require(timeline["complete_timeline"] is False and timeline["complete_observed_subset_timeline"] is True, "timeline evidence boundary drift")
    require(timeline["sampling_performed"] is False and timeline["top_n_truncation_performed"] is False, "lossless policy drift")
    require(timeline["formal_r09_r10_regeneration"] is False, "formal R09/R10 regeneration fabricated")
    counts = timeline["event_counts"]
    require(counts["formula"] == counts["actual_display_event_count"] == 17280, "timeline formula drift")
    require(counts["request_timeline_rows"] == 320 and counts["process_timeline_rows"] == 3920 and counts["kernel_timeline_rows"] == 6520, "timeline source denominator drift")
    perfetto_path = acceptance / "E2E_PROCESS_TIMELINE.full.perfetto.json"
    perfetto = json.loads(perfetto_path.read_text(encoding="utf-8"))
    events = perfetto["traceEvents"]
    require(len(events) == 17280, "Perfetto event count drift")
    event_kinds = Counter(event["cat"].split("|", 1)[0] for event in events)
    display_copies = Counter(event["args"]["display_copy"] for event in events)
    require(event_kinds == {"request": 320, "process": 3920, "kernel": 13040}, f"Perfetto kind conservation failed: {event_kinds}")
    require(display_copies["strict_owned_kernel"] == 6520 and display_copies["gpu_queue"] == 6520, "kernel display copy conservation failed")
    require(all(isinstance(event["args"]["absolute_begin_ns"], str) and isinstance(event["args"]["absolute_end_ns"], str) for event in events), "absolute nanosecond strings missing")

    page_results = []
    page_text: dict[str, str] = {}
    for name in ["index.html", "E2E_PROCESS_TIMELINE.html", "E2E_PROCESS_TIMELINE_LOSSLESS.html", "HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html", "CONCURRENCY_UTILIZATION.html"]:
        path = acceptance / name
        text = path.read_text(encoding="utf-8")
        page_text[name] = text
        hits = [pattern.pattern for pattern in FORBIDDEN if pattern.search(text)]
        require(not hits, f"offline forbidden pattern: {name}: {hits}")
        parser_instance = LinkParser(); parser_instance.feed(text)
        require(not parser_instance.external_assets, f"external page assets present: {name}")
        page_results.append({"name": name, **file_record(path), "metadata": page_metadata(text), "links": parser_instance.links, "forbidden_pattern_hits": hits})
    lossless_meta = page_metadata(page_text["E2E_PROCESS_TIMELINE_LOSSLESS.html"])
    require(lossless_meta["embedded_event_count"] == 17280, "lossless embedded denominator drift")
    require(lossless_meta["minimum_viewport_ns"] == 1 and lossless_meta["history_capacity"] >= 100, "lossless interaction contract drift")
    lossless_text = page_text["E2E_PROCESS_TIMELINE_LOSSLESS.html"]
    for token in ["onwheel", "onmousedown", "shiftKey", "fit.onclick", "jump.onclick", "list.onclick", "timeline.onclick"]:
        require(token in lossless_text, f"lossless interaction missing: {token}")
    concurrency_meta = page_metadata(page_text["CONCURRENCY_UTILIZATION.html"])
    require(concurrency_meta["live_sample_count"] == 2357298 and concurrency_meta["live_gap_count"] == 374 and concurrency_meta["live_anchor_count"] == 2, "concurrency metadata denominator drift")
    concurrency_text = page_text["CONCURRENCY_UTILIZATION.html"]
    sample_start = concurrency_text.index("SAMPLES=[") + len("SAMPLES=[")
    sample_end = concurrency_text.index("];const GAPS=", sample_start)
    sample_payload = concurrency_text[sample_start:sample_end]
    inline_sample_count = 0 if not sample_payload else sample_payload.count("],[") + 1
    require(inline_sample_count == 2357298, f"inline raw sample denominator drift: {inline_sample_count}")
    gap_start = sample_end + len("];const GAPS=")
    gap_end = concurrency_text.index(",ANCHORS=", gap_start)
    anchor_start = gap_end + len(",ANCHORS=")
    anchor_end = concurrency_text.index(";\nconst C=", anchor_start)
    inline_gaps = json.loads(concurrency_text[gap_start:gap_end])
    inline_anchors = json.loads(concurrency_text[anchor_start:anchor_end])
    require(len(inline_gaps) == 374 and len(inline_anchors) == 2, "inline gap/anchor denominator drift")

    index_parser = LinkParser(); index_parser.feed(page_text["index.html"])
    for target in index_parser.links:
        require(not re.match(r"^[a-z]+:", target, re.I), f"nonlocal index link: {target}")
        if target == "../R10_COMPLETION_AUDIT.json":
            continue
        require((acceptance / target).resolve().is_file(), f"index target missing: {target}")
    require(offline["network_denied_browser_execution_performed"] is False, "browser execution unexpectedly claimed")
    require(offline["strict_offline_acceptance_complete"] is False, "strict offline acceptance unexpectedly claimed")
    require(offline["attempted_network_requests"] == 0, "network requests recorded")
    require(lineage["strict_R10_handoff_created"] is False, "lineage strict handoff drift")
    require(artifact_manifest["strict_scheduler_handoff_included"] is False, "scheduler handoff entered artifact manifest")
    require(not (root.parents[2] / "handoffs/R10.json").exists(), "formal R10 handoff unexpectedly exists")
    for record in artifact_manifest["artifacts"]:
        path = Path(record["path"])
        require(path.is_file() and path.stat().st_size == record["size_bytes"] and sha256_file(path) == record["sha256"], f"artifact manifest drift: {path}")
    audit = {
        "schema_version": 1, "status": "complete",
        "audit_scope": "R10_degraded_observed_subset_static_acceptance_not_strict_scheduler_R10",
        "finished_utc": utc_now(), "elapsed_seconds": time.monotonic() - started,
        "runtime_run_id": timeline["runtime_run_id"],
        "lineage_id": timeline["lineage_id"], "evidence_status": timeline["evidence_status"],
        "event_counts": counts, "perfetto_event_kind_counts": dict(event_kinds),
        "kernel_display_copy_counts": dict(display_copies), "inline_live_sample_count": inline_sample_count,
        "inline_live_gap_count": len(inline_gaps), "inline_live_anchor_count": len(inline_anchors),
        "page_audits": page_results, "static_no_network_gate": True,
        "browser_runtime_available": False, "network_denied_browser_execution_performed": False,
        "strict_offline_acceptance_complete": False, "strict_R10_handoff_created": False,
        "complete_observed_subset_report": True, "complete_declared_target_report": False,
        "sampling_performed": False, "top_n_truncation_performed": False,
        "dcu_accessed": False,
    }
    audit_path = root / "R10_COMPLETION_AUDIT.json"
    write_json_x(audit_path, audit)
    complete = {
        "schema_version": 1, "status": "complete", "execution_status": "complete",
        "evidence_status": "degraded_R07_observed_subset", "finished_utc": utc_now(),
        "entry_point": file_record(acceptance / "index.html"),
        "full_timeline_manifest": file_record(timeline_path),
        "offline_acceptance_manifest": file_record(offline_path),
        "source_lineage": file_record(lineage_path), "completion_audit": file_record(audit_path),
        "artifact_manifest": file_record(artifact_manifest_path), "event_count": 17280,
        "live_sample_count": 2357298, "complete_observed_subset_report": True,
        "complete_declared_target_report": False, "strict_R10_handoff_created": False,
        "strict_offline_acceptance_complete": False, "browser_runtime_available": False,
        "dcu_accessed": False,
    }
    complete_path = root / "R10_DEGRADED_REPORT_COMPLETE.json"
    write_json_x(complete_path, complete)
    print(json.dumps(complete, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
