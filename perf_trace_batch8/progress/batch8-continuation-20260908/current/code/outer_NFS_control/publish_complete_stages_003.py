"""Outer NFS publisher for complete, closed R08/R09/R10 stages."""
from pathlib import Path
import json,hashlib,tarfile,time,os,sys,subprocess,datetime,zstandard,requests,zipfile
CONTROL=Path('/public/home/accl15ptg7/run_R08_R10');PROJECT=Path('/public/home/accl15ptg7/auto_trace');RUN=PROJECT/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003';DEADLINE=datetime.datetime.fromisoformat('2026-09-09T04:18:09+00:00').timestamp()
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':sha(p)}
def save(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(x,f,indent=2,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
# Reuse only the tested codec I/O classes, without executing the polling loop.
namespace={};source=(CONTROL/'publish_accepted_captures_003.py').read_text();exec(compile(source[:source.index('while time.time()<DEADLINE:')],'<publication-codec-primitives>','exec'),namespace);SplitWriter=namespace['SplitWriter'];ConcatReader=namespace['ConcatReader']
def package(stage,out):
 hpath=RUN/'handoffs'/(stage+'.continuation.json');h=read(hpath);assert h['status']=='complete' and h['all_started_processes_terminated'];root=RUN/'artifacts'/stage/'continuation_001';manifest=read(h['artifact_manifest']['path']);assert sha(h['artifact_manifest']['path'])==h['artifact_manifest']['sha256'] and read(h['completion_audit']['path'])['status']=='complete';out.mkdir(parents=True,exist_ok=True)
 if (out/'ASSET_MANIFEST.json').exists():
  a=read(out/'ASSET_MANIFEST.json')
  for x in a['assets']:assert sha(out/x['name'])==x['sha256']
  return a
 for p in out.glob('capture.tar.zst.part*'):p.unlink()
 for name in ['FILE_MANIFEST.json','SHA256SUMS','R10_offline_acceptance.zip']:
  (out/name).unlink(missing_ok=True)
 files={Path(x['path']) for x in manifest['files']};files|={hpath,Path(h['artifact_manifest']['path']),Path(h['completion_audit']['path'])};files|={Path(x['path']) for x in h['phase_lifecycle']+h['closed_logs']};files=sorted(files);nfs=os.stat(CONTROL).st_dev
 restoration=read(RUN/'artifacts/R08/continuation_001/raw/runtime_tools/release_restoration_001/COMPLETE.json');restored={x['source_path']:x for x in restoration['file_mappings']}
 for p in files:
  if p.stat().st_dev!=nfs:
   assert str(p) in restored and p.resolve()==Path(restored[str(p)]['destination_path']) and sha(p)==restored[str(p)]['sha256'],'only exact user-authorized restored R08 source files may be physical root'
 remote_files=[]
 if stage=='R08':
  covered={}
  index=read(root/'normalized/accepted_captures.json')
  for item in index['captures']:
   seg=item['segment_id'];folder=CONTROL/'publication/checkpoint_001' if seg=='01__gqa6_pmc' else CONTROL/'publication/r08_02__gqa6_pmc_read' if seg=='02__gqa6_pmc_read' else CONTROL/'publication_emergency'/('r08_'+seg);receipt=read(folder/'PUBLICATION_COMPLETE.json');assert receipt['status']=='published' and receipt['all_server_asset_sha256_match'];prefix=Path(item['execution_manifest']['path']).parent
   for member in read(folder/'FILE_MANIFEST.json')['files']:
    q=PROJECT/member['path']
    if q.is_relative_to(prefix):covered[q]={'archive_member':member,'published_release':rec(folder/'PUBLICATION_COMPLETE.json'),'published_file_manifest':rec(folder/'FILE_MANIFEST.json'),'release_url':receipt.get('url',receipt.get('html_url',receipt.get('release_url')))}
  kept=[]
  for p in files:
   if p in covered:
    x=covered[p];assert p.stat().st_size==x['archive_member']['size'] and sha(p)==x['archive_member']['sha256'];remote_files.append(x)
   else:kept.append(p)
  files=kept
 records=[{'path':str(p.relative_to(PROJECT)),**{k:v for k,v in rec(p).items() if k!='path'}} for p in files];save(out/'FILE_MANIFEST.json',{'status':'complete_closed_stage','runtime_goal':stage,'runtime_run_id':'batch8-dp2-fresh-003','handoff':rec(hpath),'completion_audit':h['completion_audit'],'files':records,'previously_published_raw_files':remote_files,'previously_published_raw_files_are_not_duplicated_in_this_archive':bool(remote_files),'complete_restore_instructions':'Extract this archive and all referenced accepted-capture Releases; validate the full stage artifact_manifest.json. Previously published bytes remain available in their original Releases.','weights_included':False,'all_new_stage_outputs_and_logs_physically_NFS':True,'original_R08_raw_restoration':rec(RUN/'artifacts/R08/continuation_001/raw/runtime_tools/release_restoration_001/COMPLETE.json'),'original_R07_native_controller_terminal_claimed':False,'upstream_artifacts_remain_in_prior_same_run_releases':True})
 writer=SplitWriter(out)
 try:
  with zstandard.ZstdCompressor(level=3,threads=4).stream_writer(writer,closefd=False) as compressed:
   with tarfile.open(fileobj=compressed,mode='w|',dereference=True) as tar:
    for p in files:tar.add(p,arcname=str(p.relative_to(PROJECT)),recursive=False)
    tar.add(out/'FILE_MANIFEST.json',arcname='PUBLICATION_FILE_MANIFEST.json',recursive=False)
 finally:writer.close()
 expected={x['path']:x for x in records};seen=set()
 with zstandard.ZstdDecompressor().stream_reader(ConcatReader(writer.paths)) as stream:
  with tarfile.open(fileobj=stream,mode='r|') as tar:
   for member in tar:
    if member.name=='PUBLICATION_FILE_MANIFEST.json':assert json.load(tar.extractfile(member))==read(out/'FILE_MANIFEST.json');continue
    assert member.isfile() and member.name in expected and member.name not in seen;f=tar.extractfile(member);digest=hashlib.sha256()
    for b in iter(lambda:f.read(8<<20),b''):digest.update(b)
    assert member.size==expected[member.name]['size'] and digest.hexdigest()==expected[member.name]['sha256'];seen.add(member.name)
 assert seen==set(expected);assets=writer.paths+[out/'FILE_MANIFEST.json']
 if stage=='R10':
  zpath=out/'R10_offline_acceptance.zip';zfiles=sorted(p for p in (root/'acceptance').iterdir() if p.is_file())+[root/'R10_SOURCE_LINEAGE.json',root/'R10_COMPLETION_AUDIT.json'];zexpected={str(p.relative_to(root)):rec(p) for p in zfiles}
  with zipfile.ZipFile(zpath,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as z:
   for p in zfiles:z.write(p,str(p.relative_to(root)))
  with zipfile.ZipFile(zpath) as z:
   assert set(z.namelist())==set(zexpected)
   for name,x in zexpected.items():
    digest=hashlib.sha256()
    with z.open(name) as f:
     for b in iter(lambda:f.read(8<<20),b''):digest.update(b)
    assert digest.hexdigest()==x['sha256']
  assets.append(zpath)
 result={'status':'verified_ready_for_release','runtime_goal':stage,'member_count':len(seen),'previously_published_raw_file_count':len(remote_files),'member_bytes':sum(x['size'] for x in records),'archive_codec':'zstd one concatenated tar stream; concatenate capture.tar.zst parts in order before extraction','assets':[{'name':p.name,'size':p.stat().st_size,'sha256':sha(p)} for p in assets]};save(out/'ASSET_MANIFEST.json',result);(out/'SHA256SUMS').write_text(''.join(x['sha256']+'  '+x['name']+'\n' for x in result['assets']));print('CLOSED_STAGE_PACKAGE_VERIFIED',stage,len(seen),flush=True);return result

def publish(stage,out,manifest):
 base='https://api.github.com/repos/cspool/auto_trace';tag='perf-trace-batch8-'+stage.lower()+'-complete-20260908';p=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'});assert p.returncode==0;token=dict(x.split('=',1) for x in p.stdout.splitlines() if '=' in x)['password'];api=requests.Session();api.headers.update({'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'});r=api.get(base+'/releases/tags/'+tag,timeout=45)
 if r.status_code==404:
  body=stage+' 已完成并通过独立审计。包含本阶段原始数据/阶段产物、冻结代码、关闭后的日志、来源与完成审计。\n\n权重在全部 R08 GPU 采集期间保存在物理 /root；全部采集完成后按用户授权移除，为恢复已发布的原始产物提供校验空间。所有临时移除的文件已恢复并核对原始 SHA256；新阶段产物、日志和发布缓存均在物理 NFS。所有八个请求均须通过完整声明目标覆盖检查；R07 原始采集器终态未证实的历史例外保持不变。\n\n按 ASSET_MANIFEST 顺序拼接 capture.tar.zst 分卷后解包，按 FILE_MANIFEST 核验每个文件。'
  if stage=='R08':body+='\n\n已逐段发布的通过审计原始采集数据不重复上传；完整来源列于 FILE_MANIFEST.json 的 previously_published_raw_files。恢复时合并这些已发布的采集 Release，再按完整 artifact_manifest.json 校验。当前 Release 包含最终资源模型、阶段审计、代码、日志和此前未发布的失败采集证据。'
  if stage=='R10':body+='\n\n人工查看：下载 R10_offline_acceptance.zip，完整解压后离线打开 acceptance/index.html。全部 59,872 个主显示事件、原始利用率和上下文保留；无抽样。'
  r=api.post(base+'/releases',json={'tag_name':tag,'target_commitish':subprocess.check_output(['git','-C',str(PROJECT),'rev-parse','HEAD'],text=True).strip(),'name':stage+' complete · Batch8 DP2 · 2026-09-08','body':body,'draft':True,'prerelease':False},timeout=45);assert r.status_code==201
 else:assert r.status_code==200
 release=r.json();actual={x['name']:x for x in release['assets']};paths=[out/x['name'] for x in manifest['assets']]+[out/'ASSET_MANIFEST.json',out/'SHA256SUMS'];upload=requests.Session();upload.trust_env=False;proxy=os.environ.get('ftp_proxy');assert proxy;upload.proxies={'http':proxy,'https':proxy};upload.headers.update({'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'})
 for p in paths:
  size=p.stat().st_size;digest='sha256:'+sha(p)
  if p.name in actual:assert actual[p.name]['size']==size and actual[p.name].get('digest')==digest;continue
  print('CLOSED_STAGE_UPLOAD_START',stage,p.name,size,flush=True)
  with p.open('rb') as f:r=upload.post(release['upload_url'].split('{',1)[0],params={'name':p.name},headers={'Content-Length':str(size)},data=f,timeout=(60,3600))
  assert r.status_code==201;r=r.json();assert r['state']=='uploaded' and r['size']==size and r.get('digest')==digest;print('CLOSED_STAGE_UPLOAD_VERIFIED',stage,p.name,flush=True)
 if release['draft']:
  r=api.patch(base+'/releases/'+str(release['id']),json={'draft':False},timeout=45);assert r.status_code==200 and not r.json()['draft']
 r=api.get(base+'/releases/'+str(release['id']),timeout=45);assert r.status_code==200;release=r.json();actual={x['name']:x for x in release['assets']};assert not release['draft'] and set(actual)=={p.name for p in paths}
 for p in paths:assert actual[p.name]['size']==p.stat().st_size and actual[p.name].get('digest')=='sha256:'+sha(p)
 save(out/'PUBLICATION_COMPLETE.json',{'status':'published','runtime_goal':stage,'tag':tag,'url':release['html_url'],'all_server_asset_sha256_match':True,'handoff':rec(RUN/'handoffs'/(stage+'.continuation.json')),'assets':[{k:x[k] for k in ['id','name','size','digest','browser_download_url']} for x in release['assets']]});print('CLOSED_STAGE_RELEASE_PUBLISHED',stage,release['html_url'],flush=True)
 # Raw data and stage outputs remain on NFS. Only upload copies are removed.
 for p in paths:
  if p.name.startswith('capture.tar.zst.part') or p.suffix=='.zip':p.unlink()
 save(out/'LOCAL_UPLOAD_CACHE_CLEANUP.json',{'status':'complete','only_server_SHA256_verified_upload_copies_removed':True,'all_original_stage_data_outputs_logs_retained_under_verified_storage_authorizations':True})

def main():
 while time.time()<DEADLINE:
  try:
   for stage in ['R08','R09','R10']:
    h=RUN/'handoffs'/(stage+'.continuation.json');out=CONTROL/'publication'/('complete_'+stage)
    if not h.exists() or (out/'PUBLICATION_COMPLETE.json').exists():continue
    publish(stage,out,package(stage,out))
   if all((CONTROL/'publication'/('complete_'+s)/'PUBLICATION_COMPLETE.json').exists() for s in ['R08','R09','R10']):return
  except Exception as error:print('CLOSED_STAGE_PUBLICATION_RETRY',type(error).__name__,str(error) if isinstance(error,AssertionError) else '',flush=True)
  if (CONTROL/'STOP_COMPLETE_STAGE_PUBLISHER').exists():return
  time.sleep(30)
if __name__=='__main__':main()
