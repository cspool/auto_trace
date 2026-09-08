from continuation_common import *
import csv,tarfile
R08=RUN/'artifacts/R08/continuation_001'
manifest_path=PROJECT/'perf_trace_batch8/releases/batch8-r07-local-artifacts-20260907/FILE_MANIFEST.json';published=read(manifest_path);files={f['path']:f for f in published['files']}
restore_path=CONTROL/'r07_additional_inputs_restore_manifest.json';restore=read(restore_path);require(restore['status']=='complete','verified supplemental restore')
records={}
for r in restore['entries']:
    p=Path(r['path']);original=files[r['source_member']];require(p.stat().st_size==original['size'] and sha(p)==original['sha256']==r['sha256'],'published R07 extra input identity');records[p.name]={'path':str(p),'size':p.stat().st_size,'sha256':sha(p),'original_source_member':r['source_member']}
anchor_member='diagnostic_bundle/records/live_utilization_clock_anchors.json'
with tarfile.open(CONTROL/'downloads/perf-trace-batch8-r07-attempt043-hipprof-diagnostic-20260905/r07-attempt043-hipprof-live-diagnostic.tar.gz') as archive:
    data=archive.extractfile(anchor_member).read()
require(hashlib.sha256(data).hexdigest()=='6d026e7c5135ce409d8e7d0ed1d2e4600f8373d716238e9de51478edeff61ca0','R07 anchor bytes')
anchor=CONTROL/'r07_additional_inputs/clock_anchors.json'
with anchor.open('xb') as f:f.write(data)
records['clock_anchors.json']={'path':str(anchor),'size':len(data),'sha256':sha(anchor),'original_source_member':anchor_member}
driver=read(records['driver.json']['path']);outcomes=read(records['request_results.json']['path'])['results'];require(driver['runtime_run_id']==RUN_ID and driver['runtime_goal']=='R07' and driver['runtime_attempt_id']==RUN_ID+'-R07-attempt-043','exact R07 observed run')
require(driver['completed']==8 and driver['failed']==0 and driver['total_completion_tokens']==8192 and driver['warmup_count']==2,'successful R07 workload')
require(driver['trace_profile_sha256']==PROFILE_HASH and driver['r01_request_manifest_file_byte_sha256']==sha(RUN/'artifacts/R01/contract/request_selection.json'),'selected request contract')
require(len(outcomes)==8 and len({x['request_id'] for x in outcomes})==8 and {x['request_id'] for x in outcomes}==set(driver['request_ids']),'eight unique requests')
requests={x['request_id']:x for x in outcomes};max_offset_delta=0
for x in outcomes:
    require(x['http_status']==200 and x['completion_tokens']==1024 and x['error'] is None,'complete observed client request')
    require(x['end_monotonic_ns']-x['start_monotonic_ns']==x['duration_ns'],'integer client duration')
    require(x['start_realtime_ns']<x['end_realtime_ns'],'client observed interval')
    require(x['data_parallel_rank_requested']==x['physical_device_id_expected'] in [0,1],'exact routing')
    max_offset_delta=max(max_offset_delta,abs((x['end_realtime_ns']-x['end_monotonic_ns'])-(x['start_realtime_ns']-x['start_monotonic_ns'])))
require(max_offset_delta<=1000000,'R07 realtime/monotonic drift within alignment gate')
count=0
with (RUN/'artifacts/R07/resume-042/trace/process_ranges.csv').open() as f:
    for p in csv.DictReader(f):
        request=requests[p['request_id']];require(request['start_realtime_ns']<=int(p['begin_ns'])<=int(p['end_ns'])<=request['end_realtime_ns'],'native process inside actual client request interval');require(int(p['dp_rank'])==request['data_parallel_rank_requested'],'native process/client routing');count+=1
write_new(R08/'validation/r07_additional_observed_input_admission.json',{'status':'complete','runtime_run_id':RUN_ID,'lineage_id':RUN_ID,'R07_recovered_handoff_sha256':sha(RUN/'handoffs/R07.recovered.json'),'published_FILE_MANIFEST':{'path':str(manifest_path),'sha256':sha(manifest_path)},'supplemental_restore':{'path':str(restore_path),'sha256':sha(restore_path)},'additional_same_R07_observed_inputs':records,'measured_requests':8,'native_processes_within_client_intervals':count,'max_client_realtime_monotonic_offset_drift_ns':max_offset_delta,'historical_or_other_run_values_imported':False,'original_R07_outputs_modified':False,'model_device_profiler_execution_performed':False,'tool_path':str(Path(__file__)),'tool_sha256':sha(Path(__file__))})
print('R07_CLIENT_INTERVAL_ADMISSION_COMPLETE',len(outcomes),count,max_offset_delta,flush=True)
