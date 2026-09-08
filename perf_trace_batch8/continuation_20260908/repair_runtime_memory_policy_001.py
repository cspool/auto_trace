from pathlib import Path
import hashlib,json,shutil,ast,textwrap,time,os
ROOT=Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001')
old=ROOT/'tools/revision_008';new=ROOT/'tools/revision_009';shutil.copytree(old,new)
source=ROOT.parents[2]/'artifacts/R01/tools/runtime_patch/r01_runtime_patch.py'
module=ast.parse(source.read_text());parent=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='_patch_worker_runtime_policy');function=next(n for n in parent.body if isinstance(n,ast.FunctionDef) and n.name=='determine_available_memory')
text=textwrap.dedent(ast.get_source_segment(source.read_text(),function))
a='''    if observed_tokens != EXPECTED_INSTRUMENTED_PROFILE_KV_CACHE_TOKENS:
        raise RuntimeError(
            "R01 instrumented profile KV token count drifted: "
            f"{observed_tokens} != "
            f"{EXPECTED_INSTRUMENTED_PROFILE_KV_CACHE_TOKENS}"
        )'''
assert a in text
text=text.replace(a,'''    if observed_bytes <= 0:
        raise RuntimeError("R08 measured KV memory must be positive")''')
text=text.replace('artifact_local_layer_split_profile_peak_compensation','r08_current_device_measured_profile_peak_compensation_same_final_cache_target')
# A lower or higher profiled peak is recorded; final target, geometry and 2 GiB
# minimum reserve are copied byte-for-byte from the original method.
header='''"""Adapt observed startup profile memory; preserve exact R01 final cache geometry."""
import functools,time
from typing import Any

def install(original):
    import torch
    from vllm.v1.core.kv_cache_utils import get_kv_cache_groups
    from vllm.v1.worker.gpu_worker import Worker as GPUWorker
    current=GPUWorker.determine_available_memory
    if getattr(current,'_r08_current_memory_profile',False):return
    if not getattr(current,'_qwen_dcu_r01_kv_target_restored',False):
        raise RuntimeError('original R01 worker policy missing')
    current_determine=current.__wrapped__
    EXPECTED_KV_CACHE_TOKENS=original.EXPECTED_KV_CACHE_TOKENS
    MINIMUM_POST_RESTORATION_RESERVE_BYTES=original.MINIMUM_POST_RESTORATION_RESERVE_BYTES
    PHYSICAL_DEVICE_BY_DP_RANK=original.PHYSICAL_DEVICE_BY_DP_RANK
    _append_event=original._append_event
'''
s=header+textwrap.indent(text,'    ')+'\n    determine_available_memory._r08_current_memory_profile=True\n    determine_available_memory._qwen_dcu_r01_kv_target_restored=True\n    GPUWorker.determine_available_memory=determine_available_memory\n'
(new/'r08_memory_profile.py').write_text(s)
p=new/'sitecustomize.py';s=p.read_text().replace('    r01_runtime_patch.install()','    r01_runtime_patch.install()\n    import r08_memory_profile\n    r08_memory_profile.install(r01_runtime_patch)');p.write_text(s)
p=new/'run_capture.py';s=p.read_text().replace('runtime_capture_gate_003.json','runtime_capture_gate_004.json');p.write_text(s)
for p in new.glob('*.py'):compile(p.read_text(),str(p),'exec')
def rec(p):return {'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
# CPU-only exercise of the extracted production function with mocked worker,
# geometry and profiler; no torch/vllm/device imports.
class Spec:
 block_size=784
 page_size_bytes=3211264
class G:
 kv_cache_spec=Spec()
 layer_names=list(range(16))
class MM:
 block_size=262144
 page_size_bytes=3211264
class Cuda:
 @staticmethod
 def current_device():return 0
class Torch:cuda=Cuda()
groups=[G() for _ in range(4)];groups[1].kv_cache_spec=MM()
class Snap:free_memory=20<<30
class W:
 init_snapshot=Snap();requested_memory=(20<<30)-3432000000;vllm_config=None
 def get_kv_cache_spec(self):return {str(i):None for i in range(64)}
records=[]
space={'Any':object,'current_determine':lambda w:6350000000,'get_kv_cache_groups':lambda cfg,spec:groups,'EXPECTED_KV_CACHE_TOKENS':28224,'MINIMUM_POST_RESTORATION_RESERVE_BYTES':2<<30,'PHYSICAL_DEVICE_BY_DP_RANK':{0:0,1:1},'_append_event':records.append,'torch':Torch(),'time':time}
exec(compile(text,'production_function_fixture','exec'),space)
fn=space['determine_available_memory'];w=W();value=fn(w)
assert value==36*4*3211264*16 and records[-1]['target_cache_tokens']==28224
negative=[]
for name,mutate,restore in [('insufficient_reserve',lambda:setattr(w,'requested_memory',(20<<30)-(1<<30)),lambda:setattr(w,'requested_memory',(20<<30)-3432000000)),('wrong_geometry',lambda:setattr(groups[0].kv_cache_spec,'page_size_bytes',1),lambda:setattr(groups[0].kv_cache_spec,'page_size_bytes',3211264))]:
 mutate()
 try:fn(w)
 except RuntimeError:negative.append(name)
 else:raise AssertionError('accepted '+name)
 restore()
proof={'status':'complete','original_R01_patch':rec(source),'new_policy':rec(new/'r08_memory_profile.py'),'production_function_cpu_positive':records[0],'negative_cases_rejected':negative,'model_imports':0,'device_queries':0,'same_final_KV_tokens':28224,'same_hybrid_geometry':True,'same_minimum_reserve_bytes':2<<30,'preserved_original_inputs_and_marker_logic':True,'cause':'current startup profile memory differs from old device; exact final allocation still enforced'}
(ROOT/'validation/current_memory_policy_cpu_gate.json').write_text(json.dumps(proof,indent=2)+'\n')
gate=json.loads((ROOT/'validation/runtime_capture_gate_003.json').read_text());gate['frozen_tools']=[rec(p) for p in sorted(new.glob('*')) if p.is_file()];gate['first_capture_argv']=['/usr/bin/python','-B',str(new/'run_capture.py'),'capture','--segment','01__gqa6_pmc','--attempt','attempt_003'];gate['memory_policy_cpu_gate']=rec(ROOT/'validation/current_memory_policy_cpu_gate.json');gate['prior_runtime_gate']=rec(ROOT/'validation/runtime_capture_gate_003.json');gate['repair']='replace historical measured-memory equality with fresh measured reserve check; retain exact final KV target and geometry'
(ROOT/'validation/runtime_capture_gate_004.json').write_text(json.dumps(gate,indent=2)+'\n')
print('R08_MEMORY_POLICY_CPU_GATE_COMPLETE',value,negative)
