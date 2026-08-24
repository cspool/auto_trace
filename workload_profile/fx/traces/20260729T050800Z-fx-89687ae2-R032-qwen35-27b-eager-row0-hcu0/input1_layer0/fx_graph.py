


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
    view = torch.ops.aten.view.default(getitem_1, [4096, 48, 128]);  getitem_1 = None
    _param_constant2 = self._param_constant2
    t_1 = torch.ops.aten.t.default(_param_constant2);  _param_constant2 = None
    mm_1 = torch.ops.aten.mm.default(_to_copy_2, t_1);  _to_copy_2 = t_1 = None
    split = torch.ops.aten.split.Tensor(mm_1, 48, -1);  mm_1 = None
    getitem_2 = split[0]
    getitem_3 = split[1];  split = None
    clone = torch.ops.aten.clone.default(getitem_2, memory_format = torch.contiguous_format);  getitem_2 = None
    clone_1 = torch.ops.aten.clone.default(getitem_3, memory_format = torch.contiguous_format);  getitem_3 = None
    zeros = torch.ops.aten.zeros.default([4096, 48, 128], dtype = torch.bfloat16, device = device(type='cuda', index=0), pin_memory = False)
    gdn_attention_core = torch.ops.vllm.gdn_attention_core.default(getitem, clone, clone_1, zeros, 'language_model.model.layers.0.linear_attn');  getitem = clone = clone_1 = gdn_attention_core = None
    view_1 = torch.ops.aten.view.default(zeros, [-1, 128]);  zeros = None
    clone_2 = torch.ops.aten.clone.default(view, memory_format = torch.contiguous_format);  view = None
    _unsafe_view = torch.ops.aten._unsafe_view.default(clone_2, [196608, 128]);  clone_2 = None
    _to_copy_3 = torch.ops.aten._to_copy.default(view_1, dtype = torch.float32);  view_1 = None
    _param_constant3 = self._param_constant3
    _to_copy_4 = torch.ops.aten._to_copy.default(_param_constant3, dtype = torch.float32);  _param_constant3 = None
    _to_copy_5 = torch.ops.aten._to_copy.default(_unsafe_view, dtype = torch.float32);  _unsafe_view = None
    pow_2 = torch.ops.aten.pow.Tensor_Scalar(_to_copy_3, 2)
    mean_1 = torch.ops.aten.mean.dim(pow_2, [-1], True);  pow_2 = None
    add_2 = torch.ops.aten.add.Tensor(mean_1, 1e-06);  mean_1 = None
    rsqrt_1 = torch.ops.aten.rsqrt.default(add_2);  add_2 = None
    mul_2 = torch.ops.aten.mul.Tensor(_to_copy_3, rsqrt_1);  _to_copy_3 = rsqrt_1 = None
    mul_3 = torch.ops.aten.mul.Tensor(mul_2, _to_copy_4);  mul_2 = _to_copy_4 = None
    silu = torch.ops.aten.silu.default(_to_copy_5);  _to_copy_5 = None
    mul_4 = torch.ops.aten.mul.Tensor(mul_3, silu);  mul_3 = silu = None
    _to_copy_6 = torch.ops.aten._to_copy.default(mul_4, dtype = torch.bfloat16);  mul_4 = None
    view_2 = torch.ops.aten.view.default(_to_copy_6, [4096, 48, 128]);  _to_copy_6 = None
    view_3 = torch.ops.aten.view.default(view_2, [4096, 6144]);  view_2 = None
    _param_constant4 = self._param_constant4
    t_2 = torch.ops.aten.t.default(_param_constant4);  _param_constant4 = None
    mm_2 = torch.ops.aten.mm.default(view_3, t_2);  view_3 = t_2 = None
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
    empty = torch.ops.aten.empty.memory_format([4096, 17408], dtype = torch.bfloat16, device = device(type='cuda', index=0), pin_memory = False)
    silu_and_mul = torch.ops._C.silu_and_mul.default(empty, mm_3);  mm_3 = silu_and_mul = None
    _param_constant7 = self._param_constant7
    t_4 = torch.ops.aten.t.default(_param_constant7);  _param_constant7 = None
    mm_4 = torch.ops.aten.mm.default(empty, t_4);  empty = t_4 = None
    return (mm_4, add_3)
    
