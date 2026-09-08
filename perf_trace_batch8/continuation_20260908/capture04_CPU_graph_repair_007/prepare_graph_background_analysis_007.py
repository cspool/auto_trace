from pathlib import Path
import json,hashlib,shutil,importlib.util
C=Path('/public/home/accl15ptg7/run_R08_R10');R=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');A=R/'tools/analysis_007';shutil.copytree(R/'tools/analysis_006',A,ignore=shutil.ignore_patterns('__pycache__'))
p=A/'normalize_capture.py';s=p.read_text();insert='''def selected_index_unions(processes):
    grouped=collections.defaultdict(list)
    for p in processes:grouped[p['pid'],p['tid']].append((p['native_begin_index'],p['native_end_index']))
    result={}
    for scope,items in grouped.items():
        merged=[]
        for begin,end in sorted(items):
            if merged and begin<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],end)
            else:merged.append([begin,end])
        result[scope]=([x[0] for x in merged],[x[1] for x in merged])
    return result

def outside_selected_index(unions,pid,tid,index):
    begins,ends=unions.get((pid,tid),([],[]));position=bisect.bisect_right(begins,index)-1
    return position<0 or index>ends[position]

'''
s=s.replace('def main():',insert+'def main():',1)
s=s.replace("    native_submissions=collections.defaultdict(list)\n    for pid in pid_ranks:","    native_submissions=collections.defaultdict(list)\n    selected_ranges=selected_index_unions([p for p in native_processes if bound_by_id[p['canonical_target_id']]['source_r06_target_id'] in pending])\n    graph_digest=hashlib.sha256();graph_counts=collections.Counter();graph_count=0\n    selected_launch_keys={(x['kernel']['pid'],x['kernel']['_Index']) for x in eligible.values()}\n    for pid in sorted(pid_ranks):")
s=s.replace("sql='SELECT rowid AS native_rowid,* FROM '+q('HIPOPS_'+ck)+' WHERE Name IN ('+','.join('?' for _ in ids)+')'", "sql='SELECT rowid AS native_rowid,* FROM '+q('HIPOPS_'+ck)+' WHERE Name IN ('+','.join('?' for _ in ids)+') ORDER BY rowid'")
old="            h=dict(hs[0]);require(str(h['args']).split('(',1)[0] in LAUNCH_APIS,'native direct launch API')"
new="""            h=dict(hs[0]);api=str(h['args']).split('(',1)[0]
            if api not in LAUNCH_APIS:
                require(api=='hipGraphLaunch','unknown native kernel launch API')
                require((pid,op['_Index']) not in selected_launch_keys and outside_selected_index(selected_ranges,pid,h['tid'],op['_Index']),'graph dispatch intersects a required selected process range')
                require(h['pid']==op['pid']==pid and op['dev_id']==pid_ranks[pid],'background graph native PID/device identity')
                signature=[pid,op['native_rowid'],op['_Index'],h['native_rowid'],h['tid'],op['dev_id'],h['BeginNs'],h['EndNs']]
                graph_digest.update((json.dumps(signature,separators=(',',':'))+'\\n').encode());graph_counts[pid]+=1;graph_count+=1
                continue
""".rstrip()
assert old in s;s=s.replace(old,new)
needle="    manifest={'status':'complete'"
assert needle in s
s=s.replace(needle,"    graph_path=output/'background_native_graph_classification.json';save(graph_path,{'status':'complete_background_classification','API':'hipGraphLaunch','native_dispatch_count':graph_count,'per_worker_native_dispatch_counts':dict(graph_counts),'ordered_native_identity_sha256':graph_digest.hexdigest(),'identity_fields':['pid','HIPOPS_rowid','HIP_Index','HIP_rowid','HIP_tid','native_device','HIP_BeginNs','HIP_EndNs'],'stable_sort':'worker PID then HIPOPS rowid','selected_owner_count':len(pending),'all_outside_selected_process_index_unions':True,'raw_database_sha256':accepted[0]['raw_database_sha256'],'raw_native_rows_retained_unmodified':True,'classification':'outside selected R06 process scopes; graph kernels are not promoted as directly correlated PMC attributes'})\n"+needle)
s=s.replace("'full_native_chain_proven':True", "'background_native_graph_classification':source_record(graph_path),'full_native_chain_proven':True")
p.write_text(s)
# Independent auditor computes its own interval unions and reads every classified
# graph row from the original DB via a separate SQL join. No builder import.
p=A/'audit_capture.py';s=p.read_text();s=s.replace("seen=set();pmc_seen=set();native_seen=set();counts=collections.Counter();queues={}","seen=set();pmc_seen=set();native_seen=set();counts=collections.Counter();queues={};selected_ranges=collections.defaultdict(set)")
s=s.replace("        native_id=(a['replay_hipops_table'],a['replay_hipops_rowid']);", "        selected_ranges[(int(a['pmc_pid']),tx['tid'])].add((tx['begin_Index'],tx['end_Index']))\n        native_id=(a['replay_hipops_table'],a['replay_hipops_rowid']);")
needle="    conn.close()\n    result="
proof='''    graph=m['background_native_graph_classification'];check(sha(graph['path'])==graph['sha256'],'background graph classification bytes');g=read(graph['path']);check(g['status']=='complete_background_classification' and g['raw_database_sha256']==dbsha and g['all_outside_selected_process_index_unions'] and g['raw_native_rows_retained_unmodified'],'original graph source and declared scope')
    unions={}
    for scope,items in selected_ranges.items():
        merged=[]
        for begin,end in sorted(items):
            if merged and begin<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],end)
            else:merged.append([begin,end])
        unions[scope]=([x[0] for x in merged],[x[1] for x in merged])
    digest_graph=hashlib.sha256();graph_count=0;graph_counts=collections.Counter()
    for pid in sorted({int(a['pmc_pid']) for a in attrs}):
        key=cfg[pid]['KEY'];ids=[x[0] for x in conn.execute('SELECT STR_ID FROM STR_TABLE WHERE CONFIG_KEY=? AND PID=? AND TYPE=6 AND STR_NAME=?',(key,pid,literal))];check(ids,'background exact literal IDs')
        sql='SELECT O.rowid AS oid,O._Index AS idx,O.pid AS op_pid,O.dev_id AS device,H.rowid AS hid,H.pid AS hip_pid,H.tid AS tid,H.BeginNs AS b,H.EndNs AS e FROM '+quoted('HIPOPS_'+key)+' O JOIN '+quoted('HIP_'+key)+' H ON H._Index=O._Index WHERE O.Name IN ('+','.join('?' for _ in ids)+') AND H.args LIKE ? ORDER BY O.rowid'
        previous=-1
        for row in conn.execute(sql,[*ids,'hipGraphLaunch(%']):
            check(row['oid']>previous and row['op_pid']==row['hip_pid']==pid,'unique original graph source and PID');previous=row['oid'];begins,ends=unions.get((pid,row['tid']),([],[]));position=bisect.bisect_right(begins,row['idx'])-1
            check(position<0 or row['idx']>ends[position],'background graph cannot intersect any selected process index range');check((('HIPOPS_'+key),row['oid']) not in native_seen,'graph raw row never accepted as direct PMC')
            signature=[pid,row['oid'],row['idx'],row['hid'],row['tid'],row['device'],row['b'],row['e']];digest_graph.update((json.dumps(signature,separators=(',',':'))+'\\n').encode());graph_count+=1;graph_counts[pid]+=1
    check(graph_count==g['native_dispatch_count'] and {str(k):v for k,v in graph_counts.items()}==g['per_worker_native_dispatch_counts'] and digest_graph.hexdigest()==g['ordered_native_identity_sha256'],'independent complete graph population conservation')
    conn.close()
    result='''
assert needle in s;s=s.replace(needle,proof)
s=s.replace("'raw_partition_conserved':True", "'background_graph_native_dispatches_independently_classified':graph_count,'all_graph_dispatches_outside_selected_scopes':True,'raw_partition_conserved':True")
p.write_text(s)
for p in A.glob('*.py'):compile(p.read_text(),str(p),'exec')
spec=importlib.util.spec_from_file_location('graph_boundary_CPU_gate',A/'normalize_capture.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
processes=[{'pid':10,'tid':20,'native_begin_index':4,'native_end_index':10},{'pid':10,'tid':20,'native_begin_index':8,'native_end_index':14},{'pid':10,'tid':20,'native_begin_index':20,'native_end_index':24}];u=m.selected_index_unions(processes);assert u[(10,20)]==([4,20],[14,24]);checks=[]
for value,expected in [(3,True),(4,False),(10,False),(14,False),(15,True),(19,True),(20,False),(24,False),(25,True)]:assert m.outside_selected_index(u,10,20,value)==expected;checks.append({'HIP_Index':value,'outside_selected':expected})
assert m.outside_selected_index(u,11,20,4) and m.outside_selected_index(u,10,21,4)
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
raw=R/'raw/captures/04_triton_red_fused__to_copy_add_mean_mul_pow_rsqrt_0_pmc/attempt_003';assert json.loads((raw/'execution_manifest.json').read_text())['all_started_processes_terminated'];intersection=R/'raw/runtime_tools/native_graph_selected_intersection_001.json';x=json.loads(intersection.read_text());assert x['all_outside_selected_processes'] and x['selected_native_marker_rows']==1408
proof={'status':'complete','analysis_revision':'analysis_007','changes':'classify only hipGraphLaunch dispatches proven outside every selected process native index interval; retain and hash every original graph identity; selected direct PMC correlation and exact R07 multiplicity unchanged','CPU_interval_boundary_checks':checks,'cross_PID_and_TID_positive_cases':True,'actual_closed_capture_graph_scope_proof':rec(intersection),'actual_raw_execution':rec(raw/'execution_manifest.json'),'all_raw_bytes_preserved_no_new_capture':True,'independent_auditor_rescans_entire_original_graph_population':True,'prior_analysis_gate':rec(R/'validation/NFS_mmap_analysis_CPU_gate_001.json'),'frozen_tools':[rec(p) for p in sorted(A.iterdir()) if p.is_file()],'model_or_device_actions':0}
with (R/'validation/background_graph_analysis_CPU_gate_001.json').open('x') as f:json.dump(proof,f,indent=2);f.write('\n')
print('ANALYSIS_007_CPU_BOUNDARY_GATE_COMPLETE',len(checks)+2,flush=True)
