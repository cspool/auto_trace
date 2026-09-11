# 05 Process 分布与硬件资源窗口工作流

## 在串行链条中的位置

w01–w05 **不是五个可独立执行的工作流，而是一条串行方法链**，共同覆盖
R01–R10，在**同一 lineage 内按序执行一次**：

| 工作流 | 覆盖 Goal |
|---|---|
| w01 | R01 |
| w02 | R02、R03 |
| w03 | R04 |
| w04 | R05 |
| w05 | R06–R10 |

本文档是 **w05，覆盖 R06–R10**。据此有三条不可混淆的约束：

- **不存在"只执行 w05"**：R06–R10 的 admission 要求完整有序的 R01–R05 前驱
  handoff/ledger，缺任一前驱即不得启动。
- **不存在"先跑 R01–R04，再从 w01 重跑一遍 R01–R10"**：链条只走一次；
  中断恢复是从首个未完成 Goal 继续，不回到链条起点重跑，也不复用不完整产物。
- **下游只消费上游产物，不重新证明其结论**：例如 w03 不重新证明 w02 的
  process timing attribution，w05 不重新推导 R05 的类型映射与分母。

一次 lineage 内可能包含**多轮模型采集**（如 R07 的 trace 轮次与 R08 的各计数族
轮次是不同的 run），这属于同一条链条内不同 Goal 的采集轮次，
**不是重复执行工作流**。

## 目标、证据层与执行模式

本工作流交付两个目的不同、来源连贯的视图：

| 视图 | 回答的问题 | 默认显示范围 |
|---|---|---|
| 高延迟 Process 分布 | 长耗时类型/实例在采集时间内如何执行 | 入选类型的全部真实 Process 区间，按堆形成梯形 |
| 并发/资源窗口 | 哪些时段有可用且已关联的资源指标 | 成功关联硬件指标的窗口，多个资源同时显示 |

完整证据归档、R07 目标覆盖、R08 硬件覆盖和当前可见子集分别记账。
资源图不需要复制全过程来补空白；资源缺失也不能从高延迟图删除真实 Process。
用户看到的类型阈值、分堆、时间轴及资源方法统一采用
[Process/resource contract](../skills/qwen-dcu-workflow05-trace-visualization-reporting/references/process-resource-contract.md)。

执行前选择模式，不能混用完成声明：

1. **Fresh 采集**：使用 `workflow01-10-fresh-e2e`，从 R01 到 R10 串行执行同一
   run/lineage；不可引入其他 runtime 的测量作为 fresh 前驱。
2. **已有证据展示/恢复**：只读同一已接受 lineage 的归档与源表，恢复已有
   计数/耗时，另写资源侧表和可视化；不调用模型、设备或 profiler，不改写
   已封存 handoff，不宣称 `formal_r10_regeneration=true`。如果数据不存在，
   保留不可用状态；更改显示目标本身不授权补采。

Batch8 使用 hash-pinned trace profile 的完整 DP2 拓扑：8 个 measured requests、
DP rank 0/1 对应物理 DCU 0/1，TP=1、DP=2、world size=2。stage 串行不等于
单卡执行；不得将单 rank 或单卡证据提升为完整 DP2 采集。固定模型、请求
选择、输入哈希、token 限制和运行时由该 profile 与 scheduler bootstrap 提供。

Fresh 执行或运行中断恢复前，按阶段读取
[Batch8 运行约束](references/batch8_runtime_operations.md)。

配置见 [`configs/trace_targets/batch8_dual_dcu_dp2.json`](../configs/trace_targets/batch8_dual_dcu_dp2.json)。代码/skill/Workflow 更新后，新的执行使用当前
manifest 的技能文件与树哈希；已运行或已封存 ledger 的旧哈希不可被回写。
需要恢复旧 runtime 时走其原有版本绑定与显式修订记录，而不是伪装成相同输入。

## Fresh 串行阶段及交接

| Goal | Skill | 生产并交给下游的证据 |
|---|---|---|
| R01 | `qwen-dcu-same-input-layer-wise-workflow` | SAME_INPUT 合同、layer 时间分母 |
| R02 | `qwen-dcu-fx-process-nvtx-instrumentation` | Process/fragment 语义、准确标记和所属层 |
| R03 | `qwen-dcu-process-performance-breakdown` | launch-owned kernel 归属与 process 归因 |
| R04 | `qwen-dcu-process-gpu-hardware-trace` | 当前 run 的代表性硬件证据与能力 |
| R05 | `qwen-dcu-segmented-process-attribution` | 完整分母、类型映射、未解决范围 |
| R06 | `qwen-dcu-workflow05-evidence-planning` | 冻结 R07 目标与有界 R08 计划、展示能力 |
| R07 | `qwen-dcu-workflow05-full-request-process-trace` | observed 区间、严格 kernel 归属、原始采样与缺口 |
| R08 | `qwen-dcu-workflow05-targeted-hardware-gap-analysis` | 同次计数/耗时、能力、资源公式与覆盖 |
| R09 | `qwen-dcu-workflow05-utilization-concurrency-analysis` | 十二张完整表、资源侧表、分堆计划与分母 |
| R10 | `qwen-dcu-workflow05-trace-visualization-reporting` | 两类分析视图、完整证据导出与独立验收 |

scheduler 独占正式 Goal 创建，每次仅运行一个阶段。启动前验证完整有序前驱
handoff/ledger 的路径、lineage 与 SHA-256；业务输出只写分配的 artifact root，
handoff 只写指定位置，且不纳入业务 manifest。runtime skill 不创建嵌套 Goal。
工具修订记录来源差异；输入语义、设备拓扑或输出等价性改变时不能拼接 lineage。

Fresh 阶段推进仍需分别通过 `execution_status`、`evidence_status`、
`coverage_target_met` 和 handoff 哈希检查。`status=complete` 不单独证明覆盖。
缺失某项可选硬件指标可以与已声明范围的完整处理共存；缺失必需目标不能。

## R06：先冻结覆盖范围，再规划展示

R06 是 CPU-only 规划。它完整枚举 declared Process/fragment targets，核对容量，
单独预算昂贵 PMC families。不能把显示用的 10% 阈值套到 R07 采集范围，也不能
为了资源图没有空白而自动扩大 R08。保留未选择 family 与 capability 状态。

冻结 request/rank/device/phase/step 的 trace scope。完成请求不等于追踪每个 token；
任何首个 prefill/decode 或代表阶段限制必须事先写入范围，不能在缺数据后改口径。
采集完整性按该范围验收，展示完整性按源记录守恒验收。

验证 R10 builder 能实现当前双视图 profile。仓库里的 retained-schema adapter
不等于新的 fresh R09-table renderer；若绑定工具尚未支持当前 profile，先报告
能力缺项并实现/验证对应入口，不能运行旧图后宣称新目标已验收。

## R07：只建立真实 observed 时间与采样证据

保存 request/forward/layer/Process/fragment、HIP runtime、strict-owned HIPOPS
kernel 与 queue/stream、双时钟 anchors 和真实 SE samples。R07 是唯一 observed
schedule clock；嵌套范围用唯一最深归属，不重复计算 kernel。

所有慢调用、采样缺口、对齐不确定度均保留。有效窗口均值要求至少三个合格
样本及对应 gap/alignment 门槛；缺失均值不能填零。完整 Process trace、live
mean 可用率和资源计数覆盖率是不同分母，必须分别交接。

## R08：保留可重算的硬件资源证据

只按已授权的 bounded plan 做重放，并完整保留每个 physical dispatch 的原始
计数、同次 native begin/end、counter mode、文件哈希、设备/请求与精确 R07
归属、observed/replay shape。不能只保存 family 平均值后丢掉耗时来源。

带宽 = 原生字节 / 同次计数耗时；参考百分比还需注明来源的适用带宽基准。
读写模式分别计算，不相加为同时观测。重放耗时不能进入 R07 latency/overlap。
R08 对已选择目标逐项给出 collected/no-kernel/unavailable/failed，未选择的
目标记为未采集，不要求它们在资源图上占据可见区域。

L2 命中率、请求速率、L2 投影吞吐量和 DRAM 带宽分别命名；不能把 L2 命中率
称为带宽利用率，也不能把 HBM 基准当 L2 峰值。形状不匹配、计数/耗时无效
或未验证的分母保留明确原因。

## R09：完整分析与显示计划分离

保留十二张完整 normalized tables：request/process/kernel timeline、live samples、
process live utilization、kernel/queue concurrency、launch gaps、high latency、
dependency、traffic/resource attachment、opportunities。每表锁定 schema、row count、
源/产物 SHA-256、lineage 和实际范围。并发扫描只用 R07；原始 high-latency
分类与并列项不能被可视化阈值覆盖。

派生侧表给出：全部 Process 累计时长分母；类型严格超过10%的选择；每类型5堆
的完整成员；按堆累计时长全局排序；各资源可用状态、来源、单位、公式和覆盖。
读写 reference 用同方向唯一 dispatch 的字节总和除以各自重放耗时总和，只代表
所选 kernel。缺失计数/形状不能通过借其他实例或父过程均值补齐。

## R10：两个视图按不同可见范围交付

高延迟图使用上游分堆计划，保留真实 Process 起止线并用梯形组织成员。
资源图沿用同一原始排名，默认仅保留成功关联非计算硬件指标的实例和非空堆。
每实例同时显示可用计算、读写带宽、L2 指标；高度按声明单位的数值连续缩放，
不再分四档或在每次切换时只显示一个资源。短采样窗口的 ε 是非实测占位，
数值仍为 null；其他缺失项隐藏但保留在覆盖率与详情。

两页都沿用原始十段时间边界。共享轴可以 `//` 折叠；只有资源图默认删除所有
可见轨道有效窗口并集之外的显示宽度，用 `»` 标出跳过区间并保留确切端点。
不删除其他可见轨道有数据的时间，也不据此声称 GPU 空闲。允许恢复完整数据。

完整 E2E/lossless 页面、原始表和完整 Perfetto 是独立证据资产，事件数仍遵循
`request + process + 2 × kernel`，两种 kernel 轨道不重复计时。分析页的 >10%
筛选、隐藏空堆和跳过区间不能被宣称为全量无损时间轴；它们记录可见范围并
引用完整证据。所有代码/数据离线可用，禁止手改生成 HTML。

正式 R10 完整包保留已有逻辑输出 `offline_acceptance_manifest` 和
`source_lineage`，并封存完整证据导出、两类分析页、分堆/资源/覆盖/遗漏侧表及
独立审计。公开视图仍只有一个入口；不要求每个资源窗口都出现全部设备或请求。

## 两个视图各自需要什么采集

本节是 20260910 谱系在本包 DP2 拓扑上的实测结论（8 measured requests、DP rank 0/1 → 物理 DCU 0/1），
属于上表 w05 覆盖的 R06–R08 规划依据，**不是独立入口**。它回答"要出这两个页面，必须采什么、怎么采、
哪里会踩坑"，用于在 R06 规划阶段就把范围定对，而不是采完才发现视图缺必需证据。

### 与本文档原有描述的差异

R08 要求"完整保留每个 physical dispatch 的……精确 R07 归属"，但没有说**如何**取得
这种归属。20260910 的第一次实现按 forward 步门控计数器，结果是一步含全部层、
且该后端记录 `Kernel correlation IDs are not assumed valid`，**逐 Process 归属不成立**，
R10 的资源页因此无法按每实例显示。补上的方法是把计数过滤器收窄到单个 Process 区间。
同时 R07 关于"至少三个合格样本"的窗口均值门槛隐含了"可以采到足够样本"，
但 live 采样器的窗口宽度是驱动调用延迟、结构性地粗于 Process 实例，
这一点决定了资源页的逐实例要求**只能**由门控 PMC 满足。以下两节把这两件事写实。

### 高延迟 Process 分布页：不需要计数器

`HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html` 只消费 R07 的 observed 证据：
每个 Process 实例的真实起止（共同单调时钟）、request/rank/device/phase/layer 身份、
ROCtx Process 区间与双时钟 anchors。类型分母、10% 阈值、五堆、全局排序、梯形包含
与十段折叠全部由这些字段决定，与任何硬件计数无关。

因此该页由 **R07 的一次 `--mode trace`（无 PMC）采集**即可支撑；这是链条内的
一个 Goal，不是独立入口。在同一轮次上附加 PMC 只会改变提交节奏，
让该页的时长失去与默认图轮次对照的可比性。

### 并发/资源页：只有 Process 区间门控的 PMC 能满足

该页的默认筛选要求每实例至少一个**有效且精确关联的非计算指标**。可选来源与实测结论：

| 证据来源 | 测量窗口 | 能否逐实例精确关联 |
|---|---|---|
| live SE 活跃CU | 约 0.34 ms | 属计算类，不满足"非计算"要求 |
| live DF 读/写 | 约 14.8 ms | 否——窗口宽度即驱动调用延迟 |
| live CU / wave | 约 20.6 ms | 属计算类；查询窗口由参数给定 |
| 步门控 PMC | 整个 forward 步 | 否——一步含全部层，correlation ID 不可信 |
| Process 区间门控 PMC | 单个 Process 区间 | 是 |

live 采样器的窗口是 API 调用本身的耗时：`collect_live_resources.py` 中
`begin/end_monotonic_ns` 括住的就是那一次 `rsmi_*` 调用，`--period-ms` 只在调用快于
周期时才 sleep。DF 比 Process 实例（逐层 0.37 ms、forward 步 2.24 ms）粗数倍至数十倍，
**调小周期不会让它变细**。按"测量窗口完整落在实例区间内"的严格判据统计，
live DF 的逐实例合格率在本谱系为 0.001%–0.36%，不足以支撑该页。

结论：要交付并发/资源页，R06 的 bounded plan 里就必须安排 Process 区间门控的
PMC 采集，**每个计数族一轮**（cache / read / write）。这些轮次属于**同一 lineage 内
R08 的采集**，与 R07 的 trace 轮次是不同的 run 但同属一条链条——不要理解成
重复执行工作流，也不要指望一次采集同时满足两页。

### 如何采集

Process 门控由 `fresh_counter_gate(active)` 实现。它是 rocprofiler 过滤器区间的开关，
"step gate"只是**调用点**位于步边界，粒度并未写死；把开关移入 `push`/`pop`
（`kind=='process'` 且命中选择器）即可让窗口只覆盖一个 Process 实例。

~~~text
FRESH_PMC_PROCESS_GATE=1
FRESH_PMC_PROCESS_TYPES=<严格超过10%的类型，逗号分隔>
FRESH_PMC_PROCESS_LAYERS=<显式层列表>          # 优先于 stride
FRESH_PMC_PROCESS_LAYER_STRIDE=<仅作回退>

capture_run.py --mode hierarchy --counter-group {cache|read|write} --process-gate
~~~

前提与代价：

- **必须是 PIECEWISE/NONE 调度**（`FRESH_LAYER_MARKERS=1`）。FULL graph 回放绕过
  Python Process 标记边界，门控无从下手。
- 门控调用开销实测中位 7.7 µs、最大 33.5 µs，可忽略；但 PMC 本身改变提交节奏，
  门控轮次的时长**不能**与未插桩基线相减当作优化收益。
- 有界计划：选中步 × 超过 10% 的类型 × 显式层列表。本谱系一轮为 1,728 个门控窗口、
  约 12,400–13,400 条计数行，量级合适。

先用**不加载模型**的探针验证门控粒度，再上真实采集。`pmc_step_gate/process_gate_probe.cpp`
在同一发射序列内只夹住一个子段：同步与异步两种模式都应恰好得到该子段的计数、
零泄漏、已知载荷回收偏差在 0.15% 以内；结论落在 `PROCESS_GATE_VALIDATION.json`。

### 采集与分析的坑

1. **选层不能用 stride。** 混合架构下 full_attention 可能落在固定同余类上
   （本谱系模型为层 3,7,…,63，即 3 mod 4），任何整除 4 的 stride 都只命中
   linear_attention 层，**静默漏掉** `kv_cache_attention` 这个占时长 17.9% 的类型。
   用显式层列表，并逐一核对入选类型都被覆盖。
2. **门控在 dispatch 提交时刻生效，不在执行时刻。** 计数行可能在门关闭后才执行
   （本谱系一轮 418/13,400）。归属若按"执行时间落在窗口内"来 join 会静默丢弃它们；
   正确做法是按窗口顺序归属，并把"归属期间已有更晚窗口开启"的行标为 ambiguous
   而不强行分配。
3. **空门控窗口是正常的。** 一个 Process 可能没有可计数的 dispatch。
   `audit_hierarchy` 假设"每个选中门控内至少有一个计数起点"——该假设在步门控下成立、
   在 Process 门控下不成立，会给出 `PASS_WITH_GATE_BOUNDARY_EXCEPTIONS`
   （本谱系 12/1,728）。必须逐条确认这些例外都是空窗而**不是**错误归属，再决定接受。
4. **`decode == 1023` 只在无抢占时成立。** KV 压力下请求被抢占重算，恢复后发射 token
   的步骤会归类为 mixed/prefill，于是 decode < 1023 而 completion tokens 仍为 1024。
   验收断言应改为 `prefill + decode == 该请求出现的 forward 数`，
   并把 `1024 - decode` 记为在 prefill 归类步骤中发射的 token 数。
5. **带宽分母有两个，必须分别标注。** 契约 §3 的带宽口径是
   `bytes / 这些 dispatch 自身测量时长之和`。若改用 Process 观测区间作分母，
   得到的是"该 Process 期间的平均流量密度"（区间内含未计数空隙），数值必然更低，
   **它不是带宽**。两者可并列展示，但不能混称。
6. **逐实例合格性判据用"包含"而非"重叠"。** 重叠判据会把一个覆盖数十个实例的粗窗口
   算成每个实例都合格，得出虚高覆盖率。正确判据是该指标的测量窗口
   **完整落在**实例区间内。
7. **L2 读可以超过在案的同卡混合 L2 参考。** 本谱系实测 L2 读约 2,059 GB/s，
   高于混合读写参考约 1.68 TB/s。该参考是混合实测值、不是额定峰值，
   纯读超过它属正常，不要据此"修正"数据，也不要换算成满载百分比。
8. **实现层面两个已知陷阱。** 逐实例查询若对每个实例线性扫描采样表即为 O(n·m)
   （28 万实例 × 2 万样本约 59 亿次迭代，单轮可卡半小时），必须排序加二分索引。
   生成内联 JS 时多层转义极易把换行转义写成真实换行而使整页失效，
   页面审计必须检查 `pageerror` 与实际渲染字符数，
   否则会把语法错误误报成"切段不重绘"之类的表象。

## 已有证据的 CPU-only 恢复与重建

按[执行指南](../../perf_trace/scripts/process_pile_assets/README.md)恢复归档并生成当前双视图。此路径读取已接受源文件，
对恢复成员校验哈希，重新计算可验证资源侧表，再生成视图和浏览器审计。
输出 `GROUPS.json`、`RESOURCE_COVERAGE.json`、`BUILD_MANIFEST.json` 与两类页面；
它不重写原始 twelve-table analysis、完整 Perfetto 或历史 runtime handoff。

当前实例：单 batch 的 Process 捕获有29次 forward；Batch8 的保留样例只含每个
请求首个 prefill/decode 的细粒度 Process。它们不是未来采集范围的固定模板。
页面如实呈现各自 scope；已接受旧数据不因缺硬件计数被伪装为完整资源采集。

## 验收与版本推进

- 完整源范围、输入哈希、kernel 归属和原始分类守恒。
- 类型分母、严格阈值、五堆成员与全局顺序可独立重算。
- 梯形包含所有可见真实成员线，横轴不按组独立归零。
- 资源同时显示，数值/单位/高度一致，0/null/ε 严格区分。
- 默认窗口确有硬件关联；省略区间与有效窗口并集不相交。
- 空堆保留原排名，缺数据段可跳转，恢复与精确 ns 操作有效。
- 完整证据与筛选视图分别声明 completeness，离线浏览器无外部请求。
- Fresh 完成按当前 scheduler contract 验证；retained 审计不伪造 fresh 状态。

修改活动 skill 后同步更新当前 manifest 的 skill file/tree hashes；已封存
adaptation/runtime 的版本回执保持原字节。提交说明必须区分文档/工具验证与
实际执行过的采集阶段。本次 profile 更新不自动启动采集。
