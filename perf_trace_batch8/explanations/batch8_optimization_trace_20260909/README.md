# Batch8 双卡调度的固定 trace 案例报告

重点：8 个请求怎样分给两个完整模型副本，各卡如何形成 B1–B4 动态 batch，以及 512-token 长 prefill 预算如何影响 kernel 路径。

- 在线阅读：[完整中文报告](REPORT.md)。
- 本地交互阅读：[下载独立 HTML](https://github.com/cspool/auto_trace/releases/download/perf-trace-batch8-dp2-scheduling-report-20260909/REPORT.html) 后用浏览器打开；图表和交互数据已内嵌，可离线查看。
- 打印阅读：[下载 15 页 PDF](https://github.com/cspool/auto_trace/releases/download/perf-trace-batch8-dp2-scheduling-report-20260909/Batch8_DP2_Scheduling_Report.pdf)。
- 完整产物：[下载 ZIP](https://github.com/cspool/auto_trace/releases/download/perf-trace-batch8-dp2-scheduling-report-20260909/Batch8_DP2_Scheduling_Report.zip)；[Release 与校验和](https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-dp2-scheduling-report-20260909)。
- 原始 R10 交互时间线：[下载 ZIP](https://github.com/cspool/auto_trace/releases/download/perf-trace-batch8-r10-complete-20260908/R10_offline_acceptance.zip)，解压后打开 `acceptance/index.html`。

采用仓库 [build-optimization-trace-report](../../../perf_trace/skills/build-optimization-trace-report/SKILL.md) skill。使用固定例子，全部 8 请求均有完整声明范围内的 trace。全量 kernel / process / request 表、原始 HIP launch 参数、输入 SHA256、源码快照、生成器和审计均随报告保存。

发布版本对应提交 `b491a616a30694dd436d8af183e23a185268afcf`。Release 五个文件的大小与 GitHub 服务端 SHA256 均已核对；ZIP 内所有文件逐项核对通过。发布回执见 [PUBLICATION_COMPLETE.json](PUBLICATION_COMPLETE.json)，完整日志见 [publication.log](publication.log)，归档文件清单与校验和保存在 `publication_receipts/`。
