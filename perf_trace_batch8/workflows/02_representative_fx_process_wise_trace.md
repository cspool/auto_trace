# 02 Representative FX Process-wise Trace

目标：对代表 input-layer 采集 strict FX process-wise trace，得到 direct process timing、kernel families、validation status、GPU kernel launch order。

## 运行注意项（batch8 首次执行确认）

- 执行环境不保证安装 `jq` 或 `rg`。输入 ledger、handoff、JSON schema、源码锚点
  和 artifact SHA-256 的正式校验必须有 Python 标准库实现，不能让可选的交互式
  检查工具成为 R02 的运行依赖；缺少这些命令本身不应触发 GPU 重跑。
- Stage B 探测或启动 `hipprof` 前必须先 source 当前 trace target 固定的环境
  profile，并将同一固定 DTK 的 `dcc/lib` 加入 `LD_LIBRARY_PATH`。直接从调度
  shell 执行 `/opt/dtk/bin/hipprof` 会因缺少 `libLLVM-17git.so` 返回 127；这只
  证明环境未加载，不能据此把 profiler 标为 unavailable，也不能开始新的 capture。
- `hipprof -h` 的输出格式名大小写不构成能力差异；batch8 固定版本把格式写成
  小写 `pftrace`。preflight 必须对格式名做大小写无关匹配，并分别报告缺失 flag
  与缺失 output format；不得在 flag 缺失列表为空时仅因 `PFTrace`/`pftrace`
  大小写差异报 `required local interface absent: []`。这种失败发生在 tool
  manifest 和采集之前时，只修正并重跑无测量 preflight，不启动或重跑 GPU 采集。
- Stage B 的 HIPTX adapter 范围必须由本次 R02 sidecar 中的精确名称多重集合
  定义并做集合/计数等价校验，不能用 `pra.*` 等宽泛前缀选择。目标运行时可能
  同时产生 `pra.generate_total` 等非 adapter 标记；把这些标记混入 process 范围
  会破坏期望范围数、归属与守恒。非 adapter 标记可以作为上下文单独保存，但
  不得进入 adapter 测量集合。
- 固定 hipprof 在请求成功后可能同时导出一个 `.db`、一个 `.pftrace` 以及
  `.hipkernel.csv`、`.hiptrace.csv` 辅助文件。封存门应分别要求恰好一个必需
  DB 和一个必需 PFTrace，显式白名单并哈希全部已知辅助输出，同时拒绝未知
  raw 文件；不能把 raw 目录总文件数硬编码为 2。若只因该后置 inventory 假设
  失败，先记录四个原始文件的尺寸/SHA-256、确认设备释放并保持其字节不变，
  再以可审计的 post-capture 工具修订继续封存，禁止重跑请求。
- 对真实 Qwen3.5 decoder layer 做深层 `torch.fx` trace 时，默认
  `torch.fx.Proxy` 无法表示源码中的 output-buffer slice assignment，也无法直接
  展开 `shape[:-1]` 后的动态 `view(*orig_shape, ...)`。必须依据已固定的 rank/shape
  合同提供 source-preserving `setitem`、`len`/iteration Proxy 语义，或选择等价且
  可审计的 leaf boundary；不得因 `Proxy object does not support item assignment`、
  `Proxy object cannot be iterated` 而改用伪造 FX graph。linear-attention 与
  full-attention 要按真实 `layer_type` 分别 trace，并保留 shallow/deep 两级证据。
- runtime wrapper 不得假设 model forward 的 token tensor 一定是 `input_ids`
  keyword 或第一个 positional argument。应先核对当前 source signature，再按
  `input_ids`、`inputs_embeds` 和已验证 positional slot 解析 host-visible shape；
  解析后必须用 SAME_INPUT 的 phase/q_len/kv_len grid fail-closed 校验，不能仅为
  消除 `model forward lacks host-visible input shape` 而接受任意 tensor。
- 一个 module object 可能被多个 layer path 共享。batch8 的 full-attention
  `rotary_emb` 首次按 16 个 alias path 逐次包装，导致一次真实调用生成 16 层
  wrapper event（`9472` 而非预期 `592`）。安装 wrapper 时必须按
  `(id(module), wrapper semantic)` 去重，同时记录全部 alias paths 与
  declared layer indices；预期 event 数按声明的 layer occurrence 计算，不能按
  unique binding 数计算，也不能堆叠 wrapper 后再用宽松计数掩盖错误。
- 每次失败的 FX/equivalence 尝试都要移入独立 `attempts/fx_trace_failed_NNN/`
  并保存失败 JSON/日志；修复只作用于 artifact-local tools。只有在 output
  equivalence、guard-off zero events、完整 event-count、marker nesting、wrapper
  cleanup、source AST 不变和目标 worktree clean 全部通过后，才能写 R02 handoff。
  R02 不运行 profiler，也不产出 process 性能归因。

## Skills

```text
$visipruner-fx-process-nvtx-instrumentation
$visipruner-process-performance-breakdown
```

## Skill Handoff Collaboration

This workflow is a two-skill handoff pipeline. The handoff is not a historical artifact; it must be regenerated for the current worktree before process-wise profiling/report generation.

### Stage A: Instrumentation Handoff Producer

Use `$visipruner-fx-process-nvtx-instrumentation` first.

Responsibilities:

- Inspect current FX process artifacts under `workload_analysis/fx/traces/fx_filtered_dispatch_layers_specialized/`.
- Inspect current runtime instrumentation in:
  - `code/profile_visprune_single_request.py`
  - `code/run_nsys_layer_profile_single_request.sh`
  - model/pruning/attention code reached by the profiled `visipruner-full` eager path.
- Confirm or update process/fragment NVTX insertion points without changing model semantics.
- Regenerate the handoff for this workflow at:

```text
output/visipruner_full_eager_process_wise/FX_PROCESS_NVTX_INSTRUMENTATION_HANDOFF.md
```

The handoff must include the required sections:

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

The `Process Range Inventory` must be the contract consumed by the next skill. It must include one row per process or fragment and must define:

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

Cross-function processes such as `output_projection` and `mlp` must use fragment rows with a shared `aggregation_key`. Unresolved or ambiguous mappings must be left visible in the handoff with `status=unresolved` or `status=ambiguous`.

Do not copy `output_bk/visipruner_full_eager_process_wise_bk/FX_PROCESS_NVTX_INSTRUMENTATION_HANDOFF.md` into the new output directory. The backup may be used only as a structural reference while regenerating the current handoff from current code and current FX artifacts.

### Stage B: Handoff Consumer and Report Producer

Use `$visipruner-process-performance-breakdown` second.

Responsibilities:

- Read `output/visipruner_full_eager_process_wise/FX_PROCESS_NVTX_INSTRUMENTATION_HANDOFF.md` before profiling/report generation.
- Validate that the handoff contains current process/fragment NVTX names, `aggregation_key`, FX node/op-family evidence, expected kernel families, same-input contract, trace output paths, and unresolved risks.
- Stop and return to Stage A if the handoff is missing, stale, copied from backup without regeneration, lacks process/fragment NVTX names, lacks same-input contract, or does not match the current output directory.
- Run or consume the process-level Nsight trace with `FX_PROCESS_PROFILE=on`.
- Attribute kernels by launch ownership only:

```text
process NVTX CPU range
  -> CUDA Runtime API call whose start timestamp is inside that range
  -> CUPTI kernel with matching correlationId
```

- Generate process timing, validation status, kernel families, `gpu_order_basis`, and per-parent-layer kernel launch order from the same process-level sqlite.

Do not use the old layer-total split/projection path as strict process attribution. That path is 被抛弃或不需要使用.

## Required GPU

```text
GPU=1
```

GPU 1 当前负载更轻，性能干扰更小。此 workflow 需要和 workflow 01 使用同一 GPU 策略。

## Expected Output Directory

```text
output/visipruner_full_eager_process_wise/
```

`output_bk/visipruner_full_eager_process_wise_bk/` 只作为字段和报告结构参考。该备份缺少原始 process-level `.nsys-rep/.sqlite`，不能恢复 GPU launch order。

## Possible Scripts

```text
code/profile_visprune_single_request.py
code/run_nsys_layer_profile_single_request.sh
code/analyze_layer_nsys.py
code/generate_process_performance_breakdown.py
```

## Required Handoff

```text
output/visipruner_full_eager_process_wise/FX_PROCESS_NVTX_INSTRUMENTATION_HANDOFF.md
```

The handoff must be regenerated by `$visipruner-fx-process-nvtx-instrumentation` for the current code and FX artifacts before running the command template below. `$visipruner-process-performance-breakdown` must treat this handoff as its upstream contract and validate it before producing reports.

The handoff must define process/fragment NVTX names, `aggregation_key`, FX nodes/op families, expected kernel families, same-input contract, expected trace/report outputs, validation already performed, and unresolved risks.

## Command Template

```bash
cd /workspace/VisiPrune

ROOT_DIR=/workspace/VisiPrune \
CONFIG=visipruner-full \
TAG=nsys_sameinput_visipruner_full_eager_32tok \
OUTPUT_DIR=/workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise \
REPORT_DIR=/workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise \
PROCESS_REPORT_DIR=/workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise \
FX_PROCESS_PROFILE=on \
MAX_NEW_TOKENS=32 \
WARMUP_ITERS=1 \
GPU=1 \
bash /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/code/run_nsys_layer_profile_single_request.sh
```

If a valid process-level sqlite already exists for the same input/code state, regenerate reports with:

```bash
python /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/code/generate_process_performance_breakdown.py \
  --sqlite /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise/nsys_sameinput_visipruner_full_eager_32tok.sqlite \
  --layer-events /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise/nsys_sameinput_visipruner_full_eager_32tok_layer_events.csv \
  --handoff /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise/FX_PROCESS_NVTX_INSTRUMENTATION_HANDOFF.md \
  --variant visipruner-full-eager \
  --display-name "VisiPruner Full Eager" \
  --output-csv /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise/nsys_sameinput_visipruner_full_eager_32tok_process_nvtx_kernel_breakdown.csv \
  --output-json /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise/nsys_sameinput_visipruner_full_eager_32tok_process_nvtx_kernel_breakdown.json \
  --process-csv /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise/same_input_visipruner_full_eager_process_attribution.csv \
  --process-gpu-timeline-csv /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise/process_gpu_timeline.csv \
  --process-kernel-launch-order-csv /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise/process_kernel_launch_order.csv \
  --report /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise/SAME_INPUT_VISIPRUNER_FULL_EAGER_PROCESS_WISE_PERFORMANCE_REPORT.md \
  --aggregate-report /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency/output/visipruner_full_eager_process_wise/SAME_INPUT_PROCESS_WISE_PERFORMANCE_BREAKDOWN.md
```

## Expected Files

```text
FX_PROCESS_NVTX_INSTRUMENTATION_HANDOFF.md
nsys_sameinput_visipruner_full_eager_32tok.json
nsys_sameinput_visipruner_full_eager_32tok.nsys-rep
nsys_sameinput_visipruner_full_eager_32tok.sqlite
nsys_sameinput_visipruner_full_eager_32tok_layer_events.csv
nsys_sameinput_visipruner_full_eager_32tok_stats_*.csv
SAME_INPUT_VISIPRUNER_FULL_EAGER_PROCESS_WISE_PERFORMANCE_REPORT.md
SAME_INPUT_PROCESS_WISE_PERFORMANCE_BREAKDOWN.md
nsys_sameinput_visipruner_full_eager_32tok_process_nvtx_kernel_breakdown.csv
nsys_sameinput_visipruner_full_eager_32tok_process_nvtx_kernel_breakdown.json
same_input_visipruner_full_eager_process_attribution.csv
process_gpu_timeline.csv
process_kernel_launch_order.csv
```

`process_gpu_timeline.csv` and `process_kernel_launch_order.csv` should be derived from the same process-level sqlite. They must include process NVTX start/end, runtime call start/end, CUPTI kernel start/end, stream, correlationId, kernel name/family, process GPU order, kernel launch order in parent/process, and `gpu_order_basis`.

`process_kernel_launch_order.csv` is the machine-readable launch-owned kernel-instance evidence. It should contain only CUDA kernels attributed through the workflow 02 launch-ownership rule, not CUDA runtime calls that launched no kernel.

All Markdown report tables that expose `matched_kernel_families` must split that
field into one `matched_kernel_family` per row. This applies to:

```text
SAME_INPUT_VISIPRUNER_FULL_EAGER_PROCESS_WISE_PERFORMANCE_REPORT.md
  -> Process Launch-owned Kernel Breakdown
  -> Representative Layer Process GPU Execution Order

SAME_INPUT_PROCESS_WISE_PERFORMANCE_BREAKDOWN.md
```

For `Process Launch-owned Kernel Breakdown`, each row is one
`matched_kernel_family` under an aggregated process row. `CUPTI kernel ms` is the
family-specific launch-owned kernel time. `process_CUPTI kernel ms` and
`process_NVTX CPU ms` are process-envelope context columns, not additional
family-exclusive costs.

For `SAME_INPUT_PROCESS_WISE_PERFORMANCE_BREAKDOWN.md`, each row is one
`matched_kernel_family` under a process title across the traced representative
scope. `global_cupti_pct_in_traced_scope` is computed from family-specific CUPTI
time. Process-envelope scope columns must be labeled as scope/context and must
not be summed across families as independent costs.

The Markdown report section `Representative Layer Process GPU Execution Order`
must use nsys-attributed matched-kernel-family rows, not process summary rows and not Nsight Compute replay rows:

```text
one parent layer
  -> one process/fragment owns one or more kernel families by nsys launch attribution
  -> each matched_kernel_family is one table row
  -> row order follows the first launch-owned CUPTI kernel of that family
```

Required report columns include:

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
first_kernel_launch_order_in_process
matched_kernel_family
kernel_family_instance_count
nsys_kernel_duration_ms
streams
correlationId_examples
nsys_kernel_name_examples
gpu_order_basis
```

## Checks

```bash
cd /workspace/VisiPrune/autoresearch/experiments/e2_single_request_latency

sqlite3 output/visipruner_full_eager_process_wise/nsys_sameinput_visipruner_full_eager_32tok.sqlite \
  "select count(*) from NVTX_EVENTS where text like 'visprune.fx_process%';"

rg -n 'Process Launch-owned Kernel Breakdown|Representative Layer Process GPU Execution Order|matched_kernel_family|kernel_family_instance_count|first_launch_owned_gpu_kernel_start' \
  output/visipruner_full_eager_process_wise/SAME_INPUT_VISIPRUNER_FULL_EAGER_PROCESS_WISE_PERFORMANCE_REPORT.md \
  output/visipruner_full_eager_process_wise/SAME_INPUT_PROCESS_WISE_PERFORMANCE_BREAKDOWN.md \
  output/visipruner_full_eager_process_wise/process_kernel_launch_order.csv
```

## Constraints

- No `visprune.fx_process.*` ranges means no strict process-wise report.
- The report must include per-parent-layer matched-kernel-family order sorted by that family's first launch-owned CUPTI kernel GPU start.
- `Process Launch-owned Kernel Breakdown` and `SAME_INPUT_PROCESS_WISE_PERFORMANCE_BREAKDOWN.md` must use `matched_kernel_family` rows, not comma-joined `matched_kernel_families` process rows.
- In the representative-layer order section, each table row is one nsys-attributed `matched_kernel_family`, not one process summary row and not one NCU replay kernel row.
- No-kernel rows fall back to first CUDA runtime call start, then process NVTX start; expose this in `gpu_order_basis`.
- Do not infer GPU order from old CSV/report files that lack timestamp fields.
