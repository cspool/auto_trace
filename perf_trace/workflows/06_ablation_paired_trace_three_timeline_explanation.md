# workflow06 — 消融配对采集与三类时间线图形化解释（A00–A05）

来源实践：h23（Agentix 8B 机制复现，单卡 RTX 4090，三模型，github.com/cspool/AgentSys）。
本工作流把 AutoTrace 的单次运行分析链（workflow01–05）扩展为**消融对照链**：同一负载、
同一采集栈、唯一变量为被评估机制，用三类时间线可视化把"机制是否有效、提升多少、为什么"
图形化地讲清。

## 0. 与参考链（workflow01–05）的差异

| 维度 | workflow01–05（参考链） | workflow06（本链） |
|---|---|---|
| 分析对象 | 单次运行的 trace | **一对运行**（baseline vs 机制），同负载单变量 |
| 目标 | 守恒分母、归因、硬件挂接、估计、资源缺口 | **消融解释**：直观效果 / 提升比例估算 / 提升原因 |
| Process 宇宙 | 单一（FX/模块 process） | **两级**：请求级（客户端调用窗口）+ scope 级（worker 侧区间） |
| 时间线视图 | R10 两页（高延迟分堆、并发资源窗口） | **三类且各承担解释职责**，每类上下共轴排布一对 |
| 结论形态 | 单运行资源缺口与机会 | 端侧指标差 = 时间线几何量差的闭环论证 + 上界估算 |
| 复用关系 | — | A02 逐捕获直接执行 workflow05 契约；折叠/梯形/十段制沿用其定义 |
| 两部结构 | workload_profile 拆 process 视图 → perf_trace 对其 trace | **同构保留**：A00 = workload_profile 半边（层级 + 守恒门），A01–A05 = perf_trace 半边；A00 不过门则后续步骤不得消费捕获 |

参考链的产物是本链的**构件**：workflow05 的 process-resource 契约页在 A02 原样生成，
本链新增的是配对语义（选窗、共轴、对照读法、差量记账）。

## 1. 适用前提

- 被评估机制可作为**单开关**接入（如调度策略），其余引擎参数、负载（冻结 JSON + sha256 +
  种子）、采集栈（nsys 版本、环境变量）与卡位完全一致。
- 机制的收益区间已知或可构造（h23 教训：程序级调度只在排队制有杠杆——必要时用统一
  max-batch 上限制造排队，采集必须落在收益存在的区间，否则三类时间线只能解释"为何无收益"）。
- 客户端能发出逐请求边界标记（NVTX call_begin/end），worker 侧有 scope 区间
  （vLLM：V1 runner + NVTX scopes 环境变量）。

## 2. 步骤

### A00 负载→运行时 process 视图拆解与守恒门（workload_profile 半边）

auto_trace 由两部分组成：workload_profile（把负载拆解成运行时 process 视图）与 perf_trace
（对这些已定义 process 做性能与资源 trace）。A00 是前者在消融链中的对应物，必须在任何
perf_trace 步骤消费捕获之前通过。参考实现 `analyze_a00_workload_process_view.py`，
产出 `a00_process_view.json`。

层级（规范键）：program(program_id) → call(program_id, call_index) →
step(forward scope 实例，一次引擎迭代) → scope(step, phase)。

守恒门（全部 PASS 才放行 A02–A04）：
- **G-P**：程序集合 三方一致（负载规格 = 运行记录 = trace NVTX）。
- **G-C**：调用键集合 三方相等（规格 2,440 = run jsonl = 配对 call_begin/end）。
- **G-S**：引擎循环守恒——各 phase scope 计数相对 forward 数的偏差需可解释：
  正偏差 = 空批迭代（调度器跑了 preprocess、批为空，h23 实测 +26/+62，0.2–0.4 %）；
  −1 = 采集停止截断的尾部迭代；赤字 <−1 或大正偏差 = scope 丢失，FAIL。
- **G-J**：每个调用窗口与 ≥1 个 forward step 区间相交（连续批下为成员关系而非独占）。

**验收**：六个捕获（3 模型 × 2 策略）的 a00 全部 all_pass；G-S 的每个偏差均带解释入档。

### A0W workload_analysis 前置链（W1–W5，每模型串行）

A00 只保证层级对账；**代表 process 的发现属于 workload_analysis 的另一半，必须在 A01 之前执行**，
否则 process 宇宙只是"引擎现成给什么用什么"，热点内部不可见（h23 教训：preprocess 是不透明块，
报告只能说"host 开销大"）。五步严格串行，一步一卡：

- **W1 试运行**：短定长运行 + CPU 采样（`--sample=process-tree` + `osrt` + 上下文切换）+ 现有探针。
- **W2 热点定位**（参考实现 `w2_hotspot_report.py`）：按 UNION 时间排名 host process；对头号
  host process 做 CUDA-API vs 纯 host 拆分（按引擎线程过滤，跨线程 OSRT 不可用于归因）；
  容器内部归因率；**空闲边界榜 = 命名区间并集在 step 内的补集**（逐对相邻区间算 gap 会在嵌套
  长区间上造出假空隙——h23 曾因此得到 99,457 s 的荒谬值）。
- **W3 插桩修订**（`w_instrument.py`）：按 W2 结论增删探针；去掉与引擎自带 scope 重复的项；
  把机制事件（量子块、降级、提升）升为一等 process。必须复测插桩开销（h23：−0.9 %）。
- **W4 代表性采集**：完整负载 + 修订插桩，无 CPU 采样。
- **W5 代表集选择**（`w5_select_processes.py`）：以 UNION(step) − UNION(forward) 为 host 分母，
  贪心选叶至覆盖目标；输出容器归因、空闲边界与 **perf_trace 覆盖差**，给出
   `COVERED` / `RECAPTURE_REQUIRED` 判定。

**验收**：三模型各自 W5 产出代表集；判定为 RECAPTURE_REQUIRED 时，A01 必须带修订插桩重采。

### A01 单变量配对采集

对每个模型采集两次：baseline（如 fcfs）与机制（如 agentix_core），除 `--policy` 外命令
逐 token 相同。产出：`cap.nsys-rep`（sqlite 可再导出）、`profile.log`（首行可复核完整命令）、
`run/`（逐调用 jsonl：提交/首 token/完成时刻、类别、程序号、队列路径、chunk 数；运行摘要 json
含负载 sha256 与端侧指标）。
**验收**：两侧 run summary 的负载 sha256 一致；调用数一致；trace 开销两侧同担（对比口径合法）。

### A02 逐捕获合同视图（复用 workflow05 契约）

对每个捕获执行 workflow05 的 R10 契约：>10 % 类型入选、每类型 5 个对数时长 Lloyd 连续堆、
全局堆排名、拟合梯形成员包络、共享折叠时钟、十段制、已关联资源窗口页 + GROUPS.json
（含源 sqlite sha256）。serving 适配声明：Process 宇宙 = scope 区间；硬件关联 family 级；
折叠上限 = max(2×中位时长, 段宽/2000)（µs 级 process 防微空档爆炸，只压大空洞、微间隙线性）。
**验收**：两侧入选类型集合一致（不一致说明单变量假设被破坏，回 A01）。

### A03 配对事实提取

从两侧调用记录与 GROUPS 提取可对照事实（参考实现 `analyze_gain_explain.py`，产出
`gain_facts_<model>.json`）：端侧指标与加速比；分类别等待（提交→首 token）mean/p50/p90；
队深（峰值在飞、cap 上方累计时长）；机制账本（如 MLFQ 入队分布/降级/提升/多量子计数——
机制在 trace 内的自证）；堆计划差量（重堆质量差 = 机制签名）。
**验收**：每个数字有出处字段；两侧口径相同。

### A04 三类解释性时间线（每类上下共轴：baseline 在上、机制在下）

1. **端到端 Process 时间线 → 直观效果**。无损请求车道（参照 r10_lossless_timeline 语义）：
   单一真实时间轴、全部调用逐条绘制、不折叠不抽样；车道 = 程序（按类别再按首提交排序），
   调用 = 等待段（提交→首 token，警示色）+ 服务段（首 token→完成，类别色）。
   读法：同横轴位置上下对看同一车道，等待段长度差 = 被机制移走的等待。
2. **高延迟 Process 时间线 → 提升比例估算**。A02 契约页的分堆梯形视图成对呈现；
   若两侧重堆同形（服务侧不变），做**程序级时间线重放估算**：把 baseline 每调用的等待段
   替换为机制侧同类别中位等待，重算程序级指标——得**上界**（程序内并行调用的等待在墙钟上
   重叠，逐调用求和重复计入）；实测应落在 1×–上界之间，长尾口径更接近上界。
3. **并发/资源分析时间线 → 提升原因**。lanes：设备 busy %、关键 kernel 家族占比、
   在飞请求数（含并发上限参考线）；仅在已关联窗口内作图（契约），灰底为未关联。
   读法：前两条同形 → 资源使用率不变；在飞都贴上限 → 并发不变；两个自由度排除后，
   剩余解释只能是完成顺序。
**验收**：三类视图两侧共轴同窗；交互版（十段/折叠/缩放）与静态截段版口径一致。

### A05 总结文档（图形化消融报告）

单文档结构：**预备节**（用负载规格 + trace 把论文未明说的 program/call 具体化为四层 process
层级：program→call→step→scope，含各类 program 的组成表：程序数、调用/程序、并行宽度、
token 规模，并给出"1 个 call 的服务段由多个 step 的成员资格拼成"的结构性说明）+ 三部分。
每部分 = 方法依据（论文原文出处 + 原图与轴级读图指引）→ 实现说明 → "怎么读截图"块
（**先列本部分图中全部缩写的 process 视角解释**，再讲横轴/纵轴/元素/对比方法）→ 配图 →
基于图注的主题解释。配图规则：

1. 端到端部分：短程序等待最重时段的车道图对（直观效果）。
2. 高延迟部分：**主图 = 高延迟【调用】堆对**（call 时长宇宙的最高时长堆，baseline 侧含被排队
   抬入的短程序调用、机制侧将其清出——高延迟视角凸显优势的主要证据）；**支撑图 = 高延迟
   【step】堆对**（刻意同形，钉死"服务侧不变"，作为比例估算依据）。
3. 并发部分：趋势 lanes 图之外**必须有资源墙放大图**——趋势窗内最繁忙的一小段（如 300 ms）
   按真实比例逐 kernel 展开（gemm 家族行 + 其它行 + 资源墙参考条），呈现"计算突发内顶
   L2/tensor 墙、突发间等 host"的运行时细节；结论表述为"两侧顶着同一面墙"而非"没有区别"。

**选材标准与窗口参数一律写入审计文件（如 R10_SUMMARY_AUDIT.json），报告正文只讲内容**。
**验收**：预备节组成表与 A00 三方一致；每部分含缩写卡；图注为 process 视角内容解释且含窗内
差量数字；正文无选窗准则文字；审计文件覆盖每张配图。

## 3. 产出清单

| 步骤 | 产物 |
|---|---|
| A0W | `workload_analysis/<model>_w1/W2_HOTSPOTS.json`、`<model>_w4/W5_REPRESENTATIVE_PROCESSES.json` |
| A00 | `<tag>/a00_process_view.json`（层级、事件族计数、四门结果与解释） |
| A01 | `<tag>/cap.nsys-rep`、`profile.log`、`run/*.jsonl`、`run/summary_*.json` |
| A02 | `<tag>_views/HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html`、`CONCURRENCY_UTILIZATION.html`、`GROUPS.json` |
| A03 | `gain_facts_<model>.json`、`payload_<tag>.json`（三视图数据，参考 schema：origin/sections/breaks/piles/lanes） |
| A04 | `R10_COMPARE_<model>.html`（交互，三类视图上下成对） |
| A05 | `R10_SUMMARY.html`（终版总结文档）+ `R10_SUMMARY_AUDIT.json`（选材准则与窗口审计） |

## 4. 参考实现

`reference_impl/`（取自 AgentSys `experiments/h23-agentix-8b/code`，提交 4b1cd2d）：

- `w_instrument.py` — W3 host 路径插桩层（含机制事件）
- `w2_hotspot_report.py` — W2 热点/容器/空闲边界分析
- `w5_select_processes.py` — W5 代表集与 perf_trace 覆盖判定
- `analyze_a00_workload_process_view.py` — A00 负载 process 视图拆解 + 守恒门
- `render_w05_contract_views.py` — A02 契约双页（serving 适配）
- `analyze_gain_explain.py` — A03 配对事实
- `build_r10_payloads.py` — A03/A04 三视图 payload（参考 batch16 页 schema）
- `render_r10_compare_report.py` — A04 交互对照报告（渲染器改造自 batch16 R10 页）
- `build_r10_summary_doc.py` — A05 总结文档（准则选窗截段 + 论文图嵌入）

h23 实例的最终产物与逐步原始数据见本仓库 Release `ablation-r10-h23`。
