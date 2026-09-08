"""Preserve sealed raw capture and native union audit before attribution acceptance."""
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

def record(path):
    return {'path': str(path), 'size': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

execution = json.loads((A / 'execution_manifest.json').read_text())
audit = json.loads((A / 'NATIVE_SESSION_UNION_AUDIT.json').read_text())
assert execution['status'] == 'raw_capture_complete_pending_exact_attribution'
assert execution['all_started_processes_terminated'] and execution['returncode'] == 0
assert execution['profiler_starts'] == 2 and execution['workload']['status'] == 'complete'
assert audit['status'] == 'complete' and audit['native_CSV_body_bytes_compared']
assert record(A / 'NATIVE_SESSION_UNION_AUDIT.json') == execution['native_session_union_audit']
assert record(A / 'raw_inventory_at_exit.json') == execution['raw_inventory']
original_path = R / 'raw/runtime_tools/closed_native_source_snapshots_001' / (segment + '.' + attempt + '.json')
original = json.loads(original_path.read_text())
assert original['original_native_sessions'] == execution['original_native_sessions']
out = D / ('capture' + segment[:2] + '_' + attempt + '_raw_complete_001')
out.mkdir(exist_ok=False)
sources = [A / 'execution_manifest.json', A / 'raw_inventory_at_exit.json',
           A / 'NATIVE_SESSION_UNION_AUDIT.json', A / 'logs/hipprof.log']
for source in sources:
    assert source.stat().st_size < 10_000_000
    (out / source.name).write_bytes(source.read_bytes())
(out / 'SOURCE_RECORDS.json').write_text(json.dumps([record(p) for p in sources], indent=2) + '\n')
(D / 'outer_helpers_001' / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
with (D / 'LIVE_PROGRESS.md').open('a') as stream:
    stream.write('\n- ' + datetime.datetime.now(datetime.timezone.utc).isoformat() + ': Capture ' + segment[:2] +
                 ' ' + attempt + ' sealed raw capture in ' + str(round(execution['elapsed_seconds'], 3)) +
                 ' seconds. Lossless union audit compared all ' + str(audit['native_rows_compared']) +
                 ' original native rows and all original CSV body bytes. Execution identities match the earlier closed native source seal. All collectors are closed; native attribution and independent acceptance remain separate pending steps.\n')
print(json.dumps({'checkpoint_directory': str(out), 'native_rows_compared': audit['native_rows_compared'],
                  'raw_elapsed_seconds': execution['elapsed_seconds'], 'capture_accepted': False}))
