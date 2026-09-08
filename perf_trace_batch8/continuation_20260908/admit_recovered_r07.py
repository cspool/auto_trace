"""Independently admit recovered R07 without changing its historical handoff."""
import collections
import csv
from pathlib import Path
from continuation_common import *

def rows(path):
    with Path(path).open(newline='') as f:yield from csv.DictReader(f)

def main():
    handoff_path=RUN/'handoffs/R07.recovered.json'
    require(sha(handoff_path)==R07_HASH,'original R07 handoff hash')
    h=read(handoff_path);validate_recovered_status(h)
    verified=[]
    for ordinal in range(1,7):
        stage=f'R{ordinal:02d}';p=SNAPSHOT/f'recovery_index/handoffs/{stage}.json'
        require(sha(p)==h[f'r{ordinal:02d}_handoff_sha256'],stage+' original handoff')
        j=read(p);require(j['status']=='complete' and j['runtime_run_id']==RUN_ID,stage+' lineage/status')
        verified.append({'role':stage+'_original_handoff','local_path':str(p),'sha256':sha(p)})
    ledger=SNAPSHOT/'recovery_index/control/runtime_handoff_ledger.r01_r06_prefix.json'
    require(sha(ledger)==h['cumulative_runtime_ledger_sha256'],'historical R06 prefix ledger')
    for record in [h['artifact_manifest'],h['completion_audit'],h['source_lineage'],*h['recovery_outputs'].values()]:
        verified.append(verify_record(record))
    manifest=read(resolve_source(h['artifact_manifest']['path']))
    for record in manifest['entries']:verified.append(verify_record(record))
    summaries={}
    for name in ['process_trace_summary','live_utilization_summary','fresh_run_dependency_adapter']:
        s=read(resolve_source(h['recovery_outputs'][name]['path']));summaries[name]=s
        require(s['runtime_run_id']==RUN_ID and s['lineage_id']==RUN_ID,name+' lineage')
        for record in s.get('outputs',{}).values():verified.append(verify_record(record))
        if 'csv' in s:verified.append(verify_record(s['csv']))
    trace=summaries['process_trace_summary'];live=summaries['live_utilization_summary']
    sidecar=read(resolve_source(h['recovery_outputs']['bound_target_sidecar']['path']))
    require(sidecar['target_count']==13568 and len(sidecar['records'])==13568,'bound target universe')
    target_ids={r['canonical_target_id'] for r in sidecar['records']}
    require(len(target_ids)==13568,'unique bound target IDs')
    require(sidecar['bound_request_phase_count']==16 and len(sidecar['bound_request_phases'])==16,'16 request-phase occurrences')
    requested={r['request_id'] for r in sidecar['records']}
    require(len(requested)==8,'eight requests')
    require({(r['request_id'],r['phase']) for r in sidecar['bound_request_phases']}=={(r,p) for r in requested for p in ['prefill','decode']},'complete request-phase cross product')
    processes=list(rows(resolve_source(trace['outputs']['process_ranges']['path'])))
    by_process={r['process_range_id']:r for r in processes}
    require(len(processes)==len(by_process)==12544,'process cardinality')
    require({r['request_id'] for r in processes}==requested,'process request coverage')
    require({(r['dp_rank'],r['native_device']) for r in processes}=={('0','0'),('1','1')},'native DP2 mapping')
    require(all(r['canonical_target_id'] in target_ids for r in processes),'process-target membership')
    require(all(int(r['end_ns'])-int(r['begin_ns'])==int(r['duration_ns']) for r in processes),'process time conservation')
    runtime={};runtime_counts=collections.Counter()
    for row in rows(resolve_source(trace['outputs']['hip_runtime_calls']['path'])):
        key=(row['hip_runtime_table'],row['hip_runtime_rowid'])
        require(key not in runtime,'duplicate runtime row')
        runtime[key]=(row['owner_process_range_id'],row['hip_runtime_index'],row['hip_runtime_api'],row['is_kernel_launch'])
        runtime_counts[row['owner_process_range_id']]+=1
    require(len(runtime)==316802,'runtime call universe')
    kernel_count=0;kernel_ids=set();kernel_counts=collections.Counter();rank_counts=collections.Counter()
    for row in rows(resolve_source(trace['outputs']['strict_owned_kernels']['path'])):
        kernel_count+=1;kernel_ids.add(row['kernel_instance_id'])
        p=by_process[row['owner_process_range_id']]
        require(row['owner_canonical_target_id']==p['canonical_target_id'],'kernel exact target ownership')
        require((row['request_id'],row['dp_rank'],row['native_device'])==(p['request_id'],p['dp_rank'],p['native_device']),'kernel owner scope')
        launch=runtime[(row['hip_runtime_table'],row['hip_runtime_rowid'])]
        require(launch==(row['owner_process_range_id'],row['hip_runtime_index'],row['hip_runtime_api'],'True'),'native launch chain')
        require(int(row['end_ns'])-int(row['begin_ns'])==int(row['duration_ns']),'kernel time conservation')
        kernel_counts[row['owner_process_range_id']]+=1;rank_counts[row['dp_rank']]+=1
    require(kernel_count==len(kernel_ids)==23660,'strict kernel universe')
    require(dict(rank_counts)=={'0':11830,'1':11830},'kernel rank conservation')
    for p in processes:
        require(kernel_counts[p['process_range_id']]==int(p['owned_kernel_count']),'kernel rollup conservation')
        require(runtime_counts[p['process_range_id']]==int(p['owned_runtime_call_count']),'runtime rollup conservation')
    aligned=list(rows(resolve_source(live['outputs']['process_alignment']['path'])))
    require(len(aligned)==12544 and {r['process_range_id'] for r in aligned}==set(by_process),'complete process live alignment')
    sample_count=sum(1 for _ in rows(resolve_source(live['outputs']['aligned_samples']['path'])))
    gap_count=sum(1 for _ in rows(resolve_source(live['outputs']['gaps']['path'])))
    require(sample_count==2491806 and gap_count==800,'lossless live samples and gaps')
    dep=summaries['fresh_run_dependency_adapter']
    require(len(dep['rows'])==dep['edge_count']==32492,'dependency edge count')
    require({r['process_range_id'] for r in dep['rows']}==set(by_process),'dependency process coverage')
    # Negative regressions call the same admission implementation.
    rejected=[]
    for field,value in [('status','complete'),('coverage_target_met',False),('lineage_id','other'),('native_controller_lifecycle_completion_claimed',True)]:
        bad=dict(h);bad[field]=value
        try:validate_recovered_status(bad)
        except ValueError:rejected.append(field)
        else:raise ValueError('negative admission accepted: '+field)
    for path in ['../escape','/etc/passwd',str(OLD_PROJECT/'../escape')]:
        try:resolve_source(path)
        except ValueError:pass
        else:raise ValueError('path escape accepted')
    report={'schema_version':1,'status':'admitted_recovered_r07','runtime_run_id':RUN_ID,'lineage_id':RUN_ID,'original_handoff_status':h['status'],'original_handoff_path':str(handoff_path),'original_handoff_sha256':R07_HASH,'native_controller_lifecycle_completion_claimed':False,'native_durable_nfs_completion_claimed':False,'r08_full_predevice_gate_complete':False,'recovery_admission_does_not_replace_R01_R06_artifact_validation':True,'verified_sources':verified,'coverage':{'targets':13568,'processes':len(processes),'request_phases':16,'requests':8,'runtime_calls':len(runtime),'kernels':kernel_count,'kernel_counts_by_rank':dict(rank_counts),'live_samples':sample_count,'live_gaps':gap_count,'dependency_edges':len(dep['rows'])},'negative_admission_regressions':rejected,'original_artifacts_modified':False,'model_or_device_access_performed':False,'admission_tool_sha256':sha(__file__),'resolver_sha256':sha(Path(__file__).with_name('continuation_common.py'))}
    write_new(Path(__file__).parent/'RECOVERED_R07_ADMISSION.json',report)
    print('RECOVERED_R07_ADMITTED',report['coverage'],flush=True)

if __name__=='__main__':main()
