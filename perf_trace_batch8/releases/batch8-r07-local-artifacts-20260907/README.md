# R07 / Attempt 43 local artifact publication

R07 and Attempt 43 measurements, data, metadata, logs, contracts, validation
results, and recovery intermediates must be preserved remotely. Compiler
caches, Python bytecode, wheels, and replaceable installed-runtime archives
are excluded. Runtime paths in `.gitignore` exclude working copies from Git
objects; they do **not** authorize omitting experiment evidence from publication.

## Coverage

- Regular files indexed: 2,655, totaling 128,830,618,563 logical bytes before deduplication.
- Files already covered by verified existing releases: 2,106.
- Newly archived unique files: 396, totaling 68,766,845,960 bytes.
- Additional paths restored from identical newly archived content: 153.
- Supplement: 11,954,409,547 compressed bytes in 45 ordered parts.
- Exclusions: 17,313 files; detailed categories and paths are in `EXCLUSIONS.json`.
- Historical symlinks: 96; link targets are recorded in `SYMLINKS.json`.

The snapshot covers local `runtime/attempt043_db_recovery`,
`runtime/local_r07_hipprof_attempt020_full`, the run's `artifacts/R07`,
R07 handoffs/revisions and shared state/ledger, R07 NFS spill data, and the
R07 release-download tree (including its separate offline experiments).
The inventory does not claim that missing external symlink targets exist
locally or are restored. Compiler-cache links remain historical metadata.

The supplement retains full Attempt 43 PFTrace output, available prepared and
export-mutated database states, recovery/monitor logs, and any older R07
files absent from verified published archives. Identical copies are restored
from one payload. Filenames preserve attempt and revision boundaries, including
failed normalization outputs; publication does not assert that the original
remote HIPProf process completed naturally.

## Remote locations

- Supplement: https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r07-local-artifacts-20260907
- Original R07 data: https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r07-raw-batch8-dp2-fresh-003-20260831
- Attempt 43 source DB: https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r07-attempt043-open-writer-db-20260904
- Attempt 43 diagnostics: https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r07-attempt043-hipprof-diagnostic-20260905
- Attempt 43 consumer results: https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r07-attempt043-offline-recovery-20260907

`FILE_MANIFEST.json` maps every indexed local path and SHA-256 to either an
existing asset/archive member or the supplement. Existing compressed streams
were verified against release-published SHA-256 files; archive-member hashes
were computed from those verified streams. API asset digests also matched
the downloaded control metadata. `REMOTE_VERIFICATION.json` records the final
name, size, state, and server SHA-256 checks for every supplement release asset.

## Restore

Requirements: Python 3, gzip, zstd, network access and sufficient disk space.
From this directory in a checkout (or after downloading its control files):

```bash
python3 restore.py --root /path/to/restored-auto-trace
python3 restore.py --root /path/to/restored-auto-trace --verify-only
```

To restore only this supplement's newly published files and duplicate paths:

```bash
python3 restore.py --root /path/to/restored-auto-trace --supplement-only
```

The script verifies each downloaded part, assembled stream and restored file,
reuses valid downloads in `.r07_restore_cache`, and refuses conflicting files
or writes through symlinks. Existing matching files are kept. Historical
absolute/dangling symlinks and special files are recorded as metadata only;
they are not created on the destination host.

For manual access to unique supplement members, download every ordered part
and the checksum files into one directory:

```bash
sha256sum -c ARCHIVE_PARTS_SHA256SUMS
cat r07-local-artifacts.tar.zst.part-* > r07-local-artifacts.tar.zst
sha256sum -c ARCHIVE_STREAM_SHA256
tar --zstd -xf r07-local-artifacts.tar.zst -C /path/to/restored-auto-trace
```

Manual extraction restores only unique supplement members. Use `restore.py`
to also restore duplicate paths and data covered by earlier releases.
