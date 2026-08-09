---
name: qwen-dcu-workflow05-trace-visualization-reporting
description: Execute R10 for one Qwen3.5-27B fresh R01-R10 lineage. Consume only the same run's hashed R09 analysis plus R07/R08 evidence, permit audited visualization-tool source changes without source-hash equality, and generate a self-contained offline acceptance bundle with complete request/process timelines, high-latency hardware views, concurrency/utilization views, evidence boundaries, and deterministic validation.
---

# Qwen DCU Fresh E2E Visualization and Reporting

## Objective

Create the offline acceptance bundle for the single fresh-run lineage. R10 is a
presentation/validation stage only: do not run the model, GPU, profiler, new
trace, PMC replay, or additional sampling.

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

## Required Views

Generate these files:

```text
index.html
E2E_PROCESS_TIMELINE.html
HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html
CONCURRENCY_UTILIZATION.html
```

The views must provide:

- the complete observed request, forward/layer, process HIPTX, HIP runtime,
  queue and strict-owned kernel timeline on the R07 clock;
- filters, search and zoom for process/event/layer/phase/family;
- high-latency process windows with exact owned kernels and in-window live SE
  samples;
- active kernel/queue counts, launch gaps, overlap and opportunity states;
- visibly separate tracks/styles for observed utilization, replay-projected
  PMC/resources, inferred FX-visible traffic and unavailable values;
- explicit evidence tooltips, provenance, hashes and semantic caveats.

The maintained generator must consume all twelve entries in R09
`normalized_tables`. It must fail if a table is absent or changed; it may not
fall back to the former five-table summary contract.

Never call a structural Chrome JSON check an official Perfetto parse. If the
official Python/CLI interfaces are unavailable, retain the compatible trace
candidate and visibly label the self-contained Plotly/custom viewer. This is a
presentation capability distinction, not runtime evidence degradation.

## Native Trace Exports

Native hipprof PFTrace/Chrome JSON exports are optional acceptance companions.
Operate only on disposable copies of current-run DBs, record source/copy hashes,
and prove the source DB unchanged. Do not replace the required normalized
pages with a raw native viewer.

## Validation

Independently verify:

- all four pages exist, parse, and contain no external script/resource URL;
- embedded row counts and hashes equal the R09 manifest;
- request bounds and high-latency selections reproduce R09;
- every required observed/live/replay/inferred/unavailable legend is present;
- no cross-clock or replay-latency arithmetic appears;
- all links are relative and resolve inside the acceptance directory;
- regeneration from the same inputs is deterministic.

Write `offline_acceptance_manifest.json`:

```json
{
  "schema_version": 1,
  "status": "PASS",
  "lineage_id": "...",
  "self_contained_offline": true,
  "generator": {"path": "...", "sha256": "..."},
  "source_analysis": {"path": "...", "sha256": "..."},
  "source_table_hashes": {
    "request_timeline": "...",
    "process_timeline": "...",
    "kernel_timeline": "...",
    "live_utilization_aligned": "...",
    "process_live_utilization": "...",
    "kernel_concurrency": "...",
    "queue_concurrency": "...",
    "launch_gaps": "...",
    "high_latency_processes": "...",
    "dependency_state": "...",
    "traffic_resource_attachment": "...",
    "opportunity_candidates": "..."
  },
  "outputs": {
    "index.html": {"path": "...", "sha256": "..."},
    "E2E_PROCESS_TIMELINE.html": {"path": "...", "sha256": "..."},
    "HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html": {"path": "...", "sha256": "..."},
    "CONCURRENCY_UTILIZATION.html": {"path": "...", "sha256": "..."}
  },
  "view_coverage": {
    "track_groups": ["request", "forward", "layer", "process", "hip_runtime", "gpu_queue", "strict_owned_kernel", "live_utilization", "hardware_attributes", "dependency", "opportunity"],
    "filters_search_zoom": true,
    "source_table_hashes_verified": true,
    "evidence_legends_complete": true
  }
}
```

## Required Outputs

Write under `runtime_artifact_root`:

```text
R10_SOURCE_LINEAGE.json
acceptance/index.html
acceptance/E2E_PROCESS_TIMELINE.html
acceptance/HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html
acceptance/CONCURRENCY_UTILIZATION.html
acceptance/offline_acceptance_manifest.json
R10_COMPLETION_AUDIT.json
```

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

## Stop Conditions

Stop for external runtime/network input, lineage mismatch, source-analysis hash
drift, missing page, row-count mismatch, external asset, broken link, semantic
conflation, nondeterministic generation, hand editing, or any new GPU/profile
activity.
