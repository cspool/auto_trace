---
name: qwen-dcu-fx-reconstruct-visualize
description: Explain and manually visualize pra2026-bh408 Qwen3.5-27B vLLM V1 fixed-input FX process reconstruction files on ROCm/DCU. Use when working with workload_profile/fx traces, fx_process_reconstruction.md/json, fx_process_nodes.csv, fx_graph.py, or fx_graph_module.pt and the user asks for process reconstruction explanation, tensor-dimension visualization, hybrid-attention process diagrams, or dispatch-style character-art interpretation for FX-derived processes.
---

# Qwen DCU FX Process Reconstruction Visualization

## Scope

Use this skill to explain and manually visualize FX-derived process
reconstruction artifacts, especially:

```text
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/fx/traces/<tag>/<event_id>/fx_process_reconstruction.md
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/fx/traces/<tag>/<event_id>/fx_process_reconstruction.json
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/fx/traces/<tag>/<event_id>/fx_process_nodes.csv
/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/fx/traces/<tag>/<event_id>/fx_graph.py
```

This skill is for explanation and manual tensor-axis visualization. It is not
for regenerating FX traces, dispatch traces, ONNX exports, or small-shape Torch
flows.

## Responsibility Boundary

Keep reconstruction and explanation separate:

- The concrete Qwen3.5 FX process reconstruction component is not yet confirmed
  in `pra2026-bh408`. At runtime, resolve or implement it from the current
  source, installed vLLM V1 environment, and actual FX artifact schema without
  guessing a legacy path. It should only reconstruct process groups, process
  code, node tables, node ranges, targets, users, and shape/dtype metadata from
  FX ops.
- Do not add process explanation methods, tensor visualization methods, canned
  Chinese prose, or diagram templates to the reconstruction component.
- Treat `fx_process_reconstruction.md/json`, `fx_process_nodes.csv`, and
  `fx_graph.py` as evidence inputs. The skill is responsible for turning that
  evidence into explanations and visualizations.
- If generated reconstruction files contain only ops and tables, create the
  explanation manually from those ops. Do not re-run or patch the reconstruction
  component just to produce prose.

## Evidence Boundary

Treat FX process reconstruction as a low-level fixed-input ATen DAG, not as
ground-truth Qwen3.5 module/process semantics or vLLM custom-op internals.

Evidence levels:

- Runtime sampling evidence: selected `Qwen3_5DecoderLayer` inputs and required
  replay state were sampled during real Qwen3.5-27B vLLM V1 eager execution on
  the platform-selected ROCm/DCU worker.
- FX DAG evidence: `GraphModule.graph.nodes`, `fx_graph.py`,
  `fx_process_nodes.csv`, and `fx_process_reconstruction.json` describe the
  fixed-input low-level ATen graph. An opaque vLLM/ROCm custom op proves only
  its observed FX inputs, outputs, mutation boundary, and call target, not
  unobserved internal ATen operations.
- Process labels: stage names in `fx_process_reconstruction.md`, such as
  runtime-discovered labels for `full_attention`, `linear_attention`, `rope`,
  `mlp`, or a special token/state process, are reconstruction labels produced
  by rules. Do not treat them as FX official metadata or runtime module
  ownership.

Use this boundary internally while analyzing. Do not add a standalone
`Evidence Boundary` / `证据边界` section to the final output unless the user
explicitly asks for it. If a limitation matters for correctness, state it
briefly inline where the claim is made.

## Hard Requirements

- Do not create visualizations by bulk renderer, script generator, or automated
  diagram tool. Draw process diagrams manually after reading the target
  process.
- Each process visualization's rectangle or tensor representation must
  graphically explain the `怎么做/计算` path of the ops inside that process.
  Different visualized tensors in the same process must have an explicit
  logical relationship. That relationship is expressed through the logical
  relationship between the contents of each rectangle/tensor drawing's
  `Tensor` and `Formula` labels, not deferred to a final prose sentence. Do
  not draw one-op-at-a-time diagrams.
- If the user explicitly asks to explain/visualize every reconstructed
  process, put the explanation and tensor visualization directly next to that
  process's ops, normally immediately after the `### <process>` code block in
  `fx_process_reconstruction.md`. In that mode, use the reconstruction rule,
  node range, grouped op targets, node names, and shapes while analyzing, but
  keep the final output focused on the process explanation, op-grounded
  computation steps, and tensor diagram. Do not add standalone `重建上下文`,
  `证据边界`, `Evidence Boundary`, or `可视化约束` sections unless the user
  explicitly asks for them. The attention and runtime-discovered special
  token/state tensor-axis visualization standards are hard requirements for
  every other process too: use observed shapes, last-two-dimension views for
  high-rank tensors, aligned rectangles, explicit axes, arrows/pointers, and
  flat left/right/top/bottom borders.
- When the user asks for Chinese explanation, all prose explanations outside
  diagrams must be in Chinese. Labels and explanatory text inside diagrams,
  rectangles, tensor boxes, and arrows should remain in English to preserve
  alignment.
- Process explanations must explain the process itself, not merely list the
  reconstruction rule. For each process, answer these three questions in
  Chinese prose before showing the diagram:
  - `是什么`: what this process is in the fixed-input FX DAG;
  - `为什么需要`: why the Qwen3.5 layer or vLLM V1 path needs this process;
  - `怎么做/计算`: how the grouped ATen ops compute or transform tensors.
  The `怎么做/计算` answer must be driven by the process's own ops. Walk through
  the ops in data-dependency or execution order, and for each op explain the
  concrete computation it performs: source tensor or scalar, indexing/view/
  arithmetic/compare/reduction behavior, shape or region effect, and output
  used by later ops. Do not replace this with a high-level process summary.
  If an op is bookkeeping-like, still mention its exact role compactly.
  Reconstruction rules, node ranges, targets, and OP evidence are supporting
  context for analysis. Do not emit separate `重建上下文`, `证据边界`, or
  `可视化约束` blocks in the final output unless explicitly requested.
- Do not infer true module ownership from FX stage labels. Use node names,
  node targets, args/users, and shapes as FX evidence. The current
  `pra2026-bh408/vllm/model_executor/models/qwen3_5.py` source may identify
  candidate Qwen3.5 roles, but it does not turn a reconstruction label into
  runtime ownership.
- Do not present missing ops as FX evidence. If a diagram adds conceptual
  context beyond the observed FX DAG, label that context as conceptual rather
  than observed.
- Prefer creating a companion file such as `fx_process_visualization.md` next
  to the generated reconstruction. Modify `fx_process_reconstruction.md` in
  place only when the user explicitly asks, because it is generated output and
  may be overwritten.
- When the user requests evidence notes, every drawing must include a compact
  note citing FX node indices, names, targets, and relevant shapes. Otherwise
  keep evidence in the op-by-op explanation and avoid a standalone evidence
  block.

## Workflow

1. Choose exactly one FX event directory unless the user explicitly asks for
   multiple layers.
2. Read `fx_process_reconstruction.md` and `fx_process_reconstruction.json`.
   If available, also read `fx_process_nodes.csv` and `fx_graph.py`.
3. Identify the process to explain:
   - If the user names a stage, use that stage.
   - If the user asks for special token/state handling, inspect the
     runtime-discovered process that contains the relevant
     select/index/subtract/compare/reduce or attention-region nodes if present,
     plus the immediately adjacent attention output and output-projection
     nodes. Determine `full_attention` versus `linear_attention` only from the
     current event evidence.
   - If that process is absent, inspect the available full-attention or Gated
     Delta Net nodes and adjacent nodes, and state the limitation inline when
     it matters. Current Qwen3.5 disables multimodal pruning, so never invent a
     special token-selection process that the FX DAG does not contain.
4. Build a process-level explanation:
   - what the process is;
   - why this process is needed;
   - how each grouped ATen op computes the process, in dependency/execution
     order;
   - for every op, state the concrete tensor/scalar input, transform or
     computation, shape/region effect, and output role;
   - input tensor region or token/state set;
   - transformed/compared/reduced tensor region;
   - output tensor, mask, scalar decision, selected index set, mutation, or
     side effect;
   - reconstruction rule, node range, exact FX targets, and evidence boundary
     as internal support only, not as required final-output sections.
5. Draw a tensor-axis / rectangle-axis / region diagram by hand.
6. Add a standalone evidence note only when the user asks for evidence notes;
   otherwise cite node names/targets inline in the op-by-op explanation.
7. Review the drawing for required axes, start/end coordinates, region labels,
   and representative element examples.

## Process Explanation Requirements

Use the process's own FX ops to explain the concrete computation. The following
stage guides are interpretation requirements for this skill, not code-generation
rules for reconstruction components.

- `Runtime FX inputs`: explain that placeholder nodes expose the fixed sampled
  layer inputs and control values. `怎么做/计算` should say that no numerical
  computation happens; placeholders provide flattened token hidden states,
  residuals, positions, output buffers, and any replay-relevant vLLM V1
  forward-context, KV-cache, or Gated Delta Net state tensors that the FX graph
  actually exposes to later ops. Visualize hidden states as `Token x Hidden`,
  positions as a token-axis vector, and masks/cache/state regions only when
  their shapes are materialized in the evidence.
- `Input RMSNorm`: when the graph decomposes the current `Qwen3_5RMSNorm`,
  explain fp32 conversion, square, mean over Hidden, epsilon add, `rsqrt`,
  scaling, dtype conversion, and RMSNorm weight application in the observed
  order. When it is fused, explain only the observed fused input/output and
  target. Draw token rows over Hidden plus a reduced RMS column when that
  reduction is evidenced.
- `Q/K/V projection and head reshape`: for a full-attention layer, explain the
  shared normalized hidden input, observed `qkv_proj`, split into Q-derived
  output gate/K/V regions, Q/gate chunk, Q/K per-head normalization, and
  view/reshape into runtime-local head layouts. For a linear-attention layer,
  apply the same dependency-order depth to `in_proj_qkvz`, the mixed-QKV/Z
  split and Z head reshape, `in_proj_ba`, B/A chunk, and contiguous copies when
  those nodes are exposed. Draw the shared `Token x Hidden` input, the
  observed Q/K/V or Q/K/V/Z/B/A channel partitions, and final head layouts.
- `RoPE position embedding`: explain position-id use, the observed partial/full
  rotary span, Q/K slicing or custom rotary target, rotate-half arithmetic, and
  cos/sin combination only to the extent they appear as FX nodes. Draw the
  `Dh` axis split into rotary and pass-through regions and the resulting Q/K
  layout; if RoPE is opaque, do not draw invented internal arithmetic.
- `QK scores, mask, softmax`: use this guide only when the fixed-input graph
  exposes decomposed Q/K transpose or views, matmul/bmm, scaling, mask or cache
  region handling, softmax, dtype conversion, and clone. Draw attention
  weights over observed `Q_seq x K_seq`. If vLLM V1 exposes only an opaque
  ROCm/DCU attention call, visualize its evidenced input/output boundary and
  do not claim these missing internal ops.
- `QK scores` with `fill_` + `sum` + `copy_`: if and only if those nodes occur,
  explain the observed special-region attention adjust/fold/clear operation.
  The process first uses the evidenced attention-like weights, slices the exact
  query and runtime-discovered special-key regions, sums the selected key mass,
  clears the target block with `fill_`, and copies the folded mass into the
  evidenced representative key column. Draw a `Q_seq x K_seq` region grid with
  KEEP, FOLD, and CLEAR_BY_FILL regions using observed coordinates.
- `QK scores` with `fill_` but without `sum/copy_`: if and only if that pattern
  occurs, explain it as an observed special-region clear-only operation. The
  process slices the exact query/key block and fills it with the observed
  constant. Draw the cleared `Q_seq x K_seq` block.
- `Attention-weighted V and hidden reshape`: for a decomposed full-attention
  graph, explain attention-weight/V expand or views, the value matmul/bmm over
  K, context shape, transpose/clone, and final view back to the observed
  token-hidden layout. Draw weights `[Q,K]`, values `[K,Dh]`, context
  `[Q,Dh]`, and merged hidden `[Q,Hidden]`. For a linear-attention event,
  explain instead the observed `core_attn_out` allocation, inputs and mutation
  boundary of `torch.ops.vllm.gdn_attention_core`, core/Z reshapes, gated
  RMSNorm, and head merge in exact dependency order; keep the custom op opaque
  unless its internals are themselves FX nodes.
- `Runtime-discovered token/state value-aware process` with `nonzero`: when
  those current FX nodes exist, explain last-output-row or other evidenced
  reference-row selection, last-query attention selection, weight-times-V
  contribution, permute/clone/view to token or state rows, special-span
  slicing, subtraction from the broadcast reference row, norm over Hidden,
  threshold comparison, `nonzero`, index extraction, and offset add back to
  original indices. Use the exact observed equivalent at every step; do not
  assume this legacy-shaped pattern exists. Draw current-region rows, delta
  rows, score band, and selected-index output.
- `Runtime-discovered token/state value-aware process` with `index.Tensor`:
  explain the same evidenced contribution reconstruction but restricted to
  runtime-discovered important-token/state or probe indices. Draw
  `P x Hidden` selected probe rows and the delta/compare region.
- `Runtime-discovered token/state value-aware process` without `nonzero` or
  probe index: explain it as delta construction only—an evidenced reference
  row, attention-times-V or current equivalent contribution, special-span
  slice, and subtraction—when those nodes are present.
- `Attention output projection and residual`: explain the observed full-
  attention `self_attn.o_proj` or linear-attention `linear_attn.out_proj`,
  write into the decoder layer's output buffer, optional layer scale, and the
  residual/RMSNorm boundary. Draw projected rows and residual rows on the same
  token and Hidden axes; do not invent a separate add if current fused
  RMSNorm/add nodes are the only evidence.
- `Post-attention RMSNorm`: explain the same evidenced RMSNorm chain as input
  RMSNorm, applied at the attention/residual boundary before MLP. Draw
  residual hidden, RMS reduction column, and normalized MLP input when the
  reduction is decomposed; otherwise draw the fused boundary.
- `MLP and final residual`: explain gate projection, up projection, SiLU on
  gate, elementwise gate/up product, down projection back to Hidden, optional
  layer scale, and the observed final residual handling. Draw token rows
  expanding from Hidden to the runtime-observed intermediate width and
  returning to Hidden.
- `Layer output`: explain that the output node only packages already-computed
  hidden states, residual tensors, exposed cache/state tensors, output-buffer
  aliases, and control scalars. Draw a compact output tuple, not a compute
  diagram.
- `Other FX nodes`: explain them conservatively as grouped residual FX nodes
  not covered by the main process labels. Use exact node targets and users; do
  not assign them to a more specific process without evidence.

## FX Process Categories

Use these categories as optional interpretation aids for runtime-discovered
special token/state processes; they are not mandatory gates for whether a
visualization may be drawn. First keep the event's observed
`full_attention`/`linear_attention` context distinct. Current Qwen3.5 disables
multimodal pruning, so the categories below apply only when the current FX
nodes actually show an equivalent pattern:

- No special token/state handling: no matching reconstructed process and no
  relevant select/sub/cosine/where/any/arange pattern next to attention output.
- Attention-output-side token/state comparison: nodes derive rows from
  attention output or value/state-related tensors, subtract or compare against
  a reference, and reduce to scores or a decision.
- Token/state selection or mask creation: nodes create or use token/state
  indices, `where`, boolean masks, `any`, or score thresholds over the observed
  region axis.
- Deep/probe check: nodes use probe index tensors, arange/index/select, or
  small `P × Hidden` regions before comparison/reduction.
- Attention-region adjust/fold/clear: nodes modify attention-like regions or
  fold mass into an observed special key/query region.

## Visualization Rules

Must use tensor-axis / rectangle-axis / region diagrams. Draw the rectangle
width/height axes or the tensor dimension axes that define the represented
tensor, and do not draw op boxes or flowcharts. When a process handles regions
inside a rectangle, divide the rectangle into regions and label the contents of
each region.

- Show high-dimensional tensors using the last two meaningful dimensions.
  Annotate token, batch, tensor-parallel, and head dimensions in text.
- Use axes such as `Token/state row`, `Probe index`, `Q_seq`, `K_seq`, or
  `Hidden`.
- Use observed shapes from FX metadata or generated code. Do not calculate a
  shape mentally when it is available in evidence.
- Above every visualized rectangle or tensor character-art block, label what
  tensor it represents and how that tensor is obtained. The logical
  relationship between visualized tensors is expressed through the logical
  relationship between the contents of their `Tensor` and `Formula` labels.
  They should use tensor-level names, semantic aliases, shapes/ranges, and
  mathematical formulas. Do not put raw op names, ATen targets, op boxes, or
  op-by-op expressions in the visualization labels or inside the rectangles;
  keep low-level op evidence in the prose `怎么做/计算` explanation.
- Make the rectangle width:height ratio consistent with the represented tensor
  dimension ratio. If needed, compress the ratio for readability and explicitly
  mark the compression.
- Label start and end coordinates for rectangle width/height axes and tensor
  dimension axes. For internal regions, label the region coordinate ranges
  where they matter. Label contents inside each region and enumerate a few
  representative elements as examples.
- Keep tensors with shared axes aligned to the same rectangle width/height.
- Rectangles composed from multiple character-art rows or columns must have
  flat, aligned borders: the left and right vertical borders must stay in the
  same character columns on every row, and the top/bottom borders must span the
  same width. Do not leave protrusions, indentations, jagged sides, or uneven
  internal dividers.
- Use explicit pointers:
  - `──▶` from a label into a rectangle row or band.
  - `◀──` from an explanation note back to the same row or band.
  - `▲` / `▼` under axis ticks or range boundaries.
- Put ASCII-only region IDs inside boxes, such as `CURRENT_REGION_ROWS`,
  `REFERENCE_REGION_ROWS`, `SCORE_BAND`, or `REDUCED_BOOL`.
- Put Chinese interpretation in prose outside diagrams when requested. Keep
  labels and explanations inside rectangle drawings in English unless the user
  explicitly asks otherwise, because mixed-width CJK text can break alignment.
- Include token/axis maps when ranges matter, for example token count, a
  runtime-discovered special token/state span, probe count, Q/K lengths, head
  count, state extents, or Hidden width.

## Runtime-Discovered Token/State Template

For a runtime-discovered token/state comparison over an `R × Hidden` region:

```text
Token/state row axis R=<observed> (compressed)        Hidden dimension
                                                      0                                      <H>
                                                      ▲                                        ▲
region / node                                     ┌────────────────────────────────────────┐    note
current region      <node> R=<observed>       ──▶   │ CURRENT_REGION_ROWS                     │  ◀── current token/state rows
                                                      │ CURRENT_REGION_ROWS                     │
                                                      │ CURRENT_REGION_ROWS                     │
                                                      └────────────────────────────────────────┘
                                                      ┌────────────────────────────────────────┐
reference region    <node> R=<observed>       ──▶   │ REFERENCE_REGION_ROWS                   │  ◀── same R x Hidden coordinates
                                                      │ REFERENCE_REGION_ROWS                   │
                                                      │ REFERENCE_REGION_ROWS                   │
                                                      └────────────────────────────────────────┘
                                                      ┌────────────────────────────────────────┐
delta / compare     <node> R=<observed>       ──▶   │ DELTA_COMPARE_ROWS                      │  ◀── compare or reduce over Hidden
                                                      │ DELTA_COMPARE_ROWS                      │
                                                      │ DELTA_COMPARE_ROWS                      │
                                                      └────────────────────────────────────────┘

                                                      ┌────────────────────────────────────────┐
score band          <node> R=<observed>       ──▶   │ SCORE_PER_REGION_ROW                    │  ◀── one score per observed row
                                                      └────────────────────────────────────────┘
decision scalar     <node> shape=[]           ──▶   [REDUCED_BOOL_DECISION]                     ◀── reduced score-band decision
```

For probe-index comparison over a `P × Hidden` region:

```text
Probe index axis P=<observed> (highly compressed)    Hidden dimension
                                                      0                                      <H>
                                                      ▲                                        ▲
probe selection     <node> P=<observed>        ──▶   ┌────────────────────────────────────────┐  ◀── selected probe rows
                                                      │ SELECTED_PROBE_ROWS                    │
                                                      └────────────────────────────────────────┘
reference probe     <node> P=<observed>        ──▶   ┌────────────────────────────────────────┐  ◀── same P x Hidden coordinates
                                                      │ REFERENCE_PROBE_ROWS                   │
                                                      └────────────────────────────────────────┘
delta / compare     <node> P=<observed>        ──▶   ┌────────────────────────────────────────┐  ◀── compare or reduce over Hidden
                                                      │ PROBE_DELTA_COMPARE                    │
                                                      └────────────────────────────────────────┘
score band          <node> P=<observed>        ──▶   ┌────────────────────────────────────────┐  ◀── one score per probe index
                                                      │ SCORE_PER_PROBE_INDEX                  │
                                                      └────────────────────────────────────────┘
decision scalar     <node> shape=[]            ──▶   [REDUCED_BOOL_DECISION]                     ◀── reduced probe-score decision
```

For an observed attention-region adjust/fold/clear over `Q_seq × K_seq`, use a
segment map plus a region grid:

```text
K_seq
         0      k_special_start   k_special_end     End
       ┌───────┬─────────────────────────────────┬───────┐
     0 │       │                                 │       │
       ├───────┼─────────────────────────────────┼───────┤ Q_seq
q_mid  │       │ CLEAR_OR_KEEP_REGION            │       │
       ├───────┼───────────────┬─────────────────┼───────┤
q_tail │       │ FOLD_OR_INJECT │ CLEAR_OR_KEEP   │       │
       └───────┴───────────────┴─────────────────┴───────┘
```

## Optional Evidence Note Format

Use this only when the user explicitly asks for evidence notes or when a
separate evidence block is necessary to avoid ambiguity. By default, do not
print this block; keep node/target/shape support inline in `怎么做/计算`.

```text
evidence:
- #<index> <name> target=<aten-or-custom-op target>, args=[...], users=[...], shape=<observed>
- #<index> <name> target=<aten-or-custom-op target>, args=[...], users=[...], shape=<observed>
interpretation:
- The diagram groups these FX nodes as <process>. This grouping is manual and
  is not FX-provided module/process metadata.
```

## Quality Bar

- Remember internally that FX process labels are reconstructed labels, not
  runtime module ownership. Mention this in the final output only when it is
  directly relevant to a claim or the user asks for evidence boundaries.
- The diagram must be process-level and tensor-axis based.
- Every shape, range, node, and tensor-like region must be backed by the FX
  reconstruction files.
- If only low-level ATen DAG or opaque vLLM/ROCm custom-op evidence is
  available, account for that limitation internally and state it inline only
  when needed for correctness.
- Before finishing, ensure the drawing includes required axis start/end
  coordinates, region labels, and representative element examples when
  applicable.
