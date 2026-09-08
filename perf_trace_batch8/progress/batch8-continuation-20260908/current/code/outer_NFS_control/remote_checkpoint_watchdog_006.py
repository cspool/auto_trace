"""Outer scheduler publisher. Ten-minute recoverable Git snapshots, no device calls."""
from pathlib import Path
import os,json,hashlib,subprocess,time,datetime,shutil,re,sys,traceback
CONTROL=Path('/public/home/accl15ptg7/run_R08_R10');PROJECT=Path('/public/home/accl15ptg7/auto_trace');R08=PROJECT/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001';WORKTREE=Path('/public/home/accl15ptg7/run_R08_R10/remote_progress_worktree_004');REL=Path('perf_trace_batch8/progress/batch8-continuation-20260908');DEST=WORKTREE/REL
BRANCH='progress/batch8-continuation-20260908';DEADLINE=datetime.datetime.fromisoformat('2026-09-08T20:18:09+00:00').timestamp()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def git(*args):
 p=subprocess.run(['git','-C',str(WORKTREE),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=180,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'})
 if p.returncode:raise RuntimeError('git '+args[0]+' failed with exit '+str(p.returncode))
 return p.stdout.strip()
def secrets():
 result=[]
 for k in ['http_proxy','https_proxy','ftp_proxy','HTTP_PROXY','HTTPS_PROXY']:
  value=os.environ.get(k,'')
  if value:result.append(value)
 p=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'})
 if p.returncode==0:
  fields=dict(x.split('=',1) for x in p.stdout.splitlines() if '=' in x)
  if fields.get('password'):result.append(fields['password'])
 return result
SECRET_VALUES=secrets()
def redact(b):
 text=b.decode('utf-8',errors='replace')
 for value in SECRET_VALUES:text=text.replace(value,'[REDACTED_CREDENTIAL]')
 text=re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b','[REDACTED_CREDENTIAL]',text)
 text=re.sub(r'https?://[^\s/:@]+:[^\s/@]+@','https://[REDACTED_CREDENTIAL]@',text)
 return text.encode()
def snapshot():
 begun=now();tmp=DEST/'next_snapshot'
 if tmp.exists():shutil.rmtree(tmp)
 tmp.mkdir(parents=True);records=[]
 def copy(path,relative,kind):
  if not path.is_file() or '__pycache__' in path.parts:return
  with path.open('rb') as f:
   # Bound each live read to the length observed at open. No moving-tail loop.
   before=os.fstat(f.fileno());data=f.read(before.st_size)
  check_size=len(data);clean=redact(data);q=tmp/relative;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(clean)
  records.append({'source_path':str(path),'snapshot_relative_path':str(relative),'kind':kind,'captured_bytes':check_size,'source_captured_prefix_sha256':sha_bytes(data),'snapshot_bytes':len(clean),'snapshot_sha256':sha_bytes(clean),'redacted':clean!=data,'source_was_live':kind=='log_snapshot'})
 for p in sorted(CONTROL.glob('*.log')):copy(p,Path('logs/control')/p.name,'log_snapshot')
 for p in sorted(CONTROL.glob('*.py')):copy(p,Path('code/outer_NFS_control')/p.name,'outer_scheduler_code')
 for p in sorted((CONTROL/'storage_policy_correction_001').rglob('*.json')):copy(p,Path('state/storage_policy_correction_001')/p.relative_to(CONTROL/'storage_policy_correction_001'),'closed_storage_checkpoint')
 copy(CONTROL/'RECOVERY_STATE_NFS.json',Path('state/RECOVERY_STATE_NFS.json'),'authoritative_execution_state')
 copy(CONTROL/'USER_STORAGE_POLICY_20260908.json',Path('state/USER_STORAGE_POLICY_20260908.json'),'user_storage_policy')
 for p in sorted((CONTROL/'stage_tool_templates').rglob('*')):
  if p.suffix in ['.py','.js','.css','.json','.md']:copy(p,Path('code/prepared_not_executed')/p.relative_to(CONTROL/'stage_tool_templates'),'unfrozen_template_code')
 for p in sorted((PROJECT/'perf_trace_batch8/continuation_20260908').glob('*.py')):copy(p,Path('code/outer_continuation')/p.name,'outer_scheduler_code')
 names=['session_state.json','MACHINE_TIME_EXTENSION_001.json','WEIGHTS_COMPLETE.json','WEIGHT_STORAGE_RELOCATION_COMPLETE.json','MEMORY_STORAGE_RELOCATION_AUTHORIZATION.json','MEMORY_STORAGE_RELOCATION_COMPLETE.json','MEMORY_STORAGE_RELOCATION_AUTHORIZATION_002.json','MEMORY_STORAGE_RELOCATION_COMPLETE_002.json','R07_CPU_DB_REVIEW.md']
 for name in names:copy(CONTROL/name,Path('state')/name,'state_checkpoint')
 accepted=[]
 schedule=R08/'validation/serial_scheduler_001'
 for p in sorted(schedule.glob('*')):
  if p.suffix in ['.json','.log']:copy(p,Path('r08/scheduler')/p.name,'log_snapshot' if p.suffix=='.log' else 'closed_checkpoint')
  if p.name.endswith('.accepted_checkpoint.json'):accepted.append(json.loads(p.read_text())['item'])
 for p in sorted((R08/'raw/captures').glob('*/*/logs/*.log')):copy(p,Path('r08/capture_logs')/p.relative_to(R08/'raw/captures'),'log_snapshot')
 for item in accepted:
  for key in ['execution_manifest','normalization_manifest','independent_audit']:
   p=Path(item[key]['path']);copy(p,Path('r08/accepted')/item['segment_id']/p.name,'accepted_capture_checkpoint')
 for stage in ['R09','R10']:
  root=R08.parent.parent/stage/'continuation_001'
  if root.exists():
   for p in root.rglob('*'):
    if p.is_file() and p.suffix in ['.json','.log','.py','.js','.css','.md'] and 'tables' not in p.parts and 'acceptance' not in p.parts and '__pycache__' not in p.parts:copy(p,Path(stage.lower())/p.relative_to(root),'log_snapshot' if p.suffix=='.log' else 'stage_checkpoint')
 for p in sorted((CONTROL/'publication').glob('*/PUBLICATION_COMPLETE.json')):copy(p,Path('remote_publications')/p.parent.name/p.name,'published_release_index')

 for p in sorted(Path('/root/r08_emergency_tools').rglob('*')):
  if p.is_file() and p.suffix in ['.py','.json','.log','.md']:copy(p,Path('emergency_root_tools')/p.relative_to(Path('/root/r08_emergency_tools')),'log_snapshot' if p.suffix=='.log' else 'emergency_recovery_code_or_state')
 for p in sorted((R08/'raw/runtime_tools').rglob('*')):
  if p.is_file() and p.suffix in ['.py','.sh','.json','.log']:copy(p,Path('r08/emergency_runtime')/p.relative_to(R08/'raw/runtime_tools'),'log_snapshot' if p.suffix=='.log' else 'frozen_runtime_tool_or_gate')
 for p in sorted(Path('/root/capture_publication_emergency').glob('*/PUBLICATION_COMPLETE.json')):copy(p,Path('remote_publications')/p.parent.name/p.name,'published_release_index')
 for p in sorted((R08/'raw/runtime_tools').glob('serial_scheduler_*/*.accepted_checkpoint.json')):
  item=json.loads(p.read_text())['item']
  if item['segment_id'] not in {x['segment_id'] for x in accepted}:
   accepted.append(item)
   for key in ['execution_manifest','normalization_manifest','independent_audit']:
    q=Path(item[key]['path']);copy(q,Path('r08/accepted')/item['segment_id']/q.name,'accepted_capture_checkpoint')
 for p in [Path('/dev/shm/DOWNLOAD_CACHE_CLEANUP_001.json')]:copy(p,Path('emergency_root_tools')/p.name,'verified_redundant_download_cache_cleanup')
 
 state={'snapshot_started_utc':begun,'snapshot_completed_utc':now(),'runtime_run_id':'batch8-dp2-fresh-003','r08_accepted_capture_count':len(accepted),'r08_planned_capture_count':12,'r08_accepted_segments':[x['segment_id'] for x in accepted],'deadline_utc':'2026-09-08T20:18:09Z','remote_progress_branch':BRANCH,'current_execution_state':json.loads((CONTROL/'RECOVERY_STATE_NFS.json').read_text()),'logs_are_point_in_time_snapshots':True,'active_sqlite_databases_not_claimed_transactionally_complete':True,'accepted_raw_artifacts_published_separately_with_sha256':True,'outer_publisher_not_R09_or_R10_business_execution':True,'files':records}
 (tmp/'SNAPSHOT_MANIFEST.json').write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n');current=DEST/'current'
 if current.exists():shutil.rmtree(current)
 tmp.rename(current)
 (DEST/'README.md').write_text('# Batch8 DP2 容器丢失恢复检查点\n\n每10分钟提交一次当前状态、代码和完整日志快照；Git历史保留旧检查点。当前代码模板明确标记为未执行，不能作为R09/R10完成证据。每个通过独立审计的R08采集另发原始数据Release。\n\n恢复先读 `current/SNAPSHOT_MANIFEST.json` 和 `current/state/RECOVERY_STATE_NFS.json`（覆盖此前各版本状态），再核对 `current/r08/accepted` 与 `current/remote_publications`。只有原始数据、规范化清单和独立审计均匹配的采集才能复用；未完成采集只保留日志，不算通过。\n\n截止时间：2026-09-08 20:18:09 UTC。\n')
 git('add','--',str(REL));git('commit','-m','Checkpoint batch8 continuation '+begun+'; accepted R08 '+str(len(accepted))+'/12');commit=git('rev-parse','HEAD');git('push','origin','HEAD:refs/heads/'+BRANCH)
 remote=git('ls-remote','origin','refs/heads/'+BRANCH).split()[0];assert remote==commit,'remote commit verification'
 result={'status':'pushed','utc':now(),'commit':commit,'branch':BRANCH,'accepted_R08':len(accepted),'url':'https://github.com/cspool/auto_trace/tree/'+BRANCH+'/'+str(REL),'source_snapshot_manifest_sha256':sha_bytes((current/'SNAPSHOT_MANIFEST.json').read_bytes())}
 (CONTROL/'REMOTE_PROGRESS_LAST_PUSH_NFS.json').write_text(json.dumps(result,indent=2)+'\n');print('REMOTE_PROGRESS_PUSHED',result['utc'],commit,len(accepted),flush=True)
while time.time()<DEADLINE:
 start=time.monotonic()
 try:snapshot()
 except Exception as error:
  # Never print credential-bearing subprocess stderr or request exception URLs.
  print('REMOTE_PROGRESS_RETRY_REQUIRED',now(),type(error).__name__,str(error) if isinstance(error,RuntimeError) else '',flush=True)
 for i in range(max(1,int(600-(time.monotonic()-start)))):
  if (CONTROL/'STOP_REMOTE_CHECKPOINT_WATCHDOG').exists():raise SystemExit(0)
  time.sleep(1)
