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
duration 的累加值。数字之间的关系如下：

- **`GQA6 direct`（P1、P6）**：`GQA6` 表示 1 个 KV head 服务 6 个 Q heads；
  `6=3 组×2 heads/CTA`。一个 CTA（GPU thread block）同时处理
  `32 个 query 位置×2 heads=64 行`，
  每个 64-token K/V tile 再分成 `2×32` 做数值更新。这组参数让 direct kernel
  覆盖完整 GQA6，并在当前 Q block 的 causal 边界停止扫描未来 K/V。
- **`page784`（P2–P5）**：`784=12×64+16`。前 `768` tokens 走 64 对齐的
  paged attention，剩余 `16` tokens 打包后走 contiguous attention，最后用
  FP32 log-sum-exp 合并。组合后可复用 64-token kernel，而不必展开完整 KV cache。
- **`MMAC GEMM`（紫色）**：`M=4096` 是完整 prefill chunk 的 token 行数，
  不是模型 hidden size；固定这一维后可直接复用已选好的 TunableOp solution。

GQA6 direct 仅用于 gfx936/BF16、`head_dim=256`、`page=784`、单序列且
`q≥128` 的长 prefill；这里 `256` 是每个 head 的特征宽度，`128` 是启用长
query 路径的最小 query-token 数。其他情况回退原 attention 路径。

`P6` 是较短的末尾 chunk，所以它明显更短；不能拿它与完整 chunk 的柱长相除，
当作 GQA6 的加速倍数。

对应方向的历史闭环结果（独立 benchmark）：H11.5 GQA6 prefill 相对 R24 的
小样本 TTFT 降幅，在 4–8K、8–16K、16–32K 三档分别为 `15.89%`、
`20.47%`、`24.65%`。三档表示输入 token 长度；TTFT 是“请求到首 token”的
时间，因此这些数字表示 prefill 后首 token 更早返回，不表示 decode 单 token
快了同样比例。

## C. Decode：两条专用 GEMV 是主要优化落点

[![子图 C：逐 token Decode 组成](./panel_c_decode_composition.png)](./panel_c_decode_composition.svg)

每根柱代表一个 decode step。这里 `K` 是每个输出值需要点积的输入长度，`M`
是输出通道数，`n=1` 表示一次只计算 1 个 decode token；gfx936 的 1 个 wave
包含 64 个并行 lanes：

- **`K5120 GEMV`（红色）**：在 shape gate 中，`M` 是权重矩阵的输出行数，
  `CTA 数=M/每 CTA 行数`。`M=96` 时每 CTA 算 4 行，共 24 CTAs；其余 shape
  gate 值 `M∈{14336,16384,34816,248320}` 每 CTA 算 2 行，例如 `gate_up_proj` 的
  `M=34816` 启动 17408 CTAs。
  `K=5120=640 threads×8 个 BF16 元素`，所以每个 thread 恰好负责一个 8 元素块。
- **`K17408 GEMV`（橙色）**：`17408` 个 BF16 元素分成 2176 个 8 元素块。
  一个 1024-thread CTA 中，threads `0–127` 各处理 3 块，其余 896 threads 各
  处理 2 块，即 `128×3+896×2=2176`；随后 `1024=16 waves×64 lanes` 归约出
  1 个输出行。`M=5120`，因此共启动 5120 CTAs，完成
  `[1,17408]→[1,5120]`。

单 token 的具体 MLP 算子链是：

```text
hidden [1,5120]
  → gate_up_proj: W[34816,5120]，K5120 GEMV
  → split: gate/up 各 [1,17408]
  → act_and_mul: SiLU(gate) ⊙ up → [1,17408]
  → down_proj: W[5120,17408]，K17408 GEMV
  → hidden [1,5120]
```

两条 GEMV 组合后覆盖 MLP 两端的大投影；中间的 `split + act_and_mul` 仍是独立
算子，文档不把它计作 GEMV 融合收益。

两者仅在 gfx936、BF16、单 token、无 bias、连续且 16-byte 对齐时启用；其余
shape 回退原 GEMM。本次 trace 中两条 GEMV 占 decode kernel 累加时间的
`76.0%`，加上 MMAC GEMM 为 `84.0%`；这是**时间组成占比**，不是加速比。
`41.574 ms` 是 23 个 decode steps 的平均 kernel 累加值，也不是单步 wall-clock。

因此，降低单 Batch TPOT 的首要目标很清楚：优先缩短反复出现在每个 token
中的 K5120 和 K17408 投影，而不是只优化一次性的初始化工作。

对应的历史闭环结果（独立 benchmark）如下。TPOT 是生成一个输出 token 的平均
时间；吞吐是完整请求每秒生成的 token 数：

| 对比 | 4–8K | 8–16K | 16–32K |
| --- | ---: | ---: | ---: |
| H10.8 K5120 GEMV 相对 H11.5：小样本 TPOT 降幅 | `5.23%` | `5.03%` | `4.91%` |
| H11.5 + H10.8 相对 R24 full 均值：吞吐提升 | `6.744%` | `9.540%` | `13.724%` |

这里的 **H11.5 + H10.8** 特指在同一 build 中同时启用 GQA6 prefill 与
K5120 decode 快路径：它能同时缩短首 token 等待和后续逐 token 生成。组合收益
不能用两个降幅直接相加；表中的 full 吞吐提升是重新运行完整请求得到的联合结果。

`full×3` 表示连续 3 轮完整测试，每轮 150 个请求；`450/450` 表示全部成功。
TTFT/TPOT SLA 通过表示延迟未越过规定上限，accuracy `K=1.0` 表示固定精度
评测没有扣分。这些是本地闭环结果，不是平台官方分数。

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
