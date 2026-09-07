# R07 attempt-043 offline recovery

This control bundle records the CPU-only recovery of
`batch8-dp2-fresh-003-R07-attempt-043` from the published open-writer
`capture.db` snapshot.

## Result

- Source DB SHA-256:
  `0ea77cdac40926182c4e04fc29e687e62df9b2cac50296c7e399817c583690b0`
- Source DB remained byte-exact and passed SQLite `quick_check`.
- Two `HIPTXOPS` tables were rebuilt with 234,444 and 234,832 rows.
- `TRACE_COUNTER` was rebuilt with 25 rows.
- Prepared DB SHA-256:
  `14a1e21b4bf5a0b29b11a62c4d000cac4979aa5af4ddc687f614bdab4f3179cd`
- Exact HIPProf binary SHA-256:
  `53f67d3dd4c1fe5aa9850f58d174ecf9f2c688f1e07519b456b19ca699c57f22`
- HIPProf reached `68323944/68323944`, emitted `HIP_PROF:finish`, and
  emitted no `ERROR`.
- The export contains 139 nonempty contiguous PFTrace members totaling
  14,961,678,057 bytes.
- Normalization produced 12,544 process ranges, 316,802 owned HIP runtime
  calls, and 23,660 strict-owned kernels on ranks/devices 0 and 1.
- Live-utilization alignment preserved 2,491,806 samples and 800 gaps without
  interpolation, resampling, imputation, or zero fill.
- The dependency adapter contains 32,492 edges for all 12,544 process targets.

## Evidence boundary

The remote original HIPProf process was still active when this bundle was
sealed. It is monitored without signals, debugger attachment, device queries,
or active-DB reads. Therefore this bundle claims
`complete_recovered_offline`, not natural completion of the original HIPProf
controller or its native durable-NFS lifecycle.

`R07.recovered.json` authorizes R08 only when the successor explicitly admits
the recovery boundary. It must not be represented as proof that the orphaned
remote HIPProf process exited naturally.

## Data locations

The source DB remains available from GitHub release tag
`perf-trace-batch8-r07-attempt043-open-writer-db-20260904`.

The consumer bundle is stored outside Git under the shared NFS recovery root:

```text
/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/runtime_nfs_bulk/
  qwen_dcu_perf_trace_batch8_attempt043_offline_recovery_20260906/
```

Extract the consumer bundle at
`/public/home/tangyu408/Qwen_DCU_Worker_0`; it contains only the recovered R07
trace, alignment, dependency, validation, recovery-control, and handoff
surfaces. It does not overwrite R01-R06.

## Included control files

- `prepare_attempt043_offline_db.py`
- `build_attempt043_recovery_contracts.py`
- `normalize_r07_process_trace_recovery.py`
- `audit_r07_capture_recovery.py`
- `finalize_attempt043_recovered_r07.py`
- `prepared_db_manifest_pristine.json`
- `RECOVERY_STATUS.json`
- `RECOVERY_INDEPENDENT_AUDITS.json`
- `R07_RECOVERY_SOURCE_LINEAGE.json`
- `R07_RECOVERY_COMPLETION_AUDIT.json`
- `R07_RECOVERY_ARTIFACT_MANIFEST.json`
- `R07.recovered.json`
- `SHA256SUMS`

## GitHub Release

- Tag: `perf-trace-batch8-r07-attempt043-offline-recovery-20260907`
- URL: https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r07-attempt043-offline-recovery-20260907
- Consumer bundle: `r07-attempt043-recovery-consumer-bundle.tar.gz`
