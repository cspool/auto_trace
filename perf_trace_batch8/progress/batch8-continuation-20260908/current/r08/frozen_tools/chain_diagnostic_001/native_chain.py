"""Join native replay PMC -> HIPOPS -> HIP launch -> exact process -> R07 identity."""
from pathlib import Path
import sys
ROOT=Path(__file__).parents[2]
sys.path.insert(0,str(ROOT/'tools/revision_008'))
from r08_native import *
import argparse
import collections
import csv
import sqlite3
import time

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

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--segment',required=True);ap.add_argument('--attempt',required=True);ap.add_argument('--revision',required=True);args=ap.parse_args()
    start=time.monotonic();capture=ROOT/'raw/captures'/args.segment/args.attempt
    execution=read(capture/'control/capture_contract.json')
    require(read(capture/'control/tracee_workload_complete.json')['status']=='complete','complete workload required for chain-only diagnostic')
    for source in read(capture/'raw_inventory_at_exit.json')['files']:
        require(sha(source['path'])==source['sha256'],'sealed capture bytes changed')
    output=output_path(ROOT/'normalized/chain_diagnostics'/args.segment/args.attempt/args.revision,True);require(not output.exists(),'immutable normalization revision');output.mkdir()
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
    db=capture/'capture.db';conn=sqlite3.connect('file:'+str(db)+'?mode=ro&immutable=1',uri=True);conn.row_factory=sqlite3.Row
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
        owner_rows.append({'source_r06_target_id':source_id,'r07_bound_target_id':target['r07_bound_target_id'],'replay_bound_target_id':current['canonical_target_id'],'logical_family_ids':selection['family_ids'],'matched_literal_kernel_count':len(actual),'runtime_shape_match':True})
    save(output/'NATIVE_CHAIN_DIAGNOSTIC.json',{'status':'native_chain_only_no_PMC_acceptance','selected_expected_R07_kernels':len(expected_r07),'eligible_native_dispatches':len(eligible),'full_native_owned_kernel_count':len(all_owned),'current_bound_targets':len(bound),'current_process_markers':len(events),'selected_owner_count':len(pending),'owners':owner_rows,'selection_policy':'R06 corrected request/phase/phase_occurrence identity; runtime q/kv are recorded context, not selection keys','R08_capture_accepted':False,'elapsed_seconds':time.monotonic()-start})
    print('NATIVE_CHAIN_DIAGNOSTIC_COMPLETE',len(eligible),len(all_owned),round(time.monotonic()-start,2),flush=True)
if __name__=='__main__':main()
