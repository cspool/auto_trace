---
name: qwen-dcu-workflow05-utilization-concurrency-analysis
description: Execute R09 for one Qwen3.5-27B fresh R01-R10 lineage. Consume only same-run R07 observed process/kernel/live-utilization evidence and R08 replay-projected traffic/resource evidence, permit audited analysis-tool source changes without source-hash equality, and deterministically produce the end-to-end process, utilization, concurrency, launch-gap, dependency, and opportunity tables.
---

# Qwen DCU Fresh E2E Utilization and Concurrency Analysis

## Objective

Build one normalized full-request analysis from the R07 observed clock and the
R08 attached hardware model. R09 performs analysis only and must not run the
model, GPU, profiler, or a new trace.

## Inputs

Require `user.evidence_acquisition_mode=fresh_no_prior_runtime_reuse`, matching
R06-R08 `lineage_id` values, and complete hashed references to:

- R07 request metadata, annotations, runtime calls, kernels, strict ownership,
  process performance/timeline and live samples;
- R07 fresh-run dependency adapter;
- R08 device capabilities, hardware metrics and traffic/resource model;
- configured sample-count, alignment, utilization and opportunity gates.

All runtime paths must be under the same run. Reject optional external
adapters/models and any archived runtime evidence.

## Lineage and Source Changes

R09 may modify maintained analyzers, schemas, validators, or presentation data
builders. Record the R09 tooling delta in `R09_SOURCE_LINEAGE.json`; do not
require source-hash equality with earlier stages. These changes must not alter
the frozen observed input tables or semantic contract.

## Required Analyzer

Use:

```text
pra2026-bh408/scripts/perf_trace/analyze_fresh_e2e_timeline.py
```

Do not replace its outputs with hand-edited CSV/JSON. Pass the exact R07/R08
hash-pinned inputs and user-configured gates, including `--annotations`,
`--runtime-calls`, `--strict-ownership`, utilization thresholds, dependency
coverage, and all seven opportunity-gate thresholds.

```bash
python3 pra2026-bh408/scripts/perf_trace/analyze_fresh_e2e_timeline.py \
  --profile-metadata <R07-full_request_profile_metadata.json> \
  --process-trace-summary <R07-process_trace_summary.json> \
  --annotations <R07-annotations.csv> \
  --runtime-calls <R07-runtime_calls.csv> \
  --strict-ownership <R07-strict_ownership.csv> \
  --process-performance <R07-process_performance.csv> \
  --process-gpu-timeline <R07-process_gpu_timeline.csv> \
  --kernels <R07-kernels.csv> \
  --live-samples <R07-live_utilization_samples.jsonl> \
  --live-summary <R07-live_utilization_summary.json> \
  --dependency-adapter <R07-fresh_run_dependency_adapter.json> \
  --traffic-resource-model <R08-traffic_resource_model.json> \
  --output-dir <runtime_artifact_root>/analysis \
  --minimum-live-samples <resolved-user-value> \
  --maximum-clock-alignment-error-ns <resolved-user-value> \
  --low-se-utilization-pct <resolved-user-value> \
  --low-kernel-concurrency-max <resolved-user-value> \
  --minimum-launch-gap-ns <resolved-user-value> \
  --minimum-dependency-coverage <resolved-user-value> \
  --minimum-exposed-duration-ns <resolved-user-value> \
  --minimum-exposed-fraction <resolved-user-value> \
  --slack-tolerance-ns <resolved-user-value>
```

## Timing and Evidence Semantics

- Use R07 HIPTX process intervals for observed host process time.
- Use strict-owned R07 HIPOPS intervals for observed GPU busy union.
- Compute active kernel and active queue counts with interval sweep lines.
- Compute launch gaps only on the R07 non-replay clock.
- Align R07 live samples through recorded realtime/monotonic anchors.
- Attach observed `se_active_cu_pct` only with enough in-window samples and
  acceptable uncertainty; otherwise emit `unavailable`.
- Attach R08 PMC/resources as `replay_projected`; never use their duration in
  latency, critical-path, overlap, or launch-gap arithmetic.
- Consume dependency edges as structural evidence; opaque/unknown edges remain
  unknown and cannot prove slack.
- Keep inferred FX-visible traffic and unavailable HBM/DRAM quantities
  visibly distinct.

## Required Analyses

Produce:

1. full request/forward/layer/process interval hierarchy;
2. strict-owned kernel timeline and process GPU busy unions;
3. active-kernel and active-queue concurrency sweeps;
4. host launch gaps and queue exposure;
5. per-process live utilization statistics and sample coverage;
6. high-latency process windows with hardware/resource attachments;
7. dependency/ready/slack state without adjacency inference;
8. opportunity gates covering dependency, slack, queue feasibility, resource
   coexistence, exposed duration/fraction, utilization, and evidence quality.

An opportunity is `confirmed` only when every configured gate has direct or
validated evidence. Otherwise retain `candidate` or `unavailable` with reasons.
Do not claim speedup.

## Required Outputs

Write under `runtime_artifact_root`:

```text
R09_SOURCE_LINEAGE.json
analysis/request_timeline.csv
analysis/process_timeline.csv
analysis/kernel_timeline.csv
analysis/live_utilization_aligned.csv
analysis/process_live_utilization.csv
analysis/kernel_concurrency.csv
analysis/queue_concurrency.csv
analysis/launch_gaps.csv
analysis/high_latency_processes.csv
analysis/dependency_state.csv
analysis/traffic_resource_attachment.csv
analysis/opportunity_candidates.csv
analysis/fresh_e2e_analysis.json
R09_COMPLETION_AUDIT.json
```

`fresh_e2e_analysis.json` must contain:

```json
{
  "schema_version": 1,
  "status": "PASS",
  "analysis_type": "fresh_run_full_request_e2e",
  "lineage_id": "...",
  "full_request_observed_timeline": true,
  "high_latency_process_count": 1,
  "high_latency_processes_with_live_samples": 1,
  "fresh_run_dependency_adapter_consumed": true,
  "traffic_resource_model_consumed": true,
  "track_type_counts": {
    "request": 1,
    "forward": 1,
    "layer": 1,
    "hip_runtime": 1
  },
  "configured_gates": {
    "low_se_utilization_pct": 50.0,
    "low_kernel_concurrency_max": 1,
    "minimum_launch_gap_ns": 100000,
    "minimum_dependency_coverage": 0.0,
    "minimum_exposed_duration_ns": 100000,
    "minimum_exposed_fraction": 0.01,
    "slack_tolerance_ns": 1000,
    "require_all_seven_gates": true
  },
  "normalized_tables": {
    "request_timeline": {"path": "...", "sha256": "...", "row_count": 1},
    "process_timeline": {"path": "...", "sha256": "...", "row_count": 1},
    "kernel_timeline": {"path": "...", "sha256": "...", "row_count": 1},
    "live_utilization_aligned": {"path": "...", "sha256": "...", "row_count": 1},
    "process_live_utilization": {"path": "...", "sha256": "...", "row_count": 1},
    "kernel_concurrency": {"path": "...", "sha256": "...", "row_count": 1},
    "queue_concurrency": {"path": "...", "sha256": "...", "row_count": 1},
    "launch_gaps": {"path": "...", "sha256": "...", "row_count": 1},
    "high_latency_processes": {"path": "...", "sha256": "...", "row_count": 1},
    "dependency_state": {"path": "...", "sha256": "...", "row_count": 1},
    "traffic_resource_attachment": {"path": "...", "sha256": "...", "row_count": 1},
    "opportunity_candidates": {"path": "...", "sha256": "...", "row_count": 1}
  }
}
```

All twelve table counts must be positive and must equal the corresponding CSV
row counts. Numeric gate values above illustrate the committed fresh-run
configuration; write the exact resolved user values into the manifest.

## Handoff

Write only the scheduler-assigned R09 handoff:

```json
{
  "runtime_goal": "R09",
  "status": "complete",
  "execution_status": "complete",
  "evidence_status": "complete",
  "coverage_target_met": true,
  "next_authorization_required": false,
  "fresh_e2e_evidence": {
    "schema_version": 1,
    "status": "complete",
    "lineage_id": "...",
    "full_request_analysis": {"path": "...", "sha256": "..."},
    "source_lineage": {"path": "...", "sha256": "..."}
  }
}
```

## Stop Conditions

Stop for a lineage/path/hash mismatch, missing required table, semantic mixing,
clock/alignment failure, silent row loss, dependency/model omission, required
high-latency window without valid live samples, hand-edited output, or any GPU
activity. Preserve unavailable states rather than guessing.
