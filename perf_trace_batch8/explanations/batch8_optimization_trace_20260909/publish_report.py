#!/usr/bin/env python3
"""Publish this authorized report with exact GitHub server asset digest verification."""
from pathlib import Path
import json,hashlib,subprocess,urllib.request,urllib.parse,urllib.error,os,zipfile,datetime,time
O=Path(__file__).resolve().parent;P=O.parents[2];DIST=O/'dist';DIST.mkdir(exist_ok=True)
REPO='cspool/auto_trace';TAG='perf-trace-batch8-dp2-scheduling-report-20260909-v2'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
a=json.loads((O/'REPORT_AUDIT.json').read_text());assert a['status']=='complete';assert sha(O/'REPORT.html')==a['report_html']['sha256'];assert sha(O/'Batch8_DP2_Scheduling_Report.pdf')==a['pdf']['sha256']
head=subprocess.check_output(['git','-C',str(P),'rev-parse','HEAD'],text=True).strip();remote=subprocess.check_output(['git','-C',str(P),'ls-remote','origin','refs/heads/main'],text=True,timeout=40).split()[0];assert head==remote
status=subprocess.check_output(['git','-C',str(P),'status','--porcelain','--',str(O)],text=True);assert not status,status
paths=[p for p in sorted(O.rglob('*')) if p.is_file() and not set(p.relative_to(O).parts)&{'dist','__pycache__','inspection'} and p.name not in ['PUBLICATION_COMPLETE.json']]
manifest={'status':'verified','relative_root':'.','git_commit':head,'entries':[{'path':str(p.relative_to(O)),'size':p.stat().st_size,'sha256':sha(p)} for p in paths]};dump(DIST/'FILE_MANIFEST.json',manifest)
archive=DIST/'Batch8_DP2_Scheduling_Report.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in paths:z.write(p,p.relative_to(O))
 z.write(DIST/'FILE_MANIFEST.json','FILE_MANIFEST.json')
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 for r in manifest['entries']:assert hashlib.sha256(z.read(r['path'])).hexdigest()==r['sha256']
assets=[archive,O/'REPORT.html',O/'Batch8_DP2_Scheduling_Report.pdf',DIST/'FILE_MANIFEST.json']
(DIST/'SHA256SUMS').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in assets));assets.append(DIST/'SHA256SUMS')
cred=subprocess.run(['git','-C',str(P),'credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,check=True,timeout=20);fields=dict(l.split('=',1) for l in cred.stdout.splitlines() if '=' in l);token=fields['password']
def api(url,method='GET',data=None,ctype='application/json'):
 payload=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode() if data is not None else None
 req=urllib.request.Request(url,data=payload,method=method,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Content-Type':ctype,'User-Agent':'AutoTrace-evidence-report'})
 with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)
base='https://api.github.com/repos/'+REPO
try:release=api(base+'/releases/tags/'+TAG)
except urllib.error.HTTPError as e:
 if e.code!=404:raise RuntimeError('Release lookup HTTP '+str(e.code)) from None
 body='使用固定、已验收的 Batch8 DP2 trace 解释 8 个请求如何分配到两张卡，各卡如何形成 B1–B4 动态 batch，以及 512-token 长 prefill 预算怎样影响 kernel 路径。\n\n下载 PDF 可直接阅读；REPORT.html 为独立离线图文报告，含八请求定位控件；ZIP 包含全部报告、图表、原始归属表、源码快照、生成代码及审计。\n\n已核对全部 23,660 个唯一 kernel 和两个 rank 的 4+4 请求覆盖，实际离线 Chromium 检查通过。图表使用原始观测时间；组成占比不作为加速比。'
 body='可读性修订 v2：第一节客户端长区间改为两块折叠矩形，Marker 宽度统一放大 12 倍并直接标注原始时长；第二节改为两行 16 个大信息矩形，按每卡实际启动顺序展示 B、时间与 kernel 配置。数据与 trace 计量不变。\n\n'+body
 release=api(base+'/releases','POST',{'tag_name':TAG,'target_commitish':head,'name':'Batch8 双卡调度：可视化报告 v2（折叠时间轴与大信息矩形）','body':body,'draft':False,'prerelease':False})
existing={a['name']:a for a in release['assets']}
for p in assets:
 digest='sha256:'+sha(p)
 if p.name in existing:
  v=existing[p.name];assert v['size']==p.stat().st_size and v.get('digest')==digest
 else:
  url=release['upload_url'].split('{')[0]+'?name='+urllib.parse.quote(p.name);v=api(url,'POST',p.read_bytes(),'application/octet-stream');assert v['size']==p.stat().st_size and v.get('digest')==digest
 print('REPORT_ASSET_VERIFIED',p.name,p.stat().st_size,digest,flush=True)
check=api(base+'/releases/'+str(release['id']));got={x['name']:x for x in check['assets']}
for p in assets:assert got[p.name]['size']==p.stat().st_size and got[p.name].get('digest')=='sha256:'+sha(p)
receipt={'status':'published','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'release_url':check['html_url'],'git_commit':head,'all_expected_asset_sizes_and_server_SHA256_verified':True,'assets':[{k:got[p.name][k] for k in ['name','size','digest','browser_download_url']} for p in assets],'archive_member_count':len(manifest['entries'])+1,'archive_members_SHA256_verified':True}
dump(O/'PUBLICATION_COMPLETE.json',receipt);print('REPORT_RELEASE_COMPLETE',receipt['release_url'],flush=True)
