"""Model-free nested exec/spawn probe of the actual PyTorch HIP runtime."""
import sys,os,subprocess,ctypes,json,time
from pathlib import Path
if sys.argv[1]=='parent':
    print('INJECTED',json.dumps({k:v for k,v in os.environ.items() if k.startswith(('HIPPROF_','HIP_PROF_','HSA_TOOLS')) or k=='LD_PRELOAD'}),flush=True)
    ps=[subprocess.Popen([sys.executable,'-B',__file__,'worker',str(d),sys.argv[2]]) for d in [0,1]]
    for p in ps:
        if p.wait()!=0:raise SystemExit(1)
else:
    import torch
    d=int(sys.argv[2]);torch.cuda.set_device(d)
    lib=ctypes.CDLL('/opt/dtk/lib/libamdhip64.so',mode=os.RTLD_NOW|os.RTLD_GLOBAL)
    for n in ['hipProfilerStart','hipProfilerStop']:getattr(lib,n).restype=ctypes.c_int
    assert lib.hipProfilerStop()==0
    x=torch.ones(4096,device='cuda',dtype=torch.float32);torch.cuda.synchronize()
    assert lib.hipProfilerStart()==0
    for i in range(4):
        x=x+1;torch.cuda.synchronize()
    assert lib.hipProfilerStop()==0
    print('TORCH_WORKER_COMPLETE',os.getpid(),d,float(x[0]),flush=True)
