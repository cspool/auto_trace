# Batch8 DP2 `batch8-dp2-fresh-003` R07–R10 recovery

This directory is the small, Git-tracked control and verification layer for
the DB-first recovery.  The complete segmented data package is published in:

<https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r08-r10-batch8-dp2-fresh-003-20260901>

The original R07 raw package remains separately available at:

<https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r07-raw-batch8-dp2-fresh-003-20260831>

## What is original data?

`capture.db` is the original HIPProf SQLite capture.  Its SHA-256 is
`7e71f7977d7b67781d588cc9560bd25850cb501c803286f2494d2ad5e983b15d`.
It was not modified.  The prepared database with SHA-256
`0d61e55e04c4010c144ae7d6c308ce09fa0c413e289be4f5e6ce5358292db3bf`
is a disposable copy with rebuilt/added indexes and offline-derived tables.

The R07 DB passes SQLite `quick_check`.  The problem is not database or index
corruption: the capture contains only 4,240 of 13,568 declared targets
(31.25%), including 3,920 of 12,544 process markers.  Therefore no strict
`handoffs/R07.json`, R09 handoff, or R10 handoff is fabricated.

## HIPProf finalization and DCU dependency

HIPProf's native finalizer associates raw replay/correlation records and
exports CSV/PFTrace.  Once `capture.db` exists, DB preparation, association,
segmented PFTrace export, normalization, R09 analysis, and R10 rendering are
CPU-only and do not require a DCU.  Native finalization of the original large
R07 capture did not finish, so R07 was exported offline as 66 contiguous,
independently recoverable chunks (196 PFTrace files).

R08 itself required DCUs for nine bounded PMC replay segments.  All nine
segments completed and were sealed independently.  The largest native R08
association/export handled about 2.82 GiB of raw profiler output and completed
in about 8–9 minutes; each failed/retried unit is isolated to one segment.
R08 normalization and R09/R10 are CPU-only.

## Completed recovery outputs

- R08: 9/9 segmented PMC captures, 1,131,498 canonical rows.  Twelve rows
  contain an all-`NONE` 186-counter payload and are excluded from numeric
  aggregation without zero fill; numeric counter-row coverage is
  99.99893945901804%.
- R09: exactly twelve observed-subset tables.  The large live-utilization
  table contains 2,357,298 samples, 374 gaps, and 2 anchors and is also sealed
  as 24 resumable gzip CSV parts.
- R10: self-contained offline pages and a 17,280-event Perfetto JSON
  (`320 + 3,920 + 2 × 6,520`).  All 2,357,298 raw utilization samples are
  embedded without sampling.

The R10 static/hash/event-conservation audit is complete.  Strict browser
runtime acceptance is explicitly unavailable because the worker contains no
local Chromium/Firefox binary and the offline boundary forbids dynamic
installation.

## Restore

Download every ordered `r08-r10-full-32m.tar.gz.part-NNN` asset plus
`SHA256SUMS` and `ARCHIVE_STREAM_SHA256`, verify each part, concatenate in
lexical order, then extract the GNU tar stream:

```bash
sha256sum -c SHA256SUMS
cat r08-r10-full-32m.tar.gz.part-* > r08-r10-full.tar.gz
sha256sum -c ARCHIVE_STREAM_SHA256
tar -xzf r08-r10-full.tar.gz
```

The unified 1.49 GB R09 live-utilization CSV is intentionally omitted from the
archive because its 24 gzip parts are lossless and independently recoverable.
Recreate it after extraction with:

```bash
python3 perf_trace_batch8/releases/batch8-dp2-fresh-003-r07-r10-recovery/restore_r09_live_table.py \
  --project-root /path/to/extracted/Qwen_DCU_Worker_0
```

Open the restored report at:

```text
perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/
  artifacts/R10/degraded_observed_subset_report_001/acceptance/index.html
```

All opportunity classifications are investigation hypotheses, not root-cause
or speedup claims.  R08 metrics are replay-projected shared attributes and
never replace R07 observed timing.
