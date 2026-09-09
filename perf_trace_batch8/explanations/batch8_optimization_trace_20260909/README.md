# Batch8 双卡调度的固定 trace 案例报告

重点：8 个请求怎样分给两个完整模型副本，各卡如何形成 B1–B4 动态 batch，以及 512-token 长 prefill 预算如何影响 kernel 路径。

- 在线阅读：[完整中文报告](REPORT.md)。
- 本地交互阅读：[下载独立 HTML](https://github.com/cspool/auto_trace/releases/download/perf-trace-batch8-dp2-scheduling-report-20260909-v2/REPORT.html) 后用浏览器打开；图表和交互数据已内嵌。
- 打印阅读：[下载 PDF](https://github.com/cspool/auto_trace/releases/download/perf-trace-batch8-dp2-scheduling-report-20260909-v2/Batch8_DP2_Scheduling_Report.pdf)。
- 完整产物：[v2 Release 与 ZIP](https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-dp2-scheduling-report-20260909-v2)。
- 原始 R10 交互时间线：[下载 ZIP](https://github.com/cspool/auto_trace/releases/download/perf-trace-batch8-r10-complete-20260908/R10_offline_acceptance.zip)，解压后打开 `acceptance/index.html`。

采用仓库 [build-optimization-trace-report](../../../perf_trace/skills/build-optimization-trace-report/SKILL.md) skill。使用固定例子，全部 8 请求均有完整声明范围内的 trace。全量 kernel / process / request 表、原始 HIP launch 参数、输入 SHA256、源码快照、生成器和审计均随报告保存。

可读性修订 v2 已发布，产物对应提交 `66f3e96a60d375e4ff09c0eb4bca30d1c71f684b`。五个下载文件均通过大小与 GitHub 服务端 SHA256 核对；完整发布回执见 [PUBLICATION_COMPLETE.json](PUBLICATION_COMPLETE.json)，日志见 [publication.log](publication.log)。v1 回执保存在 `publication_receipts/v1/`。
