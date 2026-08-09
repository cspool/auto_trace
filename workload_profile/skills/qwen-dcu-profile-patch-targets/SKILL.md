---
name: qwen-dcu-profile-patch-targets
description: Decide where to instrument, hook, or monkey-patch the pra2026-bh408 Qwen3.5-27B vLLM V1 runtime on ROCm/DCU to capture algorithm-level execution traces from real model or inference serving runs. Use when the user asks what to patch or what fields to record to understand actual request, scheduler, batch, layer, attention, cache, token-selection, or algorithm-decision flow.
---

# Trace Patch Target Discovery

## Core Rule

Patch only to recover the algorithm-level execution process observed during a real run.

Start from the analysis question, then choose the smallest runtime boundary that exposes the relevant algorithm state. Do not begin by patching functions found by search.

The output should be a patch target plan:

- boundary to instrument
- reason this boundary explains the algorithm process
- join keys for connecting events
- small metadata fields to record
- validation that the wrapper or hook preserves behavior

## Workflow

### 1. Turn the Goal Into Process Questions

Rewrite the user's goal into concrete process questions:

- Which request or generation step is being analyzed?
- Which phase is active: prefill, decode, mixed, selection, cache update, or output?
- Which layer, scheduler step, batch, token group, or cache state changes?
- Which algorithm decision changes the later execution path?
- What minimal metadata proves that change happened in the real run?

If the target is unclear, assume the user wants the highest-level algorithm process that can explain the observed behavior.

### 2. Choose the Runtime Boundary

Prefer semantic boundaries that already represent the algorithm concept.

Use this order:

1. Request or generation boundary
2. Engine iteration or generation step
3. Scheduler decision
4. Batch construction
5. Model execution boundary
6. Layer boundary
7. Attention or algorithm helper boundary
8. Cache state update boundary
9. Sampling or output boundary

Move lower only when the higher boundary cannot expose the needed algorithm state.

### 3. Record Join Keys

Every event should be joinable with later events. Capture whichever keys exist in the runtime:

- `request_id`
- `engine_step_id` or `iteration_id`
- `batch_id`
- `sequence_id`
- `forward_id`
- `layer_idx`
- `phase`
- `timestamp` or monotonic event index
- `rank`, `worker_id`, or `device_id` when distributed

If no stable key exists, create a local counter at the highest relevant boundary and pass it through the trace state.

### 4. Record Small Algorithm State

Capture state summaries, not full tensors.

Useful fields:

- sequence lengths: `prompt_len`, `generated_len`, `q_len`, `kv_len`, `past_len`
- batch state: `num_requests`, `num_sequences`, `num_tokens`, prefill/decode counts
- layer state: `layer_idx`, hidden shape in/out, position shape, cache length
- cache state: allocated count, reused count, freed count, block-table length, hit/miss flag
- decision state: input shape, threshold/config summary, selected count, selected indices when small, boolean decision, state before/after
- output state: sampled token id, finish reason, output token count

Avoid copying large tensors or forcing device-to-host transfers unless the user explicitly asks for tensor contents.

## Patch Target Matrices

### Inference Serving Runtime

| Question | Patch boundary | Fields |
|---|---|---|
| Request lifecycle | API ingress, queue, first output, finish | `request_id`, prompt length, output count, lifecycle timestamps |
| Scheduling path | scheduler step | selected request ids, waiting/running counts, prefill/decode/mixed phase |
| Batch formation | batch metadata builder | `num_sequences`, `num_tokens`, per-request token counts, max length |
| Model execution process | model execute boundary | batch id, phase, token counts, sequence ids |
| Cache evolution | cache manager or block-table update | allocated/reused/freed counts, block-table sizes, hit/miss |
| Attention state | attention wrapper or backend call boundary | q length, kv length, head count, head dim, cache/block summary |
| Algorithm decision | algorithm-specific decision function | state before/after, input shape, decision result, affected requests or tokens |
| Output process | sampler or streaming output boundary | sampled token id, finish reason, emitted token count |

### Local PyTorch Model Execution

| Question | Patch boundary | Fields |
|---|---|---|
| Generation schedule | `model.forward` or generation loop | `forward_id`, phase, input length, logits/output shape |
| Per-layer token schedule | transformer layer `forward` | `layer_idx`, `q_len`, `past_len`, `kv_len`, hidden shape in/out |
| Algorithm selection | attention helper or selection function | input shapes, selected count, selected indices, decision value |
| Exit or skip behavior | decision function and next layer boundary | decision flag, state before/after, affected layer range |
| Cache evolution | layer boundary receiving cache state | usable cache length, cache object summary, before/after summary |
| Output differences | sampler or logits processor | sampled token id, output token count, finish reason |

## Patch Plan Format

When applying this skill, produce:

```text
Question:
  ...

Patch targets:
  1. <boundary>
     why: <algorithm process explained>
     join keys: <ids/counters>
     fields: <small metadata list>

Do not patch:
  <unneeded lower-level boundaries>

Validation:
  <deterministic output equivalence, row-count invariant, state-transition check>
```

## Validation

After adding instrumentation, verify:

- deterministic outputs match with and without wrappers when sampling is disabled
- event counts match the expected runtime structure
- every event has the required join keys
- the target state transition is visible in the trace
- instrumentation does not introduce large tensor copies or unintended device synchronization

For serving systems, validate at least one single-request case and one batched or concurrent case when feasible.

## Anti-Patterns

Avoid:

- patching all candidate functions without a process question
- collecting tensor contents when shape, count, id, or summary is enough
- using repeated `.cpu()` or `.item()` calls in hot loops without a specific need
- adding fields that cannot be joined back to request, step, batch, sequence, forward, or layer ids
- interpreting request-level logs as layer-level behavior
- interpreting layer-level logs as scheduler behavior
