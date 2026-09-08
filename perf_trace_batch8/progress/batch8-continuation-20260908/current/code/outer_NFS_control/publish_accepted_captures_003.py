"""Outer publisher: seal each accepted native capture, upload immutable split assets."""
from pathlib import Path
import os,sys,json,hashlib,tarfile,zstandard,time,datetime,requests,subprocess,io
CONTROL=Path('/public/home/accl15ptg7/run_R08_R10');PROJECT=Path('/public/home/accl15ptg7/auto_trace');ROOT=PROJECT/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001';DEADLINE=datetime.datetime.fromisoformat('2026-09-08T20:18:09+00:00').timestamp()
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def save(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
class SplitWriter:
 def __init__(self,root):self.root=root;self.paths=[];self.current=None;self.size=0;self.limit=950_000_000
 def writable(self):return True
 def write(self,data):
  count=len(data);view=memoryview(data)
  while view:
   if self.current is None or self.size==self.limit:
    if self.current:self.current.close()
    p=self.root/('capture.tar.zst.part%03d'%(len(self.paths)+1));self.current=p.open('xb');self.paths.append(p);self.size=0
   n=min(len(view),self.limit-self.size);self.current.write(view[:n]);self.size+=n;view=view[n:]
  return count
 def flush(self):
  if self.current:self.current.flush()
 def close(self):
  if self.current:self.current.close()
class ConcatReader:
 def __init__(self,paths):self.paths=iter(paths);self.f=None
 def read(self,n=-1):
  if n<0:n=8<<20
  while True:
   if self.f is None:
    p=next(self.paths,None)
    if p is None:return b''
    self.f=p.open('rb')
   b=self.f.read(n)
   if b:return b
   self.f.close();self.f=None
 def close(self):
  if self.f:self.f.close()
def package(item,out):
 if (out/'ASSET_MANIFEST.json').exists():
  result=read(out/'ASSET_MANIFEST.json')
  for x in result['assets']:assert (out/x['name']).stat().st_size==x['size'] and sha(out/x['name'])==x['sha256'],'existing package bytes'
  return result
 out.mkdir(parents=True,exist_ok=True)
 # A prior interrupted unverified package may be rebuilt; accepted source is untouched.
 for p in out.glob('capture.tar.zst.part*'):p.unlink()
 for name in ['FILE_MANIFEST.json','SHA256SUMS']:
  if (out/name).exists():(out/name).unlink()
 execution=Path(item['execution_manifest']['path']);normalization=Path(item['normalization_manifest']['path']);audit=Path(item['independent_audit']['path'])
 for key in ['execution_manifest','normalization_manifest','independent_audit']:assert sha(item[key]['path'])==item[key]['sha256'],'accepted source manifest identity'
 assert read(execution)['all_started_processes_terminated'] and read(audit)['status']=='complete','closed audited capture'
 files=[]
 for folder in [execution.parent,normalization.parent]:files.extend(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
 files=sorted(set(files));manifest=[{'path':str(p.relative_to(PROJECT)),'size':p.stat().st_size,'sha256':sha(p)} for p in files]
 save(out/'FILE_MANIFEST.json',{'schema_version':1,'status':'closed_accepted_capture','segment_id':item['segment_id'],'capture_attempt':item['capture_attempt'],'accepted_item':item,'files':manifest,'stage_R08_complete_claimed':False,'restore_root':'auto_trace repository checkout; exact relative paths; verify before resume'})
 writer=SplitWriter(out)
 try:
  with zstandard.ZstdCompressor(level=3,threads=4).stream_writer(writer,closefd=False) as compressed:
   with tarfile.open(fileobj=compressed,mode='w|',dereference=True) as tar:
    for p in files:tar.add(p,arcname=str(p.relative_to(PROJECT)),recursive=False)
    tar.add(out/'FILE_MANIFEST.json',arcname='PUBLICATION_FILE_MANIFEST.json',recursive=False)
 finally:writer.close()
 expected={x['path']:x for x in manifest};seen=set();concat=ConcatReader(writer.paths)
 with zstandard.ZstdDecompressor().stream_reader(concat) as stream:
  with tarfile.open(fileobj=stream,mode='r|') as tar:
   for m in tar:
    if m.name=='PUBLICATION_FILE_MANIFEST.json':assert json.load(tar.extractfile(m))==read(out/'FILE_MANIFEST.json');continue
    assert m.isfile() and m.name in expected and m.name not in seen,'exact archived member set';f=tar.extractfile(m);h=hashlib.sha256()
    for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    assert m.size==expected[m.name]['size'] and h.hexdigest()==expected[m.name]['sha256'],'archived member content';seen.add(m.name)
 assert seen==set(expected),'all accepted raw and normalized bytes retained'
 assets=[{'name':p.name,'size':p.stat().st_size,'sha256':sha(p)} for p in writer.paths+[out/'FILE_MANIFEST.json']];result={'status':'verified_ready_for_release','member_count':len(seen),'member_bytes':sum(x['size'] for x in manifest),'archive_codec':'zstd one concatenated stream; concatenate parts in manifest order before extraction','assets':assets}
 save(out/'ASSET_MANIFEST.json',result);(out/'SHA256SUMS').write_text(''.join(x['sha256']+'  '+x['name']+'\n' for x in assets));print('ACCEPTED_CAPTURE_PACKAGE_VERIFIED',item['segment_id'],len(seen),sum(x['size'] for x in assets),flush=True);return result
def publish(item,out,package_manifest):
 tag='perf-trace-batch8-r08-'+item['segment_id'].replace('_','-')+'-20260908';base='https://api.github.com/repos/cspool/auto_trace'
 p=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'});assert p.returncode==0,'credential helper';token=dict(x.split('=',1) for x in p.stdout.splitlines() if '=' in x)['password']
 api=requests.Session();api.headers.update({'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'});response=api.get(base+'/releases/tags/'+tag,timeout=45)
 if response.status_code==404:
  commit=subprocess.check_output(['git','-C',str(PROJECT),'rev-parse','HEAD'],text=True).strip();body='R08 已通过独立审计的单组原始采集检查点：'+item['segment_id']+'。\n\n保留八并发 DP2 工作负载、原始 HIPProf DB/CSV、每进程原始 PMC、日志、规范化数据和独立审计。此 Release 只代表该组通过，不代表 R08/R09/R10 整体完成。\n\n按 ASSET_MANIFEST 顺序拼接 capture.tar.zst.partNNN 后用 zstd/tar 解包，逐项核验 FILE_MANIFEST SHA-256。原始采集代码及恢复说明在主分支和 progress/batch8-continuation-20260908 分支。'
  response=api.post(base+'/releases',json={'tag_name':tag,'target_commitish':commit,'name':'R08 accepted capture '+item['segment_id'],'body':body,'draft':True,'prerelease':True},timeout=45);assert response.status_code==201,'create release';release=response.json()
 else:assert response.status_code==200,'get release';release=response.json()
 assets={x['name']:x for x in release['assets']};paths=[out/x['name'] for x in package_manifest['assets']]+[out/'ASSET_MANIFEST.json',out/'SHA256SUMS'];upload=requests.Session();upload.trust_env=False;proxy=os.environ.get('ftp_proxy');assert proxy,'configured upload route';upload.proxies={'https':proxy,'http':proxy};upload.headers.update({'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':'application/octet-stream'})
 for path in paths:
  size=path.stat().st_size;digest='sha256:'+sha(path);asset=assets.get(path.name)
  if asset is not None:assert asset['size']==size and asset.get('digest')==digest and asset['state']=='uploaded','preserve existing asset, fail on mismatch';continue
  print('ACCEPTED_CAPTURE_UPLOAD_START',item['segment_id'],path.name,size,flush=True)
  with path.open('rb') as f:response=upload.post(release['upload_url'].split('{',1)[0],params={'name':path.name},headers={'Content-Length':str(size)},data=f,timeout=(60,3600))
  assert response.status_code==201,'asset HTTP status '+str(response.status_code);asset=response.json();assert asset['size']==size and asset['state']=='uploaded' and asset.get('digest')==digest,'server asset size and SHA-256';print('ACCEPTED_CAPTURE_UPLOAD_VERIFIED',path.name,digest,flush=True)
 if release['draft']:
  response=api.patch(base+'/releases/'+str(release['id']),json={'draft':False},timeout=45);assert response.status_code==200 and not response.json()['draft'],'publish complete release'
 response=api.get(base+'/releases/'+str(release['id']),timeout=45);assert response.status_code==200;remote=response.json();actual={a['name']:a for a in remote['assets']};assert not remote['draft'] and set(actual)=={p.name for p in paths},'published exact asset set'
 for path in paths:assert actual[path.name]['size']==path.stat().st_size and actual[path.name].get('digest')=='sha256:'+sha(path),'published remote bytes'
 result={'status':'published','tag':tag,'url':remote['html_url'],'id':remote['id'],'all_server_asset_sha256_match':True,'segment_id':item['segment_id'],'accepted_item':item,'assets':[{k:a[k] for k in ['id','name','size','state','browser_download_url','digest']} for a in remote['assets']]};save(out/'PUBLICATION_COMPLETE.json',result);print('ACCEPTED_CAPTURE_RELEASE_PUBLISHED',result['url'],flush=True)
while time.time()<DEADLINE:
 try:
  items={}
  for p in sorted(list((ROOT/'validation').glob('serial_scheduler_*/*.accepted_checkpoint.json'))+list((ROOT/'raw/runtime_tools').glob('serial_scheduler_*/*.accepted_checkpoint.json'))):
   item=read(p)['item'];items[item['segment_id']]=item
  for seg,item in sorted(items.items()):
   if seg=='01__gqa6_pmc':
    previous=CONTROL/'publication/checkpoint_001/PUBLICATION_COMPLETE.json';assert read(previous)['status']=='published' and read(previous)['all_server_asset_sha256_match'];continue
   out=CONTROL/'publication_emergency'/('r08_'+seg)
   if (out/'PUBLICATION_COMPLETE.json').exists():continue
   package_manifest=package(item,out);publish(item,out,package_manifest)
   for part in out.glob('capture.tar.zst.part*'):part.unlink()
   save(out/'LOCAL_UPLOAD_CACHE_CLEANUP.json',{'status':'complete','raw_capture_and_normalized_business_files_retained':True,'only_uploaded_verified_compressed_cache_removed':True,'remote_manifest':read(out/'PUBLICATION_COMPLETE.json')})
 except Exception as error:print('ACCEPTED_CAPTURE_PUBLICATION_RETRY',datetime.datetime.now(datetime.timezone.utc).isoformat(),type(error).__name__,str(error) if isinstance(error,AssertionError) else '',flush=True)
 if (CONTROL/'STOP_ACCEPTED_CAPTURE_PUBLISHER').exists():break
 time.sleep(60)
