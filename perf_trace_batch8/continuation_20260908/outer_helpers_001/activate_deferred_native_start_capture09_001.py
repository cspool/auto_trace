"""Resume unchanged capture contract only after failed attempt processes are closed."""
from pathlib import Path
import json,hashlib,os,datetime
C=Path('/public/home/accl15ptg7/run_R08_R10');P=Path('/public/home/accl15ptg7/auto_trace');D=P/'perf_trace_batch8/continuation_20260908';R=P/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001';seg='09_chunk_gated_delta_rule_fwd_kernel_h_blockdim64_pmc_write';A=R/'raw/captures'/seg/'attempt_004'
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
assert not Path('/proc/841283').exists(),'previous serial scheduler still alive'
checkpoints=[]
for unit in read(R/'plans/r08_capture_plan.json')['physical_captures'][:8]:
 p=R/'validation/serial_scheduler_011'/(unit['segment_id']+'.accepted_checkpoint.json');x=read(p);assert x['status']=='accepted'
 for key in ['execution_manifest','normalization_manifest','independent_audit']:assert rec(Path(x['item'][key]['path']))==x['item'][key]
 checkpoints.append(rec(p))
proof=R/'raw/runtime_tools/capture09_deferred_start_retry_001.json';save(proof,{'status':'authorized_CPU_gated_deferred_native_start_same_workload_retry','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'failure':rec(A/'RAW_CAPTURE_FAILURE.json'),'native_health':rec(A/'control/PRE_MEASURED_NATIVE_PMC_HEALTH.json'),'tracee_cleanup':rec(A/'control/tracee_process_cleanup.json'),'all_previous_attempt_owned_process_groups_verified_closed':groups,'previous_worker_pids_verified_closed':workers,'previous_measured_requests_started':False,'previous_eight_accepted_captures_preserved':checkpoints,'previous_runtime_revisions_018_019_preserved':True,'new_runtime_revision_020_CPU_gate':rec(R/'raw/runtime_tools/runtime_capture_gate_013.json'),'analysis_007_unchanged':True,'new_attempt':'attempt_005','additional_warmups_or_altered_workload_within_attempt':False,'deadline_authorization':rec(C/'MACHINE_TIME_EXTENSION_002.json'),'reason':'four attempts lost one native PMC worker before measured requests; warmup Stop-Start alone failed; activate CPU-gated initial-off native collection until original warmups'})
gate=R/'raw/runtime_tools/runtime_capture_gate_013.json';g=read(gate);assert g['status']=='complete' and g['runtime_revision']=='revision_020'
for x in g['frozen_tools']:assert rec(Path(x['path']))==x
s=(C/'run_r08_serial_suffix_011.py').read_text().replace('validation/serial_scheduler_010','validation/serial_scheduler_011').replace("SCHEDULE=ROOT/'validation/serial_scheduler_011'","SCHEDULE=ROOT/'validation/serial_scheduler_012'").replace("RUNTIME=ROOT/'raw/runtime_tools/revision_019'","RUNTIME=ROOT/'raw/runtime_tools/revision_020'").replace('runtime_capture_gate_012.json','runtime_capture_gate_013.json').replace("attempt='attempt_004' if ordinal==8","attempt='attempt_005' if ordinal==8").replace('capture09_warmup_reset_retry_001.json','capture09_deferred_start_retry_001.json').replace('using CPU-gated runtime019 native warmup reset and unchanged workload','using CPU-gated runtime020 deferred native startup and unchanged measured workload');compile(s,str(C/'run_r08_serial_suffix_012.py'),'exec')
with (C/'run_r08_serial_suffix_012.py').open('x') as f:f.write(s)
out=D/'capture09_failed_attempt004_activate_deferred_native_start_001';out.mkdir();sources=[proof,A/'RAW_CAPTURE_FAILURE.json',A/'raw_inventory_at_exit.json',A/'control/PRE_MEASURED_NATIVE_PMC_HEALTH.json',A/'control/tracee_process_cleanup.json',*sorted((A/'control/pmc_gate_events').glob('warmup_start.*.json')),*sorted((A/'logs').glob('*.log')),gate]
for p in sources:assert p.stat().st_size<10_000_000;(out/p.name).write_bytes(p.read_bytes())
(out/'SOURCE_RECORDS.json').write_text(json.dumps([rec(p) for p in sources],indent=2)+'\n')
for n in ['run_r08_serial_suffix_012.py','activate_deferred_native_start_capture09_001.py','checkpoint_measured_start_001.py']:(D/'outer_helpers_001'/n).write_bytes((C/n).read_bytes())
with (D/'LIVE_PROGRESS.md').open('a') as f:f.write('\n- '+datetime.datetime.now(datetime.timezone.utc).isoformat()+': Capture09 attempt004 rejected before measurement: rank0 PMC remained empty despite successful Stop and Start transitions. All groups closed and accepted eight-capture prefix reverified. Scheduler012 activates frozen runtime020 for attempt005: native PMC/trace initially off, activated before original warmups. Startup native trace before warmups is intentionally omitted; original measured workload, DP2 ordering, full declared target coverage and analysis007 remain mandatory.\n')
print(json.dumps({'retry_proof':str(proof),'next_scheduler':str(C/'run_r08_serial_suffix_012.py'),'closed_groups':groups,'runtime':'revision_020','unchanged_analysis':'analysis_007'}))
