---
name: build-optimization-trace-report
description: Build an evidence-bound optimization report from runtime traces such as Perfetto/Chrome JSON, Nsight/CUPTI exports, normalized process/kernel tables, and optional FX reconstructions. Use when the user wants to show where an optimization actually appears in a trace, visualize its measured duration or share, place it in the surrounding process/operator chain, and explain its CTA/thread/wave/tensor-size arithmetic without confusing display scaling, attribution, or benchmark speedup.
---

# Build Optimization Trace Report

## Objective

Turn an accepted runtime trace into a compact report centered on one question:
**what result does each optimization produce in this trace, and where is that
result visible?** Add process and CTA detail only to make that result
understandable. Do not lead with generic `what/why` prose.

When the requested subject is scheduling design, lead with the implemented
request-routing and per-device scheduling policy, then use the trace to
illustrate its execution. A fixed trace is a valid illustration; its request
split is not the scheduling algorithm or a guarantee for future workloads.

Read [references/report-contract.md](references/report-contract.md) before
writing the report. Read
[references/visualization-and-cta.md](references/visualization-and-cta.md) when
the report contains timeline rectangles, folded shapes, numeric labels,
process character art, or CTA arithmetic. Read
[references/current-figure-reference.md](references/current-figure-reference.md)
before creating or revising timeline figures; it selects the applicable visual
baseline. For multi-device scheduling timelines, also read
[references/batch8-scheduling-figure-reference.md](references/batch8-scheduling-figure-reference.md),
which links the revised folded overview and tall time plots. Preserve the
user's requested time axes and spacing when adapting either reference.

## Evidence Inputs

Require one accepted runtime trace or normalized tables derived from it. Record:

- request count, phase/forward/step count, clock unit, trace mode, dtype and
  parallelism when present;
- exact event fields used to identify each optimization;
- the hierarchy connecting request, phase, forward/step, layer, process,
  runtime launch and kernel;
- whether kernel ownership is explicit, correlation-based, or only inferred.

Use optional evidence only for its proper role:

- FX/process reconstruction gives the surrounding fixed-input operator chain;
- kernel source and launch metadata support CTA/thread/wave arithmetic;
- a separately measured, comparable baseline supports speedup claims.

Never turn an optimized-only trace into a before/after comparison. Never infer
kernel internals from a name when source or launch evidence is absent.

## Workflow

### 1. Define the optimization matcher

For every claimed optimization, write an auditable matcher using the strongest
available fields: exact kernel symbol or family, process range, phase, shape,
dtype, architecture and launch configuration. Keep fallback kernels separate.
Report both hit count and the execution units containing the hits.

### 2. Reconstruct strict trace ownership

Prefer explicit parent IDs or normalized exact ownership. For Nsight/CUPTI
data, attribute a kernel only through the runtime launch correlation ID, not
by GPU-time overlap. Keep nested totals separate.

If the task requires creating or reviewing sampled latency attribution and the
skill is available, use `$visipruner-sampled-latency-attribution`. If the input
is a Workflow05 fresh acceptance or retained analytical-view task, use
`$qwen-dcu-workflow05-trace-visualization-reporting` to generate/validate that
bundle under its correct execution mode; this report skill consumes that
evidence and does not start fresh acquisition or replace the R10 handoff.

### 3. Compute the observed result

For each optimization and relevant unit, compute from raw durations:

- hit count and placement;
- strict-owned duration sum;
- share of the unit's real kernel-duration sum;
- distribution across phase, forward/step or layer;
- baseline delta only when a comparable baseline is explicitly available.

State whether a number is wall-clock span, additive kernel-duration sum,
composition share, latency delta or throughput delta. Do not subtract or add
unlike quantities.

### 4. Visualize the result

First select the figure's job. For Workflow05 Process distribution or resource
availability, read the
[shared analytical-view contract](../qwen-dcu-workflow05-trace-visualization-reporting/references/process-resource-contract.md).
Use trapezoid member-line groups for high latency and simultaneously displayed,
proportionally sized resource glyphs on eligible hardware windows for the
resource view. Retain the complete source denominator separately. Do not apply
composition-panel Top-K labels, per-event width stretching, or a full-request
resource display mandate to that profile.

The following composition/optimization examples apply when that is the user's
question, rather than the analytical-view profile:

Split figures by question instead of forcing all information into one panel.
A useful, non-mandatory layout is:

- request/phase overview;
- prefill or one-time optimization composition;
- decode or repeated-step optimization composition;
- one representative layer/process zoom showing the optimized kernels in
  execution order.

For scheduling, add per-device time plots with exact launch-time anchors and
readable information rectangles. Enlarging those rectangles must not replace
the time axis with an equally spaced card grid. Keep separate batch-level
bands visibly apart by increasing plot height while preserving readable
physical rectangle sizes; the references give the geometry and export rules.

Place each figure next to its own explanation. Preserve actual timestamps and
durations as data. If short rectangles are enlarged, treat that geometry as a
display transform and label it. Use a broken two-block rectangle for capped
long events. Label the top `K=5` rectangles independently within every
timeline or vertical column unless the user specifies another `K`.

Match the physical readability baseline in
[references/current-figure-reference.md](references/current-figure-reference.md),
not merely its data-coordinate constants. Keep axes, titles, legends,
annotations and rectangle labels at their declared hierarchy. Every axis must
name its quantity, unit and coordinate transform; every complete rectangle,
including both blocks of a folded rectangle, must remain inside the displayed
axis interval. Distinguish measured-duration rectangles from fixed-size sample
annotations. After rendering, inspect individual panels, the combined image,
and the actual HTML/PDF at normal reading size. PDF sizing must preserve an
intentionally taller plot rather than silently shrinking it back down.

The existing example
`perf_trace/explanations/single_batch_optimization_timeline/build_timeline.py`
shows Perfetto streaming, event classification, scaled/folded rectangles and
per-line Top-K labels. Inspect and adapt its mechanisms; do not reuse its
hard-coded trace path, kernel matchers, panel scales or accepted-shape checks.

### 5. Locate the optimization in its process

Show the shortest operator chain that connects the process input to the
optimized operation and its consumer. Use observed FX targets and shapes when
available. Keep opaque custom ops opaque; runtime kernels may establish what
ran below that boundary, but do not invent hidden FX nodes.

Draw process character art manually. Emphasize the optimized operation inside
the diagram with `<strong>...</strong>` in an HTML `<pre>` block, or with a
clearly documented color when the output format supports it. If available,
use `$visipruner-fx-process-visualization` for evidence and tensor-axis drawing
rules, while following this report's requested concise format: omit generic
`是什么/为什么` subsections and explain only the observed chain and computation.

### 6. Close the CTA and numeric logic

Explain, at the optimization's location, how model/tensor dimensions determine
the launch and how one CTA produces its output. Every number must name its
axis or role. Write the arithmetic that closes the mapping, for example:

```text
CTA count = output rows / output rows per CTA
elements per row = threads x elements per thread
threads = waves x lanes per wave
covered Q heads = CTAs per KV head x Q heads per CTA
```

Distinguish equal-valued quantities on different axes, such as 64 query/head
rows versus a 64-token K/V tile. Do not say only that threads “reduce” or a CTA
“processes the shape”; identify the partial sums, grouping, final outputs and
scan/reduction axis.

### 7. Audit and deliver

Check the report against the checklist in
[references/report-contract.md](references/report-contract.md). Regenerate
figures from source data rather than editing generated SVG/PNG by hand. Link
the trace, process evidence, generator and output figures with relative paths
when they will move together.

For design reports, verify the implemented policy against source and distinguish
retained behavior, new changes, and unimplemented ideas. If OOM handling is in
scope, include the observed failure stage/allocation, mitigation and validation,
with historical evidence identified separately from the illustrative trace.

## Output Style

Keep the explanation concise and local:

1. observed optimization result and figure;
2. process/operator chain and emphasized character art;
3. CTA execution and numeric relationships;
4. evidence-limited conclusion.

Use a concrete example only after stating the general relationship. A trace,
model shape or architecture from one report is an example, never a default for
future traces.
