# Workflow 能力完整迁移阶段实现计划

## 1. 当前执行边界

本次只更新迁移控制面：

```text
Workflow inventory
  -> capability coverage matrix
  -> 6 个 source-Skill 文本对齐 Goal
  -> 4 个强制 Workflow-gap Skill Goal
  -> 1 个强制 scheduler-generation Goal
  -> 静态检查与 adaptation run --dry-run
  -> 停止
```

本次不执行上述 Goal，不创建 target Skill 或 handoff，不修改现有
`workload_profile/skills/`，也不修改或重建现有运行时 scheduler 和
pipeline manifests。A07 是后续明确执行 Phase 2 时才生效的产出定义。

## 2. 能力覆盖结论

六个主要参考 Skill 能力仍按原拆分保留：

| Goal | 权威参考 Skill/范围 | 目标 Skill |
| --- | --- | --- |
| A01 | `trace-patch-target-discovery` / full | `qwen-dcu-profile-patch-targets` |
| A02 | `visipruner-trace-dispatch-profile` / Algorithmic Trace + selection | `qwen-dcu-algorithmic-trace-selection` |
| A031 | `visipruner-trace-dispatch-profile` / filtered Dispatch | `qwen-dcu-dispatch-trace` |
| A041 | `dispatch-layer-reconstruct-onnx` / full | `qwen-dcu-dispatch-reconstruct-visualize` |
| A032 | `visipruner-fx-trace-workflow` / full | `qwen-dcu-fx-trace` |
| A042 | `visipruner-fx-process-visualization` / full | `qwen-dcu-fx-reconstruct-visualize` |

完整枚举 Workflow 后发现四个能力没有被上述参考 Skill 规范覆盖，因此不能
忽略，也不能暗中塞进相邻 source-Skill 文本对齐 Goal：

| Goal | Workflow-gap 权威 | 未来目标 Skill |
| --- | --- | --- |
| A00 | `00_overview.md` 的共享 run contract、event conservation 与 evidence boundaries | `qwen-dcu-workload-profile-contract-audit` |
| A051 | Dispatch 的逐事件手工 character visualization、跨事件覆盖和 completion record | `qwen-dcu-dispatch-visualization-coverage-audit` |
| A033 | FX `Rule Reconstruction` | `qwen-dcu-fx-process-reconstruction` |
| A052 | FX final coverage audit、人工签核与 completion record | `qwen-dcu-fx-coverage-audit` |

其中 A042 的参考 Skill 只规范 reconstruction 结果的逐 process 解释和手工
可视化；FX rule reconstruction 本身由 A033 独立规范。保留既有 A042 目标
Skill 名称是兼容现有产出路径，不表示把 A033 的能力重新并入 A042。

## 3. 串行迁移总序

控制面总序为：

```text
A00 -> A01 -> A02 -> A031 -> A041 -> A051
    -> A032 -> A033 -> A042 -> A052 -> A07
```

A032 的业务依赖仍只有 A02；它在总序中位于 Dispatch 分支之后，是为了让
迁移 runner 保持单 Goal 串行提交。A07 必须最后执行并依赖全部十个
Skill-producing Goal。

## 4. 两类 Skill-producing Goal

### Source-Skill 文本对齐

每个 source-backed Goal：

1. 完整读取唯一参考 Skill 及其直接资源；
2. 保留 manifest 固定的源文件集合、方法、顺序、输入输出、验证、错误与
   完成边界；
3. Workflow 只解释角色、依赖和 handoff，不提供额外能力正文；
4. 只替换经证实的当前项目绑定，未知具体绑定延迟到运行时发现；
5. 生成目标 Skill 和只索引该 Skill 的最小迁移 handoff。

### Workflow-gap Skill 生成

每个 gap Goal：

1. 只以 manifest 固定的 Workflow section 为能力权威；
2. 只以 manifest 固定且带 hash 的 binding evidence 对齐当前项目；
3. evidence 为空或不能确认具体绑定时，保留能力并显式写为 runtime
   discovery；
4. 目标文件集合严格为 `SKILL.md` 与 `agents/openai.yaml`；
5. 不复制 Workflow、业务工具、历史 artifact 或并行 goal-spec；
6. handoff 额外标记 `authority_type=workflow_gap` 和固定 authority。

## 5. 后续 A07 定义

只有后续明确执行 Phase 2 时，A07 才消费十个已提交目标 Skill，生成或校验：

```text
workload_profile/scripts/run_workload_profile.py
workload_profile/manifests/dispatch_pipeline.json
workload_profile/manifests/fx_pipeline.json
```

未来运行链定义为：

```text
Dispatch: R00 -> R01 -> R02 -> R031 -> R041 -> R051
FX:       R00 -> R01 -> R02 -> R032 -> R033 -> R042 -> R052
```

每个 runtime Goal 只绑定一个 Skill；prompt 只组合 Skill、用户参数和累计
前序 runtime handoff。A07 只生成并 dry-run 校验调度器，不执行业务
Workflow。

## 6. Gate 与状态

Source-backed Gate 校验源/目标文件集合、frontmatter、agent metadata、
文本对齐和最小 handoff。Gap Gate 校验固定文件集合、authority/evidence
hash、必需能力标记、runtime-discovery 边界和 gap handoff。A07 Gate 校验
Python、`--help`、两条 runtime 链、仅 Skill 绑定和两种 `--dry-run`。

新控制面使用独立状态：

```text
workload_profile/workflows/project_adaptation/state/
  adaptation_state_workflow_capability_complete_v1.json
```

旧状态不得被新合同自动恢复。本次 Phase 1 的 `run --dry-run` 不创建该状态。
