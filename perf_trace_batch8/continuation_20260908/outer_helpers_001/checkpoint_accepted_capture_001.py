"""Copy closed accepted capture evidence into the main-repository checkpoint tree."""
from pathlib import Path
import json,hashlib,sys,datetime
C=Path('/public/home/accl15ptg7/run_R08_R10');P=Path('/public/home/accl15ptg7/auto_trace');R=P/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001';D=P/'perf_trace_batch8/continuation_20260908'
def read(p):return json.loads(p.read_text())
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
seg=sys.argv[1];matches=sorted((R/'validation').glob('serial_scheduler_*/'+seg+'.accepted_checkpoint.json'));assert matches
checkpoint=matches[-1];x=read(checkpoint);assert x['status']=='accepted';item=x['item'];sources=[checkpoint]
for k in ['execution_manifest','normalization_manifest','independent_audit']:
 p=Path(item[k]['path']);assert rec(p)==item[k];sources.append(p)
e=read(Path(item['execution_manifest']['path']));a=read(Path(item['independent_audit']['path']));assert e['all_started_processes_terminated'] and a['status']=='complete' and set(a['rank_native_device_counts'])=={'0','1'}
sources.extend(checkpoint.parent/(seg+'.'+kind+'.log') for kind in ['capture','normalize','audit'])
graph=Path(item['normalization_manifest']['path']).parent/'background_native_graph_classification.json'
if graph.exists():sources.append(graph)
out=D/('capture'+seg[:2]+'_'+item['capture_attempt']+'_accepted_001');out.mkdir(exist_ok=False);records=[]
for p in sources:
 assert p.is_file() and p.stat().st_size<10_000_000;records.append(rec(p));(out/p.name).write_bytes(p.read_bytes())
(out/'SOURCE_RECORDS.json').write_text(json.dumps(records,indent=2)+'\n')
(D/'RECOVERY_STATE_NFS.json').write_bytes((C/'RECOVERY_STATE_NFS.json').read_bytes())
with (D/'LIVE_PROGRESS.md').open('a') as f:f.write('\n- '+datetime.datetime.now(datetime.timezone.utc).isoformat()+': '+seg+' '+item['capture_attempt']+' accepted after closed native attribution and independent audit; '+str(a['accepted_dispatches'])+' exact dispatches, ranks '+json.dumps(a['rank_native_device_counts'])+', '+str(a['counter_values_recomputed'])+' counter values independently recomputed. Raw Release publication/offload status is tracked separately.\n')
(D/'outer_helpers_001'/Path(__file__).name).write_bytes(Path(__file__).read_bytes());print(json.dumps({'checkpoint_directory':str(out),'accepted_dispatches':a['accepted_dispatches'],'rank_native_device_counts':a['rank_native_device_counts']}))
