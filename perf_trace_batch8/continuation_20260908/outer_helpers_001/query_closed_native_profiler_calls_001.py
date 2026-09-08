from pathlib import Path
import sqlite3,json,time,sys,datetime,hashlib
R=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');seg,attempt=sys.argv[1:3];assert '/' not in seg and '/' not in attempt;A=R/'raw/captures'/seg/attempt;assert json.loads((A/'RAW_CAPTURE_FAILURE.json').read_text())['status']=='failed_not_accepted';db=A/'capture.db';before=db.stat();expected=next(x for x in json.loads((A/'raw_inventory_at_exit.json').read_text())['files'] if x['path']==str(db));h=hashlib.sha256()
with db.open('rb') as f:
 for b in iter(lambda:f.read(8<<20),b''):h.update(b)
assert h.hexdigest()==expected['sha256'];c=sqlite3.connect('file:'+str(db)+'?mode=ro&immutable=1',uri=True);c.execute('PRAGMA mmap_size=2147418112');t=time.monotonic();out=[]
for (n,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'HIP_[0-9]*'").fetchall():
 rows=list(c.execute('SELECT BeginNs,EndNs,pid,tid,Name,args,_Index FROM "'+n+'" WHERE args LIKE ?',('hipProfiler%',)));out.append({'table':n,'native_profiler_calls':rows})
c.close();after=db.stat();assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns);x={'status':'complete_read_only_native_args_query','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'database':expected,'elapsed_seconds':time.monotonic()-t,'rows':out,'absence_of_rows_does_not_prove_absence_of_untraced_profiler_APIs':True,'original_data_modified':False};p=R/'raw/runtime_tools'/('capture'+seg[:2]+'_'+attempt+'_native_profiler_transition_query_001.json')
with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n')
print(json.dumps(x))
