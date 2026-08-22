# 05 Fresh R01–R10 Process Trace And Resource-gap Analysis

## 目标与唯一运行模式

本工作流只允许 `workflow01-10-fresh-e2e`：从 R01 开始，在同一个 scheduler run
和同一个 lineage 中串行执行到 R10。不得导入、复用或继承其他 runtime 的
R01–R05 ledger、trace、PMC、分析表或可视化结果。

固定模式为：

```text
evidence_acquisition_mode=fresh_no_prior_runtime_reuse
analysis_strategy=fresh_run_full_request_e2e_timeline
measurement_contract_policy=same_run_same_request
execution_topology=<由 adapt-workflows 的 hash-pinned trace profile 显式提供>
physical_devices=<trace_profile.topology.physical_devices>
HIP_VISIBLE_DEVICES=<trace_profile.topology.hip_visible_devices>
CUDA_VISIBLE_DEVICES=<trace_profile.topology.cuda_visible_devices>
tensor_parallel_size=<trace_profile.topology.tensor_parallel_size>
data_parallel_size=<trace_profile.topology.data_parallel_size>
```

串行仅表示 R01–R10 的 stage 顺序，不表示单卡。每个会执行模型、采集 trace
或生成硬件属性的 stage 都必须保持 trace profile 的完整 workload 和设备/rank
拓扑；不得把多卡目标降格为单卡执行。

## 运行注意项（batch8 首次执行确认）

- scheduler 在创建 R01 Goal 前必须显式提供完整的 batch8 request-selection
  manifest，不能让 R01 搜索数据集、从单行扩增或临时合成 prompt。本 profile
  固定使用 `/home/testdata/16-32K_throughput.jsonl` 按原文件顺序选择前 8 条
  request；文件 SHA-256 为
  `633ba4c8b4f500d2ab28094de42698c5494e5232f40eafcd119c0a314b44b936`。
  manifest 必须包含 8 个稳定 request ID、0-based row indices、1-based line
  numbers、每行原始字节 SHA-256、每条 canonical JSON SHA-256，以及 ordered
  selection 的 canonical SHA-256。clock 与 hipprof pass 必须消费完全相同的
  manifest。缺少此输入会使 R01 在任何设备查询、模型初始化或业务产物生成前
  按 fail-closed 规则进入 blocked。
- scheduler assignment 还必须在创建 R01 Goal 前提供：固定 model directory、
  `config.json` 路径/SHA-256、固定 vLLM executable 路径/文件 SHA-256/version、
  scheduler 生成的非空 attempt ID 和固定 service port。不得让 R01 扫描邻近
  模型、猜测 executable、复用旧 attempt ID 或临时选择端口。
- app-server 的正式 Goal objective 上限为 4000 字符。scheduler 必须在创建
  R01 Goal 前计算并校验完整 bootstrap，通过 R01 turn assignment 注入完整结构；
  正式 Goal objective 只写可由 payload/request/model/runtime/profile SHA-256 与
  attempt ID 核验的紧凑摘要，并在调用 `thread/goal/set` 前显式检查长度不超过
  4000。不得把完整 8-request manifest 序列化进 objective。dry-run 必须证明该
  长度门禁通过，同时仍输出完整 bootstrap 供离线验收。
- 正式 Goal 由串行 scheduler 唯一创建。runtime project skill 不得再次调用
  `create_goal` 或建立嵌套 Goal；重复调用会被 app-server 拒绝，并产生误导性
  错误日志。
- 若 R01 因上述输入遗漏而停止且 artifact/handoff 均为空，先修复并校验
  scheduler config，再以同一 run 的普通 `--resume-run-id` 从首个未完成的
  R01 重启；不要伪造 handoff，也不要使用 `--continue-current-goal` 续接已经
  blocked 的正式 Goal。
- R01 的“设备空闲/KFD PID”探测必须发生在导入 Transformers、PyTorch、vLLM
  或其他可能初始化 HIP/KFD 的模块之前；否则合同准备进程自身可能出现在
  `hy-smi --showpids` 中并被误判为外部并发负载。失败的准备尝试必须移入独立
  attempt 目录，修正探测时序后重新生成合同，不得覆盖或把失败文件提升为证据。
- batch8 目标 checkout 是 source-only vLLM，而 ABI 扩展来自固定版本的系统
  distribution。因为 checkout 根目录的 `vllm.egg-info` 会在 `PYTHONPATH` 上
  遮蔽 site-packages 元数据，禁止用首个
  `importlib.metadata.distribution("vllm")` 结果推导扩展目录。应枚举所有 vLLM
  distribution，固定版本，并只接受文件清单中同时包含且磁盘上实际存在
  `_C.abi3.so`、`_rocm_C.abi3.so` 的目录；否则会在模型加载前误报扩展缺失。
  每次失败启动必须保留独立 attempt/log，修复后使用新的空 pass root 重试。
- R01 hipprof 离线归因不得把所有名称含 `memcpy`/`memset` 的 HIP runtime API
  当成必须拥有 HIPOPS kernel row 的 launch。batch8 首次运行确认原生 exporter
  对 `hipMemcpyWithStream`、`hipMemcpyAsync` 等可只保留 host runtime row；真正
  kernel-launch API 的关联率应单独统计并保持 100%。若该分类 bug 使 analyzer
  失败，保存失败 attempt、API 分类计数和原始文件哈希，只修 analyzer 并复用
  同一 DB/pftrace，禁止无依据地重新执行设备测量。
- R02 的正式校验不得依赖环境一定存在 `jq`/`rg`；ledger、handoff、schema、
  source anchor 和 SHA-256 必须有 Python 标准库实现。缺少可选 inspection CLI
  不能被误判为模型或 DCU 失败。
- R03 探测或运行 `hipprof` 前必须 source trace target 的固定环境 profile，
  并把同一 DTK 的 `dcc/lib` 加入 `LD_LIBRARY_PATH`。裸调 `/opt/dtk/bin/hipprof`
  出现 `libLLVM-17git.so` 缺失只表示启动环境错误，不代表 profiler capability
  不可用；修正环境后先重做无测量 preflight，再决定是否开始 capture。
- R03 preflight 对 `hipprof -h` 中的输出格式名必须大小写无关匹配；batch8 固定
  版本输出小写 `pftrace`。缺失 flags 与缺失 output format 要分别诊断，不能在
  flag 缺失列表为空时因 `PFTrace`/`pftrace` 大小写差异误报
  `required local interface absent: []`。若尚未写 tool manifest、capture plan
  或测量产物，只修正审计器并重跑无测量 preflight，不应触发 GPU 重跑。
- R03 的 process adapter 测量集合必须与当前 R02 sidecar 的精确名称多重集合
  和计数完全一致；禁止以 `pra.*` 宽泛前缀筛选。目标运行时自带的
  `pra.generate_total` 等标记不属于 R02 adapter，可以保留为上下文，但不得混入
  27,862 个 adapter 范围的计数、归属、顺序或守恒校验。
- R03 固定 hipprof 可原生导出 `.db`、`.pftrace`、`.hipkernel.csv` 和
  `.hiptrace.csv`。封存器必须按类型校验“恰好一个 DB、一个 PFTrace”，白名单
  并哈希全部已知辅助 CSV，拒绝未知 raw 文件；不得把 raw 总文件数限定为 2。
  若请求、DB 和 PFTrace 已成功而仅后置 inventory 门失败，立即固定所有 raw
  尺寸/SHA-256、确认设备释放，记录 post-capture 工具修订链并复用同一测量，
  禁止因此重新执行 GPU 请求。
- R04 admission 对 R02 的 profiler/trace/PMC/report/attribution 五个执行标志必须
  分别严格断言为 `false`。不得用共享真假表达式计算这些预期值；写反
  `attribution_performed=false` 会在全部 handoff/artifact 哈希有效时伪造前序
  漂移。若 R04 artifact root 尚为空且未启动 PMC，修正只读 validator 后必须
  重跑完整前序哈希门，禁止改写 R02 或绕过该门禁。
- batch8 固定 rocprof 的 list-only capability 命令即使成功输出完整
  `gpu-agent9` basic/derived counter catalog，也可能以退出码 1 结束并打印
  `0 contexts collected`。探测器应保存原始输出和退出码，并依据可解析 agent、
  counter、公式和数量判断 catalog；不能把 list-only 的无 context 当成工具不可用。
  该例外不得扩展到真实 PMC replay，后者仍要求退出码 0、raw 文件完整且
  per-dispatch 归属有效。
- R04 的设备占用 preflight 必须先按当前 `hy-smi --help` 验证本机支持的查询参数；
  batch8 的 `hy-smi` 不支持 `--showpidgpus`，该错误发生在模型/DCU 工作之前，不能
  归类为 replay 失败。capability 与 smoke 的每一次尝试都必须分配唯一且不可变的
  attempt 名称和空目录；若名称已存在应 fail-closed 并换新名称，禁止覆盖历史
  命令、日志、raw 数据或退出码。
- batch8 固定 DTK 中的 legacy RPL v1 `rocprof` 存在安装布局不一致：它查找错误的
  `/opt/dtk-26.04/bin/rocminfo`，且预期的 roctracer tool/runtime 库不在其安装树内；
  实际 child workload 运行后仍为 `0 contexts collected`、raw 为空。其 help 宣称的
  `-o --` 也会被实现的 `.csv` 后缀检查拒绝。不得通过修改 raw 或放宽非空门禁来
  使用该路径；只有同一固定 DTK 的 `rocprofv2` 真实 smoke 以退出码 0 生成非空逐
  dispatch 计数器 CSV，并证明 HIP API/HCC operation correlation 可解析，才允许
  切换 collector。batch8 首次通过的 smoke 为 11 条逐 dispatch 行和 6 个 SQ
  counter；正式 replay 仍须逐次重新验证退出码、raw 完整性和严格归属。
- `rocprofv2` 暴露或接受 filter 环境变量不等于 file plugin 实际执行过滤。batch8
  使用不存在的 kernel literal、期望 0 个匹配的 model-free probe，仍生成与基线相同
  的 5 个 dispatch，证明 `ROCPROFILER_KERNEL_FILTER` 在固定 DTK 中被忽略。R04
  必须显式记录 `collector_kernel_filter_empirically_effective=false`，不得把该次
  native counter capture 描述为 collector-filtered。允许的降级是每个唯一安全
  literal 仅采集一次完整 canonical request 的 bounded superset。`--hip-api` 下正式
  pilot 的 PMC correlation ID 全为 `0`，且 `--kernel-trace` 未产生可连接的 kernel
  trace；独立 probe 证明只有 `--hip-trace` 产生的 HCC ops 与 counter 共享非零
  correlation ID。因此必须保留 HIP API/ROCTX 和 HCC ops correlation 所需流，不能
  以缩减 raw 为由移除 HCC ops；使用错误 trace 选项的成功 pilot 也必须隔离为
  diagnostics 并在 tool revision 后重采。非目标 native 行只保留在 immutable raw。
  软件投影必须按 exact literal、exact R02 HIPTX range、
  HIP launch correlation、PMC dispatch correlation、exact normalized R03 subsequence
  串行门禁。共享 literal 的多个逻辑 process/fragment 只可共享物理 raw，不能共享
  未经各自 range/correlation 验证的归属。batch8 计划规模门禁为 62 个代表行、58 个
  PMC 逻辑目标、4 个 no-kernel、26 个物理 capture batch 和 89 个 R03 operation
  实例；任一数量或成员集合漂移均须在设备 replay 前 fail-closed。
- R04 artifact-local replay wrapper 必须自行重建已验证的目标运行环境，不能假定
  formal Goal 的父进程会把 source root 或 DTK runtime 绑定传给 profiler child。
  batch8 首个 pilot 因缺少目标 source root 的 `PYTHONPATH` 前缀而从
  `/usr/local/lib/python3.10/dist-packages/vllm/__init__.py` 加载 Python tree，并在
  模型加载前 fail-closed。修复时应显式前置 `<trace-target-root>`、R04 tools 和同一
  固定 DTK 的 `dcc/lib`，解析目标 `.venv/bin/python`，同时继续要求 Python tree
  来自目标 checkout、ABI `.so` 来自固定系统 distribution。旧 tool manifest、旧
  plan 和失败 attempt 必须整体隔离到带 hash 的 tool-revision diagnostics，随后
  重新封存工具并重建全部 target metadata；禁止覆盖失败 attempt 或沿用包含旧工具
  SHA 的计划。
- batch8 R04 长时间串行 PMC 采集确认，Codex 后端响应流断开会使 app-server 把正式
  Goal 标记为 `blocked`，并连带终止 scheduler、executor、rocprofv2 和模型进程；即使
  executor 已输出下一物理 batch 的 `start`，该 batch 也可能只留下目录和 `pmc.txt`，
  没有 `execution_manifest.json`。这属于控制面中断，不能计为有效 replay，也不能直接
  复用非空 pass root。恢复时先证明 scoped 进程全部退出，验证此前每个 completed
  manifest 的 `pass/exit 0`、artifact hash、固定 source commit 和 clean worktree；将
  不完整 pass 以文件清单、SHA-256、原路径、stop reason 封存到不可变
  quarantine/revision attempt，然后为同一物理 batch 使用新的空 pass root。已 blocked
  的 Goal 不得 `--continue-current-goal`；普通 resume 会分配空 `resume-NNN` 根并导致
  整阶段重跑，因此 suffix-only 恢复必须对同一 `run_id` 从 R04 使用
  `--resume-artifact-root <原 R04 root>`，创建新正式 Goal 并复用 state/attempt history
  已记录且位于 canonical R04 root 内的原根，同时保持 lineage、sealed plan、已完成
  原始证据和累计 profiling wall-time 账本不变。resume 必须逐批 hash 校验并跳过合格 capture，
  禁止删除/覆盖残留、把部分文件提升为证据或从 R01-R03 重跑。
- R02 深层 FX trace 必须显式处理目标源码中的 Proxy slice assignment 与
  `shape[:-1]` 动态展开。对固定 rank 合同可实现 source-preserving
  `setitem`/`len`/iteration Proxy 语义；不得用删掉真实控制流或伪造节点的方式
  绕过 `Proxy` 异常。linear/full attention 必须按真实 `layer_type` 分别验证。
- R02 model-forward wrapper 必须按当前 source signature 解析 `input_ids`、
  `inputs_embeds` 或已验证 positional slot，随后与 SAME_INPUT phase/q_len/kv_len
  grid 对齐；不能假定 token tensor 总在 `args[0]`。
- 对跨 layer 共享的 module object（batch8 首次运行实证为 full-attention
  `rotary_emb`），wrapper 必须按 module identity 与 wrapper semantic 去重并记录
  全部 alias paths/declared layer indices。逐 alias 堆叠 wrapper 会把一次调用重复
  记录多次；严格 event-count 校验必须拒绝该结果，而不是放宽期望值。
- R02 的失败尝试必须保存在独立 attempt 目录；只有 equivalence、guard-off、
  event count、marker nesting、wrapper cleanup、source AST 和 clean-worktree
  校验全通过后才能提交 R02。R02 本身不运行 profiler 或生成性能归因。
- R06 必须先完整枚举并去重 parent process range 与全部 fragment range，再用该
  精确数量检查 `maximum_selected_process_count`；不得先按容量截断、抽样、丢弃
  fragment 或把静态默认值当成已知 universe。batch8 首次完整枚举为 25,456 个
  唯一目标（9,472 parent + 15,984 fragment），超过旧上限 25,000。此时正确行为是
  只写带完整计数和输入哈希的 failure diagnostic，不写 R06 handoff、不启动 R07。
  修复必须在没有 scoped runtime 进程且 run 为 `stopped` 时进行：将 state/ledger
  先写入不可变 `recovery/parameter-revision-NNN/` 快照，用 failure diagnostic 的
  路径和 SHA-256 绑定 observed requirement，只允许非递减地提高容量到不小于精确
  universe（本次取 32,768），并把 before/after、reason、evidence 和快照哈希写入
  `parameter_revision_history`。随后仅从首个未完成 R06 创建新正式 Goal，并通过
  `--resume-artifact-root <原 R06 root>` 复用其诊断；不得直接编辑 `state.json`、不得
  `--continue-current-goal` 续接 blocked Goal，也不得重跑 R01–R05。
- R06 的离线能力探针不得假设 `importlib.util.find_spec()` 对缺失的 dotted module
  总返回 `None`；当 `perfetto` 父包本身未安装时，探测
  `perfetto.trace_processor` 会抛 `ModuleNotFoundError`。探针必须先安全探测父包或
  捕获该异常，将首选接口标为 `unavailable` 并继续验证本地无损 fallback。失败
  探针、stderr 和旧工具 SHA-256 必须隔离，不能把正常的 optional dependency 缺失
  升级成 R06 capability failure。
- R06 恢复审计不得把容量修订绑定到 `resume_history[-1]`：安全暂停后用
  `--continue-current-goal` 会追加新的 resume 记录。必须按稳定的
  `parameter_revision.revision_id`、failure diagnostic SHA-256、before/after 容量与
  state/ledger snapshot hash 搜索并验证对应历史项；后续 continuation 不能被误判为
  prior-state hash drift。失败的 auditor 版本与 prepare stderr 必须隔离后再修工具。
- R07 的 HIPTX marker 名称必须逐字节使用 R06 transport 中的 25,456 个目标，不得把
  adapter 内部的 `forward_id` 拼入可见 marker。batch8 首次捕获错误地产生
  `inputN_forwardN_layerM...`，而 R06 目标是 `inputN_layerM...`，导致交集为 0、
  25,456 个 missing 和 25,456 个 extra。该捕获即使 DB/PFTrace 完整、请求次数为 1，
  也必须 fail-closed；`forward_id` 只能保留在 sidecar 连接字段。重测前必须先用失败
  DB 做离线规范化审计，并证明规范化后的顺序、集合、唯一性与 R06 target manifest
  完全一致。
- R07 live utilization 的请求周期目标是 500 us，但非实时 Linux 与 vendor RSMI 调用
  不能提供“任意相邻样本间隔都小于 1 ms”的硬实时保证。batch8 两次正式捕获分别出现
  24/38 个 `gap >= 1 ms` 和 4 个超限不确定度样本；停止态诊断进一步证明：移除共享
  文件系统循环写入后仍有最大 19.4 ms 调度缺口，复用底层 `UsageManager` 的原生预分配
  collector 仍有周期性约 2.5 ms driver 调用，三路独立 collector 也存在共同缺口。因此
  不得继续把全请求“零缺口”作为 R07 完成门槛，也不得只用 p50/p95 隐藏尾部。
  正确合同是 lossless、gap-aware：采样循环只写内存，停止后一次性封存；保留每个原始
  sample/attempt、sequence、begin/end、call latency、alignment uncertainty 和全部 gap
  interval；禁止删除、插值、resample、smear、impute 或用零填补。对齐不确定度超过
  1 ms 的行仍保留并标为 `unavailable_alignment_error`。只有至少三个 timing-eligible
  真样本落在精确 process interval 内、且该 interval 不与未观测 gap 相交时，才可给出
  process live-utilization；否则显式标为 `unavailable_intrinsic_short_window`、
  `unavailable_sampling_gap` 或 `unavailable_alignment_error`。孤立且完整记账的 gap 不得
  使 R07 的 request/process/runtime/kernel clock 或 target coverage 失败，但任何隐藏 gap、
  丢行、伪造连续覆盖或对 unavailable process 作低利用率结论都必须 fail-closed。
  sidecar、raw rows、gap table 与双时钟 anchors 必须在任何 postcheck 失败前封存。
- R07 strict ownership 必须把完全嵌套的 parent/fragment ranges 建模为一条层级链：先筛选
  同 DB/PID/config 且时间与 runtime-index 完全包含 runtime call 的全部候选，再要求候选
  构成严格 nesting chain，并由唯一 deepest range 拥有该 runtime/kernel。非嵌套多候选
  仍是 ambiguity；parent 与 fragment 不得双计。没有直接 kernel 的 parent 也必须保留
  explicit no-kernel row。batch8 第二次捕获的 CPU-only repair 实证 25,456 个 process rows、
  2,368 个 explicit no-kernel rows 和 38,476 个唯一 strict-owned kernels 全部可守恒。
- R07 每次 retry 在创建或冻结工具前，必须读取 run 级 retry authorization 与当前 attempt
  的 monitor advisory；这些文件只收紧本次尝试，不能充当完成证据。运行 R07 时禁止执行
  迁移 A01–A10；已经完成的 A11 及其调度脚本只作为不可变入口，不因 runtime retry 重跑。
- R07 设备访问前必须产出独立的 `validation/predevice_gate_report.json`，并在一个纯 CPU
  tool call 中完成：request、forward、parent-layer、process-or-fragment 四类 marker 的真实
  emit/parse 回归，且每类都携带 contract file SHA-256 与 canonical SHA-256；nested owner
  正向回归、非祖先 overlap 负向回归，以及授权指定的旧 DB 诊断；production tokenizer
  prompt/output hash；所有 Python compile、`bash -n`、最终工具 re-hash 与 executable
  allowlist。`TRACE_COUNTER` 必须按 trace 语义分类，不能仅因名称含 counter 就误判为 PMC；
  launcher 不得依赖 `jq`、`/usr/bin/time` 或未 pin 的 `rg`。CPU gate 完成后必须先结束该
  tool call 并发送 checkpoint；正式 preflight/capture 必须是后续独立 tool call，禁止把
  freeze、自检、preflight、collector、hipprof 或 model init 合并为一个命令。
- R07 物理设备合同要区分 visibility 后的逻辑 device/rank 与原生 profiler 表中的
  每个 physical HIPOPS `dev_id`：必须校验并保留 trace profile 声明的完整
  rank-to-physical-device 映射，不得把多个物理设备重标或合并为 logical 0。
  `hy-smi` 的 PCI 字段必须抽取且只抽取一个完整 BDF token 后做精确相等比较，不能使用
  `startswith`。传给 `hipprof -d` 的精确目录（当前为 `capture/hipprof_tmp`）必须在启动前
  创建并通过文件系统合同回归。
- R07 禁止在工具冻结前做探索性 `hy-smi`。每次设备查询都计入明示 preflight，并封存
  argv、binary hash、raw stdout/stderr 与双时钟边界。如果已发生未记录的只读探测，必须
  单独披露，并在再次查询前得到只授权一次额外正式 preflight 的 supplement；不得把探测
  擦除或冒充正式 preflight。batch8 resume-008 因 CPU gates 与 capture 紧邻、监控无法在
  边界复核而被中止：只发生 1 次 formal preflight 和 model initialization 起步，collector
  `armed=false`、sample_count=0，warmup/measured request 均为 0；该 attempt 永久隔离，
  不得提升、拼接或计作 R07 测量。
- R07 batch8 `resume-009` 证明“语法通过”不足以验证纯函数门禁：冻结 normalizer 的
  `classify_trace_counter_semantics()` 因补丁插入位置错误走到隐式 `None` 返回，CPU-only
  predevice gate 在读取 `is_pmc_evidence` 时 fail-closed。该 attempt 没有正式设备查询、
  model init、warmup、measured request、collector 或 hipprof，必须永久保留且不能原地
  修补重跑。后续 attempt 必须在 freeze 前对 TRACE_COUNTER 分类器执行返回路径回归：
  trace-summary 输入必须返回非空结构、`is_pmc_evidence=false`、精确 trace type 集合；
  真实 PMC 语义输入必须返回非空结构、`is_pmc_evidence=true`，未知/畸形输入必须显式
  抛错。回归必须调用生产函数并校验返回 schema，而不是只检查源码文本；随后重新冻结
  全部工具、写新的 predevice report，并继续保持 CPU gate 与正式 preflight 分离。
- R07 batch8 `resume-010` 的 TRACE_COUNTER 三分支回归已通过，但授权要求的旧 DB
  normalizer 回归因诊断 sidecar schema 不完整而 fail-closed：shim 只补了双合同哈希，
  漏掉生产 normalizer 必需的 `end_realtime_ns`。该 attempt 仍为零正式设备查询、零
  model init、零 warmup/measurement、零 collector/hipprof，必须永久隔离。后续 attempt
  在 freeze 前必须以生产 sidecar schema 逐字段验证旧事件转换；除双合同哈希外，至少
  保留原始 `start/end_realtime_ns`、`start/end_monotonic_ns`、kind/record_kind、range/event
  identity 与全部 ownership 字段。shim 生成后先做 schema-completeness 检查，再调用生产
  normalizer；禁止以默认值伪造缺失时钟，也禁止把诊断输出提升为本轮测量证据。
- R07 batch8 `resume-011` 的全部 CPU 门和唯一正式设备预检均通过，但 capture launcher
  从 project root 调用 hipprof，未在启动 child 前切换到固定 trace target root；生产
  runner 的 cwd 自检因此在模型初始化前 fail-closed。collector 未 armed、sample_count=0，
  model init/warmup/measured request 均为 0，16 KiB DB 只是 profiler 启动残留，不能提升。
  后续 launcher 必须在冻结前通过 cwd 语义回归：解析并固定 source root，启动 hipprof
  child 前显式 `cd` 到该目录，且 invocation/tool provenance 同时记录 parent cwd、child cwd
  与 source root；回归必须证明三者合同，而不能只做 `bash -n` 或 executable allowlist。
  runner 仍需保留独立的 `os.getcwd()==source_root` fail-closed 检查。
- R07 batch8 `resume-012` 的唯一正式采集、25,456 个 process 归一化、42,104 行无损
  live-utilization 对齐和 dependency adapter 均已生成，但最终审计在写 handoff 前因
  文件名合同不一致 fail-closed：align invocation 写出
  `alignment/r07_live_utilization_process_availability.csv`，冻结 auditor 要求
  `alignment/r07_process_live_utilization.csv`。该 attempt 已执行 1 次 model init、
  1 次 warmup 和 1 次 measured request，不能补别名、复制文件、原地改冻结工具、重跑
  audit 或提升其中任何测量/派生产物。后续 attempt 必须使用新的 retry authorization
  和空 root，重新执行全部 R07 gates 与唯一新 measured request；在工具冻结和设备访问前，
  必须以 CPU-only filename-contract regression 从生产 align argv 解析 `--process-csv`，
  从生产 auditor 解析 required artifact，并证明二者都逐字节等于唯一规范路径
  `alignment/r07_process_live_utilization.csv`。同时校验 gap CSV 的生产者/消费者路径，
  required-business-artifact 清单必须显式列出这两个对齐 CSV，禁止兼容别名或隐式发现。
- R08 batch8 canonical attempt 的第一个 PMC batch 在模型加载后、warmup/request/replay
  之前 fail-closed：artifact-local launcher 把真实 R02 inventory
  `artifacts/R02/output/qwen35_27b_pra_process_wise/fx_process_range_inventory.csv`
  与错误的 `--r02-root artifacts/R08` 配对，生产 `ProcessInstrumentation` 因 inventory
  不在声明的 R02 artifact root 内而拒绝运行。该 attempt 的
  `completed_capture_count=0`；空 DB、空 PMC 文本、日志和失败进度只能作为诊断，禁止
  提升或计入 replay。后续 R08 必须在任何 device query、hipprof、模型导入或模型加载前
  执行独立的纯 CPU root-binding regression：从经 handoff/hash 校验的 R02 handoff 解析
  唯一规范 R02 artifact root 和 inventory，证明 inventory 位于该 root 内，并解析生产
  launcher/profile argv，证明 `--r02-root` 逐字节等于该 R02 root、`--r02-inventory`
  逐字节等于该 inventory；R08 自身的 `--artifact-root` 必须继续单独指向当前 R08 root。
  launcher 应通过独立且必填的 `R08_R02_ROOT`（或等价结构化字段）传递该绑定，禁止用
  `RUNTIME_ARTIFACT_ROOT` 代替。回归必须调用生产 path-containment 校验语义，不能只搜索
  源码字符串；失败时模型初始化计数必须保持 0。恢复时保留原 canonical R08 root 与
  `attempt-001`，由串行 scheduler 通过普通 `--resume-run-id ... --resume-from R08`
  创建全新的空 `R08/resume-NNN` 正式 Goal，重新封存工具和 R08 计划/capability/capture，
  禁止 `--continue-current-goal`、禁止复用失败 attempt、禁止重跑 A01–A11 或 R01–R07。
- R08 launcher 的执行权限也属于 predevice gate：冻结后必须以生产 allowlist 和实际执行
  方式验证 launcher 可执行，再允许 device query、模型导入或 hipprof。若权限错误发生在
  这些动作之前，保留失败日志、工具 hash 和零设备/零模型计数，将非空残留隔离到独立
  quarantine 后用修正权限的冻结工具继续；不得覆盖该残留或把它计为 capture attempt。
- predevice prefix gate 解析 predecessor handoff 中的相对路径时，必须以 scheduler 的
  project root 为基准，不能以当前 R08 artifact root 为基准；否则会形成
  `<R08-root>/perf_trace_batch8/runtime/...` 的重复前缀并误报缺失。累计 ledger 内指向同一
  ledger 路径的旧 SHA 是各 stage 当时的 append-only prefix 视图，应按 prefix 语义验证，
  不能把它当作当前完整 ledger 的可变业务 artifact 做逐字节复验。CPU gate 必须覆盖一条
  project-root 相对路径、绝对路径和一条越界负例，修复尝试使用新的 gate 日志/报告，不能
  覆盖此前误报。
- launcher 在 `set -e` 下不得先对尚未创建的合法 output parent 调用依赖存在性的
  `readlink -f`；该命令在固定主机对 missing parent 返回 1，会在 mkdir、device preflight、
  模型导入和 HIPProf 之前静默退出。应先用 `realpath -m`、`Path.resolve(strict=False)` 或
  等价 lexical-normalization 验证预期路径仍位于 R08 root，创建目录后再对已存在路径做
  canonical containment 复验。predevice regression 必须同时证明合法 missing parent 可通过、
  symlink/`..` 越界被拒绝、所有失败发生在零设备/零模型状态。此类 prelaunch 失败不算一次
  device capture；保留空 driver log 和审计后，从相同 capture ordinal/attempt 名称续跑，
  已接纳前缀不得重跑。
- R08 已接纳非空 capture 前缀后，HIPProf 可能以退出码 0 完成固定请求并生成非空 DB，
  但某个 literal/mode 的必需原生 PMC 文本仍为 0 字节。此情况必须 fail-closed，失败
  attempt 仅作诊断且不贡献 normalized counter；先证明 scoped device/model/profiler
  进程全部退出并将 run 正常停为 `stopped`，再记录 retry authorization。恢复必须由
  scheduler 用 `--resume-run-id ... --resume-from R08 --resume-artifact-root <原 R08 root>`
  创建新正式 Goal：逐项 hash/语义审计并跳过已接纳前缀，保留累计 profiling wall-time、
  artifact bytes、sealed plan、lineage 和失败耗时，只对首个失败 literal/mode 使用新的空
  `attempt-NNN`，随后继续未启动后缀。不得修改或提升失败 attempt，不得把空文本重标为
  unavailable capability；只有重试/独立 capability 证据能支持该分类。恢复不得重跑
  A01–A11、R01–R07 或任何已接纳 R08 capture；若恢复器不能证明前缀完整或不能使用新
  attempt 续写，应继续停止，不能退化为整阶段重跑。
- HIPProf `--kernel-name` 接收的不是完整 demangled literal，也不是正则表达式，而是
  collector 的简化 kernel token。固定 DTK 的 `hipprof::ttrace::filtr_kernel_name(std::string)`
  二进制实现会从运行时 demangled 名称末尾逆向剥离配平的参数 `(...)` 和模板 `<...>`，
  再截取最后一个 `::` 或空格后的标识符；例如 capture 52 的逐字节 literal
  `void rocprim::detail::single_scan_kernel<...>(...)` 对应 token 为
  `single_scan_kernel`。batch8 attempt-001/002 原样传入完整 literal，attempt-003 传入逐字符
  转义并锚定的 ECMAScript regex；三次都完成请求、生成非空 DB、但产生 0 字节 PMC 文本，
  因而同时否定 raw-literal 和 regex transport 假设，三次均永久保留为 diagnostic-only，
  不得贡献 normalized counter。
- 计划、ownership、analyzer 和最终 attribution 必须继续保存并使用逐字节
  `kernel_name_filter_literal`；launcher 另行记录并只向 HIPProf 传入由固定 collector
  二进制等价算法生成的 `collector_kernel_name_token`。任何 device query 前必须对全部计划
  literal 做纯 CPU 回归，保存 literal→token 映射、token 确定性、生产 argv 实际取 token、
  analyzer 仍取 literal、collector binary/hash/symbol/disassembly 证据。多个 literal 若映射到
  同一 token，该 capture 只能声明为 bounded collector superset；必须在同一 replay 内按完整
  literal、PID、dispatch 顺序和 HIPTX/runtime/HIPOPS 归属严格后过滤，不能把 token 相等当作
  exact collector match。修复后仍须通过同 root suffix-only 恢复，只对首个失败项使用新的空
  `attempt-NNN`，把所有成功和失败耗时/字节计入容量，禁止重跑已接纳前缀或任何
  Adapt/R01–R07 阶段。
- 大型 CPU-only normalizer 输出可能超过交互工具的单次等待时间；超时中断会留下部分
  CSV。此类分析必须用可轮询的持久进程完成，每次修复写新的 `normalized-repair-NNN/`
  root，绝不覆盖或提升部分输出；partial root、stderr、工具 hash 和中断原因都要保留。
- R07 首次且唯一授权的 measured request 失败后，不得在同一正式 Goal 中静默重试，
  不得复用或拼接失败 capture 的 timing/utilization/event。先完整保留原始文件、哈希、
  failure diagnostic 和 blocked audit；待 run 为 `stopped` 且 scoped 进程为零后，
  只能由串行 scheduler 通过普通 `--resume-run-id ... --resume-from R07` 创建新正式
  Goal，显式授权恰好一次新的 non-replay measured request，并在 canonical R07 边界内
  分配全新的空 attempt root。新 Goal 必须重新校验 R01–R06 ledger、固定源码、设备隔离
  和全部 R07 gates；已 blocked 的 Goal 不得用 `--continue-current-goal`，失败 attempt
  也不得提升为 handoff 或推进 R08。
- app-server 在生成约 45–85 KiB 的 builder/auditor 文件时，content item、token、
  子进程与 artifact 可连续静止超过 5 分钟后自然恢复。监控仍须每 5 分钟检查，但
  对已明确处于大型文件生成的 Turn 应要求连续两次完整检查均静止，且无新 reasoning
  item，再向 scheduler 单 PID 发送 SIGINT；不得因一次 5 分钟窗口杀 process group。

允许每个阶段为 trace、分析或展示目的修改工具代码，但必须记录 stage source
delta。只要模型、输入和语义合同未改变，source hash 变化本身不拆分 lineage；
若语义合同改变，则停止当前 run，不能把前后证据拼成一个 fresh lineage。

## 串行 Goals 与 Skills

| Runtime Goal | Project skill | 前驱 |
|---|---|---|
| R01 | `qwen-dcu-same-input-layer-wise-workflow` | 无 |
| R02 | `qwen-dcu-fx-process-nvtx-instrumentation` | R01 |
| R03 | `qwen-dcu-process-performance-breakdown` | R01–R02 |
| R04 | `qwen-dcu-process-gpu-hardware-trace` | R01–R03 |
| R05 | `qwen-dcu-segmented-process-attribution` | R01–R04 |
| R06 | `qwen-dcu-workflow05-evidence-planning` | R01–R05 |
| R07 | `qwen-dcu-workflow05-full-request-process-trace` | R01–R06 |
| R08 | `qwen-dcu-workflow05-targeted-hardware-gap-analysis` | R01–R07 |
| R09 | `qwen-dcu-workflow05-utilization-concurrency-analysis` | R01–R08 |
| R10 | `qwen-dcu-workflow05-trace-visualization-reporting` | R01–R09 |

调度器必须满足：

1. 每个 Goal 使用持久线程，且一次只运行一个 Goal；
2. Goal 启动前校验全部前驱 handoff 的路径、payload 和 SHA-256；
3. Goal 只向 scheduler 分配的 artifact root 写业务产物；
4. Goal 完成后写一个 scheduler handoff；
5. handoff 校验通过并提交累计 ledger 后，才能启动下一个 Goal；
6. 任何失败、暂停、超时、lineage 漂移或 hash 漂移都停止串行链；
7. R01–R10 全程禁止外部 runtime ledger。

R06–R10 handoff 必须包含：

```text
runtime_goal=Rxx
status=complete
execution_status=complete
evidence_status=complete
coverage_target_met=true
next_authorization_required=false
fresh_e2e_evidence.schema_version=1
fresh_e2e_evidence.status=complete
fresh_e2e_evidence.lineage_id=<same lineage for R06-R10>
```

## R01–R05：同一 run 的上游证据

R01–R05 必须按照 Workflow 01–04 生成本次 run 的 layer denominator、FX/process
边界、代表 process 归因、DCU 硬件属性和全层 process attribution。它们不是可由
R06 外部提供的历史输入，而是当前 R01–R10 ledger 的不可变前缀。

R05 完成时，累计 ledger 必须严格包含 R01、R02、R03、R04、R05 五个已校验
handoff；R06 不得接受缺项、乱序、跨 run 或跨 branch 的前缀。

## R06：fresh 证据与全量目标规划

R06 只做离线规划和能力探测，不运行模型、GPU/DCU 或 profiler。它必须：

- 校验当前 run 的 R01–R05 handoff 前缀；
- 写出 `fresh_run_lineage_manifest.json`；
- 生成完整 request event/range 目标文件，不按 Top-N 截断；
- 在写目标文件前记录 parent、fragment、unique 与 unresolved 精确计数，并验证
  `maximum_selected_process_count >= unique target count`；容量不足时按上述审计化
  参数修订流程停止和恢复，禁止静默缩小目标集合；
- 生成 R08 的有界 PMC family 计划；
- 探测 Perfetto、Plotly 和离线展示接口；
- 明确记录 capability 可用、降级或不可用状态。

R06 handoff 至少引用：

```text
fresh_run_lineage_manifest
full_request_target_manifest
```

## R07：一次完整请求的 observed 时间轴

R07 按 hash-pinned trace profile 执行一次 non-replay 完整 workload，并覆盖其全部
物理设备、DP ranks、measured requests 以及 R06 的全部 process ranges。该捕获是
R07–R10 唯一的 observed latency clock。

必须采集并对齐：

- request、forward、layer 和 process HIPTX ranges；
- HIP runtime calls；
- strict-owned HIPOPS kernels、queue/stream 和 GPU busy union；
- realtime/monotonic anchors；
- 目标周期 500 us、完整保留 raw rows/gap intervals/不确定度并逐 process 标注
  available/unavailable 的 `se_active_cu_pct` live samples；
- 固定输入的 process dependency adapter。

R07 不得使用 replay duration 作为 observed latency，不得遗漏 R06 目标，不得将
部分请求提升为完整请求证据。

Live utilization 的“完整”是指原始采样、慢调用、gap、跨时钟不确定度和逐 process
availability 状态全部无损记账，而不是声称非实时主机上不存在 gap。R07 的 target
coverage 1.0 约束 request/process trace 集合；它不得被 live-utilization availability
替代。R09/R10 只能对 `available` process 使用 live utilization 数值，并必须把 gap 与
unavailable 区间作为独立 evidence track 暴露给分析和可视化。

R07 handoff 至少引用：

```text
full_request_profile_metadata
process_trace_summary
fresh_run_dependency_adapter
live_utilization_summary
source_lineage
```

## R08：同 lineage 的 targeted PMC 与资源模型

R08 只对 R06 选定的有界 kernel-family 集合串行执行 PMC replay。R08 必须：

- 继续使用 R06–R07 的 lineage ID；
- 保留 R07 non-replay 时间作为唯一 latency axis；
- 将 PMC/replay 结果标记为 `replay_projected` 属性；
- 探测 gfx936/DCU counter 能力并保留 unavailable 状态；
- 构建 FX-visible traffic/resource model；
- 不把 replay duration 加入 request/process 延迟。

R08 handoff 至少引用：

```text
device_capabilities
traffic_resource_model
source_lineage
```

## R09：十二表完整请求分析

R09 不运行 GPU。它必须从 R07 observed clock 和 R08 replay-projected 属性确定性
生成下列十二个 normalized tables：

```text
request_timeline
process_timeline
kernel_timeline
live_utilization_aligned
process_live_utilization
kernel_concurrency
queue_concurrency
launch_gaps
high_latency_processes
dependency_state
traffic_resource_attachment
opportunity_candidates
```

`fresh_e2e_analysis.json` 必须锁定每张表的路径、SHA-256、row count、schema 和
lineage ID。并发、launch gap 和 overlap 只能在 R07 同一 observed clock 上计算；
PMC 只能作为属性附着。依赖或 counter 不可用时保留 unknown/unavailable，不能
猜测补齐。

R09 handoff 至少引用：

```text
full_request_analysis
source_lineage
```

## R10：自包含、无损、全分辨率可视化

R10 只消费同一 run 的 R09 分析和 R07/R08 证据，不运行模型、GPU/DCU、profiler
或 PMC。交付必须包含：

```text
acceptance/index.html
acceptance/E2E_PROCESS_TIMELINE.html
acceptance/E2E_PROCESS_TIMELINE_LOSSLESS.html
acceptance/E2E_PROCESS_TIMELINE.full.perfetto.json
acceptance/full_timeline_manifest.json
acceptance/HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html
acceptance/CONCURRENCY_UTILIZATION.html
acceptance/offline_acceptance_manifest.json
R10_SOURCE_LINEAGE.json
R10_COMPLETION_AUDIT.json
```

### 无损数据要求

本地查看主机按不少于 128 GiB 内存设计。不得因内存、浏览器负载或文件体积对
timeline 做抽样、均匀取点、Top-N 截断、固定 event budget 或不可逆聚合。

全量 Perfetto 事件数必须严格等于：

```text
request_timeline rows
+ process_timeline rows
+ 2 * kernel_timeline rows
```

两份 kernel records 分别服务 `strict_owned_kernel` 和 `gpu_queue` 轨道，是同一
observed interval 的两种展示组织，不能当作两次计时。manifest 必须声明：

```text
complete_timeline=true
sampling_performed=false
formal_r09_r10_regeneration=true
```

它还必须锁定 R09 analysis SHA-256、十二表 SHA-256、每类事件数、lossless HTML
SHA-256 和完整 Perfetto trace SHA-256。

### 时间精度与交互

浏览器坐标使用相对 request begin 的整数 nanosecond offset。原始绝对
`begin_ns/end_ns` 以十进制字符串保留，禁止把约 `1.7e18` 的绝对 ns 转成
JavaScript `Number` 后相减。

`E2E_PROCESS_TIMELINE_LOSSLESS.html` 必须提供：

- 以鼠标位置为中心的连续缩放，最小 viewport 不粗于 1 ns；
- 拖拽平移、框选/按钮放大、重置和至少 100 步视图历史；
- process/event/layer/phase/family/track 全文筛选和筛选后 fit；
- request/forward/layer/process/HIP runtime/queue/kernel 分轨及 overlap sub-lane；
- 点击同一像素时列出该范围内全部重叠事件，不设条数上限；
- 按精确 begin/end 跳转并列出当前视窗全部事件；
- 总览可使用密度覆盖，但底层事件不得删除、合并或改写；
- 放大后每条原始事件都可独立定位并显示精确字段。

### 离线入口与证据语义

`index.html` 必须是单一人工入口，全部页面自包含，不依赖 CDN、远程脚本、网络
fetch 或云端上传。页面必须明确区分：

```text
observed R07 timing
observed live utilization
replay_projected R08 hardware attributes
derived analysis
unavailable/unknown evidence
```

颜色和轨道不能把 replay-projected 或 unavailable 数据伪装成 observed timing，
也不能把优化候选表达为已获得 speedup。

R10 handoff 至少引用：

```text
offline_acceptance_manifest
source_lineage
```

## 配置与运行入口

正式配置：

```text
<perf-trace-root>/configs/workflow01_10_fresh_e2e_<trace-profile-id>.json
```

调度 dry-run：

```bash
cd /public/home/tangyu408/Qwen_DCU_Worker_0
python3 <perf-trace-root>/scripts/run_perf_trace_01_10.py \
  --project-root /public/home/tangyu408/Qwen_DCU_Worker_0 \
  --branch workflow01-10-fresh-e2e \
  --user-parameters-file <perf-trace-root>/configs/workflow01_10_fresh_e2e_<trace-profile-id>.json \
  --dry-run
```

正式运行时去掉 `--dry-run` 并使用新的 `--run-id`。不得提供外部 upstream ledger。

## Completion Checks

- active manifest 只声明 `workflow01-10-fresh-e2e` 和 R01–R10；
- R01–R10 handoff 顺序完整，路径和 SHA-256 全部有效；
- R06–R10 使用同一个非空 lineage ID；
- R07 是完整 non-replay request，目标覆盖率为 100%；
- R08 replay timing 未混入 observed latency；
- R09 十二表齐全且可由源数据确定性重算；
- R10 页面、manifest 和完整 trace 的 row/event/hash 一致；
- 全量时间轴 `sampling_performed=false`；
- 离线页面在浏览器中完成缩放、平移、筛选、精确跳转和重叠事件检查；
- completion audit 未发现外部 runtime evidence、跨 lineage 输入或并行 GPU 工作。
