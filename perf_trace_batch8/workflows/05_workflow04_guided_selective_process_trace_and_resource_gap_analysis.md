# 05 Process 分布与硬件资源窗口工作流

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
