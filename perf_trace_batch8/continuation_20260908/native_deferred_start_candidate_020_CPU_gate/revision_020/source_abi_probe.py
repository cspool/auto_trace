"""Separate current source/ABI/device capability checkpoint; no model weights loaded."""
import os
import sys
from pathlib import Path
from r08_native import *

gate=read(ROOT/'validation/runtime_capture_gate_003.json')
require(gate['status']=='complete','CPU runtime gate before target import')
for r in gate['frozen_tools']:require(sha(r['path'])==r['sha256'],'frozen runtime helper')
if str(TARGET) in sys.path:sys.path.remove(str(TARGET))
sys.path.insert(0,str(TARGET))
import importlib.util
spec=importlib.util.spec_from_file_location('vllm',TARGET/'vllm/__init__.py',submodule_search_locations=[str(TARGET/'vllm'),'/usr/local/lib/python3.10/dist-packages/vllm'])
vllm=importlib.util.module_from_spec(spec)
sys.modules['vllm']=vllm
spec.loader.exec_module(vllm)
require(Path(vllm.__file__).resolve().is_relative_to(TARGET),'pinned Python module origin')
abi=Path('/usr/local/lib/python3.10/dist-packages/vllm')
vllm.__path__.append(str(abi))
import torch
import vllm._C
import vllm._rocm_C
require(hasattr(torch.ops._C,'silu_and_mul'),'required runtime operator registered')
require(torch.cuda.device_count()==2,'two current HIP devices')
devices=[]
for rank in [0,1]:
    properties=torch.cuda.get_device_properties(rank)
    require('gfx936' in properties.gcnArchName,'current GPU architecture')
    devices.append({'dp_rank':rank,'native_device':rank,'name':properties.name,'architecture':properties.gcnArchName,'total_memory':properties.total_memory,'compute_units':properties.multi_processor_count})
save(ROOT/'preflight/source_abi_probe_002.json',{'status':'complete','pinned_python_module':source_record(vllm.__file__),'extensions':[source_record(vllm._C.__file__),source_record(vllm._rocm_C.__file__)],'torch_version':torch.__version__,'hip_version':torch.version.hip,'devices':devices,'required_runtime_operator_registered':True,'model_initializations':0,'weights_loaded':False,'cpu_gate':source_record(ROOT/'validation/runtime_capture_gate_003.json')})
print('CURRENT_SOURCE_ABI_PROBE_COMPLETE',devices,flush=True)
