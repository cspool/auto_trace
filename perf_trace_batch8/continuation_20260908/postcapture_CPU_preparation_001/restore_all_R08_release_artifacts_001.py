"""Outer restoration after all twelve accepted GPU captures; never a GPU phase."""
from pathlib import Path
import json,os,sys,time,hashlib,subprocess,requests,re,tarfile,zstandard,datetime,importlib.util
C=Path('/public/home/accl15ptg7/run_R08_R10');P=Path('/public/home/accl15ptg7/auto_trace');R=P/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001';O=R/'raw/runtime_tools/release_restoration_001';DEST=Path('/root/R08_release_restored_after_capture_001');DEADLINE=datetime.datetime.fromisoformat('2026-09-08T20:18:09+00:00').timestamp()
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def rec(p):return {'path':str(p),'size':Path(p).stat().st_size,'sha256':sha(p)}
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def available(p):
 s=os.statvfs(p);return s.f_bavail*s.f_frsize
def verify(x,p=None):
 p=Path(p or x['path']);assert p.is_file() and p.stat().st_size==x['size'] and sha(p)==x['sha256'],'restored source size/SHA256 mismatch';return p
def all_captures_closed():
 index=R/'normalized/accepted_captures.json';i=read(index);plan=read(R/'plans/r08_capture_plan.json');assert i['status']=='complete' and len(i['captures'])==12 and [x['segment_id'] for x in i['captures']]==[x['segment_id'] for x in plan['physical_captures']]
 for x in i['captures']:
  for k in ['execution_manifest','normalization_manifest','independent_audit']:verify(x[k])
  e=read(x['execution_manifest']['path']);assert e['all_started_processes_terminated'] and e['workload']['status']=='complete'
 # Refuse any still-running capture, service or worker process. Watchdogs are
 # outer metadata/release operations and are stopped separately before sealing.
 forbidden=[b'run_capture.py',b'launch_vllm.py',b'vllm.entrypoints',b'VLLM::Worker',b'VLLM::EngineCore']
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:a=(p/'cmdline').read_bytes().split(b'\0');comm=(p/'comm').read_bytes()
  except OSError:continue
  assert not any(any(token in arg for arg in a) or token in comm for token in forbidden),'capture/service still running'
 return i,rec(index)
def folder(seg):return C/'publication/checkpoint_001' if seg=='01__gqa6_pmc' else C/'publication/r08_02__gqa6_pmc_read' if seg=='02__gqa6_pmc_read' else C/'publication_emergency'/('r08_'+seg)
def wait_all_publications_and_offloads(index):
 while time.time()<DEADLINE-1800:
  ready=all((folder(x['segment_id'])/'PUBLICATION_COMPLETE.json').exists() and (R/'raw/runtime_tools/remote_release_offloads_001'/(x['segment_id']+'.complete.json')).exists() for x in index['captures'])
  if ready:break
  time.sleep(20)
 assert ready,'all accepted captures must be published and offload checkpoints closed'
 (C/'STOP_RELEASE_OFFLOAD_WATCHDOG').touch()
 # Wait for the offloader to observe its stop marker and exit normally.
 for _ in range(45):
  live=[]
  for p in Path('/proc').iterdir():
   if not p.name.isdigit():continue
   try:a=(p/'cmdline').read_bytes().split(b'\0')
   except OSError:continue
   if str(C/'offload_published_R08_files_001.py').encode() in a:live.append(p.name)
  if not live:break
  time.sleep(1)
 assert not live,'offloader must exit before restoration'
def prepare_weight_removal(index_rec,offloads):
 proof=O/'WEIGHTS_REMOVED_AFTER_ALL_CAPTURES.json'
 if proof.exists():return read(proof)
 model=Path('/root/Qwen3.5-27B');back=Path('/root/Qwen3.5-27B-verified-root-backing-20260908');weights=sorted(back.glob('*.safetensors*'));prepared=O/'WEIGHT_REMOVAL_PREPARED.json';assert prepared.exists() or len(weights)==11
 missing=sum(x['size'] for o in offloads for x in o['temporarily_evicted_files'] if not Path(x['path']).exists());nfs=available(C);root=available('/root');weight_bytes=sum(p.stat().st_size for p in weights)
 assert root+weight_bytes+nfs-missing>=20*(1<<30),'aggregate restore plus later stage reserve insufficient'
 prepared=O/'WEIGHT_REMOVAL_PREPARED.json'
 if prepared.exists():plan=read(prepared)
 else:
  records=[]
  for p in weights:
   assert not p.is_symlink() and p.resolve().is_relative_to(Path('/root'));link=model/p.name;assert link.is_symlink() and os.readlink(link)==str(p);records.append(rec(p))
  plan={'status':'authorized_after_all_12_accepted_captures','accepted_index':index_rec,'user_policy':rec(C/'USER_RELEASE_OFFLOAD_POLICY_20260908.json'),'weight_files':records,'weight_bytes':weight_bytes,'bytes_to_restore':missing,'root_available_before':root,'NFS_available_before':nfs,'minimum_aggregate_post_restore_reserve':20*(1<<30),'all_capture_processes_closed':True};save(prepared,plan)
 for x in plan['weight_files']:
  p=Path(x['path']);link=model/p.name
  if p.exists():verify(x);p.unlink();print('WEIGHT_REMOVED_AFTER_ALL_GPU_CAPTURES',p.name,x['size'],flush=True)
  if link.is_symlink():assert os.readlink(link)==str(p);link.unlink()
 result={**plan,'status':'complete','prepared':rec(prepared),'root_available_after':available('/root'),'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()};save(proof,result);return result

def download(asset,folder):
 dest=folder/asset['name'];expected={'path':str(dest),'size':asset['size'],'sha256':asset['digest'].split(':',1)[1]}
 if dest.exists():verify(expected);return dest
 part=dest.with_name(dest.name+'.partial');origin=requests.Session();cdn=requests.Session();cdn.trust_env=False;cdn.proxies={'http':os.environ['ftp_proxy'],'https':os.environ['ftp_proxy']};url=None
 for attempt in range(12):
  try:
   if url is None:
    with origin.get(asset['url'],headers={'Range':'bytes=0-0'},stream=True,timeout=(30,60)) as response:response.raise_for_status();url=response.url
   offset=part.stat().st_size if part.exists() else 0
   while offset<asset['size']:
    end=min(asset['size']-1,offset+(64<<20)-1)
    with cdn.get(url,headers={'Range':f'bytes={offset}-{end}'},stream=True,timeout=(30,90)) as response:
     if response.status_code in [401,403]:url=None;raise RuntimeError('signed URL refresh')
     response.raise_for_status();match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
     if response.status_code==206:assert match and int(match[1])==offset and int(match[3])==asset['size']
     else:assert response.status_code==200 and offset==0
     before=offset
     with part.open('ab' if offset else 'wb') as f:
      for data in response.iter_content(1<<20):
       limit=end+1-offset;data=data[:limit];f.write(data);offset+=len(data)
       if offset==end+1:break
     assert offset>before
   verify(expected,part);part.rename(dest);print('RESTORE_ASSET_SHA256_VERIFIED',dest.name,asset['size'],flush=True);return dest
  except Exception as error:
   print('RESTORE_DOWNLOAD_RETRY',asset['name'],attempt,type(error).__name__,flush=True)
   if part.exists() and part.stat().st_size==asset['size'] and sha(part)!=expected['sha256']:raise RuntimeError('corrupt complete download retained')
   time.sleep(min(30,attempt*2+1))
 raise RuntimeError('bounded download failed')
class ConcatReader:
 def __init__(self,paths):self.paths=iter(paths);self.current=None
 def read(self,size=-1):
  if self.current is None:
   try:self.current=next(self.paths).open('rb')
   except StopIteration:return b''
  data=self.current.read(size)
  if data:return data
  self.current.close();self.current=None;return self.read(size)
 def close(self):
  if self.current is not None:self.current.close()

def restore_segment(offload):
 seg=offload['segment_id'];complete=O/(seg+'.complete.json')
 if complete.exists():
  result=read(complete)
  for x in offload['temporarily_evicted_files']:verify(x)
  return result
 out=C/'release_restore_downloads_001'/seg;out.mkdir(parents=True,exist_ok=True);assets=[a for a in offload['remote_verification']['assets'] if '.tar.zst' in a['name']];assert assets and all(a['digest'].startswith('sha256:') for a in assets)
 paths=[download(a,out) for a in sorted(assets,key=lambda a:a['name'])]
 filemanifest=offload['published_file_manifest'];verify(filemanifest);expected={x['path']:x for x in read(filemanifest['path'])['files']};wanted={x['archive_member_path']:x for x in offload['temporarily_evicted_files']};seen=set();moves=[]
 prepared=O/(seg+'.prepared.json')
 if prepared.exists():placement=read(prepared)['placements']
 else:
  placement=[];root_free=available('/root');nfs_free=available(C)
  for member,x in sorted(wanted.items(),key=lambda kv:-kv[1]['size']):
   lexical=Path(x['path']);assert lexical.is_relative_to(R) and '..' not in lexical.parts
   if lexical.exists():dest=lexical
   elif root_free-x['size']>=8*(1<<30):dest=DEST/lexical.relative_to(P);root_free-=x['size']
   else:assert nfs_free-x['size']>=10*(1<<30),'NFS restoration reserve';dest=lexical;nfs_free-=x['size']
   placement.append({**x,'destination_path':str(dest)})
  save(prepared,{'status':'prepared','offload_record':rec(R/'raw/runtime_tools/remote_release_offloads_001'/(seg+'.complete.json')),'placements':placement,'all_GPU_captures_accepted_before_any_root_restore':True})
 chosen={x['archive_member_path']:x for x in placement}
 with zstandard.ZstdDecompressor().stream_reader(ConcatReader(paths)) as stream:
  with tarfile.open(fileobj=stream,mode='r|') as tar:
   for member in tar:
    if member.name not in wanted:continue
    assert member.isfile() and member.name not in seen and member.size==expected[member.name]['size'];x=chosen[member.name];assert x['sha256']==expected[member.name]['sha256'];dest=Path(x['destination_path']);source=Path(x['path']);dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():verify(x,dest)
    else:
     temporary=dest.with_name(dest.name+'.restoring');digest=hashlib.sha256()
     with tar.extractfile(member) as src,temporary.open('wb') as f:
      for block in iter(lambda:src.read(8<<20),b''):f.write(block);digest.update(block)
      f.flush();os.fsync(f.fileno())
     assert temporary.stat().st_size==x['size'] and digest.hexdigest()==x['sha256'],'exact published raw member restoration';temporary.rename(dest)
    if dest!=source:
     if source.is_symlink():assert os.readlink(source)==str(dest)
     else:assert not source.exists();source.symlink_to(dest)
     moves.append({**x,'source_path':str(source),'same_bytes':True,'canonical_link_verified':True,'source_content_not_changed':True})
    verify(x);seen.add(member.name);print('R08_RAW_SOURCE_RESTORED',seg,source.name,x['size'],flush=True)
 assert seen==set(wanted),'every temporarily evicted file restored'
 result={'status':'complete','segment_id':seg,'prepared_record':rec(prepared),'file_mappings':moves,'restored_files':offload['temporarily_evicted_files'],'all_original_SHA256_verified':True,'remote_backing':offload['remote_verification'],'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()};save(complete,result)
 for path in paths:path.unlink()
 return result

def main():
 O.mkdir(exist_ok=True);index,indexrec=all_captures_closed();wait_all_publications_and_offloads(index)
 offloads=[read(R/'raw/runtime_tools/remote_release_offloads_001'/(x['segment_id']+'.complete.json')) for x in index['captures']];assert len(offloads)==12
 prepare_weight_removal(indexrec,offloads);results=[restore_segment(x) for x in offloads]
 for offload in offloads:
  for x in offload['temporarily_evicted_files']:verify(x)
 if not (O/'COMPLETE.json').exists():save(O/'COMPLETE.json',{'status':'complete','accepted_index':indexrec,'all_twelve_capture_parts_restored':True,'all_evicted_raw_files_original_SHA256_verified':True,'weight_removal':rec(O/'WEIGHTS_REMOVED_AFTER_ALL_CAPTURES.json'),'segment_receipts':[rec(O/(x['segment_id']+'.complete.json')) for x in offloads],'file_mappings':[m for x in results for m in x['file_mappings']],'user_policy':rec(C/'USER_RELEASE_OFFLOAD_POLICY_20260908.json'),'restored_bytes':sum(x['size'] for o in offloads for x in o['temporarily_evicted_files']),'new_stage_outputs_logs_still_physical_NFS':True})
 print('ALL_R08_RELEASE_EVICTIONS_RESTORED_AND_VERIFIED',flush=True)
if __name__=='__main__':main()
