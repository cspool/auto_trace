"""Bind the current R08 service to pinned source, rebuilt ABI, and replay markers."""
import os
import sys
from pathlib import Path

sys.dont_write_bytecode=True
if os.environ.get('QWEN_DCU_R08_ENABLE_PROCESS_OVERLAY')=='1':
    from r08_native import ROOT,TARGET,RUN,sha,read,require
    for key in ['HIPPROF_INPUT_FILE','HIPPROF_TMP_OUTPUT_DIR']:
        require(bool(os.environ.get(key)),'live HIPProf exec environment missing: '+key)
    require(os.environ['QWEN_DCU_R01_TARGET_ROOT']==str(TARGET),'pinned source root')
    abi=Path('/usr/local/lib/python3.10/dist-packages/vllm')
    patch=RUN/'artifacts/R01/tools/runtime_patch'
    require(sha(patch/'r01_runtime_patch.py')=='5329e3ecb54c724d259b4eeb7deccd90be447233d23b438a4cfee725e6705a48','original compiled boundary patch')
    for index,entry in enumerate([str(TARGET),str(Path(__file__).parent),str(patch)]):
        if entry in sys.path:sys.path.remove(entry)
        sys.path.insert(index,entry)
    import importlib.util
    spec=importlib.util.spec_from_file_location('vllm',TARGET/'vllm/__init__.py',submodule_search_locations=[str(TARGET/'vllm'),'/usr/local/lib/python3.10/dist-packages/vllm'])
    vllm=importlib.util.module_from_spec(spec)
    sys.modules['vllm']=vllm
    spec.loader.exec_module(vllm)
    require(Path(vllm.__file__).resolve().is_relative_to(TARGET),'vLLM Python source origin')
    if str(abi) not in vllm.__path__:vllm.__path__.append(str(abi))
    import r01_runtime_patch
    import r08_process_overlay
    import r08_pmc_gate
    r01_runtime_patch.install()
    import r08_memory_profile
    r08_memory_profile.install(r01_runtime_patch)
    r08_process_overlay.install(r01_runtime_patch)
    r08_pmc_gate.install(r01_runtime_patch)
    import r08_admission_order
    r08_admission_order.install()
    import torch
    import vllm._C
    import vllm._rocm_C
    require(hasattr(torch.ops._C,'silu_and_mul'),'required compiled runtime operator')
    for module in [vllm._C,vllm._rocm_C]:require(Path(module.__file__).resolve().is_relative_to(abi),'ABI module source')
    os.environ['QWEN_DCU_R08_SITECUSTOMIZE_READY']='1'
