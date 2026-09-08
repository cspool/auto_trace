from pathlib import Path
import sys,os,json,subprocess,collections,csv,signal,time
R=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');sys.path.insert(0,str(R/'raw/runtime_tools/revision_020'))
from r08_native import *
base=R/'raw/runtime_tools/native_PMC_independent_collectors_probe_019';base.mkdir();source=R/'raw/runtime_tools/native_fresh_exec_pmc_write_probe_001/gqa6_native_probe.py';processes=[];results=[]
for d in [0,1]:
 unit=base/('rank'+str(d));unit.mkdir();(unit/'hipprof_tmp').mkdir();script=unit/'gqa6_native_probe.py';script.write_bytes(source.read_bytes());env=clean_env();env.pop('PYTHONPATH',None);env.update(TRITON_CACHE_DIR=str(R/'raw/runtime_cache/triton'),PYTHONPYCACHEPREFIX=str(R/'raw/runtime_cache/pycache'),PYTHONDONTWRITEBYTECODE='1');argv=collector_argv('pmc_write','_gqa6',unit,[sys.executable,'-B',str(script),'worker',str(d),'direct'],trace=True,disabled=True);log=(unit/'collector.log').open('x');p=subprocess.Popen(argv,cwd=unit,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);processes.append((d,unit,p,log,argv))
for d,unit,p,log,argv in processes:
 try:rc=p.wait(timeout=120)
 except subprocess.TimeoutExpired:
  os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=15);raise
 finally:log.close()
 rows=list(csv.DictReader((unit/'capture.csv').open())) if (unit/'capture.csv').exists() else [];counts=collections.Counter(int(x['gpu-id']) for x in rows);result={'rank':d,'returncode':rc,'native_device_counts':dict(counts),'expected_four_own_device':counts=={d:4},'positive_DispatchNs':bool(rows) and all(int(x['DispatchNs'])>0 for x in rows),'worker_pids':sorted(set(x['pid'] for x in rows)),'argv':argv};save(unit/'RESULT.json',result);results.append(result)
save(base/'RESULT.json',{'status':'complete_diagnostic_only','model_initializations':0,'independent_collector_per_worker':True,'results':results,'all_workers_recorded':all(x['expected_four_own_device'] and x['positive_DispatchNs'] and x['returncode']==0 for x in results),'all_started_processes_terminated':True});print(json.dumps(results),flush=True)
