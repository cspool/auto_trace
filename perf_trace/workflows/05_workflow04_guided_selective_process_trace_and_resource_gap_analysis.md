# 05 Workflow-04-guided Selective Process Trace And Resource-gap Analysis

## 目标

以 Workflow 04 的全 input-layer process 时间估算作为全过程分析索引，尽可能
复用 Workflow 01–04 已有时间、结构和硬件数据，只对高价值或低置信度的少量
layer-process 时间窗追加真实 trace 与硬件采样。

Workflow 05 默认不是全量重新采样工作流。它依次完成：

1. 用 Workflow 04 生成全过程 process 延迟组成概览；
2. 用已有全层 kernel 时间和代表层 R4 数据补充并发与硬件属性；
3. 从全局估算中选择长延迟、高 gap、高风险候选；
4. 只对候选执行 selective non-replay process trace；
5. 只对缺少硬件证据的候选执行 targeted PMC replay；
6. 在证据不足时逐级扩大覆盖，而不是直接全量采样。

## 核心原则

### Workflow 04 是主要全局输入

Workflow 04 已经低成本覆盖全部 input-layer occurrence，并为每个目标提供：

```text
forward/layer/occurrence
phase and layer_type
q_len/past_len/kv_len
process_id and aggregation_key
estimated process ms and layer-conserved fraction
template_event_id
exact or nearest-shape match
attribution_source/evidence_class/confidence/risk
```

Workflow 05 必须首先消费这些数据，不得在没有证明必要性前重新测量全部
input-layer process。

### 已有实测和估算必须分层显示

全过程概览允许同时使用以下证据，但必须标明层级：

| 证据 | 来源 | 可以回答 | 不能回答 |
|---|---|---|---|
| layer 实测时间 | Workflow 01 | 每个 layer-input 的真实总时间 | layer 内 process 边界 |
| process 估算时间 | Workflow 04 | 全量 process 延迟占比和累计热点 | 真实 start/end 与并发 |
| 全层 kernel 时间 | Workflow 01 raw trace | 真实 kernel start/end、queue 和 kernel 并发 | 未经验证的 process owner |
| 代表 process 时间 | Workflow 02/03 | 代表事件的真实 process ownership/order | 所有 shape/layer |
| 代表硬件属性 | R4 | 代表 kernel-family 的硬件行为 | 所有目标的原始运行利用率 |
| selective trace | Workflow 05 | 候选时间窗的真实 process 时间与并发 | 未采样目标 |

### 全量采样是最后升级路径

默认禁止：

- 为 1,856 个 layer-input 全部重新执行 process trace；
- 为所有 process/kernel-family 全部执行 PMC/PMC-read/PMC-write replay；
- 因少量 nearest-shape 行而直接否定 Workflow 04 的全局筛选价值。

只有当分层追加采样仍无法覆盖主要延迟或关键风险时，才允许扩大到批量或全量
采样，并必须记录扩大的理由、预计成本和新增证据价值。

## 分支边界

本文只定义 `workflow05-existing-evidence` 的低成本 selective 路径。它的
R06–R10 分别绑定五个名称含 `legacy` 的 Skill，产物不得声明 fresh-run 完整请求
证据。`workflow01-10-fresh-e2e` 使用另一组 fresh R01–R10 Skill 和十二表 R09
契约；两套完成 schema 不得互相覆盖或混用。

## 调度状态与任意阶段继续

调度器把“阶段是否执行完”和“证据是否足够”拆成两个状态。Workflow 05 每个
R06–R10 handoff 都必须同时记录：

```text
status=complete
execution_status=complete
evidence_status=complete|degraded|insufficient|unknown
coverage_target_met=true|false|null
next_authorization_required=true|false
```

`status/execution_status=complete` 只表示该有界阶段及其校验已结束。只有
`coverage_target_met=true` 且不需要下一次授权时，才能使用
`evidence_status=complete`。因此，调度器跑到 R10 并不自动等于端到端 process、
原始运行利用率、依赖或并发证据已经齐全。

继续接口按运行状态和意图区分：

| 接口 | 适用状态 | 语义 |
|---|---|---|
| `--resume-from Rxx` | `state.status=stopped` | 只能从第一个未完成 Goal 原地恢复，防止跳过失败前驱 |
| `--replay-from Rxx` | `stopped` 或 `complete` | 从分支内任意 Rxx 非破坏性重算后缀，使用新的 `replay-NNN` 命名空间 |
| `--extend-from R06..R09` | `complete` | 冻结完整旧 ledger，只执行显式授权的补证 delta，并在 `extension-NNN` 中重建到 R10 |

R10 只是展示阶段；纯重新生成页面使用 `--replay-from R10`。新增 process trace
必须从 R06/R07 开始，新增硬件 family 可从 R06/R07/R08 开始，只补阈值、当前
child dependency/resource 绑定或重新分析可从 R09 开始。不同 selective child
capture 的绝对时钟永不合并，只按 stable semantic key 汇总覆盖率。
已采样 process 若为补采 live utilization，必须列入
`authorized_process_remeasurements`；这种重测建立新 child axis，不重复增加
semantic latency coverage。

例如，对一个已经 `complete`、但仍缺少
`pra.fx_process.input5_layer6.qkv_projection` 的 run 做增量补证：

```bash
cd /public/home/tangyu408/Qwen_DCU_Worker_0
python3 perf_trace/scripts/run_perf_trace_01_05.py \
  --project-root /public/home/tangyu408/Qwen_DCU_Worker_0 \
  --branch workflow05-existing-evidence \
  --resume-run-id workflow05-v4-dcu1-20260805 \
  --extend-from R07 \
  --extension-parameters '{"selection_batch_id":"workflow05-gap-close-001","escalation_reason":"authorize_material_high-risk_unsampled_process","authorized_additional_process_targets":["pra.fx_process.input5_layer6.qkv_projection"],"minimum_expected_evidence_value":{"policy":"marginal_request_latency_fraction","value":0.004}}'
```

先追加 `--dry-run` 可以完成路径、旧 state/ledger/hash、参数 allowlist 和阶段后缀
校验，不写状态、不创建 Goal，也不启动 DCU；输出中的
`resume.base_run_state` 会同时显示旧 run 的 execution/evidence/coverage/
authorization 状态，避免只看 `state.status=complete`。
同一 process 补证参数也保存在
`perf_trace/configs/workflow05_gap_close_process.example.json`；当前 run 的 R08
hardware-family 补证示例保存在
`perf_trace/configs/workflow05_gap_close_hardware_r08.example.json`。执行前必须把
`selection_batch_id` 改成该 run 从未使用过的新值，并复核 exact target key。

## 可复用工具、接口与代码边界

Workflow 05 不自行实现通用 trace viewer，也不为了接入新工具替换已经验证的
DCU/hipprof 采集链。工具复用分成三层：

1. **直接使用接口**：调用现有工具或 Python API，不复制其内部实现；
2. **复用代码或算法**：只移植与本项目规范化表兼容的分析逻辑；
3. **仅参考设计**：借鉴指标定义或数据模型，不作为当前 gfx936/DCU 的运行依赖。

每次运行必须输出 `workflow05_tool_reuse_manifest.json`，记录工具版本、来源、
调用方式、输入/输出、许可证、上游 commit/tag、是否修改过上游代码以及本机
capability probe 结果。没有通过 capability probe 的工具不得写成 required
runtime dependency。

### 直接使用接口

| 工具 | 使用方式 | 用于 | 默认状态 |
|---|---|---|---|
| 当前 DTK `hipprof` | CLI 读取 queryable DB，并从一次性副本离线导出有界 PFTrace/Chrome JSON/CSV | observed runtime、kernel、copy、queue/stream、flow 时间 | 必选 timing source；原生导出失败才降级 |
| Perfetto Trace Processor/UI | CLI、SQL、浏览器 UI、deep link 或 iframe | 大规模多轨 trace、并发、时间窗查询和下钻 | native 模式必选扩展 |
| Perfetto TrackEvent protobuf | Python/protobuf API 生成 synthetic PFTrace | Workflow 04 估算、证据等级、R4 投影、gap 窗口和 dependency flow | native 模式必选扩展 |
| Plotly.py | Python API 输出自包含 HTML | 29×64 热力图、Top 排名；仅在 Perfetto 尝试失败后渲染自定义时间线 | 全局概览必选，trace 仅作标注回退 |
| NetworkX | Python API 构造 DAG、拓扑检查和最长路径 | dependency、ready/slack 和 critical path | 条件必选；仅在依赖证据存在时 |

#### hipprof 离线原生有界 trace 导出

当前 gfx936/DCU 的采集事实仍由现有 hipprof 工具链提供。已验证的本机接口包括：

```text
--output-type 2     PFTrace
--output-type 0     Perfetto 支持的 Chrome Trace JSON
--db                从已有数据库离线导出
--db-merge          合并数据库
--group-stream      按 stream 组织轨道
--index-range       限制离线导出记录范围
```

典型用法如下；实际运行必须先复制 DB，再对一次性副本执行，不运行模型或 GPU：

```bash
export LD_LIBRARY_PATH=/opt/dtk/dcc/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}

python3 <trace-target>/scripts/perf_trace/export_workflow05_native_windows.py \
  --contract <R07/PFTRACE_DEFERRED_EXPORT_CONTRACT.json> \
  --output-dir <fresh-native-export-root> \
  --hipprof-bin /opt/dtk/bin/hipprof \
  --library-dir /opt/dtk/dcc/lib
```

若完整 DB 过大，先依据 Workflow 04 候选和已有 index/timestamp 映射确定范围，
再使用 `--index-range` 裁剪；每个窗口依次尝试 PFTrace 与原生 Chrome JSON。hipprof
在 index-range 模式下可能不输出包围该窗口的 HIPTX marker，此时保留原生文件不变，
只允许从同一不可变 DB/合同追加唯一且边界精确的 process-marker overlay，并分别
记录 hash。不得为了得到 trace 重新执行全量请求。Workflow 04 估算不得写入同名
observed track。源 DB 导出前后 SHA-256 必须相等；允许导出器只在副本中新增已知的
`RANGE_SUMMARY`，并记录 schema/page 差异。其他副本改写使 PFTrace bridge 降级，
但不否定由不可变源 DB/CSV 验证的时间与 ownership。

#### Perfetto trace、overlay 与 SQL

Workflow 05 使用 Perfetto 的公开格式和接口，不 fork Perfetto UI：

- 用 TrackEvent `slice` 表示 request/forward/layer/process/kernel/gap interval；
- 用 `counter` 表示 queue depth、kernel concurrency、busy state 和可解释的指标；
- 用 `flow` 表示 process→runtime→kernel ownership、dependency 和 critical path；
- 用 event `args` 保存 `evidence_class`、`timing_semantics`、confidence、template、
  hardware source；
- 用 Trace Processor SQL 生成 busy union、overlap、idle、launch gap 和选择结果；
- 用 trace archive/manifest 合并 observed PFTrace 与 synthetic PFTrace。

官方 parser 只有在 PerfettoSQL 同时验证 HIP/HIPOPS/HIPTX 类别计数、精确 process
marker、Runtime/Stream track、flow 数量及 BeginNs/EndNs/index args 后才算复用成功。
结构合法的 JSON 或能打开 UI 本身不等于语义验证通过。

Workflow 04 estimate slice 若为了构图被投影到 measured layer 区间，必须标记
`timing_semantics=projected_composition`。并发、busy union、critical path 和 idle
SQL 只允许消费 `observed_non_replay` 或经过明确许可的 derived observed interval，
不得消费 estimate slice。

接口示例：

```bash
# 合并同一时间基准上的 observed trace 和 Workflow 05 overlay
trace_processor util merge \
  --strict \
  -o workflow05_trace_bundle.tar \
  --manifest perfetto_manifest.json \
  observed.pftrace workflow05_overlay.pftrace

# 大 trace 使用原生 Trace Processor，避免浏览器 WebAssembly 内存限制
trace_processor server http workflow05_trace_bundle.tar

# CI/离线分析执行版本化 SQL，stdout 保存为 CSV
trace_processor query \
  -f workflow05_gap_metrics.sql \
  workflow05_trace_bundle.tar > workflow05_gap_metrics.csv
```

若 trace 文件没有共同 clock，必须生成 `perfetto_manifest.json` 明确 offset；不得靠
人工拖动后把结果当成可复算证据。Plotly 概览链接到 Perfetto 时使用
`visStart/visEnd` 或 `ts/dur`，而不是不稳定的 slice id。需要内嵌 UI 时页面必须由
localhost/HTTP 提供，并使用 Perfetto `postMessage` 接口；不得依赖 `file://`
iframe 行为。

#### Plotly 全局概览

Plotly 只消费 Workflow 01/04、R4 和 Workflow 05 派生的小型 CSV/JSON，不加载
原始十亿字节级 trace。最低使用方式：

```python
import plotly.express as px

fig = px.imshow(
    matrix,
    x=layer_ids,
    y=forward_ids,
    labels={"x": "layer", "y": "forward", "color": "process ms"},
    aspect="auto",
)
fig.write_html(output_html, include_plotlyjs=True, full_html=True)
```

热力图、排名和散点图必须共享稳定主键：

```text
contract_id/forward_id/layer_id/occurrence_id/process_id
```

点击事件读取 `workflow05_trace_index.csv`，显示该单元格的 process 摘要、证据等级
和 Perfetto 时间窗入口。默认输出自包含 HTML；不得依赖 Plotly Cloud 或外部上传。

#### NetworkX dependency/critical-path 接口

只有 `process_dependency_readiness.csv` 已有可审计的数据/控制依赖时，才构造
`networkx.DiGraph`。节点保存 process/kernel start/end，边区分 timing、launch、
queue-order、sync 和真实 data/control dependency；随后使用拓扑检查和
`nx.dag_longest_path(..., weight="weight")` 计算关键路径。

NetworkX 只负责图算法，不产生缺失的依赖。FX 顺序、同 stream 顺序或时间邻接
不得自动冒充 tensor data dependency。

### 复用 HTA/TraceInsight 代码和算法

HTA/TraceInsight 的输入解析面向 PyTorch Profiler/Kineto 和 CUDA 事件，不能直接
读取本项目的 HIP/HIPTX/HIPOPS schema。Workflow 05 不直接调用完整
`TraceAnalysis(trace_dir=...)` 处理 hipprof trace，而是从其 MIT 许可实现中选择性
移植以下算法，并改为消费 Workflow 05 规范化表：

| 上游模块/思想 | 本项目复用内容 | 必须修改的语义 |
|---|---|---|
| `hta/analyzers/breakdown_analysis.py` | temporal/kernel/idle breakdown | CUDA category 改为规范化 HIP family；时间单位统一为 ns |
| `hta/analyzers/trace_counters.py` | queue length 和变化点 counter | 依据 HIP runtime `_Index`、queue/stream 和 kernel start/end 重建 |
| `hta/analyzers/critical_path_analysis.py` | weighted DAG、launch/kernel delay 和 path overlay | 使用本项目 strict ownership、sync 与 FX dependency；不能串行化所有 process |
| `hta/analyzers/cuda_kernel_analysis.py` | launch delay、小 kernel 和频繁序列统计 | CUDA 名称匹配替换为 HIP runtime/kernel-family 规范化字段 |

复用代码必须：

- 固定上游 commit/tag，并保留原许可证与 copyright notice；
- 将修改后的代码放在项目独立 adapter/analyzer 模块，不能修改环境中的 site-packages；
- 为单位换算、同 stream queue、重叠 kernel、同步事件和 unknown dependency 建测试；
- 将 HTA 的 heuristic 输出标为 `heuristic`，不能升级为 observed dependency；
- 记录与上游算法的差异，不把 CUDA Graph 等建议机械翻译为 DCU 结论。

HTA 的 idle 分类只作为起点：`host_wait`、`kernel_wait` 和 `other_wait` 必须结合本项
目的扩展为 `gpu_idle`、`runtime_launch_gap`、低并发、active underutilized 和
resource-limited 等窗口。

### 仅参考设计，不作为默认运行依赖

- **ROCm Compute Profiler**：参考 Roofline、Speed-of-Light、硬件 block 指标分组和
  kernel/dispatch filtering；当前主要支持 AMD Instinct MI 系列，未证明 gfx936
  DCU 可运行。只有单独 capability probe 成功后，才允许用
  `rocprof-compute profile --kernel ...` 或 `--roof-only` 补充目标 family。
- **rocprofv3 / ROCm Systems Profiler**：参考 rocpd、PFTrace、system trace 和 counter
  track 设计。当前环境未安装，不能替换已验证 hipprof，也不能成为 Workflow 05
  的完成前提。
- **MLCommons Chakra**：参考 compute/memory/communication node、data/control
  dependency、timing 和 resource constraint schema。默认继续使用已有 FX/CSV；只在
  需要跨工具交换完整 execution graph 时追加 Chakra protobuf 导出。
- **HPCToolkit**：参考 CPU/GPU calling-context 和源码归因；其 AMD 路径依赖
  ROCProfiler-SDK，未证明适配当前 DCU，因此不进入默认采集链。

上游入口：

- [Perfetto](https://github.com/google/perfetto)
- [Perfetto custom TrackEvent](https://perfetto.dev/docs/getting-started/converting)
- [Plotly.py](https://github.com/plotly/plotly.py)
- [HTA/TraceInsight](https://github.com/facebookresearch/HolisticTraceAnalysis)
- [NetworkX DAG longest path](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.dag.dag_longest_path.html)
- [ROCm Compute Profiler](https://rocm.docs.amd.com/projects/rocprofiler-compute/en/develop/what-is-rocprof-compute.html)
- [MLCommons Chakra](https://github.com/mlcommons/chakra)
- [HPCToolkit GPU monitoring](https://hpctoolkit.gitlab.io/hpctoolkit/users/gpu/gpu.html)

## Required Inputs

### Workflow 01：全层实测分母与原始 kernel 时间

```text
SAME_INPUT_*_LAYER_PERFORMANCE_REPORT.md
*_all_input_layer_performance.csv
*_layer_events.csv
*_layer_kernel_breakdown.csv
*_layer_kernel_launch_order.csv
raw/queryable non-replay profiler trace
```

### Workflow 02/03：代表 process 时间与结构

```text
FX_PROCESS_NVTX_INSTRUMENTATION_HANDOFF.md
process_range_inventory.csv
same_input_*_process_attribution.csv
same_input_process_summary.csv
representative process performance report
```

### Workflow 04：全 input-layer process 估算

```text
full_layer_attribution_type_map.csv
full_layer_template_assignment.csv
full_layer_process_attribution.csv
full_layer_process_aggregation.csv
full_layer_coverage_and_risk.csv
full-layer process attribution reports
```

### R4：代表 kernel-family 硬件数据

```text
non_replay_analysis/process_gpu_timeline.csv
non_replay_analysis/runtime_calls.csv
non_replay_analysis/kernels.csv
non_replay_analysis/strict_ownership.csv
hardware_metrics_by_kernel_family.csv
hardware_metrics.csv
hardware_coverage.json
```

R01–R05 输入必须来自同一历史 `SAME_INPUT` contract，并保持只读。R06 只在该
历史合同内做全局排名和候选规划。R07 开始前必须检查当前 checkout、build 与
instrumentation；若执行路径与历史合同不同，不得因此丢弃历史筛选结果，也不得
把历史实测冒充为当前实测，而是创建一个不可变的**当前测量子合同**：

```text
parent = R01-R05 historical planning contract
child  = same request/model/config/device + current source/build/instrumentation
relation = same_request_cross_revision
historical clock and current clock = separate, never merged
```

子合同必须固定 parent ID/SHA、当前 revision/source-state/build hashes、R06 计划
hash、精确 range 集合、基线输出 token/text hashes 与关系类型。R07–R10 当前实测
统一使用该子合同；R01–R05 文件及其合同不得修改。若当前执行路径恰好完全一致，
仍可建立 `same_request_same_revision_new_instrumentation` 子合同以隔离新的采集时钟。

## Workflow 05 执行顺序

### Step 0：工具 capability probe 与复用锁定

该步骤只检查版本、格式和离线接口，不运行模型或 GPU：

1. 复制小型已有 DB，用 `export_workflow05_native_windows.py` 依次探测有界 PFTrace/
   Chrome JSON，并验证源 DB 不变、仅副本新增 `RANGE_SUMMARY`；
2. 用 `probe_workflow05_open_source_trace.py --native-export-manifest ...` 验证官方
   Trace Processor 的真实 parse/query 与上述 trace 语义；
3. 记录 Perfetto、Plotly、NetworkX 版本和 HTA 上游 commit/license；
4. 用最小 synthetic trace 验证 slice、counter、flow、args 和多 trace clock 对齐；
5. 生成 `workflow05_tool_reuse_manifest.json` 和 `tool_capability_probe.json`。

若 Perfetto Python 包暂不可用，可以使用其 protobuf schema 生成 TrackEvent。
默认 `auto` 模式先尝试原生 PFTrace、原生 Chrome+精确 marker overlay、规范化
Chrome overlay 和官方 Perfetto Python/CLI/UI；全部失败/不可用后才允许生成带
`CUSTOM FALLBACK` 标识的自包含 Plotly 时间线。不得冒充 Perfetto parse/bundle，
也不得另写 parser。`native` 模式必须通过官方 parser 的语义 query。

### Step 1：离线复用 Workflow 04，生成全过程估算概览

不运行 GPU。直接从 Workflow 04 生成：

- 全请求 phase/process 延迟汇总；
- 每个 forward 的 64 层 process 组成；
- 29 × 64 layer-input 延迟热力图；
- Top cumulative process、Top layer-input 和 Top forward；
- exact/nearest-shape、confidence 和 risk 覆盖图；
- 每个目标使用的代表 template 和距离。

该步骤回答“全过程中可能最重要的 process 在哪里”，并形成后续采样候选，不把
估算行表述为真实 process trace。

实现上使用 Plotly 生成热力图、排名和证据覆盖图，同时生成只包含小型派生数据的
`workflow05_trace_index.csv`。每个可下钻目标提前保存对应 observed layer/kernel
时间窗或 selective trace 时间窗；没有真实时间窗的估算行只链接到 template 和
证据说明。

固定生成 `LAYER1_HISTORICAL_LATENCY_OVERVIEW.html`：显示全过程 measured
layer/kernel 时间轴、按 host process 延迟累计到 80% 的 Pareto 排名、process 组成
以及 29×64 forward-layer 矩阵。Workflow 04 process slice 只能标为
`projected_composition`，用于延迟占比和候选定位，不得用于证明 process 并发。

### Step 2：复用 Workflow 01 kernel 时间和 R4 模板，构造低成本并发视图

Workflow 01 的原始 trace 已包含全部 layer-input 的 kernel start/end 和 queue。
优先离线复用这些真实时间，不重新采集。

对每个 layer-input：

1. 从 Workflow 04 读取 `template_event_id`、process 顺序和时间比例；
2. 从代表 R4 读取 `event_id + aggregation_key + kernel_family` 的 ownership/order；
3. 将目标 layer 内的真实 kernel family、launch order 和 queue 与模板匹配；
4. 给每个 kernel 生成 process owner 状态：

```text
observed_representative_owner
inferred_exact_template_owner
inferred_nearest_shape_owner
ambiguous_owner
unmapped_owner
```

5. 仅使用 Workflow 01 的真实 kernel start/end 计算 kernel/queue concurrency；
6. process concurrency 只有在 owner 唯一时才显示为 inferred，ambiguous/unmapped
   kernel 必须单独保留。

这一视图的时间坐标是真实的，process 标签可能是推断的。二者不能合并成一个
无证据等级的“实测 process trace”。

优先从 Workflow 01/Selective 已有 `.hipprof.db` 离线导出有界 PFTrace；若 PFTrace
无法与精确 marker companion 一起验证，则使用原生 Chrome+同 DB marker overlay；
再失败才使用规范化 Chrome adapter。Workflow 04 process owner 推断、R4 属性和
confidence 另写入 `workflow05_overlay.pftrace`，再通过 manifest 与 observed trace
合并。官方接口不可用时才从小型规范化表生成带 `CUSTOM FALLBACK` 的 Plotly
tracks。所有模式都禁止重写 observed kernel 的时间戳或持续时间。

### Step 3：从 Workflow 04 选择 selective trace 候选

候选选择同时考虑性能贡献和证据风险：

```text
cumulative process ms
layer-input ms
phase and layer_type
shape class and q/kv regime
template distance
exact versus nearest-shape
confidence/risk
unmapped or ambiguous kernel time
R4 hardware coverage
process semantic class and template kernel-family mix
host/GPU exposure and kernel-count/launch-density quantile
R4 compute/memory/occupancy/stall signature
```

最低选择策略：

1. 仍以累计延迟贡献为第一优先，直到覆盖配置比例或命中硬预算；
2. 对延迟贡献不低于当前最佳候选 90% 的候选，优先选择在 process 语义、
   phase/type/shape、kernel-family mix、host/GPU exposure、launch density、R4
   瓶颈签名或证据风险上增加新取值的 process；按新增轴数、延迟贡献、stable key
   确定性排序，不使用隐式加权分数；
3. 达到延迟覆盖后，最多使用相同 count/time/PMC 硬预算的 25% 补齐计算或性能特征
   不同、且预计证据价值达到门槛的 process；该比例不是额外预算；
4. 每种重要 `phase × layer_type × shape_class` 尽量保留代表，并继续优先高时间的
   template 风险、owner ambiguity 与缺失/矛盾 R4 证据；
5. 对数值特征只按本次历史分位数离散化，记录边界；缺失特征保持 unavailable，
   不得为了“多样性”臆造 FLOPs、利用率或瓶颈。

输出 `selective_trace_plan.csv`，每一行必须说明选择原因和它预计验证的 Workflow
04 假设，以及 feature signature、新增轴和 diversity selection reason。不得只因层号
不同重复采样相同类型目标。

### Step 4：只对候选执行 selective non-replay process trace

保持 Workflow 01/04 的请求、模型、配置与设备语义，但把当前执行路径绑定到上述
R07 测量子合同。仅为 `selective_trace_plan.csv` 中的精确 layer-process/fragment
开启 range；历史合同只负责选择候选，不负责声明当前 timing 等价。

R06 计划的采集行必须显式包含：

```text
hiptx_range
collection_required=true
fragment_id
aggregation_key
selection_batch_id
```

使用项目脚本生成当前子合同、规范化计划和当前 inventory：

```bash
python3 <trace-target>/scripts/perf_trace/prepare_workflow05_selective_capture.py \
  --parent-contract <R01 SAME_INPUT contract> \
  --baseline-run-metadata <R01 non-replay run metadata> \
  --selection-plan <R06/selective_trace_plan.csv> \
  --template-inventory <R02/process_range_inventory.csv> \
  --source-root <project-root>/pra2026-bh408 \
  --output-dir <R07/preparation>

source <R07/preparation/selective_capture_targets.env>
```

采集器使用两级门控：

```text
PRA_BACKEND_PERF_PROCESS_TARGETS=<selected event IDs>
PRA_BACKEND_PERF_PROCESS_RANGE_TARGETS=<exact full pra.fx_process.* names>
```

第一个变量只选择 layer event；第二个变量必须逐一匹配完整 process/fragment range。
Workflow 05 launcher 要求第二个变量非空并验证语法。空的精确列表只为旧工作流保留
整层兼容行为，不能用于 Workflow 05。运行 metadata 必须证明 emitted range 集合与
规范化计划完全相等，不能把一个目标扩成该层所有 process。

必须采集：

```text
selected parent layer range
selected process/fragment HIPTX range
HIP runtime begin/end and runtime index
strict-owned kernel begin/end
queue/stream and launch parameters
process/kernel order and overlap
```

该 trace 用于：

- 校验 Workflow 04 的 process 时间比例；
- 校验模板 process 顺序和 kernel-family owner；
- 确认候选 process 的真实 start/end、busy union 和并发；
- 校准相同 attribution type 的未采样目标；
- 判断是否需要扩大采样。

selective trace 不要求覆盖全部 1,856 个 layer-input。

新采 selective trace 同时保留 queryable hipprof DB，并输出 PFTrace 或允许后续从
DB 离线导出 PFTrace。采集器仍是已验证的 hipprof；Perfetto 只负责离线解析和表达，
不得被写成新的 timing source。

`analyze_qwen_hipprof_process_trace.py` 直接生成七个 `selected_*` 规范化表。其
`selected_process_overlap.csv` 固定为 version 1：对同一当前请求中的每个无序
process-range 对，分别输出 `process_host_range` 与
`strict_owned_gpu_busy_union` 域；正重叠按 segment 一行，零重叠输出显式 zero 行，
缺少 strict-owned GPU interval 输出 `interval_unavailable`，绝不能当作零重叠。
完整列序与 row grain 写入 `selected_process_overlap.schema.json`。

### Step 5：最大化复用 R4，只补采缺失硬件证据

首先尝试把代表 R4 硬件数据连接到候选：

```text
Workflow05 selected event/process
  -> Workflow04 template_event_id + aggregation_key
  -> R4 event_id + aggregation_key + matched_kernel_family
```

若 R4 与 R07 子合同执行路径不同，该连接只能标为
`historical_template_only/execution_path_changed`，用于决定采哪些当前 family，不能
作为当前 observed utilization。当前硬件结论必须来自子合同下的 targeted PMC；
历史 R4 与当前 selective 时间轴始终分轨、分合同显示。

复用状态分为：

```text
reused_exact_hardware
reused_shape_compatible_hardware
reused_exploratory_hardware
hardware_missing
execution_path_changed
```

只有以下情况才追加 PMC/PMC-read/PMC-write：

- 长延迟 process 的关键 family 没有 R4 指标；
- 目标 shape 与代表 shape 差异可能改变 kernel/path；
- selective trace 出现新的 kernel family 或 instance pattern；
- 代表 R4 的利用率/资源结论无法解释当前候选；
- 低利用率候选对优化决策具有较高端到端影响。

PMC replay 必须独立于 non-replay timing，并保持：

```text
timing_source=selective_non_replay_trace
hardware_source=reused_or_targeted_pmc_replay
pmc_replay_timing_used_as_latency=false
```

### Step 6：离线补充理论负载、依赖和 ready/slack

优先复用同 contract 的 algorithmic trace、FX process reconstruction、Workflow
04 类型映射和 runtime trace。理论 FLOPs/bytes、shape 和依赖尽量离线计算，不为
此目的重新运行全量 PMC。

每个被分析的 process 尽量补充：

```text
theoretical_flops
theoretical_read/write_bytes
arithmetic_intensity
tensor shapes and parallel dimensions
working-set estimate
predecessor/successor ids
ready timestamp when observable
critical-path status and slack
custom-op visibility status
```

缺少 ready/slack 时可以报告“低利用率窗口”，但不能报告确定的“可并发任务”。
opaque custom op 的内部负载保持 unknown。

依赖和关键路径实现优先直接调用 NetworkX。idle、queue length、launch delay 和
critical-path overlay 可复用 HTA/TraceInsight 的算法结构，但输入必须来自
`selected_runtime_calls.csv`、`selected_kernels.csv`、strict ownership 和 FX
dependency adapter；不得直接把 hipprof JSON 当成 Kineto trace。

### Step 7：按证据覆盖逐级升级

每轮 selective trace/PMC 完成后重新计算：

```text
covered_workflow04_latency_pct
exact_or_validated_process_time_pct
kernel_owner_resolved_time_pct
hardware_explained_time_pct
high_risk_unvalidated_time_pct
```

若主要延迟和高风险目标已经覆盖，则停止采样。若未覆盖，按 Workflow 04 排名
追加下一批候选。只有多轮追加仍无法满足门槛时，才允许全量 process trace 或
全量 PMC replay。

## 表达一：全过程端到端 Process 时间图

### 目的

先确认全过程的延迟组成，并尽可能观察 process/kernel 并发。主视图必须把
Workflow 04 估算与 selective 实测区分开。

### 实现载体

该表达不是单一超宽表，而是两个相互链接的开源工具视图：

1. **Plotly 全局索引**：显示 29×64 热力图、forward/process 排名、延迟组成和
   evidence/risk；适合回答“哪里长、占比多大、应先看哪里”；
2. **Perfetto 时间轴**：显示 request/forward/layer/process、HIP runtime、kernel、
   copy、queue/stream、counter 和 flow；适合回答“何时执行、是否重叠、空洞在哪里”。

Plotly 单元格和排名行通过稳定主键查询 `workflow05_trace_index.csv`。有真实时间窗
时使用 Perfetto `visStart/visEnd` 或 `ts/dur` 打开对应区域；只有 Workflow 04 估算
而无真实边界时，详情面板必须停留在 estimate/template 视图。

### 两层时间表达

#### 全量估算层

覆盖全部 input-layer：

```text
Request/forward/layer   Workflow 01 measured layer time
Process composition    Workflow 04 estimated process fractions and ms
Kernel/queue timeline  Workflow 01 measured kernel start/end
Process labels         R4-template inferred owner with confidence
```

该层用于确认延迟占比、累计热点和候选并发区域。它不声称所有 process 边界均为
实测。

#### Selective 实测层

对已采样候选显示：

```text
Host process range
strict-owned GPU kernel intervals
runtime calls
queue/stream
process/kernel overlap
```

点击全量估算中的候选，应直接切换到对应 selective 实测时间窗；未采样目标显示
其 template、confidence 和风险，而不是伪造实测条。

Perfetto track 最低布局：

```text
Estimated group   Workflow04 process composition, confidence and risk
Observed host     request/forward/layer/HIPTX process ranges
Runtime           HIP API, launch, sync and wait
GPU queue/stream  kernels, copies and barriers grouped by real queue/stream
Derived counters  active kernels, queue depth, busy state and unresolved time
Evidence          observed/inferred/replay_projected/unavailable
```

estimate track 与 observed track 必须视觉分组且命名不同；不得让同色、同轨或缺少
legend 的设计掩盖证据差异。

### 时间指标

| 指标 | 全量来源 | Selective 来源 |
|---|---|---|
| layer wall/host time | Workflow 01 measured | measured |
| process kernel-sum | Workflow 04 estimate | strict-owned measured |
| process busy union | inferred only when owner resolved | measured |
| process overlap | inferred with confidence | measured |
| exposed/critical-path time | estimated/derived | measured/derived |

## 表达二：长延迟 Process 时间窗分析

### 选择来源

首先按 Workflow 04 的累计 process 时间、layer-input 时间和风险排序，再用
selective trace 验证。优先级不是“全部采样后再排名”。

### 时间窗显微镜

所有面板共享 selective non-replay 的真实时间横轴：

| 面板 | 内容 |
|---|---|
| Process | process/fragment 和算法子阶段 |
| Kernel/queue | family、start/end、queue、重叠和空洞 |
| Hardware | 复用或补采的 ALU/MMAC/cache/带宽/occupancy/stall |
| Runtime | HIP API、launch interval、sync/wait |
| Theory | FLOPs、bytes、arithmetic intensity、shape |
| Resource | VGPR、SGPR、LDS、工作集和 occupancy 限制 |

实现分工：

- Perfetto 负责共享真实横轴、track 展开、事件选择、flow 和 runtime/kernel 并发；
- R4/targeted PMC CSV 通过 adapter 连接到 strict-owned kernel instance/family；
- synthetic PFTrace 只把 R4 指标投影为 kernel interval 的 args/counter，不改写
  non-replay duration；
- Plotly 负责单个 process 的 Roofline、理论值/实测值、资源占用和证据摘要；
- ROCm Compute Profiler 的 Roofline/SOL 分组仅作为指标组织参考，除非 gfx936
  capability probe 已通过。

R4 replay 值若画成 counter，必须标记 `counter_semantics=replay_projected_step`；
它表示该 kernel/family 的离线属性，不表示原始运行中的连续硬件采样曲线。

硬件面板默认只展示少量可决策指标组，原始 R4 全列保留在 CSV 下载/展开详情：

```text
compute      ALU/MMAC active, achieved FLOP/s, compute SOL
memory       HBM/L2/L1 traffic, bandwidth SOL, cache hit
occupancy    waves, theoretical/achieved occupancy when available
resource     VGPR/SGPR/LDS/scratch/workgroup
stall        only counters with verified semantics
evidence     reuse status, source event/family, replay batch and confidence
```

每个硬件值注明：

```text
reused_exact_hardware
reused_shape_compatible_hardware
reused_exploratory_hardware
targeted_replay_hardware
unavailable
```

长 process 分析结果要回写到相同 attribution type 的 Workflow 04 行，以更新全局
候选优先级和证据覆盖，而不是只生成孤立的代表层报告。

## 表达三：低资源利用率时间窗与可并发机会

### 低成本扫描

优先使用：

- Workflow 01 的全量真实 kernel/queue 时间；
- Workflow 04 的 process 时间和 template；
- R4 已有 kernel-family 硬件属性；
- selective trace 校准后的 process owner；

在真实 kernel start/end 变化点上构造时间区间。若硬件属性来自 replay 投影，
时间窗标记 `replay_projected`；只有原始运行采样才能标记
`observed_in_original_timeline`。

实现上由版本化 Perfetto SQL 或等价的规范化表算法完成 sweep-line interval
构造，不在 Plotly JavaScript 中重复计算。最低派生轨道包括：

```text
gpu_busy_state
active_kernel_count
active_queue_count
runtime_outstanding_count
launch_gap
idle_or_underutilized_window
window_evidence_class
```

HTA/TraceInsight 的 queue-change-point 和 idle breakdown 代码可以移植到该规范化
层；其 `host_wait/kernel_wait/other_wait` 只能作为 heuristic 子分类。最终窗口分类
仍以本项目 HIP runtime、strict ownership、R4 evidence 和 unknown 保留规则为准。

至少区分：

```text
gpu_idle
runtime_launch_gap
active_compute_underutilized
active_memory_underutilized
compute_busy_memory_idle
memory_busy_compute_idle
low_kernel_concurrency
resource_limited
utilization_unresolved
```

### 可并发机会

候选任务必须满足：

1. 没有未满足的数据或控制依赖；
2. 在时间窗开始前已经 ready；
3. 有足够 slack；
4. runtime/queue 支持并发；
5. VGPR/LDS/cache/显存/带宽能够共同容纳；
6. 资源需求与空闲资源互补；
7. 预计覆盖 exposed time，而不是只增加 kernel overlap。

没有 dependency/ready/slack 证据时，只输出“待验证并发候选”。只有 targeted
对照实验才能把机会升级为实际 speedup。

dependency graph 使用 NetworkX `DiGraph`：真实 data/control dependency、launch、
same-queue order 和 sync edge 分类型保存，先验证 DAG，再计算 weighted longest
path、earliest-ready 和 slack。HTA critical-path 实现只提供建图/overlay 参考；
MLCommons Chakra 仅在需要跨工具交换完整 execution graph 时作为可选导出 schema。

Perfetto 中用 flow/debug track 显示 critical path 和候选移动方向；Plotly 中只展示
机会排名、资源互补度和预计 exposed-time coverage。二者都不能把模拟重排显示成
observed overlap。

### 优化动机分类

| 时间窗证据 | 优化方向 |
|---|---|
| GPU idle、launch gap、sync/wait | 系统/runtime：异步提交、流水化、减少同步 |
| 大量小 kernel、低并行度 | 负载：融合、batch、重构 process |
| GEMM/attention 利用率低或资源受限 | kernel/硬件：tile、backend、VGPR/LDS |
| 独立任务 ready 且资源互补 | 并发：多 queue、跨请求 batching、计算/搬运重叠 |

## Expected Outputs

### 工具复用与 trace 底座

```text
workflow05_tool_reuse_manifest.json
tool_capability_probe.json
third_party_provenance.json
workflow05_trace_index.csv
workflow05_native_hipprof_window_exports.json
workflow05_open_source_trace_attempts.json
observed_hipprof.pftrace
observed_hipprof_with_process_marker.json
workflow05_overlay.pftrace
perfetto_manifest.json
workflow05_trace_bundle.tar
workflow05_gap_metrics.sql
workflow05_gap_metrics.csv
```

`observed_hipprof.pftrace` 可由 R01/R02/Selective 的已有 DB 离线导出，不要求复制
一份全量大文件到每个结果目录；允许 manifest 引用带 hash 的受管 trace。
`workflow05_overlay.pftrace` 只能包含 synthetic/derived 数据，并在每个 track/event
中保存证据等级。SQL 文件必须版本化，CSV 是其可复算输出。

### Workflow 04 复用与候选选择

```text
workflow04_reuse_manifest.json
full_layer_process_overview.csv
full_layer_process_evidence_status.csv
kernel_process_owner_inference.csv
selective_trace_plan.csv
selective_hardware_plan.csv
```

### Selective 实测证据

```text
current_measurement_contract.json
selective_capture_preparation_manifest.json
normalized_selective_trace_plan.csv
current_process_range_inventory.csv
selective_capture_targets.env
live_hardware_samples.csv（仅显式启用且通过分辨率/对时校验时）
live_hardware_sampling_alignment.json（同上）
selected_annotations.csv
selected_runtime_calls.csv
selected_kernels.csv
selected_strict_ownership.csv
selected_process_gpu_timeline.csv
selected_process_performance.csv
selected_process_overlap.csv
selected_process_overlap.schema.json
targeted_hardware_metrics_by_kernel_family.csv
```

这些文件使用当前测量子合同。历史全过程页面继续引用 parent contract；当前 selective
页面引用 child contract，并通过 `contract_relation` 与同一 semantic stable key 互相
跳转。两个页面不得共享绝对时间原点，也不得把两条时间轴打包成一个 observed trace。

### 理论负载、gap 与机会

```text
process_theoretical_workload.csv
process_dependency_readiness.csv
hardware_time_intervals.csv
long_process_windows.csv
low_utilization_windows.csv
concurrency_opportunities.csv
workflow05_coverage_and_risk.json
```

### 人工阅读入口

```text
WORKFLOW05_ACCEPTANCE_INDEX.html
E2E_PROCESS_ESTIMATE_AND_EVIDENCE.html
SELECTED_PROCESS_TRACE.html
LONG_PROCESS_WINDOW_ANALYSIS.html
LOW_UTILIZATION_AND_CONCURRENCY_OPPORTUNITIES.html
WORKFLOW04_GUIDED_RESOURCE_GAP_REPORT.md
```

全量页面默认显示 Workflow 04 估算和证据等级；只有 selective 页面显示真实
process trace。CSV/JSON 保持机器可复算，Markdown 只放全局结论、候选、覆盖率
和下一批采样建议。

`WORKFLOW05_ACCEPTANCE_INDEX.html` 是复制到容器外后直接双击打开的离线验收
首页。它必须使用相对链接，显示 execution/evidence/coverage/authorization 状态，
枚举历史全过程估算轴、每个独立 supplemental capture 实测轴、长 process 硬件视图和
低利用率/并发证据视图。单独的 hipprof native HTML 只是 selected-window 原始
trace viewer，不等于 Workflow 05 端到端验收页面。

其中：

- `E2E_PROCESS_ESTIMATE_AND_EVIDENCE.html` 复用第一层历史概览作为全局索引；
- `SELECTED_PROCESS_TRACE.html` 默认先通过官方 Perfetto UI launcher 显示 observed
  process、HIP runtime、GPU queue、flow、replay-projected hardware 和 evidence；
  官方接口失败后才使用明确标注的 Plotly `CUSTOM FALLBACK`；
- 后两页复用相同 trace index、SQL 输出和 stable key，不另算一套指标；
- 自包含 Plotly 页面不得上传数据到云端；Perfetto trace 默认在本地解析。

## Cost Controls

调度器先应用以下审计默认值，用户参数只覆盖明确提供的键；每次运行必须记录最终
解析值：

```text
trace target = <project-root>/pra2026-bh408（固定且与 R01-R05 source_root 一致）
strategy = two_level_historical_then_selective_timeline
primary ranking metric = hiptx_host_range_duration_ms
secondary views = kernel busy union, kernel sum（禁止与 primary 相加）
candidate policy = latency_coverage_with_feature_diversity
feature diversity budget fraction = 0.25（包含在原硬预算内）
feature diversity latency guard band = 0.90
minimum new feature axes = 1
target cumulative latency coverage = 0.80
maximum selected layer-input count = 32
maximum selected process count = 64
maximum targeted PMC family count = 16
maximum profiling wall time = 7200 seconds
Workflow 05 policy version = workflow05-low-cost-timeline-v4
selection batch id = low-cost-timeline-default-v4
escalation reason = top_latency_low_utilization_resource_gap_analysis
maximum trace export interval/count = 64
maximum trace bundle bytes = 2147483648
Trace Processor mode = auto
observed trace priority = native PFTrace -> native Chrome + exact DB marker -> normalized Chrome -> labeled custom fallback
native hipprof export order = PFTrace -> Chrome JSON
real-machine device policy = physical DCU 1 only; HIP_VISIBLE_DEVICES=1; CUDA_VISIBLE_DEVICES=1
PMC collection policy = bounded family superset + exact post-attribution
measurement contract policy = compatible_request_separate_capture_axes
base evidence role on execution-path change = base_evidence_planning_only
exact process range filter required = true
cross-capture timeline policy = separate_clock_axes_no_merge
high risk = evidence quantile 0.75
template shape distance = evidence quantile 0.90
owner ambiguity = observed duration fraction 0.05
hardware evidence gap = request latency fraction 0.01
minimum expected evidence value = marginal request latency fraction 0.005
observed HCU/CU/wave/bandwidth low thresholds = null（未授权前不可分类）
replay-projected ALU low threshold = null（只允许 replay-projected 诊断）
low kernel concurrency max active kernels = 1
runtime launch-gap minimum = null
dependency coverage threshold = null
opportunity minimum exposed duration/fraction/slack tolerance = null
dependency adapter = null（可用 path + sha256 显式绑定）
traffic/resource coexistence model = null（可用 path + sha256 显式绑定）
live hardware sampling mode = disabled
```

启用 live hardware sidecar 时必须提供 collector 路径/hash、metric 列表、正采样
间隔、每个 process 最少样本数和最大时钟对齐误差。`hy-smi` 若返回上一秒聚合值，
或实测 cadence 不细于毫秒级 process 窗口，只能作为 device-level diagnostic，
不能标为该 process 的 observed 利用率。PMC/R4 也不能替代这一原始运行采样。

采样终止条件：

- 已验证候选覆盖目标累计延迟比例；
- 高时间、高风险 Workflow 04 行均已解释；
- kernel owner ambiguity 降至目标门槛；
- 主要低利用率窗口具有足够硬件证据；
- 下一批预计新增证据价值低于配置门槛。

禁止为了追求 100% 行覆盖而忽略 profiling 成本。未采样行继续保留 Workflow 04
估算及其 confidence/risk，不得删除或伪装成实测。

已有大 trace 优先通过 hipprof DB 离线裁剪、Perfetto native Trace Processor 和 SQL
查询复用。不得因浏览器无法一次打开大文件就重新采集更小的全过程 trace。

## Completion Checks

### 工具与代码复用

- hipprof probe 证明源 DB 不变，副本改写已审计，9 个窗口的 PFTrace/Chrome 导出均
  核对 runtime/kernel 数量、raw bounds、stream/flow，且离线导出不启动 GPU；
- selected visual candidate 中同 DB HIPTX marker 恰好一次，原生事件保持不变；
- native 模式要求 Perfetto 能解析 observed/overlay trace 且 merge 无 clock error；
- observed slice 时间戳、duration 和 kernel count 与源 DB/CSV 一致；
- 所有 estimate slice 都带 `timing_semantics=projected_composition`，且不进入
  observed concurrency/busy/idle SQL；
- Plotly HTML 能离线打开，29×64 单元格和 stable key 覆盖完整；
- trace index 的时间窗能定位到对应 forward/layer/selective process；
- native 模式下 Trace Processor SQL 与 Python sweep-line 的 busy union、overlap、
  idle 一致；browser 模式保留规范化表结果并明确 native SQL unavailable；
- NetworkX graph 在求最长路径前通过 DAG 校验，unknown dependency 不被删除；
- 若移植 HTA 代码，`third_party_provenance.json` 记录 commit、license、文件和修改；
- 未通过 gfx936 capability probe 的 ROCm/HPCToolkit 工具没有进入 required path。

### Workflow 04 复用

- 全部 Workflow 04 layer-input/process 行进入全量概览；
- 每行保留 template、match、confidence、risk 和 attribution source；
- Workflow 04 process 之和仍保持到 Workflow 01 layer denominator 的守恒；
- selective 结果以新证据列覆盖或校准，不破坏原估算的可追溯性。

### 时间与并发

- 全量 kernel 时间只来自 Workflow 01 non-replay trace；
- selective process 时间只来自 selective non-replay trace；
- R01–R05 parent contract 与 R07–R10 child contract 的 source/build/hash 关系已记录；
- 当前执行路径变化时，历史 timing/R4 只用于排名与模板，不能标为当前 observed；
- 两个合同只通过 semantic stable key 跳转，绝不合并 clock、busy 或 concurrency；
- Workflow 05 采集 range 与规范化计划逐项相等，没有 event 级 marker expansion；
- inferred process owner 与 observed owner 明确区分；
- ambiguous/unmapped kernel 时间不被静默分配；
- replay duration 不进入 latency、busy union、critical path 或 overlap。

### 硬件与 gap

- 优先复用 R4 硬件属性，并记录兼容性；
- targeted PMC 只覆盖明确列入计划的缺口；
- L2 hit、stall 和 theoretical occupancy 不冒充实际利用率；
- replay 投影与原始运行采样明确区分；
- 低利用率结论附带指标、阈值、时间和证据来源。

### 并发机会

- 没有 dependency/ready/slack 时不声称确定可并发；
- 模拟重叠不表述为实际收益；
- opportunity 必须说明系统、负载或 kernel/硬件优化动机；
- 实际 speedup 只来自独立对照实验。

### 表达模式完成条件

- 每个 R06–R10 handoff 均包含相互一致的 execution/evidence/coverage/
  authorization 字段；`coverage_target_met=false` 的执行完成态不得显示为证据完成；
- 验收首页离线可打开，并明确列出缺失阈值、dependency adapter、traffic/resource
  model、live sampling 或未授权 batch 对结论的具体影响；

- `auto`：完成有序原生/官方接口尝试；有官方 parse/query PASS 时选择 Perfetto，
  否则必须保留兼容 trace、失败详情和 `CUSTOM FALLBACK` 标识；
- `browser`：仍执行并记录相同尝试，只作为 UI 兼容覆盖，不得冒充 native parse；
- `native`：除 browser 条件外，还必须通过 PFTrace、TrackEvent overlay、严格 merge、
  SQL 和 deep-link 校验；
- 任一模式中，第一层投影组成不证明并发，第二层并发只来自 selective non-replay
  observed 时间区间，R4/PMC 指标只能作为 `replay_projected_step` 属性轨。
- `selected_process_overlap.csv` 与 versioned schema 一致，每个 eligible pair/domain
  有正 segment、显式 zero 或 `interval_unavailable` 记录，并可由 strict interval
  sweep 独立复算。

## 推荐默认路径

```text
Workflow 04 全量估算
  -> Plotly 第一层全过程时间线、延迟 Pareto 与候选排序
  -> selective non-replay process/runtime/queue 采样
  -> 复用 Workflow 01 kernel timeline 和 R4 硬件属性
  -> targeted PMC only when needed
  -> Plotly 第二层多轨 observed 时间线与 gap/并发视图
  -> native 能力存在时追加 PFTrace overlay + Trace Processor SQL
  -> 用 NetworkX 处理有证据的 dependency
  -> coverage/risk review
  -> 按需追加下一小批
```

该路径保留 Workflow 04 的低成本全覆盖价值，同时把昂贵的真实 process trace 和
硬件 replay 集中在最可能贡献端到端性能 gap、资源 gap 和并发机会的时间窗；通用
时间轴、热力图和图算法由开源工具承担，项目代码只实现 Qwen/PRA process 语义、
证据分层、资源 gap 和并发可行性判断。
