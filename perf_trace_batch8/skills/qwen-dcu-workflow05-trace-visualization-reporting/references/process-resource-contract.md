# Process distribution and hardware-resource window contract

This is the maintained Workflow05 analytical-view profile for this project.
It governs the high-latency and resource pages, not unrelated optimization
composition figures or the full lossless evidence viewer. Explicit user
changes must update the resolved profile and its audits consistently.

## 1. Evidence, scope and execution modes

Keep three distinct sets: the declared R07 trace target universe, the bounded
R08 hardware capture universe, and the R10 visible subset. Neither successful
request completion nor a selected view proves full-token Process or hardware
coverage. Record request/rank/device/phase/step scope before drawing.

Fresh execution uses the serial same-run R01–R10 scheduler prefix. R07 owns
observed timing and live samples; R08 owns targeted replay counters; R09 owns
full normalized analyses; R10 owns display transforms and offline acceptance.
A changed display requirement does not authorize extra model/profiler work.

Retained presentation uses hash-verified accepted inputs from one recorded
lineage. Restore existing raw/normalized evidence before proposing collection.
Write separate derived outputs and view audits; do not modify original handoffs,
rename recovered status to fresh complete, or claim a new R07/R09 run. Renderer
code and empirical reference documents have their own provenance. A hardware
reference is not runtime evidence from another trace.

## 2. Producer contract: R06–R08

R06 enumerates the complete declared Process/fragment target set and separately
budgets expensive PMC families. The display threshold below must never truncate
R07 targets or change the workload. Record expected resource coverage and
capability limits; make omitted capture families explicit.

R07 preserves actual interval IDs, request/rank/device/phase/step identities,
parent/fragment nesting, exact launch-owned kernels and clock anchors. Keep all
raw live samples, slow calls, gaps and uncertainty. At least three eligible
samples and the resolved gap/alignment gates are needed for a valid window
mean. An unavailable mean is not low activity. Sampling failures must not be
confused with scheduling-candidate status.

R08 retains the raw counters AND their own measurement intervals, not only
family averages. For every normalized physical dispatch retain:

- unique physical-attribute/capture/pass IDs, counter mode, native row identity,
  raw file path/size/hash, and native begin/end time with unit/clock;
- exact R07 owner Process/fragment/kernel IDs and device/rank/request identity;
- observed and replay shapes, matching/comparability state, and sharing rules;
- raw counter names/values, formulas, memory space, units, missing/invalid states;
- device/architecture and any reference bandwidth or compute limit, including
  whether it is rated, empirically measured, user supplied or unknown.

In the retained Batch8 schema the own-pass timestamps are
`native_signature_begin_monotonic_ns` and `native_signature_end_monotonic_ns`.
Do not replace them with a CPU launch duration or the R07 Process duration.
A PMC/HIPOPS timestamp comparison is separate diagnostic evidence.

## 3. R09 analyses and derived resource values

Preserve the twelve base tables and their complete source membership:
`request_timeline`, `process_timeline`, `kernel_timeline`,
`live_utilization_aligned`, `process_live_utilization`, `kernel_concurrency`,
`queue_concurrency`, `launch_gaps`, `high_latency_processes`, `dependency_state`,
`traffic_resource_attachment`, `opportunity_candidates`.

Kernel/queue overlap, busy unions and launch gaps use only R07 observed time.
R08 counters supply attributes; their timestamps do not enter the observed
schedule. Preserve original high-latency classification and ties separately
from the display ranking. A no-kernel parent remains in the Process table.

Derived resource sidecars must carry source hashes, formulas, null reasons and
coverage, and be sealed with the analysis/view manifest:

- Directional replay bandwidth: `bytes / own_pass_duration_ns` is decimal GB/s;
  divide by the documented bandwidth reference for a reference percentage.
  Positive duration, valid counters and explicit units are required. Read/write
  modes from different replays stay separate. Never sum them as simultaneous
  measured traffic. Do not silently cap values above 100%.
- Process reference: aggregate unique same-direction selected dispatch bytes
  over the sum of their own replay durations. Require all included dispatches
  valid and shapes matched for projection. State selected-kernel coverage; this
  is neither whole-Process nor original R07 live bandwidth.
- L2 hit rate: hits/(hits+misses); L2 request rate: (hits+misses)/own duration.
  These are not L2 bandwidth utilization. Do not invent bytes per request or
  use HBM bandwidth as the L2 reference.
- Single-batch retained L2 projected throughput: preserve its original formula
  and evidence class. Keep family samples separate. Without a verified L2
  denominator, use GB/s; an explicit user reference permits only a clearly
  labeled relative projection percentage.
- Compute: preserve the observed same-device SE-active-CU window mean, not
  achieved FLOP utilization or exclusive Process resource ownership.

Coverage diagnostics distinguish not sampled, unmatched, shape mismatch,
invalid counter/duration, short sampling window, gap, alignment failure and
missing reference. Retain valid zero, null and epsilon-display states separately.
No source value is filled merely to make the chart denser.

## 4. Global pile plan

Use every valid positive observed Process instance once. The type key is
`process_id` in Batch8 and `stage` in the retained single-batch adapter;
request, phase, layer, fragment and device stay on each member.

1. Sum all Process durations without deduplicating concurrent/nested intervals.
2. Select types whose own sum is strictly greater than 10% of that denominator.
   Do not force ten types or substitute a top-N selection.
3. Partition each selected type into five nonempty, duration-similar piles,
   using deterministic one-dimensional log-duration clustering and explicit
   tie handling. Keep each instance exactly once. The current adapter requires
   at least five instances per selected type; otherwise report unsupported
   grouping rather than duplicate records or invent empty measurements.
4. Rank all piles globally by their own duration sum descending; tie-break by
   type name and pile index. Do not rank each type independently on the page.

These sums are selection statistics, not E2E wall-clock attribution. Preserve
membership, per-pile totals, type shares, instance counts and stable original
ranks in `GROUPS.json` or an equivalent hash-bound sidecar. Keep the same plan
for both views. Empty selection is not permission to broaden the threshold.

## 5. High-latency page: Process distribution

`HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html` shows the selected Process
population regardless of resource availability. Every visible member is a
horizontal true-start/true-end line inside its pile's fitted trapezoid outline.
Straight outline sides enclose every member line; the outline only conveys
membership and never a continuous execution interval. Preserve source high-
latency flags as annotations; selecting a type does not reclassify its members.

All piles share one clock mapping. Never reset each pile to zero, use paired
independent begin/end axes, or stretch individual event widths to imply a
schedule. Full original Process evidence remains available separately.

## 6. Resource/concurrency page: associated windows only

`CONCURRENCY_UTILIZATION.html` answers where usable resource evidence exists.
It must not duplicate the E2E Process plot just to show the full request.

Default eligibility requires at least one valid, exactly associated non-compute
hardware metric. Within eligible windows show the observed compute mean as
context. Hide unassociated/null resource glyphs and globally empty piles;
retain original rank numbers and the unfiltered coverage denominator.

Each instance simultaneously shows the available metric types: compute,
separate DRAM read/write references, L2 hit rate and L2 request rate for Batch8;
compute and L2 projected throughput for the retained single-batch source.
Different colors, labels and patterns distinguish units and evidence classes.
No resource selector replaces simultaneous display.

Heights are continuous and proportional to numeric values using labeled,
consistent per-unit references, not four discrete bins. The current renderer
uses 24 px per 100% and 24 px per 15 Grequest/s; these are display scales, not
inferred hardware limits. Expand a display scale explicitly if required and
keep the original value. L2 GB/s has its own labeled scale. Zero has a baseline.

A short-window/too-few-samples null may have an epsilon presence marker only
when the containing window is otherwise eligible, or when missing records are
explicitly restored. Epsilon means non-measured/unresolved, not a tiny measured
percentage. Other missing records remain inspectable but do not fill the plot.
R08 attributes projected at an R07 interval do not become same-run observations.
L2 hit rate and request rate must never be labeled resource occupancy percent.

## 7. Common time, folding and omission

Partition the declared captured Process extent into ten contiguous equal
integer-nanosecond sections before folding/omission; sizes differ by at most
one ns. Show one section at a time, with common zoom/pan/jump across its rows.
Clip crossing events only for rendering; preserve source intervals. Resource
sections with no eligible windows can jump to the next available original
section. Keep original section numbers/bounds for comparison with the Process
view; do not synthesize missing steps or evenly spaced execution.

Absolute ns stay decimal strings; subtract origin with integer/BigInt before
converting safe relative offsets to browser numbers. A common piecewise-linear
fold may cap long endpoint intervals (the current cap starts at twice the
median member duration). Mark compression with `//` and expose endpoints,
real durations and weights. A linear mode restores duration proportionality.

Only the RESOURCE view defaults to skipping the complement of the union of
eligible intervals across all visible piles/devices. Never remove a period
where another visible track has valid data. Skipped spans have zero display
weight and a `»` boundary, with exact omission durations and endpoints retained.
The resulting map is nondecreasing; omitted spans intentionally have no unique
inverse. It does not prove GPU idle or immediate adjacency. Handle fully empty
windows without division by zero. Restore full records and omitted time on
explicit user selection. Do not apply the resource mask to the high-latency
Process population.

## 8. Delivery, checks and completeness

Keep full lossless evidence/Perfetto exports and the twelve source tables
separate from filtered analytical views. `complete_timeline=true` and the
formula `request + process + 2*kernel` describe the full archive, never the
visible resource subset. The two kernel organizations do not double GPU time.
A view manifest records its selection/filter/omission policy, actual displayed
coverage and full-source references. No fixed event budget or source sampling.

Validate source hashes and identities, exact type denominator, pile partition
and global order, trapezoid containment, common x coordinates, simultaneous
resource glyphs, continuous numeric height, valid zero/null/epsilon separation,
resource eligibility, omission-union safety, original section boundaries,
restoration controls, empty windows, 1 ns navigation and offline operation.
Check every required rank/request/device in the source scope, not as a forced
visible row in every resource window. Inspect screenshots for readability.

A missing metric can coexist with complete processing of the declared scope;
a false coverage claim, missing required capture, invalid source hash, changed
classification or filled null cannot. No new acquisition or publication is
implied by a rendering task. Formal scheduler completion still requires its
stage audit and handoff; a retained build/audit is not a substitute.
