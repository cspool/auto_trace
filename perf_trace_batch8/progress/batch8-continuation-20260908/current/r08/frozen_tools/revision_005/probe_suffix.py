"""Consume the successful baseline CSV and collect only the unstarted probe suffix."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).parents[2]
sys.path.insert(0,str(ROOT/'tools/revision_004'))
from r08_native import *
from probe_current_capability import bounded,db_inspection
import csv
import sqlite3

def pmc_rows(path):
    if not path.exists() or not path.stat().st_size:return []
    with path.open() as f:
        reader=csv.DictReader(f);header=reader.fieldnames
        require(header[:16]==['Index','KernelName','gpu-id','queue-id','queue-index','pid','tid','grd','wgr','lds','scr','arch_vgpr','accum_vgpr','sgpr','wave_size','sig'],'native identity schema')
        require(header[-4:]==['DispatchNs','BeginNs','EndNs','CompleteNs'],'native timestamp schema')
        rows=list(reader)
    for row in rows:
        require(set(row)==set(header) and None not in row,'native CSV exact columns')
        for counter in header[16:-4]:int(row[counter])
    return rows

def exact_native_chains(case,rows):
    if not rows:return []
    db=case/'capture.db';conn=sqlite3.connect('file:'+str(db)+'?mode=ro&immutable=1',uri=True);conn.row_factory=sqlite3.Row
    configs={str(r['PID']):dict(r) for r in conn.execute('SELECT * FROM CONFIG')}
    symbols=sorted({r['KernelName'] for r in rows})
    decoded=subprocess.check_output(['/usr/bin/c++filt',*symbols],text=True).splitlines()
    demangled=dict(zip(symbols,decoded));chains=[];used=set()
    for row in rows:
        config=configs[row['pid']];key=config['KEY'];offset=int(config['TIME_OF_DAY'])-int(config['START_TIME'])
        begin=int(row['BeginNs'])+offset;end=int(row['EndNs'])+offset
        query=f'SELECT rowid AS native_rowid,* FROM HIPOPS_{key} WHERE pid=? AND dev_id=? AND queue_id=? AND BeginNs=? AND EndNs=?'
        kernels=list(conn.execute(query,(int(row['pid']),int(row['gpu-id']),row['queue-id'],begin,end)))
        require(len(kernels)==1,'unique exact native hardware timestamp identity, PID, device, queue')
        kernel=dict(kernels[0]);nativekey=(key,kernel['native_rowid']);require(nativekey not in used,'duplicate native dispatch');used.add(nativekey)
        name=conn.execute('SELECT STR_NAME FROM STR_TABLE WHERE CONFIG_KEY=? AND PID=? AND STR_ID=? AND TYPE=6',(key,int(row['pid']),int(kernel['Name']))).fetchone()[0]
        require(name==demangled[row['KernelName']],'full literal native PMC/HIPOPS match')
        launch=list(conn.execute(f'SELECT rowid AS native_rowid,* FROM HIP_{key} WHERE _Index=?',(kernel['_Index'],)))
        require(len(launch)==1 and 'LaunchKernel' in launch[0]['args'],'native HIP launch index')
        launch=dict(launch[0])
        markers=list(conn.execute(f'SELECT rowid AS native_rowid,* FROM HIPTX_{key} WHERE pid=? AND tid=? AND begin_Index<=? AND end_Index>=? AND BeginNs<=? AND EndNs>=?',(int(row['pid']),launch['tid'],launch['_Index'],launch['_Index'],launch['BeginNs'],launch['EndNs'])))
        require(len(markers)==1,'probe exact marker and native launch containment')
        marker=dict(markers[0])
        chains.append({'pmc_index':row['Index'],'pmc_queue_index':row['queue-index'],'pmc_signal':row['sig'],'pid':int(row['pid']),'native_device':int(row['gpu-id']),'queue_id':row['queue-id'],'full_kernel_literal':name,'hipops_table':'HIPOPS_'+key,'hipops_rowid':kernel['native_rowid'],'hip_runtime_index':kernel['_Index'],'hip_runtime_rowid':launch['native_rowid'],'hiptx_rowid':marker['native_rowid'],'hiptx_marker':marker['message'],'native_clock_offset_from_CONFIG':offset,'correlation_method':'Exact native hardware BeginNs and EndNs identity across formats, with CONFIG clock conversion, PID/device/queue/full literal and unique HIPOPS row; HIPOPS _Index joins the HIP launch inside its HIPTX range.','replay_interval_overlap_used_as_join':False})
    conn.close();return chains

def main():
    gate=read(ROOT/'validation/predevice_capability_gate.json')
    for record in gate['frozen_tools']:require(sha(record['path'])==record['sha256'],'original frozen helper')
    extension=ROOT/'validation/capability_suffix_cpu_gate.json'
    require(read(extension)['tool_sha256']==sha(__file__),'suffix CPU checkpoint')
    root=ROOT/'preflight/native_probe_003';root.mkdir(parents=True,exist_ok=False)
    baseline=ROOT/'preflight/native_probe_002/baseline'
    rows=pmc_rows(baseline/'capture.csv');require(len(rows)==8,'preserved baseline native CSV')
    baseline_chains=exact_native_chains(baseline,rows)
    save(root/'baseline_csv_repair.json',{'status':'complete','original_raw_csv':source_record(baseline/'capture.csv'),'original_raw_db':source_record(baseline/'capture.db'),'row_count':len(rows),'native_chains':baseline_chains,'capture_rerun':False,'reason':'Native HIPProf successfully merged PMC text into capture.csv and removed temporary text; prior raw-text-only postcheck missed these valid rows.'})
    cases=[{'case':'baseline','mode':'pmc','csv':source_record(baseline/'capture.csv'),'db':source_record(baseline/'capture.db'),'rows':8,'native_chains':baseline_chains}]
    env=clean_env()
    for name,mode,token,expected in [('nonmatching','pmc','r08_guaranteed_absent_token_20260908',0),('read','pmc_read',None,8),('write','pmc_write',None,8)]:
        case=root/name
        argv=collector_argv(mode,token,case,[str(TOOLS/'r08_native_correlation_probe'),'8'])
        result=bounded(argv,case,env,180);require(result['returncode']==0 and not result['timed_out'],'native probe lifecycle '+name)
        rows=pmc_rows(case/'capture.csv');require(len(rows)==expected,'native CSV dispatch count '+name)
        if expected:require({r['gpu-id'] for r in rows}=={'0','1'},'dual-device PMC coverage')
        chains=exact_native_chains(case,rows)
        case_result={'case':name,'mode':mode,'execution':result,'csv':source_record(case/'capture.csv') if (case/'capture.csv').exists() else None,'db':source_record(case/'capture.db'),'rows':len(rows),'native_chains':chains}
        save(case/'PROBE_COMPLETE.json',case_result);cases.append(case_result)
        print('NATIVE_PROBE_COMPLETE',name,len(rows),'native chains',len(chains),flush=True)
    schemas={}
    for case in cases:
        if case['case']=='nonmatching':continue
        with Path(case['csv']['path']).open() as f:header=next(csv.reader(f))
        schemas[case['mode']]={'columns':header,'counter_names':header[16:-4],'native_counter_count':len(header)-20,'source':case['csv']}
    save(root/'CAPABILITY_PROBE_COMPLETE.json',{'status':'complete','schemas':schemas,'cases':cases,'collector_kernel_filter_empirically_effective':True,'full_literal_native_attribution_probe_passed':True,'native_HIPTXOPS_derived_join_skipped_by_no_export':True,'observed_clock_source':'R07_only','model_initializations':0,'all_started_processes_terminated':True,'original_cpu_gate':source_record(ROOT/'validation/predevice_capability_gate.json'),'suffix_cpu_gate':source_record(extension)})
    print('CURRENT_CAPABILITY_PROBE_COMPLETE',flush=True)

if __name__=='__main__':main()
