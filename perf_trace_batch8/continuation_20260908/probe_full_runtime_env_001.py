from pathlib import Path
import sys,subprocess,csv,json
ROOT=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');sys.path.insert(0,str(ROOT/'tools/revision_011'))
from r08_native import *
if len(sys.argv)>1:
    from run_capture import runtime_env
    case=Path(sys.argv[1]);env=runtime_env(case,'model_free_runtime_env_probe')
    argv=['/usr/bin/bash','-c','source "$1"; exec "$2" -B "$3" parent full_env','probe',str(TARGET/'scripts/cscc_gfx936_env.sh'),sys.executable,str(ROOT/'tools/gate_probe_001/torch_spawn_probe.py')]
    p=subprocess.run(argv,cwd=case,env=env);raise SystemExit(p.returncode)
else:
    save(ROOT/'validation/full_runtime_env_pmc_probe_cpu_gate.json',{'status':'complete','source':source_record(Path(__file__)),'runtime_helper':source_record(ROOT/'tools/revision_011/run_capture.py'),'sitecustomize':source_record(ROOT/'tools/revision_011/sitecustomize.py'),'model_execution_performed':False})
    base=output_path(ROOT/'preflight/full_runtime_env_pmc_probe_001');base.mkdir();results=[]
    for label,off in [('off_trace',True),('on_trace',False)]:
        case=output_path(base/label);case.mkdir()
        for name in ['hipprof_tmp','logs','control','workload']:(case/name).mkdir()
        cmd=collector_argv('pmc',None,case,[sys.executable,'-B',str(Path(__file__)),str(case)],disabled=off)
        with (case/'collector.log').open('x') as f:p=subprocess.run(cmd,cwd=case,env=clean_env(),stdout=f,stderr=subprocess.STDOUT,timeout=300)
        count=0
        if (case/'capture.csv').exists():
            with (case/'capture.csv').open() as f:count=sum(1 for _ in csv.DictReader(f))
        rec={'case':label,'rc':p.returncode,'pmc_rows':count,'argv':cmd,'outputs':[source_record(p) for p in case.iterdir() if p.is_file()]};results.append(rec);print('FULL_RUNTIME_ENV_PMC_PROBE',label,p.returncode,count,flush=True)
    save(base/'RESULT.json',{'status':'complete','model_initializations':0,'cases':results})
