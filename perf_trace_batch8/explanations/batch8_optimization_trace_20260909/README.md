# Batch8 双卡调度设计与 OOM 处理报告

重点：实际逐请求负载选卡、每卡 continuous batching、按长度分档的 prefill 预算与 OOM 处理；固定 4+4 trace 展示调度和 kernel 的时间线。

- 在线阅读：[完整中文报告](REPORT.md)。
- 本地交互阅读：[下载独立 HTML](https://github.com/cspool/auto_trace/releases/download/perf-trace-batch8-dp2-scheduling-report-20260909-v4/REPORT.html) 后用浏览器打开；图表和交互数据已内嵌。
- 打印阅读：[下载 PDF](https://github.com/cspool/auto_trace/releases/download/perf-trace-batch8-dp2-scheduling-report-20260909-v4/Batch8_DP2_Scheduling_Report.pdf)。
- 完整产物：[v4 Release 与 ZIP](https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-dp2-scheduling-report-20260909-v4)。
- 原始 R10 交互时间线：[下载 ZIP](https://github.com/cspool/auto_trace/releases/download/perf-trace-batch8-r10-complete-20260908/R10_offline_acceptance.zip)，解压后打开 `acceptance/index.html`。

采用仓库 [build-optimization-trace-report](../../../perf_trace/skills/build-optimization-trace-report/SKILL.md) skill。使用固定例子，全部 8 请求均有完整声明范围内的 trace。全量 kernel / process / request 表、原始 HIP launch 参数、输入 SHA256、源码快照、生成器和审计均随报告保存。
