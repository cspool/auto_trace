#!/usr/bin/env python3
"""W3 instrumentation — workload_analysis patch layer for the serving chain.

Wraps the host-path sub-processes that W1/W2 identify as hot inside the opaque
`schedule:*` / `gpu_model_runner: preprocess` scopes, plus the mechanism events
(quantum continuation, queue migration) that the ablation needs as first-class
processes. Import and call install() before the engine is constructed.

Every wrapper emits an NVTX range named `w.<group>: <name>` so the existing
process-universe loader picks them up with no schema change.
"""
from __future__ import annotations

import os

import torch.cuda.nvtx as nvtx

_INSTALLED = False


def _wrap(obj, attr, label):
    fn = getattr(obj, attr, None)
    if fn is None:
        return False
    if getattr(fn, "_w_wrapped", False):
        return True

    def inner(*a, **kw):
        nvtx.range_push(label)
        try:
            return fn(*a, **kw)
        finally:
            nvtx.range_pop()

    inner._w_wrapped = True
    setattr(obj, attr, inner)
    return True


def install(verbose: bool = True) -> dict:
    """Patch vLLM host-path targets. Returns {label: applied} for the audit."""
    global _INSTALLED
    if _INSTALLED:
        return {}
    applied = {}

    from vllm.v1.core.sched import scheduler as sched_mod
    from vllm.v1.worker import gpu_model_runner as gmr_mod
    from vllm.v1.engine import core as core_mod

    # --- scheduler host path (inside the opaque schedule:* region)
    S = sched_mod.Scheduler
    for attr, label in [
        ("schedule", "w.sched: schedule_total"),
        ("update_from_output", "w.sched: update_from_output"),
        ("add_request", "w.sched: add_request"),
        ("finish_requests", "w.sched: finish_requests"),
    ]:
        applied[label] = _wrap(S, attr, label)

    # --- KV cache manager. W2: allocate_slots/free duplicate the engine's own
    # `schedule: allocate_slots` scope, so only the uncovered lookup is probed.
    try:
        from vllm.v1.core import kv_cache_manager as kvm_mod
        applied["w.kv: get_computed_blocks"] = _wrap(
            kvm_mod.KVCacheManager, "get_computed_blocks", "w.kv: get_computed_blocks")
    except Exception as e:  # pragma: no cover - version drift
        applied["w.kv: <import failed>"] = f"{type(e).__name__}"

    # --- model runner host path (inside gpu_model_runner: preprocess)
    R = gmr_mod.GPUModelRunner
    for attr, label in [
        ("_update_states", "w.run: update_states"),
        ("_prepare_inputs", "w.run: prepare_inputs"),
        ("_update_states_after_model_execute", "w.run: update_states_after_exec"),
        ("_dummy_run", "w.run: dummy_run"),
        # W2: prepare_inputs owns 70 % of preprocess and is 80 % pure Python;
        # these break its interior into attributable sub-processes.
        ("_get_cumsum_and_arange", "w.prep: cumsum_arange"),
        ("_prepare_input_ids", "w.prep: input_ids"),
        ("_compute_prev_positions", "w.prep: prev_positions"),
        ("_build_attention_metadata", "w.prep: attn_metadata"),
        ("_calc_mrope_positions", "w.prep: mrope_positions"),
        ("_prepare_kv_sharing_fast_prefill", "w.prep: kv_sharing_prefill"),
    ]:
        applied[label] = _wrap(R, attr, label)

    # --- engine loop. W2: AsyncLLM never calls EngineCore.step, so the async
    # entry points are probed instead (the sync one is kept for other harnesses).
    try:
        applied["w.engine: step"] = _wrap(core_mod.EngineCore, "step", "w.engine: step")
    except Exception as e:  # pragma: no cover
        applied["w.engine: <import failed>"] = f"{type(e).__name__}"
    try:
        from vllm.v1.engine import async_llm as async_mod
        A = async_mod.AsyncLLM
        applied["w.engine: async_add_request"] = _wrap(A, "add_request", "w.engine: async_add_request")
    except Exception as e:  # pragma: no cover
        applied["w.engine: <async import failed>"] = f"{type(e).__name__}"
    # in-process (VLLM_ENABLE_V1_MULTIPROCESSING=0) engine loop: the busy-loop
    # body that owns one engine iteration end to end.
    try:
        applied["w.engine: process_engine_step"] = _wrap(
            core_mod.EngineCoreProc, "_process_engine_step", "w.engine: process_engine_step")
    except Exception as e:  # pragma: no cover
        applied["w.engine: <busyloop import failed>"] = f"{type(e).__name__}"
    try:
        from vllm.v1.engine import output_processor as op_mod
        applied["w.engine: process_outputs"] = _wrap(
            op_mod.OutputProcessor, "process_outputs", "w.engine: process_outputs")
    except Exception as e:  # pragma: no cover
        applied["w.engine: <outproc import failed>"] = f"{type(e).__name__}"

    _INSTALLED = True
    if verbose:
        ok = sum(1 for v in applied.values() if v is True)
        print(f"[w_instrument] installed {ok}/{len(applied)} host-path probes", flush=True)
    return applied


def enabled() -> bool:
    return os.environ.get("AGENTIX_W_INSTRUMENT", "0") == "1"
