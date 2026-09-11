import ctypes as C,json,time,subprocess,sys,os
from pathlib import Path
root=Path(__file__).parent
if len(sys.argv)>1 and sys.argv[1]=='load':
 import torch
 matrices=[]
 for dev in range(torch.cuda.device_count()):
  with torch.cuda.device(dev):
   a=torch.randn((4096,4096),device=f'cuda:{dev}',dtype=torch.bfloat16);b=torch.randn_like(a);c=torch.empty_like(a);matrices.append((a,b,c))
 (root/'smi_load_ready').write_text(str(time.monotonic_ns()))
 end=time.monotonic()+25
 while time.monotonic()<end:
  for a,b,c in matrices:
   with torch.cuda.device(a.device):torch.mm(a,b,out=c)
  for dev in range(len(matrices)):torch.cuda.synchronize(dev)
 (root/'smi_load_end').write_text(str(time.monotonic_ns()));sys.exit()
L=C.CDLL('/opt/hyhal/lib/librocm_smi64.so.2');L.rsmi_init(C.c_uint64(0))
class SE(C.Structure):_fields_=[('percent',C.c_float*8)]
class DF(C.Structure):_fields_=[('read',C.c_double),('write',C.c_double),('read_write',C.c_double)]
log=(root/'smi_load.log').open('w');child=subprocess.Popen([sys.executable,__file__,'load'],stdout=log,stderr=subprocess.STDOUT);start=time.monotonic();f=(root/'smi_load_validation.jsonl').open('w',buffering=1)
while time.monotonic()-start<90:
 phase='load' if (root/'smi_load_ready').exists() and not (root/'smi_load_end').exists() else 'idle'
 for dev in [0,1]:
  for name in ['rsmi_dev_se_util_get','rsmi_dev_cu_util_get','rsmi_dev_wave_util_get']:
   out=SE() if name.endswith('se_util_get') else C.c_float();args=[C.c_uint32(dev)]
   if not isinstance(out,SE):args.append(C.c_uint32(5))
   a=time.monotonic_ns();ret=getattr(L,name)(*args,C.byref(out));b=time.monotonic_ns();f.write(json.dumps({'device':dev,'metric':name,'begin_ns':a,'end_ns':b,'phase':phase,'status':ret,'value':list(out.percent) if isinstance(out,SE) else out.value})+'\n')
 if child.poll() is not None and time.monotonic_ns()-int((root/'smi_load_end').read_text() if (root/'smi_load_end').exists() else time.monotonic_ns())>3e9:break
 if child.poll() not in (None,0):break
 time.sleep(.05)
for dev in [0,1]:
 out=DF();a=time.monotonic_ns();ret=L.rsmi_dev_df_bandwidth_get(C.c_uint32(dev),C.c_int(3),C.byref(out));b=time.monotonic_ns();print('DF',dev,ret,out.read,out.write,out.read_write,'elapsed_ms',(b-a)/1e6,flush=True)
f.close();print('load return',child.poll(),flush=True)
rows=[json.loads(s) for s in (root/'smi_load_validation.jsonl').read_text().splitlines()]
for dev in [0,1]:
 for name in ['rsmi_dev_se_util_get','rsmi_dev_cu_util_get','rsmi_dev_wave_util_get']:
  for phase in ['idle','load']:
   rs=[r for r in rows if r['device']==dev and r['metric']==name and r['phase']==phase];vs=[v for r in rs for v in (r['value'] if isinstance(r['value'],list) else [r['value']])];print(dev,name,phase,len(rs),'max',max(vs,default=None),'statuses',sorted({r['status'] for r in rs}),flush=True)
