---
name: qwen-dcu-dispatch-reconstruct-visualize
description: Reconstruct and audit pra2026-bh408 Qwen3.5-27B vLLM V1 dispatch layers on ROCm/DCU from TorchDispatch CSVs into evidence-aligned small-shape tensor computations and per-stage ONNX files. Use when working under workload_profile/dispatch with filtered dispatch CSVs, per-event visualization workspaces, reconstruction generators, and dispatch ONNX artifacts.
---

# Qwen DCU Dispatch Layer Reconstruction To ONNX

## Principle

Reconstruct each layer event from its own dispatch evidence. Do not reuse one event's toy flow for all events unless the dispatch audit proves the layer type, stage split, and process semantics match.

Treat `dispatch_ops.csv` as the source of truth. The reconstructed process, small-shape process, sub-process split, module split, tensor-id dataflow, and ONNX stages must cover the operations and runtime modules present in that event's dispatch rows; do not accept summaries that only identify broad Qwen3.5 stages while omitting dispatch ops/modules or changing dependencies. The checked-in Qwen3.5 configuration and vLLM source may corroborate names and dimensions, but they do not replace dispatch evidence.

The reconstructed process and the split sub-process collection must not omit any op row from that event's `dispatch_ops.csv`. Every `event_op_index` must appear in a deterministic op-coverage artifact and must be traceable to runtime module evidence, tensor-id inputs/outputs, and either a dispatch-supported stage/sub-process or an explicitly documented non-compute/bookkeeping category.

Hard op-coverage rule: every non-header row in `dispatch_ops.csv` is exactly one observed dispatch op. `process_index.md` must explicitly enumerate every such op row by `event_op_index`; no op may be omitted, including view/slice/select, inplace mutation, scalar, metadata, allocation, custom-op boundaries, and non-compute/bookkeeping ops. The same op may be referenced more than once when it genuinely participates in multiple explanations, but coverage is valid only if the complete dispatch `event_op_index` set is present. Stage summaries, module ranges, prose descriptions, or broad process names may supplement the table, but they do not count as coverage unless each covered `event_op_index` is listed explicitly.

Data dependencies must be derived from `input_tensor_ids` and `output_tensor_ids` in `dispatch_ops.csv`: an observed producer-consumer edge exists only when an earlier row's `output_tensor_ids` contains the same tensor id as a later row's `input_tensor_ids`. Do not infer data dependencies from op names, shapes, stage names, or module names when tensor ids are available.

The current workspace groups code and outputs by category. Keep dispatch profile inputs, reconstruction tools, generated reports, Torch flows, and ONNX artifacts under `workload_profile/dispatch/`.

## Canonical Paths

For the Qwen3.5/vLLM V1 workspace, prefer these paths:

```text
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/dispatch/profiles/<runtime-confirmed-tag>/dispatch_ops.csv
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/dispatch/visualize/<event_id>/
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/dispatch/layer_pipeline/
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/dispatch/tools/
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/dispatch/templates/
```

Use `workload_profile/dispatch/visualize/<event_id>/` as the user-facing layer workspace. Each event directory should keep its dispatch review, generated Torch flow, ONNX files, and manifest together.

The current source tree is `/public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408`. The concrete filtered-profile tag, event-key spelling, reconstruction tools, and templates are not yet confirmed; resolve them at runtime from the real profile, current source, and installed vLLM V1 environment without weakening any requirement below.

## Workflow

1. Enumerate layer/event directories in numeric/event order using the runtime-confirmed event-key mapping:

```bash
PROJECT_ROOT=/public/home/tangyu408/Qwen_DCU_Worker_0
find "${PROJECT_ROOT}/workload_profile/dispatch/visualize" \
  -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
```

2. For each `event_id` or runtime-confirmed equivalent, read only that event's dispatch rows from `dispatch_ops.csv`. Preserve `event_op_index` order.

2a. Build the event tensor dataflow directly from `input_tensor_ids` and `output_tensor_ids`. Emit `dispatch_review/tensor_dataflow.json`, `dispatch_review/tensor_dataflow_edges.csv`, and `dispatch_review/tensor_dataflow.md`. The reconstructed stage/module splits must expose dispatch tensor-id inputs and outputs from those same columns.

2b. Build a complete dispatch op coverage table from the event rows. Emit `dispatch_review/dispatch_op_coverage.json`, `dispatch_review/dispatch_op_coverage.csv`, and `dispatch_review/dispatch_op_coverage.md`. This table must cover every `event_op_index` from the event rows and connect each op to its runtime module split, tensor-id inputs/outputs, and stage/sub-process evidence when present.

2c. Write or refresh `process_index.md` as a strict op-by-op index over the same event rows. The file must include an explicit per-op table keyed by `event_op_index` and must list every data row from `dispatch_ops.csv` at least once. It must expose the op name/schema, runtime module evidence, input/output tensor ids, assigned process/sub-process, and whether the row is compute, mutation/view, data movement, custom-op boundary, or explicitly documented bookkeeping. Do not collapse multiple dispatch rows into a single unenumerated stage entry.

3. Infer dimensions from tensor shapes, excluding token counts from hidden-size candidates:

- Resolve `request_id`, `engine_step_id`, `forward_id`, `layer_idx`, `layer_occurrence`, `phase`, `q_len`, `kv_len`, and `layer_type` from runtime-confirmed CSV columns or an explicit alias mapping.
- Infer `hidden` from the final dimension of flattened `[num_tokens, hidden]` or equivalent unflattened tensors, excluding `q_len/kv_len`; the current Qwen3.5-27B config declares `hidden_size=5120`.
- Infer local and global head/state dimensions from rows and the actual tensor-parallel topology. The unsharded config declares 24 query heads, 4 KV heads, and `head_dim=256` for full attention, plus 16 key heads, 48 value heads, 128-dimensional keys/values, and convolution kernel size 4 for Gated Delta Net.
- Infer `ffn` from the larger MLP projection shape; the current dense config declares `intermediate_size=17408`, but recorded local shapes remain authoritative.

4. Derive expected stages from dispatch ops:

- Always expect shared decoder stages when evidence exists:
  `input_rmsnorm`, the observed attention-family path, `attention_output`, `mlp`.
- Add full-attention stages only when dispatch and runtime modules prove a `full_attention` layer:
  `qkv_projection`, Q/K normalization, partial RoPE, attention, output gate, and output projection.
- Distinguish full-attention prefill, decode, paged-cache, and ROCm/DCU backend variants from the observed phase, shapes, cache tensors, and custom-op/module evidence.
- Add Gated Delta Net stages only when dispatch and runtime modules prove a `linear_attention` layer:
  fused Q/K/V/Z and B/A projections, convolution/state preparation, GDN core, gated normalization, and output projection.
- Distinguish GDN prefill, recurrent decode, speculative, or packed-decode variants from observed ops and state tensors. Preserve an observed `torch.ops.vllm.gdn_attention_core` boundary without fabricating unobserved internal ATen rows.
- Treat full attention as rectangular when `q_len != kv_len`; the small-shape ONNX must preserve `q_small x kv_small` semantics when explicit score tensors exist. For an opaque backend, preserve the proved query/cache boundary without inventing a score tensor.

The current Qwen3.5 source disables multimodal pruning, so do not invent pruning-only visual adjustment, token-selection, early-exit, or similarity-check stages.

5. Build the small-shape PyTorch flow according to the expected stages, not according to a fixed template:

- Use small dimensions that preserve semantics, for example `hidden=32`, `ffn=64`; for full attention use `q_heads=6`, `kv_heads=1`, `head_dim=8`; for GDN use `key_heads=2`, `value_heads=6`, key/value head dimensions of 8, and convolution kernel size 4.
- For prefill full-attention events, use `q_small=kv_small=16` when the dispatch evidence is square.
- For decode/cache full-attention events, use `q_small=1` and `kv_small>1` such as `kv_small=8` or `16` when that rectangular relation is proved.
- Include only dispatch-supported optional stages.
- For full attention, implement the specific Q/K normalization, partial RoPE, output-gate, cache, and backend boundaries proven by dispatch evidence.
- For Gated Delta Net, implement the evidenced projection, convolution/state, core, gated-normalization, and output sub-processes as separate functions and ONNX stages; keep an opaque custom op's evidence limit explicit.
- For full-attention cache or GDN state transitions, implement each proved transition as its own function and ONNX stage before its consumer.
- Preserve operator and data dependencies from dispatch: stage ordering, stage inputs/outputs, flattened-token layouts, grouped-query relationships, rectangular attention shapes, cache/state inputs, variant-specific outputs, and custom-op boundaries must follow the event's observed op sequence and tensor shapes.
- Preserve tensor-id boundaries from dispatch: generated process manifests, module split files, stage evidence, and ONNX code-review maps must include input/output tensor ids derived from `dispatch_ops.csv` `input_tensor_ids` and `output_tensor_ids`.

6. Split code by function/sub-process and export one ONNX per stage. A complete event should have:

```text
workload_profile/dispatch/visualize/<event_id>/dispatch_review/
workload_profile/dispatch/visualize/<event_id>/torch_flow/
workload_profile/dispatch/visualize/<event_id>/onnx/
workload_profile/dispatch/visualize/<event_id>/layer_manifest.json
```

7. Write evidence-first reports and manifests:

```text
dispatch_review/summary.json
dispatch_review/tensor_compute_process.md
dispatch_review/tensor_dataflow.json
dispatch_review/tensor_dataflow_edges.csv
dispatch_review/tensor_dataflow.md
dispatch_review/dispatch_op_coverage.json
dispatch_review/dispatch_op_coverage.csv
dispatch_review/dispatch_op_coverage.md
process_index.md
dispatch_review/process_manifest.json
dispatch_review/process_code_index.md
dispatch_review/onnx_code_index.md
dispatch_review/onnx_code_map.json
dispatch_review/onnx_code/<onnx_stem>_code.md
onnx/manifest.json
onnx/<onnx_stem>_code.md
layer_manifest.json
```

For every ONNX file, write a corresponding code-review page under `dispatch_review/onnx_code/` and mirror the same page directly under `onnx/`. Each page must identify the ONNX file, the stage, ONNX inputs/outputs, the export wrapper in `torch_flow/export_stage_onnx.py`, the primary `torch_flow` implementation file(s), a code explanation, review comments, dispatch evidence notes, the relevant source snippets, and the dispatch tensor ids at that stage boundary.

## Audit Requirements

When reviewing or claiming completion, audit each event against its own `dispatch_ops.csv` rows with these minimum standards:

1. The reconstructed process and small-shape process must not omit operations or runtime modules present in that event's dispatch rows. Every dispatch op should be accounted for by a stage/sub-process, a module split entry, a tensor dataflow entry, or an explicitly documented non-compute/bookkeeping category.
2. `process_index.md` is a mandatory hard-coverage artifact. Count the event's `dispatch_ops.csv` data rows excluding the header, and verify that every dispatch `event_op_index` appears in `process_index.md`. Missing, renamed, or range-only op coverage is blocking; duplicate references are allowed when the op is explicitly listed and no dispatch op is omitted.
3. The sub-process collection must not omit runtime modules from the runtime-confirmed module fields/module stack evidence. Regenerate or verify `dispatch_review/module_split.{json,csv,md}` directly from dispatch rows, and check that `event_op_indices` cover the full contiguous `event_op_index` range with no omissions. Module split entries must include dispatch tensor-id inputs and outputs derived from the rows in that module.
4. Operator dependencies and data dependencies must align with dispatch evidence. Verify stage order, producer/consumer relationships, input/output tensor shapes, attention-family and cache/state variants, and module-scoped op ranges against observed `event_op_index`, op name/schema, args, outputs, and module fields.
5. Tensor-id dependencies must be recomputable from `dispatch_ops.csv`: for each op row, each dependency edge must match a prior `output_tensor_ids` producer and current `input_tensor_ids` consumer. Validate `dispatch_review/tensor_dataflow.json` and `tensor_dataflow_edges.csv` against this recomputation.
6. Stage/process reconstruction artifacts must use dispatch tensor ids as their documented inputs and outputs: `process_manifest.json`, `layer_profile.json`, `process_index.md`, `process_code_index.md`, `onnx_code_map.json`, and per-ONNX code pages should expose the relevant dispatch `input_tensor_ids` and `output_tensor_ids`.
7. The dispatch op coverage artifact must be recomputable from the same event rows and must cover the full contiguous `event_op_index` set with no omissions. The reconstructed process and split sub-process manifests must include this coverage summary and reference the coverage artifact paths.

Use or create deterministic audit tooling for these checks when possible. No compatible project-local auditor is currently confirmed; at runtime, prefer a compatible `workload_profile/dispatch/layer_pipeline/audit_layer_reconstruction.py` if present, otherwise implement the deterministic equivalent. Treat any reported issue as blocking until fixed or explicitly justified from dispatch evidence.

## Core Evidence Patterns

Use these source-backed patterns as stage candidates, while requiring the exact op schemas and tensor ids from real dispatch rows:

- `input_rmsnorm`: the `Qwen3_5DecoderLayer.input_layernorm` boundary and its observed `Qwen3_5RMSNorm` fused op or decomposed dtype/pow/mean/add/rsqrt/mul rows.
- `full_attention/qkv_projection`: `self_attn.qkv_proj`, followed by observed split/view/chunk operations for Q, output gate, K, and V with runtime-local shapes.
- `full_attention/qk_norm_rope`: `self_attn.q_norm`, `self_attn.k_norm`, then `self_attn.rotary_emb`, preserving flattened-token and partial-rotary behavior.
- `full_attention/cache`: runtime-selected vLLM V1 paged-cache reads/writes or backend cache boundaries; do not require an eager K/V `cat.default` unless dispatch records it.
- `full_attention/attention`: the `self_attn.attn` boundary and its ROCm/DCU backend/custom op; an opaque call does not prove unobserved internal matmul/softmax rows.
- `full_attention/output_gate`: sigmoid of the Q-derived gate and elementwise multiplication with the attention result when those rows are observed.
- `linear_attention`: `linear_attn.in_proj_qkvz`, `linear_attn.in_proj_ba`, observed split/reshape/cat, `torch.ops.vllm.gdn_attention_core`, and evidenced convolution/GDN/state-update ops.
- `attention_output`: the observed GDN gated RMS normalization or full-attention output, followed by `linear_attn.out_proj` or `self_attn.o_proj` and the residual/RMSNorm boundary.
- `mlp`: post-attention RMSNorm, fused or split gate/up projection, `silu`/gated multiplication, down projection, and observed residual behavior.

## Existing Project Commands

The Qwen3.5 source and ROCm/DCU environment binding are confirmed, but compatible reconstruction, review, and audit entry points are not. Resolve or implement their concrete paths and CLIs at runtime before using these starting points:

```bash
PROJECT_ROOT=/public/home/tangyu408/Qwen_DCU_Worker_0
SOURCE_ROOT="${PROJECT_ROOT}/pra2026-bh408"
source "${SOURCE_ROOT}/scripts/cscc_gfx936_env.sh"
SOURCE_CSV="${PROJECT_ROOT}/workload_profile/dispatch/profiles/<runtime-confirmed-tag>/dispatch_ops.csv"
OUT_DIR="${PROJECT_ROOT}/workload_profile/dispatch/visualize"
RECONSTRUCTION_DRIVER="${RECONSTRUCTION_DRIVER:?set the runtime-confirmed reconstruction driver}"
```

Invoke the confirmed driver with `SOURCE_CSV`, `OUT_DIR`, and the ordered event ids using its recorded real CLI.

```bash
REVIEW_TOOL="${REVIEW_TOOL:?set the runtime-confirmed reconstruction reviewer}"
```

Invoke the confirmed reviewer against the same `SOURCE_CSV` and event output root using its recorded real CLI.

```bash
AUDIT_TOOL="${AUDIT_TOOL:?set the runtime-confirmed strict layer auditor}"
```

Invoke the confirmed auditor against the same `SOURCE_CSV` and event output root using its recorded real CLI.

If the review reports missing stages or `needs_revision`, update the runtime-confirmed generator/template before claiming the event is complete.

## Completion Checks

Before reporting completion, verify all of the following:

- Every requested `workload_profile/dispatch/visualize/<event_id>` has `dispatch_review/summary.json`, `dispatch_review/tensor_compute_process.md`, `dispatch_review/onnx_code_index.md`, `dispatch_review/onnx_code_map.json`, `torch_flow/`, `onnx/manifest.json`, and `layer_manifest.json`.
- Every requested event has `process_index.md`, and it explicitly lists every non-header `dispatch_ops.csv` row by `event_op_index`; missing, range-only, or stage-summary-only coverage is a hard failure, while duplicate explicit references are allowed.
- Every ONNX entry in `onnx/manifest.json` has exactly one entry in `dispatch_review/onnx_code_map.json`, one Markdown page under `dispatch_review/onnx_code/`, and one mirrored Markdown page directly under `onnx/` with corresponding `torch_flow` source, explanation, comments, tensor ids, and dispatch evidence notes.
- Every generated stage has dispatch evidence or is explicitly marked as a non-evidence convenience stage such as `full_flow`.
- Generated stages match dispatch-derived expected stages except optional `full_flow`.
- The reconstructed process and small-shape process account for every dispatch op/module in each requested event, with no missing Qwen3.5 runtime modules in `module_split`.
- The sub-process collection covers all dispatch-derived modules, and `module_split` coverage includes the full contiguous `event_op_index` set for the event with no omissions.
- `dispatch_review/dispatch_op_coverage.*` exists, covers every `event_op_index` with no omissions, and is referenced by `process_manifest.json`, `layer_profile.json`, `process_index.md`, `process_code_index.md`, and `layer_manifest.json`.
- Operator dependencies and data dependencies in the reconstruction align with dispatch evidence: stage order, input/output shapes, full-attention/GDN and cache/state variants, custom-op boundaries, and producer/consumer transitions match the observed `dispatch_ops.csv`.
- Tensor-id dependencies are derived from `input_tensor_ids`/`output_tensor_ids` and are present in `dispatch_review/tensor_dataflow.*`, module split tensor-id fields, process manifests, stage evidence, and ONNX code maps/pages.
- The strict event audit, using the runtime-confirmed deterministic auditor, reports pass for every requested event.
- The runtime-confirmed reconstruction reviewer has been run and any `needs_revision` results are reported honestly.
- ONNX models pass `onnx.checker.check_model`.
- No `.pyc` or `__pycache__` remains under `workload_profile/dispatch`.

Never mark the job done if only generic full-attention stages are present while dispatch-supported Qwen3.5 Gated Delta Net, cache/state, output-gate, backend/custom-op, or other optional stages are missing.
