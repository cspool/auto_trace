---
name: qwen-dcu-fx-trace
description: Generate, inspect, and troubleshoot pra2026-bh408 Qwen3.5-27B vLLM V1 selected-layer FX trace artifacts on ROCm/DCU, with a bundled migration copy of fx_dynamic_trace.py. Use for make_fx layer capture, GraphModule artifacts, fx_nodes.json, fx_layer_events.csv, fx_layer_trace_manifest.csv, or run_metadata.json.
---

# Qwen DCU FX Trace

## Scope

Use this skill for the FX trace generation path, especially:

```text
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/skills/qwen-dcu-fx-trace/scripts/fx_dynamic_trace.py
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/fx/traces/<tag>/<event_id>/fx_graph.py
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/fx/traces/<tag>/<event_id>/fx_nodes.json
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/fx/traces/<tag>/<event_id>/fx_graph_module.pt
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/fx/traces/<tag>/fx_layer_events.csv
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/fx/traces/<tag>/fx_layer_trace_manifest.csv
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/fx/traces/<tag>/run_metadata.json
```

The workflow focus is generating and inspecting FX trace artifacts produced for
selected `Qwen3_5DecoderLayer` calls in the real Qwen3.5-27B vLLM V1 worker.

## Bundled Script

This skill carries a migration-friendly copy of the trace generator:

```text
scripts/fx_dynamic_trace.py
```

The bundled file is the preserved source implementation. Its generic callable
mode is reusable, but its selected-layer imports, model loading, cache handling,
and specializations are not yet bound to Qwen3.5/vLLM V1. Before selected-layer
use, inspect the checkout, installed wheel, service entry, and real worker, then
resolve or implement those bindings without weakening this method.

Prefer a confirmed current-runtime tracer:

```bash
PROJECT_ROOT=/public/home/tangyu408/Qwen_DCU_Worker_0
SOURCE_ROOT="${PROJECT_ROOT}/pra2026-bh408"
source "${SOURCE_ROOT}/scripts/cscc_gfx936_env.sh"
FX_TRACE_SCRIPT="${FX_TRACE_SCRIPT:?resolve the current-runtime FX tracer first}"
python "${FX_TRACE_SCRIPT}" ...
```

Use the bundled copy as the migration source or for a standalone callable:

```bash
python \
  /public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/skills/qwen-dcu-fx-trace/scripts/fx_dynamic_trace.py \
  --target package.module:function ...
```

The current-runtime tracer should resolve workload paths in this order:

1. an explicit workload directory accepted by the runtime-confirmed tracer;
2. `${PROJECT_ROOT}/workload_profile`;
3. the current working directory when it is the project root or
   `workload_profile`;
4. `/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile`;
5. a script-relative fallback.

Do not trace an unrelated checkout or report the unported bundled model mode as
a current-runtime capture.

## Evidence Boundary

Keep the two trace-generation evidence levels separate:

- Runtime sampling evidence: a real Qwen3.5-27B request runs through vLLM V1
  eager model execution in the actual ROCm/DCU model worker, and selected
  decoder-layer call inputs plus all replay-relevant runtime state are cloned
  at layer entry.
- Offline FX DAG evidence: after that request returns and wrappers are
  restored, sampled inputs and captured state are replayed through
  `make_fx(...)` to create a fixed-input `GraphModule`.

State this boundary for claims about runtime coverage, ownership, process
semantics, custom-op internals, worker behavior, or possible branches. Answer
from generated FX trace files only.

## Main Workflow

Prefer selected-layer mode for Qwen3.5 layer traces. Resolve the tracer, device,
and event-key mapping before running:

```bash
PROJECT_ROOT=/public/home/tangyu408/Qwen_DCU_Worker_0
SOURCE_ROOT="${PROJECT_ROOT}/pra2026-bh408"
FX_OUTPUT_ROOT="${PROJECT_ROOT}/workload_profile/fx/traces"
source "${SOURCE_ROOT}/scripts/cscc_gfx936_env.sh"
FX_TRACE_SCRIPT="${FX_TRACE_SCRIPT:?resolve the current-runtime FX tracer first}"
LOGICAL_DEVICE="${LOGICAL_DEVICE:?resolve the platform-managed device first}"
LAYER_TARGETS="${LAYER_TARGETS:?resolve stable selected-layer targets first}"
python "${FX_TRACE_SCRIPT}" \
  --model-layer-trace \
  --layers "${LAYER_TARGETS}" \
  --output-dir "${FX_OUTPUT_ROOT}" \
  --gpu "${LOGICAL_DEVICE}" \
  --tag fx_selected_layers
```

Preserve these target modes when they map unambiguously to observed events:

```text
0,5,6          trace those local layer indexes for every model forward
input1_layer5  trace one forward/layer event only when that schema is confirmed
1:5            shorthand for the same confirmed forward/layer event
```

If request, step, rank, or `layer_occurrence` is needed for uniqueness, extend
or map the syntax without dropping those keys.

The selected-layer workflow is:

1. Read optional algorithmic-trace defaults from `--trace`, then resolve the
   loaded config, model path, request inputs or prompt, generation settings, and
   `max_new_tokens`; record the exact source trace and runtime contract.
2. Load or attach to the real Qwen3.5-27B BF16 vLLM V1 worker on the
   platform-selected ROCm/DCU device. Discover the installed code, wrapper
   stack, process, and device at runtime.
3. Wrap the effective eager request/model boundary to assign stable request,
   engine-step, `forward_id`, rank, and prefill/decode fields. Resolve it from
   `GPUModelRunner` and the live model; do not assume `generate()`.
4. Wrap live `Qwen3_5DecoderLayer.forward` calls in `Qwen3_5Model.layers` to
   record the full event key, `layer_idx`, loaded `layer_type`, occurrence,
   phase, `q_len`, exposed `past_len`/`kv_len` or explicitly mapped current
   equivalents, cache/state lengths, shapes, and target match.
5. For matches, recursively clone args/kwargs and every replay-relevant vLLM V1
   forward-context, KV-cache, control, and Qwen3.5 Gated Delta Net state tensor.
   Discover concrete objects in the worker; do not substitute `DynamicCache`.
6. Immediately call the original layer. The real response comes from eager
   execution, never the FX graph, and instrumentation must not alter it.
7. Restore all wrappers and hooks in `finally` after request return or failure,
   before offline replay.
8. Replay samples offline through `make_fx(...)` with fixed-input
   specializations and the observed runtime contexts/mutation boundaries.
9. Write one event directory per success and run-level manifests; retain every
   failure as an explicit manifest error.

## Fixed-Input Specialization

Explain or check these specializations when FX capture fails or appears
surprising:

- Flatten runtime kwargs into positional FX inputs if this PyTorch `make_fx`
  rejects kwargs; restore the original keyword names inside the target.
- Compute guards derived from `positions`, token/schedule metadata, and shapes
  from cloned inputs and temporarily bind them as Python constants.
- Convert selected scalar layer/context attributes to Python values only after
  the live call identifies them.
- Dry-run sampled `.item()` or Python branches once, record the decisions, and
  replay the same fixed branch. Do not invent visual selection: current Qwen3.5
  disables multimodal pruning.
- Normalize externally managed KV-cache or Gated Delta Net state outputs and
  mutations to observed replay-relevant tensors; discover their representation
  and keep ROCm custom ops opaque unless the trace actually enters them.

All replacements are analysis-only changes to cloned inputs or in-memory
objects and must be reverted after each offline FX call, including on error.

## Expected Outputs

For each matched event, expect:

```text
workload_profile/fx/traces/<tag>/<event_id>/fx_graph.py
workload_profile/fx/traces/<tag>/<event_id>/fx_graph.txt
workload_profile/fx/traces/<tag>/<event_id>/fx_nodes.json
workload_profile/fx/traces/<tag>/<event_id>/fx_graph_module.pt
workload_profile/fx/traces/<tag>/<event_id>/fx_graph_module/
workload_profile/fx/traces/<tag>/<event_id>/fx_trace_metadata.json
```

For the whole run, expect:

```text
workload_profile/fx/traces/<tag>/fx_layer_events.csv
workload_profile/fx/traces/<tag>/fx_layer_trace_manifest.csv
workload_profile/fx/traces/<tag>/run_metadata.json
```

Inspect `run_metadata.json` first for `fx_sample_count`, `fx_trace_count`, and
`fx_trace_error_count`. Then inspect `fx_layer_trace_manifest.csv` for
per-event `status`, `node_count`, `trace_dir`, `specialization`, and `error`.
Metadata must also identify the pra2026-bh408 revision, Qwen3.5/vLLM V1 worker,
ROCm/DCU device, and event-key mapping. Complete only when every requested
event is sampled once, has all artifacts, metadata agrees, and no error is
dropped. Strict mode aborts on an event failure after restoration; otherwise
the run remains incomplete until manifest errors are resolved.

## Generic Callable Mode

Use generic mode only when the user is tracing a standalone callable rather
than a selected Qwen3.5 decoder layer:

```bash
PROJECT_ROOT=/public/home/tangyu408/Qwen_DCU_Worker_0
python \
  "${PROJECT_ROOT}/workload_profile/skills/qwen-dcu-fx-trace/scripts/fx_dynamic_trace.py" \
  --target package.module:function \
  --input-spec-file input_spec.json \
  --output-dir "${PROJECT_ROOT}/workload_profile/fx/traces" \
  --tag my_trace
```

Alternatively use `--demo`. Generic mode builds inputs from JSON, runs
`make_fx`, and writes the same single-event files under `<output-dir>/<tag>/`.
It does not prove selected-layer Qwen3.5 sampling or replay works.

## Troubleshooting

Use these checks before modifying code:

- Confirm `--layers` maps uniquely to observed keys in `fx_layer_events.csv`
  and hooks reached the effective live `Qwen3_5DecoderLayer.forward` calls.
- Confirm `HIP_VISIBLE_DEVICES`, `CUDA_VISIBLE_DEVICES`, tracer option, and
  service select the intended ROCm/DCU worker, rank, and process.
- Check `fx_layer_trace_manifest.csv` errors and the observed layer type,
  forward context, KV-cache/Gated Delta Net state, and custom-op boundary before
  rerunning all layers.
- Use `--strict-layer-trace` only when failure should abort immediately;
  always restore wrappers and specializations.
- If an FX graph misses a branch, remember it represents one fixed sampled
  input path, not all possible Python control-flow paths or opaque custom-op
  internals.
- If runtime-op coverage is disputed, compare against DispatchMode traces; FX
  is a fixed-input graph-capture view, while DispatchMode is the eager runtime
  op log.
