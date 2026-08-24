
import torch
from math import inf
from math import nan
NoneType = type(None)
import torch
from torch import device
import torch.fx._pytree as fx_pytree
import torch.utils._pytree as pytree

from torch.nn import *
class FxLayerGraphModule(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self._param_constant0 = torch.nn.Parameter(torch.empty([5120], dtype=torch.bfloat16))
        self._param_constant1 = torch.nn.Parameter(torch.empty([16384, 5120], dtype=torch.bfloat16))
        self._param_constant2 = torch.nn.Parameter(torch.empty([96, 5120], dtype=torch.bfloat16))
        self._param_constant3 = torch.nn.Parameter(torch.empty([128], dtype=torch.bfloat16))
        self._param_constant4 = torch.nn.Parameter(torch.empty([5120, 6144], dtype=torch.bfloat16))
        self._param_constant5 = torch.nn.Parameter(torch.empty([5120], dtype=torch.bfloat16))
        self._param_constant6 = torch.nn.Parameter(torch.empty([34816, 5120], dtype=torch.bfloat16))
        self._param_constant7 = torch.nn.Parameter(torch.empty([5120, 17408], dtype=torch.bfloat16))
        self.load_state_dict(torch.load(r'/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/fx/traces/20260729T050800Z-fx-89687ae2-R032-qwen35-27b-eager-row0-hcu0/input7_layer0/fx_graph_module/state_dict.pt'))

    
    
    def forward(self, arg0_1, arg1_1, arg2_1):
        _param_constant0 = self._param_constant0
        detach = torch.ops.aten.detach.default(_param_constant0);  _param_constant0 = None
        _to_copy = torch.ops.aten._to_copy.default(arg1_1, dtype = torch.float32)
        pow_1 = torch.ops.aten.pow.Tensor_Scalar(_to_copy, 2)
        mean = torch.ops.aten.mean.dim(pow_1, [-1], True);  pow_1 = None
        add = torch.ops.aten.add.Tensor(mean, 1e-06);  mean = None
        rsqrt = torch.ops.aten.rsqrt.default(add);  add = None
        mul = torch.ops.aten.mul.Tensor(_to_copy, rsqrt);  _to_copy = rsqrt = None
        _to_copy_1 = torch.ops.aten._to_copy.default(detach, dtype = torch.float32);  detach = None
        add_1 = torch.ops.aten.add.Tensor(_to_copy_1, 1.0);  _to_copy_1 = None
        mul_1 = torch.ops.aten.mul.Tensor(mul, add_1);  mul = add_1 = None
        _to_copy_2 = torch.ops.aten._to_copy.default(mul_1, dtype = torch.bfloat16);  mul_1 = None
        empty_like = torch.ops.aten.empty_like.default(_to_copy_2, pin_memory = False)
        _param_constant1 = self._param_constant1
        t = torch.ops.aten.t.default(_param_constant1);  _param_constant1 = None
        mm = torch.ops.aten.mm.default(_to_copy_2, t);  t = None
        split_with_sizes = torch.ops.aten.split_with_sizes.default(mm, [10240, 6144], -1);  mm = None
        getitem = split_with_sizes[0]
        getitem_1 = split_with_sizes[1];  split_with_sizes = None
        view = torch.ops.aten.view.default(getitem_1, [1, -1, 128]);  getitem_1 = None
        _param_constant2 = self._param_constant2
        t_1 = torch.ops.aten.t.default(_param_constant2);  _param_constant2 = None
        mm_1 = torch.ops.aten.mm.default(_to_copy_2, t_1);  _to_copy_2 = t_1 = None
        split = torch.ops.aten.split.Tensor(mm_1, 48, -1);  mm_1 = None
        getitem_2 = split[0]
        getitem_3 = split[1];  split = None
        zeros = torch.ops.aten.zeros.default([1, 48, 128], dtype = torch.bfloat16, device = device(type='cuda', index=0), pin_memory = False)
        gdn_attention_core = torch.ops.vllm.gdn_attention_core.default(getitem, getitem_2, getitem_3, zeros, 'language_model.model.layers.0.linear_attn');  getitem = getitem_2 = getitem_3 = gdn_attention_core = None
        view_1 = torch.ops.aten.view.default(zeros, [-1, 128]);  zeros = None
        view_2 = torch.ops.aten.view.default(view, [-1, 128]);  view = None
        _to_copy_3 = torch.ops.aten._to_copy.default(view_1, dtype = torch.float32);  view_1 = None
        _param_constant3 = self._param_constant3
        _to_copy_4 = torch.ops.aten._to_copy.default(_param_constant3, dtype = torch.float32);  _param_constant3 = None
        _to_copy_5 = torch.ops.aten._to_copy.default(view_2, dtype = torch.float32);  view_2 = None
        pow_2 = torch.ops.aten.pow.Tensor_Scalar(_to_copy_3, 2)
        mean_1 = torch.ops.aten.mean.dim(pow_2, [-1], True);  pow_2 = None
        add_2 = torch.ops.aten.add.Tensor(mean_1, 1e-06);  mean_1 = None
        rsqrt_1 = torch.ops.aten.rsqrt.default(add_2);  add_2 = None
        mul_2 = torch.ops.aten.mul.Tensor(_to_copy_3, rsqrt_1);  _to_copy_3 = rsqrt_1 = None
        mul_3 = torch.ops.aten.mul.Tensor(mul_2, _to_copy_4);  mul_2 = _to_copy_4 = None
        silu = torch.ops.aten.silu.default(_to_copy_5);  _to_copy_5 = None
        mul_4 = torch.ops.aten.mul.Tensor(mul_3, silu);  mul_3 = silu = None
        _to_copy_6 = torch.ops.aten._to_copy.default(mul_4, dtype = torch.bfloat16);  mul_4 = None
        view_3 = torch.ops.aten.view.default(_to_copy_6, [1, 48, 128]);  _to_copy_6 = None
        view_4 = torch.ops.aten.view.default(view_3, [1, 6144]);  view_3 = None
        _param_constant4 = self._param_constant4
        t_2 = torch.ops.aten.t.default(_param_constant4);  _param_constant4 = None
        mm_2 = torch.ops.aten.mm.default(view_4, t_2);  view_4 = t_2 = None
        copy_ = torch.ops.aten.copy_.default(empty_like, mm_2);  empty_like = mm_2 = None
        _param_constant5 = self._param_constant5
        detach_1 = torch.ops.aten.detach.default(_param_constant5);  _param_constant5 = None
        add_3 = torch.ops.aten.add.Tensor(copy_, arg1_1);  copy_ = arg1_1 = None
        _to_copy_7 = torch.ops.aten._to_copy.default(add_3, dtype = torch.float32)
        pow_3 = torch.ops.aten.pow.Tensor_Scalar(_to_copy_7, 2)
        mean_2 = torch.ops.aten.mean.dim(pow_3, [-1], True);  pow_3 = None
        add_4 = torch.ops.aten.add.Tensor(mean_2, 1e-06);  mean_2 = None
        rsqrt_2 = torch.ops.aten.rsqrt.default(add_4);  add_4 = None
        mul_5 = torch.ops.aten.mul.Tensor(_to_copy_7, rsqrt_2);  _to_copy_7 = rsqrt_2 = None
        _to_copy_8 = torch.ops.aten._to_copy.default(detach_1, dtype = torch.float32);  detach_1 = None
        add_5 = torch.ops.aten.add.Tensor(_to_copy_8, 1.0);  _to_copy_8 = None
        mul_6 = torch.ops.aten.mul.Tensor(mul_5, add_5);  mul_5 = add_5 = None
        _to_copy_9 = torch.ops.aten._to_copy.default(mul_6, dtype = torch.bfloat16);  mul_6 = None
        _param_constant6 = self._param_constant6
        t_3 = torch.ops.aten.t.default(_param_constant6);  _param_constant6 = None
        mm_3 = torch.ops.aten.mm.default(_to_copy_9, t_3);  _to_copy_9 = t_3 = None
        empty = torch.ops.aten.empty.memory_format([1, 17408], dtype = torch.bfloat16, device = device(type='cuda', index=0), pin_memory = False)
        silu_and_mul = torch.ops._C.silu_and_mul.default(empty, mm_3);  mm_3 = silu_and_mul = None
        _param_constant7 = self._param_constant7
        t_4 = torch.ops.aten.t.default(_param_constant7);  _param_constant7 = None
        mm_4 = torch.ops.aten.mm.default(empty, t_4);  empty = t_4 = None
        return (mm_4, add_3)
        
