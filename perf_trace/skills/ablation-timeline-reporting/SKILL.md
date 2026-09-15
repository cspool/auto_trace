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

## 参考实现

`perf_trace/workflows/reference_impl/workflow06/build_r10_summary_doc.py`（h23 实例）。
