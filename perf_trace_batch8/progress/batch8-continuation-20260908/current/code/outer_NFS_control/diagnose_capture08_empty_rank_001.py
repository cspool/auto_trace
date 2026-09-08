"""Read-only closed failed-attempt diagnostic; never accepts a partial capture."""
from pathlib import Path
import sqlite3,json,hashlib,time,os,re,datetime
R=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');A=R/'raw/captures/08_chunk_gated_delta_rule_fwd_kernel_h_blockdim64_pmc_read/attempt_001';started=time.monotonic();failure=json.loads((A/'RAW_CAPTURE_FAILURE.json').read_text());assert failure['status']=='failed_not_accepted';db=A/'capture.db';before=db.stat();inventory=json.loads((A/'raw_inventory_at_exit.json').read_text());expected=next(x for x in inventory['files'] if x['path']==str(db));h=hashlib.sha256()
with db.open('rb') as f:
 for b in iter(lambda:f.read(8<<20),b''):h.update(b)
assert h.hexdigest()==expected['sha256'];literal=json.loads((A/'control/capture_contract.json').read_text())['segment']['kernel_name_filter_literal'];c=sqlite3.connect('file:'+str(db)+'?mode=ro&immutable=1',uri=True);c.execute('PRAGMA mmap_size=2147418112');c.execute('PRAGMA cache_size=-262144');rows=[]
for (table,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'HIPOPS_%'").fetchall():
 assert re.fullmatch('[A-Za-z0-9_]+',table);total=c.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone()[0];counts=c.execute('SELECT pid,dev_id,COUNT(*),MIN(_Index),MAX(_Index) FROM "'+table+'" WHERE Name=? GROUP BY pid,dev_id',(literal,)).fetchall();rows.append({'table':table,'total_native_HIPOPS_rows':total,'exact_literal_native_dispatches':[{'pid':x[0],'device':x[1],'count':x[2],'first_index':x[3],'last_index':x[4]} for x in counts]})
c.close();after=db.stat();assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
native=[{'path':str(p),'size':p.stat().st_size} for p in sorted((A/'control/native_pmc_before_collector_merge').rglob('pmc_results_*.txt'))]
result={'status':'complete_closed_failure_diagnostic','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'failure_reason':failure['native_health']['reason'],'native_database':expected,'kernel_full_literal':literal,'HIPOPS':rows,'preserved_native_PMC_files':native,'both_warmup_native_start_statuses':[json.loads(p.read_text())['profiler_transition']['status'] for p in sorted((A/'control/pmc_gate_events').glob('warmup_start.*.json'))],'measured_capture_accepted':False,'all_eight_measured_requests_started':False,'root_cause_beyond_native_counter_loss_proven':False,'read_only_no_GPU_actions':True,'database_size_mtime_and_original_SHA256_unchanged':True,'elapsed_seconds':time.monotonic()-started}
p=R/'raw/runtime_tools/capture08_empty_pmc_native_diagnostic_001.json'
with p.open('x') as f:json.dump(result,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
print(json.dumps(result))
