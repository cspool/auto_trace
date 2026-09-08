"""Seal the original closed native sources before derived union completion."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import sys

C = Path('/public/home/accl15ptg7/run_R08_R10')
P = Path('/public/home/accl15ptg7/auto_trace')
R = P / 'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001'
D = P / 'perf_trace_batch8/continuation_20260908'
segment, attempt = sys.argv[1:]
assert segment in {x['segment_id'] for x in json.loads((R / 'plans/r08_capture_plan.json').read_text())['physical_captures']}
assert attempt.startswith('attempt_') and attempt[8:].isdigit()
A = R / 'raw/captures' / segment / attempt

def record(path):
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(8 << 20), b''):
            digest.update(block)
    after = path.stat()
    assert (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns)
    return {'path': str(path), 'size': after.st_size, 'sha256': digest.hexdigest()}

closed_path = A / 'control/NATIVE_COLLECTORS_CLOSED.json'
closed = json.loads(closed_path.read_text())
assert closed['status'] == 'complete' and closed['all_started_native_groups_terminated']
assert {x['rank'] for x in closed['collectors']} == {0, 1}
sources = []
for collector in sorted(closed['collectors'], key=lambda x: x['rank']):
    assert not collector['forced_group_cleanup'] and not collector['remaining_live_group_members']
    exit_path = Path(collector['wrapper_exit']['path'])
    assert record(exit_path) == collector['wrapper_exit']
    exit_proof = json.loads(exit_path.read_text())
    assert exit_proof['status'] == 'complete' and exit_proof['collector_returncode'] == 0
    assert not exit_proof['timeout'] and not exit_proof['received_signals']
    directory = A / 'native_collectors' / ('rank' + str(collector['rank']))
    db, csv = directory / 'capture.db', directory / 'capture.csv'
    assert all(p.is_file() and p.stat().st_size > 0 and p.stat().st_dev == C.stat().st_dev for p in [db, csv])
    sources.append({'rank': collector['rank'], 'database': record(db), 'csv': record(csv)})
proof = {'status': 'closed_original_native_sources_hashed_pending_union_and_attribution',
         'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'segment_id': segment, 'attempt': attempt,
         'original_native_sessions': sources, 'native_closure': record(closed_path),
         'capture_contract': record(A / 'control/capture_contract.json'),
         'weights_changed': False, 'source_bytes_changed': False, 'capture_accepted': False,
         'observer': record(Path(__file__))}
folder = R / 'raw/runtime_tools/closed_native_source_snapshots_001'
folder.mkdir(exist_ok=True)
receipt = folder / (segment + '.' + attempt + '.json')
with receipt.open('x') as stream:
    json.dump(proof, stream, indent=2)
    stream.write('\n')
    stream.flush()
    os.fsync(stream.fileno())
out = D / ('capture' + segment[:2] + '_' + attempt + '_closed_original_sources_001')
out.mkdir(exist_ok=False)
(out / 'ORIGINAL_NATIVE_SOURCES.json').write_bytes(receipt.read_bytes())
(D / 'outer_helpers_001' / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
with (D / 'LIVE_PROGRESS.md').open('a') as stream:
    stream.write('\n- ' + proof['utc'] + ': Capture ' + segment[:2] + ' ' + attempt +
                 ' has both original closed native DB/CSV files independently SHA-256 sealed before derived union completion. The receipt binds normal collector closure and the frozen capture contract. It supports source identity verification if the container is lost during CPU analysis; it does not claim capture acceptance.\n')
print(json.dumps({'checkpoint_directory': str(out), 'original_native_sessions': sources, 'capture_accepted': False}))
