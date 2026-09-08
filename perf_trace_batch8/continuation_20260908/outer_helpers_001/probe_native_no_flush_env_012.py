"""Model-free native write visibility at live, Stop, libc flush, and exit boundaries."""
from pathlib import Path
import sys,os,json,hashlib,subprocess,signal,time,collections,csv
R=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');sys.path.insert(0,str(R/'raw/runtime_tools/revision_020'))
from r08_native import *
A=R/'raw/captures/09_chunk_gated_delta_rule_fwd_kernel_h_blockdim64_pmc_write/attempt_005';failure=read(A/'RAW_CAPTURE_FAILURE.json');cleanup=read(A/'control/tracee_process_cleanup.json');groups=[failure['profiler_cleanup']['leader_pid'],cleanup['service']['leader_pid'],cleanup['workload']['leader_pid']]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:fields=(p/'stat').read_text().split(') ',1)[1].split()
 except OSError:continue
 assert int(fields[2]) not in groups and int(p.name) not in [861055,861047],'prior failed capture still running'
base=R/'raw/runtime_tools/native_PMC_no_flush_env_probe_012';base.mkdir();(base/'hipprof_tmp').mkdir();original=(R/'raw/runtime_tools/native_fresh_exec_pmc_write_probe_001/gqa6_native_probe.py').read_text();worker=original[original.index('else:\n')+len('else:\n'):]
worker=worker.replace(' assert lib.hipProfilerStop()==0\n print(',''' write('before_stop.rank'+str(d)+'.json',{'rank':d,'pid':os.getpid()});wait('ALLOW_STOP')
 assert lib.hipProfilerStop()==0
 write('after_stop.rank'+str(d)+'.json',{'rank':d,'pid':os.getpid()});wait('ALLOW_LIBC_FLUSH')
 libc=ctypes.CDLL(None);libc.fflush.argtypes=[ctypes.c_void_p];libc.fflush.restype=ctypes.c_int;rc=libc.fflush(None);assert rc==0
 write('after_libc_flush.rank'+str(d)+'.json',{'rank':d,'pid':os.getpid(),'fflush_status':rc});wait('ALLOW_EXIT')
 print(''')
header='''import sys,os,subprocess,ctypes,json,importlib.util,time,hashlib
from pathlib import Path
TARGET=Path('/public/home/accl15ptg7/auto_trace/pra2026-bh408-gqa-page784-k5120-batch8');BASE=Path(__file__).parent

def write(name,value):
 with (BASE/name).open('x') as f:json.dump(value,f,indent=2);f.write('\\n');f.flush();os.fsync(f.fileno())
def wait(name):
 deadline=time.monotonic()+60
 while not (BASE/name).exists():
  assert time.monotonic()<deadline,'probe handshake timeout';time.sleep(.05)
def snap(name,pids):
 values=[]
 for rank,pid in enumerate(pids):
  paths=list(BASE.rglob('pmc_results_'+str(pid)+'.txt'));rows=[]
  for p in paths:
   with p.open('rb') as f:prefix=f.read(4096)
   rows.append({'path':str(p),'size':p.stat().st_size,'prefix_sha256':hashlib.sha256(prefix).hexdigest()})
  values.append({'rank':rank,'pid':pid,'native_files':rows})
 write(name,{'phase':name,'workers':values,'model_free':True})
if sys.argv[1]=='parent':
 ps=[subprocess.Popen([sys.executable,'-B',__file__,'worker',str(d),'direct']) for d in [0,1]]
 for d in [0,1]:wait('before_stop.rank'+str(d)+'.json')
 pids=[p.pid for p in ps];snap('VISIBILITY_BEFORE_STOP.json',pids);(BASE/'ALLOW_STOP').touch()
 for d in [0,1]:wait('after_stop.rank'+str(d)+'.json')
 snap('VISIBILITY_AFTER_STOP.json',pids);(BASE/'ALLOW_LIBC_FLUSH').touch()
 for d in [0,1]:wait('after_libc_flush.rank'+str(d)+'.json')
 snap('VISIBILITY_AFTER_LIBC_FLUSH.json',pids);(BASE/'ALLOW_EXIT').touch()
 for p in ps:assert p.wait(timeout=60)==0
 snap('VISIBILITY_AFTER_WORKER_EXIT.json',pids)
else:
'''
script=base/'gqa6_visibility_probe.py';script.write_text(header+worker);compile(script.read_text(),str(script),'exec');save(base/'CPU_GATE.json',{'status':'complete','script':source_record(script),'prior_failed_capture':source_record(A/'RAW_CAPTURE_FAILURE.json'),'prior_groups_verified_closed':groups,'model_initializations':0,'four_measured_gqa6_dispatches_per_device_only':True,'native_counter_mode':'pmc_write','not_R08_model_measurement_evidence':True})
env=clean_env();env.pop('PYTHONPATH',None);env.update(TRITON_CACHE_DIR=str(R/'raw/runtime_cache/triton'),PYTHONPYCACHEPREFIX=str(R/'raw/runtime_cache/pycache'),PYTHONDONTWRITEBYTECODE='1',HIP_VISIBLE_DEVICES='0,1',CUDA_VISIBLE_DEVICES='0,1');argv=collector_argv('pmc_write','_gqa6',base,[sys.executable,'-B',str(script),'parent','direct'],trace=True,disabled=True);forced=False
with (base/'collector.log').open('x') as log:
 p=subprocess.Popen(argv,cwd=base,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:rc=p.wait(timeout=180)
 except subprocess.TimeoutExpired:
  forced=True;os.killpg(p.pid,signal.SIGTERM)
  try:p.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
  raise
assert rc==0 and not forced
with (base/'capture.csv').open() as f:counts=collections.Counter(int(x['gpu-id']) for x in csv.DictReader(f))
coverage_complete=(counts=={0:4,1:4})
visibility=[read(base/n) for n in ['VISIBILITY_BEFORE_STOP.json','VISIBILITY_AFTER_STOP.json','VISIBILITY_AFTER_LIBC_FLUSH.json','VISIBILITY_AFTER_WORKER_EXIT.json']];save(base/'RESULT.json',{'status':'complete','model_initializations':0,'native_device_counts':dict(counts),'visibility':visibility,'argv':argv,'all_started_processes_terminated':True,'not_R08_model_capture_evidence':True,'expected_4_per_device_observed':coverage_complete});print(json.dumps({'status':'complete_model_free_visibility_probe','native_device_counts':dict(counts),'visibility':visibility}),flush=True)
