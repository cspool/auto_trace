# Perf Trace

单 batch 的采集、分析与离线可视化工具、Skill 和已封存验收结果。

- **[Process 分堆与资源窗口](explanations/process_duration_piles/README.md)**：>10%累计时长筛选、梯形时间线、仅显示已关联硬件窗口、离线带宽恢复及L2指标。
- **[R10 分组时间线与硬件证据报告](explanations/r10_ranked_timelines/README.md)**：高延迟 Process、设备内 kernel / queue 并发、原始利用率、未知采样间隔和 launch gap；按 Batch8 的梯形、折叠、前 20 导航与精确 ns 要求补齐。
- **[下载完整离线报告](https://github.com/cspool/auto_trace/releases/tag/perf-trace-r10-ranked-timelines-20260909-v1)**：解压 ZIP 后打开 `index.html`；原始数据、完整 Perfetto JSON、源码与审计随包保留。
- [单 batch 优化说明](explanations/single_batch_optimization_timeline/README.md)。
- [恢复原始完整目录](README_RESTORE_FULL_TREE.md)。

当前分组报告使用已封存的 20260806 DCU1 单 batch trace。它是展示补充，不是新的模型运行，也不提供 Batch8 双卡调度测量。
