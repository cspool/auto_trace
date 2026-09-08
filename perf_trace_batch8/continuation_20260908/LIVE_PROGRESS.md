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

2026-09-08 12:54:36 UTC: Capture 05 completed all eight measured requests, HTTP 200 and exactly 1024 generated tokens each, total 8192, no request failures. Both rank stop events are preserved. Measured replay duration 1324.524 seconds is diagnostic only and is never substituted for R07 observed latency. Native export is still running; this checkpoint does not claim accepted attribution.

2026-09-08 13:06:31 UTC: Capture 05 accepted after normalization (77.52 seconds) and independent audit (47.43 seconds): all 1408 native counter attributes, 704 per rank, 261888 counter values independently recomputed, same R06/R07 logical ownership and all runtime shapes matched, 527868 background graph dispatches independently proven outside selected scopes. Capture 06 immediately started with runtime 018; no workload, target, or analysis changes. Fifth full raw Release publication is pending.

2026-09-08 13:10 UTC: Capture 05 full raw Release is published at https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r08-05-triton-red-fused--to-copy-add-mean-mul-pow-rsqrt-0-pmc-read-20260908 . Rechecked current GitHub asset sizes and SHA256 digests, matched each local file to the published member manifest, and temporarily removed six closed raw files totaling 7,915,953,062 bytes. Five accepted captures now have 29,008,878,525 bytes of exact raw data backed by verified Releases and retained recovery receipts; NFS free space is approximately 19.3 GiB. All 11 weight shards remain physically under /root for captures 06–12.

2026-09-08 13:22 UTC: Capture 06 passed the original two-warmup native health gate on rank 0 worker 620502 and rank 1 worker 620496. Both original four-request admission orders match R07, and the original eight-request measured workload has begun. This start checkpoint is not a trace or attribution acceptance.

2026-09-08 13:27 UTC: Capture 06 live marker audit passed all 16 request/first-phase sets, 784 exact targets each and 12544 total, with no missing, unexpected, or duplicate targets; both ranks and all first-phase request orders match R07. All eight requests are generating. This live prefix check does not replace closed native DB/PMC attribution.

2026-09-08T13:43:31.801878Z: Capture 06 attempt_001 completed all eight original measured requests, HTTP 200 and 1024 tokens each, total 8192, zero failed requests; both native rank stop events are retained. Measured replay duration 1306.412 seconds is diagnostic only, not R07 observed latency. Native export and independent attribution are still required.

2026-09-08 13:55:30 UTC: Capture 06 accepted after normalization (78.80 seconds) and independent audit (48.22 seconds): all 1408 native counter attributes, 704 per rank, 261888 counter values independently recomputed, same R06/R07 logical ownership and all runtime shapes matched, 527868 background graph dispatches independently proven outside selected scopes. Six of twelve R08 captures are now accepted. Capture 07 (chunk_gated_delta_rule_fwd_kernel_h_blockdim64, PMC) immediately started with runtime 018. Full capture 06 Release publication remains pending; no weights removed.

2026-09-08 14:04 UTC: Capture 06 full raw Release is published at https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r08-06-triton-red-fused--to-copy-add-mean-mul-pow-rsqrt-0-pmc-write-20260908 . All current remote asset sizes and SHA256 digests were verified before six closed local raw files totaling 7,960,773,281 bytes were temporarily removed. Six accepted captures now have 36,969,651,806 raw bytes backed by verified Releases. Publication was briefly delayed because its local main commit was not yet on GitHub: the stalled owned Git push was stopped and the same ordinary push completed through the existing alternate transfer route, with remote commit verified; no force push, capture change, or raw-file loss occurred. Capture 07 is running its original warmups.

2026-09-08 14:06 UTC: Capture 07 (chunk_gated_delta_rule_fwd_kernel_h_blockdim64 PMC) passed the original two-warmup native health gate on rank 0 worker 687557 and rank 1 worker 687560. Both rank admission release records are retained and the original eight-request measured batch is running. Trace coverage and native attribution remain pending.

2026-09-08 14:10 UTC: Capture 07 live marker audit passed all 16 request/first-phase sets, 784 exact targets each and 12544 total, with no missing, unexpected, or duplicate targets; both ranks and all first-phase request orders match R07. All eight requests are generating. This live prefix check does not replace closed native DB/PMC attribution.

2026-09-08T14:21:25.041372Z: Capture 07 attempt_001 completed all eight original measured requests, HTTP 200 and 1024 tokens each, total 8192, zero failed requests; both native rank stop events are retained. Measured replay duration 975.233 seconds is diagnostic only, not R07 observed latency. Native export and independent attribution are still required.

2026-09-08 14:23:31 UTC: Capture 07 accepted after 1640.80 seconds of raw capture, normalization (21.94 seconds) and independent audit (16.81 seconds): all 384 native counter attributes, 192 per rank, 71424 counter values independently recomputed, same R06/R07 logical ownership and all runtime shapes matched. No background graph dispatches have this full kernel literal. Seven of twelve R08 captures are now accepted. Capture 08 (same kernel, PMC read) immediately started with runtime 018. At the seventh unit's approximately 28-minute total pace, the five remaining captures would take roughly 2 hours 20 minutes; reserve an additional 1–2 hours for restoration and R08–R10 closure/report audits. This is an estimate, not completed-stage evidence; the authorized deadline remains 20:18:09 UTC.

2026-09-08 14:26 UTC: Capture 07 full raw Release is published at https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r08-07-chunk-gated-delta-rule-fwd-kernel-h-blockdim64-pmc-20260908 . Current remote asset sizes and SHA256 digests and local published member hashes were verified before three closed raw files totaling 4,413,265,764 bytes were temporarily removed. Seven accepted captures now have 41,382,917,570 original raw bytes backed by verified Releases and retained restoration receipts. NFS free space is approximately 18.7 GiB; capture 08 is initializing and root weights remain intact.

2026-09-08 14:36 UTC: Capture 08 attempt001 failed its pre-measured native health gate: rank1 worker 731211 produced zero PMC bytes while rank0 worker 731205 produced 14,997,379 bytes, despite successful original warmup hipProfilerStart records on both ranks. No eight-request measured batch or admission release occurred. All owned profiler/service/workload process groups were verified closed. The seven accepted capture manifest triplets were rehashed unchanged, then serial scheduler 008 started capture08 attempt002 using unchanged frozen runtime018 and analysis007, original inputs/parameters and the same hard health/coverage gates. The failed attempt, raw inventory, native snapshots and logs remain NFS; failure evidence and new scheduler code are committed for recovery.

2026-09-08 14:42 UTC: A read-only CPU diagnostic of rejected capture08 attempt001 confirmed the original 888,242,176-byte DB SHA256 d755800d9f4f1c094335aafbe6d9f4f3218bb2c34f204c5cdf4e58c6fe85ed4f is unchanged. Resolving exact kernel names through native STR_TABLE type 6 finds 2712 startup/warmup target dispatches on rank0 and 3518 on rank1, while preserved rank1 PMC is zero bytes and both warmup hipProfilerStart calls returned 0. This supports counter-collection loss; it does not prove its lower-level cause or accept any measured capture. Diagnostic 002 explicitly supersedes the first diagnostic's direct comparison against HIPOPS Name IDs. Retry attempt002 remains on frozen runtime018, and the failed-attempt/retry checkpoint push was verified at remote main 06c9599 using a bounded HTTP/1.1 retry after transport timeouts.

2026-09-08 14:46 UTC: Capture 08 attempt002 passed the unchanged original two-warmup native health gate on rank0 worker 750538 and rank1 worker 750535, both with nonempty native PMC dispatch evidence. Original eight-request measured batch has started; both rank admission release records are retained. No runtime, workload or acceptance gate change was needed. Failed attempt001 remains rejected and preserved.

- 2026-09-08T14:58:55.546023+00:00: User authorized another 8 h; deadline is now 2026-09-09 04:18:09 UTC. Seven captures accepted/published/offloaded; capture08 attempt002 has both-rank native prehealth and all-eight declared first-phase trace coverage, measured generation ongoing. Outer deadline versions prepared without modifying active GPU or frozen tools.

- 2026-09-08T15:01:11.809474+00:00: Extension002 outer observers active (health006, progress011, capture publisher004, offloader002, CPU waiter002, stage publisher003). Capture08 attempt002 live marker audit covers all 12,544 declared first-phase targets for eight requests with exact R07 phase orders; native closed attribution remains pending.

2026-09-08T15:02:29.223203Z: Capture 08 attempt_002 completed all eight original measured requests, HTTP 200 and 1024 tokens each, total 8192, zero failed requests; both native rank stop events are retained. Measured replay duration 946.873 seconds is diagnostic only, not R07 observed latency. Native export and independent attribution are still required.

- 2026-09-08T15:05:43.130185+00:00: 08_chunk_gated_delta_rule_fwd_kernel_h_blockdim64_pmc_read attempt_002 accepted after closed native attribution and independent audit; 384 exact dispatches, ranks {"0": 192, "1": 192}, 71424 counter values independently recomputed. Raw Release publication/offload status is tracked separately.

- 2026-09-08T15:08:11.244366+00:00: 08_chunk_gated_delta_rule_fwd_kernel_h_blockdim64_pmc_read Release published with server asset size/SHA256 verified: https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r08-08-chunk-gated-delta-rule-fwd-kernel-h-blockdim64-pmc-read-20260908. Authorized local large-file eviction completed for 4412532905 bytes. Original member manifests and restoration receipts retained on NFS and checkpointed here.

- 2026-09-08T15:15:45.000421+00:00: Capture09 attempt001 rejected before eight-request measurement: rank1 native PMC empty after original warmups. All owned process groups closed; eight accepted captures reverified. Scheduler009 retries capture09 attempt002 under unchanged runtime018/analysis007 and extension002 deadline; failed raw data retained on NFS.

- 2026-09-08T15:17:27.819723+00:00: Read-only capture09 attempt001 diagnostic verified original DB SHA and resolved kernel names through STR_TABLE type6. Exact target kernel dispatched on both devices (rank0 2,711; rank1 3,546), while rank1 native PMC remained empty despite both warmup Start calls succeeding. This proves native counter loss; lower-level root cause remains unproven. Diagnostic did not execute GPU work or alter original data.

- 2026-09-08T15:29:40.305388+00:00: Capture09 attempt002 rejected before measured requests because rank0 PMC remained empty; rank1 had positive counters. All failed process groups closed. A separate model-free fresh-interpreter PMC write recheck passed exactly four native gqa6 dispatches per device. This does not prove the full-model root cause. Scheduler010 retries unchanged runtime018 with attempt003; both prior failed attempts remain preserved.

- 2026-09-08T15:38:29.112009+00:00: Prepared runtime019 candidate with one native Stop/Start reset before each original warmup. CPU gate confirms both ranks, once-only reset, unchanged measured Start, wrong-rank rejection and fail-closed Stop failure; no model/device execution performed by preparation. Full model effectiveness is not yet validated. Active capture09 attempt003 remains runtime018.

- 2026-09-08T15:41:17.312947+00:00: Capture09 attempt003 rejected before measured requests (rank1 PMC empty). Three original-runtime attempts preserved; all attempt003 process groups closed and eight accepted-prefix triplets reverified. Scheduler011 activates frozen runtime019 native warmup Stop-Start reset for attempt004; original two warmups, eight requests, admission order, marker contract and analysis007 remain unchanged. Full model effectiveness remains to be validated.

- 2026-09-08T15:44:55.525790+00:00: Read-only third-attempt diagnosis verified the original 885,706,752-byte DB and observed exact target-kernel dispatches on both devices (2,714 / 3,477), with rank1 PMC empty. Fourth attempt now validates runtime019; the original third-attempt data and all earlier failures remain preserved.

- 2026-09-08T15:52:58.470825+00:00: Prepared runtime020 with native PMC/trace initially off until the existing original warmup Stop/Start. All12 collector argv cases preserve every existing argument except the two initial-off flags; CPU tests verify logical initialization does not activate collection, both-rank warmup reset and measured Start, and fail-closed error handling. All declared measured scopes remain mandatory. Native startup trace before original warmups is intentionally omitted. Full-model effectiveness remains unproven.

- 2026-09-08T15:54:29.488385+00:00: Capture09 attempt004 rejected before measurement: rank0 PMC remained empty despite successful Stop and Start transitions. All groups closed and accepted eight-capture prefix reverified. Scheduler012 activates frozen runtime020 for attempt005: native PMC/trace initially off, activated before original warmups. Startup native trace before warmups is intentionally omitted; original measured workload, DP2 ordering, full declared target coverage and analysis007 remain mandatory.

- 2026-09-08T16:14:08.077936+00:00: Capture09 attempt005 (native initially off) rejected before measurement with both PMC files empty; collector exported no native PMC CSV. Complete failure preserved. A separate model-free live-visibility probe observed both files already nonempty before Stop (~16.7 KB each), with only tails appended by libc fflush; final CSV contained four gqa6 dispatches per device. This did not reproduce the full-model empty files. Now testing the isolated effect of creating both device contexts in each fresh worker.

- 2026-09-08T16:18:29.888259+00:00: Model-free dual-context perturbation reproduced missing rank0 PMC (rank1 had four native rows), which stayed empty through Stop, fflush and worker exit. Baseline own-device-only probe had four rows per device. This narrows the issue to a reproducible native multi-device-context interaction; full-model cause is not yet proven. Testing documented kernel-profile-mode1 in the same probe before further model runs.

- 2026-09-08T16:25:03.651519+00:00: External kernel-profile-mode1 diagnostic is not admissible for the existing exact R08 chain: all DispatchNs=0, GPU IDs8/9 differ and warmup is included despite initially-off controls. Raw evidence retained, no rows promoted. Original mode now tests an owner-context initialization barrier in the same model-free dual-context reproducer.

- 2026-09-08T16:42:20.140952+00:00: R08 remains 8/12 accepted. Owner barrier and masked-extra probes failed; unmodified baseline repeat also lost rank0. This corrects the earlier cross-device causal hypothesis: root cause remains unproven. Masked/no-extra probe recorded four targets on both devices, but potential brief collector lifetime overlap limits comparison. Explicit all-worker Stop/warm/Start/target barriers are being tested before another full-model run.

- 2026-09-08T16:48:26.696261+00:00: All model-free probes 008–012 preserved. Device0 alone works; synchronized/masked dual-worker variants still show missing records. No full model retry has been started. Testing serialized worker initialization before concurrent target dispatch; accepted/published prefix remains eight.

- 2026-09-08T17:04:35.120519+00:00: Native per-worker gpu-input restriction failed reproducibility and is not admitted. Two independent profiler sessions passed model-free two-device tests, including explicit both-workers-complete-before-either-Stop barrier. Cross-device perturbation test is running. No full-model attempt006 or runtime021 has been created. All13–20 probe outputs are checkpointed.

- 2026-09-08T17:32:23.396498+00:00: Frozen runtime021 (17 tools) and analysis008 (7 tools) passed native two-session, cross-device, MP pipe/marker, supervised exit, lossless-union and independent provenance checks. Scheduler013 is prepared to start capture09 attempt006 using two independent native collectors around the unchanged single DP2 service GPU workers. Original DB/CSV sources are retained; combined data is explicitly derived with exact original-cell/byte audit. Eight accepted prefix captures were reverified. Full-model effectiveness remains to be validated.

- 2026-09-08T17:37:26.047136+00:00: Scheduler013 actually started capture09 attempt006 at 17:33:45.548799 UTC. Native wrapper processes for rank0/rank1 are present; model initialization is underway. Health monitor007 handles both historical single-session and current independent-session layouts. Start checkpoint and recovery instructions updated; accepted prefix remains eight.

- 2026-09-08T17:42:30.993050+00:00: Actual full-model capture09 attempt006 now has positive native PMC files for both worker PIDs930501/930503 on devices0/1; bounded native header/PID/device/GRBM payload prefixes were verified. Original warmups are active; this is not closed capture acceptance. All five prior failed raw attempts plus completed diagnostics (4,493,883,361 original bytes) were losslessly archived, archive roundtrip verified, and Release upload is running.

- 2026-09-08T17:43:39.890560+00:00: Closed capture09 attempts001–005 and completed diagnostic raw sources (688 members, 4,493,883,361 bytes) published to perf-trace-batch8-r08-capture09-prehealth-failures-20260908-001. All remote asset SHA256 rechecked. Only the 985 MB verified upload cache was removed; every original failed raw file and diagnostic remains on NFS. These failed attempts do not count toward R08 acceptance.

- 2026-09-08T17:44:11.582297+00:00: 09_chunk_gated_delta_rule_fwd_kernel_h_blockdim64_pmc_write attempt_006 passed both-device native prehealth and released the original four requests per rank in exact observed R07 admission order. Warmup native reset recorded on ranks []. Complete live marker and closed native attribution audits are still required.

- 2026-09-08T17:52:58.407619+00:00: Capture 09 attempt 006 has complete live marker coverage for all eight requests: exactly 784 first-prefill and 784 first-decode targets per request (12,544 total), two GPU worker PIDs, no missing/duplicate targets, and both first-phase orders match R07. This is a live-prefix checkpoint; closed native DB/PMC attribution is still pending. Both native PMC files continue growing. Previous measured-start and failed-source Release proof are verified on remote main at 84cf07cdcd36bf4c823bb785c09d9304f0f3acd1.

2026-09-08T17:55:44.229955Z: Capture 09 attempt_006 completed all eight original measured requests, HTTP 200 and 1024 tokens each, total 8192, zero failed requests; both native rank stop events are retained. Measured replay duration 797.483 seconds is diagnostic only, not R07 observed latency. Native export and independent attribution are still required.

- 2026-09-08T17:58:03.083283+00:00: Capture 09 attempt_006 completed both independent native collectors normally, return code 0, no signals, no timeout or forced group cleanup. All eight original requests completed. Original DB/CSV and collector logs remain on NFS. Lossless union verification and independent native attribution remain pending.

- 2026-09-08T18:05:31.597454+00:00: Recovery status refreshed after the actual runtime021 full model workload and both independent native collectors completed normally. Native union verification is currently CPU active; no further GPU workload has started. An outdated diagnostic-stage field saying full DP2 integration was not implemented is superseded by these actual observations. This is not capture acceptance.

- 2026-09-08T18:13:44.603558+00:00: Capture09 attempt006 lossless union produced after both native collectors closed: 30,645,909 original native rows and 21,661 original CSV data lines retained with original session/row/line provenance. Derived DB SHA-256 bc15a83f9678f801049d37541729c306e3cd95249c8454f97325e505c7ff0965 independently matches a bounded read-only sequential pass (4.953 s). The I/O prefetch does not replace SQLite checks or independent native attribution, and this checkpoint does not claim capture acceptance.
