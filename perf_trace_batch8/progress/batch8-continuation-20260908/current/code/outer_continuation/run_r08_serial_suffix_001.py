"""Outer continuation scheduler. Separate gated subprocesses; no nested Goal."""
from pathlib import Path
import json,hashlib,subprocess,time,os,sys,signal,datetime
ROOT=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001')
CONTROL=Path('/public/home/accl15ptg7/run_R08_R10')
DEADLINE=datetime.datetime.fromisoformat('2026-09-08T12:18:09+00:00').timestamp()
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':sha(p)}
def save(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def phase(argv,log):
 assert time.time()<DEADLINE-120,'hard machine deadline'
 print('PHASE_START',datetime.datetime.now(datetime.timezone.utc).isoformat(),argv,flush=True)
 with log.open('x') as f:
  p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  try:rc=p.wait(timeout=max(1,DEADLINE-120-time.time()))
  except subprocess.TimeoutExpired:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=60)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
   raise
 assert rc==0,'phase failed: '+str(log)
 print('PHASE_EXIT',argv[2],rc,flush=True)
def main():
 assert read(ROOT/'validation/native_submission_analysis_cpu_gate.json')['status']=='complete'
 assert read(ROOT/'validation/runtime_capture_gate_007.json')['status']=='complete'
 for gate,key in [('validation/native_submission_analysis_cpu_gate.json','frozen_tools'),('validation/runtime_capture_gate_007.json','frozen_tools')]:
  for x in read(ROOT/gate)[key]:assert sha(x['path'])==x['sha256'],'tool drift'
 schedule=ROOT/'validation/serial_scheduler_001';schedule.mkdir()
 save(schedule/'START.json',{'pid':os.getpid(),'source':rec(Path(__file__)),'deadline_utc':'2026-09-08T12:18:09Z','scope':'R08 capture and CPU attribution only','first_existing_capture':'01__gqa6_pmc/attempt_005','no_successor_execution':True})
 accepted=[]
 for ordinal,unit in enumerate(read(ROOT/'plans/r08_capture_plan.json')['physical_captures']):
  seg=unit['segment_id'];attempt='attempt_005' if ordinal==0 else 'attempt_001';raw=ROOT/'raw/captures'/seg/attempt
  if ordinal==0:
   start=time.time()
   while not (raw/'execution_manifest.json').exists():
    assert time.time()-start<3000 and time.time()<DEADLINE-120,'first capture did not reach raw checkpoint'
    time.sleep(10)
  else:
   assert time.time()<DEADLINE-1500,'insufficient time for another bounded full capture plus analysis reserve'
   phase([sys.executable,'-B',str(ROOT/'tools/revision_013/run_capture.py'),'capture','--segment',seg,'--attempt',attempt],schedule/(seg+'.capture.log'))
  execution=read(raw/'execution_manifest.json');assert execution['all_started_processes_terminated'] and execution['workload']['status']=='complete'
  save(schedule/(seg+'.raw_checkpoint.json'),{'execution_manifest':rec(raw/'execution_manifest.json'),'status':'raw_checkpoint_complete'})
  out=ROOT/'normalized/captures'/seg/attempt/'revision_002'
  phase([sys.executable,'-B',str(ROOT/'tools/analysis_004/normalize_capture.py'),'--segment',seg,'--attempt',attempt,'--revision','revision_002'],schedule/(seg+'.normalize.log'))
  phase([sys.executable,'-B',str(ROOT/'tools/analysis_004/audit_capture.py'),'--normalization',str(out)],schedule/(seg+'.audit.log'))
  audit=read(out/'INDEPENDENT_AUDIT.json');assert audit['status']=='complete' and set(audit['rank_native_device_counts'])=={'0','1'}
  item={'segment_id':seg,'capture_attempt':attempt,'execution_manifest':rec(raw/'execution_manifest.json'),'normalization_manifest':rec(out/'NORMALIZATION_COMPLETE.json'),'independent_audit':rec(out/'INDEPENDENT_AUDIT.json')};accepted.append(item)
  save(schedule/(seg+'.accepted_checkpoint.json'),{'status':'accepted','item':item,'accepted_prefix_count':len(accepted),'complete_plan_count':12})
  print('CAPTURE_ACCEPTED',seg,'PREFIX',len(accepted),flush=True)
 save(ROOT/'normalized/accepted_captures.json',{'status':'complete','captures':accepted,'capture_plan':rec(ROOT/'plans/r08_capture_plan.json'),'scheduler':rec(Path(__file__)),'all_capture_and_attribution_processes_terminated':True})
 save(schedule/'COMPLETE.json',{'status':'complete','accepted_capture_count':len(accepted),'accepted_index':rec(ROOT/'normalized/accepted_captures.json'),'successor_execution_performed':False})
 print('ALL_R08_CAPTURES_ACCEPTED',len(accepted),flush=True)
if __name__=='__main__':main()
