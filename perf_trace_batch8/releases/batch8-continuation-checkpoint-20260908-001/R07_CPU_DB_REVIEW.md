# R07 异机 CPU 数据库校验

校验时间：2026-09-08 UTC。原定机器时间窗口：04:18:09–12:18:09 UTC，没有重置。

结论：原始 DB 与已恢复的 R07 分析数据没有发现损坏或行对应错误。历史超过 30 小时没有结果，证据强烈指向 HIPProf 收尾阶段的 SQLite 范围关联查询效率问题，而不是必须重跑模型或等待同一查询继续扫描。没有历史 C++ 调用栈，因此不把具体函数归因写成已完全证明。

- 原始 DB：8,958,377,984 字节，SHA256 `0ea77cdac40926182c4e04fc29e687e62df9b2cac50296c7e399817c583690b0`，只读 `quick_check` 通过，耗时 10.90 秒。
- 全量核对：12,544 条进程区间、316,802 条 HIP 调用、23,660 条严格归属内核的原生表/行号/关联编号/时间/PID/设备字段全部一致。对应核对耗时约 9.4 秒。
- 在副本上复现修复：数据库修复部分 81.834 秒，包含复制及前后哈希的整体过程 132.545 秒。重建 HIPTXOPS 两个工作进程分别为 234,444 / 234,832 行，TRACE_COUNTER 为 25 行。
- 修复结果 SHA256 `14a1e21b4bf5a0b29b11a62c4d000cac4979aa5af4ddc687f614bdab4f3179cd`，与历史恢复结果完全一致，原始 DB 哈希保持不变。

原库的查询计划对 HIP 表仅按 tid 使用临时索引；加入 `(tid, _Index)` 等组合索引并更新统计信息后，计划可以使用内核编号范围和精确编号查找。历史诊断同时记录了持续 CPU 运行、约 8.13 TB 累计读取调用字节和没有输出增长，这与低效范围关联扫描吻合，不等同于进程死锁。

R08 已采用经本机双卡探针验证的 `--hip-trace --hiptx-trace --pmc --no-export` 路径。探针保留原生 DB 和计数器 CSV，未生成 HIPTXOPS 派生关联表，13 秒左右正常退出。后续分析直接使用原生编号、精确硬件时间标识、PID/设备与完整内核名称做唯一关联，所有回放时间只作为采集诊断，不替换 R07 观测延迟。

原始证据与详细结果：
- `r07_cpu_validation_001/CPU_DB_VALIDATION.json`
- `r07_cpu_validation_001/prepare_manifest.json`
- `r07_cpu_validation_001/query_plan_comparison.json`
- `r07_live_diagnostic_methods/diagnostic_bundle/DIAGNOSTIC_SUMMARY.json`
- `r07_cpu_validation_001.log`
