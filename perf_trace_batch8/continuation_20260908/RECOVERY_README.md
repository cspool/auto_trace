# R08 → R10 容器丢失后的恢复入口

本目录的 `RECOVERY_STATE_NFS.json` 是提交时的快照。最新自动备份在 [进度分支](https://github.com/cspool/auto_trace/tree/progress/batch8-continuation-20260908/perf_trace_batch8/progress/batch8-continuation-20260908)，每约 10 分钟推送并核验远端提交；阶段验收与发布记录另行提交主分支。恢复时比较时间戳，不以主分支旧快照判断当前采集。

NFS 控制目录：`/public/home/accl15ptg7/run_R08_R10`。原始 R08 运行目录：`perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001`。全部新产物、日志和控制脚本都在 NFS。`/root/r08_continuation_001_bulk` 是通往 NFS 的目录别名，不能据路径字面将它当成 root 上的可删除副本。

## 先核对实际状态

- 核对 `RECOVERY_STATE_NFS.json`、最新进度提交及各 `*.accepted_checkpoint.json` 的时间和 SHA256。会话 ID 与 PID 仅适用于原容器。
- 当前冻结工具为 `raw/runtime_tools/revision_021`、`tools/analysis_008`，对应 `runtime_capture_gate_014.json` 与 `independent_native_sessions_analysis_CPU_gate_001.json`；原有后台 graph 范围门禁仍保留。不得修改已冻结的运行代码、原始数据或验收凭证。
- 2026-09-08 20:36 UTC，`run_r08_serial_suffix_013.py` 已完成全部 12 项采集及独立审计；总索引和 36 份执行/归因/审计凭证的 SHA256 复核已提交于 `all_twelve_captures_accepted_001`。每组均有 12,544 个目标 process 标记、23,660 个原生归属 kernel，全部三种 PMC 模式共 6,912 项物理 dispatch 归属；每组两张卡均覆盖完整。第十二项原始数据正常关闭，独立审计耗时 185.44 秒。GPU 采集已全部结束，无须重新执行。截至 21:55 UTC，R08 已通过独立总审计并生成完整 handoff，四个 CPU 阶段正常关闭，全部 12 组均满足八请求 trace 与选中 PMC 覆盖。完成凭证见 `R08_local_complete_001`。当前正在准备 R08 完整阶段 Release，并执行 R09 前序入场核验；R09、R10 尚未完成。
- 只有完整执行清单、归因清单和独立审计同时存在且哈希匹配，才算一项采集完成。HTTP 成功或实时 marker 覆盖报告本身不能代替原生 DB/PMC 归因审计。

## 存储与远端恢复

权重的 11 个物理分片必须位于 `/root/Qwen3.5-27B-verified-root-backing-20260908`，模型目录 `/root/Qwen3.5-27B` 中的对应链接应指向这些分片。丢失后若仍有 GPU 采集未完成，先按已有权重校验清单恢复到 root；不向 NFS 迁移权重。

各已发布采集的 `PUBLICATION_COMPLETE.json`、`FILE_MANIFEST.json`、`ASSET_MANIFEST.json` 和 `raw/runtime_tools/remote_release_offloads_001/*.complete.json` 保留了远端资产、原始成员 SHA256 及被暂时删除的本地文件。缺失且有这些完整凭证的文件属于已授权的临时回收；没有凭证的缺失文件不能按已完成处理。

全部 12 项采集验收通过且 GPU、服务和采集进程退出后，`restore_all_R08_release_artifacts_002.py` 才可核对空间、记录并删除指定的 root 权重，拉取各 Release，恢复每个被回收的原始文件并核验其原始 SHA256。root 仅在这个阶段用作已授权的原始文件恢复空间；新阶段输出和日志仍写 NFS。恢复完成凭证为 `raw/runtime_tools/release_restoration_001/COMPLETE.json`。若恢复后的 root 文件再次随容器丢失，该工具支持按原恢复凭证重新取回相同字节，保留原凭证不变。

截至 2026-09-08 21:19 UTC，全部 12 组 Release 与回收凭证已完成，53 个原始大文件（77,001,580,022 字节）已全量恢复并再次逐文件核验原始 SHA256。总完成凭证及全部分组恢复映射已提交于 `release_restoration_complete_001`。自动回收进程已停止，11 个 root 权重分片（55,563,022,432 字节）已按逐文件 SHA256 清单释放；配置文件保留。恢复后的原始文件置于 `/root/R08_release_restored_after_capture_001`，通过原规范路径链接访问；新阶段产物和日志仍物理保存在 NFS。容器丢失时可按原凭证重新恢复，不能用不存在的 root 链接冒充已恢复文件。

## 后续阶段与最终完成条件

当前 CPU 接续入口为 `run_closed_R08_to_R10_003.py`，使用 `prepare_stage_assignments_004.py`、未改动的 `stage_tool_templates_003` 和独立的 `audit_runtime_handoff_001.py`。最初外层入场核验重复重建 67 条路径映射，已在业务阶段尚未开始时保存日志并替换；新外层路径核验在 233 个真实路径与 11 个异常场景中保持相同结果，实测约快 50 倍。每个源文件仍完整核对 SHA256，每个实际目录和文件链接仍实时验证。接续先再次核对 53 份恢复原始文件，再逐一完整核验 R01–R07 前序文件。必须依次验收 R08、执行并验收 R09、执行并验收 R10；前序完整 handoff 出现前不能提前执行后序业务阶段。

`publish_accepted_captures_004.py` 发布各采集，`offload_published_R08_files_002.py` 仅回收已审计且远端校验通过的大文件，`publish_complete_stages_003.py` 发布完整阶段及 R10 离线交付物。最终完成还需确认 R10 审计、完整 handoff、离线浏览器验收及全部阶段 Release 远端 SHA256 校验，不能仅凭后台进程已启动宣告结束。

八请求覆盖要求是 R06 声明的每个请求首个 prefill / decode 各 784 个目标，共 12,544 个，并在原生归因中保持 DP2 两张卡的完整覆盖。R10 主时间线应有 59,872 个事件。R07 是唯一 observed 时间来源；保留其“本地离线恢复完成，但历史原生控制器终止无法追认”的事实，不把重放时钟当成 R07 延迟。

已授权机器截止时间：2026-09-09 04:18:09 UTC（用户第二次追加 8 小时，见 MACHINE_TIME_EXTENSION_002.json）。第九项前五次尝试在正式测量前因一个或两个工作进程的 PMC 为空失败，失败原始数据保留于 NFS 并已[单独发布](https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r08-capture09-prehealth-failures-20260908-001)，不计作已验收采集。runtime019 的 Stop/Start 与 runtime020 的初始关闭方式均未修复。runtime021 的第九项 attempt006 已通过实际完整模型验收：八请求、两张卡各 192 项目标、71,424 个计数器值、30,645,909 条原始 DB 记录及全部 CSV 字节均经检查；证据见 `capture09_attempt_006_accepted_001` 和[第九项 Release](https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r08-09-chunk-gated-delta-rule-fwd-kernel-h-blockdim64-pmc-write-20260908)。底层共享采集器故障的精确内部原因仍未证明。

runtime021 保留同一个 DP2/TP1 服务、原有两个预热及八个并发请求，仅为两个 GPU 工作进程分别启动原生 HIPProf 会话。每张卡的原始日志与 DB/CSV 位于 `raw/captures/<segment>/<attempt>/native_collectors/rank0` 和 `rank1`。`COLLECTOR_EXIT.json`、`control/NATIVE_COLLECTORS_CLOSED.json` 记录真实退出码与进程组关闭；不能用单个原生进程完成代替两边完成。

原始两份 DB/CSV 必须完整保留在 NFS 或已校验的 Release 中；临时回收后仍按原始 SHA256 全量恢复。根目录 `capture.db` / `capture.csv` 是明确标注的无损派生合并，不是新的原生采集；`NATIVE_SESSION_UNION.json` 记录所有原始 SHA256、表行映射和 CSV 行映射。分析008独立逐行比较原始数据，并在每条归因记录中写入原始 DB/CSV 路径、SHA256 与原始 CSV 行号。不得修改原始时间戳、计数器、设备编号、PID 或关联索引。恢复全部原始文件后，仍须通过完整 R08 审计。当前采集调度器、后续 CPU 阶段、发布及进度监控均使用新期限。

最新空间预测见 `STORAGE_FORECAST_AFTER_CAPTURE09_001.json`，已计入两份原始 DB 和派生 DB 同时保留的额外大小。按第九项实测大小，全部大文件恢复量预计为 77.84 GB；即使后三项各增长 50%，释放已授权的权重并恢复原始文件后，root 预计仍余 77.73 GB。该估算不代替最后的实际容量门禁，也不授权提前删除权重。

前十一项已临时回收 69,271,297,848 字节，共 48 个大文件，均有原始 SHA256 与 Release 恢复凭证。第十二项正在采集，权重删除、实际全量恢复及 R08–R10 整体完成均尚未发生。实际 Release 分段下载已通过小范围检查，见 `release_range_download_smoke_001`；完整资产及成员 SHA256 仍须在正式恢复时核验。

两份原生采集正常关闭后，可用 `checkpoint_closed_native_sources_001.py` 先保存原始 DB/CSV 的 SHA256，避免容器在派生合并期间丢失时缺少已关闭源文件的身份凭证。第十、十一项均已将该凭证与后续合并、原始执行清单逐项核对。相关脚本和各阶段检查点位于本目录 `outer_helpers_001` 与对应 `captureNN_*` 子目录；它们本身不代替独立归因验收。

若发布器报 `create release`，先检查它引用的本地 HEAD 是否已存在于远端：本次曾因 Git 推送传输停滞导致 GitHub 找不到 `target_commitish`。保留归档和采集，核验进程归属后对同一提交做有超时限制的普通推送重试，验证远端 SHA，再让发布器继续；不要因此重跑 GPU 采集或强制改写分支。
