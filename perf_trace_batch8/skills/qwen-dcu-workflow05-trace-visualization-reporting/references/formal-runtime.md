# Formal fresh R10 execution

Read this reference only for a scheduler-owned fresh stage. Retained
restoration/presentation follows the skill entrypoint and never writes a fresh
handoff. The shared Process/resource contract defines analytical views;
full-archive conservation rules here do not force every row onto those views.

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
renumber, merge, infer, or drop a worker. The complete source archive must retain every required rank/device. A
filtered resource window may omit ranks with no eligible data when its scope
and omission are disclosed; it does not replace source coverage validation.

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

In the full evidence viewer, an overview may show reversible density coverage while zoomed out, but the
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

## Self-contained Offline Boundary

All pages must operate from local hash-verified bytes with no CDN, remote script,
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
