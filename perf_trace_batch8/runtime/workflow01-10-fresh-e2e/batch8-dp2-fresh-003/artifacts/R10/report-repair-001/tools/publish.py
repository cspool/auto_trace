#!/usr/bin/env python3
"""Publish authorized R10 revision; verify every uploaded asset's server SHA-256."""
from pathlib import Path
import json,hashlib,zipfile,subprocess,urllib.request,urllib.parse,urllib.error,datetime,time,sys
ROOT=Path(__file__).resolve().parents[1];REPO=next(p for p in ROOT.parents if (p/'.git').is_dir());DIST=ROOT/'dist';DIST.mkdir(exist_ok=True)
TAG='perf-trace-batch8-r10-ranked-timelines-20260909-v1';SLUG='cspool/auto_trace'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
audit=json.loads((ROOT/'validation/REVISION_AUDIT.json').read_text());assert audit['status']=='complete'
for r in audit['presentation_files']:assert sha(ROOT/r['path'])==r['sha256']
head=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip();remote=subprocess.check_output(['git','-C',str(REPO),'ls-remote','origin','refs/heads/main'],text=True,timeout=40).split()[0];assert head==remote
assert not subprocess.check_output(['git','-C',str(REPO),'status','--porcelain','--',str(ROOT)],text=True)
# Preserve all prior candidate outputs/logs in the ZIP as a recoverable history.
excluded={'dist','__pycache__'};skip={'PUBLICATION_COMPLETE.json','logs/publication.log','publication_receipts/FILE_MANIFEST.json','publication_receipts/SHA256SUMS'}
paths=[p for p in sorted(ROOT.rglob('*')) if p.is_file() and not set(p.relative_to(ROOT).parts)&excluded and str(p.relative_to(ROOT)) not in skip]
manifest={'status':'verified','git_commit':head,'entry_point':'index.html','entries':[{'path':str(p.relative_to(ROOT)),'size':p.stat().st_size,'sha256':sha(p)} for p in paths]};dump(DIST/'FILE_MANIFEST.json',manifest)
archive=DIST/'R10_ranked_folded_timelines.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as z:
 for i,p in enumerate(paths):
  z.write(p,p.relative_to(ROOT))
  if i%100==0:print('ZIP_MEMBERS_WRITTEN',i,len(paths),flush=True)
 z.write(DIST/'FILE_MANIFEST.json','FILE_MANIFEST.json')
with zipfile.ZipFile(archive) as z:
 for r in manifest['entries']:
  h=hashlib.sha256()
  with z.open(r['path']) as f:
   for b in iter(lambda:f.read(8<<20),b''):h.update(b)
  assert h.hexdigest()==r['sha256'],r['path']
print('ZIP_ALL_MEMBER_HASHES_VERIFIED',archive.stat().st_size,flush=True)
assets=[archive,ROOT/'acceptance/HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html',ROOT/'acceptance/CONCURRENCY_UTILIZATION.html',ROOT/'acceptance/E2E_PROCESS_TIMELINE_LOSSLESS.html',ROOT/'acceptance/REQUEST_COVERAGE.html',ROOT/'REQUEST_VIEW_SCOPE.json',ROOT/'inspection/high_first_group.png',ROOT/'inspection/dual_first.png',ROOT/'inspection/request_coverage_trimmed.png',DIST/'FILE_MANIFEST.json']
(DIST/'SHA256SUMS').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in assets));assets.append(DIST/'SHA256SUMS')
cred=subprocess.run(['git','-C',str(REPO),'credential','fill'],input='protocol=https\nhost=github.com\n\n',capture_output=True,text=True,check=True,timeout=20);token=dict(l.split('=',1) for l in cred.stdout.splitlines() if '=' in l)['password']
def api(url,method='GET',data=None,ctype='application/json'):
 payload=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode() if data is not None else None
 req=urllib.request.Request(url,data=payload,method=method,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Content-Type':ctype,'User-Agent':'AutoTrace-R10-presentation'})
 with urllib.request.urlopen(req,timeout=600) as r:return json.load(r)
base='https://api.github.com/repos/'+SLUG
try:release=api(base+'/releases/tags/'+TAG)
except urllib.error.HTTPError as e:
 if e.code!=404:raise RuntimeError('Release lookup HTTP '+str(e.code)) from None
 body='R10 同一封存样例的展示修订：高延迟、硬件、双卡并发、原始利用率、未知采样缺口及相邻 kernel 间隔均可通过排名时间线查看。默认前 20 项/组，可查看全部排名。\n\n分组使用折叠梯形：每条横线连接一个 Process 的真实开始/结束。起止双轴与单轴可切换，长间隔以 // 标注，全部真实时间和压缩比例可查。可取消折叠、展开逐行、点击查看实例及硬件证据。原始单轴详情保留真实时长。\n\n完整过程时间线已裁剪无 trace 的 Request 尾部：744.747 s → 192.958 s，省略末尾 551.789 s；图前列出追踪范围、未展示范围和八请求各自的省略时间，真实客户端完成时间保留在源记录。\n\n解压 R10_ranked_folded_timelines.zip 后打开 index.html；独立 HTML 也可直接离线打开。ZIP 含完整原始 R10、未删减的数据、50 个高延迟组、全部 249 万采样点、800 采样缺口、全量排名 CSV、工具、日志、候选历史和审计。所有源端点与排名已独立核对，浏览器禁止网络后交互检查通过。\n\nR08 重放不作为延迟或 R07 实测利用率；未知缺口不是零利用率；不同设备同轴显示不证明细粒度同步。'
 release=api(base+'/releases','POST',{'tag_name':TAG,'target_commitish':head,'name':'R10 排名时间线 v1：折叠梯形分组与完整硬件证据','body':body,'draft':False,'prerelease':False})
existing={a['name']:a for a in release['assets']}
for p in assets:
 digest='sha256:'+sha(p);print('UPLOAD_BEGIN',p.name,p.stat().st_size,flush=True)
 if p.name in existing:v=existing[p.name]
 else:v=api(release['upload_url'].split('{')[0]+'?name='+urllib.parse.quote(p.name),'POST',p.read_bytes(),'application/octet-stream')
 assert v['size']==p.stat().st_size and v.get('digest')==digest,(p.name,v.get('digest'))
 print('ASSET_SERVER_SHA256_VERIFIED',p.name,digest,flush=True)
release=api(base+'/releases/'+str(release['id']));got={a['name']:a for a in release['assets']}
for p in assets:assert got[p.name]['size']==p.stat().st_size and got[p.name]['digest']=='sha256:'+sha(p)
receipt={'status':'published','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'git_commit':head,'release_url':release['html_url'],'all_expected_server_sizes_and_SHA256_verified':True,'archive_member_hashes_verified':True,'archive_member_count':len(manifest['entries'])+1,'assets':[{k:got[p.name][k] for k in ['name','size','digest','browser_download_url']} for p in assets]}
dump(ROOT/'PUBLICATION_COMPLETE.json',receipt);print('RELEASE_COMPLETE',receipt['release_url'],flush=True)
