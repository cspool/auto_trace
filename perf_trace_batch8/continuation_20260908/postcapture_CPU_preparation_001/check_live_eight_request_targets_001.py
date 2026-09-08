"""Read-only early marker coverage; never substitutes closed native DB/PMC audit."""
from pathlib import Path
import json,hashlib,os,collections,sys,time
R=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');REFERENCE=R.parent.parent/'R07/resume-042/contract/r07_bound_target_sidecar.json'
def sha(b):return hashlib.sha256(b).hexdigest()
def snapshot(p):
 with p.open('rb') as f:n=os.fstat(f.fileno()).st_size;b=f.read(n)
 lines=b.splitlines();records=[]
 for i,line in enumerate(lines):
  try:records.append(json.loads(line))
  except json.JSONDecodeError:assert i==len(lines)-1 and not b.endswith(b'\n')
 return records,{'path':str(p),'captured_prefix_size':len(b),'captured_prefix_sha256':sha(b),'active_source_full_file_completion_claimed':False}
def main():
 seg,attempt=sys.argv[1:];root=R/'raw/captures'/seg/attempt;reference=REFERENCE.read_bytes();expected=collections.defaultdict(set)
 for x in json.loads(reference)['records']:
  if 'source_r06_target_id' in x:expected[x['request_id'],x['phase']].add(x['canonical_logical_selection_id'])
 observed=collections.defaultdict(list);sources=[];pids={}
 for p in sorted((root/'workload/overlay_events').glob('rank*/*.jsonl')):
  records,rec=snapshot(p);sources.append(rec)
  for x in records:
   if x['marker_kind']!='process':continue
   assert x['dp_rank']==x['physical_device_id'] and x['phase_occurrence']==1 and x['native_marker_transport'];observed[x['request_id'],x['phase']].append(x['canonical_logical_selection_id']);pids.setdefault(x['dp_rank'],set()).add(x['pid'])
 checks=[]
 for key,ids in sorted(expected.items()):
  actual=observed[key];checks.append({'request_id':key[0],'phase':key[1],'expected_targets':len(ids),'observed_marker_rows':len(actual),'missing_targets':sorted(ids-set(actual)),'unexpected_targets':sorted(set(actual)-ids),'duplicate_targets':len(actual)-len(set(actual))})
 passed=set(observed)==set(expected) and all(not x['missing_targets'] and not x['unexpected_targets'] and not x['duplicate_targets'] for x in checks) and set(pids)=={0,1} and all(len(x)==1 for x in pids.values())
 result={'status':'complete_live_marker_coverage' if passed else 'partial_or_invalid_live_marker_coverage','segment_id':seg,'attempt':attempt,'checks':checks,'expected_process_marker_count':sum(map(len,expected.values())),'observed_process_marker_count':sum(map(len,observed.values())),'eight_requests':len({k[0] for k in expected}),'rank_worker_PIDs':{str(k):sorted(v) for k,v in pids.items()},'source_prefixes':sources,'R07_reference':{'path':str(REFERENCE),'size':len(reference),'sha256':sha(reference)},'scope':'all declared R06 first-prefill/first-decode process targets, not every one of 1024 generated token invocations','read_only_no_native_calls':True,'closed_capture_accepted':False,'native_DB_and_PMC_correlation_audited':False,'created_realtime_ns':time.time_ns()};out=R/'raw/runtime_tools/live_eight_request_checks_001';out.mkdir(exist_ok=True);p=out/(seg+'.'+attempt+'.'+str(time.time_ns())+'.json')
 with p.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps({'status':result['status'],'requests':result['eight_requests'],'marker_rows':result['observed_process_marker_count'],'expected_rows':result['expected_process_marker_count'],'rank_worker_PIDs':result['rank_worker_PIDs'],'report':str(p)}),flush=True)
if __name__=='__main__':main()
