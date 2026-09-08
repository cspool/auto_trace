"""Fresh, bounded dual-device HIPTX/HIP/PMC capability capture; no model load."""
from r08_native import *
import argparse
import signal
import sqlite3
import time

def bounded(argv,cwd,env,timeout=120):
    cwd.mkdir(parents=True,exist_ok=False)
    start=time.monotonic()
    visible_keys=['HIP_VISIBLE_DEVICES','CUDA_VISIBLE_DEVICES','PYTHONDONTWRITEBYTECODE','LD_LIBRARY_PATH','PYTHONPATH','NO_PROXY','no_proxy']
    record={'argv':list(map(str,argv)),'cwd':str(cwd),'started_realtime_ns':time.time_ns(),'started_monotonic_ns':time.perf_counter_ns(),'environment':{k:env[k] for k in visible_keys if k in env}}
    save(cwd/'command.json',record)
    with (cwd/'stdout.txt').open('x') as out,(cwd/'stderr.txt').open('x') as err:
        p=subprocess.Popen(argv,cwd=cwd,env=env,stdout=out,stderr=err,start_new_session=True)
        try:rc=p.wait(timeout=timeout);timed_out=False
        except subprocess.TimeoutExpired:
            timed_out=True;os.killpg(p.pid,signal.SIGTERM)
            try:rc=p.wait(timeout=15)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);rc=p.wait()
    result={'returncode':rc,'pid':p.pid,'timed_out':timed_out,'seconds':time.monotonic()-start,'ended_realtime_ns':time.time_ns(),'ended_monotonic_ns':time.perf_counter_ns(),'stdout':source_record(cwd/'stdout.txt'),'stderr':source_record(cwd/'stderr.txt')}
    save(cwd/'execution.json',result)
    return result

def db_inspection(path):
    conn=sqlite3.connect('file:'+str(path)+'?mode=ro&immutable=1',uri=True)
    conn.row_factory=sqlite3.Row
    require(conn.execute('PRAGMA quick_check').fetchone()[0]=='ok','native probe database integrity')
    tables={}
    for table,sql in conn.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"):
        require(re.fullmatch(r'[A-Za-z0-9_]+',table),'native table identifier')
        count=conn.execute('SELECT count(*) FROM "'+table+'"').fetchone()[0]
        rows=[dict(row) for row in conn.execute('SELECT rowid AS native_rowid,* FROM "'+table+'" LIMIT 300')]
        tables[table]={'sql':sql,'count':count,'sample_rows':rows}
    conn.close()
    return {'source':source_record(path),'tables':tables,'quick_check':'ok'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--revision',required=True);args=parser.parse_args()
    gate=ROOT/'validation/predevice_capability_gate.json'
    require(read(gate)['status']=='complete','CPU gate before any device query')
    for record in read(gate)['frozen_tools']:
        require(sha(record['path'])==record['sha256'],'frozen capability helper changed')
    source_binding()
    env=clean_env();env['PYTHONPATH']=str(TOOLS)
    root=output_path(ROOT/'preflight'/args.revision)
    require(not root.exists(),'new capability revision');root.mkdir()
    queries=[]
    for name,argv in [('hipprof_help',[str(HIPPROF),'-h']),('hy_smi_help',['/opt/hyhal/bin/hy-smi','--help']),('hy_smi_occupancy',['/opt/hyhal/bin/hy-smi','--showuse','--showmeminfo','vram','--showpids','--showbus','--json']),('rocminfo',['/opt/dtk/bin/rocminfo']),('rocprof_basic',['/opt/dtk/rocprofiler/bin/rocprof','--list-basic']),('rocprof_derived',['/opt/dtk/rocprofiler/bin/rocprof','--list-derived'])]:
        result=bounded(argv,root/name,env)
        queries.append({'name':name,**result})
        require(result['returncode']==0 or (name.startswith('rocprof_') and result['returncode']==1),'current device capability command failed: '+name)
    helptext=(root/'hipprof_help/stdout.txt').read_text()+(root/'hipprof_help/stderr.txt').read_text()
    for flag in ['--pmc','--pmc-read','--pmc-write','--hip-trace','--hiptx-trace','--no-export','--kernel-name']:
        require(flag in helptext,'missing HIPProf flag '+flag)
    require('gfx936' in (root/'rocminfo/stdout.txt').read_text(),'current architecture')
    binary=TOOLS/'r08_native_correlation_probe'
    cases=[]
    for name,mode,token,expected in [('baseline','pmc',None,8),('nonmatching','pmc','r08_guaranteed_absent_token_20260908',0),('read','pmc_read',None,8),('write','pmc_write',None,8)]:
        case=root/name
        argv=collector_argv(mode,token,case,[str(binary),'8'])
        result=bounded(argv,case,env,180)
        raw=list(case.rglob('pmc_results_*.txt'))
        rows=[row for path in raw for row in raw_pmc_rows(path)]
        dbs=[db_inspection(path) for path in case.rglob('*.db') if path.stat().st_size]
        save(case/'native_database_inspection.json',dbs)
        save(case/'native_pmc_rows.json',rows)
        case_result={'case':name,'mode':mode,'token':token,**result,'native_rows':len(rows),'expected_rows':expected,'native_devices':sorted({row['gpu_id'] for row in rows}),'counter_names':sorted({k for row in rows for k in row['counters']}),'db_count':len(dbs),'raw_files':[source_record(p) for p in raw]}
        save(case/'PROBE_RESULT.json',case_result);cases.append(case_result)
        print(json.dumps({k:case_result[k] for k in ['case','returncode','native_rows','native_devices','db_count','seconds']}),flush=True)
        require(result['returncode']==0 and not result['timed_out'],'native capability probe failed '+name)
        require(len(rows)==expected,'native probe dispatch multiplicity '+name)
        if expected:require({row['gpu_id'] for row in rows}=={'0','1'},'native probe device coverage')
    save(root/'CAPABILITY_PROBE_COMPLETE.json',{'status':'complete','queries':queries,'cases':cases,'collector_kernel_filter_empirically_effective':True,'model_initializations':0,'measured_workload_requests':0,'all_started_processes_terminated':True,'predevice_gate_sha256':sha(gate),'source_binding':source_binding()})
    print('CURRENT_CAPABILITY_PROBE_COMPLETE',flush=True)

if __name__=='__main__':main()
