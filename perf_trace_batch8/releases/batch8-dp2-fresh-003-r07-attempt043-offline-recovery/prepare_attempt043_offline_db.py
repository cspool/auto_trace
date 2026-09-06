#!/usr/bin/env python3
"""Rebuild HIPProf-derived tables on a disposable attempt-043 DB copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import time


EXPECTED_SOURCE_BYTES = 8_958_377_984
EXPECTED_SOURCE_SHA256 = "0ea77cdac40926182c4e04fc29e687e62df9b2cac50296c7e399817c583690b0"
TABLE_RE = re.compile(r"^[A-Za-z0-9_]+$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quote_identifier(value: str) -> str:
    if not TABLE_RE.fullmatch(value):
        raise ValueError(f"unsafe SQLite identifier: {value!r}")
    return f'"{value}"'


def discover_worker_keys(conn: sqlite3.Connection) -> list[str]:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    }
    keys = sorted(name.removeprefix("HIP_") for name in tables if name.startswith("HIP_"))
    if len(keys) != 2:
        raise RuntimeError(f"expected exactly two HIP worker keys, found {keys}")
    for key in keys:
        required = {f"HIP_{key}", f"HIPOPS_{key}", f"HIPCOPY_{key}", f"HIPTX_{key}"}
        missing = sorted(required - tables)
        if missing:
            raise RuntimeError(f"worker {key} is missing tables: {missing}")
    return keys


def rebuild_hiptxops(conn: sqlite3.Connection, key: str) -> int:
    hip = quote_identifier(f"HIP_{key}")
    hipops = quote_identifier(f"HIPOPS_{key}")
    hiptx = quote_identifier(f"HIPTX_{key}")
    output = quote_identifier(f"HIPTXOPS_{key}")
    hip_index = quote_identifier(f"HIP_{key}_tid_idx")
    hiptx_index = quote_identifier(f"HIPTX_{key}_tid_range_idx")
    output_index = quote_identifier(f"HIPTXOPS_{key}_idx")

    conn.execute(f"CREATE INDEX IF NOT EXISTS {hip_index} ON {hip}(tid, _Index)")
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS {hiptx_index} "
        f"ON {hiptx}(tid, begin_Index, end_Index)"
    )
    conn.execute(f"ANALYZE {hip}")
    conn.execute(f"ANALYZE {hiptx}")

    conn.execute(f"DROP TABLE IF EXISTS {output}")
    conn.execute(
        f"""
        CREATE TABLE {output} (
          BeginNs INTEGER,
          EndNs INTEGER,
          dev_id INTEGER,
          queue_id TEXT,
          Name INTEGER,
          pid INTEGER,
          tid INTEGER,
          _Index INTEGER,
          hip_Index INTEGER,
          DurationNs INTEGER,
          args TEXT
        )
        """
    )
    conn.execute(
        f"""
        INSERT INTO {output}
        SELECT DISTINCT
          MIN(t1.BeginNs) AS BeginNs,
          MAX(t1.EndNs) AS EndNs,
          t1.dev_id,
          t1.queue_id,
          t2.message AS Name,
          t1.pid,
          t1.tid,
          t2._Index AS _Index,
          MIN(t1._Index) AS hip_Index,
          SUM(t1.DurationNs) AS DurationNs,
          group_concat(t1._Index) AS args
        FROM (
          SELECT
            db1.BeginNs,
            db1.EndNs,
            db1.dev_id,
            db1.queue_id,
            db1.pid,
            db2.tid,
            db1._Index,
            db1.DurationNs
          FROM {hipops} AS db1
          JOIN {hip} AS db2 ON db1._Index = db2._Index
        ) AS t1
        INNER JOIN {hiptx} AS t2
          ON t1._Index BETWEEN t2.begin_Index AND t2.end_Index
         AND t1.tid = t2.tid
        GROUP BY t2.BeginNs, t1.dev_id, t1.queue_id, t2.message
        """
    )
    conn.execute(
        f"""
        UPDATE {output}
        SET Name = COALESCE(Name, 'kernel') || '(' ||
          CASE
            WHEN (EndNs - BeginNs) > 0 THEN
              CASE
                WHEN (DurationNs * 10000) / (EndNs - BeginNs) % 100 < 10 THEN
                  CAST((DurationNs * 100) / (EndNs - BeginNs) AS TEXT) || '.0' ||
                  CAST((DurationNs * 10000) / (EndNs - BeginNs) % 100 AS TEXT)
                ELSE
                  CAST((DurationNs * 100) / (EndNs - BeginNs) AS TEXT) || '.' ||
                  CAST((DurationNs * 10000) / (EndNs - BeginNs) % 100 AS TEXT)
              END
            ELSE '0.00'
          END || '%)'
        WHERE EndNs > BeginNs
        """
    )
    conn.execute(
        f"""
        UPDATE {output}
        SET Name = COALESCE(Name, 'kernel') || '(0.00%)'
        WHERE EndNs <= BeginNs
        """
    )
    conn.execute(f"CREATE INDEX {output_index} ON {output}(_Index)")
    return int(conn.execute(f"SELECT count(*) FROM {output}").fetchone()[0])


def rebuild_trace_counter(conn: sqlite3.Connection) -> list[dict[str, int | str]]:
    conn.execute("DROP TABLE IF EXISTS TRACE_COUNTER")
    conn.execute(
        """
        CREATE TABLE TRACE_COUNTER (
          Key TEXT,
          TraceType INTEGER,
          MinBeginNs INTEGER,
          MaxBeginNs INTEGER,
          TraceSum INTEGER,
          MinTs INTEGER,
          MaxTs INTEGER,
          DbMinTimeOfDay INTEGER
        )
        """
    )
    base = int(conn.execute("SELECT MIN(CAST(TIME_OF_DAY AS INTEGER)) FROM CONFIG").fetchone()[0])
    type_prefixes = (
        ("HSA_", 256),
        ("HIP_", 1),
        ("HIPOPS_", 2),
        ("HIPCOPY_", 4),
        ("HIPTX_", 131072),
        ("HIPTXOPS_", 524288),
    )
    table_names = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    rows: list[dict[str, int | str]] = []
    for prefix, trace_type in type_prefixes:
        for table_name in table_names:
            if not table_name.startswith(prefix):
                continue
            table = quote_identifier(table_name)
            trace_sum, min_begin, max_begin = conn.execute(
                f"SELECT count(*), MIN(BeginNs), MAX(BeginNs) FROM {table}"
            ).fetchone()
            if not trace_sum:
                continue
            key = table_name.removeprefix(prefix)
            conn.execute(
                "INSERT INTO TRACE_COUNTER VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    key,
                    trace_type,
                    min_begin,
                    max_begin,
                    trace_sum,
                    int(min_begin) - base,
                    int(max_begin) - base,
                    base,
                ),
            )
            rows.append(
                {
                    "key": key,
                    "trace_type": trace_type,
                    "trace_sum": int(trace_sum),
                    "min_begin_ns": int(min_begin),
                    "max_begin_ns": int(max_begin),
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", required=True, type=Path)
    parser.add_argument("--prepared-db", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()

    source = args.source_db.resolve(strict=True)
    prepared = args.prepared_db
    manifest = args.manifest
    if prepared.exists() or manifest.exists():
        raise RuntimeError("refusing to overwrite an existing prepared DB or manifest")
    if source.stat().st_size != EXPECTED_SOURCE_BYTES:
        raise RuntimeError(f"source size mismatch: {source.stat().st_size}")
    source_hash_before = sha256_file(source)
    if source_hash_before != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(f"source hash mismatch: {source_hash_before}")

    prepared.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, prepared)
    if sha256_file(prepared) != EXPECTED_SOURCE_SHA256:
        raise RuntimeError("disposable copy does not match source")

    started_ns = time.time_ns()
    conn = sqlite3.connect(prepared, timeout=60)
    conn.isolation_level = None
    try:
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("source-copy quick_check failed")
        keys = discover_worker_keys(conn)
        conn.execute("PRAGMA busy_timeout=60000")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-4194304")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DROP TABLE IF EXISTS RANGE_SUMMARY")
        conn.execute("DROP TABLE IF EXISTS TRACE_COUNTER")
        for key in keys:
            conn.execute(f"DROP TABLE IF EXISTS {quote_identifier(f'HIPTXOPS_{key}')}")
        conn.execute("COMMIT")

        derived_counts: dict[str, int] = {}
        for key in keys:
            conn.execute("BEGIN IMMEDIATE")
            derived_counts[key] = rebuild_hiptxops(conn, key)
            conn.execute("COMMIT")
            if derived_counts[key] <= 0:
                raise RuntimeError(f"empty reconstructed HIPTXOPS table for {key}")

        conn.execute("BEGIN IMMEDIATE")
        counter_rows = rebuild_trace_counter(conn)
        conn.execute("COMMIT")
        conn.execute("PRAGMA optimize")
        quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            raise RuntimeError(f"prepared DB quick_check failed: {quick_check}")
        trace_counter_count = int(conn.execute("SELECT count(*) FROM TRACE_COUNTER").fetchone()[0])
        if trace_counter_count != len(counter_rows) or trace_counter_count <= 0:
            raise RuntimeError("TRACE_COUNTER row-count mismatch")
    finally:
        conn.close()

    ended_ns = time.time_ns()
    source_hash_after = sha256_file(source)
    if source_hash_after != source_hash_before:
        raise RuntimeError("source DB changed during recovery")
    prepared_hash = sha256_file(prepared)
    payload = {
        "schema_version": 1,
        "status": "complete",
        "recovery_kind": "attempt043_open_writer_db_derived_table_reconstruction",
        "source_db": str(source),
        "source_bytes": source.stat().st_size,
        "source_sha256_before": source_hash_before,
        "source_sha256_after": source_hash_after,
        "source_immutable": True,
        "prepared_db": str(prepared),
        "prepared_bytes": prepared.stat().st_size,
        "prepared_sha256": prepared_hash,
        "worker_keys": keys,
        "hiptxops_rows": derived_counts,
        "trace_counter_rows": trace_counter_count,
        "trace_counter": counter_rows,
        "quick_check": quick_check,
        "started_epoch_ns": started_ns,
        "ended_epoch_ns": ended_ns,
        "elapsed_milliseconds": (ended_ns - started_ns) // 1_000_000,
        "device_access": False,
        "pid": os.getpid(),
    }
    temp_manifest = manifest.with_name(f".{manifest.name}.tmp.{os.getpid()}")
    temp_manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp_manifest, manifest)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
