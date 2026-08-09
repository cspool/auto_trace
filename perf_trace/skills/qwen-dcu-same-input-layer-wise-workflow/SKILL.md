---
name: qwen-dcu-same-input-layer-wise-workflow
description: Execute fresh-run R01 for Qwen3.5-27B on ROCm/DCU/HIP. Freeze one SAME_INPUT semantic contract, capture every request layer occurrence on physical DCU 1, preserve strict HIPTX-to-runtime-to-HIPOPS ownership, and hand the complete observed layer denominator to R02-R10 without reusing prior runtime evidence.
---

# Qwen DCU Fresh-Run R01 Layer Trace

Capture the complete layer-level denominator required by later full-layer
process attribution for Qwen3.5-27B in the `pra2026-bh408` vLLM/PRA runtime.
Keep this workflow separate from representative process-wise instrumentation.

## Run Contract

Require `user.evidence_acquisition_mode=fresh_no_prior_runtime_reuse`. Consume
no prior `perf_trace/runtime` measurement, attribution, contract, or completion
artifact. Older files may be inspected only as tool documentation and must not
appear in evidence provenance.

R01 may change launchers, profiler integration, trace markers, analyzers, or
validators before capture. Record the R01 stage delta and post-change source
state. Preserve model, weights, dtype, prompt/tokens, sampling, device mapping,
process identity, and inference output semantics. A later stage may have a
different source hash without creating another lineage.

## Freeze the SAME_INPUT Contract

Before running, record:

```text
variant and config
source revision
dirty-status inventory and traced-source hashes (provenance, not a future-stage equality gate)
Qwen3.5-27B model and vLLM/PRA config
prompt/input digest
MAX_NEW_TOKENS
warmup count
seed and sampling settings
dtype and attention backend
ROCm/DCU/HIP device
output tag and directory
```

Refuse to compare or merge runs whose contract differs without naming the
difference. Use a new output directory for a fresh run.

R01 may patch its launcher, profiler, trace markers, or analyzers before the
capture. Freeze and record the resulting R01 stage source state and prove the
measured output contract. Later goals in the same run may add their own trace
instrumentation; their source hashes need not equal R01, and that alone does
not create a new lineage.

Read the current repository workflow first:

```text
perf_trace/workflows/01_layer_wise_end_to_end_trace.md
```

## Run the Layer Trace

Use the maintained layer-profile wrapper in the active `pra2026-bh408`
worktree. All generated evidence belongs under the scheduler-assigned
`runtime_artifact_root`; the scheduler handoff remains a separate JSON file.
Preserve this invocation shape:

```bash
env \
ROOT_DIR=/public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408 \
CONFIG=qwen3.5-27b-vllm-pra-eager-gfx936 \
TAG=<fresh-Qwen3.5-27B-same-input-layer-tag> \
OUTPUT_DIR=<runtime_artifact_root>/raw \
REPORT_DIR=<runtime_artifact_root>/reports \
RUNTIME_ARTIFACT_ROOT=<runtime_artifact_root> \
CONTRACT_PATH=<runtime_artifact_root>/R01_SAME_INPUT_CONTRACT.json \
MODEL_ROOT=/public/home/tangyu408/Qwen_DCU_Worker_0/Qwen3.5-27B \
SERVED_MODEL_NAME=Qwen3.5-27B \
PRA_BACKEND_PERF_PROCESS_PROFILE=0 \
MAX_NEW_TOKENS=32 \
WARMUP_ITERS=1 \
DCU_DEVICE=1 \
bash /public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408/scripts/perf_trace/run_qwen_layer_profile_single_request.sh
```

Run one fresh non-replay request serially on physical DCU 1 with
`HIP_VISIBLE_DEVICES=1` and `CUDA_VISIBLE_DEVICES=1`. Keep that device policy
for every later GPU stage in this run.

Do not require the runtime-resolved process-range marker family here. Require
complete coverage of the runtime-resolved layer-range marker family. Resolve
the concrete HIP marker namespace from the active run rather than treating
archived marker names as fresh evidence.

## Generate Required Evidence

Use or recreate the repository's layer report generator instead of hand-editing
reports. Resolve the concrete raw and queryable hipprof trace formats at runtime
without weakening the required evidence set. Produce:

```text
SAME_INPUT_QWEN3_5_27B_VLLM_PRA_LAYER_PERFORMANCE_REPORT.md
<tag>.json
<tag>.<runtime-resolved-raw-profiler-trace>
<tag>.<runtime-resolved-queryable-trace>
<tag>_layer_events.csv
<tag>_layer_kernel_breakdown.csv
<tag>_layer_kernel_breakdown.json
<tag>_all_input_layer_performance.csv
<tag>_stats_*.csv
```

The complete input-layer table is the downstream denominator. Preserve one row
per `(contract, forward, layer, occurrence, metric)` and keep phase, `q_len`,
`past_len`, `kv_len`, and workload type.

## Enforce Strict Attribution

For ROCm/DCU/HIP timing, apply the runtime-resolved strict sampled-latency
attribution capability. The active hipprof command and schema must be verified
at runtime; refuse to continue if they cannot enforce:

```text
layer HIPTX host range
-> HIP Runtime calls whose host start lies inside the range
-> hipprof HIPOPS kernels joined by runtime `_Index`
-> full durations summed as launch-owned kernel time
```

Keep these metrics distinct:

- synchronized request or clock latency;
- HIPTX host range duration;
- hipprof HIP launch-owned kernel sum.

Do not attribute by device timestamp overlap. Do not sum nested `total`, `attn`,
and `mlp` rows as independent costs.

## Audit Completeness

Resolve the query tool and active hipprof schema at runtime. The first check
must count all layer HIPTX ranges in the queryable trace:

```bash
<runtime-resolved-query-tool> <layer-trace-queryable-database> \
  "<runtime-resolved query counting all layer HIPTX ranges>"

rg -n '_Index|launch-owned|all input-layer' \
  <layer-report>
```

Verify:

- each complete forward contains the expected model layer count;
- every layer event has a unique occurrence key;
- layer events and kernel-breakdown rows join without silent drops;
- the all-input-layer table covers every downstream target layer;
- the raw hipprof trace or runtime-resolved queryable database and exported
  tables come from the same run;
- placeholders, archive- or backup-only artifacts including `perf_trace_bk`,
  and stale `latest` pointers are not treated as evidence.

Report missing rows and failed joins explicitly.

## Preserve the Evidence Boundary

This workflow measures layer totals. It does not establish strict process-wise
timing and must not split layer totals among processes.

Index the complete layer table in the R01 handoff for the scheduler's serial
R02-R05 consumers; R01 itself must not invoke a later Skill. R01 is complete
only when the current request marker, every
forward/layer occurrence, runtime event, strict launch ownership row, raw
queryable hipprof data, and request wall-clock anchors are present and R06 can
derive the same request's complete process target set.

Write only the scheduler-assigned R01 JSON handoff after these checks pass. It
must hash-index the frozen semantic contract, layer evidence, raw/queryable
trace, report, stage source state, and validation results; all business
artifacts remain under `runtime_artifact_root`.
