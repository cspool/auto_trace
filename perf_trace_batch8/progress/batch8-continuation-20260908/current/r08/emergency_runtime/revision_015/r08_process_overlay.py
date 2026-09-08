"""Current R08 replay overlay, preserving the exact R07 compiled boundaries.

Only current output paths, source validation, attempt identity, and replay
evidence labels differ from the source-pinned R07 marker method.
"""
from __future__ import annotations
import sys
sys.dont_write_bytecode=True
import atexit,hashlib,json,os,threading,time
from collections import Counter
from pathlib import Path
from typing import Any
from r07_common import RuntimePhaseBinder, bind_logical_targets
from r07_marker_contract import exact_forward_name,exact_request_name,roundtrip
from r08_native import ROOT, RUN, read, sha, output_path

ARTIFACT_ROOT=output_path(Path(os.environ['QWEN_DCU_R08_PASS_ROOT']))
ATTEMPT_ID=os.environ['QWEN_DCU_R08_RUNTIME_ATTEMPT_ID']
RUN_ID=LINEAGE_ID='batch8-dp2-fresh-003'
PROFILE_SHA256='3b4c952063f48ae662b48b5ce9d8fd76e0ac4d74e170bdb1839ae8b1aaa23cce'
EVENT_ROOT=ARTIFACT_ROOT/'workload/overlay_events'
BINDING_ROOT=ARTIFACT_ROOT/'workload/runtime_bindings'
WORKER_ROOT=ARTIFACT_ROOT/'control/workers'

def _require(condition,message):
    if not condition:raise RuntimeError(message)

_SOURCES=read(ROOT/'contract/runtime_overlay_sources.json')
for _name,_record in _SOURCES.items():
    _require(sha(_record['path'])==_record['sha256'],'R08 overlay source drift: '+_name)
EXPECTED_R01_PATCH=Path(_SOURCES['r01_patch']['path'])
EXPECTED_R01_PATCH_SHA256=_SOURCES['r01_patch']['sha256']
_SELECTION=read(_SOURCES['selection']['path'])
_LOGICAL_TARGETS=read(_SOURCES['logical_targets']['path'])
_require(os.environ.get('QWEN_DCU_R08_ENABLE_PROCESS_OVERLAY')=='1','R08 overlay enable')
_require(os.environ.get('HIP_VISIBLE_DEVICES')==os.environ.get('CUDA_VISIBLE_DEVICES')=='0,1','R08 DP2 visibility')
_require(_SELECTION['selector']['match_fields']==['request_id','phase','phase_occurrence'],'same R07 logical selector')
_require(_SELECTION['selector']['forbidden_match_fields']==['q_len','kv_len','forward_id'],'runtime shapes must bind after logical selection')
_require(len(_LOGICAL_TARGETS['records'])==13568,'complete logical target universe')
_logical_keys = {(str(row["request_id"]), str(row["phase"])) for row in _SELECTION["records"]}
_request_rank_map = {str(key): int(value) for key, value in _SELECTION["request_rank_map"].items()}
_binder = RuntimePhaseBinder(_logical_keys, expected_ranks=_request_rank_map, selected_occurrence=1)
_bound_by_execution_layer: dict[tuple[int, str, int], list[dict[str, Any]]] = {}
_process_by_bound_selection: dict[str, list[dict[str, Any]]] = {}
_expected_names: Counter[str] = Counter()
_binding_log_initialized: set[int] = set()

_r01: Any = None
_original_native_push: Any = None
_original_native_pop: Any = None
_installed = False
_state = threading.local()
_lock = threading.RLock()
_push_index = 0
_event_index = 0
_observed_process_names: Counter[str] = Counter()
_observed_layer_names: Counter[str] = Counter()
_seen_selection_keys: set[str] = set()
_rank_seen: set[int] = set()
_bound_target_count_by_rank: Counter[int] = Counter()
_summary_written: set[tuple[int, int]] = set()


def _selection_key(row: dict[str, Any]) -> str:
    return str(row["canonical_bound_selection_id"])


def _intercept_stack() -> list[str]:
    if not hasattr(_state, "intercept_stack"):
        _state.intercept_stack = []
    return _state.intercept_stack


def _exact_stack() -> list[dict[str, Any]]:
    if not hasattr(_state, "exact_stack"):
        _state.exact_stack = []
    return _state.exact_stack


def _session() -> dict[str, Any] | None:
    return getattr(_state, "session", None)


def _event_path(rank: int) -> Path:
    path = EVENT_ROOT / f"rank{rank}" / f"events.{os.getpid()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append_event(rank: int, row: dict[str, Any]) -> None:
    payload = {
        "schema_version": 1,
        "runtime_goal": "R08",
        "evidence_class": "replay_projected",
        "runtime_run_id": RUN_ID,
        "runtime_attempt_id": ATTEMPT_ID,
        "lineage_id": LINEAGE_ID,
        "trace_profile_sha256": PROFILE_SHA256,
        "pid": os.getpid(),
        "tid": threading.get_native_id(),
        "dp_rank": rank,
        "physical_device_id": rank,
        **row,
    }
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    descriptor = os.open(_event_path(rank), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, encoded)
    finally:
        os.close(descriptor)


def _binding_path(rank: int) -> Path:
    return BINDING_ROOT / f"rank{rank}.jsonl"


def _append_binding_rows(rank: int, rows: list[dict[str, Any]]) -> None:
    _require(rank in {0, 1}, f"R08 invalid binding-log rank: {rank}")
    path = _binding_path(rank)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        if rank not in _binding_log_initialized:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
            os.close(descriptor)
            _binding_log_initialized.add(rank)
        payload = b"".join(
            (
                json.dumps(
                    {
                        **row,
                        "runtime_attempt_id": ATTEMPT_ID,
                        "lineage_id": LINEAGE_ID,
                        "trace_profile_sha256": PROFILE_SHA256,
                        "binding_log_owner_dp_rank": rank,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
            for row in rows
        )
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND)
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                _require(written > 0, f"R08 short append to binding log: {path}")
                offset += written
        finally:
            os.close(descriptor)


def _bind_execution_context(context: dict[str, Any]) -> None:
    rank = int(context["dp_rank"])
    execution_id = str(context["execution_id"])
    bindings = _binder.observe_execution(
        dp_rank=rank,
        physical_device_id=int(context["physical_device_id"]),
        runtime_execution_id=execution_id,
        participants=context["participants"],
    )
    for binding in bindings:
        bound_rows = bind_logical_targets(_LOGICAL_TARGETS["records"], binding)
        _append_binding_rows(rank, bound_rows)
        _bound_target_count_by_rank[rank] += len(bound_rows)
        current_layer: dict[str, Any] | None = None
        process_rows: list[dict[str, Any]] = []
        for row in bound_rows:
            if row["target_kind"] == "layer_parent":
                if current_layer is not None:
                    _process_by_bound_selection[_selection_key(current_layer)] = process_rows
                current_layer = row
                process_rows = []
                _bound_by_execution_layer.setdefault(
                    (rank, execution_id, int(row["layer_idx"])), []
                ).append(row)
            else:
                _require(current_layer is not None, "R08 process target precedes layer target")
                process_rows.append(row)
                _expected_names[row["hiptx_marker_utf8"]] += 1
        _require(current_layer is not None, "R08 binding produced no layer target")
        _process_by_bound_selection[_selection_key(current_layer)] = process_rows


def _push_exact(
    *,
    rank: int,
    name: str,
    marker_kind: str,
    fields: dict[str, Any],
    strict_kernel_owner: bool,
    explicit_no_kernel_target: bool,
) -> None:
    global _push_index
    stack = _exact_stack()
    parent_name = stack[-1]["range_name"] if stack else None
    start_monotonic_ns = time.perf_counter_ns()
    start_realtime_ns = time.time_ns()
    result = _original_native_push(name)
    with _lock:
        _push_index += 1
        push_index = _push_index
    stack.append(
        {
            "range_name": name,
            "marker_kind": marker_kind,
            "record_kind": f"r08_{marker_kind}_range",
            "range_identity": hashlib.sha256(name.encode("utf-8")).hexdigest(),
            "parent_name": parent_name,
            "depth": len(stack),
            "start_monotonic_ns": start_monotonic_ns,
            "start_realtime_ns": start_realtime_ns,
            "push_result": result,
            "push_index": push_index,
            "fields": dict(fields),
            "strict_kernel_owner": bool(strict_kernel_owner),
            "explicit_no_kernel_target": bool(explicit_no_kernel_target),
        }
    )


def _pop_exact(*, rank: int, expected_name: str) -> dict[str, Any]:
    global _event_index
    stack = _exact_stack()
    _require(bool(stack), f"R08 exact marker underflow for {expected_name}")
    entry = stack[-1]
    _require(entry["range_name"] == expected_name, f"R08 exact nesting mismatch: {entry['range_name']} != {expected_name}")
    pop_result = _original_native_pop()
    end_monotonic_ns = time.perf_counter_ns()
    end_realtime_ns = time.time_ns()
    stack.pop()
    with _lock:
        _event_index += 1
        event_index = _event_index
        if entry["marker_kind"] == "process":
            _observed_process_names[entry["range_name"]] += 1
            _require(
                _observed_process_names[entry["range_name"]] <= _expected_names[entry["range_name"]],
                f"R08 duplicate/unexpected process marker: {entry['range_name']}",
            )
        elif entry["marker_kind"] == "layer":
            _observed_layer_names[entry["range_name"]] += 1
    _append_event(
        rank,
        {
            "kind": "r08_exact_range",
            "event_index": event_index,
            "push_index": entry["push_index"],
            "marker_kind": entry["marker_kind"],
            "record_kind": entry["record_kind"],
            "range_name": entry["range_name"],
            "range_identity": entry["range_identity"],
            "parent_name": entry["parent_name"],
            "depth": entry["depth"],
            "start_monotonic_ns": entry["start_monotonic_ns"],
            "end_monotonic_ns": end_monotonic_ns,
            "start_realtime_ns": entry["start_realtime_ns"],
            "end_realtime_ns": end_realtime_ns,
            "duration_monotonic_ns": end_monotonic_ns - entry["start_monotonic_ns"],
            "duration_realtime_ns": end_realtime_ns - entry["start_realtime_ns"],
            "push_result": entry["push_result"],
            "pop_result": pop_result,
            "strict_kernel_owner": entry["strict_kernel_owner"],
            "explicit_no_kernel_target": entry["explicit_no_kernel_target"],
            "operational_backend": "HIPTX/ROCTX",
            "native_marker_transport": True,
            **entry["fields"],
        },
    )
    return entry


def _base_fields(selected: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": selected["request_id"],
        "forward_id": selected["forward_id"],
        "layer_idx": int(selected["layer_idx"]),
        "layer_occurrence": int(selected["layer_occurrence"]),
        "layer_type": selected["layer_type"],
        "phase": selected["phase"],
        "phase_occurrence": int(selected["phase_occurrence"]),
        "q_len": int(selected["q_len"]),
        "kv_len": int(selected["kv_len"]),
        "runtime_execution_id": selected["runtime_execution_id"],
        "dp_rank": int(selected["dp_rank"]),
        "physical_device_id": int(selected["physical_device_id"]),
    }


def _process_rows(selected: dict[str, Any]) -> list[dict[str, Any]]:
    key = _selection_key(selected)
    rows = _process_by_bound_selection.get(key)
    _require(rows is not None, f"R08 selection lacks process inventory: {key}")
    return rows


def _parent_groups(selected: dict[str, Any]) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    rows = _process_rows(selected)
    groups: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    current: tuple[dict[str, Any], list[dict[str, Any]]] | None = None
    for row in rows:
        if row["target_kind"] == "process_parent":
            current = (row, [])
            groups.append(current)
        else:
            _require(current is not None, "R08 fragment precedes its parent")
            _require(row["range_parent"] == current[0]["nvtx_range_name"], "R08 fragment parent drift")
            current[1].append(row)
    return groups


def _push_row(rank: int, row: dict[str, Any], *, owner: bool, no_kernel: bool) -> None:
    fields = {
        "request_id": row["request_id"],
        "forward_id": row["forward_id"],
        "layer_idx": int(row["layer_idx"]),
        "layer_occurrence": int(row["layer_occurrence"]),
        "layer_type": row["layer_type"],
        "phase": row["phase"],
        "phase_occurrence": int(row["phase_occurrence"]),
        "q_len": int(row["q_len"]),
        "kv_len": int(row["kv_len"]),
        "runtime_execution_id": row["runtime_execution_id"],
        "process_id": row["process_id"],
        "fragment_id": row["fragment_id"],
        "aggregation_key": row["aggregation_key"],
        "target_kind": row["target_kind"],
        "canonical_target_id": row["canonical_target_id"],
        "canonical_target_sha256": row["canonical_target_sha256"],
        "canonical_logical_selection_id": row["canonical_logical_selection_id"],
        "canonical_logical_selection_sha256": row["canonical_logical_selection_sha256"],
        "canonical_bound_selection_id": row["canonical_bound_selection_id"],
        "canonical_bound_selection_sha256": row["canonical_bound_selection_sha256"],
        "dp_rank": rank,
        "physical_device_id": rank,
    }
    _require(roundtrip(row["nvtx_range_name"]) == row["nvtx_range_name"], "R08 runtime process codec drift")
    _push_exact(
        rank=rank,
        name=row["nvtx_range_name"],
        marker_kind="process",
        fields=fields,
        strict_kernel_owner=owner,
        explicit_no_kernel_target=no_kernel,
    )


def _emit_parent_group_zero(rank: int, parent: dict[str, Any], fragments: list[dict[str, Any]]) -> None:
    _push_row(rank, parent, owner=False, no_kernel=True)
    for fragment in fragments:
        _push_row(rank, fragment, owner=False, no_kernel=True)
        _pop_exact(rank=rank, expected_name=fragment["nvtx_range_name"])
    _pop_exact(rank=rank, expected_name=parent["nvtx_range_name"])


def _push_outer(selected: dict[str, Any], *, synthetic: bool) -> None:
    fields = _base_fields(selected)
    rank = fields["dp_rank"]
    request_name = exact_request_name(fields)
    forward_name = exact_forward_name(fields)
    layer_name = selected["layer_marker_utf8"]
    _require(roundtrip(request_name) == request_name, "R08 request marker codec drift")
    _require(roundtrip(forward_name) == forward_name, "R08 forward marker codec drift")
    _require(roundtrip(layer_name) == layer_name, "R08 layer marker codec drift")
    common = {**fields, "synthetic_zero_work": synthetic}
    _push_exact(rank=rank, name=request_name, marker_kind="request", fields=common, strict_kernel_owner=False, explicit_no_kernel_target=synthetic)
    _push_exact(rank=rank, name=forward_name, marker_kind="forward", fields=common, strict_kernel_owner=False, explicit_no_kernel_target=synthetic)
    _push_exact(rank=rank, name=layer_name, marker_kind="layer", fields=common, strict_kernel_owner=False, explicit_no_kernel_target=synthetic)


def _pop_outer(selected: dict[str, Any]) -> None:
    fields = _base_fields(selected)
    rank = fields["dp_rank"]
    _pop_exact(rank=rank, expected_name=selected["layer_marker_utf8"])
    _pop_exact(rank=rank, expected_name=exact_forward_name(fields))
    _pop_exact(rank=rank, expected_name=exact_request_name(fields))


def _emit_full_zero(selected: dict[str, Any]) -> None:
    rank = int(selected["dp_rank"])
    _push_outer(selected, synthetic=True)
    try:
        for parent, fragments in _parent_groups(selected):
            _emit_parent_group_zero(rank, parent, fragments)
    finally:
        _pop_outer(selected)


def _group_by_process(selected: dict[str, Any]) -> dict[str, tuple[dict[str, Any], list[dict[str, Any]]]]:
    result = {}
    for parent, fragments in _parent_groups(selected):
        result[parent["process_id"]] = (parent, fragments)
    return result


def _open_actual_process(session: dict[str, Any], process_id: str) -> None:
    _require(session.get("open_process") is None, f"R08 process overlap before opening {process_id}")
    parent, fragments = session["groups"][process_id]
    rank = int(session["selected"]["dp_rank"])
    _push_row(rank, parent, owner=True, no_kernel=False)
    for fragment in fragments:
        _push_row(rank, fragment, owner=False, no_kernel=True)
        _pop_exact(rank=rank, expected_name=fragment["nvtx_range_name"])
    session["open_process"] = parent


def _close_actual_process(session: dict[str, Any], process_id: str) -> None:
    parent = session.get("open_process")
    _require(parent is not None and parent["process_id"] == process_id, f"R08 process close mismatch for {process_id}")
    rank = int(session["selected"]["dp_rank"])
    _pop_exact(rank=rank, expected_name=parent["nvtx_range_name"])
    session["open_process"] = None


def _emit_zero_process(session: dict[str, Any], process_id: str) -> None:
    parent, fragments = session["groups"][process_id]
    _emit_parent_group_zero(int(session["selected"]["dp_rank"]), parent, fragments)


def _active_selections(layer_idx: int) -> list[dict[str, Any]]:
    context = getattr(_r01, "_context", None)
    if context is None:
        return []
    rank = int(context["dp_rank"])
    execution_id = str(context["execution_id"])
    _bind_execution_context(context)
    return [
        row
        for row in _bound_by_execution_layer.get((rank, execution_id, int(layer_idx)), [])
        if _selection_key(row) not in _seen_selection_keys
    ]


def _begin_layer(layer_idx: int) -> None:
    selections = _active_selections(layer_idx)
    if not selections:
        _state.session = None
        return
    for synthetic in selections[1:]:
        _emit_full_zero(synthetic)
        _seen_selection_keys.add(_selection_key(synthetic))
    selected = selections[0]
    rank = int(selected["dp_rank"])
    _rank_seen.add(rank)
    _push_outer(selected, synthetic=False)
    groups = _group_by_process(selected)
    expected_processes = (
        {"input_rmsnorm", "qkv_projection", "gdn_recurrent_core", "gdn_gated_rmsnorm", "output_projection", "post_attention_rmsnorm", "mlp", "layer_output"}
        if selected["layer_type"] == "linear_attention"
        else {"input_rmsnorm", "qkv_projection", "rope", "kv_cache_attention", "attention_output", "output_projection", "post_attention_rmsnorm", "mlp", "layer_output"}
    )
    _require(set(groups) == expected_processes, f"R08 process family drift at layer {layer_idx}: {set(groups)}")
    session = {"selected": selected, "groups": groups, "open_process": None, "component": "layer"}
    _state.session = session
    _open_actual_process(session, "input_rmsnorm")


def _begin_attention(session: dict[str, Any]) -> None:
    _emit_zero_process(session, "qkv_projection")
    if session["selected"]["layer_type"] == "linear_attention":
        _open_actual_process(session, "gdn_recurrent_core")
    else:
        _emit_zero_process(session, "rope")
        _open_actual_process(session, "kv_cache_attention")
    session["component"] = "attn"


def _end_attention(session: dict[str, Any]) -> None:
    if session["selected"]["layer_type"] == "linear_attention":
        _close_actual_process(session, "gdn_recurrent_core")
        _emit_zero_process(session, "gdn_gated_rmsnorm")
    else:
        _close_actual_process(session, "kv_cache_attention")
        _emit_zero_process(session, "attention_output")
    _emit_zero_process(session, "output_projection")


def _begin_mlp(session: dict[str, Any]) -> None:
    _open_actual_process(session, "mlp")
    session["component"] = "mlp"


def _end_mlp(session: dict[str, Any]) -> None:
    _close_actual_process(session, "mlp")


def _end_layer(session: dict[str, Any]) -> None:
    selected = session["selected"]
    _close_actual_process(session, "layer_output")
    _pop_outer(selected)
    _seen_selection_keys.add(_selection_key(selected))
    _state.session = None


def _parse_broad(name: str) -> tuple[int, str] | None:
    if not name.startswith("qwen_dcu.layer"):
        return None
    # qwen_dcu.layer00.prefill[.attn|.mlp]
    parts = name.split(".")
    _require(len(parts) in (3, 4), f"R08 unexpected R01 marker: {name}")
    layer_idx = int(parts[1][len("layer") :])
    component = "layer" if len(parts) == 3 else parts[3]
    _require(component in {"layer", "attn", "mlp"}, f"R08 unknown R01 component: {component}")
    return layer_idx, component


def _native_push(name: str) -> Any:
    parsed = _parse_broad(name)
    if parsed is not None:
        layer_idx, component = parsed
        session = _session()
        if session is not None:
            _require(int(session["selected"]["layer_idx"]) == layer_idx, "R08 cross-layer session")
            if component == "attn":
                _close_actual_process(session, "input_rmsnorm")
            elif component == "mlp":
                _close_actual_process(session, "post_attention_rmsnorm")
    result = _original_native_push(name)
    _intercept_stack().append(name)
    if parsed is None:
        return result
    layer_idx, component = parsed
    if component == "layer":
        _begin_layer(layer_idx)
    else:
        session = _session()
        if session is not None:
            _require(int(session["selected"]["layer_idx"]) == layer_idx, "R08 cross-layer session")
            if component == "attn":
                _begin_attention(session)
            else:
                _begin_mlp(session)
    return result


def _native_pop() -> Any:
    stack = _intercept_stack()
    _require(bool(stack), "R08 broad marker stack underflow")
    name = stack[-1]
    parsed = _parse_broad(name)
    if parsed is not None:
        layer_idx, component = parsed
        session = _session()
        if session is not None:
            _require(int(session["selected"]["layer_idx"]) == layer_idx, "R08 broad pop crossed layer")
            if component == "attn":
                _end_attention(session)
            elif component == "mlp":
                _end_mlp(session)
            else:
                _end_layer(session)
    result = _original_native_pop()
    stack.pop()
    if parsed is not None:
        _layer_idx, component = parsed
        session = _session()
        if session is not None:
            if component == "attn":
                _open_actual_process(session, "post_attention_rmsnorm")
                session["component"] = "layer"
            elif component == "mlp":
                _open_actual_process(session, "layer_output")
                session["component"] = "layer"
    return result


def _write_summary() -> None:
    context = getattr(_r01, "_context", None) if _r01 is not None else None
    ranks = sorted(_rank_seen)
    if context is not None:
        ranks = sorted(set(ranks) | {int(context["dp_rank"])})
    for rank in ranks:
        key = (rank, os.getpid())
        if key in _summary_written:
            continue
        _summary_written.add(key)
        local_expected = {
            name: count
            for name, count in _expected_names.items()
            if f"|dp_rank={rank}|physical_device_id={rank}" in name
        }
        local_observed = {
            name: count
            for name, count in _observed_process_names.items()
            if f"|dp_rank={rank}|physical_device_id={rank}" in name
        }
        local_seen_selection_count = sum(
            1
            for rows in _bound_by_execution_layer.values()
            for row in rows
            if int(row["dp_rank"]) == rank
            and _selection_key(row) in _seen_selection_keys
        )
        local_layer_event_count = sum(
            count
            for name, count in _observed_layer_names.items()
            if f"|dp_rank={rank}|physical_device_id={rank}" in name
        )
        local_phase_binding_count = sum(
            1
            for value in _binder.bindings.values()
            if int(value["dp_rank"]) == rank
        )
        all_ranges_closed = len(_exact_stack()) == 0 and len(_intercept_stack()) == 0
        complete = (
            Counter(local_observed) == Counter(local_expected)
            and sum(local_expected.values()) == 6_272
            and sum(local_observed.values()) == 6_272
            and local_layer_event_count == 512
            and local_seen_selection_count == 512
            and local_phase_binding_count == 8
            and _bound_target_count_by_rank[rank] == 6_784
            and all_ranges_closed
        )
        payload = {
            "schema_version": 1,
        "runtime_goal": "R08",
        "evidence_class": "replay_projected",
            "status": "complete" if complete else "incomplete",
            "runtime_run_id": RUN_ID,
            "runtime_attempt_id": ATTEMPT_ID,
            "lineage_id": LINEAGE_ID,
            "trace_profile_sha256": PROFILE_SHA256,
            "pid": os.getpid(),
            "dp_rank": rank,
            "physical_device_id": rank,
            "expected_process_event_count": sum(local_expected.values()),
            "observed_process_event_count": sum(local_observed.values()),
            "process_count_match": Counter(local_observed) == Counter(local_expected),
            "observed_layer_event_count": local_layer_event_count,
            "seen_selection_count": local_seen_selection_count,
            "bound_request_phase_count": local_phase_binding_count,
            "bound_target_count": _bound_target_count_by_rank[rank],
            "binding_log_path": str(_binding_path(rank)),
            "exact_stack_depth": len(_exact_stack()),
            "broad_stack_depth": len(_intercept_stack()),
            "all_ranges_closed": all_ranges_closed,
            "r01_compiled_patch_path": str(EXPECTED_R01_PATCH),
            "r01_compiled_patch_sha256": EXPECTED_R01_PATCH_SHA256,
            "overlay_semantics": "same_aot_graph_existing_boundaries_logical_request_phase_first_occurrence_runtime_shape_binding_rank_execution_dedup",
            "realtime_ns": time.time_ns(),
            "monotonic_ns": time.perf_counter_ns(),
        }
        path = WORKER_ROOT / f"rank{rank}" / f"overlay_summary.{os.getpid()}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def install(r01_module: Any) -> None:
    global _r01, _original_native_push, _original_native_pop, _installed
    if _installed:
        return
    _r01 = r01_module
    _require(Path(r01_module.__file__).resolve() == EXPECTED_R01_PATCH.resolve(), f"R08 loaded unexpected R01 patch: {r01_module.__file__}")
    _original_native_push = r01_module._native_push
    _original_native_pop = r01_module._native_pop
    r01_module._native_push = _native_push
    r01_module._native_pop = _native_pop
    atexit.register(_write_summary)
    _installed = True
    print(
        "R08_COMPILED_OVERLAY_READY "
        f"attempt={ATTEMPT_ID} process_targets=12544 layer_targets=1024 "
        f"r01_patch_sha256={EXPECTED_R01_PATCH_SHA256} status=ready",
        flush=True,
    )
