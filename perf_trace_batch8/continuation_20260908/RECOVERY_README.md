# R08 → R10 容器丢失后的恢复入口

本目录的 `RECOVERY_STATE_NFS.json` 是提交时的快照。最新自动备份在 [进度分支](https://github.com/cspool/auto_trace/tree/progress/batch8-continuation-20260908/perf_trace_batch8/progress/batch8-continuation-20260908)，每约 10 分钟推送并核验远端提交；阶段验收与发布记录另行提交主分支。恢复时比较时间戳，不以主分支旧快照判断当前采集。

NFS 控制目录：`/public/home/accl15ptg7/run_R08_R10`。原始 R08 运行目录：`perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001`。全部新产物、日志和控制脚本都在 NFS。`/root/r08_continuation_001_bulk` 是通往 NFS 的目录别名，不能据路径字面将它当成 root 上的可删除副本。

## 先核对实际状态

- 核对 `RECOVERY_STATE_NFS.json`、最新进度提交及各 `*.accepted_checkpoint.json` 的时间和 SHA256。会话 ID 与 PID 仅适用于原容器。
- 当前冻结工具为 `raw/runtime_tools/revision_018`、`tools/analysis_007`，对应 `runtime_capture_gate_011.json` 与 `background_graph_analysis_CPU_gate_001.json`。不得修改已冻结的运行代码、原始数据或验收凭证。
- 当前外层采集调度器为 `run_r08_serial_suffix_009.py`，复用前八项验收并从第九项 attempt002 继续。重启时保留已有目录及失败记录，建立新的调度恢复版本；复用已验收项，给未完成的采集建立新 attempt，避免覆盖旧记录。已封存但 CPU 校验失败的原始采集可在新校验版本中继续分析，无须直接重新执行 GPU 采集。
- 只有完整执行清单、归因清单和独立审计同时存在且哈希匹配，才算一项采集完成。HTTP 成功或实时 marker 覆盖报告本身不能代替原生 DB/PMC 归因审计。

## 存储与远端恢复

权重的 11 个物理分片必须位于 `/root/Qwen3.5-27B-verified-root-backing-20260908`，模型目录 `/root/Qwen3.5-27B` 中的对应链接应指向这些分片。丢失后若仍有 GPU 采集未完成，先按已有权重校验清单恢复到 root；不向 NFS 迁移权重。

各已发布采集的 `PUBLICATION_COMPLETE.json`、`FILE_MANIFEST.json`、`ASSET_MANIFEST.json` 和 `raw/runtime_tools/remote_release_offloads_001/*.complete.json` 保留了远端资产、原始成员 SHA256 及被暂时删除的本地文件。缺失且有这些完整凭证的文件属于已授权的临时回收；没有凭证的缺失文件不能按已完成处理。

全部 12 项采集验收通过且 GPU、服务和采集进程退出后，`restore_all_R08_release_artifacts_002.py` 才可核对空间、记录并删除指定的 root 权重，拉取各 Release，恢复每个被回收的原始文件并核验其原始 SHA256。root 仅在这个阶段用作已授权的原始文件恢复空间；新阶段输出和日志仍写 NFS。恢复完成凭证为 `raw/runtime_tools/release_restoration_001/COMPLETE.json`。若恢复后的 root 文件再次随容器丢失，该工具支持按原恢复凭证重新取回相同字节，保留原凭证不变。

## 后续阶段与最终完成条件

CPU 后续入口为 `await_all_captures_then_cpu_002.py` → `run_closed_R08_to_R10_002.py`，使用 `prepare_stage_assignments_003.py`、`stage_tool_templates_003` 和独立的 `audit_runtime_handoff_001.py`。必须依次恢复并验收 R08、执行并验收 R09、执行并验收 R10；前序完整 handoff 出现前不能提前执行后序业务阶段。

`publish_accepted_captures_004.py` 发布各采集，`offload_published_R08_files_002.py` 仅回收已审计且远端校验通过的大文件，`publish_complete_stages_003.py` 发布完整阶段及 R10 离线交付物。最终完成还需确认 R10 审计、完整 handoff、离线浏览器验收及全部阶段 Release 远端 SHA256 校验，不能仅凭后台进程已启动宣告结束。

八请求覆盖要求是 R06 声明的每个请求首个 prefill / decode 各 784 个目标，共 12,544 个，并在原生归因中保持 DP2 两张卡的完整覆盖。R10 主时间线应有 59,872 个事件。R07 是唯一 observed 时间来源；保留其“本地离线恢复完成，但历史原生控制器终止无法追认”的事实，不把重放时钟当成 R07 延迟。

已授权机器截止时间：2026-09-09 04:18:09 UTC（用户第二次追加 8 小时，见 MACHINE_TIME_EXTENSION_002.json）。第九项首次尝试在正式测量前因单卡原生 PMC 为空而失败，进程全部关闭后已切换采集调度器 009。当前采集调度器、后续 CPU 阶段、发布及进度监控均使用新期限。

若发布器报 `create release`，先检查它引用的本地 HEAD 是否已存在于远端：本次曾因 Git 推送传输停滞导致 GitHub 找不到 `target_commitish`。保留归档和采集，核验进程归属后对同一提交做有超时限制的普通推送重试，验证远端 SHA，再让发布器继续；不要因此重跑 GPU 采集或强制改写分支。
