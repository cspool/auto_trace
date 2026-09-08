"""Explicit source relocation and evidence primitives for the September 8 continuation."""
from pathlib import Path
import hashlib
import json
import os

PROJECT = Path('/public/home/accl15ptg7/auto_trace')
CONTROL = Path('/public/home/accl15ptg7/run_R08_R10')
OLD_PROJECT = Path('/public/home/tangyu408/Qwen_DCU_Worker_0')
RUN_ID = 'batch8-dp2-fresh-003'
BRANCH = 'workflow01-10-fresh-e2e'
RUN = PROJECT / 'perf_trace_batch8/runtime' / BRANCH / RUN_ID
SNAPSHOT = CONTROL / 'snapshot'
PROFILE_HASH = '3b4c952063f48ae662b48b5ce9d8fd76e0ac4d74e170bdb1839ae8b1aaa23cce'
TARGET_COMMIT = '2b4b2119ae3cc2c4c626dc5690ef9593c1477f66'
R07_HASH = '437e753f5dbdea8e9b0a6009ede6eebed0a61c76a26683cad6b6618f9c374b10'

def require(condition, message):
    if not condition:
        raise ValueError(message)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()

def canonical_sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def write_new(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:
        json.dump(value,f,indent=2,ensure_ascii=False,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())

def resolve_source(value, owner=None):
    p=Path(value)
    require('..' not in p.parts,'source traversal rejected')
    if p.is_relative_to(OLD_PROJECT):
        p=PROJECT/p.relative_to(OLD_PROJECT)
    elif p.is_relative_to(Path('/perf_trace_batch8_r01_r06')/RUN_ID/'expanded_artifacts'):
        p=RUN/'artifacts'/p.relative_to(Path('/perf_trace_batch8_r01_r06')/RUN_ID/'expanded_artifacts')
    elif not p.is_absolute():
        p=(Path(owner) if owner else PROJECT)/p
    require(p.is_relative_to(PROJECT),'unbound external source path: '+str(p))
    if owner is not None:
        require(p.is_relative_to(Path(owner)),'source outside declared owner: '+str(p))
    resolved=p.resolve()
    if not resolved.is_relative_to(PROJECT):
        admitted=False
        for ordinal in range(1,7):
            stage=f'R{ordinal:02d}'
            lexical=RUN/'artifacts'/stage
            bound=Path('/dev/shm/r08_continuation_predecessors/artifacts')/stage
            if p.is_relative_to(lexical):
                require(lexical.is_symlink() and os.readlink(lexical)==str(bound),'changed stage relocation binding')
                require(resolved==bound/p.relative_to(lexical),'unlisted nested symlink in predecessor')
                admitted=True
        require(admitted,'unbound source symlink escape: '+str(p))
    return p

def verify_record(record, owner=None):
    p=resolve_source(record['path'],owner)
    require(p.is_file(),'missing source: '+str(p))
    expected_size=record.get('size',record.get('size_bytes'))
    if expected_size is not None:require(p.stat().st_size==expected_size,'size mismatch: '+str(p))
    require(sha(p)==record['sha256'],'hash mismatch: '+str(p))
    return {'original_path':record['path'],'local_path':str(p),'resolved_local_path':str(p.resolve()),'size':p.stat().st_size,'sha256':record['sha256']}

def validate_recovered_status(handoff):
    require(handoff.get('status')=='complete_recovered_offline','only explicit recovered R07 admitted')
    for key in ['execution_status','evidence_status']:require(handoff.get(key)=='complete',key)
    require(handoff.get('coverage_target_met') is True,'R07 coverage')
    require(handoff.get('next_authorization_required') is False,'R07 successor authorization')
    require(handoff.get('runtime_run_id')==RUN_ID and handoff.get('lineage_id')==RUN_ID,'R07 lineage')
    require(handoff.get('runtime_branch')==BRANCH and handoff.get('runtime_goal')=='R07','R07 stage')
    require(handoff.get('trace_profile_sha256')==PROFILE_HASH,'R07 profile')
    require(handoff.get('native_controller_lifecycle_completion_claimed') is False,'native lifecycle boundary')
    require(handoff.get('native_durable_nfs_completion_claimed') is False,'native storage boundary')
    require(handoff.get('remote_original_hipprof_terminal') is False,'historical remote lifecycle must remain unchanged')
    require(handoff.get('all_local_recovery_processes_terminated') is True,'recovery process boundary')
    require(handoff.get('advance_decision',{}).get('authorized') is True,'R07 recovery advance decision')
