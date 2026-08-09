---
name: qwen-dcu-process-performance-breakdown
description: Execute fresh-run R03 for Qwen3.5-27B. Consume only the same run's R01 observed layer denominator and R02 exact-shape FX/process reconstructions, regenerate the process attribution tables, preserve measured-versus-estimated boundaries, and record any analysis-tool source changes without a source-hash equality gate.
---

# Qwen DCU Fresh-Run R03 Process Breakdown

Produce Qwen3.5-27B vLLM/PRA process-wise attribution from the current run's
R01 SAME_INPUT evidence and R02 FX process reconstruction.

## Scope

Require `user.evidence_acquisition_mode=fresh_no_prior_runtime_reuse`. Consume
only the completed R01 and R02 ledger entries. R03 is analysis-only: do not run
model inference or ROCm/DCU/HIP profiling.

The confirmed current-project bindings are the canonical project root `/public/home/tangyu408/Qwen_DCU_Worker_0`, the `pra2026-bh408` vLLM/PRA source tree, the `Qwen3.5-27B` model entry, and the ROCm/DCU/HIP accelerator stack. `perf_trace_bk` is read-only archived binding evidence, never a source of fresh runtime evidence or a live default input.

Resolve, record, and export every runtime variable below from live current-project artifacts before using the shell or Python command blocks. A missing or ambiguous concrete script, artifact, worktree, or tool binding is a stop condition: do not guess it and do not fall back to `perf_trace_bk`.

The source vocabulary `Nsight`, `CUPTI`, `NVTX`, and `CUDA` is retained below where it names a required semantic role or compatibility schema. At runtime, verify and resolve an equivalent ROCm/DCU/HIP binding before execution. Archived binding evidence records `hipprof`, HIPTX, HIP runtime `_Index`, and HIPOPS, but it is not fresh runtime evidence and does not by itself establish tool or schema equivalence. Do not rename compatibility fields or weaken their ownership/timing semantics without that verification.

Main script and runtime path bindings:

```text
PROJECT_ROOT=/public/home/tangyu408/Qwen_DCU_Worker_0
PROJECT_SOURCE_ROOT=$PROJECT_ROOT/pra2026-bh408
MODEL_ROOT=$PROJECT_ROOT/Qwen3.5-27B
PERF_ROOT=$PROJECT_ROOT/perf_trace
RUNTIME_ARTIFACT_ROOT=<scheduler-assigned-runtime_artifact_root>
PROJECTION_SCRIPT=$PROJECT_SOURCE_ROOT/scripts/perf_trace/generate_qwen_process_performance_breakdown.py
FX_ROOT=<resolve the live FX reconstruction root at runtime>
LAYER_BREAKDOWN_ROOT=<resolve the live layer-breakdown root at runtime>
REPORT_ROOT=$RUNTIME_ARTIFACT_ROOT/reports
OUTPUT_ROOT=$RUNTIME_ARTIFACT_ROOT/tables
VALIDATION_WORKTREE=$PROJECT_SOURCE_ROOT
```

If the maintained projection script is missing or incorrect, repair that
canonical path and record the R03 tooling delta. Do not create a parallel
one-off projector or manually edit reports.

Default inputs:

```text
$LAYER_BREAKDOWN_ROOT/*_layer_kernel_breakdown.csv
$FX_ROOT/fx_layer_events.csv
$FX_ROOT/*/fx_process_reconstruction.json
```

Default target reports:

```text
$REPORT_ROOT/SAME_INPUT_<RUNTIME_VARIANT>_PROCESS_WISE_PERFORMANCE_REPORT.md
```

Intermediate CSVs are under `$OUTPUT_ROOT`; every generated R03 artifact stays
inside `RUNTIME_ARTIFACT_ROOT`.

## Portable Projection Tool Contract

The process projection tool must implement these tasks.

Inputs:

- one or more variant labels mapped to runtime-resolved Nsight-compatible `layer_kernel_breakdown.csv` files;
- FX root containing `fx_layer_events.csv`;
- per-event `fx_process_reconstruction.json`;
- output paths for per-variant Markdown reports and detail/summary/coverage CSVs;
- options for match mode, process weight mode, and kernel split mode.

Required matching behavior:

- load only FX events with `fx_traced=True` and successful status;
- match performance rows to FX events by `layer`, `phase`, `q_len`, and `kv_len`;
- support `exact` and `exact-or-nearest`;
- label every row with `match=exact` or `match=nearest_shape`;
- preserve `fx q/kv` and `perf q/kv` separately.

Required source buckets:

```text
attn: measured attention component
mlp: measured MLP component
outer: total - attn - mlp after normalization
metadata: non-compute process stages, zero attributed latency
```

Required process bucket mapping:

```text
inputs -> metadata
input_rmsnorm -> outer
qkv_projection -> attn
rope -> attn
attention_scores -> attn
attention_output -> attn
visual_process -> attn
output_projection -> attn
post_attention_rmsnorm -> outer
mlp -> mlp
layer_output -> metadata
```

Required CUPTI kernel split modes:

- `family-aware`: use `<kernel_family>_ms` fields from the source layer breakdown to bias kernel allocation to plausible FX processes;
- `component-total`: split the component kernel total by process weights only.

Required process weighting modes:

- `semantic-cost`: weighted by FX node count and process semantic multiplier;
- `node-count`: weighted by FX node count only.

Required per-variant report shape:

```text
# <variant> SAME_INPUT Process-wise Performance Report
## Sources
## Coverage
## Layer/component Source Latency
## FX Process Latency Attribution
## Interpretation Notes
```

Required `FX Process Latency Attribution` column order:

```text
fx_event | layer | phase | process | title | **CUPTI kernel ms** | **NVTX CPU ms** | fx q/kv | match | perf q/kv | nodes | bucket | source bucket kernel ms | source bucket CPU ms
```

Required CSV outputs:

- per-variant process attribution CSV, one row per FX event process;
- aggregate detail CSV, one row per matched layer occurrence process;
- aggregate summary CSV, grouped by variant/phase/process;
- coverage CSV with total, exact, nearest-shape, and unmatched counts.

Required conservation check:

- for each variant and FX event, the sum of allocated process `CUPTI kernel ms` should equal the matched source layer `kernel_total_ms` within floating-point roundoff.

## Required Report Shape

Each per-variant report must have exactly this high-level structure:

```text
# <variant> SAME_INPUT Process-wise Performance Report
## Sources
## Coverage
## Layer/component Source Latency
## FX Process Latency Attribution
## Interpretation Notes
```

`Layer/component Source Latency` is one table that gathers all filtered FX events and their source `total`, `attn`, and `mlp` layer/component rows.

`FX Process Latency Attribution` is one table that gathers all filtered FX events and every FX process stage with attributed latency.

The process table should put the key timing columns early and bold the timing headers:

```text
fx_event | layer | phase | process | title | **CUPTI kernel ms** | **NVTX CPU ms** | fx q/kv | match | perf q/kv | nodes | bucket | source bucket kernel ms | source bucket CPU ms
```

Do not replace the per-variant reports with only a global top-process summary. A global aggregate report is optional and secondary.

## Default Workflow

1. Resolve the live path/tool bindings above, then inspect current artifacts only as needed:

```bash
python "$PROJECTION_SCRIPT" --help
test -f "$FX_ROOT/fx_layer_events.csv"
ls "$LAYER_BREAKDOWN_ROOT"/*_layer_kernel_breakdown.csv
```

2. Generate the per-variant process-wise reports:

```bash
python "$PROJECTION_SCRIPT" \
  --variant <current-variant> \
  --display-name <current-display-name> \
  --layer-breakdown <same-run-R01-layer-breakdown.csv> \
  --layer-events <same-run-R01-layer-events.csv> \
  --contract-id <R01-contract-id> \
  --contract-sha256 <R01-contract-sha256> \
  --fx-root "$FX_ROOT" \
  --process-db <same-run-R02-queryable.db> \
  --process-runtime-events <same-run-R02-runtime-events.jsonl> \
  --process-inventory <same-run-R02-process-inventory.csv> \
  --report-root "$REPORT_ROOT" \
  --output-root "$OUTPUT_ROOT" \
  --runtime-artifact-root "$RUNTIME_ARTIFACT_ROOT"
```

3. Generate the optional aggregate Markdown report only when explicitly useful
by repeating the exact same command and adding:

```bash
--write-aggregate-report
```

4. For stricter claims, regenerate in a new empty artifact subdirectory with
the exact same inputs and add:

```bash
--match-mode exact
```

Exact-only output may leave unmatched FX events if q/kv differs between the FX sample and the performance row.

## Attribution Semantics

Treat the output as process-wise attribution, not direct per-process timing.

- Source latency comes from SAME_INPUT runtime-resolved Nsight-compatible layer kernel breakdown rows.
- Algorithm process stages come from `fx_process_reconstruction.json`.
- `CUPTI kernel ms` is based on the upstream launch-owned kernel sum, not GPU overlap with an NVTX CPU range.
- `NVTX CPU ms` is CPU range attribution.
- `match=exact` means layer/phase/q/kv match between FX and performance data.
- `match=nearest_shape` is exploratory fallback. Do not use nearest-shape rows as strict evidence without saying so.
- `bucket=attn`, `mlp`, `outer`, or `metadata` explains which measured source bucket the process drew from.
- `source bucket * ms` columns show the measured bucket before process allocation; process timing columns show the allocated estimate.

Default CUPTI allocation should use `--kernel-split-mode family-aware`, which uses kernel family fields from the layer breakdown CSV when available. The simpler `component-total` mode is allowed for sensitivity checks.

## Validation Checklist

After generation or edits, run:

```bash
python -m py_compile "$PROJECTION_SCRIPT"
git -C "$VALIDATION_WORKTREE" diff --check -- scripts/perf_trace/generate_qwen_process_performance_breakdown.py
```

Check report shape:

```bash
for f in "$REPORT_ROOT"/SAME_INPUT_*_PROCESS_WISE_PERFORMANCE_REPORT.md; do
  echo "--- $f"
  rg -n '^## Layer/component Source Latency|^## FX Process Latency Attribution|^### input|Layer/component source latency:|FX process latency attribution:' "$f"
done
```

Expected: each report has `Layer/component Source Latency` and `FX Process Latency Attribution`; no per-event `### input...` sections.

Check exact row counts for the runtime-resolved filtered FX events:

```bash
python - <<'PY'
import os
from pathlib import Path
for p in sorted(Path(os.environ['REPORT_ROOT']).glob('SAME_INPUT_*_PROCESS_WISE_PERFORMANCE_REPORT.md')):
    text = p.read_text()
    source = text.split('## Layer/component Source Latency', 1)[1].split('## FX Process Latency Attribution', 1)[0]
    process = text.split('## FX Process Latency Attribution', 1)[1].split('## Interpretation Notes', 1)[0]
    print(p.name, 'source_rows', sum(line.startswith('| input') for line in source.splitlines()), 'process_rows', sum(line.startswith('| input') for line in process.splitlines()))
PY
```

Before running this check, derive and record the exact expected counts from the same live filtered FX event set and its process reconstructions. Each variant must have three source rows per filtered FX event and one process row per reconstructed process stage across those events. Do not reuse the source project's fixed `35`/`105`/`371` counts or the archived `perf_trace_bk` counts as current evidence.

Check process allocation conservation:

```bash
python - <<'PY'
import csv, collections, os
from pathlib import Path
for p in sorted(Path(os.environ['OUTPUT_ROOT']).glob('same_input_*_process_attribution.csv')):
    if p.name == 'same_input_process_attribution.csv':
        continue
    rows = list(csv.DictReader(p.open()))
    by = collections.defaultdict(float)
    src = {}
    for r in rows:
        key = (r['variant'], r['fx_event_id'])
        by[key] += float(r['allocated_cupti_kernel_ms'])
        src[key] = float(r['source_total_cupti_kernel_ms'])
    max_err = max((abs(v - src[k]) for k, v in by.items()), default=0.0)
    print(p.name, 'events', len(by), 'rows', len(rows), 'max_kernel_sum_err', f'{max_err:.12f}')
PY
```

The max error should be near floating-point roundoff.

## Editing Rules

If the report shape or allocation logic is wrong, patch the runtime-resolved project script rather than manually editing generated reports. Then rerun the script and validation.

Use `apply_patch` for source edits. Keep generated Markdown consistent with the script output.

Regenerate every table into `runtime_artifact_root`; never copy an older report.
Preserve directly observed layer time separately from FX-proportional process
estimates. These estimates may rank R06/R08 work, but cannot populate the final
R07 observed timeline or replace exact process HIPTX duration. R03 may change
the maintained projector, report generator, schemas, or validators; record the
stage delta without requiring equality with R01/R02. Keep R01/R02 artifacts
immutable and fail on any event-denominator drop.

## Scheduler Handoff

Write only the scheduler-assigned R03 JSON handoff after deterministic
generation, strict ownership, event coverage, and conservation checks pass.
Hash-index every generated table/report plus the R01/R02 inputs and R03 stage
source state. Do not invoke R04 or rewrite a predecessor handoff.
