"""Preserve normal independent native exits; do not promote capture acceptance."""
from pathlib import Path
import datetime
import hashlib
import json
import sys

C = Path('/public/home/accl15ptg7/run_R08_R10')
P = Path('/public/home/accl15ptg7/auto_trace')
R = P / 'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001'
D = P / 'perf_trace_batch8/continuation_20260908'
segment, attempt = sys.argv[1:]
assert segment in {x['segment_id'] for x in json.loads((R / 'plans/r08_capture_plan.json').read_text())['physical_captures']}
assert attempt.startswith('attempt_') and attempt[8:].isdigit()
A = R / 'raw/captures' / segment / attempt

def read(path):
    return json.loads(path.read_text())

def record(path):
    return {'path': str(path), 'size': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

closed = A / 'control/NATIVE_COLLECTORS_CLOSED.json'
proof = read(closed)
assert proof['status'] == 'complete' and proof['all_started_native_groups_terminated']
assert {x['rank'] for x in proof['collectors']} == {0, 1}
sources = [closed, A / 'control/tracee_process_cleanup.json', A / 'control/tracee_workload_complete.json']
for collector in proof['collectors']:
    assert collector['status'] == 'complete' and not collector['forced_group_cleanup']
    assert not collector['remaining_live_group_members']
    exit_path = Path(collector['wrapper_exit']['path'])
    assert record(exit_path) == collector['wrapper_exit']
    exit_proof = read(exit_path)
    assert exit_proof['status'] == 'complete' and exit_proof['collector_returncode'] == 0
    assert not exit_proof['timeout'] and not exit_proof['received_signals']
    unit = A / 'native_collectors' / ('rank' + str(collector['rank']))
    sources.extend([exit_path, unit / 'collector.log', unit / 'COLLECTOR_WRAPPER_START.json'])
driver = read(A / 'workload/driver.json')
assert driver['completed'] == 8 and driver['failed'] == 0 and driver['total_completion_tokens'] == 8192
out = D / ('capture' + segment[:2] + '_' + attempt + '_native_closure_001')
out.mkdir(exist_ok=False)
for source in sources:
    target = out / source.relative_to(A)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
receipt = {'status': 'both_native_collectors_normally_closed_pending_CPU_attribution',
           'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'segment_id': segment, 'attempt': attempt,
           'source_records': [record(p) for p in sources],
           'closed_capture_accepted': False,
           'observer': record(Path(__file__))}
(out / 'CHECKPOINT.json').write_text(json.dumps(receipt, indent=2) + '\n')
(D / 'outer_helpers_001' / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
with (D / 'LIVE_PROGRESS.md').open('a') as f:
    f.write('\n- ' + receipt['utc'] + ': Capture ' + segment[:2] + ' ' + attempt +
            ' completed both independent native collectors normally, return code 0, no signals, no timeout or forced group cleanup. All eight original requests completed. Original DB/CSV and collector logs remain on NFS. Lossless union verification and independent native attribution remain pending.\n')
print(json.dumps({'checkpoint_directory': str(out), 'closed_capture_accepted': False}))
