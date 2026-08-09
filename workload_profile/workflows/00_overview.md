# 00. Shared Reference And Review Contract

## Goal

Define the shared contract for the workload-analysis workflow and keep the
evidence levels used by each manually started work unit separate.

This document is shared reference and review guidance. It defines run modes,
canonical contracts, event keys, evidence boundaries, and set-conservation
gates used inside the human-started work units. It is not a runnable skill,
command entry point, router, or scheduler.

## Run Modes

Every review or execution must declare exactly one mode.

### `REFERENCE_AUDIT`

- Audit committed artifacts without rerunning or overwriting them.
- Read the run contract from the artifact metadata and report missing fields.
- Do not assume artifacts from different tags are event-wise comparable. In
  particular, the committed 1-token torch profile is a prefill patch-boundary
  discovery run, while the committed 32-token Algorithmic Trace is the full
  layer-schedule reference.
- Numeric expectations such as the current 35 selected events apply only to the
  named reference contract.

### `FRESH_RUN`

- Use a new, unique `run_id`/tag and refuse to reuse an existing output
  directory.
- Write the canonical run contract before interpreting or comparing outputs.
- Record the exact source trace path in the owning unit's evidence package; a
  later manually started branch must read it from that package rather than a
  `latest_*` pointer or tool default.
- Revalidate wrapper equivalence, event-set conservation, and selected-event
  coverage for the new run.

## Canonical Run Contract

Record this contract in the run metadata or a sidecar JSON and refer to it from
each handoff artifact:

```text
run_mode                 REFERENCE_AUDIT | FRESH_RUN
run_id                   unique tag within workload_analysis
contract_id              stable digest or explicit identifier for this contract
source_revision          repository/model revision when available
model_path, model_base
config, pruning_config
image_path, image digest when available
prompt, conversation mode
max_new_tokens
temperature, do_sample, seed
dtype
attention/decode backend, use_flash_attn
use_cache and other generation options
logical GPU/device and distributed rank when applicable
```

Comparable or replayed runs must have matching contract fields, except for a
field whose intentional difference is named in the experiment question. A
short profiler discovery probe and a full Algorithmic Trace may use different
token counts, but they must not be joined as if their runtime events came from
the same run.

Unit 2 must add a selection handoff alongside this run contract. Record the
absolute reviewed patch-plan, source-trace, and canonical selected-manifest
paths; their SHA-256 digests; selection flags; ordered event IDs; event-key-set
digest; `expected_selected_event_count`; and the verified `layer_occurrence`
contract. For the named 32-token reference contract the expected count is `35`;
for another contract it is the reviewed Unit-2 result, not a hard-coded value
chosen by a later branch.

Use the workload-analysis runtime wrapper for scripts that load VisiPrune or
LLaVA:

```text
/workspace/VisiPrune/workload_analysis/env/run_with_analysis_env.sh <script> ...
```

## Canonical Event Keys

Use the following names in plans and handoffs, even when a legacy artifact uses
aliases:

```text
forward key   = (contract_id, forward_id)
layer key     = (contract_id, forward_id, layer_idx, layer_occurrence)
decision key  = (layer key, selection_event_index)
transition key= (layer key, transition_event_index)
```

- `layer_occurrence` is `0` only after confirming one call per
  `(forward_id, layer_idx)`; otherwise it is a monotonic per-key counter.
- Legacy `input_id` means `forward_id`.
- Legacy `layer_id` means `layer_idx`.
- For the current single-occurrence reference,
  `event_id = input{forward_id}_layer{layer_idx}`. This string is local to its
  `contract_id`; it is not globally unique across runs.
- Decision events and token-state transition events are distinct. A middle/deep
  decision must be joinable to the later compaction or removal event that
  applies it.

## Event Families And Conservation

Treat the following as explicit event sets:

```text
F = forward events
L = layer-call events
S = VisiPrune middle/deep decision events
R = VisiPrune token-state transition events when explicitly instrumented
T = canonical selected-layer manifest
D = event ids observed in a filtered DispatchMode trace
X = event ids observed in a selected-layer FX trace
```

Before a handoff is complete, verify:

- JSON and CSV representations of `F`, `L`, and `S` agree on their canonical
  keys and shared fields.
- Every layer key is unique, or `layer_occurrence` disambiguates it.
- For the current 32-layer model, every complete forward has 32 layer events;
  any exception must be explained by an explicit control-flow event.
- Every emitted `S` and `R` event joins to a valid forward/layer context, and
  every emitted applied transition records its triggering decision when one
  exists. If `R` is absent, record `transition_capture_status=missing`; a
  q-length change may locate a boundary but does not prove the decision-to-
  application join.
- `keys(T) ⊆ keys(L)`, every manifest `event_id` is unique, and its
  `phase/q_len/past_len/kv_len` matches the source layer event.
- A manually started Dispatch branch independently satisfies
  `D = event_ids(T)`. A manually started FX branch independently satisfies
  `X = event_ids(T)`. Neither branch waits for or validates the other.
- Row-count checks are accompanied by key-set checks. Equal counts alone do not
  prove conservation.

## Evidence Boundaries

| Evidence source | What it proves | What it does not prove |
|---|---|---|
| `torch_profile` | Profiler events, timeline, shape hints, memory, coarse hotspots, and explicit `record_function` scope execution. | Dynamic VisiPrune schedule, tensor-id dataflow, source ownership from empty automatic stacks, or strict process reconstruction. |
| `algorithmic_trace` | Real dynamic schedule: `forward_id`, layer, phase, `q_len`, `kv_len`, selection/deep-exit decisions, state transitions when instrumented, and theoretical workload. | Wall-clock kernel timing or tensor producer-consumer dataflow. |
| DispatchMode | Eager runtime ATen ops for selected layers, with tensor ids and metadata when recorded. | A graph by itself; dependencies must be reconstructed from tensor ids. |
| FX | Fixed-input ATen DAG with node args/users and GraphModule artifacts. | Full eager runtime coverage or official module/process ownership. |

## Review Scope

- Unit 1 applies this contract while reviewing profiler evidence and its
  patch-target package.
- Unit 2 applies it while reviewing Algorithmic Trace and selection provenance.
- A later manually started branch applies it again to the exact Unit-2 evidence
  package named by its operator.

This section describes review ownership only. It does not launch a later work
unit or decide which branch a human will start.

## Ref

### Scripts

None. This shared contract is review reference only. Runtime commands belong to
the manually started work unit that owns the evidence-producing action.

### Reference artifacts

- `workload_analysis/torch_profile/traces/visipruner_full_1tok_stack_modules/`
  is the named prefill-only profiler reference.
- `workload_analysis/algorithmic_trace/traces/fresh_forward_visipruner_full_32tok/`
  is the named 32-token Algorithmic Trace reference.
- `workload_analysis/dispatch/profiles/filtered_dispatch_visipruner_full_32tok/`
  and
  `workload_analysis/fx/traces/fx_filtered_dispatch_layers_specialized/`
  contain the named 35-event branch references.

These paths are inputs to `REFERENCE_AUDIT`, not writable or safe fresh-run
destinations.

## Shared Completion Checks

- The run mode and canonical run contract are explicit.
- Cross-run claims name which contract fields match and which intentionally
  differ.
- Patch, trace, selection, and branch artifacts use the canonical key mapping.
- Event-family conservation checks pass, including key sets rather than only
  row counts.
- Each layer selected for deeper trace has a reason tied to Algorithmic Trace or
  explicitly named profiler/source evidence.
- No conclusion treats profiler events, algorithm schedule, eager ATen ops,
  fixed-input FX DAG, and performance timing as the same evidence type.

## Related Design Decision

See `workflow_goal_decomposition_and_project_adaptation.md` for the recorded
design contract about target-project adaptation, stage-level Goal Contracts,
per-event visualization quality gates, workflow state, and the Codex `/goal`
command surface. See
`project_adaptation/adaptation_stage_implementation_plan.md` for the
implemented seven-Goal bootstrap, manifest, deterministic gates, and offline
tests. The seven formal adaptation Goals have not yet been run, so their six
project Skills and runtime scheduler are not current workflow evidence.
