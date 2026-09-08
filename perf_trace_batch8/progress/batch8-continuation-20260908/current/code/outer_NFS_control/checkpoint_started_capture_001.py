"""Preserve immutable capture startup controls and the observed recovery snapshot."""
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
contract = json.loads((A / 'control/capture_contract.json').read_text())
assert contract['attempt'] == attempt and contract['segment']['segment_id'] == segment
assert not (A / 'execution_manifest.json').exists()
assert A.stat().st_dev == C.stat().st_dev
environment = json.loads((A / 'control/runtime_environment.json').read_text())
assert environment['MODEL_DIR'] == '/root/Qwen3.5-27B'
out = D / ('capture' + segment[:2] + '_' + attempt + '_started_001')
out.mkdir(exist_ok=False)
sources = [A / 'control' / name for name in ['capture_contract.json', 'profiler_identity.json',
           'live_collector_exec.json', 'service_identity.json', 'runtime_environment.json']]
for source in sources:
    assert source.stat().st_size < 100000
    (out / source.name).write_bytes(source.read_bytes())
(out / 'SOURCE_RECORDS.json').write_text(json.dumps([
    {'path': str(p), 'size': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
    for p in sources], indent=2) + '\n')
(D / 'RECOVERY_STATE_NFS.json').write_bytes((C / 'RECOVERY_STATE_NFS.json').read_bytes())
(D / 'outer_helpers_001' / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
with (D / 'LIVE_PROGRESS.md').open('a') as stream:
    stream.write('\n- ' + datetime.datetime.now(datetime.timezone.utc).isoformat() + ': Capture ' + segment[:2] +
                 ' ' + attempt + ' started under frozen runtime021/analysis008 with model weights at /root/Qwen3.5-27B and new outputs on NFS. Immutable startup controls are preserved. Startup does not establish warmup health, eight-request trace coverage, or capture acceptance.\n')
print(json.dumps({'checkpoint_directory': str(out), 'capture_accepted': False}))
