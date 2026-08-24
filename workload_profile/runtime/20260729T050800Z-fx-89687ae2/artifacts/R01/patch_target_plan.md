# R01 Trace Patch Target Plan

运行：`20260729T050800Z-fx-89687ae2`  
源码：`pra2026-bh408@3d03614452cd0a925abc82a7686560ff80252dfa`  
模型：Qwen3.5-27B，64 层（48 层 `linear_attention`、16 层 `full_attention`）

## Question

在真实 Qwen3.5-27B vLLM V1 ROCm/DCU serving 请求中：

- 当前是哪个请求、engine 调用和逐请求阶段（prefill、decode、mixed 或 empty）？
- scheduler 如何把 token/cache 决策变成 worker batch 和 model forward？
- 64 个 hybrid decoder layer 中，哪个 `layer_idx` 选择了 GDN linear-attention，哪个选择了 ROCm full-attention？
- KV cache 如何命中、分配、复用和释放？
- sampler/output 如何产生 token 并结束请求？
- 哪些最小元数据足以证明这些状态变化，同时不复制 tensor 内容、不触发设备同步？

未选择 API ingress：当前问题从 `EngineCore` 开始，scheduler 已持有 `request_id`；API 层不能解释模型算法路径。

## Patch targets

1. `EngineCore.step` 和 `EngineCore.step_with_batch_queue`

   why：这是同时覆盖同步路径、异步 batch queue 填充/排空、scheduler 更新和 client output 的最高语义边界。

   join keys：`run_id`、`contract_id`、本地单调 `engine_call_id`、`event_index`、`rank`。

   fields：入口名称、queue depth 前后值、是否仍有请求、是否执行模型、返回/完成 output 数、`duration_ns`。

2. `Scheduler.schedule` 和 `Scheduler.update_from_output`

   why：前者作出请求/token/cache 决策并推进 computed-token 状态，后者用同一个 `SchedulerOutput` 回收 sample、finish 和 client output。

   join keys：`engine_call_id`、本地 `schedule_id`、`batch_id`、`request_id`。

   fields：有序请求、逐请求 phase、batch phase、scheduler prompt length、generated/computed 前后值、scheduled token 数、waiting/running 前后值、preempt/finish、host-side token id/count、finish reason。

3. `GPUModelRunner._prepare_inputs` 和 `_build_attention_metadata`

   why：这是 scheduler token 数首次成为实际 request position、q/past/kv length 和 attention metadata 的位置。

   join keys：`batch_id`、`forward_id`、`request_id`、`batch_position`、`rank/worker/device`。

   fields：请求顺序、prefill/decode 数、逐请求 token/q/past/kv length、unpadded/padded token 数、metadata type，以及 block table/slot mapping 的 shape。

4. `GPUModelRunner.execute_model`

   why：把一个 scheduler batch 连接到一个 worker forward，并包围全部 layer/helper 事件。

   join keys：`batch_id`、`forward_id`、`rank/worker/device`。

   fields：batch phase、请求数、scheduled token 总数、输入 shape 摘要、result type、是否真正执行、`duration_ns`。

5. `Qwen3_5DecoderLayer.forward`（继承自 `Qwen3NextDecoderLayer.forward`）

   why：这是证明 64 层实际调用以及 `layer_type` 分支选择的最小公共边界。

   join keys：`batch_id`、`forward_id`、`layer_idx`、`layer_occurrence`、`rank/worker`。

   fields：`layer_type`、phase、q/past/kv length、hidden/residual/position 输入输出 shape、`duration_ns`。

   注意：production `torch.compile` 会绕过 Python layer wrapper。层级事件必须来自单独声明、相同确定性请求的 `--enforce-eager` trace；compiled 模式零行不能解释为“层未执行”。

6. `Qwen3_5GatedDeltaNet.forward`

   why：layer event 只能说明选择了 `linear_attention`，此边界进一步证明 Qwen3.5 GDN helper 和 recurrent/cache 路径确实运行。

   join keys：layer key 加 `gdn_call_id`。

   fields：module prefix、phase、q/past/kv length、hidden/output shape、cache/state 是否存在及 shape 摘要、`duration_ns`。

7. `RocmAiterUnifiedAttentionImpl.forward`

   why：证明 full-attention 层采用的真实 ROCm backend、GQA head layout 和 KV metadata。

   join keys：layer key 加 `attention_call_id`、`layer_name`、device。

   fields：backend/metadata type、q/past/kv length、24 query heads、4 KV heads、head dim 256、Q/K/V/output/cache/block/slot shape、cascade/common-prefix 摘要。

8. `KVCacheManager.get_computed_blocks`、`allocate_slots`、`free`、`take_new_block_ids`

   why：四个操作分别覆盖 cache hit/reuse、分配、释放和新 block 物化。

   join keys：`schedule_id`、`batch_id`、`request_id`、本地 `cache_event_id`。

   fields：操作、hit、computed/new token 数、allocated/reused/freed block 数、各 cache group 的 table length、free block 与 usage 前后值、是否成功。

9. `GPUModelRunner.sample_tokens`、`Sampler.forward` 和 host-side `Scheduler.update_from_output`

   why：worker/sampler 只证明调用和 shape；精确的小 token id、emitted count 和 finish reason 在 host-side scheduler output 处安全采集。

   join keys：`schedule_id`、`batch_id`、`forward_id`、`request_id`、`output_ordinal`。

   fields：请求数、logits/sample shape、sampling config、host-side token id、单次和累计 output count、finish/stop reason、result type。

### Join contract

- 每条事件都有 `run_id`、`contract_id`、source revision、`trace_mode`、进程内单调 `event_index`、PID/rank/worker/device。
- `engine_call_id` 不等同于 `forward_id`；异步 queue 中 schedule 和 update 也不要求相邻。
- `schedule_id` 绑定原始 `SchedulerOutput`；`batch_id` 由 CPU metadata 中的 `(request_id, num_computed_before, num_scheduled_tokens)` 规范化后计算。
- batch 先计算逐请求 phase，再汇总为 prefill/decode/mixed/empty；不能仅以 batch 总 token 数推断。
- benchmark token count 和 scheduler/template token count 分开命名，不能假设相等。
- layer key 为 `(run, contract, rank, worker, forward_id, layer_idx, layer_occurrence)`；timestamp 不能单独作为 join key。

## Do not patch

- 不 patch 所有搜索命中的 scheduler helper，也不 patch 所有 ATen/Triton/AITER/HIP/DCU kernel。
- 不 patch 与本问题无关的通用 MLP、norm、linear、embedding 和 LM head。
- 不把既存 GQA6、page784、LLMM1、TunableOp、M-RoPE 等优化专用事件当成本 R01 的通用 layer/selection 证据。
- 不保存 hidden/logits/KV cache/block table 等 tensor 内容，只保存 shape、dtype、device、count 和短 ID。
- hot loop 中禁止 `.cpu()`、`.numpy()`、`.item()` 和 device-tensor `.tolist()`；精确 token id 只从已经在 host 侧的 scheduler output 获取。
- compiled 模式缺少 Python wrapper 行时不得补造事件或推断层被跳过。

## Validation

1. 固定 `temperature=0`、`do_sample=false`、`seed=0` 的同一请求，比较无 wrapper、compiled-safe wrapper 和单独声明的 enforce-eager trace；completed、failed、generated text、input/output lengths 必须完全相等。
2. engine、model、attention begin/end key set 必须守恒；每个 `SchedulerOutput` 必须有同一 `schedule_id/batch_id` 的 schedule/update。
3. 每个非空 eager forward 必须有 64 个 layer event：48 个 linear-attention、16 个 full-attention；GDN 和 full-attention helper 数分别与对应 layer 数一致。
4. 所有长度明确的记录满足 `past_len + q_len == kv_len`；chunked prefill 的 computed/cache 状态在 decode 前单调推进。
5. cache allocated/reused/freed 数与 free-block 前后值可对账；正常完成以及范围内的 abort/preemption 必须能看到 free。
6. 所有目标事件必须具备可连接的 key；不能依赖跨进程时间顺序。
7. 静态检查 wrapper 不含 tensor 内容复制或设备同步；patch exception 只能形成显式 `patch_error`，不能改变原返回值。
8. 当前固定 contract 的 single-request 验证已通过。该 contract 明确 `max_concurrency=1`，因此不声称并发覆盖；若下游扩大为一般 batched/concurrent serving，必须追加独立的两请求验证。

## Real-run evidence result

- 当前源码 HEAD 与证据 contract 都是 `3d03614452cd0a925abc82a7686560ff80252dfa`。
- production baseline、compiled-instrumented、enforce-eager 三次输出完全一致：1 completed、0 failed、20574 benchmark input tokens、23 output tokens。
- compiled trace：712 条事件、0 `patch_error`；layer/GDN Python wrapper 为 0，按实际 visibility gap 处理。
- enforce-eager trace：8744 条事件、0 `patch_error`；29 个非空 forward（6 prefill + 23 decode），共 1856 个 layer event = `29 × 64`，其中 1392 个 linear-attention/GDN、464 个 full-attention。
- 6 个 prefill q length 为 `4096, 4096, 4096, 4096, 4096, 105`；23 个 decode q length 均为 1；全部 layer transition 满足 `past + q = kv`。
- cache allocation transition 和最终 host output 已可见；既存 wrapper 未 patch `KVCacheManager.free`，所以 T08 明确补入该边界，未伪造释放证据。

完整机器可读计划、验证和证据哈希分别见 `patch_target_plan.json`、`validation_report.json`、`evidence_manifest.json`。
