"""Publish byte-verified stage assets using the existing Git credential helper."""
from pathlib import Path
import requests,subprocess,os,json,sys,hashlib,time,argparse
ap=argparse.ArgumentParser();ap.add_argument('--package',required=True);ap.add_argument('--tag',required=True);ap.add_argument('--title',required=True);ap.add_argument('--body-file',required=True);ap.add_argument('--commit',required=True);args=ap.parse_args();root=Path(args.package)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def main():
 p=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'},timeout=30);assert p.returncode==0,'credential helper unavailable';credential=dict(l.split('=',1) for l in p.stdout.splitlines() if '=' in l);token=credential['password']
 api=requests.Session();api.headers.update({'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
 base='https://api.github.com/repos/cspool/auto_trace';existing=api.get(base+'/releases/tags/'+args.tag,timeout=30);assert existing.status_code==404,'release tag already exists; preserve immutable publication'
 create=api.post(base+'/releases',json={'tag_name':args.tag,'target_commitish':args.commit,'name':args.title,'body':Path(args.body_file).read_text(),'draft':True,'prerelease':True},timeout=30);assert create.status_code==201,'release creation failed '+str(create.status_code);release=create.json();(root/'DRAFT_RELEASE.json').write_text(json.dumps({k:release[k] for k in ['id','tag_name','html_url','upload_url','draft']},indent=2)+'\n')
 upload=requests.Session();upload.trust_env=False;proxy=os.environ.get('ftp_proxy');assert proxy,'configured upload proxy';upload.proxies={'https':proxy,'http':proxy};upload.headers.update({'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':'application/octet-stream'})
 assets=[]
 paths=[root/x for x in ['r07-cpu-r08-first-accepted-20260908.tar.zst','FILE_MANIFEST.json','ASSET_MANIFEST.json','SHA256SUMS']]
 for path in paths:
  digest=sha(path);size=path.stat().st_size;print('UPLOAD_START',path.name,size,flush=True)
  with path.open('rb') as f:response=upload.post(release['upload_url'].split('{',1)[0],params={'name':path.name},headers={'Content-Length':str(size)},data=f,timeout=(60,3600))
  assert response.status_code==201,'asset upload HTTP '+str(response.status_code);asset=response.json();assert asset['size']==size and asset['state']=='uploaded','server asset incomplete';server_digest=asset.get('digest');assert server_digest=='sha256:'+digest,'server SHA-256 mismatch or absent'
  record={k:asset[k] for k in ['id','name','size','state','browser_download_url','digest']};assets.append(record);print('UPLOAD_VERIFIED',path.name,record['digest'],flush=True)
  with (root/(path.name+'.remote.json')).open('x') as f:json.dump(record,f,indent=2)
 publish=api.patch(base+'/releases/'+str(release['id']),json={'draft':False},timeout=30);assert publish.status_code==200 and publish.json()['draft'] is False,'publication failed';published=publish.json();remote=api.get(base+'/releases/'+str(release['id']),timeout=30);assert remote.status_code==200 and len(remote.json()['assets'])==len(assets),'remote release verification'
 result={'status':'published','tag':args.tag,'url':published['html_url'],'id':release['id'],'commit':args.commit,'all_server_asset_sha256_match':True,'assets':assets}
 with (root/'PUBLICATION_COMPLETE.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print('RELEASE_PUBLISHED',published['html_url'],flush=True)
try:main()
except Exception as error:
 print('PUBLICATION_FAILED',type(error).__name__,flush=True)
 with (root/'PUBLICATION_FAILURE.json').open('x') as f:json.dump({'status':'failed','exception_type':type(error).__name__,'secret_details_omitted':True},f,indent=2)
 raise SystemExit(1)
