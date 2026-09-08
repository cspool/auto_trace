import sys,os,subprocess,ctypes,json,importlib.util
from pathlib import Path
TARGET=Path('/public/home/accl15ptg7/auto_trace/pra2026-bh408-gqa-page784-k5120-batch8')
if sys.argv[1]=='parent':
 ps=[subprocess.Popen([sys.executable,'-B',__file__,'worker',str(d),sys.argv[2]]) for d in [0,1]]
 for p in ps:
  if p.wait()!=0:raise SystemExit(1)
else:
 sys.path.insert(0,str(TARGET))
 import torch
 if sys.argv[3].startswith('title'):
  import setproctitle;setproctitle.setproctitle('VLLM::Worker')
 if sys.argv[3]=='title_cpuinfo':
  import cpuinfo;cpuinfo.get_cpu_info()
 spec=importlib.util.spec_from_file_location('gqa6_probe_source',TARGET/'vllm/v1/attention/ops/rocm_aiter_unified_attention_gqa6.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 d=int(sys.argv[2]);torch.cuda.set_device(d);lib=ctypes.CDLL('/opt/dtk/lib/libamdhip64.so',mode=os.RTLD_NOW|os.RTLD_GLOBAL)
 q=torch.randn((16,48,256),dtype=torch.bfloat16,device='cuda');k=torch.randn((2,784,8,256),dtype=torch.bfloat16,device='cuda');v=torch.randn_like(k);o=torch.empty_like(q);table=torch.tensor([[0,1]],device='cuda',dtype=torch.int32);seq=torch.tensor([16],device='cuda',dtype=torch.int32);cu=torch.tensor([0,16],device='cuda',dtype=torch.int32)
 def launch():mod._gqa6[(1,24,1)](o,q,k,v,table,seq,cu,0.0625,CACHE_SIZE=784,BLOCK_M=32,STRIDES=(2,q.stride(0),o.stride(0),*k.stride()[:3],*v.stride()[:3]))
 launch();torch.cuda.synchronize()
 graph=None
 if sys.argv[3]=='graph':
  graph=torch.cuda.CUDAGraph()
  with torch.cuda.graph(graph):launch()
 assert lib.hipProfilerStart()==0
 for i in range(128):
  graph.replay() if graph else launch();torch.cuda.synchronize()
 assert lib.hipProfilerStop()==0
 print('GQA6_PROBE_COMPLETE',d,sys.argv[3],flush=True)
