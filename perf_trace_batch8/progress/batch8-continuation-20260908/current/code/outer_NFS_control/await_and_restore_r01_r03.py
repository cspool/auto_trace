import json
from pathlib import Path
import subprocess
import time
import sys

C=Path('/public/home/accl15ptg7/run_R08_R10')
P=Path('/public/home/accl15ptg7/auto_trace')
release=next(r for r in json.loads((P/'perf_trace_batch8/releases/batch8-r08-continuation-20260908/RELEASE_CATALOG.json').read_text())['releases'] if 'r01-r03-batch8' in r['tag'])
parts=[C/'downloads'/release['tag']/a['name'] for a in release['assets'] if 'full.tar.gz.part-' in a['name']]
while not all(p.exists() for p in parts):
    print(time.strftime('%H:%M:%S',time.gmtime()),'AWAITING_PARTS',sum(p.exists() for p in parts),len(parts),flush=True)
    time.sleep(30)
subprocess.run([sys.executable,str(C/'restore_predecessors.py'),'r01-r03','--destination','/dev/shm/r08_continuation_predecessors'],check=True)
run=P/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003'
for stage in ['R01','R02','R03']:
    target=Path('/dev/shm/r08_continuation_predecessors/artifacts')/stage
    assert target.is_dir()
    (run/'artifacts'/stage).symlink_to(target,target_is_directory=True)
    source=Path('/dev/shm/r08_continuation_predecessors/handoffs')/(stage+'.json')
    expected=C/'snapshot/recovery_index/handoffs'/(stage+'.json')
    assert source.read_bytes()==expected.read_bytes()
    with (run/'handoffs'/(stage+'.json')).open('xb') as f:f.write(source.read_bytes())
subprocess.run([sys.executable,str(P/'perf_trace_batch8/continuation_20260908/verify_predecessor_manifests.py'),'R01','R02','R03'],check=True)
print('R01_R03_RESTORED_AND_ALL_ENTRIES_VERIFIED',flush=True)
