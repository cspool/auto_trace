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

## 调度与输入注意项

- project scheduler 必须在 R01 启动前显式绑定固定 request 文件或 literal、
  选中行、原始文件哈希和选中请求哈希；缺失时 R01 必须停止，不能自行搜索
  数据集或生成替代 prompt。
- runtime Skill 运行时，正式 Goal 已由外层串行 scheduler 创建；Skill 不得
  再次调用 `create_goal`。恢复一个已 blocked 的 R01 时，应修复输入合同并从
  首个未完成 Goal 重新启动新线程，不续接 blocked Goal，也不复用不完整产物。
- 设备独占性/KFD PID 检查必须在任何可能导入 PyTorch 或初始化 HIP 的模块
  之前执行，避免把当前合同准备进程误判为外部 GPU/DCU 工作。失败 attempt
  应单独保存后重试，不得覆盖或接纳其部分输入/合同文件。
- 当 pinned source checkout 只有 Python 源码、ABI 扩展由同版本已安装 vLLM
  提供时，不能用 `importlib.metadata.distribution("vllm")` 的首个匹配结果定位
  `_C.abi3.so`。`PYTHONPATH` 中 checkout 自带的 `vllm.egg-info` 会遮蔽实际
  site-packages distribution，导致误报“ABI extensions unavailable”。必须枚举
  同名 distribution，校验固定版本，并选择其文件清单中同时实际存在
  `vllm/_C.abi3.so` 与 `vllm/_rocm_C.abi3.so` 的目录；Python 模块仍从 pinned
  checkout 加载，并在证据中记录源码与扩展各自的路径和 SHA-256。
- hipprof 的 HIP runtime 表可能记录 `hipMemcpyWithStream`、`hipMemcpyAsync`、
  memset 等内存 API，但当前 exporter 不保证为这些 host API 生成 HIPOPS kernel
  行。严格“launch 必须有关联 device row”校验只能覆盖经原生 DB 实证的真正
  kernel-launch API（例如 `hipLaunchKernel`、`hipModuleLaunchKernel`、
  `hipExtModuleLaunchKernel`），不能用包含 `memcpy`/`memset` 的宽泛子串规则。
  若首次离线分析因此误报，应保留失败日志和诊断计数，修正 API 分类后复用
  byte-identical 原始 DB/pftrace；不得为纯 analyzer bug 重跑 GPU/DCU 采集。

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
