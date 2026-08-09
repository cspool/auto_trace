# 03.1 -> 04.1 Dispatch Branch Manual Runbook

## Goal

Run one complete Dispatch branch in this fixed order:

```text
3.1 filtered eager Dispatch trace
  -> profile validation
  -> 4.1 per-selected-event reconstruction and ONNX
  -> manual character visualization
  -> strict review and audit
```

One human start opens this complete 3.1 -> 4.1 unit, and a human later signs off
its completion. There is no second manual start between 3.1 and 4.1. This
runbook is not a router, does not choose between Dispatch and FX, and does not
run Steps 1 or 2.

## Existing Skills Used

- Step 3.1 — `visipruner-trace-dispatch-profile`: apply its filtered eager
  Dispatch capture and profile-validation responsibilities to the approved
  Unit-2 event manifest; do not select a different target set.
- Step 4.1 — `dispatch-layer-reconstruct-onnx`: apply its per-event Dispatch
  reconstruction, tensor-dependency, ONNX, review, and strict-audit
  responsibilities after the Step-3.1 evidence gate passes.

This Markdown document supplies the ordered invocation scope, handoff gates,
manual character-visualization procedure, and script references for those
existing Skills. It does not define a new Skill, invoke Skills automatically,
or add an orchestration layer.

A human operator must explicitly:

1. approve one Step 2 `selection_handoff.json`;
2. provide only its path as branch input;
3. authorize execution after reading the blockers below; and
4. sign off completion after every selected event passes the final audit.

## Local Evidence Mode

- `REFERENCE_AUDIT`: inspect only the historical profile/reconstruction under
  `Ref`, report current coverage and provenance gaps, and stop without running
  any command below. The historical tree has no new Step-2 handoff.
- `FRESH_RUN`: use the human-approved Step-2 handoff and follow the remaining
  branch sections. It is currently blocked by the issues listed below.

## Fresh-run Input And Entry Gate

The only branch input is:

```bash
SELECTION_HANDOFF="${SELECTION_HANDOFF:?set the human-reviewed Step 2 selection_handoff.json path}"
```

Do not accept a loose trace path, manifest path, copied event list, historical
tag, or default tool path as a substitute.

The handoff must name and bind:

```text
contract_id
source_trace and source_trace_sha256
canonical_selected_manifest and canonical_manifest_sha256
selection_flags
expected_selected_event_count
ordered_event_ids
event_key_set_sha256
run_contract
```

Let `T` be `ordered_event_ids` and `N = |T|`. `N` is dynamic. A historical
event count is never a fresh-run constant.

Validate the handoff before loading a model:

```bash
set -euo pipefail
mapfile -t HANDOFF_VALUES < <(
  /workspace/VisiPrune/workload_analysis/env/run_with_analysis_env.sh \
    - "${SELECTION_HANDOFF}" <<'PY'
import csv
import hashlib
import json
import sys
from pathlib import Path

handoff_path = Path(sys.argv[1]).resolve()
handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
required = {
    "run_mode", "contract_id", "source_trace", "source_trace_sha256",
    "canonical_selected_manifest", "canonical_manifest_sha256",
    "selection_flags", "expected_selected_event_count", "ordered_event_ids",
    "event_key_set_sha256", "run_contract", "layer_occurrence_contract",
}
missing = sorted(required - set(handoff))
if missing:
    raise SystemExit(f"BLOCKED: selection handoff missing fields: {missing}")
if handoff["run_mode"] != "FRESH_RUN":
    raise SystemExit("BLOCKED: fresh Dispatch branch requires a FRESH_RUN handoff")
if handoff["layer_occurrence_contract"] != "single_call_per_forward_layer_verified":
    raise SystemExit("BLOCKED: current Dispatch schema requires the single-call gate")

trace_path = Path(handoff["source_trace"]).resolve()
manifest_path = Path(handoff["canonical_selected_manifest"]).resolve()
if hashlib.sha256(trace_path.read_bytes()).hexdigest() != handoff["source_trace_sha256"]:
    raise SystemExit("BLOCKED: source trace SHA-256 mismatch")
if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != handoff["canonical_manifest_sha256"]:
    raise SystemExit("BLOCKED: canonical manifest SHA-256 mismatch")

with manifest_path.open(newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))
events = [
    row["event_id"]
    for row in rows
    if str(row.get("keep_default", "true")).strip().lower() != "false"
]
if not events or len(events) != len(set(events)):
    raise SystemExit("BLOCKED: canonical selected events are empty or duplicated")
if events != handoff["ordered_event_ids"]:
    raise SystemExit("BLOCKED: canonical event order differs from handoff")
if len(events) != int(handoff["expected_selected_event_count"]):
    raise SystemExit("BLOCKED: canonical event count differs from handoff")
digest = hashlib.sha256("\n".join(sorted(events)).encode()).hexdigest()
if digest != handoff["event_key_set_sha256"]:
    raise SystemExit("BLOCKED: canonical event-set digest differs from handoff")

trace = json.loads(trace_path.read_text(encoding="utf-8"))
layer_pairs = [
    (int(row["forward_id"]), int(row["layer_idx"]))
    for row in trace.get("layer_events", [])
]
if len(layer_pairs) != len(set(layer_pairs)):
    raise SystemExit(
        "BLOCKED: current Dispatch event_id cannot represent repeated "
        "(forward_id, layer_idx) calls; layer_occurrence support is required"
    )

flags = handoff["selection_flags"]
priorities = ",".join(flags.get("priorities", []))
if not priorities:
    raise SystemExit("BLOCKED: selection priorities are empty")

print(trace_path)
print(manifest_path)
print(handoff["contract_id"])
print(len(events))
print(priorities)
print(str(bool(flags.get("include_decode_effect", True))).lower())
print(str(bool(flags.get("include_shallow", True))).lower())
PY
)

if [ "${#HANDOFF_VALUES[@]}" -ne 7 ]; then
  echo "failed to load the reviewed Step-2 handoff" >&2
  exit 1
fi
TRACE_JSON="${HANDOFF_VALUES[0]}"
CANONICAL_MANIFEST="${HANDOFF_VALUES[1]}"
CONTRACT_ID="${HANDOFF_VALUES[2]}"
N="${HANDOFF_VALUES[3]}"
PRIORITIES="${HANDOFF_VALUES[4]}"
INCLUDE_DECODE_EFFECT="${HANDOFF_VALUES[5]}"
INCLUDE_SHALLOW="${HANDOFF_VALUES[6]}"
if [ "${N}" -le 0 ]; then
  echo "reviewed Step-2 handoff has no selected events" >&2
  exit 1
fi
```

The uniqueness check above is the `layer_occurrence=0` gate. If it fails, this
branch stops because the current `input{forward_id}_layer{layer_idx}` schema
cannot distinguish repeated layer calls.

## Current Blockers

Do not start an expensive fresh run or claim completion while any blocker is
unresolved.

1. **Dispatch schema blocker.** The current profiler writer emits only 14
   compact columns:

   ```text
   args,event_id,kv_len,kwargs,module_class,op_schema,outputs,past_len,phase,
   q_len,token_state,visipruner_role,input_tensor_ids,output_tensor_ids
   ```

   It omits required `event_op_index`, `op_name`, detailed module context,
   detailed tensor metadata, and alias evidence.
2. **Generator/auditor blocker.** `run.py` writes the full per-event evidence
   copy to `dispatch_review/dispatch_ops.csv`, while the strict auditor also
   requires `<event_id>/dispatch_ops.csv`. Do not use the compact splitter or a
   placeholder to bridge this contract mismatch.
3. **`process_index.md` blocker.** The generated per-op table does not yet expose
   every required op schema, tensor-id input/output, assigned process, and
   `compute`/`mutation-view`/`data_movement`/`bookkeeping` classification.

Manual character visualization is intentionally manual work, not a missing
automatic feature to bypass.

## 3.1 Dispatch Trace

After the 14-column blocker is fixed, create a new profile directory and refuse
reuse:

```bash
RUN_ID="$(date -u +%Y%m%d_%H%M%S)"
PROFILE_TAG="filtered_dispatch_${RUN_ID}"
PROFILE_DIR="/workspace/VisiPrune/workload_analysis/dispatch/profiles/${PROFILE_TAG}"
if [ -e "${PROFILE_DIR}" ]; then
  echo "refusing to reuse profile directory: ${PROFILE_DIR}" >&2
  exit 1
fi

SELECTION_ARGS=(--priorities "${PRIORITIES}")
if [ "${INCLUDE_DECODE_EFFECT}" != "true" ]; then
  SELECTION_ARGS+=(--no-decode-effect)
fi
if [ "${INCLUDE_SHALLOW}" != "true" ]; then
  SELECTION_ARGS+=(--no-shallow)
fi

/workspace/VisiPrune/workload_analysis/env/run_with_analysis_env.sh \
  /workspace/VisiPrune/workload_analysis/dispatch/tools/visipruner_filtered_dispatch_profile.py \
  --trace "${TRACE_JSON}" \
  "${SELECTION_ARGS[@]}" \
  --gpu 1 \
  --tag "${PROFILE_TAG}"
```

## Validate The Dispatch Profile

Before reconstruction, require all of the following:

- the copied handoff still passes the entry-gate hashes and digests;
- emitted kept manifest order equals `T`;
- distinct `dispatch_ops.csv` events equal `T`;
- each event has contiguous `event_op_index = 1..N_ops`;
- the ops header contains stable event/order fields, `op_name/op_schema`, args
  and outputs, module stack/context, detailed input/output tensors, tensor ids,
  producers/edges, and alias records;
- `observed_layer_events.csv` covers the expected source schedule;
- `run_metadata.json.source_trace` resolves to the handoff source trace;
- metadata target count is `N` and output consistency passes.

The profile handoff is:

```text
selection_handoff.json
dispatch_manifest.csv
dispatch_ops.csv
dispatch_op_summary.csv
observed_layer_events.csv
run_metadata.json
```

No reconstruction begins until validation passes.

Only after this review passes, copy the evidence package into the profile:

```bash
cp --no-clobber "${SELECTION_HANDOFF}" "${PROFILE_DIR}/selection_handoff.json"
```

## 4.1 Reconstruction And ONNX

After the generator/auditor and `process_index.md` blockers are fixed, derive
the complete ordered event list from the copied handoff and canonical manifest;
do not type layer IDs manually.

```bash
mapfile -t SELECTED_EVENTS < <(
  /workspace/VisiPrune/workload_analysis/env/run_with_analysis_env.sh \
    - "${PROFILE_DIR}/selection_handoff.json" <<'PY'
import json
import sys
from pathlib import Path
handoff = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("\n".join(handoff["ordered_event_ids"]))
PY
)
if [ "${#SELECTED_EVENTS[@]}" -ne "${N}" ]; then
  echo "profile handoff event count differs from reviewed Step 2" >&2
  exit 1
fi

RECON_TAG="${PROFILE_TAG}_reconstruction"
RUN_ROOT="/workspace/VisiPrune/workload_analysis/dispatch/visualize/${RECON_TAG}"
if [ -e "${RUN_ROOT}" ]; then
  echo "refusing to reuse reconstruction directory: ${RUN_ROOT}" >&2
  exit 1
fi

/workspace/VisiPrune/workload_analysis/env/run_with_analysis_env.sh \
  /workspace/VisiPrune/workload_analysis/dispatch/layer_pipeline/run.py \
  --source-csv "${PROFILE_DIR}/dispatch_ops.csv" \
  --out-dir "${RUN_ROOT}" \
  --code-dir "${RUN_ROOT}" \
  --layers "${SELECTED_EVENTS[@]}"
```

Do not use `--skip-onnx`. For every event, require full-schema event evidence,
`dispatch_review/`, module split, tensor dataflow, op coverage, small-shape
Torch, `torch_flow/process_index.md`, `onnx/manifest.json`, per-stage ONNX,
one-to-one ONNX code-review pages, and `layer_manifest.json`.

`process_index.md` is mandatory and must explicitly enumerate every source op
with its op/schema, runtime module, tensor-id inputs/outputs, assigned process,
classification, and coverage evidence. No equivalent artifact substitutes for
it.

## Manual Character Visualization

For every event in `T`, manually use the validated dispatch evidence to write:

```text
${RUN_ROOT}/<event_id>/dispatch_process_visualization.md
```

Each file must show character/ASCII tensor flow, original and small shapes,
tensor IDs at producer-consumer boundaries, relevant op indices/modules,
inplace/alias transitions, and evidence-supported cache, rectangular-attention,
visual-adjust, or similarity branches. A stage-name list or copied shared
template is incomplete.

## Strict Review And Audit

```bash
/workspace/VisiPrune/workload_analysis/env/run_with_analysis_env.sh \
  /workspace/VisiPrune/workload_analysis/dispatch/layer_pipeline/review_reconstruction.py \
  --source-csv "${PROFILE_DIR}/dispatch_ops.csv" \
  --layer-dir "${RUN_ROOT}" \
  --code-dir "${RUN_ROOT}" \
  --review-dir "${RUN_ROOT}/reconstruction_review"

/workspace/VisiPrune/workload_analysis/env/run_with_analysis_env.sh \
  /workspace/VisiPrune/workload_analysis/dispatch/layer_pipeline/audit_layer_reconstruction.py \
  --source-csv "${PROFILE_DIR}/dispatch_ops.csv" \
  --layer-dir "${RUN_ROOT}" \
  --audit-dir "${RUN_ROOT}/reconstruction_audit" \
  --layers "${SELECTED_EVENTS[@]}"
```

Command exit code alone is insufficient. Require:

```text
T
 == profiled events
 == pipeline_manifest events
 == review events with status=match
 == audit events with status=pass
 == events containing dispatch_process_visualization.md
size of every set == N
```

Also require recomputable tensor-id edges, full module/op coverage, correct
optional stages and rectangular shapes, ONNX checker success, one-to-one code
pages, zero audit issues, and no `.pyc` or `__pycache__` under the fresh root.

## Manual Completion Record

This runbook has no autonomous completion action. A human reviewer records:

```text
selection_handoff path and SHA-256
contract_id
source trace and canonical manifest SHA-256
event-set digest and N
profile tag and reconstruction root
N review matches, N audit passes, zero issues
N independently reviewed character visualizations
reviewer and completion time
```

Any blocker, missing event/artifact, `needs_revision`, audit failure, or
unreviewed visualization leaves the branch incomplete.

For `REFERENCE_AUDIT`, the completion record instead states the inspected
historical paths and gaps; it never claims fresh branch completion.

## Ref

### Scripts

These are scripts used by this manually started runbook, not Skills or
separately scheduled work units. There is no end-to-end branch router or
`run_all` entry.

- Runtime wrapper: `workload_analysis/env/run_with_analysis_env.sh`
- Filtered profiler:
  `workload_analysis/dispatch/tools/visipruner_filtered_dispatch_profile.py`
- Reconstruction driver: `workload_analysis/dispatch/layer_pipeline/run.py`
- Analysis: `workload_analysis/dispatch/layer_pipeline/analyze.py`
- Flow/ONNX generation:
  `workload_analysis/dispatch/layer_pipeline/flow_codegen.py`
- Reconstruction review:
  `workload_analysis/dispatch/layer_pipeline/review_reconstruction.py`
- Strict audit:
  `workload_analysis/dispatch/layer_pipeline/audit_layer_reconstruction.py`
- ONNX export template:
  `workload_analysis/dispatch/templates/small_tensor_flow/export_stage_onnx.py`
- Compact splitter:
  `workload_analysis/dispatch/tools/split_dispatch_ops_by_event.py` is
  noncanonical for this branch.

### Reference artifacts

- Historical profile:
  `workload_analysis/dispatch/profiles/filtered_dispatch_visipruner_full_32tok/`
- Historical reconstruction:
  `workload_analysis/dispatch/visualize/<event_id>/`
- The named historical reference has `35` selected events. This is reference
  metadata only, not a fresh-run invariant or valid branch input by itself.
- At this review snapshot, 35 event directories exist, 31 contain
  `dispatch_review/`, and none contains the new separate
  `dispatch_process_visualization.md`; historical audit JSON may be stale.
