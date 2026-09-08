"""Adapt frozen same-lineage marker methods into a current R08 replay driver."""
from continuation_common import *
import shutil

def main():
    root=RUN/'artifacts/R08/continuation_001'
    tools=root/'tools/revision_002';tools.mkdir(exist_ok=False)
    latest=CONTROL/'r07_latest_tools/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R07/resume-042'
    old=CONTROL/'historical_methods/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/observed_subset_replay_001/tools'
    sources=[]
    def copy(source,dest):
        source=Path(source);dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open('xb') as f:f.write(source.read_bytes())
        sources.append({'original_path':str(source),'original_sha256':sha(source),'output_path':str(dest),'output_sha256':sha(dest),'method':'byte_exact_copy'})
    for name in ['r07_common.py','r07_marker_contract.py']:copy(latest/'tools'/name,tools/name)
    for name in ['r07_full_request_selection.json','r07_process_range_inventory.json']:copy(latest/'contract'/name,root/'contract'/name)
    copy(root/'tools/revision_001/r08_native.py',tools/'r08_native.py')
    logical=PROJECT/'perf_trace_batch8/recovery/r06_request_phase_selection_fix_004/corrected_logical_target_contract.json'
    require(sha(logical)=='fb45d3637f7af627399b99c64acd152088d76af0c4b6b494f16f215c1b25c3b6','corrected R06 logical target contract')
    selection=root/'contract/r07_full_request_selection.json'
    runtime_sources={'selection':{'path':str(selection),'sha256':sha(selection)},'inventory':{'path':str(root/'contract/r07_process_range_inventory.json'),'sha256':sha(root/'contract/r07_process_range_inventory.json')},'logical_targets':{'path':str(logical),'sha256':sha(logical)},'r01_patch':{'path':str(RUN/'artifacts/R01/tools/runtime_patch/r01_runtime_patch.py'),'sha256':'5329e3ecb54c724d259b4eeb7deccd90be447233d23b438a4cfee725e6705a48'},'r07_overlay_method':{'path':str(latest/'tools/r07_runtime_patch_loader.py'),'sha256':sha(latest/'tools/r07_runtime_patch_loader.py')}}
    write_new(root/'contract/runtime_overlay_sources.json',runtime_sources)
    original=(latest/'tools/r07_runtime_patch_loader.py').read_text()
    state=original[original.index('_logical_keys ='):original.index('def _selection_key')]
    body=original[original.index('def _selection_key'):]
    body=body.replace('"schema_version": 1,','"schema_version": 1,\n        "runtime_goal": "R08",\n        "evidence_class": "replay_projected",')
    body=body.replace('"r07_', '"r08_').replace('f"r07_', 'f"r08_').replace('R07','R08')
    header='''"""Current R08 replay overlay, preserving the exact R07 compiled boundaries.

Only current output paths, source validation, attempt identity, and replay
evidence labels differ from the source-pinned R07 marker method.
"""
from __future__ import annotations
import sys
sys.dont_write_bytecode=True
import atexit,hashlib,json,os,threading,time
from collections import Counter
from pathlib import Path
from typing import Any
from r07_common import RuntimePhaseBinder, bind_logical_targets
from r07_marker_contract import exact_forward_name,exact_request_name,roundtrip
from r08_native import ROOT, RUN, read, sha, output_path

ARTIFACT_ROOT=output_path(Path(os.environ['QWEN_DCU_R08_PASS_ROOT']))
ATTEMPT_ID=os.environ['QWEN_DCU_R08_RUNTIME_ATTEMPT_ID']
RUN_ID=LINEAGE_ID='batch8-dp2-fresh-003'
PROFILE_SHA256='3b4c952063f48ae662b48b5ce9d8fd76e0ac4d74e170bdb1839ae8b1aaa23cce'
EVENT_ROOT=ARTIFACT_ROOT/'workload/overlay_events'
BINDING_ROOT=ARTIFACT_ROOT/'workload/runtime_bindings'
WORKER_ROOT=ARTIFACT_ROOT/'control/workers'

def _require(condition,message):
    if not condition:raise RuntimeError(message)

_SOURCES=read(ROOT/'contract/runtime_overlay_sources.json')
for _name,_record in _SOURCES.items():
    _require(sha(_record['path'])==_record['sha256'],'R08 overlay source drift: '+_name)
EXPECTED_R01_PATCH=Path(_SOURCES['r01_patch']['path'])
EXPECTED_R01_PATCH_SHA256=_SOURCES['r01_patch']['sha256']
_SELECTION=read(_SOURCES['selection']['path'])
_LOGICAL_TARGETS=read(_SOURCES['logical_targets']['path'])
_require(os.environ.get('QWEN_DCU_R08_ENABLE_PROCESS_OVERLAY')=='1','R08 overlay enable')
_require(os.environ.get('HIP_VISIBLE_DEVICES')==os.environ.get('CUDA_VISIBLE_DEVICES')=='0,1','R08 DP2 visibility')
_require(_SELECTION['selector']['match_fields']==['request_id','phase','phase_occurrence'],'same R07 logical selector')
_require(_SELECTION['selector']['forbidden_match_fields']==['q_len','kv_len','forward_id'],'runtime shapes must bind after logical selection')
_require(len(_LOGICAL_TARGETS['records'])==13568,'complete logical target universe')
'''
    (tools/'r08_process_overlay.py').write_text(header+state+body)
    sources.append({'original_path':str(latest/'tools/r07_runtime_patch_loader.py'),'original_sha256':sha(latest/'tools/r07_runtime_patch_loader.py'),'output_path':str(tools/'r08_process_overlay.py'),'output_sha256':sha(tools/'r08_process_overlay.py'),'method':'Original binder/marker functions retained; replace path/attempt/header validation and label every current event replay_projected.'})
    gate=(old/'r08_pmc_gate.py').read_text()
    gate=gate.replace('        profiler_transition = _hip_call("hipProfilerStop")\n        _stopped = True','        from r08_process_overlay import _write_summary\n        _write_summary()\n        profiler_transition = _hip_call("hipProfilerStop")\n        _stopped = True')
    (tools/'r08_pmc_gate.py').write_text(gate)
    workload=(old/'r08_workload_driver.py').read_text().replace('51c456166035a03f65cec6147c24cb228757402d1b59b555c50ac5baae58a093',sha(selection))
    (tools/'r08_workload_driver.py').write_text(workload)
    for name in ['r08_pmc_gate.py','r08_workload_driver.py']:
        sources.append({'original_path':str(old/name),'original_sha256':sha(old/name),'output_path':str(tools/name),'output_sha256':sha(tools/name),'method':'Current R07 selection hash; persist current process-overlay summary before profiler stop.'})
    for p in tools.glob('*.py'):compile(p.read_text(),str(p),'exec')
    write_new(root/'contract/runtime_method_adaptation.json',{'status':'prepared_pending_frozen_runtime_gate','sources':sources,'historical_measurements_reused':False,'selected_request_bytes_changed':False,'target_source_changed':False})
    print('R08_RUNTIME_METHODS_PREPARED',len(sources),flush=True)

if __name__=='__main__':main()
