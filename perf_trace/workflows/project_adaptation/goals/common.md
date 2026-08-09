# perf_trace Workflow 01–05 适配通用 Goal 合同

## 适用阶段

- P01–P04：`source_skill_text_alignment`，完整源 Skill 是唯一规范能力来源。
- P05：已提交 Workflow 03 `workflow_gap_skill_generation`。
- P07–P11：Workflow 05 强制 `workflow_gap_skill_generation`。
- P12：唯一当前 `scheduler_generation`。
- P06：只读历史 scheduler Goal，不在当前 stage graph 中，不得重新执行。

## 共同禁止事项

任何迁移 Goal 均不得：

- 执行模型、GPU、profiler、PMC、正式 Workflow、dashboard 或优化实验；
- 修改源 Skill、其他目标 Skill、manifest、runner、verifier、canonical state、
  历史 P06 产物或其他 stage 输出；
- 启动或管理后继 Goal、Codex 进程或 agent；
- 将归档/示例 evidence 声称为本轮新测量；
- 生成 goal-spec、迁移报告、Workflow 摘要或未声明文件；
- 猜测工具、路径、schema、counter、依赖或硬件常量；
- 把 estimated、inferred、replay-projected 或 heuristic 值提升为 observed。

## P01–P04 源 Skill 对齐

必须完整镜像声明的源相对文件集合，保留方法、步骤顺序、I/O、证据边界、
validation、failure、stop 与 completion 条件。只允许对齐经项目证据确认的
项目、模型、runtime、硬件、路径、模块、命令、schema、示例、frontmatter
和 agent metadata。Workflow 仅定义角色、依赖和 handoff，不向目标 Skill
增加方法。

源 Skill 适配 handoff 仅含：`stage`、`status`、`source_skill`、
`output_skill`、`outputs`、`validation`、`completed_at`。

## P05 边界

P05 继续遵循 `goals/P05.md`。Workflow 03 scope 是硬件能力权威，固定的当前
`pra2026-bh408/scripts/perf_trace` 文件是具体绑定证据；non-replay timing 仍归 P02/P03。其既有
目标 Skill 和 handoff 已提交，本扩展不得改写。

## P07–P11 Workflow 05 gap 生成

每个阶段必须完整读取：

1. 本合同与当前 Goal；
2. manifest 固定的 Workflow 05 authority scope；
3. 本阶段完整 `binding_evidence`；
4. 已提交依赖 handoff 和 boundary Skills，仅用于接口边界；
5. `unresolved_bindings`、required sections/markers 和 final gate。

只生成 manifest 声明的 `SKILL.md`、`agents/openai.yaml` 和 handoff。具体命令
或 schema 必须可追溯到本阶段 evidence；未证实的绑定必须写成明确的 runtime
discovery/stop/degraded 条件，不能删除能力。

Workflow-gap handoff 顶层字段严格为：

- `stage`
- `status`
- `authority_type`
- `workflow_authority`
- `output_skill`
- `outputs`
- `validation`
- `completed_at`

其中 `authority_type=workflow_gap`，`workflow_authority` 必须等于 manifest 中
完整 authority 对象，`outputs` 只能是当前目标 Skill 目录。

## P12 scheduler generation

P12 不生成或修改 Skill。它必须消费 P01–P05、P07–P11 的 committed target
Skills 和 handoff，按 manifest 生成：

- `run_perf_trace_01_05.py`；
- `workflow01_05_full_pipeline.json`；
- `workflow05_existing_evidence_pipeline.json`；
- P12 最小 handoff。

完整分支必须是 R01→R10；复用分支必须要求用户提供兼容 R01–R05 cumulative
handoff ledger 后才运行 R06→R10。每个 runtime Goal input 只能由 target
Skill、用户参数和累计 ledger 构成。runner 必须使用 `ephemeral=false`、只在
`complete` 后继续、提供 `--help` 与无 Goal `--dry-run`，且不得执行正式分支。

## 完成与外部 gate

Goal 只在声明文件、最小 handoff 和允许的静态检查完成后标记 `complete`。
runner 会在提交 stage 前独立重哈希合同/authority/evidence，重新发现目标
Skill 并执行 final gate。任何 blocked、paused、limited、timeout、hash drift、
handoff mismatch 或 gate failure 都必须停止整条串行链。
