# R07 attempt043 live HIPProf diagnostic bundle

This bundle preserves the logs and non-interrupting diagnostics collected while
R07 attempt043 HIPProf was still running.  It is intended for postmortem review
if the worker container disappears, and for diagnosing the unusually long
SQLite-style post-capture phase.

## Download

- Release:
  <https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r07-attempt043-hipprof-diagnostic-20260905>
- Release tag: `perf-trace-batch8-r07-attempt043-hipprof-diagnostic-20260905`
- Archive: `r07-attempt043-hipprof-live-diagnostic.tar.gz`
- Archive size: `672279` bytes
- Archive SHA-256:
  `55b4c097f32f3c7d22ef9324f4294979d9add98b451369d01ee33b65b060936a`

The collection timestamp reported by the live container's UTC clock is
`2026-09-04T16:32:55Z`; the `20260905` release label corresponds to the local
`+08:00` date used by the artifact filesystem.

## Safety boundary

The collection did not wait for HIPProf to exit and did not interrupt it.  The
collector recorded:

- `0` signals;
- `0` debugger or `ptrace` attachments;
- `0` device queries;
- `0` SQLite connections;
- `0` bytes read from the active `capture.db`;
- `0` bytes read from the open `etilqs_*` file descriptors.

The active DB and the open SQLite temporary-file bodies are deliberately not in
this release.  Only their `/proc`/filesystem metadata is included.  Full model
request/completion payloads, the 867 MB utilization body, and large per-rank
event bodies are also excluded; their paths and metadata are indexed without
duplicating them.  Published text was checked for common private-key and token
shapes before upload.

## Included evidence

The release has 11 verified assets.  Its diagnostic archive contains 90 files,
including:

- `capture.log`, `service.log`, collector stdout/stderr, and a sanitized
  `process_registry.jsonl`;
- workload/service completion records and selected non-payload summaries;
- three short `/proc` process/IO/FD samples for PIDs `295616`, `295635`, and
  `295637`;
- process maps, status, scheduler, cgroup, limits, syscall, FD, and loaded
  object identities;
- exact HIPProf binary/library SHA-256 identities and static SQL/symbol clues;
- exact frozen capture runner and recovery/checkpoint helper sources;
- artifact/marker inventories and the prior NFS/GitHub DB-insurance metadata;
- per-file `PAYLOAD_MANIFEST.json`, `SHA256SUMS`, and completion records.

Start with:

1. `DIAGNOSTIC_SUMMARY.json`
2. `diagnostics/live_process_samples.json`
3. `diagnostics/insurance_to_current_comparison.json`
4. `logs/capture.log`
5. `diagnostics/hipprof_relevant_static_strings.json`

## Snapshot finding

At collection time PID `295637` remained in state `R`.  Across the four-second
sample it used `3.99` CPU seconds, issued `61329` read calls, and consumed
`251203584` logical read bytes: exactly `4096` bytes per read call on average.
Its cumulative logical reads were `8130442159046` bytes, about `907.58` times
the `8958377984`-byte DB size.  The live binary contains `commitDb`,
`updateTXKernel`, `TXOPS_`, range-join, and grouping paths.

This proves active, CPU-bound SQLite-style page scanning; it does not prove the
exact current C++ stack or eventual completion.  No intrusive stack sampler was
used.

## Integrity

Key control-file hashes:

| File | SHA-256 |
|---|---|
| `COLLECTION_COMPLETE.json` | `36a5b3608e34fa74fa5739ddf9c5b7addb67d75096ec96aa3e8867eb36889533` |
| `DIAGNOSTIC_SUMMARY.json` | `1664a73b0a1c49cb38dd4996ca3112c32f354ac86e04e1f84e464aa823b0f0bf` |
| `PAYLOAD_MANIFEST.json` | `183410d1ddcdfb0356642725ef7750e96441abdfe1ff6b8d3749705049704aae` |
| `RELEASE_ASSETS.json` | `ccb5871d0a9a896304bfabfc7814c94a1b2235b65dbff5c554347c3d9075e9c3` |
| `RELEASE_ASSET_SHA256SUMS` | `1cf93ed678f03a00e0880dc6d61458ae4c38597a2e308fc69236e18319eb96d0` |
| `REMOTE_VERIFICATION.json` | `b4e3819caeb5bc7788b250437cd142e6f1645ef09a9d46648b5bb0703da006bc` |
| `RELEASE_PUBLISHED.json` | `08124633ee03f23ad883312a20cbe361a794e414f7a00797c2316f683b91a644` |
| `PUBLICATION_SHA256SUMS` | `e7f41fd4d447ff9398e2527badd6469b1f0b81306dc692ff803e13d53b40aea2` |
| diagnostic archive | `55b4c097f32f3c7d22ef9324f4294979d9add98b451369d01ee33b65b060936a` |

After downloading every release asset:

```bash
sha256sum -c PUBLICATION_SHA256SUMS
sha256sum -c RELEASE_ASSET_SHA256SUMS
tar -xzf r07-attempt043-hipprof-live-diagnostic.tar.gz
cd diagnostic_bundle
sha256sum -c SHA256SUMS
```

GitHub API readback verified all 11 remote assets by name, size, `uploaded`
state, and server-provided SHA-256 digest.  The publication proof is preserved
in `REMOTE_VERIFICATION.json` and `RELEASE_PUBLISHED.json`.

The separately published open-writer DB insurance release remains available at:

<https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r07-attempt043-open-writer-db-20260904>

## Durable NFS source

The immutable diagnostic directory is:

```text
/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/runtime_nfs_bulk/qwen_dcu_perf_trace_batch8_diagnostics_20260905/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/R07/batch8-dp2-fresh-003-R07-attempt-043/hipprof_live_diagnostic_001
```

The release-upload package is:

```text
/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/remote_uploads/perf-trace-batch8-r07-attempt043-hipprof-diagnostic-20260905
```
