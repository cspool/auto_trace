"""Recheck completed restoration before resuming an interrupted CPU admission."""
from pathlib import Path
import datetime
import hashlib
import importlib.util
import json
import os

C = Path('/public/home/accl15ptg7/run_R08_R10')
P = Path('/public/home/accl15ptg7/auto_trace')
R = P / 'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001'
B = R / 'raw/runtime_tools'

def read(path):
    return json.loads(Path(path).read_text())

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()

def rec(path):
    return {'path': str(path), 'size': Path(path).stat().st_size, 'sha256': sha(path)}

def verify(record):
    assert rec(Path(record['path'])) == record

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

proof_path = B / 'release_restoration_001/COMPLETE.json'
proof = read(proof_path)
assert proof['status'] == 'complete' and proof['all_twelve_capture_parts_restored']
assert proof['all_evicted_raw_files_original_SHA256_verified']
assert (C / 'STOP_RELEASE_OFFLOAD_WATCHDOG').exists()
for key in ['accepted_index', 'weight_removal', 'user_policy']:
    verify(proof[key])
index = read(proof['accepted_index']['path'])
assert index['status'] == 'complete' and len(index['captures']) == 12
assert index['all_capture_and_attribution_processes_terminated']
for item in index['captures']:
    for key in ['execution_manifest', 'normalization_manifest', 'independent_audit']:
        verify(item[key])
common = module('restoration_resume_common', C / 'stage_tool_templates_003/shared_001/cpu_stage_common.py')
optimized = module('restoration_resume_path_validator', C / 'outer_source_path_validation_001.py')
gate = read(C / 'outer_source_path_optimization_gate_001/COMPLETE.json')
assert gate['status'] == 'complete'
verify(gate['candidate'])
verify(gate['reference_common'])
validator = optimized.OuterSourcePathValidator(common)
counts = []
assert len(proof['segment_receipts']) == 12
for item, receipt in zip(index['captures'], proof['segment_receipts']):
    verify(receipt)
    segment = read(receipt['path'])
    assert segment['status'] == 'complete' and segment['all_original_SHA256_verified']
    assert segment['segment_id'] == item['segment_id']
    offload = read(B / 'remote_release_offloads_001' / (item['segment_id'] + '.complete.json'))
    assert segment['restored_files'] == offload['temporarily_evicted_files']
    for source in segment['restored_files']:
        path = validator.validate_path(source['path'])
        assert path.stat().st_size == source['size'] and sha(path) == source['sha256']
    counts.append({'segment_id': item['segment_id'], 'files': len(segment['restored_files']),
                   'bytes': sum(x['size'] for x in segment['restored_files'])})
    print('CPU_RESUME_ORIGINAL_RAW_RECHECKED', item['segment_id'], counts[-1]['files'], flush=True)
assert sum(x['files'] for x in counts) == 53
assert sum(x['bytes'] for x in counts) == proof['restored_bytes'] == 77001580022
result = {'status': 'complete', 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'restoration_complete_receipt': rec(proof_path), 'capture_count': 12,
          'raw_file_count': 53, 'raw_bytes': proof['restored_bytes'],
          'all_original_source_SHA256_rechecked': True, 'segments': counts,
          'no_capture_or_restore_reexecution': True, 'source_bytes_changed': False,
          'validator_CPU_gate': rec(C / 'outer_source_path_optimization_gate_001/COMPLETE.json'),
          'code': rec(Path(__file__))}
out = R / 'validation/CPU_RESUME_RESTORATION_RECHECK_001.json'
with out.open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
    stream.flush()
    os.fsync(stream.fileno())
print('CPU_RESUME_ALL_RESTORED_ORIGINAL_SHA256_VERIFIED', flush=True)
