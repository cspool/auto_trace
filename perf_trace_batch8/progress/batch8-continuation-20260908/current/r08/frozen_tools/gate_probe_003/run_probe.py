from pathlib import Path
import sys,subprocess,csv,collections
ROOT=Path("/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001");sys.path.insert(0,str(ROOT/'tools/revision_012'))
from r08_native import *
case=ROOT/'preflight/gqa6_hsa_probe_001';case.mkdir();(case/'hipprof_tmp').mkdir();env=clean_env();env.pop('PYTHONPATH',None);env['TRITON_CACHE_DIR']=str(ROOT/'raw/runtime_cache/triton')
argv=collector_argv('pmc','_gqa6',case,[sys.executable,'-B',str(Path(__file__).with_name('gqa6_hsa_probe.py')),'parent','direct'],disabled=False);argv.insert(1,'--hsa-trace')
with (case/'collector.log').open('x') as f:p=subprocess.run(argv,cwd=case,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=300)
rows=list(csv.DictReader((case/'capture.csv').open())) if (case/'capture.csv').exists() else []
save(case/'RESULT.json',{'status':'complete','exit':p.returncode,'rows':len(rows),'device_counts':dict(collections.Counter(x['gpu-id'] for x in rows)),'files':[source_record(f) for f in case.iterdir() if f.is_file()]});print('HSA_PROBE',p.returncode,len(rows),flush=True)
