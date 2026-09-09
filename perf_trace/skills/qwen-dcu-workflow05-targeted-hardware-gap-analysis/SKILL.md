---
name: qwen-dcu-workflow05-targeted-hardware-gap-analysis
description: Collect bounded same-lineage PMC evidence or restore retained dispatch counters and their own timings for audited resource references. Preserve missing states and distinguish replay resources from observed latency.
---

# R08: Process evidence and analytical views

Own hardware evidence and its scope. Capture only when explicitly running
the authorized fresh R08 plan; for an existing report, restore and calculate
from retained counters before considering any new acquisition.

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

1. Identify fresh capture versus retained restoration; pin the lineage and sources.
2. In fresh mode, validate the R06 bounded plan, R07 ownership and formal runtime
   binding before any device work. Preserve full topology and immutable attempts.
3. Retain raw counters and their own begin/end times per dispatch. In retained
   mode, rehash existing archives/normalized records and perform CPU-only recovery.
4. Derive separate directional bandwidth and L2 activity only from supported
   counters; compare original derived metrics independently. Require valid
   own-pass durations, exact identities and shape gates for projection.
5. Publish metric coverage and reason-coded missing states with source hashes.
   Do not increase capture scope just to remove empty rectangles in a report.

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
runtime_goal=R08
runtime_predecessors=R01,R02,R03,R04,R05,R06,R07
runtime_artifact_root=<scheduler-assigned>
runtime_handoff_output=<scheduler-assigned>
advance_only_after=complete
```
