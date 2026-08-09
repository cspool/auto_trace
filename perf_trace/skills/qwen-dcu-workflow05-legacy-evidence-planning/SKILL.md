---
name: qwen-dcu-workflow05-legacy-evidence-planning
description: Execute legacy Workflow05 R06 when a compatible completed R01-R05 ledger is supplied or produced by the same low-cost branch. Validate the base evidence, build bounded selective process and hardware plans, and keep estimated, observed, replay-projected, and unavailable evidence classes separate without claiming a fresh full-request trace.
---

# Qwen DCU Legacy Workflow05 R06 Planning

## Contract

Require `user.evidence_acquisition_mode=historical_then_selective`. Accept the
immutable R01-R05 ledger provided by the scheduler; do not scan other runtime
directories. This Skill never emits `fresh_e2e_evidence` and never claims that
the base estimates and later selective captures share an absolute clock.

R06 is offline planning only. Do not run a model, GPU, profiler, or sampler.

## Workflow

1. Rehash every ledger handoff and referenced base artifact.
2. Build the full estimated process index from the base R05 attribution.
3. Rank candidates by configured latency coverage and feature diversity.
4. Write bounded process targets and hardware-family targets.
5. Probe local visualization interfaces without downloading software.
6. Record every base artifact as `base_estimate`, every planned measurement as
   `not_yet_observed`, and every missing field as `unavailable`.

Use `pra2026-bh408/scripts/perf_trace/prepare_workflow05_selective_capture.py`
for the maintained legacy planning contract. Do not use the fresh-run lineage
builder.

## Required Outputs

Write under `runtime_artifact_root`:

```text
workflow04_reuse_manifest.json
workflow05_trace_index.csv
selective_trace_plan.csv
selective_hardware_plan.csv
tool_capability_probe.json
workflow05_tool_capability_manifest.json
R06_COMPLETION_AUDIT.json
```

Require each selected semantic key to be unique and traceable to one base row.
Never use source-hash equality as a substitute for semantic compatibility.

## Handoff

Write only the scheduler-assigned R06 handoff with
`execution_status=complete`. Set `evidence_status`, `coverage_target_met`, and
`next_authorization_required` from the actual bounded plan. Do not include a
fresh-run lineage object.

