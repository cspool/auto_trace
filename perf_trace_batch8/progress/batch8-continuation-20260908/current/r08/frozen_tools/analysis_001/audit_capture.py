"""Independent raw-native row and logical attachment audit; no builder imports."""
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
    conn=sqlite3.connect('file:'+str(capture/'capture.db')+'?mode=ro&immutable=1',uri=True);conn.row_factory=sqlite3.Row
    cfg={int(r['PID']):dict(r) for r in conn.execute('SELECT * FROM CONFIG')}
    symbols=sorted({r['pmc_kernel_symbol'] for r in attrs});decoded=subprocess.check_output(['/usr/bin/c++filt',*symbols],text=True).splitlines();names=dict(zip(symbols,decoded))
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
        check(hipops['BeginNs']==int(pmc['BeginNs'])+offset and hipops['EndNs']==int(pmc['EndNs'])+offset,'exact native hardware timestamp pair')
        matches=conn.execute('SELECT COUNT(*) FROM '+quoted(a['replay_hipops_table'])+' WHERE pid=? AND dev_id=? AND BeginNs=? AND EndNs=?',(pid,device,hipops['BeginNs'],hipops['EndNs'])).fetchone()[0]
        check(matches==1,'unique native timestamp identity')
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
        for k in ['request_id','phase','phase_occurrence','dp_rank','physical_device_id','layer_idx','process_id','fragment_id','q_len','kv_len']:check(cb[k]==ob[k],'observed/replay logical key '+k)
        q=(pid,device,pmc['queue-id']);check(q not in queues or queues[q]==hipops['queue_id'],'native queue namespace consistency');queues[q]=hipops['queue_id'];counts[device]+=1
    check(seen==set(expected) and set(counts)=={0,1},'complete expected DP2 attachments')
    exclusions=[json.loads(l) for l in (out/'excluded_pmc_rows.jsonl').read_text().splitlines()]
    excluded_indices={int(r['pmc_csv_row']) for r in exclusions}
    check(len(excluded_indices)==len(exclusions) and not (excluded_indices&pmc_seen) and excluded_indices|pmc_seen==set(range(2,len(native_pmc)+2)),'lossless raw row partition')
    conn.close()
    result={'status':'complete','independent_audit':True,'segment_id':m['segment_id'],'normalization_manifest_sha256':sha(out/'NORMALIZATION_COMPLETE.json'),'auditor_sha256':sha(Path(__file__)),'raw_database_sha256':dbsha,'raw_pmc_sha256':csvsha,'accepted_dispatches':len(attrs),'excluded_dispatches':len(exclusions),'rank_native_device_counts':dict(counts),'counter_values_recomputed':sum(len(a['counters']) for a in attrs),'exact_native_chain':True,'same_R06_R07_logical_ownership':True,'raw_partition_conserved':True,'replay_timing_used_as_latency':False,'elapsed_seconds':time.monotonic()-start}
    with (out/'INDEPENDENT_AUDIT.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print('R08_INDEPENDENT_AUDIT_COMPLETE',m['segment_id'],len(attrs),round(time.monotonic()-start,2),flush=True)
if __name__=='__main__':main()
