# Formal fresh R10 execution

Read this reference only for a scheduler-owned fresh stage. Retained
restoration/presentation follows the skill entrypoint and never writes a fresh
handoff. The shared Process/resource contract defines analytical views;
full-archive conservation rules here do not force every row onto those views.

## Inputs

Require `user.evidence_acquisition_mode=fresh_no_prior_runtime_reuse`, complete
R06-R09 handoffs, one matching `lineage_id`, and hashed references to:

- R09 `fresh_e2e_analysis.json` and every normalized table;
- R07 request/process/runtime/kernel/live-utilization evidence;
- R08 capabilities, hardware metrics and traffic/resource model;
- R06 visualization capability attempts and selected backend.

Every runtime input must be inside the same run directory. Reject archived
dashboards, another run's HTML/trace, user-supplied tables and external network
assets.

## Lineage and Source Changes

R10 may modify the maintained visualization generator, validator, schemas, or
offline assets. Record these changes in `R10_SOURCE_LINEAGE.json`; source-hash
equality with earlier stages is not required. The R09 data hashes and semantics
are immutable inputs and generated pages must reproduce them exactly.

## Generator

Use:

```bash
python3 pra2026-bh408/scripts/perf_trace/generate_fresh_e2e_visualization.py \
  --analysis-manifest <same-run-R09-fresh_e2e_analysis.json> \
  --output-dir <runtime_artifact_root>/acceptance
```

Do not hand-edit generated HTML or its manifest. Embed JavaScript and data
locally. Acceptance must work after copying the directory to a machine with no
container network, SSH tunnel, HTTP server, package install, or remote CDN.

## Top-Latency Process Colors and All Rectangle Labels

Make the ten largest observed process-latency contributors immediately
distinguishable in both `E2E_PROCESS_TIMELINE.html` and
`E2E_PROCESS_TIMELINE_LOSSLESS.html`.

Derive the ranking once, before rendering, from the complete immutable R09
`process_timeline` table. For each valid row, use the exact non-replay HIPTX
duration `hiptx_end_ns - hiptx_begin_ns`; sort by duration descending, then
`hiptx_begin_ns` ascending and exact `process_range` ascending. Select
`min(10, valid_process_count)` rows. Never rank from the current viewport,
filtered rows, sampled events, kernel busy time, replay duration, or inferred
traffic. If duplicate `process_range` rows exist, fail instead of silently
merging them.

Assign ranks 1 through 10 this fixed, color-blind-conscious palette in order so
the mapping is deterministic across regeneration, filtering, zoom and both
pages:

```text
#4E79A7 #F28E2B #E15759 #76B7B2 #59A14F
#EDC948 #B07AA1 #FF9DA7 #9C755F #BAB0AC
```

Treat the scheduler-supplied `timeline_visualization` fields
`top_latency_process_color_count`, `top_latency_process_palette`, and
`show_process_name_when_zoomed` as immutable presentation requirements. Also
require `rectangle_label_groups` to equal request, forward, layer, process,
HIP runtime, GPU queue and strict-owned kernel in that order, and require
`show_all_timeline_labels_when_zoomed=true`. Fail if any field disagrees with
this contract.

Use the rank color as the fill for each selected process HIPTX interval. Keep
the existing track/evidence fill semantics for its exact-owned HIP runtime,
GPU queue and kernel intervals, but add a clearly visible outline or top stripe
in the same rank color. Match ownership only by exact `process_range`; never by
substring, event proximity or time overlap. Non-top-ten processes retain the
ordinary process color.

Render a semantic label inside every request, forward, layer, process HIPTX,
HIP runtime, GPU queue and strict-owned kernel rectangle whenever the current
zoom provides enough space. Use the exact process name for process rectangles
and the exact normalized event label for every other group. Measure text after
every zoom, pan, filter and resize; clip it to the rectangle. Show the full
label when it fits, otherwise show the longest fitting prefix plus an ellipsis
once the rectangle is wide enough for a useful label, and omit inline text when
it is too narrow. Choose black or white text from the actual fill-color
luminance. Keep the unshortened label in click details.

Embed a `top_latency_processes` payload in both pages. Each entry must include
the rank, exact process range, observed duration in integer nanoseconds, its
share of the sum of all valid observed process durations, its ratio to the
observed request span, and the assigned hex color. The two ratios must be
separately named and the request-span ratio must carry the caveat that
overlapping process intervals are not additive end-to-end attribution. Show
the same information in a persistent ten-item color legend and in interval
tooltips/details; long process names may be visually shortened only when the
full exact name remains available via tooltip and copyable detail.

The complete Perfetto-compatible trace must carry the rank, color and both
ratios in event arguments for selected process-owned events without changing
timestamps, categories, track IDs or event counts. Record the ranking policy,
palette, selected mappings and denominator totals in
`full_timeline_manifest.json` and `offline_acceptance_manifest.json`.

Never call a structural Chrome JSON check an official Perfetto parse. If the
official Python/CLI interfaces are unavailable, retain the compatible trace
candidate and visibly label the self-contained Plotly/custom viewer. This is a
presentation capability distinction, not runtime evidence degradation.

## Native Trace Exports

Native hipprof PFTrace/Chrome JSON exports are optional acceptance companions.
Operate only on disposable copies of current-run DBs, record source/copy hashes,
and prove the source DB unchanged. Do not replace the required normalized
pages with a raw native viewer.

## Handoff

Write only the scheduler-assigned R10 handoff:

```json
{
  "runtime_goal": "R10",
  "status": "complete",
  "execution_status": "complete",
  "evidence_status": "complete",
  "coverage_target_met": true,
  "next_authorization_required": false,
  "fresh_e2e_evidence": {
    "schema_version": 1,
    "status": "complete",
    "lineage_id": "...",
    "offline_acceptance_manifest": {"path": "...", "sha256": "..."},
    "source_lineage": {"path": "...", "sha256": "..."}
  }
}
```


## Fresh R10 artifact acceptance

The full evidence bundle retains `index.html`, `E2E_PROCESS_TIMELINE.html`,
`E2E_PROCESS_TIMELINE_LOSSLESS.html`, `E2E_PROCESS_TIMELINE.full.perfetto.json`,
`full_timeline_manifest.json`, both analytical pages,
`offline_acceptance_manifest.json`, `R10_SOURCE_LINEAGE.json` and
`R10_COMPLETION_AUDIT.json`. Additional view-plan, resource and coverage
sidecars must be sealed, not rejected because they enlarge a legacy fixed file
count. Handoffs remain outside business-artifact manifests.

The two analytical pages follow the shared Process/resource contract, not an
all-records-visible requirement. The full archive retains every source row,
classification, unavailable state and complete-event identity. Seal each
artifact's distinct role, visible scope and source hashes; the full archive's
`complete_timeline` claim must not be copied onto a hardware-filtered view.

The independent audit checks the shared visual contract plus the formal prefix,
profile, target, topology, all source table hashes, full-event conservation,
source-lineage sealing and offline operation. Complete handling of declared
coverage is distinct from 100% hardware availability. Missing expected source
bytes, concealed missing targets or a false complete-token claim still fail.

Current repository `build_process_duration_piles.py` is a retained-schema
adapter, not a direct fresh R09-table renderer. Before a fresh run, verify the
bound artifact-local R10 builder implements the current profile. If not,
report the missing implementation; do not relabel a retained build as formal
R10 or rewrite an archived handoff. A formal implementation must prove the
same derived view plan and audits against its native twelve-table input.
