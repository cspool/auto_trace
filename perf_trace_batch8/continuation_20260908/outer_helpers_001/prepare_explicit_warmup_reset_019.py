"""Prepare native Stop/Start before original warmup; CPU verification only."""
from pathlib import Path
import json,hashlib,shutil,os,importlib.util,types,datetime
C=Path('/public/home/accl15ptg7/run_R08_R10');R=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');B=R/'raw/runtime_tools';OLD=B/'revision_018';NEW=B/'revision_019'
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def save(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
previous=json.loads((B/'runtime_capture_gate_011.json').read_text());assert previous['status']=='complete'
for x in previous['frozen_tools']:assert rec(Path(x['path']))==x
shutil.copytree(OLD,NEW,ignore=shutil.ignore_patterns('__pycache__'))
for p in NEW.iterdir():
 if p.is_file() and p.suffix in ['.py','.sh']:p.write_text(p.read_text().replace('/revision_018/','/revision_019/'))
p=NEW/'run_capture.py';p.write_text(p.read_text().replace('runtime_capture_gate_011.json','runtime_capture_gate_012.json'))
p=NEW/'r08_pmc_gate.py';s=p.read_text();old='''        transition = _hip_call("hipProfilerStart")
        payload = _event_payload("warmup_native_start", rank)''';new='''        # Establish a real off-to-on native transition after model initialization.
        # This runs once before the existing original warmup, never adds a request.
        reset_transition = _hip_call("hipProfilerStop")
        transition = _hip_call("hipProfilerStart")
        payload = _event_payload("warmup_native_start", rank)
        payload.update(profiler_reset_stop_transition=reset_transition,
                       native_off_to_on_reset_before_original_warmup=True)''';assert s.count(old)==1;s=s.replace(old,new).replace('native_initially_on_explicit_warmup_and_measured_start_terminal_stop','native_initially_on_warmup_stop_start_reset_measured_start_terminal_stop');p.write_text(s)
for p in NEW.glob('*.py'):compile(p.read_text(),str(p),'exec')
spec=importlib.util.spec_from_file_location('warmup_reset_CPU_fixture',NEW/'r08_pmc_gate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);manifest=json.loads((R.parent.parent/'R01/contract/request_selection.json').read_text());ids=[x['request_id'] for x in manifest['records']];assert len(ids)==8;m._WARMUP_REQUEST_IDS=[f'r08-pmc-warmup-{i+1:03d}-{ids[i]}' for i in range(2)];m._MEASURED_REQUEST_IDS=set(ids)
f=C/'warmup_reset_CPU_fixture_001';f.mkdir();os.environ.update(QWEN_DCU_R08_PMC_GATE_EVENT_ROOT=str(f),QWEN_DCU_R08_PMC_GATE_STOP_FILE=str(f/'stop.json'),QWEN_DCU_R08_RUNTIME_ATTEMPT_ID='CPU_FIXTURE_ONLY',QWEN_DCU_R08_SEGMENT_ID='CPU_FIXTURE_ONLY');calls=[];m._hip_call=lambda op,*args:calls.append(op) or {'operation':op,'status':0,'CPU_mock':True};m._original_native_push=lambda name:None;m._ensure_watcher=lambda:None
out=lambda value:types.SimpleNamespace(num_scheduled_tokens={value:4096})
for rank in [0,1]:
 m._process_pid=None;m._warmup_start_pid=None;runner=types.SimpleNamespace(device=types.SimpleNamespace(index=rank));before=len(calls);m._start_before_original_warmup(runner,out('unrelated'));assert len(calls)==before
 stable=m._WARMUP_REQUEST_IDS[rank];assert m._warmup_identifier('chatcmpl-'+stable+'-abcd1234')==stable and m._warmup_identifier(stable+'-bad') is None
 m._start_before_original_warmup(runner,out('chatcmpl-'+stable+'-abcd1234'));m._start_before_original_warmup(runner,out(stable));assert calls[before:]==['hipProfilerStop','hipProfilerStart'] and not m._started
 event=json.loads((f/f'warmup_start.rank{rank}.pid{os.getpid()}.json').read_text());assert event['profiler_reset_stop_transition']['operation']=='hipProfilerStop' and event['profiler_transition']['operation']=='hipProfilerStart' and event['added_requests']==event['added_model_executions']==0 and event['native_off_to_on_reset_before_original_warmup']
 m._r01=types.SimpleNamespace(_context={'dp_rank':rank,'participants':[{'request_id':ids[rank]}]});m._native_push('qwen_dcu.layer00.prefill');assert calls[before:]==['hipProfilerStop','hipProfilerStart','hipProfilerStart'] and m._started
before=len(calls);m._process_pid=None;m._warmup_start_pid=None
try:m._start_before_original_warmup(types.SimpleNamespace(device=types.SimpleNamespace(index=1)),out(m._WARMUP_REQUEST_IDS[0]))
except RuntimeError:pass
else:raise AssertionError('wrong-rank warmup accepted')
assert len(calls)==before
# Native reset failure cannot proceed to Start or mark the worker initialized.
m._process_pid=None;m._warmup_start_pid=None;failure_calls=[]
def fail_stop(op,*args):
 failure_calls.append(op)
 if op=='hipProfilerStop':raise RuntimeError('CPU simulated native reset failure')
 raise AssertionError('must not Start after failed Stop')
m._hip_call=fail_stop
try:m._start_before_original_warmup(types.SimpleNamespace(device=types.SimpleNamespace(index=0)),out(m._WARMUP_REQUEST_IDS[0]))
except RuntimeError:pass
else:raise AssertionError('native reset failure ignored')
assert failure_calls==['hipProfilerStop'] and m._warmup_start_pid is None and not m._started
# Core workload, observed admission order, capture plans and independent analysis are unchanged.
unchanged=['r08_admission_order.py','workload_driver.py','launch_vllm.py','source_abi_probe.py']
for name in unchanged:
 if (OLD/name).exists():assert (OLD/name).read_bytes()==(NEW/name).read_bytes()
failures=[B/'capture09_prehealth_retry_001.json',B/'capture09_prehealth_retry_002.json'];probe=B/'native_fresh_exec_pmc_write_recheck_002/RESULT.json';q=json.loads(probe.read_text());assert q['status']=='complete' and q['native_device_counts']=={'0':4,'1':4}
gate={'status':'complete','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runtime_revision':'revision_019','previous_runtime_gate':rec(B/'runtime_capture_gate_011.json'),'frozen_tools':[rec(p) for p in sorted(NEW.iterdir()) if p.is_file()],'outer_preparation':rec(Path(__file__)),'hypothesis':'A real per-worker native off-to-on transition after full model initialization may reinitialize counter collection where Start alone leaves an empty PMC file. Short model-free Stop/Start probing passed on both devices, but full-model root cause and repair remain unproven.','root_cause_proven':False,'actual_full_model_validation_required':True,'candidate_not_activated_by_this_preparation':True,'prior_closed_failure_retry_evidence':[rec(p) for p in failures],'model_free_probe':rec(probe),'CPU_fixture':{'native_device_calls':0,'both_ranks_native_Stop_Start_once_before_original_warmup':True,'existing_measured_Start_unchanged':True,'wrong_rank_rejected_before_native_calls':True,'unrelated_and_malformed_IDs_ignored':True,'native_Stop_failure_prevents_Start_and_activation':True},'original_two_warmups_and_eight_measured_requests_unchanged':True,'no_added_model_requests_or_model_executions':True,'exact_R01_R07_marker_boundaries_unchanged':True,'observed_R07_admission_order_unchanged':True,'pre_measured_two_worker_native_health_still_required':True,'full_eight_request_and_native_attribution_audits_still_required':True,'capture_plan_sha256':rec(R/'plans/r08_capture_plan.json')['sha256'],'active_capture_interrupted':False};save(B/'runtime_capture_gate_012.json',gate);print(json.dumps({'status':'CPU_gate_complete_candidate_only','frozen_tool_count':len(gate['frozen_tools']),'gate':str(B/'runtime_capture_gate_012.json'),'native_GPU_calls':0}))
