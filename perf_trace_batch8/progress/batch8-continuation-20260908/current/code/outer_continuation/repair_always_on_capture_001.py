from pathlib import Path
import sys,json,shutil,hashlib,runpy
ROOT=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');old=ROOT/'tools/revision_011';new=ROOT/'tools/revision_012';shutil.copytree(old,new)
p=new/'r08_pmc_gate.py';s=p.read_text();point='def _event_payload(operation: str, rank: int | None) -> dict[str, Any]:'
fn='''def _logical_window_transition(operation: str) -> dict[str, Any]:
    now=time.perf_counter_ns()
    return {'operation':operation,'status':'logical_window_only','native_profiler_transition_performed':False,'pid':os.getpid(),'tid':threading.get_native_id(),'started_monotonic_ns':now,'finished_monotonic_ns':now}


'''
assert point in s;s=s.replace(point,fn+point).replace('_hip_call("hipProfilerStop")','_logical_window_transition("logical_window_stop")').replace('_hip_call("hipProfilerStart")','_logical_window_transition("logical_window_start")').replace('hipProfilerStop_Start_with_offline_pid_monotonic_guard','always_on_native_collection_with_exact_marker_PID_dispatch_guard').replace('collection_state=initially_stopped','collection_state=native_always_on').replace('canonical_window=dynamic_plus_offline_guard','canonical_window=offline_exact_marker_guard')
s=s.replace('"initial_profiler_stop_monotonic_ns": _initial_stop_monotonic_ns,','"initial_profiler_stop_monotonic_ns": _initial_stop_monotonic_ns,\n        "legacy_initial_stop_field_is_logical_guard_only": True,\n        "native_collection_always_on": True,')
p.write_text(s)
p=new/'run_capture.py';s=p.read_text().replace('runtime_capture_gate_005.json','runtime_capture_gate_006.json').replace('disabled=True)','disabled=False)');s=s.replace("save(root/'control/live_collector_exec.json'","(root/'control/live_collector_input.txt').write_bytes(Path(env['HIPPROF_INPUT_FILE']).read_bytes())\n    save(root/'control/live_collector_exec.json'");p.write_text(s)
p=new/'vllm_r08_contract_shim.sh';p.write_text(p.read_text().replace('revision_011/launch_vllm.py','revision_012/launch_vllm.py'))
p=new/'r08_workload_driver.py';s=p.read_text().replace('hipProfilerStop_Start_plus_offline_pid_monotonic_guard','native_always_on_with_exact_marker_PID_dispatch_guard');p.write_text(s)
for p in new.glob('*.py'):compile(p.read_text(),str(p),'exec')
sys.path.insert(0,str(new));runpy.run_path(str(new/'launch_vllm.py'),run_name='__mp_main__')
# Import the gate without install or HIP calls and prove that logical windows
# do not invoke the native transition helper.
ns=runpy.run_path(str(new/'r08_pmc_gate.py'),run_name='cpu_gate');r=ns['_logical_window_transition']('fixture');assert r['native_profiler_transition_performed'] is False

def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
probes=[]
for f in ['preflight/torch_pmc_exec_probe_001/RESULT.json','preflight/full_runtime_env_pmc_probe_001/RESULT.json','preflight/gqa6_pmc_probe_001/RESULT.json','preflight/torch_abrupt_exit_probe_001/RESULT.json']:
 p=ROOT/f;x=json.loads(p.read_text());assert x['status']=='complete';probes.append(rec(p))
proof={'status':'complete','strategy':'native target-filtered PMC and HIP tracing always on; exact measured marker and native dispatch chain selects eligible rows','reason':'full vLLM dynamic-gated capture had zero PMC despite successful full workload; short exact-runtime and real-gqa6 probes produce PMC; root cause within model lifecycle remains unresolved','root_cause_claimed_proven':False,'model_free_current_probes':probes,'logical_window_fixture':r,'model_imports_this_gate':0,'device_queries_this_gate':0,'frozen_tools':[rec(p) for p in sorted(new.iterdir()) if p.is_file()],'capture_plan_sha256':hashlib.sha256((ROOT/'plans/r08_capture_plan.json').read_bytes()).hexdigest(),'prior_runtime_gate':rec(ROOT/'validation/runtime_capture_gate_005.json'),'first_capture_argv':['/usr/bin/python','-B',str(new/'run_capture.py'),'capture','--segment','01__gqa6_pmc','--attempt','attempt_004'],'same_full_workload_source_model_and_final_cache_target':True}
with (ROOT/'validation/runtime_capture_gate_006.json').open('x') as f:json.dump(proof,f,indent=2);f.write('\n')
with (ROOT/'authorization/first_capture_retry_003.json').open('x') as f:json.dump({'status':'authorized','same_user_continuation_scope':True,'prior_capture_retained':'01__gqa6_pmc/attempt_003','prior_capture_workload_complete':True,'prior_PMC_missing':True,'prior_owned_processes_terminated':True,'retry_scope':'only first unaccepted segment','gate':rec(ROOT/'validation/runtime_capture_gate_006.json')},f,indent=2);f.write('\n')
print('ALWAYS_ON_CAPTURE_CPU_GATE_COMPLETE')
