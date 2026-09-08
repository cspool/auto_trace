"""Checkpoint derived union provenance against the earlier closed-source seal."""
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
union_path = A / 'NATIVE_SESSION_UNION.json'
union = json.loads(union_path.read_text())
assert union['status'] == 'complete_lossless_derived_union' and union['original_native_files_retained_unmodified']
assert union['timestamps_counters_PID_device_and_correlation_values_unchanged']
original_path = R / 'raw/runtime_tools/closed_native_source_snapshots_001' / (segment + '.' + attempt + '.json')
original = json.loads(original_path.read_text())
assert original['segment_id'] == segment and original['attempt'] == attempt and not original['capture_accepted']
assert [{k: x[k] for k in ['rank', 'database', 'csv']} for x in union['source_sessions']] == original['original_native_sessions']
prefetch_path = C / ('capture' + segment[:2] + '_derived_DB_sequential_read_001.log')
prefetch = json.loads(prefetch_path.read_text().splitlines()[-1])
assert prefetch['status'] == 'read_only_sequential_pass_complete'
assert prefetch['sha256'] == union['derived_database']['sha256'] and prefetch['size'] == union['derived_database']['size']
rows = sum(t['row_count'] for x in union['source_sessions'] for t in x['tables'])
csv_rows = sum(x['CSV_identity_mapping']['data_lines'] for x in union['source_sessions'])
out = D / ('capture' + segment[:2] + '_' + attempt + '_lossless_union_001')
out.mkdir(exist_ok=False)
sources = [union_path, original_path, prefetch_path, C / 'read_closed_derived_db_sequentially_001.py']
for source in sources:
    (out / source.name).write_bytes(source.read_bytes())
(out / 'SOURCE_RECORDS.json').write_text(json.dumps([
    {'path': str(p), 'size': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
    for p in sources], indent=2) + '\n')
(D / 'outer_helpers_001' / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
with (D / 'LIVE_PROGRESS.md').open('a') as stream:
    stream.write('\n- ' + datetime.datetime.now(datetime.timezone.utc).isoformat() + ': Capture ' + segment[:2] +
                 ' ' + attempt + ' produced a lossless derived union of ' + str(rows) + ' original native rows and ' + str(csv_rows) +
                 ' original CSV data lines. Both original DB/CSV identities exactly match the earlier independently hashed closed-source receipt. The derived DB SHA also matches the bounded read-only sequential pass. Full independent cell and native attribution audits remain required; this is not capture acceptance.\n')
print(json.dumps({'checkpoint_directory': str(out), 'native_rows': rows, 'native_CSV_data_lines': csv_rows,
                  'original_closed_source_SHA_records_match': True, 'capture_accepted': False}))
