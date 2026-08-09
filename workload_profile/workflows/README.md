# Workload Profile Workflow 使用说明

## 1. 阶段划分

产出阶段顺序：

```text
A01 -> A02 -> A031 -> A041 -> A032 -> A042 -> A07
```

- A01–A42 是六个参考 Skill 文本对齐 Goal：源 Skill 或指定能力段是目标
  约束，Workflow 只说明它在环节中的角色；
- A07 不是适配，它生成使用六个 Skill 的运行时 Goal 调度脚本。

真正的项目源码检查、代码实现、运行和偏差修正由后续 R01–R042 使用适配
Skill 时完成。

两种运行链：

```text
Dispatch: R01 -> R02 -> R031 -> R041
FX:       R01 -> R02 -> R032 -> R042
```

所有持久化产出必须位于：

```text
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile
```

## 2. 适配调度器

```bash
cd /public/home/tangyu408/Qwen_DCU_Worker_0
```

入口：

```text
workload_profile/workflows/project_adaptation/scripts/adapt_workload_profile.py
```

默认配置：

```text
model             gpt-5.6-sol
effort            max
sandbox           danger-full-access
approval policy   never
network access    true
Goal token budget unset
```

## 3. 启动前检查

环境诊断，不创建 Goal：

```bash
python3 workload_profile/workflows/project_adaptation/scripts/adapt_workload_profile.py doctor \
  --project-root /public/home/tangyu408/Qwen_DCU_Worker_0
```

Dry run，只检查配置和七阶段顺序：

```bash
python3 workload_profile/workflows/project_adaptation/scripts/adapt_workload_profile.py run \
  --project-root /public/home/tangyu408/Qwen_DCU_Worker_0 \
  --dry-run
```

当前 canonical state：

```text
workload_profile/workflows/project_adaptation/state/
  adaptation_state_source_skill_text_alignment.json
```

旧错误迁移的 state、日志和产物已经从活动目录清理；当前合同从 A01
全新执行，不恢复旧状态。

## 4. 正式执行

只有下面的命令会启动六个源 Skill 文本对齐 Goal 和一个 A07 产出 Goal：

```bash
python3 workload_profile/workflows/project_adaptation/scripts/adapt_workload_profile.py run \
  --project-root /public/home/tangyu408/Qwen_DCU_Worker_0
```

调度器：

```text
创建当前阶段 Goal
  -> 启动一次初始 Turn
  -> 等待 Goal 自主管理 Turn 并到达终态
  -> 等待 thread idle
  -> complete 后运行轻量 Gate
  -> COMMITTED
  -> 下一阶段
```

它不会拆分 IMPLEMENT/SMOKE。A01–A42 的 Gate 检查目标文件集合是否镜像
源 Skill、当前项目文本对齐和最小 handoff，不要求正式业务运行。

## 5. 状态查看

```bash
python3 workload_profile/workflows/project_adaptation/scripts/adapt_workload_profile.py status \
  --project-root /public/home/tangyu408/Qwen_DCU_Worker_0 \
  --format human
```

持续查看：

```bash
python3 workload_profile/workflows/project_adaptation/scripts/adapt_workload_profile.py status \
  --project-root /public/home/tangyu408/Qwen_DCU_Worker_0 \
  --format human \
  --watch
```

`status` 只读 canonical state，不启动或推进 Goal。

## 6. 中断与恢复

运行终端按 `Ctrl-C` 后，调度器会尽量暂停当前 Goal 并保存状态。

```bash
python3 workload_profile/workflows/project_adaptation/scripts/adapt_workload_profile.py resume \
  --project-root /public/home/tangyu408/Qwen_DCU_Worker_0
```

已 `COMMITTED` 的阶段直接跳过。paused Goal 经人工检查后可显式恢复：

```bash
python3 workload_profile/workflows/project_adaptation/scripts/adapt_workload_profile.py resume \
  --project-root /public/home/tangyu408/Qwen_DCU_Worker_0 \
  --reactivate
```

## 7. A07 产出与使用

```text
workload_profile/scripts/run_workload_profile.py
workload_profile/manifests/dispatch_pipeline.json
workload_profile/manifests/fx_pipeline.json
```

每个适配后的 Skill 本身就是对应运行 Goal 的目标约束。A07 调度器会组合
Skill、运行参数和前序 runtime handoff；运行 Goal 再负责当前项目中的
实际实现与修正，不维护第二份 goal-spec。

只查看接口和顺序，不启动 Goal：

```bash
python3 workload_profile/scripts/run_workload_profile.py --help

python3 workload_profile/scripts/run_workload_profile.py \
  --project-root /public/home/tangyu408/Qwen_DCU_Worker_0 \
  --branch dispatch \
  --dry-run

python3 workload_profile/scripts/run_workload_profile.py \
  --project-root /public/home/tangyu408/Qwen_DCU_Worker_0 \
  --branch fx \
  --dry-run
```
