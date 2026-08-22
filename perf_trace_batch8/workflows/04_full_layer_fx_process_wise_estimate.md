# 04 Full-layer FX Process-wise Estimate

目标：使用 workflow 01 的全量 layer-wise denominator 和 workflow 02 的代表 process template，估计全量 input-layer 的 process-wise 性能分解。

## 运行注意项（batch8 首次执行确认）

- R05 是离线生成阶段，但不能只用 scheduler `state.json` 的心跳判断 formal Turn
  仍有实质进展。batch8 首次尝试曾在 Goal 保持 `active`、scheduler/app-server
  存活且 state 每两秒更新的情况下，连续五分钟不再产生 item、Goal token/time
  更新、子进程或 artifact 文件；默认 `--goal-timeout-seconds=0` 会无限等待这种
  状态。监控必须同时检查最后一个内容 item、Goal `updatedAt`/token/time、活动子进程
  和 artifact 增长；四者均静止且超过明确观察窗时，才可判为挂起 Turn。
- 不得把向 scheduler 的共享 PTY 发送 `Ctrl-C` 当作可靠的“先 pause Goal、再中断
  Turn”操作。batch8 首次恢复中，SIGINT 同时命中同一前台进程组的 app-server，
  app-server 先成为 zombie，scheduler 因无法完成 pause RPC 而只能在 request timeout
  后保存 `stopped` 状态；旧 Goal 仍显示 `active`。恢复前必须等待 scheduler 完整退出、
  核对 scoped PID、ledger 和本阶段 artifact。若 artifact root 只有空目录且无业务文件，
  可从 R05 正常 resume，并用受约束的
  `--resume-artifact-root <canonical R05 root>` 新建正式 Goal，把旧尝试写入 immutable
  `attempt_history`；不得使用 `--continue-current-goal` 假装旧 Goal 已成功 paused。
  若已有部分文件，则必须先逐一审计或隔离失败 attempt，不能覆盖后续可能有效的产物。
  若 app-server 仍健康，优先先用 `/proc/<pid>/cmdline` 校验目标确为当前 run 的 scheduler，
  再只向该 scheduler PID（不是 PTY/进程组）发送 `SIGINT`；batch8 第二次挂起用此方式使
  scheduler 完成 Goal pause 与 Turn interrupt，随后成功用 `--continue-current-goal`
  续接同一 thread、Goal 与 artifact root。恢复后必须重新验证已有文件、ledger、handoff、
  source commit/clean 和锚点哈希，再从未完成后缀继续。
- 运行主机不保证安装 `jq`。R05 首次只读 ledger 检查在成功输出 SHA-256 后因
  `jq: command not found` 返回 127；正式 admission、generator 和 auditor 不得依赖
  未预检的 `jq`，应使用 Python 标准库解析 JSON，并保留明确的非零退出门禁。
- Decimal 权重的计算、求和与容差断言必须位于同一个显式高精度 `localcontext` 中。
  batch8 首次 generator 在 precision 60 下正确计算权重，却离开该 context 后用默认
  precision 28 重新求和，再以 `1e-50` 断言等于 1，导致模板权重假失败。此失败发生在
  output directory 创建前，业务输出数为 0；恢复时应隔离旧 input manifest，记录
  generator/auditor 新旧 SHA-256 和 failure JSON，仅修订离线工具并重新生成，不能放宽
  守恒阈值或修改 R01-R04。修复后仍必须由独立 auditor 重算 denominator group 数、
  leaf row 数、unmatched 数和最大绝对守恒误差。

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
