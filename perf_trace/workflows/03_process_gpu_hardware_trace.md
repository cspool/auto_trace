# 03 Representative-layer Process GPU Hardware Trace

目标：以 workflow 02 的 `Representative Layer Process GPU Execution Order`
为行索引，给所有代表 layer/process 补充 Nsight Compute 硬件属性。workflow
03 不重新证明 process timing attribution，也不把 NCU replay 时间当作 latency。

## Skill Reference

```text
$visipruner-process-performance-breakdown
```

该 skill 只作为边界参考：workflow 02 已经负责 process-level NVTX、
launch-owned CUPTI timing、kernel launch order、validation evidence。workflow 03
只在这些已确定的 process/order 行上投影硬件属性。

## Required GPU

```text
GPU=1
```

固定 GPU 1，避免 GPU 间负载差异影响同一输入下的硬件采样。NCU 会 replay
kernel，不能和 workflow 02 的 nsys timing run 合并。

## Expected Output Directory

```text
output/visipruner_full_eager_process_wise_ncu/
```

## Required Inputs

Workflow 03 consumes workflow 02 outputs:

```text
output/visipruner_full_eager_process_wise/SAME_INPUT_VISIPRUNER_FULL_EAGER_PROCESS_WISE_PERFORMANCE_REPORT.md
output/visipruner_full_eager_process_wise/same_input_visipruner_full_eager_process_attribution.csv
output/visipruner_full_eager_process_wise/nsys_sameinput_visipruner_full_eager_32tok_process_nvtx_kernel_breakdown.csv
output/visipruner_full_eager_process_wise/process_kernel_launch_order.csv
output/visipruner_full_eager_process_wise/FX_PROCESS_NVTX_INSTRUMENTATION_HANDOFF.md
```

The Markdown report is the human-readable source. The CSV files are the
machine-readable source for reconstructing the same representative-layer process
order.

## Existing Tools or Scripts

```text
ncu
code/profile_visprune_single_request.py
code/generate_process_ncu_plan.py
code/generate_process_ncu_report.py
```

Do not patch workflow 02 attribution logic inside this workflow unless the
workflow 02 output is missing the representative order table.

## Boundary

Workflow 02 owns process performance evidence:

```text
process NVTX range
CUDA runtime correlationId
CUPTI kernel start/end
stream
kernel family
process latency/order/validation
```

Workflow 03 owns process hardware attributes:

```text
SM utilization
Tensor Core utilization
DRAM throughput
L2 throughput
occupancy
warp stall reasons
register/shared memory pressure when available
```

The two workflows reuse the same input and the same FX process NVTX ranges, but
must remain separate because NCU replay changes runtime behavior and can heavily
distort timing.

## Target Selection

Select targets from workflow 02 `Representative Layer Process GPU Execution
Order`, not from a new high-CUPTI/high-NVTX ranking.

Required policy:

```text
1. Use all representative parent layers present in workflow 02.
2. Keep workflow 02 process GPU order within each parent layer.
3. Profile process/fragment targets that have launch-owned kernels.
4. For aggregated cross-function processes such as mlp/output_projection,
   expand to fragment-level NVTX ranges for NCU, then report them under the
   same workflow 02 process/order row.
5. Use filters only for debugging or batching; final completion requires all
   workflow 02 representative parent layers.
```

Default full plan for all workflow 02 representative layers:

```bash
cd /workspace/VisiPrune

/workspace/VisiPrune/venv_profiling/bin/python \
  autoresearch/experiments/e2_single_request_latency/code/generate_process_ncu_plan.py \
  --selection-mode layer
```

Example debug batch: profile all process fragments in layer 18 prefill:

```bash
/workspace/VisiPrune/venv_profiling/bin/python \
  autoresearch/experiments/e2_single_request_latency/code/generate_process_ncu_plan.py \
  --selection-mode layer \
  --layers 18 \
  --phases prefill \
  --forward-ids 1 \
  --processes all
```

Example: rebuild a plan/report for existing NCU artifacts without rerunning NCU:

```bash
/workspace/VisiPrune/venv_profiling/bin/python \
  autoresearch/experiments/e2_single_request_latency/code/generate_process_ncu_plan.py \
  --selection-mode existing-artifacts
```

## NCU Execution

Run each `ncu_command` from `ncu_process_selection_plan.csv`. A plan row is one
workflow 02 process/fragment NVTX target, not one report row. The generated
commands already include:

```text
CUDA_VISIBLE_DEVICES=1
--gpu 1
--nvtx
--nvtx-include "<workflow02_fx_process_nvtx_range>/"
```

The trailing `/` in `--nvtx-include` is required for PyTorch push/pop NVTX ranges
with the local NCU version.

Do not insert additional workflow03-only NVTX ranges. Reuse workflow 02 FX
process/fragment ranges so hardware attributes can be joined back to the same
nsys attribution contract.

Export raw metrics after each `.ncu-rep`:

```bash
ncu --import <target>.ncu-rep --csv --page raw > <target>_metrics.csv
```

## Expected Files

```text
ncu_process_selection_plan.csv
ncu_<layer>_<phase>_<process>[_<fragment>].ncu-rep
ncu_<layer>_<phase>_<process>[_<fragment>]_metrics.csv
SAME_INPUT_VISIPRUNER_FULL_EAGER_PROCESS_WISE_NCU_REPORT.md
```

## Report Shape

The report is a filtered hardware-attribute projection over workflow 02 rows.
It should not repeat workflow 02 performance attribution evidence columns.
The main report rows must be nsys-attributed matched kernel families:

```text
workflow 02 process/fragment NVTX target
  -> launch-owned nsys/CUPTI kernels
  -> group by matched_kernel_family
  -> one report row per matched_kernel_family
  -> map NCU metrics for the same family when available
```

Do not make one row per process summary and do not use one Nsight Compute replay
kernel instance as the main row unit.

Required columns:

```text
parent_layer_range
forward_id
layer
first_kernel_launch_order_in_parent
process_gpu_order
process_gpu_start_offset_us
process_id
process_title
fragment_id
matched_kernel_family
kernel_family_instance_count
nsys_kernel_name_examples
ncu_status
ncu_kernel_family_instance_count
ncu_profiled_kernel_names
nvtx_include
SM utilization
Tensor Core utilization
DRAM throughput
L2 throughput
occupancy
dominant stall reasons
hardware bottleneck interpretation
target_id
```

Do not include these workflow 02 evidence columns in the main workflow 03 table:

```text
CUPTI kernel ms
NVTX CPU ms
process_cupti_pct_in_parent
process_nvtx_pct_in_parent
runtime API calls
kernel instances
validation status
```

These fields remain available in workflow 02.

Generate the report:

```bash
/workspace/VisiPrune/venv_profiling/bin/python \
  autoresearch/experiments/e2_single_request_latency/code/generate_process_ncu_report.py
```

## Checks

```bash
test -d /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise_ncu

rg -n 'Kernel-family Hardware Attributes by Representative Layer|matched_kernel_family|ncu_status|SM|Tensor|DRAM|L2|occupancy|stall|workflow 02' \
  /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise_ncu/SAME_INPUT_VISIPRUNER_FULL_EAGER_PROCESS_WISE_NCU_REPORT.md

if rg -n 'CUPTI kernel ms|NVTX CPU ms|runtime API calls|kernel instances|validation status' \
  /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise_ncu/SAME_INPUT_VISIPRUNER_FULL_EAGER_PROCESS_WISE_NCU_REPORT.md; then
  echo "unexpected workflow02 evidence columns in workflow03 report"
  exit 1
fi
```

## Constraints

- Keep workflow 03 outputs separate from workflow 02 strict timing outputs.
- NCU timing is diagnostic-only and must not be compared as process latency.
- Reuse workflow 02 FX process NVTX range names; do not invent new ranges here.
- Final workflow03 coverage requires all representative parent layers in
  workflow02; filtered plans are incomplete unless explicitly documented as
  debug/batch runs.
- Main report rows are workflow 02 nsys-attributed `matched_kernel_family` rows,
  not process summary rows and not NCU replay kernel rows.
- If NCU replay changes kernel choices or pruning behavior, regenerate workflow
  02 before making latency claims.
