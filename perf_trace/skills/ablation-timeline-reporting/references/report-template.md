# 消融时间线报告模板（排版 + 图形几何规范）

来源：h23 `R10_SUMMARY.html` 定稿（AgentSys `experiments/h23-agentix-8b/code/build_r10_summary_doc.py`，
本仓库 `reference_impl/workflow06/` 同步了同一份——该脚本就是本模板的可执行形态）。
新报告应直接复用这些常数；改动任何一项须在报告审计文件中记录理由。

## 1. 文本排版（CSS）

```css
body   { font: 22px/1.7 "Noto Sans CJK SC", system-ui, sans-serif; color:#1f2f45; background:#fff }
.wrap  { max-width: 1200px; padding: 26px 22px 60px }
h1 { font-size: 33px }   h2 { font-size: 27px; color:#2f6f9f }   h3 { font-size: 22px }
.sub,.cap,.theme { font-size: 20px; color:#48607d; max-width: 120ch }   /* 图注/主题/导语 */
.block { font-size: 20px; padding: 12px 16px; border-radius: 6px; max-width: 120ch }
.block          { background:#f2f7fb; border:1px solid #c9d6e4 }   /* 论文方法卡 */
.block.impl     { background:#f4faf6; border-color:#bcd8c6 }        /* 实现卡 */
.block.howto    { background:#fbf7ef; border-color:#e2d3ae }        /* 怎么读截图卡 */
table  { font-size: 20px }  td,th { border:1px solid #c9d6e4; padding:4px 10px }
pre.art{ font: 18px/1.55 "IBM Plex Mono","Noto Sans Mono CJK SC",monospace;
         background:#f7f9f7; border:1px solid #cfd9cf; padding:12px 14px }  /* 字符画 */
.pfig img { border:1px solid #c9d6e4; border-radius:6px }  .pfig figcaption { font-size:19px }
```

## 2. 颜色语义（固定，不随模型/策略换色）

| 语义 | 色值 |
|---|---|
| 等待段 / cap 参考线 / 高延迟强调 | `#c94040` |
| bfcl / sharegpt / lats 类别 | `#eb6834` / `#2a78d6` / `#1baf7a` |
| gemm kernel 家族 | `#a8802f`；其它 kernel `#2f6f9f` |
| 机制侧标签（agentix/core） | `#2f6f9f`；baseline 标签 `#1f2f45` |
| 梯形包络 | 填 `#eef4fa` 描 `#8fb2ce`；网格 `#e6edf4` |

## 3. 图形几何（SVG，viewBox 宽 1150）

通用：`LEFT=130 RIGHT=20`；坐标轴 7 个刻度，刻度字 y 偏移 −12；SVG 内字号 13–22px
（历史基数 ×1.7 后取整，上限 22）；图外框 1px `#c9d6e4` 圆角 6。

| 部件 | 常数 |
|---|---|
| 端到端配对车道 | 行高 rh=24（放大图 42），同程序 F/A 两行，pair 高 = 2·rh+18，条高 rh−6，行间分隔线 `#eef2ee` |
| 生命周期图 | 调用条高 34；lats 波行距 48；图高 100+行数×48 |
| 调用堆 / step 堆带 | 带区 y0+44…y0+320 / y0+46…y0+300；成员线宽：短程序 5、lats 2.2 / step 1 |
| 并发 lanes | 每 lane 高 138、间距 24、竖条区高 lane−24；cap 红虚线 `4 3` |
| kernel 显微图 | 两行（gemm/其它）各高 84、矩形高 68；行距 gemm y0+46、其它 y0+150；资源墙竖条高 190 |
| 逐调用配对条 | 条高 30，每对纵距 96，条尾标注秒数与倍数 |

## 4. 版式规则（与 SKILL.md 必须做/禁止配套）

- 对比一律共轴：同程序 F/A 相邻两行，或 baseline 面板在上、机制面板在下。
- 每张图 = 图注（内容与差量数字）+ 轴注（每个轴符号的 process 视角解释）；选材标准只进审计文件。
- 每部分顺序：论文方法卡（看图说话，指向示意图）→ 示意图 → 实现卡 → 怎么读截图卡（先缩写卡）→ trace 图。
- 预备节：字符画（等宽、真实数字）+ 三类负载生命周期图 + 组成表。
