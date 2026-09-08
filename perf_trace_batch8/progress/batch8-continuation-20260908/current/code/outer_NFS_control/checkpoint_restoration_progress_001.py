"""Copy immutable restoration receipts into a remotely publishable checkpoint."""
from pathlib import Path
import datetime
import hashlib
import json
import re
import sys

C = Path('/public/home/accl15ptg7/run_R08_R10')
P = Path('/public/home/accl15ptg7/auto_trace')
R = P / 'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001'
O = R / 'raw/runtime_tools/release_restoration_001'
D = P / 'perf_trace_batch8/continuation_20260908'
label = sys.argv[1]
assert re.fullmatch(r'[a-z0-9_]+', label)
index = R / 'normalized/accepted_captures.json'
accepted = json.loads(index.read_text())
assert accepted['status'] == 'complete' and len(accepted['captures']) == 12
weight_proof = O / 'WEIGHTS_REMOVED_AFTER_ALL_CAPTURES.json'
assert json.loads(weight_proof.read_text())['status'] == 'complete'
receipts = sorted(O.glob('*.complete.json'))
summaries = []
for path in receipts:
    item = json.loads(path.read_text())
    assert item['status'] == 'complete' and item['all_original_SHA256_verified']
    summaries.append({'segment_id': item['segment_id'],
                      'restored_file_count': len(item['restored_files']),
                      'restored_bytes': sum(x['size'] for x in item['restored_files']),
                      'completed_utc': item['completed_utc']})
complete = O / 'COMPLETE.json'
if complete.exists():
    item = json.loads(complete.read_text())
    assert item['status'] == 'complete' and item['all_twelve_capture_parts_restored']
    assert item['all_evicted_raw_files_original_SHA256_verified'] and len(summaries) == 12
sources = [index, O / 'WEIGHT_REMOVAL_PREPARED.json', weight_proof, Path(__file__)]
sources += sorted(O.glob('*.prepared.json')) + receipts
if complete.exists():
    sources.append(complete)
out = D / ('release_restoration_' + label + '_001')
out.mkdir(exist_ok=False)
records = []
for path in sources:
    data = path.read_bytes()
    assert len(data) < 5_000_000
    (out / path.name).write_bytes(data)
    records.append({'path': str(path), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
(out / 'SOURCE_RECORDS.json').write_text(json.dumps(records, indent=2) + '\n')
summary = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'status': 'restoration_complete' if complete.exists() else 'restoration_in_progress',
           'weight_removal_complete_after_all_GPU_captures': True,
           'restored_capture_count': len(summaries),
           'restored_bytes': sum(x['restored_bytes'] for x in summaries),
           'producer_original_SHA_verification_receipts': summaries,
           'observer_does_not_repeat_full_raw_hashing': True,
           'stage_acceptance_not_inferred_from_restoration': True}
(out / 'RESTORATION_PROGRESS.json').write_text(json.dumps(summary, indent=2) + '\n')
with (D / 'LIVE_PROGRESS.md').open('a') as stream:
    stream.write('\n- ' + summary['utc'] + ': Restoration checkpoint ' + label + ': root weights were removed only after all 12 GPU captures and publications closed; ' + str(len(summaries)) + '/12 capture groups have original-SHA restoration receipts (' + str(summary['restored_bytes']) + ' bytes). Stage completion is tracked separately.\n')
print(json.dumps({'checkpoint_directory': str(out), **summary}))
