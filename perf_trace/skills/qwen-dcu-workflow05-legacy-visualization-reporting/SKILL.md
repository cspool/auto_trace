---
name: qwen-dcu-workflow05-legacy-visualization-reporting
description: Execute legacy Workflow05 R10 from the R09 base-estimate and selective-capture analysis. Generate an offline report that visibly separates the estimated full-request overview from every independently observed capture, replay-projected hardware attributes, and unavailable evidence.
---

# Qwen DCU Legacy Workflow05 R10 Reporting

## Contract

Require `user.evidence_acquisition_mode=historical_then_selective` and the
hashed R09 analysis. R10 is presentation-only: do not run a model, GPU,
profiler, replay, sampler, or new analysis capture.

R10 may change only the maintained report generator, validator and offline
assets. Preserve the R09 input hashes and evidence classes.

## Views

Generate a self-contained offline directory containing:

```text
index.html
BASE_ESTIMATED_PROCESS_OVERVIEW.html
SELECTIVE_OBSERVED_CAPTURE_TIMELINES.html
HARDWARE_GAPS_AND_OPPORTUNITIES.html
offline_acceptance_manifest.json
```

The UI must label base estimates, each observed capture clock, replay-projected
hardware attributes and unavailable values with different tracks and legends.
Never draw independent captures on one absolute time axis. Provide filters,
search, zoom, provenance and hashes.

## Validation and Handoff

Require all pages to be self-contained, deterministic, internally linked and
free of external URLs. Verify embedded row counts and hashes against R09. Write
only the scheduler-assigned R10 handoff and derive evidence sufficiency from
R09 coverage rather than page existence.

