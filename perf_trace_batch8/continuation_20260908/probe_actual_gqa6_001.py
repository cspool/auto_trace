from pathlib import Path
import sys,subprocess,csv
ROOT=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');sys.path.insert(0,str(ROOT/'tools/revision_011'))
from r08_native import *
script=ROOT/'tools/gate_probe_001/gqa6_native_probe.py';save(ROOT/'validation/gqa6_pmc_probe_cpu_gate.json',{'status':'complete','script':source_record(script),'model_imports':0,'model_initializations':0,'device_work':'two workers x four torch add kernels; no Qwen initialization','source':source_record(Path(__file__))})
base=output_path(ROOT/'preflight/gqa6_pmc_probe_001');base.mkdir();env=clean_env();env.pop('PYTHONPATH',None);env['TRITON_CACHE_DIR']=str(ROOT/'raw/runtime_cache/triton')
results=[]
for label,off,trace in [('direct',True,True),('graph',True,True)]:
    case=output_path(base/label);case.mkdir();(case/'hipprof_tmp').mkdir();cmd=collector_argv('pmc','_gqa6',case,[sys.executable,'-B',str(script),'parent',label],trace=trace,disabled=off)
    with (case/'collector.log').open('x') as log:p=subprocess.run(cmd,cwd=case,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
    count=0
    if (case/'capture.csv').exists():
        with (case/'capture.csv').open() as f:count=sum(1 for _ in csv.DictReader(f))
    raw=list(case.glob('pmc_results*.txt'));record={'case':label,'rc':p.returncode,'pmc_csv_rows':count,'raw_native_pmc_files':[source_record(p) for p in raw],'argv':cmd,'files':[source_record(p) for p in case.iterdir() if p.is_file()]};results.append(record);print('TORCH_PMC_EXEC_PROBE',label,p.returncode,count,len(raw),flush=True)
save(base/'RESULT.json',{'status':'complete','cases':results,'model_initializations':0})
