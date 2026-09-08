"""Scope each native PMC input to its DP worker's physical device.

Only the native input's gpu selector changes. HIP visibility, DP topology,
workload, selected kernels, counter list and native trace IPC remain intact.
"""
from pathlib import Path
import functools
import hashlib
import inspect
import json
import os
import threading
import time

_lock = threading.RLock()
_installed = False
EXPECTED_EXECUTOR_SHA256 = "REPLACE_AT_FREEZE"


def _record(path):
    path = Path(path)
    data = path.read_bytes()
    return {"path": str(path), "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def _write_x(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _scoped_input(data, rank):
    if rank not in (0, 1):
        raise RuntimeError("native PMC scope requires physical device zero or one")
    lines = data.decode("utf-8").splitlines(keepends=True)
    selected = [i for i, line in enumerate(lines) if line.startswith("gpu:")]
    if len(selected) != 1:
        raise RuntimeError("native input must contain exactly one gpu selector")
    index = selected[0]
    if lines[index].split(":", 1)[1].strip():
        raise RuntimeError("parent native input already restricts devices")
    if sum(line.startswith("pmc:") for line in lines) != 1:
        raise RuntimeError("native input must contain exactly one PMC counter list")
    if sum(line.startswith("kernel:") for line in lines) != 1:
        raise RuntimeError("native input must contain exactly one kernel selector")
    old = lines[index]
    newline = "\r\n" if old.endswith("\r\n") else "\n" if old.endswith("\n") else ""
    lines[index] = "gpu: " + str(rank) + newline
    return "".join(lines).encode("utf-8")


def _physical_rank(config, local_rank, rank):
    p = config.parallel_config
    dp = int(p.data_parallel_index)
    local_dp = p.data_parallel_rank_local
    if local_dp is None:
        local_dp = dp
    if (dp not in (0, 1) or int(local_dp) != dp or local_rank != 0 or rank != 0
            or p.tensor_parallel_size != 1 or p.pipeline_parallel_size != 1
            or p.data_parallel_size != 1 or p.nnodes_within_dp != 1):
        raise RuntimeError("unexpected DP2/TP1 native worker topology")
    return dp


def _wrap_make_worker_process(original):
    signature = inspect.signature(original)

    @functools.wraps(original)
    def scoped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        dp = _physical_rank(bound.arguments["vllm_config"],
                            bound.arguments["local_rank"], bound.arguments["rank"])
        with _lock:
            for key in ("HIP_VISIBLE_DEVICES", "CUDA_VISIBLE_DEVICES"):
                if os.environ.get(key) != "0,1":
                    raise RuntimeError("original two-device visibility must remain unchanged")
            source = Path(os.environ["HIPPROF_INPUT_FILE"])
            data = source.read_bytes()
            scoped_data = _scoped_input(data, dp)
            root = Path(os.environ["QWEN_DCU_R08_PASS_ROOT"])
            directory = root / "control/native_worker_gpu_inputs"
            directory.mkdir(parents=True, exist_ok=True)
            destination = directory / f"rank{dp}.parent{os.getpid()}.txt"
            with destination.open("xb") as handle:
                handle.write(scoped_data)
                handle.flush()
                os.fsync(handle.fileno())
            binding = {"status": "prepared", "parent_pid": os.getpid(),
                       "physical_device_id": dp, "dp_rank": dp,
                       "original_native_input": _record(source),
                       "worker_native_input": _record(destination),
                       "only_native_gpu_selector_changed": True,
                       "HIP_and_CUDA_visibility": "0,1",
                       "native_trace_IPC_unchanged": True,
                       "added_model_executions": 0,
                       "prepared_realtime_ns": time.time_ns()}
            _write_x(directory / f"rank{dp}.parent{os.getpid()}.prepared.json", binding)
            previous = os.environ["HIPPROF_INPUT_FILE"]
            os.environ["HIPPROF_INPUT_FILE"] = str(destination)
            try:
                result = original(*args, **kwargs)
            finally:
                os.environ["HIPPROF_INPUT_FILE"] = previous
            _write_x(directory / f"rank{dp}.parent{os.getpid()}.spawned.json",
                     {**binding, "status": "worker_spawned",
                      "worker_pid": result.proc.pid,
                      "parent_input_environment_restored": os.environ["HIPPROF_INPUT_FILE"] == previous,
                      "spawned_realtime_ns": time.time_ns()})
            return result
    scoped._qwen_r08_native_worker_gpu_scope = True
    return scoped


def install():
    global _installed
    if _installed:
        return
    from vllm.v1.executor import multiproc_executor
    if _record(multiproc_executor.__file__)["sha256"] != EXPECTED_EXECUTOR_SHA256:
        raise RuntimeError("pinned worker process launcher source changed")
    cls = multiproc_executor.WorkerProc
    original = cls.make_worker_process
    if not getattr(original, "_qwen_r08_native_worker_gpu_scope", False):
        cls.make_worker_process = staticmethod(_wrap_make_worker_process(original))
    _installed = True
