---
name: qwen-dcu-fx-process-nvtx-instrumentation
description: Execute fresh-run R02 for Qwen3.5-27B. Reconstruct every exact request shape class, map FX stages to eager vLLM/PRA symbols, add guarded pra.fx_process HIPTX ranges, prove output equivalence, and emit the same-lineage dependency inputs required by the full-request R07 trace.
---

# Qwen3.5-27B Fresh-Run R02 FX Process Instrumentation

Produce the R02 instrumentation contract consumed by
`$qwen-dcu-process-performance-breakdown`. Regenerate evidence from the current
R01 request and current `pra2026-bh408` worktree.
`perf_trace_bk` is read-only binding evidence and is never fresh runtime
evidence.

## Establish the Run Contract

Require `user.evidence_acquisition_mode=fresh_no_prior_runtime_reuse` and the
same run's complete R01 handoff. Cover every unique current-request `(phase,
layer_type, q_len, kv_len)` class. Permit transfer only for an audited exact
shape class and label it explicitly; never import a previous run's template.

Read the repository's current Workflow role document and source artifacts:

```text
perf_trace/workflows/02_representative_fx_process_wise_trace.md
<runtime-resolved-current-fx-artifact-root>/run_metadata.json
<runtime-resolved-current-fx-artifact-root>/fx_layer_events.csv
<runtime-resolved-current-fx-artifact-root>/*/fx_process_reconstruction.json
```

Locate the concrete current-run equivalents at runtime within
`/public/home/tangyu408/Qwen_DCU_Worker_0` when the repository or run layout
differs. Do not guess a path or bind current evidence to `perf_trace_bk`.
Record the exact input/config, code revision, phase, layer, occurrence,
`q_len`, `past_len`, and `kv_len`. Do not combine artifacts from different
contracts.

R02 is expected to edit runtime source when process/fragment ranges are
missing or incorrect. Record the R01 and post-R02 stage source states plus the
instrumentation delta. Source revision/hash equality with R01 is not required;
model/input/sampling/device semantics and output equivalence are required.

## Map FX Processes to Runtime Code

For every selected FX event:

1. Read the ordered process reconstruction, FX nodes, op families, inputs, and
   users.
2. Trace each process into the eager Qwen3.5-27B model/PRA/pruning/attention
   code actually reached by the profiled vLLM/PRA configuration.
3. Identify the smallest runtime symbol that owns the process without changing
   execution order, tensor values, synchronization, or backend selection.
4. Split a process into fragments when it spans functions or fused transitions.
5. Give all fragments of one logical process a shared `aggregation_key`.
6. Leave uncertain mappings visible as `ambiguous` or `unresolved`; do not
   convert assumptions into passing evidence.

Inspect at least:

```text
the current Qwen3.5-27B single-request profiling entry point resolved at runtime
the current ROCm/DCU/HIP process-trace launcher resolved at runtime
the pra2026-bh408 model/PRA/pruning/attention files reached by Qwen3.5-27B vLLM/PRA eager
```

Resolve the first two concrete paths from the current worktree and runtime at
execution time; do not infer them from the archived `perf_trace_bk` layout.

## Instrument Ranges

Guard instrumentation with the confirmed project process-profile flag
`PRA_BACKEND_PERF_PROCESS_PROFILE=1`. Keep the ordinary path unchanged when
the flag is not `1`.

Use stable, parseable names beginning with:

```text
pra.fx_process.
```

Encode enough identity to join a range to its parent layer, process, and
fragment. Preserve nested layer/process structure. Do not reuse one range name
for semantically different fragments.

Use a range mechanism exported to hipprof HIPTX events on ROCm/DCU/HIP. The
read-only archive confirms the historical transport binding
`torch.cuda.nvtx` on HIP to hipprof HIPTX, but validate a semantically
equivalent mechanism in the actual current runtime. If the concrete API, tool,
or path differs, resolve it at runtime rather than guessing. Do not assume a
Python context manager appears in the trace, and do not treat the archived
capture as current validation.

## Write the Handoff

Use the maintained current-worktree R02 toolchain; patch these tools or the
instrumented runtime source in place when needed, rather than creating a
parallel implementation:

```text
pra2026-bh408/scripts/perf_trace/prepare_qwen_r02_fresh_fx_plan.py
pra2026-bh408/scripts/perf_trace/capture_qwen_fresh_run_fx.py
pra2026-bh408/scripts/perf_trace/audit_qwen_r02_fresh_fx.py
pra2026-bh408/scripts/perf_trace/generate_qwen_fx_process_handoff.py
```

Pass `--runtime-artifact-root <runtime_artifact_root>` to the fresh FX capture
and keep its output directory plus intermediate capture handoff under that
root. Record R01 and R02 source states separately; never use revision or file
hash equality between stages as a completion gate.

Generate the business handoff under the scheduler-assigned artifact root:

```text
<runtime_artifact_root>/FX_PROCESS_NVTX_INSTRUMENTATION_HANDOFF.md
```

All other generated R02 evidence must also remain under
`runtime_artifact_root`. Write the separate scheduler JSON only to
`runtime_handoff_output`.

Include exactly these high-level sections:

```text
# FX Process NVTX Instrumentation Handoff
## Source FX Artifacts
## Execution Reproducibility Contract
## Instrumented Code Changes
## Process Range Inventory
## Range Naming Contract
## Expected Trace Outputs
## Validation Performed
## Open Risks
```

Give `Process Range Inventory` one row per process or fragment with:

```text
variant_scope
phase
layer_or_layer_pattern
process_id
process_title
fragment_id
aggregation_key
fx_nodes
fx_op_families
expected_kernel_families
torch_code_path
instrumented_file
instrumented_symbol
nvtx_range_name
range_parent
range_guard_or_flag
status
notes
```

Regenerate this file from current evidence. A handoff under `perf_trace_bk` is
only a schema reference and must never be copied as current evidence.

## Validate Before Handoff

Run syntax and focused tests for every edited source. Then run the smallest real
hipprof trace that reaches representative prefill and decode paths on
ROCm/DCU/HIP.

Verify:

```text
Using the current hipprof database or export schema resolved at runtime:
count HIPTX events whose message starts with "pra.fx_process."
require the count to be greater than zero
```

Also verify:

- every expected range appears under the intended layer;
- range identity joins uniquely to the handoff inventory;
- fragment rows share the intended `aggregation_key`;
- disabling `PRA_BACKEND_PERF_PROCESS_PROFILE` preserves ordinary behavior;
- model outputs remain equivalent within the repository's tolerance;
- expected kernel families are hypotheses, not claimed measurements.

Do not approve Stage A when the handoff is missing, stale, copied from
`perf_trace_bk`, or lacks same-input provenance.

## Evidence Boundary

This skill defines and verifies instrumentation. It does not claim process DCU
kernel time. The consumer must attribute:

```text
process HIPTX CPU range
-> HIP Runtime call launched inside the range and within its runtime index bounds
-> HIPOPS kernel with the identical runtime _Index
```

Resolve the concrete hipprof schema at runtime while preserving this strict
launch-ownership chain; the runtime `_Index` is the confirmed ROCm/DCU/HIP
correlation identity for this project binding.

Each reconstruction must expose stable node names, `args`/`users`, process
stage, shape, dtype, and opaque custom-op guards. Metadata must bind the R01
semantic contract and record both R01 and R02 source provenance without an
equality gate. Produce a hashed manifest for
`pra2026-bh408/scripts/perf_trace/build_fresh_run_dependency_adapter.py`. Temporal adjacency,
stream order, and queue order are never data dependencies.

Write only the scheduler-assigned R02 JSON handoff at
`runtime_handoff_output`, distinct from the Markdown business handoff, and only
after instrumentation, shape coverage, and output-equivalence checks pass. The
scheduler may then advance to R03; R02 must not invoke another Skill itself.
