"""Freeze independent native worker sessions after native and CPU gates."""
from pathlib import Path
import hashlib, json, shutil, os, importlib.util, types, sys, datetime, ast

C=Path('/public/home/accl15ptg7/run_R08_R10')
P=Path('/public/home/accl15ptg7/auto_trace')
R=P/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001'
B=R/'raw/runtime_tools';OLD=B/'revision_018';NEW=B/'revision_021'

def rec(p):
    data=Path(p).read_bytes()
    return {'path':str(p),'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}

def save(p,x):
    with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())

previous=json.loads((B/'runtime_capture_gate_011.json').read_text())
for item in previous['frozen_tools']:assert rec(Path(item['path']))==item
probes=[]
for name in ['native_PMC_independent_overlap_probe_020','native_PMC_independent_dual_context_probe_021','native_PMC_mp_transport_marker_probe_023','native_PMC_supervised_transport_probe_024']:
    p=B/name/'RESULT.json';x=json.loads(p.read_text())
    assert x.get('all_workers_recorded',x.get('status')=='complete')
    probes.append(rec(p))
union_gate=B/'native_session_union_CPU_gate_002/RESULT.json';assert json.loads(union_gate.read_text())['status']=='complete_CPU_gate'
executor=P/'pra2026-bh408-gqa-page784-k5120-batch8/vllm/v1/executor/multiproc_executor.py'
for p in NEW.glob('*.py'):compile(p.read_text(),str(p),'exec')
for name in ['r08_pmc_gate.py','r08_admission_order.py','r08_workload_driver.py','r08_process_overlay.py','r08_memory_profile.py','launch_vllm.py','source_abi_probe.py']:assert (OLD/name).read_bytes()==(NEW/name).read_bytes()
# Exercise the production launcher wrapper without importing torch or vLLM.
spec=importlib.util.spec_from_file_location('collector_CPU_fixture',NEW/'r08_worker_collectors.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
fixture=B/'independent_worker_collectors_CPU_fixture_003';fixture.mkdir();calls=[]
fake_native=types.ModuleType('r08_native');fake_native.ROOT=R;fake_native.TARGET=P/'pra2026-bh408-gqa-page784-k5120-batch8'
fake_native.collector_argv=lambda mode,token,unit,tracee,**kw: calls.append({'mode':mode,'token':token,'trace':kw['trace'],'disabled':kw['disabled']}) or ['CPU_FIXTURE_ONLY']
old_native=sys.modules.get('r08_native');sys.modules['r08_native']=fake_native
from multiprocessing import resource_tracker,spawn
old_ensure=resource_tracker.ensure_running;resource_tracker.ensure_running=lambda:None
keys=['HIP_VISIBLE_DEVICES','CUDA_VISIBLE_DEVICES','QWEN_DCU_R08_PASS_ROOT','QWEN_DCU_R08_SEGMENT_ID','QWEN_DCU_R08_NATIVE_COLLECTOR_DESCRIPTOR','QWEN_DCU_R08_NATIVE_COLLECTOR_WORKER'];saved={k:os.environ.get(k) for k in keys};before_exe=spawn.get_executable()
os.environ.update(HIP_VISIBLE_DEVICES='0,1',CUDA_VISIBLE_DEVICES='0,1',QWEN_DCU_R08_PASS_ROOT=str(fixture),QWEN_DCU_R08_SEGMENT_ID='09_chunk_gated_delta_rule_fwd_kernel_h_blockdim64_pmc_write');os.environ.pop('QWEN_DCU_R08_NATIVE_COLLECTOR_WORKER',None);os.environ.pop('QWEN_DCU_R08_NATIVE_COLLECTOR_DESCRIPTOR',None)
def config(rank):return types.SimpleNamespace(parallel_config=types.SimpleNamespace(data_parallel_index=rank,data_parallel_rank_local=rank,tensor_parallel_size=1,pipeline_parallel_size=1,data_parallel_size=1,nnodes_within_dp=1))
def fake_make(vllm_config,local_rank,rank,fail=False):
    assert os.fsdecode(spawn.get_executable())==str(NEW/'r08_collector_python.py')
    d=json.loads(Path(os.environ['QWEN_DCU_R08_NATIVE_COLLECTOR_DESCRIPTOR']).read_text());assert d['physical_device_id']==vllm_config.parallel_config.data_parallel_index
    if fail:raise RuntimeError('CPU simulated spawn failure')
    return types.SimpleNamespace(proc=types.SimpleNamespace(pid=987654))
try:
    wrapped=m.wrap_make(fake_make);wrapped(config(0),0,0)
    assert spawn.get_executable()==before_exe and 'QWEN_DCU_R08_NATIVE_COLLECTOR_DESCRIPTOR' not in os.environ
    try:wrapped(config(1),0,0,fail=True)
    except RuntimeError as e:assert str(e)=='CPU simulated spawn failure'
    else:raise AssertionError('spawn failure ignored')
    assert spawn.get_executable()==before_exe and 'QWEN_DCU_R08_NATIVE_COLLECTOR_DESCRIPTOR' not in os.environ
    for bad in [(-1,0,0),(2,0,0),(0,1,0),(1,0,1)]:
        try:m.physical_rank(config(bad[0]),bad[1],bad[2])
        except RuntimeError:pass
        else:raise AssertionError('invalid worker topology admitted')
    called=[]
    m.wrap_termination(lambda ps:called.append(ps))([types.SimpleNamespace(is_alive=lambda:False)])
    assert len(called)==1
    selected=types.SimpleNamespace(_qwen_r08_native_collector=True,join=lambda t:called.append(t),is_alive=lambda:False)
    m.wrap_termination(lambda ps:(_ for _ in ()).throw(AssertionError('native wrapper passed to four-second killer')))([selected])
    assert len(called)==2
finally:
    resource_tracker.ensure_running=old_ensure
    if old_native is None:sys.modules.pop('r08_native',None)
    else:sys.modules['r08_native']=old_native
    for key,value in saved.items():
        if value is None:os.environ.pop(key,None)
        else:os.environ[key]=value
assert len(calls)==2 and all(x['mode']=='pmc_write' and x['trace'] and not x['disabled'] for x in calls)
gate={'status':'complete','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runtime_revision':'revision_021','previous_runtime_gate':rec(B/'runtime_capture_gate_011.json'),'frozen_tools':[rec(p) for p in sorted(NEW.iterdir()) if p.is_file()],'outer_preparation':rec(Path(__file__)),'native_probe_evidence':probes,'lossless_native_union_CPU_gate':rec(union_gate),'pinned_executor_source':rec(executor),'original_two_warmups_and_eight_measured_requests_unchanged':True,'original_R01_patch_source_and_R07_admission_order_unchanged':True,'same_single_DP2_TP1_service_with_two_native_worker_sessions':True,'original_native_DB_CSV_files_retained_unmodified':True,'combined_DB_CSV_explicitly_derived_with_exact_cell_and_byte_audit':True,'native_collection_initially_on_and_existing_Start_Stop_transitions_unchanged_from_018':True,'service_and_EngineCore_CPU_startup_no_longer_profiled':True,'all_selected_native_GPU_worker_scopes_still_required':True,'CPU_fixture':{'native_GPU_calls':0,'launcher_executable_and_environment_restored_on_success_and_exception':True,'resource_tracker_never_uses_collector_wrapper':True,'wrong_rank_topologies_rejected':4,'ordinary_process_termination_preserved':True,'native_collector_export_not_subject_to_four_second_worker_kill':True},'actual_full_model_validation_required':True,'candidate_not_activated_by_this_preparation':True,'capture_plan_sha256':rec(R/'plans/r08_capture_plan.json')['sha256']}
gate['two_native_directory_health_CPU_gate']=rec(B/'independent_worker_health_CPU_fixture_001/RESULT.json')
gate['initial_preparation']=rec(C/'prepare_independent_worker_collectors_021.py')
save(B/'runtime_capture_gate_014.json',gate)
print(json.dumps({'status':'CPU_gate_complete_candidate_only','frozen_tool_count':len(gate['frozen_tools']),'gate':str(B/'runtime_capture_gate_014.json')}))
