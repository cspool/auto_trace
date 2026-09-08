"""Remove only the exact already-published first Release upload archive."""
from pathlib import Path
import importlib.util,json,os
C=Path('/public/home/accl15ptg7/run_R08_R10')
spec=importlib.util.spec_from_file_location('verified_offloader',C/'offload_published_R08_files_001.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
folder=C/'publication/checkpoint_001';complete=folder/'UPLOAD_CACHE_REMOVAL_COMPLETE.json'
if complete.exists():print('ALREADY_COMPLETE',flush=True);raise SystemExit(0)
remote=m.verify_remote(folder/'PUBLICATION_COMPLETE.json');assets=m.read(folder/'ASSET_MANIFEST.json')['assets'];expected=next(x for x in assets if x['name']=='r07-cpu-r08-first-accepted-20260908.tar.zst');path=Path(expected['path']);assert path.parent==folder
actual=next(x for x in remote['assets'] if x['name']==expected['name']);assert actual['size']==expected['size'] and actual['digest']=='sha256:'+expected['sha256']
prepared=folder/'UPLOAD_CACHE_REMOVAL_PREPARED.json'
if prepared.exists():assert m.read(prepared)['removed_upload_cache']==expected
else:
 assert path.is_file() and path.stat().st_size==expected['size'] and m.sha(path)==expected['sha256']
 m.save(prepared,{'status':'verified_before_removal','removed_upload_cache':expected,'remote_verification':remote,'archive_is_upload_cache_only':True,'all_manifests_and_receipts_remain_NFS':True,'raw_artifact_restoration_uses_existing_independent_offload_receipts':True,'user_policy':m.rec(C/'USER_RELEASE_OFFLOAD_POLICY_20260908.json')})
if path.exists():assert path.stat().st_size==expected['size'] and m.sha(path)==expected['sha256'];path.unlink()
m.save(complete,{'status':'complete','removed_bytes':expected['size'],'prepared':m.rec(prepared),'remote_verification':remote,'no_weight_or_live_capture_changes':True})
print('VERIFIED_RELEASE_UPLOAD_CACHE_REMOVED',expected['size'],flush=True)
