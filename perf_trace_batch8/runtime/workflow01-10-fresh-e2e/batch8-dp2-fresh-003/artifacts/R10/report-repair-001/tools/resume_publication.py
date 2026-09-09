#!/usr/bin/env python3
"""Resume publication using streamed individual pages and independent ZIP parts."""
from pathlib import Path
import json,hashlib,urllib.request,urllib.parse,urllib.error,subprocess,concurrent.futures,datetime,time
ROOT=Path(__file__).resolve().parents[1];DIST=ROOT/'dist';TAG='perf-trace-batch8-r10-ranked-timelines-20260909-v1';BASE='https://api.github.com/repos/cspool/auto_trace';ARCHIVE=DIST/'R10_ranked_folded_timelines.zip';CHUNKS=DIST/'parts';CHUNKS.mkdir(exist_ok=True)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
cred=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',capture_output=True,text=True,check=True);token=dict(l.split('=',1) for l in cred.stdout.splitlines() if '=' in l)['password']
def headers():return {'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'AutoTrace-streamed-release','X-GitHub-Api-Version':'2022-11-28'}
def api(url,method='GET',data=None):
 h=headers();h['Content-Type']='application/json';r=urllib.request.Request(url,data=json.dumps(data,ensure_ascii=False).encode() if data is not None else None,method=method,headers=h)
 with urllib.request.urlopen(r,timeout=90) as f:
  body=f.read();return json.loads(body) if body else None
release=api(BASE+'/releases/tags/'+TAG);existing={a['name']:a for a in release['assets']}
# Remove only this publication's incomplete, zero-byte starter object, if present.
for name,a in existing.copy().items():
 if name==ARCHIVE.name and a['state']=='starter' and a['size']==0:api(BASE+'/releases/assets/'+str(a['id']),'DELETE');del existing[name]
results={}
def upload(p):
 digest='sha256:'+sha(p);size=p.stat().st_size
 if p.name in existing:
  a=existing[p.name];assert a['size']==size and a.get('digest')==digest;results[p.name]=a;return a
 for attempt in range(1,4):
  class Body:
   def __iter__(self):
    with p.open('rb') as f:
     done=0
     while True:
      data=f.read(4<<20)
      if not data:break
      yield data;done+=len(data)
      if done%(32<<20)==0 or done==size:print('SENT',p.name,done,size,flush=True)
  h=headers();h.update({'Content-Type':'application/octet-stream','Content-Length':str(size)})
  req=urllib.request.Request(release['upload_url'].split('{')[0]+'?name='+urllib.parse.quote(p.name),data=Body(),headers=h,method='POST')
  try:
   print('STREAM_UPLOAD_BEGIN',p.name,size,'attempt',attempt,flush=True)
   with urllib.request.urlopen(req,timeout=180) as f:a=json.load(f)
   assert a['size']==size and a.get('digest')==digest,(p.name,a.get('digest'));results[p.name]=a;print('SERVER_SHA256_VERIFIED',p.name,digest,flush=True);return a
  except Exception as err:
   print('UPLOAD_RETRY_STATE',p.name,type(err).__name__,flush=True)
   current=api(BASE+'/releases/'+str(release['id']));candidate=next((x for x in current['assets'] if x['name']==p.name),None)
   if candidate and candidate['size']==size and candidate.get('digest')==digest:results[p.name]=candidate;return candidate
   if candidate:
    assert candidate['state']=='starter' and candidate['size']==0,'Refuse overwriting a different completed asset';api(BASE+'/releases/assets/'+str(candidate['id']),'DELETE')
   if attempt==3:raise
# Small directly-openable results are available before the recoverable full archive.
assets=[ROOT/'acceptance/REQUEST_COVERAGE.html',ROOT/'REQUEST_VIEW_SCOPE.json',ROOT/'inspection/request_coverage_trimmed.png',ROOT/'inspection/high_first_group.png',ROOT/'inspection/dual_first.png',ROOT/'acceptance/E2E_PROCESS_TIMELINE_LOSSLESS.html',ROOT/'acceptance/HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html',ROOT/'acceptance/CONCURRENCY_UTILIZATION.html']
for p in assets:upload(p)
parts=[]
with ARCHIVE.open('rb') as f:
 for i in range(1,1000):
  b=f.read(64<<20)
  if not b:break
  p=CHUNKS/(ARCHIVE.name+f'.part{i:03d}')
  if not p.exists():p.write_bytes(b)
  assert sha(p)==hashlib.sha256(b).hexdigest();parts.append(p)
part_manifest={'archive_name':ARCHIVE.name,'archive_size':ARCHIVE.stat().st_size,'archive_sha256':sha(ARCHIVE),'release_tag':TAG,'download_base':'https://github.com/cspool/auto_trace/releases/download/'+TAG+'/','parts':[{'name':p.name,'size':p.stat().st_size,'sha256':sha(p)} for p in parts]};dump(DIST/'PARTS_MANIFEST.json',part_manifest)
restore='''#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,urllib.request,sys
root=Path(__file__).resolve().parent
manifest=json.loads((root/'PARTS_MANIFEST.json').read_text())
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
for part in manifest['parts']:
 p=root/part['name']
 if not p.exists():
  if '--download' not in sys.argv:raise SystemExit('Missing '+p.name+'; use --download to fetch missing parts')
  print('Downloading',p.name,flush=True)
  tmp=p.with_suffix(p.suffix+'.partial')
  with urllib.request.urlopen(manifest['download_base']+p.name,timeout=180) as src,tmp.open('wb') as dst:
   for b in iter(lambda:src.read(4<<20),b''):dst.write(b)
  assert tmp.stat().st_size==part['size'] and digest(tmp)==part['sha256'];tmp.rename(p)
 assert p.stat().st_size==part['size'] and digest(p)==part['sha256'],p
out=root/manifest['archive_name'];tmp=out.with_suffix('.assembling')
with tmp.open('wb') as dst:
 for part in manifest['parts']:
  with (root/part['name']).open('rb') as src:
   for b in iter(lambda:src.read(8<<20),b''):dst.write(b)
assert tmp.stat().st_size==manifest['archive_size'] and digest(tmp)==manifest['archive_sha256'];tmp.replace(out)
print('Verified',out,'; extract and open index.html')
'''
(DIST/'RESTORE_R10.py').write_text(restore)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(upload,parts))
more=[DIST/'PARTS_MANIFEST.json',DIST/'RESTORE_R10.py',DIST/'FILE_MANIFEST.json'];allassets=assets+parts+more
(DIST/'SHA256SUMS_SPLIT').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in allassets));more.append(DIST/'SHA256SUMS_SPLIT');allassets.append(DIST/'SHA256SUMS_SPLIT')
for p in more:upload(p)
current=api(BASE+'/releases/'+str(release['id']));got={a['name']:a for a in current['assets']}
for p in allassets:assert got[p.name]['size']==p.stat().st_size and got[p.name].get('digest')=='sha256:'+sha(p)
body=current['body']+'\n\n完整 ZIP 因大请求上传超时改为 64 MiB 分块发布，字节与原 ZIP 完全一致。先下载 RESTORE_R10.py 和 PARTS_MANIFEST.json 到同一目录，再运行 `python3 RESTORE_R10.py --download`，自动下载、逐块校验并重建 ZIP。各 HTML 可以单独下载直接离线打开。'
api(BASE+'/releases/'+str(release['id']),'PATCH',{'body':body})
receipt={'status':'published','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'release_url':current['html_url'],'git_commit':json.loads((DIST/'FILE_MANIFEST.json').read_text())['git_commit'],'publication_method':'streamed standalone pages and checksum-verified ZIP parts','archive_sha256':part_manifest['archive_sha256'],'archive_size':part_manifest['archive_size'],'all_expected_server_sizes_and_SHA256_verified':True,'assets':[{k:got[p.name][k] for k in ['name','size','digest','browser_download_url']} for p in allassets]};dump(ROOT/'PUBLICATION_COMPLETE.json',receipt);print('RELEASE_COMPLETE',receipt['release_url'],flush=True)
