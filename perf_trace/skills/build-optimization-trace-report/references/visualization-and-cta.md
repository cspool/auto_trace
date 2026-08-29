# Visualization and CTA Rules

## Separate measured coordinates from display coordinates

Keep two representations:

```text
actual_start    = trace timestamp
actual_duration = trace duration
display_length  = min(actual_duration x scale, display_limit)
```

Use actual values for labels, totals, ratios and placement claims. A transformed
display axis must say that it is a display scale. Do not print ordinary numeric
ticks that invite readers to treat a capped or folded coordinate as physical
time. If a panel preserves actual start positions but enlarges only widths,
say so explicitly.

## Minimum rectangles and folds

Choose one declared scale per panel/orientation so the smallest meaningful
event is readable. Scale other rectangles in that panel proportionally. When a
scaled rectangle exceeds the display limit:

1. draw two blocks with the same style;
2. join them with a zigzag/break mark;
3. retain the raw duration in its label or tooltip;
4. exclude the gap and displayed area from all arithmetic.

A fold means “longer than the visible cap,” not “idle time” or two executions.

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
