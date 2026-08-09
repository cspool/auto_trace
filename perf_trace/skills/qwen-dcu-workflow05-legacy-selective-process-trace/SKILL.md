---
name: qwen-dcu-workflow05-legacy-selective-process-trace
description: Execute legacy Workflow05 R07 from an approved R06 selective plan. Capture only the authorized process ranges on physical DCU 1, enforce strict HIPTX-to-runtime-to-HIPOPS ownership, and retain each selective capture as an independent observed clock rather than merging it with base estimates or another capture.
---

# Qwen DCU Legacy Workflow05 R07 Selective Trace

## Contract

Require `user.evidence_acquisition_mode=historical_then_selective`, a complete
R06 plan, and nonempty authorized process targets. Run GPU work serially on
physical DCU 1. A selective capture is supplemental observed evidence; it does
not turn unsampled base estimates into observed timing.

R07 may change trace-only wrappers, marker transport, analyzers, or validators.
Record the stage delta and prove unchanged model/input/output semantics.

## Capture

For each authorized batch:

1. use a new empty output directory and unique capture identifier;
2. pass exact process targets through the maintained newline-file transport;
3. capture non-replay HIPTX, HIP runtime and HIPOPS data;
4. attribute kernels only through runtime `_Index` launch ownership;
5. analyze only the requested process ranges;
6. retain request anchors and capture identity on every row.

Do not merge absolute timestamps from independent captures. Join coverage only
by stable semantic keys.

## Required Outputs

```text
capture_manifest.json
annotations.csv
runtime_calls.csv
kernels.csv
strict_ownership.csv
process_performance.csv
process_gpu_timeline.csv
process_trace_summary.json
R07_COMPLETION_AUDIT.json
```

Mark incomplete ranges, ambiguous ownership, changed execution paths, and
unmeasured targets explicitly. Never promote partial capture data to complete.

## Handoff

Write only the scheduler-assigned R07 handoff. Derive evidence sufficiency from
the cumulative authorized target denominator, not from successful process exit.

