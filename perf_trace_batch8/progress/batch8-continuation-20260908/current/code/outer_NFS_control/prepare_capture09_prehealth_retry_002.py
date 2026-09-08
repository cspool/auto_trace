"""Resume unchanged capture contract only after failed attempt processes are closed."""
from pathlib import Path
import json,hashlib,os,datetime
C=Path('/public/home/accl15ptg7/run_R08_R10');P=Path('/public/home/accl15ptg7/auto_trace');D=P/'perf_trace_batch8/continuation_20260908';R=P/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001';seg='09_chunk_gated_delta_rule_fwd_kernel_h_blockdim64_pmc_write';A=R/'raw/captures'/seg/'attempt_002'
def read(p):return json.loads(p.read_text())
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def save(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
f=read(A/'RAW_CAPTURE_FAILURE.json');h=read(A/'control/PRE_MEASURED_NATIVE_PMC_HEALTH.json');cleanup=read(A/'control/tracee_process_cleanup.json');assert f['status']=='failed_not_accepted' and h['status']=='failed' and h['reason']=='empty native PMC worker file before measured requests'
assert not (A/'workload/driver.json').exists() and not (A/'control/tracee_workload_complete.json').exists() and not list((A/'control/admission_order').glob('*.json'))
groups=[f['profiler_cleanup']['leader_pid'],cleanup['service']['leader_pid'],cleanup['workload']['leader_pid']];workers=[]
for p in (A/'workload/r01_events').glob('rank*/events.*.jsonl'):
 with p.open() as src:workers.append(json.loads(src.readline())['pid'])
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:t=(p/'stat').read_text().split(') ',1)[1].split()
 except (OSError,IndexError):continue
 assert int(t[2]) not in groups and int(p.name) not in workers,'failed owned process still alive'
assert not Path('/proc/806642').exists(),'previous serial scheduler still alive'
checkpoints=[]
for unit in read(R/'plans/r08_capture_plan.json')['physical_captures'][:8]:
 p=R/'validation/serial_scheduler_009'/(unit['segment_id']+'.accepted_checkpoint.json');x=read(p);assert x['status']=='accepted'
 for key in ['execution_manifest','normalization_manifest','independent_audit']:assert rec(Path(x['item'][key]['path']))==x['item'][key]
 checkpoints.append(rec(p))
proof=R/'raw/runtime_tools/capture09_prehealth_retry_002.json';save(proof,{'status':'authorized_same_contract_bounded_retry','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'failure':rec(A/'RAW_CAPTURE_FAILURE.json'),'native_health':rec(A/'control/PRE_MEASURED_NATIVE_PMC_HEALTH.json'),'tracee_cleanup':rec(A/'control/tracee_process_cleanup.json'),'all_previous_attempt_owned_process_groups_verified_closed':groups,'previous_worker_pids_verified_closed':workers,'previous_measured_requests_started':False,'previous_eight_accepted_captures_preserved':checkpoints,'runtime_revision_018_unchanged':True,'analysis_007_unchanged':True,'new_attempt':'attempt_003','additional_warmups_or_altered_workload_within_attempt':False,'deadline_authorization':rec(C/'MACHINE_TIME_EXTENSION_002.json'),'reason':'rank0 native PMC empty despite successful warmup native Start; preserve complete failure and retry original service initialization'})
probe=R/'raw/runtime_tools/native_fresh_exec_pmc_write_recheck_002/RESULT.json';q=read(probe);assert q['status']=='complete' and q['native_device_counts']=={'0':4,'1':4} and q['all_started_processes_terminated'];save(R/'raw/runtime_tools/capture09_third_attempt_probe_admission_001.json',{'status':'complete_model_free_counter_recheck_only','probe':rec(probe),'native_retry_authorization':rec(proof),'model_free_probe_is_not_measured_capture_evidence':True,'runtime_configuration_unchanged':True})
s=(C/'run_r08_serial_suffix_009.py').read_text().replace('validation/serial_scheduler_008','validation/serial_scheduler_009').replace("SCHEDULE=ROOT/'validation/serial_scheduler_009'","SCHEDULE=ROOT/'validation/serial_scheduler_010'").replace("attempt='attempt_002' if ordinal==8","attempt='attempt_003' if ordinal==8").replace('capture09_prehealth_retry_001.json','capture09_prehealth_retry_002.json');compile(s,str(C/'run_r08_serial_suffix_010.py'),'exec')
with (C/'run_r08_serial_suffix_010.py').open('x') as f:f.write(s)
out=D/'capture09_failed_prehealth_attempt002_retry_002';out.mkdir();sources=[proof,A/'RAW_CAPTURE_FAILURE.json',A/'raw_inventory_at_exit.json',A/'control/PRE_MEASURED_NATIVE_PMC_HEALTH.json',A/'control/tracee_process_cleanup.json',*sorted((A/'control/pmc_gate_events').glob('warmup_start.*.json')),*sorted((A/'logs').glob('*.log')),R/'raw/runtime_tools/capture09_attempt_002_empty_pmc_native_diagnostic_001.json',R/'raw/runtime_tools/capture09_attempt002_process_library_observation_001.json',R/'raw/runtime_tools/capture09_attempt_001_native_profiler_transition_query_001.json',R/'raw/runtime_tools/capture09_third_attempt_probe_admission_001.json']
for p in sources:assert p.stat().st_size<10_000_000;(out/p.name).write_bytes(p.read_bytes())
(out/'SOURCE_RECORDS.json').write_text(json.dumps([rec(p) for p in sources],indent=2)+'\n')
sub=out/'model_free_native_probe';sub.mkdir()
for p in probe.parent.iterdir():
 if p.is_file() and p.stat().st_size<10_000_000:(sub/p.name).write_bytes(p.read_bytes())
for n in ['run_r08_serial_suffix_010.py','prepare_capture09_prehealth_retry_002.py','probe_fresh_exec_pmc_write_recheck_002.py','query_closed_native_profiler_calls_001.py']:(D/'outer_helpers_001'/n).write_bytes((C/n).read_bytes())
with (D/'LIVE_PROGRESS.md').open('a') as f:f.write('\n- '+datetime.datetime.now(datetime.timezone.utc).isoformat()+': Capture09 attempt002 rejected before measured requests because rank0 PMC remained empty; rank1 had positive counters. All failed process groups closed. A separate model-free fresh-interpreter PMC write recheck passed exactly four native gqa6 dispatches per device. This does not prove the full-model root cause. Scheduler010 retries unchanged runtime018 with attempt003; both prior failed attempts remain preserved.\n')
print(json.dumps({'retry_proof':str(proof),'next_scheduler':str(C/'run_r08_serial_suffix_010.py'),'closed_groups':groups,'model_free_probe':q['native_device_counts']}))
