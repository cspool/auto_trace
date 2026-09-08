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

## 2026-09-08 11:06 UTC — exact replay admission retry

R08 remains **3/12 accepted**. Capture 04 attempt 002 completed all eight 1,024-token requests, both native PMC streams, 12,544 process markers and 23,660 strictly owned kernels. Its independent attribution was **not accepted**: 128 of 1,408 required Triton owners had no owned kernel under a different first-decode batch admission context. Original raw data and failed normalization remain intact. Revision 018 restores the per-rank request admission order recorded in hash-sealed R07 while preserving the eight original HTTP requests, submission order, prompts, parameters and DP2 topology. The production admission buffer passed all 48 per-rank permutations, warmup passthrough and duplicate/cross-rank negative cases. Capture 04 attempt 003 started at 11:05:50 UTC under serial scheduler 006; real kernel equivalence still requires validation.

Analysis 006 adds connection-local SQLite mmap/pager caching only. The actual closed 3.49 GB NFS DB passed quick_check in 4.19 seconds with unchanged size/mtime; attribution rules and independent audit formulas are unchanged. Both normalizer and independent auditor use the new read cache.

The first three published captures have 9 large files temporarily evicted (13,251,173,857 bytes). Exact original-file manifests, GitHub server asset digests and per-segment recovery records are retained in NFS and remote checkpoints. Weights remain physically under /root until all twelve captures are accepted; every evicted original byte must be restored and SHA256 verified before final R08 closure. R09/R10 business execution has not begun.

## 2026-09-08 11:15 UTC — terminal sealing preparation

Capture 04 attempt 003 finished model initialization in 414.46 seconds. Both worker warmup hipProfilerStart calls returned status 0 and both native PMC streams are growing. Final pre-measured two-worker health and actual eight-request kernel attribution are still pending.

Prepared stage templates 003 and outer assignment 002 add direct required R01–R09 prefix/output hashes and explicit per-stage execution fields, checked by an independent scheduler validator before any handoff is written. Twenty-two CPU preparation checks cover valid schemas plus missing-hash, three-request, single-device, unclosed-process, altered-output-hash and erased-R07-uncertainty rejection. The R10 preaudit manifest is immutable and separate; its final artifact manifest is written after the independent audit and includes all ten mandatory deliverables. This is tool preparation only; no R09/R10 business execution or terminal acceptance is claimed.

## 2026-09-08 11:22 UTC — actual two-rank admission confirmed

Capture 04 attempt 003 passed pre-measured native PMC health for rank 0 / worker 471808 and rank 1 / worker 471801, with 714,706,447 and 717,798,743 native bytes respectively. All eight original measured requests started after the original two warmups. Both EngineCore admission releases match the exact R07 order; rank 1 arrived as request 8,7,1,3 and was released as recorded 1,3,8,7. Request objects and workload are unchanged. This establishes actual admission control only; full native trace/PMC attribution and capture acceptance remain pending.

## 2026-09-08 11:28 UTC — all eight live target sets and first-phase order verified

Capture 04 attempt 003 has all 12,544 declared process targets across the eight original measured requests, with no missing, extra or duplicate target. Each request retains 784 first-prefill and 784 first-decode targets. Both ranks’ actual first-prefill and first-decode request orders equal the recorded R07 order. This is a read-only live process-marker checkpoint, not completed native DB/PMC attribution; all eight 1,024-token requests and the final 1,408-owner Triton counter audit still must finish before acceptance.

## 2026-09-08 12:12 UTC — complete native ownership, CPU-only graph classification repair

Capture 04 attempt 003 completed 8/8 HTTP 200 requests, exactly 1,024 tokens each, and closed both workers. Native output contains all 12,544 process markers and 23,660 strictly owned kernels. **All 1,408 required Triton owner multiplicities now match R07**, resolving the previous 128 missing-owner mismatch.

Analysis 006 then rejected an out-of-scope `hipGraphLaunch` while globally scanning every same-literal native kernel, including warmup/later unselected execution. A complete native diagnostic found 527,868 graph dispatch records (263,934 per worker), none attached to a required selected dispatch. A separate CPU native-index check found zero graph launch intersections with all 1,408 selected process ranges. The full 434 MiB diagnostic remains on NFS with a hash reference here; no raw DB/counter bytes were changed.

Analysis 007 preserves direct selected launch/PMC correlation, exact per-owner kernel multiplicity and all raw row partition gates. It permits only known graph dispatches strictly outside every selected process index union, records a complete ordered identity hash/count, and has the independent auditor rescan that original native population. Eleven CPU boundary cases passed; actual new normalization is running against the same sealed capture in revision 003. No GPU recapture or completed-capture acceptance is claimed yet. The progress publisher now keeps large evidence files in NFS for Release publication and pushes their complete hash references, avoiding Git blob limits.

## 2026-09-08 12:17 UTC — R08 4/12 accepted; fifth capture started

The same capture 04 attempt 003 passed analysis 007 normalization in 79.26 seconds and its separate independent audit in 49.28 seconds. All 1,408 selected dispatches are accepted (704 per native rank/device); all 584,295 other PMC rows are retained and partitioned as outside the selected dispatch set. The independent auditor also rescanned and verified every one of 527,868 native graph dispatch identities as outside the selected native process-index intervals. No required counter cell is missing, no raw bytes were modified, and no GPU recapture was used for this CPU repair.

Serial scheduler 007 reuses the four accepted captures and started capture 05 Triton pmc_read / attempt_001 at 12:17:09 UTC using runtime revision 018 and analysis 007. Capture 04 publication and subsequent server-SHA256-verified offload are handled by the existing outer publishers. R08 is not terminal yet; R09/R10 business execution remains pending.

## 2026-09-08 12:21 UTC — fourth full capture Release and verified eviction complete

Capture 04 is published at https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r08-04-triton-red-fused--to-copy-add-mean-mul-pow-rsqrt-0-pmc-20260908. Both compressed parts and all manifest/checksum assets passed current GitHub server SHA256 verification. Six large original raw files (7,841,751,606 bytes) were then temporarily evicted under the user-approved Release backing policy. The first four captures now account for 21,092,925,463 temporarily evicted bytes; original-file SHA256 recovery manifests remain on NFS and in remote checkpoints. Full original restoration remains mandatory before final R08 validation; no weights have been removed. Capture 05 remains active.

2026-09-08 12:34 UTC: Capture 05 has passed both native-worker pre-measured health checks and entered the original eight-request measured batch. Both rank admission orders match R07. Four accepted capture Releases are SHA256-verified; 21,092,925,463 bytes were temporarily evicted with restoration receipts retained. Outer health monitor 005 synchronizes current top-level recovery fields with the per-observation data; capture and analysis tools remain unchanged.

2026-09-08 12:37 UTC: Capture 05 live marker audit reached all 12,544 declared first-prefill/first-decode targets across eight requests, zero missing/unexpected/duplicate targets, and all first-phase orders match R07. This live check does not replace closed native DB/PMC attribution. Separately rechecked every current asset of the first published Release and verified the local archive SHA256, then removed only its redundant 874,112,320-byte upload cache; manifests and independent raw-restoration receipts remain NFS.
