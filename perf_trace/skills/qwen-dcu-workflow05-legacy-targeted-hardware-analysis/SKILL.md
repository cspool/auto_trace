---
name: qwen-dcu-workflow05-legacy-targeted-hardware-analysis
description: Execute legacy Workflow05 R08 for the hardware-family gaps authorized by R06/R07. Collect bounded serial PMC replay evidence on physical DCU 1, join exact family/name/order identities, and keep replay counters and durations separate from all non-replay latency axes.
---

# Qwen DCU Legacy Workflow05 R08 Hardware Gaps

## Contract

Require `user.evidence_acquisition_mode=historical_then_selective` and the exact
unresolved hardware-family set from R06/R07. Reuse a compatible base hardware
row only when its semantic family identity is proven; otherwise collect a new
bounded replay batch.

R08 may change profiler wrappers, counter sets, parsers, consolidators, or
validators. Record those changes and preserve model/input/output semantics.

## Workflow

1. Probe the physical DCU 1 architecture and counter availability.
2. Resolve each target to one literal kernel-family identity.
3. Collect `pmc`, `pmc-read`, and `pmc-write` serially when supported.
4. Join by capture, exact demangled name, family and dispatch order.
5. Mark every target `collected`, `reused_compatible`, `no_kernel`,
   `unavailable`, or `failed`.
6. Preserve PMC duration as diagnostic-only and never use it as latency.

## Required Outputs

```text
device_capabilities.json
targeted_family_plan.json
hardware_metrics.csv
hardware_metrics_by_kernel_family.csv
hardware_coverage.json
R08_COMPLETION_AUDIT.json
```

## Handoff

Write only the scheduler-assigned R08 handoff. Coverage is complete only when
every authorized family has exactly one final disposition and all accepted
joins pass the replay/non-replay evidence boundary.

