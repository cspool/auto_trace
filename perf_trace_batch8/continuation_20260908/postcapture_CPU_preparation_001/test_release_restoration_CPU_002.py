from pathlib import Path
import importlib.util,json,tarfile,zstandard,io,hashlib
C=Path('/public/home/accl15ptg7/run_R08_R10');spec=importlib.util.spec_from_file_location('restore_production',C/'restore_all_R08_release_artifacts_001.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
f=C/'release_restore_CPU_fixture_002';f.mkdir();m.C=f;m.P=f/'project';m.R=m.P/'R08';m.O=m.R/'raw/runtime_tools/release_restoration_001';m.O.mkdir(parents=True);m.DEST=f/'synthetic_root_destination';seg='CPU_fixture';source=m.R/'raw/captures'/seg/'attempt_001/capture.db';source.parent.mkdir(parents=True);member=str(source.relative_to(m.P));data=b'CPU_FIXTURE_ONLY\x00'+bytes(range(256))*10000;digest=hashlib.sha256(data).hexdigest();out=f/'release_restore_downloads_001'/seg;out.mkdir(parents=True);archive=out/'fixture.tar.zst';manifest=out/'FILE_MANIFEST.json';m.save(manifest,{'files':[{'path':member,'size':len(data),'sha256':digest}]})
with archive.open('wb') as f1:
 with zstandard.ZstdCompressor().stream_writer(f1) as z:
  with tarfile.open(fileobj=z,mode='w|') as t:
   info=tarfile.TarInfo(member);info.size=len(data);t.addfile(info,io.BytesIO(data))
offload={'segment_id':seg,'published_file_manifest':m.rec(manifest),'temporarily_evicted_files':[{'path':str(source),'archive_member_path':member,'size':len(data),'sha256':digest}],'remote_verification':{'assets':[{'name':archive.name,'size':archive.stat().st_size,'digest':'sha256:'+m.sha(archive),'url':'https://invalid.example/never-used'}]}}
m.save(m.R/'raw/runtime_tools/remote_release_offloads_001'/(seg+'.complete.json'),offload)
x=m.restore_segment(offload);assert x['status']=='complete' and m.sha(source)==digest and source.is_symlink();assert not archive.exists();assert m.restore_segment(offload)==x
# Simulate losing the root backing while immutable NFS receipts survive.
receipt_path=m.O/(seg+'.complete.json');receipt_sha=m.sha(receipt_path);source.resolve().unlink()
with archive.open('wb') as f1:
 with zstandard.ZstdCompressor().stream_writer(f1) as z:
  with tarfile.open(fileobj=z,mode='w|') as t:
   info=tarfile.TarInfo(member);info.size=len(data);t.addfile(info,io.BytesIO(data))
assert m.restore_segment(offload)==x and m.sha(source)==digest and m.sha(receipt_path)==receipt_sha
try:m.verify({'path':str(source),'size':len(data),'sha256':'0'*64})
except AssertionError:pass
else:raise AssertionError('corrupt hash accepted')
m.save(C/'RELEASE_RESTORATION_CPU_GATE_002.json',{'status':'complete','production_restore_source':m.rec(C/'restore_all_R08_release_artifacts_001.py'),'exact_binary_member_roundtrip':True,'canonical_symlink_binding':True,'completed_restart_idempotent':True,'wrong_SHA256_rejected':True,'root_backing_loss_restored_without_rewriting_immutable_receipt':True,'native_device_calls':0,'network_calls':0,'actual_weights_removed':False,'actual_R08_capture_files_restored':False});print('RELEASE_RESTORATION_CPU_GATE_COMPLETE')
