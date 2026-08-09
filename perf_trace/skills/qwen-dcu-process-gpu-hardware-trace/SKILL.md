---
name: qwen-dcu-process-gpu-hardware-trace
description: Execute fresh-run R04 for Qwen3.5-27B. Collect current same-lineage non-replay representative process timing and serial DCU 1 PMC replay diagnostics, enforce exact HIPTX/runtime/HIPOPS ownership and family joins, and retain replay counters strictly as hardware attributes rather than latency.
---

# Qwen3.5 Fresh-Run R04 GPU Hardware Trace on DCU

Project DCU hardware attributes onto representative process rows already
established by the current process trace. Keep process markers, launch
ownership, process order, and non-replay timing under the upstream
instrumentation and performance Skills. Use replay only for hardware
attribution.

Require `user.evidence_acquisition_mode=fresh_no_prior_runtime_reuse` and only
the same run's R01-R03 handoffs. Capture every R04 non-replay timing and PMC
row freshly on physical DCU 1. Do not reuse a prior hardware row merely because
its family name matches.

Treat `perf_trace_bk` as read-only archived binding evidence. It is never fresh
run evidence, a live input directory, or a valid output directory. Its pinned
tools establish the verified hipprof collection modes, HIPTX/HIP/HIPOPS schema,
PMC block parsing, family projection, and report vocabulary; resolve writable
live tool and artifact paths at runtime.

## Establish the Current Run Contract

Use the canonical project root and confirmed project identities:

```text
PROJECT_ROOT=/public/home/tangyu408/Qwen_DCU_Worker_0
SOURCE_ROOT=/public/home/tangyu408/Qwen_DCU_Worker_0/pra2026-bh408
MODEL_ROOT=/public/home/tangyu408/Qwen_DCU_Worker_0/Qwen3.5-27B
RUNTIME=vLLM/PRA
ACCELERATOR=ROCm/DCU/HIP
DEVICE=physical gfx936 DCU 1
```

Resolve all current run paths below from the live worktree and current
handoffs. Do not infer them from archived run directories:

```text
PROCESS_INSTRUMENTATION_HANDOFF=<current regenerated handoff>
NON_REPLAY_PROCESS_ANALYSIS=<same-run R03 process analysis>
NON_REPLAY_FAMILY_ORDER=<current process_launch_owned_kernel_family_order.csv or schema-equivalent>
LIVE_HIPPROF_RUNNER=$SOURCE_ROOT/scripts/perf_trace/run_qwen_hardware_profile_single_request.sh
LIVE_TRACE_ANALYZER=$SOURCE_ROOT/scripts/perf_trace/analyze_qwen_hipprof_process_trace.py
LIVE_PMC_ANALYZER=$SOURCE_ROOT/scripts/perf_trace/analyze_qwen_hipprof_pmc.py
LIVE_HARDWARE_CONSOLIDATOR=$SOURCE_ROOT/scripts/perf_trace/consolidate_qwen_dcu_hardware_metrics.py
HARDWARE_OUTPUT_ROOT=<scheduler-assigned-runtime_artifact_root>
```

Require the upstream handoff and non-replay analysis to describe the same
Qwen3.5-27B semantic request, vLLM/PRA configuration, input, token limits,
scheduling, tensor parallelism, device, process definitions, and current-run
lineage. Record each stage's `pra2026-bh408` revision/source state; do not
require R04 hashes to equal R01-R03. Reject missing, stale, mixed-run, or
archive-copied inputs.

Consume these fields, or explicitly verified schema-equivalent fields, from
each current non-replay family row:

```text
parent_layer_range
forward_id
layer
event_id
stage
first_kernel_launch_order_in_parent
process_gpu_order
process_gpu_start_offset_us
process_id
process_title
fragment_id
first_kernel_launch_order_in_process
matched_kernel_family
kernel_family_instance_count
hipprof_kernel_duration_ms
hipprof_kernel_name_examples
gpu_order_basis
```

Treat `hipprof_kernel_duration_ms`, process offsets, and launch order as
read-only non-replay timing/order evidence. Never replace them with replay
duration.

Derive every expected denominator from the current handoff and its current
non-replay family-order table. Archived example counts for events, processes,
layers, markers, or kernel families are never completion denominators.

## Build the Complete Representative Selection

Build the target plan in this order:

1. Enumerate every representative parent layer in the current upstream
   handoff.
2. Preserve the upstream `process_gpu_order` within each parent.
3. Select every process or fragment with launch-owned kernels.
4. Keep cross-function fragments as distinct capture targets while preserving
   their upstream process identity and aggregation relationship.
5. Preserve every expected `event_id + stage + matched_kernel_family` row in a
   separate family ledger.
6. Retain expected no-kernel process rows with `no_kernel` status, but do not
   launch a hardware replay solely for them.

Use the existing current HIPTX process range for each capture target. The
confirmed naming form is:

```text
pra.fx_process.<event_id>.<stage>
```

Do not add hardware-only markers, rename an upstream range, select a new
high-time ranking, or infer targets from replay results. One capture target is
one upstream process/fragment range; one report row is one upstream
`matched_kernel_family`.

Write `dcu_process_selection_plan.csv` before collection. Include the capture
target identity, parent/event/process/fragment identity, HIPTX range, expected
kernel families, current-run provenance, selection mode, and collection
status. Permit layer, phase, process, or target filters only for explicit
debugging or batching. Mark filtered output `debug_batch` or `incomplete`;
never declare it complete.

## Resolve and Validate Live hipprof Bindings

Use the pinned archive only to verify the required behavior:

- support `process-trace`, `pmc`, `pmc-read`, and `pmc-write` mode names;
- use hipprof HIPTX and HIP tracing in every relevant capture;
- use the selected PMC type consistently across the three replay modes;
- record tool, source revision, runtime package, device, start time, finish
  time, and exit status;
- keep each raw capture and analysis directory separate.

The archived implementation used `/opt/dtk/bin/hipprof` with
`--hiptx-trace`, `--hip-trace`, `--pmc-type 0`, and the corresponding
`--pmc`, `--pmc-read`, or `--pmc-write` switch. Verify those bindings against
the live gfx936 environment before use. If the live path, option spelling,
database schema, or current project runner differs, resolve and record the
equivalent at runtime. Do not guess, silently substitute a similar profiler,
or execute a script under `perf_trace_bk`.

Require each resolved live tool to exist outside the archive, expose its
expected interface, and pass syntax or `--help` inspection before collection.
If no verified live binding exists, stop with the unresolved path/tool binding
and preserve the full collection requirement.

## Collect Three Separate Replay Traces

Run the same request contract three times through the verified live runner:

```bash
"$LIVE_HIPPROF_RUNNER" pmc "$PMC_OUTPUT_ROOT" "$PMC_TAG"
"$LIVE_HIPPROF_RUNNER" pmc-read "$PMC_READ_OUTPUT_ROOT" "$PMC_READ_TAG"
"$LIVE_HIPPROF_RUNNER" pmc-write "$PMC_WRITE_OUTPUT_ROOT" "$PMC_WRITE_TAG"
```

Define those variables only after runtime resolution. Place all three roots
under the new `HARDWARE_OUTPUT_ROOT`, never under `perf_trace_bk`.

For every replay:

- use physical gfx936 DCU 1 and the exact upstream input/configuration;
- capture HIPTX, HIP runtime, and HIPOPS data needed for strict ownership;
- preserve the upstream process-profile flag and existing process ranges;
- save raw profiler data, log, and tool/run provenance;
- use a distinct hipprof session and output directory;
- keep replay artifacts separate from the upstream non-replay trace.

Do not merge the three replays with one another or with the non-replay timing
capture. Do not use replay kernel time as process latency, end-to-end latency,
or a denominator.

## Reconstruct Strict Replay Ownership

Normalize each replay trace independently. Preserve this ownership chain:

```text
process HIPTX range
  -> HIP runtime call inside the range and within its runtime-index bounds
  -> HIPOPS kernel with identical source DB, config key, pid, and runtime _Index
```

Require the runtime call start and end timestamps to lie inside the HIPTX
range. Require its `_Index` to lie between the marker's begin and end runtime
indices. Join HIPOPS only by the identical runtime `_Index` within the same
database/configuration/process identity. Never attribute a kernel by time
overlap, name similarity, nearest timestamp, or process-title coincidence.

Parse the upstream-compatible `pra.fx_process.<event_id>.<stage>` identity and
emit replay-side annotations, runtime calls, kernels, strict ownership,
process launch order, and process kernel-family order. Classify kernel names
with the verified current family classifier; do not create an ad hoc family
only to force a join.

Reject an ambiguous marker identity, duplicated ownership, cross-database
collision, missing runtime call, index mismatch, or selected marker with no
explainable ownership result.

## Attach PMC Blocks to Replay Kernels

For each of `pmc`, `pmc-read`, and `pmc-write`:

1. Parse each `kernel-name:"..."` block from the profiler metric text or the
   verified live equivalent.
2. Preserve numeric counter values and retain unparsed values visibly.
3. Demangle each PMC kernel name with the verified live demangler.
4. Partition by profiler process ID and sort blocks by
   `kernel_dispatch_index`.
5. Sort replay trace kernels by begin timestamp and stable kernel ID within
   the same process.
6. Pair only when dispatch order and the exact demangled kernel name agree.
7. Attach only kernels already owned through the strict HIPTX-to-runtime-to-
   HIPOPS chain.
8. Write joined blocks and all unmatched blocks separately.

Do not fuzzy-match kernel names or discard unmatched blocks. Record
`pmc_block_count`, trace kernel count, exact name/order matches, unmatched
count, strict-owned metric rows, selected event/process coverage, and
`name_order_match_rate` for each replay mode.

Require a global name/order match rate of at least the verified implementation
threshold of `0.99`. Also require zero unmatched or ambiguous blocks that
belong to a selected target. A high global rate never excuses a missing target
family.

## Join Replay Hardware to Non-Replay Families

Use the non-replay family ledger as the left side of every projection. Join
each replay source only on:

```text
event_id + stage + matched_kernel_family
```

Use replay `kernel_id` only inside its own replay trace. Never equate kernel
IDs across runs. Never join by family alone, process title alone, layer alone,
or row position.

For each expected family row, record:

```text
dcu_pmc_status
pmc_kernel_family_instance_count
pmc_read_kernel_family_instance_count
pmc_write_kernel_family_instance_count
pmc_profiled_kernel_names
hardware_join_key
replay_instance_count_changed
```

Preserve the upstream row order. Expose a replay instance-count difference
against `kernel_family_instance_count`; do not rescale or replace upstream
timing because of it. Treat an unexpected, missing, or renamed family as a
possible replay path change rather than silently joining it to a nearby row.

Use these row states:

- `complete`: all three replay sources strictly join to the expected family;
- `partial`: at least one replay source joins and at least one is absent;
- `missing`: no replay source joins;
- `no_kernel`: the upstream row explicitly represents an expected CPU-only
  process range;
- `unavailable`: a particular metric is not exposed even though its required
  replay collection completed.

Keep `unavailable` at field level. Never invent an unsupported counter or turn
an unavailable field into zero.

## Project DCU Hardware Diagnostics

Aggregate replay instances within the same strict family key. Preserve raw
replay rows in addition to the projection.

Report the following diagnostics when their verified PMC fields are present:

- activity from `processed_alu_instructions`, weighted by replay
  `kernel_time`;
- a DCU matrix-core utilization proxy only for the confirmed
  `TunableOp_MMAC_GEMM` family, explicitly labeled as a proxy;
- L2 hit rate from `l2_cache_hit_rate`;
- mean L2 read and write size per replay instance from
  `size_of_l2_cache_read` and `size_of_l2_cache_write`;
- projected L2 bytes as `(mean read KB + mean write KB) * 1024 *` the
  non-replay family instance count;
- projected L2 throughput using projected bytes and the upstream non-replay
  family duration, without changing that duration;
- a theoretical occupancy upper bound from work-group size, VGPR count, and
  shared-memory size;
- register and shared-memory pressure fields when exposed;
- the strongest available stall proxy among L1 cache stall, L2 write stall,
  and shared-memory bank conflict.

For the confirmed gfx936 projection, compute the occupancy upper bound with
wave size 64 and the verified limits encoded by the live consolidator:

```text
waves_per_group = ceil(work_group_size / 64)
groups = min(
  40 / waves_per_group,
  2560 / work_group_size,
  196608 / (vgpr_count * work_group_size),
  65536 / shared_memory_size when shared memory is nonzero
)
occupancy_upper_bound_pct = min(100, 100 * groups * waves_per_group / 40)
```

Use integer floor limits as the live implementation does. Verify that the
current device is still gfx936 before applying these constants; otherwise
stop and resolve the correct device limits rather than guessing.

Label replay `kernel_time` weighting as diagnostic-only. Label occupancy as a
theoretical resource upper bound, not achieved occupancy. Label matrix
activity as a DCU proxy, not an NVIDIA Tensor Core metric. Mark DRAM
throughput `unavailable` when the selected hipprof derived PMC set does not
expose a verified equivalent. Do not infer DRAM behavior from L2 bytes.

Base the bottleneck interpretation only on available evidence. Distinguish
compute-active MMAC behavior, low-L2-hit cache or memory pressure, occupancy
resource limits, and the strongest available stall proxy. When evidence does
not identify a dominant cause, say so explicitly.

## Emit Family-Level Outputs

Write all new artifacts beneath `HARDWARE_OUTPUT_ROOT`. Produce:

```text
dcu_process_selection_plan.csv
hardware_replay_kernel_metrics.csv
hardware_metrics_by_kernel_family.csv
hardware_metrics.csv
hardware_coverage.json
DCU_HARDWARE_METRICS_REPORT.md
SAME_INPUT_PRA_QWEN35_FULL_EAGER_PROCESS_WISE_DCU_REPORT.md
```

Keep per-mode normalized trace tables, PMC summaries, and unmatched-block
files beside these consolidated outputs. Make
`hardware_metrics_by_kernel_family.csv` and the report's primary table one row
per upstream `matched_kernel_family`. Keep `hardware_metrics.csv` as a
secondary process summary only.

Include the upstream identity/order columns, family instance counts, replay
status/counts/names, activity, matrix proxy, L2 read/write/hit and projected
throughput, occupancy upper bound, register/shared-memory pressure when
available, stall proxy, bottleneck interpretation, and a stable
`event_id:stage:matched_kernel_family` target ID.

Do not repeat upstream CPU-envelope or process-attribution evidence as new
hardware evidence. Exclude replay duration from the primary report. State in
both report and machine-readable metadata:

```text
timing_source=workflow02_non_replay_family_row
hardware_join_key=event_id+stage+matched_kernel_family
pmc_replay_timing_used_as_latency=false
```

## Validate Coverage and Failure Semantics

Compute `hardware_coverage.json` from the current expected sets, including:

- expected and observed representative parent layers;
- expected process/fragment capture targets;
- expected kernel-family rows and expected no-kernel rows;
- complete, partial, missing, and no-kernel row counts;
- family join coverage and per-mode join coverage;
- replay family instance counts and count-drift rows;
- unmatched and ambiguous PMC block counts;
- unexpected replay families or execution-path changes;
- `pmc_is_latency_evidence=false`.

Require every expected family row to appear exactly once in the projection and
in the primary report. Require all current representative parent layers, all
launch-owning process/fragment targets, and all three replay modes. Require
strict selected-target joins and preserve the upstream family/order ledger.

Set the full-run coverage status to `PASS` only when:

- the selection plan covers the complete current upstream denominator;
- all required captures share the current run contract;
- each selected HIPTX range has valid strict ownership;
- every required family row is `complete` and no required row is `partial` or
  `missing`;
- every expected no-kernel row is explicitly `no_kernel`;
- selected-target kernel name/order joins are unambiguous;
- no replay family or execution path contradicts the non-replay ledger;
- the main report uses family rows and preserves the replay timing boundary.

Set filtered runs, incomplete coverage, partial/missing rows, stale inputs,
ambiguous joins, tool/schema drift, and run-contract mismatches to a non-PASS
status. Emit their evidence, then stop; never relabel them as complete.

If replay changes the kernel family or execution path, stop all latency
interpretation. Do not regenerate a predecessor inside R04; resume or replay
R02/R03 through the scheduler before any timing claim. A replay instance-count drift
may remain a visible hardware diagnostic only when family identity and the
execution-path checks still pass.

## Preserve the Timing and Evidence Boundary

Keep replay hardware diagnostics separate from non-replay timing and latency.
Never use PMC duration to overwrite process time, end-to-end time, launch
order, or the full-layer denominator. Never change a downstream segmented
attribution denominator from this Skill.

Declare completion only after the full current target set, three replay
collections, strict ownership, strict family joins, output set, coverage
checks, and report checks pass. Archived reports, databases, fixed counts, or
previous PASS summaries cannot satisfy any current-run completion condition.

Keep GPU work serial, retain exact family/name/order matching, and preserve PMC
replay duration as non-latency. Emit enough current family/resource evidence
for R08 to target high-latency gaps and build the same-run traffic/resource
model. R04 may change profiling wrappers, counter selection, instrumentation,
parsers, consolidators, or validators before capture. Record the R04 stage
delta and freeze that post-patch state for R04's non-replay and replay set.
Source equality with earlier goals is not required. If a patch changes model,
input, sampling, device, process identity, or output semantics, stop; otherwise
recapture the affected R04 evidence within this same lineage.

Use the maintained finalizer to write only the scheduler-assigned R04 JSON
handoff after the full target set, serial replay captures, strict joins,
coverage, and independent audit pass. All R04 business artifacts remain under
`runtime_artifact_root`; R04 must not invoke R05 or regenerate R01-R03.
