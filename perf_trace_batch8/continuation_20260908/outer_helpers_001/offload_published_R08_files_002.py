"""User-authorized temporary local eviction after verified complete Release publication."""
from pathlib import Path
import json,os,hashlib,requests,subprocess,time,datetime
CONTROL=Path('/public/home/accl15ptg7/run_R08_R10');PROJECT=Path('/public/home/accl15ptg7/auto_trace');ROOT=PROJECT/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001';OUT=ROOT/'raw/runtime_tools/remote_release_offloads_001';OUT.mkdir(exist_ok=True);DEADLINE=datetime.datetime.fromisoformat('2026-09-09T04:18:09+00:00').timestamp()
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':sha(p)}
def save(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def verify_remote(receipt):
 r=read(receipt);assert r['status']=='published' and r['all_server_asset_sha256_match'];p=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'});assert p.returncode==0;token=dict(x.split('=',1) for x in p.stdout.splitlines() if '=' in x)['password'];response=requests.get('https://api.github.com/repos/cspool/auto_trace/releases/tags/'+r['tag'],headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'},timeout=45);assert response.status_code==200;current=response.json();assert not current['draft'];actual={x['name']:x for x in current['assets']}
 for x in r['assets']:assert actual[x['name']]['state']=='uploaded' and actual[x['name']]['size']==x['size'] and actual[x['name']].get('digest')==x['digest'],'current remote asset size/digest'
 return {'status':'complete','receipt':rec(receipt),'release_url':current['html_url'],'remote_rechecked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'assets':[{'name':x['name'],'size':x['size'],'digest':x['digest'],'url':x['browser_download_url']} for x in current['assets']]}
def checkpoint():
 accepted={}
 for p in list((ROOT/'validation').glob('serial_scheduler_*/*.accepted_checkpoint.json'))+list((ROOT/'raw/runtime_tools').glob('serial_scheduler_*/*.accepted_checkpoint.json')):
  item=read(p)['item'];accepted[item['segment_id']]=item
 for seg,item in sorted(accepted.items()):
  if (OUT/(seg+'.complete.json')).exists():continue
  folder=CONTROL/'publication/checkpoint_001' if seg=='01__gqa6_pmc' else CONTROL/'publication/r08_02__gqa6_pmc_read' if seg=='02__gqa6_pmc_read' else CONTROL/'publication_emergency'/('r08_'+seg);receipt=folder/'PUBLICATION_COMPLETE.json'
  if not receipt.exists():continue
  remote=verify_remote(receipt);filemanifest=folder/'FILE_MANIFEST.json';expected={x['path']:x for x in read(filemanifest)['files']};execution=Path(item['execution_manifest']['path']);assert sha(execution)==item['execution_manifest']['sha256'] and read(execution)['all_started_processes_terminated'];raw=execution.parent;selected=[]
  for p in raw.rglob('*'):
   if not p.is_file() or p.stat().st_size<200_000_000:continue
   rel=str(p.relative_to(PROJECT))
   if rel not in expected:continue
   x=expected[rel];assert p.stat().st_size==x['size'] and sha(p)==x['sha256'];selected.append({'path':str(p),'archive_member_path':rel,'size':x['size'],'sha256':x['sha256']})
  prepared=OUT/(seg+'.prepared.json')
  if prepared.exists():record=read(prepared);assert record['accepted_item']==item;selected=record['temporarily_evicted_files']
  else:
   record={'schema_version':1,'status':'verified_ready_for_temporary_release_backing','segment_id':seg,'accepted_item':item,'original_execution_and_raw_inventory_unchanged':True,'user_authorization':'已经发布的部分可以暂时移除 因为可以随时从release恢复；全部R08采集完成后移除权重并恢复所有产物进行R08校验','remote_verification':remote,'published_file_manifest':rec(filemanifest),'temporarily_evicted_files':selected,'original_data_restoration_required_before_R08_final_validation':True,'weight_deletion_performed':False,'NFS_metadata_and_logs_retained':True};save(prepared,record)
  for x in selected:
   p=Path(x['path'])
   if p.exists():assert p.is_file() and sha(p)==x['sha256'];p.unlink();print('PUBLISHED_RAW_LOCAL_COPY_EVICTED',seg,p.name,x['size'],flush=True)
  save(OUT/(seg+'.complete.json'),{**record,'status':'complete','evicted_bytes':sum(x['size'] for x in selected),'prepared_record':rec(prepared),'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()});print('RELEASE_BACKING_CHECKPOINT_COMPLETE',seg,sum(x['size'] for x in selected),flush=True)
def main():
 while time.time()<DEADLINE:
  try:checkpoint()
  except Exception as error:print('RELEASE_OFFLOAD_RETRY_REQUIRED',type(error).__name__,str(error) if isinstance(error,AssertionError) else '',flush=True)
  if (CONTROL/'STOP_RELEASE_OFFLOAD_WATCHDOG').exists():return
  time.sleep(30)
if __name__=='__main__':main()
