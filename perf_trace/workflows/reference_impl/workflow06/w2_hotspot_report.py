#!/usr/bin/env python3
"""W2 — host-path hotspot analysis of a trial capture (workload_analysis).

Produces the patch-target evidence the next W3 iteration needs:
  * ranked host-path processes (union time, count, median)
  * CUDA-API vs pure-host split inside the top host process, on the engine thread
  * container interior attribution (how much of each container is still unnamed)
  * dominant idle boundaries between named ranges (where the engine actually waits)
"""
from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


def _merge(l):
    m = []
    for a, b in sorted(l):
        if m and a <= m[-1][1]:
            m[-1][1] = max(m[-1][1], b)
        else:
            m.append([a, b])
    return [tuple(x) for x in m]


def _inter(A, B):
    out, j = [], 0
    for a, b in A:
        while j < len(B) and B[j][1] <= a:
            j += 1
        k = j
        while k < len(B) and B[k][0] < b:
            lo, hi = max(a, B[k][0]), min(b, B[k][1])
            if hi > lo:
                out.append((lo, hi))
            k += 1
    return out


def _sub(A, B):
    out, j = [], 0
    for a, b in A:
        cur = a
        while j < len(B) and B[j][1] <= a:
            j += 1
        k = j
        while k < len(B) and B[k][0] < b:
            if B[k][0] > cur:
                out.append((cur, min(B[k][0], b)))
            cur = max(cur, B[k][1])
            k += 1
        if cur < b:
            out.append((cur, b))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture-dir", type=Path, required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    sq = next(a.capture_dir.glob("*.sqlite"))
    db = sqlite3.connect(str(sq))
    s = dict(db.execute("select id, value from StringIds"))
    iv, cnt, tids = defaultdict(list), defaultdict(int), {}
    for text, tid, st, en, gt in db.execute(
            "select text, textId, start, end, globalTid from NVTX_EVENTS"):
        n = text if text else s.get(tid, "")
        if en and en > st and n.startswith(("gpu_model_runner:", "schedule:", "w.")):
            k = n[:60]
            iv[k].append((st, en))
            cnt[k] += 1
            tids.setdefault(k, gt)
    kern = _merge([(x, y) for x, y in db.execute(
        "select start, end from CUPTI_ACTIVITY_KIND_KERNEL") if y > x])

    ranked = sorted(((k, cnt[k], sum(b - a for a, b in _merge(v))) for k, v in iv.items()),
                    key=lambda r: -r[2])

    # CUDA-API vs pure host inside the top *leaf-ish* host process
    target = "w.run: prepare_inputs"
    api = defaultdict(lambda: [0, 0])
    if target in iv:
        wins = sorted(iv[target])
        wstart = [w[0] for w in wins]
        t0 = tids[target]
        for st, en, nid, gt in db.execute(
                "select start, end, nameId, globalTid from CUPTI_ACTIVITY_KIND_RUNTIME"):
            if gt != t0 or not en or en <= st:
                continue
            i = bisect.bisect_right(wstart, st) - 1
            if i >= 0 and wins[i][1] > st:
                e = api[s.get(nid, "?")[:44]]
                e[0] += min(en, wins[i][1]) - st
                e[1] += 1
    db.close()

    CONT = {
        "w.engine: process_engine_step": ("gpu_model_runner:", "schedule:", "w.sched:", "w.run:", "w.kv:", "w.prep:", "w.engine: process_outputs"),
        "gpu_model_runner: preprocess": ("w.run:", "w.prep:", "schedule:"),
        "w.run: prepare_inputs": ("w.prep:",),
        "w.sched: schedule_total": ("schedule:", "w.kv:"),
    }
    containers = {}
    for c, pref in CONT.items():
        if c not in iv:
            continue
        C = _merge(iv[c])
        kids = _merge([x for k, v in iv.items() if k != c and k.startswith(pref) for x in v])
        tot = sum(b - a for a, b in C)
        att = sum(b - a for a, b in _inter(C, kids))
        resid = _sub(C, kids)
        gpu = sum(b - a for a, b in _inter(resid, kern))
        containers[c] = {"total_ns": tot, "attributed_share": att / max(tot, 1),
                         "interior_unnamed_ns": tot - att,
                         "interior_gpu_running_ns": gpu,
                         "interior_host_idle_ns": (tot - att) - gpu}

    # Idle gaps = complement of the named-range UNION inside the step union.
    # (Naively pairing consecutive ranges invents gaps across nested long ranges.)
    step_u = _merge(iv.get("w.engine: process_engine_step", []))
    named_u = _merge([x for k, v in iv.items()
                      if k != "w.engine: process_engine_step" for x in v])
    holes = _sub(step_u, named_u)
    ev = sorted((st, en, k) for k, v in iv.items()
                if k != "w.engine: process_engine_step" for st, en in v)
    ends = sorted((en, k) for st, en, k in ev)
    end_ts = [e[0] for e in ends]
    starts = [e[0] for e in ev]
    gaps, gapn = defaultdict(int), defaultdict(int)
    for h0, h1 in holes:
        if h1 - h0 <= 50_000:
            continue
        i = bisect.bisect_right(end_ts, h0) - 1
        left = ends[i][1] if i >= 0 else "<start>"
        j = bisect.bisect_left(starts, h1)
        right = ev[j][2] if j < len(ev) else "<end>"
        key = f"{left} -> {right}"
        gaps[key] += h1 - h0
        gapn[key] += 1
    top_gaps = [{"boundary": k, "sum_ns": v, "count": gapn[k], "mean_ms": v / gapn[k] / 1e6}
                for k, v in sorted(gaps.items(), key=lambda kv: -kv[1])[:6]]

    rep = {
        "model": a.model, "source_sqlite": str(sq),
        "ranked_processes": [{"process": k, "count": n, "union_ns": d,
                              "mean_us": d / max(n, 1) / 1e3} for k, n, d in ranked[:18]],
        "prepare_inputs_api_split": {
            "window_union_ns": sum(b - a for a, b in _merge(iv.get(target, []))),
            "cuda_api_ns": sum(v[0] for v in api.values()),
            "top_apis": [{"api": k, "ns": v[0], "count": v[1]}
                         for k, v in sorted(api.items(), key=lambda kv: -kv[1][0])[:6]],
        },
        "container_account": containers,
        "dominant_idle_boundaries": top_gaps,
    }
    a.out.write_text(json.dumps(rep, indent=2))
    pi = rep["prepare_inputs_api_split"]
    print(json.dumps({"model": a.model, "top3": [r[0] for r in ranked[:3]],
                      "prepare_inputs_s": round(pi["window_union_ns"] / 1e9, 1),
                      "prepare_inputs_cuda_share": round(pi["cuda_api_ns"] / max(pi["window_union_ns"], 1), 3),
                      "top_gap": top_gaps[0]["boundary"] if top_gaps else None,
                      "top_gap_s": round(top_gaps[0]["sum_ns"] / 1e9, 1) if top_gaps else 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
