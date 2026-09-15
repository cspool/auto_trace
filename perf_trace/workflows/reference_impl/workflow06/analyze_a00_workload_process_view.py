#!/usr/bin/env python3
"""A00 — workload-analysis half of the ablation chain (auto_trace workload_profile
contract applied to serving): decompose the frozen workload into the runtime
process-view hierarchy, then verify set conservation between the workload spec,
the client-side run records, and the trace, BEFORE any perf_trace step consumes
the capture.

Hierarchy (canonical keys):
  program  key = program_id                       (spec + run records + NVTX)
  call     key = (program_id, call_index)         (spec + run records + NVTX marks)
  step     key = (worker, step_seq)               (scope instances: one engine
                                                   iteration = one forward scope)
  scope    key = (step key, phase)                (schedule:*/gpu_model_runner:*)

Gates (all must PASS before A02/A03/A04 run):
  G-P   programs(spec) == programs(run) == programs(NVTX)
  G-C   calls(spec) == calls(run) == paired NVTX call_begin/end; key sets equal
  G-S   per-phase scope counts agree with the forward count (engine-loop
        conservation); mismatches listed per phase
  G-J   every call window overlaps >=1 forward step interval (call->step join;
        continuous batching makes this membership, not exclusive ownership)
"""
import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workload", type=Path, required=True)
    ap.add_argument("--capture-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    spec = json.loads(a.workload.read_text())
    spec_calls = {(p["program_id"], c["index"]) for p in spec["programs"] for c in p["llm_calls"]}
    spec_progs = {p["program_id"] for p in spec["programs"]}

    calls_f = next((a.capture_dir / "run").glob("calls_*.jsonl"))
    run_rows = [json.loads(l) for l in calls_f.open()]
    run_calls = {(r["program_id"], r["call_index"]) for r in run_rows}
    run_progs = {r["program_id"] for r in run_rows}

    sq = next(a.capture_dir.glob("*.sqlite"))
    db = sqlite3.connect(str(sq))
    strings = dict(db.execute("select id, value from StringIds"))
    begins, ends = {}, {}
    phases = defaultdict(int)
    fwd_iv = []
    for text, tid_, s, e in db.execute("select text, textId, start, end from NVTX_EVENTS"):
        n = text if text else strings.get(tid_, "")
        if n.startswith("agentix.call_begin::"):
            _, pid, idx, _cls = n.split("::")
            begins[(pid, int(idx))] = s
        elif n.startswith("agentix.call_end::"):
            _, pid, idx, _cls = n.split("::")
            ends[(pid, int(idx))] = s
        elif (n.startswith("schedule:") or n.startswith("gpu_model_runner:")) and e and e > s:
            phases[n[:60]] += 1
            if n.startswith("gpu_model_runner: forward"):
                fwd_iv.append((s, e))
    db.close()
    nvtx_calls = set(begins) & set(ends)
    nvtx_progs = {k[0] for k in nvtx_calls}

    fwd_iv.sort()
    fstarts = [s for s, _ in fwd_iv]
    import bisect

    def joins_step(k):
        s, e = begins[k], ends[k]
        i = bisect.bisect_left(fstarts, s)
        if i < len(fwd_iv) and fwd_iv[i][0] < e:
            return True
        return i > 0 and fwd_iv[i - 1][1] > s

    unjoined = [k for k in nvtx_calls if not joins_step(k)]

    n_fwd = phases.get("gpu_model_runner: forward", 0)
    phase_dev = {ph: c - n_fwd for ph, c in sorted(phases.items())
                 if ph.startswith("gpu_model_runner:") and c != n_fwd}

    gates = {
        "G-P_programs": {"spec": len(spec_progs), "run": len(run_progs), "nvtx": len(nvtx_progs),
                         "pass": spec_progs == run_progs == nvtx_progs},
        "G-C_calls": {"spec": len(spec_calls), "run": len(run_calls), "nvtx_paired": len(nvtx_calls),
                      "keyset_equal": spec_calls == run_calls == nvtx_calls,
                      "pass": spec_calls == run_calls == nvtx_calls},
        # one-sided small surplus of pre-forward phases = empty engine iterations
        # (scheduler ran, batch was empty: warm-up/drain); a DEFICIT or a large
        # surplus would mean lost scope instances and fails the gate.
        "G-S_engine_loop": {"forward_steps": n_fwd,
                            "per_phase_deviation_from_forward": phase_dev,
                            "explanation": ("positive = engine iterations without forward (empty batch); "
                                            "-1 = trailing iteration truncated by profiler stop"),
                            "pass": all(-1 <= d <= max(2, n_fwd // 200) for d in phase_dev.values())},
        "G-J_call_step_join": {"calls": len(nvtx_calls), "unjoined": len(unjoined),
                               "unjoined_keys": [list(k) for k in unjoined[:10]],
                               "pass": not unjoined},
    }
    out = {
        "step": "A00 workload process-view decomposition + conservation gates",
        "workload": {"path": str(a.workload), "sha256": spec["provenance"].get("sha256")
                     if isinstance(spec.get("provenance"), dict) else None,
                     "programs": len(spec_progs), "llm_calls": len(spec_calls)},
        "capture": str(a.capture_dir),
        "hierarchy": ["program(program_id)", "call(program_id,call_index)",
                      "step(forward scope instance)", "scope(step,phase)"],
        "scope_phase_counts": dict(sorted(phases.items())),
        "gates": gates,
        "all_pass": all(g["pass"] for g in gates.values()),
    }
    a.out.write_text(json.dumps(out, indent=2))
    print(json.dumps({"capture": a.capture_dir.name, "all_pass": out["all_pass"],
                      **{k: v["pass"] for k, v in gates.items()}}))


if __name__ == "__main__":
    main()
