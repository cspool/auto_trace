"""Bounded CPU-only verification of published R07 SQLite evidence on this host."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

CONTROL = Path('/public/home/accl15ptg7/run_R08_R10')
PROJECT = Path('/public/home/accl15ptg7/auto_trace')
TAG = 'perf-trace-batch8-r07-attempt043-open-writer-db-20260904'
CATALOG = json.loads((PROJECT/'perf_trace_batch8/releases/batch8-r08-continuation-20260908/RELEASE_CATALOG.json').read_text())
ASSETS = next(r['assets'] for r in CATALOG['releases'] if r['tag'] == TAG)
ROOT = Path('/dev/shm/r07_cpu_validation_001')
REPORT = CONTROL/'r07_cpu_validation_001'
TRACE = PROJECT/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R07/resume-042/trace'
SOURCE_HASH = '0ea77cdac40926182c4e04fc29e687e62df9b2cac50296c7e399817c583690b0'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(16*1024*1024),b''):h.update(b)
    return h.hexdigest()

def emit(label, **values):
    print(json.dumps({'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'event':label,**values}),flush=True)

def save(name, value):
    with (REPORT/name).open('x') as f:json.dump(value,f,indent=2);f.write('\n')

def ident(name):
    assert re.fullmatch('[A-Za-z0-9_]+',name),name
    return '"'+name+'"'

def main():
    started=time.monotonic()
    REPORT.mkdir(exist_ok=False)
    ROOT.mkdir(exist_ok=False)
    parts=sorted((a for a in ASSETS if '.db.gz.part-' in a['name']),key=lambda a:a['name'])
    paths=[CONTROL/'downloads'/TAG/a['name'] for a in parts]
    wait_deadline=time.monotonic()+7200
    while not all(p.exists() for p in paths):
        assert time.monotonic()<wait_deadline,'source download wait deadline'
        emit('awaiting_verified_download',ready=sum(p.exists() for p in paths),total=len(paths))
        time.sleep(30)
    stream_hash=hashlib.sha256()
    for a,p in zip(parts,paths):
        assert p.stat().st_size==a['size'] and sha(p)==a['sha256'],p
        with p.open('rb') as f:
            for b in iter(lambda:f.read(16*1024*1024),b''):stream_hash.update(b)
    expected=(CONTROL/'downloads'/TAG/'ARCHIVE_STREAM_SHA256').read_text().split()[0]
    assert stream_hash.hexdigest()==expected,'compressed stream hash'
    source=ROOT/'capture.source.db'
    emit('decompression_started')
    cat=subprocess.Popen(['cat',*map(str,paths)],stdout=subprocess.PIPE)
    digest=hashlib.sha256();total=0
    with gzip.GzipFile(fileobj=cat.stdout) as archive,source.open('xb') as dest:
        for b in iter(lambda:archive.read(16*1024*1024),b''):
            dest.write(b);digest.update(b);total+=len(b)
    assert cat.wait()==0
    assert total==8958377984 and digest.hexdigest()==SOURCE_HASH,'source DB identity'
    source.chmod(0o444)
    emit('source_verified',bytes=total,sha256=digest.hexdigest())
    conn=sqlite3.connect('file:'+str(source)+'?mode=ro&immutable=1',uri=True)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    deadline=time.monotonic()+600
    conn.set_progress_handler(lambda:1 if time.monotonic()>deadline else 0,100000)
    check_start=time.monotonic()
    assert conn.execute('PRAGMA quick_check').fetchone()[0]=='ok'
    quick_seconds=time.monotonic()-check_start
    tables={r['name']:r['sql'] for r in conn.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")}
    save('source_schema.json',tables)
    emit('source_quick_check_ok',seconds=quick_seconds,tables=len(tables))
    schemas={name:[r['name'] for r in conn.execute('PRAGMA table_info('+ident(name)+')')] for name in tables}
    save('source_columns.json',schemas)
    checks=[]
    specs=[('process_ranges.csv','hiptx_table','hiptx_rowid',{'begin_ns':'BeginNs','end_ns':'EndNs','hiptx_range_index':'_Index','pid':'pid','tid':'tid'}),
           ('hip_runtime_calls.csv','hip_runtime_table','hip_runtime_rowid',{'begin_ns':'BeginNs','end_ns':'EndNs','hip_runtime_index':'_Index','pid':'pid','tid':'tid'}),
           ('strict_owned_kernels.csv','native_device_table','native_device_rowid',{'begin_ns':'BeginNs','end_ns':'EndNs','native_device_index':'_Index','pid':'pid','native_device':'dev_id','queue_id':'queue_id'})]
    for filename,tablefield,rowfield,fieldmap in specs:
        count=0;begun=time.monotonic();by_table={}
        with (TRACE/filename).open() as f:
            for row in csv.DictReader(f):
                table=row[tablefield]
                assert table in tables,(filename,table)
                native=conn.execute('SELECT * FROM '+ident(table)+' WHERE rowid=?',(int(row[rowfield]),)).fetchone()
                assert native is not None,(filename,row[rowfield])
                for column,native_column in fieldmap.items():
                    assert native_column in schemas[table],(table,native_column)
                    if column in row and row[column]!='':
                        assert str(native[native_column])==row[column],(filename,count,column,native[native_column],row[column])
                count+=1;by_table[table]=by_table.get(table,0)+1
                if count%50000==0:emit('native_row_validation_progress',file=filename,rows=count)
        item={'file':filename,'sha256':sha(TRACE/filename),'rows':count,'native_rows_exact':True,'fields':fieldmap,'tables':by_table,'seconds':time.monotonic()-begun}
        checks.append(item);emit('native_row_validation_complete',**item)
    conn.close()
    save('native_row_validation.json',checks)
    script=PROJECT/'perf_trace_batch8/releases/batch8-dp2-fresh-003-r07-attempt043-offline-recovery/prepare_attempt043_offline_db.py'
    argv=[sys.executable,str(script),'--source-db',str(source),'--prepared-db',str(ROOT/'capture.prepared.db'),'--manifest',str(REPORT/'prepare_manifest.json')]
    emit('derived_table_reconstruction_started',timeout_seconds=600)
    begun=time.monotonic()
    with (REPORT/'prepare.log').open('x') as log:
        result=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,timeout=600)
    assert result.returncode==0,('prepare failed',result.returncode)
    prepared=json.loads((REPORT/'prepare_manifest.json').read_text())
    assert sorted(prepared['hiptxops_rows'].values())==[234444,234832]
    assert prepared['trace_counter_rows']==25 and prepared['quick_check']=='ok'
    assert sha(source)==SOURCE_HASH,'source mutated'
    report={'status':'complete','cpu_only':True,'source_sha256':SOURCE_HASH,'source_immutable':True,'source_quick_check_seconds':quick_seconds,'native_row_checks':checks,'prepare_argv':argv,'prepare_tool_sha256':sha(script),'prepare_wall_seconds':time.monotonic()-begun,'prepare_manifest_sha256':sha(REPORT/'prepare_manifest.json'),'elapsed_seconds_including_download':time.monotonic()-started,'native_gpu_capture_rerun':False,'native_pftrace_export_rerun':False,'conclusion':'Published source database is structurally valid and every consumed process/runtime/kernel native row matches. CPU derived-table reconstruction completes within bounded timeout on this host. Historical collector termination remains unclaimed.'}
    save('CPU_DB_VALIDATION.json',report);emit('CPU_DB_VALIDATION_COMPLETE',report_path=str(REPORT/'CPU_DB_VALIDATION.json'),prepare_wall_seconds=report['prepare_wall_seconds'])

if __name__=='__main__':
    try:main()
    except BaseException as e:
        emit('FAILED',error=repr(e));raise
