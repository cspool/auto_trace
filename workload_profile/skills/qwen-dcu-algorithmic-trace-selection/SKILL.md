---
name: qwen-dcu-algorithmic-trace-selection
description: Generate and audit pra2026-bh408 Qwen3.5-27B vLLM V1 algorithmic traces on ROCm/DCU, then select a small evidence-backed set of representative layer events.
---

# Qwen DCU Algorithmic Trace And Layer Selection

## Scope

Use this skill for two linked jobs:

1. Produce an end-to-end algorithmic trace from a real Qwen3.5-27B vLLM V1 inference request on ROCm/DCU.
2. Choose important layer events from that trace for later filtered op-level profiling.

Do not treat this as ROCm kernel-latency profiling. Algorithmic Trace records the dynamic request, scheduler, layer, cache/state, and decision schedule plus theoretical FLOPs, not kernels or wall-clock latency.

Stop this skill at validated fresh-forward traces and an evidence-backed selected-event set. Do not run filtered DispatchMode, FX, reconstruction, ONNX, or visualization work here.

## Project Layout

Use the current workspace split:

```text
/public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408/
  vllm/v1/{engine/core.py,core/sched/scheduler.py,worker/gpu_model_runner.py}
  vllm/model_executor/models/qwen3_5.py
  vllm/transformers_utils/configs/qwen3_5.py
  scripts/cscc_gfx936_env.sh
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/algorithmic_trace/traces/
```

Keep fresh trace outputs under `workload_profile/algorithmic_trace/traces/`.

No project-local Algorithmic Trace tool, wrapper, or schema is currently confirmed. At runtime, inspect the current source, installed wheel, platform service entry, and instrumentation before choosing or implementing them; record the resolved command, symbols, schema, and paths rather than guessing.

The confirmed runtime is Qwen3.5-27B BF16 on vLLM V1 and ROCm/DCU. The repository provides `scripts/cscc_gfx936_env.sh`; the platform provides the model, service script, and device allocation. Do not hard-code an unconfirmed device or external path.

## Step 1: Run End-To-End Inference Trace

Prefer a fresh real request when a DCU is available. Load the model through vLLM V1, run one deterministic inference request, record request/step/forward/layer/decision events, and write Algorithmic Trace outputs.

Resolve the concrete trace command at runtime:

```bash
PROJECT_ROOT=/public/home/tangyu408/Qwen_DCU_Worker_0
SOURCE_ROOT="${PROJECT_ROOT}/pra2026-bh408"
TRACE_DIR="${PROJECT_ROOT}/workload_profile/algorithmic_trace/traces/<tag>"
source "${SOURCE_ROOT}/scripts/cscc_gfx936_env.sh"
# Run the runtime-confirmed tracer, vLLM V1 service entry, and real request.
```

The resolved command must record the model, request, runtime, device, source revision, and tag. Do not complete with placeholders. If no compatible tracer exists, discover or implement the smallest required instrumentation before executing; profiler logs or inferred source structure are not a real trace.

Expected output directory:

```text
workload_profile/algorithmic_trace/traces/<tag>/
  algorithmic_trace.json
  layer_trace.csv
  selection_trace.csv
  operator_flops.csv
```

These are the required semantic artifacts. If a confirmed tool uses different names, record a one-to-one mapping and preserve all four roles and validations.

Use the current optimized runtime to identify project-relevant layers. A requested baseline needs a separate tag and one stated contract difference; never join events from different requests as one run.

## Step 2: Validate Trace Outputs

Inspect the output before proceeding:

- `algorithmic_trace.json`: request metadata, loaded dimensions and `layer_types`, request/step/forward/layer/decision events, and FLOP summary.
- `layer_trace.csv`: per request, step, forward, layer, and occurrence, including phase, `q_len`, `kv_len`, and exposed `past_len`.
- `selection_trace.csv`: actual scheduler or model decisions and affected context. Qwen3.5 disables multimodal pruning, so never fabricate pruning or early-exit events. If no applicable decision family is captured, keep the artifact and state that limitation.
- `operator_flops.csv`: expanded theoretical operator FLOPs for the observed Qwen3.5 full-attention and Gated Delta Net paths.

Sanity checks:

- Each complete forward should include every loaded `hf_text_config.num_hidden_layers` layer; explain pipeline partitioning, skipped control flow, or repeated calls.
- Layer roles should agree with loaded `hf_text_config.layer_types`; do not assume class defaults.
- Decision rows must join to the request, step, forward, and affected layer context.
- JSON and CSVs must agree on keys, occurrences, phases, lengths, layer types, and counts.
- Do not use a comparison-only trace to infer current-runtime target layers.

## Step 3: Select Layers Worth Later Profiling

Select a small, justified subset for later op-level profiling. Avoid selecting the whole model unless explicitly requested.

For Qwen3.5/vLLM V1-focused analysis, prioritize:

- **P0 decision events**: layers affected by actual scheduler, cache/state, or model decisions in `selection_trace.csv`.
- **P1 boundaries**: first layers before and after an observed phase, token-count, batch, or cache/state change.
- **P2 hybrid representatives**: early/late loaded `linear_attention` and `full_attention` layers and an observed boundary.
- **P3 decode representatives**: early and late decode steps across the observed full-attention KV-cache and Gated Delta Net state regimes.

Use `selection_trace.csv + layer_trace.csv` as the authority. Explain each target as `(request_id, engine_step_id, forward_id, layer_idx, layer_occurrence, phase, q_len, kv_len, layer_type, role/reason)`. Map differing runtime fields without dropping join or evidence requirements.

## Current Common Outputs

Primary Qwen3.5/vLLM V1 trace:

```text
workload_profile/algorithmic_trace/traces/<fresh-runtime-tag>/
```

An optional comparison uses a different tag under the same root.

## Completion Checks

Report completion only when:

- The requested fresh trace directory exists and contains the four Algorithmic Trace artifact roles.
- Trace files consistently identify request/step/forward, phase, layer occurrence, `q_len`/`kv_len`, loaded layer type, and emitted decisions.
- Every complete forward covers the loaded layers; observed control flow explains every exception or repetition.
- Important layer events are selected with explicit reasons tied to trace evidence, and every selected event joins uniquely to its source layer event.
- Theoretical FLOP output is present and is not reported as measured ROCm/DCU latency.
- The final answer states whether the trace is the current optimized runtime or a named comparison baseline and whether actual algorithm-decision evidence is available.
