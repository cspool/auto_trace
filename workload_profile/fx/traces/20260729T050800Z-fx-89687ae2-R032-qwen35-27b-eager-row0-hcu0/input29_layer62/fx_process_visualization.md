# input29_layer62 FX Process 手工解释与张量可视化

本文件对应 `selected:08` 的 linear-attention decode 固定输入路径：第 29 次 forward、第 62 层，`q/past/kv=1/20607/20608`。以下 9 个 process 覆盖全部 75 个 FX nodes。

### Runtime FX inputs

节点范围为 #0–#2。

**是什么**：positions `[3,1]`、single-token hidden `[1,5120]` 和 residual `[1,5120]`。

**为什么需要**：late decode 的 layer 62 已有 residual stream；hidden/residual 需要融合，positions虽保留但该 fixed linear graph不使用。

**怎么做/计算**：#0–#2 是无 arithmetic 的 placeholders。#1/#2 输入 #5；#0 users为空。

```text
Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_in [1,5120]                                  Formula: H_in=sampled_decode_hidden
Tensor: R_in [1,5120]                                  Formula: R_in=sampled_decode_residual
aligned current rows                            ──▶    ┌──────────────────────────────────────────┐
                                                       │ h[0,0..5119] / r[0,0..5119]              │  ◀── current token
                                                       └──────────────────────────────────────────┘

Position channel axis 0..2                             Token axis 0..0
                                                       ▲                   ▲
Tensor: P [3,1]                                        Formula: P=sampled_positions; users(P)=empty
position placeholder                            ──▶    ┌──────────────────────────────────────────┐
                                                       │ p[0,0], p[1,0], p[2,0]                   │  ◀── not consumed here
                                                       └──────────────────────────────────────────┘
```

### Input RMSNorm

节点范围为 #3–#16。

**是什么**：entry residual add、single-row Gemma-style RMSNorm和 output buffer allocation。

**为什么需要**：GDN projections需要 normalized row，且 `R0` 要保留到 output projection之后。

**怎么做/计算**：#3/#4 读取/detach `[5120]` weight；#5 得 `R0=H_in+R_in`。#6 fp32，#7 square，#8 mean→`[1,1]`，#9 epsilon，#10 rsqrt，#11 normalize；#12 weight fp32，#13 +1，#14 scale，#15 bf16→`[1,5120]`。#16 分配同形 buffer。

```text
Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: R0 [1,5120]                                    Formula: R0=H_in+R_in
entry residual                                  ──▶    ┌──────────────────────────────────────────┐
                                                       │ r0[0,h]=h[0,h]+r[0,h], h=0..5119         │  ◀── aligned add
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Reduced Hidden axis 0..0
                                                       ▲                     ▲
Tensor: InvRMS0 [1,1]                                  Formula: 1/sqrt(mean_h(fp32(R0)^2)+1e-6)
single RMS scale                                ──▶    ┌──────────────────────────────────────────┐
                                                       │ inv0[0]                                  │  ◀── broadcast over Hidden
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_norm [1,5120]                                Formula: bf16(fp32(R0)*InvRMS0*(1+W0))
normalized GDN row                              ──▶    ┌──────────────────────────────────────────┐
                                                       │ h_norm[0,0] ... h_norm[0,5119]           │  ◀── shared projection source
                                                       └──────────────────────────────────────────┘
```

### Attention/GDN input projections and head reshape

节点范围为 #17–#30。

**是什么**：single-token QKVZ/BA projections、Z head view和zero output allocation。

**为什么需要**：GDN core的 fixed boundary需要 `[1,10240]` mixed-QKV、B/A `[1,48]` 和 output `[1,48,128]`，Z用于后续 gating。

**怎么做/计算**：#17/#18 准备 `[16384,5120]` weight，#19 得 `[1,16384]`；#20–#23 split `[10240|6144]`并 view Z `[1,48,128]`。#24/#25 准备 `[96,5120]` weight，#26 得 `[1,96]`；#27–#29 split B/A `[1,48]`。decode graph不做 contiguous clones。#30 zeros分配 `[1,48,128]`。

```text
Token axis 0..0                                        Projected-channel axis
                                                       0             10239 10240             16383
                                                       ▲                ▲ ▲                     ▲
Tensor: P_qkvz [1,16384]                               Formula: P_qkvz=H_norm@W_qkvz^T
projected partition                             ──▶    ┌──────────────────────────┬───────────────┐
                                                       │ MIXED_QKV [1,10240]      │ Z [1,6144]    │  ◀── current token
                                                       └──────────────────────────┴───────────────┘

Token axis 0..0                                        BA-channel axis
                                                       0                    47 48                 95
                                                       ▲                     ▲ ▲                   ▲
Tensor: P_ba [1,96]                                    Formula: P_ba=H_norm@W_ba^T=[B|A]
direct BA rows                                  ──▶    ┌──────────────────────┬────────────────────┐
                                                       │ B [1,48]             │ A [1,48]           │  ◀── no clone
                                                       └──────────────────────┴────────────────────┘

Head axis 0..47                                        Value-head dimension
                                                       0                                      127
                                                       ▲                                         ▲
Tensor: Z_heads [1,48,128]                             Formula: Z_heads=reshape(Z)
Tensor: Core_buf [1,48,128]                            Formula: Core_buf=zeros_like(Z_heads)
aligned head rows                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ z/core[0,head,0..127]                    │  ◀── head=0..47
                                                       └──────────────────────────────────────────┘
```

### Gated DeltaNet recurrent core

节点范围为 #31。

**是什么**：layer-62 decode 的 opaque GDN core mutation boundary。

**为什么需要**：它把当前 token projection与 recurrent state结合并写 48-head core output。

**怎么做/计算**：#31 接收 mixed-QKV、direct B/A、zero buffer和prefix。后续读取 mutated buffer；external snapshots为 `[1,3,10240]`、`[1,48,128,128]`。FX没有内部 recurrence、state update或 kernel nodes。

```text
Token axis 0..0                                        Mixed-channel axis
                                                       0                                     10239
                                                       ▲                                         ▲
Tensor: Mixed [1,10240]                                Formula: Mixed=QKV_partition(P_qkvz)
current projected row                           ──▶    ┌──────────────────────────────────────────┐
                                                       │ mixed[0,0] ... mixed[0,10239]            │  ◀── opaque input
                                                       └──────────────────────────────────────────┘

State-0 lane axis 0..2                                 State-0 channel axis
                                                       0                                     10239
                                                       ▲                                         ▲
Tensor: State0_entry [1,3,10240]                       Formula: State0_entry=sampled_external_GDN_state_tensor_0
external state tensor 0                         ──▶    ┌──────────────────────────────────────────┐
                                                       │ STATE0_LANES_0_TO_2 x CHANNELS_0_TO_10239│ ◀── observed entry slice
                                                       └──────────────────────────────────────────┘

Value-head axis 0..47                                  State dimension 0..127
                                                       0                                      127
                                                       ▲                                         ▲
Tensor: S_entry [1,48,128,128]                         Formula: S_entry=sampled_external_GDN_state
late-decode state                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ STATE_HEADS_0_TO_47                      │  ◀── mutation internals opaque
                                                       └──────────────────────────────────────────┘

Head axis 0..47                                        Value-head dimension 0..127
                                                       0                                      127
                                                       ▲                                         ▲
Tensor: Core_out [1,48,128]                            Formula: Core_out=OpaqueGDN(Mixed,B,A,S_entry)
mutated output                                  ──▶    ┌──────────────────────────────────────────┐
                                                       │ core[0,head,0] ... core[0,head,127]      │  ◀── boundary output
                                                       └──────────────────────────────────────────┘
```

### Gated DeltaNet output RMSNorm and SiLU gate

节点范围为 #32–#48。

**是什么**：48 head rows的 core RMSNorm、Z SiLU gate与head merge。

**为什么需要**：core/Z在 `[48,128]` grid逐坐标融合后才能形成 `[1,6144]` mixer row。

**怎么做/计算**：#32/#33 view core/Z为 `[48,128]`。#34 core fp32；#35/#36 weight读取/cast；#37 Z fp32。#38 square，#39 mean→`[48,1]`，#40 epsilon，#41 rsqrt，#42 normalize，#43 weight scaling；#44 SiLU(Z)，#45乘，#46 bf16，#47 reshape `[1,48,128]`，#48 merge `[1,6144]`。

```text
Head-row axis 0..47                                    Head dimension
                                                       0                                      127
                                                       ▲                                         ▲
Tensor: C32 [48,128]                                   Formula: C32=fp32(reshape(Core_out))
Tensor: Z32 [48,128]                                   Formula: Z32=fp32(reshape(Z_heads))
aligned core/Z                                  ──▶    ┌──────────────────────────────────────────┐
                                                       │ c[head,0..127] / z[head,0..127]          │  ◀── one row per head
                                                       └──────────────────────────────────────────┘

Head-row axis 0..47                                    Reduced dimension 0..0
                                                       ▲                     ▲
Tensor: InvRMS_c [48,1]                                Formula: 1/sqrt(mean_d(C32^2)+1e-6)
RMS scales                                      ──▶    ┌──────────────────────────────────────────┐
                                                       │ inv_c[0] ... inv_c[47]                   │  ◀── broadcast over 128 dims
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Merged value channels
                                                       0                                      6143
                                                       ▲                                         ▲
Tensor: GDN_mix [1,6144]                               Formula: merge_heads(bf16(C32*InvRMS_c*W*SiLU(Z32)))
gated mixer row                                 ──▶    ┌──────────────────────────────────────────┐
                                                       │ mix[0,0] ... mix[0,6143]                 │  ◀── 48*128 channels
                                                       └──────────────────────────────────────────┘
```

### Mixer output projection and residual

节点范围为 #49–#55。

**是什么**：GDN 6144→5120 projection、buffer copy和与已融合 `R0` 的 add。

**为什么需要**：linear mixer output回到 model width后必须接回完整 residual stream。

**怎么做/计算**：#49/#50 准备 `[5120,6144]` weight；#51 得 `[1,5120]`，#52 copy到 buffer。#53/#54 读取/detach下一 norm weight；#55 得 `R_attn=P_out+R0`。

```text
Token axis 0..0                                        Mixer-channel axis
                                                       0                                      6143
                                                       ▲                                         ▲
Tensor: GDN_mix [1,6144]                               Formula: source=normalized_gated_GDN_heads
projection source                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ mix[0,0] ... mix[0,6143]                 │  ◀── one mixer row
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: P_out [1,5120]                                 Formula: P_out=GDN_mix@W_out^T
Tensor: R_attn [1,5120]                                Formula: R_attn=P_out+R0
project-and-add                                 ──▶    ┌──────────────────────────────────────────┐
                                                       │ p[0,h]+r0[0,h]=r_attn[0,h]               │  ◀── h=0..5119
                                                       └──────────────────────────────────────────┘
```

### Post-attention RMSNorm

节点范围为 #56–#65。

**是什么**：late-decode residual row上的第二个 RMSNorm。

**为什么需要**：MLP需要 normalized bf16 input，residual保持给 tuple return。

**怎么做/计算**：#56 fp32，#57 square，#58 mean→`[1,1]`，#59 epsilon，#60 rsqrt，#61 normalize；#62 weight fp32，#63 +1，#64 scale，#65 bf16。

```text
Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: R32 [1,5120]                                   Formula: R32=fp32(R_attn)
RMS input                                       ──▶    ┌──────────────────────────────────────────┐
                                                       │ r32[0,0]^2 ... r32[0,5119]^2             │  ◀── reduction source
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Reduced Hidden axis 0..0
                                                       ▲                     ▲
Tensor: InvRMS1 [1,1]                                  Formula: 1/sqrt(mean_h(R32^2)+1e-6)
single scale                                    ──▶    ┌──────────────────────────────────────────┐
                                                       │ inv1[0]                                  │  ◀── broadcast over Hidden
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_mlp [1,5120]                                 Formula: bf16(R32*InvRMS1*(1+W1))
normalized MLP row                              ──▶    ┌──────────────────────────────────────────┐
                                                       │ h_mlp[0,0] ... h_mlp[0,5119]             │  ◀── current token
                                                       └──────────────────────────────────────────┘
```

### Gated MLP projections

节点范围为 #66–#73。

**是什么**：single-token dense gated MLP。

**为什么需要**：扩展/非线性/降维提供 token-wise channel transformation。

**怎么做/计算**：#66/#67 准备 `[34816,5120]` weight；#68 得 `[1,34816]=[gate|up]`。#69 分配 `[1,17408]`，#70 fused boundary写 `SiLU(gate)*up`。#71/#72 准备 down weight，#73 得 `[1,5120]`。

```text
Token axis 0..0                                        Expanded-channel axis
                                                       0                  17407 17408          34815
                                                       ▲                      ▲ ▲                  ▲
Tensor: GU [1,34816]                                   Formula: GU=H_mlp@W_gate_up^T=[GATE|UP]
expanded channels                               ──▶    ┌───────────────────────┬────────────────────┐
                                                       │ GATE [1,17408]        │ UP [1,17408]       │  ◀── paired features
                                                       └───────────────────────┴────────────────────┘

Token axis 0..0                                        Intermediate axis
                                                       0                                     17407
                                                       ▲                                         ▲
Tensor: M [1,17408]                                    Formula: M=SiLU(GATE)*UP
gated nonlinearity                              ──▶    ┌──────────────────────────────────────────┐
                                                       │ m[0,j]=silu(g[0,j])*u[0,j]               │  ◀── j=0..17407
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_out [1,5120]                                 Formula: H_out=M@W_down^T
hidden output                                   ──▶    ┌──────────────────────────────────────────┐
                                                       │ h_out[0,0] ... h_out[0,5119]             │  ◀── restored width
                                                       └──────────────────────────────────────────┘
```

### Layer output

节点范围为 #74。

**是什么**：late-decode hidden/residual tuple。

**为什么需要**：下一 layer需要 MLP output与 residual stream。

**怎么做/计算**：#74 返回 `(mm_4,add_4)`，两者均 `[1,5120]`；没有新增计算。

```text
Token axis 0..0                                        Hidden axis 0..5119
                                                       ▲                     ▲
Tensor: H_out [1,5120]                                 Formula: H_out=MLP_down(H_mlp)
hidden return                                   ──▶    [H_OUT_ROW]                                ◀── tuple item 0

Tensor: R_attn [1,5120]                                Formula: R_attn=ProjectedGDN+R0
residual return                                 ──▶    [RESIDUAL_ROW]                              ◀── tuple item 1

Tensor: LayerTuple                                     Formula: LayerTuple=(H_out,R_attn)
packaged output                                 ──▶    [(1,5120),(1,5120)]                        ◀── no new arithmetic
```
