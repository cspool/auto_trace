#!/usr/bin/env python3
"""Restore hash-verified R08 normalized dispatches without running a profiler."""
from pathlib import Path
import argparse,json,hashlib,subprocess,concurrent.futures,io,tarfile,shutil
import zstandard

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def main(root,repo):
 dest=root/'batch8_bandwidth';downloads=dest/'downloads';downloads.mkdir(parents=True,exist_ok=True)
 source=repo/'perf_trace_batch8/continuation_20260908/R08_full_stage_publication_001'
 manifest=json.loads((source/'FILE_MANIFEST.json').read_text());assets=json.loads((source/'ASSET_MANIFEST.json').read_text())['assets'];parts=[a for a in assets if '.part' in a['name']]
 url='https://github.com/cspool/auto_trace/releases/download/perf-trace-batch8-r08-complete-20260908/'
 def download(a):
  p=downloads/a['name']
  if not(p.is_file() and p.stat().st_size==a['size'] and sha(p)==a['sha256']):
   tmp=p.with_name(p.name+'.partial');subprocess.run(['curl','-fL','--retry','5','--connect-timeout','30','-sS','-o',str(tmp),url+a['name']],check=True)
   assert tmp.stat().st_size==a['size'] and sha(tmp)==a['sha256'],a['name'];tmp.replace(p)
  print('VERIFIED',a['name'],a['size'],flush=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(download,parts))
 # These small normalized files retain complete counters, source identities and
 # same-row GPU timestamps. Large raw DBs remain archived and are not expanded.
 selected={r['path']:r for r in manifest['files'] if '/normalized/captures/' in r['path'] and Path(r['path']).name in ['dispatch_attributes.jsonl','NORMALIZATION_COMPLETE.json','INDEPENDENT_AUDIT.json']}
 print('RESTORING',len(selected),'normalized evidence files',flush=True)
 class Parts(io.RawIOBase):
  def __init__(self):self.index=0;self.f=(downloads/parts[0]['name']).open('rb')
  def readable(self):return True
  def readinto(self,buf):
   while self.f:
    n=self.f.readinto(buf)
    if n:return n
    self.f.close();self.index+=1;self.f=(downloads/parts[self.index]['name']).open('rb') if self.index<len(parts) else None
   return 0
 restored=[]
 with io.BufferedReader(Parts(),buffer_size=8<<20) as chunks,zstandard.ZstdDecompressor().stream_reader(chunks) as stream,tarfile.open(fileobj=stream,mode='r|') as archive:
  for member in archive:
   name=member.name.removeprefix('./')
   if name not in selected:continue
   r=selected[name];assert member.isfile() and member.size==r['size']
   p=dest/'restored'/name;p.parent.mkdir(parents=True,exist_ok=True)
   with archive.extractfile(member) as src,p.open('wb') as out:shutil.copyfileobj(src,out,8<<20)
   assert sha(p)==r['sha256'],name
   restored.append(dict(r,local_path=str(p.resolve())));print('RESTORED',name.split('/normalized/')[1],flush=True)
 assert {r['path'] for r in restored}==set(selected)
 (dest/'RESTORE_MANIFEST.json').write_text(json.dumps(dict(status='verified',source_release=url,archive_parts=parts,restored=restored),indent=2)+'\n')
 print('RESTORE COMPLETE',len(restored),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--repo',type=Path,required=True);a=p.parse_args();main(a.root.resolve(),a.repo.resolve())
