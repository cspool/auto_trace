#!/usr/bin/env python3
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
