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

2026-09-08 09:27 UTC：R08 全部 7,630 个文件、28,025,404,918 字节已迁到物理 NFS，逐文件复制及切换后 SHA-256 校验一致。逻辑路径不变；`/root/r08_continuation_001_bulk` 现仅是指向 `/public/home/accl15ptg7/r08_continuation_001_NFS_bulk` 的目录别名。权重的物理文件仍全部位于 `/root`。当前权威状态为进度分支 `current/state/RECOVERY_STATE_NFS.json`；后续输出采用 revision_016 / analysis_005 的 NFS 路径检查，原冻结版本保留。每次新采集前检查 NFS 容量，不足即暂停。

## 2026-09-08 09:57 UTC: verified Release offload and fourth-capture retry

User explicitly authorizes temporarily removing published local data and restoring it before final R08 validation. Three accepted segments are published; all nine evicted files were checked against published file SHA256 and current GitHub asset size/digest. This frees 13,251,173,857 bytes. NFS retains exact recovery manifests and logs. Original inventory and accepted audit certificates are unchanged; their large source files are temporarily absent and must be restored before final stage closure.

Weights remain physical `/root` until all 12 R08 GPU captures are accepted and all workers terminate. User authorizes removing weights then to make room for restoring all R08 artifacts and performing aggregate validation. Capture outputs continue to be physical NFS.

Fourth segment attempt001 failed the pre-measurement native health gate (rank0 empty PMC); the eight measured requests never started. All its known processes are terminated. Revision017 starts native collection explicitly before each of the original two warmups and retains explicit measured start, exact marker boundaries, all-eight coverage and independent attribution gates. CPU fixtures pass; actual two-worker native validation remains pending. Attempt002 started at 09:56:04 UTC. Spawn alone is not a proven remedy.

Latest recovery state: `/public/home/accl15ptg7/run_R08_R10/RECOVERY_STATE_NFS.json`. Deadline remains 2026-09-08 20:18:09 UTC.

## 2026-09-08 10:07 UTC: restoration and CPU suffix prepared

The post-capture restorer is prepared and passed a CPU-only binary member roundtrip, original SHA256 validation, completed restart, and wrong-hash rejection. It has not deleted weights or restored actual capture files. It requires all 12 accepted captures, closed GPU processes, complete per-segment publication and offload receipts, and a capacity reserve before deleting any weight shard. Every removed source is restored byte-for-byte before formal R08 assignment. Final R08 checks also rehash every member in every original raw capture inventory, including rejected attempts.

An outer waiter is running; R09/R10 business execution has not started. New CPU-stage outputs and logs remain on NFS. Final R08 publication references already published accepted raw captures instead of duplicating their compressed upload caches. Each reference contains the original Release receipt and exact file manifest.

The immutable storage authorization maps are cached per CPU process to avoid parsing and rehashing the same multi-megabyte proof for each of more than 136,000 predecessor files; each actual source file still gets its own full content hash and exact symlink check. A production-path check validated 300 paths in 0.72 seconds with a single authorization-map load.

Fourth capture retry revision017: both worker warmup hipProfilerStart calls returned 0 and both native PMC files are growing. Full measured and independent attribution acceptance still pending.

## 2026-09-08 10:26 UTC: all-eight early target coverage in fourth capture

Fourth segment attempt002 passed the native per-worker pre-measurement health check at 10:11:16 UTC. Both original warmups completed; both native PMC files were about 715 MB, with exact PID/device identities. The measured eight-request batch remains running.

A read-only early marker check now observes the full declared R06 first-prefill/first-decode process target universe: 8 requests, 12,544 process rows, exact logical-target sets per request/phase, no missing/unexpected/duplicate targets, exactly one worker per rank. This is a live-prefix coverage checkpoint and does not substitute final native DB correlation or PMC attribution. The full 1,024-token workload per request remains required.

The restoration CPU fixture additionally simulates loss of a previously restored root backing while NFS receipts remain. It successfully recreates the original bytes without rewriting the immutable completion receipt. Actual weights remain on root and no actual post-capture restoration has run.
