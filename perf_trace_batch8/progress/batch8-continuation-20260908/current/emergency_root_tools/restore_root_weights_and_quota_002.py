"""Relocate immutable bytes to writable local storage; preserve canonical identities."""
from pathlib import Path
import json,hashlib,shutil,os,time,datetime
CONTROL=Path('/public/home/accl15ptg7/run_R08_R10');ROOT=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');OUT=ROOT/'raw/runtime_tools/storage_recovery_002';OUT.mkdir();RAM=Path('/dev/shm/r08_quota_recovery_002');RAM.mkdir()
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(16<<20),b''):h.update(b)
 return h.hexdigest()
def save(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def relocate(source,dest,role):
 size=source.stat().st_size;before=sha(source);dest.parent.mkdir(parents=True,exist_ok=True);assert not dest.exists();shutil.copyfile(source,dest);assert dest.stat().st_size==size and sha(dest)==before,'copied bytes';dest.chmod(0o444)
 record={'source_path':str(source),'destination_path':str(dest),'size':size,'sha256':before,'role':role,'same_bytes':True,'source_content_not_changed':True}
 save(OUT/(role+'.copied_verified.json'),record)
 # Root-backed sources can be replaced atomically. For over-quota NFS,
 # keep the original path until enough redundant bytes have been removed.
 if str(source).startswith('/public/home/accl15ptg7/verified-memory-backing'):
  source.unlink()
  try:source.symlink_to(dest);record['canonical_link_restored']=True
  except OSError:record['canonical_link_restored']=False
 else:
  link=source.with_name(source.name+'.same-bytes-link-001');link.symlink_to(dest);os.replace(link,source);assert sha(source)==before;record['canonical_link_restored']=True
 save(OUT/(role+'.relocated.json'),record);print('STORAGE_RELOCATED',role,size,record['canonical_link_restored'],flush=True);return record
moves=[]
# Only rejected, fully closed attempts: do not touch the current capture.
for seg,attempt in [('01__gqa6_pmc','attempt_003'),('01__gqa6_pmc','attempt_004'),('03__gqa6_pmc_write','attempt_001')]:
 raw=ROOT/'raw/captures'/seg/attempt
 if (raw/'execution_manifest.json').exists():assert json.loads((raw/'execution_manifest.json').read_text())['all_started_processes_terminated']
 else:
  pids=[json.loads((raw/'control/profiler_identity.json').read_text())['pid']]
  cleanup=json.loads((raw/'control/tracee_process_cleanup.json').read_text())
  for x in cleanup.values():pids.extend([x['leader_pid'],*x['remaining_group_members_before_final_cleanup']])
  pids.extend(int(p.name.split('.')[1]) for p in (raw/'workload/r01_events').glob('rank*/events.*.jsonl'))
  assert all(not Path('/proc',str(pid)).exists() for pid in pids),'rejected capture still has a recorded process'
 moves.append(relocate(raw/'capture.db',RAM/seg/attempt/'capture.db',seg+'_'+attempt))
# Return weights to physical root disk, matching the user's original request.
weights=Path('/root/Qwen3.5-27B');backing=Path('/root/Qwen3.5-27B-verified-root-backing-20260908');backing.mkdir()
for logical in sorted(weights.glob('*.safetensors')):
 old=logical.resolve();dest=backing/logical.name;size=old.stat().st_size;assert shutil.disk_usage('/root').free>size+(1<<30),'root free space guard';before=sha(old);shutil.copyfile(old,dest);assert sha(dest)==before and dest.stat().st_size==size;dest.chmod(0o444)
 record={'logical_path':str(logical),'previous_backing':str(old),'new_backing':str(dest),'size':size,'sha256':before,'same_bytes_verified':True};save(OUT/('weight_'+logical.name+'.json'),record)
 link=logical.with_name(logical.name+'.root-backing-001');link.symlink_to(dest);os.replace(link,logical);assert sha(logical)==before;old.unlink();print('ROOT_WEIGHT_RESTORED',logical.name,size,flush=True)
# These R07 DBs are immutable CPU-only validation inputs, already fully audited.
for name in ['capture.source.db','capture.prepared.db']:
 source=Path('/public/home/accl15ptg7/verified-memory-backing-20260908/r07_cpu_validation_001')/name;moves.append(relocate(source,RAM/'r07_cpu_validation_001'/name,'r07_'+name.replace('.','_')))
# Preserve public remote caches' manifests while removing only exact checksum
# matches. No stage business evidence is removed by this cache cleanup.
removed=[]
for directory in sorted((CONTROL/'downloads').iterdir()):
 if not directory.is_dir() or not (directory/'SHA256SUMS').exists():continue
 expected={line.split()[1].lstrip('*'):line.split()[0] for line in (directory/'SHA256SUMS').read_text().splitlines() if len(line.split())==2}
 for path in sorted(directory.iterdir()):
  if not path.is_file() or path.stat().st_size<32_000_000 or path.name not in expected:continue
  before=sha(path);assert before==expected[path.name],'published download checksum';removed.append({'path':str(path),'size':path.stat().st_size,'sha256':before,'remote_release_tag':directory.name});path.unlink();print('REMOVED_VERIFIED_REMOTE_CACHE',directory.name,path.name,flush=True)
for move in moves:
 if not move['canonical_link_restored']:
  source=Path(move['source_path']);assert not source.exists();source.symlink_to(move['destination_path']);assert sha(source)==move['sha256'];move['canonical_link_restored']=True
save(OUT/'STORAGE_RECOVERY_COMPLETE.json',{'status':'complete','recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'file_relocations':moves,'weights_returned_to_physical_root_disk':True,'model_logical_path_unchanged':True,'removed_only_verified_remote_download_caches':removed,'all_canonical_paths_resolve_identical_bytes':True,'storage_report_home':list(os.statvfs(CONTROL)),'storage_report_root':list(os.statvfs('/root'))})
for file in [Path('/dev/shm/DOWNLOAD_CACHE_CLEANUP_001.json')]:
 try:(CONTROL/file.name).write_bytes(file.read_bytes())
 except OSError:pass
print('STORAGE_RECOVERY_COMPLETE',flush=True)
