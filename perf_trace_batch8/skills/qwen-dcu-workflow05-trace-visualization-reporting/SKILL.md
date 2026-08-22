---
name: qwen-dcu-workflow05-trace-visualization-reporting
description: Build and independently audit the project-bound R10 self-contained offline acceptance bundle and lossless full-resolution timeline from the same-run R01-R09 batch8 DP2 lineage, without running the model or accelerator stack.
---

# Qwen DCU Workflow 05 Trace Visualization and Reporting

## Scope and Stage Boundary

This project skill owns runtime Goal R10 and only R10 on branch
`workflow01-10-fresh-e2e`. It consumes the exact same-run R01-R09 runtime
prefix, renders the R09 twelve-table analysis together with the R07 observed
clock and R08 replay-projected attributes, and produces one independently
audited, self-contained offline acceptance bundle. R10 is the terminal stage
of the fresh R01-R10 lineage.

R10 is CPU-only. It must not initialize or run Qwen3.5-27B, contact a serving
endpoint, query or use a GPU/DCU, invoke HIP or KFD, run a profiler, collect a
trace, replay PMC counters, or regenerate any R01-R09 measurement or analysis.
It may generate only the offline HTML, full-resolution Perfetto JSON,
manifests, source-lineage record, and audit declared below. R07 remains the
sole observed latency clock. R08 contributes only explicitly labeled
`replay_projected` hardware attributes; its replay timestamps and durations
never enter an observed axis.

R10 does not plan targets, instrument the model, capture a request, normalize
R09 tables, infer missing evidence, claim a root cause or speedup, patch the
trace target, or start a successor. It imports no historical, backup,
external-run, prior one-card, or separately generated analysis or
visualization. Definitions, taxonomy, marker vocabulary, schemas, and
reconstruction methods under
`/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile` may be consulted as
implementation guidance, but its timings, traces, mappings, runtime handoffs,
and measurement evidence are inadmissible.

The outer serial scheduler creates the formal R10 Goal. This skill must never
call `create_goal`, create a nested Goal, invoke another project skill, run an
Adapt Goal, edit scheduler state, or create an R11. It was created by
migration-only Adapt Goal A10. Creating or statically validating this file is
not R10 execution, report generation, or performance-workflow evidence.

## Migration Provenance

This is a `synthesize_uncovered` project skill whose only pinned workflow
source is:

~~~text
workflow_path=/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/workflows/05_workflow04_guided_selective_process_trace_and_resource_gap_analysis.md
workflow_sha256=d4ed4a1a265c79b0579c7f695f9c66585ef9588f14ee3aea072707097eb77d39
adapt_goal=A10
reference_skill_inputs=none
workflow_execution_performed=false
project_skill_execution_performed=false
~~~

No reference skill was selected or invoked. This skill directly packages the
uncovered R10 semantics: exact same-run prefix admission, complete batch8 DP2
identity preservation, R07/R08/R09 evidence separation, lossless
full-resolution timeline construction, integer-safe browser coordinates,
unbounded overlap inspection, self-contained offline pages, deterministic
manifests, source-lineage sealing, independent browser/content audit, and the
terminal acceptance gate.

## Immutable Project Binding

Before creating any promotable R10 business output, fail closed unless these
bindings are exact:

~~~text
project_root=/public/home/tangyu408/Qwen_DCU_Worker_0
trace_target_root=/public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408-gqa-page784-k5120-batch8
trace_target_git_commit=2b4b2119ae3cc2c4c626dc5690ef9593c1477f66
trace_target_git_branch=repro-gqa-page784-k5120-batch8-final
trace_profile_path=/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/configs/trace_targets/batch8_dual_dcu_dp2.json
trace_profile_sha256=3b4c952063f48ae662b48b5ce9d8fd76e0ac4d74e170bdb1839ae8b1aaa23cce
trace_profile_schema_version=1
trace_profile_id=batch8-dual-dcu-dp2
project_runtime=vLLM
served_model_name=Qwen3.5-27B
model_dtype=bfloat16
accelerator=ROCm/DCU/HIP gfx936
native_marker_backend=HIPTX/ROCTX
runtime_trace_vocabulary=HIP runtime and HIPOPS
hardware_attribute_source=HIPProf targeted PMC
evidence_acquisition_mode=fresh_no_prior_runtime_reuse
analysis_strategy=fresh_run_full_request_e2e_timeline
measurement_contract_policy=same_run_same_request
~~~

The target checkout is read-only for R10. Validate its commit, branch, clean
index, clean worktree, absence of untracked files, and the following source
identities at admission and again before the runtime handoff. Do not import the
target Python package merely to prove identity, and never patch, chmod, build,
cache, or write below the target.

| Role | Target-relative path | SHA-256 |
| --- | --- | --- |
| Qwen3.5 model and linear-attention implementation | `vllm/model_executor/models/qwen3_5.py` | `f3c0479dbc37a8794c4d6b1c4c01906ae341b3276ed43e588c17d92b1ddb94d6` |
| inherited decoder and full-attention implementation | `vllm/model_executor/models/qwen3_next.py` | `5a14b14a40fcf6382f9a20be4ca0f850b2b19b2840a3c57488821f0952d96053` |
| V1 execution and DP-rank boundary | `vllm/v1/worker/gpu_model_runner.py` | `d63424d3cbe81bfaa2c0967a5c81b8c980c2d76bc7eb3b2f8fe2a079af825bce` |
| compatibility marker hooks | `vllm/utils/nvtx_pytorch_hooks.py` | `e9711444f33242ce1864d6a32d051bbf0ba0b37b5f17965de6e5dbba0c0c75ff` |
| compiled-module marker wrapper | `vllm/compilation/wrapper.py` | `b4dca93456e945ce8231e9a954792c8f687d5d48b427ed38bfb96011015d4090` |
| DP2 service launcher | `scripts/serve_cscc_dp2.sh` | `233bb2ce6fee3654bc870e37e65b7ecf4de6874cb6c7fd1a6bd5687a40783699` |
| batch benchmark launcher | `scripts/bench_cscc_multi_request.sh` | `9b5e02116911729e901077866389e448c0e4a055e8bb901ed160dcdc7664a595` |
| gfx936 runtime environment | `scripts/cscc_gfx936_env.sh` | `58d483450c23e9c4fa87fb981b5e63cf4babf5e8d230fe93e400563596dfc18a` |
| DP2 design contract | `docs/cscc/DP2_MULTI_REQUEST.md` | `f83ebea84fd570908be0df58255eca371ad4c28c4dc9d70ec3db0401b1143569` |

The checkout may retain `NVTX`, `torch.cuda.nvtx`, or
`CUDA_VISIBLE_DEVICES` compatibility names. R10 evidence labels use native
HIPTX/ROCTX, HIP runtime, HIPOPS, and HIPProf terminology. Never present a
compatibility API name as NVIDIA profiler evidence. Target documentation and
historical benchmark results prove only project, model, runtime, and topology
bindings; their timings, charts, or conclusions cannot populate R10.

All R10 renderers, browser harnesses, schemas, resolved contracts, scratch
data, pages, trace JSON, manifests, lineage records, and audits live under the
scheduler-assigned R10 artifact root. Only the scheduler handoff is written to
its separately assigned handoff path. No R10 command may write to the target,
a predecessor artifact root, a predecessor handoff, or the cumulative ledger.

## Authoritative Workload and Complete DP2 Topology

The hash-pinned trace profile is the sole workload and topology authority:

~~~text
workload_mode=batch8_concurrent_requests
dataset_path=/home/testdata/16-32K_throughput.jsonl
batch_size=8
request_count=8
max_concurrency=8
request_rate=inf
output_tokens_per_request=1024
warmup_requests=2
temperature=0
ignore_eos=true
physical_devices=0,1
HIP_VISIBLE_DEVICES=0,1
CUDA_VISIBLE_DEVICES=0,1
world_size=2
tensor_parallel_size=1
pipeline_parallel_size=1
data_parallel_size=2
data_parallel_backend=mp
rank_to_physical_device=0:0,1:1
required_physical_devices=0,1
required_dp_ranks=0,1
required_measured_request_count=8
require_per_rank_and_per_device_artifacts=true
forbid_single_device_promotion=true
~~~

DP rank 0 maps to native physical DCU 0 and DP rank 1 maps to native physical
DCU 1. Although R10 is CPU-only, every admission check, page, track, filter,
tooltip, manifest, audit, source-lineage entry, and handoff must retain both DP
ranks, both native device identities, and that exact mapping. Never pool,
renumber, merge, infer, or drop a worker. A page or manifest representing only
one required rank/device cannot be promoted as batch8 DP2 acceptance.

The fixed request source is row zero of the dataset and is carried only
through the validated same-run predecessor chain:

~~~text
dataset_file_sha256=633ba4c8b4f500d2ab28094de42698c5494e5232f40eafcd119c0a314b44b936
dataset_row_0_bytes_sha256=06c7c1cc0e97951303631942dea7a2759fe7b693a79e06d495a164a2354146fd
~~~

R10 must not search the dataset, shuffle rows, synthesize or retokenize a
prompt, send a request, or substitute a local workload. It visualizes the
eight measured requests already sealed by R07 and R09. The two warmup requests
remain source metadata and must not be silently mixed into measured-event
counts. Serial R01-R10 ordering constrains stage overlap only; it never changes
the full DP2 contract.

## Serial Runtime Contract

~~~text
runtime_branch=workflow01-10-fresh-e2e
runtime_goal=R10
runtime_predecessors=R01,R02,R03,R04,R05,R06,R07,R08,R09
required_handoff_fields=status,execution_status,evidence_status,coverage_target_met,next_authorization_required,runtime_branch,runtime_goal,runtime_run_id,lineage_id,trace_profile_sha256,cumulative_runtime_ledger_sha256,r01_handoff_sha256,r02_handoff_sha256,r03_handoff_sha256,r04_handoff_sha256,r05_handoff_sha256,r06_handoff_sha256,r07_handoff_sha256,r08_handoff_sha256,r09_handoff_sha256,offline_acceptance_manifest_sha256,full_timeline_manifest_sha256,full_perfetto_trace_sha256,e2e_process_timeline_sha256,e2e_process_timeline_lossless_sha256,high_latency_process_hardware_timeline_sha256,concurrency_utilization_sha256,index_html_sha256,source_lineage_sha256,artifact_manifest_sha256,completion_audit_sha256
runtime_artifact_root=<scheduler-assigned>
runtime_handoff_output=<scheduler-assigned>
advance_only_after=complete
~~~

Before any runtime work, load and SHA-256 validate the scheduler-assigned R01,
R02, R03, R04, R05, R06, R07, R08, and R09 handoffs plus the cumulative
immutable runtime ledger. Consume exactly the ordered
`R01,R02,R03,R04,R05,R06,R07,R08,R09` prefix from the same scheduler run and
branch. Refuse a missing, failed, partial, duplicated, shorter, longer,
out-of-order, cross-run, cross-branch, external, or hash-mismatched
predecessor.

Require each predecessor to state `status=complete`,
`execution_status=complete`, `evidence_status=complete`,
`coverage_target_met=true`, and `next_authorization_required=false`. Require
one identical nonempty lineage ID, the pinned profile hash, target commit,
selected request hashes, complete rank/device mapping, and fresh evidence
status through R09. In particular, R09 must satisfy its explicit R10 advance
gate; a terminal but degraded R09 handoff is not an admission token.

Validate every transitive business-artifact hash against the direct handoff
that owns it. Preserve the cumulative-ledger hash, all nine direct handoff
hashes, predecessor artifact-manifest hashes, and every consumed business hash
in the resolved contract, R10 source-lineage record, artifact manifest,
completion audit, and handoff. An earlier ledger hash is an immutable prefix
view and must not be compared as though it were the later ledger bytes.

Write business outputs only under `runtime_artifact_root`. Write exactly one
scheduler handoff only to `runtime_handoff_output`, outside the business
artifact manifest, and only after all applicable R10 checks pass. Never edit a
predecessor artifact, handoff, ledger, project skill, or attempt. Because R10
is terminal, advancement means only that the scheduler validates and commits
the R10 handoff and closes this branch; it never authorizes an undeclared
successor.

## Fresh-lineage Admission and Producer Boundaries

The first R10 phase is a read-only CPU admission gate. It must prove:

1. The branch is exactly `workflow01-10-fresh-e2e`; the ledger belongs to the
   current runtime run; no external upstream ledger, Adapt output, ambient
   file, backup, historical timing, prior one-card evidence, or previous
   visualization was accepted.
2. The ledger contains exactly R01-R09 in order, and all direct/transitive
   handoff, manifest, and business-output paths and hashes validate under the
   owning stage's root.
3. Runtime run ID, lineage ID, trace-profile hash, target identity, selected
   input hashes, request semantics, ranks, native devices, and mapping are
   identical across the prefix.
4. R07 is the only source of observed request, process, runtime, queue,
   strict-owned-kernel, GPU-busy, and live-utilization time. Its raw samples,
   gaps, anchors, uncertainty, availability, and dependency adapter remain
   losslessly represented.
5. R08 owns capability states, targeted PMC, and traffic/resource attributes;
   all replay time is excluded from latency, concurrency, and timeline event
   positions.
6. R09 exposes a hash-valid `full_request_analysis` and `source_lineage`,
   exactly twelve normalized tables, `complete_timeline=true`,
   `sampling_performed=false`, complete source universes, and an independent
   completion audit.
7. Every measured request, DP rank, native device, process/fragment, kernel,
   queue, utilization sample/gap, dependency, and hardware attachment remains
   attributable or explicitly unavailable/unknown. Missing or duplicate join
   keys are terminal states, never silently dropped or guessed.

R10's direct business inputs are the exact R09 analysis plus the R07/R08
evidence referenced and hash-sealed through the R09 handoff. R01-R06 artifacts
are consumed only as transitive lineage and denominator proofs. Do not bypass
R09 by rebuilding its tables, and do not accept a file merely because it has a
familiar name.

Resolve project-relative paths against the scheduler project root and
artifact-relative paths against the predecessor root declared by the owning
handoff. Never resolve a predecessor path against the current R10 artifact
root. Exercise the production resolver with a project-root-relative positive
case, an absolute-path positive case, and a traversal/containment negative
case before accepting inputs.

Write the admission result to
`contract/r01_r02_r03_r04_r05_r06_r07_r08_r09_predecessor_validation.json`.
A failed admission may write only attempt-local diagnostics and cannot create
acceptance pages, a complete handoff, or a branch-completion claim.

## Required R09 Input Surface

Read `analysis/fresh_e2e_analysis.json` from the exact R09 handoff. It must
index exactly these twelve ordered logical tables and their contained paths,
byte sizes, SHA-256 values, row counts, ordered schemas, schema hashes, stable
sort keys, lineage IDs, evidence classes, and request/rank/device coverage:

~~~text
request_timeline
process_timeline
kernel_timeline
live_utilization_aligned
process_live_utilization
kernel_concurrency
queue_concurrency
launch_gaps
high_latency_processes
dependency_state
traffic_resource_attachment
opportunity_candidates
~~~

Require the R09 manifest to state the exact R07 observed-clock identity, the
exclusion of R08 replay time from latency, complete source denominators,
lossless utilization gap/availability accounting, and no Top-N, sampling, or
fixed event budget. Recompute every input hash, size, row count, schema hash,
and containment relation before rendering. Eleven valid tables do not form a
valid R10 input.

Also hash-validate the R07 `full_request_profile_metadata`,
`process_trace_summary`, `fresh_run_dependency_adapter`,
`live_utilization_summary`, and `source_lineage`, and the R08
`device_capabilities`, `targeted_pmc_manifest`, `traffic_resource_model`, and
`source_lineage`, exactly as sealed through R09. These inputs verify evidence
class and lineage; they may not introduce new rows that are absent from the
R09 normalized tables.

## Evidence Classes and the Unique Observed Clock

Every page, track, legend, tooltip, table, filter result, manifest entry, and
audit must preserve these evidence classes or an equally strict field-level
mapping:

- `observed_r07`: request, process, HIP runtime, queue, and strict-owned kernel
  intervals from the sole non-replay R07 clock;
- `observed_r07_live_utilization`: actual R07 samples, gap intervals, anchors,
  uncertainty, and eligible process aggregates;
- `replay_projected`: R08 PMC, device, traffic, and resource attributes joined
  to R07 identities without replay timestamps;
- `derived_static`: deterministic identity, taxonomy, schema, or dependency
  structure that uses no measured or replay value;
- `derived_from_observed_r07`: concurrency, busy union, launch gap, overlap,
  and latency classification derived solely from R07;
- `derived_from_observed_and_replay_projected`: an explicitly labeled join or
  rule combining R07 observed fields with R08 attributes; and
- `unavailable` or `unknown`: a preserved absence with reason and provenance,
  never a numeric zero, empty visual gap, or inferred value.

R07 live-utilization gaps are an independent visible evidence track. Render a
numeric utilization value only for a process marked `available` by R09 after
at least three eligible true samples, no intersecting unobserved gap, and
valid alignment uncertainty. Keep every raw sample, slow call, gap, anchor,
and unavailable reason. Never interpolate, resample, smooth, smear, impute,
zero-fill, hide, or describe unavailable utilization as low utilization.

R08 replay begin/end, replay duration, counter-pass order, and capture wall
time are diagnostics only. They must not set an event coordinate, enter a
request/process/kernel duration, drive concurrency or gap calculation, rank a
high-latency process, or be added to R07 time. A replay-projected attribute may
appear beside an observed event only with a distinct evidence badge, legend,
field provenance, unit/formula/capability state, and source hash.

Opportunity candidates are investigation hypotheses. Never label them as
measured speedup, predicted speedup, proven root cause, accepted optimization,
or authorization to change the target.

## Artifact-local Tools, Commands, and Output Layout

Resolve one CPU-only interpreter and, when available, one local offline browser
through the scheduler environment. Record each absolute path, executable
bytes, version, SHA-256, and capability result. R10 tools are generated or
copied only below the current artifact root, reviewed before use, and frozen
before they read business inputs:

~~~text
tools/build_r10_acceptance.py
tools/audit_r10_acceptance.py
tools/run_r10_offline_browser_acceptance.py
contract/resolved_r10_contract.json
contract/r01_r02_r03_r04_r05_r06_r07_r08_r09_predecessor_validation.json
acceptance/index.html
acceptance/E2E_PROCESS_TIMELINE.html
acceptance/E2E_PROCESS_TIMELINE_LOSSLESS.html
acceptance/E2E_PROCESS_TIMELINE.full.perfetto.json
acceptance/full_timeline_manifest.json
acceptance/HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html
acceptance/CONCURRENCY_UTILIZATION.html
acceptance/offline_acceptance_manifest.json
R10_SOURCE_LINEAGE.json
R10_COMPLETION_AUDIT.json
artifact_manifest.json
~~~

The scheduler-resolved CPU commands have this semantic shape:

~~~text
<r10_python> <runtime_artifact_root>/tools/build_r10_acceptance.py --resolved-contract <runtime_artifact_root>/contract/resolved_r10_contract.json --artifact-root <runtime_artifact_root>
<r10_python> <runtime_artifact_root>/tools/run_r10_offline_browser_acceptance.py --resolved-contract <runtime_artifact_root>/contract/resolved_r10_contract.json --acceptance-root <runtime_artifact_root>/acceptance --output <runtime_artifact_root>/attempts/<attempt-id>/offline_browser_acceptance.json
<r10_python> <runtime_artifact_root>/tools/audit_r10_acceptance.py --resolved-contract <runtime_artifact_root>/contract/resolved_r10_contract.json --offline-manifest <runtime_artifact_root>/acceptance/offline_acceptance_manifest.json --artifact-root <runtime_artifact_root>
~~~

Read and hash-validate R06's Perfetto, Plotly, and offline-display capability
states through the predecessor chain. A missing optional plotting package does
not authorize a CDN or a reduced event set: use a frozen, artifact-local,
lossless fallback. The full Perfetto JSON remains mandatory even when no
Perfetto Python package is installed. If no validated local browser can run the
required interaction checks, preserve the capability reason and report
insufficient evidence rather than claiming offline acceptance.

Do not substitute a target launcher, model script, profiler, trace collector,
PMC tool, R09 table builder, cloud renderer, remote visualization service, or
network-hosted asset for these CPU-only commands. Record exact argv, cwd,
environment allowlist, start/end clocks, exit status, stdout/stderr paths,
interpreter/browser/tool hashes, input-manifest hashes, and output inventory.
The builder, browser acceptance harness, and auditor are separate invocations;
the auditor must not trust mutable in-memory state from either earlier step.

Every canonical page is UTF-8 with LF line endings and embeds its required CSS,
JavaScript, fonts or font fallback declarations, schemas, and display data.
No glob-discovered file, temporary partial, diagnostic, scheduler handoff,
repair output, CDN asset, or remote response enters the business artifact
manifest.

## Lossless Full-resolution Timeline Contract

Design the local viewing host for at least 128 GiB of memory. File size,
renderer cost, browser load, or convenience is never a reason to discard or
irreversibly aggregate events. Forbid sampling, uniform point selection,
Top-N selection, fixed event budgets, event-count caps, hidden tail removal,
coalescing distinct intervals, or lossy binning.

The full Perfetto event count is exactly:

~~~text
full_perfetto_event_count = request_timeline_row_count
                            + process_timeline_row_count
                            + 2 * kernel_timeline_row_count
~~~

For every R09 kernel row, emit two records with the exact same observed
interval and immutable kernel identity:

1. one `strict_owned_kernel` record organized beneath its exact owning process
   or fragment; and
2. one `gpu_queue` record organized beneath its exact DP rank, native device,
   and queue/stream.

These are two display organizations of one observed interval, not two kernel
executions and not additive time. Give the pair a shared source-row identity,
display-copy index, and observed-interval hash. Audits must count both records
while union/duration summaries count the source interval once.

Emit every request and process row exactly once. Preserve parent/fragment
identity, no-kernel states, overlap sub-lane, request, layer, phase, family,
event, track, runtime correlation, rank, native device, queue/stream,
begin/end, duration, evidence class, and source-row hash. No name, proximity,
or pixel-location heuristic may replace exact identity.

The following manifest declarations are literal and mandatory:

~~~text
complete_timeline=true
sampling_performed=false
formal_r09_r10_regeneration=true
~~~

`formal_r09_r10_regeneration=true` means the accepted R09 analysis and R10
bundle were generated in the current formal fresh lineage. It does not permit
R10 to rerun R09 or to adopt a prior visualization.

An overview may show reversible density coverage while zoomed out, but the
complete underlying event array must remain present and addressable. Density
pixels are presentation caches only: they cannot replace, merge, reorder, or
rewrite source events, enter the lossless event count, or become timing
evidence.

## Integer-safe Time and Coordinate Rules

Retain every absolute `begin_ns` and `end_ns` as a canonical base-10 integer
string. Never parse an approximately `1.7e18` absolute nanosecond timestamp as
a JavaScript `Number` before subtraction. Validate decimal syntax and ordering
with an integer-safe implementation such as `BigInt`, then derive exact
relative offsets.

Use a manifest-pinned `request_begin_ns` equal to the exact beginning of the
complete measured-request envelope. Browser coordinates are signed or
unsigned integer nanosecond offsets from that origin. Preserve each event's
owning request begin and exact request-relative offsets as well, so all eight
concurrent requests remain independently auditable. Any conversion to a
floating viewport coordinate occurs only after subtracting the origin and
only when the displayed span is proven exactly representable at the chosen
zoom.

All intervals are half-open `[begin_ns,end_ns)`. Use deterministic end-before-
start ordering at equal timestamps. A minimum viewport must be no coarser than
1 ns. Labels may format a duration for humans, but exact decimal nanoseconds
remain visible and are used for jump, selection, filtering, and audit.

## Required Timeline Interaction

`acceptance/E2E_PROCESS_TIMELINE_LOSSLESS.html` must provide all of the
following over the complete embedded event universe:

- continuous wheel or equivalent zoom centered at the pointer position, down
  to a viewport no coarser than 1 ns;
- drag pan, box zoom or an explicit zoom control, reset, and at least 100 exact
  back/forward view-history states;
- full-text filters for process, event, layer, phase, family, and track, plus a
  deterministic fit-to-filter action;
- separate request, forward, layer, process, HIP runtime, queue, and kernel
  tracks with deterministic overlap sub-lanes;
- click inspection that returns every event intersecting the selected pixel or
  exact interval, with no result-count limit and a displayed total;
- exact begin/end jump controls and an unbounded listing of every event in the
  current viewport;
- a density overview that never deletes or mutates the underlying events; and
- independent location and exact-field inspection for every original event
  after sufficient zoom.

Filtering changes visibility only, never the source array or manifest counts.
The page must disclose active filters, visible and total counts, request/rank/
device coverage, coordinate origin, viewport bounds, event evidence class,
source table/row/hash, and whether a kernel mark is its process-track or queue-
track display copy.

## Acceptance Pages and Evidence Semantics

`acceptance/index.html` is the single human entry point. It links by contained
relative paths to every required page, the full Perfetto JSON, the two
manifests, the source-lineage record, and the completion audit; summarizes the
exact target, profile, workload, topology, run, lineage, coverage, evidence
state, and audit result; and explains how to use the lossless page offline.

`acceptance/E2E_PROCESS_TIMELINE.html` is a self-contained overview of all
eight measured requests and the full event denominator. It may use reversible
density or summary views but must link to and state the hash of the lossless
page and full Perfetto trace. It may not present a sampled overview as the
complete timeline.

`acceptance/HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html` renders the complete
R09 high-latency classification, including all ties and the full denominator,
beside exact R07 process/kernel intervals and exactly attached R08 hardware
attributes. Show global and comparable-group thresholds, rule versions,
join/cardinality state, units, formulas, rank/device, capability, and
unavailable/unknown reasons. Do not truncate to Top-N or claim that an
association proves causality or speedup.

`acceptance/CONCURRENCY_UTILIZATION.html` renders exact R07-derived kernel and
queue concurrency, launch gaps/overlaps, GPU-busy unions, raw live samples,
gap intervals, alignment uncertainty, and process availability across both
ranks and native devices. It must visibly distinguish observed utilization,
derived concurrency, replay-projected attributes, and unavailable windows.

Every page must visibly and textually distinguish:

~~~text
observed R07 timing
observed live utilization
replay_projected R08 hardware attributes
derived analysis
unavailable/unknown evidence
~~~

Use distinct legend entries, patterns or colors, tooltips, and accessible text
labels. Color alone is insufficient. Replay-projected or unavailable values
must never look like observed timing, and opportunity candidates must never
look like achieved performance gains.

## Self-contained Offline Boundary

All pages must operate from local immutable bytes with no CDN, remote script,
remote font, analytics beacon, cloud upload, network fetch, dynamic package
install, external API, WebSocket, or runtime service. Inline the required code
and data into each HTML page. Relative navigation among declared acceptance
files is allowed; a page must not need another file to render its own required
view.

The offline audit must combine static inspection with a network-denied local
browser run. Reject remote URL schemes, external script/link/image/media
sources, `fetch`, `XMLHttpRequest`, WebSocket/EventSource, dynamic module
imports, service-worker registration, and any attempted network connection.
Record the browser binary/hash/version, isolation flags, network-denial
mechanism, console errors, page errors, and attempted requests. Zero attempted
network requests is required for complete evidence.

Do not upload the Perfetto trace to a hosted viewer. The standalone JSON is a
portable offline artifact; any optional local viewer instructions must remain
non-authoritative and cannot replace the lossless HTML or browser audit.

## `full_timeline_manifest.json` Contract

Write `acceptance/full_timeline_manifest.json` only after all timeline and
page candidate files close successfully. It must contain:

- schema and renderer-algorithm versions; runtime run, formal Goal, and
  lineage IDs; exact profile and target identities; selected-request hashes;
  full workload/topology; and R01-R09 handoff/ledger hashes;
- the R09 `fresh_e2e_analysis.json` path, byte size, SHA-256, lineage ID, and
  exactly twelve ordered table entries with their paths, sizes, hashes, row
  counts, ordered schemas, schema hashes, sort keys, evidence classes, and
  coverage;
- request/process/kernel source row counts, the exact event-count formula,
  expected and actual per-class counts, the two kernel display-copy counts,
  pair conservation, source-row identity hashes, and total Perfetto count;
- `complete_timeline=true`, `sampling_performed=false`,
  `formal_r09_r10_regeneration=true`, and explicit no-Top-N/no-fixed-budget/no-
  irreversible-aggregation declarations;
- the exact observed-clock origin, integer/decimal time representation,
  half-open interval and tie rules, minimum viewport, and absolute exclusion
  of replay timing;
- every required timeline/analysis HTML and Perfetto JSON contained path,
  byte size, SHA-256, MIME/format, embedded-data hash, evidence classes, and
  request/rank/device coverage;
- utilization sample/gap/anchor/availability counts and reasons with no hidden
  gaps or imputation; and
- renderer/interpreter/tool, invocation, source-input, and candidate-output
  provenance hashes. Later manifests and audits seal this manifest rather than
  creating a circular self-reference.

The manifest must not point outside `runtime_artifact_root`, except to sealed
read-only predecessor inputs explicitly listed by path and hash. It must not
include the scheduler handoff. A path, count, schema, lineage, event, coverage,
or hash mismatch invalidates the complete timeline.

## `offline_acceptance_manifest.json` Contract

Write `acceptance/offline_acceptance_manifest.json` after the candidate pages,
full trace, timeline manifest, and browser acceptance result exist. It must
seal:

- the exact presentation payload—`index.html`, the four visualization pages,
  the full Perfetto JSON, and `full_timeline_manifest.json`—and each contained
  path, byte size, SHA-256, content type, schema/version, and logical role;
- the single-entry `index.html` navigation graph and proof that every declared
  local target exists and hash-validates;
- per-page embedded code/data hashes, source table/row/event counts,
  evidence-class counts, request/rank/device coverage, legends, filters,
  interaction capabilities, and exact-coordinate rules;
- the lossless-page and Perfetto event counts and their equality to the R09
  formula, including the paired-but-nonadditive kernel organization;
- all static no-network checks and the network-denied browser results for zoom,
  pan, box/control zoom, reset, 100-step history, filters, fit, exact jump,
  overlap inspection without caps, viewport listing without caps, density
  overview, 1 ns minimum viewport, and independent event selection;
- observed/live/replay-projected/derived/unavailable presentation separation,
  unavailable reasons, and absence of causality or speedup claims; and
- exact builder/browser/auditor invocations, tools, environment, logs, result
  hashes, attempt/revision history, and final evidence decision.

The manifest is an acceptance index, not self-authenticating evidence. It does
not hash itself or later lineage/audit files. Its path and SHA-256 are sealed
by `R10_SOURCE_LINEAGE.json`, `R10_COMPLETION_AUDIT.json`,
`artifact_manifest.json`, and the runtime handoff.

## Source Lineage and Stage-source Audit

`R10_SOURCE_LINEAGE.json` must seal:

- runtime branch/run/formal Goal/lineage IDs and the exact R01-R09 ordered
  ledger prefix;
- profile path/hash/content identity, target commit/branch/clean state, source
  anchor paths/hashes, model/runtime/accelerator identity, selected request,
  workload, topology, ranks, native devices, and mapping;
- every consumed predecessor handoff, artifact manifest, business artifact,
  table schema/row universe, and source-lineage hash with its owning stage and
  evidence class;
- the unique R07 observed clock and live-utilization provenance, the R08
  replay-projected provenance, the R09 deterministic derivation provenance,
  and every R10 display transform;
- exact renderer/browser/interpreter bytes, argv, cwd, environment allowlist,
  attempt/revision history, page/trace/timeline-manifest hashes, and the
  completed offline-acceptance-manifest hash;
- every R10 stage-source delta with before/after source SHA-256, reason,
  affected output, semantic-contract assessment, and authorization; and
- declarations that no external runtime evidence, prior one-card evidence,
  model execution, accelerator work, device query, profiler, trace collection,
  PMC replay, target mutation, predecessor mutation, nested skill, Adapt Goal,
  or successor execution occurred in R10.

Changing renderer implementation without changing the selected input,
workload, clock, identity, evidence class, event membership, timing,
interaction, or acceptance semantics may remain in the lineage only when the
immutable revision history and all before/after tool/output hashes are
recorded. A semantic change stops the lineage; never splice pre-change and
post-change evidence into one fresh run.

## Deterministic Independent Audit

After the builder and browser harness exit, the frozen auditor independently
reads sealed inputs and on-disk outputs. It must at minimum recompute or verify:

1. exact prefix, source, profile, target, request, lineage, path-containment,
   schema, and every input/output hash;
2. exactly eight measured requests and complete rank 0/rank 1 plus native
   device 0/device 1 representation wherever the source universe applies;
3. exactly twelve R09 tables, their full row universes, ordered schemas,
   source-lineage closure, and exclusion of replay time from observed latency;
4. request rows emitted once, process rows emitted once, kernel rows emitted
   exactly twice with paired identity and equal observed intervals, and total
   Perfetto events equal to the required formula;
5. no sampling, Top-N, fixed event budget, hidden tail, lossy aggregation,
   event merge, float-corrupted absolute time, duplicate timing, or dropped
   no-kernel/unavailable/unknown state;
6. exact integer-safe request-relative coordinates, half-open intervals,
   deterministic tie rules, 1 ns minimum viewport, complete tracks, overlap
   sub-lanes, and source-row lookup for every event;
7. lossless utilization samples/gaps/anchors/availability and prohibition of
   interpolation, imputation, zero fill, or unavailable-as-low claims;
8. page legends, evidence badges, hardware units/formulas/capability states,
   exact joins, full high-latency ties/denominators, and absence of speedup or
   causality claims;
9. the exact nine pre-audit required deliverables, page and trace bytes,
   timeline/offline manifests, source-lineage closure, the declared path for
   the audit it is about to write, and exclusion of the scheduler handoff from
   every business manifest;
10. static self-containment plus network-denied browser operation of every
    required zoom, pan, history, filter, fit, jump, overlap, viewport-listing,
    density, and independent-event interaction with no result cap; and
11. no model, GPU/DCU, device query, profiler, trace, PMC, predecessor,
    successor, external service, network, or Adapt execution by R10.

The auditor writes only `R10_COMPLETION_AUDIT.json` and its own attempt-local
stdout/stderr. Its result records every check, denominator, observed value,
pass/fail state, source path/hash, and mismatch detail. A builder or page
self-declaration is not an independent audit. Any disagreement is fail-closed.

## Failure, Repair, and Formal Turn Liveness

Every build, browser, or audit attempt uses a new empty immutable attempt
directory and records inputs, tools, commands, logs, partial inventory,
hashes, and failure reason. Never overwrite a failed page or trace, add a
compatibility alias, patch embedded data in place, append missing events, or
promote a partial output. Repair a CPU-only renderer/browser/auditor defect in
a new `report-repair-NNN` root using the same sealed R01-R09 bytes, and record
before/after tool hashes plus the semantic-equivalence justification. Only a
fully audited repair may be promoted to canonical output paths.

Do not rerun A01-A11 or R01-R09, recapture a request, repeat a device pass,
rebuild an R09 table, or modify predecessor evidence to repair R10. If
predecessor integrity, lineage, coverage, browser capability, self-containment,
or evidence sufficiency cannot be proven, stop R10 and request the outer
scheduler's authorization; do not guess, fetch remote assets, import an older
report, or degrade to one rank/device. A failed stage writes no
acceptance-eligible handoff.

Large CPU-only renderers or auditors can be temporarily quiet. Monitor at
five-minute intervals. During a known large-file generation turn, require two
consecutive complete five-minute observations with no new content item, token,
subprocess progress, artifact size/mtime change, or reasoning item before any
interruption. Then interrupt only the cmdline-verified scheduler-owned PID,
never a process group or unrelated process. Preserve the partial attempt and
restart in a new immutable root.

If a formal R10 Goal becomes blocked, do not mutate the completed prefix or
claim branch acceptance. Resume from the scheduler's first incomplete R10
stage with the exact same run and lineage only after verifying scoped
processes are gone and recording retry authorization. Never fabricate a
handoff or infer success from existing HTML or a partial manifest.

## Deterministic Runtime Procedure

Execute R10 in this order:

1. Resolve scheduler-assigned artifact/handoff paths, runtime/formal Goal and
   lineage IDs, retry authorization, and current attempt root; prove business-
   output and scheduler-handoff separation.
2. Hash-validate the trace profile, read-only target binding, exact R01-R09
   ledger prefix, every direct/transitive predecessor output, the R07 unique
   observed clock, R08 replay boundary, R09 twelve-table contract, complete
   workload, and full DP2 identity. Seal the resolved contract and admission
   report.
3. Create or copy only artifact-local CPU renderers and auditors. Freeze the
   interpreter, optional browser, tool bytes, schemas, coordinate/event rules,
   argv, cwd, and environment. No target import, device query, or network is
   permitted.
4. Build the full event universe from the exact R09 row universes. Preserve
   integer-safe time, all source identities and evidence classes, and the
   exact request/process/twice-kernel count before any page rendering.
5. Generate the complete Perfetto JSON and all four self-contained HTML pages,
   including lossless interactions, gap/unavailable tracks, evidence legends,
   and exact source provenance. Generate `index.html` as the single entry.
6. Seal every timeline input/output count and hash in
   `full_timeline_manifest.json` without referencing later manifests or
   audits.
7. End the builder invocation. Run the network-denied offline browser harness
   independently against all required pages and preserve its result and logs.
8. Write `offline_acceptance_manifest.json` from frozen output bytes and the
   browser result, end that invocation, and then write
   `R10_SOURCE_LINEAGE.json` so it seals the offline-manifest hash.
9. Run the independent auditor as a separate invocation and write
   `R10_COMPLETION_AUDIT.json` only after its checks finish. The audit seals the
   source-lineage hash and does not refer to its own hash.
10. Write `artifact_manifest.json` last so it seals all ten required
    deliverables, including the completion audit, without including itself or
    the scheduler handoff. Re-hash sources, predecessors, tools, pages, trace,
    manifests, lineage, audit, and final artifact manifest; verify target and
    predecessor bytes remain unchanged; derive execution, evidence, coverage,
    and authorization fields from sealed checks.
11. Write exactly one R10 runtime handoff only when the applicable terminal
    gate permits it. Do not start another runtime stage.

## Required Logical Outputs and Completion Validation

Expose these workflow-required logical outputs with stable path, byte size,
SHA-256, schema/version, lineage, request/rank/device coverage, evidence
classes, and audit state:

~~~text
offline_acceptance_manifest=acceptance/offline_acceptance_manifest.json
source_lineage=R10_SOURCE_LINEAGE.json
~~~

The required deliverable set is exactly:

~~~text
acceptance/index.html
acceptance/E2E_PROCESS_TIMELINE.html
acceptance/E2E_PROCESS_TIMELINE_LOSSLESS.html
acceptance/E2E_PROCESS_TIMELINE.full.perfetto.json
acceptance/full_timeline_manifest.json
acceptance/HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html
acceptance/CONCURRENCY_UTILIZATION.html
acceptance/offline_acceptance_manifest.json
R10_SOURCE_LINEAGE.json
R10_COMPLETION_AUDIT.json
~~~

Completion validation must prove:

- every pinned workflow/profile/target/predecessor identity and hash, exact
  fresh same-run lineage, correct path ownership, and no external evidence;
- the complete batch8 workload identity, all eight measured requests, both DP
  ranks, both native physical devices, and the exact rank-to-device mapping;
- exactly twelve hash-valid R09 tables and deterministic use of their complete
  row universes, with R07 as the only observed latency source and R08 replay
  time excluded;
- every required file is nonempty, contained, self-contained where applicable,
  canonical, hash-indexed, lineage-bound, and mutually consistent;
- request/process/kernel event conservation and exact equality of the full
  Perfetto count to request rows plus process rows plus twice kernel rows;
- `complete_timeline=true`, `sampling_performed=false`,
  `formal_r09_r10_regeneration=true`, no Top-N/fixed event budget/lossy
  aggregation, and no duplicate-time interpretation of kernel display copies;
- integer-safe absolute and relative nanoseconds, half-open intervals,
  deterministic ties, complete tracks, overlap lanes, exact jumps, unbounded
  overlap/viewport listings, and at least 100 view-history steps;
- honest utilization gaps and unavailable states, complete high-latency ties
  and denominators, exact hardware joins, evidence-class separation, and no
  speedup or causality claim;
- one offline entry point, no remote dependency or network attempt, and
  successful network-denied browser checks for every required interaction;
- byte-complete timeline/offline/source-lineage/artifact/audit manifests,
  independent audit agreement, target/predecessor immutability, and scheduler-
  handoff exclusion; and
- no model, GPU/DCU, device query, profiler, trace capture, PMC replay,
  predecessor/successor skill, external service, or Adapt execution by R10.

Fail closed on any missing/mismatched prefix item, cross-lineage or external
input, path escape, source drift, one-rank/device promotion, request-count
drift, missing table or source row, replay timestamp on an observed axis,
hidden utilization gap, fabricated availability, dropped unavailable/unknown
state, float-corrupted timestamp, sampled or truncated timeline, wrong event
formula, unpaired kernel display copy, capped overlap result, incomplete
interaction, remote dependency, network attempt, unsupported evidence claim,
partial-output promotion, in-place repair, or independent-audit disagreement.

## Evidence State and Terminal Acceptance Gate

Keep these fields independent:

- `status=complete` means the bounded R10 stage reached a valid terminal
  handoff state; it does not by itself prove offline acceptance sufficiency.
- `execution_status=complete` means the authorized CPU-only render, browser,
  and audit procedure ended.
- `evidence_status` is `complete`, `degraded`, `insufficient`, or `unknown`.
- `coverage_target_met` covers all required files, all twelve R09 tables,
  complete event universes, eight measured requests, both ranks/devices, exact
  mapping, interactions, self-containment, lineage, and independent audit.
- `next_authorization_required` records whether human/scheduler action remains;
  it never authorizes an undeclared successor.

Capability-proven unavailable R08 metrics and honestly unavailable R07
live-utilization windows may coexist with complete R10 evidence when every
state, denominator, gap, reason, and visual distinction is preserved. An
unprobed capability, hidden gap, missing source row, partial rank/device/request
universe, incomplete browser audit, network dependency, or failed content
audit is not complete evidence.

The only terminal branch-acceptance state is:

~~~text
status=complete
execution_status=complete
evidence_status=complete
coverage_target_met=true
next_authorization_required=false
fresh_e2e_evidence.schema_version=1
fresh_e2e_evidence.status=complete
fresh_e2e_evidence.lineage_id=<same nonempty lineage used by R06-R10>
~~~

A valid terminal handoff may describe degraded, insufficient, or unknown
evidence with false or null coverage and
`next_authorization_required=true`; it is not an offline-acceptance claim. A
failed attempt that never reaches a valid terminal stage writes no complete
handoff. The scheduler must never infer sufficiency from `status=complete`
alone.

## Runtime Handoff

After all applicable business outputs and validation pass, write one JSON
handoff only to `runtime_handoff_output`. An acceptance-eligible handoff
contains at least:

~~~text
status=complete
execution_status=complete
evidence_status=complete
coverage_target_met=true
next_authorization_required=false
runtime_branch=workflow01-10-fresh-e2e
runtime_goal=R10
runtime_predecessors=R01,R02,R03,R04,R05,R06,R07,R08,R09
model_execution_performed=false
gpu_dcu_execution_performed=false
device_query_performed=false
profiler_execution_performed=false
trace_collection_performed=false
pmc_collection_performed=false
replay_performed=false
cpu_report_generation_performed=true
offline_browser_acceptance_performed=true
external_network_contacted=false
replay_timing_used_as_latency=false
sampling_performed=false
complete_timeline=true
formal_r09_r10_regeneration=true
~~~

Also record runtime run, formal Goal, attempt/revision, retry authorization,
monitor, and lineage IDs; cumulative-ledger and R01-R09 handoff paths/hashes;
all consumed predecessor business paths/hashes/counts/schemas; target commit/
branch/clean state and source anchors; profile path/hash; selected request and
complete workload/topology; the R07 observed-clock/live-utilization sources;
the R08 capability/PMC/traffic-resource sources; the R09 analysis, all twelve
tables, and source-lineage sources; interpreter/renderer/browser/auditor/config/
invocation hashes; every required page/trace/manifest path, size, hash, count,
schema/version, and coverage; exact event conservation; interaction and
network-denial results; all availability and evidence-class audits; the two
required logical outputs; artifact manifest; completion audit; all explicit
execution booleans; nested `fresh_e2e_evidence`; and the exact terminal
acceptance decision.

The scheduler may close the branch only after independently validating this
handoff, every referenced byte/count/schema, the complete batch8 DP2 identity,
the exact same-run lineage, observed/replay separation, source-lineage closure,
offline browser/content audit, and `evidence_status=complete`,
`coverage_target_met=true`, and `next_authorization_required=false`. This
Adapt-created skill and its A10 Adapt handoff do not prove that R10, report
generation, or any performance workflow ran.
