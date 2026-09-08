"""Read-only /proc evidence of scoped native exporter forward progress."""
from pathlib import Path
import json,time,os,sys,datetime
R=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');seg,attempt=sys.argv[1:];raw=R/'raw/captures'/seg/attempt;rows=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  a=(p/'cmdline').read_bytes().split(b'\0')
  if not a or a[0]!=b'/opt/dtk/bin/hipprof' or str(raw).encode() not in a:continue
  stat=(p/'stat').read_text().split(') ',1)[1].split();io={k:int(v) for k,v in (line.split(':',1) for line in (p/'io').read_text().splitlines())};files=[]
  for f in (p/'fd').iterdir():
   try:
    name=os.readlink(f)
    if 'pmc_results_' not in name or not (name.startswith(str(raw)) or name.startswith(str(raw.resolve()))):continue
    info=dict(line.split(':',1) for line in (p/'fdinfo'/f.name).read_text().splitlines());files.append({'file':name,'offset':int(info['pos']),'file_size':Path(name).stat().st_size})
   except (OSError,KeyError):pass
  rows.append({'pid':int(p.name),'process_state':stat[0],'user_cpu_ticks':int(stat[11]),'system_cpu_ticks':int(stat[12]),'io':io,'PMC_input_file_positions':files})
 except OSError:continue
result={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'segment_id':seg,'attempt':attempt,'status':'scoped_native_export_observation','processes':rows,'database_was_not_opened':True,'model_or_device_actions':0,'native_export_complete':(raw/'execution_manifest.json').exists()};out=R/'raw/runtime_tools/native_export_progress_001';out.mkdir(exist_ok=True);p=out/(seg+'.'+attempt+'.'+str(time.time_ns())+'.json')
with p.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({'utc':result['utc'],'processes':rows,'report':str(p)},separators=(',',':')),flush=True)
