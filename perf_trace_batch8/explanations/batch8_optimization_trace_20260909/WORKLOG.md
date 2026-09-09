# 报告工作记录

- 阅读 build-optimization-trace-report skill 及全部三份引用规则；核对已验收 R09/R10 handoff、清单和输入 SHA256。
- 独立输出全量 kernel / process / request 精简表与 23,660 个原始 HIP 启动参数，保留唯一事件身份、整数时间和匹配规则。
- 首次提取因 HIP context 列索引断言失败而中止（日志 analysis_attempt001.log）；按原始 schema 修正列索引后全部归属检查通过。原始材料未改动。
- 关键统计与代码先提交远端；报告、图表、浏览器检查继续完成。

- 用户明确报告主线为 Batch8 双卡调度，并确认采用固定 trace 作为例子。加入实际 4+4 映射、两个副本的 B1–B4 启动样本、512-token 预算及 MLP 张量尺寸分析。
- 图表按原始数据生成并逐图检查，A/B/D 矩形物理高度均为 56.241 pt，四图组合高 67 英寸。
- 独立审计识别 hipExtModuleLaunchKernel 的 global/localWorkSize 参数格式；保留原始参数，未出现的 gridDim 字段保持为空。首次审计日志保存于 audit_attempt001.log，修正审计器以核对这两类原始格式。

- 2026-09-09T01:36:39.200046+00:00: 中文报告、5 张主图、67 英寸四图组合、八请求交互定位与 15 页 PDF 完成。独立核对 23,660 个唯一 kernel 及 launch 参数；离线 Chromium 检查全部 8 个选择项，0 页面错误、0 外部网络请求；浏览器关闭。PDF 全部页面非空、中文可提取、文字未越出页界；逐图、HTML、PDF 已人工视觉检查。

- 2026-09-09T01:41:18.858580+00:00: 完整报告提交 `b491a616a30694dd436d8af183e23a185268afcf` 已推送并确认远端 main 一致。专用 Release 发布成功：https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-dp2-scheduling-report-20260909；5 个资产均核对大小与服务端 SHA256，ZIP 内 67 个成员通过完整性与清单校验。发布日志、回执、文件清单及下载入口一起提交保存。
