"""Outer CPU phase runner. Reap orphan descendants before sealing exit evidence."""
from pathlib import Path
import argparse,ctypes,os,sys,json,subprocess,time,signal,datetime,hashlib

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def processes():
 result={}
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   a=(p/'stat').read_text().rsplit(') ',1)[1].split();result[int(p.name)]={'pid':int(p.name),'ppid':int(a[1]),'state':a[0],'start_ticks':int(a[19])}
  except (FileNotFoundError,PermissionError,ProcessLookupError):pass
 return result

def descendants(owner):
 ps=processes();selected={owner};changed=True
 while changed:
  before=len(selected);selected|={pid for pid,x in ps.items() if x['ppid'] in selected};changed=len(selected)!=before
 return {pid:x for pid,x in ps.items() if pid in selected and pid!=owner}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--stage-root',required=True);ap.add_argument('--phase',required=True);ap.add_argument('--timeout',type=int,default=3600);ap.add_argument('argv',nargs=argparse.REMAINDER);a=ap.parse_args();argv=a.argv[1:] if a.argv and a.argv[0]=='--' else a.argv;assert argv
 root=Path(a.stage_root);out=root/'validation/phase_lifecycle'/(a.phase+'.json');log=root/'logs'/(a.phase+'.log');assert not out.exists() and not log.exists();out.parent.mkdir(parents=True,exist_ok=True);log.parent.mkdir(parents=True,exist_ok=True)
 assert ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0,'PR_SET_CHILD_SUBREAPER'
 env=dict(os.environ)
 for key in list(env):
  if 'proxy' in key.lower() or key.startswith('HIPPROF') or key in ['LD_PRELOAD','ROCP_TOOL_LIB','HSA_TOOLS_LIB','ROCP_TOOL_LOAD']:env.pop(key)
 env.update(ROCR_VISIBLE_DEVICES='',HIP_VISIBLE_DEVICES='',CUDA_VISIBLE_DEVICES='',VLLM_NO_USAGE_STATS='1',DO_NOT_TRACK='1',PYTHONDONTWRITEBYTECODE='1',PLAYWRIGHT_BROWSERS_PATH='/root/r08_r10_browser_tools')
 start=time.monotonic();begun=now();seen={};forced=False
 with log.open('x') as f:
  p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,start_new_session=True,env=env)
  while p.poll() is None:
   for pid,x in descendants(os.getpid()).items():seen[(pid,x['start_ticks'])]=x
   if time.monotonic()-start>a.timeout:
    forced=True
    for pid,x in descendants(os.getpid()).items():
     try:os.kill(pid,signal.SIGTERM)
     except ProcessLookupError:pass
    break
   time.sleep(.1)
  try:rc=p.wait(timeout=30)
  except subprocess.TimeoutExpired:
   forced=True
   for pid in descendants(os.getpid()):
    try:os.kill(pid,signal.SIGKILL)
    except ProcessLookupError:pass
   rc=p.wait(timeout=30)
 # Any descendant that double-forked is now adopted by this subreaper. Reap
 # all exited children, and prove no living descendants before the checkpoint.
 cleanup_start=time.monotonic();reaped=[]
 while True:
  while True:
   try:pid,status=os.waitpid(-1,os.WNOHANG)
   except ChildProcessError:break
   if not pid:break
   reaped.append({'pid':pid,'wait_status':status})
  live=descendants(os.getpid())
  for pid,x in live.items():seen[(pid,x['start_ticks'])]=x
  if not live:break
  if time.monotonic()-cleanup_start>30:
   forced=True
   for pid in live:
    try:os.kill(pid,signal.SIGKILL)
    except ProcessLookupError:pass
  assert time.monotonic()-cleanup_start<60,'orphan descendants failed to close';time.sleep(.1)
 result={'status':'complete' if rc==0 and not forced else 'failed','phase':a.phase,'argv':argv,'started_utc':begun,'finished_utc':now(),'elapsed_seconds':time.monotonic()-start,'leader_pid':p.pid,'leader_returncode':rc,'observed_descendant_identities':list(seen.values()),'observed_list_is_not_claimed_full_spawn_event_log':True,'orphan_reaping':reaped,'kernel_child_subreaper_enabled':True,'remaining_owned_descendants':[],'all_started_processes_terminated':True,'forced_cleanup':forced,'cpu_only_environment_device_visibility_empty':True,'proxy_and_profiler_injection_removed':True,'stdout_stderr':{'path':str(log),'size':log.stat().st_size,'sha256':sha(log)},'outer_runner':{'path':str(Path(__file__)),'sha256':sha(Path(__file__))}}
 with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 print('OUTER_PHASE_CLOSED',a.phase,result['status'],len(seen),flush=True);return 0 if result['status']=='complete' else 1
if __name__=='__main__':sys.exit(main())
