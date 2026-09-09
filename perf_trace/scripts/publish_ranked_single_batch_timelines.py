#!/usr/bin/env python3
"""Seal and publish the authorized single-batch offline presentation bundle."""
import argparse,datetime,hashlib,json,mimetypes,subprocess,urllib.request,urllib.parse,urllib.error,zipfile
from pathlib import Path
TAG='perf-trace-r10-ranked-timelines-20260909-v1';BASE='https://api.github.com/repos/cspool/auto_trace'
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main(root):
 site=root/'site';dist=root/'dist';dist.mkdir(exist_ok=True)
 for n in ['SOURCE_AUDIT.json','BROWSER_AUDIT.json']:
  d=json.loads((root/'validation'/n).read_text());assert d['status'] in ('complete','source_checks_complete')
 files={str(p.relative_to(site)):p for p in sorted(site.rglob('*')) if p.is_file()}
 for folder in ['validation','logs']:
  for p in sorted((root/folder).rglob('*')):
   if p.is_file() and p.name!='publication.log':files[str(p.relative_to(root))]=p
 files['README.md']=root/'README.md';files['WORKLOG.md']=root/'WORKLOG.md'
 scripts=Path(__file__).parent
 for p in [scripts/'build_ranked_single_batch_timelines.py',scripts/'audit_ranked_single_batch_timelines.py',Path(__file__)]+sorted((scripts/'ranked_timeline_assets').glob('*')):
  if p.is_file():files['tools/'+str(p.relative_to(scripts))]=p
 manifest={k:dict(sha256=sha(p),size=p.stat().st_size) for k,p in files.items()};dump(dist/'FILE_MANIFEST.json',manifest)
 archive=dist/'PerfTrace_single_batch_R10_ranked_timelines.zip'
 with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
  for name,p in files.items():z.write(p,name)
  z.write(dist/'FILE_MANIFEST.json','FILE_MANIFEST.json')
 with zipfile.ZipFile(archive) as z:
  for name,r in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==r['sha256']
 print('ZIP_ALL_MEMBERS_VERIFIED',archive.stat().st_size,sha(archive),flush=True)
 (dist/'SHA256SUMS').write_text(f'{sha(archive)}  {archive.name}\n{sha(dist/"FILE_MANIFEST.json")}  FILE_MANIFEST.json\n')
 cred=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,check=True)
 token=dict(l.split('=',1) for l in cred.stdout.splitlines() if '=' in l)['password']
 def headers():return {'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'AutoTrace-ranked-timeline-publication','X-GitHub-Api-Version':'2022-11-28'}
 def api(url,method='GET',data=None):
  h=headers();h['Content-Type']='application/json';request=urllib.request.Request(url,method=method,headers=h,data=json.dumps(data,ensure_ascii=False).encode() if data is not None else None)
  with urllib.request.urlopen(request,timeout=90) as f:
   s=f.read();return json.loads(s) if s else None
 body='''单 batch Perf Trace 的 R10 展示补充：DCU1 内并发、高延迟 Process / 硬件证据、原始 SE 利用率、未知相邻采样间隔和 host launch gap。

下载 **PerfTrace_single_batch_R10_ranked_timelines.zip**，解压后双击 **index.html**；完全离线，无需 HTTP 服务。也可单独下载 HTML 页面打开。

- 完整 507,005 个区间、29,964 个唯一 kernel、34,782 个原始采样点；原封存 archives 与完整 Perfetto JSON 字节保留。
- 高延迟 128 条归为 1 组；并发 29 个 forward、利用率 26 个 Process 组，支持前 20 导航和任意排名/实例。
- 可逆折叠梯形、足够的行高、真实线性细节轴、精确 ns 跳转、原始点不连线/补零。
- Request 默认省略末尾仅有 Request 而无后续 trace 的 6,113,817 ns；原始完成时间保留并在各图前披露。
- 这是已封存 20260806 trace 的 presentation replay，不是新的模型运行或 formal R09/R10 regeneration。硬件重放属性不作为 R07 延迟；相邻采样点间距不是已证实的停采时长。

SOURCE_AND_SCOPE.json、FILE_MANIFEST.json、SHA256SUMS 和源码/浏览器审计随包提供。'''
 try:release=api(BASE+'/releases/tags/'+TAG)
 except urllib.error.HTTPError as e:
  if e.code!=404:raise
  head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip();release=api(BASE+'/releases','POST',dict(tag_name=TAG,target_commitish=head,name='Perf Trace 单 batch · R10 分组时间线与硬件证据',body=body,draft=False,prerelease=False))
 existing={a['name']:a for a in release['assets']};verified={}
 def upload(path):
  digest='sha256:'+sha(path);size=path.stat().st_size
  if path.name in existing:
   a=existing[path.name];assert a['size']==size and a.get('digest')==digest;verified[path.name]=a;return
  for attempt in range(1,4):
   class Body:
    def __iter__(self):
     with path.open('rb') as f:
      done=0
      for b in iter(lambda:f.read(4<<20),b''):
       yield b;done+=len(b)
       if done%(32<<20)==0 or done==size:print('SENT',path.name,done,size,flush=True)
   h=headers();h.update({'Content-Type':mimetypes.guess_type(path.name)[0] or 'application/octet-stream','Content-Length':str(size)})
   request=urllib.request.Request(release['upload_url'].split('{')[0]+'?name='+urllib.parse.quote(path.name),data=Body(),headers=h,method='POST')
   try:
    print('UPLOAD_BEGIN',path.name,attempt,flush=True)
    with urllib.request.urlopen(request,timeout=180) as f:a=json.load(f)
    assert a['size']==size and a.get('digest')==digest;verified[path.name]=a;print('SERVER_SHA256_VERIFIED',path.name,digest,flush=True);return
   except Exception as e:
    print('RETRY',path.name,type(e).__name__,flush=True);current=api(BASE+'/releases/'+str(release['id']));a=next((a for a in current['assets'] if a['name']==path.name),None)
    if a and a['size']==size and a.get('digest')==digest:verified[path.name]=a;return
    if a:
     assert a['state']=='starter' and a['size']==0,'Refuse overwriting a completed mismatched asset';api(BASE+'/releases/assets/'+str(a['id']),'DELETE')
    if attempt==3:raise
 assets=[archive,dist/'FILE_MANIFEST.json',dist/'SHA256SUMS',site/'SOURCE_AND_SCOPE.json',site/'HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html',site/'CONCURRENCY_UTILIZATION.html',site/'E2E_PROCESS_TIMELINE_LOSSLESS.html',root/'validation/screenshots/high_group.png',root/'validation/screenshots/concurrency_detail.png']
 for path in assets:upload(path)
 api(BASE+'/releases/'+str(release['id']),'PATCH',dict(body=body))
 dump(root/'PUBLICATION_COMPLETE.json',dict(status='complete',release_url=release['html_url'],tag=TAG,completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),archive_sha256=sha(archive),assets=verified))
 print('RELEASE_COMPLETE',release['html_url'],flush=True)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--report-root',type=Path,required=True);args=a.parse_args();main(args.report_root)
