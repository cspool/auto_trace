"""Freeze path-only NFS continuation revision after all current files are verified."""
from pathlib import Path
import json,hashlib,os,shutil,re,time
CONTROL=Path('/public/home/accl15ptg7/run_R08_R10');ROOT=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001');PROOF=CONTROL/'storage_policy_correction_001/COMPLETE.json';BACKING=Path('/public/home/accl15ptg7/r08_continuation_001_NFS_bulk')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':sha(p)}
def save(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def main():
 proof=json.loads(PROOF.read_text());assert proof['status']=='complete' and proof['R08_all_current_data_outputs_logs_physical_NFS'];nfs_device=os.stat(CONTROL).st_dev;assert nfs_device!=os.stat('/root').st_dev and os.stat(BACKING).st_dev==nfs_device
 original=ROOT/'authorization/bulk_storage_authorization.json';old=json.loads(original.read_text());authpath=ROOT/'authorization/NFS_output_storage_authorization_001.json';auth={'schema_version':1,'status':'complete','runtime_run_id':'batch8-dp2-fresh-003','runtime_goal':'R08','user_instruction':rec(CONTROL/'USER_STORAGE_POLICY_20260908.json'),'original_root_bulk_authorization':rec(original),'migration_proof':rec(PROOF),'file_manifest':rec(CONTROL/'storage_policy_correction_001/r08_bulk.FILES.json'),'physical_NFS_root':str(BACKING),'NFS_filesystem_device':nfs_device,'original_directory_alias':{'path':'/root/r08_continuation_001_bulk','destination':str(BACKING)},'paths':{str(ROOT/key):str(BACKING/key) for key in ['raw','normalized','model']},'original_logical_bulk_links':old['paths'],'all_new_R08_outputs_and_logs_must_be_physical_NFS':True,'weights_physical_root_must_remain_unchanged':True};save(authpath,auth)
 oldtools=ROOT/'raw/runtime_tools/revision_015';tools=ROOT/'raw/runtime_tools/revision_016';shutil.copytree(oldtools,tools,ignore=shutil.ignore_patterns('__pycache__'))
 native=tools/'r08_native.py';s=native.read_text();b=s.index('def output_path(');e=s.index('def r02_bindings(',b)
 new='''def output_path(value,create_parent=False):
    p=Path(value)
    require(p.is_absolute() and '..' not in p.parts and p.is_relative_to(ROOT),'output lexical containment')
    authpath=ROOT/'authorization/NFS_output_storage_authorization_001.json';authorization=read(authpath)
    require(authorization['status']=='complete' and sha(authorization['original_root_bulk_authorization']['path'])==authorization['original_root_bulk_authorization']['sha256'],'explicit NFS override preserves original authorization')
    require(sha(authorization['migration_proof']['path'])==authorization['migration_proof']['sha256'],'complete verified NFS migration')
    alias=authorization['original_directory_alias'];require(Path(alias['path']).is_symlink() and os.readlink(alias['path'])==alias['destination'],'exact root alias to physical NFS')
    resolved=p.resolve(strict=False);bound=False
    for lexical,destination in authorization['paths'].items():
        lexical=Path(lexical);destination=Path(destination)
        if p.is_relative_to(lexical):
            require(lexical.is_symlink() and os.readlink(lexical)==authorization['original_logical_bulk_links'][str(lexical)],'original canonical bulk link retained')
            require(resolved==destination/p.relative_to(lexical),'no unlisted nested output link')
            require(destination.stat().st_dev==authorization['NFS_filesystem_device'],'physical NFS output device')
            bound=True
    if not bound:require(resolved==p and p.parent.stat().st_dev==authorization['NFS_filesystem_device'],'unlisted output link or non-NFS metadata')
    if create_parent:
        p.parent.mkdir(parents=True,exist_ok=True)
        require(p.resolve(strict=False)==resolved and p.parent.stat().st_dev==authorization['NFS_filesystem_device'],'post-creation physical NFS containment')
    return p

'''
 s=s[:b]+new+s[e:];native.write_text(s)
 # Short NFS paths were CPU-tested for Unix socket IPC, so temporary runtime
 # files and control sockets also remain on NFS.
 for p in tools.glob('*'):
  if p.is_file() and p.suffix in ['.sh','.py']:
   text=p.read_text().replace('/revision_015/','/revision_016/');p.write_text(text)
 runtime=tools/'run_capture.py';r=runtime.read_text().replace("tmp=Path('/tmp')/('r8-'+str(os.getpid()))","tmp=Path('/public/home/accl15ptg7/r8tmp')/('r8-'+str(os.getpid()))");runtime.write_text(r)
 analysis=ROOT/'tools/analysis_005';shutil.copytree(ROOT/'tools/analysis_004',analysis,ignore=shutil.ignore_patterns('__pycache__'))
 for p in analysis.glob('*.py'):
  s=p.read_text().replace("ROOT/'tools/revision_008'", "ROOT/'raw/runtime_tools/revision_016'").replace("ROOT/'tools/revision_011'", "ROOT/'raw/runtime_tools/revision_016'");p.write_text(s)
 for p in list(tools.glob('*.py'))+list(analysis.glob('*.py')):compile(p.read_text(),str(p),'exec')
 # Execute production path function on new nonexistent output names, without
 # model import, device access, or any new capture.
 import importlib.util
 spec=importlib.util.spec_from_file_location('r08_nfs_native_fixture',native);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 for p in [ROOT/'raw/captures/04_path_cpu_fixture/attempt_001',ROOT/'normalized/captures/03__gqa6_pmc_write/attempt_003/revision_002',ROOT/'model/resource_model_001']:assert m.output_path(p)==p
 rejected=[]
 for p in [Path('/root/forbidden_R08_output'),ROOT/'raw/../escape']:
  try:m.output_path(p)
  except ValueError:rejected.append(str(p))
  else:raise AssertionError('unsafe output accepted')
 assert len(rejected)==2
 frozen=[rec(p) for p in sorted(tools.iterdir()) if p.is_file()]+[rec(p) for p in sorted(analysis.iterdir()) if p.is_file()]
 save(ROOT/'validation/NFS_runtime_CPU_gate_001.json',{'status':'complete','runtime_revision':'revision_016','analysis_revision':'analysis_005','storage_authorization':rec(authpath),'previous_runtime_gate':rec(ROOT/'raw/runtime_tools/runtime_capture_gate_009.json'),'previous_analysis_gate':rec(ROOT/'validation/native_submission_analysis_cpu_gate.json'),'changes':'explicit NFS storage path validation and matching immutable tool binding only; prior spawn/native health/attribution/workload unchanged','model_initializations':0,'device_queries':0,'production_NFS_output_paths_validated':3,'non_NFS_and_traversal_negative_cases':rejected,'frozen_tools':frozen});print('R08_NFS_RUNTIME_CPU_GATE_COMPLETE',len(frozen),flush=True)
if __name__=='__main__':main()
