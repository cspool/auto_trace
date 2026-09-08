"""Read-only native per-worker PMC health check after original two warmups."""
from pathlib import Path
import json,re,time,hashlib

def inspect_health(root,raw_directory=None):
 root=Path(root);workers=[];bindings={}
 if raw_directory is None:
  mode=json.loads((root/'control/live_collector_exec.json').read_text())
  if mode.get('mode')=='independent_native_worker_collectors':
   for rank in [0,1]:
    p=root/'control/worker_native_collectors'/('rank'+str(rank)+'.json')
    if not p.exists():return {'status':'failed','reason':'native collector worker binding missing','rank':rank,'workers':workers}
    bindings[rank]=json.loads(p.read_text())
  else:raw_directory=Path(mode['injected_output_directory'])
 else:raw_directory=Path(raw_directory)
 for rank in [0,1]:
  sources=list((root/'workload/r01_events'/f'rank{rank}').glob('events.*.jsonl'))
  if len(sources)!=1:return {'status':'failed','reason':'exact one initialized worker per rank','rank':rank,'workers':workers}
  with sources[0].open() as f:identity=json.loads(f.readline())
  pid=int(identity['pid'])
  if any(int(identity[k])!=rank for k in ['dp_rank','physical_device_id','native_current_device']):return {'status':'failed','reason':'worker topology mismatch','workers':workers}
  if bindings:
   binding=bindings[rank]
   if binding['rank']!=rank or binding['worker_pid']!=pid:return {'status':'failed','reason':'independent native collector PID/rank mismatch','rank':rank,'workers':workers}
   directory=Path(binding['native_output_directory'])
  else:directory=raw_directory
  path=directory/f'pmc_results_{pid}.txt';size=path.stat().st_size if path.exists() else 0
  if not size:return {'status':'failed','reason':'empty native PMC worker file before measured requests','rank':rank,'pid':pid,'workers':workers}
  with path.open('rb') as f:prefix=f.read(65536)
  lines=prefix.decode().splitlines();headers=[line for line in lines if line.startswith('dispatch[')]
  if not headers or not any('GRBM_COUNT (' in line for line in lines):return {'status':'failed','reason':'no native dispatch and native counter payload','rank':rank,'pid':pid,'workers':workers}
  for line in headers:
   match=re.search(r'gpu-id\((\d+)\).*?pid\((\d+)\)',line)
   if match is None or [int(x) for x in match.groups()]!=[rank,pid]:return {'status':'failed','reason':'native PMC PID/device mismatch','rank':rank,'pid':pid,'workers':workers}
  workers.append({'rank':rank,'native_device':rank,'pid':pid,'worker_identity_path':str(sources[0]),'native_raw_path':str(path),'observed_native_bytes':size,'examined_prefix_bytes':len(prefix),'examined_prefix_sha256':hashlib.sha256(prefix).hexdigest(),'native_dispatch_headers_in_prefix':len(headers)})
 if len({w['pid'] for w in workers})!=2:return {'status':'failed','reason':'duplicate worker PID','workers':workers}
 return {'status':'complete','workers':workers,'measured_requests_started':False,'read_only_native_file_gate':True,'no_native_calls_no_added_workload':True}

def require_pre_measured_health(root):
 root=Path(root);started=time.monotonic();result=None
 while time.monotonic()-started<10:
  result=inspect_health(root)
  if result['status']=='complete':break
  time.sleep(1)
 result['elapsed_seconds']=time.monotonic()-started;result['checked_realtime_ns']=time.time_ns()
 with (root/'control/PRE_MEASURED_NATIVE_PMC_HEALTH.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 if result['status']!='complete':raise RuntimeError('Both-device native PMC health gate failed: '+result['reason'])
 return result
