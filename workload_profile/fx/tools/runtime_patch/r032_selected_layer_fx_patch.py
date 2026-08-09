"""R032 Qwen3.5 selected-layer runtime sampling and post-request FX replay.

Evidence is deliberately split into two stages:

* During the real vLLM V1 eager request, selected decoder-layer inputs,
  selected forward-context metadata, and the active external cache/state
  slices are cloned at layer entry. The response always comes from the
  original eager layer forward.
* A controller creates the finalize marker only after the HTTP request has
  returned. The worker waits for no active model execution, restores every
  wrapper installed by this module, and only then replays the fixed samples
  through ``make_fx``.

ROCm attention and GDN core custom operations remain opaque FX nodes. Their
entry-state snapshots document the external mutation boundary; they are not
substituted for invented Python implementations.
"""

from __future__ import annotations

import atexit
import copy
import csv
import dataclasses
import functools
import hashlib
import importlib.metadata
import inspect
import json
import os
import sys
import threading
import time
import traceback
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import torch
from torch.fx.experimental.proxy_tensor import make_fx

# This is the runtime-confirmed Qwen/vLLM tracer utility implementation from
# the archived current-runtime evidence. Its patch entry point is never called;
# only its proven make_fx serialization and reversible specialization helpers
# are reused.
import vllm_selected_layer_fx_patch as _base


_PATCHED = False
_FINALIZED = False
_FINALIZE_STARTED = False
_LOCK = threading.RLock()
_FINALIZE_LOCK = threading.Lock()
_STATE = threading.local()
_RESTORES: list["RestoreRecord"] = []
_LAYER_ROWS: list[dict[str, Any]] = []
_MANIFEST_ROWS: list[dict[str, Any]] = []
_SAMPLES: dict[str, "FxSample"] = {}
_OCCURRENCES: Counter[tuple[int, int]] = Counter()
_REQUEST_COMPUTED: dict[str, int] = {}
_FORWARD_ROWS: list[dict[str, Any]] = []
_PATCH_ERRORS: list[dict[str, Any]] = []
_CAPTURE_ERRORS: list[dict[str, Any]] = []
_RESTORE_ERRORS: list[dict[str, Any]] = []
_ACTIVE_EXECUTES = 0
_SOURCE_ROWS_CACHE: list[dict[str, str]] | None = None
_SOURCE_BY_EVENT_CACHE: dict[str, dict[str, str]] | None = None
_CAPTURE_FIRST_NS: int | None = None
_CAPTURE_LAST_NS: int | None = None
_FINALIZE_MARKER_OBSERVED_NS: int | None = None
_WRAPPERS_RESTORED_NS: int | None = None
_OFFLINE_FIRST_START_NS: int | None = None
_OFFLINE_LAST_END_NS: int | None = None


LAYER_EVENT_FIELDS = [
    "event_id",
    "selection_id",
    "source_event_id",
    "source_run_id",
    "run_id",
    "contract_id",
    "source_revision",
    "rank",
    "worker_id",
    "device_id",
    "request_id",
    "engine_step_id",
    "forward_id",
    "layer_id",
    "layer_occurrence",
    "phase",
    "total_num_scheduled_tokens",
    "q_len",
    "past_len",
    "kv_len",
    "layer_type",
    "source_contract_match",
    "source_mapping_error",
    "hidden_shape_in",
    "residual_shape_in",
    "positions_shape",
    "hidden_shape_out",
    "residual_shape_out",
    "matched",
    "fx_sampled",
    "fx_traced",
    "fx_trace_status",
    "fx_node_count",
    "trace_dir",
    "capture_begin_ns",
    "capture_end_ns",
    "eager_begin_ns",
    "eager_end_ns",
    "error",
]

TRACE_MANIFEST_FIELDS = [
    "event_id",
    "selection_id",
    "source_event_id",
    "source_run_id",
    "run_id",
    "contract_id",
    "source_revision",
    "rank",
    "worker_id",
    "device_id",
    "request_id",
    "engine_step_id",
    "forward_id",
    "layer_id",
    "layer_occurrence",
    "phase",
    "q_len",
    "past_len",
    "kv_len",
    "layer_type",
    "source_contract_match",
    "status",
    "node_count",
    "trace_dir",
    "specialization",
    "input_binding",
    "opaque_custom_ops",
    "save_errors",
    "error",
    "offline_trace_start_ns",
    "offline_trace_end_ns",
    "duration_ns",
]


@dataclass
class RestoreRecord:
    cls: Any
    name: str
    original: Any
    wrapped: Any


@dataclass
class FxSample:
    event_id: str
    layer: Any
    original_forward: Any
    call_args: tuple[Any, ...]
    call_kwargs: dict[str, Any]
    replay_context: Any
    context_summary: dict[str, Any]
    state_summary: dict[str, Any]
    retained_state_tensors: list[torch.Tensor]
    layer_row: dict[str, Any]
    capture_begin_ns: int
    capture_end_ns: int


def _enabled() -> bool:
    return os.environ.get("VLLM_R032_FX_ENABLE") == "1"


def _trace_dir() -> Path:
    value = os.environ.get("VLLM_SELECTED_LAYER_FX_DIR")
    if not value:
        raise RuntimeError("VLLM_SELECTED_LAYER_FX_DIR is required")
    return Path(value).expanduser().resolve()


def _selected_manifest_path() -> Path:
    value = os.environ.get("VLLM_SELECTED_LAYER_FX_CANONICAL_MANIFEST")
    if not value:
        raise RuntimeError("VLLM_SELECTED_LAYER_FX_CANONICAL_MANIFEST is required")
    return Path(value).expanduser().resolve()


def _selection_handoff_path() -> Path:
    value = os.environ.get("VLLM_SELECTED_LAYER_FX_SELECTION_HANDOFF")
    if not value:
        raise RuntimeError("VLLM_SELECTED_LAYER_FX_SELECTION_HANDOFF is required")
    return Path(value).expanduser().resolve()


def _source_trace_path() -> Path:
    value = os.environ.get("VLLM_SELECTED_LAYER_FX_SOURCE_TRACE")
    if not value:
        raise RuntimeError("VLLM_SELECTED_LAYER_FX_SOURCE_TRACE is required")
    return Path(value).expanduser().resolve()


def _arm_file() -> Path:
    value = os.environ.get("VLLM_SELECTED_LAYER_FX_ARM_FILE")
    if not value:
        raise RuntimeError("VLLM_SELECTED_LAYER_FX_ARM_FILE is required")
    return Path(value).expanduser().resolve()


def _finalize_file() -> Path:
    value = os.environ.get("VLLM_R032_FX_FINALIZE_FILE")
    if not value:
        raise RuntimeError("VLLM_R032_FX_FINALIZE_FILE is required")
    return Path(value).expanduser().resolve()


def _done_file() -> Path:
    value = os.environ.get("VLLM_R032_FX_DONE_FILE")
    if not value:
        raise RuntimeError("VLLM_R032_FX_DONE_FILE is required")
    return Path(value).expanduser().resolve()


def _run_id() -> str:
    return os.environ.get("VLLM_TRACE_RUN_ID", "")


def _contract_id() -> str:
    return os.environ.get("VLLM_TRACE_CONTRACT_ID", "")


def _source_revision() -> str:
    return os.environ.get("VLLM_R032_SOURCE_REVISION", "")


def _device_id() -> str:
    return os.environ.get("VLLM_R032_DEVICE_ID", "")


def _is_armed() -> bool:
    return _arm_file().is_file()


def _now_ns() -> int:
    return time.monotonic_ns()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _shape(value: Any) -> list[int] | None:
    if not torch.is_tensor(value):
        return None
    return [int(item) for item in value.shape]


def _shape_json(value: Any) -> str:
    return json.dumps(_shape(value), separators=(",", ":"))


def _rank() -> int:
    try:
        if torch.distributed.is_available() and torch.distributed.is_initialized():
            return int(torch.distributed.get_rank())
    except Exception:
        pass
    return int(os.environ.get("RANK", os.environ.get("LOCAL_RANK", "0")) or "0")


def _worker_id() -> str:
    return f"rank{_rank()}"


def _event_id(forward_id: int, layer_id: int) -> str:
    return f"input{forward_id}_layer{layer_id}"


def _source_rows() -> list[dict[str, str]]:
    global _SOURCE_ROWS_CACHE, _SOURCE_BY_EVENT_CACHE
    if _SOURCE_ROWS_CACHE is not None:
        return _SOURCE_ROWS_CACHE
    rows: list[dict[str, str]] = []
    with _selected_manifest_path().open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            normalized = dict(row)
            normalized["event_id"] = _event_id(
                int(normalized["forward_id"]),
                int(normalized["layer_idx"]),
            )
            rows.append(normalized)
    if not rows:
        raise RuntimeError("canonical selected manifest is empty")
    if len({row["event_id"] for row in rows}) != len(rows):
        raise RuntimeError("canonical selected event ids are not unique")
    _SOURCE_ROWS_CACHE = rows
    _SOURCE_BY_EVENT_CACHE = {row["event_id"]: row for row in rows}
    return rows


def _source_by_event() -> dict[str, dict[str, str]]:
    if _SOURCE_BY_EVENT_CACHE is None:
        _source_rows()
    assert _SOURCE_BY_EVENT_CACHE is not None
    return _SOURCE_BY_EVENT_CACHE


def _target_order() -> list[str]:
    return [row["event_id"] for row in _source_rows()]


def _write_event(event_type: str, **payload: Any) -> None:
    try:
        root = _trace_dir()
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"events.{os.getpid()}.jsonl"
        event = {
            "event_type": event_type,
            "ts_monotonic_ns": _now_ns(),
            "pid": os.getpid(),
            "rank": _rank(),
            "worker_id": _worker_id(),
            "run_id": _run_id(),
            "contract_id": _contract_id(),
            **payload,
        }
        with _LOCK, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_base._jsonable(event), ensure_ascii=False, sort_keys=True) + "\n")
    except BaseException as exc:
        try:
            sys.stderr.write(f"[r032-selected-layer-fx] event write failed: {exc!r}\n")
        except Exception:
            pass


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(
        json.dumps(_base._jsonable(dict(payload)), indent=2, ensure_ascii=False, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _write_csv_atomic(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    tmp.replace(path)


def _clone_replay_value(value: Any, memo: dict[int, Any] | None = None) -> Any:
    if memo is None:
        memo = {}
    if torch.is_tensor(value):
        return value.detach().clone(memory_format=torch.preserve_format)
    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return value
    value_id = id(value)
    if value_id in memo:
        return memo[value_id]
    if isinstance(value, Mapping):
        cloned: dict[Any, Any] = {}
        memo[value_id] = cloned
        cloned.update(
            {
                key: _clone_replay_value(item, memo)
                for key, item in value.items()
            }
        )
        return cloned
    if isinstance(value, tuple):
        result = tuple(_clone_replay_value(item, memo) for item in value)
        memo[value_id] = result
        return result
    if isinstance(value, list):
        result_list: list[Any] = []
        memo[value_id] = result_list
        result_list.extend(_clone_replay_value(item, memo) for item in value)
        return result_list
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        result = copy.copy(value)
        memo[value_id] = result
        for item in dataclasses.fields(value):
            try:
                object.__setattr__(
                    result,
                    item.name,
                    _clone_replay_value(getattr(value, item.name), memo),
                )
            except Exception:
                setattr(result, item.name, _clone_replay_value(getattr(value, item.name), memo))
        return result
    return value


def _named_tensors(
    value: Any,
    prefix: str = "",
    *,
    depth: int = 0,
    seen: set[int] | None = None,
) -> list[tuple[str, torch.Tensor]]:
    if seen is None:
        seen = set()
    if torch.is_tensor(value):
        return [(prefix or "tensor", value)]
    if value is None or depth > 6 or isinstance(value, (str, int, float, bool, bytes)):
        return []
    value_id = id(value)
    if value_id in seen:
        return []
    seen.add(value_id)
    found: list[tuple[str, torch.Tensor]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            found.extend(
                _named_tensors(
                    item,
                    f"{prefix}.{key}" if prefix else str(key),
                    depth=depth + 1,
                    seen=seen,
                )
            )
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        for item in dataclasses.fields(value):
            found.extend(
                _named_tensors(
                    getattr(value, item.name),
                    f"{prefix}.{item.name}" if prefix else item.name,
                    depth=depth + 1,
                    seen=seen,
                )
            )
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            found.extend(
                _named_tensors(
                    item,
                    f"{prefix}[{index}]",
                    depth=depth + 1,
                    seen=seen,
                )
            )
    return found


def _tensor_sha256(tensor: torch.Tensor) -> str:
    cpu = tensor.detach().contiguous().cpu()
    raw = cpu.view(torch.uint8).numpy().tobytes()
    return hashlib.sha256(raw).hexdigest()


def _metadata_entries_for_layer(
    layer: Any,
    forward_context: Any,
) -> tuple[list[str], Any, Any]:
    candidates = []
    if hasattr(layer, "linear_attn"):
        candidates.append(getattr(layer, "linear_attn"))
    if hasattr(layer, "self_attn") and hasattr(layer.self_attn, "attn"):
        candidates.append(layer.self_attn.attn)

    keys: list[str] = []
    no_compile = getattr(forward_context, "no_compile_layers", {}) or {}
    if isinstance(no_compile, Mapping):
        for key, value in no_compile.items():
            if any(value is candidate for candidate in candidates):
                keys.append(str(key))

    layer_idx = _safe_int(getattr(layer, "layer_idx", None))
    if not keys and layer_idx is not None:
        marker = f".layers.{layer_idx}."
        attn_metadata = getattr(forward_context, "attn_metadata", {})
        if isinstance(attn_metadata, Mapping):
            keys = [str(key) for key in attn_metadata if marker in str(key)]

    def select(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                key: _clone_replay_value(item)
                for key, item in value.items()
                if str(key) in keys
            }
        if isinstance(value, list):
            return [select(item) for item in value]
        return _clone_replay_value(value)

    metadata = select(getattr(forward_context, "attn_metadata", None))
    slot_mapping = select(getattr(forward_context, "slot_mapping", None))
    return keys, metadata, slot_mapping


def _capture_forward_context(layer: Any) -> tuple[Any, dict[str, Any], Any]:
    from vllm.forward_context import get_forward_context

    context = get_forward_context()
    keys, metadata, slot_mapping = _metadata_entries_for_layer(layer, context)
    replay_context = copy.copy(context)
    replay_context.attn_metadata = metadata
    replay_context.slot_mapping = slot_mapping
    replay_context.dp_metadata = _clone_replay_value(getattr(context, "dp_metadata", None))
    replay_context.additional_kwargs = _clone_replay_value(
        getattr(context, "additional_kwargs", {})
    )
    replay_context.all_moe_layers = (
        list(context.all_moe_layers)
        if getattr(context, "all_moe_layers", None) is not None
        else None
    )
    replay_context.moe_layer_index = int(getattr(context, "moe_layer_index", 0))

    summary = {
        "class": f"{context.__class__.__module__}.{context.__class__.__qualname__}",
        "selected_context_keys": keys,
        "virtual_engine": int(getattr(context, "virtual_engine", 0)),
        "cudagraph_runtime_mode": str(getattr(context, "cudagraph_runtime_mode", "")),
        "skip_compiled": bool(getattr(context, "skip_compiled", False)),
        "attn_metadata": _base._describe_value(metadata),
        "slot_mapping": _base._describe_value(slot_mapping),
        "metadata_tensor_count": len(_named_tensors(metadata)),
        "slot_mapping_tensor_count": len(_named_tensors(slot_mapping)),
        "clone_stage": "selected_decoder_layer_entry_before_original_forward",
    }
    return replay_context, summary, metadata


def _integer_ids(
    metadata: Any,
    path_needles: tuple[str, ...],
) -> list[int]:
    ids: set[int] = set()
    for name, tensor in _named_tensors(metadata):
        lowered = name.lower()
        if not any(needle in lowered for needle in path_needles):
            continue
        if tensor.numel() == 0:
            continue
        values = tensor.detach().reshape(-1).to(device="cpu", dtype=torch.int64).tolist()
        ids.update(int(value) for value in values if int(value) >= 0)
    return sorted(ids)


def _capture_external_state(
    layer: Any,
    replay_context: Any,
    selected_metadata: Any,
) -> tuple[dict[str, Any], list[torch.Tensor]]:
    retained: list[torch.Tensor] = []
    virtual_engine = int(getattr(replay_context, "virtual_engine", 0))

    if getattr(layer, "layer_type", None) == "linear_attention":
        module = layer.linear_attn
        state_ids = _integer_ids(
            selected_metadata,
            ("state_indices", "block_table"),
        )
        cache = getattr(module, "kv_cache", None)
        tensors = []
        if isinstance(cache, Sequence) and len(cache) > virtual_engine:
            selected_cache = cache[virtual_engine]
            if torch.is_tensor(selected_cache):
                tensors = [selected_cache]
            elif isinstance(selected_cache, Sequence):
                tensors = [item for item in selected_cache if torch.is_tensor(item)]
        entries = []
        for index, tensor in enumerate(tensors):
            valid = [item for item in state_ids if item < int(tensor.shape[0])]
            if not valid:
                continue
            index_tensor = torch.tensor(valid, dtype=torch.long, device=tensor.device)
            snapshot = tensor.detach().index_select(0, index_tensor).to("cpu").clone()
            retained.append(snapshot)
            entries.append(
                {
                    "cache_tensor_index": index,
                    "source_shape": _shape(tensor),
                    "source_dtype": str(tensor.dtype),
                    "source_device": str(tensor.device),
                    "state_indices": valid,
                    "snapshot_shape": _shape(snapshot),
                    "snapshot_sha256": _tensor_sha256(snapshot),
                }
            )
        return (
            {
                "family": "linear_attention",
                "boundary": "torch.ops.vllm.gdn_attention_core remains opaque",
                "representation": "Qwen3_5GatedDeltaNet.kv_cache[virtual_engine]",
                "virtual_engine": virtual_engine,
                "active_state_indices": state_ids,
                "snapshot_tensors": entries,
                "snapshot_tensor_count": len(entries),
                "replay_use": "entry state retained as external mutation-boundary evidence; opaque fake implementation does not consume it",
            },
            retained,
        )

    module = layer.self_attn.attn
    block_ids = _integer_ids(selected_metadata, ("block_table",))
    cache = getattr(module, "kv_cache", None)
    cache_tensor = None
    if isinstance(cache, Sequence) and len(cache) > virtual_engine:
        candidate = cache[virtual_engine]
        if torch.is_tensor(candidate):
            cache_tensor = candidate
        elif isinstance(candidate, Sequence):
            cache_tensor = next((item for item in candidate if torch.is_tensor(item)), None)
    entries = []
    if torch.is_tensor(cache_tensor) and cache_tensor.dim() >= 2:
        valid = [item for item in block_ids if item < int(cache_tensor.shape[1])]
        if valid:
            index_tensor = torch.tensor(valid, dtype=torch.long, device=cache_tensor.device)
            snapshot = cache_tensor.detach().index_select(1, index_tensor).to("cpu").clone()
            retained.append(snapshot)
            entries.append(
                {
                    "source_shape": _shape(cache_tensor),
                    "source_dtype": str(cache_tensor.dtype),
                    "source_device": str(cache_tensor.device),
                    "block_dimension": 1,
                    "active_block_ids": valid,
                    "snapshot_shape": _shape(snapshot),
                    "snapshot_sha256": _tensor_sha256(snapshot),
                }
            )
    return (
        {
            "family": "full_attention",
            "boundary": "torch.ops.vllm.unified_kv_cache_update and torch.ops.vllm.unified_attention_with_output remain opaque",
            "representation": "Attention.kv_cache[virtual_engine]",
            "virtual_engine": virtual_engine,
            "active_block_ids": block_ids,
            "snapshot_tensors": entries,
            "snapshot_tensor_count": len(entries),
            "replay_use": "active entry blocks retained as external mutation-boundary evidence; opaque fake implementations do not consume them",
        },
        retained,
    )


def _wrap_method(cls: Any, name: str, wrapper_factory: Any) -> None:
    original = getattr(cls, name)
    if getattr(original, "_r032_selected_layer_fx_patched", False):
        return
    wrapped = wrapper_factory(original)
    wrapped._r032_selected_layer_fx_patched = True
    setattr(cls, name, wrapped)
    _RESTORES.append(RestoreRecord(cls=cls, name=name, original=original, wrapped=wrapped))


def _source_mapping(
    expected: Mapping[str, str] | None,
    *,
    request_id: str,
    engine_step_id: int,
    forward_id: int,
    layer_id: int,
    layer_occurrence: int,
    phase: str,
    q_len: int,
    past_len: int,
    kv_len: int,
    layer_type: str,
) -> tuple[bool | str, str]:
    if not expected:
        return "", ""
    checks = {
        "contract_id": (_contract_id(), expected.get("contract_id")),
        "rank": (_rank(), _safe_int(expected.get("rank"))),
        "worker_id": (_worker_id(), expected.get("worker_id")),
        "request_id": (request_id, expected.get("request_id")),
        "engine_step_id": (engine_step_id, _safe_int(expected.get("engine_step_id"))),
        "forward_id": (forward_id, _safe_int(expected.get("forward_id"))),
        "layer_idx": (layer_id, _safe_int(expected.get("layer_idx"))),
        "layer_occurrence": (
            layer_occurrence,
            _safe_int(expected.get("layer_occurrence")),
        ),
        "phase": (phase, expected.get("phase")),
        "q_len": (q_len, _safe_int(expected.get("q_len"))),
        "past_len": (past_len, _safe_int(expected.get("past_len"))),
        "kv_len": (kv_len, _safe_int(expected.get("kv_len"))),
        "layer_type": (layer_type, expected.get("layer_type")),
    }
    # A direct in-process LLM request does not expose a stable scheduler
    # request ID before execution.  Empty source cells are therefore explicit
    # non-join fields, while every populated contract/shape field remains
    # strict.  This never relaxes forward/layer/phase/q/past/kv/type matching.
    errors = [
        f"{key}:{actual!r}!={source!r}"
        for key, (actual, source) in checks.items()
        if source not in (None, "") and actual != source
    ]
    return not errors, ";".join(errors)


def _patch_model_runner() -> None:
    from vllm.v1.worker.gpu_model_runner import GPUModelRunner

    def execute_wrapper(original: Any) -> Any:
        @functools.wraps(original)
        def wrapped(self: Any, scheduler_output: Any, *args: Any, **kwargs: Any) -> Any:
            global _ACTIVE_EXECUTES
            if not _is_armed():
                return original(self, scheduler_output, *args, **kwargs)

            forward_id = int(getattr(self, "_r032_fx_forward_id", 0)) + 1
            setattr(self, "_r032_fx_forward_id", forward_id)
            token_map = getattr(scheduler_output, "num_scheduled_tokens", {}) or {}
            scheduled = {str(key): int(value) for key, value in token_map.items()}
            request_ids = list(scheduled)
            request_id = request_ids[0] if len(request_ids) == 1 else ""
            total = sum(scheduled.values())
            phase = "empty" if total == 0 else ("decode" if total == 1 else "prefill_chunk")
            past_len = _REQUEST_COMPUTED.get(request_id, 0) if request_id else 0
            context = {
                "request_id": request_id,
                "request_ids": request_ids,
                "engine_step_id": forward_id,
                "forward_id": forward_id,
                "phase": phase,
                "total_num_scheduled_tokens": total,
                "past_len": past_len,
                "kv_len": past_len + total,
                "rank": _rank(),
                "worker_id": _worker_id(),
            }
            previous = getattr(_STATE, "forward", None)
            _STATE.forward = context
            with _LOCK:
                _ACTIVE_EXECUTES += 1
            begin = _now_ns()
            error = ""
            try:
                return original(self, scheduler_output, *args, **kwargs)
            except BaseException as exc:
                error = repr(exc)
                raise
            finally:
                end = _now_ns()
                if request_id and total > 0:
                    _REQUEST_COMPUTED[request_id] = past_len + total
                with _LOCK:
                    _ACTIVE_EXECUTES -= 1
                    _FORWARD_ROWS.append(
                        {
                            **context,
                            "begin_ns": begin,
                            "end_ns": end,
                            "error": error,
                        }
                    )
                _STATE.forward = previous

        return wrapped

    _wrap_method(GPUModelRunner, "execute_model", execute_wrapper)


def _patch_decoder_layer() -> None:
    from vllm.model_executor.models.qwen3_5 import Qwen3_5DecoderLayer

    def forward_wrapper(original: Any) -> Any:
        @functools.wraps(original)
        def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            global _CAPTURE_FIRST_NS, _CAPTURE_LAST_NS
            if not _is_armed():
                return original(self, *args, **kwargs)

            forward = getattr(_STATE, "forward", None) or {}
            forward_id = int(forward.get("forward_id", -1))
            engine_step_id = int(forward.get("engine_step_id", forward_id))
            request_id = str(forward.get("request_id", ""))
            phase = str(forward.get("phase", "unknown"))
            past_len = int(forward.get("past_len", 0))

            hidden_states = kwargs.get("hidden_states")
            if hidden_states is None and args:
                hidden_states = args[0]
            residual = kwargs.get("residual")
            if residual is None and len(args) > 1:
                residual = args[1]
            positions = kwargs.get("positions")
            if positions is None and len(args) > 2:
                positions = args[2]

            layer_id = int(getattr(self, "layer_idx"))
            layer_type = str(getattr(self, "layer_type"))
            q_len = int(hidden_states.shape[0]) if torch.is_tensor(hidden_states) else -1
            kv_len = past_len + max(q_len, 0)
            occurrence_key = (forward_id, layer_id)
            with _LOCK:
                layer_occurrence = _OCCURRENCES[occurrence_key]
                _OCCURRENCES[occurrence_key] += 1

            event_id = _event_id(forward_id, layer_id)
            expected = _source_by_event().get(event_id)
            matched = expected is not None
            source_match, source_error = _source_mapping(
                expected,
                request_id=request_id,
                engine_step_id=engine_step_id,
                forward_id=forward_id,
                layer_id=layer_id,
                layer_occurrence=layer_occurrence,
                phase=phase,
                q_len=q_len,
                past_len=past_len,
                kv_len=kv_len,
                layer_type=layer_type,
            )

            capture_begin = 0
            capture_end = 0
            sample: FxSample | None = None
            if matched:
                capture_begin = _now_ns()
                try:
                    sample_args, sample_kwargs = _base._snapshot_inputs(
                        tuple(args), dict(kwargs)
                    )
                    replay_context, context_summary, selected_metadata = (
                        _capture_forward_context(self)
                    )
                    state_summary, retained_state = _capture_external_state(
                        self,
                        replay_context,
                        selected_metadata,
                    )
                    capture_end = _now_ns()
                    if event_id in _SAMPLES:
                        raise RuntimeError(f"duplicate selected event sample: {event_id}")
                    sample = FxSample(
                        event_id=event_id,
                        layer=self,
                        original_forward=original,
                        call_args=sample_args,
                        call_kwargs=sample_kwargs,
                        replay_context=replay_context,
                        context_summary=context_summary,
                        state_summary=state_summary,
                        retained_state_tensors=retained_state,
                        layer_row={},
                        capture_begin_ns=capture_begin,
                        capture_end_ns=capture_end,
                    )
                    with _LOCK:
                        _SAMPLES[event_id] = sample
                        _CAPTURE_FIRST_NS = (
                            capture_begin
                            if _CAPTURE_FIRST_NS is None
                            else min(_CAPTURE_FIRST_NS, capture_begin)
                        )
                        _CAPTURE_LAST_NS = (
                            capture_end
                            if _CAPTURE_LAST_NS is None
                            else max(_CAPTURE_LAST_NS, capture_end)
                        )
                    _write_event(
                        "selected_sample_captured",
                        event_id=event_id,
                        source_event_id=expected.get("source_event_id") if expected else None,
                        capture_begin_ns=capture_begin,
                        capture_end_ns=capture_end,
                        context_keys=context_summary.get("selected_context_keys"),
                        state_snapshot_tensor_count=state_summary.get(
                            "snapshot_tensor_count"
                        ),
                    )
                except BaseException as exc:
                    capture_end = _now_ns()
                    error_record = {
                        "event_id": event_id,
                        "where": "layer_entry_capture",
                        "error": repr(exc),
                        "traceback": traceback.format_exc(),
                    }
                    _CAPTURE_ERRORS.append(error_record)
                    _write_event("capture_error", **error_record)

            eager_begin = _now_ns()
            eager_error = ""
            output = None
            try:
                output = original(self, *args, **kwargs)
                return output
            except BaseException as exc:
                eager_error = repr(exc)
                raise
            finally:
                eager_end = _now_ns()
                hidden_out = output[0] if isinstance(output, tuple) and output else output
                residual_out = (
                    output[1]
                    if isinstance(output, tuple) and len(output) > 1
                    else None
                )
                row = {
                    "event_id": event_id,
                    "selection_id": expected.get("selection_id", "") if expected else "",
                    "source_event_id": (
                        expected.get("source_event_id", "") if expected else ""
                    ),
                    "source_run_id": expected.get("run_id", "") if expected else "",
                    "run_id": _run_id(),
                    "contract_id": _contract_id(),
                    "source_revision": _source_revision(),
                    "rank": _rank(),
                    "worker_id": _worker_id(),
                    "device_id": _device_id(),
                    "request_id": request_id,
                    "engine_step_id": engine_step_id,
                    "forward_id": forward_id,
                    "layer_id": layer_id,
                    "layer_occurrence": layer_occurrence,
                    "phase": phase,
                    "total_num_scheduled_tokens": forward.get(
                        "total_num_scheduled_tokens", ""
                    ),
                    "q_len": q_len,
                    "past_len": past_len,
                    "kv_len": kv_len,
                    "layer_type": layer_type,
                    "source_contract_match": source_match,
                    "source_mapping_error": source_error,
                    "hidden_shape_in": _shape_json(hidden_states),
                    "residual_shape_in": _shape_json(residual),
                    "positions_shape": _shape_json(positions),
                    "hidden_shape_out": _shape_json(hidden_out),
                    "residual_shape_out": _shape_json(residual_out),
                    "matched": matched,
                    "fx_sampled": sample is not None,
                    "fx_traced": False,
                    "fx_trace_status": "pending" if sample is not None else "",
                    "fx_node_count": "",
                    "trace_dir": "",
                    "capture_begin_ns": capture_begin,
                    "capture_end_ns": capture_end,
                    "eager_begin_ns": eager_begin,
                    "eager_end_ns": eager_end,
                    "error": eager_error,
                }
                if sample is not None:
                    sample.layer_row = row
                with _LOCK:
                    _LAYER_ROWS.append(row)
                    _base._append_csv(
                        _trace_dir() / "fx_layer_events.csv",
                        LAYER_EVENT_FIELDS,
                        row,
                    )

        return wrapped

    _wrap_method(Qwen3_5DecoderLayer, "forward", forward_wrapper)


def _restore_wrappers() -> None:
    global _WRAPPERS_RESTORED_NS
    for record in reversed(_RESTORES):
        try:
            current = getattr(record.cls, record.name)
            if current is record.wrapped:
                setattr(record.cls, record.name, record.original)
            elif current is not record.original:
                raise RuntimeError(
                    f"{record.cls.__module__}.{record.cls.__qualname__}.{record.name} "
                    "was replaced by an unknown wrapper"
                )
        except BaseException as exc:
            _RESTORE_ERRORS.append(
                {
                    "target": (
                        f"{record.cls.__module__}.{record.cls.__qualname__}."
                        f"{record.name}"
                    ),
                    "error": repr(exc),
                }
            )
    _WRAPPERS_RESTORED_NS = _now_ns()
    _write_event(
        "wrappers_restored",
        wrapper_count=len(_RESTORES),
        errors=_RESTORE_ERRORS,
        wrappers_restored_ns=_WRAPPERS_RESTORED_NS,
    )


def _expected_opaque_ops(layer_type: str) -> list[str]:
    if layer_type == "linear_attention":
        return ["vllm.gdn_attention_core.default"]
    return [
        "vllm.unified_kv_cache_update.default",
        "vllm.unified_attention_with_output.default",
    ]


def _trace_one(sample: FxSample, expected: Mapping[str, str]) -> dict[str, Any]:
    global _OFFLINE_FIRST_START_NS, _OFFLINE_LAST_END_NS
    event_id = sample.event_id
    trace_dir = _trace_dir() / event_id
    start = _now_ns()
    if _OFFLINE_FIRST_START_NS is None:
        _OFFLINE_FIRST_START_NS = start
    row = {
        "event_id": event_id,
        "selection_id": expected.get("selection_id", ""),
        "source_event_id": expected.get("source_event_id", ""),
        "source_run_id": expected.get("run_id", ""),
        "run_id": _run_id(),
        "contract_id": _contract_id(),
        "source_revision": _source_revision(),
        "rank": sample.layer_row.get("rank"),
        "worker_id": sample.layer_row.get("worker_id"),
        "device_id": sample.layer_row.get("device_id"),
        "request_id": sample.layer_row.get("request_id"),
        "engine_step_id": sample.layer_row.get("engine_step_id"),
        "forward_id": sample.layer_row.get("forward_id"),
        "layer_id": sample.layer_row.get("layer_id"),
        "layer_occurrence": sample.layer_row.get("layer_occurrence"),
        "phase": sample.layer_row.get("phase"),
        "q_len": sample.layer_row.get("q_len"),
        "past_len": sample.layer_row.get("past_len"),
        "kv_len": sample.layer_row.get("kv_len"),
        "layer_type": sample.layer_row.get("layer_type"),
        "source_contract_match": sample.layer_row.get("source_contract_match"),
        "trace_dir": str(trace_dir),
        "offline_trace_start_ns": start,
    }
    try:
        target, flat_args, input_binding = _base._make_fx_positional_call(
            sample.original_forward,
            sample.layer,
            sample.call_args,
            sample.call_kwargs,
        )
        expected_ops = _expected_opaque_ops(str(sample.layer_row["layer_type"]))
        specialization = {
            "kind": "qwen35_vllm_v1_fixed_runtime_input_post_request_replay",
            "analysis_only": True,
            "run_id": _run_id(),
            "contract_id": _contract_id(),
            "selection_id": expected.get("selection_id"),
            "source_event_id": expected.get("source_event_id"),
            "source_join_key": {
                key: expected.get(key)
                for key in (
                    "run_id",
                    "contract_id",
                    "rank",
                    "worker_id",
                    "request_id",
                    "engine_step_id",
                    "forward_id",
                    "layer_idx",
                    "layer_occurrence",
                )
            },
            "capture_join_key": {
                "run_id": _run_id(),
                "contract_id": sample.layer_row.get("contract_id"),
                "rank": sample.layer_row.get("rank"),
                "worker_id": sample.layer_row.get("worker_id"),
                "request_id": sample.layer_row.get("request_id"),
                "engine_step_id": sample.layer_row.get("engine_step_id"),
                "forward_id": sample.layer_row.get("forward_id"),
                "layer_idx": sample.layer_row.get("layer_id"),
                "layer_occurrence": sample.layer_row.get("layer_occurrence"),
            },
            "source_sequence_contract": {
                "phase": sample.layer_row.get("phase"),
                "q_len": sample.layer_row.get("q_len"),
                "past_len": sample.layer_row.get("past_len"),
                "kv_len": sample.layer_row.get("kv_len"),
                "layer_type": sample.layer_row.get("layer_type"),
                "matched": sample.layer_row.get("source_contract_match"),
            },
            "runtime_inputs": {
                "args": _base._describe_value(sample.call_args),
                "kwargs": _base._describe_value(sample.call_kwargs),
            },
            "forward_context_snapshot": sample.context_summary,
            "external_state_snapshot": sample.state_summary,
            "opaque_custom_op_boundary": {
                "expected_nodes": expected_ops,
                "claim_guard": (
                    "FX records the fixed input path up to opaque ROCm/DCU custom "
                    "ops; it does not expose their internal kernels or branches."
                ),
            },
            "lifecycle": {
                "sample_capture_begin_ns": sample.capture_begin_ns,
                "sample_capture_end_ns": sample.capture_end_ns,
                "finalize_marker_observed_ns": _FINALIZE_MARKER_OBSERVED_NS,
                "wrappers_restored_ns": _WRAPPERS_RESTORED_NS,
                "offline_trace_start_ns": start,
                "runtime_response_source": "original eager decoder layer forward",
                "fx_graph_used_for_runtime_response": False,
            },
            "reversible_analysis_specializations": [
                "temporarily unwrap instance-compiled RMSNorm helpers",
                "temporarily replace vLLM parameter subclasses with plain Parameters",
                "temporarily route rotary embedding through its native path",
                "temporarily route RMSNormGated through its native path",
                "temporarily disable the gfx936 GDN strided-RMSNorm fast-path guard during structural fake replay",
                "temporarily route unquantized GEMM through torch.nn.functional.linear",
            ],
            "no_multimodal_pruning_specialization": True,
        }

        from vllm.forward_context import override_forward_context

        with (
            torch.inference_mode(),
            override_forward_context(sample.replay_context),
            _base._temporarily_unwrap_compiled_layernorms(sample.layer),
            _base._temporarily_plain_parameters(sample.layer),
            _base._temporarily_use_native_rotary(sample.layer),
            _base._temporarily_use_native_gdn_norm(sample.layer),
            _base._temporarily_use_default_unquantized_gemm(),
        ):
            graph_module = make_fx(target, **_base._trace_options())(*flat_args)

        targets = [str(node.target) for node in graph_module.graph.nodes]
        missing_ops = [name for name in expected_ops if name not in targets]
        if missing_ops:
            raise RuntimeError(f"missing expected opaque FX custom ops: {missing_ops}")

        save_errors = _base._write_trace_outputs(
            trace_dir,
            graph_module,
            {
                "target": f"{event_id}:Qwen3_5DecoderLayer.forward",
                "event_id": event_id,
                "selection_id": expected.get("selection_id"),
                "source_event_id": expected.get("source_event_id"),
                "run_id": _run_id(),
                "contract_id": _contract_id(),
                "source_revision": _source_revision(),
                "rank": sample.layer_row.get("rank"),
                "worker_id": sample.layer_row.get("worker_id"),
                "device_id": sample.layer_row.get("device_id"),
                "request_id": sample.layer_row.get("request_id"),
                "engine_step_id": sample.layer_row.get("engine_step_id"),
                "forward_id": sample.layer_row.get("forward_id"),
                "layer_idx": sample.layer_row.get("layer_id"),
                "layer_occurrence": sample.layer_row.get("layer_occurrence"),
                "phase": sample.layer_row.get("phase"),
                "q_len": sample.layer_row.get("q_len"),
                "past_len": sample.layer_row.get("past_len"),
                "kv_len": sample.layer_row.get("kv_len"),
                "layer_type": sample.layer_row.get("layer_type"),
                "source_contract_match": sample.layer_row.get(
                    "source_contract_match"
                ),
                "trace_strategy": "runtime_sample_then_post_request_offline_make_fx",
                "input_binding": input_binding,
                "specialization": specialization,
                "tracing_options": _base._trace_options(),
                "opaque_custom_ops": expected_ops,
            },
        )
        if save_errors:
            raise RuntimeError(f"GraphModule serialization errors: {save_errors}")

        node_count = len(list(graph_module.graph.nodes))
        end = _now_ns()
        row.update(
            {
                "status": "ok",
                "node_count": node_count,
                "specialization": json.dumps(
                    _base._jsonable(specialization),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "input_binding": json.dumps(
                    _base._jsonable(input_binding),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "opaque_custom_ops": json.dumps(expected_ops),
                "save_errors": "[]",
                "offline_trace_end_ns": end,
                "duration_ns": end - start,
            }
        )
        sample.layer_row.update(
            {
                "fx_traced": True,
                "fx_trace_status": "ok",
                "fx_node_count": node_count,
                "trace_dir": str(trace_dir),
            }
        )
        _write_event(
            "offline_fx_trace_ok",
            event_id=event_id,
            source_event_id=expected.get("source_event_id"),
            node_count=node_count,
            trace_dir=str(trace_dir),
            offline_trace_start_ns=start,
            offline_trace_end_ns=end,
        )
    except BaseException as exc:
        end = _now_ns()
        row.update(
            {
                "status": "error",
                "error": repr(exc),
                "offline_trace_end_ns": end,
                "duration_ns": end - start,
            }
        )
        sample.layer_row.update(
            {
                "fx_traced": False,
                "fx_trace_status": "error",
                "trace_dir": str(trace_dir),
                "error": repr(exc),
            }
        )
        _write_event(
            "offline_fx_trace_error",
            event_id=event_id,
            error=repr(exc),
            traceback=traceback.format_exc(),
        )
    _OFFLINE_LAST_END_NS = int(row["offline_trace_end_ns"])
    return row


def _source_identity() -> dict[str, Any]:
    from vllm.forward_context import ForwardContext
    from vllm.model_executor.models.qwen3_5 import Qwen3_5DecoderLayer
    from vllm.v1.worker.gpu_model_runner import GPUModelRunner

    identities = {}
    for name, value in (
        ("ForwardContext", ForwardContext),
        ("Qwen3_5DecoderLayer", Qwen3_5DecoderLayer),
        ("GPUModelRunner", GPUModelRunner),
    ):
        path = Path(inspect.getsourcefile(value) or inspect.getfile(value)).resolve()
        identities[name] = {
            "path": str(path),
            "sha256": _sha256_file(path),
        }
    return {
        "installed_vllm_version": importlib.metadata.version("vllm"),
        "installed_sources": identities,
        "repository": os.environ.get("VLLM_R032_SOURCE_ROOT", ""),
        "revision": _source_revision(),
        "model_path": os.environ.get("VLLM_R032_MODEL_PATH", ""),
        "model_config_sha256": os.environ.get("VLLM_R032_MODEL_CONFIG_SHA256", ""),
    }


def _write_run_metadata(status: str) -> None:
    ordered_samples = [event for event in _target_order() if event in _SAMPLES]
    ok_count = sum(row.get("status") == "ok" for row in _MANIFEST_ROWS)
    error_count = sum(row.get("status") == "error" for row in _MANIFEST_ROWS)
    state_bytes = 0
    for sample in _SAMPLES.values():
        state_bytes += sum(
            tensor.numel() * tensor.element_size()
            for tensor in sample.retained_state_tensors
        )
    metadata = {
        "schema_version": 1,
        "analysis_type": os.environ.get(
            "VLLM_R032_FX_ANALYSIS_TYPE",
            "qwen35_vllm_v1_selected_layer_fx_trace",
        ),
        "status": status,
        "run_id": _run_id(),
        "contract_id": _contract_id(),
        "trace_strategy": "runtime_sample_then_post_request_offline_make_fx",
        "evidence_boundary": {
            "runtime_sampling": (
                "A real eager Qwen3.5-27B vLLM V1 request returned only original "
                "decoder-layer outputs; selected fixed inputs, context metadata, "
                "and active external state slices were cloned at layer entry."
            ),
            "offline_fx_dag": (
                "After the request client returned, the finalize marker was "
                "observed, active model execution reached zero, all R032 wrappers "
                "were restored, and fixed samples were replayed with make_fx."
            ),
            "custom_ops": (
                "ROCm/DCU attention and GDN core operations remain opaque nodes; "
                "their internal kernels and unobserved branches are out of scope."
            ),
        },
        "source_identity": _source_identity(),
        "device": {
            "logical_device": os.environ.get("CUDA_VISIBLE_DEVICES", ""),
            "hip_visible_devices": os.environ.get("HIP_VISIBLE_DEVICES", ""),
            "device_id": _device_id(),
            "serial": os.environ.get("VLLM_R032_DEVICE_SERIAL", ""),
        },
        "canonical_selected_manifest": str(_selected_manifest_path()),
        "canonical_manifest_sha256": _sha256_file(_selected_manifest_path()),
        "selection_handoff": str(_selection_handoff_path()),
        "selection_handoff_sha256": _sha256_file(_selection_handoff_path()),
        "source_trace": str(_source_trace_path()),
        "source_trace_sha256": _sha256_file(_source_trace_path()),
        "join_key": [
            "run_id",
            "contract_id",
            "rank",
            "worker_id",
            "request_id",
            "engine_step_id",
            "forward_id",
            "layer_idx",
            "layer_occurrence",
        ],
        "target_event_keys": _target_order(),
        "ordered_selection_ids": [row["selection_id"] for row in _source_rows()],
        "ordered_source_event_ids": [
            row["source_event_id"] for row in _source_rows()
        ],
        "observed_layer_event_count": len(_LAYER_ROWS),
        "observed_forward_count": len(
            [row for row in _FORWARD_ROWS if row.get("total_num_scheduled_tokens", 0) > 0]
        ),
        "observed_model_execute_count": len(_FORWARD_ROWS),
        "fx_sample_count": len(_SAMPLES),
        "fx_trace_count": ok_count,
        "fx_trace_error_count": error_count,
        "captured_events": ordered_samples,
        "captured_request_ids": sorted(
            {
                str(sample.layer_row.get("request_id"))
                for sample in _SAMPLES.values()
                if sample.layer_row.get("request_id")
            }
        ),
        "external_state_snapshot_bytes_retained": state_bytes,
        "external_state_snapshots": {
            event: _SAMPLES[event].state_summary for event in ordered_samples
        },
        "forward_context_snapshots": {
            event: _SAMPLES[event].context_summary for event in ordered_samples
        },
        "lifecycle": {
            "capture_first_ns": _CAPTURE_FIRST_NS,
            "capture_last_ns": _CAPTURE_LAST_NS,
            "finalize_protocol": os.environ.get(
                "VLLM_R032_FINALIZE_PROTOCOL",
                "controller creates marker only after request client returns",
            ),
            "finalize_marker": str(_finalize_file()),
            "finalize_marker_observed_ns": _FINALIZE_MARKER_OBSERVED_NS,
            "active_execute_count_at_finalize": _ACTIVE_EXECUTES,
            "wrappers_installed_count": len(_RESTORES),
            "wrappers_restored_ns": _WRAPPERS_RESTORED_NS,
            "wrapper_restore_errors": _RESTORE_ERRORS,
            "offline_first_start_ns": _OFFLINE_FIRST_START_NS,
            "offline_last_end_ns": _OFFLINE_LAST_END_NS,
            "wrappers_restored_before_offline_fx": bool(
                _WRAPPERS_RESTORED_NS
                and _OFFLINE_FIRST_START_NS
                and _WRAPPERS_RESTORED_NS <= _OFFLINE_FIRST_START_NS
            ),
        },
        "tracing_options": _base._trace_options(),
        "patch_errors": _PATCH_ERRORS,
        "capture_errors": _CAPTURE_ERRORS,
        "outputs": {
            "fx_layer_events": str(_trace_dir() / "fx_layer_events.csv"),
            "fx_layer_trace_manifest": str(
                _trace_dir() / "fx_layer_trace_manifest.csv"
            ),
            "run_metadata": str(_trace_dir() / "run_metadata.json"),
            "request_result": str(_trace_dir() / "request" / "result.json"),
            "event_stream_glob": str(_trace_dir() / "events.*.jsonl"),
        },
        "expected_event_outputs": [
            "fx_graph.py",
            "fx_graph.txt",
            "fx_nodes.json",
            "fx_graph_module.pt",
            "fx_graph_module/",
            "fx_trace_metadata.json",
        ],
        "scope_guards": [
            "FX is a fixed-input DAG and does not prove unobserved Python branches.",
            "Opaque custom-op internals and ROCm/DCU kernel timelines are not FX evidence.",
            "This max_concurrency=1 TP=PP=DP=1 run does not prove concurrent or distributed behavior.",
            "No multimodal pruning or early-exit decision is claimed.",
            "R02 theoretical FLOPs are not measured latency.",
        ],
    }
    _write_json_atomic(_trace_dir() / "run_metadata.json", metadata)


def _finalize() -> None:
    global _FINALIZED, _FINALIZE_STARTED, _FINALIZE_MARKER_OBSERVED_NS
    with _FINALIZE_LOCK:
        if _FINALIZED or _FINALIZE_STARTED:
            return
        _FINALIZE_STARTED = True
        _FINALIZE_MARKER_OBSERVED_NS = _now_ns()

        deadline = time.monotonic() + 60.0
        while True:
            with _LOCK:
                active = _ACTIVE_EXECUTES
            if active == 0:
                break
            if time.monotonic() >= deadline:
                _PATCH_ERRORS.append(
                    {
                        "where": "finalize_wait",
                        "error": f"active execute count remained {active}",
                    }
                )
                break
            time.sleep(0.05)

        _restore_wrappers()

        # Processes that never executed decoder layers still restore their
        # wrappers, but only the real model worker owns samples and artifacts.
        if not _LAYER_ROWS and not _SAMPLES:
            _FINALIZED = True
            return

        _write_event(
            "offline_finalize_begin",
            sample_count=len(_SAMPLES),
            layer_event_count=len(_LAYER_ROWS),
            finalize_marker_observed_ns=_FINALIZE_MARKER_OBSERVED_NS,
            wrappers_restored_ns=_WRAPPERS_RESTORED_NS,
        )
        if torch.cuda.is_available():
            torch.cuda.synchronize()

        for expected in _source_rows():
            event_id = expected["event_id"]
            sample = _SAMPLES.get(event_id)
            if sample is None:
                now = _now_ns()
                _MANIFEST_ROWS.append(
                    {
                        "event_id": event_id,
                        "selection_id": expected.get("selection_id", ""),
                        "source_event_id": expected.get("source_event_id", ""),
                        "source_run_id": expected.get("run_id", ""),
                        "run_id": _run_id(),
                        "contract_id": _contract_id(),
                        "source_revision": _source_revision(),
                        "status": "error",
                        "error": "selected runtime sample is missing",
                        "offline_trace_start_ns": now,
                        "offline_trace_end_ns": now,
                        "duration_ns": 0,
                    }
                )
                continue
            _MANIFEST_ROWS.append(_trace_one(sample, expected))

        if torch.cuda.is_available():
            torch.cuda.synchronize()
        with _LOCK:
            _write_csv_atomic(
                _trace_dir() / "fx_layer_events.csv",
                LAYER_EVENT_FIELDS,
                _LAYER_ROWS,
            )
            _write_csv_atomic(
                _trace_dir() / "fx_layer_trace_manifest.csv",
                TRACE_MANIFEST_FIELDS,
                _MANIFEST_ROWS,
            )

        passed = (
            len(_SAMPLES) == len(_source_rows())
            and len(_MANIFEST_ROWS) == len(_source_rows())
            and all(row.get("status") == "ok" for row in _MANIFEST_ROWS)
            and not _PATCH_ERRORS
            and not _CAPTURE_ERRORS
            and not _RESTORE_ERRORS
        )
        status = "complete" if passed else "error"
        _write_run_metadata(status)
        _write_json_atomic(
            _done_file(),
            {
                "status": status,
                "pid": os.getpid(),
                "rank": _rank(),
                "worker_id": _worker_id(),
                "fx_sample_count": len(_SAMPLES),
                "fx_trace_count": sum(
                    row.get("status") == "ok" for row in _MANIFEST_ROWS
                ),
                "fx_trace_error_count": sum(
                    row.get("status") == "error" for row in _MANIFEST_ROWS
                ),
                "observed_layer_event_count": len(_LAYER_ROWS),
                "run_metadata": str(_trace_dir() / "run_metadata.json"),
            },
        )
        _write_event(
            "offline_finalize_end",
            status=status,
            done_file=str(_done_file()),
        )
        sys.stderr.write(
            "[r032-selected-layer-fx] finalize "
            f"status={status} samples={len(_SAMPLES)} "
            f"ok={sum(row.get('status') == 'ok' for row in _MANIFEST_ROWS)}\n"
        )
        _FINALIZED = True


def _monitor_finalize() -> None:
    try:
        while not _FINALIZED:
            if _finalize_file().is_file():
                _finalize()
                return
            time.sleep(0.2)
    except BaseException as exc:
        _PATCH_ERRORS.append(
            {
                "where": "finalize_monitor",
                "error": repr(exc),
                "traceback": traceback.format_exc(),
            }
        )
        if _LAYER_ROWS or _SAMPLES:
            try:
                _write_run_metadata("error")
                _write_json_atomic(
                    _done_file(),
                    {
                        "status": "error",
                        "pid": os.getpid(),
                        "error": repr(exc),
                    },
                )
            except Exception:
                pass


def _atexit_incomplete() -> None:
    if not _enabled() or _FINALIZED or (not _LAYER_ROWS and not _SAMPLES):
        return
    try:
        _write_run_metadata("incomplete_service_exit_before_finalize")
    except Exception:
        pass


def apply_patches() -> None:
    global _PATCHED
    if _PATCHED or not _enabled():
        return
    _PATCHED = True
    _trace_dir().mkdir(parents=True, exist_ok=True)
    _source_rows()
    for patch_fn in (_patch_model_runner, _patch_decoder_layer):
        try:
            patch_fn()
        except BaseException as exc:
            record = {
                "patch": patch_fn.__name__,
                "error": repr(exc),
                "traceback": traceback.format_exc(),
            }
            _PATCH_ERRORS.append(record)
            _write_event("patch_error", **record)
    _write_event(
        "patch_loaded",
        patches=["GPUModelRunner.execute_model", "Qwen3_5DecoderLayer.forward"],
        target_event_keys=_target_order(),
        replay_protocol="post_request_finalize_marker",
        patch_errors=_PATCH_ERRORS,
    )
    monitor = threading.Thread(
        target=_monitor_finalize,
        name="r032-fx-finalize-monitor",
        daemon=True,
    )
    monitor.start()
    atexit.register(_atexit_incomplete)
