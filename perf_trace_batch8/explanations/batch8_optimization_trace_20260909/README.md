# Batch8 双卡调度的固定 trace 案例报告

重点：8 个请求怎样分给两个完整模型副本，各卡如何形成 B1–B4 动态 batch，以及 512-token 长 prefill 预算如何影响 kernel 路径。

- 在线阅读：[完整中文报告](REPORT.md)。
- 本地交互阅读：下载完整交付包后打开 `REPORT.html`；主报告 HTML 的图表和交互数据已内嵌，可独立离线打开。
- 打印阅读：`Batch8_DP2_Scheduling_Report.pdf`。
- 原始 R10 交互时间线：[下载 ZIP](https://github.com/cspool/auto_trace/releases/download/perf-trace-batch8-r10-complete-20260908/R10_offline_acceptance.zip)，解压后打开 `acceptance/index.html`。

采用仓库 [build-optimization-trace-report](../../../perf_trace/skills/build-optimization-trace-report/SKILL.md) skill。使用固定例子，全部 8 请求均有完整声明范围内的 trace。全量 kernel / process / request 表、原始 HIP launch 参数、输入 SHA256、源码快照、生成器和审计均随报告保存。
