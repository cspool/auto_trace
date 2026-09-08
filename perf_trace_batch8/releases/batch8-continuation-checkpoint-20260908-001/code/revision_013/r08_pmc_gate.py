#!/usr/bin/env python3
"""Per-worker recoverable HIPProf gate for the measured R08 request batch.

Every profiled Python process disables collection before model warmup.  Each
GPU worker enables collection at its first measured R01 layer marker and a
watcher disables it after the eight-request batch completes.  The same PID and
monotonic markers remain an offline containment guard for exported rows.
"""

from __future__ import annotations

import atexit
import ctypes
import functools
import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any


EXPECTED_MANIFEST_SHA256 = "dc8b848a360d977d1c30adcace393459bce536aa2278ff997d6c71b9e94be280"

_lock = threading.RLock()
_r01: Any = None
_original_native_push: Any = None
_installed = False
_started = False
_stopped = False
_rank: int | None = None
_start_event: Path | None = None
_stop_event: Path | None = None
_process_pid: int | None = None
_watcher_pid: int | None = None
_initial_stop_pid: int | None = None
_initial_stop_monotonic_ns: int | None = None
_hip_runtime: Any = None

HIP_RUNTIME = Path("/opt/dtk/lib/libamdhip64.so")


def _required_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"R08 PMC gate environment missing: {name}")
    return Path(value)


def _write_json_x(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(encoded)


def _runtime() -> Any:
    global _hip_runtime
    if _hip_runtime is None:
        if not HIP_RUNTIME.is_file():
            raise RuntimeError(f"R08 HIP runtime missing: {HIP_RUNTIME}")
        runtime = ctypes.CDLL(
            str(HIP_RUNTIME),
            mode=getattr(os, "RTLD_NOW", 2) | getattr(os, "RTLD_GLOBAL", 0x100),
        )
        runtime.hipProfilerStart.argtypes = []
        runtime.hipProfilerStart.restype = ctypes.c_int
        runtime.hipProfilerStop.argtypes = []
        runtime.hipProfilerStop.restype = ctypes.c_int
        runtime.hipSetDevice.argtypes = [ctypes.c_int]
        runtime.hipSetDevice.restype = ctypes.c_int
        runtime.hipDeviceSynchronize.argtypes = []
        runtime.hipDeviceSynchronize.restype = ctypes.c_int
        runtime.hipGetErrorString.argtypes = [ctypes.c_int]
        runtime.hipGetErrorString.restype = ctypes.c_char_p
        _hip_runtime = runtime
    return _hip_runtime


def _hip_call(operation: str, *args: Any) -> dict[str, Any]:
    runtime = _runtime()
    started_ns = time.perf_counter_ns()
    status = int(getattr(runtime, operation)(*args))
    finished_ns = time.perf_counter_ns()
    if status != 0:
        raw = runtime.hipGetErrorString(status)
        message = raw.decode("utf-8", errors="replace") if raw else f"status={status}"
        raise RuntimeError(f"R08 {operation} failed: {message} ({status})")
    return {
        "operation": operation,
        "status": status,
        "pid": os.getpid(),
        "tid": threading.get_native_id(),
        "started_monotonic_ns": started_ns,
        "finished_monotonic_ns": finished_ns,
    }


def _logical_window_transition(operation: str) -> dict[str, Any]:
    now=time.perf_counter_ns()
    return {'operation':operation,'status':'logical_window_only','native_profiler_transition_performed':False,'pid':os.getpid(),'tid':threading.get_native_id(),'started_monotonic_ns':now,'finished_monotonic_ns':now}


def _event_payload(operation: str, rank: int | None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "complete",
        "operation": operation,
        "runtime_attempt_id": os.environ["QWEN_DCU_R08_RUNTIME_ATTEMPT_ID"],
        "segment_id": os.environ["QWEN_DCU_R08_SEGMENT_ID"],
        "pid": os.getpid(),
        "tid": threading.get_native_id(),
        "dp_rank": rank,
        "physical_device_id": rank,
        "monotonic_ns": time.perf_counter_ns(),
        "realtime_ns": time.time_ns(),
        "control_backend": "native_initially_on_explicit_measured_start_and_terminal_stop",
        "initial_profiler_stop_monotonic_ns": _initial_stop_monotonic_ns,
        "legacy_initial_stop_field_is_logical_guard_only": True,
        "native_collection_initially_on": True,
    }


def _stop_if_started(reason: str) -> None:
    global _stopped, _stop_event
    with _lock:
        if not _started or _stopped:
            return
        device_transition = None
        synchronize_transition = None
        if _rank is not None:
            device_transition = _hip_call("hipSetDevice", int(_rank))
            synchronize_transition = _hip_call("hipDeviceSynchronize")
        from r08_process_overlay import _write_summary
        _write_summary()
        profiler_transition = _hip_call("hipProfilerStop")
        _stopped = True
        event_root = _required_path("QWEN_DCU_R08_PMC_GATE_EVENT_ROOT")
        _stop_event = event_root / f"stop.rank{_rank}.pid{os.getpid()}.json"
        payload = _event_payload("stop", _rank)
        payload["reason"] = reason
        payload["device_transition"] = device_transition
        payload["synchronize_transition"] = synchronize_transition
        payload["profiler_transition"] = profiler_transition
        _write_json_x(_stop_event, payload)


def _watch_stop_file() -> None:
    stop_file = _required_path("QWEN_DCU_R08_PMC_GATE_STOP_FILE")
    while True:
        if stop_file.is_file():
            _stop_if_started("measured_batch_complete_control_file")
            return
        time.sleep(0.1)


def _ensure_watcher() -> None:
    global _watcher_pid
    current = os.getpid()
    with _lock:
        if _watcher_pid == current:
            return
        threading.Thread(
            target=_watch_stop_file,
            name="r08-pmc-stop-watcher",
            daemon=True,
        ).start()
        _watcher_pid = current


def _ensure_process_initialized() -> None:
    """Reset marker state and disable PMC after a multiprocessing fork."""
    global _process_pid, _started, _stopped, _rank, _start_event, _stop_event
    global _initial_stop_pid, _initial_stop_monotonic_ns, _watcher_pid
    current = os.getpid()
    with _lock:
        if _process_pid == current:
            return
        _process_pid = current
        _started = False
        _stopped = False
        _rank = None
        _start_event = None
        _stop_event = None
        _watcher_pid = None
        transition = _logical_window_transition("logical_window_stop")
        _initial_stop_pid = current
        _initial_stop_monotonic_ns = int(transition["finished_monotonic_ns"])


def _participant_ids() -> tuple[int | None, set[str]]:
    context = getattr(_r01, "_context", None)
    if not isinstance(context, dict):
        return None, set()
    rank = int(context["dp_rank"])
    identifiers = {
        str(row["request_id"])
        for row in context.get("participants", [])
        if isinstance(row, dict) and row.get("request_id") is not None
    }
    return rank, identifiers


def _patch_worker_device_initialization() -> None:
    """Reset marker state in a forked worker before its first layer kernel."""
    from vllm.platforms.rocm import RocmPlatform

    current = RocmPlatform.set_device
    if getattr(current, "_qwen_dcu_r08_pmc_gate", False):
        return

    @functools.wraps(current)
    def set_device(cls: Any, device: Any) -> Any:
        _ensure_process_initialized()
        return current(device)

    set_device._qwen_dcu_r08_pmc_gate = True
    RocmPlatform.set_device = classmethod(set_device)


def _native_push(name: str) -> Any:
    global _started, _rank, _start_event
    if name.startswith("qwen_dcu.layer"):
        _ensure_process_initialized()
        rank, participants = _participant_ids()
        measured = participants & _MEASURED_REQUEST_IDS
        if measured:
            with _lock:
                if not _started:
                    stop_file = _required_path("QWEN_DCU_R08_PMC_GATE_STOP_FILE")
                    if stop_file.exists():
                        raise RuntimeError("R08 PMC stop file appeared before measured start")
                    profiler_transition = _hip_call("hipProfilerStart")
                    _started = True
                    _rank = rank
                    event_root = _required_path("QWEN_DCU_R08_PMC_GATE_EVENT_ROOT")
                    _start_event = event_root / f"start.rank{rank}.pid{os.getpid()}.json"
                    payload = _event_payload("start", rank)
                    payload["first_broad_marker"] = name
                    payload["participant_request_ids"] = sorted(participants)
                    payload["measured_request_ids"] = sorted(measured)
                    payload["profiler_transition"] = profiler_transition
                    _write_json_x(_start_event, payload)
                    _ensure_watcher()
    return _original_native_push(name)


def _atexit() -> None:
    try:
        _stop_if_started("python_atexit_fallback")
    except BaseException:
        pass


def install(r01_module: Any) -> None:
    global _r01, _original_native_push, _installed, _MEASURED_REQUEST_IDS, _process_pid
    if _installed:
        return
    manifest_path = _required_path("QWEN_DCU_R01_REQUEST_MANIFEST")
    raw = manifest_path.read_bytes()
    observed = hashlib.sha256(raw).hexdigest()
    if observed != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError(f"R08 request manifest hash mismatch: {observed}")
    manifest = json.loads(raw)
    _MEASURED_REQUEST_IDS = {str(row["request_id"]) for row in manifest["records"]}
    if len(_MEASURED_REQUEST_IDS) != 8:
        raise RuntimeError("R08 measured request denominator is not eight")

    _r01 = r01_module
    _original_native_push = r01_module._native_push
    _process_pid = None
    _ensure_process_initialized()
    r01_module._native_push = _native_push
    _patch_worker_device_initialization()
    atexit.register(_atexit)
    _installed = True
    print(
        "R08_PMC_GATE_READY "
        f"attempt={os.environ['QWEN_DCU_R08_RUNTIME_ATTEMPT_ID']} "
        f"segment={os.environ['QWEN_DCU_R08_SEGMENT_ID']} "
        "measured_requests=8 collection_state=native_always_on "
        "canonical_window=offline_exact_marker_guard",
        flush=True,
    )
