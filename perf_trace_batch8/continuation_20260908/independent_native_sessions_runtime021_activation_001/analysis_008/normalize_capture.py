"""Join native replay PMC -> HIPOPS -> HIP launch -> exact process -> R07 identity."""
from pathlib import Path
import sys
ROOT=Path(__file__).parents[2]
sys.path.insert(0,str(ROOT/'raw/runtime_tools/revision_016'))
from r08_native import *
import argparse
import collections
import bisect
import csv
import sqlite3
import time
from native_session_provenance import load as load_native_union, source_fields

LAUNCH_APIS={'hipLaunchKernel','hipModuleLaunchKernel','hipExtModuleLaunchKernel'}

def csv_rows(path):
    with Path(path).open() as f:yield from csv.DictReader(f)

def records(root,glob):
    for path in sorted(root.glob(glob)):
        with path.open() as f:
            for line in f:
                if line.strip():yield json.loads(line)

def q(name):
    require(re.fullmatch(r'[A-Za-z0-9_]+',name),'native table identifier');return '"'+name+'"'

def write_csv(path,rows,fields):
    with path.open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)

def locate_native_submission(items,begins,submitted):
    position=bisect.bisect_right(begins,submitted)-1
    if position<0:return None
    h,op=items[position]
    if h['BeginNs']<=submitted<=h['EndNs']:return h,op
    return None

def selected_index_unions(processes):
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

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--segment',required=True);ap.add_argument('--attempt',required=True);ap.add_argument('--revision',required=True);args=ap.parse_args()
    start=time.monotonic();capture=ROOT/'raw/captures'/args.segment/args.attempt
    execution=read(capture/'execution_manifest.json')
    require(execution['status']=='raw_capture_complete_pending_exact_attribution','raw capture terminal checkpoint')
    native_union=load_native_union(capture,verify_all=False)
    for source in read(capture/'raw_inventory_at_exit.json')['files']:
        require(sha(source['path'])==source['sha256'],'sealed capture bytes changed')
    output=output_path(ROOT/'normalized/captures'/args.segment/args.attempt/args.revision,True);require(not output.exists(),'immutable normalization revision');output.mkdir()
    logical=read(ROOT/'plans/logical_plan.json');unit=execution['segment'];literal=unit['kernel_name_filter_literal']
    families=[f for f in logical['selected_families'] if f['r06_plan']['plan_id'] in unit['logical_family_ids']]
    pending={}
    for family in families:
        for target in family['targets']:
            if target['state']!='requires_fresh_r08_pmc':continue
            key=target['source_r06_target_id']
            if key not in pending:pending[key]={'target':target,'family_ids':[]}
            pending[key]['family_ids'].append(family['r06_plan']['plan_id'])
    require(pending,'physical pass has no selected native owners')
    r07_root=RUN/'artifacts/R07/resume-042'
    observed_bound={r['canonical_target_id']:r for r in read(r07_root/'contract/r07_bound_target_sidecar.json')['records']}
    observed_kernels={r['kernel_instance_id']:r for r in csv_rows(r07_root/'trace/strict_owned_kernels.csv')}
    bound=list(records(capture/'workload/runtime_bindings','rank*.jsonl'))
    require(len(bound)==13568 and len({r['canonical_target_id'] for r in bound})==13568,'full current bound target universe')
    bound_by_id={r['canonical_target_id']:r for r in bound}
    bound_by_source={r['source_r06_target_id']:r for r in bound if 'source_r06_target_id' in r}
    events=[r for r in records(capture/'workload/overlay_events','rank*/events.*.jsonl') if r.get('marker_kind')=='process']
    require(len(events)==12544 and len({r['range_name'] for r in events})==12544,'complete current exact process markers')
    event_by_name={r['range_name']:r for r in events}
    require(collections.Counter(r['dp_rank'] for r in events)=={0:6272,1:6272},'process DP2 split')
    db=capture/'capture.db';conn=sqlite3.connect('file:'+str(db)+'?mode=ro&immutable=1',uri=True);conn.row_factory=sqlite3.Row;conn.execute('PRAGMA mmap_size=4294967296');conn.execute('PRAGMA cache_size=-1048576')
    require(conn.execute('PRAGMA quick_check').fetchone()[0]=='ok','native database integrity')
    configs={int(r['PID']):dict(r) for r in conn.execute('SELECT * FROM CONFIG')}
    pid_ranks={}
    for event in events:
        if event['pid'] in pid_ranks:require(pid_ranks[event['pid']]==event['dp_rank'],'worker PID rank')
        pid_ranks[event['pid']]=event['dp_rank']
    require(set(pid_ranks.values())=={0,1} and len(pid_ranks)==2,'exact two worker PIDs')
    native_processes=[];marker_seen=collections.Counter();runtime_candidates=collections.defaultdict(list)
    for pid,rank in pid_ranks.items():
        config=configs[pid];key=config['KEY'];tx_table='HIPTX_'+key;hip_table='HIP_'+key
        for native in conn.execute('SELECT rowid AS native_rowid,* FROM '+q(tx_table)):
            name=native['message']
            if name not in event_by_name:continue
            event=event_by_name[name];marker_seen[name]+=1
            require(event['pid']==pid and event['dp_rank']==rank and event['tid']==native['tid'],'exact process PID/TID/rank')
            process={**event,'native_hiptx_table':tx_table,'native_hiptx_rowid':native['native_rowid'],'native_begin_ns':native['BeginNs'],'native_end_ns':native['EndNs'],'native_begin_index':native['begin_Index'],'native_end_index':native['end_Index'],'config_key':key}
            native_processes.append(process)
            query='SELECT rowid AS native_rowid,* FROM '+q(hip_table)+' WHERE _Index>=? AND _Index<=? AND tid=? AND BeginNs>=? AND EndNs<=?'
            for call in conn.execute(query,(native['begin_Index'],native['end_Index'],native['tid'],native['BeginNs'],native['EndNs'])):
                api=str(call['args']).split('(',1)[0]
                if api not in LAUNCH_APIS:continue
                runtime_candidates[(pid,int(call['_Index']))].append((process,dict(call),api))
        print('NATIVE_PROCESS_ROWS',args.segment,rank,len(native_processes),flush=True)
    require(marker_seen==collections.Counter(event_by_name.keys()),'native process marker multiset')
    kernels_by_source=collections.defaultdict(list)
    all_owned=[]
    for (pid,index),candidates in runtime_candidates.items():
        deepest=max(int(p['depth']) for p,_,_ in candidates)
        owners=[row for row in candidates if int(row[0]['depth'])==deepest]
        require(len(owners)==1,'ambiguous deepest exact process owner')
        process,call,api=owners[0]
        require(process['strict_kernel_owner'] and not process['explicit_no_kernel_target'],'kernel launched inside an explicitly zero-work process')
        key=process['config_key'];table='HIPOPS_'+key
        native=list(conn.execute('SELECT rowid AS native_rowid,* FROM '+q(table)+' WHERE _Index=?',(index,)))
        require(len(native)==1,'one native HIPOPS row for owned HIP launch')
        kernel=dict(native[0]);require(kernel['pid']==pid and kernel['dev_id']==process['dp_rank'],'HIP launch/dispatch PID/device')
        name=conn.execute('SELECT STR_NAME FROM STR_TABLE WHERE CONFIG_KEY=? AND PID=? AND STR_ID=? AND TYPE=6',(key,pid,int(kernel['Name']))).fetchone()
        require(name is not None,'native kernel literal table')
        bound_row=bound_by_id[process['canonical_target_id']];source_id=bound_row['source_r06_target_id']
        record={'process':process,'launch':call,'launch_api':api,'kernel':kernel,'kernel_literal':name[0],'source_r06_target_id':source_id,'bound':bound_row,'hipops_table':table}
        kernels_by_source[source_id].append(record);all_owned.append(record)
    eligible={};expected_r07=set();owner_rows=[]
    for source_id,selection in pending.items():
        target=selection['target'];current=bound_by_source[source_id];observed=observed_bound[target['r07_bound_target_id']]
        for field in ['request_id','phase','phase_occurrence','dp_rank','physical_device_id','layer_idx','process_id','fragment_id']:
            require(current[field]==observed[field],'same logical owner/runtime shape mismatch '+field+' '+source_id)
        actual=sorted((r for r in kernels_by_source[source_id] if r['kernel_literal']==literal),key=lambda r:(r['kernel']['_Index'],r['kernel']['BeginNs']))
        expected=sorted((observed_kernels[k] for k in target['exact_literal_kernel_ids']),key=lambda r:(int(r['hip_runtime_index']),int(r['begin_ns'])))
        require(len(actual)==len(expected),'exact R07/replay literal subsequence multiplicity '+source_id)
        for ordinal,(native,old) in enumerate(zip(actual,expected)):
            kernel=native['kernel'];pid=kernel['pid'];config=configs[pid];offset=int(config['TIME_OF_DAY'])-int(config['START_TIME'])
            key=(pid,kernel['dev_id'],kernel['BeginNs']-offset,kernel['EndNs']-offset)
            require(key not in eligible,'ambiguous native hardware timestamp signature')
            eligible[key]={**native,'r07':old,'logical_family_ids':selection['family_ids'],'subsequence_ordinal':ordinal,'native_clock_offset':offset}
            expected_r07.add(old['kernel_instance_id'])
        owner_rows.append({'source_r06_target_id':source_id,'r07_bound_target_id':target['r07_bound_target_id'],'replay_bound_target_id':current['canonical_target_id'],'logical_family_ids':selection['family_ids'],'matched_literal_kernel_count':len(actual),'runtime_shape_match':current['q_len']==observed['q_len'] and current['kv_len']==observed['kv_len'],'observed_q_len':observed['q_len'],'observed_kv_len':observed['kv_len'],'replay_q_len':current['q_len'],'replay_kv_len':current['kv_len']})
    csvpath=capture/'capture.csv'
    with csvpath.open() as f:
        reader=csv.DictReader(f);header=reader.fieldnames;counter_names=header[16:-4]
        require(counter_names==unit['native_counter_names'],'native counter schema bound to capability')
        raw=list(reader)
    symbols=sorted({r['KernelName'] for r in raw})
    decoded=subprocess.check_output(['/usr/bin/c++filt',*symbols],text=True).splitlines();demangled=dict(zip(symbols,decoded))
    # Native PMC DispatchNs is the CPU submission timestamp. Bind it to the
    # unique same-PID/TID native HIP launch with the exact full kernel literal.
    # This is not GPU interval proximity: the submission must lie inside the
    # exact API call, which has exactly one _Index-correlated HIPOPS record.
    native_submissions=collections.defaultdict(list)
    selected_ranges=selected_index_unions([p for p in native_processes if bound_by_id[p['canonical_target_id']]['source_r06_target_id'] in pending])
    graph_digest=hashlib.sha256();graph_counts=collections.Counter();graph_count=0
    selected_launch_keys={(x['kernel']['pid'],x['kernel']['_Index']) for x in eligible.values()}
    for pid in sorted(pid_ranks):
        cfg=configs[pid];ck=cfg['KEY']
        ids=[x[0] for x in conn.execute('SELECT STR_ID FROM STR_TABLE WHERE CONFIG_KEY=? AND PID=? AND TYPE=6 AND STR_NAME=?',(ck,pid,literal))]
        require(ids,'native exact kernel symbol set')
        sql='SELECT rowid AS native_rowid,* FROM '+q('HIPOPS_'+ck)+' WHERE Name IN ('+','.join('?' for _ in ids)+') ORDER BY rowid'
        for op in conn.execute(sql,ids):
            hs=list(conn.execute('SELECT rowid AS native_rowid,* FROM '+q('HIP_'+ck)+' WHERE _Index=?',(op['_Index'],)))
            require(len(hs)==1,'one launch for every exact-literal native dispatch')
            h=dict(hs[0]);api=str(h['args']).split('(',1)[0]
            if api not in LAUNCH_APIS:
                require(api=='hipGraphLaunch','unknown native kernel launch API')
                require((pid,op['_Index']) not in selected_launch_keys and outside_selected_index(selected_ranges,pid,h['tid'],op['_Index']),'graph dispatch intersects a required selected process range')
                require(h['pid']==op['pid']==pid and op['dev_id']==pid_ranks[pid],'background graph native PID/device identity')
                signature=[pid,op['native_rowid'],op['_Index'],h['native_rowid'],h['tid'],op['dev_id'],h['BeginNs'],h['EndNs']]
                graph_digest.update((json.dumps(signature,separators=(',',':'))+'\n').encode());graph_counts[pid]+=1;graph_count+=1
                continue
            require(conn.execute('SELECT COUNT(*) FROM '+q('HIPOPS_'+ck)+' WHERE _Index=?',(op['_Index'],)).fetchone()[0]==1,'one dispatch for API correlation')
            native_submissions[(pid,h['tid'])].append((h,dict(op)))
    submission_begins={}
    for scope,items in native_submissions.items():
        items.sort(key=lambda x:x[0]['BeginNs'])
        require(all(a[0]['EndNs']<b[0]['BeginNs'] for a,b in zip(items,items[1:])),'nonoverlapping same-thread native launch ownership')
        submission_begins[scope]=[x[0]['BeginNs'] for x in items]
    eligible_launches={(x['kernel']['pid'],x['kernel']['_Index']):k for k,x in eligible.items()}
    accepted=[];rejected=[];used=set();queues={};unavailable=0
    for number,row in enumerate(raw,2):
        require(set(row)==set(header) and None not in row,'native CSV schema')
        pid=int(row['pid']);scope=(pid,int(row['tid']));cfg=configs.get(pid)
        submitted=int(row['DispatchNs'])+int(cfg['TIME_OF_DAY'])-int(cfg['START_TIME']) if cfg else None
        key=None;submission_native=None
        if scope in native_submissions and submitted is not None:
            found=locate_native_submission(native_submissions[scope],submission_begins[scope],submitted)
            if found:
                h,op=found
                require(op['dev_id']==int(row['gpu-id']),'submission exact native device')
                require(demangled[row['KernelName']]==literal,'submission exact full literal')
                key=eligible_launches.get((pid,h['_Index']));submission_native=(h,op)
        identity={'pmc_csv_row':number,'pmc_index':row['Index'],'pmc_pid':row['pid'],'pmc_native_device':row['gpu-id'],'pmc_queue_id':row['queue-id'],'pmc_queue_index':row['queue-index'],'pmc_signal':row['sig'],'pmc_kernel_symbol':row['KernelName'],**{'native_'+k:row[k] for k in ['grd','wgr','lds','scr','arch_vgpr','accum_vgpr','sgpr','wave_size']}}
        if key not in eligible:
            rejected.append({**identity,'reason':'outside_R06_selected_exact_marker_owned_dispatch_set'});continue
        native=eligible[key];old=native['r07'];kernel=native['kernel'];process=native['process']
        require(key not in used,'duplicate accepted native PMC dispatch');used.add(key)
        require(demangled[row['KernelName']]==native['kernel_literal']==literal,'exact full literal chain')
        require(row['tid']==str(native['launch']['tid']),'native PMC/HIP launch TID')
        queue_key=(key[0],key[1],row['queue-id'])
        require(queue_key not in queues or queues[queue_key]==kernel['queue_id'],'consistent native queue mapping');queues[queue_key]=kernel['queue_id']
        counters={name:(None if row[name]=='NONE' else int(row[name])) for name in counter_names}
        unavailable+=sum(v is None for v in counters.values())
        attribute={'physical_attribute_id':hashlib.sha256((str(csvpath)+':'+str(number)).encode()).hexdigest(),'runtime_run_id':'batch8-dp2-fresh-003','runtime_goal':'R08','lineage_id':'batch8-dp2-fresh-003','segment_id':args.segment,'capture_attempt':args.attempt,'counter_mode':unit['mode'],'evidence_class':'replay_projected','r07_kernel_instance_id':old['kernel_instance_id'],'r07_process_range_id':old['owner_process_range_id'],'r07_bound_target_id':old['owner_canonical_target_id'],'source_r06_target_id':native['source_r06_target_id'],'replay_bound_target_id':process['canonical_target_id'],'logical_family_ids':native['logical_family_ids'],'request_id':old['request_id'],'dp_rank':int(old['dp_rank']),'native_device':int(old['native_device']),'kernel_name_filter_literal':literal,'collector_kernel_name_token':unit['collector_kernel_name_token'],'kernel_subsequence_ordinal':native['subsequence_ordinal'],**identity,'replay_hipops_table':native['hipops_table'],'replay_hipops_rowid':kernel['native_rowid'],'replay_hip_runtime_table':'HIP_'+process['config_key'],'replay_hip_runtime_rowid':native['launch']['native_rowid'],'replay_hip_runtime_index':kernel['_Index'],'replay_hip_runtime_api':native['launch_api'],'replay_hiptx_table':process['native_hiptx_table'],'replay_hiptx_rowid':process['native_hiptx_rowid'],'replay_exact_process_marker':process['range_name'],'replay_hipops_queue_id':kernel['queue_id'],'native_correlation_rule':'cpu_submission_inside_unique_native_HIP_launch_v1','pmc_dispatch_monotonic_ns':int(row['DispatchNs']),'pmc_dispatch_native_realtime_ns':submitted,'GPU_timestamp_pair_equal_after_CONFIG_conversion':key==(pid,int(row['gpu-id']),int(row['BeginNs']),int(row['EndNs'])),'native_signature_begin_monotonic_ns':int(row['BeginNs']),'native_signature_end_monotonic_ns':int(row['EndNs']),'native_CONFIG_clock_offset':native['native_clock_offset'],'raw_csv_path':str(csvpath),'raw_csv_sha256':sha(csvpath) if not accepted else accepted[0]['raw_csv_sha256'],'raw_database_sha256':sha(db) if not accepted else accepted[0]['raw_database_sha256'],'counters':counters,'counter_units':'native counter counts; semantic derived units separately specified in the model','observed_q_len':observed_bound[old['owner_canonical_target_id']]['q_len'],'observed_kv_len':observed_bound[old['owner_canonical_target_id']]['kv_len'],'replay_q_len':native['bound']['q_len'],'replay_kv_len':native['bound']['kv_len'],'runtime_shape_match':all(native['bound'][k]==observed_bound[old['owner_canonical_target_id']][k] for k in ['q_len','kv_len']),'projection_context':'same corrected R06 request/phase/occurrence target and exact native kernel subsequence; runtime scheduler shapes are separately recorded','direct_R07_resource_measurement_claimed':False,'counter_payload_availability':'complete' if all(v is not None for v in counters.values()) else 'partial','replay_duration_used_as_observed_latency':False}
        attribute.update(source_fields(native_union,pid,number))
        accepted.append(attribute)
    require(used==set(eligible),'missing PMC payload for a selected native dispatch')
    require({r['r07_kernel_instance_id'] for r in accepted}==expected_r07,'exact observed R07 kernel attachment conservation')
    require(unavailable==0,'selected required native counter payload unavailable')
    with (output/'dispatch_attributes.jsonl').open('x') as f:
        for row in accepted:f.write(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n')
    fields=[k for k in accepted[0] if k!='counters']+counter_names
    wide=[{**{k:(json.dumps(v,separators=(',',':')) if isinstance(v,list) else v) for k,v in r.items() if k!='counters'},**r['counters']} for r in accepted]
    write_csv(output/'dispatch_attributes.csv',wide,fields)
    with (output/'excluded_pmc_rows.jsonl').open('x') as f:
        for row in rejected:f.write(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n')
    save(output/'logical_owner_multiplicity.json',owner_rows)
    graph_path=output/'background_native_graph_classification.json';save(graph_path,{'status':'complete_background_classification','API':'hipGraphLaunch','native_dispatch_count':graph_count,'per_worker_native_dispatch_counts':dict(graph_counts),'ordered_native_identity_sha256':graph_digest.hexdigest(),'identity_fields':['pid','HIPOPS_rowid','HIP_Index','HIP_rowid','HIP_tid','native_device','HIP_BeginNs','HIP_EndNs'],'stable_sort':'worker PID then HIPOPS rowid','selected_owner_count':len(pending),'all_outside_selected_process_index_unions':True,'raw_database_sha256':accepted[0]['raw_database_sha256'],'raw_native_rows_retained_unmodified':True,'classification':'outside selected R06 process scopes; graph kernels are not promoted as directly correlated PMC attributes'})
    manifest={'status':'complete','runtime_run_id':'batch8-dp2-fresh-003','segment_id':args.segment,'counter_mode':unit['mode'],'capture':source_record(capture/'execution_manifest.json'),'normalizer':source_record(Path(__file__)),'raw_pmc_rows':len(raw),'accepted_rows':len(accepted),'excluded_rows':len(rejected),'mapped_R07_kernel_count':len(expected_r07),'current_process_markers':len(events),'current_bound_targets':len(bound),'native_owned_kernel_count':len(all_owned),'selected_owner_count':len(pending),'counter_count':len(counter_names),'missing_selected_counter_cells':unavailable,'rank_counts':dict(collections.Counter(r['dp_rank'] for r in accepted)),'native_device_counts':dict(collections.Counter(r['native_device'] for r in accepted)),'logical_family_ids':unit['logical_family_ids'],'dispatch_attributes':source_record(output/'dispatch_attributes.jsonl'),'dispatch_attributes_csv':source_record(output/'dispatch_attributes.csv'),'excluded_rows_file':source_record(output/'excluded_pmc_rows.jsonl'),'owner_multiplicity':source_record(output/'logical_owner_multiplicity.json'),'background_native_graph_classification':source_record(graph_path),'full_native_chain_proven':True,'native_correlation_method':'native PMC CPU submission timestamp inside unique same-PID/TID exact-literal native HIP launch with CONFIG conversion and no tolerance; one HIPOPS per native API _Index, same device; deepest exact HIPTX process -> logical R06 target -> R07 kernel subsequence; GPU timestamp equality retained as diagnostic only','R07_observed_clock_modified':False,'all_attributes_replay_projected':True,'runtime_shape_match_counts':dict(collections.Counter(str(r['runtime_shape_match']) for r in accepted)),'elapsed_seconds':time.monotonic()-start}
    manifest.update(native_database_source_kind='lossless_derived_union_of_retained_native_sessions' if native_union else 'native_single_session',native_session_union=native_union['_manifest_record'] if native_union else None,original_native_session_count=len(native_union['source_sessions']) if native_union else 1)
    save(output/'NORMALIZATION_COMPLETE.json',manifest);conn.close()
    print('R08_NORMALIZATION_COMPLETE',args.segment,len(accepted),len(rejected),round(time.monotonic()-start,2),flush=True)

if __name__=='__main__':main()
