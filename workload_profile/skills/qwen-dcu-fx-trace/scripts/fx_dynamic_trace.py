#!/usr/bin/env python3
"""Capture a runtime FX graph with make_fx.

This tool is intentionally separate from the TorchDispatch CSV profiler. It
uses PyTorch's official FX proxy-tensor tracing entry point to execute a Python
callable with example inputs and save a GraphModule plus normalized node JSON.
"""

from __future__ import annotations

import argparse
import csv
import inspect
import importlib
import importlib.util
import json
import math
import operator
import os
import shutil
import sys
import textwrap
import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def resolve_workload_dir() -> Path:
    env_workload = os.environ.get("VISIPRUNE_WORKLOAD_DIR")
    if env_workload:
        return Path(env_workload).expanduser().resolve()

    env_root = os.environ.get("VISIPRUNE_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve() / "workload_analysis"

    cwd = Path.cwd().resolve()
    if (cwd / "workload_analysis" / "fx").exists():
        return cwd / "workload_analysis"
    if cwd.name == "workload_analysis" and (cwd / "fx").exists():
        return cwd

    default_workload = Path("/workspace/VisiPrune/workload_analysis")
    if default_workload.exists():
        return default_workload

    return Path(__file__).resolve().parents[1]


WORKLOAD_DIR = resolve_workload_dir()
ROOT_DIR = WORKLOAD_DIR.parent
REPO_DIR = ROOT_DIR / "repo"
TRACE_SCRIPT_DIR = WORKLOAD_DIR / "algorithmic_trace/tools"
DEFAULT_TRACE = (
    WORKLOAD_DIR
    / "algorithmic_trace/traces/fresh_forward_visipruner_full_32tok/algorithmic_trace.json"
)
DEFAULT_OUTPUT_ROOT = WORKLOAD_DIR / "fx/traces"


def parse_gpu_early(argv: list[str]) -> str:
    for idx, arg in enumerate(argv):
        if arg == "--gpu" and idx + 1 < len(argv):
            return argv[idx + 1]
        if arg.startswith("--gpu="):
            return arg.split("=", 1)[1]
    return "0"


os.environ.setdefault("CUDA_VISIBLE_DEVICES", parse_gpu_early(sys.argv))
os.environ.setdefault("HF_HOME", str(ROOT_DIR / "models"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))
if str(TRACE_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(TRACE_SCRIPT_DIR))

import torch
import torch.fx as fx
from torch.fx.experimental.proxy_tensor import make_fx


def compact_json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)


def import_from_file(path: Path, attr_path: str) -> Any:
    module_name = f"_fx_dynamic_trace_target_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot import target file: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return resolve_attr(module, attr_path)


def resolve_attr(root: Any, attr_path: str) -> Any:
    value = root
    for part in attr_path.split("."):
        value = getattr(value, part)
    return value


def resolve_target(target: str) -> Any:
    if ":" not in target:
        raise ValueError("Target must use 'module:callable' or '/path/file.py:callable' syntax")
    module_part, attr_path = target.split(":", 1)
    path = Path(module_part)
    if path.suffix == ".py" or path.exists():
        return import_from_file(path.resolve(), attr_path)
    module = importlib.import_module(module_part)
    return resolve_attr(module, attr_path)


def torch_dtype(name: str) -> torch.dtype:
    normalized = name.replace("torch.", "")
    dtype = getattr(torch, normalized, None)
    if not isinstance(dtype, torch.dtype):
        raise ValueError(f"Unknown torch dtype: {name}")
    return dtype


def build_tensor(spec: Mapping[str, Any]) -> torch.Tensor:
    dtype = torch_dtype(str(spec.get("dtype", "float32")))
    device = torch.device(str(spec.get("device", "cpu")))
    requires_grad = bool(spec.get("requires_grad", False))
    if "value" in spec:
        tensor = torch.tensor(spec["value"], dtype=dtype, device=device)
    else:
        shape = [int(item) for item in spec.get("shape", [])]
        fill = str(spec.get("fill", "randn"))
        if fill == "randn":
            tensor = torch.randn(*shape, dtype=dtype, device=device)
        elif fill == "rand":
            tensor = torch.rand(*shape, dtype=dtype, device=device)
        elif fill == "zeros":
            tensor = torch.zeros(*shape, dtype=dtype, device=device)
        elif fill == "ones":
            tensor = torch.ones(*shape, dtype=dtype, device=device)
        elif fill == "arange":
            if not shape:
                raise ValueError("arange tensor specs require a shape")
            tensor = torch.arange(math.prod(shape), dtype=dtype, device=device).reshape(shape)
        else:
            raise ValueError(f"Unknown tensor fill mode: {fill}")
    if requires_grad:
        tensor.requires_grad_(True)
    return tensor


def build_value(spec: Any) -> Any:
    if isinstance(spec, Mapping):
        kind = spec.get("kind", spec.get("type"))
        if kind == "tensor" or "shape" in spec or "value" in spec and spec.get("as") == "tensor":
            return build_tensor(spec)
        if "literal" in spec:
            return spec["literal"]
        if kind == "tuple":
            return tuple(build_value(item) for item in spec.get("items", []))
        if kind == "list":
            return [build_value(item) for item in spec.get("items", [])]
        if kind == "dict":
            return {str(key): build_value(value) for key, value in spec.get("items", {}).items()}
        return {str(key): build_value(value) for key, value in spec.items()}
    if isinstance(spec, list):
        return [build_value(item) for item in spec]
    return spec


def load_input_spec(args: argparse.Namespace) -> dict[str, Any]:
    if args.input_spec and args.input_spec_file:
        raise ValueError("Use only one of --input-spec and --input-spec-file")
    if args.input_spec_file:
        return json.loads(Path(args.input_spec_file).read_text(encoding="utf-8"))
    if args.input_spec:
        return json.loads(args.input_spec)
    if args.demo:
        return {
            "args": [
                {"kind": "tensor", "shape": [2, 3], "dtype": "float32", "fill": "randn"},
                {"kind": "tensor", "shape": [2, 3], "dtype": "float32", "fill": "randn"},
            ],
            "kwargs": {},
        }
    raise ValueError("Provide --input-spec/--input-spec-file, or use --demo")


def build_inputs(spec: Mapping[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    args = tuple(build_value(item) for item in spec.get("args", []))
    kwargs = {str(key): build_value(value) for key, value in spec.get("kwargs", {}).items()}
    return args, kwargs


def demo_target(x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    z = torch.ops.aten.add.Tensor(x, y)
    z = torch.ops.aten.relu.default(z)
    return torch.ops.aten.sum.dim_IntList(z, [1], False)


def int_shape(value: Any) -> list[int] | None:
    if value is None or not hasattr(value, "shape"):
        return None
    return [int(item) for item in value.shape]


def safe_cache_len(past_key_value: Any, q_len: int, layer_idx: int) -> int:
    if past_key_value is None:
        return 0
    if hasattr(past_key_value, "get_usable_length"):
        try:
            return int(past_key_value.get_usable_length(q_len, layer_idx=layer_idx))
        except TypeError:
            return int(past_key_value.get_usable_length(q_len))
        except Exception:
            return 0
    try:
        return int(past_key_value[layer_idx][0].shape[-2])
    except Exception:
        return 0


def event_id(forward_id: int, layer_id: int) -> str:
    return f"input{forward_id}_layer{layer_id}"


def target_expr(target: Any) -> str:
    text = str(target)
    if text.startswith("aten."):
        return f"torch.ops.{text}"
    module = getattr(target, "__module__", None)
    qualname = getattr(target, "__qualname__", None)
    if module and qualname:
        if module == "builtins":
            return qualname
        return f"{module}.{qualname}"
    return repr(target)


def serialize_value(value: Any) -> Any:
    if isinstance(value, fx.Node):
        return {"node": value.name}
    if isinstance(value, tuple):
        return {"tuple": [serialize_value(item) for item in value]}
    if isinstance(value, list):
        return {"list": [serialize_value(item) for item in value]}
    if isinstance(value, dict):
        return {"dict": {str(key): serialize_value(item) for key, item in value.items()}}
    if isinstance(value, slice):
        return {
            "slice": {
                "start": serialize_value(value.start),
                "stop": serialize_value(value.stop),
                "step": serialize_value(value.step),
            }
        }
    if isinstance(value, torch.Size):
        return {"list": [int(item) for item in value]}
    if isinstance(value, torch.dtype):
        return {"torch_dtype": str(value).replace("torch.", "")}
    if isinstance(value, torch.device):
        return {"torch_device": str(value)}
    if torch.is_tensor(value):
        return {
            "tensor_literal": {
                "shape": [int(item) for item in value.shape],
                "dtype": str(value.dtype).replace("torch.", ""),
                "device": str(value.device),
            }
        }
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return {"repr": repr(value)}


def serialize_meta(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return repr(value)
    if torch.is_tensor(value):
        return {
            "type": type(value).__name__,
            "shape": [int(item) for item in value.shape],
            "dtype": str(value.dtype).replace("torch.", ""),
            "device": str(value.device),
            "requires_grad": bool(value.requires_grad),
        }
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, torch.Size):
        return [int(item) for item in value]
    if isinstance(value, torch.dtype):
        return str(value).replace("torch.", "")
    if isinstance(value, torch.device):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): serialize_meta(item, depth + 1) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [serialize_meta(item, depth + 1) for item in value]
    if hasattr(value, "_asdict"):
        return serialize_meta(value._asdict(), depth + 1)
    if hasattr(value, "__dict__"):
        return {
            "type": type(value).__name__,
            "attrs": serialize_meta(vars(value), depth + 1),
        }
    return repr(value)


def serialize_node(index: int, node: fx.Node) -> dict[str, Any]:
    return {
        "index": index,
        "name": node.name,
        "op": node.op,
        "target": str(node.target),
        "target_expr": target_expr(node.target),
        "args": serialize_value(node.args),
        "kwargs": serialize_value(dict(node.kwargs)),
        "users": sorted(user.name for user in node.users),
        "meta": serialize_meta(dict(node.meta)),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def describe_runtime_value(value: Any, depth: int = 0) -> Any:
    if torch.is_tensor(value):
        return {
            "type": "Tensor",
            "shape": [int(item) for item in value.shape],
            "dtype": str(value.dtype).replace("torch.", ""),
            "device": str(value.device),
            "requires_grad": bool(value.requires_grad),
        }
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if depth >= 3:
        return type(value).__name__
    if isinstance(value, tuple):
        return {"tuple": [describe_runtime_value(item, depth + 1) for item in value]}
    if isinstance(value, list):
        return [describe_runtime_value(item, depth + 1) for item in value]
    if isinstance(value, Mapping):
        return {str(key): describe_runtime_value(item, depth + 1) for key, item in value.items()}
    return type(value).__name__


def runtime_input_summary(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "args": describe_runtime_value(args),
        "kwargs": describe_runtime_value(kwargs),
    }


def snapshot_tensor(value: torch.Tensor) -> torch.Tensor:
    snapshot = value.detach().clone(memory_format=torch.preserve_format)
    snapshot.requires_grad_(False)
    return snapshot


def snapshot_dynamic_cache(value: Any) -> Any:
    cache = value.__class__()
    if hasattr(value, "seen_tokens"):
        cache.seen_tokens = int(value.seen_tokens)
    if hasattr(value, "key_cache") and hasattr(value, "value_cache"):
        cache.key_cache = [snapshot_runtime_value(item) for item in value.key_cache]
        cache.value_cache = [snapshot_runtime_value(item) for item in value.value_cache]
        return cache
    return value


def snapshot_runtime_value(value: Any) -> Any:
    if torch.is_tensor(value):
        return snapshot_tensor(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "key_cache") and hasattr(value, "value_cache"):
        return snapshot_dynamic_cache(value)
    if isinstance(value, tuple):
        return tuple(snapshot_runtime_value(item) for item in value)
    if isinstance(value, list):
        return [snapshot_runtime_value(item) for item in value]
    if isinstance(value, Mapping):
        return {key: snapshot_runtime_value(item) for key, item in value.items()}
    return value


def snapshot_runtime_inputs(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    return snapshot_runtime_value(args), snapshot_runtime_value(kwargs)


def make_fx_positional_call(
    orig: Any,
    call_args: tuple[Any, ...],
    call_kwargs: dict[str, Any],
) -> tuple[Any, tuple[Any, ...], dict[str, Any]]:
    """Convert runtime kwargs to positional FX inputs.

    ``make_fx`` does not accept keyword arguments on the generated wrapper in
    this PyTorch build. The inner target still calls the real layer with the
    original keyword names, so the captured computation follows the runtime
    forward call instead of a hand-written argument rule.
    """
    keyword_names = tuple(call_kwargs)
    positional_arg_count = len(call_args)
    flat_args = tuple(call_args) + tuple(call_kwargs[name] for name in keyword_names)

    def target(*flat_call_args: Any) -> Any:
        original_args = flat_call_args[:positional_arg_count]
        original_kwargs = {
            name: flat_call_args[positional_arg_count + index]
            for index, name in enumerate(keyword_names)
        }
        return orig(*original_args, **original_kwargs)

    input_binding = {
        "positional_arg_count": positional_arg_count,
        "keyword_names": list(keyword_names),
        "flat_inputs": [
            {
                "flat_index": index,
                "source": "arg",
                "source_index": index,
            }
            for index in range(positional_arg_count)
        ]
        + [
            {
                "flat_index": positional_arg_count + index,
                "source": "kwarg",
                "source_name": name,
            }
            for index, name in enumerate(keyword_names)
        ],
    }
    return target, flat_args, input_binding


def write_trace_outputs(
    out_dir: Path,
    graph_module: fx.GraphModule,
    target_name: str,
    input_spec: Mapping[str, Any],
    args: argparse.Namespace,
    input_binding: Mapping[str, Any] | None = None,
    specialization: Mapping[str, Any] | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    nodes = [serialize_node(index, node) for index, node in enumerate(graph_module.graph.nodes)]
    graph_module_dir = out_dir / "fx_graph_module"
    graph_module_pt = out_dir / "fx_graph_module.pt"
    (out_dir / "fx_graph.py").write_text(graph_module.code + "\n", encoding="utf-8")
    (out_dir / "fx_graph.txt").write_text(str(graph_module.graph) + "\n", encoding="utf-8")
    (out_dir / "fx_nodes.json").write_text(compact_json(nodes) + "\n", encoding="utf-8")
    torch.save(graph_module, graph_module_pt)
    if graph_module_dir.exists():
        shutil.rmtree(graph_module_dir)
    graph_module.to_folder(graph_module_dir, module_name="FxLayerGraphModule")
    metadata = {
        "target": target_name,
        "tracing_mode": args.tracing_mode,
        "pre_dispatch": bool(args.pre_dispatch),
        "record_module_stack": not bool(args.no_record_module_stack),
        "record_stack_traces": bool(args.record_stack_traces),
        "allow_non_fake_inputs": bool(args.allow_non_fake_inputs),
        "input_spec": input_spec,
        "input_binding": input_binding or {},
        "specialization": specialization or {},
        "node_count": len(nodes),
        "outputs": {
            "fx_graph_py": str(out_dir / "fx_graph.py"),
            "fx_graph_txt": str(out_dir / "fx_graph.txt"),
            "fx_nodes_json": str(out_dir / "fx_nodes.json"),
            "fx_graph_module_pt": str(graph_module_pt),
            "fx_graph_module_dir": str(graph_module_dir),
        },
    }
    (out_dir / "fx_trace_metadata.json").write_text(
        compact_json(metadata) + "\n",
        encoding="utf-8",
    )
    print(compact_json(metadata))


@dataclass
class LayerTargetSet:
    any_forward_layers: set[int] = field(default_factory=set)
    event_keys: set[tuple[int, int]] = field(default_factory=set)

    def matches(self, forward_id: int, layer_id: int) -> bool:
        return layer_id in self.any_forward_layers or (forward_id, layer_id) in self.event_keys


@dataclass
class LayerFxSample:
    event_id: str
    layer_id: int
    layer_forward: Any
    call_args: tuple[Any, ...]
    call_kwargs: dict[str, Any]
    layer_row: dict[str, Any]


@dataclass
class ModelFxTraceState:
    forward_id: int = 0
    current_forward_id: int | None = None
    current_phase: str | None = None
    layer_events: list[dict[str, Any]] = field(default_factory=list)
    trace_rows: list[dict[str, Any]] = field(default_factory=list)
    fx_samples: list[LayerFxSample] = field(default_factory=list)
    restore_callbacks: list[Any] = field(default_factory=list)


def parse_layer_targets(value: str) -> LayerTargetSet:
    targets = LayerTargetSet()
    if not value:
        raise ValueError("--layers cannot be empty in --model-layer-trace mode")
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if item.startswith("input") and "_layer" in item:
            left, right = item.split("_layer", 1)
            targets.event_keys.add((int(left.removeprefix("input")), int(right)))
            continue
        if ":" in item:
            forward, layer = item.split(":", 1)
            targets.event_keys.add((int(forward), int(layer)))
            continue
        targets.any_forward_layers.add(int(item))
    if not targets.any_forward_layers and not targets.event_keys:
        raise ValueError(f"No valid layer targets parsed from: {value!r}")
    return targets


def import_visipruner_runtime() -> dict[str, Any]:
    from PIL import Image
    from llava.constants import IMAGE_TOKEN_INDEX
    from llava.mm_utils import get_model_name_from_path, process_images, tokenizer_image_token
    from llava.model.builder import load_pretrained_model
    from llava.utils import disable_torch_init
    from visipruner_algorithmic_trace import (
        CONFIGS,
        DEFAULT_IMAGE_PATH,
        DEFAULT_MODEL_PATH,
        build_prompt,
    )

    return {
        "Image": Image,
        "IMAGE_TOKEN_INDEX": IMAGE_TOKEN_INDEX,
        "get_model_name_from_path": get_model_name_from_path,
        "process_images": process_images,
        "tokenizer_image_token": tokenizer_image_token,
        "load_pretrained_model": load_pretrained_model,
        "disable_torch_init": disable_torch_init,
        "CONFIGS": CONFIGS,
        "DEFAULT_IMAGE_PATH": DEFAULT_IMAGE_PATH,
        "DEFAULT_MODEL_PATH": DEFAULT_MODEL_PATH,
        "build_prompt": build_prompt,
    }


def make_layer_fx_tracer(args: argparse.Namespace):
    def trace_layer(
        orig: Any,
        call_args: tuple[Any, ...],
        call_kwargs: dict[str, Any],
    ) -> tuple[fx.GraphModule, tuple[Any, ...], dict[str, Any]]:
        target, flat_args, input_binding = make_fx_positional_call(orig, call_args, call_kwargs)
        traced_fn = make_fx(
            target,
            tracing_mode=args.tracing_mode,
            pre_dispatch=args.pre_dispatch,
            record_module_stack=not args.no_record_module_stack,
            record_stack_traces=args.record_stack_traces,
            _allow_non_fake_inputs=args.allow_non_fake_inputs,
        )
        return traced_fn(*flat_args), flat_args, input_binding

    return trace_layer


def get_layer_from_forward(layer_forward: Any) -> Any | None:
    return getattr(layer_forward, "__self__", None)


def get_position_ids_from_inputs(
    call_args: tuple[Any, ...],
    call_kwargs: dict[str, Any],
) -> torch.Tensor | None:
    position_ids = call_kwargs.get("position_ids")
    if position_ids is None and len(call_args) > 2:
        position_ids = call_args[2]
    return position_ids if torch.is_tensor(position_ids) else None


def position_last_plus_one(
    call_args: tuple[Any, ...],
    call_kwargs: dict[str, Any],
) -> int | None:
    position_ids = get_position_ids_from_inputs(call_args, call_kwargs)
    if position_ids is None or position_ids.numel() == 0:
        return None
    return int(position_ids[0, -1].detach().item()) + 1


def fixed_input_shape_values(
    call_args: tuple[Any, ...],
    call_kwargs: dict[str, Any],
) -> dict[str, int] | None:
    hidden_states = call_kwargs.get("hidden_states")
    if hidden_states is None and call_args:
        hidden_states = call_args[0]
    if not torch.is_tensor(hidden_states) or hidden_states.dim() < 2:
        return None
    return {
        "batch_size": int(hidden_states.shape[0]),
        "q_len": int(hidden_states.shape[1]),
    }


def specialize_attention_forward(
    attn: Any,
    position_value: int | None,
    shape_values: Mapping[str, int] | None,
) -> tuple[Any, dict[str, Any]]:
    if position_value is None:
        return attn.forward, {"enabled": False, "reason": "missing_position_ids"}
    source = textwrap.dedent(inspect.getsource(attn.forward.__func__))
    replacements = {
        "position_ids[0,-1]+1": "__fx_position_last_plus_one",
        "position_ids[0, -1] + 1": "__fx_position_last_plus_one",
        "bsz, q_len, _ = hidden_states.size()": (
            "bsz, q_len, _ = hidden_states.size()\n"
            "    bsz = __fx_batch_size\n"
            "    q_len = __fx_q_len"
        ),
    }
    patched_source = source
    replacement_count = 0
    for old, new in replacements.items():
        count = patched_source.count(old)
        replacement_count += count
        patched_source = patched_source.replace(old, new)
    namespace = dict(attn.forward.__func__.__globals__)
    namespace["__fx_position_last_plus_one"] = position_value
    namespace["__fx_batch_size"] = int(shape_values["batch_size"]) if shape_values else None
    namespace["__fx_q_len"] = int(shape_values["q_len"]) if shape_values else None
    exec(compile(patched_source, "<fx_specialized_attention_forward>", "exec"), namespace)
    specialized_forward = types.MethodType(namespace["forward"], attn)
    metadata = {
        "enabled": True,
        "kind": "position_ids_last_plus_one",
        "position_last_plus_one": position_value,
        "fixed_shape_values": dict(shape_values or {}),
        "source_function": f"{attn.__class__.__module__}.{attn.__class__.__qualname__}.forward",
        "replacement_count": replacement_count,
    }
    return specialized_forward, metadata


def make_recording_value_aware_selection(records: list[dict[str, Any]]):
    def value_aware_token_selection(
        self: Any,
        value_states: torch.Tensor,
        attn_output: torch.Tensor,
        attn_weights: torch.Tensor,
        important_vis_tokens: torch.Tensor | None = None,
    ) -> Any:
        attn_output_last = attn_output[:, -1, :]
        attn_weights_last = attn_weights[:, :, -1, :]
        batch_size, _, seq_len, _ = value_states.size()
        contributions = attn_weights_last[:, :, :, None] * value_states
        contributions = contributions.permute(0, 2, 1, 3).contiguous()
        contributions = contributions.view(batch_size, seq_len, -1)

        if important_vis_tokens is None:
            vision_contributions = contributions[:, 35:self.vis_end_index, :]
            masked_attn_output_last = attn_output_last[:, None, :] - vision_contributions
            cos_sim = torch.nn.functional.cosine_similarity(
                masked_attn_output_last,
                attn_output_last[:, None, :],
                dim=-1,
            ).squeeze(0)
            decision = bool(torch.any(cos_sim < self.layer_threshold).item())
            records.append(
                {
                    "call_index": len(records),
                    "case": "select",
                    "decision": decision,
                    "threshold": float(self.layer_threshold),
                    "vis_end_index": int(self.vis_end_index),
                }
            )
            selected_tokens = None
            if decision:
                l_2 = torch.norm(
                    masked_attn_output_last - attn_output_last[:, None, :],
                    p=2,
                    dim=-1,
                ).squeeze(0)
                selected_tokens = torch.where(l_2 > self.tokens_threshold)[0] + 35
            return selected_tokens

        offset_tokens_index = torch.arange(
            35,
            35 + important_vis_tokens.shape[0],
            device=important_vis_tokens.device,
        )
        vision_contributions = contributions[:, offset_tokens_index, :]
        masked_attn_output_last = attn_output_last[:, None, :] - vision_contributions
        cos_sim = torch.nn.functional.cosine_similarity(
            masked_attn_output_last,
            attn_output_last[:, None, :],
            dim=-1,
        ).squeeze(0)
        decision = bool(torch.any(cos_sim < 0.999).item())
        records.append(
            {
                "call_index": len(records),
                "case": "verify",
                "decision": decision,
                "threshold": 0.999,
                "important_vis_token_count": int(important_vis_tokens.shape[0]),
            }
        )
        return False if decision else True

    return value_aware_token_selection


def make_replay_value_aware_selection(records: list[dict[str, Any]]):
    replay_state = {"index": 0}

    def value_aware_token_selection(
        self: Any,
        value_states: torch.Tensor,
        attn_output: torch.Tensor,
        attn_weights: torch.Tensor,
        important_vis_tokens: torch.Tensor | None = None,
    ) -> Any:
        if replay_state["index"] >= len(records):
            raise RuntimeError("No recorded value_aware_token_selection branch is available for replay")
        record = records[replay_state["index"]]
        replay_state["index"] += 1

        attn_output_last = attn_output[:, -1, :]
        attn_weights_last = attn_weights[:, :, -1, :]
        batch_size, _, seq_len, _ = value_states.size()
        contributions = attn_weights_last[:, :, :, None] * value_states
        contributions = contributions.permute(0, 2, 1, 3).contiguous()
        contributions = contributions.view(batch_size, seq_len, -1)

        if important_vis_tokens is None:
            if record["case"] != "select":
                raise RuntimeError(f"Expected select replay record, got {record['case']}")
            vision_contributions = contributions[:, 35:self.vis_end_index, :]
            masked_attn_output_last = attn_output_last[:, None, :] - vision_contributions
            if bool(record["decision"]):
                l_2 = torch.norm(
                    masked_attn_output_last - attn_output_last[:, None, :],
                    p=2,
                    dim=-1,
                ).squeeze(0)
                return torch.where(l_2 > self.tokens_threshold)[0] + 35
            return None

        if record["case"] != "verify":
            raise RuntimeError(f"Expected verify replay record, got {record['case']}")
        offset_tokens_index = torch.arange(
            35,
            35 + important_vis_tokens.shape[0],
            device=important_vis_tokens.device,
        )
        vision_contributions = contributions[:, offset_tokens_index, :]
        masked_attn_output_last = attn_output_last[:, None, :] - vision_contributions
        _ = masked_attn_output_last
        return False if bool(record["decision"]) else True

    return value_aware_token_selection


def run_with_specialized_attention(
    sample: "LayerFxSample",
    args_for_call: tuple[Any, ...],
    kwargs_for_call: dict[str, Any],
    value_aware_mode: str,
    value_aware_records: list[dict[str, Any]] | None = None,
    position_value: int | None = None,
    constant_attr_values: Mapping[str, int] | None = None,
) -> tuple[Any, dict[str, Any]]:
    layer = get_layer_from_forward(sample.layer_forward)
    attn = getattr(layer, "self_attn", None) if layer is not None else None
    if attn is None:
        return sample.layer_forward(*args_for_call, **kwargs_for_call), {
            "attention_forward": {"enabled": False, "reason": "missing_self_attn"}
        }

    if position_value is None:
        position_value = position_last_plus_one(args_for_call, kwargs_for_call)
    shape_values = fixed_input_shape_values(args_for_call, kwargs_for_call)
    specialized_forward, forward_metadata = specialize_attention_forward(
        attn,
        position_value,
        shape_values,
    )
    original_forward = attn.forward
    original_value_aware = getattr(attn, "value_aware_token_selection", None)
    original_constant_attrs: dict[str, Any] = {}
    constant_attr_metadata: dict[str, Any] = {}
    for attr_name in ("num_images", "vis_end_index", "vis_half_index"):
        if hasattr(attn, attr_name):
            attr_value = getattr(attn, attr_name)
            if constant_attr_values is not None and attr_name in constant_attr_values:
                original_constant_attrs[attr_name] = attr_value
                int_value = int(constant_attr_values[attr_name])
                setattr(attn, attr_name, int_value)
                constant_attr_metadata[attr_name] = int_value
            elif torch.is_tensor(attr_value) and attr_value.numel() == 1:
                original_constant_attrs[attr_name] = attr_value
                int_value = int(attr_value.detach().item())
                setattr(attn, attr_name, int_value)
                constant_attr_metadata[attr_name] = int_value
    records = value_aware_records if value_aware_records is not None else []
    if value_aware_mode == "record":
        value_aware = types.MethodType(make_recording_value_aware_selection(records), attn)
    elif value_aware_mode == "replay":
        value_aware = types.MethodType(make_replay_value_aware_selection(records), attn)
    else:
        value_aware = original_value_aware

    attn.forward = specialized_forward
    if value_aware is not None:
        attn.value_aware_token_selection = value_aware
    try:
        output = sample.layer_forward(*args_for_call, **kwargs_for_call)
    finally:
        attn.forward = original_forward
        if original_value_aware is not None:
            attn.value_aware_token_selection = original_value_aware
        for attr_name, attr_value in original_constant_attrs.items():
            setattr(attn, attr_name, attr_value)

    return output, {
        "attention_forward": forward_metadata,
        "constant_module_attrs": constant_attr_metadata,
        "value_aware_token_selection": {
            "mode": value_aware_mode,
            "record_count": len(records),
            "records": records,
        },
    }


def collect_fx_specialization(sample: "LayerFxSample") -> dict[str, Any]:
    dry_args, dry_kwargs = snapshot_runtime_inputs(sample.call_args, sample.call_kwargs)
    records: list[dict[str, Any]] = []
    with torch.inference_mode():
        _, metadata = run_with_specialized_attention(
            sample,
            dry_args,
            dry_kwargs,
            value_aware_mode="record",
            value_aware_records=records,
        )
    metadata["strategy"] = "analysis_only_runtime_input_specialization"
    return metadata


def normalize_fx_output(value: Any, layer_id: int) -> Any:
    if torch.is_tensor(value) or value is None or isinstance(value, (bool, int, float)):
        return value
    if hasattr(value, "key_cache") and hasattr(value, "value_cache"):
        if layer_id < len(value.key_cache):
            return {
                "dynamic_cache_layer": (
                    value.key_cache[layer_id],
                    value.value_cache[layer_id],
                )
            }
        return {"dynamic_cache_layer": None}
    if isinstance(value, tuple):
        return tuple(normalize_fx_output(item, layer_id) for item in value)
    if isinstance(value, list):
        return [normalize_fx_output(item, layer_id) for item in value]
    if isinstance(value, Mapping):
        return {key: normalize_fx_output(item, layer_id) for key, item in value.items()}
    return None


def wrap_model_for_selected_layer_fx(
    model: Any,
    state: ModelFxTraceState,
    targets: LayerTargetSet,
) -> None:
    original_forward = model.forward

    def wrapped_model_forward(*call_args: Any, **call_kwargs: Any) -> Any:
        input_ids = call_kwargs.get("input_ids")
        inputs_embeds = call_kwargs.get("inputs_embeds")
        if input_ids is None and call_args:
            input_ids = call_args[0]
        if inputs_embeds is not None:
            seq_len = int(inputs_embeds.shape[1])
        elif input_ids is not None:
            seq_len = int(input_ids.shape[1])
        else:
            seq_len = -1

        state.forward_id += 1
        previous_forward_id = state.current_forward_id
        previous_phase = state.current_phase
        state.current_forward_id = state.forward_id
        state.current_phase = "prefill" if seq_len > 1 else "decode"
        try:
            return original_forward(*call_args, **call_kwargs)
        finally:
            state.current_forward_id = previous_forward_id
            state.current_phase = previous_phase

    model.forward = wrapped_model_forward
    state.restore_callbacks.append(lambda: setattr(model, "forward", original_forward))

    base_model = model.get_model()
    for layer_idx, layer in enumerate(base_model.layers):
        original_layer_forward = layer.forward

        def make_wrapped_layer(orig: Any, idx: int):
            def wrapped_layer(*call_args: Any, **call_kwargs: Any) -> Any:
                hidden_states = call_kwargs.get("hidden_states")
                if hidden_states is None and call_args:
                    hidden_states = call_args[0]
                position_ids = call_kwargs.get("position_ids")
                past_key_value = call_kwargs.get("past_key_value")
                if hidden_states is None:
                    return orig(*call_args, **call_kwargs)

                q_len = int(hidden_states.shape[1])
                past_len = safe_cache_len(past_key_value, q_len, idx)
                forward_id = int(state.current_forward_id or -1)
                phase = state.current_phase or ("prefill" if q_len > 1 else "decode")
                event_key = event_id(forward_id, idx)
                matched = targets.matches(forward_id, idx)
                layer_row = {
                    "event_id": event_key,
                    "forward_id": forward_id,
                    "layer_id": idx,
                    "phase": phase,
                    "q_len": q_len,
                    "past_len": past_len,
                    "kv_len": past_len + q_len,
                    "hidden_shape_in": json.dumps(int_shape(hidden_states)),
                    "position_shape": json.dumps(int_shape(position_ids)),
                    "fx_sampled": matched,
                    "fx_traced": False,
                }

                sample = None
                if matched:
                    sample_args, sample_kwargs = snapshot_runtime_inputs(call_args, call_kwargs)
                    sample = LayerFxSample(
                        event_id=event_key,
                        layer_id=idx,
                        layer_forward=orig,
                        call_args=sample_args,
                        call_kwargs=sample_kwargs,
                        layer_row=layer_row,
                    )
                    state.fx_samples.append(sample)

                output = orig(*call_args, **call_kwargs)
                if isinstance(output, tuple) and output:
                    layer_row["hidden_shape_out"] = json.dumps(int_shape(output[0]))
                    if sample is not None:
                        sample.layer_row["hidden_shape_out"] = layer_row["hidden_shape_out"]
                state.layer_events.append(layer_row)
                return output

            return wrapped_layer

        layer.forward = make_wrapped_layer(original_layer_forward, layer_idx)
        state.restore_callbacks.append(
            lambda layer=layer, original_layer_forward=original_layer_forward: setattr(
                layer,
                "forward",
                original_layer_forward,
            )
        )


def restore_wrapped_forwards(state: ModelFxTraceState) -> None:
    while state.restore_callbacks:
        callback = state.restore_callbacks.pop()
        callback()


def run_offline_layer_fx_traces(
    state: ModelFxTraceState,
    out_dir: Path,
    args: argparse.Namespace,
) -> None:
    layer_tracer = make_layer_fx_tracer(args)
    for sample in state.fx_samples:
        trace_dir = out_dir / sample.event_id
        trace_row = dict(sample.layer_row)
        trace_row["trace_dir"] = str(trace_dir)
        try:
            specialization = collect_fx_specialization(sample)
            position_value = specialization.get("attention_forward", {}).get("position_last_plus_one")
            value_aware_records = specialization.get("value_aware_token_selection", {}).get("records", [])
            constant_attr_values = specialization.get("constant_module_attrs", {})

            def specialized_layer_forward(*call_args: Any, **call_kwargs: Any) -> Any:
                output, _metadata = run_with_specialized_attention(
                    sample,
                    call_args,
                    call_kwargs,
                    value_aware_mode="replay",
                    value_aware_records=value_aware_records,
                    position_value=position_value,
                    constant_attr_values=constant_attr_values,
                )
                return normalize_fx_output(output, sample.layer_id)

            specialization["output_normalization"] = {
                "enabled": True,
                "dynamic_cache": "return_current_layer_key_value_tensors",
            }

            with torch.inference_mode():
                graph_module, _flat_args, input_binding = layer_tracer(
                    specialized_layer_forward,
                    sample.call_args,
                    sample.call_kwargs,
                )
            write_trace_outputs(
                trace_dir,
                graph_module,
                f"{sample.event_id}:layer{sample.layer_id}.forward",
                runtime_input_summary(sample.call_args, sample.call_kwargs),
                args,
                input_binding,
                specialization,
            )
            trace_row["status"] = "ok"
            trace_row["fx_traced"] = True
            trace_row["fx_trace_status"] = "ok"
            trace_row["node_count"] = len(list(graph_module.graph.nodes))
            trace_row["specialization"] = json.dumps(specialization, ensure_ascii=False, sort_keys=True)
            sample.layer_row["fx_traced"] = True
            sample.layer_row["fx_trace_status"] = "ok"
            sample.layer_row["fx_node_count"] = trace_row["node_count"]
            sample.layer_row["fx_specialization"] = trace_row["specialization"]
        except Exception as exc:
            trace_row["status"] = "error"
            trace_row["fx_traced"] = False
            trace_row["fx_trace_status"] = "error"
            trace_row["error"] = repr(exc)
            trace_row["fx_trace_error"] = trace_row["error"]
            sample.layer_row["fx_traced"] = False
            sample.layer_row["fx_trace_status"] = "error"
            sample.layer_row["fx_trace_error"] = trace_row["error"]
            state.trace_rows.append(trace_row)
            if args.strict_layer_trace:
                raise
            continue
        state.trace_rows.append(trace_row)


def run_model_layer_trace(args: argparse.Namespace) -> None:
    runtime = import_visipruner_runtime()
    trace_payload = {}
    trace_path = Path(args.trace)
    if trace_path.exists():
        trace_payload = json.loads(trace_path.read_text(encoding="utf-8"))

    config_name = args.config or trace_payload.get("config") or "visipruner-full"
    configs = runtime["CONFIGS"]
    if config_name not in configs:
        raise ValueError(f"Unknown config: {config_name}")
    cfg = configs[config_name]
    model_path = args.model_path or trace_payload.get("model_path") or runtime["DEFAULT_MODEL_PATH"]
    image_path = args.image_path or trace_payload.get("image_path") or runtime["DEFAULT_IMAGE_PATH"]
    prompt = args.prompt or trace_payload.get("prompt") or "Describe the image briefly."
    conv_mode = args.conv_mode or trace_payload.get("conv_mode") or "llava_v1"
    max_new_tokens = int(args.max_new_tokens or trace_payload.get("max_new_tokens") or 32)
    tag = args.tag or f"fx_layer_trace_{config_name}_{max_new_tokens}tok_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    out_dir = Path(args.output_dir) / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = parse_layer_targets(args.layers or "")
    runtime["disable_torch_init"]()
    model_name = runtime["get_model_name_from_path"](model_path)
    tokenizer, model, image_processor, context_len = runtime["load_pretrained_model"](
        model_path,
        args.model_base,
        model_name,
        device_map="cuda:0",
        use_flash_attn=cfg["use_flash_attn"],
        use_visipruner=cfg["use_visipruner"],
    )
    model.eval()

    state = ModelFxTraceState()
    wrap_model_for_selected_layer_fx(model, state, targets)

    prompt_text = runtime["build_prompt"](prompt, conv_mode)
    input_ids = runtime["tokenizer_image_token"](
        prompt_text,
        tokenizer,
        runtime["IMAGE_TOKEN_INDEX"],
        return_tensors="pt",
    ).unsqueeze(0)
    attention_mask = torch.ones_like(input_ids, dtype=torch.long)
    image = runtime["Image"].open(image_path).convert("RGB")
    image_size = image.size
    image_tensor = runtime["process_images"]([image], image_processor, model.config)
    if isinstance(image_tensor, list):
        image_tensor = image_tensor[0]
    input_ids = input_ids.to(device="cuda", non_blocking=True)
    attention_mask = attention_mask.to(device="cuda", non_blocking=True)
    image_tensor = image_tensor.to(dtype=torch.float16, device="cuda", non_blocking=True)

    try:
        with torch.inference_mode():
            output_ids = model.generate(
                input_ids,
                attention_mask=attention_mask,
                images=image_tensor,
                image_sizes=[image_size],
                do_sample=args.temperature > 0,
                temperature=args.temperature,
                max_new_tokens=max_new_tokens,
                pruning_config=cfg["pruning_config"],
                use_cache=True,
            )
    finally:
        restore_wrapped_forwards(state)
    if torch.cuda.is_available():
        torch.cuda.synchronize()

    run_offline_layer_fx_traces(state, out_dir, args)
    if torch.cuda.is_available():
        torch.cuda.synchronize()

    output_token_ids = output_ids[0, input_ids.shape[1]:] if output_ids.shape[1] > input_ids.shape[1] else output_ids[0]
    output_text = tokenizer.decode(output_token_ids, skip_special_tokens=True).strip()
    write_csv(out_dir / "fx_layer_events.csv", state.layer_events)
    write_csv(out_dir / "fx_layer_trace_manifest.csv", state.trace_rows)
    metadata = {
        "analysis_type": "visipruner_selected_layer_fx_trace",
        "trace_strategy": "runtime_sample_then_offline_make_fx",
        "trace": str(trace_path),
        "config": config_name,
        "layers": args.layers,
        "target_any_forward_layers": sorted(targets.any_forward_layers),
        "target_event_keys": [event_id(forward, layer) for forward, layer in sorted(targets.event_keys)],
        "layer_trace_continue_with": "eager",
        "strict_layer_trace": bool(args.strict_layer_trace),
        "tracing_mode": args.tracing_mode,
        "pre_dispatch": bool(args.pre_dispatch),
        "record_module_stack": not bool(args.no_record_module_stack),
        "record_stack_traces": bool(args.record_stack_traces),
        "model_path": model_path,
        "image_path": image_path,
        "prompt": prompt,
        "conv_mode": conv_mode,
        "max_new_tokens": max_new_tokens,
        "context_len": context_len,
        "observed_layer_event_count": len(state.layer_events),
        "fx_sample_count": len(state.fx_samples),
        "fx_trace_count": len([row for row in state.trace_rows if row.get("status") == "ok"]),
        "fx_trace_error_count": len([row for row in state.trace_rows if row.get("status") == "error"]),
        "output_token_count": int(output_token_ids.numel()),
        "output_text": output_text,
        "outputs": {
            "fx_layer_events": str(out_dir / "fx_layer_events.csv"),
            "fx_layer_trace_manifest": str(out_dir / "fx_layer_trace_manifest.csv"),
        },
    }
    (out_dir / "run_metadata.json").write_text(compact_json(metadata) + "\n", encoding="utf-8")
    print(compact_json(metadata))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", help="Callable as 'module:attr' or '/path/file.py:attr'.")
    parser.add_argument("--demo", action="store_true", help="Trace a built-in demo tensor function.")
    parser.add_argument("--model-layer-trace", action="store_true", help="Run a VisiPrune generate request and make_fx only selected decoder layers.")
    parser.add_argument("--layers", help="Comma-separated layer targets. Use '0,5' for all forwards of layers, or 'input1_layer5'/'1:5' for one event.")
    parser.add_argument("--input-spec", help="JSON input spec with args/kwargs.")
    parser.add_argument("--input-spec-file", help="Path to JSON input spec with args/kwargs.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_ROOT), help="Output root directory.")
    parser.add_argument("--tag", default="fx_dynamic_trace", help="Output subdirectory name.")
    parser.add_argument("--python-path", action="append", default=[], help="Extra path to prepend to sys.path.")
    parser.add_argument("--trace", default=str(DEFAULT_TRACE), help="Optional Algorithmic Trace JSON used to inherit config/request defaults.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--model-base", default=None)
    parser.add_argument("--image-path", default=None)
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--conv-mode", default=None)
    parser.add_argument("--max-new-tokens", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--gpu", default="0")
    parser.add_argument("--layer-trace-continue-with", choices=["eager", "graph"], default="eager", help="Deprecated compatibility flag. Runtime generation always continues with eager output; make_fx runs offline after sampling.")
    parser.add_argument("--strict-layer-trace", action="store_true", help="Raise immediately if a selected layer FX trace fails.")
    parser.add_argument("--tracing-mode", choices=["real", "fake", "symbolic"], default="real")
    parser.add_argument("--pre-dispatch", action="store_true")
    parser.add_argument("--allow-non-fake-inputs", action="store_true")
    parser.add_argument("--no-record-module-stack", action="store_true")
    parser.add_argument("--record-stack-traces", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for path in reversed(args.python_path):
        sys.path.insert(0, path)
    torch.manual_seed(args.seed)
    if args.model_layer_trace:
        run_model_layer_trace(args)
        return

    input_spec = load_input_spec(args)
    call_args, call_kwargs = build_inputs(input_spec)
    if args.demo:
        target = demo_target
        target_name = "demo_target"
    elif args.target:
        target = resolve_target(args.target)
        target_name = args.target
    else:
        raise ValueError("Provide --target or --demo")

    traced_fn = make_fx(
        target,
        tracing_mode=args.tracing_mode,
        pre_dispatch=args.pre_dispatch,
        record_module_stack=not args.no_record_module_stack,
        record_stack_traces=args.record_stack_traces,
        _allow_non_fake_inputs=args.allow_non_fake_inputs,
    )
    graph_module = traced_fn(*call_args, **call_kwargs)
    out_dir = Path(args.output_dir) / args.tag
    write_trace_outputs(out_dir, graph_module, target_name, input_spec, args)


if __name__ == "__main__":
    main()
