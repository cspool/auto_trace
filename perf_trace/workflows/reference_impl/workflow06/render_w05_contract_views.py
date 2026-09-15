#!/usr/bin/env python3
"""Workflow05 R10 contract views for the serving chain (two pages + GROUPS.json).

Implements the process/resource contract (AutoTrace perf_trace
skills/qwen-dcu-workflow05-trace-visualization-reporting/references/):

  Page 1  HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html
          selected Process types (>10 % of the summed-duration denominator,
          overlaps counted) -> 5 nonempty contiguous piles per type via
          deterministic 1-D log-duration Lloyd clustering -> global pile rank
          by pile duration sum desc (tie: type name, pile index). Every member
          is a true-start/true-end horizontal line inside its pile's fitted
          trapezoid outline; all piles share ONE folded clock (endpoint gaps
          capped at 2x median process duration, '>>' boundary markers);
          high-latency flags (per-type median+3*MAD) are annotations only.

  Page 2  CONCURRENCY_UTILIZATION.html
          associated-resource windows only: a pile is eligible if members'
          windows contain kernels of the NCU-profiled family carrying a valid
          NON-COMPUTE metric (DRAM active %, L2 %); compute (SM %) is context.
          Hidden piles keep their original rank numbers in the coverage list;
          the unfiltered denominator is reported.

Serving adaptation (declared): the Process universe is the worker-side scope
instances (schedule:* / gpu_model_runner:*) captured by nsys — the serving
chain's process_timeline. Hardware association is family-level (NCU replay of
the batched-GEMM family), never per-instance; this page states that scope.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

FOLD_CAP_FACTOR = 2.0
SECTIONS = 10


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_processes(sq: Path):
    db = sqlite3.connect(str(sq))
    strings = dict(db.execute("select id, value from StringIds"))
    procs = []
    for start, end, text, tid_, g in db.execute(
        "select start, end, text, textId, globalTid from NVTX_EVENTS"
    ):
        name = text if text else strings.get(tid_, "")
        if end and end > start and (name.startswith("schedule:") or name.startswith("gpu_model_runner:")):
            procs.append({"type": name[:60], "start": start, "end": end, "d": end - start})
    kernels = [(s, e, strings.get(n, "")) for s, e, n in db.execute(
        "select start, end, demangledName from CUPTI_ACTIVITY_KIND_KERNEL")]
    db.close()
    procs.sort(key=lambda p: (p["start"], p["end"]))
    for i, p in enumerate(procs):
        p["id"] = i
    return procs, kernels


def lloyd_piles(members):
    """Deterministic 1-D log-duration Lloyd clustering -> 5 nonempty contiguous piles."""
    ms = sorted(members, key=lambda m: (m["d"], m["start"], m["id"]))  # stable ties
    logs = [math.log(max(m["d"], 1)) for m in ms]
    n = len(ms)
    if n < 5:
        return None  # unsupported grouping, per contract
    # quantile-seeded centers, fixed iterations
    centers = [logs[min(n - 1, int((i + 0.5) * n / 5))] for i in range(5)]
    for _ in range(25):
        bounds = [ (centers[i] + centers[i + 1]) / 2 for i in range(4) ]
        groups = [[] for _ in range(5)]
        for v in logs:
            k = 0
            while k < 4 and v > bounds[k]:
                k += 1
            groups[k].append(v)
        centers = [ (sum(g) / len(g)) if g else centers[i] for i, g in enumerate(groups) ]
    bounds = [ (centers[i] + centers[i + 1]) / 2 for i in range(4) ]
    cuts = [0]
    j = 0
    for b in bounds:
        while j < n and logs[j] <= b:
            j += 1
        cuts.append(j)
    cuts.append(n)
    cuts = sorted(set(cuts))
    # enforce 5 nonempty contiguous piles: split largest runs if fewer cuts
    while len(cuts) - 1 < 5:
        sizes = [(cuts[i + 1] - cuts[i], i) for i in range(len(cuts) - 1)]
        sz, i = max(sizes)
        if sz < 2:
            break
        cuts.insert(i + 1, cuts[i] + sz // 2)
        cuts = sorted(set(cuts))
    piles = []
    for i in range(len(cuts) - 1):
        seg = ms[cuts[i]:cuts[i + 1]]
        if seg:
            piles.append(seg)
    return piles if len(piles) == 5 else None


def build_fold(intervals, cap_ns):
    """Piecewise mapping: gaps between consecutive selected endpoints capped at cap_ns."""
    pts = sorted({p for iv in intervals for p in iv})
    segs = []   # (real_start, real_end, folded_start)
    folded = 0
    prev = pts[0]
    marks = []
    for p in pts[1:]:
        gap = p - prev
        take = min(gap, cap_ns)
        if gap > cap_ns:
            marks.append(folded + take)
        segs.append((prev, p, folded, take / gap if gap else 1.0))
        folded += take
        prev = p
    def fmap(t):
        lo, hi = 0, len(segs) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if segs[mid][0] <= t:
                lo = mid
            else:
                hi = mid - 1
        rs, re, fs, ratio = segs[lo]
        return fs + (min(t, re) - rs) * ratio
    return fmap, folded, marks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture-dir", type=Path, required=True)
    ap.add_argument("--ncu-raw", type=Path, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    a = ap.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    sq = next(a.capture_dir.glob("*.sqlite"))
    procs, kernels = load_processes(sq)

    total_ns = sum(p["d"] for p in procs)
    by_type = defaultdict(list)
    for p in procs:
        by_type[p["type"]].append(p)
    selected = sorted([t for t, ms in by_type.items()
                       if sum(m["d"] for m in ms) * 10 > total_ns],
                      key=lambda t: -sum(m["d"] for m in by_type[t]))
    unsupported = []
    groups = []
    for t in selected:
        ps = lloyd_piles(by_type[t])
        if ps is None:
            unsupported.append(t)
            continue
        for idx, seg in enumerate(ps):
            groups.append({"type": t, "pile": idx, "members": seg,
                           "sum_ns": sum(m["d"] for m in seg)})
    groups.sort(key=lambda g: (-g["sum_ns"], g["type"], g["pile"]))
    for rank, g in enumerate(groups, 1):
        g["rank"] = rank

    # high-latency flags per type (median + 3*MAD), annotation only
    hl_thr = {}
    for t in selected:
        vals = [m["d"] for m in by_type[t]]
        med = statistics.median(vals)
        mad = statistics.median([abs(v - med) for v in vals]) or 1
        hl_thr[t] = med + 3 * mad

    # fold over union of selected member intervals
    med_d = statistics.median([m["d"] for t in selected for m in by_type[t]]) if selected else 1
    cap = int(FOLD_CAP_FACTOR * med_d) or 1
    sel_iv = [(m["start"], m["end"]) for g in groups for m in g["members"]]
    fmap, folded_total, marks = build_fold(sel_iv, cap)
    sections = [(i * folded_total // SECTIONS, (i + 1) * folded_total // SECTIONS) for i in range(SECTIONS)]

    # resource association: kernels of the profiled family inside member windows
    fam_rows = list(csv.reader(a.ncu_raw.open()))
    hdr = fam_rows[0]
    idx = {h: i for i, h in enumerate(hdr)}
    def med_metric(col):
        vs = [float(r[idx[col]].replace(",", "")) for r in fam_rows[2:] if r[idx[col]] not in ("", "n/a")]
        vs.sort()
        return vs[len(vs) // 2] if vs else None
    res = {"dram_pct": med_metric("dram__cycles_active.avg.pct_of_peak_sustained_elapsed"),
           "l2_pct": med_metric("lts__throughput.avg.pct_of_peak_sustained_elapsed"),
           "sm_pct": med_metric("sm__throughput.avg.pct_of_peak_sustained_elapsed")}
    gemm_iv = sorted((s, e) for s, e, n in kernels if "gemm" in n.lower())
    import bisect
    gstarts = [s for s, _ in gemm_iv]
    def has_gemm(m):
        i = bisect.bisect_left(gstarts, m["start"])
        return i < len(gemm_iv) and gemm_iv[i][0] < m["end"]
    for g in groups:
        g["assoc"] = sum(1 for m in g["members"] if has_gemm(m))

    groups_json = {
        "label": a.label, "source_sqlite": str(sq), "source_sha256": sha(sq),
        "process_universe": "worker-side scope instances (schedule:*, gpu_model_runner:*)",
        "total_process_ns": total_ns, "instances": len(procs),
        "selected_types": selected, "unsupported_grouping": unsupported,
        "hl_threshold_ns": hl_thr,
        "fold": {"cap_ns": cap, "policy": f"gaps capped at {FOLD_CAP_FACTOR}x median duration", "marks": len(marks)},
        "policy": {"selection": "type duration sum *10 > total (overlaps counted)",
                   "clustering": "deterministic 1-D log-duration Lloyd, 5 nonempty contiguous piles",
                   "ranking": "global pile duration sum desc; tie type name, pile index",
                   "resource_association": "family-level: NCU batched-GEMM replay medians attach to windows containing gemm kernels; never per-instance"},
        "groups": [{"rank": g["rank"], "type": g["type"], "pile": g["pile"],
                    "sum_ns": g["sum_ns"], "members": len(g["members"]),
                    "hl_members": sum(1 for m in g["members"] if m["d"] > hl_thr[g["type"]]),
                    "assoc_members": g["assoc"]} for g in groups],
    }
    (a.out_dir / "GROUPS.json").write_text(json.dumps(groups_json, indent=2))

    # ---- render pages (default: densest section; all sections listed with counts)
    def sect_of(t):
        f = fmap(t)
        for i, (lo, hi) in enumerate(sections):
            if lo <= f < hi or (i == SECTIONS - 1 and f == hi):
                return i
        return SECTIONS - 1
    dens = [0] * SECTIONS
    for g in groups:
        for m in g["members"]:
            dens[sect_of(m["start"])] += 1
    default_s = dens.index(max(dens))

    W, PAD = 1180, 40
    css = """
:root{--paper:#fafaf8;--card:#fff;--line:#e3e5e0;--ink:#14181a;--ink2:#5a625f;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--s7:#4a3aa7;--hl:#e34948;--accent:#0f6b63;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#15181a;--card:#1c2023;--line:#32383b;--ink:#eef0ee;--ink2:#a9b1ad;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s7:#9085e9;--hl:#e66767;--accent:#43b0a5;}}
:root[data-theme="dark"]{--paper:#15181a;--card:#1c2023;--line:#32383b;--ink:#eef0ee;--ink2:#a9b1ad;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s7:#9085e9;--hl:#e66767;--accent:#43b0a5;}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 "IBM Plex Sans",sans-serif}
.wrap{max-width:1240px;margin:0 auto;padding:30px 24px 60px}
h1{font-family:Archivo,sans-serif;font-size:26px;margin:0 0 6px}
.sub{color:var(--ink2);max-width:80ch;font-size:13.5px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;margin-top:12px;overflow-x:auto}
.plab{font:11.5px "IBM Plex Mono",monospace;fill:var(--ink2)}
.trap{fill:none;stroke:var(--accent);stroke-width:1.1;opacity:.75}
.mono{font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--ink2)}
svg{width:100%;height:auto;display:block}
"""
    type_color = {}
    palette = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s7)"]
    for i, t in enumerate(selected):
        type_color[t] = palette[i % len(palette)]

    def render_page(resource_mode: bool):
        s_lo, s_hi = sections[default_s]
        span = s_hi - s_lo or 1
        def X(t):
            return PAD + (W - 2 * PAD) * (fmap(t) - s_lo) / span
        rows_svg = []
        y = 30
        vis_groups = [g for g in groups if not resource_mode or g["assoc"] > 0]
        hidden = [g["rank"] for g in groups if resource_mode and g["assoc"] == 0]
        for g in vis_groups:
            mem = [m for m in g["members"] if s_lo <= fmap(m["start"]) < s_hi]
            mem.sort(key=lambda m: -m["d"])
            band_h = max(14, min(3, 1) * 0 + min(len(mem), 60) * 2 + 10)
            rows_svg.append(f'<text x="{PAD}" y="{y+10}" class="plab">#{g["rank"]} {g["type"][:44]} · pile{g["pile"]} · {len(mem)}/{len(g["members"])} 成员在本段'
                            + (f' · assoc {g["assoc"]}' if resource_mode else '') + '</text>')
            y0 = y + 14
            xs = []
            n_draw = min(len(mem), 60)
            for i, m in enumerate(mem[:60]):
                x1, x2 = X(m["start"]), X(min(m["end"], m["start"] + span))
                w = max(x2 - x1, 0.35)
                yy = y0 + i * 2
                col = "var(--hl)" if m["d"] > hl_thr[g["type"]] else type_color[g["type"]]
                rows_svg.append(f'<rect x="{x1:.1f}" y="{yy:.1f}" width="{w:.2f}" height="1.4" fill="{col}"><title>{g["type"]} d={m["d"]/1e3:.1f}us{" HL" if m["d"]>hl_thr[g["type"]] else ""}</title></rect>')
                xs.append((x1, x1 + w, yy))
            if xs:
                # fitted trapezoid: straight sides enclosing all member lines
                top, bot = xs[0], xs[-1]
                lmin = min(p[0] for p in xs); rmax = max(p[1] for p in xs)
                l_top = max(top[0], lmin); l_bot = min(bot[0], lmin) if len(xs)>1 else lmin
                rows_svg.append(f'<polygon class="trap" points="{min(top[0],lmin):.1f},{y0-2:.1f} {max(top[1],top[0]+1):.1f},{y0-2:.1f} {rmax:.1f},{xs[-1][2]+3:.1f} {lmin:.1f},{xs[-1][2]+3:.1f}"/>')
                if resource_mode:
                    bx = rmax + 8
                    for k, (key, colr) in enumerate([("dram_pct", "var(--s2)"), ("l2_pct", "var(--s7)")]):
                        v = res[key]
                        if v is not None:
                            rows_svg.append(f'<rect x="{bx+k*34:.1f}" y="{y0}" width="26" height="{max(1,(min(len(mem),60)*2)*v/100):.1f}" fill="{colr}" opacity=".8"><title>{key}={v:.1f}% (family-level NCU)</title></rect>')
                    rows_svg.append(f'<text x="{bx+70}" y="{y0+10}" class="plab">SM {res["sm_pct"]:.0f}% (context)</text>')
            y = y0 + min(len(mem), 60) * 2 + 12
        title = "CONCURRENCY_UTILIZATION" if resource_mode else "HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE"
        note = ("仅显示含已关联（family 级 NCU gemm 重放）非计算指标的堆；隐藏堆保留原始排名：" + (", ".join(f"#{r}" for r in hidden[:20]) or "无")
                if resource_mode else
                "入选类型全部真实 Process 区间；红色 = 高延迟（类型中位+3×MAD）注记；梯形轮廓仅表成员归属")
        html = f"""<title>{title} · {a.label}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600&family=IBM+Plex+Sans:wght@400;500&family=IBM+Plex+Mono&display=swap">
<style>{css}</style><div class="wrap">
<h1>{title}</h1>
<p class="sub">{a.label} · Process 宇宙 = worker 侧 scope 实例（{len(procs):,} 实例，{len(selected)} 类型入选，>10% 阈值）。
共享折叠时钟（端点间隔上限 2×中位时长 = {cap/1e3:.0f} µs，{len(marks)} 个 » 折叠点）；十段制，当前显示第 {default_s+1}/10 段（最密段，
各段成员数 {dens}）。每堆最多绘制 60 条成员线（其余在 GROUPS.json 完整记账）。{note}。</p>
<div class="panel"><svg viewBox="0 0 {W} {y+20}">{''.join(rows_svg)}</svg></div>
<p class="mono">GROUPS.json: 全部 {len(groups)} 堆的成员/时长/份额/排名 + 政策与源 sha256。可见范围与折叠不声称全量无损时间轴。</p></div>"""
        (a.out_dir / f"{title}.html").write_text(html)

    render_page(False)
    render_page(True)
    print(json.dumps({"out": str(a.out_dir), "instances": len(procs), "selected": selected,
                      "piles": len(groups), "unsupported": unsupported,
                      "default_section": default_s + 1, "fold_marks": len(marks)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
