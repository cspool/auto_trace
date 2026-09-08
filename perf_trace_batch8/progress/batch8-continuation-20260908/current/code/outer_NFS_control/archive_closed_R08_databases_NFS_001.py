"""Reversible lossless NFS backing for closed databases; retain original identities."""
from pathlib import Path
import json,hashlib,os,time,datetime,zstandard,sys
CONTROL=Path('/public/home/accl15ptg7/run_R08_R10');ROOT=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');OUT=ROOT/'raw/runtime_tools/NFS_database_archives_001';OUT.mkdir(exist_ok=True);DEADLINE=datetime.datetime.fromisoformat('2026-09-08T20:18:09+00:00').timestamp()
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':sha(p)}
def save(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def stream_check(archive,size,digest):
 h=hashlib.sha256();count=0
 with archive.open('rb') as raw:
  with zstandard.ZstdDecompressor().stream_reader(raw) as f:
   for b in iter(lambda:f.read(8<<20),b''):count+=len(b);h.update(b)
 assert count==size and h.hexdigest()==digest,'independent full decompressed byte identity'
 return {'uncompressed_size':count,'uncompressed_sha256':h.hexdigest(),'all_bytes_recovered_exactly':True}
def archive_one(raw,prepare_only=False):
 source=raw/'capture.db';execution=raw/'execution_manifest.json';inventory=raw/'raw_inventory_at_exit.json'
 if not source.is_file() or source.is_symlink() or source.stat().st_size<500_000_000 or not execution.exists():return
 e=read(execution);assert e['all_started_processes_terminated'];expected=next(x for x in read(inventory)['files'] if x['path']==str(source));key=hashlib.sha256(str(source).encode()).hexdigest();done=OUT/(key+'.complete.json')
 if done.exists():return
 # An accepted database is archived only after the complete original raw
 # capture was published and its server SHA-256 independently verified.
 accepted=[]
 for p in list((ROOT/'validation').glob('serial_scheduler_*/*.accepted_checkpoint.json'))+list((ROOT/'raw/runtime_tools').glob('serial_scheduler_*/*.accepted_checkpoint.json')):
  item=read(p)['item']
  if item['execution_manifest']['path']==str(execution):accepted.append(item)
 remote=None
 if accepted:
  seg=accepted[0]['segment_id'];receipt=CONTROL/'publication/checkpoint_001/PUBLICATION_COMPLETE.json' if seg=='01__gqa6_pmc' else CONTROL/'publication_emergency'/('r08_'+seg)/'PUBLICATION_COMPLETE.json'
  if not receipt.exists():return
  r=read(receipt);assert r['status']=='published' and r['all_server_asset_sha256_match'];remote=rec(receipt)
 archive=source.with_name('capture.db.lossless.zst');prepared=OUT/(key+'.prepared.json');assert source.stat().st_dev==os.stat(CONTROL).st_dev,'source physically NFS'
 if prepared.exists():
  record=read(prepared);assert record['original_file']==expected and archive.stat().st_size==record['archive']['size'] and sha(archive)==record['archive']['sha256'];stream_check(archive,expected['size'],expected['sha256'])
 else:
  archive.unlink(missing_ok=True);digest=hashlib.sha256();count=0
  with source.open('rb') as f,archive.open('xb') as out:
   with zstandard.ZstdCompressor(level=3,threads=2).stream_writer(out,closefd=False) as z:
    for b in iter(lambda:f.read(8<<20),b''):digest.update(b);count+=len(b);z.write(b)
   out.flush();os.fsync(out.fileno())
  assert count==expected['size'] and digest.hexdigest()==expected['sha256'],'original immutable inventory bytes';check=stream_check(archive,count,digest.hexdigest());record={'schema_version':1,'status':'verified_ready_for_reversible_NFS_archive','runtime_goal':'R08','runtime_run_id':'batch8-dp2-fresh-003','original_file':expected,'archive':rec(archive),'archive_codec':'zstd','decompressed_byte_verification':check,'execution_manifest':rec(execution),'raw_inventory':rec(inventory),'prior_remote_publication':remote,'physically_stored_on_NFS':True,'storage_policy':rec(CONTROL/'USER_STORAGE_POLICY_20260908.json'),'no_model_or_device_execution_performed':True,'original_inventory_or_execution_manifest_modified':False,'restore_instruction':'Stream zstd decompression from archive.path into original_file.path on NFS; verify full uncompressed size and SHA-256 before any SQLite read. Never point a .db symlink at compressed bytes.','prepared_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()};save(prepared,record)
 # Only the exact, closed uncompressed duplicate is removed. The original
 # byte stream is preserved in full on NFS and already round-trip verified.
 if prepare_only:return record
 assert sha(source)==expected['sha256'];source.unlink();save(done,{**record,'status':'complete','uncompressed_duplicate_removed':True,'prepared_record':rec(prepared),'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()});print('NFS_CLOSED_DATABASE_ARCHIVED',raw.parent.name,raw.name,expected['size'],archive.stat().st_size,flush=True)
def main():
 while time.time()<DEADLINE:
  try:
   for raw in sorted((ROOT/'raw/captures').glob('*/*')):archive_one(raw)
  except Exception as error:print('NFS_ARCHIVE_RETRY_REQUIRED',type(error).__name__,str(error),flush=True)
  if (CONTROL/'STOP_NFS_DATABASE_ARCHIVER').exists():return
  time.sleep(30)
if __name__=='__main__':main()
