# 01 Layer-wise End-to-End Trace

目标：获得 VisiPruner full eager SAME_INPUT 全量 input-layer 的 Nsight/CUPTI layer-wise 性能数据，作为后续 full-layer process attribution 的守恒分母。

## Skill

```text
$visipruner-same-input-layer-wise-workflow
```

## Required GPU

```text
GPU=1
```

GPU 1 当前负载更轻，性能干扰更小。除非重新审查 GPU 负载，否则本 workflow 固定使用 GPU 1。

## Expected Output Directory

```text
output/visipruner_full_eager_layer_wise/
```

`output_bk/visipruner_full_eager_layer_wise_bk/` 只作为历史参考。它不能替代本轮 expected output。

## Possible Scripts

```text
code/profile_visprune_single_request.py
code/run_nsys_layer_profile_single_request.sh
code/analyze_layer_nsys.py
code/generate_layer_performance_report.py
code/run_same_input_three_way_layer_retest.sh
code/audit_same_input_three_way_layer_retest.py
```

## Command Template

```bash
cd /workspace/VisiPrune

ROOT_DIR=/workspace/VisiPrune \
CONFIG=visipruner-full \
TAG=nsys_fxsameinput_visipruner_full_eager_32tok \
OUTPUT_DIR=/workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_layer_wise \
REPORT_DIR=/workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise \
FX_PROCESS_PROFILE=off \
MAX_NEW_TOKENS=32 \
WARMUP_ITERS=1 \
GPU=1 \
bash /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/code/run_nsys_layer_profile_single_request.sh
```

Generate the layer report and complete input-layer table:

```bash
python /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/code/generate_layer_performance_report.py \
  --profile-json /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_layer_wise/nsys_fxsameinput_visipruner_full_eager_32tok.json \
  --fx-run-metadata /workspace/VisiPrune/workload_analysis/fx/traces/fx_filtered_dispatch_layers_specialized/run_metadata.json \
  --attribution-status pass \
  --layer-events /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_layer_wise/nsys_fxsameinput_visipruner_full_eager_32tok_layer_events.csv \
  --nsys-layer-csv /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_layer_wise/nsys_fxsameinput_visipruner_full_eager_32tok_layer_kernel_breakdown.csv \
  --all-input-layer-csv /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_layer_wise/nsys_fxsameinput_visipruner_full_eager_32tok_all_input_layer_performance.csv \
  --output /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_layer_wise/SAME_INPUT_VISIPRUNER_FULL_EAGER_LAYER_PERFORMANCE_REPORT.md \
  --title "Same-input eager VisiPruner full layer performance report"
```

## Expected Files

```text
SAME_INPUT_VISIPRUNER_FULL_EAGER_LAYER_PERFORMANCE_REPORT.md
nsys_fxsameinput_visipruner_full_eager_32tok.json
nsys_fxsameinput_visipruner_full_eager_32tok.nsys-rep
nsys_fxsameinput_visipruner_full_eager_32tok.sqlite
nsys_fxsameinput_visipruner_full_eager_32tok_layer_events.csv
nsys_fxsameinput_visipruner_full_eager_32tok_layer_kernel_breakdown.csv
nsys_fxsameinput_visipruner_full_eager_32tok_layer_kernel_breakdown.json
nsys_fxsameinput_visipruner_full_eager_32tok_all_input_layer_performance.csv
nsys_fxsameinput_visipruner_full_eager_32tok_stats_*.csv
```

## Checks

```bash
cd /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency

sqlite3 output/visipruner_full_eager_layer_wise/nsys_fxsameinput_visipruner_full_eager_32tok.sqlite \
  "select count(*) from NVTX_EVENTS where text like 'visprune.layer%';"

rg -n 'runtime_correlation_id|CUPTI launch-owned|all input-layer' \
  output/visipruner_full_eager_layer_wise/SAME_INPUT_VISIPRUNER_FULL_EAGER_LAYER_PERFORMANCE_REPORT.md
```

## Constraints

- This workflow does not require `visprune.fx_process.*`.
- `all_input_layer_performance.csv` is the target-layer denominator for workflow 04.
- Do not infer process attribution from layer totals in this workflow.
