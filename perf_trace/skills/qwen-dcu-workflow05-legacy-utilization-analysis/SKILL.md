---
name: qwen-dcu-workflow05-legacy-utilization-analysis
description: Execute legacy Workflow05 R09 over a base estimated axis plus independent selective observed captures. Compute per-axis concurrency, utilization, hardware gaps, dependency quality and opportunity gates without merging clocks or presenting projected values as observed full-request evidence.
---

# Qwen DCU Legacy Workflow05 R09 Analysis

## Contract

Require `user.evidence_acquisition_mode=historical_then_selective` and complete
R06-R08 handoffs. R09 is analysis-only: do not run a model, GPU, profiler, PMC
replay, or live sampler.

Treat each selective capture as a separate clock axis. The base R05 process
composition remains estimated. Aggregate coverage by stable semantic key only;
never concatenate timestamps or infer concurrency across axes.

## Analyses

Produce:

1. the full base process estimate index;
2. one observed process/kernel/queue timeline per selective capture;
3. per-axis kernel and queue concurrency;
4. measured utilization only where a valid sampler exists;
5. hardware evidence dispositions from R08;
6. dependency and opportunity states with missing gates visible.

An opportunity is confirmed only when every configured gate is supported on
one observed clock. Otherwise label it `candidate` or `unavailable`.

## Required Outputs

```text
base_process_estimates.csv
capture_axis_manifest.json
selective_process_timeline.csv
selective_kernel_timeline.csv
selective_concurrency.csv
hardware_gap_state.csv
dependency_state.csv
opportunity_candidates.csv
workflow05_analysis.json
R09_COMPLETION_AUDIT.json
```

## Handoff

Write only the scheduler-assigned R09 handoff. Do not emit
`fresh_e2e_evidence`; report observed coverage and remaining estimate-only
coverage separately.

