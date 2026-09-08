from pathlib import Path
import sys,subprocess,json,hashlib,os,time,csv
ROOT=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');sys.path.insert(0,str(ROOT/'tools/revision_011'))
from r08_native import *
tool=ROOT/'tools/gate_probe_001';tool.mkdir();source=(ROOT/'tools/revision_001/r08_native_correlation_probe.cpp').read_text()
source=source.replace('#include <cstdlib>','#include <cstdlib>\n#include <dlfcn.h>')
source=source.replace('if (argc != 2)','if (argc != 3)')
source=source.replace('  int device_count = 0;','''  void* runtime=dlopen("/opt/dtk/lib/libamdhip64.so",RTLD_NOW|RTLD_GLOBAL);
  bool direct=std::atoi(argv[2])!=0;
  auto start=direct ? reinterpret_cast<hipError_t(*)()>(dlsym(runtime,"hipProfilerStart")) : &hipProfilerStart;
  auto stop=direct ? reinterpret_cast<hipError_t(*)()>(dlsym(runtime,"hipProfilerStop")) : &hipProfilerStop;
  check(stop(),"initial stop");
  int device_count = 0;''')
source=source.replace('  for (int launch = 0; launch < dispatch_count; ++launch) {','  for (int launch = 0; launch < dispatch_count; ++launch) {\n    if (launch==4) check(start(),"measured start");')
source=source.replace('  for (int device = 0; device < 2; ++device) {\n    check(hipSetDevice(device), "hipSetDevice cleanup");','  check(stop(),"measured stop");\n  for (int device = 0; device < 2; ++device) {\n    check(hipSetDevice(device), "hipSetDevice cleanup");')
p=tool/'probe.cpp';p.write_text(source);binary=tool/'probe';env=clean_env()
argv=['/opt/dtk/hip/bin/hipcc','--offload-arch=gfx936','-O2','-I/opt/dtk/roctracer/include',str(p),'-L/opt/dtk/roctracer/lib','-lroctx64','-ldl','-o',str(binary)];subprocess.run(argv,env=env,check=True)
report={'status':'cpu_gate_complete','model_initializations':0,'source':source_record(p),'binary':source_record(binary),'hipprof':source_record(HIPPROF),'purpose':'validate current direct-CDLL versus linked profiler API PMC transition','cases':['direct_default_on','direct_off','linked_off']};save(ROOT/'validation/pmc_transition_probe_cpu_gate.json',report)
base=output_path(ROOT/'preflight/pmc_transition_probe_001');base.mkdir();results=[]
for name,direct,off in [('direct_default_on','1',False),('direct_off','1',True),('linked_off','0',True)]:
    case=output_path(base/name);case.mkdir();(case/'hipprof_tmp').mkdir()
    cmd=collector_argv('pmc',None,case,[str(binary),'8',direct],disabled=off)
    with (case/'collector.log').open('x') as f:r=subprocess.run(cmd,cwd=case,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=90)
    count=0
    if (case/'capture.csv').exists():
        with (case/'capture.csv').open() as f:count=sum(1 for _ in csv.DictReader(f))
    result={'case':name,'rc':r.returncode,'raw_pmc_rows':count,'argv':cmd,'outputs':[source_record(p) for p in case.iterdir() if p.is_file()]};results.append(result);print('PMC_TRANSITION_PROBE',name,r.returncode,count,flush=True)
save(base/'RESULT.json',{'status':'complete','cases':results,'model_execution_performed':False})
