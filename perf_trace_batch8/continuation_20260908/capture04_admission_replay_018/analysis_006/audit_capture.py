"""Independent raw-native row and logical attachment audit; no builder imports."""
import bisect
import argparse, collections, csv, hashlib, json, re, sqlite3, subprocess, time
from pathlib import Path
ROOT=Path(__file__).parents[2]
RUN=ROOT.parents[2]
def check(x,m):
    if not x:raise RuntimeError(m)
def read(p):return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def rows(p):
    with Path(p).open() as f:yield from csv.DictReader(f)
def quoted(s):
    check(re.fullmatch('[A-Za-z0-9_]+',s),'unsafe native identifier');return '"'+s+'"'
def at(conn,table,rowid):
    result=conn.execute('SELECT * FROM '+quoted(table)+' WHERE rowid=?',(rowid,)).fetchone()
    check(result is not None,'missing native row');return dict(result)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--normalization',required=True);args=ap.parse_args()
    start=time.monotonic();out=Path(args.normalization);check(out.is_relative_to(ROOT/'normalized/captures') and '..' not in out.parts,'audit output scope')
    m=read(out/'NORMALIZATION_COMPLETE.json');check(m['status']=='complete','builder checkpoint')
    for key in ['capture','normalizer','dispatch_attributes','dispatch_attributes_csv','excluded_rows_file','owner_multiplicity']:
        check(sha(m[key]['path'])==m[key]['sha256'],'input hash '+key)
    e=read(m['capture']['path']);capture=Path(m['capture']['path']).parent
    unit=e['segment'];literal=unit['kernel_name_filter_literal'];mode=unit['mode']
    check(e['all_started_processes_terminated'] and e['workload']['status']=='complete','terminal full workload')
    driver=read(capture/'workload/driver.json');check(driver['completed']==8 and driver['total_completion_tokens']==8192,'batch8 completion')
    attrs=[json.loads(l) for l in (out/'dispatch_attributes.jsonl').read_text().splitlines()]
    native_pmc=list(rows(capture/'capture.csv'));oldroot=RUN/'artifacts/R07/resume-042'
    oldkernels={r['kernel_instance_id']:r for r in rows(oldroot/'trace/strict_owned_kernels.csv')}
    oldprocess={r['process_range_id']:r for r in rows(oldroot/'trace/process_ranges.csv')}
    oldbound={r['canonical_target_id']:r for r in read(oldroot/'contract/r07_bound_target_sidecar.json')['records']}
    bindings=[]
    for p in sorted((capture/'workload/runtime_bindings').glob('rank*.jsonl')):bindings.extend(json.loads(l) for l in p.read_text().splitlines())
    bound={r['canonical_target_id']:r for r in bindings};check(len(bound)==13568,'complete current binding universe')
    plan=read(ROOT/'plans/logical_plan.json');expected=collections.defaultdict(set)
    for f in plan['selected_families']:
        fid=f['r06_plan']['plan_id']
        if fid not in unit['logical_family_ids']:continue
        for t in f['targets']:
            if t['state']=='requires_fresh_r08_pmc':
                for kid in t['exact_literal_kernel_ids']:expected[kid].add(fid)
    check(len(attrs)==len(expected),'physical attribute denominator')
    conn=sqlite3.connect('file:'+str(capture/'capture.db')+'?mode=ro&immutable=1',uri=True);conn.row_factory=sqlite3.Row;conn.execute('PRAGMA mmap_size=4294967296');conn.execute('PRAGMA cache_size=-1048576')
    cfg={int(r['PID']):dict(r) for r in conn.execute('SELECT * FROM CONFIG')}
    symbols=sorted({r['pmc_kernel_symbol'] for r in attrs});decoded=subprocess.check_output(['/usr/bin/c++filt',*symbols],text=True).splitlines();names=dict(zip(symbols,decoded))
    # Scan each native API table once. Repeating a tid/time range scan for
    # each metric would recreate the R07 quadratic-query failure mode.
    launch_envelopes={};launch_begin_arrays={}
    for pid in {int(a['pmc_pid']) for a in attrs}:
        for tid in {int(x['tid']) for x in native_pmc if int(x['pid'])==pid}:
            table='HIP_'+cfg[pid]['KEY']
            values=[(int(x[0]),int(x[1]),int(x[2])) for x in conn.execute('SELECT BeginNs,EndNs,_Index FROM '+quoted(table)+' WHERE tid=? AND (args LIKE ? OR args LIKE ? OR args LIKE ?)',(tid,'hipLaunchKernel(%','hipModuleLaunchKernel(%','hipExtModuleLaunchKernel(%'))]
            values.sort();check(all(x[1]<=y[0] for x,y in zip(values,values[1:])),'all native direct launches on one thread do not overlap')
            launch_envelopes[pid,tid]=values;launch_begin_arrays[pid,tid]=[x[0] for x in values]
    seen=set();pmc_seen=set();native_seen=set();counts=collections.Counter();queues={}
    dbsha=sha(capture/'capture.db');csvsha=sha(capture/'capture.csv')
    for a in attrs:
        kid=a['r07_kernel_instance_id'];check(kid not in seen and kid in expected,'unique expected R07 attachment');seen.add(kid)
        check(set(a['logical_family_ids'])==expected[kid],'logical family sharing conservation')
        check(a['counter_mode']==mode and a['kernel_name_filter_literal']==literal,'counter/literal plan binding')
        check(a['evidence_class']=='replay_projected' and not a['replay_duration_used_as_observed_latency'],'replay boundary')
        check(a['raw_csv_sha256']==csvsha and a['raw_database_sha256']==dbsha,'native byte identity')
        n=int(a['pmc_csv_row']);check(n not in pmc_seen,'duplicate raw PMC row');pmc_seen.add(n);pmc=native_pmc[n-2]
        for field,native in [('pmc_index','Index'),('pmc_pid','pid'),('pmc_native_device','gpu-id'),('pmc_queue_id','queue-id'),('pmc_queue_index','queue-index'),('pmc_signal','sig'),('pmc_kernel_symbol','KernelName')]:check(str(a[field])==pmc[native],'PMC identity '+field)
        for k,v in a['counters'].items():check(v==(None if pmc[k]=='NONE' else int(pmc[k])),'counter value '+k)
        check(list(a['counters'])!=[] and set(a['counters'])==set(unit['native_counter_names']),'full native counter schema')
        for k in ['grd','wgr','lds','scr','arch_vgpr','accum_vgpr','sgpr','wave_size']:check(a['native_'+k]==pmc[k],'resource property '+k)
        hipops=at(conn,a['replay_hipops_table'],a['replay_hipops_rowid']);hip=at(conn,a['replay_hip_runtime_table'],a['replay_hip_runtime_rowid']);tx=at(conn,a['replay_hiptx_table'],a['replay_hiptx_rowid'])
        native_id=(a['replay_hipops_table'],a['replay_hipops_rowid']);check(native_id not in native_seen,'duplicate native dispatch');native_seen.add(native_id)
        pid=int(pmc['pid']);device=int(pmc['gpu-id']);config=cfg[pid];offset=int(config['TIME_OF_DAY'])-int(config['START_TIME'])
        check(hipops['pid']==pid and hipops['dev_id']==device==a['dp_rank']==a['native_device'],'native PID/device/rank')
        submitted=int(pmc['DispatchNs'])+offset
        check(hip['BeginNs']<=submitted<=hip['EndNs'],'native CPU submission inside exact API call without tolerance')
        check(a['native_correlation_rule']=='cpu_submission_inside_unique_native_HIP_launch_v1' and a['pmc_dispatch_native_realtime_ns']==submitted and a['pmc_dispatch_monotonic_ns']==int(pmc['DispatchNs']),'explicit native submission identity')
        envelopes=launch_envelopes[pid,int(pmc['tid'])];position=bisect.bisect_right(launch_begin_arrays[pid,int(pmc['tid'])],submitted)-1
        check(position>=0 and envelopes[position][0]<=submitted<=envelopes[position][1] and envelopes[position][2]==hip['_Index'],'independently unique native launch containing CPU submission')
        check(conn.execute('SELECT COUNT(*) FROM '+quoted(a['replay_hipops_table'])+' WHERE _Index=?',(hip['_Index'],)).fetchone()[0]==1,'one native dispatch per submission-owned launch')
        check(a['GPU_timestamp_pair_equal_after_CONFIG_conversion']==(hipops['BeginNs']==int(pmc['BeginNs'])+offset and hipops['EndNs']==int(pmc['EndNs'])+offset),'lossless GPU clock diagnostic')
        check(hip['_Index']==hipops['_Index']==a['replay_hip_runtime_index'],'native launch correlation')
        check(hip['tid']==int(pmc['tid'])==tx['tid'],'native launch/marker thread')
        check(tx['begin_Index']<=hip['_Index']<=tx['end_Index'] and tx['BeginNs']<=hip['BeginNs']<=hip['EndNs']<=tx['EndNs'],'marker native index and temporal containment')
        check(tx['message']==a['replay_exact_process_marker'],'exact marker text')
        name=conn.execute('SELECT STR_NAME FROM STR_TABLE WHERE CONFIG_KEY=? AND PID=? AND STR_ID=? AND TYPE=6',(config['KEY'],pid,int(hipops['Name']))).fetchone()
        check(name and name[0]==names[pmc['KernelName']]==literal,'exact full literal')
        old=oldkernels[kid];proc=oldprocess[old['owner_process_range_id']];ob=oldbound[old['owner_canonical_target_id']];cb=bound[a['replay_bound_target_id']]
        check(a['r07_process_range_id']==old['owner_process_range_id'] and a['r07_bound_target_id']==old['owner_canonical_target_id'],'observed owner identity')
        check(old['native_kernel_name']==literal and int(old['native_device'])==device,'observed literal/device')
        check(cb['source_r06_target_id']==ob['source_r06_target_id']==a['source_r06_target_id'],'same logical source')
        for k in ['request_id','phase','phase_occurrence','dp_rank','physical_device_id','layer_idx','process_id','fragment_id']:check(cb[k]==ob[k],'observed/replay logical key '+k)
        check(a['observed_q_len']==ob['q_len'] and a['observed_kv_len']==ob['kv_len'] and a['replay_q_len']==cb['q_len'] and a['replay_kv_len']==cb['kv_len'],'lossless runtime shape context')
        check(a['runtime_shape_match']==(cb['q_len']==ob['q_len'] and cb['kv_len']==ob['kv_len']) and a['direct_R07_resource_measurement_claimed'] is False,'honest replay shape projection boundary')
        q=(pid,device,pmc['queue-id']);check(q not in queues or queues[q]==hipops['queue_id'],'native queue namespace consistency');queues[q]=hipops['queue_id'];counts[device]+=1
    check(seen==set(expected) and set(counts)=={0,1},'complete expected DP2 attachments')
    exclusions=[json.loads(l) for l in (out/'excluded_pmc_rows.jsonl').read_text().splitlines()]
    excluded_indices={int(r['pmc_csv_row']) for r in exclusions}
    check(len(excluded_indices)==len(exclusions) and not (excluded_indices&pmc_seen) and excluded_indices|pmc_seen==set(range(2,len(native_pmc)+2)),'lossless raw row partition')
    conn.close()
    result={'status':'complete','independent_audit':True,'segment_id':m['segment_id'],'normalization_manifest_sha256':sha(out/'NORMALIZATION_COMPLETE.json'),'auditor_sha256':sha(Path(__file__)),'raw_database_sha256':dbsha,'raw_pmc_sha256':csvsha,'accepted_dispatches':len(attrs),'excluded_dispatches':len(exclusions),'rank_native_device_counts':dict(counts),'counter_values_recomputed':sum(len(a['counters']) for a in attrs),'exact_native_chain':True,'same_R06_R07_logical_ownership':True,'raw_partition_conserved':True,'replay_timing_used_as_latency':False,'runtime_shape_match_counts':dict(collections.Counter(str(a['runtime_shape_match']) for a in attrs)),'elapsed_seconds':time.monotonic()-start}
    with (out/'INDEPENDENT_AUDIT.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print('R08_INDEPENDENT_AUDIT_COMPLETE',m['segment_id'],len(attrs),round(time.monotonic()-start,2),flush=True)
if __name__=='__main__':main()
