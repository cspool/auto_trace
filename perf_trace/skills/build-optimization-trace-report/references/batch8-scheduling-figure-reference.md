# Batch8 Scheduling Figure Reference (v4)

Use this profile when explaining multi-device request scheduling with a trace.
It incorporates the revised long-span folds, large annotations on true time
axes, and increased vertical spacing. Use the existing
[A–D profile](current-figure-reference.md) for composition and kernel zooms.

The concrete reference is report revision v4, figure commit
`5452774f977be62d35f52a2b67435185d18bdee8`, with
[published PDF, HTML and ZIP][release]. The values below describe that render;
preserve the visual/measurement relationships when adapting to another trace,
rather than copying its request split, model shape or caps unconditionally.

## Pictures, source and verification

| Role | Pictures / report | Generator / evidence |
| --- | --- | --- |
| A: long client span and selected markers | [SVG][a-svg] · [PNG][a-png] | [Generator][fig-generator] · [A–D geometry audit][ad-audit] |
| S (report figure 2): per-device scheduling over time | [SVG][s-svg] · [PNG][s-png] | [Generator][s-generator] · [Spacing and sample audit][s-audit] |
| A–D composition/zoom context | [Combined SVG][combined] | [Raw analysis][analysis] |
| Actual design and OOM explanation | [Report][report] · [Design evidence][design] | [Design extractor][design-generator] |
| Delivered layout | [Full HTML screenshot][html-shot] · [Tall PDF page][pdf-shot] | [Browser/data audit][report-audit] · [PDF audit][pdf-audit] |

### A: fold the long background interval to enlarge the markers

![Folded client spans with readable selected prefill/decode markers][a-png]

- The gray client interval is capped at `260 display seconds`, drawn as two
  same-style blocks with a zigzag between offsets `225` and `238` from its
  start. Its full raw duration remains labeled on the right.
- Selected process-marker widths are `12 × raw duration`. Every marker's left
  edge retains its actual start; its duration appears inside and start above.
- The `32 × 14 in` panel uses `56.241 pt` main rectangle height. The x-axis
  explicitly distinguishes actual left edges from display-scaled right edges.
- The fold is one client interval. It does not denote idle time or two runs.
  Colored selected windows are not a measurement of the entire phase.

### S: preserve time and make adjacent B levels visibly separate

![Tall per-device scheduling time plots with separated batch-level bands][s-png]

Both device panels retain actual time on X and observed local sequence count
`B` at each dot on Y. The 16 launch samples illustrate execution; there is no
state interpolation. Each annotation's left edge aligns with the sample time.
Its fixed width is only room for text, not a launch duration.

| Property | v4 reference |
| --- | --- |
| Combined S canvas | `32 × 40 in` (previous time plot was `32 × 18 in`) |
| X interval / ticks | `[-4,239] s`; ticks `0,25,...,225 s`; raw starts unchanged |
| Y interval / ticks | `[0.5,4.5]`; ticks `B=1,2,3,4` |
| Physical distance between Y ticks | `290 pt`, about `3.18 ×` the previous `91.1 pt` |
| Annotation width | `43 display seconds`; right edge is not completion time |
| Annotation height | `h=0.36 B units` → `104.4 pt`, retaining the previous readable physical size |
| Gap from anchor to annotation | `g=0.06 B units` |
| Prefill / decode placement | Prefill above dot: `[B+g,B+g+h]`; decode below: `[B-g-h,B-g]` |
| Minimum adjacent-B band clearance | `(1−2(g+h))×290 = 46.4 pt` |
| Gap between above/below annotations at one B | `2g×290 = 34.8 pt` |
| Information text | Three horizontal lines: request/phase/B; raw time; kernel configuration/threads |

Preserve the time chart when enlarging information. An equal-width ordinal
card grid is not a replacement for this figure. Likewise, enlarging the canvas
while scaling rectangle heights by the same factor does not solve vertical
crowding: keep useful physical rectangle height and increase clear space
between B bands. Do not optimize colored area coverage at the cost of these
requirements.

Numeric duration labels inside A–D bars remain single-line under their profile.
The three-line S annotations are a distinct role. They do not acquire measured
durations or duration-based Top-K rankings from their display dimensions.

## HTML/PDF acceptance

The HTML embeds the SVG at readable width and permits normal vertical page
scrolling. Inspect the full figure as well as the viewport. The reference PDF
uses a `420 × 560 mm` page for S, with `12 mm` margins; the other pages retain
their original format. A named print page disables the global SVG height cap
for S so it does not shrink back to the earlier crowded size. A future report
may instead split devices across suitable pages while preserving the scale.

Reconcile every displayed sample with its exact request, rank, raw timestamp,
B and launch configuration. Audit all rectangle/text bounds, Y-tick physical
spacing, adjacent-B band clearance, and raw time anchors. Inspect the rendered
PNG/SVG, full HTML screenshot and actual PDF page; check exported page sizes
and text bounds. Ordinary two-dimensional non-overlap alone would miss the
crowding corrected by this reference.

## Explain the design that the pictures illustrate

Lead a scheduling report with the actual implemented routing and per-device
budgeting policy. In this example, official load-based DP routing is retained;
the source uses `4*waiting + running`, while length-based prefill budgets and
Graph/autotune protections control device working sets. Explain these from
source rather than presenting the illustration's fixed 4+4 as the algorithm.
These are this implementation's policies, not defaults to impose on future
reports.

When OOM is part of the requested explanation, connect failure location and
allocation to the corresponding protection and validation. This report's OOM
tables are historical repository evidence, while its fixed trace illustrates
the resulting execution. Follow the [report contract](report-contract.md) for
source availability and measurement distinctions.

[a-svg]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/figures/panel_a.svg
[a-png]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/figures/panel_a.png
[s-svg]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/figures/scheduling_local_batch.svg
[s-png]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/figures/scheduling_local_batch.png
[combined]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/figures/batch8_optimization_timeline.svg
[fig-generator]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/build_figures.py
[s-generator]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/analyze_scheduling.py
[ad-audit]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/FIGURE_AUDIT.json
[s-audit]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/SCHEDULING_FIGURE_AUDIT.json
[analysis]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/data/analysis.json
[design]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/data/scheduling_design.json
[design-generator]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/analyze_design.py
[report]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/REPORT.md
[html-shot]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/validation/report_scheduling_full.png
[pdf-shot]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/validation/pdf_page_05.png
[report-audit]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/REPORT_AUDIT.json
[pdf-audit]: ../../../../perf_trace_batch8/explanations/batch8_optimization_trace_20260909/PDF_AUDIT.json
[release]: https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-dp2-scheduling-report-20260909-v4
