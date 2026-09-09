---
name: qwen-dcu-workflow05-trace-visualization-reporting
description: Build high-latency Process trapezoids and hardware-associated resource windows with shared time axes, continuous resource heights, explicit omissions and offline audits; distinguish retained presentation from formal fresh R10.
---

# R10: Process evidence and analytical views

Give the two views distinct jobs: high latency shows the captured Process
distribution; concurrency/resource visualization shows only successfully
associated hardware windows by default.

Read the [shared Process/resource contract](references/process-resource-contract.md) for formulas,
selection, geometry, availability, time mapping and acceptance. Its rules are
shared across R08–R10 so producer fields and displayed meaning stay consistent.

## Execution modes

For a scheduler-assigned fresh stage, read [formal runtime requirements](references/formal-runtime.md)
and validate its full predecessor prefix, target/profile/topology, source hashes,
artifact ownership, immutable attempts and handoff gates. These formal rules
remain applicable even when the visual subset is small.

For retained evidence, work in a separate output directory, keep original
archives/tables/handoffs unchanged, and record `formal_r10_regeneration=false`
for presentation. Restoring existing bytes and calculating sidecars is not a
new R07/R08 acquisition or a fresh R09/R10 handoff. Do not invoke the scheduler,
create a Goal or start a profiler merely to revise a report.

## Procedure

1. Validate the full source universe, declared Process scope, derived pile plan
   and resource provenance. A request envelope is not full-token trace coverage.
2. Draw all selected Process member intervals in trapezoid group outlines on
   the common observed axis; resource absence must not delete Process evidence.
3. In the resource view, retain only windows with valid exactly associated
   non-compute hardware metrics; hide empty piles without renumbering ranks.
4. Show compute, directional bandwidth and available L2 indicators simultaneously,
   with continuously proportional heights and explicit units/evidence classes.
   Epsilon is a non-measured marker for short-window nulls, never a numeric fill.
5. Keep ten original time sections. Fold on one common mapping; omit only the
   resource view's global no-eligible-data union complement with `»` boundaries.
   Preserve absolute timestamps and provide restoration controls.
6. Independently audit source conservation, pile membership/order, trapezoid
   containment, resource values/heights, eligibility, omission safety and offline
   interaction. Deliver the full evidence archive separately from filtered views.

## Local tools and capability boundary

The project tools are in `perf_trace/scripts/` (also used for Batch8).
Read the [execution guide](../../../perf_trace/scripts/process_pile_assets/README.md)
when restoring or generating a retained report.

- Restore/calculate: `restore_batch8_bandwidth_sources.py`,
  `calculate_batch8_replay_bandwidth.py`, `audit_batch8_replay_bandwidth.py`,
  `calculate_batch8_l2_activity.py`.
- Render/audit retained supported schemas: `build_process_duration_piles.py`,
  `audit_process_duration_piles.py`.

These retained adapters do not implement a fresh scheduler stage or regenerate
its twelve-table analysis. A formal R10 must use a bound native builder that
implements the same profile; verify capability before declaring completion.
No new acquisition, upload or publication is implied. Keep existing user scope.

## Serial Runtime Contract

This machine-readable block applies only to fresh execution. It preserves the
existing scheduler interface; retained work does not emit this handoff.

```text
trace_profile_id=batch8-dual-dcu-dp2
workload_mode=batch8_concurrent_requests
batch_size=8
max_concurrency=8
physical_devices=0,1
HIP_VISIBLE_DEVICES=0,1
CUDA_VISIBLE_DEVICES=0,1
tensor_parallel_size=1
pipeline_parallel_size=1
data_parallel_size=2
data_parallel_backend=mp
runtime_branch=workflow01-10-fresh-e2e
runtime_goal=R10
runtime_predecessors=R01,R02,R03,R04,R05,R06,R07,R08,R09
required_handoff_fields=status,execution_status,evidence_status,coverage_target_met,next_authorization_required,runtime_branch,runtime_goal,runtime_run_id,lineage_id,trace_profile_sha256,cumulative_runtime_ledger_sha256,r01_handoff_sha256,r02_handoff_sha256,r03_handoff_sha256,r04_handoff_sha256,r05_handoff_sha256,r06_handoff_sha256,r07_handoff_sha256,r08_handoff_sha256,r09_handoff_sha256,offline_acceptance_manifest_sha256,full_timeline_manifest_sha256,full_perfetto_trace_sha256,e2e_process_timeline_sha256,e2e_process_timeline_lossless_sha256,high_latency_process_hardware_timeline_sha256,concurrency_utilization_sha256,index_html_sha256,source_lineage_sha256,artifact_manifest_sha256,completion_audit_sha256
runtime_artifact_root=<scheduler-assigned>
runtime_handoff_output=<scheduler-assigned>
advance_only_after=complete
```
