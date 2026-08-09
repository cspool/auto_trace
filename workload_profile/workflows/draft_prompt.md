# 当前最终需求摘要

## 六个文本适配 Goal

依次执行：

```text
A01 -> A02 -> A031 -> A041 -> A032 -> A042
```

源 Workflow 和参考 Skill 提供方法、约束、目标与执行流程。六个 Goal
只把其中的旧项目上下文改写为当前项目后续可使用的 Skill 文本合同，产出
`SKILL.md`、references、`goal-spec.md` 和适配 handoff。

不写业务代码、辅助脚本、verifier、fixture 或测试，不运行正式 Workflow。
具体源码符号、hook、命令、schema 和实现由后续 R01–R042 使用这些 Skill
时检查当前项目并自动实现、修正。

A01 按当前合同重新执行。

## A07：调度器产出

A07 不属于适配。它消费六个适配 Skill 和各自的 `goal-spec.md`，产出一个
运行时调度脚本与两个 manifest：

```text
Dispatch: R01 -> R02 -> R031 -> R041
FX:       R01 -> R02 -> R032 -> R042
```

每阶段创建独立 Goal，将 Skill、goal-spec、运行参数和前序 runtime
handoff 组成 prompt。只有当前 Goal `complete` 才启动下一个；其他终态、
中断或缺少 handoff 时停止。

A07 不执行 Workflow，只检查脚本语法、`--help`、两种 `--dry-run` 顺序与
manifest 绑定。
