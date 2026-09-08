"""Outer checkpoint of closed client results; never promotes native attribution."""
from pathlib import Path
import json,hashlib,datetime,os,shutil,sys
P=Path('/public/home/accl15ptg7/auto_trace');R=P/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001';seg,attempt=sys.argv[1:]
assert seg in {x['segment_id'] for x in json.loads((R/'plans/r08_capture_plan.json').read_text())['physical_captures']}
assert attempt.startswith('attempt_') and attempt[8:].isdigit()
a=R/'raw/captures'/seg/attempt;driver=a/'workload/driver.json';p=a/'workload/request_results.json';d=json.loads(driver.read_text());rows=json.loads(p.read_text())['results']
assert len(rows)==8 and all(x['http_status']==200 and x['completion_tokens']==1024 and x['error'] is None for x in rows)
assert d['completed']==8 and d['failed']==0 and [x['request_id'] for x in rows]==d['dispatch']['expected_request_write_order']
assert len(d['pmc_gate']['stop_events'])==2 and d['pmc_gate']['rank_coverage']==[0,1]
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
proof={'status':'all_eight_workload_requests_complete_pending_native_export_and_attribution','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'segment_id':seg,'attempt':attempt,'completed_requests':[{k:x[k] for k in ['request_id','data_parallel_rank_requested','http_status','completion_tokens','error']} for x in rows],'total_completion_tokens':sum(x['completion_tokens'] for x in rows),'request_results':rec(p),'driver':rec(driver),'measured_duration_seconds':d['dispatch']['batch_duration_ns']/1e9,'native_stop_events':d['pmc_gate']['stop_events'],'native_export_accepted':False,'observer_code':rec(Path(__file__))}
folder=R/'raw/runtime_tools/workload_completion_checkpoints_001';folder.mkdir(exist_ok=True);p=folder/(seg+'.'+attempt+'.json')
with p.open('x') as f:json.dump(proof,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
o=P/'perf_trace_batch8/continuation_20260908'/('capture'+seg[:2]+'_'+attempt+'_workload_completion_001');o.mkdir()
for q in [p,driver]+[Path(x['path']) for x in d['pmc_gate']['stop_events']]:shutil.copy2(q,o/q.name)
with (o.parent/'LIVE_PROGRESS.md').open('a') as f:f.write('\n'+d['finished_utc']+': Capture '+seg[:2]+' '+attempt+' completed all eight original measured requests, HTTP 200 and 1024 tokens each, total 8192, zero failed requests; both native rank stop events are retained. Measured replay duration '+str(round(proof['measured_duration_seconds'],3))+' seconds is diagnostic only, not R07 observed latency. Native export and independent attribution are still required.\n')
print(json.dumps({'checkpoint':str(p),'remote_commit_directory':str(o),'measured_seconds':proof['measured_duration_seconds']}))
