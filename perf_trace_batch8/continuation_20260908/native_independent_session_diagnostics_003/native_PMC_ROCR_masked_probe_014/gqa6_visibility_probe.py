import sys,os,subprocess,ctypes,json,importlib.util,time,hashlib
from pathlib import Path
TARGET=Path('/public/home/accl15ptg7/auto_trace/pra2026-bh408-gqa-page784-k5120-batch8');BASE=Path(__file__).parent

def write(name,value):
 with (BASE/name).open('x') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
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
 ps=[subprocess.Popen([sys.executable,'-B',__file__,'worker',str(d),'direct'],env={**os.environ,'ROCR_VISIBLE_DEVICES':str(d),'HIP_VISIBLE_DEVICES':'0','CUDA_VISIBLE_DEVICES':'0'}) for d in [0,1]]
 for d in [0,1]:wait('before_stop.rank'+str(d)+'.json')
 pids=[p.pid for p in ps];snap('VISIBILITY_BEFORE_STOP.json',pids);(BASE/'ALLOW_STOP').touch()
 for d in [0,1]:wait('after_stop.rank'+str(d)+'.json')
 snap('VISIBILITY_AFTER_STOP.json',pids);(BASE/'ALLOW_LIBC_FLUSH').touch()
 for d in [0,1]:wait('after_libc_flush.rank'+str(d)+'.json')
 snap('VISIBILITY_AFTER_LIBC_FLUSH.json',pids);(BASE/'ALLOW_EXIT').touch()
 for p in ps:assert p.wait(timeout=60)==0
 snap('VISIBILITY_AFTER_WORKER_EXIT.json',pids)
else:
 sys.path.insert(0,str(TARGET))
 import torch
 spec=importlib.util.spec_from_file_location('gqa6_probe_source',TARGET/'vllm/v1/attention/ops/rocm_aiter_unified_attention_gqa6.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 d=int(sys.argv[2]);torch.cuda.set_device(0);lib=ctypes.CDLL('/opt/dtk/lib/libamdhip64.so',mode=os.RTLD_NOW|os.RTLD_GLOBAL)
 write('device_observation.rank'+str(d)+'.json',{'rank':d,'pid':os.getpid(),'visible_count':torch.cuda.device_count(),'current_device':torch.cuda.current_device(),'device_properties':str(torch.cuda.get_device_properties(0))})
 lib.hipProfilerStop();q=torch.randn((16,48,256),dtype=torch.bfloat16,device='cuda');k=torch.randn((2,784,8,256),dtype=torch.bfloat16,device='cuda');v=torch.randn_like(k);o=torch.empty_like(q);table=torch.tensor([[0,1]],device='cuda',dtype=torch.int32);seq=torch.tensor([16],device='cuda',dtype=torch.int32);cu=torch.tensor([0,16],device='cuda',dtype=torch.int32)
 def launch():mod._gqa6[(1,24,1)](o,q,k,v,table,seq,cu,0.0625,CACHE_SIZE=784,BLOCK_M=32,STRIDES=(2,q.stride(0),o.stride(0),*k.stride()[:3],*v.stride()[:3]))
 launch();torch.cuda.synchronize()
 graph=None
 if sys.argv[3]=='graph':
  graph=torch.cuda.CUDAGraph()
  with torch.cuda.graph(graph):launch()
 assert lib.hipProfilerStart()==0
 for i in range(4):
  graph.replay() if graph else launch();torch.cuda.synchronize()
 write('before_stop.rank'+str(d)+'.json',{'rank':d,'pid':os.getpid()});wait('ALLOW_STOP')
 assert lib.hipProfilerStop()==0
 write('after_stop.rank'+str(d)+'.json',{'rank':d,'pid':os.getpid()});wait('ALLOW_LIBC_FLUSH')
 libc=ctypes.CDLL(None);libc.fflush.argtypes=[ctypes.c_void_p];libc.fflush.restype=ctypes.c_int;rc=libc.fflush(None);assert rc==0
 write('after_libc_flush.rank'+str(d)+'.json',{'rank':d,'pid':os.getpid(),'fflush_status':rc});wait('ALLOW_EXIT')
 print('GQA6_PROBE_COMPLETE',d,sys.argv[3],flush=True)
