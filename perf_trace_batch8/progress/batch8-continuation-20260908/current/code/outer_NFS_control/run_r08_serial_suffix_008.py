"""Outer serial resume after native PMC coverage failure; full accepted prefix reuse."""
from pathlib import Path
import json,hashlib,subprocess,time,os,sys,signal,datetime
ROOT=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');DEADLINE=datetime.datetime.fromisoformat('2026-09-08T20:18:09+00:00').timestamp();RUNTIME=ROOT/'raw/runtime_tools/revision_018';SCHEDULE=ROOT/'validation/serial_scheduler_008'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def rec(p):return {'path':str(p),'size':Path(p).stat().st_size,'sha256':sha(p)}
def save(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def phase(argv,log):
 assert time.time()<DEADLINE-120,'machine deadline';print('PHASE_START',datetime.datetime.now(datetime.timezone.utc).isoformat(),argv,flush=True)
 with log.open('x') as f:
  p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  try:rc=p.wait(timeout=max(1,DEADLINE-120-time.time()))
  except subprocess.TimeoutExpired:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=60)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
   raise
 assert rc==0,'phase failed '+str(log);print('PHASE_EXIT',argv[2],rc,flush=True)
def main():
 for gate in [ROOT/'raw/runtime_tools/runtime_capture_gate_011.json', ROOT/'validation/background_graph_analysis_CPU_gate_001.json']:
  g=read(gate);assert g['status']=='complete'
  for x in g['frozen_tools']:assert sha(x['path'])==x['sha256'],'frozen tool bytes'
 SCHEDULE.mkdir();save(SCHEDULE/'START.json',{'pid':os.getpid(),'source':rec(Path(__file__)),'deadline_utc':'2026-09-08T20:18:09Z','deadline_authorization':rec(Path('/public/home/accl15ptg7/run_R08_R10/MACHINE_TIME_EXTENSION_001.json')),'previous_scheduler':rec(ROOT/'validation/serial_scheduler_007/START.json'),'resume_reason':'reuse seven audited captures; retry capture08 after rank1 native pre-measured health failure without changing runtime or workload','native_prehealth_retry_authorization':rec(ROOT/'raw/runtime_tools/capture08_prehealth_retry_001.json'),'NFS_storage_authorization':rec(ROOT/'authorization/NFS_output_storage_authorization_001.json'),'user_storage_policy':rec(Path('/public/home/accl15ptg7/run_R08_R10/USER_STORAGE_POLICY_20260908.json')),'scope':'R08 captures and CPU attribution; no R09/R10 business execution'})
 accepted=[]
 for ordinal,unit in enumerate(read(ROOT/'plans/r08_capture_plan.json')['physical_captures']):
  seg=unit['segment_id']
  if ordinal<7:
   previous=read(ROOT/'validation/serial_scheduler_007'/(seg+'.accepted_checkpoint.json'));assert previous['status']=='accepted';item=previous['item']
   for key in ['execution_manifest','normalization_manifest','independent_audit']:assert sha(item[key]['path'])==item[key]['sha256'],'accepted prefix immutable'
   accepted.append(item);save(SCHEDULE/(seg+'.accepted_checkpoint.json'),{**previous,'reused_verified_prefix':True});continue
  attempt='attempt_002' if ordinal==7 else 'attempt_001';raw=ROOT/'raw/captures'/seg/attempt
  assert time.time()<DEADLINE-1800,'bounded full capture reserve'
  while True:
   fs=os.statvfs(ROOT);free=fs.f_bavail*fs.f_frsize
   if free>=10*(1<<30):break
   assert time.time()<DEADLINE-3600,'NFS publication/offload wait reached full-capture deadline reserve'
   print('WAITING_FOR_VERIFIED_RELEASE_OFFLOAD_SPACE',seg,free,flush=True);time.sleep(30)
  phase([sys.executable,'-B',str(RUNTIME/'run_capture.py'),'capture','--segment',seg,'--attempt',attempt],SCHEDULE/(seg+'.capture.log'))
  execution=read(raw/'execution_manifest.json');assert execution['status']=='raw_capture_complete_pending_exact_attribution' and execution['all_started_processes_terminated'] and execution['workload']['status']=='complete'
  save(SCHEDULE/(seg+'.raw_checkpoint.json'),{'status':'raw_checkpoint_complete','execution_manifest':rec(raw/'execution_manifest.json')})
  output=ROOT/'normalized/captures'/seg/attempt/'revision_002';phase([sys.executable,'-B',str(ROOT/'tools/analysis_007/normalize_capture.py'),'--segment',seg,'--attempt',attempt,'--revision','revision_002'],SCHEDULE/(seg+'.normalize.log'));phase([sys.executable,'-B',str(ROOT/'tools/analysis_007/audit_capture.py'),'--normalization',str(output)],SCHEDULE/(seg+'.audit.log'))
  audit=read(output/'INDEPENDENT_AUDIT.json');assert audit['status']=='complete' and set(audit['rank_native_device_counts'])=={'0','1'}
  item={'segment_id':seg,'capture_attempt':attempt,'execution_manifest':rec(raw/'execution_manifest.json'),'normalization_manifest':rec(output/'NORMALIZATION_COMPLETE.json'),'independent_audit':rec(output/'INDEPENDENT_AUDIT.json')};accepted.append(item);save(SCHEDULE/(seg+'.accepted_checkpoint.json'),{'status':'accepted','item':item,'accepted_prefix_count':len(accepted),'complete_plan_count':12});print('CAPTURE_ACCEPTED',seg,'PREFIX',len(accepted),flush=True)
 save(ROOT/'normalized/accepted_captures.json',{'status':'complete','captures':accepted,'capture_plan':rec(ROOT/'plans/r08_capture_plan.json'),'scheduler':rec(Path(__file__)),'all_capture_and_attribution_processes_terminated':True});save(SCHEDULE/'COMPLETE.json',{'status':'complete','accepted_capture_count':len(accepted),'accepted_index':rec(ROOT/'normalized/accepted_captures.json'),'successor_execution_performed':False});print('ALL_R08_CAPTURES_ACCEPTED',len(accepted),flush=True)
if __name__=='__main__':main()
