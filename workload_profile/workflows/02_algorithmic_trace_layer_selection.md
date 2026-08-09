# 02. Layer-wise Algorithmic Trace And Canonical Layer Selection

## Goal

Implement the human-reviewed patch targets from Unit 1, capture a real
layer-wise Algorithmic Trace, and materialize exactly one canonical
selected-event manifest for later, separately started DispatchMode or FX work.

This step answers:

- Which canonical forward/layer events happened in the real request?
- What are the dynamic `q_len`, `kv_len`, and `past_len` values?
- Where did VisiPrune shallow adjustment, middle selection, token compaction,
  deep verification/removal, and decode cache-regime effects occur or become
  visible?
- Which source events are selected for deeper op-level trace, and why?

## Existing Skills Used

- `trace-patch-target-discovery`: apply the reviewed patch plan while checking
  that the implemented boundaries, join keys, metadata, and wrapper-equivalence
  evidence still satisfy its contract; do not reopen Unit 1 target discovery.
- `visipruner-trace-dispatch-profile`: apply only its end-to-end Algorithmic
  Trace and selected-layer responsibilities in this unit. Its filtered
  Dispatch capture responsibility belongs to the separately started 3.1 -> 4.1
  runbook.

This Markdown document is the human-started runbook for Manual Work Unit 2. It
adds the exact handoff, trace-selection contract, commands, and script
references for those existing Skills; it does not define a new Skill or a
scheduler. The unit stops before running a full DispatchMode or FX trace.

## Manual Start And Stop

This document is Manual Work Unit 2. A human starts it explicitly only after
reviewing and accepting Unit 1. The operator supplies the reviewed
`patch_target_plan.json` path and selects `REFERENCE_AUDIT` or `FRESH_RUN` for
this unit. Completing Unit 2 does not start either later branch.

## Run Mode And Contract

Follow `00_overview.md` and declare `REFERENCE_AUDIT` or `FRESH_RUN`.

- In `REFERENCE_AUDIT`, inspect the committed 32-token VisiPrune trace and its
  committed 35-event manifests without writing them again.
- In `FRESH_RUN`, use a unique trace tag and a second unique manifest tag. Record
  the exact trace path in this unit's evidence package.
- A Step-1 1-token profiler run may justify prefill patch boundaries, but its
  events are not joined to this 32-token run. The handoff is the reviewed
  `patch_target_plan`, not shared `forward_id` values.
- The committed reference profile predates the required
  `patch_target_plan.md/json`. In `REFERENCE_AUDIT`, use the documented
  source-confirmed boundaries only as a legacy fallback and report the missing
  plan as a provenance gap. In `FRESH_RUN`, both reviewed plan files are a hard
  entry requirement.

## Run A Fresh Algorithmic Trace

Use the direct command below because it accepts the unique tag required by
`FRESH_RUN`.

```bash
RUN_ID="$(date -u +%Y%m%d_%H%M%S)"
TRACE_TAG="fresh_forward_visipruner_full_32tok_${RUN_ID}"
CONTRACT_ID="${CONTRACT_ID:-${TRACE_TAG}}"
TRACE_DIR="/workspace/VisiPrune/workload_analysis/algorithmic_trace/traces/${TRACE_TAG}"
if [ -e "${TRACE_DIR}" ]; then
  echo "refusing to reuse trace directory: ${TRACE_DIR}" >&2
  exit 1
fi

/workspace/VisiPrune/workload_analysis/env/run_with_analysis_env.sh \
  /workspace/VisiPrune/workload_analysis/algorithmic_trace/tools/visipruner_algorithmic_trace.py \
  --config visipruner-full \
  --max-new-tokens 32 \
  --temperature 0 \
  --gpu 1 \
  --tag "${TRACE_TAG}"

TRACE_JSON="${TRACE_DIR}/algorithmic_trace.json"
```

Optional dense baseline, with its own unique tag:

```bash
: "${RUN_ID:?run or set the fresh-run id first}"
DENSE_TAG="fresh_forward_dense_eager_32tok_${RUN_ID}"
DENSE_DIR="/workspace/VisiPrune/workload_analysis/algorithmic_trace/traces/${DENSE_TAG}"
if [ -e "${DENSE_DIR}" ]; then
  echo "refusing to reuse dense trace directory: ${DENSE_DIR}" >&2
  exit 1
fi
/workspace/VisiPrune/workload_analysis/env/run_with_analysis_env.sh \
  /workspace/VisiPrune/workload_analysis/algorithmic_trace/tools/visipruner_algorithmic_trace.py \
  --config dense-eager \
  --max-new-tokens 32 \
  --temperature 0 \
  --gpu 1 \
  --tag "${DENSE_TAG}"
```

## Algorithmic Trace Output

```text
workload_analysis/algorithmic_trace/traces/<TRACE_TAG>/
  algorithmic_trace.json
  layer_trace.csv
  selection_trace.csv
  operator_flops.csv
```

## Validate The Trace Before Selection

- `algorithmic_trace.json` and the CSVs must agree on forward/layer/decision
  keys and shared sequence fields.
- Every current reference forward must contain layers `0..31`; the committed
  trace therefore contains 32 forwards and 1024 layer events.
- `selection_trace.csv` must distinguish middle `none/tensor` decisions from
  deep boolean verification. Dense selection output may be empty.
- Confirm the prefill transitions `624 -> 58 -> 48` and join them to the
  relevant selection/deep decision context. If explicit transition events are
  not yet emitted, state that limitation rather than treating a q-length change
  as a fully captured causal event.
- Confirm Step 1 wrapper-equivalence evidence matches this run contract before
  accepting instrumented output.
- Validate `operator_flops.csv` existence and reconcile its phase/op totals with
  the JSON summary. It is theoretical workload, not measured latency.

## Canonical Event Mapping

The source Algorithmic Trace uses:

```text
(contract_id, forward_id, layer_idx, layer_occurrence)
```

For the current one-call-per-layer reference:

```text
layer_occurrence = 0
input_id         = forward_id
layer_id         = layer_idx
event_id         = input{forward_id}_layer{layer_idx}
```

`event_id` is unique only within the source `contract_id`. Dispatch manifests
use `input_id/layer_id`; the current FX manifest uses `forward_id/layer_id`.
Normalize both back to the canonical layer key before comparing sets.

### Current transition-capture limitation

The checked-in Algorithmic Trace tool currently wraps forward, layer, and
selection boundaries but does not emit explicit model-level token-state
transition (`R`) events. `REFERENCE_AUDIT` may use the observed q-length changes
to locate the historical `624 -> 58 -> 48` boundaries, while reporting the
missing causal join. A `FRESH_RUN` may select those boundaries for deeper trace,
but it must not claim full decision-to-application trace completeness until the
Step-1 compaction/removal patch targets are implemented and `R` joins validate.

## Select Representative Events

Use the VisiPrune Algorithmic Trace plus the source-confirmed Step-1 patch plan:

- P0 decision events: middle selection and deep verification layers.
- P1 transition boundaries: the event before and after token-state changes such
  as `624 -> 58 -> 48`.
- P2 shallow representatives: only layers supported by the shallow-adjust
  configuration and profiler/source confirmation, not merely generic full-shape
  layers.
- P3 decode representatives: early/late decode events across full,
  middle-pruned, and deep-removed KV-cache regimes.

Every target row must include:

```text
event_id, input_id, layer_id, phase
q_len, past_len, kv_len
priority, visipruner_role, selection_result, token_state, reason
source contract_id and source trace path in the handoff record
```

## Generate The Canonical Selected Manifest

For `FRESH_RUN`, materialize selection with the exact trace path and a unique
new tag. Do not rely on the profiler's default 32-token trace.

Provide the reviewed Unit-2 values explicitly for this action. Do not depend on
transient command-session state from Unit 1 or intended for a later branch:

```bash
RUN_ID="${RUN_ID:?set the Unit-2 run id}"
PATCH_TARGET_PLAN_JSON="${PATCH_TARGET_PLAN_JSON:?set the absolute reviewed patch_target_plan.json path}"
TRACE_JSON="${TRACE_JSON:?set the absolute Unit-2 algorithmic_trace.json path}"
MANIFEST_TAG="selected_manifest_visipruner_full_32tok_${RUN_ID}"
MANIFEST_DIR="/workspace/VisiPrune/workload_analysis/dispatch/profiles/${MANIFEST_TAG}"
if [ -e "${MANIFEST_DIR}" ]; then
  echo "refusing to reuse manifest directory: ${MANIFEST_DIR}" >&2
  exit 1
fi

/workspace/VisiPrune/workload_analysis/env/run_with_analysis_env.sh \
  /workspace/VisiPrune/workload_analysis/dispatch/tools/visipruner_filtered_dispatch_profile.py \
  --trace "${TRACE_JSON}" \
  --priorities P0,P1,P2,P3 \
  --gpu 1 \
  --tag "${MANIFEST_TAG}" \
  --manifest-only

CANONICAL_SELECTED_MANIFEST="${MANIFEST_DIR}/dispatch_manifest.csv"
SELECTION_HANDOFF="${MANIFEST_DIR}/selection_handoff.json"
```

That `dispatch_manifest.csv` is the sole canonical selected-event manifest for
the run. Materialize the handoff immediately; the manifest-only profiler does
not create this provenance sidecar itself:

```bash
TRACE_JSON="${TRACE_JSON:?set the absolute Unit-2 algorithmic_trace.json path}"
PATCH_TARGET_PLAN_JSON="${PATCH_TARGET_PLAN_JSON:?set the absolute reviewed patch_target_plan.json path}"
CANONICAL_SELECTED_MANIFEST="${CANONICAL_SELECTED_MANIFEST:?set the absolute Unit-2 manifest path}"
SELECTION_HANDOFF="${SELECTION_HANDOFF:?set the output selection_handoff.json path}"
CONTRACT_ID="${CONTRACT_ID:?set the reviewed Unit-2 contract id}"
SOURCE_REVISION="$(git -C /workspace/VisiPrune rev-parse HEAD 2>/dev/null || true)"
/workspace/VisiPrune/workload_analysis/env/run_with_analysis_env.sh \
  - "${TRACE_JSON}" "${CANONICAL_SELECTED_MANIFEST}" \
  "${SELECTION_HANDOFF}" "${CONTRACT_ID}" "${SOURCE_REVISION}" \
  "${PATCH_TARGET_PLAN_JSON}" <<'PY'
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

trace_path = Path(sys.argv[1]).resolve()
manifest_path = Path(sys.argv[2]).resolve()
output_path = Path(sys.argv[3]).resolve()
contract_id = sys.argv[4]
source_revision = sys.argv[5] or "unknown"
patch_plan_path = Path(sys.argv[6]).resolve()
trace = json.loads(trace_path.read_text(encoding="utf-8"))
with manifest_path.open(encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle))
selected = [
    row for row in rows
    if str(row.get("keep_default", "true")).strip().lower() != "false"
]
event_ids = [row["event_id"] for row in selected]
if not event_ids or len(event_ids) != len(set(event_ids)):
    raise SystemExit("selected manifest is empty or contains duplicate event_id values")
expected_ids = [f"input{row['input_id']}_layer{row['layer_id']}" for row in selected]
if event_ids != expected_ids:
    raise SystemExit("selected manifest violates the canonical event_id mapping")

layer_pairs = [
    (int(row["forward_id"]), int(row["layer_idx"]))
    for row in trace.get("layer_events", [])
]
if len(layer_pairs) != len(set(layer_pairs)):
    raise SystemExit(
        "current Dispatch/FX schemas cannot represent repeated "
        "(forward_id, layer_idx) calls; layer_occurrence support is required"
    )
source_layers = {
    (int(row["forward_id"]), int(row["layer_idx"])): row
    for row in trace.get("layer_events", [])
}
for row in selected:
    key = (int(row["input_id"]), int(row["layer_id"]))
    source = source_layers.get(key)
    if source is None:
        raise SystemExit(f"selected event {row['event_id']} is absent from source trace")
    if row["phase"] != source["phase"]:
        raise SystemExit(f"phase mismatch for {row['event_id']}")
    for field in ("q_len", "past_len", "kv_len"):
        if int(row[field]) != int(source[field]):
            raise SystemExit(f"{field} mismatch for {row['event_id']}")

manifest_bytes = manifest_path.read_bytes()
event_set_digest = hashlib.sha256("\n".join(sorted(event_ids)).encode()).hexdigest()
image_path = Path(trace["image_path"])
image_digest = hashlib.sha256(image_path.read_bytes()).hexdigest() if image_path.is_file() else None
payload = {
    "run_mode": "FRESH_RUN",
    "run_id": trace.get("tag"),
    "contract_id": contract_id,
    "source_revision": source_revision,
    "reviewed_patch_target_plan": str(patch_plan_path),
    "reviewed_patch_target_plan_sha256": hashlib.sha256(
        patch_plan_path.read_bytes()
    ).hexdigest(),
    "source_trace": str(trace_path),
    "source_trace_sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
    "canonical_selected_manifest": str(manifest_path),
    "canonical_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    "selection_flags": {
        "priorities": ["P0", "P1", "P2", "P3"],
        "include_decode_effect": True,
        "include_shallow": True,
    },
    "expected_selected_event_count": len(event_ids),
    "ordered_event_ids": event_ids,
    "event_key_set_sha256": event_set_digest,
    "layer_occurrence_contract": "single_call_per_forward_layer_verified",
    "transition_capture_status": (
        "captured" if trace.get("transition_events") else "missing"
    ),
    "run_contract": {
        "config": trace.get("config"),
        "model_path": trace.get("model_path"),
        "model_base": None,
        "image_path": trace.get("image_path"),
        "image_sha256": image_digest,
        "prompt": trace.get("prompt"),
        "conversation_mode": trace.get("conv_mode"),
        "max_new_tokens": trace.get("max_new_tokens"),
        "temperature": 0.0,
        "do_sample": False,
        "dtype": "float16",
        "attention_backend": "eager" if not trace.get("use_flash_attn") else "flash_attention",
        "use_flash_attn": trace.get("use_flash_attn"),
        "use_cache": True,
        "pruning_config": trace.get("pruning_config"),
        "logical_gpu": "1",
        "seed": "not applicable to deterministic greedy generation",
    },
}
temporary = output_path.with_suffix(output_path.suffix + ".tmp")
temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
os.replace(temporary, output_path)
print(output_path)
PY
```

Record any additional contract fields required by `00_overview.md` if they
cannot be derived from the trace. Do not independently reselect events while
building this evidence package. For `REFERENCE_AUDIT`, a missing historical
`selection_handoff.json` is an audit gap; do not add it inside a read-only
reference directory.

The current dispatch profiler does not accept an existing manifest as an input
to a full capture; it deterministically rebuilds one from `--trace` and the
selection flags. Therefore `selection_handoff.json` must preserve the exact
trace path and digest, selection flags, manifest path and digest, ordered event
IDs, event-key-set digest, and expected count. Unit 2 does not launch a full
capture. A branch started later performs its own equality check against this
file-based evidence package.

## Ref

### Scripts

- `workload_analysis/algorithmic_trace/tools/visipruner_algorithmic_trace.py`
- `workload_analysis/algorithmic_trace/tools/compare_algorithmic_traces.py`
- `workload_analysis/algorithmic_trace/verification/tools/verify_wrapper_equivalence.py`
- `workload_analysis/dispatch/tools/visipruner_filtered_dispatch_profile.py`
- `workload_analysis/env/run_with_analysis_env.sh`
- `workload_analysis/algorithmic_trace/runners/run_full_forward.sh` is a legacy
  fixed-tag reference-reproduction helper. It writes conventional tags and a
  `latest_algorithmic_trace_path.txt` pointer, so it is not a safe entry point
  for either `REFERENCE_AUDIT` or isolated `FRESH_RUN`.

`run_all.sh` is excluded: its historical reconstruction input is absent in the
current tree.

### Rules

- `workload_analysis/DISPATCH_FILTER_RULES.md`

### Reference artifacts

```text
workload_analysis/algorithmic_trace/traces/fresh_forward_visipruner_full_32tok/
workload_analysis/dispatch/profiles/filtered_dispatch_visipruner_full_32tok/dispatch_manifest.csv
workload_analysis/fx/traces/fx_filtered_dispatch_layers_specialized/fx_layer_trace_manifest.csv
```

The historical trace directory also contains a `README.md`; the direct tracer
generates the four machine artifacts listed in the run section, not that
historical note.

Under `REFERENCE_AUDIT`, the committed contract has 35 dispatch targets and 35
FX targets, identical normalized canonical key sets, and every selected key in
the 1024-row source layer set. The value 35 is a reference-contract fact, not an
unconditional constant for another contract. A fresh run matching the
reference contract should reproduce it; otherwise completion is blocked until
the difference is explained from trace evidence.

## Completion Checks

- Run mode, unique tags, canonical run contract, and exact source trace path are
  recorded.
- The four Algorithmic Trace files exist and pass JSON/CSV key-set, sequence,
  event-count, and FLOP-summary checks.
- Wrapper equivalence passes for the instrumented contract.
- The canonical selected manifest was generated with explicit `--trace` and
  `--manifest-only`; its tag was not reused.
- For `FRESH_RUN`, `selection_handoff.json` records the source trace, canonical
  trace/manifest SHA-256 values, selection flags, contract, expected count,
  ordered event IDs, event-key-set digest, and the verified single-call
  `layer_occurrence` contract.
- `keys(selected manifest) ⊆ keys(layer events)`, `event_id` is unique, and
  every row's `phase/q_len/past_len/kv_len` agrees with its source event.
- Every selected row has an evidence-backed VisiPrune role/reason. Shallow
  targets cite source/profiler confirmation; transition targets distinguish
  decisions from application boundaries.
- `transition_capture_status` is explicit. If it is `missing`, the handoff is
  labelled boundary-selection evidence rather than a complete causal
  decision-to-application trace.
- For `REFERENCE_AUDIT`, both committed manifests contain exactly 35 events and
  their normalized key sets are equal.
- The evidence package contains the exact canonical selected-event set that any
  later, manually started branch must validate independently.

## Stop Boundary

After the trace, canonical manifest, `selection_handoff.json`, and Unit-2 review
result are written, stop. Do not invoke DispatchMode, FX, reconstruction, or
visualization. A human reviews this evidence package and may later start either
combined branch separately by providing the absolute `selection_handoff.json`
path. Transient command-session state is not part of the handoff.
