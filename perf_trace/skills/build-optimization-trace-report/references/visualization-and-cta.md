# Visualization and CTA Rules

## Separate measured coordinates from display coordinates

Keep two representations:

```text
actual_start    = trace timestamp
actual_duration = trace duration
display_length  = min(actual_duration x scale, display_limit)
```

Use actual values for labels, totals, ratios and placement claims. A transformed
display axis must say that it is a display scale. Ordinary time ticks may
locate unmodified start-time anchors; enlarged or capped right edges must be
identified as display boundaries. Do not label a cumulative transformed axis
or a capped endpoint as actual elapsed/completion time.

## Minimum rectangles and folds

Choose one declared scale per semantic event role and orientation so the
smallest meaningful event is readable. Use the same rule across comparable
events. A long client envelope and short selected process markers may use
different rules if both are stated on the figure. When a scaled rectangle
exceeds the display limit:

1. draw two blocks with the same style;
2. join them with a zigzag/break mark;
3. retain the raw duration in its label or tooltip;
4. exclude the gap and displayed area from all arithmetic.

A fold means “longer than the visible cap,” not “idle time” or two executions.

When a long background/client interval crowds short markers, cap and fold that
interval, then allocate the recovered width to the markers. Keep original
starts and raw durations. Make the break visible and place it away from
selected markers where possible; retain the full interval's duration label.

## Scheduling time plots and information rectangles

Keep the requested time axis. Do not replace a time plot with equal-width
ordinal cards merely to make information larger. Retain numeric time ticks,
the actual spacing between observed starts, and a separate plot per device
when this makes the scheduling path readable.

For an instantaneous launch sample, draw an exact `(time, local batch)` anchor
and attach a large information rectangle. Its left edge may align to the
actual timestamp; use a dot/leader to identify the measured batch coordinate.
State that its width/height are annotation sizes, not execution duration or a
range of batch values. Such callouts need no invented duration or duration
Top-K ranking: preserve every selected sample and its ID in the data.

Place the request, phase, local B, raw timestamp and kernel configuration in
the rectangles, with horizontal text on a few separate lines. Increase the
annotation area and canvas until the main information is readable. A colored
area percentage is not an acceptance target and must not displace time
semantics or required spacing. Do not interpolate unobserved scheduler state
between discrete samples.

## Vertical spacing and export

For plots with above/below callouts around each batch level, give adjacent B
levels separate vertical bands. Rectangles at different horizontal positions
can still look crowded if their vertical bands overlap. Check both ordinary
rectangle intersection and separation along Y between different B levels.

Measure geometry in physical points after axes layout. Increase the canvas
height and tick spacing while keeping the information rectangles at a readable
physical height; stretching every rectangle with the axis preserves the
crowding. With uniform tick spacing and symmetric callouts:

```text
H = axis height in points / displayed Y range
h = rectangle height in Y units
g = anchor-to-rectangle gap in Y units
physical rectangle height = h * H
adjacent-level clearance = (1 - 2 * (g + h)) * H
```

Choose positive, visibly useful clearance and verify actual text bounding
boxes. The [Batch8 v4 profile](batch8-scheduling-figure-reference.md) supplies
one measured example; recompute geometry for a different layout.

Inspect the complete tall figure in the actual browser, not only the visible
viewport, and inspect its PDF page. A global CSS `max-height` or fit-to-page
rule must not undo the increased spacing or shrink all labels. Use a suitable
tall PDF page or separate device panels across pages while preserving readable
scale. Record the actual exported page dimensions and check text/page bounds.

## Numeric labels

Rank independently inside each semantic unit:

- each horizontal timeline;
- each stacked horizontal bar;
- each vertical column;
- each kernel-category lane in a zoom panel.

Default to the five largest raw-duration rectangles per unit. If fewer than
five exist, label all. Do not select five globally and leave other units
unexplained.

A compact label should expose the actual value and, when useful, its share of
that unit's actual-duration sum:

```text
12.4 ms | 31.8%
```

For narrow vertical bars, rotate or move the label with a leader line. Text may
overflow the rectangle only into a reserved annotation area, never into an
unrelated bar. Labels and ratios remain based on raw durations after scaling.

## Process character art

Use observed tensor axes and a short dependency chain, not a collection of
unconnected operator boxes. In Markdown, use an HTML `<pre>` block so the
optimized portion can be emphasized with `<strong>`:

```html
<pre>
Tensor: H, shape=[Q, K]
Formula: H = normalized process input
         +--------------------------+
token 0  |       INPUT_ROWS         |
         +--------------------------+
                    |
                    | <strong>OPTIMIZED_KERNEL: Y = H @ W.T</strong>
                    v
Tensor: Y, shape=[Q, M]
         +--------------------------+
token 0  |       OUTPUT_ROWS        |
         +--------------------------+
</pre>
```

Keep ASCII labels inside boxes if mixed-width characters would break borders.
Mark exact axis endpoints. If widths are compressed, state that outside or
above the box. Emphasis identifies the optimized computation, not the entire
process.

## CTA explanation pattern

Explain one CTA from input through output, then scale it to the grid:

```text
1. CTA ownership: output rows/heads/query block/tile handled by one CTA.
2. Per-thread work: element indices and local products or updates.
3. Intra-wave combine: lanes and partial-sum grouping.
4. Inter-wave combine: wave totals and final output(s).
5. Grid closure: CTA result x CTA count = complete output region.
```

Close every number with an equation. Two common patterns are:

```text
row projection:
  blocks per row = K / vector_width
  blocks covered = sum(blocks handled by each thread)
  CTA count = M / rows_per_CTA

grouped-query attention:
  Q heads per KV head = Q_heads / KV_heads
  covered Q heads = CTAs per KV head x Q_heads per CTA
  query/head rows per CTA = Q_heads per CTA x query positions per block
  K/V tile tokens are a separate scan axis
```

For reductions, specify whether paired threads first combine partial sums and
how many waves then reduce them. For attention, say whether the CTA owns query
rows and scans K/V tiles, or owns the K/V tile itself; do not conflate the two.

## Reusing the example generator

The repository script
`perf_trace/explanations/single_batch_optimization_timeline/build_timeline.py`
contains reusable implementation patterns:

- streaming Chrome/Perfetto JSON with `ijson`;
- strict event-category filtering;
- kernel-family classification;
- scaled rectangles with two-block folds;
- per-unit duration aggregation and Top-K labels;
- separate panel PNG/SVG export.

Before adapting it, replace all trace-specific constants:

- input path and hierarchy assertions;
- kernel-name and process matchers;
- phase/forward/layer selections;
- categories, colors, panel scale and display limits;
- model dimensions and explanatory annotations.

Keep generated outputs deterministic. Prefer SVG for inspection and PNG for
inline reading. Regenerate both from the same raw data after any rule change.
