# workflow06 — 消融配对采集与三类时间线图形化解释（A01–A05）

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

单文档三部分，每部分 = 方法依据（论文/设计文档原文出处 + 原图与轴级读图指引）→ 实现说明
→ "怎么读截图"块（横轴/纵轴/元素/对比方法）→ 按**明示准则**截取的最说明性时间段配图
（每模型一张，选窗准则写进图注）→ 基于图注的主题解释。选窗准则示例：
①滑动窗最大化 baseline 短类别等待总量；②重堆成员最密段；③在飞贴上限时间最长的窗。
**验收**：每张配图的图注含选窗准则与窗内差量数字；跨模型规律（收益 ~ 排队压力）以数字点列出。

## 3. 产出清单

| 步骤 | 产物 |
|---|---|
| A01 | `<tag>/cap.nsys-rep`、`profile.log`、`run/*.jsonl`、`run/summary_*.json` |
| A02 | `<tag>_views/HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html`、`CONCURRENCY_UTILIZATION.html`、`GROUPS.json` |
| A03 | `gain_facts_<model>.json`、`payload_<tag>.json`（三视图数据，参考 schema：origin/sections/breaks/piles/lanes） |
| A04 | `R10_COMPARE_<model>.html`（交互，三类视图上下成对） |
| A05 | `R10_SUMMARY.html`（终版总结文档） |

## 4. 参考实现

`reference_impl/`（取自 AgentSys `experiments/h23-agentix-8b/code`，提交 4b1cd2d）：

- `render_w05_contract_views.py` — A02 契约双页（serving 适配）
- `analyze_gain_explain.py` — A03 配对事实
- `build_r10_payloads.py` — A03/A04 三视图 payload（参考 batch16 页 schema）
- `render_r10_compare_report.py` — A04 交互对照报告（渲染器改造自 batch16 R10 页）
- `build_r10_summary_doc.py` — A05 总结文档（准则选窗截段 + 论文图嵌入）

h23 实例的最终产物与逐步原始数据见本仓库 Release `ablation-r10-h23`。
