#!/usr/bin/env python3
"""W5 — representative process selection (workload_analysis half).

Reads a W4 capture and produces the representative process set that perf_trace
must cover, with an explicit conservation account per layer:

  host layer  — engine-iteration sub-processes, selected greedily until they
                cover >= COVER of the measured host time (step time minus the
                model-forward scope), so the set is representative by construction.
  device layer— the model-forward scope (already covered by the perf_trace chain).
  request layer— call windows plus the workload-shape processes (tool-delay gap,
                lats wave barrier) derivable from the client marks.
  mechanism layer— quantum chunks, demotions, promotions (agentix_core only).

Output: W5_REPRESENTATIVE_PROCESSES.json — the set, each member's share, the
uncovered remainder, and the perf_trace coverage delta (which members the
existing perf_trace process universe does NOT contain).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

COVER = 0.90
# process types the existing perf_trace universe already carries
PERF_TRACE_UNIVERSE_PREFIXES = ("schedule:", "gpu_model_runner:")


def _union(iv):
    """Total covered time of possibly overlapping/nested intervals."""
    out, cur = 0, None
    for s, e in sorted(iv):
        if cur and s <= cur[1]:
            cur[1] = max(cur[1], e)
        else:
            cur = [s, e]
            out += 0
            yield_cur = None
            out_list = None
    # second pass (simple and explicit)
    merged = []
    for s, e in sorted(iv):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return sum(e - s for s, e in merged)


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


def _merge(l):
    m = []
    for a, b in sorted(l):
        if m and a <= m[-1][1]:
            m[-1][1] = max(m[-1][1], b)
        else:
            m.append([a, b])
    return [tuple(x) for x in m]


def container_and_gap_account(sq: Path):
    """The two findings a leaf-cover cannot express: how much of each container's
    interior is still unnamed, and which boundary between named ranges owns the
    idle time."""
    import bisect
    db = sqlite3.connect(str(sq))
    s = dict(db.execute("select id, value from StringIds"))
    iv = defaultdict(list)
    for text, tid, st, en in db.execute("select text, textId, start, end from NVTX_EVENTS"):
        n = text if text else s.get(tid, "")
        if en and en > st and n.startswith(("gpu_model_runner:", "schedule:", "w.")):
            iv[n[:60]].append((st, en))
    kern = _merge([(a, b) for a, b in db.execute(
        "select start, end from CUPTI_ACTIVITY_KIND_KERNEL") if b > a])
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
        att = sum(b - a for a, b in _inter(C, kids))
        resid = _sub(C, kids)
        on_gpu = sum(b - a for a, b in _inter(resid, kern))
        tot = sum(b - a for a, b in C)
        containers[c] = {"total_ns": tot, "attributed_share": att / max(tot, 1),
                         "interior_unnamed_ns": tot - att,
                         "interior_gpu_running_ns": on_gpu,
                         "interior_host_idle_ns": (tot - att) - on_gpu}
    # dominant boundary gaps between named ranges
    # Idle gaps = complement of the named-range UNION inside the step union
    # (pairing consecutive ranges naively invents gaps across nested ranges).
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
        gaps[f"{left} -> {right}"] += h1 - h0
        gapn[f"{left} -> {right}"] += 1
    top = sorted(gaps.items(), key=lambda kv: -kv[1])[:6]
    return containers, [{"boundary": k, "sum_ns": v, "count": gapn[k],
                         "mean_ms": v / gapn[k] / 1e6} for k, v in top]


def load(sq: Path):
    """Ranges are aggregated by UNION of intervals: NVTX ranges nest (a step
    contains prepare_inputs contains attn_metadata) and the async engine can
    overlap them, so summing durations double-counts. Union is the only
    denominator that cannot exceed wall clock."""
    db = sqlite3.connect(str(sq))
    s = dict(db.execute("select id, value from StringIds"))
    iv = defaultdict(list)
    counts = defaultdict(int)
    marks = defaultdict(int)
    for text, tid, st, en in db.execute("select text, textId, start, end from NVTX_EVENTS"):
        n = text if text else s.get(tid, "")
        if not n:
            continue
        if en and en > st:
            k = n[:60]
            iv[k].append((st, en))
            counts[k] += 1
        else:
            marks[n.split("::", 1)[0]] += 1
    db.close()
    ranges = {k: [counts[k], _union(v)] for k, v in iv.items()}
    fwd_iv = [x for k, v in iv.items() if k.startswith("gpu_model_runner: forward") for x in v]
    step_iv = [x for k, v in iv.items() if k.startswith("w.engine: process_engine_step") for x in v]
    forward_ns = _union(fwd_iv)
    step_ns = _union(step_iv)
    # host = step time not covered by the device forward
    host_ns = _union(step_iv) - _union([x for x in fwd_iv])
    return ranges, marks, forward_ns, step_ns, max(host_ns, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture-dir", type=Path, required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    sq = next(a.capture_dir.glob("*.sqlite"))
    ranges, marks, forward_ns, step_ns, host_ns = load(sq)

    # Host universe = EVERY host-side process type, old and new, so the cover is
    # computed against the real denominator. Containers (whose children are also
    # probed) are excluded from the greedy pick to avoid double counting.
    host = {k: v for k, v in ranges.items()
            if not k.startswith("gpu_model_runner: forward")
            and not k.startswith("agentix.")}
    host_denom = host_ns

    CONTAINERS = {"w.engine: process_engine_step", "w.run: prepare_inputs",
                  "gpu_model_runner: preprocess", "w.sched: schedule_total"}
    leafs = {k: v for k, v in host.items() if k not in CONTAINERS}
    ordered = sorted(leafs.items(), key=lambda kv: -kv[1][1])
    chosen, acc = [], 0
    for k, (n, d) in ordered:
        chosen.append({"process": k, "count": n, "sum_ns": d,
                       "share_of_host": d / host_denom})
        acc += d
        if acc / host_denom >= COVER:
            break

    sel = {
        "model": a.model,
        "source_sqlite": str(sq),
        "layers": {
            "host": {
                "denominator_ns": host_denom,
                "denominator_note": "UNION(engine step intervals) - UNION(model-forward intervals); union, not sum, because NVTX ranges nest",
                "step_union_ns": step_ns, "forward_union_ns": forward_ns,
                "selected": chosen,
                "covered_share": acc / host_denom,
                "cover_target": COVER,
                "containers_excluded": sorted(CONTAINERS),
                "container_totals": {k: {"count": host[k][0], "sum_ns": host[k][1]}
                                     for k in CONTAINERS if k in host},
            },
            "device": {"process": "gpu_model_runner: forward", "sum_ns": forward_ns,
                       "note": "already covered by the perf_trace chain"},
            "request": {"call_begin_marks": marks.get("agentix.call_begin", 0),
                        "call_end_marks": marks.get("agentix.call_end", 0)},
            "mechanism": {"chunk_begin": marks.get("agentix.chunk_begin", 0),
                          "chunk_end": marks.get("agentix.chunk_end", 0),
                          "demote": marks.get("agentix.demote", 0),
                          "promote": marks.get("agentix.promote", 0)},
        },
    }
    containers, gaps = container_and_gap_account(sq)
    sel["container_account"] = containers
    sel["dominant_idle_boundaries"] = gaps

    # coverage delta vs the perf_trace universe
    missing = [c["process"] for c in chosen
               if not c["process"].startswith(PERF_TRACE_UNIVERSE_PREFIXES)]
    mech_missing = [k for k, v in sel["layers"]["mechanism"].items() if v > 0]
    sel["perf_trace_gap"] = {
        "host_processes_not_in_perf_trace": missing,
        "host_share_not_covered_by_perf_trace":
            sum(c["share_of_host"] for c in chosen
                if not c["process"].startswith(PERF_TRACE_UNIVERSE_PREFIXES)),
        "mechanism_events_not_in_perf_trace": mech_missing,
        "verdict": "RECAPTURE_REQUIRED" if missing or mech_missing else "COVERED",
    }
    a.out.write_text(json.dumps(sel, indent=2))
    print(json.dumps({"model": a.model, "host_cover": round(acc / host_denom, 3),
                      "n_selected": len(chosen),
                      "verdict": sel["perf_trace_gap"]["verdict"],
                      "gap_share": round(sel["perf_trace_gap"]["host_share_not_covered_by_perf_trace"], 3)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
