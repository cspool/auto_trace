---
name: qwen-dcu-process-gpu-hardware-trace
description: >-
  Run the project-bound R04 hardware-attribute stage for the pinned Qwen3.5-27B
  batch8 DP2 workload, preserving R03 non-replay process timing while collecting
  auditable rocprofv2 PMC replay attributes on both physical DCUs.
---

# Qwen DCU Process GPU Hardware Trace

## Scope and Stage Boundary

This skill owns runtime Goal R04 only. It consumes the fresh same-run R01,
R02, and R03 handoffs and projects DCU hardware attributes onto the R03
Representative Layer Process GPU Execution Order. R03 remains the sole owner
of direct process latency, exact HIPTX launch ownership, native kernel timing,
and process/kernel order. R04 owns counter capability proof, bounded PMC
replay, dispatch-to-process attribution, hardware-attribute normalization,
coverage audit, and the hardware report.

Keep the two evidence clocks separate:

- retain R03 non-replay timestamps, durations, and order as immutable input;
- treat every rocprofv2 counter pass as replayed diagnostic evidence;
- never use replay elapsed time, replay dispatch order, replay duration, or
  replay throughput as process latency or execution-order evidence;
- never regenerate, repair, or weaken R02/R03 timing attribution in R04;
- if replay changes kernel choices, pruning behavior, or the normalized R03
  operation subsequence, stop and require a fresh R02/R03 lineage before any
  latency claim.

This skill was synthesized from the Workflow 03 text because A04 declares no
reference-skill input. Its presence is a runtime capability, not proof that a
runtime workflow, model, profiler, PMC pass, or report has run.

## Immutable Project Binding

The only permitted source checkout is:

~~~text
trace_target_root=/public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408-gqa-page784-k5120-batch8
trace_target_git_commit=2b4b2119ae3cc2c4c626dc5690ef9593c1477f66
trace_target_git_branch=repro-gqa-page784-k5120-batch8-final
model_identity=Qwen3.5-27B
runtime_identity=vLLM BF16 on ROCm/DCU/HIP gfx936
~~~

Before runtime work, prove that the checkout resolves to the exact commit and
has a clean worktree. Treat it as read-only. Do not install into it, patch it,
write profiler outputs into it, alter caches under it, or use a different
checkout with similar contents.

The binding is evidenced by these source files and must be re-hashed into the
R04 resolved contract:

| Role | Target-relative path | Adapt-inspected SHA-256 |
| --- | --- | --- |
| Qwen3.5 model and linear-attention path | vllm/model_executor/models/qwen3_5.py | f3c0479dbc37a8794c4d6b1c4c01906ae341b3276ed43e588c17d92b1ddb94d6 |
| shared decoder and full-attention path | vllm/model_executor/models/qwen3_next.py | 5a14b14a40fcf6382f9a20be4ca0f850b2b19b2840a3c57488821f0952d96053 |
| model execution boundary | vllm/v1/worker/gpu_model_runner.py | d63424d3cbe81bfaa2c0967a5c81b8c980c2d76bc7eb3b2f8fe2a079af825bce |
| compatibility marker hooks | vllm/utils/nvtx_pytorch_hooks.py | e9711444f33242ce1864d6a32d051bbf0ba0b37b5f17965de6e5dbba0c0c75ff |
| compiled-module marker wrapper | vllm/compilation/wrapper.py | b4dca93456e945ce8231e9a954792c8f687d5d48b427ed38bfb96011015d4090 |
| DP2 service launcher | scripts/serve_cscc_dp2.sh | 233bb2ce6fee3654bc870e37e65b7ecf4de6874cb6c7fd1a6bd5687a40783699 |
| multi-request launcher | scripts/bench_cscc_multi_request.sh | 9b5e02116911729e901077866389e448c0e4a055e8bb901ed160dcdc7664a595 |
| fixed gfx936 environment | scripts/cscc_gfx936_env.sh | 58d483450c23e9c4fa87fb981b5e63cf4babf5e8d230fe93e400563596dfc18a |
| DP2 design contract | docs/cscc/DP2_MULTI_REQUEST.md | f83ebea84fd570908be0df58255eca371ad4c28c4dc9d70ec3db0401b1143569 |

The service binding is the target launcher with served model Qwen3.5-27B,
BF16, TP1, PP1, DP2 using the mp backend, max-num-seqs 128,
max-num-batched-tokens 4096, compile size 4096, and GPU memory utilization
0.95. The scheduler supplies and hashes the actual model directory and its
config; do not substitute an unrecorded model, wheel, Python source tree, or
ABI library.

## Authoritative Workload and Complete DP2 Topology

Load and SHA-256 validate this profile before any runtime action:

~~~text
trace_profile_id=batch8-dual-dcu-dp2
trace_profile_path=/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/configs/trace_targets/batch8_dual_dcu_dp2.json
trace_profile_sha256=3b4c952063f48ae662b48b5ce9d8fd76e0ac4d74e170bdb1839ae8b1aaa23cce
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
accelerator=ROCm/DCU/HIP gfx936
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

The eight measured requests retain dataset order, run at infinite request rate
and concurrency eight, request 1024 output tokens each, use temperature zero,
ignore EOS, and exclude two warmup requests from all measured or reported
evidence. Reject request reordering, oversampling, early EOS, partial success,
or a different input bucket.

Every model execution, smoke, and formal capture uses the full DP2 service on
physical devices 0 and 1. Preserve world size two, rank 0 mapped to device 0,
rank 1 mapped to device 1, TP1, PP1, DP2, and the mp backend. A profiler pass
may be split by native device or counter family only when every piece remains
an attribute of this same dual-card workload. Never implement serial stage
ordering by hiding a device or reducing the service topology.

Completion requires independently auditable artifacts for both DP ranks and
both native physical-device identities, all eight measured requests, and the
declared rank-to-device mapping. Evidence from one card cannot be promoted to
full-stage evidence.

The tree at /public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile may
contribute only process definitions, taxonomy, marker vocabulary, schemas, and
reconstruction method. Prior single-card timings, traces, device mappings,
runtime handoffs, PMC rows, and measurement evidence are forbidden; regenerate
all R04 evidence in the current lineage.

## Fixed Service Readiness

The runtime wrapper must source the pinned scripts/cscc_gfx936_env.sh before
starting the target service and preserve its fixed TunableOp profile with
tuning and untuned-record generation disabled. Use the pinned
scripts/serve_cscc_dp2.sh launcher contract; do not reconstruct a weaker
single-worker command.

Cold compilation is not a steady-state capture. After initial readiness,
restart with the same source, installed distribution, model, cache, and
launcher arguments. Admit measured or replay work only when logs prove both
DP workers loaded their expected compiled graph caches, both report a
28,224-token GPU KV cache, both TunableOp initialization and pre-capture gates
are ready, speculative execution is disabled, and compile size 4096 is active.
Record the two worker/rank observations separately. This service-readiness
restart does not replace the two excluded request warmups.

## Serial Runtime Contract

~~~text
runtime_branch=workflow01-10-fresh-e2e
runtime_goal=R04
runtime_predecessors=R01,R02,R03
required_handoff_fields=status,execution_status,evidence_status,coverage_target_met,next_authorization_required,runtime_branch,runtime_goal,runtime_run_id,trace_profile_sha256,cumulative_runtime_ledger_sha256,r01_handoff_sha256,r02_handoff_sha256,r03_handoff_sha256,r03_artifact_manifest_sha256,selection_plan_sha256,capability_manifest_sha256,capture_tool_manifest_sha256,raw_manifest_sha256,hardware_attributes_sha256,independent_audit_sha256,report_sha256,artifact_manifest_sha256
runtime_artifact_root=<scheduler-assigned>
runtime_handoff_output=<scheduler-assigned>
advance_only_after=complete
~~~

Before runtime work, load and SHA-256 validate all three scheduler-assigned
predecessor handoffs and the immutable cumulative runtime ledger. Require the
exact same-run ordered prefix R01,R02,R03 on workflow01-10-fresh-e2e. Every
predecessor must have status=complete, execution_status=complete,
evidence_status=complete, coverage_target_met=true, the exact trace-profile
hash, and valid hashes for every referenced business artifact. Cross-check the
R01 and R02 hashes recorded transitively by R02 and R03 against the bytes
supplied directly to R04.

Reject a missing, failed, incomplete, out-of-order, shorter, longer,
cross-run, cross-branch, externally supplied, or hash-mismatched prefix.
Preserve the ledger and all predecessor handoff/artifact hashes in the resolved
R04 contract and final handoff. Never edit a predecessor handoff, ledger
entry, project skill, business artifact, or prior attempt.

Write business outputs only below runtime_artifact_root. Write exactly one
scheduler handoff only to runtime_handoff_output after all R04 stage checks
pass. Keep that handoff outside the business artifact manifest. The scheduler
must hash-validate it and every referenced output before starting R05.

## Admission Gate and Producer Responsibilities

R04 admission must read R02 directly even though R03 is the immediate
predecessor. Assert each of these R02 fields independently and literally as
false:

~~~text
profiler_execution_performed=false
trace_collection_performed=false
pmc_collection_performed=false
report_generation_performed=false
attribution_performed=false
~~~

Do not derive these five expectations through one mixed true/false expression
or a shared branch. A false admission caused only by validator logic, while
the R04 artifact root is still empty and no PMC work has started, permits only
an artifact-local admission-validator revision followed by the complete
predecessor hash gate again. It never permits editing R02, skipping a field,
or accepting an unvalidated predecessor.

R02 owns the exact Qwen process/fragment HIPTX instrumentation contract. R03
owns non-replay launch attribution, timing, matched kernel families, and GPU
order. R04 may consume but never re-prove or replace either producer's
responsibility.

## Required Fresh Predecessor Inputs

Resolve every input through the R03 scheduler handoff and its artifact
manifest, then validate its recorded path and SHA-256. At minimum consume:

~~~text
R02/handoff/FX_PROCESS_NVTX_INSTRUMENTATION_HANDOFF.md
R02/instrumentation/process_range_inventory.csv
R02/instrumentation/process_range_inventory.json
R02/instrumentation/fx_process_hiptx_adapter_sidecar.json
R02/manifests/artifact_manifest.json
R03/tables/qwen_dcu_batch8_dp2_process_hiptx_kernel_breakdown.csv
R03/tables/qwen_dcu_batch8_dp2_process_hiptx_kernel_breakdown.json
R03/tables/same_input_qwen_dcu_batch8_dp2_process_attribution.csv
R03/tables/process_gpu_timeline.csv
R03/tables/process_kernel_launch_order.csv
R03/reports/SAME_INPUT_QWEN_DCU_BATCH8_DP2_PROCESS_WISE_PERFORMANCE_REPORT.md
R03/validation/process_correlation.json
R03/validation/process_conservation.json
R03/validation/rank_device_coverage.json
R03/manifests/artifact_manifest.json
~~~

The R03 report's Representative Layer Process GPU Execution Order is the
human-readable row index. The R03 attribution, timeline, and launch-order
tables are the machine-readable source. They must agree on target/profile,
request selection, parent layer, forward, process/fragment identity,
matched_kernel_family, launch order, exact native kernel instances, rank,
physical device, and raw provenance.

Require exact R02 adapter literals and exact R03 normalized operation
subsequences. Broad marker prefixes, context-only ranges, stale reports,
historical copied CSVs, high-time rankings, and replay-derived order cannot
enter target selection.

Do not add an R04-only marker range. Reuse the exact R02 HIPTX/ROCTX
process/fragment push-pop range so the replay attributes join to the same R03
contract. If the inherited nvtx_include compatibility field is emitted,
serialize that exact push-pop literal with the historical trailing slash and
validate that removing only the slash yields the native R02 literal. The
trailing slash is compatibility data for the former NCU interface; never pass
an invented NCU option to rocprofv2.

## Native Vocabulary and Compatibility Boundary

Use native terms operationally:

| Compatibility/source term | R04 native binding |
| --- | --- |
| GPU | both physical gfx936 DCUs under the complete DP2 service |
| NVTX process range | exact HIPTX/ROCTX process or fragment range from R02 |
| CUDA runtime launch | proven HIP runtime launch call from R03 and replay correlation |
| CUPTI timing | immutable native hipprof non-replay timing from R03 |
| Nsight Compute or NCU replay | rocprofv2 PMC replay under the fixed DTK |
| NCU metric row | native per-dispatch PMC counter row plus formula/provenance |
| ncu_status | compatibility alias beside canonical pmc_status |

Retain NVTX, CUDA, CUPTI, NCU, nsys, and ncu_status only where an inherited
schema, report column, or compatibility alias requires them. Label every such
field. Never imply that NVIDIA tooling executed. The operational profiler is
rocprofv2, the marker backend is HIPTX/ROCTX, and timing comes only from the
R03 native non-replay capture.

## Representative Target Selection

Build the selection plan from the hash-validated R03 Representative Layer
Process GPU Execution Order, never from a new high-duration ranking:

1. include every representative parent layer present in R03;
2. preserve R03 process GPU order within each parent;
3. select process/fragment targets only when R03 proves launch-owned kernels;
4. expand aggregated cross-function processes to their declared R02 fragment
   ranges, then roll attributes back under the same R03 process/order row;
5. retain no-kernel rows in coverage with pmc_status=no_kernel and no invented
   counters;
6. allow filters only for debugging or physical batching; final completion
   still requires the entire representative scope on both ranks/devices.

One logical plan row represents one R03 process/fragment target, not a report
summary row and not a physical replay pass. Give each row a deterministic
target_id and retain its parent, forward, layer, process, fragment,
aggregation_key, exact HIPTX literal, matched kernel family, R03 instance
subsequence, request, rank, physical device, and source-row hashes.

For this locked batch8 workflow, the sealed full plan must prove these current
cardinalities from the same-run R02/R03 inputs:

~~~text
representative_rows=62
pmc_eligible_logical_targets=58
no_kernel_rows=4
unique_literal_physical_capture_batches=26
current_dynamic_expected_mapping_instances=66
~~~

Do not use 66 as the normalization algorithm and never use the obsolete value
89. Compute expected_mapped_dispatch_count by summing
selected_literal_r03_instance_count across all 58 eligible logical targets in
the sealed selection plan. The locked inputs currently prove a sum of 66; a
different fresh result is plan drift that must be investigated and explicitly
resolved, not silently forced to either historical number.

Same-literal logical targets may share one physical capture, but each logical
target retains its own selected R03 instances and must independently pass the
complete attribution chain. A shared raw file, capture order, or replay clock
does not prove process ownership, process order, or latency.

## Artifact-local Tools and Immutable Layout

Materialize the minimum runtime helpers below runtime_artifact_root/tools and
hash them before use. The surface may include a predecessor validator,
selection-plan builder, device/counter capability probe, replay wrapper,
normalizer, independent auditor, report generator, and artifact validator.
These helpers are created or revised only inside the current R04 artifact
tree; they never patch the target checkout or predecessor artifacts.

Use deterministic, attempt-scoped paths. At minimum produce:

~~~text
contract/resolved_input_contract.json
contract/r01_r02_r03_predecessor_validation.json
contract/r04_capture_contract.json
preflight/device_query_help.txt
preflight/device_occupancy.json
preflight/counter_catalog/basic.stdout.txt
preflight/counter_catalog/basic.stderr.txt
preflight/counter_catalog/basic.exit_code.txt
preflight/counter_catalog/derived.stdout.txt
preflight/counter_catalog/derived.stderr.txt
preflight/counter_catalog/derived.exit_code.txt
preflight/counter_catalog/counter_catalog.json
preflight/capability_manifest.json
preflight/filter_probe/collector_kernel_filter_probe.json
preflight/correlation_probe/hip_hcc_pmc_join.json
preflight/smoke/rocprofv2_smoke.json
plans/selection_plan.csv
plans/selection_plan.json
plans/capture_batches.json
tools/capture_tool_manifest.json
raw/captures/<capture_batch_id>/<pass_id>/execution_manifest.json
raw/captures/<capture_batch_id>/<pass_id>/<native-rocprofv2-files>
raw/raw_manifest.json
tables/process_gpu_hardware_attributes.csv
tables/process_gpu_hardware_attributes.json
tables/pmc_dispatch_mapping.csv
reports/SAME_INPUT_QWEN_DCU_BATCH8_DP2_PROCESS_GPU_HARDWARE_REPORT.md
validation/selection_plan_validation.json
validation/mapping_count_validation.json
validation/rank_device_coverage.json
validation/hardware_attribute_audit.json
validation/report_shape.json
validation/source_immutability.json
validation/r04_validation.json
manifests/analysis_manifest.json
manifests/artifact_manifest.json
attempts/
revisions/
quarantine/
~~~

Every attempt name is unique and immutable. Create a pass only in a verified
empty, previously absent output directory and fail closed on any name/path
collision. Never reuse, clear, truncate, or overwrite an old log, raw file,
exit-code record, plan, manifest, or report. The scheduler handoff is separate
from this layout and is not listed in artifact_manifest.json.

## Device Occupancy Preflight

Do not hard-code a hy-smi PID, utilization, or memory option. First capture and
parse the installed hy-smi help text, hash it, identify only options actually
supported by that version, and then perform read-only occupancy queries for
both physical devices. In particular, do not assume the unsupported
showpidgpus spelling exists.

Record the exact query interface selected, commands as argument arrays,
stdout, stderr, exit codes, parsed PID/utilization/memory state, timestamp,
and both device identities. Stop before model or PMC work when safe occupancy
cannot be proven. A preflight failure may be retried only in a new empty
attempt directory with the old attempt preserved.

## Counter Catalog Capability Contract

The fixed tool roots are:

~~~text
legacy_rocprof=/opt/dtk-26.04-DCC2602-0317/rocprofiler/bin/rocprof
native_rocprofv2=/opt/dtk-26.04-DCC2602-0317/rocprofiler/bin/rocprofv2
fixed_dtk_dcc_lib=/opt/dtk-26.04-DCC2602-0317/dcc/lib
~~~

Run list-basic and list-derived only in a later scheduler-authorized R04
capability attempt. For each list operation preserve stdout, stderr, and the
exact exit code. The fixed rocprof build can successfully print a gpu-agent9
catalog and then exit 1 with a zero-context message because list-only mode
creates no collection context. Therefore a nonzero list exit code alone does
not prove that counters are unavailable.

Accept a catalog only when an independent parser proves a recognizable agent,
counter names, derived formulas, categories/families, and nonzero counts from
the saved bytes. Record both the parsed proof and the nonzero exit diagnostic.
Conversely, every true replay pass must exit 0 and emit nonempty per-dispatch
counter rows that can be attributed; the list-only exception never weakens a
replay exit or evidence gate.

## Legacy Rejection and rocprofv2 Smoke Gate

Treat the legacy rocprof path as RPL v1 and unavailable for formal replay in
this fixed installation. Its help text is not capability proof: it searches an
incorrect /opt/dtk-26.04/bin/rocminfo path, lacks
rocprofiler/lib/roctracer/libroctracer_tool.so and libroctracer64.so.4, can run
a child while collecting zero contexts and empty raw output, and still
requires a .csv output suffix despite help showing a generic output operand.

Select rocprofv2 only after a real, small, model-free DCU smoke in a unique
attempt directory proves all of the following:

- process exit code is zero;
- the per-dispatch CSV is nonempty and parseable;
- requested counter columns contain usable values;
- HIP API and HCC operation streams are parseable;
- PMC dispatch rows join to HCC operations by nonzero correlation identity;
- tool path, tool hash, DTK libraries, commands, environment, raw hashes, row
  counts, and counter names are recorded.

The locked batch8 baseline smoke evidence is 11 per-dispatch rows and six
usable SQ counters. Re-prove and record those observed counts rather than
accepting the prose as runtime evidence. A drifted smoke blocks formal replay
until reviewed; it cannot be hidden by the old successful observation.

## Required HIP/HCC/PMC Correlation

Do not use hip-api alone for a formal counter pass. In the fixed installation,
the Qwen pilot counter CSV used zero Correlation_ID values while the HIP API
CSV used another sequence, and adding kernel-trace did not produce a joinable
kernel trace in PMC mode.

Before formal replay, a model-free probe must prove that hip-trace emits HCC
operations and that counter rows and HCC operations share nonzero correlation
IDs. Retain the HCC operation stream for every formal pass. Record the join
coverage, unmatched rows, duplicate IDs, and raw provenance. Do not replace
hip-trace with hip-api to reduce raw volume, and never delete the HCC stream.
Any pilot captured with the wrong trace option remains immutable diagnostics
and must be recaptured only after a recorded tool revision.

The historical model-free hip-trace smoke joined nonzero IDs such as
32, 43, 54, 65, and 78. Preserve those values only as diagnostic provenance;
the current runtime probe must independently establish its own nonzero join.

## Empirical Collector-filter Probe

The presence of ROCPROFILER_KERNEL_FILTER is not evidence that collector-side
filtering works. Before every formal run, execute an independent model-free
probe with a guaranteed-nonexistent literal and compare its dispatch count to
an unfiltered baseline. Record the exact literal, environment, raw files,
counts, decision rule, and result.

The fixed batch8 observation was five dispatches for the nonexistent literal,
equal to the five-dispatch baseline, so the collector filter was ineffective.
That observation explains the fail-safe policy but is not reusable runtime
evidence; every formal run must repeat the independent probe.

Write collector_kernel_filter_empirically_effective into each of:

~~~text
preflight/filter_probe/collector_kernel_filter_probe.json
preflight/capability_manifest.json
plans/selection_plan.json
plans/capture_batches.json
raw/raw_manifest.json
validation/r04_validation.json
reports/SAME_INPUT_QWEN_DCU_BATCH8_DP2_PROCESS_GPU_HARDWARE_REPORT.md
~~~

If the value is false, collect only the minimum bounded superset: one safe
literal physical batch corresponds to one complete canonical request inside
the unchanged eight-request DP2 workload. Retain every non-target native row
in immutable raw data, but exclude it from the hardware projection. Do not
claim collector-side filtering or shrink the workload because an environment
variable was set.

## Replay Environment and Python/ABI Provenance

The artifact-local replay wrapper must construct its own environment rather
than relying on variables inherited from the formal Goal control plane.
Immediately before launching rocprofv2 it must:

1. place the pinned trace-target source root first and the current R04 tools
   directory second on PYTHONPATH, followed only by the prior value;
2. place /opt/dtk-26.04-DCC2602-0317/dcc/lib first on LD_LIBRARY_PATH;
3. resolve the pinned checkout's .venv/bin/python to its real path and record
   the link plus resolution;
4. record all relevant environment values without leaking unrelated secrets;
5. prove in the pilot that imported vLLM Python modules come from the pinned
   source tree while compiled ABI shared objects come from the pinned installed
   vLLM distribution; and
6. hash the source tree evidence, Python executable, installed distribution,
   ABI objects, profiler executable, wrapper, and tool manifest.

A loaded-Python-tree drift before model load is not hardware evidence. A tool
fix must not mutate an old attempt. Isolate the old manifest, plan, helper,
logs, and raw directory; record old and new tool hashes and a revision reason;
seal a new tool manifest; rebuild every hash-pinned target metadata file; and
retry only in a new empty attempt. The repaired pilot must prove both source
tree and ABI provenance before formal capture.

## Full-DP2 Replay and Pass Manifests

Each formal physical capture batch preserves the complete eight-request
workload and both DP workers. Counter-family or device splits are multiple
attribute passes over the same sealed logical batch contract, not independent
latency experiments. Keep visible-device lists unchanged and retain native
rank/device identity in every raw row and manifest.

Before each pass, hash-validate the target, profile, predecessor prefix,
selection plan, capture-batch plan, tool manifest, request selection, model,
launcher, counter list, environment, and empty output root. A successful
execution_manifest.json records at least:

- run, Goal, attempt, logical batch, physical pass, counter family, rank, and
  native device IDs;
- command as an argument vector, environment contract, start/end timestamps,
  scoped PIDs, exit code, and accumulated profiling wall time;
- exact safe literal set and whether empirical collector filtering worked;
- hip-trace/HCC correlation mode and join proof;
- all output paths, sizes, SHA-256 values, schemas, dispatch counts, counter
  columns, and source-row provenance;
- request completion for all eight measured requests plus two excluded
  warmups, with both ranks/devices covered; and
- successful device release after files are sealed.

Require exit code zero, a nonempty attributable counter table, complete
request success, both-rank/device coverage, and a sealed execution manifest
for every accepted pass. A directory containing only a counter-request file
or partial CSV is never a completed pass.

## Exact Attribution Chain

Project a native PMC row only when all links below are proven within the same
physical replay and against the sealed predecessor plan:

~~~text
logical R04 target
  -> exact software literal selected from R02
  -> exact R02 HIPTX process/fragment range in that replay
  -> proven HIP runtime launch owned by that exact range
  -> retained HCC operation joined to the PMC dispatch by nonzero correlation ID
  -> exact normalized R03 operation subsequence for the selected literal instance
  -> R03 matched_kernel_family row, request, rank, and physical device
~~~

Kernel name alone, time overlap, pass order, replay order, row proximity,
shared raw membership, or a repeated literal is insufficient. Preserve raw
unmatched, non-target, duplicate, and ambiguous rows with explicit reason
codes; none may enter the projected attribute table.

The same-literal optimization may reuse one physical capture for several
logical targets, but each target separately proves its exact range, launch,
correlation, normalized subsequence, and mapping multiplicity. Never use the
replay clock to fill R03 process timing or order fields.

## Metric Normalization and Independent Audit

Normalize raw counters into these hardware-attribute families when supported
by the proven catalog and formulas:

- SM or compute-unit utilization;
- matrix/Tensor Core utilization or a clearly labeled unavailable value when
  this DCU exposes no defensible equivalent;
- DRAM throughput;
- L2 throughput;
- occupancy;
- dominant warp/wave stall reasons; and
- register/shared-memory pressure when available.

Every normalized value records native counters, units, formula, aggregation,
counter-family pass, device/rank, dispatch provenance, catalog hash, and tool
hash. Never fabricate a metric, silently substitute a differently defined
counter, mix incompatible replay passes as simultaneous observations, or turn
an unavailable metric into zero.

The normalizer and an independent auditor must separately read the sealed
selection plan and compute:

~~~text
expected_mapped_dispatch_count=sum(selected_literal_r03_instance_count for every eligible logical target)
mapped_dispatch_count=number of accepted logical-target-to-dispatch mappings
required_relation=mapped_dispatch_count == expected_mapped_dispatch_count > 0
~~~

They must agree on eligible targets, per-target multiplicities, total mapping
count, rejected rows, and both-rank/device coverage. For the current sealed
batch8 inputs both computations must derive 66, not embed 66 as an assertion
constant and never compare to 89.

If capture passes are valid but normalization or audit code is wrong, revise
offline only. Archive and hash the capture-time tool manifest, old normalizer,
old auditor, failure result, and revision history. The new analysis manifest
must cite the capture-time manifest, distinguish capture-time and
analysis-time tool hashes, and validate every replay manifest's original
capture provenance. Do not recapture valid raw bytes for an offline analysis
defect.

## Hardware Projection and Report Shape

The main report is a filtered hardware-attribute projection over R03 rows:

~~~text
R03 process/fragment HIPTX target
  -> R03 launch-owned matched kernel family and non-replay order
  -> exact R04 replay dispatch mapping
  -> normalized native hardware attributes for that same family
  -> one report row per R03 matched_kernel_family
~~~

Do not emit one process-summary row or one row per replayed kernel instance.
Preserve these inherited columns and add explicit request/rank/device and PMC
provenance columns as needed:

~~~text
parent_layer_range
forward_id
layer
first_kernel_launch_order_in_parent
process_gpu_order
process_gpu_start_offset_us
process_id
process_title
fragment_id
matched_kernel_family
kernel_family_instance_count
nsys_kernel_name_examples
ncu_status
ncu_kernel_family_instance_count
ncu_profiled_kernel_names
nvtx_include
SM utilization
Tensor Core utilization
DRAM throughput
L2 throughput
occupancy
dominant stall reasons
hardware bottleneck interpretation
target_id
request_id
dp_rank
physical_device_id
pmc_status
pmc_counter_provenance
collector_kernel_filter_empirically_effective
~~~

Compatibility columns nsys_kernel_name_examples, ncu_status,
ncu_kernel_family_instance_count, ncu_profiled_kernel_names, and nvtx_include
must be labeled as aliases. Their values originate from native R03 kernel
names, native rocprofv2 PMC rows, and exact R02 HIPTX literals respectively.

Do not include these Workflow 02 timing/evidence columns in the main hardware
table:

~~~text
CUPTI kernel ms
NVTX CPU ms
process_cupti_pct_in_parent
process_nvtx_pct_in_parent
runtime API calls
kernel instances
validation status
~~~

Those fields remain in R03 evidence. The R03 order and start-offset columns are
immutable join context, not R04 latency measurements. The report must explain
the non-replay/replay boundary, target coverage, metric availability, filter
probe result, mapping counts, both-rank/device coverage, raw/analysis tool
provenance, and every degraded or unavailable attribute.

## Interruption, Quarantine, and Resume

The formal runtime scheduler and profiler processes are held by the Codex
app-server control plane. A response-stream break after a capture start record
can terminate the scheduler, app-server, model executor, and profiler without
producing an ordinary replay failure.

Before recovery, inspect and cross-check runtime state, the formal Goal stop
reason, scoped PIDs, the last complete execution_manifest.json, the active
pass directory, source/plan/tool hashes, and cumulative profiling wall time.
If the Goal is already blocked by a control-plane error, do not use
continue-current-goal. A generic resume that creates a new empty resume root
also cannot implement suffix-only recovery.

Resume the same run from R04 only through the scheduler's constrained
resume-artifact-root interface, naming the original canonical R04 artifact
root. The scheduler must create a new formal R04 Goal attempt while preserving
the run lineage, artifact root, sealed plan, completed manifests, and all
predecessor hashes. Accept that root only if runtime state or attempt history
already records it for R04 and its resolved path remains inside the canonical
R04 root.

An interrupted pass without a qualifying execution manifest is immutable
failed evidence. Record interruption reason, original path, scoped process
state, file inventory, sizes, and SHA-256 values, then move the whole directory
to a unique quarantine/revision location within runtime_artifact_root. Never
delete, clear, or overwrite it. Recollect that physical batch only in a new
empty pass root. Before any suffix resume, revalidate every completed manifest
and artifact hash, target commit/clean state, profile and predecessor hashes,
sealed plan/tool manifests, both-device coverage to date, and cumulative
profiling wall time.

## Runtime Procedure

These steps are only for a later scheduler-authorized R04 invocation. The
Adapt Goal that creates this skill must not execute any of them.

1. Validate the exact R01,R02,R03 ledger prefix, all handoff bytes and
   transitive hashes, R02's five independent false assertions, R03 business
   artifacts, target commit/clean state, trace profile, workload/topology,
   scheduler paths, and an unused R04 attempt root before HIP initialization.
2. Build and seal the complete representative-target plan from R03, preserving
   order, fragments, literals, matched families, instances, rank/device
   identity, 62/58/4/26 plan cardinalities, and the dynamically derived
   mapping count.
3. Materialize and hash the minimum artifact-local helpers. Capture and parse
   hy-smi help before choosing read-only occupancy queries for both devices.
4. Capture rocprof counter catalogs with stdout, stderr, and exit codes;
   validate them by parseable content. Reject the legacy collector for formal
   work and prove rocprofv2 with the small DCU smoke.
5. Prove the nonzero PMC-to-HCC join with hip-trace and empirically test the
   nonexistent-literal collector filter. Seal capability and tool manifests.
6. Construct the replay environment explicitly, prove Python-source and ABI
   provenance, then execute each sealed physical capture batch over the full
   DP2 workload. Preserve one immutable execution manifest per successful
   pass and preserve all failures separately.
7. Seal all raw outputs without dropping non-target rows. Attribute only by
   exact literal, exact replay HIPTX range, owned HIP launch, HCC/PMC
   correlation, and exact normalized R03 subsequence.
8. Normalize hardware attributes and independently audit mapping counts,
   per-target multiplicities, raw provenance, request/rank/device coverage,
   formulas, and units. Repair valid captures offline only.
9. Generate the matched-kernel-family projection and hardware report from the
   sealed R03 and R04 inputs. Validate report shape and the timing/replay
   evidence separation.
10. Validate source immutability, every hash, complete coverage, raw and
    analysis manifests, report reproduction, attempt inventory, and device
    release. Only then write the scheduler handoff.

## Validation and Failure Rules

R04 is complete only when all of the following are true:

- target commit/clean state, source hashes, trace-profile hash, complete
  R01-R03 handoff prefix, cumulative ledger, and every referenced predecessor
  artifact hash validate;
- R02's profiler, trace, PMC, report, and attribution execution fields are
  independently false, while R03 supplies the only accepted non-replay timing
  and order evidence;
- the exact eight-request contract completes under full DP2 with two excluded
  warmups, and both ranks/devices are independently present in plans, raw
  rows, mappings, tables, reports, manifests, validation, and the handoff;
- the device query interface was selected from captured help and both devices
  were safely available before capture;
- counter catalogs are content-validated, rocprofv2 smoke succeeds, and every
  accepted replay exits zero with nonempty attributable per-dispatch data;
- hip-trace HCC operations provide the proven nonzero correlation join and the
  empirical collector-filter result is consistently recorded;
- every projected row passes the exact literal/range/launch/correlation/R03
  subsequence chain, while unmatched or ambiguous rows remain immutable and
  excluded;
- both normalizer and independent auditor derive the same positive expected
  mapping count from the plan and mapped dispatch count equals it;
- all hardware values carry counter/formula/unit/pass/device provenance, and
  unavailable metrics are labeled rather than invented;
- the main report uses R03 matched-kernel-family rows, contains no replay
  latency claim or forbidden Workflow 02 evidence column, and retains R03
  timing/order only as labeled immutable context;
- capture-time and analysis-time tool provenance, every pass manifest, raw
  hash, offline revision, failed attempt, and quarantine entry validate; and
- business artifacts remain below runtime_artifact_root, the scheduler
  handoff remains separate, predecessor bytes are unchanged, the target stays
  clean, and both devices are released.

Fail closed on a missing/mismatched predecessor, dirty or wrong target,
profile/request/topology drift, single-card promotion, unsupported occupancy
query, unparseable catalog, failed smoke, legacy zero-context output,
formal-replay nonzero exit, empty counter data, absent HCC join, ambiguous
dispatch ownership, filter claim without empirical proof, count mismatch,
missing rank/device, unit/formula ambiguity, source/ABI drift, overwrite risk,
incomplete pass manifest, report/schema failure, or unaccounted interruption.

A capability or pre-model environment defect permits only a new isolated
preflight attempt. A proven capture failure permits a new full-DP2 capture in
a new pass root. A valid raw-capture normalization, audit, or report defect
permits only byte-preserving offline repair. Never recapture valid raw bytes
merely to repair post-processing.

## Runtime Handoff

After every business output and gate passes, write one JSON handoff only to
runtime_handoff_output with at least:

~~~text
status=complete
execution_status=complete
evidence_status=complete
coverage_target_met=true
next_authorization_required=false
runtime_branch=workflow01-10-fresh-e2e
runtime_goal=R04
runtime_predecessors=R01,R02,R03
timing_collection_performed=false
pmc_replay_treated_as_latency=false
profiler_execution_performed=true
pmc_collection_performed=true
report_generation_performed=true
attribution_performed=true
~~~

Also record the runtime run/attempt IDs; cumulative-ledger path/hash; exact
R01, R02, and R03 handoff paths/hashes; all transitive predecessor hashes;
target commit, clean state, and source hashes; trace-profile path/hash;
model/Python/ABI/launcher hashes; request selection and workload parameters;
complete rank-to-device mapping; R03 report/table/manifest hashes; R02 exact
literal sidecar hash; selection and capture-plan hashes; device preflight;
counter catalogs; rocprofv2 smoke and HCC join; filter effectiveness; capture
and analysis tool manifests; every pass execution manifest; raw manifest;
dynamic expected and observed mapping counts; per-rank/per-device coverage;
normalized table and audit hashes; report and validation hashes; failed and
quarantined attempt inventories; cumulative profiling wall time; device
release; artifact manifest; and the exact R05 advance gate.

The scheduler may advance only after it validates this handoff and every
referenced hash. A complete Adapt handoff for A04 is never runtime evidence and
must not be cited as proof that R04 executed.
