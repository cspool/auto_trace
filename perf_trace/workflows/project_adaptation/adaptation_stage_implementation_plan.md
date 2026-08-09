# perf_trace Workflow 01–05 统一适配实施计划

## 产出边界

本目录是唯一迁移控制面。P01–P05 已完成且不重写；P06 是已完成的历史
Workflow 01–04 scheduler。当前 Phase 1 只追加 P07–P12 的定义并更新统一
runner/verifier，不执行任何新 Goal。

## Goal 划分

| 顺序 | Goal | kind | 产出 | 主要依赖 |
| --- | --- | --- | --- | --- |
| 1–5 | P01–P05 | 已提交 source/gap | 01–04 五个 Skills | 保持原合同 |
| 6 | P07 | Workflow-gap | 上游复用、能力探测、候选计划 Skill | P01–P05 |
| 7 | P08 | Workflow-gap | selective non-replay process trace Skill | P02、P03、P07 |
| 8 | P09 | Workflow-gap | R4-first targeted hardware gap Skill | P05、P07、P08 |
| 9 | P10 | Workflow-gap | utilization/concurrency analysis Skill | P01–P05、P07–P09 |
| 10 | P11 | Workflow-gap | Perfetto/Plotly reporting Skill | P01–P05、P07–P10 |
| 11 | P12 | scheduler generation | 01–05 runner + 两个 manifests | 所有十个 Skill Goals |

P06 不复用为新 Goal，避免其既有 handoff、gate 和 runtime outputs 与新合同
混淆。它保留在历史记录中，当前 stage ID 有意从 P05 跳到 P07。

## P01–P05 保留策略

- P01–P04 继续以完整源 Skill 为权威；P05 继续以 Workflow 03 scope 和固定
  hipprof evidence 为权威。
- 五个目标 Skill 的 tree hash、P01–P05 handoff hash、旧 plan/contract hash
  和 canonical state 均被 manifest 固定。
- Phase 1 不改这些 Skill、handoff、gate report、state、run log、旧 scheduler
  或 `core_attribution_pipeline.json`。
- 后续 `--adopt-workflow05-extension` 只在 P01–P06 都是
  COMMITTED/complete/pass 且保护证据未漂移时成立。

## P07–P11 通用协议

每个 Workflow 05 gap Goal：

1. 不附加源 Skill；
2. 只使用 manifest 固定的 Workflow 05 scope 作为规范能力合同；
3. 只使用本阶段 `binding_evidence` 建立项目工具、路径、硬件与 schema 绑定；
4. 相邻 Skills 只定义输入、输出和所有权边界；
5. 未验证绑定必须明确保留并要求 runtime discovery；
6. 只生成 `SKILL.md`、`agents/openai.yaml` 和一个最小 handoff；
7. 不运行模型、GPU、hipprof、PMC、Workflow、dashboard 或优化实验；
8. Goal complete 后由 runner 重哈希 authority/evidence 并运行外部 final gate。

各阶段详细方法、required sections、markers、stop 和 escalation 语义均固定在
manifest 与 `goals/P07.md` 至 `goals/P11.md`。

## P12 协议

P12 消费十个已提交 target Skills，生成且只生成：

```text
perf_trace/scripts/run_perf_trace_01_05.py
perf_trace/manifests/workflow01_05_full_pipeline.json
perf_trace/manifests/workflow05_existing_evidence_pipeline.json
perf_trace/workflows/project_adaptation/artifacts/P12/handoff.json
```

完整分支严格执行：

```text
R01 -> R02 -> R03 -> R04 -> R05 -> R06 -> R07 -> R08 -> R09 -> R10
```

复用分支仅在用户提供兼容 R01–R05 ledger 时执行 R06–R10。两个 manifest 的
runtime binding 只能含目标 Skill identity；runner 必须使用持久 Goal、累计
handoff、fail-stop、`--help` 和 no-Goal `--dry-run`。P12 不执行正式 runtime。

## Runner 状态扩展

统一 runner 保留参考实现的：完整计划先验验证、non-ephemeral thread、paused
bootstrap、Goal-owned continuation、外部 gate、原子 state、fail-stop 和 resume。

显式采用扩展时：

1. 验证 predecessor schema/protocol/plan/contract；
2. 验证 P01–P06 state 和保护产物；
3. 保留 P01–P05 stage records；
4. 将 P06 record 移到 `superseded_scheduler_stages`；
5. 添加 P07–P12 的 NOT_STARTED records；
6. 更新新 plan/contract/protocol 后只从 P07 继续。

## 验证策略

Phase 1 verifier 检查：

- 五个 Workflow 和完整 capability matrix；
- P01–P05 原权威/输出，P07–P11 authority/evidence/unresolved/file-set，P12
  唯一 final scheduler 合同；
- P01–P06 predecessor state、目标 Skill/handoff 和旧 runtime outputs 未漂移；
- P07–P12 目标、handoff、artifact 和新 runtime outputs均不存在；
- runner/verifier AST 与必要编排不变量；
- 不存在 ignored/unsupported/unscheduled 节点。

P07–P11 gate 额外检查 frontmatter、agent metadata、精确两文件集合、required
sections/markers、runtime deferral、authority/evidence hash 和最小 handoff。

P12 gate 检查两个 Skill-only manifest、Python AST、`--help`、两条 branch
`--dry-run`、R01–R10 顺序及 dry-run 零 Goal/零 runtime side effect。

## 本轮允许的验证入口

```bash
python3 perf_trace/workflows/project_adaptation/scripts/verify_adaptation_output.py \
  --project-root /public/home/tangyu408/Qwen_DCU_Worker_0 \
  --control-plane-extension

python3 perf_trace/workflows/project_adaptation/scripts/adapt_perf_trace.py \
  run \
  --project-root /public/home/tangyu408/Qwen_DCU_Worker_0 \
  --dry-run
```

不得运行 `doctor`、真实 `run`、`resume`、`reactivate` 或任何 Goal/Thread API。
