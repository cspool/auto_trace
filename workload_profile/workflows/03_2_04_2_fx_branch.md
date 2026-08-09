# 03.2–04.2 FX Branch Manual Runbook

## Goal

Run the complete selected-layer FX branch from an already reviewed Step-2
selection handoff through trace, reconstruction, manual process visualization,
and final coverage audit.

A human starts this complete 3.2–4.2 unit once by explicitly requesting it and
supplying the approved Step-2 `selection_handoff.json`. There is no second
manual start between 3.2 and 4.2. The operator remains responsible through the
final audit or blocking report. This runbook is not a router, does not choose
between FX and DispatchMode, and does not run or repair Steps 1–2.

## Existing Skills Used

- Step 3.2 — `visipruner-fx-trace-workflow`: apply its real eager input
  sampling, offline fixed-input FX capture, trace validation, and evidence-
  boundary responsibilities to the approved Unit-2 events.
- Step 4.2 — `visipruner-fx-process-visualization`: after rule reconstruction,
  apply its process-by-process Chinese explanation and manual tensor-axis
  character-visualization responsibilities.

This Markdown document supplies the ordered invocation scope, handoff gates,
coverage audit, and script references for those existing Skills. It does not
define a new Skill, invoke Skills automatically, or add an orchestration layer.
The reconstruction between the two Skill scopes uses
`fx_layer_process_reconstruct.py`, listed separately under `Ref`; that script is
not a Skill.

## Local Evidence Mode

- `REFERENCE_AUDIT`: inspect only the historical artifacts under `Ref`, report
  provenance/layout gaps, and stop without running any command below.
- `FRESH_RUN`: use the human-approved Step-2 handoff and follow the ordered
  branch sections below.

## Ref

### Scripts

- `workload_analysis/fx/fx_dynamic_trace.py`
- `workload_analysis/fx/fx_layer_process_reconstruct.py`
- `workload_analysis/env/run_with_analysis_env.sh`

These are scripts used by this runbook, not Skills or separately started work
units. `fx_dynamic_trace.py` only creates FX trace evidence;
`fx_layer_process_reconstruct.py` only creates rule-derived reconstruction
evidence. Neither script creates the manual character visualizations.

### Reference artifacts

The following committed artifacts are read-only `REFERENCE_AUDIT` evidence:

```text
workload_analysis/dispatch/profiles/filtered_dispatch_visipruner_full_32tok/dispatch_manifest.csv
workload_analysis/algorithmic_trace/traces/fresh_forward_visipruner_full_32tok/algorithmic_trace.json
workload_analysis/fx/traces/fx_filtered_dispatch_layers_specialized/
```

The historical FX tree has 35 successful trace/reconstruction event directories
and 35 generated reconstruction Markdown files with embedded manual diagrams,
but no separate `fx_process_visualization.md` companions and no current
`selection_handoff.json`. Report those provenance/layout gaps when auditing it.
Never run either script against this tree, synthesize missing files inside it,
or use it as a fresh output destination: reconstruction would overwrite the
embedded manual content.

## Fresh-run Input Gate

The only human-supplied input is:

```bash
SELECTION_HANDOFF=/absolute/path/to/reviewed/selection_handoff.json
```

The handoff must declare `FRESH_RUN` and contain the exact source trace and
SHA-256, canonical selected manifest and SHA-256, `contract_id`, ordered selected
event ids, expected count, event-key-set digest, reviewed run contract, and:

```text
layer_occurrence_contract=single_call_per_forward_layer_verified
```

The current FX event-id/directory schema cannot encode `layer_occurrence`; any
other occurrence contract blocks this branch.

## Ordered Workflow

The order is fixed:

```text
3.2 runtime eager sampling + offline specialized FX trace
  -> validate trace/provenance/specialization
  -> 4.2 rule reconstruction
  -> manually explain and visualize every reconstructed process
  -> final provenance and event-set coverage audit
```

Do not begin reconstruction when trace validation fails, and do not declare the
branch complete before every manual companion and the final audit pass.

## 1. Runtime Sample And Specialized FX Trace

The command below derives every runtime input from the one handoff path, verifies
its hashes and event order, refuses output reuse, runs the real eager request,
and validates the resulting FX trace before copying the handoff into the fresh
trace root.

```bash
set -euo pipefail
VISIPRUNE_ROOT=/workspace/VisiPrune
SELECTION_HANDOFF="${SELECTION_HANDOFF:?human must supply the reviewed Step-2 handoff path}"
FX_OUTPUT_ROOT="${VISIPRUNE_ROOT}/workload_analysis/fx/traces"
REFERENCE_AUDIT="${FX_OUTPUT_ROOT}/fx_filtered_dispatch_layers_specialized"
GPU=1
FX_TAG="fx_branch_$(date -u +%Y%m%d_%H%M%S)"
FX_TRACE_DIR="${FX_OUTPUT_ROOT}/${FX_TAG}"

mapfile -t HANDOFF_VALUES < <(
  "${VISIPRUNE_ROOT}/workload_analysis/env/run_with_analysis_env.sh" \
    - "${SELECTION_HANDOFF}" <<'PY'
import csv
import hashlib
import json
import sys
from pathlib import Path

handoff = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if handoff.get("run_mode") != "FRESH_RUN":
    raise SystemExit("the FX branch requires a FRESH_RUN handoff")
if not handoff.get("contract_id"):
    raise SystemExit("selection handoff has no contract_id")
if handoff.get("layer_occurrence_contract") != "single_call_per_forward_layer_verified":
    raise SystemExit("current FX schema requires the single-call occurrence gate")

trace = Path(handoff["source_trace"]).resolve()
manifest = Path(handoff["canonical_selected_manifest"]).resolve()
if hashlib.sha256(trace.read_bytes()).hexdigest() != handoff["source_trace_sha256"]:
    raise SystemExit("source trace digest differs from the Step-2 handoff")
if hashlib.sha256(manifest.read_bytes()).hexdigest() != handoff["canonical_manifest_sha256"]:
    raise SystemExit("canonical manifest digest differs from the Step-2 handoff")

run_contract = handoff.get("run_contract", {})
image = Path(run_contract.get("image_path", ""))
if not image.is_file() or hashlib.sha256(image.read_bytes()).hexdigest() != run_contract.get("image_sha256"):
    raise SystemExit("input image differs from the Step-2 run contract")

with manifest.open(encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle))
events = [
    row["event_id"].strip()
    for row in rows
    if str(row.get("keep_default", "true")).strip().lower() != "false"
]
if not events or len(events) != len(set(events)):
    raise SystemExit("canonical manifest is empty or contains duplicate event ids")
if events != handoff.get("ordered_event_ids"):
    raise SystemExit("canonical event order differs from the Step-2 handoff")
if len(events) != int(handoff["expected_selected_event_count"]):
    raise SystemExit("canonical event count differs from the Step-2 handoff")
digest = hashlib.sha256("\n".join(sorted(events)).encode()).hexdigest()
if digest != handoff.get("event_key_set_sha256"):
    raise SystemExit("canonical event-key-set digest differs from the Step-2 handoff")

print(trace)
print(manifest)
print(handoff["contract_id"])
print(",".join(events))
PY
)
if [ "${#HANDOFF_VALUES[@]}" -ne 4 ]; then
  echo "failed to load the complete Step-2 handoff" >&2
  exit 1
fi
ALGO_TRACE="${HANDOFF_VALUES[0]}"
CANONICAL_MANIFEST="${HANDOFF_VALUES[1]}"
CONTRACT_ID="${HANDOFF_VALUES[2]}"
FX_LAYERS="${HANDOFF_VALUES[3]}"

if [ -z "${FX_LAYERS}" ] || [ -e "${FX_TRACE_DIR}" ]; then
  echo "empty FX target list or reused output directory: ${FX_TRACE_DIR}" >&2
  exit 1
fi
if [ "$(realpath -m "${FX_TRACE_DIR}")" = "$(realpath -m "${REFERENCE_AUDIT}")" ]; then
  echo "refusing to write into the read-only FX reference" >&2
  exit 1
fi

CUDA_VISIBLE_DEVICES="${GPU}" \
"${VISIPRUNE_ROOT}/workload_analysis/env/run_with_analysis_env.sh" \
  "${VISIPRUNE_ROOT}/workload_analysis/fx/fx_dynamic_trace.py" \
  --model-layer-trace \
  --trace "${ALGO_TRACE}" \
  --layers "${FX_LAYERS}" \
  --output-dir "${FX_OUTPUT_ROOT}" \
  --gpu "${GPU}" \
  --strict-layer-trace \
  --tag "${FX_TAG}"

"${VISIPRUNE_ROOT}/workload_analysis/env/run_with_analysis_env.sh" \
  - "${FX_TRACE_DIR}" "${SELECTION_HANDOFF}" <<'PY'
import csv
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
handoff = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
metadata = json.loads((root / "run_metadata.json").read_text(encoding="utf-8"))
source = json.loads(Path(handoff["source_trace"]).read_text(encoding="utf-8"))
with (root / "fx_layer_trace_manifest.csv").open(encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle))

expected = list(handoff["ordered_event_ids"])
observed = [row["event_id"] for row in rows]
targets = list(metadata.get("target_event_keys", []))
if observed != expected or len(observed) != len(set(observed)):
    raise SystemExit("FX trace manifest differs from the canonical event order")
if targets != expected or len(targets) != len(set(targets)):
    raise SystemExit("FX run targets differ from the canonical event order")
if Path(metadata.get("trace", "")).resolve() != Path(handoff["source_trace"]).resolve():
    raise SystemExit("FX source trace differs from the Step-2 handoff")
if metadata.get("output_text") != (source.get("request") or {}).get("output_text"):
    raise SystemExit("FX eager output differs from the source Algorithmic Trace")
if (
    int(metadata.get("fx_sample_count", -1)) != len(expected)
    or int(metadata.get("fx_trace_count", -1)) != len(expected)
    or int(metadata.get("fx_trace_error_count", -1)) != 0
):
    raise SystemExit("FX run-level counts are inconsistent")

for row in rows:
    if (
        row.get("status") != "ok"
        or str(row.get("fx_sampled", "")).lower() != "true"
        or str(row.get("fx_traced", "")).lower() != "true"
    ):
        raise SystemExit(f"FX event did not complete: {row}")
    event_dir = Path(row["trace_dir"])
    for name in (
        "fx_graph_module.pt", "fx_graph.py", "fx_graph.txt", "fx_nodes.json",
        "fx_trace_metadata.json",
    ):
        if not (event_dir / name).is_file():
            raise SystemExit(f"missing FX artifact: {event_dir / name}")
    if not (event_dir / "fx_graph_module").is_dir():
        raise SystemExit(f"missing GraphModule folder: {event_dir}")
    specialization = json.loads(row.get("specialization") or "{}")
    event_metadata = json.loads((event_dir / "fx_trace_metadata.json").read_text(encoding="utf-8"))
    if not specialization or event_metadata.get("specialization") != specialization:
        raise SystemExit(f"missing or inconsistent specialization for {row['event_id']}")

print(f"FX trace validation ok: {len(expected)} events")
PY

cp --no-clobber "${SELECTION_HANDOFF}" "${FX_TRACE_DIR}/selection_handoff.json"
printf 'FX_TAG=%s\nFX_TRACE_DIR=%s\nCONTRACT_ID=%s\n' \
  "${FX_TAG}" "${FX_TRACE_DIR}" "${CONTRACT_ID}"
```

### Specialization Evidence Boundary

Keep three evidence levels distinct:

1. The real eager `generate()` call proves that selected layer inputs were
   sampled at runtime; the eager output does not come from FX.
2. An offline dry-run on cloned inputs flattens kwargs, fixes scalar guards and
   selected scalar module attributes, records `.item()` branch decisions, and
   normalizes Python cache outputs.
3. `make_fx` replays that fixed branch. Its `GraphModule` proves only the
   specialized fixed-input ATen DAG, not alternative branches, removed predicate
   computations, Python object semantics, full eager op coverage, or module
   ownership.

The manifest and per-event `fx_trace_metadata.json` specialization records are
required evidence for every later explanation.

## 2. Rule Reconstruction

Do not continue unless trace validation passed. The reconstruction script may
finish with per-event errors, so its exit status is not sufficient.

```bash
set -euo pipefail
: "${VISIPRUNE_ROOT:?run the trace setup first}" \
  "${FX_TRACE_DIR:?set the validated fresh FX trace directory}"
REFERENCE_AUDIT="${VISIPRUNE_ROOT}/workload_analysis/fx/traces/fx_filtered_dispatch_layers_specialized"

if [ "$(realpath -m "${FX_TRACE_DIR}")" = "$(realpath -m "${REFERENCE_AUDIT}")" ]; then
  echo "refusing to reconstruct the read-only FX reference" >&2
  exit 1
fi
for required in fx_layer_trace_manifest.csv run_metadata.json selection_handoff.json; do
  test -f "${FX_TRACE_DIR}/${required}"
done
if [ -e "${FX_TRACE_DIR}/fx_process_reconstruction_manifest.csv" ] || \
   [ -e "${FX_TRACE_DIR}/fx_process_reconstruction_manifest.json" ]; then
  echo "refusing to overwrite an existing FX reconstruction" >&2
  exit 1
fi

"${VISIPRUNE_ROOT}/workload_analysis/env/run_with_analysis_env.sh" \
  "${VISIPRUNE_ROOT}/workload_analysis/fx/fx_layer_process_reconstruct.py" \
  --trace-dir "${FX_TRACE_DIR}" \
  --recursive

"${VISIPRUNE_ROOT}/workload_analysis/env/run_with_analysis_env.sh" \
  - "${FX_TRACE_DIR}" <<'PY'
import csv
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
handoff = json.loads((root / "selection_handoff.json").read_text(encoding="utf-8"))
expected = list(handoff["ordered_event_ids"])
with (root / "fx_process_reconstruction_manifest.csv").open(encoding="utf-8", newline="") as handle:
    csv_rows = list(csv.DictReader(handle))
payload = json.loads((root / "fx_process_reconstruction_manifest.json").read_text(encoding="utf-8"))
json_rows = payload.get("results", [])
csv_ids = [Path(row["trace_dir"]).name for row in csv_rows]
json_ids = [Path(row["trace_dir"]).name for row in json_rows]
if int(payload.get("processed", -1)) != len(json_rows):
    raise SystemExit("reconstruction JSON processed count is inconsistent")
if set(csv_ids) != set(expected) or json_ids != csv_ids or len(csv_ids) != len(set(csv_ids)):
    raise SystemExit("reconstruction manifests differ from the canonical event set")
for csv_row, json_row in zip(csv_rows, json_rows):
    if csv_row.get("status") != "ok" or json_row.get("status") != "ok":
        raise SystemExit(f"reconstruction failed: {csv_row}")
    for field in ("json", "markdown", "csv"):
        artifact = Path(csv_row[field])
        if not artifact.is_absolute():
            artifact = (Path.cwd() / artifact).resolve()
        if not artifact.is_file():
            raise SystemExit(f"missing reconstruction artifact: {artifact}")
print(f"FX reconstruction validation ok: {len(expected)} events")
PY
```

The generated `fx_process_reconstruction.md/json` and `fx_process_nodes.csv`
contain rule-derived labels, ranges, code, node dependencies, and shape/dtype
metadata. They are regenerable evidence, not official module ownership.

## 3. Manual Per-process Character Visualization

For every canonical event, manually read:

- `fx_process_reconstruction.md` and `.json`;
- `fx_process_nodes.csv` and `fx_graph.py`;
- `fx_trace_metadata.json`, especially `specialization`.

Manually explain every reconstructed process—what it is on this fixed path, why
it is needed, and how its own FX nodes transform tensors in dependency order—then
draw a process-level tensor-axis, rectangle-axis, or tensor-region diagram from
observed targets, args/users, shapes, and dependencies. Do not use a bulk
renderer, generated diagram template, or one-op-at-a-time flowchart. Label any
non-FX conceptual context explicitly.

Write exactly one manual companion per event:

```text
workload_analysis/fx/traces/<FX_TAG>/<event_id>/fx_process_visualization.md
```

Every companion must cover every process in that event's reconstruction. The
generated reconstruction files are strictly read-only during this stage: never
write, append, or copy manual prose/diagrams into them.

## 4. Final Coverage Audit

Run this only after every manual companion is complete:

```bash
: "${VISIPRUNE_ROOT:?run the branch setup first}" \
  "${FX_TRACE_DIR:?set the fresh FX trace directory}"
"${VISIPRUNE_ROOT}/workload_analysis/env/run_with_analysis_env.sh" \
  - "${FX_TRACE_DIR}" <<'PY'
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
handoff = json.loads((root / "selection_handoff.json").read_text(encoding="utf-8"))
metadata = json.loads((root / "run_metadata.json").read_text(encoding="utf-8"))
if handoff.get("run_mode") != "FRESH_RUN" or not handoff.get("contract_id"):
    raise SystemExit("invalid fresh-run provenance")
if handoff.get("layer_occurrence_contract") != "single_call_per_forward_layer_verified":
    raise SystemExit("invalid layer-occurrence contract")

source = Path(handoff["source_trace"])
manifest = Path(handoff["canonical_selected_manifest"])
if hashlib.sha256(source.read_bytes()).hexdigest() != handoff["source_trace_sha256"]:
    raise SystemExit("source trace digest changed")
if hashlib.sha256(manifest.read_bytes()).hexdigest() != handoff["canonical_manifest_sha256"]:
    raise SystemExit("canonical manifest digest changed")
with manifest.open(encoding="utf-8", newline="") as handle:
    canonical_rows = list(csv.DictReader(handle))
canonical = [
    row["event_id"].strip()
    for row in canonical_rows
    if str(row.get("keep_default", "true")).strip().lower() != "false"
]
if canonical != handoff.get("ordered_event_ids") or len(canonical) != len(set(canonical)):
    raise SystemExit("canonical manifest order/uniqueness differs from the handoff")
if len(canonical) != int(handoff["expected_selected_event_count"]):
    raise SystemExit("canonical event count differs from the handoff")
if hashlib.sha256("\n".join(sorted(canonical)).encode()).hexdigest() != handoff["event_key_set_sha256"]:
    raise SystemExit("canonical event-key-set digest changed")

with (root / "fx_layer_trace_manifest.csv").open(encoding="utf-8", newline="") as handle:
    trace_rows = list(csv.DictReader(handle))
with (root / "fx_process_reconstruction_manifest.csv").open(encoding="utf-8", newline="") as handle:
    reconstruction_rows = list(csv.DictReader(handle))
reconstruction_payload = json.loads(
    (root / "fx_process_reconstruction_manifest.json").read_text(encoding="utf-8")
)
reconstruction_json_rows = reconstruction_payload.get("results", [])

targets = list(metadata.get("target_event_keys", []))
trace_ids = [row["event_id"] for row in trace_rows]
reconstruction_ids = [Path(row["trace_dir"]).name for row in reconstruction_rows]
reconstruction_json_ids = [Path(row["trace_dir"]).name for row in reconstruction_json_rows]
if targets != canonical or trace_ids != canonical:
    raise SystemExit("target/trace order differs from canonical T")
if set(reconstruction_ids) != set(canonical) or len(reconstruction_ids) != len(set(reconstruction_ids)):
    raise SystemExit("reconstruction events differ from canonical T")
if reconstruction_json_ids != reconstruction_ids:
    raise SystemExit("reconstruction JSON/CSV manifests differ")
if int(reconstruction_payload.get("processed", -1)) != len(reconstruction_json_rows):
    raise SystemExit("reconstruction JSON processed count is inconsistent")
if Path(metadata.get("trace", "")).resolve() != source.resolve():
    raise SystemExit("FX metadata source trace differs from the handoff")

trace_errors = [
    row for row in trace_rows
    if row.get("status") != "ok"
    or str(row.get("fx_sampled", "")).lower() != "true"
    or str(row.get("fx_traced", "")).lower() != "true"
]
reconstruction_errors = [row for row in reconstruction_rows if row.get("status") != "ok"]
if trace_errors or reconstruction_errors:
    raise SystemExit(f"trace/reconstruction errors: {trace_errors} {reconstruction_errors}")

T = set(canonical)
X = {row["event_id"] for row in trace_rows if row.get("status") == "ok"}
R = {
    Path(row["trace_dir"]).name
    for row in reconstruction_rows
    if row.get("status") == "ok"
}
G = {path.parent.name for path in root.glob("*/fx_graph_module.pt")}
V = {path.parent.name for path in root.glob("*/fx_process_visualization.md")}
D = {
    path.name
    for path in root.iterdir()
    if path.is_dir() and re.fullmatch(r"input\d+_layer\d+", path.name)
}
if not (T == X == R == G == V == D):
    raise SystemExit(
        "coverage mismatch:\n"
        f"T={sorted(T)}\nX={sorted(X)}\nR={sorted(R)}\n"
        f"G={sorted(G)}\nV={sorted(V)}\nD={sorted(D)}"
    )

print(f"FX branch coverage ok: {len(T)} selected input-layer events")
PY
```

This proves event-level conservation:

```text
canonical T == trace X_ok == reconstruction R_ok
            == GraphModule events == manual visualization events
            == event directories
```

The automated audit proves file/event coverage, not diagram quality. The human
must also confirm that every companion explains and visualizes every process in
its reconstruction.

## Manual Completion Record

This runbook has no autonomous completion action. A human records the reviewed handoff
SHA-256, `contract_id`, FX trace root, selected-event count, final coverage
result, process-by-process visualization review, reviewer, and completion time.
Any missing/error event or unreviewed process leaves the branch incomplete.

## Outputs

```text
workload_analysis/fx/traces/<FX_TAG>/
  run_metadata.json
  selection_handoff.json
  fx_layer_events.csv
  fx_layer_trace_manifest.csv
  fx_process_reconstruction_manifest.csv
  fx_process_reconstruction_manifest.json
  <event_id>/
    fx_graph.py
    fx_graph.txt
    fx_graph_module.pt
    fx_graph_module/
    fx_nodes.json
    fx_trace_metadata.json
    fx_process_nodes.csv
    fx_process_reconstruction.json
    fx_process_reconstruction.md
    fx_process_visualization.md
```

## Completion Checks

- `REFERENCE_AUDIT` completes only with a read-only report of the historical
  tree and its gaps; the remaining checks apply to `FRESH_RUN`.
- A human explicitly started this combined runbook once with one reviewed
  Step-2 handoff path; only the two named existing Skills were applied at their
  documented phases, with no automatic routing, Steps 1–2 execution, or
  DispatchMode selection.
- Source trace, canonical manifest, image, event order/count, key-set digest,
  `contract_id`, and single-call occurrence gate remain valid.
- Runtime eager sampling, offline dry-run specialization, and fixed-branch FX
  evidence remain distinct; every event retains matching specialization metadata.
- Trace validation passed before reconstruction; reconstruction validation passed
  before manual visualization.
- Generated reconstruction evidence contains no manual additions; every event has
  a separate, complete `fx_process_visualization.md`.
- The historical reference tree remained unchanged.
- The final audit passes `T == X == R == G == V == D`, with no duplicate, stale,
  missing, or error events, and the human process-by-process review is complete.
