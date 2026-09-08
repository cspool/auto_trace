"""Copy the completed live eight-request marker check without native acceptance."""
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
reports = sorted((R / 'raw/runtime_tools/live_eight_request_checks_001').glob(segment + '.' + attempt + '.*.json'))
assert reports
report = reports[-1]
check = json.loads(report.read_text())
assert check['segment_id'] == segment and check['attempt'] == attempt
assert check['status'] == 'complete_live_marker_coverage' and check['eight_requests'] == 8
assert check['expected_process_marker_count'] == check['observed_process_marker_count'] == 12544
assert check['all_first_phase_orders_match_R07']
assert not check['closed_capture_accepted'] and not check['native_DB_and_PMC_correlation_audited']
assert len(check['checks']) == 16
assert len({x['request_id'] for x in check['checks']}) == 8
assert all(x['expected_targets'] == x['observed_marker_rows'] == 784 and not x['missing_targets']
           and not x['unexpected_targets'] and x['duplicate_targets'] == 0 for x in check['checks'])
assert set(check['rank_worker_PIDs']) == {'0', '1'}
assert all(len(pids) == 1 for pids in check['rank_worker_PIDs'].values())
assert len({pid for pids in check['rank_worker_PIDs'].values() for pid in pids}) == 2
out = D / ('capture' + segment[:2] + '_' + attempt + '_live_eight_request_coverage_001')
out.mkdir(exist_ok=False)
checker = C / 'check_live_eight_request_targets_002.py'
sources = [report, checker]
(out / 'LIVE_EIGHT_REQUEST_TARGET_COVERAGE.json').write_bytes(report.read_bytes())
(out / checker.name).write_bytes(checker.read_bytes())
(out / 'SOURCE_RECORDS.json').write_text(json.dumps([
    {'path': str(p), 'size': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
    for p in sources], indent=2) + '\n')
(D / 'outer_helpers_001' / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
with (D / 'LIVE_PROGRESS.md').open('a') as stream:
    stream.write('\n- ' + datetime.datetime.now(datetime.timezone.utc).isoformat() + ': Capture ' + segment[:2] +
                 ' ' + attempt + ' passed exact live coverage for all eight requests, each with 784 declared first-prefill and 784 first-decode targets, 12,544 total, no missing or duplicate targets. Both rank orders match R07. Original live-prefix hashes and checker code are retained. Closed native attribution and capture acceptance remain pending.\n')
print(json.dumps({'checkpoint_directory': str(out), 'live_target_count': 12544, 'closed_capture_accepted': False}))
