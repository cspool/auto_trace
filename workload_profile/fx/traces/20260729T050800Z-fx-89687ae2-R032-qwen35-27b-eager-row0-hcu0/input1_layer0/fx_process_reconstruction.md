# FX Layer Process Reconstruction

Event: `input1_layer0` (`selected:01`)
Source event: `chatcmpl-bench-7f1746b7-0-9eeec82b|s1|f1|l0|o0`
Observed path: `linear_attention`, phase `prefill_chunk`, q/past/kv = `4096/0/4096`
Trace directory: `/public/home/tangyu408/Qwen_DCU_Worker_0/workload_profile/fx/traces/20260729T050800Z-fx-89687ae2-R032-qwen35-27b-eager-row0-hcu0/input1_layer0`
GraphModule provenance: `fx_graph_module.pt` (SHA-256 `d9bbef1c5d8b04389196de5063613e2e774b81cc411384ad9d45b733cde0880e`)
Capture-time nodes: `fx_nodes.json` (SHA-256 `5d788945fa0ad14ecdeee628e0853865c0e2b1cd7b34b8b1b74770a110424c21`)

Source: rule reconstruction over the capture-time serialization of `GraphModule.graph.nodes`; the meta-storage GraphModule is not executed.
Process labels are target-specific reconstruction labels, not FX metadata or proof of runtime module ownership.
Opaque vLLM/ROCm/DCU custom-op nodes expose only their observed call and mutation boundary; their internal kernels are not reconstructed.

## Stage Summary

| stage | rule | node range | count | external inputs | external outputs |
| --- | --- | ---: | ---: | --- | --- |
| Runtime FX inputs | contiguous placeholder prefix | 0-2 | 3 | - | `arg1_1` |
| Input RMSNorm | nodes after placeholders through the node before the first mixer projection weight | 3-15 | 13 | `arg1_1` | `_to_copy_2`, `empty_like` |
| Attention/GDN input projections and head reshape | first mixer projection weight through the node before the family landmark (RoPE table or GDN custom op) | 16-31 | 16 | `_to_copy_2` | `getitem`, `view`, `clone`, `clone_1`, `zeros` |
| Gated DeltaNet recurrent core | single opaque vllm.gdn_attention_core call | 32-32 | 1 | `getitem`, `clone`, `clone_1`, `zeros` | - |
| Gated DeltaNet output RMSNorm and SiLU gate | observed core-output reshape, RMS normalization, SiLU Z gate, and head merge before the mixer output projection | 33-50 | 18 | `view`, `zeros` | `view_3` |
| Mixer output projection and residual | mixer output projection weight through output-buffer copy and observed residual add | 51-57 | 7 | `arg1_1`, `empty_like`, `view_3` | `detach_1`, `add_3` |
| Post-attention RMSNorm | nodes after mixer residual add through the normalized MLP input | 58-67 | 10 | `detach_1`, `add_3` | `_to_copy_9` |
| Gated MLP projections | gate/up projection weight, fused SiLU-product boundary, and down projection through the node before graph output | 68-75 | 8 | `_to_copy_9` | `mm_4` |
| Layer output | single FX output node | 76-76 | 1 | `add_3`, `mm_4` | - |

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
_to_copy = aten._to_copy.default(arg1_1,)  # kwargs={'dtype': torch.float32}
pow_1 = aten.pow.Tensor_Scalar(_to_copy, 2)
mean = aten.mean.dim(pow_1, [-1], True)
add = aten.add.Tensor(mean, 1e-06)
rsqrt = aten.rsqrt.default(add,)
mul = aten.mul.Tensor(_to_copy, rsqrt)
_to_copy_1 = aten._to_copy.default(detach,)  # kwargs={'dtype': torch.float32}
add_1 = aten.add.Tensor(_to_copy_1, 1.0)
mul_1 = aten.mul.Tensor(mul, add_1)
_to_copy_2 = aten._to_copy.default(mul_1,)  # kwargs={'dtype': torch.bfloat16}
empty_like = aten.empty_like.default(_to_copy_2,)  # kwargs={'pin_memory': False}
```

### Attention/GDN input projections and head reshape

```python
_param_constant1 = self._param_constant1
t = aten.t.default(_param_constant1,)
mm = aten.mm.default(_to_copy_2, t)
split_with_sizes = aten.split_with_sizes.default(mm, [10240, 6144], -1)
getitem = <built-in function getitem>(split_with_sizes, 0)
getitem_1 = <built-in function getitem>(split_with_sizes, 1)
view = aten.view.default(getitem_1, [4096, 48, 128])
_param_constant2 = self._param_constant2
t_1 = aten.t.default(_param_constant2,)
mm_1 = aten.mm.default(_to_copy_2, t_1)
split = aten.split.Tensor(mm_1, 48, -1)
getitem_2 = <built-in function getitem>(split, 0)
getitem_3 = <built-in function getitem>(split, 1)
clone = aten.clone.default(getitem_2,)  # kwargs={'memory_format': torch.contiguous_format}
clone_1 = aten.clone.default(getitem_3,)  # kwargs={'memory_format': torch.contiguous_format}
zeros = aten.zeros.default([4096, 48, 128],)  # kwargs={'dtype': torch.bfloat16, 'device': device(type='cuda', index=0), 'pin_memory': False}
```

### Gated DeltaNet recurrent core

```python
gdn_attention_core = vllm.gdn_attention_core.default(getitem, clone, clone_1, zeros, 'language_model.model.layers.0.linear_attn')
```

### Gated DeltaNet output RMSNorm and SiLU gate

```python
view_1 = aten.view.default(zeros, [-1, 128])
clone_2 = aten.clone.default(view,)  # kwargs={'memory_format': torch.contiguous_format}
_unsafe_view = aten._unsafe_view.default(clone_2, [196608, 128])
_to_copy_3 = aten._to_copy.default(view_1,)  # kwargs={'dtype': torch.float32}
_param_constant3 = self._param_constant3
_to_copy_4 = aten._to_copy.default(_param_constant3,)  # kwargs={'dtype': torch.float32}
_to_copy_5 = aten._to_copy.default(_unsafe_view,)  # kwargs={'dtype': torch.float32}
pow_2 = aten.pow.Tensor_Scalar(_to_copy_3, 2)
mean_1 = aten.mean.dim(pow_2, [-1], True)
add_2 = aten.add.Tensor(mean_1, 1e-06)
rsqrt_1 = aten.rsqrt.default(add_2,)
mul_2 = aten.mul.Tensor(_to_copy_3, rsqrt_1)
mul_3 = aten.mul.Tensor(mul_2, _to_copy_4)
silu = aten.silu.default(_to_copy_5,)
mul_4 = aten.mul.Tensor(mul_3, silu)
_to_copy_6 = aten._to_copy.default(mul_4,)  # kwargs={'dtype': torch.bfloat16}
view_2 = aten.view.default(_to_copy_6, [4096, 48, 128])
view_3 = aten.view.default(view_2, [4096, 6144])
```

### Mixer output projection and residual

```python
_param_constant4 = self._param_constant4
t_2 = aten.t.default(_param_constant4,)
mm_2 = aten.mm.default(view_3, t_2)
copy_ = aten.copy_.default(empty_like, mm_2)
_param_constant5 = self._param_constant5
detach_1 = aten.detach.default(_param_constant5,)
add_3 = aten.add.Tensor(copy_, arg1_1)
```

### Post-attention RMSNorm

```python
_to_copy_7 = aten._to_copy.default(add_3,)  # kwargs={'dtype': torch.float32}
pow_3 = aten.pow.Tensor_Scalar(_to_copy_7, 2)
mean_2 = aten.mean.dim(pow_3, [-1], True)
add_4 = aten.add.Tensor(mean_2, 1e-06)
rsqrt_2 = aten.rsqrt.default(add_4,)
mul_5 = aten.mul.Tensor(_to_copy_7, rsqrt_2)
_to_copy_8 = aten._to_copy.default(detach_1,)  # kwargs={'dtype': torch.float32}
add_5 = aten.add.Tensor(_to_copy_8, 1.0)
mul_6 = aten.mul.Tensor(mul_5, add_5)
_to_copy_9 = aten._to_copy.default(mul_6,)  # kwargs={'dtype': torch.bfloat16}
```

### Gated MLP projections

```python
_param_constant6 = self._param_constant6
t_3 = aten.t.default(_param_constant6,)
mm_3 = aten.mm.default(_to_copy_9, t_3)
empty = aten.empty.memory_format([4096, 17408],)  # kwargs={'dtype': torch.bfloat16, 'device': device(type='cuda', index=0), 'pin_memory': False}
silu_and_mul = _C.silu_and_mul.default(empty, mm_3)
_param_constant7 = self._param_constant7
t_4 = aten.t.default(_param_constant7,)
mm_4 = aten.mm.default(empty, t_4)
```

### Layer output

```python
return ((mm_4, add_3),)
```

## Node Table

| index | stage | name | op | target | shape | dtype | args | users |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | `inputs` | `arg0_1` | `placeholder` | `arg0_1` | `[3, 4096]` | `int64` | - | - |
| 1 | `inputs` | `arg1_1` | `placeholder` | `arg1_1` | `[4096, 5120]` | `bfloat16` | - | `_to_copy`, `add_3` |
| 2 | `inputs` | `arg2_1` | `placeholder` | `arg2_1` | `-` | `-` | - | - |
| 3 | `input_rmsnorm` | `_param_constant0` | `get_attr` | `_param_constant0` | `[5120]` | `bfloat16` | - | `detach` |
| 4 | `input_rmsnorm` | `detach` | `call_function` | `aten.detach.default` | `[5120]` | `bfloat16` | `_param_constant0` | `_to_copy_1` |
| 5 | `input_rmsnorm` | `_to_copy` | `call_function` | `aten._to_copy.default` | `[4096, 5120]` | `float32` | `arg1_1` | `mul`, `pow_1` |
| 6 | `input_rmsnorm` | `pow_1` | `call_function` | `aten.pow.Tensor_Scalar` | `[4096, 5120]` | `float32` | `_to_copy` | `mean` |
| 7 | `input_rmsnorm` | `mean` | `call_function` | `aten.mean.dim` | `[4096, 1]` | `float32` | `pow_1` | `add` |
| 8 | `input_rmsnorm` | `add` | `call_function` | `aten.add.Tensor` | `[4096, 1]` | `float32` | `mean` | `rsqrt` |
| 9 | `input_rmsnorm` | `rsqrt` | `call_function` | `aten.rsqrt.default` | `[4096, 1]` | `float32` | `add` | `mul` |
| 10 | `input_rmsnorm` | `mul` | `call_function` | `aten.mul.Tensor` | `[4096, 5120]` | `float32` | `_to_copy`, `rsqrt` | `mul_1` |
| 11 | `input_rmsnorm` | `_to_copy_1` | `call_function` | `aten._to_copy.default` | `[5120]` | `float32` | `detach` | `add_1` |
| 12 | `input_rmsnorm` | `add_1` | `call_function` | `aten.add.Tensor` | `[5120]` | `float32` | `_to_copy_1` | `mul_1` |
| 13 | `input_rmsnorm` | `mul_1` | `call_function` | `aten.mul.Tensor` | `[4096, 5120]` | `float32` | `mul`, `add_1` | `_to_copy_2` |
| 14 | `input_rmsnorm` | `_to_copy_2` | `call_function` | `aten._to_copy.default` | `[4096, 5120]` | `bfloat16` | `mul_1` | `empty_like`, `mm`, `mm_1` |
| 15 | `input_rmsnorm` | `empty_like` | `call_function` | `aten.empty_like.default` | `[4096, 5120]` | `bfloat16` | `_to_copy_2` | `copy_` |
| 16 | `qkv_projection` | `_param_constant1` | `get_attr` | `_param_constant1` | `[16384, 5120]` | `bfloat16` | - | `t` |
| 17 | `qkv_projection` | `t` | `call_function` | `aten.t.default` | `[5120, 16384]` | `bfloat16` | `_param_constant1` | `mm` |
| 18 | `qkv_projection` | `mm` | `call_function` | `aten.mm.default` | `[4096, 16384]` | `bfloat16` | `_to_copy_2`, `t` | `split_with_sizes` |
| 19 | `qkv_projection` | `split_with_sizes` | `call_function` | `aten.split_with_sizes.default` | `-` | `-` | `mm` | `getitem`, `getitem_1` |
| 20 | `qkv_projection` | `getitem` | `call_function` | `<built-in function getitem>` | `[4096, 10240]` | `bfloat16` | `split_with_sizes` | `gdn_attention_core` |
| 21 | `qkv_projection` | `getitem_1` | `call_function` | `<built-in function getitem>` | `[4096, 6144]` | `bfloat16` | `split_with_sizes` | `view` |
| 22 | `qkv_projection` | `view` | `call_function` | `aten.view.default` | `[4096, 48, 128]` | `bfloat16` | `getitem_1` | `clone_2` |
| 23 | `qkv_projection` | `_param_constant2` | `get_attr` | `_param_constant2` | `[96, 5120]` | `bfloat16` | - | `t_1` |
| 24 | `qkv_projection` | `t_1` | `call_function` | `aten.t.default` | `[5120, 96]` | `bfloat16` | `_param_constant2` | `mm_1` |
| 25 | `qkv_projection` | `mm_1` | `call_function` | `aten.mm.default` | `[4096, 96]` | `bfloat16` | `_to_copy_2`, `t_1` | `split` |
| 26 | `qkv_projection` | `split` | `call_function` | `aten.split.Tensor` | `-` | `-` | `mm_1` | `getitem_2`, `getitem_3` |
| 27 | `qkv_projection` | `getitem_2` | `call_function` | `<built-in function getitem>` | `[4096, 48]` | `bfloat16` | `split` | `clone` |
| 28 | `qkv_projection` | `getitem_3` | `call_function` | `<built-in function getitem>` | `[4096, 48]` | `bfloat16` | `split` | `clone_1` |
| 29 | `qkv_projection` | `clone` | `call_function` | `aten.clone.default` | `[4096, 48]` | `bfloat16` | `getitem_2` | `gdn_attention_core` |
| 30 | `qkv_projection` | `clone_1` | `call_function` | `aten.clone.default` | `[4096, 48]` | `bfloat16` | `getitem_3` | `gdn_attention_core` |
| 31 | `qkv_projection` | `zeros` | `call_function` | `aten.zeros.default` | `[4096, 48, 128]` | `bfloat16` | - | `gdn_attention_core`, `view_1` |
| 32 | `gdn_recurrent_core` | `gdn_attention_core` | `call_function` | `vllm.gdn_attention_core.default` | `-` | `-` | `getitem`, `clone`, `clone_1`, `zeros` | - |
| 33 | `gdn_gated_rmsnorm` | `view_1` | `call_function` | `aten.view.default` | `[196608, 128]` | `bfloat16` | `zeros` | `_to_copy_3` |
| 34 | `gdn_gated_rmsnorm` | `clone_2` | `call_function` | `aten.clone.default` | `[4096, 48, 128]` | `bfloat16` | `view` | `_unsafe_view` |
| 35 | `gdn_gated_rmsnorm` | `_unsafe_view` | `call_function` | `aten._unsafe_view.default` | `[196608, 128]` | `bfloat16` | `clone_2` | `_to_copy_5` |
| 36 | `gdn_gated_rmsnorm` | `_to_copy_3` | `call_function` | `aten._to_copy.default` | `[196608, 128]` | `float32` | `view_1` | `mul_2`, `pow_2` |
| 37 | `gdn_gated_rmsnorm` | `_param_constant3` | `get_attr` | `_param_constant3` | `[128]` | `bfloat16` | - | `_to_copy_4` |
| 38 | `gdn_gated_rmsnorm` | `_to_copy_4` | `call_function` | `aten._to_copy.default` | `[128]` | `float32` | `_param_constant3` | `mul_3` |
| 39 | `gdn_gated_rmsnorm` | `_to_copy_5` | `call_function` | `aten._to_copy.default` | `[196608, 128]` | `float32` | `_unsafe_view` | `silu` |
| 40 | `gdn_gated_rmsnorm` | `pow_2` | `call_function` | `aten.pow.Tensor_Scalar` | `[196608, 128]` | `float32` | `_to_copy_3` | `mean_1` |
| 41 | `gdn_gated_rmsnorm` | `mean_1` | `call_function` | `aten.mean.dim` | `[196608, 1]` | `float32` | `pow_2` | `add_2` |
| 42 | `gdn_gated_rmsnorm` | `add_2` | `call_function` | `aten.add.Tensor` | `[196608, 1]` | `float32` | `mean_1` | `rsqrt_1` |
| 43 | `gdn_gated_rmsnorm` | `rsqrt_1` | `call_function` | `aten.rsqrt.default` | `[196608, 1]` | `float32` | `add_2` | `mul_2` |
| 44 | `gdn_gated_rmsnorm` | `mul_2` | `call_function` | `aten.mul.Tensor` | `[196608, 128]` | `float32` | `_to_copy_3`, `rsqrt_1` | `mul_3` |
| 45 | `gdn_gated_rmsnorm` | `mul_3` | `call_function` | `aten.mul.Tensor` | `[196608, 128]` | `float32` | `_to_copy_4`, `mul_2` | `mul_4` |
| 46 | `gdn_gated_rmsnorm` | `silu` | `call_function` | `aten.silu.default` | `[196608, 128]` | `float32` | `_to_copy_5` | `mul_4` |
| 47 | `gdn_gated_rmsnorm` | `mul_4` | `call_function` | `aten.mul.Tensor` | `[196608, 128]` | `float32` | `mul_3`, `silu` | `_to_copy_6` |
| 48 | `gdn_gated_rmsnorm` | `_to_copy_6` | `call_function` | `aten._to_copy.default` | `[196608, 128]` | `bfloat16` | `mul_4` | `view_2` |
| 49 | `gdn_gated_rmsnorm` | `view_2` | `call_function` | `aten.view.default` | `[4096, 48, 128]` | `bfloat16` | `_to_copy_6` | `view_3` |
| 50 | `gdn_gated_rmsnorm` | `view_3` | `call_function` | `aten.view.default` | `[4096, 6144]` | `bfloat16` | `view_2` | `mm_2` |
| 51 | `output_projection` | `_param_constant4` | `get_attr` | `_param_constant4` | `[5120, 6144]` | `bfloat16` | - | `t_2` |
| 52 | `output_projection` | `t_2` | `call_function` | `aten.t.default` | `[6144, 5120]` | `bfloat16` | `_param_constant4` | `mm_2` |
| 53 | `output_projection` | `mm_2` | `call_function` | `aten.mm.default` | `[4096, 5120]` | `bfloat16` | `view_3`, `t_2` | `copy_` |
| 54 | `output_projection` | `copy_` | `call_function` | `aten.copy_.default` | `[4096, 5120]` | `bfloat16` | `empty_like`, `mm_2` | `add_3` |
| 55 | `output_projection` | `_param_constant5` | `get_attr` | `_param_constant5` | `[5120]` | `bfloat16` | - | `detach_1` |
| 56 | `output_projection` | `detach_1` | `call_function` | `aten.detach.default` | `[5120]` | `bfloat16` | `_param_constant5` | `_to_copy_8` |
| 57 | `output_projection` | `add_3` | `call_function` | `aten.add.Tensor` | `[4096, 5120]` | `bfloat16` | `arg1_1`, `copy_` | `_to_copy_7`, `output` |
| 58 | `post_attention_rmsnorm` | `_to_copy_7` | `call_function` | `aten._to_copy.default` | `[4096, 5120]` | `float32` | `add_3` | `mul_5`, `pow_3` |
| 59 | `post_attention_rmsnorm` | `pow_3` | `call_function` | `aten.pow.Tensor_Scalar` | `[4096, 5120]` | `float32` | `_to_copy_7` | `mean_2` |
| 60 | `post_attention_rmsnorm` | `mean_2` | `call_function` | `aten.mean.dim` | `[4096, 1]` | `float32` | `pow_3` | `add_4` |
| 61 | `post_attention_rmsnorm` | `add_4` | `call_function` | `aten.add.Tensor` | `[4096, 1]` | `float32` | `mean_2` | `rsqrt_2` |
| 62 | `post_attention_rmsnorm` | `rsqrt_2` | `call_function` | `aten.rsqrt.default` | `[4096, 1]` | `float32` | `add_4` | `mul_5` |
| 63 | `post_attention_rmsnorm` | `mul_5` | `call_function` | `aten.mul.Tensor` | `[4096, 5120]` | `float32` | `_to_copy_7`, `rsqrt_2` | `mul_6` |
| 64 | `post_attention_rmsnorm` | `_to_copy_8` | `call_function` | `aten._to_copy.default` | `[5120]` | `float32` | `detach_1` | `add_5` |
| 65 | `post_attention_rmsnorm` | `add_5` | `call_function` | `aten.add.Tensor` | `[5120]` | `float32` | `_to_copy_8` | `mul_6` |
| 66 | `post_attention_rmsnorm` | `mul_6` | `call_function` | `aten.mul.Tensor` | `[4096, 5120]` | `float32` | `mul_5`, `add_5` | `_to_copy_9` |
| 67 | `post_attention_rmsnorm` | `_to_copy_9` | `call_function` | `aten._to_copy.default` | `[4096, 5120]` | `bfloat16` | `mul_6` | `mm_3` |
| 68 | `mlp` | `_param_constant6` | `get_attr` | `_param_constant6` | `[34816, 5120]` | `bfloat16` | - | `t_3` |
| 69 | `mlp` | `t_3` | `call_function` | `aten.t.default` | `[5120, 34816]` | `bfloat16` | `_param_constant6` | `mm_3` |
| 70 | `mlp` | `mm_3` | `call_function` | `aten.mm.default` | `[4096, 34816]` | `bfloat16` | `_to_copy_9`, `t_3` | `silu_and_mul` |
| 71 | `mlp` | `empty` | `call_function` | `aten.empty.memory_format` | `[4096, 17408]` | `bfloat16` | - | `mm_4`, `silu_and_mul` |
| 72 | `mlp` | `silu_and_mul` | `call_function` | `_C.silu_and_mul.default` | `-` | `-` | `mm_3`, `empty` | - |
| 73 | `mlp` | `_param_constant7` | `get_attr` | `_param_constant7` | `[5120, 17408]` | `bfloat16` | - | `t_4` |
| 74 | `mlp` | `t_4` | `call_function` | `aten.t.default` | `[17408, 5120]` | `bfloat16` | `_param_constant7` | `mm_4` |
| 75 | `mlp` | `mm_4` | `call_function` | `aten.mm.default` | `[4096, 5120]` | `bfloat16` | `empty`, `t_4` | `output` |
| 76 | `layer_output` | `output` | `output` | `output` | `-` | `-` | `add_3`, `mm_4` | - |
