from pathlib import Path
import json,hashlib,shutil,os,importlib.util,types,sys
C=Path('/public/home/accl15ptg7/run_R08_R10');R=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');base=R/'raw/runtime_tools';old=base/'revision_016';new=base/'revision_017'
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def save(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n')
shutil.copytree(old,new,ignore=shutil.ignore_patterns('__pycache__'))
for p in new.iterdir():
 if p.is_file() and p.suffix in ['.py','.sh']:p.write_text(p.read_text().replace('/revision_016/','/revision_017/'))
p=new/'run_capture.py';p.write_text(p.read_text().replace('runtime_capture_gate_009.json','runtime_capture_gate_010.json'))
p=new/'r08_pmc_gate.py';s=p.read_text();start=s.index('"""');end=s.index('"""',start+3)+3;s=s[:start]+'''"""Explicit per-worker native start before the original warmup and measured batch.

Warmup native rows remain outside the unchanged exact R07 logical selection.
The original two warmups and full eight measured requests are preserved.
"""'''+s[end:]
s=s.replace('_hip_runtime: Any = None','_hip_runtime: Any = None\n_warmup_start_pid: int | None = None')
pos=s.index('\ndef _native_push(')
newhook='''
def _warmup_identifier(internal_id: str) -> str | None:
    candidate = internal_id[len("chatcmpl-"):] if internal_id.startswith("chatcmpl-") else internal_id
    for stable in _WARMUP_REQUEST_IDS:
        if candidate == stable:
            return stable
        if candidate.startswith(stable + "-"):
            suffix = candidate[len(stable)+1:]
            if len(suffix) == 8 and all(c in "0123456789abcdef" for c in suffix):
                return stable
    return None


def _start_before_original_warmup(runner: Any, scheduler_output: Any) -> None:
    global _warmup_start_pid
    identifiers = {str(x) for x in scheduler_output.num_scheduled_tokens}
    warmups = {x for x in (_warmup_identifier(x) for x in identifiers) if x is not None}
    if not warmups:
        return
    _ensure_process_initialized()
    with _lock:
        if _warmup_start_pid == os.getpid():
            return
        rank = int(runner.device.index)
        if rank not in (0, 1) or len(warmups) != 1 or _WARMUP_REQUEST_IDS[rank] not in warmups:
            raise RuntimeError("Original warmup request/rank mismatch")
        if _started or _required_path("QWEN_DCU_R08_PMC_GATE_STOP_FILE").exists():
            raise RuntimeError("Warmup native start after measured boundary")
        transition = _hip_call("hipProfilerStart")
        payload = _event_payload("warmup_native_start", rank)
        payload.update(participant_request_ids=sorted(warmups),profiler_transition=transition,
                       added_requests=0,added_model_executions=0,canonical_measured_window_started=False)
        path = _required_path("QWEN_DCU_R08_PMC_GATE_EVENT_ROOT") / f"warmup_start.rank{rank}.pid{os.getpid()}.json"
        _write_json_x(path,payload)
        _warmup_start_pid = os.getpid()


def _patch_original_warmup_execution() -> None:
    from vllm.v1.worker.gpu_model_runner import GPUModelRunner
    current = GPUModelRunner.execute_model
    if getattr(current,"_qwen_dcu_r08_explicit_warmup_start",False):
        return
    @functools.wraps(current)
    def execute_model(runner: Any, scheduler_output: Any, *args: Any, **kwargs: Any) -> Any:
        _start_before_original_warmup(runner,scheduler_output)
        return current(runner,scheduler_output,*args,**kwargs)
    execute_model._qwen_dcu_r08_explicit_warmup_start=True
    GPUModelRunner.execute_model=execute_model

'''
s=s[:pos]+newhook+s[pos:]
s=s.replace('global _r01, _original_native_push, _installed, _MEASURED_REQUEST_IDS, _process_pid','global _r01, _original_native_push, _installed, _MEASURED_REQUEST_IDS, _WARMUP_REQUEST_IDS, _process_pid')
s=s.replace('    _r01 = r01_module','    _WARMUP_REQUEST_IDS = [f"r08-pmc-warmup-{i+1:03d}-{manifest[\'records\'][i][\'request_id\']}" for i in range(2)]\n    _r01 = r01_module')
s=s.replace('    _patch_worker_device_initialization()','    _patch_worker_device_initialization()\n    _patch_original_warmup_execution()')
s=s.replace('native_initially_on_explicit_measured_start_and_terminal_stop','native_initially_on_explicit_warmup_and_measured_start_terminal_stop').replace('Reset marker state and disable PMC after a multiprocessing fork.','Reset logical marker state after a multiprocessing fork.');p.write_text(s)
for p in new.glob('*.py'):compile(p.read_text(),str(p),'exec')
# Execute the production warmup gate with native calls replaced by a recorder.
spec=importlib.util.spec_from_file_location('warmup_gate_cpu_fixture',new/'r08_pmc_gate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
manifest=json.loads((R.parents[2]/'R01/contract/request_selection.json').read_text()) if False else json.loads((R.parent.parent/'R01/contract/request_selection.json').read_text())
ids=[x['request_id'] for x in manifest['records']];m._WARMUP_REQUEST_IDS=[f'r08-pmc-warmup-{i+1:03d}-{ids[i]}' for i in range(2)];m._MEASURED_REQUEST_IDS=set(ids)
f=C/'warmup_start_CPU_fixture_001';f.mkdir();os.environ.update(QWEN_DCU_R08_PMC_GATE_EVENT_ROOT=str(f),QWEN_DCU_R08_PMC_GATE_STOP_FILE=str(f/'stop.json'),QWEN_DCU_R08_RUNTIME_ATTEMPT_ID='CPU_FIXTURE_ONLY',QWEN_DCU_R08_SEGMENT_ID='CPU_FIXTURE_ONLY')
calls=[];m._hip_call=lambda op,*args:calls.append(op) or {'operation':op,'status':0,'CPU_mock':True};m._original_native_push=lambda name:None;m._ensure_watcher=lambda:None
for rank in [0,1]:
 m._process_pid=None;m._warmup_start_pid=None;runner=types.SimpleNamespace(device=types.SimpleNamespace(index=rank));out=lambda value:types.SimpleNamespace(num_scheduled_tokens={value:4096})
 m._start_before_original_warmup(runner,out('unrelated'));assert len(calls)==rank*2
 stable=m._WARMUP_REQUEST_IDS[rank];assert m._warmup_identifier('chatcmpl-'+stable+'-abcd1234')==stable
 assert m._warmup_identifier(stable+'-bad') is None
 m._start_before_original_warmup(runner,out('chatcmpl-'+stable+'-abcd1234'));m._start_before_original_warmup(runner,out(stable));assert len(calls)==rank*2+1 and not m._started
 m._r01=types.SimpleNamespace(_context={'dp_rank':rank,'participants':[{'request_id':ids[rank]}]});m._native_push('qwen_dcu.layer00.prefill');assert len(calls)==rank*2+2 and m._started
m._process_pid=None;m._warmup_start_pid=None
try:m._start_before_original_warmup(types.SimpleNamespace(device=types.SimpleNamespace(index=1)),out(m._WARMUP_REQUEST_IDS[0]))
except RuntimeError:pass
else:raise AssertionError('wrong-rank warmup accepted')
raw=R/'raw/captures/04_triton_red_fused__to_copy_add_mean_mul_pow_rsqrt_0_pmc/attempt_001';failure=json.loads((raw/'RAW_CAPTURE_FAILURE.json').read_text());assert failure['native_health']['status']=='failed';pids=[failure['profiler_cleanup']['leader_pid']]
for x in json.loads((raw/'control/tracee_process_cleanup.json').read_text()).values():pids.extend([x['leader_pid'],*x['remaining_group_members_before_final_cleanup']])
for p in (raw/'workload/r01_events').glob('rank*/*.jsonl'):pids.append(int(p.name.split('.')[1]))
assert all(not Path('/proc',str(pid)).exists() for pid in pids)
gate={'status':'complete','runtime_revision':'revision_017','previous_NFS_runtime_gate':rec(R/'validation/NFS_runtime_CPU_gate_001.json'),'prior_capture_failure':rec(raw/'RAW_CAPTURE_FAILURE.json'),'prior_pids_verified_terminated':pids,'hypothesis':'explicit hipProfilerStart in each original warmup worker before its scheduled model execution removes reliance on initially-on native state; spawn alone has failed again','root_cause_proven':False,'no_added_model_requests_or_executions':True,'original_two_warmups_and_eight_measured_requests_unchanged':True,'exact_R01_R07_marker_boundaries_unchanged':True,'pre_measured_two_worker_native_health_still_required':True,'CPU_fixture':{'native_device_calls':0,'both_ranks_start_once_before_warmup_then_again_at_measured_boundary':True,'wrong_rank_rejected':True,'unrelated_and_malformed_IDs_ignored':True},'capture_plan_sha256':rec(R/'plans/r08_capture_plan.json')['sha256'],'frozen_tools':[rec(p) for p in sorted(new.iterdir()) if p.is_file()]}
save(base/'runtime_capture_gate_010.json',gate);print('EXPLICIT_WARMUP_START_CPU_GATE_COMPLETE',len(gate['frozen_tools']))
