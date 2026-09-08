"""Bounded read-only cache prefetch during SQLite's NFS integrity check.

This is an outer I/O observation, never native or capture acceptance evidence.
The original collector exits must be complete. No source bytes are changed.
"""
from pathlib import Path
import datetime
import hashlib
import json
import signal
import sys
import time

path = Path(sys.argv[1])
assert path.name == 'capture.db' and path.parent.name.startswith('attempt_')
closed = json.loads((path.parent / 'control/NATIVE_COLLECTORS_CLOSED.json').read_text())
assert closed['status'] == 'complete' and closed['all_started_native_groups_terminated']
assert path.stat().st_dev == Path('/public/home/accl15ptg7').stat().st_dev
before = path.stat()
assert time.time() - before.st_mtime > 30
signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('bounded 180 second read')))
signal.alarm(180)
started = time.monotonic()
digest = hashlib.sha256()
size = 0
next_report = 256 << 20
print(json.dumps({'event': 'READ_ONLY_SEQUENTIAL_PREFETCH_START', 'path': str(path),
                  'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'size': before.st_size, 'does_not_replace_SQLite_or_native_audit': True}), flush=True)
with path.open('rb') as source:
    for block in iter(lambda: source.read(8 << 20), b''):
        digest.update(block)
        size += len(block)
        if size >= next_report:
            print(json.dumps({'bytes_read': size, 'elapsed_seconds': round(time.monotonic()-started, 3)}), flush=True)
            next_report += 256 << 20
after = path.stat()
assert (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns)
assert size == before.st_size
signal.alarm(0)
print(json.dumps({'status': 'read_only_sequential_pass_complete', 'path': str(path),
                  'size': size, 'sha256': digest.hexdigest(),
                  'elapsed_seconds': time.monotonic()-started,
                  'capture_accepted': False, 'SQLite_check_replaced': False}), flush=True)
