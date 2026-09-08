import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import time
import zstandard

C=Path('/public/home/accl15ptg7/run_R08_R10')
P=Path('/public/home/accl15ptg7/auto_trace')
manifest=json.loads((P/'perf_trace_batch8/releases/batch8-r07-local-artifacts-20260907/FILE_MANIFEST.json').read_text())
supplement=manifest['supplement']
parts=[C/'downloads'/supplement['release']/a['asset'] for a in supplement['parts']]
while not all(p.exists() for p in parts):
    print(time.strftime('%H:%M:%S',time.gmtime()),'AWAITING_PARTS',sum(p.exists() for p in parts),len(parts),flush=True)
    time.sleep(30)
stream=hashlib.sha256()
for p,a in zip(parts,supplement['parts']):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(16*1024*1024),b''):h.update(b);stream.update(b)
    assert p.stat().st_size==a['size'] and h.hexdigest()==a['sha256']
assert stream.hexdigest()==supplement['sha256']
selected={f['path']:f for f in manifest['files'] if '/R07/resume-042/' in f['path'] and ('/tools/' in f['path'] or '/contract/' in f['path']) and f['coverage']['type']!='existing_release'}
print('STREAM_VERIFIED',len(selected),'selected tools/contracts',flush=True)
dest=C/'r07_latest_tools'
dest.mkdir(exist_ok=False)
proc=subprocess.Popen(['cat',*map(str,parts)],stdout=subprocess.PIPE)
found=[]
try:
    with zstandard.ZstdDecompressor().stream_reader(proc.stdout) as reader,tarfile.open(fileobj=reader,mode='r|') as archive:
        for m in archive:
            name=m.name.removeprefix('./')
            if name not in selected:continue
            a=selected[name]
            assert m.isfile() and m.size==a['size'] and '..' not in Path(name).parts and not Path(name).is_absolute()
            data=archive.extractfile(m).read()
            assert hashlib.sha256(data).hexdigest()==a['sha256'],name
            out=dest/name;out.parent.mkdir(parents=True,exist_ok=True)
            with out.open('xb') as f:f.write(data)
            out.chmod(m.mode&0o777)
            found.append({'path':str(out),'source_member':name,'size':len(data),'sha256':a['sha256']})
            print('EXTRACTED_VERIFIED',name,len(data),flush=True)
    assert proc.wait()==0
finally:
    if proc.poll() is None:proc.terminate();proc.wait()
assert len(found)==len(selected),(len(found),len(selected))
with (C/'r07_tools_restore_manifest.json').open('x') as f:json.dump({'status':'complete','stream_sha256':stream.hexdigest(),'entries':found},f,indent=2);f.write('\n')
print('R07_TOOLS_RESTORED_VERIFIED',len(found),flush=True)
