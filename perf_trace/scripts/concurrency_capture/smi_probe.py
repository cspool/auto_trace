import ctypes as C,json,time
L=C.CDLL('/opt/hyhal/lib/librocm_smi64.so.2')
class SE(C.Structure):_fields_=[('percent',C.c_float*8)]
L.rsmi_init.argtypes=[C.c_uint64];print('init',L.rsmi_init(0),flush=True)
n=C.c_uint32();print('count_status',L.rsmi_num_monitor_devices(C.byref(n)),'n',n.value,flush=True)
for i in range(n.value):
 b=C.c_uint64();u=C.c_uint64();L.rsmi_dev_pci_id_get(i,C.byref(b));L.rsmi_dev_unique_id_get(i,C.byref(u));d={'index':i,'pci_id':hex(b.value),'unique_id':hex(u.value)}
 for name in ['rsmi_dev_se_util_get','rsmi_dev_cu_usage_get','rsmi_dev_hcu_util_get','rsmi_dev_cu_util_get','rsmi_dev_wave_util_get']:
  try:
   out=SE() if 'se_util' in name else C.c_float();args=[C.c_uint32(i)];
   if name in ['rsmi_dev_hcu_util_get','rsmi_dev_cu_util_get','rsmi_dev_wave_util_get']:args.append(C.c_uint32(10))
   a=time.monotonic_ns();status=getattr(L,name)(*args,C.byref(out));btime=time.monotonic_ns();d[name]={'status':status,'value':list(out.percent) if isinstance(out,SE) else out.value,'call_ns':btime-a}
  except Exception as e:d[name]={'error':str(e)}
 print(json.dumps(d),flush=True)
L.rsmi_shut_down()
