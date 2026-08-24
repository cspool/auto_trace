# input29_layer63 FX Process 手工解释与张量可视化

本文件对应 `selected:09` 的 full-attention decode 固定输入路径：第 29 次 forward、第 63 层，`q/past/kv=1/20607/20608`。以下 10 个 process 覆盖全部 155 个 FX nodes。

### Runtime FX inputs

节点范围为 #0–#2。

**是什么**：late-decode positions `[3,1]`、hidden `[1,5120]` 和 residual `[1,5120]`。

**为什么需要**：当前单 token 在最末 decoder layer 仍要做 residual fusion、MRoPE 与 full attention。

**怎么做/计算**：#0–#2 只暴露固定 tensors；#0输入 position lookup，#1/#2在 #5 对齐相加。

```text
Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_in [1,5120]                                  Formula: H_in=sampled_late_decode_hidden
Tensor: R_in [1,5120]                                  Formula: R_in=sampled_late_decode_residual
aligned current rows                            ──▶    ┌──────────────────────────────────────────┐
                                                       │ h[0,0..5119] / r[0,0..5119]              │  ◀── token coordinate 0
                                                       └──────────────────────────────────────────┘

Position channel axis 0..2                             Token axis 0..0
                                                       ▲                   ▲
Tensor: P [3,1]                                        Formula: P=sampled_MRoPE_positions
position triplet                                ──▶    ┌──────────────────────────────────────────┐
                                                       │ p[0,0], p[1,0], p[2,0]                   │  ◀── current position channels
                                                       └──────────────────────────────────────────┘
```

### Input RMSNorm

节点范围为 #3–#16。

**是什么**：entry residual add、Gemma-style RMSNorm和 attention output buffer allocation。

**为什么需要**：Q/gate/K/V projection需要 normalized row；attention后 residual必须接回 `R0`。

**怎么做/计算**：#3/#4 读取/detach `[5120]` weight；#5 得 `R0=H_in+R_in`。#6 fp32，#7 square，#8 Hidden mean→`[1,1]`，#9 epsilon，#10 rsqrt，#11 normalize；#12 weight fp32，#13 +1，#14 scale，#15 bf16。#16分配 `[1,5120]` 未初始化 buffer。

```text
Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: R0 [1,5120]                                    Formula: R0=H_in+R_in
entry residual                                  ──▶    ┌──────────────────────────────────────────┐
                                                       │ r0[0,h]=h[0,h]+r[0,h], h=0..5119         │  ◀── elementwise sum
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Reduced Hidden axis 0..0
                                                       ▲                     ▲
Tensor: InvRMS0 [1,1]                                  Formula: 1/sqrt(mean_h(fp32(R0)^2)+1e-6)
single RMS scale                                ──▶    ┌──────────────────────────────────────────┐
                                                       │ inv0[0]                                  │  ◀── broadcast to 5120 dims
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_norm [1,5120]                                Formula: bf16(fp32(R0)*InvRMS0*(1+W0))
normalized projection row                       ──▶    ┌──────────────────────────────────────────┐
                                                       │ h_norm[0,0] ... h_norm[0,5119]           │  ◀── shared QGKV input
                                                       └──────────────────────────────────────────┘
```

### Attention/GDN input projections and head reshape

节点范围为 #17–#59。

**是什么**：single-token Q/gate/K/V fused projection、Q/gate partition与 Q/K per-head RMSNorm。

**为什么需要**：unified backend需要 24 Q heads、4 K heads、4 V heads；24-head gate在 output side使用。

**怎么做/计算**：#17/#18 准备 `[14336,5120]` weight，#19 得 `[1,14336]`；#20–#23 split `[12288,1024,1024]`。#24–#31 view Q-gate `[1,24,512]`，split Q/gate `[1,24,256]`，clone并 flatten。#32–#45 对 Q按每头256 dims做 fp32 square、mean、epsilon、rsqrt、`(1+w)` scaling、bf16与flatten。#46–#59 对 K `[1,4,256]` 做同一链。V `[1,1024]`只在 attention boundary前 view。

```text
Token axis 0..0                                        Fused channel axis
                                                       0        12287 12288 13311 13312       14335
                                                       ▲            ▲ ▲         ▲ ▲               ▲
Tensor: QGKV [1,14336]                                 Formula: QGKV=H_norm@W_qgkv^T
fused partition                                 ──▶    ┌──────────────────────┬──────────┬──────────┐
                                                       │ Q_GATE [1,12288]     │ K[1,1024]│ V[1,1024]│ ◀── exact split
                                                       └──────────────────────┴──────────┴──────────┘

Query-head axis 0..23                                  Head dimension
                                                       0                  255 256                 511
                                                       ▲                    ▲ ▲                     ▲
Tensor: QGate [1,24,512]                               Formula: QGate=[Q_raw|Gate]
Q/gate head split                               ──▶    ┌──────────────────────┬─────────────────────┐
                                                       │ Q_RAW [1,24,256]     │ GATE [1,24,256]     │  ◀── matched heads
                                                       └──────────────────────┴─────────────────────┘

Head axis Q=0..23 / K=0..3                             Head dimension
                                                       0                                      255
                                                       ▲                                         ▲
Tensor: Qn [1,24,256]                                  Formula: Qn=RMSNorm_head(Q_raw)
Tensor: Kn [1,4,256]                                   Formula: Kn=RMSNorm_head(K_raw)
normalized Q/K                                  ──▶    ┌──────────────────────────────────────────┐
                                                       │ qn[0,h,0..255] / kn[0,j,0..255]          │  ◀── h=0..23, j=0..3
                                                       └──────────────────────────────────────────┘
```

### RoPE position embedding

节点范围为 #60–#118。

**是什么**：late-decode MRoPE table lookup、cos/sin channel interleave和 Q/K partial rotation。

**为什么需要**：当前 token 的 position要进入 Q/K前64 dims；后192 dims保持原样。

**怎么做/计算**：#60/#61 按 `P` 从 `[1048576,64]` table取得 `[3,1,64]`；#62–#64 得 cos/sin `[3,1,32]`。#65–#74 对 cos选择 channel0并 clone，再copy channel1 `[1:33:3]` 11列与 channel2 `[2:30:3]` 10列；#75–#84 对 sin对称。#85–#101 对 Q `[1,24,256]` 切64+192，把64切32+32并算 `x0*c-x1*s`、`x1*c+x0*s`，再拼回；#102–#118 对 K `[1,4,256]`同样处理。

```text
Position channel axis 0..2                             Table feature axis
                                                       0                 31 32                63
                                                       ▲                   ▲ ▲                   ▲
Tensor: CS_raw [3,1,64]                                Formula: CS_raw=RotaryTable[P]=[COS_raw|SIN_raw]
position lookup                                 ──▶    ┌─────────────────────┬─────────────────────┐
                                                       │ COS_RAW [3,1,32]    │ SIN_RAW [3,1,32]    │  ◀── current token
                                                       └─────────────────────┴─────────────────────┘

Token axis 0..0                                        Rotary scalar axis
                                                       0                                      31
                                                       ▲                                         ▲
Tensor: Cos,Sin [1,32]                                 Formula: interleave(channel0,channel1[11],channel2[10])
interleaved scalars                             ──▶    ┌──────────────────────────────────────────┐
                                                       │ cos[0,0..31] / sin[0,0..31]              │  ◀── broadcast to Q/K heads
                                                       └──────────────────────────────────────────┘

Head axis Q=0..23 / K=0..3                             Head dimension
                                                       0          31 32       63 64            255
                                                       ▲            ▲ ▲         ▲ ▲                ▲
Tensor: QK_rot [1,heads,256]                           Formula: [x0*c-x1*s|x1*c+x0*s|x_pass]
partial rotated heads                           ──▶    ┌─────────────┬─────────────┬────────────────┐
                                                       │ ROT_FIRST32 │ ROT_SECOND32│ PASS_192       │  ◀── d=0..255
                                                       └─────────────┴─────────────┴────────────────┘
```

### KV-cache update and unified full attention

节点范围为 #119–#125。

**是什么**：Q/K/V views、output allocation、layer-63 cache mutation与 unified-attention opaque call。

**为什么需要**：当前 K/V把 cache从20607推进至20608，当前 Q获得 one-token context。

**怎么做/计算**：#119 分配 `[1,6144]`；#120/#121 view Q/output `[1,24,256]`，#122/#123 view K/V `[1,4,256]`。#124 以 layer-63 prefix更新 external cache并返回 `[0]` dependency；snapshot为 `[2,28,784,4,256]`。#125写 output。内部 scores、mask、softmax、V aggregation与 kernels均未暴露。

```text
Token axis 0..0                                        Head dimension
                                                       0                                      255
                                                       ▲                                         ▲
Tensor: Q [1,24,256]                                   Formula: Q=reshape(Q_rot)
Tensor: K,V [1,4,256]                                  Formula: K=reshape(K_rot); V=reshape(V_proj)
current token heads                             ──▶    ┌──────────────────────────────────────────┐
                                                       │ Q_HEADS_0_TO_23 / KV_HEADS_0_TO_3        │  ◀── coordinate 0
                                                       └──────────────────────────────────────────┘

Snapshot-local block axis 0..27                        Last dimensions KV-head x Head-dim
                                                       0                                      255
                                                       ▲                                         ▲
Tensor: Cache_entry [2,28,784,4,256]                   Formula: Cache_next=OpaqueCacheUpdate(Cache_entry,K,V)
late entry cache                                ──▶    ┌──────────────────────────────────────────┐
                                                       │ ACTIVE_IDS: 0,4..30; 784 x 4 x 256       │  ◀── internal mutation opaque
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Merged query-head channels
                                                       0                                      6143
                                                       ▲                                         ▲
Tensor: A_out [1,6144]                                 Formula: A_out=OpaqueUnifiedAttention(Q,K,V,Cache_next)
observed context                                ──▶    ┌──────────────────────────────────────────┐
                                                       │ context[0,0] ... context[0,6143]         │  ◀── output mutation boundary
                                                       └──────────────────────────────────────────┘
```

### Attention output gate and hidden reshape

节点范围为 #126–#128。

**是什么**：one-token context merge与 output sigmoid gate。

**为什么需要**：每个 6144-wide context channel都与 projection-derived gate对齐。

**怎么做/计算**：#126 view output `[1,6144]`；#127 sigmoid gate `[1,6144]`；#128逐元素相乘。

```text
Token axis 0..0                                        Mixer-channel axis
                                                       0                                      6143
                                                       ▲                                         ▲
Tensor: A_flat [1,6144]                                Formula: A_flat=merge_heads(A_out)
context row                                     ──▶    ┌──────────────────────────────────────────┐
                                                       │ a[0,0] ... a[0,6143]                     │  ◀── 24*256 channels
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Mixer-channel axis
                                                       0                                      6143
                                                       ▲                                         ▲
Tensor: Gate01 [1,6144]                                Formula: Gate01=sigmoid(Gate_flat)
gate row                                        ──▶    ┌──────────────────────────────────────────┐
                                                       │ g[0,0] ... g[0,6143]                     │  ◀── same coordinates
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Mixer-channel axis
                                                       0                                      6143
                                                       ▲                                         ▲
Tensor: A_gated [1,6144]                               Formula: A_gated=A_flat*Gate01
gated output                                    ──▶    ┌──────────────────────────────────────────┐
                                                       │ a_g[0,j]=a[0,j]*g[0,j], j=0..6143        │  ◀── elementwise
                                                       └──────────────────────────────────────────┘
```

### Mixer output projection and residual

节点范围为 #129–#135。

**是什么**：attention 6144→5120 projection、buffer copy和 residual add。

**为什么需要**：context返回 model width并接回 `R0`，形成 MLP前 residual。

**怎么做/计算**：#129/#130 准备 `[5120,6144]` weight；#131 得 `[1,5120]`，#132 copy进 buffer。#133/#134 读取/detach下一 norm weight；#135 得 `R_attn=P_attn+R0`。

```text
Token axis 0..0                                        Mixer-channel axis
                                                       0                                      6143
                                                       ▲                                         ▲
Tensor: A_gated [1,6144]                               Formula: source=A_flat*Gate01
projection source                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ a_g[0,0] ... a_g[0,6143]                 │  ◀── source context
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: P_attn [1,5120]                                Formula: P_attn=A_gated@W_out^T
Tensor: R_attn [1,5120]                                Formula: R_attn=P_attn+R0
project-and-add                                 ──▶    ┌──────────────────────────────────────────┐
                                                       │ p[0,h]+r0[0,h]=r_attn[0,h]               │  ◀── h=0..5119
                                                       └──────────────────────────────────────────┘
```

### Post-attention RMSNorm

节点范围为 #136–#145。

**是什么**：late full-attention residual row上的 second RMSNorm。

**为什么需要**：MLP需要 normalized bf16 current row。

**怎么做/计算**：#136 fp32，#137 square，#138 mean→`[1,1]`，#139 epsilon，#140 rsqrt，#141 normalize；#142 weight fp32，#143 +1，#144 scale，#145 bf16。

```text
Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: R32 [1,5120]                                   Formula: R32=fp32(R_attn)
RMS source                                      ──▶    ┌──────────────────────────────────────────┐
                                                       │ r32[0,0]^2 ... r32[0,5119]^2             │  ◀── Hidden reduction source
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
normalized row                                  ──▶    ┌──────────────────────────────────────────┐
                                                       │ h_mlp[0,0] ... h_mlp[0,5119]             │  ◀── MLP input
                                                       └──────────────────────────────────────────┘
```

### Gated MLP projections

节点范围为 #146–#153。

**是什么**：single-token gate/up expansion、fused SiLU-product和down projection。

**为什么需要**：为当前 token提供 nonlinear channel transformation并恢复5120 width。

**怎么做/计算**：#146/#147 准备 `[34816,5120]` weight；#148 得 `[1,34816]=[gate|up]`。#149 分配 `[1,17408]`，#150 fused boundary写 `SiLU(gate)*up`。#151/#152 准备 down weight，#153 得 `[1,5120]`。

```text
Token axis 0..0                                        Expanded-channel axis
                                                       0                  17407 17408          34815
                                                       ▲                      ▲ ▲                  ▲
Tensor: GU [1,34816]                                   Formula: GU=H_mlp@W_gate_up^T=[GATE|UP]
expanded current row                            ──▶    ┌───────────────────────┬────────────────────┐
                                                       │ GATE [1,17408]        │ UP [1,17408]       │  ◀── paired channels
                                                       └───────────────────────┴────────────────────┘

Token axis 0..0                                        Intermediate axis
                                                       0                                     17407
                                                       ▲                                         ▲
Tensor: M [1,17408]                                    Formula: M=SiLU(GATE)*UP
nonlinear result                                ──▶    ┌──────────────────────────────────────────┐
                                                       │ m[0,j]=silu(g[0,j])*u[0,j]               │  ◀── j=0..17407
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_out [1,5120]                                 Formula: H_out=M@W_down^T
final-layer hidden                              ──▶    ┌──────────────────────────────────────────┐
                                                       │ h_out[0,0] ... h_out[0,5119]             │  ◀── restored width
                                                       └──────────────────────────────────────────┘
```

### Layer output

节点范围为 #154。

**是什么**：late-decode hidden/residual tuple。

**为什么需要**：decoder caller分别取得 MLP output和 residual stream。

**怎么做/计算**：#154 返回 `(mm_3,add_9)`，均为 `[1,5120]`；没有新 arithmetic。

```text
Token axis 0..0                                        Hidden axis 0..5119
                                                       ▲                     ▲
Tensor: H_out [1,5120]                                 Formula: H_out=MLP_down(H_mlp)
hidden return                                   ──▶    [H_OUT_ROW]                                ◀── tuple item 0

Tensor: R_attn [1,5120]                                Formula: R_attn=ProjectedAttention+R0
residual return                                 ──▶    [RESIDUAL_ROW]                              ◀── tuple item 1

Tensor: LayerTuple                                     Formula: LayerTuple=(H_out,R_attn)
packaged output                                 ──▶    [(1,5120),(1,5120)]                        ◀── no new arithmetic
```
