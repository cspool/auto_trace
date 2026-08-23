---
name: qwen-dcu-workflow05-evidence-planning
description: Build the R06 plan for one Qwen3.5-27B fresh R01-R10 DCU trace lineage. Validate only the current run's R01-R05 ledger, record allowed stage instrumentation changes without requiring source-hash equality, derive complete process target files plus a bounded PMC subset, and probe offline visualization interfaces without running a model or GPU. Use at R06 before the full-request R07 capture.
---

# Qwen DCU Fresh-Run Evidence Planning

## Objective

Prepare R07-R10 from the completed R01-R05 prefix of the same scheduler run.
R06 performs deterministic planning and offline capability probes only. It does
not run the model, use a GPU, collect a new trace, or import measurements from
another runtime tree.

Use the canonical roots:

```text
project_root=/public/home/tangyu408/Qwen_DCU_Worker_0
trace_target_root=/public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408
```

## Required Mode

Require all of the following before work:

```text
branch=workflow01-10-fresh-e2e
user.evidence_acquisition_mode=fresh_no_prior_runtime_reuse
completed ledger prefix=R01,R02,R03,R04,R05
```

Reject any other branch or evidence mode. Legacy existing-evidence planning is
owned by the removed result-reuse planning path; never mix its evidence
or completion schema into this Skill.

## Fresh-Run Lineage Contract

Treat R01-R10 as one lineage identified by:

```text
branch + run_id + R01 semantic contract_id
```

Source byte identity is not a completion condition. R01-R10 may modify source
files to add trace markers, collectors, exporters, analyzers, validation, or a
generated performance profile. Record these changes as stage instrumentation
deltas. Keep semantically equivalent stages in the same fresh-run lineage; a
changed source hash alone is provenance, not a lineage transition.

Preserve these semantic invariants instead:

- model identity, weights, dtype, input/prompt and sampling;
- one physical DCU 1 and the recorded single-card mapping;
- request shape and token limits;
- process IDs, FX/process definitions, range nesting, and ownership semantics;
- unchanged inference output when a stage changes executable instrumentation;
- evidence-class separation among observed, attributed, inferred,
  replay-projected, heuristic, and unavailable values.

Stop when a change alters one of those invariants or output equivalence cannot
be shown. A changed file hash by itself is audit information, not failure.

Write `fresh_run_lineage_manifest.json` with at least:

```json
{
  "schema_version": 1,
  "status": "PASS",
  "branch": "workflow01-10-fresh-e2e",
  "run_id": "...",
  "lineage_id": "...",
  "semantic_contract_id": "...",
  "evidence_source_policy": "current_run_only",
  "source_change_policy": "stage_trace_instrumentation_allowed",
  "source_hash_equality_required": false,
  "external_runtime_reference_count": 0,
  "upstream_goals": ["R01", "R02", "R03", "R04", "R05"],
  "runtime_references": [{"path": "...", "sha256": "..."}],
  "stage_instrumentation_deltas": [],
  "semantic_invariants": {"status": "PASS"}
}
```

Every `runtime_references[].path` must resolve under this run directory. Hash
each referenced handoff/artifact for provenance, but do not compare current
source hashes to an earlier stage as a pass/fail gate.

## Inputs and Validation

Consume only the cumulative ledger supplied by the scheduler. Require exactly
the completed R01-R05 prefix in order and revalidate each handoff path, payload,
and recorded SHA-256. Refuse directory scanning to discover another run.

Use the current-run products with these boundaries:

| Goal | Input role |
|---|---|
| R01 | semantic request contract, layer events, observed layer trace and strict launch ownership |
| R02 | current-run FX/process definitions, exact process inventory and instrumentation validation |
| R03 | process attribution derived from the current R01/R02 evidence |
| R04 | current-run non-replay process/family timing plus replay-projected DCU counters |
| R05 | complete layer/process aggregation, type map, risk and conservation tables |

Never add host-range duration, kernel-duration sum, or busy union as if they
were the same metric. Never use replay duration as request/process latency.

## Planning Workflow

1. Revalidate the R01-R05 ledger and write the lineage manifest.
2. Reconcile R01 event order with the exact R02 process inventory.
3. Build a whole-request planning index from current-run rows only.
4. Write every expected event and process range to deterministic newline files.
5. Rank a bounded high-latency/high-risk family subset for expensive R08 PMC.
6. Run the maintained lineage/target manifest builder after the three target
   files are final:

   ```text
   python3 pra2026-bh408/scripts/perf_trace/build_fresh_run_lineage_manifest.py \
     --project-root <project_root> \
     --runtime-root <runtime_root> \
     --branch <branch> \
     --run-id <run_id> \
     --ledger <runtime_root>/runtime_handoff_ledger.json \
     --semantic-contract <same-run-R01-contract> \
     --event-targets <full_request_process_targets.txt> \
     --range-targets <full_request_process_range_targets.txt> \
     --hardware-plan <bounded_hardware_plan.csv> \
     --output-dir <runtime_artifact_root>
   ```

   Add `--stage-delta-manifest` once for every already-recorded R01-R06
   instrumentation delta. Do not hand-edit either generated manifest.
7. Probe visualization interfaces offline in this order: official Perfetto
   Python API, advertised Trace Processor CLI, local Perfetto-compatible file,
   then a visibly labeled self-contained Plotly fallback.
8. Independently recompute counts, joins, hashes, conservation, and target
   coverage before writing the handoff.

The full R07 target lists are not cost-truncated. The bounded ranking controls
only R08 PMC and R10 zoom selection.

## Required Outputs

Write under `runtime_artifact_root`:

```text
fresh_run_lineage_manifest.json
full_request_process_targets.txt
full_request_process_range_targets.txt
full_request_target_manifest.json
fresh_run_trace_index.csv
full_request_trace_plan.csv
bounded_hardware_plan.csv
tool_capability_probe.json
workflow05_open_source_trace_attempts.json
workflow05_tool_capability_manifest.json
third_party_provenance.json
R06_RUN_CONTRACT.json
R06_COMPLETION_AUDIT.json
```

`workflow05_tool_capability_manifest.json` describes the locally available
software interfaces only and must contain zero runtime-measurement references.
Use only the fresh-run lineage and target-building workflow defined in this
Skill; existing-evidence planners and their output schemas are outside R06.

`full_request_target_manifest.json` must contain:

```json
{
  "schema_version": 1,
  "status": "PASS",
  "lineage_id": "...",
  "event_target_file": {"path": "...", "sha256": "...", "line_count": 1},
  "range_target_file": {"path": "...", "sha256": "...", "line_count": 1},
  "capture_scope": "one_fresh_run_request_all_process_ranges",
  "r08_hardware_subset": {"path": "...", "sha256": "...", "row_count": 1}
}
```

Require positive event/range counts, unique nonempty lines, exact reconciliation
to R01/R02, and no path outside the current run.

## Handoff

Write only the scheduler-assigned R06 handoff. Require:

```json
{
  "runtime_goal": "R06",
  "status": "complete",
  "execution_status": "complete",
  "evidence_status": "complete",
  "coverage_target_met": true,
  "next_authorization_required": false,
  "fresh_e2e_evidence": {
    "schema_version": 1,
    "status": "complete",
    "lineage_id": "...",
    "fresh_run_lineage_manifest": {"path": "...", "sha256": "..."},
    "full_request_target_manifest": {"path": "...", "sha256": "..."}
  }
}
```

An unavailable official Perfetto parser may be a recorded presentation
capability degradation, but it does not degrade complete lineage/target
planning when the compatible file and labeled fallback probes pass.

## Stop Conditions

Stop without a complete handoff for an external runtime reference, incomplete
R01-R05 prefix, semantic-contract change, output-equivalence failure, target
count mismatch, nonunique range, path escape, ledger drift, or any GPU/model
activity during R06. Preserve diagnostics in the attempt directory.
