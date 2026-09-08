#!/usr/bin/env python3
"""Pure-CPU production marker codec shared by R07 runtime and normalizer."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from typing import Any
from urllib.parse import quote, unquote


PROCESS_PREFIX = "qwen_dcu.fx_process|schema=1"
LAYER_PREFIX = "qwen_dcu.r02.layer_occurrence"
REQUEST_PREFIX = "qwen_dcu.r07.request"
FORWARD_PREFIX = "qwen_dcu.r07.forward"
SAFE = "-._~"
PROCESS_FIELD_ORDER = (
    "request_id", "forward_id", "layer_idx", "layer_occurrence", "layer_type",
    "phase", "q_len", "kv_len", "process_id", "fragment_id", "dp_rank",
    "physical_device_id",
)
LAYER_FIELD_ORDER = (
    "request_id", "forward_id", "layer_idx", "layer_type", "phase", "q_len",
    "kv_len", "dp_rank", "physical_device_id",
)


def escape_value(value: Any) -> str:
    return quote("none" if value is None else str(value), safe=SAFE, encoding="utf-8", errors="strict")


def _emit(prefix: str, fields: dict[str, Any], order: tuple[str, ...]) -> str:
    missing = [field for field in order if field not in fields]
    if missing:
        raise RuntimeError(f"marker missing fields: {missing}")
    if str(fields.get("layer_type", "linear_attention")) not in {"linear_attention", "full_attention"}:
        raise RuntimeError(f"invalid layer type: {fields.get('layer_type')!r}")
    if int(fields["dp_rank"]) not in {0, 1} or int(fields["physical_device_id"]) != int(fields["dp_rank"]):
        raise RuntimeError("rank/device marker mapping mismatch")
    return prefix + "".join(f"|{field}={escape_value(fields[field])}" for field in order)


def exact_process_name(fields: dict[str, Any]) -> str:
    return _emit(PROCESS_PREFIX, fields, PROCESS_FIELD_ORDER)


def exact_layer_name(fields: dict[str, Any]) -> str:
    return _emit(LAYER_PREFIX, fields, LAYER_FIELD_ORDER)


def exact_request_name(fields: dict[str, Any]) -> str:
    return _emit(REQUEST_PREFIX, fields, ("request_id", "dp_rank", "physical_device_id"))


def exact_forward_name(fields: dict[str, Any]) -> str:
    return _emit(FORWARD_PREFIX, fields, ("request_id", "forward_id", "phase", "q_len", "kv_len", "dp_rank", "physical_device_id"))


def parse_name(name: str) -> dict[str, str]:
    parts = name.split("|")
    if parts[0] not in {PROCESS_PREFIX.split("|")[0], LAYER_PREFIX, REQUEST_PREFIX, FORWARD_PREFIX}:
        raise RuntimeError(f"unknown marker prefix: {parts[0]!r}")
    result = {"prefix": parts[0]}
    for part in parts[1:]:
        if "=" not in part:
            raise RuntimeError(f"malformed marker component: {part!r}")
        key, value = part.split("=", 1)
        if key in result:
            raise RuntimeError(f"duplicate marker field: {key}")
        result[key] = unquote(value, encoding="utf-8", errors="strict")
    return result


def roundtrip(name: str) -> str:
    parsed = parse_name(name)
    prefix = parsed.pop("prefix")
    if prefix == PROCESS_PREFIX.split("|")[0]:
        if parsed.pop("schema", None) != "1":
            raise RuntimeError("process marker schema drift")
        return exact_process_name(parsed)
    if prefix == LAYER_PREFIX:
        return exact_layer_name(parsed)
    if prefix == REQUEST_PREFIX:
        return exact_request_name(parsed)
    return exact_forward_name(parsed)
