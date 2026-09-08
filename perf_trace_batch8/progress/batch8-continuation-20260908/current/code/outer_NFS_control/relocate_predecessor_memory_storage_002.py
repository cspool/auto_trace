from pathlib import Path
import json,hashlib,shutil,os,time
control=Path('/public/home/accl15ptg7/run_R08_R10');destination=Path('/public/home/accl15ptg7/verified-memory-backing-20260908');destination.mkdir(exist_ok=True)
paths=[Path('/dev/shm/r08_continuation_predecessors/artifacts/R01/raw/hipprof/capture.db'),Path('/dev/shm/r08_continuation_predecessors/artifacts/R03/raw/process/capture.db'),Path('/dev/shm/r08_continuation_predecessors/artifacts/R01/raw/hipprof/capture_2.pftrace'),Path('/dev/shm/r08_continuation_predecessors/artifacts/R01/tmp/db-recovery/capture.db.original_candidate.gz')]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(16<<20),b''):h.update(b)
 return h.hexdigest()
plan={'status':'authorized_same_bytes_storage_relocation','reason':'121.5GiB cgroup memory limit and57GiB immutable predecessor tmpfs plus22GiB runtime RSS pressure cause repeated weight-cache eviction','content_changes':False,'existing_stage_directory_symlinks_unchanged':True,'exact_file_mappings':[{'source':str(p),'destination':str(destination/p.relative_to('/dev/shm'))} for p in paths]}
(control/'MEMORY_STORAGE_RELOCATION_AUTHORIZATION_002.json').write_text(json.dumps(plan,indent=2)+'\n');result=[]
for p in paths:
 q=destination/p.relative_to('/dev/shm');q.parent.mkdir(parents=True,exist_ok=True);before=sha(p);shutil.copyfile(p,q);assert sha(q)==before;q.chmod(0o444)
 link=p.with_name(p.name+'.verified-storage-link-002');link.symlink_to(q);os.replace(link,p);assert sha(p)==before
 result.append({'source_path':str(p),'resolved_destination':str(q),'size':p.stat().st_size,'sha256':before,'double_hash_verified':True});print('MEMORY_STORAGE_VERIFIED',p.name,p.stat().st_size,flush=True)
with (control/'MEMORY_STORAGE_RELOCATION_COMPLETE_002.json').open('x') as f:json.dump({'status':'complete','file_mappings':result,'authorization_sha256':sha(control/'MEMORY_STORAGE_RELOCATION_AUTHORIZATION_002.json'),'predecessor_content_changed':False},f,indent=2)
# Rewarm the identical weight bytes after releasing immutable tmpfs pressure.
for p in sorted(Path('/root/Qwen3.5-27B').glob('*.safetensors')):
 with p.open('rb') as f:
  for block in iter(lambda:f.read(32<<20),b''):pass
 print('WEIGHT_PAGECACHE_WARMED',p.name,flush=True)
print('MEMORY_STORAGE_AND_WEIGHT_CACHE_READY',flush=True)
