# Optimization Trace Report Contract

## Core content

The report is organized around optimization evidence, not around a fixed set
of chapter titles. Each optimization needs one self-contained evidence unit:

| Content | Required answer | Primary evidence |
| --- | --- | --- |
| Trace result | Did the optimized path run, where, how often, and for how long? | Runtime trace and strict ownership |
| Result visualization | Where does it sit in the request and what share does it occupy? | Raw timestamps and durations |
| Process context | Which operator chain contains it and what consumes its output? | FX/process reconstruction plus runtime mapping |
| CTA view | How do tensor dimensions map to grid, CTA, threads, waves and outputs? | Kernel source/launch metadata and shapes |
| Conclusion | What is demonstrated, and what is not? | The evidence above and an optional comparable baseline |

The runtime result and its visualization are the core. Process and CTA content
must clarify the result rather than become unrelated architecture exposition.

## Measurement definitions

Use explicit names and denominators:

```text
owned_duration(unit, category)
    = sum(raw duration of strict-owned kernel instances in category)

unit_kernel_sum(unit)
    = sum(raw duration of all strict-owned kernels in the unit)

composition_share(unit, category)
    = owned_duration(unit, category) / unit_kernel_sum(unit)

wall_clock_span(unit)
    = max(observed end) - min(observed start)
```

An additive kernel-duration sum is not a wall-clock span when kernels overlap.
A composition share is not a speedup. Displayed rectangle area is never a
measurement denominator.

When a baseline exists, state its comparability: workload, model/configuration,
input/output lengths, batch/concurrency, hardware, build, precision and timing
definition. Otherwise write only the optimized trace composition and placement.

## Per-optimization evidence record

Capture this record before writing prose:

```text
optimization:
matcher:
trace units containing hits:
hit count:
owned duration sum:
unit denominator and share:
process range / operator chain:
input and output shapes:
grid / CTA / wave / thread mapping:
fallback or unmatched cases:
baseline result, if comparable:
evidence limitations:
```

Missing fields should be marked unavailable, not inferred silently.

## Process requirements

- Show only the chain needed to reach and leave the optimized operation.
- Preserve observed operator order, targets and shapes.
- Connect runtime kernel evidence to an FX/custom-op boundary explicitly.
- Treat reconstructed process labels as reconstruction labels, not automatic
  proof of runtime module ownership.
- Put the character art beside the corresponding result figure/explanation.
- Emphasize the optimized operation inside the character art.
- Avoid separate generic `是什么` and `为什么` passages unless requested.

## CTA requirements

For each number, state what it counts and on which axis. At minimum, close the
relationships that apply:

- tensor dimension to grid/CTA count;
- CTA to output row/head/token/tile ownership;
- threads to waves and lanes;
- elements per thread to the full reduction length;
- partial sums to final outputs;
- grouped-query heads to KV heads and query blocks;
- aligned tiles, residual tails and their merge.

If two values happen to be equal but represent different axes, name both. For
example, `2 Q heads x 32 query positions = 64 query/head rows` does not mean a
CTA owns a 64-token K/V tile; the CTA may scan successive 64-token K/V tiles
for those 64 query/head rows.

## Final audit

- Every claimed optimization has runtime hits or is explicitly reported as not
  observed.
- Kernel matchers and ownership rules are reproducible.
- All plotted lengths derive from raw timestamps/durations.
- Display scaling, caps and broken rectangles are disclosed.
- Top-K selection is local to each timeline/column and uses raw duration.
- Numeric labels carry values and within-unit proportions where useful.
- Process art emphasizes the exact optimized operation.
- CTA arithmetic closes without unexplained constants.
- Shape-specific and architecture-specific gates are not generalized.
- Optimized-only trace composition is not called speedup.
- Historical benchmark results are visually and verbally separated from the
  current trace.

## Example adaptation

The repository's single-batch example uses four panels: request overview,
prefill routes, decode composition and a layer zoom. It also illustrates two
different numeric closures: an output-row GEMV mapping and a grouped-query
attention mapping. These are examples of the contract, not required panel
names, scale factors, kernel families or model dimensions for another trace.
