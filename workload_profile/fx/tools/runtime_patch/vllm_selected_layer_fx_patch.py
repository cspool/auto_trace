"""Current-source FX serialization helpers for Qwen3.5 fixed-input replay.

This module deliberately contains utilities only.  It never installs runtime
patches by itself.  The R02 current-child sampler imports these helpers after
the real eager request inputs have been cloned, restores the runtime wrappers,
and then performs analysis-only ``make_fx`` replay.
"""

from __future__ import annotations

import csv
import dataclasses
import inspect
import json
import os
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import torch


def _jsonable(value: Any) -> Any:
    if torch.is_tensor(value):
        return {
            "type": "tensor",
            "shape": [int(item) for item in value.shape],
            "stride": [int(item) for item in value.stride()],
            "dtype": str(value.dtype),
            "device": str(value.device),
            "requires_grad": bool(value.requires_grad),
        }
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (torch.dtype, torch.device)):
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted(_jsonable(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def _describe_value(value: Any) -> Any:
    """Describe replay inputs without serializing tensor payloads."""
    return _jsonable(value)


def _snapshot_value(value: Any, memo: dict[int, Any]) -> Any:
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
            {key: _snapshot_value(item, memo) for key, item in value.items()}
        )
        return cloned
    if isinstance(value, tuple):
        cloned_tuple = tuple(_snapshot_value(item, memo) for item in value)
        memo[value_id] = cloned_tuple
        return cloned_tuple
    if isinstance(value, list):
        cloned_list: list[Any] = []
        memo[value_id] = cloned_list
        cloned_list.extend(_snapshot_value(item, memo) for item in value)
        return cloned_list
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        cloned = object.__new__(type(value))
        memo[value_id] = cloned
        for field in dataclasses.fields(value):
            object.__setattr__(
                cloned,
                field.name,
                _snapshot_value(getattr(value, field.name), memo),
            )
        return cloned
    return value


def _snapshot_inputs(
    args: tuple[Any, ...], kwargs: dict[str, Any]
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    memo: dict[int, Any] = {}
    return (
        tuple(_snapshot_value(item, memo) for item in args),
        {key: _snapshot_value(item, memo) for key, item in kwargs.items()},
    )


def _append_csv(path: Path, fields: list[str], row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.is_file()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fields})


def _make_fx_positional_call(
    original: Any,
    module: torch.nn.Module,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> tuple[Any, tuple[Any, ...], dict[str, Any]]:
    """Flatten a method call into stable positional make_fx inputs."""
    signature = inspect.signature(original)
    bound = signature.bind(module, *args, **kwargs)
    bound.apply_defaults()

    input_names: list[str] = []
    input_values: list[Any] = []
    extra_kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if name == "self":
            continue
        value = bound.arguments.get(name)
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            for index, item in enumerate(value or ()):
                input_names.append(f"{name}[{index}]")
                input_values.append(item)
        elif parameter.kind == inspect.Parameter.VAR_KEYWORD:
            extra_kwargs = dict(value or {})
            for key in sorted(extra_kwargs):
                input_names.append(f"{name}.{key}")
                input_values.append(extra_kwargs[key])
        else:
            input_names.append(name)
            input_values.append(value)

    def target(*flat: Any) -> Any:
        cursor = 0
        call_args: list[Any] = []
        call_kwargs: dict[str, Any] = {}
        for name, parameter in signature.parameters.items():
            if name == "self":
                continue
            if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
                count = len(bound.arguments.get(name) or ())
                call_args.extend(flat[cursor : cursor + count])
                cursor += count
            elif parameter.kind == inspect.Parameter.VAR_KEYWORD:
                for key in sorted(extra_kwargs):
                    call_kwargs[key] = flat[cursor]
                    cursor += 1
            elif parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
                call_args.append(flat[cursor])
                cursor += 1
            else:
                call_kwargs[name] = flat[cursor]
                cursor += 1
        if cursor != len(flat):
            raise RuntimeError("make_fx input binding did not consume all values")
        return original(module, *call_args, **call_kwargs)

    target.__name__ = f"fx_replay_{module.__class__.__name__}_forward"
    binding = {
        "signature": str(signature),
        "ordered_inputs": [
            {
                "ordinal": ordinal,
                "name": name,
                "value": _describe_value(value),
            }
            for ordinal, (name, value) in enumerate(
                zip(input_names, input_values, strict=True)
            )
        ],
    }
    return target, tuple(input_values), binding


@contextmanager
def _replace_forward_methods(
    root: torch.nn.Module, class_name_needles: tuple[str, ...]
) -> Iterator[None]:
    changes: list[tuple[torch.nn.Module, Any]] = []
    for module in root.modules():
        if not any(needle in module.__class__.__name__ for needle in class_name_needles):
            continue
        native = getattr(module, "forward_native", None)
        if native is None or not hasattr(module, "_forward_method"):
            continue
        changes.append((module, module._forward_method))
        module._forward_method = native
    try:
        yield
    finally:
        for module, original in reversed(changes):
            module._forward_method = original


@contextmanager
def _temporarily_unwrap_compiled_layernorms(
    root: torch.nn.Module,
) -> Iterator[None]:
    # GemmaRMSNorm.forward_cuda lazily caches torch.compile wrappers for the
    # two static native helpers on each module instance.  Merely routing the
    # CustomOp through forward_native is therefore insufficient after model
    # warmup: forward_native still resolves the instance-level compiled
    # helpers, and make_fx rejects tracing a Dynamo-optimized function.
    #
    # Replace only those instance caches with the current class-native
    # implementations for the offline structural replay, then restore the
    # exact cached objects.  The real eager request has already returned
    # before this context is entered.
    static_changes: list[tuple[torch.nn.Module, str, Any]] = []
    for module in root.modules():
        if "RMSNorm" not in module.__class__.__name__:
            continue
        for name in (
            "_forward_static_no_residual",
            "_forward_static_with_residual",
        ):
            if name not in module.__dict__:
                continue
            class_descriptor = inspect.getattr_static(type(module), name, None)
            if isinstance(class_descriptor, staticmethod):
                replacement = class_descriptor.__func__
            else:
                replacement = getattr(type(module), name, None)
            if replacement is None:
                continue
            static_changes.append((module, name, module.__dict__[name]))
            setattr(module, name, replacement)
    try:
        with _replace_forward_methods(root, ("RMSNorm",)):
            yield
    finally:
        for module, name, original in reversed(static_changes):
            setattr(module, name, original)


@contextmanager
def _temporarily_plain_parameters(root: torch.nn.Module) -> Iterator[None]:
    changes: list[tuple[torch.nn.Module, str, torch.nn.Parameter]] = []
    for module in root.modules():
        for name, parameter in list(module._parameters.items()):
            if parameter is None or type(parameter) is torch.nn.Parameter:
                continue
            replacement = torch.nn.Parameter(
                parameter.detach(), requires_grad=parameter.requires_grad
            )
            changes.append((module, name, parameter))
            module._parameters[name] = replacement
    try:
        yield
    finally:
        for module, name, original in reversed(changes):
            module._parameters[name] = original


@contextmanager
def _temporarily_use_native_rotary(root: torch.nn.Module) -> Iterator[None]:
    with _replace_forward_methods(root, ("RotaryEmbedding",)):
        yield


@contextmanager
def _temporarily_use_native_gdn_norm(root: torch.nn.Module) -> Iterator[None]:
    from vllm.model_executor.models import qwen3_5

    original_guard = qwen3_5._can_use_qwen35_gdn_strided_z_rmsnorm
    qwen3_5._can_use_qwen35_gdn_strided_z_rmsnorm = lambda *_args: False
    try:
        with _replace_forward_methods(root, ("RMSNormGated",)):
            yield
    finally:
        qwen3_5._can_use_qwen35_gdn_strided_z_rmsnorm = original_guard


@contextmanager
def _temporarily_use_default_unquantized_gemm() -> Iterator[None]:
    from vllm.model_executor.layers import linear, utils

    original = linear.dispatch_unquantized_gemm
    linear.dispatch_unquantized_gemm = lambda: utils.default_unquantized_gemm
    try:
        yield
    finally:
        linear.dispatch_unquantized_gemm = original


def _trace_options() -> dict[str, Any]:
    return {
        "tracing_mode": "fake",
        "_allow_non_fake_inputs": True,
        "_allow_fake_constant": True,
        "record_module_stack": True,
    }


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _node_record(index: int, node: torch.fx.Node) -> dict[str, Any]:
    return {
        "index": index,
        "name": node.name,
        "op": node.op,
        "target": str(node.target),
        "args": repr(node.args),
        "kwargs": repr(node.kwargs),
        "users": [user.name for user in node.users],
        "meta": {
            "val": _describe_value(node.meta.get("val")),
            "tensor_meta": _jsonable(node.meta.get("tensor_meta")),
        },
    }


def _meta_tensor(tensor: torch.Tensor) -> torch.Tensor:
    return torch.empty_strided(
        tuple(int(item) for item in tensor.shape),
        tuple(int(item) for item in tensor.stride()),
        dtype=tensor.dtype,
        device="meta",
    )


def _strip_graph_module_tensor_storage(graph_module: torch.fx.GraphModule) -> None:
    for module in graph_module.modules():
        for name, parameter in list(module._parameters.items()):
            if parameter is None:
                continue
            module._parameters[name] = torch.nn.Parameter(
                _meta_tensor(parameter), requires_grad=parameter.requires_grad
            )
        for name, buffer in list(module._buffers.items()):
            if buffer is not None:
                module._buffers[name] = _meta_tensor(buffer)
    for node in graph_module.graph.nodes:
        node.meta.clear()


def _write_trace_outputs(
    trace_dir: Path,
    graph_module: torch.fx.GraphModule,
    metadata: Mapping[str, Any],
) -> list[str]:
    if trace_dir.exists() and any(trace_dir.iterdir()):
        return [f"refusing non-empty FX trace directory: {trace_dir}"]
    trace_dir.mkdir(parents=True, exist_ok=True)

    nodes = [
        _node_record(index, node)
        for index, node in enumerate(graph_module.graph.nodes)
    ]
    targets = [row["target"] for row in nodes]
    opaque_ops = sorted({target for target in targets if target.startswith("vllm.")})
    payload = {
        **dict(metadata),
        "node_count": len(nodes),
        "opaque_custom_ops": opaque_ops,
        "graph_module_tensor_storage": "meta_only_no_runtime_tensor_payload",
    }
    _write_text_atomic(trace_dir / "fx_graph.py", graph_module.code)
    _write_text_atomic(trace_dir / "fx_graph.txt", str(graph_module.graph) + "\n")
    _write_text_atomic(
        trace_dir / "fx_nodes.json",
        json.dumps(nodes, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _write_text_atomic(
        trace_dir / "fx_trace_metadata.json",
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )

    module_dir = trace_dir / "fx_graph_module"
    module_dir.mkdir(exist_ok=False)
    _write_text_atomic(module_dir / "graph.py", graph_module.code)
    _write_text_atomic(
        module_dir / "metadata.json",
        json.dumps(
            {"node_count": len(nodes), "tensor_storage": "meta_only"},
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )

    _strip_graph_module_tensor_storage(graph_module)
    save_path = trace_dir / "fx_graph_module.pt"
    temporary = save_path.with_name(f".{save_path.name}.{os.getpid()}.tmp")
    torch.save(graph_module, temporary)
    temporary.replace(save_path)
    return []
