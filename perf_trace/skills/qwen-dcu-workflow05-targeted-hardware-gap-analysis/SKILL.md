---
name: qwen-dcu-workflow05-targeted-hardware-gap-analysis
description: Execute R08 for one Qwen3.5-27B fresh R01-R10 lineage. Consume the same run's R07 observed full-request trace and R06 bounded family plan, allow audited profiling-tool source changes without source-hash equality, collect serial DCU 1 PMC evidence, probe gfx936 capabilities, and build the FX-visible traffic/DCU-resource model without turning replay timing into latency.
---

# Qwen DCU Fresh Targeted Hardware Evidence

## Objective

Attach fresh, replay-projected hardware diagnostics to the bounded high-value
kernel-family subset selected by R06 while preserving R07 non-replay time as
the only latency axis. Build the traffic/resource model used by R09 and R10.

## Inputs

Require `user.evidence_acquisition_mode=fresh_no_prior_runtime_reuse` and the
same run's complete R06/R07 handoffs. Rehash:

- R06 lineage and target manifests;
- R06 bounded hardware-family plan;
- R07 full-request metadata and normalized timing/ownership tables;
- R07 fresh-run dependency adapter;
- current profiler, capability probe, consolidator, and model builder.

Reject paths from another runtime tree, archived PMC data, user-supplied
adapters/models, and untracked substitutions.

## Lineage and Source Changes

Carry the same `lineage_id`. R08 may change profiling wrappers, counter lists,
exporters, analyzers, or trace-only code. Record these changes in
`R08_SOURCE_LINEAGE.json`; source hash equality with R01/R07 is not required.

Preserve model/input/sampling/device and inference-output semantics. Stop when
a change alters those semantics or invalidates R07 process/family identity.

## Device and Collection

Use physical DCU 1 only and run GPU work serially. Re-probe device identity and
load immediately before each capture. Allocate a new empty output directory for
every replay mode/batch.

Use R06's bounded family subset, not the full process target list, for expensive
PMC work. A plan-bounded superset capture is allowed only when every discarded
row is audited and exact selected-family post-attribution is complete.

For each batch:

1. freeze the exact request, environment, literal kernel-family filter and
   expected process/family order;
2. collect the required compute, memory/cache and occupancy/stall counter modes
   in separate fresh roots;
3. retain raw DB/PMC/exporter logs and device/tool provenance;
4. recover selected rows by same-replay pid, exact name subsequence and dispatch
   order, then strict HIPTX/runtime/`_Index`/HIPOPS ownership;
5. require selected-name/order match rate at least `0.99`, zero selected
   ambiguity, and complete selected-family coverage.

Never use replay duration, replay launch gaps, or replay overlap as request or
process latency.

## Capability Probe

Run:

```text
pra2026-bh408/scripts/perf_trace/probe_dcu_capabilities.py
```

Require physical device 1 and architecture `gfx936`. Record verified counter
availability and unavailable quantities explicitly. Do not infer HBM/DRAM
bandwidth from logical tensor bytes. Treat occupancy formulas as theoretical
upper bounds unless an achieved field is directly observed.

## Traffic and Resource Model

Run:

```bash
python3 pra2026-bh408/scripts/perf_trace/build_traffic_resource_model.py \
  --lineage-manifest <R06-fresh-run-lineage-manifest.json> \
  --dependency-adapter <R07-fresh-run-dependency-adapter.json> \
  --hardware-metrics <R08-hardware-metrics.csv> \
  --device-capabilities <R08-device-capabilities.json> \
  --output-dir <runtime_artifact_root>/traffic-resource-model
```

Inputs are the R07 fresh-run dependency adapter, R08 current PMC metrics, the
R01/R02 fixed-input FX shapes referenced by the lineage, and the R08 capability
JSON. Require:

```text
model_type=fresh_run_fx_visible_traffic_and_dcu_family_resource
status=complete
lineage_id=<R06/R07 lineage_id>
traffic_boundary.hbm_or_dram_traffic_claimed=false
resource_boundary.achieved_occupancy_claimed=false
```

Logical FX tensor bytes, visible working sets, FLOPs, theoretical occupancy,
observed counters, replay projections, and unavailable values must remain
separate fields.

## Required Outputs

Write under `runtime_artifact_root`:

```text
R08_SOURCE_LINEAGE.json
device_capabilities.json
targeted_family_plan.json
raw/<batch>/...
hardware_metrics.csv
hardware_metrics_by_kernel_family.csv
hardware_coverage.json
traffic-resource-model/process_traffic_model.csv
traffic-resource-model/kernel_family_resource_model.csv
traffic-resource-model/traffic_resource_model.json
R08_COMPLETION_AUDIT.json
```

Every selected R07 family must appear exactly once in the final disposition as
`collected`, `no_kernel`, `unavailable`, or `failed`.

## Handoff

Write only the scheduler-assigned R08 handoff:

```json
{
  "runtime_goal": "R08",
  "status": "complete",
  "execution_status": "complete",
  "evidence_status": "complete",
  "coverage_target_met": true,
  "next_authorization_required": false,
  "fresh_e2e_evidence": {
    "schema_version": 1,
    "status": "complete",
    "lineage_id": "...",
    "device_capabilities": {"path": "...", "sha256": "..."},
    "traffic_resource_model": {"path": "...", "sha256": "..."},
    "source_lineage": {"path": "...", "sha256": "..."}
  }
}
```

## Stop Conditions

Stop for external evidence, lineage mismatch, semantic-contract change,
concurrent GPU use, cap violation, profiler/device drift, filter ambiguity,
selected-family coverage gaps, ownership failure, unverified required counter
semantics, replay timing mixed into latency, or model-builder validation
failure. Preserve raw evidence and diagnostics.
