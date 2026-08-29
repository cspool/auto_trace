# Current Figure Reference Profile

Use the current single-batch A–D figure as the default visual baseline for an
optimization trace report. This profile defines readable physical geometry,
text hierarchy, axis semantics and required information. It does not make the
example's model dimensions, event counts, display multipliers or time caps
universal.

## Reference artifacts

- Combined figure:
  [`single_batch_optimization_timeline.svg`](../../../explanations/single_batch_optimization_timeline/single_batch_optimization_timeline.svg)
- Panels:
  [`A`](../../../explanations/single_batch_optimization_timeline/panel_a_request_overview.svg),
  [`B`](../../../explanations/single_batch_optimization_timeline/panel_b_prefill_routes.svg),
  [`C`](../../../explanations/single_batch_optimization_timeline/panel_c_decode_composition.svg),
  [`D`](../../../explanations/single_batch_optimization_timeline/panel_d_decode_layer_zoom.svg)
- Reusable generator:
  [`build_timeline.py`](../../../explanations/single_batch_optimization_timeline/build_timeline.py)

Inspect the SVG for geometry and text placement and the PNG at normal reading
size. Regenerate both formats from the same trace data; never hand-edit an
exported figure.

## Physical layout baseline

Treat these as default reference sizes for this report family:

| Item | Current reference | Requirement |
| --- | ---: | --- |
| Combined canvas | `32.0 x 67.5 in` | Preserve a comparably large reading surface when four panels are stacked. |
| Panel height ratios | `1.65 : 2.75 : 4.75 : 2.85` | Give the vertical-composition panel the most height; do not compress it to match horizontal timelines. |
| Inter-panel spacing | `hspace=0.86` | Reserve space for two-line axes, legends and panel-local explanations. |
| A/B/D main rectangle thickness | `56.241 pt` in the current render | Convert from each axis' data units so all three panels have the same physical thickness. |
| A strict-owned band thickness | `28.121 pt` | Use one half of the A/B/D main rectangle thickness. |
| C column width | `1.20` data units, about `187.8 pt` in the current render | Keep columns broad enough for horizontal Top-K text; preserve space between columns. |
| A lane spacing | `0.50` data units for `0.425`-unit rectangles | Leave a visible gap between the three display lanes. |
| B/D row spacing | `1.35` data units | Keep annotation text and adjacent rows separate. |
| C column spacing | `1.65` data units for `1.20`-unit columns | Keep folds and labels visually distinct. |

The current tight-cropped PNGs are approximately `6697x1869` (A),
`6391x2416` (B), `6393x3493` (C), `6810x2442` (D), and `6764x13642`
(combined) at `210 dpi`. Pixel dimensions are a regression clue, not a hard
cross-platform equality check.

Measure A/B/D thickness in physical points after axes are laid out. Assert that
their values agree; do not reuse one panel's data-unit height in another axis.
Assert that every rectangle boundary, including both folded blocks, lies
inside the corresponding tick interval.

## Display geometry baseline

The current example uses the following transforms:

| Panel | Direction | Current example transform |
| --- | --- | --- |
| A | horizontal | `min(3 x actual duration, 1.80 s)` with actual start |
| B | horizontal | `min(3 x actual duration, 260 ms)` accumulated within each row |
| C | vertical | `min(9 x actual duration, 10 ms)` accumulated within each column |
| D | horizontal | `min(6 x actual duration, 360 us)` with actual layer-relative start |

For another trace, choose scale and cap from its smallest meaningful event and
available panel extent. Preserve the behavior: scale all events in one panel
proportionally, replace capped spans with two same-style blocks joined by a
visible zigzag, and keep all arithmetic on raw durations. A folded rectangle
is one event, not two executions or idle time.

## Typography and stroke baseline

Use DejaVu Sans or an equivalently legible sans-serif. The current hierarchy is:

| Text or stroke | Current size/style |
| --- | --- |
| Figure title | `25 pt`, bold |
| Panel titles | `22 pt`, bold |
| Axis labels | `20 pt`, semibold |
| A tick labels | `18 pt` |
| B/C/D tick labels | `24 pt` |
| Legends | `20 pt` |
| A rectangle Top-K percentages | `26 pt`, normal |
| B rectangle Top-K percentages | `26 pt`, normal; `18 pt` only for a narrow block |
| C rectangle Top-K duration | `24 pt` |
| A forward ID and A/B/D boundary coordinates | about `15.3 pt` (`23 x 2/3`) |
| C boundary coordinates | `21 pt` (`31.5 x 2/3`) |
| B/C/D auxiliary annotations | `18 pt` |
| A bottom explanation | `20 pt`, equal to the axis-label size |
| Figure metadata / evidence footer | `14.5 pt` / `11.5 pt` |
| Axis spine / major tick | `2.2 pt` / `2.0 pt`, tick length `8 pt` |
| Major grid | `1.15 pt`, light gray |

Keep rectangle text horizontal and single-line. Do not wrap, rotate, enlarge or
bold it merely to force a fit. Hide a label when its rendered bounding box does
not fit the appropriate visible block; retain the rectangle and explain the
omission. Put D's kernel name/rank/duration outside the rectangle with a leader
line and leave the rectangle interior empty. Boundary coordinates label only
the three largest raw-duration rectangles per semantic unit unless requested
otherwise.

Axis identifiers may use short vertically stacked lines to save width. In A,
stack the category labels (for example `Strict / GPU / kernels` and
`Forward / envelopes / 3 display lanes / not concurrent`) while keeping them
aligned with their actual lanes. Do not rotate or stack numeric tick values in
a way that obscures their scale.

## Axis contract

Every panel must state, on the figure itself:

1. the x-axis quantity and unit;
2. the y-axis quantity and unit, or that it is categorical;
3. whether each rectangle edge is an actual coordinate or a display-scaled
   boundary;
4. the exact scale/cap formula when display geometry differs from measurement;
5. the meaning of a fold and any grouping or averaging.

The rectangle edges and numeric ticks must use one coherent coordinate system.
For actual-start panels, the left edge falls in the tick interval containing
its actual start and the right edge equals `start + display_length`. For
cumulative panels, the next edge equals the previous edge plus
`display_length`. Never label a display boundary as an actual completion time.

Place longer display-contract explanations below the plot, not over a data
lane. Use the axis-label font size. Reserve enough inter-panel spacing that the
explanation does not overlap the next title or legend.

## Required panel information

Panel names may change, but preserve the following information roles when the
trace contains them:

### Request overview

- observed phase spans and their boundaries;
- one rectangle per forward/envelope, with phase color;
- forward/chunk or decode-step ID at the upper-right corner;
- strict-owned GPU work in a separate lower track;
- Top-5 raw-duration labels independently per display lane and Top-3 actual
  start coordinates;
- an explicit statement when multiple lanes are round-robin layout rather
  than concurrency;
- a bottom explanation covering scale/cap, ID meaning, hidden labels and the
  observed request span/evidence boundary.

### One-time or prefill composition

- one row per observed forward/chunk;
- kernel-category legend and strict-owned composition;
- Top-5 raw-duration share per row and Top-3 cumulative display boundaries;
- actual kernel-duration sum and selected route/fallback beside each row;
- categorical row IDs and the cumulative display-axis formula.

### Repeated-step or decode composition

- individual steps or disclosed groups of near-identical adjacent steps;
- group membership and the statistic used, such as arithmetic mean;
- kernel-category legend;
- Top-5 actual mean durations per column with sufficient precision to expose
  small differences, and Top-3 cumulative display boundaries;
- actual trace aggregate/share callouts;
- external benchmark numbers only in a visibly separate annotation labeled as
  separate evidence.

### Representative process/layer zoom

- one observed, identified forward/step and layer/process range;
- strict-owned kernel categories in observed launch order;
- actual start coordinates with display-scaled widths;
- kernel name/category, local rank and actual duration outside rectangles;
- one declared time unit for title, axes and annotations;
- kernel-duration sum and enclosing annotation envelope;
- a warning that gaps are not automatically production idle time.

## Render audit

After generation:

1. run syntax/data assertions and print the measured A/B/D rectangle height;
2. inspect A–D PNG/SVG separately for clipped text, invisible folds and axis
   mismatch;
3. inspect the combined image for explanation/title/legend overlap;
4. verify Top-K is selected from raw duration independently per unit;
5. verify hidden labels are omissions for fit only, not missing events;
6. verify every claimed measurement is readable without consulting source
   code, while detailed process and CTA explanations remain in the report.
