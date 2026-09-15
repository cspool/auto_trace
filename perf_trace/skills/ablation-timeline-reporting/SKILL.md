---
name: ablation-timeline-reporting
description: 消融时间线总结文档（workflow06 A05）的写作与配图规范：process 层级具体化、缩写卡、调用堆主图、资源墙放大图、选材标准入审计文件。
---

# 消融时间线报告规范（workflow06 A05）

## 必须做

1. **先具体化 process 层级**：报告开头用负载规格 + trace 数字回答"program/call 到底是什么"
   （program→call→step→scope 四层 + 各类 program 组成表），后文所有图都用这套词汇解释。
2. **缩写卡**：每部分"怎么读截图"块先列本部分图中出现的全部缩写，用 process 视角解释
   （如 gemm = step 的主要 kernel 家族；在飞 = 已提交未完成的 call 数），再讲轴与元素。
3. **高延迟部分的主图是调用堆**：baseline 最高时长 call 堆里被排队抬入的短程序调用 vs 机制侧
   将其清出——这是凸显机制优势的证据；step 堆同形图只作"服务不变"的支撑。
4. **并发部分必须有放大图**：趋势 lanes 之外，取最繁忙的一小段逐 kernel 真实比例展开 +
   资源墙参考条；结论说"两侧顶同一面墙"，不说"没有区别"。
5. **选材标准与窗口只进审计文件**（R10_SUMMARY_AUDIT.json），正文图注只讲内容与差量数字。

## 禁止

- 图注里写选窗准则、阈值、算法名（移入审计）。
- 用趋势图代替运行时细节声称"资源相同"。
- 图内缩写在附近无 process 视角解释。
- 图注声称与实测数字矛盾的形态（如低 busy 却写"排满"）。

## 文本写作方法（方法块必须遵循）

每部分"论文方法与创新点"块的**表达策略取自 `/paper-experiment-idea`**，四段式：
① 一句话论点（加粗开头）；② Baseline 是什么/缺陷是什么——写论文实际评估的具体臂
（如 vLLM-opt / 朴素 MLFQ），并**沿一个具体请求给全栈执行例**（请求→队列→批→kernel，
缺失层写"论文未明确说明"）；③ 创新点按三元素（动机→机制→证据角色）逐项对应到它解决的
baseline 缺陷；④ 双向看图说话——先顺论文原图走读（图内元素逐个点名），再"再看我们的
trace 图"逐项对应到实盘证据，以边界句收尾。

**表达方式取自 `/nature-writing`**：论点先于句子；主张有界（show/suggest/enable 级别的
动词校准，不写 unsupported novelty）；证据缺失写占位而非编造；术语首次出现即入术语卡
（缩写卡）并全文用同一规范形。

**公式渲染**：正文公式一律用 HTML 标记——下标 `<sub>`、上标 `<sup>`（如
p(c<sub>j</sub>) = Σ<sub>k&lt;j</sub> t<sub>k</sub>、(W<sub>p</sub>+W<sub>c</sub>)/(T<sub>p</sub>+T<sub>c</sub>) ≥ β）；
禁止裸下划线记法（`W_p`、`c_j`）流入正文，它们不会被渲染；唯一豁免是 `<pre>` 字符画
（等宽原样即语义）。交付前检查：正文（剔除 pre 块后）不得残留 `X_y` 形式。

## 模板（必须引用）

排版、颜色语义与图形几何一律按 `references/report-template.md` 执行——该文件固化了 h23
定稿报告的全部常数（正文 22px、图注 20px、字符画 18px；车道行高 24、lane 高 138、
kernel 行高 84 等）；可执行形态即下方参考实现脚本。偏离模板须在审计文件记录理由。

## 参考实现

`perf_trace/workflows/reference_impl/workflow06/build_r10_summary_doc.py`（h23 实例）。
