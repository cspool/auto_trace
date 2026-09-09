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

- 2026-09-09T01:50:27.993366+00:00: 按用户反馈开始可读性修订：图 A 折叠客户端长区间并放大 Marker；图 S 将散点改为大信息矩形，压缩留白。原始发布回执保存在 publication_receipts/v1，固定 trace 数据和计量口径沿用已验收版本。

- 2026-09-09T01:56:26.931238+00:00: v2 图 A 已将 8 个客户端长区间折叠为两块矩形，显示上限 260 秒，16 个 Marker 宽度统一乘 12 并在矩形内标注原始时长。图 S 为两行共 16 个等宽大矩形，按每卡原始启动顺序排列，矩形占主图区 77.08%、整张图 51.91%。独立审计核对 23,660 个 kernel、所有原始时间与启动配置；HTML 八请求控件、离线加载及 15 页 PDF 检查通过。已检查 PNG、组合图、浏览器截图与 PDF 第 3 / 5 页。生成代码、日志、审计和产物提交后发布独立 v2 Release。

- 2026-09-09T01:57:50.232012+00:00: v2 报告提交 `66f3e96a60d375e4ff09c0eb4bca30d1c71f684b` 已 push 且远端 main 一致。v2 Release 五个文件已发布并核对大小与服务端 SHA256；ZIP 内 81 个成员完成完整性检查。发布地址：https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-dp2-scheduling-report-20260909-v2。回执、文件清单及完整发布日志一并提交到远程仓库。

- 2026-09-09T02:06:17.302915+00:00: 用户要求图 S 恢复真实时间轴并保持大信息矩形，补充 8 请求最初选卡步骤及 OOM 出现与处理。开始 v3 修订；v2 发布回执已归档。历史 OOM 依据目标仓库 2026-08-11 消融记录，其原始失败日志目录当前不可访问，报告将与本次固定 trace 的成功记录分别注明。

- 2026-09-09T02:15:16.231593+00:00: 按用户进一步澄清，报告改以实际调度设计为主线：沿用官方 DP 请求负载选卡（4×waiting+running、本地计数更新、同分扫描），各卡独立 continuous batching，长度三档 prefill、Graph cap16 与 chunk_o 调优保护；4+4 trace 仅作执行示意。图 S 恢复两个真实秒数时间图，16 个大信息矩形与原始 (time,B) 圆点对齐且互不遮挡。新增 4 个历史 OOM 场景及 6 行消融结果，注明仓库记录来源和原始失败日志当前不可访问。独立审计通过 23,660 个 kernel、16 个标注、8 请求和设计源码哈希；HTML 离线正常，17 页 PDF 无文字越界，已视觉检查调度图、报告开头和 OOM 章节。首次图 S 审计 JSON 输出遇到 NumPy int64 序列化错误，修正为普通数值后通过，失败日志保留于 scheduling_revision3_attempt001.log。

- 2026-09-09T02:16:37.772589+00:00: v3 完整报告提交 `41c5149e82f95400c522a6369215aea9b3afcebd` 已 push 并确认远端 main 一致。v3 Release 的 HTML、17 页 PDF、ZIP、清单及 SHA256SUMS 共五个资产已全部上传，大小与服务端 SHA256 均核对通过；ZIP 96 个成员通过逐项校验。发布日志和回执继续提交到远程仓库。地址：https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-dp2-scheduling-report-20260909-v3。
