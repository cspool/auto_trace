# 04 Full-layer FX Process-wise Estimate

目标：使用 workflow 01 的全量 layer-wise denominator 和 workflow 02 的代表 process template，估计全量 input-layer 的 process-wise 性能分解。

## Skill

```text
$visipruner-segmented-process-attribution
```

## Required GPU

This workflow is offline CSV/report generation and normally does not use GPU. If any validation rerun is needed, use:

```text
GPU=1
```

## Expected Output Directory

```text
output/visipruner_full_eager_full_layer_process_attribution/
```

`output_bk/visipruner_full_eager_full_layer_process_attribution_bk/` is only a historical reference. New estimates must consume current workflow 01 and workflow 02 outputs.

## Possible Scripts

```text
code/generate_segmented_process_attribution.py
```

## Required Inputs

```text
output/visipruner_full_eager_layer_wise/nsys_fxsameinput_visipruner_full_eager_32tok_all_input_layer_performance.csv
output/visipruner_full_eager_layer_wise/nsys_fxsameinput_visipruner_full_eager_32tok_layer_kernel_breakdown.csv
output/visipruner_full_eager_process_wise/same_input_visipruner_full_eager_process_attribution.csv
output/visipruner_full_eager_process_wise/SAME_INPUT_VISIPRUNER_FULL_EAGER_PROCESS_WISE_PERFORMANCE_REPORT.md
output/visipruner_full_eager_layer_wise/SAME_INPUT_VISIPRUNER_FULL_EAGER_LAYER_PERFORMANCE_REPORT.md
```

## Command Template

```bash
cd /workspace/VisiPrune

python /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/code/generate_segmented_process_attribution.py \
  --full-input-layer-csv /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_layer_wise/nsys_fxsameinput_visipruner_full_eager_32tok_all_input_layer_performance.csv \
  --layer-kernel-csv /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_layer_wise/nsys_fxsameinput_visipruner_full_eager_32tok_layer_kernel_breakdown.csv \
  --representative-process-csv /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise/same_input_visipruner_full_eager_process_attribution.csv \
  --representative-report /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise/SAME_INPUT_VISIPRUNER_FULL_EAGER_PROCESS_WISE_PERFORMANCE_REPORT.md \
  --layer-report /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_layer_wise/SAME_INPUT_VISIPRUNER_FULL_EAGER_LAYER_PERFORMANCE_REPORT.md
```

## Expected Files

```text
SAME_INPUT_VISIPRUNER_FULL_EAGER_FULL_LAYER_PROCESS_ATTRIBUTION_REPORT.md
SAME_INPUT_FULL_LAYER_PROCESS_ATTRIBUTION_BREAKDOWN.md
full_layer_attribution_type_map.csv
full_layer_template_assignment.csv
full_layer_process_attribution.csv
full_layer_process_aggregation.csv
full_layer_coverage_and_risk.csv
```

## Checks

```bash
python - <<'PY'
import csv
from pathlib import Path
p = Path('autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_full_layer_process_attribution/full_layer_template_assignment.csv')
rows = list(csv.DictReader(p.open()))
missing = [r for r in rows if not r.get('attribution_source') or not r.get('attribution_type_id')]
print('assignment_rows', len(rows), 'missing_assignment', len(missing))
PY

python - <<'PY'
import csv, collections
from pathlib import Path
p = Path('autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_full_layer_process_attribution/full_layer_process_attribution.csv')
rows = list(csv.DictReader(p.open()))
by = collections.defaultdict(float)
src = {}
for r in rows:
    key = (r.get('variant'), r.get('phase'), r.get('layer'), r.get('occurrence'), r.get('metric'))
    by[key] += float(r.get('ms', 0.0))
    src[key] = float(r.get('source_layer_metric_ms', 0.0))
errs = [abs(v - src[k]) for k, v in by.items()]
print('metric_groups', len(by), 'max_conservation_err', max(errs, default=0.0))
PY
```

## Constraints

- `observed_fx_op` is direct process evidence from workflow 02.
- `template_scaled` is a layer-conserved estimate, not a direct full-layer process trace.
- Do not report representative absolute process latency as target-layer latency unless it is normalized to the target layer's own measured metric.
- Every `(phase, layer, occurrence, metric)` must conserve to `source_layer_metric_ms`.
- NCU hardware diagnostics from workflow 03 can explain bottlenecks, but must not change the timing denominator.
