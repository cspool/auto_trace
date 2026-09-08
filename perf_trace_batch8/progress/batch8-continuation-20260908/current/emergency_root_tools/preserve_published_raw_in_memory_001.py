"""Keep only remote-verified closed capture bytes in an explicit RAM backing."""
from pathlib import Path
import json,hashlib,shutil,os,time,datetime
ROOT=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');OUT=ROOT/'raw/runtime_tools/published_storage_maps_001';OUT.mkdir(exist_ok=True);DEST=Path('/dev/shm/r08_published_capture_backing_001');DEST.mkdir(exist_ok=True)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(16<<20),b''):h.update(b)
 return h.hexdigest()
def migrate(source,remote):
 rel=source.relative_to(ROOT/'raw/captures');dest=DEST/rel;size=source.stat().st_size
 memory=dict(x.split() for x in Path('/sys/fs/cgroup/memory/memory.stat').read_text().splitlines());assert int(memory['shmem'])+size<90*(1<<30),'retain runtime RSS reserve within121.5GiB memory limit'
 before=sha(source);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest);assert sha(dest)==before and dest.stat().st_size==size;dest.chmod(0o444)
 record={'status':'verified_same_bytes_storage_relocation','source_path':str(source),'destination_path':str(dest),'size':size,'sha256':before,'prior_remote_publication':remote,'role':'closed_accepted_native_capture_file','measurement_completed_on_original_root_disk':True,'new_measurement_or_content_change':False,'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()};name=hashlib.sha256(str(source).encode()).hexdigest()
 with (OUT/(name+'.authorization.json')).open('x') as f:json.dump(record,f,indent=2);f.write('\n')
 link=source.with_name(source.name+'.remote-verified-memory-link');link.symlink_to(dest);os.replace(link,source);assert sha(source)==before
 with (OUT/(name+'.complete.json')).open('x') as f:json.dump({**record,'status':'complete','canonical_link_verified':True},f,indent=2);f.write('\n')
 print('REMOTE_VERIFIED_RAW_MEMORY_BACKING',str(rel),size,shutil.disk_usage('/root').free,flush=True)
def checkpoint():
 accepted={}
 for path in list((ROOT/'validation').glob('serial_scheduler_*/*.accepted_checkpoint.json'))+list((ROOT/'raw/runtime_tools').glob('serial_scheduler_*/*.accepted_checkpoint.json')):
  x=json.loads(path.read_text())['item'];accepted[x['segment_id']]=x
 for seg,item in sorted(accepted.items()):
  if shutil.disk_usage('/root').free>=12*(1<<30):break
  receipt=Path('/public/home/accl15ptg7/run_R08_R10/publication/checkpoint_001/PUBLICATION_COMPLETE.json') if seg=='01__gqa6_pmc' else Path('/root/capture_publication_emergency')/('r08_'+seg)/'PUBLICATION_COMPLETE.json'
  if not receipt.exists():continue
  remote=json.loads(receipt.read_text());assert remote['status']=='published' and remote['all_server_asset_sha256_match'];raw=Path(item['execution_manifest']['path']).parent;assert json.loads((raw/'execution_manifest.json').read_text())['all_started_processes_terminated']
  candidates=sorted((p for p in raw.rglob('*') if p.is_file() and not p.is_symlink() and p.stat().st_size>=200_000_000),key=lambda p:p.stat().st_size,reverse=True)
  for source in candidates:
   if shutil.disk_usage('/root').free>=12*(1<<30):break
   migrate(source,{'path':str(receipt),'sha256':sha(receipt),'url':remote['url'],'all_server_asset_sha256_match':True})
while time.time()<datetime.datetime.fromisoformat('2026-09-08T20:18:09+00:00').timestamp():
 try:checkpoint()
 except Exception as error:print('RAW_STORAGE_CHECKPOINT_PENDING',type(error).__name__,str(error),flush=True)
 if Path('/root/r08_emergency_tools/STOP_RAW_STORAGE_WATCHDOG').exists():break
 time.sleep(30)
