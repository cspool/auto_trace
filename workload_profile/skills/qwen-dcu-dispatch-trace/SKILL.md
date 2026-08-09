---
name: qwen-dcu-dispatch-trace
description: Generate and audit filtered TorchDispatch profiles for selected Qwen3.5-27B layer events in the pra2026-bh408 vLLM V1 runtime on ROCm/DCU.
---

# Qwen DCU Filtered Dispatch Profile

## Scope

Use this skill to run filtered TorchDispatch profiling on only the important
Qwen3.5-27B layer events supplied in a validated current-runtime target list.

Do not treat this as ROCm kernel-latency profiling. Dispatch profiling records
ATen ops and tensor shapes for selected layers, not kernels or wall-clock
latency. Avoid wrapping the whole model unless explicitly requested.

## Project Layout

Use the current workspace split:

```text
/public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408/vllm/v1/worker/
/public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408/vllm/model_executor/models/qwen3_5.py
/public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408/scripts/cscc_gfx936_env.sh
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/dispatch/profiles/
```

Keep filtered dispatch profile outputs under
`workload_profile/dispatch/profiles/`.

No project-local filtered TorchDispatch profiler, wrapper, command, or event
schema is currently confirmed. At runtime, inspect the current source,
installed wheel, platform service entry, and real worker process before
choosing or implementing the profiler. Resolve the concrete `TorchDispatchMode`
entry, worker/process, module context, tensor identity, producer, and
alias/mutation bindings from that runtime rather than guessing them. Preserve
precise ATen-op and tensor-shape capture for only the target layers.

The confirmed runtime is Qwen3.5-27B BF16 on vLLM V1 and ROCm/DCU, and the
repository provides `scripts/cscc_gfx936_env.sh`. Do not hard-code an
unconfirmed profiler path, service command, device, or worker topology.

Stop this skill at validated filtered dispatch profiles. Do not create, audit,
or organize per-layer reconstruction, small-shape Torch flows, ONNX exports, or
visualization artifacts here. If the user asks for those after dispatch
profiling exists, switch to `$qwen-dcu-dispatch-reconstruct-visualize`.

## Step 4: Run Filtered Dispatch Trace

Run the filtered profiler for the current Qwen3.5/vLLM V1 configuration and
target layer events:

```bash
PROJECT_ROOT=/public/home/tangyu408/Qwen_DCU_Worker_0
SOURCE_ROOT="${PROJECT_ROOT}/pra2026-bh408"
source "${SOURCE_ROOT}/scripts/cscc_gfx936_env.sh"
# Run the runtime-discovered filtered TorchDispatch profiler in the actual
# vLLM V1 model worker with its resolved DCU/device and unique --tag binding.
```

The concrete profiler script, invocation flags, DCU binding, layer event
schema, and output tag must be discovered from the current runtime. The
resolved command must execute a real Qwen3.5-27B vLLM V1 inference and capture
only the supplied target events. Do not report a placeholder command as a run.

Expected output:

```text
workload_profile/dispatch/profiles/<tag>/
  README.md
  dispatch_manifest.csv
  dispatch_ops.csv
  dispatch_op_summary.csv
  observed_layer_events.csv
  run_metadata.json
```

Interpretation:

- `dispatch_manifest.csv` is the selected target list. Each row is a selected
  runtime-discovered layer event with reason/priority.
- `dispatch_ops.csv` is the real ATen dispatch trace for selected layers.
- `dispatch_op_summary.csv` aggregates operator counts by event and op schema.
- `observed_layer_events.csv` checks global layer-event numbering; it is not a
  full dispatch trace.
- `run_metadata.json` should confirm target counts, captured op counts, source
  trace path, and output-text consistency when available.

## Step 5: Validate Dispatch Profile

Before reporting the dispatch profile complete:

- Confirm the dispatch target events match the intended important Qwen3.5
  layers.
- Confirm `observed_layer_events.csv` covers the expected full layer schedule.
- Confirm `dispatch_ops.csv` contains rows for every runtime-confirmed
  `event_id` or equivalent stable event key in the manifest.
- Confirm `run_metadata.json` reports output text matches the source trace, if
  the runtime profiler records that check.
- Confirm the profiler did not accidentally capture all layers unless that was
  intended.

For per-layer tensor-process reconstruction and ONNX visualization, leave this
skill and use `$qwen-dcu-dispatch-reconstruct-visualize`.

## Current Common Outputs

Filtered Qwen3.5/vLLM V1 dispatch:

```text
workload_profile/dispatch/profiles/<fresh-runtime-tag>/
```

## Completion Checks

Report completion only when:

- The requested filtered dispatch directory exists under
  `workload_profile/dispatch/profiles/<tag>/` and includes README, manifest,
  ops, summary, observed events, and metadata.
- The dispatch target events match the intended important Qwen3.5 layers.
- `observed_layer_events.csv` covers the expected full layer schedule.
- Dispatch rows cover every selected event.
- The final answer states which Qwen3.5/vLLM V1 ROCm/DCU configuration the
  profile represents.
