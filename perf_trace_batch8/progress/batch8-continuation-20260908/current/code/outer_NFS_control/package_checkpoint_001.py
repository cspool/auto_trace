from pathlib import Path
import json,hashlib,tarfile,zstandard,time
project=Path('/public/home/accl15ptg7/auto_trace');r=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');control=Path('/public/home/accl15ptg7/run_R08_R10');out=control/'publication/checkpoint_001';out.mkdir(parents=True,exist_ok=False)
files=[]
for base in [r/'raw/captures/01__gqa6_pmc/attempt_005',r/'normalized/captures/01__gqa6_pmc/attempt_005/revision_002',project/'perf_trace_batch8/continuation_20260908/predecessor_validations',project/'perf_trace_batch8/releases/batch8-continuation-checkpoint-20260908-001']:
 files += [p for p in sorted(base.rglob('*')) if p.is_file()]
for folder in ['plans','contract','authorization','tools/revision_013','tools/analysis_004']:
 files += [p for p in sorted((r/folder).rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
files=sorted(set(files));manifest=[]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
for p in files:manifest.append({'path':str(p.relative_to(project)),'size':p.stat().st_size,'sha256':sha(p)})
(out/'FILE_MANIFEST.json').write_text(json.dumps({'schema_version':1,'runtime_run_id':'batch8-dp2-fresh-003','checkpoint':'R07_CPU_complete_R08_first_capture_accepted','files':manifest,'R08_stage_complete':False,'R09_R10_started':False},indent=2)+'\n')
archive=out/'r07-cpu-r08-first-accepted-20260908.tar.zst';start=time.monotonic()
with archive.open('xb') as raw:
 with zstandard.ZstdCompressor(level=3,threads=4).stream_writer(raw) as compressed:
  with tarfile.open(fileobj=compressed,mode='w|',dereference=True) as tar:
   for p in files:tar.add(p,arcname=str(p.relative_to(project)),recursive=False)
   tar.add(out/'FILE_MANIFEST.json',arcname='PUBLICATION_FILE_MANIFEST.json',recursive=False)
print('ARCHIVE_BUILT',archive.stat().st_size,round(time.monotonic()-start,2),flush=True)
# Verify every member independently through the compressed stream.
expected={x['path']:x for x in manifest};seen=set()
with archive.open('rb') as raw:
 with zstandard.ZstdDecompressor().stream_reader(raw) as stream:
  with tarfile.open(fileobj=stream,mode='r|') as tar:
   for m in tar:
    if m.name=='PUBLICATION_FILE_MANIFEST.json':continue
    assert m.isfile() and m.name in expected and m.name not in seen
    f=tar.extractfile(m);h=hashlib.sha256()
    for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    assert m.size==expected[m.name]['size'] and h.hexdigest()==expected[m.name]['sha256'];seen.add(m.name)
assert seen==set(expected)
assets=[{'name':p.name,'path':str(p),'size':p.stat().st_size,'sha256':sha(p)} for p in [archive,out/'FILE_MANIFEST.json']]
(out/'ASSET_MANIFEST.json').write_text(json.dumps({'status':'verified_ready_for_release','member_count':len(seen),'member_bytes':sum(x['size'] for x in manifest),'assets':assets},indent=2)+'\n')
(out/'SHA256SUMS').write_text(''.join(x['sha256']+'  '+x['name']+'\n' for x in assets))
print('RELEASE_PACKAGE_VERIFIED',len(seen),flush=True)
