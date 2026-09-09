# Process duration piles and resource windows

These tools revise retained single-batch and Batch8 trace presentations. They
never run a model, profiler or new GPU acquisition. Original release inputs and
source classification flags remain unchanged.

## Inputs and reproduction

Prepare a local report root with the previously downloaded release bundles:

- `single_batch/site/`: `perf-trace-r10-ranked-timelines-20260909-v1`.
- `batch8/site/acceptance/`: `perf-trace-batch8-r10-ranked-timelines-20260909-v1`.
- `hardware_docs/HARDWARE_REFERENCE.json`: a documented empirical bandwidth
  reference. The accompanying `hardware_reference.example.json` records the
  reference used in this analysis; it is not a manufacturer specification.

From the repository root, replace `/path/to/local_reports` with that directory:

```bash
python3 perf_trace/scripts/restore_batch8_bandwidth_sources.py \
  --root /path/to/local_reports --repo .
python3 perf_trace/scripts/calculate_batch8_replay_bandwidth.py \
  --root /path/to/local_reports
python3 perf_trace/scripts/audit_batch8_replay_bandwidth.py \
  --root /path/to/local_reports
python3 perf_trace/scripts/calculate_batch8_l2_activity.py \
  --root /path/to/local_reports
python3 perf_trace/scripts/build_process_duration_piles.py \
  --root /path/to/local_reports
python3 perf_trace/scripts/audit_process_duration_piles.py \
  --root /path/to/local_reports
```

For Batch8-only input, keep the restore/calculation commands and explicitly
use `--trace batch8` for both build and browser audit. The defaults require
both accepted report packages. The restore script is bound to the published
`perf-trace-batch8-r08-complete-20260908` manifest; it is not a generic archive
restorer. Missing parts are downloaded to `batch8_bandwidth/downloads/`, and
only the required normalized members are restored. A different archive needs
an explicitly validated adapter. The current rendering adapter also reports
unsupported input when no type exceeds the threshold; it must not broaden it.

Restore requires `curl` and Python `zstandard`; browser checks require Python
Playwright with Chromium. Other calculation/build dependencies are in the Python
standard library. `--trace single_batch` or `--trace batch8` limits builds and
browser audits. `--refresh-assets` reuses a current normalized payload after
checking original input hashes, allowing presentation-only rebuilds.

Outputs are `revised/{single_batch,batch8}/`, `batch8_bandwidth/` and
`single_batch_bandwidth/` under the report root. Open each generated `index.html`
offline. Keep the report root structure for relative links to original evidence.

## Selection, grouping and geometry

Select only Process types whose summed instance durations strictly exceed 10%
of the sum of all Process durations, including overlaps. There is no fixed
number of types. Cluster each type into five nonempty contiguous duration piles
using deterministic one-dimensional log-duration clustering. Rank all piles
by their own duration sums, descending; break ties by type name and pile index.

The original time extent is split into ten contiguous integer-nanosecond
sections. One section is visible at a time. All visible tracks share one clock,
with global zoom/pan and exact-ns navigation. Common folding compresses long
endpoint intervals and exposes their original endpoints and compression ratios.

High-latency views retain the captured Process distribution. Each pile contains
all visible member intervals as horizontal lines inside a fitted trapezoid
outline. The outline indicates membership, not continuous execution.

Resource views default to successfully associated hardware windows: an instance
must have a valid non-compute hardware metric. Unassociated resources and empty
piles are hidden, without renumbering the original ranks. The union of eligible
intervals is formed across all visible tracks/devices; only its complement is
omitted. A skipped span has zero display weight and a `»` boundary marker. This
is not GPU-idle evidence. Omitted spans have no unique inverse; exact endpoints
remain available, and full records/time intervals can be restored explicitly.
Empty resource sections jump to an available section.

## Resource semantics

Batch8 instances simultaneously display compute activity, directional DRAM
read/write replay references, L2 hit rate and L2 request rate. Single-batch
instances show the available compute and L2 projected-throughput metrics.
Heights vary continuously with the values using labeled per-unit scales.
Zero is a baseline. Short-window or insufficient-sample nulls may display an
explicitly non-measured epsilon marker; their source values remain null.

- Compute is the original same-device SE-active-CU window mean, not achieved
  FLOP utilization or exclusive attribution to the Process.
- DRAM bandwidth uses bytes and EndNs-minus-BeginNs from the same native PMC
  record, divided by the documented reference in the sealed reference file (the bundled
  example uses an empirical 1206 GB/s). Read
  and write remain separate replays. Process summaries use unique selected
  dispatch byte sums divided by their own replay-duration sums. Missing
  counters, invalid duration or shape mismatch prevent projection onto R07.
  These values are not observed R07 live bandwidth; values above 100% are kept.
- Batch8 L2 activity uses hit/(hit+miss) and (hit+miss)/same-replay-duration.
  Neither metric is L2 bandwidth utilization. No request byte size or L2 peak
  is assumed.
- Single-batch L2 throughput preserves the original replay-to-R07 projection.
  Family samples remain separately selectable. Without a verified L2 reference,
  the default unit is GB/s. An explicitly user-entered reference can produce a
  labeled relative projection percentage, never an asserted measurement.

Coverage reports retain the complete selected-instance denominator, including
missing records. They distinguish sampling resolution, gaps, missing captures,
shape mismatch and invalid counters. Scheduling `candidate` status is not used
as a sampling failure reason.

## Validation

The bandwidth audit independently recomputes native byte formulas, timestamp
identity, directional rates and shape gates. L2 calculations compare hit, miss
and hit-rate values against accepted R10 metrics. Browser checks verify source
hashes, rankings, memberships, all ten sections, common x positions, trapezoid
containment, proportional heights, epsilon semantics, default resource omission,
restoration controls and offline operation. Recorded results are under
`perf_trace/explanations/process_duration_piles/validation/`.
