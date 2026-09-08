"""Prepare a reviewed capture09 retry after all prior workers are closed."""
from pathlib import Path
import json, hashlib, datetime, os, shutil
C=Path('/public/home/accl15ptg7/run_R08_R10');P=Path('/public/home/accl15ptg7/auto_trace');D=P/'perf_trace_batch8/continuation_20260908'
R=P/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001';B=R/'raw/runtime_tools'
seg='09_chunk_gated_delta_rule_fwd_kernel_h_blockdim64_pmc_write';A=R/'raw/captures'/seg/'attempt_005'
def read(p):return json.loads(p.read_text())
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def save(p,x):
    with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
f=read(A/'RAW_CAPTURE_FAILURE.json');cl=read(A/'control/tracee_process_cleanup.json');assert f['status']=='failed_not_accepted' and not (A/'workload/driver.json').exists()
groups=[f['profiler_cleanup']['leader_pid'],cl['service']['leader_pid'],cl['workload']['leader_pid']]
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:fields=(p/'stat').read_text().split(') ',1)[1].split();argv=(p/'cmdline').read_bytes().split(b'\0')
    except OSError:continue
    assert int(fields[2]) not in groups and int(p.name) not in [861055,861047],'failed full-model process still alive'
    if any(x.endswith(b'/gqa6_visibility_probe.py') or x.endswith(b'/gqa6_native_probe.py') for x in argv):assert fields[0]=='Z','native model-free worker still running'
checkpoints=[]
for u in read(R/'plans/r08_capture_plan.json')['physical_captures'][:8]:
    p=R/'validation/serial_scheduler_012'/(u['segment_id']+'.accepted_checkpoint.json');x=read(p);assert x['status']=='accepted'
    for k in ['execution_manifest','normalization_manifest','independent_audit']:assert rec(Path(x['item'][k]['path']))==x['item'][k]
    checkpoints.append(rec(p))
for gate in [B/'runtime_capture_gate_014.json',R/'validation/independent_native_sessions_analysis_CPU_gate_001.json']:
    g=read(gate);assert g['status']=='complete'
    for x in g['frozen_tools']:assert rec(Path(x['path']))==x
proof=B/'capture09_independent_native_sessions_retry_001.json'
save(proof,{'status':'authorized_CPU_and_native_probe_gated_retry','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'prior_failed_capture':rec(A/'RAW_CAPTURE_FAILURE.json'),'prior_owned_process_groups_verified_closed':groups,'prior_measured_requests_started':False,'previous_eight_accepted_captures_preserved':checkpoints,'runtime_gate':rec(B/'runtime_capture_gate_014.json'),'analysis_gate':rec(R/'validation/independent_native_sessions_analysis_CPU_gate_001.json'),'new_attempt':'attempt_006','native_session_layout':'independent_native_collector_per_GPU_worker; original single DP2 service, original two warmups and eight requests','original_native_DB_CSVs_retained_unmodified':True,'derived_union_requires_exact_original_cell_and_byte_audit':True,'full_model_validation_still_required':True,'deadline_authorization':rec(C/'MACHINE_TIME_EXTENSION_002.json')})
s=(C/'run_r08_serial_suffix_012.py').read_text().replace('validation/serial_scheduler_011','validation/serial_scheduler_012').replace("SCHEDULE=ROOT/'validation/serial_scheduler_012'","SCHEDULE=ROOT/'validation/serial_scheduler_013'").replace("RUNTIME=ROOT/'raw/runtime_tools/revision_020'","RUNTIME=ROOT/'raw/runtime_tools/revision_021'").replace('runtime_capture_gate_013.json','runtime_capture_gate_014.json').replace("ROOT/'validation/background_graph_analysis_CPU_gate_001.json']","ROOT/'validation/background_graph_analysis_CPU_gate_001.json',ROOT/'validation/independent_native_sessions_analysis_CPU_gate_001.json']").replace("attempt='attempt_005' if ordinal==8","attempt='attempt_006' if ordinal==8").replace('capture09_deferred_start_retry_001.json','capture09_independent_native_sessions_retry_001.json').replace('using CPU-gated runtime020 deferred native startup and unchanged measured workload','using native-probed runtime021 independent worker collectors with retained original sources and unchanged full workload').replace('tools/analysis_007/','tools/analysis_008/')
p=C/'run_r08_serial_suffix_013.py';compile(s,str(p),'exec');p.write_text(s)
s=(C/'watch_runtime_health_006.py').read_text().replace("  d=Path(read(p)['injected_output_directory'])","  mode=read(p);d=Path(mode['injected_output_directory']) if 'injected_output_directory' in mode else None")
old="   q=d/('pmc_results_'+str(i['pid'])+'.txt');size=q.stat().st_size if q.exists() else 0;native.append"
new="   directory=d\n   if directory is None:\n    binding=root/'control/worker_native_collectors'/('rank'+str(i['dp_rank'])+'.json')\n    if not binding.exists():continue\n    binding=read(binding)\n    if binding['worker_pid']!=i['pid']:raise ValueError('live native worker binding mismatch')\n    directory=Path(binding['native_output_directory'])\n   q=directory/('pmc_results_'+str(i['pid'])+'.txt');size=q.stat().st_size if q.exists() else 0;native.append"
assert s.count(old)==1;s=s.replace(old,new);p=C/'watch_runtime_health_007.py';p.write_text(s);compile(s,str(p),'exec')
out=D/'independent_native_sessions_runtime021_activation_001';out.mkdir()
for n in ['native_PMC_independent_dual_context_probe_021','native_PMC_mp_executable_probe_022','native_PMC_mp_transport_marker_probe_023','native_PMC_supervised_transport_probe_024','native_session_union_CPU_gate_001','native_session_union_CPU_gate_002','independent_worker_health_CPU_fixture_001']:shutil.copytree(B/n,out/n)
shutil.copytree(B/'revision_021',out/'runtime_revision_021');shutil.copytree(R/'tools/analysis_008',out/'analysis_008')
for p in [proof,B/'runtime_capture_gate_014.json',R/'validation/independent_native_sessions_analysis_CPU_gate_001.json']:(out/p.name).write_bytes(p.read_bytes())
for name in ['probe_native_independent_dual_context_021.py','probe_native_mp_executable_022.py','probe_native_mp_transport_marker_023.py','probe_native_supervised_transport_024.py','native_session_merge_001.py','native_session_merge_002.py','native_session_provenance_001.py','r08_collector_python_021.py','r08_worker_collectors_021.py','prepare_independent_worker_collectors_021.py','complete_independent_worker_gate_021.py','complete_independent_worker_gate_021_v2.py','run_r08_serial_suffix_013.py','watch_runtime_health_007.py','activate_independent_native_sessions_001.py']:shutil.copy2(C/name,D/'outer_helpers_001'/name)
for name in ['prepare_independent_worker_collectors_021.log','complete_independent_worker_gate_021.log','complete_independent_worker_gate_021_v2.log']:shutil.copy2(C/name,out/name)
with (D/'LIVE_PROGRESS.md').open('a') as f:f.write('\n- '+datetime.datetime.now(datetime.timezone.utc).isoformat()+': Frozen runtime021 (17 tools) and analysis008 (7 tools) passed native two-session, cross-device, MP pipe/marker, supervised exit, lossless-union and independent provenance checks. Scheduler013 is prepared to start capture09 attempt006 using two independent native collectors around the unchanged single DP2 service GPU workers. Original DB/CSV sources are retained; combined data is explicitly derived with exact original-cell/byte audit. Eight accepted prefix captures were reverified. Full-model effectiveness remains to be validated.\n')
print('PREPARED_SCHEDULER013_AND_REMOTE_CHECKPOINT',len(checkpoints))
