"""Read-only compact observation of actual CPU phases and stage publications."""
from pathlib import Path
import datetime
import json
import os

C = Path('/public/home/accl15ptg7/run_R08_R10')
RUN = Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003')
plan = {'R08': ['resource_model', 'resource_audit', 'seal', 'completion_audit'],
        'R09': ['analysis', 'table_audit', 'seal', 'completion_audit'],
        'R10': ['render', 'browser', 'seal', 'completion_audit']}
result = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'stages': {}}
for stage, phases in plan.items():
    root = RUN / 'artifacts' / stage / 'continuation_001'
    summary = {}
    for phase in phases:
        path = root / 'validation/phase_lifecycle' / (phase + '.json')
        if path.exists():
            value = json.loads(path.read_text())
            summary[phase] = {'status': value['status'], 'seconds': round(value['elapsed_seconds'], 2)}
        elif (root / 'logs' / (phase + '.log')).exists():
            summary[phase] = {'status': 'started_pending_closed_receipt'}
    summary['handoff'] = (RUN / 'handoffs' / (stage + '.continuation.json')).exists()
    summary['published'] = (C / 'publication' / ('complete_' + stage) / 'PUBLICATION_COMPLETE.json').exists()
    result['stages'][stage] = summary
result['NFS_free_GiB'] = round(os.statvfs(C).f_bavail * os.statvfs(C).f_frsize / (1 << 30), 2)
result['root_free_GiB'] = round(os.statvfs('/root').f_bavail * os.statvfs('/root').f_frsize / (1 << 30), 2)
print(json.dumps(result, separators=(',', ':')))
