# perf_trace Workflow 01–05 完整能力迁移合同

## 目标与当前边界

本目录是 `perf_trace/workflows/01` 至 `05` 的唯一迁移控制面。Workflow 05
不是独立项目：它消费 Workflow 01–04 的时间、process、硬件和全层估算证据，
再生成面向性能 gap 的选择性采样、分析和表达能力。

当前调用只更新 Phase 1 控制面并做静态验证与 `run --dry-run`。不得启动
app-server、Thread、Goal、模型、GPU、profiler 或正式 Workflow；不得创建
P07–P12 handoff、目标 Skill、新 scheduler、runtime state 或 gate report。

P01–P05 已在前一轮迁移中提交，其五个目标 Skill、handoff 和运行时产物保持
不变。历史 P06 scheduler 及其产物保留作审计证据，但 P06 不再是当前计划的
最终阶段；新的唯一最终 scheduler-generation Goal 是 P12。

## 权威规则

- P01–P04：各自完整源 Skill 是唯一规范能力来源，Workflow 只定义角色、顺序
  和 handoff 边界。
- P05：Workflow 03 的硬件 replay/严格连接/报告 scope 是规范能力来源；固定
  `pra2026-bh408/scripts/perf_trace` 文件仅提供当前 Qwen/DCU/hipprof 绑定证据。
- P07–P11：Workflow 05 没有声明覆盖这些新增能力的参考 Skill，因此每项都是
  强制 `workflow_gap_skill_generation`。manifest 中精确的 Workflow 05 scope
  是能力权威，逐阶段 `binding_evidence` 是具体路径、工具和 schema 的唯一
  绑定权威。
- 已提交 P01–P05 Skills 以及两个 `workload_profile` Skills 对 P07–P11 只定义
  上游接口或边界，不得被当成新增能力的规范来源。
- P12 没有源 Skill、也不生成 Skill；它只消费全部十个 committed target
  Skills 并生成运行时 runner 与分支 manifest。

未知的 Perfetto、Trace Processor、选择性 hipprof、PMC 字段、依赖恢复、HTA
adapter 等绑定必须保留为 runtime discovery。不得猜测命令、虚构 schema，
也不得因此忽略 Workflow 能力。

## 能力覆盖矩阵

| Workflow 能力 | 覆盖类型 | 迁移 Goal / 目标 Skill |
| --- | --- | --- |
| 01 全层 SAME_INPUT 时间与分母 | source Skill | P01 / `qwen-dcu-same-input-layer-wise-workflow` |
| 02 process marker 与 instrumentation | source Skill | P02 / `qwen-dcu-fx-process-nvtx-instrumentation` |
| 02 process 性能分解 | source Skill | P03 / `qwen-dcu-process-performance-breakdown` |
| 03 process/non-replay timing 边界 | P02/P03 接口 | P02、P03 |
| 03 GPU 硬件 replay、严格 join 与报告 | Workflow gap | P05 / `qwen-dcu-process-gpu-hardware-trace` |
| 04 全 layer-input segmented process 估算 | source Skill | P04 / `qwen-dcu-segmented-process-attribution` |
| 05 上游复用、能力探测、全局索引与候选计划 | Workflow gap | P07 / `qwen-dcu-workflow05-evidence-planning` |
| 05 选择性 non-replay process trace | Workflow gap | P08 / `qwen-dcu-workflow05-selective-process-trace` |
| 05 R4-first 定向硬件与长 process gap | Workflow gap | P09 / `qwen-dcu-workflow05-targeted-hardware-gap-analysis` |
| 05 低利用率区间、依赖和并发机会 | Workflow gap | P10 / `qwen-dcu-workflow05-utilization-concurrency-analysis` |
| 05 Perfetto/Plotly 联动 trace 与报告 | Workflow gap | P11 / `qwen-dcu-workflow05-trace-visualization-reporting` |
| 01–05 运行时串行编排 | scheduler generation | P12 / runner + 两个 manifests |

不得出现 ignored、unsupported、unscheduled 或
`no_authoritative_target_skill` 能力节点。

## 当前迁移 Goal 图

显式总顺序：

```text
P01 -> P02 -> P03 -> P04 -> P05
    -> P07 -> P08 -> P09 -> P10 -> P11 -> P12
```

P06 被有意保留为历史编号，不在当前 `stages` 中。逻辑依赖由 manifest 固定：

- P03 依赖 P02；P04 依赖 P01、P03；P05 依赖 P02、P03；
- P07 消费全部 P01–P05 上游能力；
- P08 消费 P02、P03、P07；
- P09 消费 P05、P07、P08；
- P10 消费 P01–P05、P07–P09；
- P11 消费 P01–P05、P07–P10；
- P12 依赖所有十个 Skill-producing Goal。

迁移 Goal 顺序用于保证 Skill/handoff 可用性；运行时 Workflow 的规范全链为
R01 至 R10。

## Workflow 05 共同证据边界

- 同一运行必须共享一个 SAME_INPUT 合同。
- Workflow 04/R05 是全 layer-input 的估算与证据索引，不是 observed process
  timeline。
- 延迟、busy、overlap、critical path 以 non-replay observed trace 为准。
- R4/PMC replay 只能提供硬件属性，`replay_projected` 不得替代 latency。
- `observed`、`inferred`、`estimate`、`replay_projected`、`heuristic`、
  `unavailable` 必须始终分离。
- 无 dependency/ready/slack/resource coexistence 证据时，只能列 concurrency
  candidate，不能声称可并发或实际加速。
- 优先复用 01–04 数据并选择性补证；只有记录的 coverage/escalation 条件触发
  后才允许扩大采样。

## 运行时拓扑

P12 必须生成两个分支。

完整顺序分支 `workflow01-05-full`：

```text
R01 -> R02 -> R03 -> R04 -> R05 -> R06 -> R07 -> R08 -> R09 -> R10
```

其中 R01–R05 分别绑定 P01–P05 的五个现有 Skill，R06–R10 分别绑定
P07–P11 的五个 Workflow 05 Skill。该分支证明 Workflow 05 是 01–04 的后续，
而不是独立流程。

低成本分支 `workflow05-existing-evidence` 只执行 R06–R10，但用户必须显式
提供兼容且完成的 R01–R05 cumulative runtime handoff ledger；调度器不得静默
重跑或修改 01–04。

每个运行 Goal 只能组合对应 target Skill、用户参数和累计前序 handoff
ledger；使用 non-ephemeral thread，仅 `complete` 后继续。

## 已完成状态的 Workflow 05 扩展

manifest 的 `workflow05_extension` 固定当前 COMPLETE P01–P06 predecessor
state、plan 和 contract hash：

- P01–P05 必须保持 COMMITTED/complete/pass 并验证目标 Skill/handoff；
- 历史 P06 必须保持 COMMITTED/complete/pass，并移入状态中的 superseded
  scheduler 记录；
- 只追加 P07–P12，不重跑 P01–P05；
- 新目标 Skill、P07–P12 handoff 和新 runtime outputs 必须在采用扩展前不存在。

后续 Phase 2 的显式入口是：

```bash
python3 perf_trace/workflows/project_adaptation/scripts/adapt_perf_trace.py \
  resume \
  --project-root /public/home/tangyu408/Qwen_DCU_Worker_0 \
  --adopt-workflow05-extension
```

本轮不得执行该命令。

## Phase 1 完成条件

只允许：manifest/合同/Goal 静态检查、Python AST、两个脚本的 `--help`、
runner `run --dry-run`，以及验证当前 P01–P06 历史状态和 P07–P12 零产出。
通过后只能声明“统一 adaptation control plane 已生成并 dry-run 验证”，不能
声明 Workflow 05 Skill 迁移、scheduler 生成或性能分析已经完成。
