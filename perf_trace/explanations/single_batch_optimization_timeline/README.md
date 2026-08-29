# 单 Batch 主要优化：按 A–D 分图阅读

这组图回答两个问题：一次优化后的单请求是怎样执行的，以及主要优化落在
prefill 还是 decode。建议按 **A → B → C → D** 阅读：先定位两个阶段，再看
prefill 路由、decode 主成本，最后放大到一个 decode layer。

> A–D 展示的是同一次**优化后 trace**，不是 before/after 曲线。图旁的历史
> 收益来自独立的固定 benchmark；不能用图中柱长直接计算优化幅度。

<details>
<summary>展开完整 A–D 总览图</summary>

[![完整单 Batch 优化时间线](./single_batch_optimization_timeline.png)](./single_batch_optimization_timeline.svg)

</details>

## A. 请求全貌：先区分 prefill 和 decode

[![子图 A：请求级时间线](./panel_a_request_overview.png)](./panel_a_request_overview.svg)

怎么看：

- 上排矩形是 29 次 forward：橙色 `P1–P6` 是 6 个分块 prefill，蓝色
  `D1–D23` 是 23 个逐 token decode。
- 下排短线是这些 forward 归属到的 strict-owned GPU kernels，用来确认 GPU
  工作实际落在什么位置。
- 本次观测中，prefill span 约 `5.692 s`，decode span 约 `11.678 s`，请求
  span 约 `17.463 s`。

结论：这个请求先用 6 个 chunk 处理输入，再连续生成 23 个 token。A 只负责
建立全局位置；它是带 eager instrumentation 的观测时间，不代表生产 E2E，
也不单独证明某项优化带来多少收益。

## B. Prefill：GQA6 与 page784 分别处理不同 chunk

[![子图 B：Prefill 路由组成](./panel_b_prefill_routes.png)](./panel_b_prefill_routes.svg)

每根横柱对应一个 prefill forward，长度是该 forward 内 strict-owned kernel
duration 的累加值。这里主要看两条 attention 路由：

| 图中位置 | 实际路由 | 主要优化 |
| --- | --- | --- |
| `P1`、`P6` 的蓝色 `GQA6 direct` | Wide-causal GQA6 | 每个 CTA 处理 2 个 Q head，按 32-token Q block 只扫描可见的 56-token K/V tiles；仅用于 gfx936/BF16、head_dim=256、page=784、单序列且 q≥128 的 GQA6 prefill |
| `P2–P5` 的橙/黄/粉色 | page784 `main / tail / pack+merge` | 将不能按 64 对齐的 784-token page 拆为 `768 main + 16 tail`，分别计算后用 FP32 log-sum-exp 合并，无需展开完整 KV cache |
| 各柱中的紫色 | `MMAC GEMM` | M=4096 prefill linear 使用冻结的 TunableOp solution，作为 attention 之外的配套优化 |

`P6` 是较短的末尾 chunk，所以它明显更短；不能拿它与完整 chunk 的柱长相除，
当作 GQA6 的加速倍数。

对应的历史闭环结果（独立 benchmark）：H11.5 GQA6 prefill 相对 R24 的小样本
TTFT 降幅，在 4–8K、8–16K、16–32K 三档分别为 `15.89%`、`20.47%`、
`24.65%`。

## C. Decode：两条专用 GEMV 是主要优化落点

[![子图 C：逐 token Decode 组成](./panel_c_decode_composition.png)](./panel_c_decode_composition.svg)

每根柱代表一个 decode step。23 根柱的组成基本稳定，说明优化不是只偶然命中
某一个 token：

- 红色 `K5120 GEMV` 最大：为单 token 投影提供 640-thread pair-reduction
  kernel，并按输出行数选择 row2/row4。
- 橙色 `K17408 GEMV` 第二：为 `K=17408` 输出投影提供专用 BF16 kernel，
  使用局部 FP32 FMA 累加和固定归约。
- 两条路径都只在冻结的 dtype、shape、连续性和对齐条件满足时命中；否则回退
  原 GEMM 路径。
- 两条专用 GEMV 合计占本次 decode strict-owned GPU kernel 时间的 `76.0%`；
  连同紫色 `MMAC GEMM` 后为 `84.0%`。单步 kernel 累加均值约 `41.574 ms`。

因此，降低单 Batch TPOT 的首要目标很清楚：优先缩短反复出现在每个 token
中的 K5120 和 K17408 投影，而不是只优化一次性的初始化工作。

对应的历史闭环结果（独立 benchmark）：

| 对比 | 4–8K | 8–16K | 16–32K |
| --- | ---: | ---: | ---: |
| H10.8 K5120 GEMV 相对 H11.5：小样本 TPOT 降幅 | `5.23%` | `5.03%` | `4.91%` |
| H11.5 + H10.8 相对 R24 full 均值：吞吐提升 | `6.744%` | `9.540%` | `13.724%` |

组合版本完成 full×3，共 `450/450` 请求成功，TTFT/TPOT SLA 通过，固定
accuracy 为 `K=1.0`。这些是本地闭环结果，不是平台官方分数。

## D. 单层放大：确认优化 kernel 确实落在执行序列中

[![子图 D：一个 Decode layer 的 kernel 精确位置](./panel_d_decode_layer_zoom.png)](./panel_d_decode_layer_zoom.svg)

D 只放大 `forward 10 / layer 0`。横轴是相对该 layer 开始的时间，纵轴按
kernel 类别分行，因此能直接看到 K5120、K17408、MMAC GEMM、GDN recurrent
以及 RMS/copy 在一次真实 layer 中的启动位置。

这个样本包含 11 个 strict-owned kernels：kernel duration 累加约
`0.601 ms`，layer annotation envelope 约 `4.794 ms`。D 的用途是验证“专用
kernel 已进入目标执行路径”，不是把矩形之间的空隙解释成性能损失。空隙还可能
包含 eager、runtime、异步执行与 tracing 影响，不能称为生产 GPU idle。

## 配套优化如何理解

GDN recurrent、连续 M-RoPE copy、RMS/copy 和若干严格 shape-gated 路径也在
减少计算或调度开销；它们在 B–D 中作为组成项出现。由于本图没有为这些路径构造
独立 before/after 对照，文档不从单次 trace 推导它们各自的端到端收益。

## 证据边界与复现

- B、C 是 strict-owned kernel duration 的**累加值**，不是 wall-clock；异步
  尾部可能越过上层 annotation envelope。
- process 区间可能嵌套，不能相加后当作请求耗时。
- A–D 来自已接受 trace，不重新运行模型、profiler 或加速卡。输入是
  [`replay002` acceptance 归档](../../acceptance/workflow01-10-fresh-e2e-dcu1-20260806-r10-replay002-all-rectangle-labels.tar.gz)。

复现时运行：

```bash
python perf_trace/explanations/single_batch_optimization_timeline/build_timeline.py
```

脚本会同时生成完整总览图和 A–D 四组独立的 PNG/SVG，文档默认显示 PNG，点击
后可打开 SVG 无损放大。
