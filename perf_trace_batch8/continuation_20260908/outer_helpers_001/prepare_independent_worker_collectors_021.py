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
shutil.copytree(OLD,NEW,ignore=shutil.ignore_patterns('__pycache__'))
for p in NEW.iterdir():
    if p.is_file() and p.suffix in ['.py','.sh']:p.write_text(p.read_text().replace('/revision_018/','/revision_021/'))
for source,destination in [('r08_collector_python_021.py','r08_collector_python.py'),('r08_worker_collectors_021.py','r08_worker_collectors.py'),('native_session_merge_002.py','native_session_merge.py')]:
    shutil.copy2(C/source,NEW/destination)
(NEW/'r08_collector_python.py').chmod(0o700)
executor=P/'pra2026-bh408-gqa-page784-k5120-batch8/vllm/v1/executor/multiproc_executor.py'
p=NEW/'r08_worker_collectors.py';p.write_text(p.read_text().replace('REPLACE_AT_FREEZE',rec(executor)['sha256']))
p=NEW/'sitecustomize.py';s=p.read_text();old="    for key in ['HIPPROF_INPUT_FILE','HIPPROF_TMP_OUTPUT_DIR']:\n        require(bool(os.environ.get(key)),'live HIPProf exec environment missing: '+key)";new="    require(os.environ.get('QWEN_DCU_R08_INDEPENDENT_COLLECTORS')=='1','independent native worker session mode')\n    if os.environ.get('QWEN_DCU_R08_NATIVE_COLLECTOR_WORKER')=='1':\n        for key in ['HIPPROF_INPUT_FILE','HIPPROF_TMP_OUTPUT_DIR']:\n            require(bool(os.environ.get(key)),'live worker HIPProf exec environment missing: '+key)";assert s.count(old)==1;s=s.replace(old,new);s=s.replace("    os.environ['QWEN_DCU_R08_SITECUSTOMIZE_READY']='1'", "    import r08_worker_collectors\n    r08_worker_collectors.install()\n    os.environ['QWEN_DCU_R08_SITECUSTOMIZE_READY']='1'");p.write_text(s)
p=NEW/'run_capture.py';s=p.read_text().replace('runtime_capture_gate_011.json','runtime_capture_gate_014.json')
s=s.replace("env.update(VLLM_WORKER_MULTIPROC_METHOD='spawn',", "env.update(QWEN_DCU_R08_INDEPENDENT_COLLECTORS='1',VLLM_WORKER_MULTIPROC_METHOD='spawn',")
start=s.index("    for key in ['HIPPROF_INPUT_FILE','HIPPROF_TMP_OUTPUT_DIR']:require(bool(env.get(key))")
end=s.index('    visible_keys=',start)
s=s[:start]+"    save(root/'control/live_collector_exec.json',{'mode':'independent_native_worker_collectors','native_collector_count':2,'service_parent_unprofiled':True,'worker_bindings_directory':str(root/'control/worker_native_collectors')})\n"+s[end:]
start=s.index("    native_directory=Path(env['HIPPROF_TMP_OUTPUT_DIR'])")
end=s.index('    try:\n        with ',start)
s=s[:start]+"    from r08_worker_collectors import snapshot_native_files,close_native_collectors\n    snapshot=root/'control/native_pmc_before_collector_merge';snapshot.mkdir()\n    def snapshot_native():snapshot_native_files(root,snapshot)\n    native_cleanup=None\n"+s[end:]
old="        if workload is not None:cleanup['workload']=terminate(workload)\n        if service is not None:cleanup['service']=terminate(service)\n        snapshot_native()\n        save(root/'control/tracee_process_cleanup.json',cleanup)"
new="        snapshot_native()\n        if workload is not None:cleanup['workload']=terminate(workload)\n        if service is not None:cleanup['service']=terminate(service,grace=120)\n        native_cleanup=close_native_collectors(root)\n        cleanup['native_collectors']=native_cleanup\n        save(root/'control/tracee_process_cleanup.json',cleanup)\n    require(native_cleanup is not None and native_cleanup['status']=='complete','both independent native collectors closed successfully')"
assert s.count(old)==1;s=s.replace(old,new)
old="    argv=collector_argv(unit['mode'],unit['collector_kernel_name_token'],root,[sys.executable,'-B',str(Path(__file__)),'tracee','--pass-root',str(root),'--segment',args.segment],disabled=False)"
new="    argv=[sys.executable,'-B',str(Path(__file__)),'tracee','--pass-root',str(root),'--segment',args.segment]"
assert s.count(old)==1;s=s.replace(old,new)
s=s.replace("'profiling_mode':'replay_projected_attributes_only','latency_axis':'observed_R07_only'", "'profiling_mode':'replay_projected_attributes_only','latency_axis':'observed_R07_only','native_session_layout':'one independent native collector per DP2 GPU worker; same single service and workload'")
s=s.replace("save(root/'control/profiler_identity.json',{'pid':profiler.pid,'process_group':profiler.pid})", "save(root/'control/profiler_identity.json',{'pid':profiler.pid,'process_group':profiler.pid,'role':'unprofiled_capture_supervisor','native_collectors':2})")
old="    cleanup=terminate(profiler)\n    # Keep all raw data even when a postcheck fails."
new="    cleanup=terminate(profiler)\n    if rc==0 and error is None:\n        try:\n            require(read(root/'control/NATIVE_COLLECTORS_CLOSED.json')['status']=='complete','closed independent native sessions')\n            from native_session_merge import merge,audit\n            merge([root/'native_collectors/rank0',root/'native_collectors/rank1'],root)\n            audit(root)\n        except Exception as union_error:\n            error='native session union failed: '+type(union_error).__name__+': '+str(union_error)\n    # Keep original sessions and any derived data even when a postcheck fails."
assert s.count(old)==1;s=s.replace(old,new)
s=s.replace("'profiler_starts':1,'warmups':2", "'profiler_starts':2,'capture_supervisor_starts':1,'native_session_layout':'independent_workers_lossless_derived_union','native_session_union':source_record(root/'NATIVE_SESSION_UNION.json'),'native_session_union_audit':source_record(root/'NATIVE_SESSION_UNION_AUDIT.json'),'original_native_sessions':[{'rank':rank,'database':source_record(root/'native_collectors'/('rank'+str(rank))/'capture.db'),'csv':source_record(root/'native_collectors'/('rank'+str(rank))/'capture.csv')} for rank in [0,1]],'warmups':2")
p.write_text(s)
p=NEW/'r08_native_health.py';s=p.read_text();old=" root=Path(root);raw_directory=Path(raw_directory) if raw_directory else Path(json.loads((root/'control/live_collector_exec.json').read_text())['injected_output_directory']);workers=[]";new=" root=Path(root);workers=[];bindings={}\n if raw_directory is None:\n  mode=json.loads((root/'control/live_collector_exec.json').read_text())\n  if mode.get('mode')=='independent_native_worker_collectors':\n   for rank in [0,1]:\n    p=root/'control/worker_native_collectors'/('rank'+str(rank)+'.json')\n    if not p.exists():return {'status':'failed','reason':'native collector worker binding missing','rank':rank,'workers':workers}\n    bindings[rank]=json.loads(p.read_text())\n  else:raw_directory=Path(mode['injected_output_directory'])\n else:raw_directory=Path(raw_directory)";assert s.count(old)==1;s=s.replace(old,new)
old="  path=raw_directory/f'pmc_results_{pid}.txt';size=path.stat().st_size if path.exists() else 0";new="  if bindings:\n   binding=bindings[rank]\n   if binding['rank']!=rank or binding['worker_pid']!=pid:return {'status':'failed','reason':'independent native collector PID/rank mismatch','rank':rank,'workers':workers}\n   directory=Path(binding['native_output_directory'])\n  else:directory=raw_directory\n  path=directory/f'pmc_results_{pid}.txt';size=path.stat().st_size if path.exists() else 0";assert s.count(old)==1;s=s.replace(old,new);p.write_text(s)
for p in NEW.glob('*.py'):compile(p.read_text(),str(p),'exec')
for name in ['r08_pmc_gate.py','r08_admission_order.py','r08_workload_driver.py','r08_process_overlay.py','r08_memory_profile.py','launch_vllm.py','source_abi_probe.py']:
    assert (OLD/name).read_bytes()==(NEW/name).read_bytes(),'original workload or marker behavior changed: '+name
# Exercise the production launcher wrapper without importing torch or vLLM.
spec=importlib.util.spec_from_file_location('collector_CPU_fixture',NEW/'r08_worker_collectors.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
fixture=B/'independent_worker_collectors_CPU_fixture_001';fixture.mkdir();calls=[]
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
save(B/'runtime_capture_gate_014.json',gate)
print(json.dumps({'status':'CPU_gate_complete_candidate_only','frozen_tool_count':len(gate['frozen_tools']),'gate':str(B/'runtime_capture_gate_014.json')}))
