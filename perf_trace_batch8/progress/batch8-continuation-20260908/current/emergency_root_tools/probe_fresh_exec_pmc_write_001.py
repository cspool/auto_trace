from pathlib import Path
import sys,subprocess,csv,collections
ROOT=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');sys.path.insert(0,str(ROOT/'raw/runtime_tools/revision_014'))
from r08_native import *
base=output_path(ROOT/'raw/runtime_tools/native_fresh_exec_pmc_write_probe_001');base.mkdir();(base/'hipprof_tmp').mkdir();original=ROOT/'tools/gate_probe_001/gqa6_native_probe.py';script=base/'gqa6_native_probe.py';script.write_bytes(original.read_bytes());save(base/'CPU_GATE.json',{'status':'complete','script':source_record(script),'device_scope':'two independent fresh Python interpreter workers, four actual gqa6 dispatches each under pmc_write; model-free diagnostic only','model_initializations':0,'native_counter_mode':'pmc_write','not_measured_model_evidence':True})
env=clean_env();env.pop('PYTHONPATH',None);env['TRITON_CACHE_DIR']=str(ROOT/'raw/runtime_cache/triton');env['PYTHONPYCACHEPREFIX']=str(ROOT/'raw/runtime_cache/pycache');env['PYTHONDONTWRITEBYTECODE']='1';argv=collector_argv('pmc_write','_gqa6',base,[sys.executable,'-B',str(script),'parent','direct'],trace=True,disabled=True)
with (base/'collector.log').open('x') as log:result=subprocess.run(argv,cwd=base,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
with (base/'capture.csv').open() as f:rows=list(csv.DictReader(f));counts=collections.Counter(int(r['gpu-id']) for r in rows)
require(result.returncode==0 and counts=={0:4,1:4},'fresh independent interpreter exact both-device PMC writes')
save(base/'RESULT.json',{'status':'complete','model_initializations':0,'native_device_counts':dict(counts),'rows':len(rows),'argv':argv,'all_started_processes_terminated':True,'model_free_probe_only':True,'files':[source_record(p) for p in sorted(base.iterdir()) if p.is_file()]});print('FRESH_EXEC_PMC_WRITE_PROBE_COMPLETE',dict(counts),flush=True)
