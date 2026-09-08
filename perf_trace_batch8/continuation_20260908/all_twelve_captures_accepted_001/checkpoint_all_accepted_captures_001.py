"""Publishable observation of the complete capture index, not stage acceptance."""
from pathlib import Path
import datetime
import hashlib
import json

C = Path('/public/home/accl15ptg7/run_R08_R10')
P = Path('/public/home/accl15ptg7/auto_trace')
R = P / 'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001'
D = P / 'perf_trace_batch8/continuation_20260908'

def read(path):
    return json.loads(path.read_text())

def record(path):
    data = path.read_bytes()
    return {'path': str(path), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

index_path = R / 'normalized/accepted_captures.json'
index = read(index_path)
assert index['status'] == 'complete' and index['all_capture_and_attribution_processes_terminated']
plan_path = R / 'plans/r08_capture_plan.json'
assert index['capture_plan'] == record(plan_path)
assert [x['segment_id'] for x in index['captures']] == [x['segment_id'] for x in read(plan_path)['physical_captures']]
assert len(index['captures']) == 12
records = [record(index_path), record(plan_path)]
summaries = []
for item in index['captures']:
    for key in ['execution_manifest', 'normalization_manifest', 'independent_audit']:
        assert item[key] == record(Path(item[key]['path']))
        records.append(item[key])
    execution = read(Path(item['execution_manifest']['path']))
    normalization = read(Path(item['normalization_manifest']['path']))
    audit = read(Path(item['independent_audit']['path']))
    assert execution['all_started_processes_terminated']
    assert execution['workload']['status'] == 'complete'
    assert audit['status'] == 'complete' and audit['independent_audit']
    assert set(audit['rank_native_device_counts']) == {'0', '1'}
    assert audit['same_R06_R07_logical_ownership'] and audit['exact_native_chain']
    assert audit['raw_partition_conserved'] and not audit['replay_timing_used_as_latency']
    assert normalization['status'] == 'complete'
    assert normalization['current_process_markers'] == 12544
    assert normalization['native_owned_kernel_count'] == 23660
    assert normalization['missing_selected_counter_cells'] == 0
    summaries.append({'segment_id': item['segment_id'], 'attempt': item['capture_attempt'],
                      'accepted_dispatches': audit['accepted_dispatches'],
                      'current_process_markers': normalization['current_process_markers'],
                      'native_owned_kernel_count': normalization['native_owned_kernel_count'],
                      'rank_native_device_counts': audit['rank_native_device_counts'],
                      'counter_values_recomputed': audit['counter_values_recomputed']})
assert sum(x['accepted_dispatches'] for x in summaries) == 6912
out = D / 'all_twelve_captures_accepted_001'
out.mkdir(exist_ok=False)
for source in [index_path, plan_path, Path(__file__)]:
    (out / source.name).write_bytes(source.read_bytes())
(out / 'SOURCE_RECORDS.json').write_text(json.dumps(records, indent=2) + '\n')
summary = {'status': 'all_twelve_captures_accepted_pending_restoration_and_stage_audit',
           'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'accepted_capture_count': 12, 'accepted_physical_dispatches': 6912,
           'captures': summaries, 'R08_stage_complete': False,
           'required_next_steps': ['verify all raw Release assets', 'restore all original raw file identities',
                                   'R08 resource model and completion audit', 'R09', 'R10', 'stage publications']}
(out / 'CAPTURE_AGGREGATE.json').write_text(json.dumps(summary, indent=2) + '\n')
with (D / 'LIVE_PROGRESS.md').open('a') as stream:
    stream.write('\n- ' + summary['utc'] + ': All 12 R08 capture groups accepted; all 36 execution/normalization/independent-audit records match their SHA256 identities, both ranks are represented in every group, and 6,912 physical dispatches are attributed. This completes GPU capture collection; R08 stage completion still requires restored originals, resource construction and closure audits, followed by R09 and R10.\n')
print(json.dumps({'checkpoint_directory': str(out), 'accepted_capture_count': 12, 'accepted_physical_dispatches': 6912, 'R08_stage_complete': False}))
