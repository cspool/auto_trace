# Workflow Goal 拆分与项目适配

## 1. 基本判断

Workflow 已经把完整流程拆成独立 Goal，并标明每个环节使用哪个现有
Skill。Workflow 的作用是解释 Skill 在环节中的角色和上下游关系；迁移
产出的正确目标约束来自该参考 Skill 本身。

本轮适配只把参考 Skill 的旧项目文本绑定对齐到当前
Qwen3.5、vLLM V1、ROCm/DCU 项目，不从 Workflow 重新编写或扩展一套
Skill 合同。

## 2. 两阶段架构

```text
产出阶段
  六个参考 Skill 文本对齐 Goal:
    A01 -> A02 -> A031 -> A041 -> A032 -> A042
  一个调度器产出 Goal:
    A07

使用阶段
  Dispatch: R01 -> R02 -> R031 -> R041
  FX:       R01 -> R02 -> R032 -> R042
```

所有项目产出必须位于 `${project_root}/workload_profile/`。

## 3. 六个文本对齐 Goal

| Goal | Workflow 角色 | 迁移主体 | 文本产出 |
|---|---|---|---|
| A01 | 01 profiler/patch target | `trace-patch-target-discovery` 全部 | S01 Skill |
| A02 | 02 trace/selection | `visipruner-trace-dispatch-profile` 的 Algorithmic Trace/selection 能力段 | S02 Skill |
| A031 | 03-1 Dispatch capture | `visipruner-trace-dispatch-profile` 的 filtered Dispatch 能力段 | S031 Skill |
| A041 | 04-1 Dispatch reconstruction | `dispatch-layer-reconstruct-onnx` 全部 | S041 Skill |
| A032 | 03-2 FX capture | `visipruner-fx-trace-workflow` 全部 | S032 Skill |
| A042 | 04-2 FX visualization | `visipruner-fx-process-visualization` 全部 | S042 Skill |

每个 Goal：

- 以 Goal 模板 `## Prompt` 指定的参考 Skill 或能力段为唯一迁移主体；
- 镜像源 Skill 的文件结构并最大限度复用其原文、资源和引用关系；
- 保留方法、顺序、输入输出、验证、错误边界和完成条件；
- 只把旧项目名称、路径、模块、运行时、硬件、命令、schema、artifact
  和示例绑定改成当前项目事实；
- 无法确认的具体绑定保留原约束强度，改为运行时发现；
- 只产出目标 Skill 和最小适配 handoff。

不得从 Workflow 复制内容到目标 Skill，也不得统一新增
`workflow-requirement.md`、`adaptation-mapping.md`、
`shared-contract.md`、`handoff-contract.md` 或 `goal-spec.md`。参考
Skill 本来存在的 `references/`、`scripts/` 或其他资源必须按源结构保留。

## 4. 两类 handoff

适配 handoff：

```text
workload_profile/workflows/project_adaptation/artifacts/<Axx>/handoff.json
```

它只索引已经完成文本对齐的 Skill：

```json
{
  "schema_version": 1,
  "stage_id": "<Axx>",
  "status": "complete",
  "outputs": {
    "skill": "workload_profile/skills/<skill-name>"
  }
}
```

runtime handoff 由 R01–R042 的正式运行产生，承载实际运行数据并输入下一
运行 Goal。适配 handoff 不替代 runtime handoff。

## 5. 实现责任

A01–A42 不冻结当前项目的具体源码实现。后续 R01–R042 直接使用适配后的
Skill，并自行：

1. 检查当前项目源码、入口、模块、符号、环境和已有工具；
2. 根据 Skill 的原始方法选择或实现实际 hook、脚本、schema 和命令；
3. 完成 Skill 要求的验证、证据和停止检查；
4. 生成供下一 Goal 使用的 runtime handoff。

运行 Goal 的目标约束已完整包含在适配后的 Skill 中，不再另行维护
goal-spec。

## 6. A07 的性质

A07 不算适配。它消费六个适配后的 Skill，产出：

```text
workload_profile/scripts/run_workload_profile.py
workload_profile/manifests/dispatch_pipeline.json
workload_profile/manifests/fx_pipeline.json
```

调度语义为：

```text
Dispatch:
  start R01 -> wait complete
  start R02 with R01 runtime handoff -> wait complete
  start R031 with R02 runtime handoff -> wait complete
  start R041 with R031 runtime handoff -> wait complete

FX:
  start R01 -> wait complete
  start R02 with R01 runtime handoff -> wait complete
  start R032 with R02 runtime handoff -> wait complete
  start R042 with R032 runtime handoff -> wait complete
```

每阶段使用独立 Goal/thread、`effort=max` 且不设置 token budget。A07 将
对应适配 Skill、用户运行参数和前序 runtime handoff 组成 prompt；只有
当前 Goal 为 `complete` 才启动下一个。

## 7. 调度与验收

适配调度脚本管理“六个文本对齐 + 一个 A07 产出”的固定顺序和 canonical
state。每个 Goal 自主管理内部 Turn 和完成判断；脚本只等待终态、执行
轻量 Gate、提交或停止。

六个适配 Gate 检查目标 Skill 的文件集合是否镜像参考 Skill、基本
frontmatter/agent 配置、当前项目文本对齐和最小 handoff，不检查正式业务
运行证据。A07 Gate 检查调度脚本语法、两条串行链、只含 Skill 的 manifest
绑定和 dry-run。
