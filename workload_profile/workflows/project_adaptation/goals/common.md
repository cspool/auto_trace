# Workflow 能力完整迁移 Goal 通用合同

## 适用范围

本合同适用于：

- source-Skill 文本对齐：A01、A02、A031、A041、A032、A042；
- Workflow-gap Skill 生成：A00、A051、A033、A052；
- 最终 scheduler generation：A07。

当前 Goal 只处理自身 stage，不启动后继 Goal，不管理其他 Agent、thread 或
Goal。外部迁移 runner 负责串行顺序、等待、Gate 和提交。

## 共用边界

所有阶段必须：

1. 读取当前 Goal 模板和 manifest 中属于本 stage 的固定输入；
2. 只在 `${project_root}/workload_profile/` 下写 manifest 声明的产出；
3. 不执行 profiler、模型、GPU、Algorithmic Trace、Dispatch、FX、重建、
   ONNX、可视化或业务审计；
4. 不把历史 artifact 冒充当前运行证据；
5. 不修改 Workflow、参考 Skill、manifest、runner、verifier 或 canonical
   state；
6. 不创建额外合同、迁移报告或未声明的文件。

## Source-Skill 文本对齐

对 A01、A02、A031、A041、A032、A042，约束优先级为：

1. 当前 Goal `## Prompt` 指定唯一参考 Skill 及能力范围；
2. 参考 Skill 或指定能力段是结构、内容和约束强度的唯一规范；
3. Workflow 只解释角色、边界、依赖和 handoff；
4. 当前项目源码与配置只用于替换旧项目具体绑定。

必须完整保留参考 Skill 声明范围内的文件组织、章节、方法、顺序、输入输出、
证据、验证、失败、停止和完成条件。只改写项目名、路径、模型、运行时、
硬件、模块、命令、schema、artifact、示例、frontmatter 和 agent metadata。
不能确认的具体绑定必须保留原能力与强度，并改为正式运行时发现。

目标相对文件集合必须与 manifest 固定的源文件集合一致。不得从 Workflow
合成额外能力，不得新增源 Skill 没有的 references、scripts、assets、
goal-spec 或统一模板。

## Workflow-gap Skill 生成

对 A00、A051、A033、A052：

1. `workflow_authority.path + sections + sha256` 是完整且唯一的能力规范；
2. `binding_evidence` 只提供当前项目具体路径、工具、命令和 schema 事实，
   不能缩小或取代 Workflow 能力；
3. `unresolved_bindings` 必须原样保留为 runtime discovery，不能因此忽略、
   降级或取消 Goal；
4. 目标相对文件集合严格为：

   ```text
   SKILL.md
   agents/openai.yaml
   ```

5. 目标 Skill 必须可独立触发、定义输入输出、步骤、证据边界、验证、失败、
   停止和完成条件，并清楚区分相邻 source-backed Skills；
6. 不得复制 Workflow 全文、binding-evidence 业务代码、历史运行 artifact、
   固定事件数、迁移说明或 goal-spec。

Gap handoff 必须保留最小 `outputs.skill`，并额外声明：

```json
{
  "authority_type": "workflow_gap",
  "workflow_authority": {
    "path": "<manifest 固定路径>",
    "sections": ["<manifest 固定 section>"],
    "sha256": "<manifest 固定 hash>"
  }
}
```

## Source-backed handoff

Source-backed stage 只写：

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

它只表示迁移完成，不是正式 runtime handoff。

## A07

A07 不产出 Skill。它必须消费全部十个 Skill-producing stage 的已提交
handoff，按自身模板生成 runtime scheduler 与两个只含 Skill 绑定的
manifest。A07 不读取或生成第二份 goal-spec，不修改目标 Skill，也不执行
runtime Workflow。

## 完成条件

Source-backed Goal 只有在源结构镜像、文本绑定对齐和最小 handoff 通过外部
Gate 后才能 `complete`。Gap Goal 只有在全部 authority 能力得到表达、所有
具体绑定有固定 evidence 或明确 runtime discovery、精确文件集合和 gap
handoff 通过 Gate 后才能 `complete`。A07 按其模板的静态与 dry-run Gate
完成。
