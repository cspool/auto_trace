from pathlib import Path
import shutil,json,hashlib,runpy,os,signal
ROOT=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');base=ROOT/'raw/runtime_tools';old=base/'revision_014';new=base/'revision_015';shutil.copytree(old,new,ignore=shutil.ignore_patterns('__pycache__'))
probe=base/'native_fresh_exec_pmc_write_probe_001/RESULT.json';x=json.loads(probe.read_text());assert x['status']=='complete' and x['native_device_counts']=={'0':4,'1':4}
p=new/'run_capture.py';s=p.read_text().replace('runtime_capture_gate_008.json','runtime_capture_gate_009.json');s=s.replace("env.update(HIP_VISIBLE_DEVICES='0,1'", "env.update(VLLM_WORKER_MULTIPROC_METHOD='spawn',HIP_VISIBLE_DEVICES='0,1'")
a=s.index("    require(rc==0 and error is None,'profiler did not exit successfully')");b=s.index("    print('R08_RAW_CAPTURE_COMPLETE'",a);block=s[a:b]
s=s[:a]+"    try:\n"+''.join('    '+line+'\n' for line in block.splitlines())+"    except Exception as failure:\n        save(root/'RAW_CAPTURE_FAILURE.json',{'status':'failed_not_accepted','failure_type':type(failure).__name__,'reason':str(failure),'raw_inventory':source_record(root/'raw_inventory_at_exit.json'),'profiler_cleanup':cleanup,'native_health':read(root/'control/PRE_MEASURED_NATIVE_PMC_HEALTH.json') if (root/'control/PRE_MEASURED_NATIVE_PMC_HEALTH.json').exists() else None,'measurement_completion_claimed':False})\n        raise\n"+s[b:];p.write_text(s)
p=new/'vllm_r08_contract_shim.sh';p.write_text(p.read_text().replace(str(old/'launch_vllm.py'),str(new/'launch_vllm.py')))
p=new/'r08_workload_driver.py';s=p.read_text().replace('"excluded_from_pmc_by_worker_gate": True','"excluded_from_raw_native_pmc": False').replace('"hipProfilerStop_Start_gate_and_target_kernel_filter"','"native_initially_on_measured_start_terminal_stop_and_exact_offline_guard"');p.write_text(s)
for p in new.glob('*.py'):compile(p.read_text(),str(p),'exec')
def rec(p):return {'path':str(p),'size':Path(p).stat().st_size,'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
proof={'status':'complete','strategy':'fresh spawn vLLM workers plus existing read-only native health gate before full8request measurement','hypothesis':'default fork can inherit initialized native profiling state; explicit spawn avoids inheriting process-local native profiler state','root_cause_claimed_proven':False,'pinned_runtime_context_source':rec(Path('/public/home/accl15ptg7/auto_trace/pra2026-bh408-gqa-page784-k5120-batch8/vllm/utils/system_utils.py')),'model_free_fresh_interpreter_native_probe':rec(probe),'frozen_tools':[rec(p) for p in sorted(new.iterdir()) if p.is_file()],'capture_plan_sha256':rec(ROOT/'plans/r08_capture_plan.json')['sha256'],'prior_runtime_gate':rec(base/'runtime_capture_gate_008.json'),'model_initializations_this_cpu_gate':0,'device_queries_this_cpu_gate':0,'workload_request_selection_native_counters_and_marker_semantics_unchanged':True,'worker_multiprocessing_method':'spawn','data_parallel_backend':'mp','native_health_gate_must_pass_before_measured_requests':True,'raw_failure_checkpoint_now_explicit':True}
with (base/'runtime_capture_gate_009.json').open('x') as f:json.dump(proof,f,indent=2);f.write('\n')
raw=ROOT/'raw/captures/03__gqa6_pmc_write/attempt_002';health=json.loads((raw/'control/PRE_MEASURED_NATIVE_PMC_HEALTH.json').read_text());assert health['status']=='failed';cleanup=json.loads((raw/'control/tracee_process_cleanup.json').read_text());pids=[]
for v in cleanup.values():pids.extend([v['leader_pid'],*v['remaining_group_members_before_final_cleanup']])
pids.extend(int(p.name.split('.')[1]) for p in (raw/'workload/r01_events').glob('rank*/events.*.jsonl'));pids.append(json.loads((raw/'control/profiler_identity.json').read_text())['pid']);assert all(not Path('/proc',str(pid)).exists() for pid in pids)
with (base/'capture03_retry_authorization_002.json').open('x') as f:json.dump({'status':'authorized_within_user_continuation','prior_attempt':'03__gqa6_pmc_write/attempt_002','new_attempt':'03__gqa6_pmc_write/attempt_003','prior_native_health':rec(raw/'control/PRE_MEASURED_NATIVE_PMC_HEALTH.json'),'measured_batch_not_started_in_prior_attempt':True,'prior_pids_verified_terminated':pids,'source_native_device_population_still_DP2':True,'gate':rec(base/'runtime_capture_gate_009.json'),'deadline_utc':'2026-09-08T20:18:09Z'},f,indent=2);f.write('\n')
# Stop only the obsolete outer waiter. The failed capture and native probe exited.
previous='/root/r08_emergency_tools/run_r08_serial_suffix_002.py'
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 try:argv=(proc/'cmdline').read_bytes().split(b'\0')
 except (FileNotFoundError,PermissionError,ProcessLookupError):continue
 if len(argv)>2 and argv[0] in [b'python',b'/usr/bin/python'] and argv[1]==b'-B' and argv[2].decode()==previous:os.kill(int(proc.name),signal.SIGTERM)
print('SPAWN_CAPTURE_CPU_GATE_COMPLETE')
