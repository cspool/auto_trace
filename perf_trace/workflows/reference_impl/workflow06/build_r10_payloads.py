#!/usr/bin/env python3
"""Build reference-schema payloads (origin/sections/breaks/piles) for the three
R10 timelines of one serving capture, mirroring the archives_final batch16 pages:

  e2e  end-to-end request-level Process view: universe = client call windows
       (agentix.call_begin/end NVTX marks), one type per workload class,
       5 duration piles per class (contract pile plan applied to calls).
  hl   high-latency scope Process view: universe = worker scope instances,
       >10 % type selection, 5 log-duration Lloyd piles per type.
  cu   concurrency/resource lanes: GPU busy %, in-flight calls, gemm share,
       drawn only inside windows associated with gemm-family kernels.

Schema per view: {origin, sections[10]{section,begin_ns,end_ns,width_ns},
breaks[10][]{begin_ns,end_ns,true_ns,display_ns}, piles[]{rank,type,pile_index,
count,sum_ns,min_ns,max_ns,rows[10][[rel_start,dur]]}}; cu adds lanes/eligible.
"""
import argparse
import json
import sqlite3
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from render_w05_contract_views import lloyd_piles  # noqa: E402

SECTIONS = 10


def load_sqlite(sq: Path):
    db = sqlite3.connect(str(sq))
    strings = dict(db.execute("select id, value from StringIds"))
    scopes, begins, ends = [], {}, {}
    for text, tid_, s, e in db.execute("select text, textId, start, end from NVTX_EVENTS"):
        n = text if text else strings.get(tid_, "")
        if e and e > s and (n.startswith("schedule:") or n.startswith("gpu_model_runner:")):
            scopes.append({"type": n[:60], "start": s, "end": e, "d": e - s})
        elif n.startswith("agentix.call_begin::"):
            begins[n.split("::", 1)[1]] = s
        elif n.startswith("agentix.call_end::"):
            ends[n.split("::", 1)[1]] = s
    calls = []
    for k, s in begins.items():
        e = ends.get(k)
        if e and e > s:
            prog, idx, cls = k.split("::")
            calls.append({"type": cls, "start": s, "end": e, "d": e - s,
                          "label": f"{prog}#{idx}"})
    kernels = [(s, e, strings.get(n, "")) for s, e, n in db.execute(
        "select start, end, demangledName from CUPTI_ACTIVITY_KIND_KERNEL") if e > s]
    db.close()
    for lst in (scopes, calls):
        lst.sort(key=lambda m: (m["start"], m["end"]))
        for i, m in enumerate(lst):
            m["id"] = i
    kernels.sort()
    return scopes, calls, kernels


def union(iv):
    out = []
    for s, e in sorted(iv):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def sections_breaks(members, origin, extent):
    width = (extent - origin) // SECTIONS or 1
    secs = [{"section": i + 1, "begin_ns": str(origin + i * width),
             "end_ns": str(origin + (i + 1) * width if i < SECTIONS - 1 else extent),
             "width_ns": width} for i in range(SECTIONS)]
    # contract cap = 2x median duration; a display floor of width/2000 keeps the
    # break list to real idle holes — smaller gaps stay uncompressed (linear),
    # which distorts nothing and is declared on the page.
    cap = max(int(2 * statistics.median([m["d"] for m in members])) or 1,
              width // 2000)
    cov = union([(m["start"], m["end"]) for m in members])
    breaks = [[] for _ in range(SECTIONS)]
    for i, sc in enumerate(secs):
        lo, hi = int(sc["begin_ns"]), int(sc["end_ns"])
        seg = [(max(s, lo), min(e, hi)) for s, e in cov if e > lo and s < hi]
        prev = lo
        for s, e in seg + [(hi, hi)]:
            if s - prev > cap:
                breaks[i].append({"begin_ns": str(prev), "end_ns": str(s),
                                  "true_ns": s - prev, "display_ns": cap})
            prev = max(prev, e)
    return secs, breaks, cap


def pile_payload(members_by_type, origin, extent, min_share=None, total_ns=None):
    all_members = [m for ms in members_by_type.values() for m in ms]
    secs, breaks, cap = sections_breaks(all_members, origin, extent)
    width = int(secs[0]["width_ns"])
    groups, unsupported = [], []
    for t, ms in members_by_type.items():
        if min_share and sum(m["d"] for m in ms) * 100 <= min_share * total_ns:
            continue
        ps = lloyd_piles(ms)
        if ps is None:
            unsupported.append(t)
            continue
        for idx, seg in enumerate(ps):
            groups.append({"type": t, "pile_index": idx + 1, "members": seg,
                           "sum_ns": sum(m["d"] for m in seg)})
    groups.sort(key=lambda g: (-g["sum_ns"], g["type"], g["pile_index"]))
    piles = []
    for rank, g in enumerate(groups, 1):
        rows = [[] for _ in range(SECTIONS)]
        for m in g["members"]:
            si = min((m["start"] - origin) // width, SECTIONS - 1)
            rows[si].append([m["start"] - origin, m["d"]])
        piles.append({"rank": rank, "type": g["type"], "pile_index": g["pile_index"],
                      "count": len(g["members"]), "sum_ns": g["sum_ns"],
                      "min_ns": min(m["d"] for m in g["members"]),
                      "max_ns": max(m["d"] for m in g["members"]), "rows": rows})
    return {"origin": str(origin), "sections": secs, "breaks": breaks,
            "fold_cap_ns": cap, "piles": piles, "unsupported": unsupported}


def lane_rows(secs, origin, win_per_sec, value_fn):
    rows = [[] for _ in range(SECTIONS)]
    for i, sc in enumerate(secs):
        lo, hi = int(sc["begin_ns"]), int(sc["end_ns"])
        w = max((hi - lo) // win_per_sec, 1)
        t = lo
        while t < hi:
            e = min(t + w, hi)
            rows[i].append([t - origin, e - t, round(value_fn(t, e), 2)])
            t = e
    return rows


def busy_fn(kernels):
    starts = [k[0] for k in kernels]
    import bisect

    def f(lo, hi):
        i = bisect.bisect_left(starts, lo)
        # walk back for kernels straddling lo
        j = i
        while j > 0 and kernels[j - 1][1] > lo:
            j -= 1
        busy = 0
        for s, e, _ in kernels[j:]:
            if s >= hi:
                break
            busy += min(e, hi) - max(s, lo)
        return 100.0 * busy / (hi - lo)
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    sq = next(a.capture_dir.glob("*.sqlite"))
    scopes, calls, kernels = load_sqlite(sq)

    # e2e: request-level universe, all classes kept (representative view; the
    # >10 % rule is a selection device for the scope universe, declared adapted)
    by_cls = defaultdict(list)
    for c in calls:
        by_cls[c["type"]].append(c)
    o1, x1 = min(c["start"] for c in calls), max(c["end"] for c in calls)
    e2e = pile_payload(by_cls, o1, x1)

    # hl: scope universe with the contract 10 % selection
    by_type = defaultdict(list)
    for m in scopes:
        by_type[m["type"]].append(m)
    total = sum(m["d"] for m in scopes)
    o2, x2 = min(m["start"] for m in scopes), max(m["end"] for m in scopes)
    hl = pile_payload(by_type, o2, x2, min_share=10, total_ns=total)

    # cu: lanes over the hl extent; eligible = union of forward-pile member
    # windows containing a gemm-family kernel
    import bisect
    gemm = [(s, e) for s, e, n in kernels if "gemm" in n.lower()]
    gs = [g[0] for g in gemm]

    def has_gemm(m):
        i = bisect.bisect_left(gs, m["start"])
        return (i < len(gemm) and gemm[i][0] < m["end"]) or (i > 0 and gemm[i - 1][1] > m["start"])
    elig_members = [m for p in hl["piles"] if "forward" in p["type"]
                    for si in range(SECTIONS) for s0, d0 in p["rows"][si]
                    for m in [{"start": o2 + 0 + s0, "end": o2 + s0 + d0}] if has_gemm(m)]
    elig = union([(m["start"], m["end"]) for m in elig_members])
    secs = hl["sections"]
    open_calls = sorted([(c["start"], 1) for c in calls] + [(c["end"], -1) for c in calls])
    oc_t = [t for t, _ in open_calls]
    oc_cum = []
    d = 0
    for _, x in open_calls:
        d += x
        oc_cum.append(d)

    def conc_fn(lo, hi):
        i = bisect.bisect_right(oc_t, (lo + hi) // 2) - 1
        return float(oc_cum[i]) if i >= 0 else 0.0
    gemm_busy = busy_fn([(s, e, "") for s, e in gemm])
    cu = {
        "origin": hl["origin"], "sections": secs, "breaks": hl["breaks"],
        "fold_cap_ns": hl["fold_cap_ns"],
        "lanes": [
            {"label": "GPU busy", "unit": "%", "max": 100, "color": "#2f6f9f",
             "evidence": "CUPTI kernel 区间求并/窗口", "rows": lane_rows(secs, o2, 260, busy_fn(kernels))},
            {"label": "gemm 家族占比", "unit": "%", "max": 100, "color": "#a8802f",
             "evidence": "gemm kernel 时间/窗口", "rows": lane_rows(secs, o2, 260, gemm_busy)},
            {"label": "在飞调用数", "unit": "个", "max": max(oc_cum) if oc_cum else 1,
             "color": "#57a48a", "evidence": "客户端 call_begin/end 计数",
             "rows": lane_rows(secs, o2, 260, conc_fn)},
        ],
        "eligible_union": [[[max(s, int(sc["begin_ns"])) - o2, min(e, int(sc["end_ns"])) - max(s, int(sc["begin_ns"]))]
                            for s, e in elig if e > int(sc["begin_ns"]) and s < int(sc["end_ns"])]
                           for sc in secs],
        "piles": [{k: p[k] for k in ("rank", "type", "pile_index", "count", "sum_ns")}
                  for p in hl["piles"] if "forward" in p["type"]],
        "hidden_ranks": [p["rank"] for p in hl["piles"] if "forward" not in p["type"]],
    }
    a.out.write_text(json.dumps({"e2e": e2e, "hl": hl, "cu": cu}))
    print(json.dumps({"capture": str(a.capture_dir), "calls": len(calls),
                      "scope_members": sum(p["count"] for p in hl["piles"]),
                      "e2e_piles": len(e2e["piles"]), "hl_piles": len(hl["piles"]),
                      "elig_windows": len(elig), "bytes": a.out.stat().st_size}))


if __name__ == "__main__":
    main()
