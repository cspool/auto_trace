"""Record user extension and derive outer control versions; no active GPU mutation."""
from pathlib import Path
import json,hashlib,datetime,os,difflib
C=Path('/public/home/accl15ptg7/run_R08_R10');P=Path('/public/home/accl15ptg7/auto_trace');D=P/'perf_trace_batch8/continuation_20260908'
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def save(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
a=json.loads((C/'MACHINE_TIME_EXTENSION_001.json').read_text());save(C/'MACHINE_TIME_EXTENSION_002.json',{'status':'authorized_by_user','recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'user_instruction':'额外延长了8h','original_started_utc':a['original_started_utc'],'previous_deadline_utc':a['deadline_utc'],'additional_seconds':28800,'deadline_utc':'2026-09-09T04:18:09Z','total_authorized_machine_seconds':86400,'previous_authorization':rec(C/'MACHINE_TIME_EXTENSION_001.json'),'checkpoint_policy':a['checkpoint_policy'],'existing_frozen_stage_assignments_not_rewritten':True})
pairs=[('watch_runtime_health_005.py','watch_runtime_health_006.py'),('remote_checkpoint_watchdog_010.py','remote_checkpoint_watchdog_011.py'),('publish_accepted_captures_003.py','publish_accepted_captures_004.py'),('offload_published_R08_files_001.py','offload_published_R08_files_002.py'),('await_all_captures_then_cpu_001.py','await_all_captures_then_cpu_002.py'),('run_closed_R08_to_R10_001.py','run_closed_R08_to_R10_002.py'),('prepare_stage_assignments_002.py','prepare_stage_assignments_003.py'),('restore_all_R08_release_artifacts_001.py','restore_all_R08_release_artifacts_002.py'),('publish_complete_stages_002.py','publish_complete_stages_003.py')]
changes=[]
for old,new in pairs:
 s=(C/old).read_text();t=s.replace('2026-09-08T20:18:09','2026-09-09T04:18:09')
 if new=='remote_checkpoint_watchdog_011.py':
  t=t.replace("'session_state.json','MACHINE_TIME_EXTENSION_001.json'","'session_state.json','MACHINE_TIME_EXTENSION_001.json','MACHINE_TIME_EXTENSION_002.json','MACHINE_TIME_EXTENSION_APPLIED_002.json','MACHINE_TIME_EXTENSION_ACTIVATED_002.json'")
 if new=='await_all_captures_then_cpu_002.py':t=t.replace('run_closed_R08_to_R10_001.py','run_closed_R08_to_R10_002.py')
 if new=='run_closed_R08_to_R10_002.py':t=t.replace('restore_all_R08_release_artifacts_001.py','restore_all_R08_release_artifacts_002.py').replace('prepare_stage_assignments_002.py','prepare_stage_assignments_003.py')
 if new=='prepare_stage_assignments_003.py':t=t.replace('MACHINE_TIME_EXTENSION_001.json','MACHINE_TIME_EXTENSION_002.json')
 if new=='restore_all_R08_release_artifacts_002.py':t=t.replace("if str(C/'offload_published_R08_files_001.py').encode() in a:","if any(str(C/name).encode() in a for name in ['offload_published_R08_files_001.py','offload_published_R08_files_002.py']):")
 if new=='publish_complete_stages_003.py':t=t.replace('   time.sleep(30)','   time.sleep(30)') # no algorithm change
 if new=='publish_complete_stages_003.py':t=t.replace('  time.sleep(30)',"  if (CONTROL/'STOP_COMPLETE_STAGE_PUBLISHER').exists():return\n  time.sleep(30)")
 compile(t,str(C/new),'exec')
 with (C/new).open('x') as f:f.write(t);f.flush();os.fsync(f.fileno())
 changes.append({'old':rec(C/old),'new':rec(C/new),'syntax_validated':True,'diff':''.join(difflib.unified_diff(s.splitlines(True),t.splitlines(True),fromfile=old,tofile=new))})
proof={'status':'prepared_outer_deadline_extension','authorization':rec(C/'MACHINE_TIME_EXTENSION_002.json'),'changes':changes,'frozen_runtime_and_analysis_tools_modified':False,'GPU_processes_signalled':False,'active_capture_scheduler':'run_r08_serial_suffix_008.py','active_capture_scheduler_retains_earlier_conservative_deadline_utc':'2026-09-08T20:18:09Z','reason':'Do not interrupt the active capture. Existing serial capture scheduler is expected to finish remaining captures before its conservative bound; any required successor will use extension002. All unstarted CPU stages and outer observers use the extended bound.','prior_CPU_algorithm_gates_preserved':True,'new_actual_stage_execution_not_claimed':True}
save(C/'MACHINE_TIME_EXTENSION_APPLIED_002.json',proof)
s=json.loads((C/'RECOVERY_STATE_NFS.json').read_text());s.update(deadline_utc='2026-09-09T04:18:09Z',deadline_extension_authorization=str(C/'MACHINE_TIME_EXTENSION_002.json'),outer_extension_status='prepared_restarting_waiting_observers',active_capture_scheduler_conservative_deadline_utc='2026-09-08T20:18:09Z');tmp=C/'RECOVERY_STATE_NFS.extension.partial';tmp.write_text(json.dumps(s,indent=2)+'\n');os.replace(tmp,C/'RECOVERY_STATE_NFS.json')
for name in ['STOP_RUNTIME_HEALTH_WATCHDOG','STOP_REMOTE_CHECKPOINT_WATCHDOG','STOP_ACCEPTED_CAPTURE_PUBLISHER','STOP_RELEASE_OFFLOAD_WATCHDOG','STOP_CPU_SUFFIX_WAITER']:(C/name).touch()
for name in ['MACHINE_TIME_EXTENSION_002.json','MACHINE_TIME_EXTENSION_APPLIED_002.json','RECOVERY_STATE_NFS.json']:(D/name).write_bytes((C/name).read_bytes())
for old,new in pairs:(D/'outer_helpers_001'/new).write_bytes((C/new).read_bytes())
(D/'outer_helpers_001'/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
p=D/'RECOVERY_README.md';s=p.read_text().replace('2026-09-08 20:18:09 UTC。额外延期须以用户的新授权为准。','2026-09-09 04:18:09 UTC（用户第二次追加 8 小时，见 MACHINE_TIME_EXTENSION_002.json）。当前已启动的采集调度器 008 保留较早的保守时间上限，避免中断正在运行的采集；后续 CPU 阶段、发布及进度监控均使用新期限。')
for old,new in pairs:s=s.replace(old,new)
p.write_text(s)
with (D/'LIVE_PROGRESS.md').open('a') as f:f.write('\n- '+datetime.datetime.now(datetime.timezone.utc).isoformat()+': User authorized another 8 h; deadline is now 2026-09-09 04:18:09 UTC. Seven captures accepted/published/offloaded; capture08 attempt002 has both-rank native prehealth and all-eight declared first-phase trace coverage, measured generation ongoing. Outer deadline versions prepared without modifying active GPU or frozen tools.\n')
print(json.dumps({'authorization':rec(C/'MACHINE_TIME_EXTENSION_002.json'),'new_outer_versions':len(changes),'stop_markers_written':True}))
