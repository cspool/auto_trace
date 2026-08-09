#!/usr/bin/env python3
"""Reconstruct Qwen3.5 fixed-input FX processes for runtime Goal R042.

The tool consumes the capture-time ``fx_nodes.json`` snapshots produced by
R032.  Those snapshots were serialized directly from ``GraphModule.graph``
before parameter storage was replaced with meta tensors.  Reconstruction is
structural: it never executes the FX graph and never attempts to inspect the
internals of opaque vLLM/DCU custom operations.

Only rule-derived process artifacts are generated here.  Human explanations
and tensor-axis diagrams belong in the separate per-event
``fx_process_visualization.md`` companions.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1

STAGE_ORDER = [
    "inputs",
    "input_rmsnorm",
    "qkv_projection",
    "rope",
    "kv_cache_attention",
    "attention_output",
    "gdn_recurrent_core",
    "gdn_gated_rmsnorm",
    "output_projection",
    "post_attention_rmsnorm",
    "mlp",
    "layer_output",
]

STAGE_TITLES = {
    "inputs": "Runtime FX inputs",
    "input_rmsnorm": "Input RMSNorm",
    "qkv_projection": "Attention/GDN input projections and head reshape",
    "rope": "RoPE position embedding",
    "kv_cache_attention": "KV-cache update and unified full attention",
    "attention_output": "Attention output gate and hidden reshape",
    "gdn_recurrent_core": "Gated DeltaNet recurrent core",
    "gdn_gated_rmsnorm": "Gated DeltaNet output RMSNorm and SiLU gate",
    "output_projection": "Mixer output projection and residual",
    "post_attention_rmsnorm": "Post-attention RMSNorm",
    "mlp": "Gated MLP projections",
    "layer_output": "Layer output",
}

STAGE_RULES = {
    "inputs": "contiguous placeholder prefix",
    "input_rmsnorm": (
        "nodes after placeholders through the node before the first mixer "
        "projection weight"
    ),
    "qkv_projection": (
        "first mixer projection weight through the node before the family "
        "landmark (RoPE table or GDN custom op)"
    ),
    "rope": (
        "position-indexed rotary table lookup and observed Q/K rotary "
        "arithmetic through the node before attention output allocation"
    ),
    "kv_cache_attention": (
        "attention output allocation/views, opaque KV-cache update, and "
        "opaque unified attention call"
    ),
    "attention_output": (
        "opaque attention output view followed by observed sigmoid output "
        "gate multiplication"
    ),
    "gdn_recurrent_core": "single opaque vllm.gdn_attention_core call",
    "gdn_gated_rmsnorm": (
        "observed core-output reshape, RMS normalization, SiLU Z gate, and "
        "head merge before the mixer output projection"
    ),
    "output_projection": (
        "mixer output projection weight through output-buffer copy and "
        "observed residual add"
    ),
    "post_attention_rmsnorm": (
        "nodes after mixer residual add through the normalized MLP input"
    ),
    "mlp": (
        "gate/up projection weight, fused SiLU-product boundary, and down "
        "projection through the node before graph output"
    ),
    "layer_output": "single FX output node",
}

REQUIRED_EVENT_FILES = (
    "fx_graph.py",
    "fx_graph.txt",
    "fx_graph_module.pt",
    "fx_nodes.json",
    "fx_trace_metadata.json",
)

GENERATED_EVENT_FILES = (
    "fx_process_reconstruction.json",
    "fx_process_reconstruction.md",
    "fx_process_nodes.csv",
)

GENERATED_ROOT_FILES = (
    "fx_process_reconstruction_manifest.json",
    "fx_process_reconstruction_manifest.csv",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r032-handoff", type=Path, required=True)
    parser.add_argument("--fx-root", type=Path, required=True)
    parser.add_argument("--logical-run-id", required=True)
    parser.add_argument("--runtime-goal", default="R042")
    parser.add_argument("--source-goal", default="R032")
    parser.add_argument("--capture-run-id")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path, role: str) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "role": role,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def write_json_atomic(path: Path, payload: Any) -> None:
    write_text_atomic(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_shape(raw: dict[str, Any]) -> list[int] | None:
    meta = raw.get("meta")
    if not isinstance(meta, dict):
        return None
    value = meta.get("val")
    if isinstance(value, dict) and isinstance(value.get("shape"), list):
        return [int(item) for item in value["shape"]]
    tensor_meta = meta.get("tensor_meta")
    if (
        isinstance(tensor_meta, list)
        and tensor_meta
        and isinstance(tensor_meta[0], list)
    ):
        return [int(item) for item in tensor_meta[0]]
    return None


def normalized_dtype(raw: dict[str, Any]) -> str | None:
    meta = raw.get("meta")
    if not isinstance(meta, dict):
        return None
    value = meta.get("val")
    if isinstance(value, dict) and value.get("dtype"):
        return str(value["dtype"]).removeprefix("torch.")
    tensor_meta = meta.get("tensor_meta")
    if isinstance(tensor_meta, list) and len(tensor_meta) > 1:
        return str(tensor_meta[1]).removeprefix("torch.")
    return None


def normalize_nodes(raw_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not raw_nodes:
        raise ValueError("fx_nodes.json is empty")
    indices = [int(row["index"]) for row in raw_nodes]
    if indices != list(range(len(raw_nodes))):
        raise ValueError(f"FX node indices are not contiguous: {indices[:8]}...")

    names = [str(row["name"]) for row in raw_nodes]
    if len(names) != len(set(names)):
        raise ValueError("FX node names are not unique")
    name_set = set(names)
    incoming: dict[str, list[str]] = {name: [] for name in names}
    for raw in raw_nodes:
        source = str(raw["name"])
        users = [str(item) for item in raw.get("users", [])]
        unknown = sorted(set(users) - name_set)
        if unknown:
            raise ValueError(f"node {source} has unknown users: {unknown}")
        for user in users:
            incoming[user].append(source)

    nodes: list[dict[str, Any]] = []
    for raw in raw_nodes:
        name = str(raw["name"])
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
        value = meta.get("val") if isinstance(meta.get("val"), dict) else {}
        nodes.append(
            {
                "index": int(raw["index"]),
                "name": name,
                "op": str(raw["op"]),
                "target": str(raw["target"]),
                "args": incoming[name],
                "args_repr": str(raw.get("args", "")),
                "kwargs_repr": str(raw.get("kwargs", "")),
                "users": [str(item) for item in raw.get("users", [])],
                "shape": normalized_shape(raw),
                "dtype": normalized_dtype(raw),
                "device": value.get("device"),
            }
        )
    return nodes


def first_target_after(
    nodes: list[dict[str, Any]], start: int, target: str
) -> int:
    for row in nodes[start:]:
        if row["target"] == target:
            return int(row["index"])
    raise ValueError(f"missing target {target!r} after index {start}")


def weight_start(
    nodes: list[dict[str, Any]], by_name: dict[str, dict[str, Any]], mm_index: int
) -> int:
    mm = nodes[mm_index]
    if len(mm["args"]) < 2:
        raise ValueError(f"mm node {mm['name']} lacks a weight dependency")
    weight = by_name[mm["args"][1]]
    if weight["target"] == "aten.t.default":
        if len(weight["args"]) != 1:
            raise ValueError(f"transpose node {weight['name']} is ambiguous")
        parameter = by_name[weight["args"][0]]
        if parameter["op"] != "get_attr":
            raise ValueError(f"weight source {parameter['name']} is not get_attr")
        return int(parameter["index"])
    if weight["op"] == "get_attr":
        return int(weight["index"])
    raise ValueError(f"cannot resolve weight start for {mm['name']}")


def build_ranges(
    nodes: list[dict[str, Any]], layer_type: str
) -> tuple[dict[str, tuple[int, int]], str]:
    by_name = {row["name"]: row for row in nodes}
    placeholders = [row["index"] for row in nodes if row["op"] == "placeholder"]
    outputs = [row["index"] for row in nodes if row["op"] == "output"]
    mm_indices = [
        row["index"] for row in nodes if row["target"] == "aten.mm.default"
    ]
    gdn = [
        row["index"]
        for row in nodes
        if row["target"] == "vllm.gdn_attention_core.default"
    ]
    cache_update = [
        row["index"]
        for row in nodes
        if row["target"] == "vllm.unified_kv_cache_update.default"
    ]
    unified = [
        row["index"]
        for row in nodes
        if row["target"] == "vllm.unified_attention_with_output.default"
    ]
    if placeholders != list(range(len(placeholders))) or len(outputs) != 1:
        raise ValueError("graph must have a contiguous placeholder prefix and one output")
    output_index = outputs[0]
    if output_index != len(nodes) - 1:
        raise ValueError("FX output node is not last")
    norm_start = placeholders[-1] + 1

    if layer_type == "linear_attention":
        if len(gdn) != 1 or cache_update or unified or len(mm_indices) != 5:
            raise ValueError(
                "linear-attention landmarks differ from the observed R032 schema"
            )
        gdn_index = gdn[0]
        qkv_start = weight_start(nodes, by_name, mm_indices[0])
        output_start = weight_start(nodes, by_name, mm_indices[2])
        mlp_start = weight_start(nodes, by_name, mm_indices[3])
        residual_add = first_target_after(
            nodes, mm_indices[2] + 1, "aten.add.Tensor"
        )
        ranges = {
            "inputs": (placeholders[0], placeholders[-1]),
            "input_rmsnorm": (norm_start, qkv_start - 1),
            "qkv_projection": (qkv_start, gdn_index - 1),
            "gdn_recurrent_core": (gdn_index, gdn_index),
            "gdn_gated_rmsnorm": (gdn_index + 1, output_start - 1),
            "output_projection": (output_start, residual_add),
            "post_attention_rmsnorm": (residual_add + 1, mlp_start - 1),
            "mlp": (mlp_start, output_index - 1),
            "layer_output": (output_index, output_index),
        }
        rule = "qwen35_linear_gdn_landmarks_v1"
    elif layer_type == "full_attention":
        if gdn or len(cache_update) != 1 or len(unified) != 1 or len(mm_indices) != 4:
            raise ValueError(
                "full-attention landmarks differ from the observed R032 schema"
            )
        unified_index = unified[0]
        if cache_update[0] != unified_index - 1:
            raise ValueError("KV-cache update is not adjacent to unified attention")
        qkv_start = weight_start(nodes, by_name, mm_indices[0])
        rope_candidates = [
            row["index"]
            for row in nodes[qkv_start:unified_index]
            if row["op"] == "get_attr"
            and row["target"].startswith("_tensor_constant")
        ]
        if len(rope_candidates) != 1:
            raise ValueError(f"expected one RoPE table, found {rope_candidates}")
        rope_start = rope_candidates[0]
        output_allocations = [
            row["index"]
            for row in nodes[rope_start:unified_index]
            if row["target"] == "aten.empty.memory_format"
        ]
        if len(output_allocations) != 1:
            raise ValueError(
                f"expected one attention output allocation, found {output_allocations}"
            )
        attention_start = output_allocations[0]
        output_start = weight_start(nodes, by_name, mm_indices[1])
        mlp_start = weight_start(nodes, by_name, mm_indices[2])
        residual_add = first_target_after(
            nodes, mm_indices[1] + 1, "aten.add.Tensor"
        )
        ranges = {
            "inputs": (placeholders[0], placeholders[-1]),
            "input_rmsnorm": (norm_start, qkv_start - 1),
            "qkv_projection": (qkv_start, rope_start - 1),
            "rope": (rope_start, attention_start - 1),
            "kv_cache_attention": (attention_start, unified_index),
            "attention_output": (unified_index + 1, output_start - 1),
            "output_projection": (output_start, residual_add),
            "post_attention_rmsnorm": (residual_add + 1, mlp_start - 1),
            "mlp": (mlp_start, output_index - 1),
            "layer_output": (output_index, output_index),
        }
        rule = "qwen35_full_unified_attention_landmarks_v1"
    else:
        raise ValueError(f"unsupported layer_type: {layer_type!r}")

    assigned = [
        index
        for start, end in ranges.values()
        if start <= end
        for index in range(start, end + 1)
    ]
    if any(start > end for start, end in ranges.values()):
        raise ValueError(f"empty or reversed process range: {ranges}")
    if sorted(assigned) != list(range(len(nodes))):
        raise ValueError(f"process ranges do not cover every node exactly once: {ranges}")
    if len(assigned) != len(set(assigned)):
        raise ValueError(f"process ranges overlap: {ranges}")
    return ranges, rule


def stage_for_index(
    index: int, ranges: dict[str, tuple[int, int]]
) -> str:
    matches = [
        stage
        for stage, (start, end) in ranges.items()
        if start <= index <= end
    ]
    if len(matches) != 1:
        raise ValueError(f"node {index} maps to {matches}")
    return matches[0]


def summarize_stages(
    nodes: list[dict[str, Any]], ranges: dict[str, tuple[int, int]]
) -> list[dict[str, Any]]:
    by_name = {row["name"]: row for row in nodes}
    summaries: list[dict[str, Any]] = []
    for stage in STAGE_ORDER:
        if stage not in ranges:
            continue
        start, end = ranges[stage]
        stage_nodes = nodes[start : end + 1]
        names = {row["name"] for row in stage_nodes}
        external_inputs = sorted(
            {
                dependency
                for row in stage_nodes
                for dependency in row["args"]
                if dependency not in names
            },
            key=lambda name: by_name[name]["index"],
        )
        external_outputs = sorted(
            {
                row["name"]
                for row in stage_nodes
                for user in row["users"]
                if user not in names
            },
            key=lambda name: by_name[name]["index"],
        )
        targets = [row["target"] for row in stage_nodes]
        summaries.append(
            {
                "stage": stage,
                "title": STAGE_TITLES[stage],
                "reconstruction_rule": STAGE_RULES[stage],
                "start_index": start,
                "end_index": end,
                "node_count": len(stage_nodes),
                "nodes": [row["name"] for row in stage_nodes],
                "targets": list(dict.fromkeys(targets)),
                "target_counts": dict(sorted(Counter(targets).items())),
                "external_inputs": external_inputs,
                "external_outputs": external_outputs,
            }
        )
    return summaries


def render_node(row: dict[str, Any]) -> str:
    if row["op"] == "placeholder":
        return f"# placeholder {row['name']}"
    if row["op"] == "get_attr":
        return f"{row['name']} = self.{row['target']}"
    if row["op"] == "output":
        return f"return {row['args_repr']}"
    suffix = ""
    if row["kwargs_repr"] not in ("", "{}"):
        suffix = f"  # kwargs={row['kwargs_repr']}"
    return f"{row['name']} = {row['target']}{row['args_repr']}{suffix}"


def render_markdown(payload: dict[str, Any]) -> str:
    identity = payload["event_identity"]
    source = payload["source_artifacts"]
    lines = [
        "# FX Layer Process Reconstruction",
        "",
        f"Event: `{identity['event_id']}` (`{identity['selection_id']}`)",
        f"Source event: `{identity['source_event_id']}`",
        (
            f"Observed path: `{identity['layer_type']}`, phase `{identity['phase']}`, "
            f"q/past/kv = `{identity['q_len']}/{identity['past_len']}/{identity['kv_len']}`"
        ),
        f"Trace directory: `{payload['trace_dir']}`",
        (
            f"GraphModule provenance: `fx_graph_module.pt` "
            f"(SHA-256 `{source['fx_graph_module_pt']['sha256']}`)"
        ),
        (
            f"Capture-time nodes: `fx_nodes.json` "
            f"(SHA-256 `{source['fx_nodes_json']['sha256']}`)"
        ),
        "",
        (
            "Source: rule reconstruction over the capture-time serialization of "
            "`GraphModule.graph.nodes`; the meta-storage GraphModule is not executed."
        ),
        (
            "Process labels are target-specific reconstruction labels, not FX "
            "metadata or proof of runtime module ownership."
        ),
        (
            "Opaque vLLM/ROCm/DCU custom-op nodes expose only their observed call "
            "and mutation boundary; their internal kernels are not reconstructed."
        ),
        "",
        "## Stage Summary",
        "",
        (
            "| stage | rule | node range | count | external inputs | "
            "external outputs |"
        ),
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for stage in payload["stages"]:
        inputs = ", ".join(f"`{item}`" for item in stage["external_inputs"]) or "-"
        outputs = (
            ", ".join(f"`{item}`" for item in stage["external_outputs"]) or "-"
        )
        lines.append(
            f"| {stage['title']} | {stage['reconstruction_rule']} | "
            f"{stage['start_index']}-{stage['end_index']} | "
            f"{stage['node_count']} | {inputs} | {outputs} |"
        )
    lines.extend(["", "## Process Code", ""])
    for stage in payload["stages"]:
        lines.extend([f"### {stage['title']}", "", "```python"])
        lines.extend(
            render_node(row)
            for row in payload["nodes"]
            if row["process_stage"] == stage["stage"]
        )
        lines.extend(["```", ""])
    lines.extend(
        [
            "## Node Table",
            "",
            "| index | stage | name | op | target | shape | dtype | args | users |",
            "| ---: | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in payload["nodes"]:
        shape = json.dumps(row["shape"]) if row["shape"] is not None else "-"
        dtype = row["dtype"] or "-"
        args = ", ".join(f"`{item}`" for item in row["args"]) or "-"
        users = ", ".join(f"`{item}`" for item in row["users"]) or "-"
        lines.append(
            f"| {row['index']} | `{row['process_stage']}` | `{row['name']}` | "
            f"`{row['op']}` | `{row['target']}` | `{shape}` | `{dtype}` | "
            f"{args} | {users} |"
        )
    return "\n".join(lines) + "\n"


def render_csv(nodes: list[dict[str, Any]]) -> str:
    fieldnames = [
        "index",
        "process_stage",
        "name",
        "op",
        "target",
        "args",
        "users",
        "shape",
        "dtype",
        "device",
        "args_repr",
        "kwargs_repr",
    ]
    fd, temporary = tempfile.mkstemp(prefix=".r042-nodes-", suffix=".csv")
    path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in nodes:
                writer.writerow(
                    {
                        **{key: row.get(key, "") for key in fieldnames},
                        "args": " ".join(row["args"]),
                        "users": " ".join(row["users"]),
                        "shape": (
                            json.dumps(row["shape"])
                            if row["shape"] is not None
                            else ""
                        ),
                    }
                )
        return path.read_text(encoding="utf-8")
    finally:
        if path.exists():
            path.unlink()


def validate_handoff(
    handoff: dict[str, Any],
    fx_root: Path,
    logical_run_id: str,
    source_goal: str,
    capture_run_id: str,
) -> tuple[list[str], list[str], list[str]]:
    if (
        handoff.get("status") != "complete"
        or handoff.get("source_goal") != source_goal
    ):
        raise ValueError(f"{source_goal} handoff is not complete")
    downstream = handoff.get("downstream_contract")
    if not isinstance(downstream, dict) or downstream.get("consume_as_is") is not True:
        raise ValueError("R032 downstream contract is not consume_as_is")
    if Path(downstream["fx_root"]).resolve() != fx_root:
        raise ValueError("requested FX root differs from R032 handoff")
    if handoff.get("runtime", {}).get("run_id") != capture_run_id:
        raise ValueError("capture run ID differs from source handoff")
    event_ids = list(downstream.get("ordered_fx_event_ids", []))
    source_ids = list(downstream.get("ordered_source_event_ids", []))
    selection_ids = list(handoff.get("selection", {}).get("ordered_selection_ids", []))
    if not event_ids or not (len(event_ids) == len(source_ids) == len(selection_ids)):
        raise ValueError("R032 ordered event identities are missing or inconsistent")
    if len(event_ids) != len(set(event_ids)) or len(source_ids) != len(set(source_ids)):
        raise ValueError("R032 ordered event identities are not unique")
    return event_ids, source_ids, selection_ids


def prepare_event(
    event_dir: Path,
    expected_event_id: str,
    expected_source_id: str,
    expected_selection_id: str,
    logical_run_id: str,
    capture_run_id: str,
    runtime_goal: str,
) -> dict[str, Any]:
    for name in REQUIRED_EVENT_FILES:
        if not (event_dir / name).is_file():
            raise FileNotFoundError(event_dir / name)
    for name in GENERATED_EVENT_FILES:
        if (event_dir / name).exists():
            raise FileExistsError(f"refusing to overwrite {event_dir / name}")

    metadata = load_json(event_dir / "fx_trace_metadata.json")
    raw_nodes = load_json(event_dir / "fx_nodes.json")
    if not isinstance(raw_nodes, list):
        raise TypeError(f"{event_dir / 'fx_nodes.json'} is not a list")
    nodes = normalize_nodes(raw_nodes)
    identity_checks = {
        "event_id": metadata.get("event_id") == expected_event_id == event_dir.name,
        "source_event_id": metadata.get("source_event_id") == expected_source_id,
        "selection_id": metadata.get("selection_id") == expected_selection_id,
        "node_count": metadata.get("node_count") == len(nodes),
        "logical_run_id": (
            metadata.get("specialization", {})
            .get("capture_join_key", {})
            .get("run_id")
            == capture_run_id
        ),
    }
    if not all(identity_checks.values()):
        raise ValueError(
            f"event identity mismatch for {event_dir.name}: {identity_checks}"
        )

    layer_type = str(metadata["layer_type"])
    ranges, reconstruction_rule = build_ranges(nodes, layer_type)
    for row in nodes:
        row["process_stage"] = stage_for_index(row["index"], ranges)
    stages = summarize_stages(nodes, ranges)
    opaque_targets = list(metadata.get("opaque_custom_ops", []))
    observed_custom_targets = sorted(
        {
            row["target"]
            for row in nodes
            if row["target"].startswith("vllm.")
        }
    )
    if sorted(opaque_targets) != observed_custom_targets:
        raise ValueError(
            f"opaque custom-op mismatch for {event_dir.name}: "
            f"{opaque_targets} != {observed_custom_targets}"
        )
    specialization = metadata.get("specialization", {})
    runtime_inputs = specialization.get("runtime_inputs", {}).get("kwargs", {})
    external_state = specialization.get("external_state_snapshot", {})
    source_artifacts = {
        "fx_graph_py": artifact(event_dir / "fx_graph.py", "generated_fx_python"),
        "fx_graph_txt": artifact(event_dir / "fx_graph.txt", "generated_fx_graph_text"),
        "fx_graph_module_pt": artifact(
            event_dir / "fx_graph_module.pt",
            "serialized_meta_storage_graph_module",
        ),
        "fx_nodes_json": artifact(
            event_dir / "fx_nodes.json",
            "capture_time_normalized_fx_node_manifest",
        ),
        "fx_trace_metadata": artifact(
            event_dir / "fx_trace_metadata.json",
            "per_event_capture_replay_and_boundary_metadata",
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "analysis_type": "qwen35_fixed_input_fx_process_reconstruction",
        "created_at": utc_now(),
        "runtime_goal": runtime_goal,
        "logical_pipeline_run_id": logical_run_id,
        "trace_dir": str(event_dir),
        "event_identity": {
            "event_id": expected_event_id,
            "selection_id": expected_selection_id,
            "source_event_id": expected_source_id,
            "r032_run_id": metadata["run_id"],
            "request_id": metadata["request_id"],
            "contract_id": metadata["contract_id"],
            "rank": metadata["rank"],
            "worker_id": metadata["worker_id"],
            "engine_step_id": metadata["engine_step_id"],
            "forward_id": metadata["forward_id"],
            "layer_idx": metadata["layer_idx"],
            "layer_occurrence": metadata["layer_occurrence"],
            "layer_type": layer_type,
            "phase": metadata["phase"],
            "q_len": metadata["q_len"],
            "past_len": metadata["past_len"],
            "kv_len": metadata["kv_len"],
        },
        "fixed_input_context": {
            "runtime_inputs": runtime_inputs,
            "external_state_snapshot": external_state,
            "trace_strategy": metadata.get("trace_strategy"),
            "graph_module_tensor_storage": metadata.get(
                "graph_module_tensor_storage"
            ),
            "no_multimodal_pruning_specialization": specialization.get(
                "no_multimodal_pruning_specialization"
            ),
        },
        "source_artifacts": source_artifacts,
        "source": "capture-time GraphModule.graph node serialization",
        "reconstruction_rule": reconstruction_rule,
        "evidence_guards": {
            "fixed_input_path_only": True,
            "graph_module_not_executed": True,
            "meta_storage_is_structural_evidence": True,
            "process_labels_are_rule_derived": True,
            "opaque_custom_ops": opaque_targets,
            "opaque_custom_op_internals_reconstructed": False,
            "measured_latency_reported": False,
            "concurrent_or_distributed_coverage_claimed": False,
            "pruning_or_early_exit_claimed": False,
        },
        "node_count": len(nodes),
        "stage_count": len(stages),
        "stages": stages,
        "nodes": nodes,
    }


def write_event(event_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    json_path = event_dir / "fx_process_reconstruction.json"
    markdown_path = event_dir / "fx_process_reconstruction.md"
    csv_path = event_dir / "fx_process_nodes.csv"
    write_json_atomic(json_path, payload)
    write_text_atomic(markdown_path, render_markdown(payload))
    write_text_atomic(csv_path, render_csv(payload["nodes"]))
    return {
        "event_id": payload["event_identity"]["event_id"],
        "selection_id": payload["event_identity"]["selection_id"],
        "source_event_id": payload["event_identity"]["source_event_id"],
        "trace_dir": payload["trace_dir"],
        "layer_type": payload["event_identity"]["layer_type"],
        "phase": payload["event_identity"]["phase"],
        "node_count": payload["node_count"],
        "stage_count": payload["stage_count"],
        "reconstruction_rule": payload["reconstruction_rule"],
        "status": "ok",
        "json": artifact(json_path, "machine_readable_fx_process_reconstruction"),
        "markdown": artifact(
            markdown_path, "generated_fx_process_reconstruction_report"
        ),
        "csv": artifact(csv_path, "fx_process_node_table"),
    }


def render_manifest_csv(results: list[dict[str, Any]]) -> str:
    fieldnames = [
        "event_id",
        "selection_id",
        "source_event_id",
        "trace_dir",
        "layer_type",
        "phase",
        "node_count",
        "stage_count",
        "reconstruction_rule",
        "status",
        "json",
        "markdown",
        "csv",
    ]
    fd, temporary = tempfile.mkstemp(prefix=".r042-manifest-", suffix=".csv")
    path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for result in results:
                writer.writerow(
                    {
                        **{key: result.get(key, "") for key in fieldnames},
                        "json": result["json"]["path"],
                        "markdown": result["markdown"]["path"],
                        "csv": result["csv"]["path"],
                    }
                )
        return path.read_text(encoding="utf-8")
    finally:
        if path.exists():
            path.unlink()


def main() -> None:
    args = parse_args()
    handoff_path = args.r032_handoff.resolve()
    fx_root = args.fx_root.resolve()
    if not handoff_path.is_file():
        raise FileNotFoundError(handoff_path)
    if not fx_root.is_dir():
        raise NotADirectoryError(fx_root)
    for name in GENERATED_ROOT_FILES:
        if (fx_root / name).exists():
            raise FileExistsError(f"refusing to overwrite {fx_root / name}")

    handoff = load_json(handoff_path)
    capture_run_id = args.capture_run_id or args.logical_run_id
    event_ids, source_ids, selection_ids = validate_handoff(
        handoff,
        fx_root,
        args.logical_run_id,
        args.source_goal,
        capture_run_id,
    )
    actual_event_dirs = sorted(
        path.name
        for path in fx_root.iterdir()
        if path.is_dir() and path.name.startswith("input")
    )
    if sorted(event_ids) != actual_event_dirs:
        raise ValueError(
            f"event directory set differs from R032 handoff: "
            f"{actual_event_dirs} != {sorted(event_ids)}"
        )

    # Prepare and validate every payload before writing the first output.
    prepared = [
        prepare_event(
            fx_root / event_id,
            event_id,
            source_id,
            selection_id,
            args.logical_run_id,
            capture_run_id,
            args.runtime_goal,
        )
        for event_id, source_id, selection_id in zip(
            event_ids, source_ids, selection_ids, strict=True
        )
    ]
    results = [
        write_event(fx_root / event_id, payload)
        for event_id, payload in zip(event_ids, prepared, strict=True)
    ]
    manifest_payload = {
        "schema_version": SCHEMA_VERSION,
        "analysis_type": "qwen35_fixed_input_fx_process_reconstruction_manifest",
        "created_at": utc_now(),
        "runtime_goal": args.runtime_goal,
        "logical_pipeline_run_id": args.logical_run_id,
        "source_goal": args.source_goal,
        "source_handoff": artifact(
            handoff_path, f"complete_{args.source_goal.lower()}_runtime_handoff"
        ),
        "fx_root": str(fx_root),
        "processed": len(results),
        "ordered_event_ids": event_ids,
        "ordered_selection_ids": selection_ids,
        "ordered_source_event_ids": source_ids,
        "results": results,
        "completion_checks": {
            "source_capture_handoff_complete": True,
            "consume_as_is_event_order_preserved": True,
            "all_event_payloads_validated_before_write": True,
            "every_fx_node_partitioned_exactly_once": True,
            "all_opaque_custom_ops_match_metadata": True,
            "no_graph_module_execution": True,
            "no_custom_op_internal_reconstruction": True,
            "no_manual_explanation_or_visualization_generated": True,
        },
    }
    manifest_json = fx_root / "fx_process_reconstruction_manifest.json"
    manifest_csv = fx_root / "fx_process_reconstruction_manifest.csv"
    write_json_atomic(manifest_json, manifest_payload)
    write_text_atomic(manifest_csv, render_manifest_csv(results))
    print(
        json.dumps(
            {
                "status": "ok",
                "processed": len(results),
                "ordered_event_ids": event_ids,
                "manifest_json": str(manifest_json),
                "manifest_csv": str(manifest_csv),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
