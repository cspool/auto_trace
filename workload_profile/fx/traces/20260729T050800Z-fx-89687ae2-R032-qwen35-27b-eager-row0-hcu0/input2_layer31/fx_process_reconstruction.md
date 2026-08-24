# FX Layer Process Reconstruction

Event: `input2_layer31` (`selected:03`)
Source event: `chatcmpl-bench-7f1746b7-0-9eeec82b|s2|f2|l31|o0`
Observed path: `full_attention`, phase `prefill_chunk`, q/past/kv = `4096/4096/8192`
Trace directory: `/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/fx/traces/20260729T050800Z-fx-89687ae2-R032-qwen35-27b-eager-row0-hcu0/input2_layer31`
GraphModule provenance: `fx_graph_module.pt` (SHA-256 `275da1589c5188374bee9a84baf02ae42c131cd1ece0019f55cc0b957f56b0a5`)
Capture-time nodes: `fx_nodes.json` (SHA-256 `7fc479b00e28eb7057d0f18776822e7c2f73e8e0085138e6553b993eba6f9955`)

Source: rule reconstruction over the capture-time serialization of `GraphModule.graph.nodes`; the meta-storage GraphModule is not executed.
Process labels are target-specific reconstruction labels, not FX metadata or proof of runtime module ownership.
Opaque vLLM/ROCm/DCU custom-op nodes expose only their observed call and mutation boundary; their internal kernels are not reconstructed.

## Stage Summary

| stage | rule | node range | count | external inputs | external outputs |
| --- | --- | ---: | ---: | --- | --- |
| Runtime FX inputs | contiguous placeholder prefix | 0-2 | 3 | - | `arg0_1`, `arg1_1`, `arg2_1` |
| Input RMSNorm | nodes after placeholders through the node before the first mixer projection weight | 3-16 | 14 | `arg1_1`, `arg2_1` | `add`, `_to_copy_2`, `empty_like` |
| Attention/GDN input projections and head reshape | first mixer projection weight through the node before the family landmark (RoPE table or GDN custom op) | 17-59 | 43 | `_to_copy_2` | `getitem_2`, `_unsafe_view_1`, `view_2`, `view_4` |
| RoPE position embedding | position-indexed rotary table lookup and observed Q/K rotary arithmetic through the node before attention output allocation | 60-118 | 59 | `arg0_1`, `view_2`, `view_4` | `view_6`, `view_8` |
| KV-cache update and unified full attention | attention output allocation/views, opaque KV-cache update, and opaque unified attention call | 119-125 | 7 | `getitem_2`, `view_6`, `view_8` | `view_10` |
| Attention output gate and hidden reshape | opaque attention output view followed by observed sigmoid output gate multiplication | 126-128 | 3 | `_unsafe_view_1`, `view_10` | `mul_14` |
| Mixer output projection and residual | mixer output projection weight through output-buffer copy and observed residual add | 129-135 | 7 | `add`, `empty_like`, `mul_14` | `detach_3`, `add_9` |
| Post-attention RMSNorm | nodes after mixer residual add through the normalized MLP input | 136-145 | 10 | `detach_3`, `add_9` | `_to_copy_11` |
| Gated MLP projections | gate/up projection weight, fused SiLU-product boundary, and down projection through the node before graph output | 146-153 | 8 | `_to_copy_11` | `mm_3` |
| Layer output | single FX output node | 154-154 | 1 | `add_9`, `mm_3` | - |

## Process Code

### Runtime FX inputs

```python
# placeholder arg0_1
# placeholder arg1_1
# placeholder arg2_1
```

### Input RMSNorm

```python
_param_constant0 = self._param_constant0
detach = aten.detach.default(_param_constant0,)
add = aten.add.Tensor(arg1_1, arg2_1)
_to_copy = aten._to_copy.default(add,)  # kwargs={'dtype': torch.float32}
pow_1 = aten.pow.Tensor_Scalar(_to_copy, 2)
mean = aten.mean.dim(pow_1, [-1], True)
add_1 = aten.add.Tensor(mean, 1e-06)
rsqrt = aten.rsqrt.default(add_1,)
mul = aten.mul.Tensor(_to_copy, rsqrt)
_to_copy_1 = aten._to_copy.default(detach,)  # kwargs={'dtype': torch.float32}
add_2 = aten.add.Tensor(_to_copy_1, 1.0)
mul_1 = aten.mul.Tensor(mul, add_2)
_to_copy_2 = aten._to_copy.default(mul_1,)  # kwargs={'dtype': torch.bfloat16}
empty_like = aten.empty_like.default(_to_copy_2,)  # kwargs={'pin_memory': False}
```

### Attention/GDN input projections and head reshape

```python
_param_constant1 = self._param_constant1
t = aten.t.default(_param_constant1,)
mm = aten.mm.default(_to_copy_2, t)
split_with_sizes = aten.split_with_sizes.default(mm, [12288, 1024, 1024], -1)
getitem = <built-in function getitem>(split_with_sizes, 0)
getitem_1 = <built-in function getitem>(split_with_sizes, 1)
getitem_2 = <built-in function getitem>(split_with_sizes, 2)
view = aten.view.default(getitem, [4096, 24, -1])
split = aten.split.Tensor(view, 256, -1)
getitem_3 = <built-in function getitem>(split, 0)
getitem_4 = <built-in function getitem>(split, 1)
clone = aten.clone.default(getitem_3,)  # kwargs={'memory_format': torch.contiguous_format}
_unsafe_view = aten._unsafe_view.default(clone, [4096, 6144])
clone_1 = aten.clone.default(getitem_4,)  # kwargs={'memory_format': torch.contiguous_format}
_unsafe_view_1 = aten._unsafe_view.default(clone_1, [4096, 6144])
view_1 = aten.view.default(_unsafe_view, [-1, 24, 256])
_param_constant2 = self._param_constant2
detach_1 = aten.detach.default(_param_constant2,)
_to_copy_3 = aten._to_copy.default(view_1,)  # kwargs={'dtype': torch.float32}
pow_2 = aten.pow.Tensor_Scalar(_to_copy_3, 2)
mean_1 = aten.mean.dim(pow_2, [-1], True)
add_3 = aten.add.Tensor(mean_1, 1e-06)
rsqrt_1 = aten.rsqrt.default(add_3,)
mul_2 = aten.mul.Tensor(_to_copy_3, rsqrt_1)
_to_copy_4 = aten._to_copy.default(detach_1,)  # kwargs={'dtype': torch.float32}
add_4 = aten.add.Tensor(_to_copy_4, 1.0)
mul_3 = aten.mul.Tensor(mul_2, add_4)
_to_copy_5 = aten._to_copy.default(mul_3,)  # kwargs={'dtype': torch.bfloat16}
view_2 = aten.view.default(_to_copy_5, [-1, 6144])
view_3 = aten.view.default(getitem_1, [-1, 4, 256])
_param_constant3 = self._param_constant3
detach_2 = aten.detach.default(_param_constant3,)
_to_copy_6 = aten._to_copy.default(view_3,)  # kwargs={'dtype': torch.float32}
pow_3 = aten.pow.Tensor_Scalar(_to_copy_6, 2)
mean_2 = aten.mean.dim(pow_3, [-1], True)
add_5 = aten.add.Tensor(mean_2, 1e-06)
rsqrt_2 = aten.rsqrt.default(add_5,)
mul_4 = aten.mul.Tensor(_to_copy_6, rsqrt_2)
_to_copy_7 = aten._to_copy.default(detach_2,)  # kwargs={'dtype': torch.float32}
add_6 = aten.add.Tensor(_to_copy_7, 1.0)
mul_5 = aten.mul.Tensor(mul_4, add_6)
_to_copy_8 = aten._to_copy.default(mul_5,)  # kwargs={'dtype': torch.bfloat16}
view_4 = aten.view.default(_to_copy_8, [-1, 1024])
```

### RoPE position embedding

```python
_tensor_constant0 = self._tensor_constant0
index = aten.index.Tensor(_tensor_constant0, [arg0_1])
split_1 = aten.split.Tensor(index, 32, -1)
getitem_5 = <built-in function getitem>(split_1, 0)
getitem_6 = <built-in function getitem>(split_1, 1)
select = aten.select.int(getitem_5, 0, 0)
clone_2 = aten.clone.default(select,)
select_1 = aten.select.int(getitem_5, 0, 1)
slice_1 = aten.slice.Tensor(select_1, 1, 1, 33, 3)
slice_2 = aten.slice.Tensor(clone_2, 1, 1, 33, 3)
copy_ = aten.copy_.default(slice_2, slice_1)
select_2 = aten.select.int(getitem_5, 0, 2)
slice_3 = aten.slice.Tensor(select_2, 1, 2, 30, 3)
slice_4 = aten.slice.Tensor(clone_2, 1, 2, 30, 3)
copy__1 = aten.copy_.default(slice_4, slice_3)
select_3 = aten.select.int(getitem_6, 0, 0)
clone_3 = aten.clone.default(select_3,)
select_4 = aten.select.int(getitem_6, 0, 1)
slice_5 = aten.slice.Tensor(select_4, 1, 1, 33, 3)
slice_6 = aten.slice.Tensor(clone_3, 1, 1, 33, 3)
copy__2 = aten.copy_.default(slice_6, slice_5)
select_5 = aten.select.int(getitem_6, 0, 2)
slice_7 = aten.slice.Tensor(select_5, 1, 2, 30, 3)
slice_8 = aten.slice.Tensor(clone_3, 1, 2, 30, 3)
copy__3 = aten.copy_.default(slice_8, slice_7)
view_5 = aten.view.default(view_2, [4096, -1, 256])
slice_9 = aten.slice.Tensor(view_5, 2, 0, 64)
slice_10 = aten.slice.Tensor(view_5, 2, 64, 9223372036854775807)
unsqueeze = aten.unsqueeze.default(clone_2, -2)
unsqueeze_1 = aten.unsqueeze.default(clone_3, -2)
split_2 = aten.split.Tensor(slice_9, 32, -1)
getitem_7 = <built-in function getitem>(split_2, 0)
getitem_8 = <built-in function getitem>(split_2, 1)
mul_6 = aten.mul.Tensor(getitem_7, unsqueeze)
mul_7 = aten.mul.Tensor(getitem_8, unsqueeze_1)
sub = aten.sub.Tensor(mul_6, mul_7)
mul_8 = aten.mul.Tensor(getitem_8, unsqueeze)
mul_9 = aten.mul.Tensor(getitem_7, unsqueeze_1)
add_7 = aten.add.Tensor(mul_8, mul_9)
cat = aten.cat.default([sub, add_7], -1)
cat_1 = aten.cat.default([cat, slice_10], -1)
view_6 = aten.view.default(cat_1, [4096, 6144])
view_7 = aten.view.default(view_4, [4096, -1, 256])
slice_11 = aten.slice.Tensor(view_7, 2, 0, 64)
slice_12 = aten.slice.Tensor(view_7, 2, 64, 9223372036854775807)
unsqueeze_2 = aten.unsqueeze.default(clone_2, -2)
unsqueeze_3 = aten.unsqueeze.default(clone_3, -2)
split_3 = aten.split.Tensor(slice_11, 32, -1)
getitem_9 = <built-in function getitem>(split_3, 0)
getitem_10 = <built-in function getitem>(split_3, 1)
mul_10 = aten.mul.Tensor(getitem_9, unsqueeze_2)
mul_11 = aten.mul.Tensor(getitem_10, unsqueeze_3)
sub_1 = aten.sub.Tensor(mul_10, mul_11)
mul_12 = aten.mul.Tensor(getitem_10, unsqueeze_2)
mul_13 = aten.mul.Tensor(getitem_9, unsqueeze_3)
add_8 = aten.add.Tensor(mul_12, mul_13)
cat_2 = aten.cat.default([sub_1, add_8], -1)
cat_3 = aten.cat.default([cat_2, slice_12], -1)
view_8 = aten.view.default(cat_3, [4096, 1024])
```

### KV-cache update and unified full attention

```python
empty = aten.empty.memory_format([4096, 6144],)  # kwargs={'dtype': torch.bfloat16, 'device': device(type='cuda', index=0), 'pin_memory': False}
view_9 = aten.view.default(view_6, [-1, 24, 256])
view_10 = aten.view.default(empty, [-1, 24, 256])
view_11 = aten.view.default(view_8, [-1, 4, 256])
view_12 = aten.view.default(getitem_2, [-1, 4, 256])
unified_kv_cache_update = vllm.unified_kv_cache_update.default(view_11, view_12, 'language_model.model.layers.31.self_attn.attn')
unified_attention_with_output = vllm.unified_attention_with_output.default(view_9, view_11, view_12, view_10, 'language_model.model.layers.31.self_attn.attn', None, None, unified_kv_cache_update)
```

### Attention output gate and hidden reshape

```python
view_13 = aten.view.default(view_10, [-1, 6144])
sigmoid = aten.sigmoid.default(_unsafe_view_1,)
mul_14 = aten.mul.Tensor(view_13, sigmoid)
```

### Mixer output projection and residual

```python
_param_constant4 = self._param_constant4
t_1 = aten.t.default(_param_constant4,)
mm_1 = aten.mm.default(mul_14, t_1)
copy__4 = aten.copy_.default(empty_like, mm_1)
_param_constant5 = self._param_constant5
detach_3 = aten.detach.default(_param_constant5,)
add_9 = aten.add.Tensor(copy__4, add)
```

### Post-attention RMSNorm

```python
_to_copy_9 = aten._to_copy.default(add_9,)  # kwargs={'dtype': torch.float32}
pow_4 = aten.pow.Tensor_Scalar(_to_copy_9, 2)
mean_3 = aten.mean.dim(pow_4, [-1], True)
add_10 = aten.add.Tensor(mean_3, 1e-06)
rsqrt_3 = aten.rsqrt.default(add_10,)
mul_15 = aten.mul.Tensor(_to_copy_9, rsqrt_3)
_to_copy_10 = aten._to_copy.default(detach_3,)  # kwargs={'dtype': torch.float32}
add_11 = aten.add.Tensor(_to_copy_10, 1.0)
mul_16 = aten.mul.Tensor(mul_15, add_11)
_to_copy_11 = aten._to_copy.default(mul_16,)  # kwargs={'dtype': torch.bfloat16}
```

### Gated MLP projections

```python
_param_constant6 = self._param_constant6
t_2 = aten.t.default(_param_constant6,)
mm_2 = aten.mm.default(_to_copy_11, t_2)
empty_1 = aten.empty.memory_format([4096, 17408],)  # kwargs={'dtype': torch.bfloat16, 'device': device(type='cuda', index=0), 'pin_memory': False}
silu_and_mul = _C.silu_and_mul.default(empty_1, mm_2)
_param_constant7 = self._param_constant7
t_3 = aten.t.default(_param_constant7,)
mm_3 = aten.mm.default(empty_1, t_3)
```

### Layer output

```python
return ((mm_3, add_9),)
```

## Node Table

| index | stage | name | op | target | shape | dtype | args | users |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | `inputs` | `arg0_1` | `placeholder` | `arg0_1` | `[3, 4096]` | `int64` | - | `index` |
| 1 | `inputs` | `arg1_1` | `placeholder` | `arg1_1` | `[4096, 5120]` | `bfloat16` | - | `add` |
| 2 | `inputs` | `arg2_1` | `placeholder` | `arg2_1` | `[4096, 5120]` | `bfloat16` | - | `add` |
| 3 | `input_rmsnorm` | `_param_constant0` | `get_attr` | `_param_constant0` | `[5120]` | `bfloat16` | - | `detach` |
| 4 | `input_rmsnorm` | `detach` | `call_function` | `aten.detach.default` | `[5120]` | `bfloat16` | `_param_constant0` | `_to_copy_1` |
| 5 | `input_rmsnorm` | `add` | `call_function` | `aten.add.Tensor` | `[4096, 5120]` | `bfloat16` | `arg1_1`, `arg2_1` | `_to_copy`, `add_9` |
| 6 | `input_rmsnorm` | `_to_copy` | `call_function` | `aten._to_copy.default` | `[4096, 5120]` | `float32` | `add` | `mul`, `pow_1` |
| 7 | `input_rmsnorm` | `pow_1` | `call_function` | `aten.pow.Tensor_Scalar` | `[4096, 5120]` | `float32` | `_to_copy` | `mean` |
| 8 | `input_rmsnorm` | `mean` | `call_function` | `aten.mean.dim` | `[4096, 1]` | `float32` | `pow_1` | `add_1` |
| 9 | `input_rmsnorm` | `add_1` | `call_function` | `aten.add.Tensor` | `[4096, 1]` | `float32` | `mean` | `rsqrt` |
| 10 | `input_rmsnorm` | `rsqrt` | `call_function` | `aten.rsqrt.default` | `[4096, 1]` | `float32` | `add_1` | `mul` |
| 11 | `input_rmsnorm` | `mul` | `call_function` | `aten.mul.Tensor` | `[4096, 5120]` | `float32` | `_to_copy`, `rsqrt` | `mul_1` |
| 12 | `input_rmsnorm` | `_to_copy_1` | `call_function` | `aten._to_copy.default` | `[5120]` | `float32` | `detach` | `add_2` |
| 13 | `input_rmsnorm` | `add_2` | `call_function` | `aten.add.Tensor` | `[5120]` | `float32` | `_to_copy_1` | `mul_1` |
| 14 | `input_rmsnorm` | `mul_1` | `call_function` | `aten.mul.Tensor` | `[4096, 5120]` | `float32` | `mul`, `add_2` | `_to_copy_2` |
| 15 | `input_rmsnorm` | `_to_copy_2` | `call_function` | `aten._to_copy.default` | `[4096, 5120]` | `bfloat16` | `mul_1` | `empty_like`, `mm` |
| 16 | `input_rmsnorm` | `empty_like` | `call_function` | `aten.empty_like.default` | `[4096, 5120]` | `bfloat16` | `_to_copy_2` | `copy__4` |
| 17 | `qkv_projection` | `_param_constant1` | `get_attr` | `_param_constant1` | `[14336, 5120]` | `bfloat16` | - | `t` |
| 18 | `qkv_projection` | `t` | `call_function` | `aten.t.default` | `[5120, 14336]` | `bfloat16` | `_param_constant1` | `mm` |
| 19 | `qkv_projection` | `mm` | `call_function` | `aten.mm.default` | `[4096, 14336]` | `bfloat16` | `_to_copy_2`, `t` | `split_with_sizes` |
| 20 | `qkv_projection` | `split_with_sizes` | `call_function` | `aten.split_with_sizes.default` | `-` | `-` | `mm` | `getitem`, `getitem_1`, `getitem_2` |
| 21 | `qkv_projection` | `getitem` | `call_function` | `<built-in function getitem>` | `[4096, 12288]` | `bfloat16` | `split_with_sizes` | `view` |
| 22 | `qkv_projection` | `getitem_1` | `call_function` | `<built-in function getitem>` | `[4096, 1024]` | `bfloat16` | `split_with_sizes` | `view_3` |
| 23 | `qkv_projection` | `getitem_2` | `call_function` | `<built-in function getitem>` | `[4096, 1024]` | `bfloat16` | `split_with_sizes` | `view_12` |
| 24 | `qkv_projection` | `view` | `call_function` | `aten.view.default` | `[4096, 24, 512]` | `bfloat16` | `getitem` | `split` |
| 25 | `qkv_projection` | `split` | `call_function` | `aten.split.Tensor` | `-` | `-` | `view` | `getitem_3`, `getitem_4` |
| 26 | `qkv_projection` | `getitem_3` | `call_function` | `<built-in function getitem>` | `[4096, 24, 256]` | `bfloat16` | `split` | `clone` |
| 27 | `qkv_projection` | `getitem_4` | `call_function` | `<built-in function getitem>` | `[4096, 24, 256]` | `bfloat16` | `split` | `clone_1` |
| 28 | `qkv_projection` | `clone` | `call_function` | `aten.clone.default` | `[4096, 24, 256]` | `bfloat16` | `getitem_3` | `_unsafe_view` |
| 29 | `qkv_projection` | `_unsafe_view` | `call_function` | `aten._unsafe_view.default` | `[4096, 6144]` | `bfloat16` | `clone` | `view_1` |
| 30 | `qkv_projection` | `clone_1` | `call_function` | `aten.clone.default` | `[4096, 24, 256]` | `bfloat16` | `getitem_4` | `_unsafe_view_1` |
| 31 | `qkv_projection` | `_unsafe_view_1` | `call_function` | `aten._unsafe_view.default` | `[4096, 6144]` | `bfloat16` | `clone_1` | `sigmoid` |
| 32 | `qkv_projection` | `view_1` | `call_function` | `aten.view.default` | `[4096, 24, 256]` | `bfloat16` | `_unsafe_view` | `_to_copy_3` |
| 33 | `qkv_projection` | `_param_constant2` | `get_attr` | `_param_constant2` | `[256]` | `bfloat16` | - | `detach_1` |
| 34 | `qkv_projection` | `detach_1` | `call_function` | `aten.detach.default` | `[256]` | `bfloat16` | `_param_constant2` | `_to_copy_4` |
| 35 | `qkv_projection` | `_to_copy_3` | `call_function` | `aten._to_copy.default` | `[4096, 24, 256]` | `float32` | `view_1` | `mul_2`, `pow_2` |
| 36 | `qkv_projection` | `pow_2` | `call_function` | `aten.pow.Tensor_Scalar` | `[4096, 24, 256]` | `float32` | `_to_copy_3` | `mean_1` |
| 37 | `qkv_projection` | `mean_1` | `call_function` | `aten.mean.dim` | `[4096, 24, 1]` | `float32` | `pow_2` | `add_3` |
| 38 | `qkv_projection` | `add_3` | `call_function` | `aten.add.Tensor` | `[4096, 24, 1]` | `float32` | `mean_1` | `rsqrt_1` |
| 39 | `qkv_projection` | `rsqrt_1` | `call_function` | `aten.rsqrt.default` | `[4096, 24, 1]` | `float32` | `add_3` | `mul_2` |
| 40 | `qkv_projection` | `mul_2` | `call_function` | `aten.mul.Tensor` | `[4096, 24, 256]` | `float32` | `_to_copy_3`, `rsqrt_1` | `mul_3` |
| 41 | `qkv_projection` | `_to_copy_4` | `call_function` | `aten._to_copy.default` | `[256]` | `float32` | `detach_1` | `add_4` |
| 42 | `qkv_projection` | `add_4` | `call_function` | `aten.add.Tensor` | `[256]` | `float32` | `_to_copy_4` | `mul_3` |
| 43 | `qkv_projection` | `mul_3` | `call_function` | `aten.mul.Tensor` | `[4096, 24, 256]` | `float32` | `mul_2`, `add_4` | `_to_copy_5` |
| 44 | `qkv_projection` | `_to_copy_5` | `call_function` | `aten._to_copy.default` | `[4096, 24, 256]` | `bfloat16` | `mul_3` | `view_2` |
| 45 | `qkv_projection` | `view_2` | `call_function` | `aten.view.default` | `[4096, 6144]` | `bfloat16` | `_to_copy_5` | `view_5` |
| 46 | `qkv_projection` | `view_3` | `call_function` | `aten.view.default` | `[4096, 4, 256]` | `bfloat16` | `getitem_1` | `_to_copy_6` |
| 47 | `qkv_projection` | `_param_constant3` | `get_attr` | `_param_constant3` | `[256]` | `bfloat16` | - | `detach_2` |
| 48 | `qkv_projection` | `detach_2` | `call_function` | `aten.detach.default` | `[256]` | `bfloat16` | `_param_constant3` | `_to_copy_7` |
| 49 | `qkv_projection` | `_to_copy_6` | `call_function` | `aten._to_copy.default` | `[4096, 4, 256]` | `float32` | `view_3` | `mul_4`, `pow_3` |
| 50 | `qkv_projection` | `pow_3` | `call_function` | `aten.pow.Tensor_Scalar` | `[4096, 4, 256]` | `float32` | `_to_copy_6` | `mean_2` |
| 51 | `qkv_projection` | `mean_2` | `call_function` | `aten.mean.dim` | `[4096, 4, 1]` | `float32` | `pow_3` | `add_5` |
| 52 | `qkv_projection` | `add_5` | `call_function` | `aten.add.Tensor` | `[4096, 4, 1]` | `float32` | `mean_2` | `rsqrt_2` |
| 53 | `qkv_projection` | `rsqrt_2` | `call_function` | `aten.rsqrt.default` | `[4096, 4, 1]` | `float32` | `add_5` | `mul_4` |
| 54 | `qkv_projection` | `mul_4` | `call_function` | `aten.mul.Tensor` | `[4096, 4, 256]` | `float32` | `_to_copy_6`, `rsqrt_2` | `mul_5` |
| 55 | `qkv_projection` | `_to_copy_7` | `call_function` | `aten._to_copy.default` | `[256]` | `float32` | `detach_2` | `add_6` |
| 56 | `qkv_projection` | `add_6` | `call_function` | `aten.add.Tensor` | `[256]` | `float32` | `_to_copy_7` | `mul_5` |
| 57 | `qkv_projection` | `mul_5` | `call_function` | `aten.mul.Tensor` | `[4096, 4, 256]` | `float32` | `mul_4`, `add_6` | `_to_copy_8` |
| 58 | `qkv_projection` | `_to_copy_8` | `call_function` | `aten._to_copy.default` | `[4096, 4, 256]` | `bfloat16` | `mul_5` | `view_4` |
| 59 | `qkv_projection` | `view_4` | `call_function` | `aten.view.default` | `[4096, 1024]` | `bfloat16` | `_to_copy_8` | `view_7` |
| 60 | `rope` | `_tensor_constant0` | `get_attr` | `_tensor_constant0` | `[1048576, 64]` | `bfloat16` | - | `index` |
| 61 | `rope` | `index` | `call_function` | `aten.index.Tensor` | `[3, 4096, 64]` | `bfloat16` | `arg0_1`, `_tensor_constant0` | `split_1` |
| 62 | `rope` | `split_1` | `call_function` | `aten.split.Tensor` | `-` | `-` | `index` | `getitem_5`, `getitem_6` |
| 63 | `rope` | `getitem_5` | `call_function` | `<built-in function getitem>` | `[3, 4096, 32]` | `bfloat16` | `split_1` | `select`, `select_1`, `select_2` |
| 64 | `rope` | `getitem_6` | `call_function` | `<built-in function getitem>` | `[3, 4096, 32]` | `bfloat16` | `split_1` | `select_3`, `select_4`, `select_5` |
| 65 | `rope` | `select` | `call_function` | `aten.select.int` | `[4096, 32]` | `bfloat16` | `getitem_5` | `clone_2` |
| 66 | `rope` | `clone_2` | `call_function` | `aten.clone.default` | `[4096, 32]` | `bfloat16` | `select` | `slice_2`, `slice_4`, `unsqueeze`, `unsqueeze_2` |
| 67 | `rope` | `select_1` | `call_function` | `aten.select.int` | `[4096, 32]` | `bfloat16` | `getitem_5` | `slice_1` |
| 68 | `rope` | `slice_1` | `call_function` | `aten.slice.Tensor` | `[4096, 11]` | `bfloat16` | `select_1` | `copy_` |
| 69 | `rope` | `slice_2` | `call_function` | `aten.slice.Tensor` | `[4096, 11]` | `bfloat16` | `clone_2` | `copy_` |
| 70 | `rope` | `copy_` | `call_function` | `aten.copy_.default` | `[4096, 11]` | `bfloat16` | `slice_1`, `slice_2` | - |
| 71 | `rope` | `select_2` | `call_function` | `aten.select.int` | `[4096, 32]` | `bfloat16` | `getitem_5` | `slice_3` |
| 72 | `rope` | `slice_3` | `call_function` | `aten.slice.Tensor` | `[4096, 10]` | `bfloat16` | `select_2` | `copy__1` |
| 73 | `rope` | `slice_4` | `call_function` | `aten.slice.Tensor` | `[4096, 10]` | `bfloat16` | `clone_2` | `copy__1` |
| 74 | `rope` | `copy__1` | `call_function` | `aten.copy_.default` | `[4096, 10]` | `bfloat16` | `slice_3`, `slice_4` | - |
| 75 | `rope` | `select_3` | `call_function` | `aten.select.int` | `[4096, 32]` | `bfloat16` | `getitem_6` | `clone_3` |
| 76 | `rope` | `clone_3` | `call_function` | `aten.clone.default` | `[4096, 32]` | `bfloat16` | `select_3` | `slice_6`, `slice_8`, `unsqueeze_1`, `unsqueeze_3` |
| 77 | `rope` | `select_4` | `call_function` | `aten.select.int` | `[4096, 32]` | `bfloat16` | `getitem_6` | `slice_5` |
| 78 | `rope` | `slice_5` | `call_function` | `aten.slice.Tensor` | `[4096, 11]` | `bfloat16` | `select_4` | `copy__2` |
| 79 | `rope` | `slice_6` | `call_function` | `aten.slice.Tensor` | `[4096, 11]` | `bfloat16` | `clone_3` | `copy__2` |
| 80 | `rope` | `copy__2` | `call_function` | `aten.copy_.default` | `[4096, 11]` | `bfloat16` | `slice_5`, `slice_6` | - |
| 81 | `rope` | `select_5` | `call_function` | `aten.select.int` | `[4096, 32]` | `bfloat16` | `getitem_6` | `slice_7` |
| 82 | `rope` | `slice_7` | `call_function` | `aten.slice.Tensor` | `[4096, 10]` | `bfloat16` | `select_5` | `copy__3` |
| 83 | `rope` | `slice_8` | `call_function` | `aten.slice.Tensor` | `[4096, 10]` | `bfloat16` | `clone_3` | `copy__3` |
| 84 | `rope` | `copy__3` | `call_function` | `aten.copy_.default` | `[4096, 10]` | `bfloat16` | `slice_7`, `slice_8` | - |
| 85 | `rope` | `view_5` | `call_function` | `aten.view.default` | `[4096, 24, 256]` | `bfloat16` | `view_2` | `slice_10`, `slice_9` |
| 86 | `rope` | `slice_9` | `call_function` | `aten.slice.Tensor` | `[4096, 24, 64]` | `bfloat16` | `view_5` | `split_2` |
| 87 | `rope` | `slice_10` | `call_function` | `aten.slice.Tensor` | `[4096, 24, 192]` | `bfloat16` | `view_5` | `cat_1` |
| 88 | `rope` | `unsqueeze` | `call_function` | `aten.unsqueeze.default` | `[4096, 1, 32]` | `bfloat16` | `clone_2` | `mul_6`, `mul_8` |
| 89 | `rope` | `unsqueeze_1` | `call_function` | `aten.unsqueeze.default` | `[4096, 1, 32]` | `bfloat16` | `clone_3` | `mul_7`, `mul_9` |
| 90 | `rope` | `split_2` | `call_function` | `aten.split.Tensor` | `-` | `-` | `slice_9` | `getitem_7`, `getitem_8` |
| 91 | `rope` | `getitem_7` | `call_function` | `<built-in function getitem>` | `[4096, 24, 32]` | `bfloat16` | `split_2` | `mul_6`, `mul_9` |
| 92 | `rope` | `getitem_8` | `call_function` | `<built-in function getitem>` | `[4096, 24, 32]` | `bfloat16` | `split_2` | `mul_7`, `mul_8` |
| 93 | `rope` | `mul_6` | `call_function` | `aten.mul.Tensor` | `[4096, 24, 32]` | `bfloat16` | `unsqueeze`, `getitem_7` | `sub` |
| 94 | `rope` | `mul_7` | `call_function` | `aten.mul.Tensor` | `[4096, 24, 32]` | `bfloat16` | `unsqueeze_1`, `getitem_8` | `sub` |
| 95 | `rope` | `sub` | `call_function` | `aten.sub.Tensor` | `[4096, 24, 32]` | `bfloat16` | `mul_6`, `mul_7` | `cat` |
| 96 | `rope` | `mul_8` | `call_function` | `aten.mul.Tensor` | `[4096, 24, 32]` | `bfloat16` | `unsqueeze`, `getitem_8` | `add_7` |
| 97 | `rope` | `mul_9` | `call_function` | `aten.mul.Tensor` | `[4096, 24, 32]` | `bfloat16` | `unsqueeze_1`, `getitem_7` | `add_7` |
| 98 | `rope` | `add_7` | `call_function` | `aten.add.Tensor` | `[4096, 24, 32]` | `bfloat16` | `mul_8`, `mul_9` | `cat` |
| 99 | `rope` | `cat` | `call_function` | `aten.cat.default` | `[4096, 24, 64]` | `bfloat16` | `sub`, `add_7` | `cat_1` |
| 100 | `rope` | `cat_1` | `call_function` | `aten.cat.default` | `[4096, 24, 256]` | `bfloat16` | `slice_10`, `cat` | `view_6` |
| 101 | `rope` | `view_6` | `call_function` | `aten.view.default` | `[4096, 6144]` | `bfloat16` | `cat_1` | `view_9` |
| 102 | `rope` | `view_7` | `call_function` | `aten.view.default` | `[4096, 4, 256]` | `bfloat16` | `view_4` | `slice_11`, `slice_12` |
| 103 | `rope` | `slice_11` | `call_function` | `aten.slice.Tensor` | `[4096, 4, 64]` | `bfloat16` | `view_7` | `split_3` |
| 104 | `rope` | `slice_12` | `call_function` | `aten.slice.Tensor` | `[4096, 4, 192]` | `bfloat16` | `view_7` | `cat_3` |
| 105 | `rope` | `unsqueeze_2` | `call_function` | `aten.unsqueeze.default` | `[4096, 1, 32]` | `bfloat16` | `clone_2` | `mul_10`, `mul_12` |
| 106 | `rope` | `unsqueeze_3` | `call_function` | `aten.unsqueeze.default` | `[4096, 1, 32]` | `bfloat16` | `clone_3` | `mul_11`, `mul_13` |
| 107 | `rope` | `split_3` | `call_function` | `aten.split.Tensor` | `-` | `-` | `slice_11` | `getitem_10`, `getitem_9` |
| 108 | `rope` | `getitem_9` | `call_function` | `<built-in function getitem>` | `[4096, 4, 32]` | `bfloat16` | `split_3` | `mul_10`, `mul_13` |
| 109 | `rope` | `getitem_10` | `call_function` | `<built-in function getitem>` | `[4096, 4, 32]` | `bfloat16` | `split_3` | `mul_11`, `mul_12` |
| 110 | `rope` | `mul_10` | `call_function` | `aten.mul.Tensor` | `[4096, 4, 32]` | `bfloat16` | `unsqueeze_2`, `getitem_9` | `sub_1` |
| 111 | `rope` | `mul_11` | `call_function` | `aten.mul.Tensor` | `[4096, 4, 32]` | `bfloat16` | `unsqueeze_3`, `getitem_10` | `sub_1` |
| 112 | `rope` | `sub_1` | `call_function` | `aten.sub.Tensor` | `[4096, 4, 32]` | `bfloat16` | `mul_10`, `mul_11` | `cat_2` |
| 113 | `rope` | `mul_12` | `call_function` | `aten.mul.Tensor` | `[4096, 4, 32]` | `bfloat16` | `unsqueeze_2`, `getitem_10` | `add_8` |
| 114 | `rope` | `mul_13` | `call_function` | `aten.mul.Tensor` | `[4096, 4, 32]` | `bfloat16` | `unsqueeze_3`, `getitem_9` | `add_8` |
| 115 | `rope` | `add_8` | `call_function` | `aten.add.Tensor` | `[4096, 4, 32]` | `bfloat16` | `mul_12`, `mul_13` | `cat_2` |
| 116 | `rope` | `cat_2` | `call_function` | `aten.cat.default` | `[4096, 4, 64]` | `bfloat16` | `sub_1`, `add_8` | `cat_3` |
| 117 | `rope` | `cat_3` | `call_function` | `aten.cat.default` | `[4096, 4, 256]` | `bfloat16` | `slice_12`, `cat_2` | `view_8` |
| 118 | `rope` | `view_8` | `call_function` | `aten.view.default` | `[4096, 1024]` | `bfloat16` | `cat_3` | `view_11` |
| 119 | `kv_cache_attention` | `empty` | `call_function` | `aten.empty.memory_format` | `[4096, 6144]` | `bfloat16` | - | `view_10` |
| 120 | `kv_cache_attention` | `view_9` | `call_function` | `aten.view.default` | `[4096, 24, 256]` | `bfloat16` | `view_6` | `unified_attention_with_output` |
| 121 | `kv_cache_attention` | `view_10` | `call_function` | `aten.view.default` | `[4096, 24, 256]` | `bfloat16` | `empty` | `unified_attention_with_output`, `view_13` |
| 122 | `kv_cache_attention` | `view_11` | `call_function` | `aten.view.default` | `[4096, 4, 256]` | `bfloat16` | `view_8` | `unified_attention_with_output`, `unified_kv_cache_update` |
| 123 | `kv_cache_attention` | `view_12` | `call_function` | `aten.view.default` | `[4096, 4, 256]` | `bfloat16` | `getitem_2` | `unified_attention_with_output`, `unified_kv_cache_update` |
| 124 | `kv_cache_attention` | `unified_kv_cache_update` | `call_function` | `vllm.unified_kv_cache_update.default` | `[0]` | `bfloat16` | `view_11`, `view_12` | `unified_attention_with_output` |
| 125 | `kv_cache_attention` | `unified_attention_with_output` | `call_function` | `vllm.unified_attention_with_output.default` | `-` | `-` | `view_9`, `view_10`, `view_11`, `view_12`, `unified_kv_cache_update` | - |
| 126 | `attention_output` | `view_13` | `call_function` | `aten.view.default` | `[4096, 6144]` | `bfloat16` | `view_10` | `mul_14` |
| 127 | `attention_output` | `sigmoid` | `call_function` | `aten.sigmoid.default` | `[4096, 6144]` | `bfloat16` | `_unsafe_view_1` | `mul_14` |
| 128 | `attention_output` | `mul_14` | `call_function` | `aten.mul.Tensor` | `[4096, 6144]` | `bfloat16` | `view_13`, `sigmoid` | `mm_1` |
| 129 | `output_projection` | `_param_constant4` | `get_attr` | `_param_constant4` | `[5120, 6144]` | `bfloat16` | - | `t_1` |
| 130 | `output_projection` | `t_1` | `call_function` | `aten.t.default` | `[6144, 5120]` | `bfloat16` | `_param_constant4` | `mm_1` |
| 131 | `output_projection` | `mm_1` | `call_function` | `aten.mm.default` | `[4096, 5120]` | `bfloat16` | `mul_14`, `t_1` | `copy__4` |
| 132 | `output_projection` | `copy__4` | `call_function` | `aten.copy_.default` | `[4096, 5120]` | `bfloat16` | `empty_like`, `mm_1` | `add_9` |
| 133 | `output_projection` | `_param_constant5` | `get_attr` | `_param_constant5` | `[5120]` | `bfloat16` | - | `detach_3` |
| 134 | `output_projection` | `detach_3` | `call_function` | `aten.detach.default` | `[5120]` | `bfloat16` | `_param_constant5` | `_to_copy_10` |
| 135 | `output_projection` | `add_9` | `call_function` | `aten.add.Tensor` | `[4096, 5120]` | `bfloat16` | `add`, `copy__4` | `_to_copy_9`, `output` |
| 136 | `post_attention_rmsnorm` | `_to_copy_9` | `call_function` | `aten._to_copy.default` | `[4096, 5120]` | `float32` | `add_9` | `mul_15`, `pow_4` |
| 137 | `post_attention_rmsnorm` | `pow_4` | `call_function` | `aten.pow.Tensor_Scalar` | `[4096, 5120]` | `float32` | `_to_copy_9` | `mean_3` |
| 138 | `post_attention_rmsnorm` | `mean_3` | `call_function` | `aten.mean.dim` | `[4096, 1]` | `float32` | `pow_4` | `add_10` |
| 139 | `post_attention_rmsnorm` | `add_10` | `call_function` | `aten.add.Tensor` | `[4096, 1]` | `float32` | `mean_3` | `rsqrt_3` |
| 140 | `post_attention_rmsnorm` | `rsqrt_3` | `call_function` | `aten.rsqrt.default` | `[4096, 1]` | `float32` | `add_10` | `mul_15` |
| 141 | `post_attention_rmsnorm` | `mul_15` | `call_function` | `aten.mul.Tensor` | `[4096, 5120]` | `float32` | `_to_copy_9`, `rsqrt_3` | `mul_16` |
| 142 | `post_attention_rmsnorm` | `_to_copy_10` | `call_function` | `aten._to_copy.default` | `[5120]` | `float32` | `detach_3` | `add_11` |
| 143 | `post_attention_rmsnorm` | `add_11` | `call_function` | `aten.add.Tensor` | `[5120]` | `float32` | `_to_copy_10` | `mul_16` |
| 144 | `post_attention_rmsnorm` | `mul_16` | `call_function` | `aten.mul.Tensor` | `[4096, 5120]` | `float32` | `mul_15`, `add_11` | `_to_copy_11` |
| 145 | `post_attention_rmsnorm` | `_to_copy_11` | `call_function` | `aten._to_copy.default` | `[4096, 5120]` | `bfloat16` | `mul_16` | `mm_2` |
| 146 | `mlp` | `_param_constant6` | `get_attr` | `_param_constant6` | `[34816, 5120]` | `bfloat16` | - | `t_2` |
| 147 | `mlp` | `t_2` | `call_function` | `aten.t.default` | `[5120, 34816]` | `bfloat16` | `_param_constant6` | `mm_2` |
| 148 | `mlp` | `mm_2` | `call_function` | `aten.mm.default` | `[4096, 34816]` | `bfloat16` | `_to_copy_11`, `t_2` | `silu_and_mul` |
| 149 | `mlp` | `empty_1` | `call_function` | `aten.empty.memory_format` | `[4096, 17408]` | `bfloat16` | - | `mm_3`, `silu_and_mul` |
| 150 | `mlp` | `silu_and_mul` | `call_function` | `_C.silu_and_mul.default` | `-` | `-` | `mm_2`, `empty_1` | - |
| 151 | `mlp` | `_param_constant7` | `get_attr` | `_param_constant7` | `[5120, 17408]` | `bfloat16` | - | `t_3` |
| 152 | `mlp` | `t_3` | `call_function` | `aten.t.default` | `[17408, 5120]` | `bfloat16` | `_param_constant7` | `mm_3` |
| 153 | `mlp` | `mm_3` | `call_function` | `aten.mm.default` | `[4096, 5120]` | `bfloat16` | `empty_1`, `t_3` | `output` |
| 154 | `layer_output` | `output` | `output` | `output` | `-` | `-` | `add_9`, `mm_3` | - |
