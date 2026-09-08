# 容器丢失恢复入口

机器额度已由用户增加8小时，当前截止时间为2026-09-08 20:18:09 UTC（北京时间次日04:18:09）。原始冻结阶段授权不改写；后续阶段显式引用追加授权。

最新状态、实现代码模板和完整日志快照，每10分钟提交至：
https://github.com/cspool/auto_trace/tree/progress/batch8-continuation-20260908/perf_trace_batch8/progress/batch8-continuation-20260908

读取该分支的 `current/SNAPSHOT_MANIFEST.json`，核验 `current/r08/accepted` 的独立审计，再按 `current/remote_publications` 下载原始数据。只复用原始字节、规范化清单与独立审计全部验证一致的采集。活动数据库不作为已完成产物保存或采用。

第一组原始数据及R07 CPU复核已发布：
https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-continuation-checkpoint-20260908-001

`remote_checkpoint_watchdog_001.py` 是独立于业务阶段的外层Git检查点任务；`publish_accepted_captures_001.py` 会为之后每组已验收采集制作逐文件SHA-256验证的压缩分卷，上传Release并核对GitHub服务器摘要。每阶段完成后仍需另发完整阶段产物与完成审计。

R09/R10模板在检查点中标记为 prepared_not_executed，不代表相应阶段执行或完成。R07原始远端采集器终态未证实，继续保留complete_recovered_offline例外，不伪造历史原生终态。
