# 容器丢失恢复入口

机器额度已由用户增加8小时，当前截止时间为2026-09-08 20:18:09 UTC（北京时间次日04:18:09）。原始冻结阶段授权不改写；后续阶段显式引用追加授权。

最新状态、实现代码模板和完整日志快照，每10分钟提交至：
https://github.com/cspool/auto_trace/tree/progress/batch8-continuation-20260908/perf_trace_batch8/progress/batch8-continuation-20260908

读取该分支的 `current/SNAPSHOT_MANIFEST.json`，核验 `current/r08/accepted` 的独立审计，再按 `current/remote_publications` 下载原始数据。只复用原始字节、规范化清单与独立审计全部验证一致的采集。活动数据库不作为已完成产物保存或采用。

第一组原始数据及R07 CPU复核已发布：
https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-continuation-checkpoint-20260908-001

当前外层检查点与发布任务的版本、代码和会话号见进度分支 `current/emergency_root_tools/RECOVERY_STATE.json`。该记录覆盖早先的 NFS `session_state.json`。发布任务为每组已验收采集制作逐文件 SHA-256 验证的压缩分卷，上传 Release 并核对 GitHub 服务器摘要。每阶段完成后仍需另发完整阶段产物与完成审计。

R09/R10模板在检查点中标记为 prepared_not_executed，不代表相应阶段执行或完成。R07原始远端采集器终态未证实，继续保留complete_recovered_offline例外，不伪造历史原生终态。

权重存储约束：11 个权重分片的物理文件必须始终位于 `/root`。此前迁入 NFS 的做法已纠正，所有分片回迁后逐片 SHA-256 一致；`WEIGHTS_MUST_REMAIN_PHYSICAL_ROOT.json` 列出当前物理路径。之后只调整日志、trace 和已验证可从远程恢复的下载缓存，不再迁移权重到 NFS。

用户追加存储要求：R08 到 R10 的全部运行产物、阶段产出和日志均须物理保存在 NFS，权重仍须物理保存在 `/root`。后续采集已暂停；当前第三项采集已关闭，正在逐文件校验并将已有 root/内存盘产物迁回 NFS。迁移记录在 `run_R08_R10/storage_policy_correction_001`。当前 NFS 主目录总配额 50 GB，已请求提高配额或提供更大的 NFS 路径；不会用 root/内存盘存放后续 R08–R10 产物来绕过这一要求。
