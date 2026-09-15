#!/usr/bin/env python3
"""One summary document, three parts (e2e intuitive effect / high-latency gain
estimate / concurrency-resource reason). Each part embeds, per model, a static
excerpt figure cropped from the timeline data at the most illustrative window
(picked programmatically, criterion stated in the caption), FCFS above and
agentix_core below on a shared axis."""
import argparse
import base64
import json
import sqlite3
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from render_w05_contract_views import lloyd_piles  # noqa: E402

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
        out.append(f'<text x="{x:.0f}" y="{y-12}" font-size="17" text-anchor="middle" fill="#48607d">{t/1e3:.0f} s</text>')
    return out


def class_lifecycle_figs(cf):
    """Preamble: one real exemplar program per class, drawn e2e-style on its own
    lifetime axis — load shape and lifecycle differences at a glance."""
    from collections import defaultdict
    progs = defaultdict(list)
    for c in cf:
        progs[c["program_id"]].append(c)
    out_blocks = []
    for cls, note in [("bfcl", "串行工具链：调用短而密，寿命被『等待+工具延迟』主导"),
                      ("sharegpt", "会话链：调用少、decode 长（彩段远长于 bfcl），寿命被服务段主导"),
                      ("lats", "树搜索：5 路并行波推进，寿命 = 关键路径（最慢的一路决定下一波开始）")]:
        cands = [(pid, cs) for pid, cs in progs.items() if cs[0]["class"] == cls]
        cands.sort(key=lambda kv: len(kv[1]))
        pid, cs = cands[len(cands) // 2]
        cs = sorted(cs, key=lambda c: c["submitted_rel_ms"])
        t0 = min(c["submitted_rel_ms"] for c in cs)
        t1 = max(c["finished_rel_ms"] for c in cs)
        X = lambda t: LEFT + (W - LEFT - RIGHT) * (t - t0) / max(t1 - t0, 1e-9)
        waves = sorted({c.get("wave", 0) for c in cs})
        rows = min(len(waves), 5) if cls == "lats" else 1
        H0 = 100 + rows * 48
        svg = [f'<text x="4" y="30" font-size="20" font-weight="600">{cls} · 程序 {pid} · {len(cs)} 个调用 · 寿命 {(t1-t0)/1e3:.1f} s（真实 trace，FCFS 侧）</text>']
        for i in range(7):
            t = t0 + (t1 - t0) * i / 6
            svg.append(f'<text x="{X(t):.0f}" y="60" font-size="15" text-anchor="middle" fill="#48607d">{(t-t0)/1e3:.1f}s</text>')
        for c in cs:
            r = (c.get("wave", 0) % 5) if cls == "lats" else 0
            y = 74 + r * 48
            x0, x1, x2 = X(c["submitted_rel_ms"]), X(c["first_token_rel_ms"]), X(c["finished_rel_ms"])
            svg.append(f'<rect x="{x0:.1f}" y="{y}" width="{max(x1-x0,0.5):.1f}" height="34" fill="{WAIT}" opacity=".85"/>')
            svg.append(f'<rect x="{x1:.1f}" y="{y}" width="{max(x2-x1,0.5):.1f}" height="34" fill="{CLS_COLOR[cls]}" opacity=".9"/>')
        if cls == "lats":
            svg.append(f'<text x="{LEFT-6}" y="{74+120}" font-size="15" text-anchor="end" fill="#48607d">5 路并行</text>')
        out_blocks.append(fig(svg, H0) + f'<p class="cap"><b>{cls} 的生命周期：</b>{note}。'
                          f'红段 = 等待（提交→首token），彩段 = 服务；横轴为该程序自身的寿命时间。</p>')
    return "".join(out_blocks)


def e2e_paired_strip(cf, cc, w0, w1, y0, rh=24, short_only=False, annotate=False):
    """One panel, lanes = programs; each program gets TWO adjacent sub-rows:
    FCFS on top, agentix_core below — same p side by side, calls stay in-lane."""
    lanes = {}
    for src, rows in (("f", cf), ("c", cc)):
        for c in rows:
            if short_only and c["class"] == "lats":
                continue
            if c["finished_rel_ms"] < w0 or c["submitted_rel_ms"] > w1:
                continue
            L = lanes.setdefault(c["program_id"], {"cls": c["class"], "f": [], "c": []})
            L[src].append(c)
    order = sorted(lanes.items(), key=lambda kv: ({"bfcl": 0, "sharegpt": 1, "lats": 2}[kv[1]["cls"]], kv[0]))
    pair_h = 2 * rh + 18
    out = []
    X = lambda t: LEFT + (W - LEFT - RIGHT) * (max(min(t, w1), w0) - w0) / (w1 - w0)
    for i, (pid, L) in enumerate(order):
        y = y0 + i * pair_h
        out.append(f'<text x="{LEFT-24}" y="{y+rh+3}" font-size="15" text-anchor="end" fill="#48607d">{pid}·{L["cls"]}</text>')
        for j, src in enumerate(("f", "c")):
            yy = y + j * rh
            out.append(f'<text x="{LEFT-4}" y="{yy+rh-1}" font-size="14" text-anchor="end" fill="{"#1f2f45" if src=="f" else "#2f6f9f"}">{"F" if src=="f" else "A"}</text>')
            for c in L[src]:
                x0, x1, x2 = X(c["submitted_rel_ms"]), X(c["first_token_rel_ms"]), X(c["finished_rel_ms"])
                out.append(f'<rect x="{x0:.1f}" y="{yy+3}" width="{max(x1-x0,0.5):.1f}" height="{rh-6}" fill="{WAIT}" opacity=".9"/>')
                out.append(f'<rect x="{x1:.1f}" y="{yy+3}" width="{max(x2-x1,0.5):.1f}" height="{rh-6}" fill="{CLS_COLOR[L["cls"]]}"/>')
                if annotate and x1 - x0 > 30:
                    out.append(f'<text x="{(x0+x1)/2:.0f}" y="{yy+rh-2}" font-size="13" text-anchor="middle" fill="#fff">{c["first_token_rel_ms"]-c["submitted_rel_ms"]:.0f}ms</text>')
        out.append(f'<line x1="{LEFT}" y1="{y+pair_h-9}" x2="{W-RIGHT}" y2="{y+pair_h-9}" stroke="#eef2ee"/>')
    return out, y0 + len(order) * pair_h + 6


def e2e_strip(calls, w0, w1, y0, tag):
    lanes = {}
    for c in calls:
        lanes.setdefault(c["program_id"], {"cls": c["class"], "cs": []})["cs"].append(c)
    order = sorted(lanes.items(), key=lambda kv: ({"bfcl": 0, "sharegpt": 1, "lats": 2}[kv[1]["cls"]],
                                                  min(x["submitted_rel_ms"] for x in kv[1]["cs"])))
    rh = 9
    out = [f'<text x="4" y="{y0+10}" font-size="20" font-weight="600" fill="{"#2f6f9f" if "core" in tag else "#1f2f45"}">{tag}</text>']
    X = lambda t: LEFT + (W - LEFT - RIGHT) * (max(min(t, w1), w0) - w0) / (w1 - w0)
    for i, (pid, ln) in enumerate(order):
        y = y0 + 16 + i * rh
        out.append(f'<text x="{LEFT-6}" y="{y+7}" font-size="14" text-anchor="end" fill="#8fa2b6">{pid}·{ln["cls"]}</text>')
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
    out = [f'<text x="4" y="{y0+10}" font-size="20" font-weight="600" fill="{"#2f6f9f" if "core" in tag else "#1f2f45"}">{tag} · #1 {p1["type"]} 堆{p1["pile_index"]} · 全堆 {p1["count"]} 次 / 和 {p1["sum_ns"]/1e9:.2f} s · 窗内 {len(ms)} 次</text>']
    top, bottom = y0 + 46, y0 + 300
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
    return out, bottom + 26


def cu_strip(payload, y0, tag, w0_ns, w1_ns, cap=16):
    out = [f'<text x="4" y="{y0+10}" font-size="20" font-weight="600" fill="{"#2f6f9f" if "core" in tag else "#1f2f45"}">{tag}</text>']
    y = y0 + 36
    X = lambda t: LEFT + (W - LEFT - RIGHT) * (min(max(t, w0_ns), w1_ns) - w0_ns) / (w1_ns - w0_ns)
    for ln in payload["lanes"]:
        lane_h = 138
        base = y + lane_h - 10
        out.append(f'<text x="{LEFT-6}" y="{y+16}" font-size="16" text-anchor="end" fill="#48607d">{ln["label"]}</text>')
        out.append(f'<rect x="{LEFT}" y="{y}" width="{W-LEFT-RIGHT}" height="{lane_h}" fill="#fbfbf9" stroke="#eee"/>')
        path = ""
        for rows in ln["rows"]:
            for r in rows:
                if r[0] + r[1] < w0_ns or r[0] > w1_ns:
                    continue
                x1, x2 = X(r[0]), X(r[0] + r[1])
                h = (lane_h - 24) * min(1.0, r[2] / ln["max"])
                path += f'M{x1:.1f} {base:.1f}V{base-h:.1f}H{x2:.1f}V{base:.1f}'
        out.append(f'<path d="{path}" stroke="{ln["color"]}" stroke-width="1" fill="none"/>')
        if ln["unit"] == "个":
            yc = base - (lane_h - 24) * min(1.0, cap / ln["max"])
            out.append(f'<line x1="{LEFT}" y1="{yc:.1f}" x2="{W-RIGHT}" y2="{yc:.1f}" stroke="{WAIT}" stroke-dasharray="4 3"/>')
            out.append(f'<text x="{W-RIGHT-2}" y="{yc-3:.1f}" font-size="15" text-anchor="end" fill="{WAIT}">cap=16</text>')
        y += lane_h + 24
    return out, y + 4


def fig(parts_svg, height):
    return (f'<svg viewBox="0 0 {W} {height}" style="width:100%;height:auto;background:#fff;'
            f'border:1px solid #c9d6e4;border-radius:6px">' + "".join(parts_svg) + "</svg>")


def compo_section(workload: Path):
    spec = json.loads(workload.read_text())
    from collections import defaultdict
    by = defaultdict(lambda: {"n": 0, "calls": [], "pt": [], "ot": [], "w": set()})
    for p in spec["programs"]:
        b = by[p["class"]]
        b["n"] += 1
        b["calls"].append(len(p["llm_calls"]))
        b["w"].add(p["width"])
        for c in p["llm_calls"]:
            b["pt"].append(c["prompt_tokens"])
            b["ot"].append(c["output_tokens"])
    row = lambda k, desc: (f'<tr><td>{k}</td><td>{desc}</td><td>{by[k]["n"]}</td>'
                           f'<td>{sum(by[k]["calls"])/by[k]["n"]:.1f}</td>'
                           f'<td>{max(by[k]["w"])}</td>'
                           f'<td>{sum(by[k]["pt"])/len(by[k]["pt"]):.0f} / {sum(by[k]["ot"])/len(by[k]["ot"]):.0f}</td></tr>')
    return f"""<h2>预备：Process 视图下的 program 与 call 到底是什么</h2>
<p class="theme">论文只把 program 说成"含控制流、反复发起 LLM 调用的通用程序"，没有给出组成。
本实验的负载规格（冻结 JSON）+ trace 把它具体化为四层 Process 层级，四层在 A00 守恒门下
三方对得上（规格 = 运行记录 = trace）：</p>
<ul class="theme"><li><b>program</b>：一个 agent 会话实例。三类共 25 个（下表）。每个 program 是
一条（或多条并行的）call 链：前一 call 的输出经工具/思考延迟后触发下一 call。</li>
<li><b>call</b>：一次 LLM 请求，即 trace 里一对 call_begin/end 标记的窗口 = 等待段（排队+prefill
首 token 前）+ 服务段（decode）。共 2,440 个。</li>
<li><b>step</b>：引擎的一次连续批迭代（一个 forward scope 实例，约 1.5 万个/捕获）。一个 step
同时服务多个 call 的各一小段 decode；反过来一个 call 的服务段由几十到上千个 step 的成员资格
拼成——这就是"调度只能改 call 进入 step 的顺序，改不了 step 本身"的结构原因。</li>
<li><b>scope</b>：step 内的引擎阶段（preprocess 调度与输入准备 / forward 模型前向 /
postprocess、sample 等）。</li></ul>
<table><tr><th>类别</th><th>组成（process 视角）</th><th>程序数</th><th>调用/程序</th><th>并行宽度</th><th>prompt/输出 token 均值</th></tr>
{row("sharegpt", "多轮会话：少量长 decode 调用串成链")}
{row("bfcl", "工具调用：十余个短 decode 调用密集串行")}
{row("lats", "树搜索：每波 5 个并行调用、近 200 调用的深链")}
</table>
<p class="theme">读后面所有图时的换算：橙/蓝车道（bfcl/sharegpt）是"短而多/短而长尾"的调用，
绿车道（lats）是巨量小调用的持续洪流；重 forward 堆的成员是"大 batch 的 step"，
不属于任何单个 call。</p>
{{CHAR_ART}}"""


def char_art(cf, cc, pf_hl):
    """Character-art process anatomy from real trace numbers (LLaMA pair)."""
    idx_f = {(r["program_id"], r["call_index"]): r for r in cf}
    idx_c = {(r["program_id"], r["call_index"]): r for r in cc}
    # worst-wait bfcl call present on both sides
    key = max((k for k, r in idx_f.items() if r["class"] == "bfcl" and k in idx_c),
              key=lambda k: idx_f[k]["first_token_rel_ms"] - idx_f[k]["submitted_rel_ms"])
    rf, rc = idx_f[key], idx_c[key]
    wf = rf["first_token_rel_ms"] - rf["submitted_rel_ms"]
    sf = rf["finished_rel_ms"] - rf["first_token_rel_ms"]
    wc = rc["first_token_rel_ms"] - rc["submitted_rel_ms"]
    sc = rc["finished_rel_ms"] - rc["first_token_rel_ms"]
    unit = max(wf + sf, wc + sc) / 46
    bar = lambda w, s: "█" * max(1, round(w / unit)) + "░" * max(1, round(s / unit))
    n_calls = sum(1 for r in cf if r["program_id"] == key[0])
    def med(t):
        v = sorted(d for p in pf_hl["piles"] if p["type"].endswith(t)
                   for rows in p["rows"] for _, d in rows)
        return v[len(v) // 2] / 1e3 if v else 0
    art = f"""program 层（每个 program 是一条 call 链；lats 为 5 路并行的波）
  bfcl    p=8 :  [c0]->[c1]->[c2]-> ... ->[c11]         12.5 call/程序, 串行, 工具延迟穿插
  sharegpt p=5:  [c0]----->[c1]----->[c2]->[c3]         4.6 call/程序, 长 decode
  lats   p=12 :  [c0 c1 c2 c3 c4] => [c5 .. c9] => ...  每波 5 个并行 call, ~193 call/程序

call 层（真实调用 {key[0]}#{key[1]}，bfcl，程序共 {n_calls} 个 call；█=等待 ░=服务，同一比例尺）
  FCFS        |{bar(wf, sf)}|  等待 {wf:,.0f} ms + 服务 {sf:,.0f} ms = {wf+sf:,.0f} ms
  agentix_core|{bar(wc, sc)}|  等待 {wc:,.0f} ms + 服务 {sc:,.0f} ms = {wc+sc:,.0f} ms
  —— 服务段几乎等长（{sf:,.0f} vs {sc:,.0f} ms），被移走的全部是 █ 等待段。

step 层（引擎一次连续批迭代；LLaMA 捕获的 scope 中位时长）
  [ preprocess ~{med('preprocess'):,.0f} µs | forward ~{med('forward'):,.0f} µs | sample/postprocess ... ]  × ~14,800 次/捕获
  一个 call 的 ░ 服务段 = 连续许多 step 中各占一片：
     step_k   [ c_a | c_b | …… | c_p ]   <= 一个 step 同时服务至多 16 个 call 各一个 token
     step_k+1 [ c_a | c_b | …… | c_p ]      调度改变的只是谁的 token 进入下一个 step"""
    return f'<pre class="art">{art}</pre>'


def call_top_pile(calls_rows):
    ms = [{"d": int((r["finished_rel_ms"] - r["submitted_rel_ms"]) * 1e6),
           "start": int(r["submitted_rel_ms"] * 1e6), "end": int(r["finished_rel_ms"] * 1e6),
           "id": i, "cls": r["class"], "pid": r["program_id"], "idx": r["call_index"]}
          for i, r in enumerate(calls_rows)]
    return lloyd_piles(ms)[4]


def e2e_zoom_strip(calls, w0, w1, y0, tag):
    """Paper-Fig.2-grained zoom: only short-program lanes, thick bars, short window."""
    lanes = {}
    for c in calls:
        if c["class"] == "lats" or c["finished_rel_ms"] < w0 or c["submitted_rel_ms"] > w1:
            continue
        lanes.setdefault(c["program_id"], {"cls": c["class"], "cs": []})["cs"].append(c)
    order = sorted(lanes.items(), key=lambda kv: (kv[1]["cls"], kv[0]))
    rh = 20
    out = [f'<text x="4" y="{y0+12}" font-size="20" font-weight="600" fill="{"#2f6f9f" if "core" in tag else "#1f2f45"}">{tag}</text>']
    X = lambda t: LEFT + (W - LEFT - RIGHT) * (max(min(t, w1), w0) - w0) / (w1 - w0)
    for i, (pid, ln) in enumerate(order):
        y = y0 + 18 + i * rh
        out.append(f'<text x="{LEFT-6}" y="{y+12}" font-size="16" text-anchor="end" fill="#48607d">{pid}·{ln["cls"]}</text>')
        for c in ln["cs"]:
            x0, x1, x2 = X(c["submitted_rel_ms"]), X(c["first_token_rel_ms"]), X(c["finished_rel_ms"])
            out.append(f'<rect x="{x0:.1f}" y="{y+3}" width="{max(x1-x0,0.6):.1f}" height="12" fill="{WAIT}" opacity=".9"/>')
            out.append(f'<rect x="{x1:.1f}" y="{y+3}" width="{max(x2-x1,0.6):.1f}" height="12" fill="{CLS_COLOR[ln["cls"]]}"/>')
            if x1 - x0 > 30:
                out.append(f'<text x="{(x0+x1)/2:.0f}" y="{y+12}" font-size="14" text-anchor="middle" fill="#fff">{c["first_token_rel_ms"]-c["submitted_rel_ms"]:.0f}ms</text>')
    return out, y0 + 18 + len(order) * rh + 6


def pair_bars(seg_f, idx_c, y0):
    """Top short-class calls of the FCFS top pile vs the SAME call under core."""
    shorts = sorted([m for m in seg_f if m["cls"] != "lats"], key=lambda m: -m["d"])[:5]
    out = []
    y = y0
    dmax = max(m["d"] for m in shorts)
    X = lambda ns: LEFT + (W - LEFT - RIGHT - 120) * ns / dmax
    for m in shorts:
        rc = idx_c.get((m["pid"], m["idx"]))
        out.append(f'<text x="{LEFT-6}" y="{y+26}" font-size="16" text-anchor="end" fill="#48607d">{m["pid"]}#{m["idx"]} {m["cls"]}</text>')
        out.append(f'<rect x="{LEFT}" y="{y+8}" width="{X(m["d"])-LEFT:.1f}" height="30" fill="{WAIT}" opacity=".85"/>')
        out.append(f'<text x="{X(m["d"])+6:.0f}" y="{y+30}" font-size="15" fill="#1f2f45">FCFS {m["d"]/1e9:.1f} s</text>')
        if rc:
            dc = (rc["finished_rel_ms"] - rc["submitted_rel_ms"]) * 1e6
            out.append(f'<rect x="{LEFT}" y="{y+44}" width="{max(X(dc)-LEFT,1):.1f}" height="30" fill="#2f6f9f" opacity=".85"/>')
            out.append(f'<text x="{X(dc)+6:.0f}" y="{y+66}" font-size="15" fill="#2f6f9f">core {dc/1e9:.1f} s（{m["d"]/max(dc,1):.1f}×）</text>')
        y += 96
    return out, y + 4


def call_pile_strip(seg, y0, tag, w0, w1):
    from collections import Counter
    comp = Counter(m["cls"] for m in seg)
    lab = " ".join(f"{k}:{v}" for k, v in comp.most_common())
    out = [f'<text x="4" y="{y0+11}" font-size="20" font-weight="600" fill="{"#2f6f9f" if "core" in tag else "#1f2f45"}">{tag} · 最高时长堆：{len(seg)} 个调用 · 合计 {sum(m["d"] for m in seg)/1e9:.0f} s · 单次 {seg[0]["d"]/1e9:.1f}–{seg[-1]["d"]/1e9:.1f} s · 构成 {lab}</text>']
    top, bottom = y0 + 44, y0 + 320
    X = lambda t: LEFT + (W - LEFT - RIGHT) * (min(max(t, w0), w1) - w0) / (w1 - w0)
    ms = sorted(seg, key=lambda m: m["start"])
    n = len(ms)
    frac = lambda k: 0.5 if n == 1 else k / (n - 1)
    ends = [[X(m["start"]), max(X(m["end"]), X(m["start"]) + 0.8)] for m in ms]
    ls = (ends[-1][0] - ends[0][0]) if n > 1 else 0
    rs = (ends[-1][1] - ends[0][1]) if n > 1 else 0
    li = min(e[0] - ls * frac(k) for k, e in enumerate(ends)) - 4
    ri = max(e[1] - rs * frac(k) for k, e in enumerate(ends)) + 4
    out.append(f'<path d="M{li:.1f} {top} L{ri:.1f} {top} L{ri+rs:.1f} {bottom} L{li+ls:.1f} {bottom} Z" fill="#eef4fa" stroke="#8fb2ce"/>')
    for k, m in enumerate(ms):
        yy = top + frac(k) * (bottom - top)
        out.append(f'<path d="M{ends[k][0]:.1f} {yy:.1f}H{ends[k][1]:.1f}" stroke="{CLS_COLOR.get(m["cls"], "#888")}" stroke-width="{5 if m["cls"] != "lats" else 2.2}" opacity="{0.95 if m["cls"] != "lats" else 0.45}"/>')
    return out, bottom + 28


def kernel_micro_best(sq: Path, abs_lo, abs_hi, span_ns):
    """Densest 300 ms (max kernel busy) inside [abs_lo, abs_hi) — the honest
    place to look at the wall."""
    db = sqlite3.connect(str(sq))
    iv = sorted(db.execute(
        "select start, end from CUPTI_ACTIVITY_KIND_KERNEL where start < ? and end > ?",
        (abs_hi, abs_lo)).fetchall())
    db.close()
    step = span_ns // 3
    best, at = -1, abs_lo
    t = abs_lo
    while t + span_ns <= abs_hi:
        busy = sum(min(e, t + span_ns) - max(s, t) for s, e in iv
                   if s < t + span_ns and e > t)
        if busy > best:
            best, at = busy, t
        t += step
    return at


def kernel_micro_strip(sq: Path, y0, tag, abs0, span_ns):
    db = sqlite3.connect(str(sq))
    rows = db.execute(
        "select k.start, k.end, s.value from CUPTI_ACTIVITY_KIND_KERNEL k "
        "left join StringIds s on k.demangledName=s.id "
        "where k.start < ? and k.end > ?", (abs0 + span_ns, abs0)).fetchall()
    db.close()
    gemm = [(s, e) for s, e, n in rows if n and "gemm" in n.lower()]
    other = [(s, e) for s, e, n in rows if not (n and "gemm" in n.lower())]
    busy_iv = sorted([(max(s, abs0), min(e, abs0 + span_ns)) for s, e in gemm + other])
    merged, cur = [], None
    for s, e in busy_iv:
        if cur and s <= cur[1]:
            cur[1] = max(cur[1], e)
        else:
            cur = [s, e]
            merged.append(cur)
    busy = sum(e - s for s, e in merged) / span_ns * 100
    gsum = sum(min(e, abs0 + span_ns) - max(s, abs0) for s, e in gemm) / span_ns * 100
    X = lambda t: LEFT + (W - LEFT - RIGHT - 150) * (min(max(t, abs0), abs0 + span_ns) - abs0) / span_ns
    out = [f'<text x="4" y="{y0+11}" font-size="20" font-weight="600" fill="{"#2f6f9f" if "core" in tag else "#1f2f45"}">{tag} · 窗内 kernel {len(rows):,} 个 · GPU busy {busy:.0f} % · gemm 占 {gsum:.0f} %</text>']
    for lane_y, iv, col, name in [(y0 + 46, gemm, "#a8802f", "gemm 家族"), (y0 + 150, other, "#2f6f9f", "其它 kernel")]:
        out.append(f'<text x="{LEFT-6}" y="{lane_y+52}" font-size="16" text-anchor="end" fill="#48607d">{name}</text>')
        out.append(f'<rect x="{LEFT}" y="{lane_y}" width="{W-LEFT-RIGHT-150}" height="84" fill="#fbfbf9" stroke="#eee"/>')
        for s, e in iv:
            x1, x2 = X(s), X(e)
            out.append(f'<rect x="{x1:.2f}" y="{lane_y+8}" width="{max(x2-x1,0.25):.2f}" height="68" fill="{col}" opacity=".8"/>')
    bx = W - RIGHT - 130
    out.append(f'<text x="{bx}" y="{y0+34}" font-size="16" fill="#48607d">资源墙（NCU family 中位）</text>')
    for i, (lab, v, col) in enumerate([("L2", 76, "#9085e9"), ("SM/tensor", 49, "#1baf7a"), ("DRAM", 17, "#eb6834")]):
        bxx = bx + i * 44
        out.append(f'<rect x="{bxx}" y="{y0+50+(190*(1-v/100)):.1f}" width="26" height="{190*v/100:.1f}" fill="{col}" opacity=".85"/>')
        out.append(f'<text x="{bxx+13}" y="{y0+262}" font-size="15" text-anchor="middle" fill="#48607d">{lab} {v}%</text>')
    return out, y0 + 276, busy, gsum


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", type=Path, required=True)
    ap.add_argument("--art", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    MODELS = [("llama", "LLaMA-3.1-8B"), ("qwen3", "Qwen3-1.7B"), ("qwenvl", "Qwen2.5-VL-3B")]
    figs = {1: [], 2: [], 3: []}
    stats = {}
    audit = {"purpose": "excerpt-selection criteria and windows for R10_SUMMARY figures",
             "models": {}}
    compo_html = ""
    for key, name in MODELS:
        cf = load_calls(a.art / f"{key}_fcfs_cap16")
        cc = load_calls(a.art / f"{key}_core_cap16")
        pf = json.loads((a.scratch / f"payload_{key}_fcfs_cap16.json").read_text())
        pc = json.loads((a.scratch / f"payload_{key}_core_cap16.json").read_text())
        facts = json.loads((a.art / f"gain_facts_{key}.json").read_text())
        if key == "llama":
            compo_html = compo_section(
                Path("experiments/h23-agentix-8b/workloads/thr_mixed_r0.5.json")
            ).replace("{CHAR_ART}", char_art(cf, cc, pf["hl"])
                      + '<h2 style="font-size:22px">三类负载的真实生命周期（各取一个中位规模的程序实例）</h2>'
                      + class_lifecycle_figs(cf))
            # concretize the paper figures with our own trace numbers (LLaMA pair)
            idx_f0 = {(r["program_id"], r["call_index"]): r for r in cf}
            idx_c0 = {(r["program_id"], r["call_index"]): r for r in cc}
            k0 = max((k for k, r in idx_f0.items() if r["class"] == "bfcl" and k in idx_c0),
                     key=lambda k: idx_f0[k]["first_token_rel_ms"] - idx_f0[k]["submitted_rel_ms"])
            rf0, rc0 = idx_f0[k0], idx_c0[k0]
            def ratio(rows, cls):
                w = [r["first_token_rel_ms"] - r["submitted_rel_ms"] for r in rows if r["class"] == cls]
                s = [r["finished_rel_ms"] - r["first_token_rel_ms"] for r in rows if r["class"] == cls]
                return sum(w) / max(sum(s), 1e-9)
            e0 = facts["endpoint"]
            spec0 = json.loads(Path("experiments/h23-agentix-8b/workloads/thr_mixed_r0.5.json").read_text())
            plist = lambda cls: "、".join(
                f"{p['program_id']}({len(p['llm_calls'])}调用)" for p in spec0["programs"] if p["class"] == cls)
            prog_note = (f"<br><b>纵轴上的程序是什么：</b>p 编号按到达顺序分配，同类程序只差到达时刻与"
                         f"抽样出的调用数/长度（负载对三个模型完全相同）。bfcl 类 8 个：{plist('bfcl')}；"
                         f"sharegpt 类 5 个：{plist('sharegpt')}；lats 类 12 个（p 编号其余，每程序约 193 调用、"
                         f"5 路并行波）。看图时车道标签的 \"pid·类别·调用数\" 就是这里的身份。")
            pfig_notes = {
                "{OUR_FIG2}": (f"我们 trace 里的真实对应：调用 {k0[0]}#{k0[1]}（bfcl）在 FCFS 下等待 "
                               f"{rf0['first_token_rel_ms']-rf0['submitted_rel_ms']:,.0f} ms 才进第一个 step，"
                               f"agentix_core 下同一调用只等 {rc0['first_token_rel_ms']-rc0['submitted_rel_ms']:,.0f} ms"
                               f"——就是图 (b)→(d) 里 D1 提前的实盘版本。"),
                "{OUR_FIG6}": (f"用我们 LLaMA 对照对算同一度量（类内等待总时长/执行总时长）："
                               f"bfcl 在 FCFS 下 {ratio(cf,'bfcl'):.1f} → core {ratio(cc,'bfcl'):.1f}，"
                               f"sharegpt {ratio(cf,'sharegpt'):.1f} → {ratio(cc,'sharegpt'):.1f}，"
                               f"lats {ratio(cf,'lats'):.2f} → {ratio(cc,'lats'):.2f}——与图中"
                               f"『绿线把左端压平、对长程序中性』的形态一致。"),
                "{OUR_FIG10}": (f"我们 trace 里的 MLFQ 账本逐项对应这四步（LLaMA core）：① 进程表查得 p(c) 后"
                                f"② 直接入队 Q1–Q4 = {'/'.join(str(v) for v in facts['mlfq']['admission'].values())}，"
                                f"③ 量子用尽降级 {facts['mlfq']['demotions']} 次（多量子调用 {facts['mlfq']['multi_quantum_calls']} 个），"
                                f"④ β 提升 {facts['mlfq']['promotions']} 次（β=2.0 未触发饥饿线）。"),
                "{OUR_FIG12}": (f"我们的实测点落在该列 0.5 program/s 处：FCFS "
                                f"{e0['fcfs']['ptl']['mean']/1e3:.4f} s/token、agentix_core "
                                f"{e0['core']['ptl']['mean']/1e3:.4f} s/token（{e0['speedup']['mean']:.2f}×）——"
                                f"位于蓝红两线膝点之前的区间，与图中该负载段两线的间距量级一致。"),
                "{OUR_FIG13}": (f"我们的对应实测（LLaMA，0.5 program/s）：p99 加速 {e0['speedup']['p99']:.2f}× "
                                f"> p90 {e0['speedup']['p90']:.2f}× > mean {e0['speedup']['mean']:.2f}×——"
                                f"收益向尾部集中的次序与该图相同。"),
            }
        # -- part 1 window: 30 s maximizing FCFS wait mass of the SHORT program
        # classes (bfcl+sharegpt) — the classes the optimization acts on
        short = [c for c in cf if c["class"] != "lats"]
        w0, w1, wsum = pick_wait_window(short)
        wsum_c = sum(max(0.0, min(c["first_token_rel_ms"], w1) - max(c["submitted_rel_ms"], w0))
                     for c in cc if c["class"] != "lats")
        parts = axis(w0, w1, 60, 1700)
        s12, ye = e2e_paired_strip(cf, cc, w0, w1, 70)
        # paper-grained zoom around the worst-wait short call in the window
        shorts_w = [c for c in cf if c["class"] != "lats" and w0 <= c["submitted_rel_ms"] <= w1]
        wc0 = max(shorts_w, key=lambda c: c["first_token_rel_ms"] - c["submitted_rel_ms"]) if shorts_w else None
        zoom_html = ""
        if wc0:
            z0 = max(0.0, wc0["submitted_rel_ms"] - 500)
            z1 = wc0["finished_rel_ms"] + 1500
            zp = axis(z0, z1, 60, 900)
            za, zy2 = e2e_paired_strip(cf, cc, z0, z1, 70, rh=42, short_only=True, annotate=True)
            zoom_html = (f'<p class="cap"><b>放大（论文 Fig.2 粒度，{(z1-z0)/1e3:.1f} s 窗，仅短程序，'
                         f'每程序 F/A 两行相邻，红段内标注等待毫秒数）：</b>同一程序上下两行直接对看，'
                         f'F 行红段以秒计、A 行以十毫秒计。</p>'
                         + fig(zp + za, zy2 + 6))
        figs[1].append((name, fig(parts + s12, ye + 6) + zoom_html,
                        f"图示 [{w0/1e3:.0f}, {w1/1e3:.0f}] s 这 30 秒里的全部调用；**同一程序占相邻两行**："
                        f"上行 F = FCFS、下行 A = agentix_core，同程序的调用留在各自行内，上下对看即为"
                        f"同一负载在两种策略下的直接对比。看橙（bfcl）与蓝（sharegpt）程序：F 行几乎每条"
                        f"调用都拖着长红段（排在 lats 洪流后面），紧贴其下的 A 行红段消失——窗内短程序"
                        f"等待合计 {wsum/1e3:.1f} s → {wsum_c/1e3:.1f} s（{100*(wsum_c/max(wsum,1e-9)-1):+.0f} %）；"
                        f"绿（lats）程序的 F/A 两行肉眼无差别。"
                        f"process 视角：每条红段的消失都对应『该 call 更早获得第一个 step 的成员资格』。"
                        f"<br><b>轴注：</b>横轴数字 + \"s\" = 从运行起点起算的墙钟秒（所有 process 的公共时钟，"
                        f"call 的提交/首token/完成都落在这条轴上）；纵轴无刻度，一行 = 一个 program 的车道，"
                        f"行内每条横条 = 该 program 的一个 call；放大图中 \"ms\" = 该 call 红段（等待）的毫秒长度。"
                        "{PROG_NOTE}"))
        stats.setdefault(key, {})["w1"] = (wsum, wsum_c)
        audit["models"].setdefault(key, {})["part1"] = {
            "criterion": "sliding 30 s window maximizing FCFS short-class (bfcl+sharegpt) wait mass",
            "window_s": [w0 / 1e3, w1 / 1e3],
            "short_wait_s": {"fcfs": wsum / 1e3, "core": wsum_c / 1e3}}
        # -- part 2 lead figure: call-universe top-latency pile, cropped to the
        # densest 60 s so member lines are individually readable
        seg_f, seg_c = call_top_pile(cf), call_top_pile(cc)
        from collections import Counter
        short_f = sum(v for k, v in Counter(m["cls"] for m in seg_f).items() if k != "lats")
        short_c = sum(v for k, v in Counter(m["cls"] for m in seg_c).items() if k != "lats")
        win = int(60e9)
        best_n, cw0 = -1, 0
        for t in range(0, int(max(m["end"] for m in seg_f)) - win, int(5e9)):
            n = sum(1 for m in seg_f if m["start"] < t + win and m["end"] > t)
            if n > best_n:
                best_n, cw0 = n, t
        cw1 = cw0 + win
        in_f = [m for m in seg_f if m["start"] < cw1 and m["end"] > cw0]
        in_c = [m for m in seg_c if m["start"] < cw1 and m["end"] > cw0]
        parts_call = axis(cw0 / 1e6, cw1 / 1e6, 60, 740)
        c1, yn = call_pile_strip(in_f, 70, f"FCFS baseline（窗内 {len(in_f)}/{len(seg_f)} 成员）", cw0, cw1)
        c2, ye = call_pile_strip(in_c, yn, f"agentix_core（窗内 {len(in_c)}/{len(seg_c)} 成员）", cw0, cw1)
        e = facts["endpoint"]["speedup"]
        cap_call = (f"高延迟【调用】堆的对比（全程视图，每条线一个调用，粗线 = bfcl/sharegpt，"
                    f"细淡线 = lats）。上图（FCFS）的最高时长堆有 {len(seg_f)} 个调用、合计 "
                    f"{sum(m['d'] for m in seg_f)/1e9:.0f} s，其中 {short_f} 个是短程序调用——它们本该几秒完成，"
                    f"却因排队被抬进最高时长堆。下图（agentix_core）同一堆缩到 {len(seg_c)} 个调用、"
                    f"{sum(m['d'] for m in seg_c)/1e9:.0f} s，短程序成员只剩 {short_c} 个：agentix 的优势"
                    f"在高延迟视角就是『把不该出现在这里的调用清出去』。实测 mean {e['mean']:.2f}× / "
                    f"p90 {e['p90']:.2f}×。")
        # -- supporting figure: forward (step) top pile, cropped to the densest
        # 2 s so individual step durations are readable
        p1 = pf["hl"]["piles"][0]
        si = max(range(10), key=lambda i: len(p1["rows"][i]))
        sec = pf["hl"]["sections"][si]
        o = int(pf["hl"]["origin"])
        sw0, sw1 = int(sec["begin_ns"]) - o, int(sec["end_ns"]) - o
        starts = sorted(s for s, _ in p1["rows"][si])
        win2 = int(1e9)
        best_n, w0n = -1, sw0
        for t in range(sw0, max(sw0 + 1, sw1 - win2), int(200e6)):
            import bisect as _b
            n = _b.bisect_left(starts, t + win2) - _b.bisect_left(starts, t)
            if n > best_n:
                best_n, w0n = n, t
        w1n = w0n + win2
        parts = axis(w0n / 1e6, w1n / 1e6, 60, 740)
        s1, yn = hl_strip(pf["hl"], 70, "FCFS baseline", w0n, w1n)
        s2, ye2 = hl_strip(pc["hl"], yn, "agentix_core", w0n, w1n)
        cap_fwd = (f"高延迟【step】堆的对比（同一时段放大）。这两个梯形刻意地看不出区别——它们是"
                   f"『重 forward step』（大 batch/含 prefill 的引擎迭代），全堆和 {p1['sum_ns']/1e9:.1f} vs "
                   f"{pc['hl']['piles'][0]['sum_ns']/1e9:.1f} s。step 不属于任何单个调用，调度改不了它；"
                   f"上一张图里调用堆的巨大差异，全部来自调用进入这些 step 的顺序。两图合起来是"
                   f"提升比例估算的依据：服务侧不变 ⇒ 用等待几何量重放 baseline 得上界，"
                   f"本模型为程序级重放估算的上界（见 gain_facts 与审计文件）。")
        guide2 = (f'<p class="cap"><b>本模型三图导读（{name}）：</b>图一画『最贵的调用』——两侧各自的'
                  f'最高时长调用堆（FCFS {len(seg_f)} 个/{sum(m["d"] for m in seg_f)/1e9:.0f} s，'
                  f'core {len(seg_c)} 个/{sum(m["d"] for m in seg_c)/1e9:.0f} s），看的是堆的大小与颜色构成'
                  f'（粗彩线 = 被排队抬进来的短程序调用）；图二从图一里挑出最长的 5 个短程序调用，'
                  f'与 core 侧的同一调用逐个配对，看的是单个调用的倍数差；图三画『最贵的 step』——'
                  f'两侧重 forward step 堆在同一 1 秒窗内的逐条对比，看的是两侧纹理是否一致（应当一致：'
                  f'step 是共享的引擎迭代，机制改不动它）。三图合读：图三钉死服务不变，图一/图二把'
                  f'全部差异归到等待上。</p>')
        idx_cc = {(r["program_id"], r["call_index"]): r for r in cc}
        pb, pby = pair_bars(seg_f, idx_cc, 70)
        pb_head = [f'<text x="{LEFT}" y="36" font-size="17" fill="#48607d">同一调用两种策略下的端到端时长（上条 FCFS 红、下条 core 蓝；取 baseline 高延迟堆中最长的 5 个短程序调用）</text>']
        figs[2].append((name, guide2 + fig(parts_call + c1 + c2, ye + 6) +
                        f'<p class="cap"><b>图注：</b>{cap_call}'
                        f'<br><b>轴注：</b>横轴 \"s\" = 全程墙钟秒；一条线 = 一个 call 从提交到完成的窗口，'
                        f'线长 = 该 call 的端到端时长（等待+服务）；梯形只圈成员归属。</p>' +
                        fig(pb_head + pb, pby + 6) +
                        f'<p class="cap"><b>放大（逐调用配对）：</b>同一个 call（同 program 同序号）在两种策略下的'
                        f'端到端时长直接对比——差值全部是等待。<b>轴注：</b>横轴为时长（条长正比于秒数，'
                        f'条尾标注实际秒数与倍数）；行标签 = program#call 序号与类别。</p>' +
                        fig(parts + s1 + s2, ye2 + 6), cap_fwd +
                        "<br><b>轴注：</b>横轴 \"ms\" = 所选段内墙钟毫秒（0 为段首）；一条细线 = 一个 forward "
                        "step（引擎一次迭代的模型前向 scope），线长 = 该 step 的耗时；纵向只是排列顺序，无量纲。"))
        audit["models"][key]["part2"] = {
            "call_pile": {"universe": "call durations, lloyd 5 piles, top pile shown",
                          "fcfs": {"n": len(seg_f), "sum_s": sum(m['d'] for m in seg_f)/1e9,
                                   "short_members": short_f},
                          "core": {"n": len(seg_c), "sum_s": sum(m['d'] for m in seg_c)/1e9,
                                   "short_members": short_c}},
            "fwd_pile_window": {"criterion": "densest section of FCFS rank-1 forward pile",
                                "section": si + 1}}
        # -- part 3: 30 s lanes window (max time-at-cap) + 300 ms kernel microscope
        inf = pf["cu"]["lanes"][2]
        rows = [r for rs in inf["rows"] for r in rs]
        best, w0c = 0, 0
        for start in range(0, int(rows[-1][0]), int(5e9)):
            end = start + int(30e9)
            sc = sum(r[1] for r in rows if r[0] >= start and r[0] < end and r[2] >= 16)
            if sc > best:
                best, w0c = sc, start
        w1c = w0c + int(30e9)
        # detail comparison, not trend: display only the central 5 s of the
        # busiest window so each lane bar (~100 ms) is individually readable
        d0 = w0c + (w1c - w0c) // 2 - int(2500e6)
        d1 = d0 + int(5e9)
        parts = axis(d0 / 1e6, d1 / 1e6, 60, 1100)
        s1, yn = cu_strip(pf["cu"], 70, "FCFS baseline", d0, d1)
        s2, ye = cu_strip(pc["cu"], yn, "agentix_core", d0, d1)
        q = facts["queue"]
        span = int(300e6)
        sq_f = next((a.art / f"{key}_fcfs_cap16").glob("*.sqlite"))
        sq_c = next((a.art / f"{key}_core_cap16").glob("*.sqlite"))
        at_f = kernel_micro_best(sq_f, int(pf["hl"]["origin"]) + w0c, int(pf["hl"]["origin"]) + w1c, span)
        at_c = kernel_micro_best(sq_c, int(pc["hl"]["origin"]) + w0c, int(pc["hl"]["origin"]) + w1c, span)
        m1, ym, busy_f, g_f = kernel_micro_strip(sq_f, 70, "FCFS baseline", at_f, span)
        m2, ym2, busy_c, g_c = kernel_micro_strip(sq_c, ym + 4, "agentix_core", at_c, span)
        micro_axis = [f'<text x="{LEFT}" y="16" font-size="17" fill="#48607d">排队最重时段内最繁忙的 300 ms（真实比例，每个矩形一个 kernel）</text>']
        cap_lanes = (f"排队最重时段中部的 5 秒细节窗（每根竖条 ≈ 100 ms 的一个采样窗口，可逐根对比，"
                     f"不是趋势线）。上下两图逐条对看：GPU busy 与 gemm 占比的竖条起伏结构相同，"
                     f"在飞调用数每根都压着 cap=16 的红虚线（全程 above-cap {q['fcfs']['ms_above_cap']/1e3:.0f} vs "
                     f"{q['core']['ms_above_cap']/1e3:.0f} s）。细节相同不是『没有区别』，而是排除法的前半："
                     f"并发与资源两个自由度都被占满了。")
        cap_micro = (f"把排队最重时段里最繁忙的 300 ms 按真实比例展开看运行时细节：gemm kernel（黄）"
                     f"成串背靠背，其它 kernel（蓝）填在缝隙里——窗内 busy {busy_f:.0f} % / {busy_c:.0f} %，"
                     f"gemm 占 {g_f:.0f} % / {g_c:.0f} %，两侧微观结构同构，空白（GPU 空闲）主要来自"
                     f"step 间的 host 调度段，而这部分对两种策略同样存在。"
                     f"右侧参考条是资源墙：这些 gemm 在 NCU family 中位下 L2 已用到 76 %，SM/tensor 49 %，"
                     f"DRAM 只有 17 %——瓶颈顶在 L2/tensor 上，且两种策略顶在同一面墙上。"
                     f"process 视角的结论：step 内部已无油水，agentix 的收益只能来自 call→step 的排序，"
                     f"这正是它与 baseline 唯一不同的地方。")
        span2 = int(30e6)
        at_f2 = kernel_micro_best(sq_f, at_f, at_f + span, span2)
        at_c2 = kernel_micro_best(sq_c, at_c, at_c + span, span2)
        u1, uy, _, _ = kernel_micro_strip(sq_f, 70, "FCFS baseline", at_f2, span2)
        u2, uy2, _, _ = kernel_micro_strip(sq_c, uy + 4, "agentix_core", at_c2, span2)
        micro2_axis = [f'<text x="{LEFT}" y="16" font-size="17" fill="#48607d">再放大到 30 ms：单个 kernel 可分辨（一个 step 的一簇 gemm ≈ 模型各层的线性层依次发射）</text>']
        figs[3].append((name, fig(parts + s1 + s2, ye + 6) +
                        f'<p class="cap"><b>图注：</b>{cap_lanes}'
                        f'<br><b>轴注：</b>横轴 \"s\" = 全程墙钟秒；lane 高度为该指标的满量程'
                        f'（busy/gemm 满格 = 100 %，在飞满格 = 观测峰值，红虚线 = cap 16 个 call）。</p>' +
                        fig(micro_axis + m1 + m2, ym2 + 8) +
                        f'<p class="cap"><b>图注：</b>{cap_micro}'
                        f'<br><b>轴注：</b>横轴为该 300 ms 窗内的真实时间（比例尺一致）；黄行/蓝行'
                        f'每个矩形 = 一个 kernel 的起止；右侧竖条 = NCU 对 gemm 家族重放的中位利用率。</p>' +
                        fig(micro2_axis + u1 + u2, uy2 + 8),
                        f"30 ms 级放大：黄色 gemm 矩形逐个可辨——一簇 ≈ 一个 step 内模型各层线性层的"
                        f"依次发射，簇间空白是 step 间的 host 调度间隙。两侧的簇形、簇密度与空隙结构"
                        f"同构：机制没有改变任何一个 step 的内部，这就是收益只能来自 call 排序的"
                        f"kernel 级证据。<br><b>轴注：</b>横轴为 30 ms 窗内真实时间；行与矩形含义同上图。"))
        audit["models"][key]["part3"] = {
            "lanes_window": {"criterion": "30 s window with max FCFS time-at-cap",
                             "window_s": [w0c / 1e9, w1c / 1e9]},
            "microscope": {"criterion": "busiest 300 ms (max kernel busy) inside the lanes window, per side",
                           "busy_pct": {"fcfs": busy_f, "core": busy_c},
                           "gemm_pct": {"fcfs": g_f, "core": g_c}}}

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
        "只是换了顺序——这就是我们端到端车道图要在真实 trace 上验证的行为。{OUR_FIG2}") + paper_fig(
        "_page_4_Figure_0.jpeg",
        "论文 Fig.6（原图）。2×2 面板：上行 Chatbot、下行 MCTS；左列按调用（横轴 = decode 步数）、"
        "右列按程序（横轴 = 程序的 LLM 调用数）；纵轴 = 等待/执行时间比；三条线 = FCFS（蓝圆）、"
        "MLFQ（橙三角）、Agentix（绿倒三角）。看左列：FCFS 在短 decode 端比值冲到 10–50（调用级队头阻塞）；"
        "看右列：FCFS 与 MLFQ 都在调用数少的程序端比值最高（程序级队头阻塞），Agentix 绿线两端都被压低。"
        "我们的红段/彩段就是这个『等待/执行』度量的逐调用展开。{OUR_FIG6}")

    PFIGS2 = paper_fig("_page_7_Figure_0.jpeg",
        "论文 Fig.10（原图）。左 = 进程表（PID → 程序数据）；右 = K 级队列，Q1 在下（高优先级）、"
        "QK 在上（低优先级），灰块 = 队内按 FCFS 排队的调用。红色数字即 Algorithm 1 的四步：① 新调用查"
        "进程表取 p(c)；② 按 p(c) 直接进入对应队列（不像传统 MLFQ 全部从 Q1 开始）；③ 量子用尽降级；"
        "④ β 反饥饿提回 Q1。{OUR_FIG10}") + paper_fig(
        "_page_9_Figure_0.jpeg",
        "论文 Fig.12（原图，单引擎主结果）。4 行负载（ShareGPT/BFCL/LATS/Mixed）× 3 列硬件档"
        "（8B-1GPU / 70B-4GPU / 180B-8GPU）；横轴 = 程序到达率（program/s），纵轴 = 平均 token 延迟"
        "（s/token）；四条曲线 = vLLM（绿）、vLLM-opt（红）、MLFQ（橙）、Agentix（蓝）。读法：每条曲线的"
        "『膝点』是延迟起飞的到达率，蓝线膝点最靠右；同一延迟水平线下可承受到达率之比，就是文中 2×/5× 的"
        "吞吐口径。我们的复现对应左上角那一列（8B, 1 GPU），fcfs 臂近似红线（vLLM-opt：有前缀缓存与 "
        "chunked prefill 的 FCFS）。{OUR_FIG12}")

    PFIGS3 = paper_fig("_page_10_Figure_0.jpeg",
        "论文 Fig.13（原图，单引擎尾延迟，LLaMA-3.1-8B）。行 = 4 种负载，列 = P95 / P99；轴与曲线含义同 "
        "Fig.12。看 ShareGPT 行：MLFQ（橙）平均延迟不差，但 P95/99 先于 Agentix 起飞——追短调用把长程序"
        "饿出了长尾；Agentix 蓝线膝点仍最右。这解释了为什么我们实测的收益里 p99（2.67×）比 mean（1.35×）"
        "大：MLFQ 家族的收益天然集中在尾部，而 β 反饥饿控制住了另一侧的尾巴。{OUR_FIG13}")

    PAPER1 = """<p><b>论点：agent 程序的端到端延迟主要消耗在引擎队列里，而队列的病灶是"引擎不认识程序"
——这是一个只需换排序就能消除的病灶。</b></p>
<p><b>Baseline 是什么（论文实际评估的臂）：</b>vLLM 与 vLLM-opt（开了前缀缓存 + chunked prefill 的
vLLM，FCFS 调度），以及在其上加请求级抢占的朴素 MLFQ。沿一个请求走 baseline 的全栈：bfcl 程序的
第 5 个调用到达 → 作为孤立请求进 FCFS 队尾（引擎不知道它属于哪个程序、前面已经跑了多少）→
排在 lats 程序几十个调用之后 → 等到进批才开始 prefill/decode。算法与 kernel 层不参与调度决策
（论文未明确说明 baseline 在这两层有任何差异）。</p>
<p><b>看图（论文 Fig.2，下方第一张）：</b>(a) 表给 4 个程序，D 只有 1 个 4 步调用；(b) FCFS 甘特图里
D1 色块被 A、B 挤到 t≈4 才进槽；(d) PLAS 同样两个槽、同样的色块，只换顺序，C、D 左移提前完成。
论文 §3.1 再把它量化成 Fig.6（第二张）的等待/执行比：FCFS 蓝线在"短"端（左列短 decode、右列少
调用）翘得最高；朴素 MLFQ 橙线压住左列（调用级阻塞）却压不住右列（程序级阻塞）——它抢占的是
调用，不认识程序。</p>
<p><b>创新点如何对应解决：</b>动机——两级阻塞里更贵的一级在程序上；机制——仿 OS 的全局<b>进程表</b>
（§4.2.1）逐程序记录服务时间（多线程取最长观测关键路径）、等待时间、线程元数据与最近到达/完成
时刻，调用到达即携带程序历史进调度，全程不需预知长度；证据角色——同一请求在 Agentix 下的路径
只改一处：进队前先查表。<b>再看我们的 trace 图：</b>车道图是 Fig.2 的实盘放大版——每个程序 F/A
两行相邻，红段（等待）在 F 行成片、在紧邻的 A 行消失；Fig.2 里"色块只换位置不换大小"对应我们
图中彩段（服务）长度不变。边界：此效应只在引擎排队时存在（cap16 制造排队；不排队则 F/A 两行同形）。</p>"""
    IMPL1 = """<p>本实现把进程表放在客户端 serving 适配层（<code>serve_agentix.py</code>）：
每程序维护 {attained_us, wait_us}，每个调用提交时以程序累计服务时间为优先级进入
MLFQ（下详），vLLM 0.29 原生 priority 调度 / 前缀缓存 / chunked prefill 作为接入项。
端到端时间线的"车道 = 程序、调用 = 红(等待)+彩(服务)段"是论文 §3.1 等待/执行比度量（其 Fig.6）
在真实 trace 上的逐调用展开：优化是否生效，看红段是否从短程序车道消失。</p>"""

    PAPER2 = """<p><b>论点：Agentix 的调度器用"已获得的服务"替代"未知的剩余时长"做优先级，并把它离散进
K 级队列——由此获得的提升有一个可从时间线直接估算的上界，因为它不加速任何一次 forward。</b></p>
<p><b>Baseline 的缺陷（对照论文实际评估臂）：</b>SJF/SRPT 需预知运行时长（违背非透视前提，论文因此
不用）；vLLM-opt 的 FCFS 完全不排序；朴素 MLFQ 有量子和降级但按调用计费——长程序的每个新调用都
被当成新客人从最高队开始，短程序照样被挤。</p>
<p><b>看图（论文 Fig.10，下方第一张）怎么讲机制：</b>新调用从左上进来，① 查进程表拿到其程序累计服务
p(c)——这就是 <b>PLAS</b>（式 1：p(c<sub>j</sub>) = Σ<sub>k&lt;j, 同程序</sub> t<sub>k</sub>，即同程序先前调用运行时之和，值大 = 优先级低，"已经花了多少"
替代"还要花多少"）；② 顺红线按 p(c) <b>直接落进 Q1–QK 对应队</b>（与传统 MLFQ 全从 Q1 开始不同——
这一步正是治"长程序新调用插队"的药）；③ 量子用尽向低优先级降级；④ β 反饥饿拉回 Q1。多线程程序
用 <b>ATLAS</b>（式 2：p(c<sub>j</sub>) = max<sub>c<sub>k</sub> ∈ 父调用</sub>{p(c<sub>k</sub>) + t<sub>k</sub>}，单个最长观测关键路径标量近似 DAG 关键路径，
并行调用天然成组）。沿一个请求：bfcl 第 5 调用到达 → 查表得 p(c)≈几秒 → 直接进高队 → 先于
lats 巨量调用进批；GPU 上执行的 kernel 与 baseline 相同（论文未明确说明对 kernel 层有任何修改）。</p>
<p><b>证据角色与边界：</b>机制只动队列，不动 forward——看第二张示意图（Fig.12），四条曲线是"延迟
起飞点"，Agentix 蓝线膝点最靠右，但没有任何 step 变快。<b>再看我们的 trace 图：</b>图一/图二里
调用堆缩小与逐调用倍数差，是 Fig.10 第 ② 步在真实负载上的效果；图三两侧 step 堆纹理一致，是
"不动 forward"的实盘证据——也因此提升可用等待几何量重放并给出上界。论文 §6.3 端点：ShareGPT/BFCL
至高 2× vLLM-opt、Mixed 高载至高 5×；本机排队压力处于其低载区间，实测落在 1×–上界之间。</p>"""
    IMPL2 = """<p>本实现的 MLFQ 常数（论文未给数值，自行标定并在报告声明）：K=4，入队界
[0, 2, 8, 32] s（按程序累计服务），量子 32/64/128/256 token；量子用尽的调用以
prompt+已生成 token 重提交（前缀缓存重命中，实现 chunk 边界的"抢占"），ATLAS 已实现。
高延迟时间线上的 core 侧重堆多出的质量（如 LLaMA +2.3 s）即 continuation 的机制签名。</p>"""

    PAPER3 = """<p><b>论点：Agentix 的收益不来自资源利用率——在饱和引擎上它是纯排序收益，并用程序级
β 反饥饿保证重排不以长程序长尾为代价。</b></p>
<p><b>Baseline 的缺陷：</b>朴素 MLFQ 的反饥饿是"调用等超时就提回最高队"——长程序的调用一旦提升
反过来打断短程序，尾延迟改善以均值退化为代价（论文 Fig.13 的 ShareGPT 行：MLFQ 橙线在 P95/99
先于 Agentix 起飞）。沿一个请求：lats 长程序某调用等久了 → 朴素 MLFQ 立即升 Q1 → 插到 bfcl
短调用前面 → 短程序均值受损。</p>
<p><b>创新点如何对应解决（§4.2.2）：</b>动机——饥饿应按程序而非调用度量；机制——进程表算程序的
等待/服务比 (W<sub>p</sub>+W<sub>c</sub>)/(T<sub>p</sub>+T<sub>c</sub>)，≥ β 才把该调用提回 Q1，且只重置本调用的 W<sub>c</sub>/T<sub>c</sub>（β 调节均值
与公平性的权衡）；证据角色——看下方示意图（Fig.13），蓝线在均值端与尾端同时占优。§3.1 另给一个
吞吐副效应：等待降低 → 程序更快发起下一调用 → 稳态并发上升（其 Fig.4：约多容纳 10 个并发调用），
与我们观测的 core 吞吐 +4 % 同机理。</p>
<p><b>再看我们的 trace 图（可检验形态）：</b>若 5 秒细节窗里 GPU busy、gemm 占比、在飞数两侧逐条
同形，且 300 ms / 30 ms 显微图里 kernel 簇结构一致，则收益只能解释为<b>饱和态下的纯排序收益</b>。
我们的账本印证边界：β=2.0 下提升 0 次（本负载未触发饥饿线，反饥饿是保险而非收益来源），
p99 2.67× > mean 1.35× 与图中"尾部收益大于均值"的次序一致。</p>"""
    IMPL3 = """<p>本实现在 trace 内留下机制自证：入队分布 Q1–Q4、降级次数、多量子调用数、
β 提升次数（本负载 β=2.0 未触发）都从调用记录可读出。并发/资源时间线的三条 lane
（GPU busy、gemm 占比、在飞调用数）是对"资源与并发不变"这一论文论证的直接检验；
跨模型 above-cap 时长与 p90 提升的单调对应（169 s→1.86×，77 s→1.15×，40 s→1.11×）
把论文"收益随负载压力增大"的曲线（其 Fig.13 形态）在单卡上复现为三点。</p>"""

    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>Agentix 优化的时间线解释 · 三模型总结</title><style>
body{{margin:0;font:22px/1.7 "Noto Sans CJK SC",system-ui,sans-serif;color:#1f2f45;background:#fff}}
.wrap{{max-width:1200px;margin:0 auto;padding:26px 22px 60px}}
h1{{font-size:33px;margin:0 0 6px}} h2{{font-size:27px;color:#2f6f9f;margin:36px 0 6px}}
h3{{font-size:22px;margin:20px 0 6px}}
.sub,.cap,.theme{{font-size:20px;color:#48607d;max-width:120ch}}
.cap{{margin:6px 0 0}} .theme{{margin:10px 0 8px}}
.block{{background:#f2f7fb;border:1px solid #c9d6e4;border-radius:6px;padding:12px 16px;margin:10px 0;font-size:20px;max-width:120ch}}
.block.impl{{background:#f4faf6;border-color:#bcd8c6}}
.block.howto{{background:#fbf7ef;border-color:#e2d3ae}}
.pfig{{margin:10px 0;max-width:980px}}
.pfig img{{width:100%;height:auto;border:1px solid #c9d6e4;border-radius:6px;background:#fff}}
.pfig figcaption{{font-size:19px;color:#48607d;margin-top:4px;line-height:1.6}}
.block b{{display:block;margin-bottom:2px;color:#2f6f9f}}
.block p{{margin:4px 0}}
table{{border-collapse:collapse;font-size:20px;margin:10px 0}}
td,th{{border:1px solid #c9d6e4;padding:4px 10px;text-align:right}}
td:first-child,th:first-child{{text-align:left}}
pre.art{{background:#f7f9f7;border:1px solid #cfd9cf;border-radius:6px;padding:12px 14px;
font:18px/1.55 "IBM Plex Mono","Noto Sans Mono CJK SC",monospace;overflow-x:auto;max-width:1150px}}
</style></head><body><div class="wrap">
<h1>Agentix（agentix_core）优化如何被时间线可视化解释 —— 三模型总结</h1>
<p class="sub">数据：本项目 3 模型 × {{FCFS, agentix_core}} 的 cap16 r0.5 采集（同负载同栈，唯一变量调度策略）。
配图 FCFS 在上、agentix_core 在下、共轴；截取窗口与选材标准的完整记录在
R10_SUMMARY_AUDIT.json，报告正文只讲内容。完整可交互时间线见 R10_COMPARE_{{llama,qwen3,qwenvl}}.html。</p>

{compo_html}

{section("一、", "端到端 Process 时间线 —— 优化生效的直观效果", PAPER1, PFIGS1, IMPL1,
 """<p><b>图中缩写（process 视角）：</b>FCFS = 先来先服务（vLLM 原生调度，call 按到达序进 step）；
agentix_core = 论文机制的本实现（程序级 MLFQ 决定 call 进 step 的顺序）；bfcl / sharegpt / lats =
三类 program（组成见预备节表格）；首 token = 该 call 第一次被某个 step 服务产出的 token，
它之前的时间全部是排队与 prefill 等待。</p>
<p>横轴 = 运行墙钟（秒，窗口内线性、无折叠）；纵轴 = 25 条程序车道，自上而下先按类别
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
 """<p><b>图中缩写（process 视角）：</b>堆/pile = 时长相近的 process 实例簇（对数时长聚类，每宇宙
5 堆）；调用堆的宇宙 = 2,440 个 call 的总时长（等待+服务）；step 堆的宇宙 = 引擎迭代的 forward
scope 实例；PLAS = 程序累计服务时间优先级；MLFQ = 多级反馈队列（Q0–Q3 离散化 + 量子降级）；
ptl = program token latency，程序响应时间除以其生成 token 数；mean/p90 = 全体程序 ptl 的
均值/90 分位。</p>
<p>第一张图：横轴 = 全程墙钟（秒）；一条线 = 一个调用（起点提交、终点完成，长度 = 该 call 的
端到端时长），粗深线 = bfcl/sharegpt 调用、细淡线 = lats 调用；梯形 = 该堆成员的包络。
第二张图：横轴 = 所选段内的墙钟（毫秒，0 为段首）；每张图画全局第 1 名堆（最重的 forward 时长簇）在该段
的成员：一条水平细线 = 一个 forward Process 实例的真实起止（左端开始、右端结束、长度 = 该步耗时），
纵向按开始时刻从上往下排；蓝色梯形是这些成员的拟合包络，只表示"谁属于这个堆"，不表示连续执行。
标题行给出全堆成员数、时长和与窗内成员数。对比方法：上下两图看三点——线的横向密度（步频）、
单线长度（步长）、梯形宽度（堆的时间跨度）；三者几乎一致，说明重 forward 的服务侧没有被策略改变。</p>""",
 "每模型两张图。第一张是主图：高延迟【调用】堆——baseline 的最高时长堆里挤着大量被排队抬进来的"
 "短程序调用，agentix 把它们清了出去，堆的成员数与总时长都显著缩小，这是高延迟视角下最直接的优势"
 "证据。第二张是支撑图：高延迟【step】堆两侧同形（服务侧不变），它把第一张图的差异钉死为"
 "『纯排序效果』，并给出估算依据："
 "把 FCFS 每调用等待段替换为 core 同类别中位等待做程序级重放，得上界估算 "
 "LLaMA 2.05× / VL 1.46× / Qwen3 1.14×；实测 mean 1.33× / 1.09× / 0.99×，p90 1.86× / 1.15× / 1.11×，"
 "均落在 1×–上界之间且长尾更接近上界——与『收益全部来自等待重排』自洽。", figs[2])}

{section("三、", "并发分析时间线 —— 性能提升的原因（资源使用率、并发情况）", PAPER3, PFIGS3, IMPL3,
 """<p><b>图中缩写（process 视角）：</b>gemm = 批内线性层矩阵乘的 kernel 家族（step 的主要构成，
连续批把 decode 也保持成 GEMM 形）；在飞 = 已提交未完成的 call 数；cap=16 = 引擎最大批容量
（制造排队的实验设定）；L2 / SM(tensor) / DRAM = 三个硬件资源维度的利用率（NCU 对 gemm 家族
重放的中位数）；busy = 窗口内任意 kernel 在跑的时间占比。</p>
<p>第一张图（趋势）：横轴 = 所选 30 秒窗的墙钟；每张图三条 lane，自上而下：GPU busy（%，CUPTI kernel 区间在窗口内的
占比）、gemm 家族时间占比（%）、在飞调用数（个，客户端 call_begin/end 计数）。lane 内每根竖条是一个
采样窗口的值，画成阶梯轮廓，高度满格 = 该 lane 的最大值（前两条 100%，第三条为观测峰值）；
第三条 lane 的红色虚线是 cap=16。灰底表示该时段不在已关联窗口内（合同规定资源页只在关联窗口作图）。
对比方法：前两条 lane 上下同形 → 资源使用率不变；第三条两侧都贴红线 → 并发同样打满。</p>
<p>第二张图（放大）：从趋势窗中部取 300 ms 按真实比例展开，每个矩形是一个 kernel（黄 = gemm
家族一行，蓝 = 其它 kernel 一行），矩形之间的空白就是 GPU 空闲——看的是微观结构而非趋势；
右侧三根参考条是资源墙（L2/SM/DRAM 利用率）。对比方法：两侧 gemm 行同样背靠背致密、
busy 同水平、且都顶着同一面 L2/tensor 墙 → step 内部无优化空间，机制的作用面只剩排序。</p>""",
 "这一部分的结论不是『两侧没有区别』，而是『两侧顶着同一面资源墙』——这正是收益来源的证明主体。"
 "趋势图先排除两个自由度（资源使用率不变、并发同样打满）；放大图再把墙看实：最忙的 300 ms 里 "
 "GPU busy 也只有约 18–25%，gemm 以突发串出现、突发之间是 step 间的 host 调度空隙——即"
 "『计算突发内顶资源墙、突发间等 host』的双层结构，且两种策略逐项相同：突发内 NCU 中位 "
 "L2≈76%、SM/tensor≈49%、DRAM 仅 14–20%（墙在 L2/tensor），突发间的 host 空隙也同构。"
 "资源与并发两个自由度都被排除后，唯一剩下的解释是出队顺序：MLFQ 用相同资源、相同并发把短程序先送进批。"
 "排队压力决定杠杆：above-cap 时长 LLaMA 169 s→p90 1.86×，VL 77 s→1.15×，Qwen3 40 s→1.11×——"
 "这同时解释了三个模型提升幅度的差异。", figs[3])}

<h2>补充：host 侧代表 process（workload_analysis W1–W5 的产物）</h2>
<p class="theme">本版之前，报告只能说"host 开销大"，说不出大在哪——因为 process 宇宙里
<code>preprocess</code> 与 <code>schedule</code> 是不透明块。补做 workload_analysis 后，
三个模型各自的试运行→热点定位→插桩→代表采集→代表集选择（W1–W5）给出以下可归因结果，
新捕获已把它们全部纳入 process 宇宙（13–14 类 host process + 量子块/降级事件）：</p>
<table><tr><th>发现</th><th>LLaMA-3.1-8B</th><th>Qwen3-1.7B</th><th>Qwen2.5-VL-3B</th></tr>
<tr><td>preprocess 中 <code>_prepare_inputs</code> 占比</td><td>70 %（33.9 s）</td><td>（17.2 s）</td><td>（15.4 s）</td></tr>
<tr><td>其中 CUDA API 占比（其余为纯 Python）</td><td>19.1 %</td><td>21.8 %</td><td>20.1 %</td></tr>
<tr><td>主导空闲边界：sampled_token_ids → update_from_output</td><td>108.0 s</td><td>21.0 s</td><td>23.2 s</td></tr>
<tr><td>host 代表集覆盖 / 旧宇宙缺失份额</td><td>25.5 % / 13.6 %</td><td>43.4 % / 25.0 %</td><td>34.2 % / 19.5 %</td></tr>
<tr><td>量子块 / 降级事件（core 侧）</td><td>2,601 / 151</td><td>2,739 / 292</td><td>2,660 / 212</td></tr></table>
<p class="theme"><b>这改变了优化方向的判断：</b>此前从显微图只能得出"step 间有 host 空隙"；
现在可以定位到具体过程——最大的单项不是任何命名的 host 工作，而是<b>异步输出等待</b>
（引擎在 <code>set_async_sampled_token_ids</code> 之后、<code>update_from_output</code> 之前
的空档，LLaMA 上 108 s、约 13,568 次、平均 8 ms，期间 GPU 基本空闲），其规模超过 forward
本身（54.6 s）与全部命名 host 工作（37.6 s）之和；其次才是 <code>_prepare_inputs</code> 内部
约 80 % 的纯 Python 张量构建。两者都与调度策略无关，对 FCFS 与 agentix_core 同等存在，
因此不影响本报告的排序收益结论，但它们是下一步优化的主目标。插桩开销实测 −0.9 %。</p>
<p class="cap">记账：配图为截取窗口（非全程），每张图的选材标准与窗口参数记录在
R10_SUMMARY_AUDIT.json；完整无损/全量视图与全部账目在
R10_COMPARE_*.html 与 GROUPS/payload；硬件关联 family 级；trace 开销两侧同担。
A00 守恒门认证（workflow06，6/6 捕获 all_pass，见各捕获 a00_process_view.json）：程序与调用键集合
在负载规格 / 运行记录 / trace NVTX 三方完全相等（25 程序 / 2,440 调用），每个调用窗口都与 ≥1 个
forward step 相交。两条边界披露：preprocess 宇宙含少量空批引擎迭代（+26～+62 次，占 0.2–0.4 %，
落在最低时长堆，不影响分堆与结论）；qwenvl_fcfs 的最后一个引擎迭代被采集停止截断，其 forward
之后的各 phase scope 各缺 1 个实例。</p>
</div></body></html>"""
    for ph, txt in pfig_notes.items():
        doc = doc.replace(ph, txt)
    doc = doc.replace("{PROG_NOTE}", prog_note)
    a.out.write_text(doc)
    (a.out.parent / "R10_SUMMARY_AUDIT.json").write_text(json.dumps(audit, indent=2))
    print("wrote", a.out, a.out.stat().st_size // 1024, "KB, audit written")


if __name__ == "__main__":
    main()
