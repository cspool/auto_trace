"""Checkpoint verified Release and authorized local eviction receipts to main."""
from pathlib import Path
import json,hashlib,sys,datetime
C=Path('/public/home/accl15ptg7/run_R08_R10');P=Path('/public/home/accl15ptg7/auto_trace');R=P/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001';D=P/'perf_trace_batch8/continuation_20260908'
def read(p):return json.loads(p.read_text())
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
seg=sys.argv[1];folder=C/'publication/checkpoint_001' if seg=='01__gqa6_pmc' else C/'publication/r08_02__gqa6_pmc_read' if seg=='02__gqa6_pmc_read' else C/'publication_emergency'/('r08_'+seg)
pub=read(folder/'PUBLICATION_COMPLETE.json');assert pub['status']=='published' and pub['all_server_asset_sha256_match'];o=R/'raw/runtime_tools/remote_release_offloads_001';ev=read(o/(seg+'.complete.json'));assert ev['status']=='complete' and ev['segment_id']==seg
assert rec(Path(ev['published_file_manifest']['path']))==ev['published_file_manifest']
sources=[folder/n for n in ['FILE_MANIFEST.json','PUBLICATION_COMPLETE.json','ASSET_MANIFEST.json','SHA256SUMS','LOCAL_UPLOAD_CACHE_CLEANUP.json']]+[o/(seg+'.prepared.json'),o/(seg+'.complete.json')]
out=D/('capture'+seg[:2]+'_publication_and_eviction_001');out.mkdir(exist_ok=False);records=[]
for p in sources:
 assert p.stat().st_size<10_000_000;records.append(rec(p));(out/p.name).write_bytes(p.read_bytes())
(out/'SOURCE_RECORDS.json').write_text(json.dumps(records,indent=2)+'\n')
(D/'RECOVERY_STATE_NFS.json').write_bytes((C/'RECOVERY_STATE_NFS.json').read_bytes())
with (D/'LIVE_PROGRESS.md').open('a') as f:f.write('\n- '+datetime.datetime.now(datetime.timezone.utc).isoformat()+': '+seg+' Release published with server asset size/SHA256 verified: '+pub['url']+'. Authorized local large-file eviction completed for '+str(ev['evicted_bytes'])+' bytes. Original member manifests and restoration receipts retained on NFS and checkpointed here.\n')
(D/'outer_helpers_001'/Path(__file__).name).write_bytes(Path(__file__).read_bytes());print(json.dumps({'checkpoint_directory':str(out),'release':pub['url'],'evicted_bytes':ev['evicted_bytes']}))
