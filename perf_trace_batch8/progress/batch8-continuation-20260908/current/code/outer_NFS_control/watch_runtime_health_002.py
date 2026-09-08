"""Read-only capture observations plus durable outer recovery state, every minute."""
from pathlib import Path
import json,time,os,datetime
C=Path('/public/home/accl15ptg7/run_R08_R10');R=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');RUN=R.parents[2];DEADLINE=datetime.datetime.fromisoformat('2026-09-08T20:18:09+00:00').timestamp()
def read(p):return json.loads(Path(p).read_text())
def observe():
 accepted={}
 for p in list((R/'validation').glob('serial_scheduler_*/*.accepted_checkpoint.json'))+list((R/'raw/runtime_tools').glob('serial_scheduler_*/*.accepted_checkpoint.json')):x=read(p)['item'];accepted[x['segment_id']]=x
 contracts=list((R/'raw/captures').glob('*/*/control/capture_contract.json'));newest=max(contracts,key=lambda p:read(p)['started_realtime_ns']);root=newest.parent.parent;x=read(newest);phase='model_initialization';p=root/'control/live_collector_exec.json';native=[]
 if p.exists():
  d=Path(read(p)['injected_output_directory'])
  for p in sorted((root/'workload/r01_events').glob('rank*/events.*.jsonl')):
   with p.open() as f:i=json.loads(f.readline())
   q=d/('pmc_results_'+str(i['pid'])+'.txt');size=q.stat().st_size if q.exists() else 0;native.append({'rank':i['dp_rank'],'worker_pid':i['pid'],'PMC_bytes':size,'worker_alive':Path('/proc',str(i['pid'])).exists()})
 if list((root/'control/pmc_gate_events').glob('warmup_start.*.json')):phase='original_two_warmups'
 health=read(root/'control/PRE_MEASURED_NATIVE_PMC_HEALTH.json') if (root/'control/PRE_MEASURED_NATIVE_PMC_HEALTH.json').exists() else None
 if health:phase='measured_batch' if health['status']=='complete' else 'failed_pre_measured_native_health'
 if (root/'workload/driver.json').exists():phase='workload_complete_collector_export_or_raw_sealing'
 if (root/'execution_manifest.json').exists():phase='raw_complete_attribution_or_audit_pending'
 if x['segment']['segment_id'] in accepted and accepted[x['segment']['segment_id']]['capture_attempt']==root.name:phase='accepted'
 if (root/'RAW_CAPTURE_FAILURE.json').exists():phase='failed_not_accepted'
 tokens={}
 if health and health['status']=='complete':
  for p in sorted((root/'workload/r01_events').glob('rank*/events.*.jsonl')):
   with p.open('rb') as f:f.seek(max(0,p.stat().st_size-131072));tail=f.read(131072)
   for line in reversed(tail.splitlines()):
    try:event=json.loads(line)
    except json.JSONDecodeError:continue
    if event.get('participants'):
     for participant in event['participants']:tokens[participant['request_id']]=participant['num_output_tokens_before_step']
     break
 fs=os.statvfs(C);offloads=list((R/'raw/runtime_tools/remote_release_offloads_001').glob('*.complete.json'));result={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'accepted_R08':len(accepted),'planned_R08':12,'current_capture':str(root.relative_to(R/'raw/captures')),'current_phase':phase,'native_workers':native,'pre_measured_health':health['status'] if health else 'pending','measured_request_token_progress':tokens,'NFS_available_GiB':round(fs.f_bavail*fs.f_frsize/(1<<30),2),'temporarily_evicted_bytes':sum(read(p)['evicted_bytes'] for p in offloads),'remaining_machine_hours':round((DEADLINE-time.time())/3600,2),'completed_stages':[stage for stage in ['R08','R09','R10'] if (RUN/'handoffs'/(stage+'.continuation.json')).exists()]}
 state=read(C/'RECOVERY_STATE_NFS.json');state.update(current_capture=result['current_capture'],accepted_prefix_count=len(accepted),current_capture_phase=phase,latest_health_observation=result,home_storage_available_gib=result['NFS_available_GiB'],R09_R10_actual_execution_started=(RUN/'artifacts/R09/continuation_001/authorization/assignment.json').exists());tmp=C/'RECOVERY_STATE_NFS.monitor.partial';tmp.write_text(json.dumps(state,indent=2)+'\n');os.replace(tmp,C/'RECOVERY_STATE_NFS.json');print(json.dumps(result,separators=(',',':')),flush=True)
while time.time()<DEADLINE:
 try:observe()
 except Exception as error:print('OBSERVATION_RETRY',type(error).__name__,flush=True)
 for _ in range(60):
  if (C/'STOP_RUNTIME_HEALTH_WATCHDOG').exists():raise SystemExit(0)
  time.sleep(1)
