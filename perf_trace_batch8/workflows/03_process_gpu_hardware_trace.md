# 03 Representative-layer Process GPU Hardware Trace

目标：以 workflow 02 的 `Representative Layer Process GPU Execution Order`
为行索引，给所有代表 layer/process 补充 Nsight Compute 硬件属性。workflow
03 不重新证明 process timing attribution，也不把 NCU replay 时间当作 latency。

## 运行注意项（batch8 首次执行确认）

- R04 admission 必须把 R02 的 `profiler_execution_performed`、
  `trace_collection_performed`、`pmc_collection_performed`、
  `report_generation_performed` 和 `attribution_performed` 五个字段逐项断言为
  `false`。不得用混合真假分支的共享表达式推导期望值；首次只读校验曾把
  `attribution_performed=false` 写反而误报前序证据失败。此类失败若 artifact
  root 仍为空且尚未运行 PMC，只修正 admission 校验并重新执行完整前序哈希门，
  不能改写 R02 handoff 或跳过约束。
- batch8 固定 rocprof 的 `--list-basic`/`--list-derived` 在成功打印
  `gpu-agent9` counter catalog 后仍可能返回退出码 1，并追加
  `ROCPRofiler: 0 contexts collected`；list-only 命令本来就不创建采集 context。
  capability probe 必须同时保存 stdout/stderr/退出码，并以可解析的 agent、counter
  名称、公式与数量证明 catalog 可用，不能仅凭非零退出码判定“无 counters”。
  真正 replay 命令仍必须要求退出码 0 和非空、可归属的 per-dispatch counter 证据。
- 设备占用 preflight 不得硬编码未经当前 `hy-smi --help` 验证的参数。batch8
  首次探测确认 `--showpidgpus` 不受本机版本支持，并在任何模型/DCU 工作之前
  退出；应先解析本机支持的 PID、利用率和显存查询接口，再执行只读检查。每次
  capability/smoke 尝试必须使用唯一、不可变的 attempt 名称和空输出目录；名称
  冲突必须 fail-closed，不能复用或覆盖旧日志、raw 文件与退出码。
- `/opt/dtk-26.04-DCC2602-0317/rocprofiler/bin/rocprof` 是 legacy RPL v1。
  本机安装中它会错误查找 `/opt/dtk-26.04/bin/rocminfo`，且其期望的
  `rocprofiler/lib/roctracer/libroctracer_tool.so`、`libroctracer64.so.4` 不存在；
  实际 child workload 即使运行也得到 `0 contexts collected` 和空 raw 结果。
  其 help 虽显示 `-o --`，实现仍要求 `.csv` 后缀，故不能把 help 文本视为可用性
  证明。允许切换到同一固定 DTK 的 `rocprofv2`，但只有真实小型 DCU smoke 退出码
  为 0、产生非空逐 dispatch CSV、计数器列可用且 HIP API/HCC operation correlation
  可解析后，才能批准正式 replay；batch8 首次 smoke 的门禁证据为 11 条逐 dispatch
  行与 6 个可用 SQ counter。
- 不得仅因设置了 `ROCPROFILER_KERNEL_FILTER` 就声称 native counter 已在 collector
  侧按 kernel 过滤。batch8 固定 DTK 的 `rocprofv2` file plugin 会忽略该变量：使用
  不存在的 literal、期望 0 个匹配 dispatch 的独立 model-free probe 仍记录了 5 个
  dispatch，与基线数量相同。正式计划必须在每次运行前用不存在-literal probe 验证
  filter 是否真实生效，并把 `collector_kernel_filter_empirically_effective` 写入
  capability、plan、raw manifest、validation 与报告。若结果为 false，只允许采集
  “一个安全 literal 批次对应一次完整 canonical request”的最小 bounded superset；
  所有非目标 native 行留在不可变 raw 中但不得进入投影。归属必须依次通过软件 exact
  literal、同 replay 的 exact R02 HIPTX range、HIP launch correlation、PMC dispatch
  correlation 和 exact normalized R03 operation subsequence。相同 literal 的逻辑目标
  可以共享一次物理 capture，但必须分别通过上述 range/correlation 门禁；禁止把共享
  raw、replay 顺序或 replay 时长冒充 process 归属、process 顺序或 latency。batch8
  当前完整计划应保持 62 个代表行（58 个 PMC 逻辑目标、4 个 no-kernel）、26 个唯一
  literal 物理 capture batch。映射实例总数必须从封存的 selection plan 中对 58 个
  eligible 目标的 `selected_literal_r03_instance_count` 动态求和，不能另写固定常量；
  batch8 当前封存计划的可证明总数是 66，不是早期设计阶段误写的 89。
- batch8 的 `rocprofv2 --hip-api` 不能单独满足 PMC dispatch correlation：正式
  Qwen pilot 的 counter CSV 中 `Correlation_ID` 全为 `0`，而 HIP API CSV 使用另一组
  递增 ID；即使额外指定 `--kernel-trace`，PMC 模式也没有生成可连接的 kernel trace。
  独立 smoke 证明 `--hip-trace` 会同时生成 HCC ops，且 counter 与 HCC ops 共享非零
  correlation ID（例如 `32/43/54/65/78`）。需要 launch/dispatch 归属时必须在正式
  replay 前用 model-free probe 证明这条 join，并保留 `--hip-trace` 产生的 HCC ops
  correlation 流；不得为了减小 raw 体积退回 `--hip-api` 或删除 HCC ops。已用错误
  trace 选项完成的 pilot 只能作为 immutable diagnostics，须在 tool revision 后重采。
- R04 的 artifact-local replay shell 不能依赖启动 formal Goal 时继承的
  `PYTHONPATH`/`LD_LIBRARY_PATH`。batch8 首个正式 pilot 因 shell 只继承
  artifact tools 与 `/usr/local`，使 Python tree 从系统 site-packages 加载，触发
  `loaded vLLM Python tree drift`；失败发生在模型加载前且没有有效硬件证据。每次
  replay 必须在调用 profiler 前显式把固定 trace target source root、R04 tools
  依次前置到 `PYTHONPATH`，把同一固定 DTK 的 `dcc/lib` 前置到
  `LD_LIBRARY_PATH`，并解析目标 `.venv/bin/python` 的真实路径。此类执行工具修订
  必须隔离旧 manifest、旧 plan 与失败 raw attempt，记录新旧工具 SHA，重新封存
  tool manifest 并重建所有 hash-pinned target metadata 后再重试；不得就地改写旧
  attempt。修复后的 pilot 还必须证明加载的是目标 source tree，同时 ABI `.so`
  仍来自已固定的系统 vLLM distribution。
- R04 的模型/profiler 子进程当前由 Codex app-server 控制面持有；后端响应流断开可在
  已打印下一 capture batch 的 `start` 记录后终止 scheduler、app-server、executor 和
  profiler，而不是产生一个正常的 replay 失败。恢复前必须同时核对 runtime state、
  Goal stop reason、scoped PID、最后一个完整 `execution_manifest.json` 和活动 pass 目录。
  若 Goal 已因控制面错误进入 `blocked`，不得使用 `--continue-current-goal`；普通
  resume 默认会创建空的 `resume-NNN` artifact root，也不能用于 suffix-only 恢复。
  应对同一 `run_id` 从 R04 使用受约束的 `--resume-artifact-root <原 R04 root>`，建立
  新的正式 R04 Goal 尝试，同时保持原 lineage、artifact root、sealed plan 和已完成
  manifest 不变；该路径必须是 state 当前或 attempt history 已记录的本阶段目录，并
  fail-closed 限制在 canonical R04 root 内。被中止且没有合格 execution manifest 的
  pass 目录必须作为不可变失败 attempt 保全，记录中断原因、原路径、文件清单与 SHA-256，
  再移入独立 quarantine/revision 目录；随后只能在新的空 pass root 重采该物理 batch。
  禁止删除、清空、覆盖残留目录，禁止把仅有 `pmc.txt` 或部分 CSV 的目录当成 resume
  成功；再次执行 `--resume` 前还必须逐一验证所有已完成 manifest、artifact hash、源码
  commit/clean 状态和累计 profiling wall time。
- normalizer 与独立 auditor 都必须从同一封存 selection plan 独立重算预期映射实例数，
  并分别强制 `mapped_dispatch_count == expected_mapped_dispatch_count > 0`。batch8 首次
  全量后处理虽然 26/26 capture 均通过，却因 normalizer 额外硬编码
  `expected_mapped == 89` 而在最终断言处失败；实际 plan 求和与 mapping 行数均为 66。
  这类失败只允许修订离线分析工具，不得重采有效 raw。修订前必须归档捕获期 tool
  manifest、旧 normalizer/auditor 和 revision history 并记录 SHA-256；修订后的
  analysis manifest 必须显式引用捕获期 manifest，normalizer/auditor 还须同时验证
  capture-time 与 analysis-time 工具哈希及所有 replay manifest 的捕获期 provenance。

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
CUDA_VISIBLE_DEVICES=<trace-profile-visible-devices>
--gpu <trace-profile-capture-device>
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
