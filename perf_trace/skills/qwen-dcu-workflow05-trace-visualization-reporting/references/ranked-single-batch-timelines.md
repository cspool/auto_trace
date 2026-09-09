# Ranked timelines for retained single-batch R10 reports

Use this mode for presentation revisions to an already accepted single-batch
trace. Keep the original tar archives unchanged and bundle them for recovery.
Do not require unavailable historical generator checkouts or rerun the model.
Declare `formal_r10_regeneration=false` and
`original_acceptance_untouched=true`; retain original lineage/table hashes.

The repository-local generator is:

```bash
python3 perf_trace/scripts/build_ranked_single_batch_timelines.py \
  --source-archive <same-lineage-r10-offline-acceptance.tar.gz> \
  --full-archive <same-lineage-r10-replay002-all-rectangle-labels.tar.gz> \
  --output-dir <new-NFS-output-directory>
```

It consumes retained page payloads and the complete replay002 trace. It must
verify matching request origin, exact category/interval counts and the complete
ordered interval universe across the two archives. The older offline archive's
small 256-event Perfetto candidate is not the complete trace. Preserve the
complete replay002 JSON bytes and its top-ten color semantics. This adapter is
for the retained single-request schema; reject incompatible input instead of
inventing fields. Formal fresh runs still require all twelve normalized tables.

## Visual requirements

- Derive device identity and concurrency from the input. The 20260806 example
  is physical DCU1, one Request, 29 forwards; it is not Batch8 and has no dual
  device trace. Kernel/queue interval counts are separate views of the same
  execution and are not additive.
- High latency: retain every accepted high-latency row and its classification.
  Group by phase + stage for navigation, ranking the sum of observed Process
  durations; do not invent a new p95 threshold or rank replay timings. Show
  exact-owned kernels, original SE points, and hardware rows joined by exact
  event + stage + retained attachment family. A missing match is unavailable.
- Concurrency: group by forward, rank by the busy union of observed owned
  kernels within the actual forward window, and show kernel count, queue count
  and raw SE points on the same linear clock. Also expose overlap duration and
  peak counts; do not infer speedup.
- Raw utilization: rank process groups by the longest window; retain every
  original point including alignment-ineligible points, and show no fabricated
  averages, connecting lines, interpolation, or zero filling. Unknown sampling
  intervals and host runtime launch gaps need distinct views and semantics.
  In this archive, sampling call endpoints are absent: adjacent point spacing
  describes lack of interior samples, not proven acquisition downtime.
- Each ranked category starts with at most 20 groups/items and exposes the
  complete ranking, arbitrary rank windows, every member, and searchable
  source tables. Full event payloads and the original complete trace stay
  intact. Grouping is optional where it would obscure evidence.
- Group trapezoids/ribbons connect every actual instance endpoint with one
  horizontal line per member. The outline means membership, not execution.
  Paired begin/end axes must be explicitly labeled: connector length is not
  duration. Offer an original single axis and reversible time folding with
  visible // marks, exact endpoints, real interval duration, and compression
  weight/ratio. Keep detailed kernel/count timelines on true linear time.
- Give rectangles and lanes enough height and spacing (detail lanes 76 px,
  rectangles around 30 px). A collapsed group overview may compact rows;
  expanded rows use 36 px and paginate large groups so browser Canvas height
  limits cannot silently remove instances. Avoid mostly empty figures.
- Before all timeline views disclose what was traced, absent evidence, and
  omitted time. If Request completion extends beyond all retained non-Request
  trace, clip only the displayed Request tail to the maximum retained end;
  retain original completion/source rows, report exact omitted ns and percent,
  and do not delete interior gaps. This example omits 6,113,817 ns, not the
  Batch8 example's long tail. Calculate these values from each input.
- Preserve integer timestamps: parse archive JSON in Python, stringify unsafe
  absolute integers, subtract origin with BigInt before any JS Number cast.
  Detail plots and full viewer provide exact integer-ns jumps, zoom, pan and
  uncapped pixel-overlap inspection. Preserve original full-view top-ten colors
  and all rectangle labels when there is room.

## Validation and example

Check source archive hashes and full-trace bytes; independently reproduce row
counts, ranking denominators, all group memberships, interval endpoints,
concurrency sweeps, hardware joins and clipped Request scope. Exercise browser
navigation beyond rank 20, group member selection, folded/unfolded mappings,
large-group row pagination, source search, and a 1 ns jump. Check offline links,
no external assets, no browser errors, and legible screenshots before publishing.

The maintained example, reproduction commands, browser audit, previews and
Release link live at `perf_trace/explanations/r10_ranked_timelines/README.md`.
Source assets are in `perf_trace/scripts/ranked_timeline_assets/`. Update the
source generator/assets rather than hand-editing generated HTML. Push code,
progress and audits; publish the offline bundle and verify remote asset hashes.
