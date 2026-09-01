#!/usr/bin/env python3
"""Restore and verify the unified R09 live-utilization CSV from gzip parts."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import shutil
from pathlib import Path


RUN_REL = Path(
    "perf_trace_batch8/runtime/workflow01-10-fresh-e2e/"
    "batch8-dp2-fresh-003/artifacts/R09/degraded_observed_subset_001"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve() / RUN_REL
    analysis_path = root / "analysis/fresh_e2e_analysis.json"
    parts_root = root / "recovery/live_utilization_parts"
    output = root / "analysis/tables/live_utilization_aligned.csv"
    require(analysis_path.is_file(), f"analysis manifest missing: {analysis_path}")
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    table = next(
        record
        for record in analysis["ordered_tables"]
        if record["logical_name"] == "live_utilization_aligned"
    )
    expected_sha = table["sha256"]
    expected_size = table["size_bytes"]
    expected_rows = table["row_count"]
    if output.exists():
        require(output.stat().st_size == expected_size, "existing output size mismatch")
        require(sha256_file(output) == expected_sha, "existing output hash mismatch")
        print(json.dumps({"status": "already_restored_verified", "path": str(output)}))
        return 0
    markers = sorted(parts_root.glob("part-*.complete.json"))
    require(len(markers) == 24, f"expected 24 part markers, found {len(markers)}")
    temporary = output.with_name(f".{output.name}.partial.{os.getpid()}")
    require(not temporary.exists(), f"partial output collision: {temporary}")
    total_rows = 0
    expected_header: str | None = None
    with temporary.open("x", encoding="utf-8", newline="") as destination:
        for ordinal, marker_path in enumerate(markers, 1):
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            require(marker["status"] == "complete", f"part incomplete: {marker_path}")
            require(marker["part_ordinal"] == ordinal, f"part ordinal drift: {marker_path}")
            part = parts_root / f"part-{ordinal:04d}.csv.gz"
            require(part.is_file(), f"part missing: {part}")
            require(part.stat().st_size == marker["size_bytes"], f"part size drift: {part}")
            require(sha256_file(part) == marker["sha256"], f"part hash drift: {part}")
            with gzip.open(part, "rt", encoding="utf-8", newline="") as source:
                header = source.readline()
                require(header, f"part header missing: {part}")
                if expected_header is None:
                    expected_header = header
                    destination.write(header)
                else:
                    require(header == expected_header, f"part schema drift: {part}")
                copied_rows = 0
                for line in source:
                    destination.write(line)
                    copied_rows += 1
            require(copied_rows == marker["row_count"], f"part row drift: {part}")
            total_rows += copied_rows
            print(f"verified part {ordinal}/24 cumulative_rows={total_rows}", flush=True)
        destination.flush()
        os.fsync(destination.fileno())
    require(total_rows == expected_rows, f"restored row denominator drift: {total_rows}")
    require(temporary.stat().st_size == expected_size, "restored size mismatch")
    require(sha256_file(temporary) == expected_sha, "restored SHA-256 mismatch")
    os.replace(temporary, output)
    print(
        json.dumps(
            {
                "status": "restored_verified",
                "path": str(output),
                "row_count": total_rows,
                "size_bytes": expected_size,
                "sha256": expected_sha,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
