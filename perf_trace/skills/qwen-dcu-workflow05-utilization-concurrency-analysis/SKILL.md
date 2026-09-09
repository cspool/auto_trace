---
name: qwen-dcu-workflow05-utilization-concurrency-analysis
description: Build complete same-lineage process, utilization and concurrency analyses, or validate retained resource sidecars and the shared Process pile plan without changing source classifications.
---

# R09: Process evidence and analytical views

Own the full normalized analysis and deterministic display plan. Preserve
the observed event universe while exposing explicit resource availability;
R10 filtering must not erase base-table records.

Read the [shared Process/resource contract](../qwen-dcu-workflow05-trace-visualization-reporting/references/process-resource-contract.md) for formulas,
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

1. Validate R07 observed scope, live-sampling gates, exact ownership and R08
   resource identity. Keep timing, sampling coverage and PMC coverage separate.
2. Produce the complete twelve normalized tables in fresh mode. For retained
   work, preserve accepted tables and write separate derived sidecars.
3. Compute type-duration totals from all valid observed Process instances,
   apply the strict ten-percent threshold, cluster into five duration piles and
   rank piles globally. Preserve original high-latency classifications.
4. Validate directional replay bandwidth, L2 metrics and per-metric coverage;
   never use replay duration in observed latency/concurrency calculations.
5. Seal tables, view-plan inputs, resource sidecars, formulas and independent
   checks. Pass full evidence and the resolved plan to R10, not a filtered table.

## Local tools and capability boundary

The project tools are in `perf_trace/scripts/` (also used for Batch8).
Read the [execution guide](../../scripts/process_pile_assets/README.md)
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
runtime_branch=workflow01-10-fresh-e2e
runtime_goal=R09
runtime_predecessors=R01,R02,R03,R04,R05,R06,R07,R08
runtime_artifact_root=<scheduler-assigned>
runtime_handoff_output=<scheduler-assigned>
advance_only_after=complete
```
