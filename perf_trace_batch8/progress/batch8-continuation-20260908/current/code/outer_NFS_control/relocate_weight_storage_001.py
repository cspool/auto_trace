from pathlib import Path
import hashlib,json,shutil,os,time
source=Path('/root/Qwen3.5-27B');destination=Path('/public/home/accl15ptg7/Qwen3.5-27B-verified-backing-20260908');destination.mkdir(exist_ok=False)
control=Path('/public/home/accl15ptg7/run_R08_R10');records=[]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(16<<20),b''):h.update(b)
 return h.hexdigest()
for p in sorted(source.glob('*.safetensors')):
 assert p.is_file() and not p.is_symlink()
 q=destination/p.name;before=sha(p);shutil.copyfile(p,q);after=sha(q);assert before==after
 # Both byte-verified files coexist until an atomic logical path switch.
 link=p.with_name(p.name+'.storage-link-001');link.symlink_to(q);os.replace(link,p)
 assert p.resolve()==q and p.stat().st_size==q.stat().st_size
 rec={'logical_path':str(p),'backing_path':str(q),'size':q.stat().st_size,'sha256':before,'source_and_destination_rehashed_before_switch':True};records.append(rec)
 with (control/('weight_storage_checkpoint_'+p.stem+'.json')).open('x') as f:json.dump(rec,f,indent=2)
 print('WEIGHT_STORAGE_VERIFIED',p.name,q.stat().st_size,'root_free',shutil.disk_usage('/root').free,flush=True)
with (control/'WEIGHT_STORAGE_RELOCATION_COMPLETE.json').open('x') as f:json.dump({'status':'complete','reason':'shared root filesystem exhaustion; logical root model path and all bytes unchanged','original_download_and_SHA_verification_complete':True,'root_model_path':str(source),'backing_root':str(destination),'files':records},f,indent=2)
