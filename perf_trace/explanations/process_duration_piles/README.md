# Process 分堆与资源窗口可视化

高延迟图保留采集范围内的 Process 分布，以梯形外框组织各堆时间线。
资源图只展示成功关联硬件指标的窗口，隐藏缺失项和空堆；无可显示数据的
时间区间用 `»` 跳过，原始时间戳、覆盖率分母和堆排名保留。

筛选条件为每种 Process 累计时长占所有 Process 时长求和严格超过10%，
每种类型按相近时长分5堆，再按堆总时长全局排序。两个视图共享原始十段
时间边界，并支持折叠、缩放、平移和精确纳秒定位。

| 当前默认资源视图 | 有效实例 | 可见堆 | 原始高延迟堆 |
|---|---:|---:|---:|
| 单 batch | 10 | 7 | 15 |
| Batch8 | 992 | 9 | 15 |

Batch8 已离线恢复36个R08归一化与审计文件，核对4608条方向性计数记录：
2304条读带宽和1578条写带宽可计算；其余726条写计数保持未知。
归一化参考1206 GB/s来自用户提供的gfx936微基准文档，不是厂商标称规格。
读写重放不相加，也不使用R07 Process时长作为重放带宽分母。

L2命中率、请求速率和单 batch 的L2投影吞吐量分别标注，均不冒充已验证
的L2带宽利用率。资源高度与数值连续成比例，采样过短的ε仅为非实测标记。

[工具与复现说明](../../scripts/process_pile_assets/README.md) ·
[浏览器检查](validation/BROWSER_AUDIT.json) ·
[带宽独立复核](validation/BANDWIDTH_AUDIT.json) ·
[默认资源窗口统计](validation/RESOURCE_WINDOW_VISIBILITY.json)

生成HTML和下载归档位于工作目录下的`local_reports/`，不纳入Git。

## Workflow 和 skill 入口

[单 batch Workflow05](../../workflows/05_workflow04_guided_selective_process_trace_and_resource_gap_analysis.md) · [Batch8 Workflow05](../../../perf_trace_batch8/workflows/05_workflow04_guided_selective_process_trace_and_resource_gap_analysis.md) · [目标、方法与可视化合同](../../skills/qwen-dcu-workflow05-trace-visualization-reporting/references/process-resource-contract.md)

R08、R09、R10 skill 共用同一方法合同。正式运行身份/拓扑/hand-off细节作为专门参考，已有证据的恢复不再误入fresh采集路径。当前离线生成器作为已验证实现参考；fresh R09表的原生渲染入口需单独证明支持新目标，不能由离线构建结果代替正式完成。
