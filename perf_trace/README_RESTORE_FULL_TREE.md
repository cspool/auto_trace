# Restore the complete `perf_trace` tree

GitHub rejects ordinary Git objects larger than 100 MB. Four expanded visualization
files exceed that limit. Their byte-identical copies are retained inside the two
`acceptance/*full-resolution*.tar.gz` archives, which are committed normally.

After cloning, restore the four expanded files and verify all 92 files from the
original source directory:

```bash
python3 perf_trace/restore_perf_trace_large_files.py
```

`SOURCE_TREE_SHA256SUMS` is the pre-removal checksum inventory. The restore command
fails closed if either archive or any reconstructed/original source file differs.
