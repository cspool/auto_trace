---
name: qwen-dcu-workflow05-utilization-concurrency-analysis
description: Deterministically build and audit the project-bound R09 twelve-table full-request utilization, concurrency, launch-gap, dependency, resource-attachment, and opportunity analysis from the same-run R01-R08 batch8 DP2 evidence, without running the model or accelerator stack.
---

# Qwen DCU Workflow 05 Utilization and Concurrency Analysis

## Scope and Stage Boundary

This project skill owns runtime Goal R09 and only R09 on branch
`workflow01-10-fresh-e2e`. It consumes the exact same-run R01-R08 runtime
prefix, normalizes the sole R07 non-replay observed clock and the R08
replay-projected hardware attributes into twelve complete tables, and produces
the independently audited `fresh_e2e_analysis.json` used by R10.

R09 is a CPU-only analysis stage. It must not initialize or run Qwen3.5-27B,
contact a serving endpoint, query or use a GPU/DCU, invoke HIP or KFD, run a
profiler, collect a trace, replay PMC counters, or generate an HTML, Perfetto,
presentation, or report deliverable. It must never recapture or repair R01-R08
evidence. R07 remains the only observed latency clock; R08 contributes only
explicitly labeled replay-projected or derived attributes.

R09 does not plan R06 targets, perform the R07 full-request capture, perform
the R08 targeted replay, render R10 acceptance pages, claim an optimization
speedup, or start a successor. It imports no historical, backup, external-run,
or prior one-card ledger, timing, trace, counter, device map, analysis table,
or visualization. Definitions, taxonomy, marker vocabulary, schemas, and
reconstruction methods under
`/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile` may be consulted as
implementation guidance, but its timings, traces, mappings, runtime handoffs,
and measurement evidence are inadmissible.

The outer serial scheduler creates the formal R09 Goal. This skill must never
call `create_goal`, create a nested Goal, invoke another project skill, run an
Adapt Goal, edit scheduler state, or start R10. It was created by migration-only
Adapt Goal A09. Creating or statically validating this file is not R09
execution and is not performance-workflow evidence.

## Migration Provenance

This is a `synthesize_uncovered` project skill whose only pinned workflow
source is:

~~~text
workflow_path=/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/workflows/05_workflow04_guided_selective_process_trace_and_resource_gap_analysis.md
workflow_sha256=d4ed4a1a265c79b0579c7f695f9c66585ef9588f14ee3aea072707097eb77d39
adapt_goal=A09
reference_skill_inputs=none
workflow_execution_performed=false
project_skill_execution_performed=false
~~~

No reference skill was selected or invoked. This skill directly packages the
uncovered R09 semantics: exact same-run prefix admission, complete batch8 DP2
identity preservation, lossless observed-clock normalization, the twelve-table
contract, gap-aware utilization, deterministic concurrency and launch-gap
calculation, dependency and traffic/resource joins, opportunity classification
without speedup claims, source-lineage sealing, independent audit, and the R10
advance gate.

## Immutable Project Binding

Before creating any promotable R09 business output, fail closed unless these
bindings are exact:

~~~text
project_root=/public/home/tangyu408/Qwen_DCU_Worker_0
trace_target_root=/public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408-gqa-page784-k5120-batch8
trace_target_git_commit=2b4b2119ae3cc2c4c626dc5690ef9593c1477f66
trace_target_git_branch=repro-gqa-page784-k5120-batch8-final
trace_profile_path=/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/configs/trace_targets/batch8_dual_dcu_dp2.json
trace_profile_sha256=3b4c952063f48ae662b48b5ce9d8fd76e0ac4d74e170bdb1839ae8b1aaa23cce
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

The target checkout is read-only for R09. Validate its commit, branch, clean
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
`CUDA_VISIBLE_DEVICES` compatibility names. R09 evidence vocabulary is native
HIPTX/ROCTX, HIP runtime, HIPOPS, and HIPProf. Never relabel native rows as
NVIDIA profiler evidence. The target documents and any earlier validation
results prove only source and topology bindings; their timings and reported
measurements cannot populate R09 tables.

All R09 analyzers, schemas, resolved contracts, scratch data, normalized
tables, manifests, and audits live under the scheduler-assigned R09 artifact
root. Only the scheduler handoff is written to its separately assigned handoff
path. No R09 command may write to the target, a predecessor artifact root, a
predecessor handoff, or the cumulative ledger.

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
~~~

DP rank 0 maps to native physical DCU 0 and DP rank 1 maps to native physical
DCU 1. Although R09 is CPU-only, every input gate, table schema, join,
availability state, manifest, audit, and handoff must retain both DP ranks,
both native device identities, and that exact mapping. Never pool, renumber,
merge, infer, or drop a worker. A source or table covering only one required
rank/device cannot be promoted as batch8 DP2 analysis.

The fixed request is row zero of the dataset and is carried through the
validated same-run predecessor chain:

~~~text
dataset_file_sha256=633ba4c8b4f500d2ab28094de42698c5494e5232f40eafcd119c0a314b44b936
dataset_row_0_bytes_sha256=06c7c1cc0e97951303631942dea7a2759fe7b693a79e06d495a164a2354146fd
~~~

R09 must not search the dataset, shuffle rows, synthesize or retokenize a
prompt, send a request, or substitute a local workload. It analyzes the eight
measured requests already admitted by R07. The two warmup requests remain
accounted for in source metadata but are not silently mixed into measured
request rows. Serial R01-R10 ordering constrains stage overlap only; it never
changes this DP2 contract.

## Serial Runtime Contract

~~~text
runtime_branch=workflow01-10-fresh-e2e
runtime_goal=R09
runtime_predecessors=R01,R02,R03,R04,R05,R06,R07,R08
required_handoff_fields=status,execution_status,evidence_status,coverage_target_met,next_authorization_required,runtime_branch,runtime_goal,runtime_run_id,lineage_id,trace_profile_sha256,cumulative_runtime_ledger_sha256,r01_handoff_sha256,r02_handoff_sha256,r03_handoff_sha256,r04_handoff_sha256,r05_handoff_sha256,r06_handoff_sha256,r07_handoff_sha256,r08_handoff_sha256,request_timeline_sha256,process_timeline_sha256,kernel_timeline_sha256,live_utilization_aligned_sha256,process_live_utilization_sha256,kernel_concurrency_sha256,queue_concurrency_sha256,launch_gaps_sha256,high_latency_processes_sha256,dependency_state_sha256,traffic_resource_attachment_sha256,opportunity_candidates_sha256,full_request_analysis_sha256,source_lineage_sha256,artifact_manifest_sha256,completion_audit_sha256
runtime_artifact_root=<scheduler-assigned>
runtime_handoff_output=<scheduler-assigned>
advance_only_after=complete
~~~

Before any runtime work, load and SHA-256 validate the scheduler-assigned R01,
R02, R03, R04, R05, R06, R07, and R08 handoffs plus the cumulative immutable
runtime ledger. Consume exactly the ordered `R01,R02,R03,R04,R05,R06,R07,R08`
prefix from the same scheduler run and branch. Refuse a missing, failed,
partial, duplicated, shorter, longer, out-of-order, cross-run, cross-branch,
external, or hash-mismatched predecessor.

Require each predecessor to state `status=complete`,
`execution_status=complete`, `evidence_status=complete`,
`coverage_target_met=true`, and `next_authorization_required=false`. Require
one identical nonempty lineage ID, the pinned profile hash, target commit,
selected request hashes, full rank/device mapping, and fresh evidence status
through R08. In particular, R08 must independently satisfy its R09 advance
gate; a terminal but degraded R08 handoff is not an admission token.

Validate every transitive business-artifact hash against the direct handoff
that owns it. Preserve the cumulative-ledger hash, all eight direct handoff
hashes, predecessor artifact-manifest hashes, and every consumed business hash
in the resolved contract, R09 source-lineage manifest, artifact manifest,
completion audit, and handoff. An earlier ledger hash represents an immutable
prefix view and must not be compared as though it were the later ledger bytes.

Write business outputs only under `runtime_artifact_root`. Write exactly one
scheduler handoff only to `runtime_handoff_output`, outside the business
artifact manifest, and only after all stage checks pass. Never edit a
predecessor artifact, handoff, ledger, project skill, or attempt. The scheduler
must hash-validate the R09 handoff and the R10 advance gate before R10 starts.

## Fresh-lineage Admission and Producer Boundaries

The first R09 phase is a read-only CPU admission gate. It must prove:

1. The branch is exactly `workflow01-10-fresh-e2e`; the ledger belongs to the
   current runtime run; no external upstream ledger, Adapt output, ambient
   file, backup, or historical evidence was accepted.
2. The ledger contains exactly R01-R08 in order, and all direct/transitive
   handoff, manifest, and business-output paths and hashes validate under the
   owning stage's root.
3. Runtime run ID, lineage ID, trace-profile hash, target identity, selected
   input hashes, request semantics, ranks, native devices, and mapping are
   identical across the prefix.
4. R01 owns observed request/layer denominators; R02 owns FX process/fragment
   identities and the canonical range inventory; R03 owns non-replay launch
   order and representative timing context; R04 owns diagnostic hardware
   attributes; R05 owns full-layer process attribution; R06 owns the complete
   target universe and bounded family plan; R07 owns the only full-request
   observed request/process/runtime/kernel clock, strict-owned kernels,
   lossless gap-aware live utilization, and dependency adapter; R08 owns
   capability states, attributable targeted PMC, and the FX-visible
   traffic/resource model.
5. R07 exposes and hash-validates `full_request_profile_metadata`,
   `process_trace_summary`, `fresh_run_dependency_adapter`,
   `live_utilization_summary`, and `source_lineage`. Its timing collection is
   non-replay and covers all measured requests, target ranges, ranks, and
   native devices.
6. R08 exposes and hash-validates `device_capabilities`,
   `targeted_pmc_manifest`, `traffic_resource_model`, and `source_lineage`.
   Its replay time is explicitly excluded from observed latency, and every
   unavailable counter remains represented rather than zero-filled.
7. R06 target membership, R07 observed ownership, and R08 logical attachment
   identities form a lossless, auditable join. Missing or duplicate join keys
   are explicit terminal states, never silently dropped or guessed.

Resolve project-relative paths against the scheduler project root and
artifact-relative paths against the predecessor root declared by the owning
handoff. Never resolve a predecessor path against the current R09 artifact
root. Exercise the production resolver with a project-root-relative positive
case, an absolute-path positive case, and a traversal/containment negative
case before accepting inputs.

Write the admission result to
`contract/r01_r02_r03_r04_r05_r06_r07_r08_predecessor_validation.json`.
A failed admission may write only attempt-local diagnostics and cannot create
normalized tables, a complete handoff, or R10 authorization.

## Evidence Classes and the Unique Observed Clock

Every normalized row and derived field must carry one of these evidence
classes, or an equally strict field-level mapping:

- `observed_r07`: request, process, runtime, queue, and strict-owned kernel
  intervals from the sole non-replay R07 clock;
- `observed_r07_live_utilization`: actual R07 live samples, gaps, anchors,
  uncertainty, and eligible process aggregates;
- `replay_projected`: R08 PMC, device, traffic, and resource attributes
  attached to R07 identities without importing replay timestamps;
- `derived_static`: deterministic identity, shape, taxonomy, dependency, or
  schema values that use no observed or replay measurement;
- `derived_from_observed_r07`: concurrency, busy unions, launch gaps,
  duration classifications, and dependency timing derived solely from R07;
- `derived_from_observed_and_replay_projected`: an explicitly labeled join or
  rule that combines R07 observed fields with R08 attributes; and
- `unavailable` or `unknown`: a preserved absence with reason and provenance,
  never a numeric zero or inferred value.

All timing computations use the exact R07 clock domain and integer nanoseconds.
Intervals are half-open `[begin_ns,end_ns)`. Absolute nanoseconds are retained
as decimal integer text or an integer-safe representation, and request-relative
offsets are exact integer differences. Never convert approximately
`1.7e18`-scale timestamps through binary floating point. At equal timestamps,
process ends before starts when constructing concurrency segments so touching
intervals do not create false overlap.

R08 replay begin/end, replay duration, counter-pass order, and capture wall
time are diagnostics only. They must not appear on a request/process/kernel
latency axis, drive concurrency or gap calculations, rank a high-latency row,
or be added to R07 time. R04 hardware rows cannot replace current R08
capability/attachment states. Unknown dependency or hardware evidence stays
unknown; an unavailable metric stays unavailable.

## Artifact-local Tools, Commands, and Output Layout

Resolve one CPU-only interpreter through the scheduler environment and record
its absolute path, executable bytes, version, and SHA-256. R09 tools are
generated or copied only below the current artifact root, reviewed before use,
and frozen before they read business inputs:

~~~text
tools/build_r09_analysis.py
tools/audit_r09_analysis.py
contract/resolved_r09_contract.json
contract/r01_r02_r03_r04_r05_r06_r07_r08_predecessor_validation.json
analysis/tables/request_timeline.csv
analysis/tables/process_timeline.csv
analysis/tables/kernel_timeline.csv
analysis/tables/live_utilization_aligned.csv
analysis/tables/process_live_utilization.csv
analysis/tables/kernel_concurrency.csv
analysis/tables/queue_concurrency.csv
analysis/tables/launch_gaps.csv
analysis/tables/high_latency_processes.csv
analysis/tables/dependency_state.csv
analysis/tables/traffic_resource_attachment.csv
analysis/tables/opportunity_candidates.csv
analysis/fresh_e2e_analysis.json
lineage/R09_SOURCE_LINEAGE.json
validation/R09_COMPLETION_AUDIT.json
artifact_manifest.json
~~~

The scheduler-resolved CPU commands have this semantic shape:

~~~text
<r09_python> <runtime_artifact_root>/tools/build_r09_analysis.py --resolved-contract <runtime_artifact_root>/contract/resolved_r09_contract.json --artifact-root <runtime_artifact_root>
<r09_python> <runtime_artifact_root>/tools/audit_r09_analysis.py --resolved-contract <runtime_artifact_root>/contract/resolved_r09_contract.json --analysis-manifest <runtime_artifact_root>/analysis/fresh_e2e_analysis.json --artifact-root <runtime_artifact_root>
~~~

Do not substitute a target launcher, model script, profiler, trace converter,
PMC normalizer, report generator, or R10 renderer for these CPU-only analysis
commands. Record exact argv, cwd, environment allowlist, start/end clocks,
exit status, stdout/stderr paths, interpreter/tool hashes, input-manifest
hashes, and output inventory. The builder and auditor are separate invocations;
the auditor must not trust mutable in-memory state from the builder.

Every table uses UTF-8, LF line endings, an explicit ordered header, canonical
null encoding, locale-independent decimal rendering, and a schema-pinned
stable sort. CSV quoting and newline rules are fixed in the analysis manifest.
No glob-discovered file, temporary partial, diagnostic, scheduler handoff, or
repair output enters the business artifact manifest.

## Common Row Identity and Normalization Rules

Each table schema must carry the applicable subset of these explicit keys:

~~~text
schema_version
runtime_run_id
lineage_id
trace_profile_sha256
request_id
measured_request_ordinal
rank
physical_device_id
source_record_kind
source_path
source_sha256
source_row_id
evidence_class
availability_state
availability_reason
~~~

Use stable IDs inherited from the owning predecessor. Never synthesize an ID
from row position when a source identity exists. Every join records left and
right source row IDs and hashes, join cardinality, matched/unmatched state,
and the rule version. A many-to-many join is rejected unless the schema
explicitly declares the physical-sharing relationship and the independent
auditor proves its multiplicity conservation.

Normalize complete source universes, not just rows that have favorable timing,
utilization, dependencies, counters, or kernels. Preserve explicit no-kernel,
host-only, unknown, unavailable, unmatched, nested, and shared-physical-capture
states. Parent and fragment rows remain distinct; roll-up happens only by a
declared aggregation key and cannot double count a deepest-owned runtime or
kernel. No Top-N truncation, random or uniform sampling, fixed event budget,
downsampling, resampling, interpolation, imputation, smearing, zero fill, or
irreversible aggregation is permitted.

The workflow records earlier batch8 counts such as the target-universe and
strict-owned-kernel diagnostics. Those historical numbers are useful only as
non-evidentiary regression warnings. Current R09 row membership and counts
must come from the hash-validated same-run R06-R08 artifacts; never copy an
earlier count or row into a current table.

## The Twelve Normalized Tables

`fresh_e2e_analysis.json` must index exactly these twelve logical tables in
this order. Additional diagnostics cannot masquerade as a thirteenth analysis
table.

### 1. `request_timeline`

Emit one normalized row for every measured request admitted by R07, preserving
request identity, measured ordinal, success state, rank/device routing,
observed begin/end/duration, phase boundaries when present, and source hashes.
The table must cover exactly eight successful measured requests for the
advance gate. Warmups remain separately accounted in profile metadata and are
not relabeled as measured rows. Duplicate, missing, cross-request, or replay-
sourced request intervals fail closed.

### 2. `process_timeline`

Emit every R06 target process or fragment observed by R07, including parent
identity, fragment identity, layer, input/phase/config, nesting depth, exact
begin/end/duration, deepest-owner state, no-kernel state, rank/device, and
source membership. Preserve rows lacking a direct kernel. Parent/fragment
nesting must be a strict chain where ownership requires it; non-ancestor
overlap remains ambiguity. Never rank, truncate, or remove short processes.

### 3. `kernel_timeline`

Emit every unique R07 strict-owned HIPOPS kernel with its exact event and
kernel literal, family, owner process/fragment, runtime-launch and correlation
identity, queue/stream, rank/native-device identity, and observed begin/end.
Shared presentation tracks do not duplicate the logical kernel row. R08
attributes may be referenced by exact join keys, but replay timestamps and
unattributed counter rows never replace the observed interval.

### 4. `live_utilization_aligned`

Losslessly normalize all R07 utilization samples, gap intervals, alignment
anchors, sequence numbers, collector-call latencies, clock-domain transforms,
and uncertainty values for both devices. Use a `record_kind` or equivalent
schema to distinguish sample, gap, and anchor rows without deleting any type.
Preserve original values and source row IDs. Do not interpolate, resample,
smooth, smear, or hide a slow call or gap.

### 5. `process_live_utilization`

Emit one row for every process/fragment row, not only available rows. A numeric
live-utilization value is allowed only when at least three timing-eligible true
samples fall inside the exact process interval, the interval intersects no
unobserved gap, and alignment uncertainty does not violate the R07 1 ms gate.
Use the R07-declared aggregation semantics and independently recompute sample
membership. Otherwise set the numeric field null and retain the exact reason,
including `unavailable_intrinsic_short_window`,
`unavailable_sampling_gap`, or `unavailable_alignment_error`. Never interpret
unavailable as low utilization.

### 6. `kernel_concurrency`

Construct an exact sweep-line segmentation from unique R07 half-open kernel
intervals. Each segment records begin/end, active-kernel count, an order-
independent hash of active IDs, rank, native device, request scope, and clock
provenance. Ends sort before starts at a shared timestamp. Produce per-device
and per-rank segments; produce a cross-device aggregate only when the same-run
clock alignment is proven, otherwise represent it as unavailable. The union
duration and active-membership audit must conserve the kernel timeline.

### 7. `queue_concurrency`

Using the same observed sweep-line, emit queue/stream activity segments with
active queue count, active kernel count, queue identities, rank, native device,
request, and membership hashes. A queue with multiple overlapping kernels is
not multiplied into multiple active queues. Queue concurrency is derived from
R07 observed intervals only and must reconcile with kernel concurrency and
the strict-owned queue mapping.

### 8. `launch_gaps`

Order strictly correlated runtime launch/kernel pairs within each exact
request, rank, native device, queue/stream, and launch sequence. Record adjacent
IDs, previous end, next begin, `gap_ns=max(0,next_begin-prev_end)`, and a
separate overlap value when intervals overlap. Missing correlation, clock, or
sequence evidence produces an explicit unknown/unavailable row, not a guessed
gap. Replay order, capture-wall time, name proximity, and row proximity are
never launch-gap evidence.

### 9. `high_latency_processes`

Classify from R07 observed process duration only. Compute the exact nearest-
rank p95 threshold over the complete eligible process universe and, separately,
over each declared comparable phase/family group. Include every row meeting a
global or peer-group threshold, including all ties; never use a Top-N cutoff.
Record denominators, thresholds, percentile rule/version, group keys, flags,
duration, rank/device, and source identity. If a group lacks a valid
denominator, preserve its classification as unknown. R08 replay durations
cannot influence this table.

### 10. `dependency_state`

Normalize every node and edge in the R07 fresh-run dependency adapter using a
stable `record_kind`, exact endpoint IDs, dependency type, direction, state,
source hash, observed interval references, and availability. Preserve unknown,
unresolved, cycle, host-only, no-kernel, and missing-counter states. Derived
waiting/ready/overlap state is allowed only when endpoint identities and the
R07 clock prove it. Missing dependency evidence is not reconstructed from
kernel names or temporal proximity.

### 11. `traffic_resource_attachment`

Join the R08 FX-visible traffic/resource model to exact R07 process, fragment,
kernel-family, rank, and native-device identities. Prefer a lossless long-form
metric schema containing metric name, value, unit, formula, assumptions,
availability, capability source, logical source rows, physical capture IDs,
aggregation rule, evidence class, and both-side hashes. Preserve static,
replay-projected, combined-derived, unavailable, unmatched, and shared-raw
states. Never call theoretical bytes measured traffic, infer a counter from
duration, replace unknown with zero, or multiply a shared physical capture
across logical owners.

### 12. `opportunity_candidates`

Evaluate every eligible process/family against versioned deterministic rules
for observed duration, concurrency/serialization, launch gaps, dependency
state, honest live-utilization availability, and R08 traffic/resource evidence.
Emit candidate, non-candidate, blocked-by-unavailable, and unknown states with
all rule inputs, thresholds, provenance, rank/device, supporting row IDs, and
contradicting evidence. Do not truncate to Top-N, turn a missing value into a
score, or let one unsupported metric dominate. A candidate is an investigation
hypothesis, not measured speedup, predicted speedup, root-cause proof, or
authorization to change the target.

## `fresh_e2e_analysis.json` Contract

Write `analysis/fresh_e2e_analysis.json` only after all twelve candidate table
files close successfully. It is the logical `full_request_analysis` output and
must contain:

- schema and analysis-algorithm versions, runtime run and lineage IDs, exact
  profile and target identities, selected-request hashes, complete workload
  and topology, and the R01-R08 handoff/ledger hashes;
- exactly twelve ordered table entries, each with logical name, contained
  path, byte size, SHA-256, row count, ordered schema, schema SHA-256, stable
  sort key, null/encoding rules, lineage ID, evidence classes, and measured-
  request/rank/native-device coverage;
- source manifests and row-universe denominators for every table, join and
  multiplicity reports, concurrency/gap algorithm versions, percentile rule,
  dependency rule, traffic/resource rule, and opportunity rule;
- explicit observed-clock identity and an explicit statement that R08 replay
  time was neither collected as R09 timing nor used as latency;
- utilization sample/gap/anchor/availability counts and reasons, with no
  hidden rows or imputation;
- unknown/unavailable counts by reason and evidence class;
- `complete_timeline=true`, `sampling_performed=false`, and exact no-Top-N/no-
  event-budget declarations for downstream R10; and
- builder, interpreter, invocation, environment, source-input, artifact-
  manifest, independent-audit, and source-lineage hashes.

The manifest must not point outside `runtime_artifact_root`, except to sealed
read-only predecessor inputs explicitly listed by path and hash. It must not
include the scheduler handoff. A path, row count, schema, lineage, or hash
mismatch invalidates the whole analysis; do not promote eleven tables as a
complete result.

## Source Lineage and Evidence Boundary

`lineage/R09_SOURCE_LINEAGE.json` must seal:

- runtime branch/run/formal Goal/lineage IDs and the exact R01-R08 ordered
  ledger prefix;
- profile path/hash/content identity, target commit/branch/clean state, source
  anchor paths/hashes, model/runtime/accelerator identity, selected request,
  workload, topology, ranks, native devices, and mapping;
- every consumed predecessor handoff, artifact manifest, business artifact,
  schema, and row-universe hash with its owning stage and evidence class;
- exact builder/auditor/interpreter bytes, argv, cwd, environment allowlist,
  attempt/revision history, and output hashes;
- the R07 observed clock and live-utilization provenance, the R08 replay-
  projected attachment provenance, and all field-level derived rules; and
- declarations that no external runtime evidence, prior one-card evidence,
  model execution, accelerator work, profiler, trace, PMC replay, report,
  visualization, target mutation, predecessor mutation, or successor execution
  occurred in R09.

Any semantic change to selected input, workload, clock, identity, ownership,
join, availability, or derivation rules stops the lineage. A tool-only repair
may remain in the lineage only when all inputs and semantics are unchanged and
the immutable revision history plus new tool/output hashes are recorded.

## Deterministic Independent Audit

The frozen auditor runs after the builder exits and independently reads sealed
inputs and on-disk outputs. It must at minimum recompute or verify:

1. exact prefix, source, profile, target, request, lineage, path-containment,
   schema, and all input/output hashes;
2. exactly eight measured request rows and full rank 0/rank 1 plus native
   device 0/device 1 representation wherever the source universe applies;
3. complete R06 target to R07 process membership, strict deepest ownership,
   explicit no-kernel rows, unique kernel identity, queue mapping, and no
   parent/fragment or duplicate-track double counting;
4. lossless R07 sample/gap/anchor counts, exact process sample membership,
   availability gates/reasons, and absence of interpolation or zero filling;
5. integer-safe half-open interval semantics, kernel and queue sweep-line
   membership, union-duration conservation, launch order, gap/overlap values,
   and the absolute exclusion of replay time;
6. high-latency denominators, nearest-rank p95 thresholds, group membership,
   ties, and the absence of Top-N truncation;
7. dependency node/edge conservation and the explicit preservation of
   unresolved or unavailable states;
8. exact R08 traffic/resource joins, metric units/formulas/availability,
   logical-to-physical multiplicity, shared-capture conservation, and evidence
   labels;
9. opportunity-rule inputs and classifications, including blocked/unknown
   states and the absence of speedup or root-cause claims;
10. the exact twelve-entry analysis manifest, every path/hash/size/row count/
    schema/sort key, artifact manifest completeness, source-lineage closure,
    and exclusion of the scheduler handoff; and
11. no model, GPU/DCU, device query, profiler, trace, PMC, report,
    visualization, predecessor, successor, or Adapt execution by R09.

The auditor writes only `validation/R09_COMPLETION_AUDIT.json` and its own
attempt-local stdout/stderr. Its result records every check, denominator,
observed value, pass/fail state, and input hash. A builder self-declaration is
not an independent audit. Any disagreement is fail-closed.

## Failure, Repair, and Formal Turn Liveness

Every build or audit attempt uses a new empty immutable attempt directory and
records inputs, tools, commands, logs, partial inventory, hashes, and failure
reason. Never overwrite a failed or partial table, alias it to a canonical
path, append incompatible rows, or promote it into the twelve-table manifest.
Repair a CPU-only builder/auditor defect in a new `analysis-repair-NNN` root,
using the same sealed R01-R08 inputs and recording before/after tool hashes and
the semantic-equivalence justification. Only a fully audited repair may be
promoted to the canonical output paths.

Do not rerun A01-A11 or R01-R08, recapture a request, repeat a device pass, or
modify predecessor evidence to repair R09. If predecessor integrity,
lineage, coverage, or sufficiency cannot be proven, stop R09 and request the
outer scheduler's authorization; do not guess, fetch external evidence, or
degrade to a one-card analysis. A failed stage writes no advance-eligible
handoff.

Large CPU-only builders or auditors can be temporarily quiet. Monitor at
five-minute intervals. During a known large-file generation turn, require two
consecutive complete five-minute observations with no new content item, token,
subprocess progress, artifact size/mtime change, or reasoning item before any
interruption. Then interrupt only the cmdline-verified scheduler-owned PID,
never a process group or unrelated process. Preserve the partial attempt and
restart in a new immutable root.

If a formal R09 Goal becomes blocked, do not use it to mutate the completed
prefix or to start R10. Resume from the scheduler's first incomplete R09 stage
with the exact same run and lineage only after verifying scoped processes are
gone and recording the retry authorization. Never fabricate a handoff or
infer success from an existing partial manifest.

## Deterministic Runtime Procedure

Execute R09 in this order:

1. Resolve scheduler-assigned artifact/handoff paths, runtime/formal Goal and
   lineage IDs, retry authorization, and the current attempt root; prove
   business-output and scheduler-handoff separation.
2. Hash-validate the trace profile, read-only target binding, exact R01-R08
   ledger prefix, every direct/transitive predecessor output, the sole R07
   observed clock, R08 evidence boundary, full workload, and complete DP2
   identity. Seal the resolved contract and admission report.
3. Create or copy only artifact-local CPU analyzers, freeze interpreter/tool
   bytes, schemas, algorithms, thresholds, argv, cwd, and environment. No
   target import or device query is permitted.
4. Normalize request, process, kernel, utilization, and dependency source
   universes losslessly; validate their identities and conservation before
   computing derived tables.
5. Compute exact kernel/queue sweep-line concurrency, launch gaps/overlaps,
   process live-utilization availability, and high-latency classifications on
   the R07 clock only.
6. Attach R08 traffic/resource states by exact identity and multiplicity, then
   evaluate versioned opportunity rules while preserving unknown/unavailable
   inputs and forbidding speedup claims.
7. Canonically serialize all twelve tables, seal each path/size/hash/row count/
   schema/sort key in `fresh_e2e_analysis.json`, and write the R09 source
   lineage and business artifact manifest.
8. End the builder invocation. Run the independent auditor as a separate
   invocation and write `R09_COMPLETION_AUDIT.json` only after its checks
   finish.
9. Re-hash sources, predecessors, tools, tables, manifests, and audits; verify
   the target and all predecessor bytes remain unchanged; derive execution,
   evidence, coverage, and authorization fields from sealed checks.
10. Write exactly one R09 runtime handoff only when the applicable terminal
    gate permits it. Do not generate or launch R10 outputs.

## Required Logical Outputs and Completion Validation

Expose these workflow-required logical outputs with stable path, size,
SHA-256, schema, lineage, request/rank/device coverage, and evidence class:

~~~text
full_request_analysis=analysis/fresh_e2e_analysis.json
source_lineage=lineage/R09_SOURCE_LINEAGE.json
~~~

Completion validation must prove:

- every pinned workflow/profile/target/predecessor identity and hash, exact
  fresh same-run lineage, correct path ownership, and no external evidence;
- the complete batch8 workload identity and all eight measured requests, both
  ranks, both native physical devices, and exact rank-to-device mapping;
- exactly the twelve required nonempty logical tables with canonical schema,
  contained path, byte size, hash, row count, stable order, and one lineage;
- complete request/process/kernel/sample/gap/anchor/dependency and R08
  attachment accounting, including no-kernel, unmatched, shared, unknown, and
  unavailable rows;
- integer-safe R07-only latency, deterministic concurrency/gap/high-latency
  results, and no R08 replay time on an observed axis;
- honest live-utilization availability with no hidden gaps, interpolation,
  imputation, zero fill, or unavailable-as-low-utilization claim;
- formulas, units, capability states, exact attachment multiplicity, and
  evidence-class labels for every hardware/resource field;
- versioned opportunity rules with no Top-N/event budget/sampling and no
  claimed or predicted speedup;
- byte-complete analysis/source-lineage/artifact/audit manifests, independent
  audit agreement, target/predecessor immutability, and scheduler-handoff
  exclusion; and
- no model, GPU/DCU, device query, profiler, trace, PMC, report,
  visualization, predecessor/successor skill, or Adapt execution.

Fail closed on any missing/mismatched prefix item, cross-lineage or external
input, path escape, source drift, single-rank/device promotion, request-count
drift, duplicate or missing identity, parent/fragment double count, hidden
no-kernel row, floating-point timestamp loss, replay timing on an observed
axis, dropped utilization row or gap, fabricated availability, ambiguous
dependency, guessed counter, missing formula/unit, shared-capture
multiplication, Top-N/sample/event-budget truncation, opportunity-as-speedup
claim, partial output promotion, in-place repair, or independent-audit
disagreement.

## Evidence State and R10 Advance Gate

Keep these fields independent:

- `status=complete` means the bounded R09 stage reached a valid terminal
  handoff state; it does not by itself prove table or evidence sufficiency.
- `execution_status=complete` means the authorized CPU-only procedure ended.
- `evidence_status` is `complete`, `degraded`, `insufficient`, or `unknown`.
- `coverage_target_met` covers all twelve tables, complete source universes,
  eight measured requests, both ranks/devices, exact mapping, lineage, joins,
  and independent audit.
- `next_authorization_required` controls whether R10 may start.

Capability-proven unavailable R08 metrics and honestly unavailable R07
live-utilization windows may coexist with complete R09 evidence when every
state and denominator is preserved and no required table or identity is
missing. An unprobed capability, hidden gap, missing source row, unattributed
required row, partial rank/device/request universe, or failed audit is not
complete evidence.

The only R10-advance-eligible state is:

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
`next_authorization_required=true`; it is not an R10 advance token. A failed
attempt that never reaches a valid terminal stage writes no complete handoff.
The scheduler must never infer sufficiency from `status=complete` alone.

## Runtime Handoff

After all applicable business outputs and validation pass, write one JSON
handoff only to `runtime_handoff_output`. An advance-eligible handoff contains
at least:

~~~text
status=complete
execution_status=complete
evidence_status=complete
coverage_target_met=true
next_authorization_required=false
runtime_branch=workflow01-10-fresh-e2e
runtime_goal=R09
runtime_predecessors=R01,R02,R03,R04,R05,R06,R07,R08
model_execution_performed=false
gpu_dcu_execution_performed=false
device_query_performed=false
profiler_execution_performed=false
trace_collection_performed=false
pmc_collection_performed=false
replay_performed=false
cpu_analysis_performed=true
twelve_table_analysis_performed=true
report_generation_performed=false
visualization_performed=false
replay_timing_used_as_latency=false
~~~

Also record runtime run, formal Goal, attempt/revision, retry authorization,
monitor, and lineage IDs; cumulative-ledger and R01-R08 handoff paths/hashes;
all consumed predecessor business paths/hashes/counts/schemas; target commit/
branch/clean state and source anchors; profile path/hash; selected request and
complete workload/topology; R07 observed-clock/live-utilization/dependency
sources; R08 capability/PMC/traffic-resource sources; interpreter/tool/config/
invocation hashes; every table path/size/hash/row count/schema/sort key; all
coverage, availability, join, concurrency, gap, percentile, dependency,
attachment, and opportunity audits; the two required logical outputs;
artifact manifest; completion audit; all explicit execution booleans; nested
`fresh_e2e_evidence`; and the exact R10 advance decision.

The scheduler may advance only after independently validating this handoff,
every referenced byte/count/schema, all twelve tables, complete batch8 DP2
identity, exact same-run lineage, observed/replay separation, source-lineage
closure, independent audit, and `evidence_status=complete`,
`coverage_target_met=true`, and `next_authorization_required=false`. This
Adapt-created skill and its A09 Adapt handoff do not prove that R09 or any
performance workflow ran.
