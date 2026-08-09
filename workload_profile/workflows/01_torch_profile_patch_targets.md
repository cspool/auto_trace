# 01. Generic Profiler Evidence To VisiPrune Patch Targets

## Goal

Use a real `torch.profiler` run to discover coarse runtime boundaries, then
confirm the VisiPrune-specific semantic boundaries against source and observed
events before implementing Algorithmic Trace wrappers.

This step has two distinct stages. Profiler evidence alone does not establish
algorithm semantics or source ownership, and this step is not the source of the
final layer schedule or tensor dependencies.

## Existing Skill Used

- `trace-patch-target-discovery`: use the profiler and source evidence to
  choose the smallest semantic patch boundaries, join keys, and metadata fields,
  then validate wrapper equivalence.

This Markdown document is the human-started runbook for Manual Work Unit 1. It
adds the VisiPrune-specific invocation scope, evidence contract, commands, and
script references for the existing Skill; it does not define a new Skill or a
scheduler. The unit stops before producing the authoritative Algorithmic Trace.

## Manual Start And Stop

This document is Manual Work Unit 1. A human starts it explicitly and selects
`REFERENCE_AUDIT` or `FRESH_RUN` for this unit. Completing its commands and
checks does not start Unit 2.

## Stage A: Generic Profiler Evidence

Inspect the request, generation, model-forward, decoder-layer, attention, and
MLP regions using profiler events, shapes, the Chrome timeline, and explicit
coarse `record_function` scopes.

The generic evidence can answer:

- which semantic module boundaries execute in the real request;
- where sequence shapes or operator families change;
- whether automatic stack/module metadata is usable;
- which coarse boundary should receive a smaller semantic wrapper.

It cannot by itself label an ATen region as shallow adjustment, middle
selection, token compaction, or deep removal. In the current eager run,
automatic stack/module metadata can be empty, so source correlation is
mandatory before assigning a VisiPrune meaning.

## Stage B: VisiPrune Semantic Confirmation

The current `torch_profiler_generate_trace.py` is a **hybrid confirmation
tool**, not a purely automatic discovery profiler. It installs known wrappers
around model/layer/attention/MLP boundaries and explicitly wraps
`value_aware_token_selection` before profiling. Consequently:

- generic request/layer/attention evidence is useful for coarse discovery;
- an explicit selection scope proves that the already nominated helper ran;
- the scope name alone must not be presented as an automatically discovered
  source location.

Confirm each candidate using both profiler evidence and the current VisiPrune
source:

| Candidate semantic boundary | Current source boundary | Evidence to confirm | Required Algorithmic Trace event |
|---|---|---|---|
| Generation/forward context | `LlavaLlamaForCausalLM.forward` and the language-model forward | request/forward scopes, input shape, phase | `forward_id`, phase, input/output shape |
| Per-layer workload | decoder-layer `forward` | layer scopes and hidden/q/kv shapes | layer key, `q_len`, `past_len`, `kv_len`, hidden shapes |
| Shallow attention adjustment | `VisiPrunerLlamaAttention.forward`, shallow branch in `repo/llava/model/language_model/custom_modeling_llama.py` (currently around lines 718-730) | layer 0-5 attention scopes and the sum/in-place mask-adjust ops inside them | explicit `shallow_adjust` event or a documented source-confirmed boundary; config, layer, condition, affected ranges |
| Middle selection and deep verification | `VisiPrunerLlamaAttention.value_aware_token_selection` (currently around lines 565-592; called around lines 748-758) | `profile.value_aware_token_selection.layer*` scopes plus `selection_events.csv` results | separate decision events with selected count or boolean result |
| Middle token compaction | language-model layer loop, currently around lines 1622-1629 | q-length change before the next layer and source confirmation of hidden/position/mask compaction | `token_state_transition` from full visual to middle-pruned, joined to its selection decision |
| Deep visual-token removal | language-model layer loop, currently around lines 1631-1636 | q-length change before the next layer, exit state, and source confirmation | `token_state_transition` from middle-pruned to deep-removed, joined to the triggering deep decisions |
| Decode pruned-mask adaptation | language-model layer loop, currently around lines 1616-1620 | a decode run showing layer-dependent `past_len/kv_len` and mask slicing | decode mask/cache-regime event when that process is in scope |

Decision and application are different boundaries. The selection helper decides
which tokens to keep or whether deep exit is allowed; model-level code later
compacts or removes tokens. Do not claim the helper alone captures both events.
VisiPrune does not skip decoder layers in the current reference; it changes the
token workload seen by later layers.

## How To Run

### Reference prefill audit

In `REFERENCE_AUDIT`, inspect the committed output listed below without running
the fixed default tag again. The committed 1-token run is intentionally a
**prefill-only discovery and confirmation probe**. It is sufficient to expose
the current shallow branch, middle/deep decision calls, middle compaction, and
deep removal in prefill. It does not prove the decode pruned-mask/cache branch
and must not be event-wise joined to the committed 32-token Algorithmic Trace.

### Fresh discovery or decode confirmation

In `FRESH_RUN`, always pass a unique `TAG`. Use `TOKENS=1` for a prefill-only
probe, or at least `TOKENS=2` when the decode-specific patch boundary is in
scope:

```bash
RUN_ID="$(date -u +%Y%m%d_%H%M%S)"
TOKENS="${TOKENS:-1}"
TAG="torch_profile_visipruner_full_${TOKENS}tok_${RUN_ID}"
if [ -e "/workspace/VisiPrune/workload_analysis/torch_profile/traces/${TAG}" ]; then
  echo "refusing to reuse profiler directory for ${TAG}" >&2
  exit 1
fi
GPU=1 TOKENS="${TOKENS}" TAG="${TAG}" \
/workspace/VisiPrune/workload_analysis/torch_profile/runners/run_visipruner_full_profile.sh
```

## Review

- `metadata.json`: confirm the run mode/contract, model/config, input, token
  count, device, backend, and profiler options.
- `record_function_scopes.csv`: confirm which request, forward, layer,
  attention, MLP, and source-guided selection scopes actually executed.
- `forward_events.csv` and `layer_events.csv`: inspect forward/layer keys,
  sequence transitions, hidden shapes, cache lengths, and exit state.
- `selection_events.csv`: distinguish middle `none/tensor` results from deep
  boolean verification; this result metadata is not present in the scope name.
- `profiler_events.csv`: identify coarse operator/shape evidence inside and
  between the semantic scopes. Do not infer tensor dataflow from it.
- `module_stack_summary.csv`: record whether automatic stack/module metadata is
  non-empty. When empty, use explicit source confirmation and do not claim
  automatic source ownership.

## Required Patch-target Handoff

For `FRESH_RUN`, write both files under the new reviewed profile directory:

```text
patch_target_plan.md
patch_target_plan.json
```

They are review artifacts; the current profiler script does not generate them
automatically. Both forms must describe the same targets. The JSON should
contain, at minimum:

```text
run_mode, run_id, contract_id, profiler_artifact
question
targets[]:
  target_id
  semantic_process
  qualified_symbol
  source_path and current source region
  branch predicate
  profiler evidence scopes/events
  why this is a VisiPrune boundary
  canonical join keys
  small metadata fields
  implementation_status
do_not_patch[]
validation[]
```

For `REFERENCE_AUDIT`, report these handoff files as missing if they are not
already committed; do not add them inside the read-only reference directory.

The plan must cover the shallow adjustment, middle/deep decisions, model-level
middle compaction, model-level deep removal, and decode mask boundary when
decode is in scope. Generic attention/MLP scopes may be retained as evidence,
but generic MLP is not itself a VisiPrune-specific patch target.

## Wrapper-equivalence Validation

After the Algorithmic Trace wrappers named by the plan are implemented, run the
same deterministic request once without and once with wrappers:

```bash
RUN_ID="$(date -u +%Y%m%d_%H%M%S)"
EQUIVALENCE_TAG="wrapper_equivalence_visipruner_full_32tok_${RUN_ID}"
EQUIVALENCE_OUTPUT="/workspace/VisiPrune/workload_analysis/algorithmic_trace/verification/runs/${EQUIVALENCE_TAG}.json"
if [ -e "${EQUIVALENCE_OUTPUT}" ]; then
  echo "refusing to overwrite equivalence evidence: ${EQUIVALENCE_OUTPUT}" >&2
  exit 1
fi
CUDA_VISIBLE_DEVICES=1 \
/workspace/VisiPrune/workload_analysis/env/run_with_analysis_env.sh \
  /workspace/VisiPrune/workload_analysis/algorithmic_trace/verification/tools/verify_wrapper_equivalence.py \
  --config visipruner-full \
  --max-new-tokens 32 \
  --temperature 0 \
  --tag "${EQUIVALENCE_TAG}"
```

For `REFERENCE_AUDIT`, use the committed equivalence evidence listed under
`Ref`; do not rerun it against a fixed reference tag.

The current verifier automates output-id equality plus forward/layer/selection
event-count checks. It does not validate the full canonical-key set or explicit
decision-to-transition joins. Audit those separately from the generated trace;
if transition events are not emitted, record that instrumentation gap rather
than claiming the verifier covered it. Timing equivalence is not required.

## Ref

### Scripts

- `workload_analysis/torch_profile/tools/torch_profiler_generate_trace.py`
- `workload_analysis/torch_profile/runners/run_visipruner_full_profile.sh`
- `workload_analysis/algorithmic_trace/verification/tools/verify_wrapper_equivalence.py`
- `workload_analysis/env/run_with_analysis_env.sh`

`run_visipruner_full_profile.sh` is safe for `FRESH_RUN` only when the caller
passes a new explicit `TAG`, as in the run section above. Its fixed default tag
must not be treated as a safe entry point or run during `REFERENCE_AUDIT`.

### Reference artifacts

```text
workload_analysis/torch_profile/traces/visipruner_full_1tok_stack_modules/
  metadata.json
  chrome_trace.json
  profiler_events.csv
  profiler_key_averages.csv
  record_function_scopes.csv
  forward_events.csv
  layer_events.csv
  selection_events.csv
  module_stack_summary.csv
  process_view.md

workload_analysis/algorithmic_trace/verification/runs/
  wrapper_equivalence_visipruner_full_32tok.json
```

These artifacts are read-only `REFERENCE_AUDIT` inputs. Missing legacy
`patch_target_plan.md/json` files are reported, not added in place.

## Completion Checks

- Generic profiler discovery and VisiPrune source confirmation are reported as
  separate evidence stages.
- The 1-token reference is labelled prefill-only; decode claims require a
  decode-containing confirmation run.
- For `FRESH_RUN`, `patch_target_plan.md` and `.json` exist and agree on
  boundaries, source anchors, reasons, keys, metadata, and implementation
  status. For `REFERENCE_AUDIT`, their absence is reported rather than repaired
  in place.
- The plan covers shallow adjustment, middle/deep decisions, middle compaction,
  deep removal, and any in-scope decode-mask process.
- Deterministic wrapper equivalence and event/key invariants pass.
- Only small algorithm metadata is requested; profiler or trace evidence is not
  misrepresented as tensor dataflow or automatic source ownership.

## Stop Boundary

After the patch-target evidence package and review result are written, stop.
Do not start Algorithmic Trace, select layers, or invoke either branch. A human
reviews `patch_target_plan.md/json`, wrapper-equivalence evidence, source
anchors, and instrumentation gaps. Manual Work Unit 2 may be started later only
after that review is accepted, using the reviewed files rather than transient
command-session state.
