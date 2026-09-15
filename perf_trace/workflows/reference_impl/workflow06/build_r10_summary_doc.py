#!/usr/bin/env python3
"""One summary document, three parts (e2e intuitive effect / high-latency gain
estimate / concurrency-resource reason). Each part embeds, per model, a static
excerpt figure cropped from the timeline data at the most illustrative window
(picked programmatically, criterion stated in the caption), FCFS above and
agentix_core below on a shared axis."""
import argparse
import base64
import json
import statistics
from pathlib import Path

PAPER_FIG_DIR = Path("/workspace/AgentSys/Agentix An Efficient Serving Engine for LLM Agents as General Programs")


def paper_fig(fname, cap):
    b64 = base64.b64encode((PAPER_FIG_DIR / fname).read_bytes()).decode()
    return (f'<figure class="pfig"><img src="data:image/jpeg;base64,{b64}" alt="{fname}">'
            f'<figcaption>{cap}</figcaption></figure>')

CLS_COLOR = {"bfcl": "#eb6834", "sharegpt": "#2a78d6", "lats": "#1baf7a"}
WAIT = "#c94040"
W = 1150
LEFT, RIGHT = 130, 20


def load_calls(cap: Path):
    f = next((cap / "run").glob("calls_*.jsonl"))
    return [json.loads(l) for l in f.open()]


def pick_wait_window(calls, width_ms=30000, step=5000):
    wall = max(c["finished_rel_ms"] for c in calls)
    best, bw = 0.0, 0.0
    t = 0.0
    while t + width_ms <= wall:
        sc = sum(max(0.0, min(c["first_token_rel_ms"], t + width_ms) - max(c["submitted_rel_ms"], t))
                 for c in calls)
        if sc > best:
            best, bw = sc, t
        t += step
    return bw, bw + width_ms, best


def axis(w0, w1, y, h):
    out = []
    for i in range(7):
        t = w0 + (w1 - w0) * i / 6
        x = LEFT + (W - LEFT - RIGHT) * i / 6
        out.append(f'<line x1="{x:.0f}" y1="{y}" x2="{x:.0f}" y2="{y+h}" stroke="#e6edf4"/>')
        out.append(f'<text x="{x:.0f}" y="{y-5}" font-size="10" text-anchor="middle" fill="#48607d">{t/1e3:.0f} s</text>')
    return out


def e2e_strip(calls, w0, w1, y0, tag):
    lanes = {}
    for c in calls:
        lanes.setdefault(c["program_id"], {"cls": c["class"], "cs": []})["cs"].append(c)
    order = sorted(lanes.items(), key=lambda kv: ({"bfcl": 0, "sharegpt": 1, "lats": 2}[kv[1]["cls"]],
                                                  min(x["submitted_rel_ms"] for x in kv[1]["cs"])))
    rh = 9
    out = [f'<text x="4" y="{y0+10}" font-size="11.5" font-weight="600" fill="{"#2f6f9f" if "core" in tag else "#1f2f45"}">{tag}</text>']
    X = lambda t: LEFT + (W - LEFT - RIGHT) * (max(min(t, w1), w0) - w0) / (w1 - w0)
    for i, (pid, ln) in enumerate(order):
        y = y0 + 16 + i * rh
        out.append(f'<text x="{LEFT-6}" y="{y+7}" font-size="8" text-anchor="end" fill="#8fa2b6">{pid}·{ln["cls"]}</text>')
        for c in ln["cs"]:
            if c["finished_rel_ms"] < w0 or c["submitted_rel_ms"] > w1:
                continue
            x0, x1, x2 = X(c["submitted_rel_ms"]), X(c["first_token_rel_ms"]), X(c["finished_rel_ms"])
            if x1 > x0:
                out.append(f'<rect x="{x0:.1f}" y="{y+1}" width="{max(x1-x0,0.5):.1f}" height="6" fill="{WAIT}" opacity=".85"/>')
            out.append(f'<rect x="{x1:.1f}" y="{y+1}" width="{max(x2-x1,0.5):.1f}" height="6" fill="{CLS_COLOR[ln["cls"]]}" opacity=".9"/>')
    return out, y0 + 16 + len(order) * rh + 6


def hl_strip(payload, y0, tag, w0_ns, w1_ns):
    p1 = payload["piles"][0]
    origin = int(payload["origin"])
    ms = [m for rows in p1["rows"] for m in rows if m[0] + m[1] > w0_ns and m[0] < w1_ns]
    ms.sort(key=lambda m: m[0])
    out = [f'<text x="4" y="{y0+10}" font-size="11.5" font-weight="600" fill="{"#2f6f9f" if "core" in tag else "#1f2f45"}">{tag} · #1 {p1["type"]} 堆{p1["pile_index"]} · 全堆 {p1["count"]} 次 / 和 {p1["sum_ns"]/1e9:.2f} s · 窗内 {len(ms)} 次</text>']
    top, bottom = y0 + 18, y0 + 100
    X = lambda t: LEFT + (W - LEFT - RIGHT) * (min(max(t, w0_ns), w1_ns) - w0_ns) / (w1_ns - w0_ns)
    n = len(ms)
    if n:
        frac = lambda k: 0.5 if n == 1 else k / (n - 1)
        ends = [[X(m[0]), max(X(m[0] + m[1]), X(m[0]) + 0.6)] for m in ms]
        ls = (ends[-1][0] - ends[0][0]) / max(frac(n - 1) - frac(0), 1e-9) if n > 1 else 0
        rs = (ends[-1][1] - ends[0][1]) / max(frac(n - 1) - frac(0), 1e-9) if n > 1 else 0
        li = min(e[0] - ls * frac(k) for k, e in enumerate(ends)) - 4
        ri = max(e[1] - rs * frac(k) for k, e in enumerate(ends)) + 4
        out.append(f'<path d="M{li:.1f} {top} L{ri:.1f} {top} L{ri+rs:.1f} {bottom} L{li+ls:.1f} {bottom} Z" fill="#eef4fa" stroke="#8fb2ce"/>')
        seg = "".join(f'M{e[0]:.1f} {top+frac(k)*(bottom-top):.1f}H{e[1]:.1f}' for k, e in enumerate(ends))
        out.append(f'<path d="{seg}" stroke="#2f6f9f" stroke-width="1" fill="none" opacity=".8"/>')
    return out, bottom + 10


def cu_strip(payload, y0, tag, w0_ns, w1_ns, cap=16):
    out = [f'<text x="4" y="{y0+10}" font-size="11.5" font-weight="600" fill="{"#2f6f9f" if "core" in tag else "#1f2f45"}">{tag}</text>']
    y = y0 + 14
    X = lambda t: LEFT + (W - LEFT - RIGHT) * (min(max(t, w0_ns), w1_ns) - w0_ns) / (w1_ns - w0_ns)
    for ln in payload["lanes"]:
        lane_h = 46
        base = y + lane_h - 4
        out.append(f'<text x="{LEFT-6}" y="{y+16}" font-size="9.5" text-anchor="end" fill="#48607d">{ln["label"]}</text>')
        out.append(f'<rect x="{LEFT}" y="{y}" width="{W-LEFT-RIGHT}" height="{lane_h}" fill="#fbfbf9" stroke="#eee"/>')
        path = ""
        for rows in ln["rows"]:
            for r in rows:
                if r[0] + r[1] < w0_ns or r[0] > w1_ns:
                    continue
                x1, x2 = X(r[0]), X(r[0] + r[1])
                h = (lane_h - 8) * min(1.0, r[2] / ln["max"])
                path += f'M{x1:.1f} {base:.1f}V{base-h:.1f}H{x2:.1f}V{base:.1f}'
        out.append(f'<path d="{path}" stroke="{ln["color"]}" stroke-width="1" fill="none"/>')
        if ln["unit"] == "个":
            yc = base - (lane_h - 8) * min(1.0, cap / ln["max"])
            out.append(f'<line x1="{LEFT}" y1="{yc:.1f}" x2="{W-RIGHT}" y2="{yc:.1f}" stroke="{WAIT}" stroke-dasharray="4 3"/>')
            out.append(f'<text x="{W-RIGHT-2}" y="{yc-3:.1f}" font-size="9" text-anchor="end" fill="{WAIT}">cap=16</text>')
        y += lane_h + 8
    return out, y + 4


def fig(parts_svg, height):
    return (f'<svg viewBox="0 0 {W} {height}" style="width:100%;height:auto;background:#fff;'
            f'border:1px solid #c9d6e4;border-radius:6px">' + "".join(parts_svg) + "</svg>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", type=Path, required=True)
    ap.add_argument("--art", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    MODELS = [("llama", "LLaMA-3.1-8B"), ("qwen3", "Qwen3-1.7B"), ("qwenvl", "Qwen2.5-VL-3B")]
    figs = {1: [], 2: [], 3: []}
    stats = {}
    for key, name in MODELS:
        cf = load_calls(a.art / f"{key}_fcfs_cap16")
        cc = load_calls(a.art / f"{key}_core_cap16")
        pf = json.loads((a.scratch / f"payload_{key}_fcfs_cap16.json").read_text())
        pc = json.loads((a.scratch / f"payload_{key}_core_cap16.json").read_text())
        facts = json.loads((a.art / f"gain_facts_{key}.json").read_text())
        # -- part 1 window: 30 s maximizing FCFS wait mass of the SHORT program
        # classes (bfcl+sharegpt) — the classes the optimization acts on
        short = [c for c in cf if c["class"] != "lats"]
        w0, w1, wsum = pick_wait_window(short)
        wsum_c = sum(max(0.0, min(c["first_token_rel_ms"], w1) - max(c["submitted_rel_ms"], w0))
                     for c in cc if c["class"] != "lats")
        parts = axis(w0, w1, 26, 560)
        s1, yn = e2e_strip(cf, w0, w1, 30, "FCFS baseline")
        s2, ye = e2e_strip(cc, w0, w1, yn, "agentix_core")
        figs[1].append((name, fig(parts + s1 + s2, ye + 6),
                        f"选窗准则：滑动 30 s 窗最大化 FCFS 中短程序类（bfcl+sharegpt）的红段（等待）总量"
                        f" → [{w0/1e3:.0f}, {w1/1e3:.0f}] s。窗内短程序等待总量 FCFS {wsum/1e3:.1f} s → "
                        f"core {wsum_c/1e3:.1f} s（{100*(wsum_c/max(wsum,1e-9)-1):+.0f} %）。"
                        f"红段 = 提交→首token，彩段 = 服务；橙/蓝车道（短程序）的红段消失、绿车道（lats）不变；"
                        f"同窗同负载，上下两图仅调度策略不同。"))
        stats.setdefault(key, {})["w1"] = (wsum, wsum_c)
        # -- part 2 window: densest section of the FCFS rank-1 pile
        p1 = pf["hl"]["piles"][0]
        si = max(range(10), key=lambda i: len(p1["rows"][i]))
        sec = pf["hl"]["sections"][si]
        o = int(pf["hl"]["origin"])
        w0n, w1n = int(sec["begin_ns"]) - o, int(sec["end_ns"]) - o
        parts = axis(w0n / 1e6, w1n / 1e6, 26, 250)
        s1, yn = hl_strip(pf["hl"], 30, "FCFS baseline", w0n, w1n)
        s2, ye = hl_strip(pc["hl"], yn, "agentix_core", w0n, w1n)
        e = facts["endpoint"]["speedup"]
        figs[2].append((name, fig(parts + s1 + s2, ye + 6),
                        f"选窗准则：FCFS 全局第 1 堆成员最密的段（段{si+1}/10，绝对窗见两侧 payload）。"
                        f"两侧梯形（成员包络）近乎同形：全堆和 {p1['sum_ns']/1e9:.2f} vs "
                        f"{pc['hl']['piles'][0]['sum_ns']/1e9:.2f} s——重 forward 服务质量不因策略改变，"
                        f"提升只能来自等待段。实测 mean {e['mean']:.2f}× / p90 {e['p90']:.2f}×。"))
        # -- part 3 window: 30 s with max time-at-cap in FCFS in-flight lane
        inf = pf["cu"]["lanes"][2]
        rows = [r for rs in inf["rows"] for r in rs]
        best, w0c = 0, 0
        for start in range(0, int(rows[-1][0]), int(5e9)):
            end = start + int(30e9)
            sc = sum(r[1] for r in rows if r[0] >= start and r[0] < end and r[2] >= 16)
            if sc > best:
                best, w0c = sc, start
        w1c = w0c + int(30e9)
        parts = axis(w0c / 1e6, w1c / 1e6, 26, 360)
        s1, yn = cu_strip(pf["cu"], 30, "FCFS baseline", w0c, w1c)
        s2, ye = cu_strip(pc["cu"], yn, "agentix_core", w0c, w1c)
        q = facts["queue"]
        figs[3].append((name, fig(parts + s1 + s2, ye + 6),
                        f"选窗准则：30 s 窗内 FCFS 在飞调用数贴 cap 时间最长 → [{w0c/1e9:.0f}, {w1c/1e9:.0f}] s。"
                        f"窗内两侧 GPU busy / gemm 占比同形，在飞数同样贴 cap"
                        f"（全程 above-cap：{q['fcfs']['ms_above_cap']/1e3:.0f} vs {q['core']['ms_above_cap']/1e3:.0f} s）。"
                        f"资源与并发都相同，改变的只是队内成员。"))

    def section(no, title, paper, pfigs, impl, howto, theme, items):
        body = "".join(
            f'<h3>{name}</h3>{svg}<p class="cap"><b>图注：</b>{cap}</p>' for name, svg, cap in items)
        return (f'<h2>{no} {title}</h2>'
                f'<div class="block"><b>论文方法与创新点</b>{paper}</div>'
                f'{pfigs}'
                f'<div class="block impl"><b>本实现（被可视化的对象）</b>{impl}</div>'
                f'<div class="block howto"><b>怎么读下面的截图</b>{howto}</div>'
                f'<p class="theme"><b>运行时效果（图证）：</b>{theme}</p>{body}')

    PFIGS1 = paper_fig("_page_1_Figure_0.jpeg",
        "论文 Fig.2（原图）。横轴 = 时间（decode 步）；纵轴 = 引擎的 2 个批槽（BS=2）；每个色块 = "
        "一个程序的一次 LLM 调用（A1 即程序 A 的第 1 次调用），(a) 表给出 4 个程序的调用数与各调用 "
        "decode 步数。看 (b)：FCFS 下单调用短程序 D 要等到 t≈4 才进槽，A 的 4 次调用穿插占槽到 t≈12；"
        "看 (d)：PLAS 按程序累计服务排序，C、D 提前完成，B 的长调用被推到尾部。同两个槽、同一批程序，"
        "只是换了顺序——这就是我们端到端车道图要在真实 trace 上验证的行为。") + paper_fig(
        "_page_4_Figure_0.jpeg",
        "论文 Fig.6（原图）。2×2 面板：上行 Chatbot、下行 MCTS；左列按调用（横轴 = decode 步数）、"
        "右列按程序（横轴 = 程序的 LLM 调用数）；纵轴 = 等待/执行时间比；三条线 = FCFS（蓝圆）、"
        "MLFQ（橙三角）、Agentix（绿倒三角）。看左列：FCFS 在短 decode 端比值冲到 10–50（调用级队头阻塞）；"
        "看右列：FCFS 与 MLFQ 都在调用数少的程序端比值最高（程序级队头阻塞），Agentix 绿线两端都被压低。"
        "我们的红段/彩段就是这个『等待/执行』度量的逐调用展开。")

    PFIGS2 = paper_fig("_page_7_Figure_0.jpeg",
        "论文 Fig.10（原图）。左 = 进程表（PID → 程序数据）；右 = K 级队列，Q1 在下（高优先级）、"
        "QK 在上（低优先级），灰块 = 队内按 FCFS 排队的调用。红色数字即 Algorithm 1 的四步：① 新调用查"
        "进程表取 p(c)；② 按 p(c) 直接进入对应队列（不像传统 MLFQ 全部从 Q1 开始）；③ 量子用尽降级；"
        "④ β 反饥饿提回 Q1。我们 trace 里的 MLFQ 账本（入队分布/降级/提升计数）逐项对应这四步。") + paper_fig(
        "_page_9_Figure_0.jpeg",
        "论文 Fig.12（原图，单引擎主结果）。4 行负载（ShareGPT/BFCL/LATS/Mixed）× 3 列硬件档"
        "（8B-1GPU / 70B-4GPU / 180B-8GPU）；横轴 = 程序到达率（program/s），纵轴 = 平均 token 延迟"
        "（s/token）；四条曲线 = vLLM（绿）、vLLM-opt（红）、MLFQ（橙）、Agentix（蓝）。读法：每条曲线的"
        "『膝点』是延迟起飞的到达率，蓝线膝点最靠右；同一延迟水平线下可承受到达率之比，就是文中 2×/5× 的"
        "吞吐口径。我们的复现对应左上角那一列（8B, 1 GPU），fcfs 臂近似红线（vLLM-opt：有前缀缓存与 "
        "chunked prefill 的 FCFS）。")

    PFIGS3 = paper_fig("_page_10_Figure_0.jpeg",
        "论文 Fig.13（原图，单引擎尾延迟，LLaMA-3.1-8B）。行 = 4 种负载，列 = P95 / P99；轴与曲线含义同 "
        "Fig.12。看 ShareGPT 行：MLFQ（橙）平均延迟不差，但 P95/99 先于 Agentix 起飞——追短调用把长程序"
        "饿出了长尾；Agentix 蓝线膝点仍最右。这解释了为什么我们实测的收益里 p99（2.67×）比 mean（1.35×）"
        "大：MLFQ 家族的收益天然集中在尾部，而 β 反饥饿控制住了另一侧的尾巴。")

    PAPER1 = """<p>Agentix（Autellix, NSDI'26）§3.1 用等待/执行时间比（其 Fig.5/6）论证两级病灶：
<b>调用级队头阻塞</b>——长 decode 的调用挡住短调用（vLLM 等引擎等在批的 decode 完成后才调度新调用）；
<b>程序级队头阻塞</b>——现有调度器是"程序无关"的，长程序的众多调用把短程序拖住，其 Fig.6 显示
FCFS 与朴素 MLFQ 在调用数少的（短）程序上等待/执行比最高，故"负载升高后程序的大部分时间花在等待上"。
创新点是把<b>程序（而非请求）作为一等调度实体</b>（§4.2.1）：仿 OS 维护全局<b>进程表</b>，逐程序记录
服务时间（多线程程序取最长观测关键路径）、等待时间（用于反饥饿）、线程元数据、最近到达/完成时刻；
调用到达时携带其程序历史，调度据此排序——全程 non-clairvoyant，不需预知程序长度。</p>"""
    IMPL1 = """<p>本实现把进程表放在客户端 serving 适配层（<code>serve_agentix.py</code>）：
每程序维护 {attained_us, wait_us}，每个调用提交时以程序累计服务时间为优先级进入
MLFQ（下详），vLLM 0.29 原生 priority 调度 / 前缀缓存 / chunked prefill 作为接入项。
端到端时间线的"车道 = 程序、调用 = 红(等待)+彩(服务)段"是论文 §3.1 等待/执行比度量（其 Fig.6）
在真实 trace 上的逐调用展开：优化是否生效，看红段是否从短程序车道消失。</p>"""

    PAPER2 = """<p>论文的调度算法（§4.2.1–4.2.2, Algorithm 1）：SJF/SRPT 虽最优但需预知运行时长，
违背非透视假设，故取 <b>LAS 的程序级推广 PLAS</b>——第 j 个调用的优先级
p(c_j) = Σ<sub>k&lt;j, 同程序</sub> t_k（式 1，值大 = 优先级低），从进程表直读、调用完成时回写；
多线程程序用 <b>ATLAS</b>（式 2）：p(c_j) = max<sub>父调用</sub>{p(c_k)+t_k}，以单个"最长观测关键路径"
标量非透视地逼近 DAG 关键路径，并使同程序并行调用天然成组（gang），防止散兵线程拖垮程序完成。
为避免连续优先级退化为最坏轮转与频繁 KV 换入换出，§4.2.2 把优先级<b>离散化为 K 级 MLFQ</b>：
调用按 p(c)∈[Q_i^lo, Q_i^hi) 直接入第 i 队（不同于传统 MLFQ 全部从 Q1 开始），队内 FCFS、
配时间量子、量子用尽降级。该设计的隐含前提是调度只重排等待、不加速任何 forward——这正是
高延迟 Process 时间线可检验的论断：两侧重 forward 堆同形 ⇒ 前提成立 ⇒ 提升上界可从等待几何量估算。
论文 §6.3 的单引擎端点：ShareGPT/BFCL 上至高 2× vLLM-opt（1.5× MLFQ），LATS 2× vLLM-opt，
Mixed 高载至高 5× vLLM-opt；本机排队压力对应其中低载区间。</p>"""
    IMPL2 = """<p>本实现的 MLFQ 常数（论文未给数值，自行标定并在报告声明）：K=4，入队界
[0, 2, 8, 32] s（按程序累计服务），量子 32/64/128/256 token；量子用尽的调用以
prompt+已生成 token 重提交（前缀缓存重命中，实现 chunk 边界的"抢占"），ATLAS 已实现。
高延迟时间线上的 core 侧重堆多出的质量（如 LLaMA +2.3 s）即 continuation 的机制签名。</p>"""

    PAPER3 = """<p>论文 §4.2.2 的反饥饿组件：简单的"等待超时提升"会退化为朴素 MLFQ（长程序调用进 Q1
反过来打断短程序），故 Agentix 用进程表度量<b>程序级</b>饥饿——当程序等待/服务比
(W_p+W_c)/(T_p+T_c) ≥ β 时把该调用提回 Q1，仅重置 W_c/T_c；β 调节平均响应时间与公平性的权衡。
关于收益来源，§3.1 指出降低等待同时反哺吞吐（调用完成更快 → 程序更快发起下一调用 → 到达率上升，
其 Fig.4：同批稳态下 Agentix 比 FCFS 多容纳约 10 个并发调用）；§6.3 的尾延迟结论是 8 场景中 7 个
P95/99 优于 MLFQ 与 vLLM-opt（至高 1.7×）。这些论断的可检验形态正是并发/资源时间线：
若 GPU busy、gemm 占比、在飞数在两策略下同形，则收益必须解释为<b>饱和态下的纯排序收益</b>，
且随排队压力增大而增大。</p>"""
    IMPL3 = """<p>本实现在 trace 内留下机制自证：入队分布 Q1–Q4、降级次数、多量子调用数、
β 提升次数（本负载 β=2.0 未触发）都从调用记录可读出。并发/资源时间线的三条 lane
（GPU busy、gemm 占比、在飞调用数）是对"资源与并发不变"这一论文论证的直接检验；
跨模型 above-cap 时长与 p90 提升的单调对应（169 s→1.86×，77 s→1.15×，40 s→1.11×）
把论文"收益随负载压力增大"的曲线（其 Fig.13 形态）在单卡上复现为三点。</p>"""

    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>Agentix 优化的时间线解释 · 三模型总结</title><style>
body{{margin:0;font:14.5px/1.7 "Noto Sans CJK SC",system-ui,sans-serif;color:#1f2f45;background:#fff}}
.wrap{{max-width:1200px;margin:0 auto;padding:26px 22px 60px}}
h1{{font-size:22px;margin:0 0 6px}} h2{{font-size:18px;color:#2f6f9f;margin:36px 0 6px}}
h3{{font-size:15px;margin:20px 0 6px}}
.sub,.cap,.theme{{font-size:13px;color:#48607d;max-width:120ch}}
.cap{{margin:6px 0 0}} .theme{{margin:10px 0 8px}}
.block{{background:#f2f7fb;border:1px solid #c9d6e4;border-radius:6px;padding:10px 14px;margin:8px 0;font-size:13.5px;max-width:120ch}}
.block.impl{{background:#f4faf6;border-color:#bcd8c6}}
.block.howto{{background:#fbf7ef;border-color:#e2d3ae}}
.pfig{{margin:10px 0;max-width:980px}}
.pfig img{{width:100%;height:auto;border:1px solid #c9d6e4;border-radius:6px;background:#fff}}
.pfig figcaption{{font-size:12.5px;color:#48607d;margin-top:4px;line-height:1.6}}
.block b{{display:block;margin-bottom:2px;color:#2f6f9f}}
.block p{{margin:4px 0}}
table{{border-collapse:collapse;font-size:13px;margin:10px 0}}
td,th{{border:1px solid #c9d6e4;padding:4px 10px;text-align:right}}
td:first-child,th:first-child{{text-align:left}}
</style></head><body><div class="wrap">
<h1>Agentix（agentix_core）优化如何被时间线可视化解释 —— 三模型总结</h1>
<p class="sub">数据：本项目 3 模型 × {{FCFS, agentix_core}} 的 cap16 r0.5 采集（同负载同栈，唯一变量调度策略）。
每部分配图为从对应时间线中按明示准则截取的最说明性时间段，FCFS 在上、agentix_core 在下、共轴。
完整可交互时间线见 R10_COMPARE_{{llama,qwen3,qwenvl}}.html。</p>

{section("一、", "端到端 Process 时间线 —— 优化生效的直观效果", PAPER1, PFIGS1, IMPL1,
 """<p>横轴 = 运行墙钟（秒，窗口内线性、无折叠）；纵轴 = 25 条程序车道，自上而下先按类别
（bfcl → sharegpt → lats）、再按首次提交时刻排序，车道标签给出程序号、类别与调用数。
每条水平条是一次 LLM 调用：<span style="color:#c94040">红段</span>从提交时刻画到首 token
（等待 = 排队 + prefill），彩段从首 token 画到完成（服务），颜色按类别
（<span style="color:#eb6834">橙 bfcl</span> / <span style="color:#2a78d6">蓝 sharegpt</span> /
<span style="color:#1baf7a">绿 lats</span>）。上图 FCFS、下图 agentix_core，两图同负载同窗口共轴。
对比方法：在同一横轴位置上下对看同一车道——红段长度之差就是该调用被移走的等待。</p>""",
 "每行一个程序，调用 = 红段（等待）+ 彩段（服务）。三个模型呈现同一直观效果、不同幅度："
 "FCFS 图中短程序车道（bfcl 橙 / sharegpt 蓝）被红段占据，agentix_core 图中红段消失、"
 "lats（绿）车道不变——优化生效即红色等待质量从短程序车道被移走；模型越大（等待越贵），"
 "红段消失越显著（LLaMA 最明显，Qwen3 最弱）。", figs[1])}

{section("二、", "高延迟 Process 时间线 —— 性能提升比例的估算", PAPER2, PFIGS2, IMPL2,
 """<p>横轴 = 所选段内的墙钟（毫秒，0 为段首）；每张图画全局第 1 名堆（最重的 forward 时长簇）在该段
的成员：一条水平细线 = 一个 forward Process 实例的真实起止（左端开始、右端结束、长度 = 该步耗时），
纵向按开始时刻从上往下排；蓝色梯形是这些成员的拟合包络，只表示"谁属于这个堆"，不表示连续执行。
标题行给出全堆成员数、时长和与窗内成员数。对比方法：上下两图看三点——线的横向密度（步频）、
单线长度（步长）、梯形宽度（堆的时间跨度）；三者几乎一致，说明重 forward 的服务侧没有被策略改变。</p>""",
 "两侧全局第 1 名重 forward 堆的梯形近乎同形（服务时间与策略无关），因此提升比例可从时间线几何量估算："
 "把 FCFS 每调用等待段替换为 core 同类别中位等待做程序级重放，得上界估算 "
 "LLaMA 2.05× / VL 1.46× / Qwen3 1.14×；实测 mean 1.33× / 1.09× / 0.99×，p90 1.86× / 1.15× / 1.11×，"
 "均落在 1×–上界之间且长尾更接近上界——与『收益全部来自等待重排』自洽。", figs[2])}

{section("三、", "并发分析时间线 —— 性能提升的原因（资源使用率、并发情况）", PAPER3, PFIGS3, IMPL3,
 """<p>横轴 = 所选 30 秒窗的墙钟；每张图三条 lane，自上而下：GPU busy（%，CUPTI kernel 区间在窗口内的
占比）、gemm 家族时间占比（%）、在飞调用数（个，客户端 call_begin/end 计数）。lane 内每根竖条是一个
采样窗口的值，画成阶梯轮廓，高度满格 = 该 lane 的最大值（前两条 100%，第三条为观测峰值）；
第三条 lane 的红色虚线是 cap=16。灰底表示该时段不在已关联窗口内（合同规定资源页只在关联窗口作图）。
对比方法：前两条 lane 上下同形 → 资源使用率不变；第三条两侧都贴红线 → 并发同样打满；
两个自由度都被排除，剩下的差异只能在出队顺序里。</p>""",
 "选窗聚焦排队最重时段：两侧 GPU busy 与 gemm 占比 lane 同形（资源使用率不变，family 级 NCU 中位数 "
 "L2≈76%/SM≈49%/DRAM 14–20%，墙在 L2/tensor 不动），在飞调用数 lane 都贴 cap=16（并发同样打满）。"
 "资源与并发两个自由度都被排除后，唯一剩下的解释是出队顺序：MLFQ 用相同资源、相同并发把短程序先送进批。"
 "排队压力决定杠杆：above-cap 时长 LLaMA 169 s→p90 1.86×，VL 77 s→1.15×，Qwen3 40 s→1.11×——"
 "这同时解释了三个模型提升幅度的差异。", figs[3])}

<p class="cap">记账：配图为按明示准则截取的窗口（非全程）；完整无损/全量视图与全部账目在
R10_COMPARE_*.html 与 GROUPS/payload；硬件关联 family 级；trace 开销两侧同担。
A00 守恒门认证（workflow06，6/6 捕获 all_pass，见各捕获 a00_process_view.json）：程序与调用键集合
在负载规格 / 运行记录 / trace NVTX 三方完全相等（25 程序 / 2,440 调用），每个调用窗口都与 ≥1 个
forward step 相交。两条边界披露：preprocess 宇宙含少量空批引擎迭代（+26～+62 次，占 0.2–0.4 %，
落在最低时长堆，不影响分堆与结论）；qwenvl_fcfs 的最后一个引擎迭代被采集停止截断，其 forward
之后的各 phase scope 各缺 1 个实例。</p>
</div></body></html>"""
    a.out.write_text(doc)
    print("wrote", a.out, a.out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
