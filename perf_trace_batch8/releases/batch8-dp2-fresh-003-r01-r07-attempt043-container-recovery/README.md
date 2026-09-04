# Batch8 DP2 `batch8-dp2-fresh-003` container-loss recovery

This note records the output-only recovery entry points for R01-R06 and the
live R07 attempt
`batch8-dp2-fresh-003-R07-attempt-043`. It does not archive source trees,
model files, replaceable AOT copies, or a second copy of the expanded 43 GB
predecessor surface.

The paths below are on the cluster NFS mount
`scnet.hx:/mnt/public/home/tangyu408`, mounted at
`/public/home/tangyu408`. Paths below `/workspace`, `/dev/shm`, and `/` are
worker/container-local and must be reconstructed after container loss.

## Recovery priority

1. If the original container is still alive, do not signal, stop, or restart
   HIPProf. Let attempt-043 finish naturally.
2. After container loss, prefer a completed, closed R07 checkpoint in the
   formal durable root when its completion marker exists and its recorded hash
   matches.
3. If no formal checkpoint exists, use the open-writer NFS snapshot only for
   salvage or an attempted offline `hipprof --db` export. It cannot resume the
   capture.
4. Reconstruct R01-R06 from their public, hash-pinned release parts and the
   NFS control/hash bundle.

## NFS entry points and top-level seals

```text
R01-R06 bundle:
/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/runtime_nfs_bulk/
  qwen_dcu_perf_trace_batch8_container_loss_insurance_20260903/
  workflow01-10-fresh-e2e/batch8-dp2-fresh-003/R01-R06/
  output_recovery_index_001

R07 open-writer snapshot:
/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/runtime_nfs_bulk/
  qwen_dcu_perf_trace_batch8_container_loss_insurance_20260903/
  workflow01-10-fresh-e2e/batch8-dp2-fresh-003/R07/
  batch8-dp2-fresh-003-R07-attempt-043/open_writer_snapshot_001

R07 formal durable root (preferred once complete):
/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/runtime_nfs_bulk/
  qwen_dcu_perf_trace_batch8_sealed_20260901/
  workflow01-10-fresh-e2e/batch8-dp2-fresh-003/R07/
  batch8-dp2-fresh-003-R07-attempt-043
```

| File | SHA-256 |
| --- | --- |
| `R01_R06_OUTPUT_RECOVERY_INDEX.json` | `79cb6d014b33d194c5d543d18758253c502220aa76af852807e468cebdfbe552` |
| `RECOVERY_COMPLETE.json` | `70ca5c32894d91d23f277efd81dbb6c60a4aa6b5230be837027b5bdfe8c6644c` |
| R07 `RECOVERY_ENTRYPOINT.json` | `0a72eb05c1be07ceb3a52b6267322c27327cd85acae8c3f59e4963af47e867d3` |
| R07 `RECOVERY_INDEX.json` | `df5da1ddf9a31ae568e5acf688dc6d57ef14f1921c81d419bd11505d7912e353` |

Start R07 recovery with `RECOVERY_ENTRYPOINT.json`. The immutable underlying
index records its atomic staging prefix; the entry point contains the exact
old-prefix/new-prefix rebinding. Do not interpret the staging paths literally.

For R01-R06, verify the two small top-level files first:

```bash
R0106_RECOVERY=/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/runtime_nfs_bulk/qwen_dcu_perf_trace_batch8_container_loss_insurance_20260903/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/R01-R06/output_recovery_index_001
cd "$R0106_RECOVERY"
sha256sum -c SHA256SUMS
```

## R07 attempt-043 open-writer insurance

The snapshot was sealed at `2026-09-03T14:33:29.818740Z` without a signal,
lock request, device query, or SQLite open. The source file stat was stable
during the copy and the NFS readback matched.

| Output | Bytes | SHA-256 |
| --- | ---: | --- |
| `raw_open_writer_snapshot/capture.db` | 8,958,377,984 | `0ea77cdac40926182c4e04fc29e687e62df9b2cac50296c7e399817c583690b0` |
| `raw_open_writer_snapshot/capture.log` | 779 | `7ee8d01b39beb57027450d70b956204518bed57311a2db6be08e098ae8be38a4` |
| `raw_open_writer_snapshot/service.log` | 54,314 | `5dd1e0f0be115b8215e6eb470d331c57a8ad3516aa84c118622c456236155b30` |
| `raw_open_writer_snapshot/service_start_validation.json` | 3,426 | `fa6f9c42bf354319d5c5d63dc7b2680a90dda80e2c13fee3cbd44cf7006ea3b2` |
| `open_unlinked_sqlite_temporaries/hipprof_fd_4.bin` | 183,943,168 | `b7fe998029621179b6f0efa1f6a428940f69566d5aa132d0844586c816ebf43f` |
| `open_unlinked_sqlite_temporaries/hipprof_fd_5.bin` | 27,141,058 | `60aabab82feca8c199f8ee467afb5c3b9b8fffbd84470659e4b80b827abc1410` |

The R07 index also seals 108 NFS-resident artifact files totaling
1,915,664,039 bytes. Completed workload evidence includes:

| File | SHA-256 |
| --- | --- |
| `capture/workload/driver.json` | `59443f304c3cdba263e30f369b07cea6e17f0581643933dbdeed4dabc8307f51` |
| `capture/workload/request_results.json` | `5c7c7ad97d55f31bc4794609f071b3d0ccfab6e803917cfecef247bab1689bd8` |
| `capture/workload/runtime_bindings/rank0.jsonl` | `305f33ea34020ec654a6f82066d9e61c9b24a11876b2b7456ac33804bb9c8337` |
| `capture/workload/runtime_bindings/rank1.jsonl` | `d37978920cb1793ade2889aff0e549ab4d49e6d80ec570e89e8d4658b6fabbe7` |

Capability boundary:

- This is not a formal closed-database checkpoint.
- SQLite consistency was intentionally not checked while the writer was open.
- HIPProf does not support resuming or appending to this capture.
- The two unlinked temporary files are forensic dependencies, not standalone
  databases.
- Never run recovery tools against the immutable insurance copy in place.
  First copy `capture.db` to a new worker-local recovery directory, verify the
  copied bytes against the hash above, and only then attempt offline export.

If the formal durable root contains `CAPTURE_DB_DURABLE.json`, prefer the
closed database named by that marker. Verify the marker and database hashes
before using it; do not fall back to the open-writer snapshot merely because
offline export is slow.

## R01-R06 outputs

The NFS bundle was generated at `2026-09-03T14:55:21.921685Z`. It contains
the six handoffs, six authoritative per-file artifact manifests, both release
part manifests, the reconstruction seal, the preparation record, the frozen
R01-R06 ledger prefix, and the materialization report. It intentionally does
not duplicate the expanded worker-local output surface.

Public release families:

| Scope | Release | Parts | Bytes | Ordered stream SHA-256 | `PARTS.tsv` SHA-256 |
| --- | --- | ---: | ---: | --- | --- |
| R01-R03 | [`perf-trace-batch8-r01-r03-batch8-dp2-fresh-003-20260827`](https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r01-r03-batch8-dp2-fresh-003-20260827) | 7 | 13,763,365,701 | `4a55990b77a4a5eea0e0d38aeccf474f220b0c0b8c1054d10090ed711567a530` | `d419e3b423b69acdf31a6bfa4549164eec5875b33ed20dcd633cf7e90d87d9cc` |
| R04-R06 | [`perf-trace-batch8-r04-r06-batch8-dp2-fresh-003-20260829`](https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r04-r06-batch8-dp2-fresh-003-20260829) | 74 | 2,461,322,416 | `ffd4f191083aaed418345e42c92d0e3dc6e0e2b500e7ee0a902f56cc7dc735d2` | `b87c9d17b92e9c4f23e27c87f39f93986a9d27194baff6dc290dea3c12d6c191` |

All 81 direct asset URLs and per-part hashes are in
`R01_R06_OUTPUT_RECOVERY_INDEX.json`; the copied `release_parts/*.PARTS.tsv`
files are the concise download manifests.

Authoritative stage identities:

| Stage | Handoff SHA-256 | Artifact manifest SHA-256 |
| --- | --- | --- |
| R01 | `f28cb9274151c5b08f15964e9645cbcaa41b90fb6f867607472028e993b774d6` | `be394f98cc18892c176d444ed08247d411ed7a911d248e6aded28352f8a69d56` |
| R02 | `9c1b908430fe9757935d029e8f423192652f21675aeffd77bc6a0f5d48d2e7e6` | `0bd7fb447cb51ae63f54d957fd703b9c0018196a7913f01ff414f5fbdeab1487` |
| R03 | `f7e6066bd72272cee9e96d2ac31596bd20f01841157bda4d0c2eb56092f99885` | `9b49cddeb1a2823becb6bd1a8e191fea4180aa7fa2d2adc0ef9dfc23e693aed1` |
| R04 | `403af982ff2f70f89fce2cfda59074a9b014a32e95c53e9e05e292dc843e6719` | `bb3ab2c39d0b1c52ea1d0ff6355c58d34fa2df5f84bc29e04f9cb6fb1767730c` |
| R05 | `db08474f64a999428287388a949762274716df125132cbccbabe3ec23c1aec66` | `ee8aa843f85d4cbe5d02e3c7aa0cd54c36faa155fa050218cfb3101254366325` |
| R06 | `0da6d692f1d69194ab02f4de0993c7aaca2381793eeb61ce33ffeb52ec058976` | `c5b8a21eb164478e4c5ad67d0e0bd828d337cb070588616deba4a3a2e0455f0d` |

The reconstructed R01/R02/R04/R05/R06 surface has 155,319 entries,
43,362,488,683 logical bytes, and canonical identity
`a7c2a109016baa4165ebf9f12e2a92899123754cf5b7aacaf3e2bbb4104e384d`.
The materialization report file SHA-256 is
`40c99216696495af478fec7e2fc1a8120f68425a303913cef42f3916e230b301`;
its payload SHA-256 is
`74021dfb3ac83d7ffda195ce75decaabf0a9eaf1718421397dbea232801d8a0f`.
R03 remains a direct NFS directory with 17,182 entries and
24,770,989,137 logical bytes.

## R01-R06 replacement-container procedure

The canonical artifact links for R01, R02, R04, R05, and R06 survive on NFS,
but their `/perf_trace_batch8_r01_r06` target does not. R03 is already a real
NFS directory and must not be replaced.

On a fresh replacement container, first require all three worker-local paths
below to be absent. Abort on any unexpected existing path; do not delete it
blindly. Then recreate this exact ordered topology:

```text
/dev/shm/perf_trace_batch8_r01_r06
  -> /workspace/qwen_dcu_perf_trace_batch8_predecessor_rebuild_20260901
/perf_trace_batch8_r01_r06
  -> /dev/shm/perf_trace_batch8_r01_r06
runtime/.../artifacts/R01,R02,R04,R05,R06
  -> /perf_trace_batch8_r01_r06/batch8-dp2-fresh-003/expanded_artifacts/<stage>
```

The last five links are NFS-resident and should already exist. A fail-closed
worker-local recreation is:

```bash
R0106_WORKER_ROOT=/workspace/qwen_dcu_perf_trace_batch8_predecessor_rebuild_20260901
for recovery_path in "$R0106_WORKER_ROOT" /dev/shm/perf_trace_batch8_r01_r06 /perf_trace_batch8_r01_r06; do
  if [ -e "$recovery_path" ] || [ -L "$recovery_path" ]; then
    echo "unexpected existing recovery path: $recovery_path" >&2
    exit 1
  fi
done
mkdir -p "$R0106_WORKER_ROOT"
ln -s "$R0106_WORKER_ROOT" /dev/shm/perf_trace_batch8_r01_r06
ln -s /dev/shm/perf_trace_batch8_r01_r06 /perf_trace_batch8_r01_r06
```

Then use the pinned, resumable restore and materialization helpers:

```bash
PERF_TRACE_ROOT=/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8
/usr/bin/python3.10 -B "$PERF_TRACE_ROOT/scripts/restore_relocated_release_archives.py"
PERF_TRACE_RESTORE_EXISTING_RELOCATED_ROOTS=1 \
  /usr/bin/python3.10 -B "$PERF_TRACE_ROOT/scripts/materialize_relocated_predecessors.py"
```

Pinned helper hashes:

| Helper | SHA-256 |
| --- | --- |
| `restore_relocated_release_archives.py` | `bda20e48938da98630ad7a98fe69d78d70244ce617479dfd301fb2786ce0bb6f` |
| `materialize_relocated_predecessors.py` | `b2a116000231f4bd2fb8684d797149aa34dde128f578c1493bffa0dfe3034d85` |
| `prepare_r01_r06_worker_reconstruction_v4.py` | `6c579d1d819867d7d2b585815aa5b3b2989a96e9023f67199ffd83b0ffc7b590` |
| `seal_r01_r06_worker_reconstruction_v4.py` | `8429e1dcc6ba648a9ccccc63209e7086996fd47abfe12205e7048f5bbc1df646` |

The preparation and v4 seal are retained as immutable reference records on
NFS. Do not rerun them blindly when their exclusive output files already
exist. Instead, compare the newly generated materialization report and stage
manifests with the identities in the recovery index and the existing v4 seal:

```text
/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/runtime/
  workflow01-10-fresh-e2e/batch8-dp2-fresh-003/relocation/
  r01_r06_worker_root_reconstruction_004.json
SHA-256: 1bad97176b0ebed1c07d58a56714691f64cd50e36c50d396383cc23924e63aa9
```

Only after the surface identity, all six handoffs, and all six artifact
manifests match should R07 post-processing or a new R07 capture consume the
reconstructed predecessors.

## Live-state note

At `2026-09-04T11:26:32Z`, attempt-043 HIPProf had run for about 31 hours 12
minutes and its active worker was still CPU-running. The 8.96 GB active raw
database remained under worker-local `/workspace`; no formal durable
checkpoint, PFTrace export, normalized R07 outputs, or R07 handoff existed at
that snapshot. This status line is historical. The recovery priority above,
not this line, determines which R07 copy to use after a later completion.
