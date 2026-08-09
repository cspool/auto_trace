---
name: qwen-dcu-segmented-process-attribution
description: Execute fresh-run R05 for Qwen3.5-27B. Combine only the same run's R01-R04 evidence into a complete layer-conserved process denominator with explicit type mapping, estimate provenance and risk, while keeping the later R07 full-request process trace authoritative for observed process duration.
---

# Qwen DCU Fresh-Run R05 Segmented Process Attribution

Scale representative Qwen3.5-27B vLLM/PRA process evidence to the full layer
schedule without presenting estimates as direct measurements.

Require `user.evidence_acquisition_mode=fresh_no_prior_runtime_reuse`. Build the
whole current-request denominator only from this run's R01-R04 ledger. Every R01
event must receive one deterministic assignment and every metric must conserve
its source-layer total. Never import Workflow04 rows from another runtime tree.

The confirmed current-project bindings are the canonical project root
`/public/home/tangyu408/Qwen_DCU_Worker_0`, the `pra2026-bh408` vLLM/PRA source
tree, the `Qwen3.5-27B` model entry, and the ROCm/DCU/HIP accelerator stack.
`perf_trace_bk` is read-only archived binding evidence, never fresh runtime
evidence or a live default input. Resolve unknown concrete tool, script, schema,
and artifact paths from the live current project at runtime.

## Require Upstream Evidence

Read the current repository workflow:

```text
perf_trace/workflows/04_full_layer_fx_process_wise_estimate.md
```

Require inputs from one compatible Qwen3.5-27B vLLM/PRA SAME_INPUT contract:

```text
full input-layer performance CSV from the layer-wise workflow
layer kernel-breakdown CSV
representative process attribution CSV
representative process report
layer performance report
```

Reject mixed variants, prompts, token counts, shapes, timing definitions, or
runtime lineages unless the intended difference is part of the experiment.
Different recorded source revisions across R01-R05 are allowed when they are
same-lineage trace/tooling stage deltas and the semantic request is preserved.

Missing or incomplete R01-R04 inputs are a stop condition. R05 must not invoke
another Skill, regenerate a predecessor, or silently replace a missing
handoff; resume or replay the owning predecessor through the scheduler first.

## Build the Type Map

Define deterministic target-layer types from fields supported by the complete
layer evidence, such as:

```text
variant
phase
q_len / kv_len shape class
layer region
attention/backend path
pruning or selection state
```

For every target occurrence, record:

```text
attribution_type_id
attribution_source
representative event or template
match rationale
risk/status
```

Do not silently use nearest-shape or nearest-layer fallbacks. Mark them as
estimates and expose the distance or mismatch.

## Allocate with Conservation

Use the target layer's measured metric as the denominator. Derive process
fractions from a compatible representative template and normalize them before
scaling.

For each `(variant, phase, layer, occurrence, metric)` require:

```text
sum(process_ms) == source_layer_metric_ms
```

within floating-point tolerance.

Preserve metric identity. Do not allocate NVTX CPU time using CUPTI fractions
or combine CPU and GPU metrics. Here `NVTX` and `CUPTI` name required semantic
roles, not confirmed current tool bindings: resolve and verify equivalent
host-range and launch-owned kernel semantics against the active ROCm/DCU/HIP
tool and schema at runtime. Fail rather than rename or mix metrics when that
equivalence cannot be confirmed.

Use evidence labels consistently:

- `observed_fx_op`: directly observed representative process evidence;
- `template_scaled`: normalized estimate applied to another target occurrence;
- explicit fallback labels for weaker mappings.

Never describe `template_scaled` rows as direct full-layer traces.

## Generate the Evidence Package

Use the repository's maintained segmented process attribution generator:

```text
/public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408/scripts/perf_trace/generate_segmented_process_attribution.py
```

Pass the scheduler-assigned `runtime_artifact_root` as `--output-dir`. If the
generator is missing or incorrect, repair that canonical path and record the
R05 tooling delta; do not create a parallel one-off generator.

```bash
python3 /public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408/scripts/perf_trace/generate_segmented_process_attribution.py \
  --r01-handoff <same-run-R01-handoff.json> \
  --r02-handoff <same-run-R02-handoff.json> \
  --r03-handoff <same-run-R03-handoff.json> \
  --r04-handoff <same-run-R04-handoff.json> \
  --source-root /public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408 \
  --full-input-layer-csv <same-run-R01-all-input-layer.csv> \
  --layer-kernel-csv <same-run-R01-layer-kernel.csv> \
  --representative-process-csv <same-run-R03-process-attribution.csv> \
  --representative-report <same-run-R03-process-report.md> \
  --layer-report <same-run-R01-layer-report.md> \
  --output-dir <runtime_artifact_root> \
  --run-id <run_id> \
  --branch workflow01-10-fresh-e2e
```

Run the same generator a second time with identical arguments except
`--output-dir <runtime_artifact_root>/determinism_rerun`. Do not modify source
or any input between the two generations. Then finalize R05 only through the
maintained independent auditor:

```bash
python3 /public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408/scripts/perf_trace/audit_qwen_segmented_process_attribution.py \
  --project-root /public/home/tangyu408/Qwen_DCU_Worker_0 \
  --source-root /public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408 \
  --model-root /public/home/tangyu408/Qwen_DCU_Worker_0/Qwen3.5-27B \
  --served-model-name <same-run-served-model-name> \
  --runtime-root <runtime_root> \
  --runtime-artifact-root <runtime_artifact_root> \
  --primary-output-dir <runtime_artifact_root> \
  --determinism-output-dir <runtime_artifact_root>/determinism_rerun \
  --runtime-handoff-output <runtime_handoff_output> \
  --r01-handoff <same-run-R01-handoff.json> \
  --r02-handoff <same-run-R02-handoff.json> \
  --r03-handoff <same-run-R03-handoff.json> \
  --r04-handoff <same-run-R04-handoff.json> \
  --generator /public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408/scripts/perf_trace/generate_segmented_process_attribution.py \
  --run-id <run_id> \
  --branch workflow01-10-fresh-e2e
```

The generator and auditor must record distinct R01-R05 stage source revisions,
the R05 dirty-state digest, and `source_hash_equality_required=false`. They may
compare primary and deterministic-rerun file hashes, but must never compare one
stage's source hash with another as a completion gate.

Produce:

```text
SAME_INPUT_QWEN3_5_27B_VLLM_PRA_FULL_EAGER_FULL_LAYER_PROCESS_ATTRIBUTION_REPORT.md
SAME_INPUT_FULL_LAYER_PROCESS_ATTRIBUTION_BREAKDOWN.md
full_layer_attribution_type_map.csv
full_layer_template_assignment.csv
full_layer_process_attribution.csv
full_layer_process_aggregation.csv
full_layer_coverage_and_risk.csv
```

Generate reports from the tables. Do not repair generated totals manually.

## Validate

Check that every assignment row has both `attribution_source` and
`attribution_type_id`. Then group the attribution table by:

```text
(variant, phase, layer, occurrence, metric)
```

Compare the process sum with `source_layer_metric_ms` for every group. Report
the maximum absolute conservation error and fail when it exceeds the chosen
numeric tolerance.

Also verify:

- every denominator row has one assignment;
- each referenced template exists in representative evidence;
- process IDs and aggregation keys remain stable;
- coverage and risk counts reconcile with assignment rows;
- reports distinguish direct, scaled, and fallback evidence;
- regenerated output is deterministic for identical inputs.

## Interpretation Rules

- Normalize representative process proportions to each target layer's own
  measured metric.
- Do not copy a representative absolute latency onto another layer.
- Keep layer totals authoritative when process estimates disagree.
- Use runtime-resolved ROCm/DCU/HIP hardware diagnostics only to explain
  bottlenecks; never let them replace the timing denominator.
- State coverage, fallback use, and conservation error beside performance
  conclusions.

R05 estimates and risk flags are planning evidence for R06; the later R07
full-request process trace is authoritative for observed process duration. R05
may change its attribution generator, type mapper, report generator,
schemas, or validators. Record the R05 stage source delta without requiring
hash equality with R01-R04. Do not mutate the hashed upstream measurements or
change model/input/process semantics.

## Scheduler Handoff

Write only the scheduler-assigned R05 JSON handoff after deterministic rerun,
full denominator coverage, metric conservation, and risk reconciliation pass.
Hash-index all generated outputs and the immutable R01-R04 inputs. R05 must not
invoke R06 or rewrite a predecessor.
