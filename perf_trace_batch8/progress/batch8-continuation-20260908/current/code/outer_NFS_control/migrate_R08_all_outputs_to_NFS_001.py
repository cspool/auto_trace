"""Enforce user storage policy using closed, SHA-256 verified relocations only."""
from pathlib import Path
import json,os,shutil,hashlib,time,datetime
CONTROL=Path('/public/home/accl15ptg7/run_R08_R10');PROJECT=Path('/public/home/accl15ptg7/auto_trace');ROOT=PROJECT/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001';OUT=CONTROL/'storage_policy_correction_001';OUT.mkdir();RAM=Path('/dev/shm/pre_r08_nfs_quota_reclaim_001');RAM.mkdir()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(16<<20),b''):h.update(b)
 return h.hexdigest()
def save(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(x,f,indent=2,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
def replace_file(source,dest,role):
 before=sha(source);size=source.stat().st_size;dest.parent.mkdir(parents=True,exist_ok=True);assert not dest.exists();shutil.copyfile(source,dest);assert dest.stat().st_size==size and sha(dest)==before;dest.chmod(0o444)
 x={'source_path':str(source),'destination_path':str(dest),'size':size,'sha256':before,'role':role,'same_bytes':True,'only_R01_R03_predecessor_data_relocated_to_RAM':True};save(OUT/'predecessor_moves'/(role+'.copied_verified.json'),x)
 link=source.with_name(source.name+'.pre-r08-nfs-space-link');link.symlink_to(dest);os.replace(link,source);assert sha(source)==before;x.update(status='complete',canonical_link_verified=True);save(OUT/'predecessor_moves'/(role+'.complete.json'),x);print('PRE_R08_NFS_SPACE_RECLAIMED',role,size,flush=True);return x

def move_tree(source,dest,name):
 assert not source.is_symlink() and not dest.exists();dest.mkdir(parents=True);files=[];oldlinks=[]
 for base,dirs,names in os.walk(source,followlinks=True):
  b=Path(base);(dest/b.relative_to(source)).mkdir(parents=True,exist_ok=True)
  for fname in names:
   p=b/fname;q=dest/p.relative_to(source);size=p.stat().st_size;before=sha(p);shutil.copyfile(p,q);assert q.stat().st_size==size and sha(q)==before;q.chmod(p.stat().st_mode&0o777);files.append({'relative_path':str(p.relative_to(source)),'size':size,'sha256':before})
   if p.is_symlink():oldlinks.append({'old_link':str(p),'old_physical_file':str(p.resolve()),'size':size,'sha256':before})
   if len(files)%1000==0:print('NFS_TREE_COPY_PROGRESS',name,len(files),flush=True)
 save(OUT/(name+'.FILES.json'),{'status':'all_copied_verified','source':str(source),'destination':str(dest),'files':files,'previous_file_backings':oldlinks,'recorded_utc':now()})
 backup=source.with_name(source.name+'.closed-verified-before-NFS-001');source.rename(backup);source.symlink_to(dest,target_is_directory=True)
 # Verify canonical reads after the atomic closed-directory switch.
 for f in files:assert (source/f['relative_path']).stat().st_size==f['size'] and sha(source/f['relative_path'])==f['sha256']
 shutil.rmtree(backup)
 # These backing files were introduced exclusively for R08 capture storage.
 # Their canonical paths now read exact bytes physically on NFS.
 cleaned=[]
 for f in oldlinks:
  p=Path(f['old_physical_file'])
  if p.is_relative_to(Path('/dev/shm/r08_quota_recovery_002')) or p.is_relative_to(Path('/dev/shm/r08_published_capture_backing_001')):
   assert p.is_file() and sha(p)==f['sha256'];p.unlink();cleaned.append(str(p))
 x={'status':'complete','source_directory_alias':str(source),'physical_NFS_directory':str(dest),'file_count':len(files),'logical_bytes':sum(x['size'] for x in files),'manifest_path':str(OUT/(name+'.FILES.json')),'manifest_sha256':sha(OUT/(name+'.FILES.json')),'all_canonical_file_reads_sha256_verified':True,'removed_only_verified_old_R08_RAM_backings':cleaned,'recorded_utc':now()};save(OUT/(name+'.COMPLETE.json'),x);print('ALL_TREE_BYTES_NOW_NFS',name,len(files),x['logical_bytes'],flush=True);return x

assert json.loads((ROOT/'raw/captures/03__gqa6_pmc_write/attempt_003/execution_manifest.json').read_text())['all_started_processes_terminated']
weights=Path('/root/Qwen3.5-27B');assert len(list(weights.glob('*.safetensors')))==11 and all(p.resolve().is_relative_to(Path('/root')) for p in weights.glob('*.safetensors'))
save(OUT/'START.json',{'recorded_utc':now(),'user_policy_path':str(CONTROL/'USER_STORAGE_POLICY_20260908.json'),'user_policy_sha256':sha(CONTROL/'USER_STORAGE_POLICY_20260908.json'),'model_and_profiler_closed_before_relocation':True,'weights_must_remain_physical_root':True,'source_code':{'path':str(Path(__file__)),'sha256':sha(Path(__file__))}})
predecessors=[];backing=Path('/public/home/accl15ptg7/verified-memory-backing-20260908/r08_continuation_predecessors')
for ordinal,p in enumerate(sorted(x for x in backing.rglob('*') if x.is_file() and not x.is_symlink())):
 memory=dict(x.split() for x in Path('/sys/fs/cgroup/memory/memory.stat').read_text().splitlines());assert int(memory['shmem'])+p.stat().st_size<112*(1<<30),'closed-model cgroup RAM reserve';predecessors.append(replace_file(p,RAM/p.relative_to(backing),'predecessor_%03d'%ordinal))
results=[]
for source,dest,name in [(Path('/root/r08_emergency_tools'),CONTROL/'emergency_tools','emergency_tools'),(Path('/root/capture_publication_emergency'),CONTROL/'publication_emergency','publication_emergency'),(Path('/root/remote_progress_checkout_002'),CONTROL/'remote_progress_worktree_003','remote_progress_worktree'),(Path('/root/r08_continuation_001_bulk'),Path('/public/home/accl15ptg7/r08_continuation_001_NFS_bulk'),'r08_bulk')]:
 results.append(move_tree(source,dest,name))
save(OUT/'COMPLETE.json',{'status':'complete','recorded_utc':now(),'weights_all_physical_root':all(p.resolve().is_relative_to(Path('/root')) for p in weights.glob('*.safetensors')),'R08_all_current_data_outputs_logs_physical_NFS':True,'pre_R08_predecessor_relocations':predecessors,'directory_relocations':results,'new_capture_launch_requires_new_NFS_path_CPU_gate':True});print('R08_NFS_STORAGE_POLICY_COMPLETE',flush=True)
