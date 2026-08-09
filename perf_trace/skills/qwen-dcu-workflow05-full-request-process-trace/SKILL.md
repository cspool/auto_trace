---
name: qwen-dcu-workflow05-full-request-process-trace
description: Execute R07 as one complete fresh-run Qwen3.5-27B process trace on physical DCU 1. Consume only the same run's R06 lineage and full target files, permit audited trace-instrumentation source changes without source-hash equality, collect live SE utilization, enforce strict HIPTX-to-HIP-runtime-to-HIPOPS ownership, and build the fixed-input process dependency adapter.
---

# Qwen DCU Fresh Full-Request Process Trace

## Objective

Collect exactly one non-replay request containing every R06 process range,
along with live SE utilization and the process dependency adapter required by
R08-R10. This is the observed latency clock for the rest of the run.

## Inputs

Require `user.evidence_acquisition_mode=fresh_no_prior_runtime_reuse` and a
completed current-run R06 handoff. Rehash and validate:

- `fresh_run_lineage_manifest.json`;
- `full_request_target_manifest.json`;
- the newline event and exact-range files;
- the R01 semantic contract and R02 FX/process inventory referenced by R06;
- the hash-pinned live-utilization collector and capture launcher;
- `pra2026-bh408/scripts/perf_trace/build_fresh_run_dependency_adapter.py`.

Every runtime evidence path must remain under the same `branch/run_id` root.
Do not accept a user-supplied trace, adapter, target list, archived profile, or
another run's path.

## Source Changes

Source changes for R07 trace instrumentation are allowed. Record them as the
R07 stage delta in `R07_SOURCE_LINEAGE.json`; do not require equality with R01
source hashes. Preserve the single fresh-run lineage when semantic invariants
and output equivalence pass.

Require the R01 semantic invariants and inference-output equivalence to remain
true. Stop if a patch changes model/input/sampling/device semantics or process
definitions instead of merely enabling trace observation.

## Device and Serialization

Use physical DCU 1 only:

```text
HIP_VISIBLE_DEVICES=1
CUDA_VISIBLE_DEVICES=1
DCU_DEVICE=1
```

Recheck device identity and load immediately before capture. Refuse concurrent
GPU work. Use a new empty `runtime_artifact_root`; never overwrite an earlier
attempt.

## Capture

Launch exactly one profiling process and pass R06's newline files without
converting them into shell arrays:

```bash
env \
  ROOT_DIR=/public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408 \
  CONFIG=qwen3.5-27b-vllm-pra-eager-gfx936 \
  TAG=<fresh-R07-tag> \
  OUTPUT_DIR=<runtime_artifact_root>/capture \
  RUNTIME_ARTIFACT_ROOT=<runtime_artifact_root> \
  CONTRACT_PATH=<same-run-R01-contract> \
  MODEL_ROOT=/public/home/tangyu408/Qwen_DCU_Worker_0/Qwen3.5-27B \
  SERVED_MODEL_NAME=Qwen3.5-27B \
  MAX_NEW_TOKENS=32 \
  WARMUP_ITERS=1 \
  DCU_DEVICE=1 \
  PRA_BACKEND_PERF_PROCESS_PROFILE=1 \
  PRA_BACKEND_PERF_PROCESS_TARGETS_FILE=<R06-full-request-events.txt> \
  PRA_BACKEND_PERF_PROCESS_RANGE_TARGETS_FILE=<R06-full-request-ranges.txt> \
  WORKFLOW05_LIVE_UTILIZATION_MODE=rsmi_se_snapshot \
  PRA_BACKEND_LIVE_UTIL_COLLECTOR=<hash-pinned-collector-path> \
  PRA_BACKEND_LIVE_UTIL_COLLECTOR_SHA256=<resolved-user-parameter-sha256> \
  PRA_BACKEND_LIVE_UTIL_INTERVAL_US=500 \
  FRESH_RUN_LINEAGE_MANIFEST=<R06-fresh-run-lineage-manifest.json> \
  bash pra2026-bh408/scripts/perf_trace/run_qwen_process_profile_single_request.sh
```

Use the configured 500-us target interval and the hash-pinned collector. Keep
warmup outside the measured request. Record realtime and monotonic anchors for
the request and collector.

Normalize the completed non-replay capture into a separate empty subdirectory:

```bash
python3 pra2026-bh408/scripts/perf_trace/analyze_qwen_hipprof_process_trace.py \
  --db <R07-capture-queryable.db> \
  --runtime-events <R07-capture-runtime-events.jsonl> \
  --inventory <same-run-R02-process-range-inventory.csv> \
  --output-dir <runtime_artifact_root>/analysis \
  --contract-id <R01-contract-id> \
  --contract-sha256 <R01-contract-sha256> \
  --capture-mode non-replay \
  --expected-device 1
```

## Required Capture Checks

Require all of the following:

- expected process ranges equal emitted process ranges exactly;
- every expected range occurs once at the correct layer occurrence;
- positive request start/end timestamps and correct DCU identity;
- a queryable hipprof DB with required HIPTX, HIP runtime, HIPOPS, string and
  counter tables;
- strict range nesting and unique process identity;
- strict ownership via contained HIPTX range -> HIP runtime call -> identical
  source/config/pid/`_Index` HIPOPS row;
- analyzer status `PASS` with complete request/process/runtime/kernel tables;
- at least three successful live samples overall;
- empirical collector p50 and p95 cadence below one millisecond;
- sample alignment uncertainty within the configured bound.

Short process windows with fewer than the configured sample count remain
`unavailable`; never interpolate utilization.

## Dependency Adapter

Run the maintained dependency builder with the current run's R01 contract,
R02 fixed-input FX manifest, R07 process annotations/runtime/ownership, and R07
recorded source revision. The adapter describes structural dependencies only;
it does not merge clocks or invent opaque custom-op edges.

Require:

```text
adapter_type=fresh_run_fixed_input_fx_process_dependency
status=complete
lineage_id=<R06 lineage_id>
```

Exact-shape transfer is allowed only when audited. Mark opaque or missing edges
`unknown_dependency`.

```bash
python3 pra2026-bh408/scripts/perf_trace/build_fresh_run_dependency_adapter.py \
  --lineage-manifest <R06-fresh-run-lineage-manifest.json> \
  --measurement-contract <same-run-R01-contract> \
  --annotations <R07-annotations.csv> \
  --runtime-calls <R07-runtime_calls.csv> \
  --strict-ownership <R07-strict_ownership.csv> \
  --template-assignments <same-run-R02-template-assignments.csv> \
  --fx-manifest <same-run-R02-FX-manifest.json> \
  --stage-source-revision <frozen-R07-stage-revision> \
  --output-dir <runtime_artifact_root>/dependency \
  --allow-exact-shape-template-transfer
```

## Required Outputs

Write under `runtime_artifact_root`:

```text
R07_SOURCE_LINEAGE.json
capture/full_request_profile_metadata.json
analysis/annotations.csv
analysis/runtime_calls.csv
analysis/kernels.csv
analysis/strict_ownership.csv
analysis/process_performance.csv
analysis/process_gpu_timeline.csv
capture/live_utilization_samples.jsonl
capture/live_utilization_summary.json
dependency/fresh_run_dependency_nodes.csv
dependency/fresh_run_dependency_edges.csv
dependency/fresh_run_dependency_event_audit.csv
dependency/fresh_run_dependency_adapter.json
analysis/process_trace_summary.json
R07_COMPLETION_AUDIT.json
```

`live_utilization_samples.jsonl` is the canonical raw sample format; do not
convert it to CSV or create a second competing sample file.

## Handoff

Write only the scheduler-assigned complete R07 handoff containing:

```json
{
  "runtime_goal": "R07",
  "status": "complete",
  "execution_status": "complete",
  "evidence_status": "complete",
  "coverage_target_met": true,
  "next_authorization_required": false,
  "fresh_e2e_evidence": {
    "schema_version": 1,
    "status": "complete",
    "lineage_id": "...",
    "full_request_profile_metadata": {"path": "...", "sha256": "..."},
    "process_trace_summary": {"path": "...", "sha256": "..."},
    "fresh_run_dependency_adapter": {"path": "...", "sha256": "..."},
    "live_utilization_summary": {"path": "...", "sha256": "..."},
    "source_lineage": {"path": "...", "sha256": "..."}
  }
}
```

## Stop Conditions

Stop for a lineage mismatch, external runtime input, semantic-contract change,
output mismatch, nonempty output root, device conflict, missing marker,
ownership ambiguity, clock/alignment failure, incomplete live sampling, replay
capture, analyzer failure, or partial request. Preserve diagnostics and never
promote a partial capture to observed evidence.
