# 05 Fresh R01–R10 Process Trace And Resource-gap Analysis

## 目标与唯一运行模式

本工作流只允许 `workflow01-10-fresh-e2e`：从 R01 开始，在同一个 scheduler run
和同一个 lineage 中串行执行到 R10。不得导入、复用或继承其他 runtime 的
R01–R05 ledger、trace、PMC、分析表或可视化结果。

固定模式为：

```text
evidence_acquisition_mode=fresh_no_prior_runtime_reuse
analysis_strategy=fresh_run_full_request_e2e_timeline
measurement_contract_policy=same_run_same_request
physical_dcu_device=1
HIP_VISIBLE_DEVICES=1
CUDA_VISIBLE_DEVICES=1
```

允许每个阶段为 trace、分析或展示目的修改工具代码，但必须记录 stage source
delta。只要模型、输入和语义合同未改变，source hash 变化本身不拆分 lineage；
若语义合同改变，则停止当前 run，不能把前后证据拼成一个 fresh lineage。

## 串行 Goals 与 Skills

| Runtime Goal | Project skill | 前驱 |
|---|---|---|
| R01 | `qwen-dcu-same-input-layer-wise-workflow` | 无 |
| R02 | `qwen-dcu-fx-process-nvtx-instrumentation` | R01 |
| R03 | `qwen-dcu-process-performance-breakdown` | R01–R02 |
| R04 | `qwen-dcu-process-gpu-hardware-trace` | R01–R03 |
| R05 | `qwen-dcu-segmented-process-attribution` | R01–R04 |
| R06 | `qwen-dcu-workflow05-evidence-planning` | R01–R05 |
| R07 | `qwen-dcu-workflow05-full-request-process-trace` | R01–R06 |
| R08 | `qwen-dcu-workflow05-targeted-hardware-gap-analysis` | R01–R07 |
| R09 | `qwen-dcu-workflow05-utilization-concurrency-analysis` | R01–R08 |
| R10 | `qwen-dcu-workflow05-trace-visualization-reporting` | R01–R09 |

调度器必须满足：

1. 每个 Goal 使用持久线程，且一次只运行一个 Goal；
2. Goal 启动前校验全部前驱 handoff 的路径、payload 和 SHA-256；
3. Goal 只向 scheduler 分配的 artifact root 写业务产物；
4. Goal 完成后写一个 scheduler handoff；
5. handoff 校验通过并提交累计 ledger 后，才能启动下一个 Goal；
6. 任何失败、暂停、超时、lineage 漂移或 hash 漂移都停止串行链；
7. R01–R10 全程禁止外部 runtime ledger。

R06–R10 handoff 必须包含：

```text
runtime_goal=Rxx
status=complete
execution_status=complete
evidence_status=complete
coverage_target_met=true
next_authorization_required=false
fresh_e2e_evidence.schema_version=1
fresh_e2e_evidence.status=complete
fresh_e2e_evidence.lineage_id=<same lineage for R06-R10>
```

## R01–R05：同一 run 的上游证据

R01–R05 必须按照 Workflow 01–04 生成本次 run 的 layer denominator、FX/process
边界、代表 process 归因、DCU 硬件属性和全层 process attribution。它们不是可由
R06 外部提供的历史输入，而是当前 R01–R10 ledger 的不可变前缀。

R05 完成时，累计 ledger 必须严格包含 R01、R02、R03、R04、R05 五个已校验
handoff；R06 不得接受缺项、乱序、跨 run 或跨 branch 的前缀。

## R06：fresh 证据与全量目标规划

R06 只做离线规划和能力探测，不运行模型、GPU/DCU 或 profiler。它必须：

- 校验当前 run 的 R01–R05 handoff 前缀；
- 写出 `fresh_run_lineage_manifest.json`；
- 生成完整 request event/range 目标文件，不按 Top-N 截断；
- 生成 R08 的有界 PMC family 计划；
- 探测 Perfetto、Plotly 和离线展示接口；
- 明确记录 capability 可用、降级或不可用状态。

R06 handoff 至少引用：

```text
fresh_run_lineage_manifest
full_request_target_manifest
```

## R07：一次完整请求的 observed 时间轴

R07 在物理 DCU 1 上执行一次 non-replay 完整请求，并覆盖 R06 的全部 process
ranges。该捕获是 R07–R10 唯一的 observed latency clock。

必须采集并对齐：

- request、forward、layer 和 process HIPTX ranges；
- HIP runtime calls；
- strict-owned HIPOPS kernels、queue/stream 和 GPU busy union；
- realtime/monotonic anchors；
- 小于 1 ms 周期的 `se_active_cu_pct` live samples；
- 固定输入的 process dependency adapter。

R07 不得使用 replay duration 作为 observed latency，不得遗漏 R06 目标，不得将
部分请求提升为完整请求证据。

R07 handoff 至少引用：

```text
full_request_profile_metadata
process_trace_summary
fresh_run_dependency_adapter
live_utilization_summary
source_lineage
```

## R08：同 lineage 的 targeted PMC 与资源模型

R08 只对 R06 选定的有界 kernel-family 集合串行执行 PMC replay。R08 必须：

- 继续使用 R06–R07 的 lineage ID；
- 保留 R07 non-replay 时间作为唯一 latency axis；
- 将 PMC/replay 结果标记为 `replay_projected` 属性；
- 探测 gfx936/DCU counter 能力并保留 unavailable 状态；
- 构建 FX-visible traffic/resource model；
- 不把 replay duration 加入 request/process 延迟。

R08 handoff 至少引用：

```text
device_capabilities
traffic_resource_model
source_lineage
```

## R09：十二表完整请求分析

R09 不运行 GPU。它必须从 R07 observed clock 和 R08 replay-projected 属性确定性
生成下列十二个 normalized tables：

```text
request_timeline
process_timeline
kernel_timeline
live_utilization_aligned
process_live_utilization
kernel_concurrency
queue_concurrency
launch_gaps
high_latency_processes
dependency_state
traffic_resource_attachment
opportunity_candidates
```

`fresh_e2e_analysis.json` 必须锁定每张表的路径、SHA-256、row count、schema 和
lineage ID。并发、launch gap 和 overlap 只能在 R07 同一 observed clock 上计算；
PMC 只能作为属性附着。依赖或 counter 不可用时保留 unknown/unavailable，不能
猜测补齐。

R09 handoff 至少引用：

```text
full_request_analysis
source_lineage
```

## R10：自包含、无损、全分辨率可视化

R10 只消费同一 run 的 R09 分析和 R07/R08 证据，不运行模型、GPU/DCU、profiler
或 PMC。交付必须包含：

```text
acceptance/index.html
acceptance/E2E_PROCESS_TIMELINE.html
acceptance/E2E_PROCESS_TIMELINE_LOSSLESS.html
acceptance/E2E_PROCESS_TIMELINE.full.perfetto.json
acceptance/full_timeline_manifest.json
acceptance/HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html
acceptance/CONCURRENCY_UTILIZATION.html
acceptance/offline_acceptance_manifest.json
R10_SOURCE_LINEAGE.json
R10_COMPLETION_AUDIT.json
```

### 无损数据要求

本地查看主机按不少于 128 GiB 内存设计。不得因内存、浏览器负载或文件体积对
timeline 做抽样、均匀取点、Top-N 截断、固定 event budget 或不可逆聚合。

全量 Perfetto 事件数必须严格等于：

```text
request_timeline rows
+ process_timeline rows
+ 2 * kernel_timeline rows
```

两份 kernel records 分别服务 `strict_owned_kernel` 和 `gpu_queue` 轨道，是同一
observed interval 的两种展示组织，不能当作两次计时。manifest 必须声明：

```text
complete_timeline=true
sampling_performed=false
formal_r09_r10_regeneration=true
```

它还必须锁定 R09 analysis SHA-256、十二表 SHA-256、每类事件数、lossless HTML
SHA-256 和完整 Perfetto trace SHA-256。

### 时间精度与交互

浏览器坐标使用相对 request begin 的整数 nanosecond offset。原始绝对
`begin_ns/end_ns` 以十进制字符串保留，禁止把约 `1.7e18` 的绝对 ns 转成
JavaScript `Number` 后相减。

`E2E_PROCESS_TIMELINE_LOSSLESS.html` 必须提供：

- 以鼠标位置为中心的连续缩放，最小 viewport 不粗于 1 ns；
- 拖拽平移、框选/按钮放大、重置和至少 100 步视图历史；
- process/event/layer/phase/family/track 全文筛选和筛选后 fit；
- request/forward/layer/process/HIP runtime/queue/kernel 分轨及 overlap sub-lane；
- 点击同一像素时列出该范围内全部重叠事件，不设条数上限；
- 按精确 begin/end 跳转并列出当前视窗全部事件；
- 总览可使用密度覆盖，但底层事件不得删除、合并或改写；
- 放大后每条原始事件都可独立定位并显示精确字段。

### Top 10 process 配色与所有时间线矩形内名称

生成器必须从完整 R09 `process_timeline` 按 observed HIPTX duration 降序确定前
10 个 `process_range`，不能按当前视窗、筛选结果或 replay duration 排名。同长
时依次按 begin ns 和完整 process 名稳定排序。排名 1–10 必须使用配置
`timeline_visualization.top_latency_process_palette` 中十个互异颜色，且在普通与
lossless 时间线中保持完全相同的映射。

前 10 个 process 矩形使用对应排名色；它们 exact-owned 的 runtime、queue 和
kernel 保留原轨道底色并增加同色描边。页面必须提供常驻图例，列出排名、完整
process 名、observed duration、process-duration share 和 request-span ratio；后者
不能宣称为可相加的端到端归因。

缩放、平移或改变窗口后，request、forward、layer、process、HIP runtime、queue
和 kernel 的每个矩形都必须在空间足够时绘制可读标签。process 使用完整
`process_range`，其余轨道使用规范化事件标签。文字必须裁剪在矩形内；完整标签
能放下时完整显示，否则显示可容纳的前缀和省略号，矩形过窄时不显示。无论是否
显示内嵌文字，点击详情始终提供可复制的完整标签。R10 auditor 必须独立验证排名、
十色映射、七类矩形标签、两个页面的一致性以及放大后的完整标签。

### 离线入口与证据语义

`index.html` 必须是单一人工入口，全部页面自包含，不依赖 CDN、远程脚本、网络
fetch 或云端上传。页面必须明确区分：

```text
observed R07 timing
observed live utilization
replay_projected R08 hardware attributes
derived analysis
unavailable/unknown evidence
```

颜色和轨道不能把 replay-projected 或 unavailable 数据伪装成 observed timing，
也不能把优化候选表达为已获得 speedup。

R10 handoff 至少引用：

```text
offline_acceptance_manifest
source_lineage
```

## 配置与运行入口

正式配置：

```text
perf_trace/configs/workflow01_10_fresh_e2e_dcu1.json
```

调度 dry-run：

```bash
cd /public/home/tangyu408/Qwen_DCU_Worker_0
python3 perf_trace/scripts/run_perf_trace_01_05.py \
  --project-root /public/home/tangyu408/Qwen_DCU_Worker_0 \
  --branch workflow01-10-fresh-e2e \
  --user-parameters-file perf_trace/configs/workflow01_10_fresh_e2e_dcu1.json \
  --dry-run
```

正式运行时去掉 `--dry-run` 并使用新的 `--run-id`。不得提供外部 upstream ledger。

## Completion Checks

- active manifest 只声明 `workflow01-10-fresh-e2e` 和 R01–R10；
- R01–R10 handoff 顺序完整，路径和 SHA-256 全部有效；
- R06–R10 使用同一个非空 lineage ID；
- R07 是完整 non-replay request，目标覆盖率为 100%；
- R08 replay timing 未混入 observed latency；
- R09 十二表齐全且可由源数据确定性重算；
- R10 页面、manifest 和完整 trace 的 row/event/hash 一致；
- 全量时间轴 `sampling_performed=false`；
- 离线页面在浏览器中完成缩放、平移、筛选、精确跳转和重叠事件检查；
- completion audit 未发现外部 runtime evidence、跨 lineage 输入或并行 GPU 工作。
