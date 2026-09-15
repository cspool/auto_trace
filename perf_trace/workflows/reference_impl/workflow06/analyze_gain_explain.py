#!/usr/bin/env python3
"""Pair analysis: explain queueing-regime performance gain from call records + pile plans.

Inputs: two capture dirs (fcfs / agentix_core, cap16 r0.5, same stack) and their
contract-view GROUPS.json. Output: JSON facts consumed by the per-model gain report.
"""
import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def load_calls(d: Path):
    f = next((d / "run").glob("calls_*.jsonl"))
    return [json.loads(l) for l in f.open()]


def load_summary(d: Path):
    f = next((d / "run").glob("summary_*.json"))
    return json.load(f.open())


def per_class_wait(calls):
    out = {}
    by = defaultdict(list)
    for c in calls:
        # first_token - submitted = queue wait + prefill: the schedulable part
        by[c["class"]].append(c["first_token_rel_ms"] - c["submitted_rel_ms"])
    for k, v in by.items():
        v.sort()
        out[k] = {"n": len(v), "mean": sum(v) / len(v),
                  "p50": v[len(v) // 2], "p90": v[int(len(v) * 0.9)]}
    return out


def queue_depth_peak(calls, cap=16):
    ev = []
    for c in calls:
        ev.append((c["submitted_rel_ms"], 1))
        ev.append((c["finished_rel_ms"], -1))
    ev.sort()
    d = peak = 0
    over = 0.0
    prev = None
    for t, x in ev:
        if prev is not None and d > cap:
            over += t - prev
        d += x
        peak = max(peak, d)
        prev = t
    return {"peak_in_flight": peak, "ms_above_cap": over}


def mlfq_ledger(calls):
    adm = defaultdict(int)
    demo = promo = multi = 0
    for c in calls:
        qp = c.get("queue_path") or [c.get("priority", 0)]
        adm[qp[0]] += 1
        for a, b in zip(qp, qp[1:]):
            if b > a:
                demo += 1
            elif b < a:
                promo += 1
        if c.get("chunks", 1) > 1:
            multi += 1
    return {"admission": dict(sorted(adm.items())), "demotions": demo,
            "promotions": promo, "multi_quantum_calls": multi}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fcfs", type=Path, required=True)
    ap.add_argument("--core", type=Path, required=True)
    ap.add_argument("--fcfs-groups", type=Path, required=True)
    ap.add_argument("--core-groups", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    cf, cc = load_calls(a.fcfs), load_calls(a.core)
    sf, sc = load_summary(a.fcfs)["observed"], load_summary(a.core)["observed"]
    gf = json.load(a.fcfs_groups.open())
    gc = json.load(a.core_groups.open())
    def gtop(g):
        t = g["groups"][0]
        return {"sum_s": t["sum_ns"] / 1e9, "n": t["members"], "assoc": t["assoc_members"]}
    facts = {
        "endpoint": {
            "fcfs": {"ptl": sf["program_token_latency_ms"], "thr": sf["throughput_tokens_per_s"], "wall": sf["wall_s"]},
            "core": {"ptl": sc["program_token_latency_ms"], "thr": sc["throughput_tokens_per_s"], "wall": sc["wall_s"]},
            "speedup": {k: sf["program_token_latency_ms"][k] / sc["program_token_latency_ms"][k]
                        for k in ("mean", "p90", "p99")},
        },
        "class_wait_ms": {"fcfs": per_class_wait(cf), "core": per_class_wait(cc)},
        "queue": {"fcfs": queue_depth_peak(cf), "core": queue_depth_peak(cc)},
        "mlfq": mlfq_ledger(cc),
        "piles": {"fcfs": {"instances": gf["instances"], "fold_marks": gf["fold"]["marks"],
                            "top": gtop(gf)},
                  "core": {"instances": gc["instances"], "fold_marks": gc["fold"]["marks"],
                            "top": gtop(gc)}},
    }
    a.out.write_text(json.dumps(facts, indent=2))
    print(json.dumps(facts["endpoint"]["speedup"]))


if __name__ == "__main__":
    main()
