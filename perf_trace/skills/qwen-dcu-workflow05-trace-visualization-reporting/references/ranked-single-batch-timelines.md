# Retained single-batch source adapter

Use this reference only to identify and restore the accepted single-request
source schema. The maintained visual method is the
[shared Process/resource contract](process-resource-contract.md), used by both
single-batch and Batch8 views. Historical top-20/paired-axis pages are retained
source packages, not the current output layout.

The sealed 20260806 example includes one request, 29 forwards, 17168 Process
records and exact-owned HIP runtime/kernel intervals. Its original high-latency
classification contains one Process type; that classification does not restrict
the new type-duration display selection. Preserve the original labels and full
source archive while deriving a separate view plan.

The intermediate adapter `perf_trace/scripts/build_ranked_single_batch_timelines.py`
can reconstruct the accepted source-page format from the matching original R10
and complete replay002 archives. It verifies the same request origin and full
ordered event universe, keeps the complete Perfetto bytes and source identities,
and must not be treated as a new measurement or new formal R09/R10 run.

For the current views, prepare `single_batch/site/` under a local report root,
then run `build_process_duration_piles.py` and `audit_process_duration_piles.py`
with `--trace single_batch`. See the
[tool guide](../../../scripts/process_pile_assets/README.md) for complete inputs
and commands. The default resource view uses only exactly associated L2 samples,
not every Process or a copy of Batch8 hardware results. Missing DRAM counters
and a missing L2 reference remain missing; epsilon never becomes measured data.
