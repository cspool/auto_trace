# Workload Profile Workflow-to-Skill 迁移合同

## 阶段边界

本控制面只执行迁移 Phase 1：

```text
参考 Workflow + 参考 Skill + 当前项目绑定证据
  -> source-Skill 文本对齐 Goal
  -> Workflow-gap Skill 生成 Goal
  -> 最终 scheduler-generation Goal
  -> 静态检查与 run --dry-run
  -> 停止
```

本阶段不得创建或激活 Codex Goal，不得执行迁移，不得改写目标 Skill，不得
生成运行时 scheduler/manifest，也不得运行 profiler、模型、Dispatch、FX、
重建、可视化或审计 Workflow。

Phase 2 只有在后续明确请求时才允许执行本控制面，生成目标 Skill 和最终
运行时 scheduler。Phase 3 还需要另一条明确授权，才允许执行生成的运行时
scheduler。

## Workflow 清单与覆盖判定

必须递归枚举 `workload_profile/workflows/` 下、但不属于
`project_adaptation/` 的全部 Markdown。`README.md`、
`draft_prompt.md` 和
`workflow_goal_decomposition_and_project_adaptation.md` 是控制面说明或历史
设计记录；它们仍须进入 inventory，但不替代 00–04.2 运行 Workflow 的能力
权威。

覆盖是语义覆盖，不是名字匹配：

- 参考 Skill 真正包含的能力，由该参考 Skill 独占规范；
- Workflow 只确定该能力的角色、边界、依赖、分支和 handoff；
- Workflow 中出现但任何参考 Skill 都不包含的采集、重建、分析、校验或
  报告能力，必须生成独立 Workflow-gap Skill；
- 不得把 gap 塞入相邻参考 Skill 的文本对齐 Goal；
- 不得把 gap 标记为 ignored、unsupported 或 unscheduled。

## Source-Skill 文本对齐

每个 `source_skill_text_alignment` Goal 必须：

1. 完整读取唯一参考 Skill 及其直接资源；
2. 保留声明的源文件集合、章节、方法、顺序、输入输出、证据边界、验证、
   失败、停止和完成条件；
3. 只对齐项目名、模型、运行时、硬件、路径、模块、命令、schema、artifact、
   示例、frontmatter 和 agent metadata；
4. 无法确认的具体绑定保留能力要求并延迟到运行时发现；
5. 不复制 Workflow 方法，不实现正式业务 Workflow，不声称未执行的验证；
6. 只生成 manifest 声明的目标 Skill 文件和最小迁移 handoff。

## 强制 Workflow-gap Skill

本控制面必须生成四个 gap Skill：

1. `qwen-dcu-workload-profile-contract-audit`
   - 权威：`00_overview.md` 中的 run mode、canonical run contract、event
     keys、event conservation、evidence boundaries 和 shared completion
     checks。
2. `qwen-dcu-dispatch-visualization-coverage-audit`
   - 权威：`03_1_04_1_dispatch_branch.md` 中未被参考 Skill 覆盖的手工
     character visualization、跨事件覆盖相等和 completion record。
3. `qwen-dcu-fx-process-reconstruction`
   - 权威：`03_2_04_2_fx_branch.md` 的 `## 2. Rule Reconstruction`，包括
     输入 gate、禁止覆盖、递归 rule reconstruction、逐事件结果校验和
     rule-derived evidence boundary。
4. `qwen-dcu-fx-coverage-audit`
   - 权威：`03_2_04_2_fx_branch.md` 的 `## 4. Final Coverage Audit`、
     `## Manual Completion Record` 及对应完成检查。

每个 gap Goal 只能使用 manifest 固定的 Workflow scope 作为能力规范，并
只能使用固定的 binding-evidence 文件确定当前 Qwen3.5/vLLM/ROCm/DCU
路径、工具、命令和 schema。空 evidence 集或尚未确认的绑定必须显式保留为
runtime discovery，不能删掉能力。

Gap Skill 的文件集合严格为：

```text
SKILL.md
agents/openai.yaml
```

不得把当前项目业务工具、历史运行 artifact、Workflow 副本、goal-spec 或
迁移报告复制进 Skill 目录。

## 迁移 handoff

每个 Skill-producing Goal 写一个最小 handoff：

```json
{
  "schema_version": 1,
  "stage_id": "<stage>",
  "status": "complete",
  "outputs": {
    "skill": "workload_profile/skills/<target-skill>"
  }
}
```

Workflow-gap handoff 还必须声明 `authority_type=workflow_gap` 和 manifest
固定的 `workflow_authority`；source-Skill handoff 不得伪装成 runtime
handoff。所有正式 runtime handoff 由后续运行 Goal 产生。

## 最终 scheduler-generation Goal

最终 A07 必须依赖所有十个 Skill-producing Goal，消费其已提交目标 Skill
和 handoff，并生成：

```text
workload_profile/scripts/run_workload_profile.py
workload_profile/manifests/dispatch_pipeline.json
workload_profile/manifests/fx_pipeline.json
```

运行链必须为：

```text
Dispatch:
  R00 -> R01 -> R02 -> R031 -> R041 -> R051

FX:
  R00 -> R01 -> R02 -> R032 -> R033 -> R042 -> R052
```

每个 runtime stage 只能绑定一个目标 Skill。运行 Goal 输入只能由目标
Skill、用户参数和累计前序 runtime handoff ledger 组成。scheduler 必须为
每阶段创建持久 thread 上的独立 Goal，仅在 `complete` 后前进，并在任何
其他终态或不一致状态停止。

A07 只生成和 dry-run 校验 scheduler，不执行运行时 Workflow。

## Phase-1 完成条件

只有以下条件全部满足，才可称为“adaptation control plane generated and
dry-run validated”：

- 全部 Workflow 文档已进入 inventory；
- 每个运行能力恰好映射到 source-backed、source-boundary 或 Workflow-gap
  stage；
- 四个 gap Goal 均固定 authority、binding evidence、未决绑定、目标文件
  集、handoff 和 gate；
- A07 是唯一最终 scheduler-generation Goal，并消费全部目标 Skill；
- runner/verifier 语法和 `--help` 通过；
- `run --dry-run` 显示完整总序、依赖、两条运行链和 contract hash；
- dry-run 未连接 app-server，未创建 Goal、handoff、canonical state、
  target Skill、runtime scheduler 或 runtime artifact。
