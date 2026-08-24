# input7_layer0 FX Process 手工解释与张量可视化

本文件对应 `selected:06` 的 linear-attention decode 固定输入路径：第 7 次 forward、第 0 层，`q/past/kv=1/20585/20586`。以下 9 个 process 覆盖全部 74 个 FX nodes。

### Runtime FX inputs

节点范围为 #0–#2。

**是什么**：positions `[3,1]`、单 token hidden `[1,5120]` 与本次为 `None` 的 residual。

**为什么需要**：decode 每次只推进一个 token；首层尚未形成 residual，positions 保留在调用签名中但此 linear fixed path 不读取它。

**怎么做/计算**：#0/#1/#2 都是 placeholders。#1 被 RMSNorm 和后续 residual add 使用；#0/#2 users 为空。

```text
Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_in [1,5120]                                  Formula: H_in=sampled_decode_hidden
single decode row                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ h[0,0] ... h[0,5119]                     │  ◀── only current token
                                                       └──────────────────────────────────────────┘

Position channel axis 0..2                             Token axis 0..0
                                                       ▲                   ▲
Tensor: P [3,1]                                        Formula: P=sampled_positions; users(P)=empty
position placeholder                            ──▶    ┌──────────────────────────────────────────┐
                                                       │ p[0,0], p[1,0], p[2,0]                   │  ◀── not consumed in this graph
                                                       └──────────────────────────────────────────┘

Tensor: R_in                                           Formula: R_in=None
residual placeholder                           ──▶    [NONE_RESIDUAL]                              ◀── no entry residual tensor
```

### Input RMSNorm

节点范围为 #3–#15。

**是什么**：单 token hidden 上的 Gemma-style RMSNorm与 `[1,5120]` output buffer allocation。

**为什么需要**：decode GDN projections 仍需要 normalized hidden；buffer 供 output projection 写入。

**怎么做/计算**：#3/#4 读取并 detach `[5120]` weight；#5 fp32 cast，#6 square，#7 Hidden mean→`[1,1]`，#8 加 `1e-6`，#9 rsqrt，#10 normalize；#11 weight fp32，#12 weight+1，#13 scale，#14 bf16→`[1,5120]`。#15 `empty_like` 只分配同形 buffer。

```text
Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: X32 [1,5120]                                   Formula: X32=fp32(H_in)
single RMS row                                  ──▶    ┌──────────────────────────────────────────┐
                                                       │ x[0,0]^2 ... x[0,5119]^2                 │  ◀── reduction source
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Reduced Hidden axis 0..0
                                                       ▲                     ▲
Tensor: InvRMS0 [1,1]                                  Formula: 1/sqrt(mean_h(X32^2)+1e-6)
single scale                                    ──▶    ┌──────────────────────────────────────────┐
                                                       │ inv0[0]                                  │  ◀── broadcast to 5120 dims
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_norm [1,5120]                                Formula: bf16(X32*InvRMS0*(1+W0))
normalized decode row                           ──▶    ┌──────────────────────────────────────────┐
                                                       │ h_norm[0,0] ... h_norm[0,5119]           │  ◀── projection input
                                                       └──────────────────────────────────────────┘
```

### Attention/GDN input projections and head reshape

节点范围为 #16–#29。

**是什么**：单-token QKVZ/BA projections、Z head view 和 zero core buffer。

**为什么需要**：decode GDN core 需要 mixed-QKV `[1,10240]`、48 B/A scalars与 `[1,48,128]` 可写 output；Z 同形用于 gating。

**怎么做/计算**：#16/#17 准备 `[16384,5120]` weight，#18 得 `[1,16384]`；#19–#22 split `[10240|6144]`并把 Z view `[1,48,128]`。#23/#24 准备 `[96,5120]` weight，#25 得 `[1,96]`；#26–#28 等分为 B/A `[1,48]`。与 prefill graph 不同，这里没有 clone，#30 直接读取这两个 views。#29 zeros分配 `[1,48,128]`。

```text
Token axis 0..0                                        Projected-channel axis
                                                       0             10239 10240             16383
                                                       ▲                ▲ ▲                     ▲
Tensor: P_qkvz [1,16384]                               Formula: P_qkvz=H_norm@W_qkvz^T
QKV/Z split                                     ──▶    ┌──────────────────────────┬───────────────┐
                                                       │ MIXED_QKV [1,10240]      │ Z [1,6144]    │  ◀── current token
                                                       └──────────────────────────┴───────────────┘

Token axis 0..0                                        BA-channel axis
                                                       0                    47 48                 95
                                                       ▲                     ▲ ▲                   ▲
Tensor: P_ba [1,96]                                    Formula: P_ba=H_norm@W_ba^T=[B|A]
direct BA views                                 ──▶    ┌──────────────────────┬────────────────────┐
                                                       │ B [1,48]             │ A [1,48]           │  ◀── no clone in this graph
                                                       └──────────────────────┴────────────────────┘

Head axis 0..47                                        Value-head dimension
                                                       0                                      127
                                                       ▲                                         ▲
Tensor: Z_heads [1,48,128]                             Formula: Z_heads=reshape(Z)
Tensor: Core_buf [1,48,128]                            Formula: Core_buf=zeros_like(Z_heads)
head-aligned rows                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ z/core[0,head,0] ... [0,head,127]        │  ◀── head=0..47
                                                       └──────────────────────────────────────────┘
```

### Gated DeltaNet recurrent core

节点范围为 #30。

**是什么**：decode 的 opaque `gdn_attention_core` mutation boundary。

**为什么需要**：它把当前 token与进入 decode 的 GDN recurrent state结合，并写 48-head output。

**怎么做/计算**：#30 接收 mixed-QKV `[1,10240]`、未经 clone 的 B/A `[1,48]`、zero buffer `[1,48,128]` 和 layer-0 prefix。后续读取被写入的 buffer。外部 snapshots 是 `[1,3,10240]` 与 `[1,48,128,128]`；FX 不暴露内部 state update 或 kernel。

```text
Token axis 0..0                                        Mixed-channel axis
                                                       0                                     10239
                                                       ▲                                         ▲
Tensor: Mixed [1,10240]                                Formula: Mixed=QKV_partition(P_qkvz)
decode projected row                            ──▶    ┌──────────────────────────────────────────┐
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
entry recurrent state                           ──▶    ┌──────────────────────────────────────────┐
                                                       │ STATE_HEADS_0_TO_47                      │  ◀── mutation internals opaque
                                                       └──────────────────────────────────────────┘

Head axis 0..47                                        Value-head dimension 0..127
                                                       0                                      127
                                                       ▲                                         ▲
Tensor: Core_out [1,48,128]                            Formula: Core_out=OpaqueGDN(Mixed,B,A,S_entry)
mutated decode output                           ──▶    ┌──────────────────────────────────────────┐
                                                       │ core[0,head,0] ... core[0,head,127]      │  ◀── boundary output only
                                                       └──────────────────────────────────────────┘
```

### Gated DeltaNet output RMSNorm and SiLU gate

节点范围为 #31–#47。

**是什么**：48 core rows 的 per-head RMSNorm、Z SiLU gate 和 head merge。

**为什么需要**：单 token 的 48 heads 仍要独立规范化 128 dims，并由相同 head/dim坐标的 Z gate调节。

**怎么做/计算**：#31/#32 将 core/Z view为 `[48,128]`。#33 core fp32；#34/#35 weight读取/cast；#36 Z fp32。#37 square，#38 mean over 128→`[48,1]`，#39 epsilon，#40 rsqrt，#41 normalize，#42 weight scale；#43 SiLU(Z)，#44逐元素乘，#45 bf16，#46恢复 `[1,48,128]`，#47 merge `[1,6144]`。

```text
Flattened head-row axis 0..47                          Head dimension
                                                       0                                      127
                                                       ▲                                         ▲
Tensor: C32 [48,128]                                   Formula: C32=fp32(reshape(Core_out))
Tensor: Z32 [48,128]                                   Formula: Z32=fp32(reshape(Z_heads))
aligned head rows                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ c[head,0..127] / z[head,0..127]          │  ◀── one row per head
                                                       └──────────────────────────────────────────┘

Head-row axis 0..47                                    Reduced dimension 0..0
                                                       ▲                     ▲
Tensor: InvRMS_c [48,1]                                Formula: 1/sqrt(mean_d(C32^2)+1e-6)
head scales                                     ──▶    ┌──────────────────────────────────────────┐
                                                       │ inv_c[0] ... inv_c[47]                   │  ◀── broadcast over 128 dims
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Merged value channels
                                                       0                                      6143
                                                       ▲                                         ▲
Tensor: GDN_mix [1,6144]                               Formula: merge_heads(bf16(C32*InvRMS_c*W*SiLU(Z32)))
gated decode mixer                              ──▶    ┌──────────────────────────────────────────┐
                                                       │ mix[0,0] ... mix[0,6143]                 │  ◀── 48*128 channels
                                                       └──────────────────────────────────────────┘
```

### Mixer output projection and residual

节点范围为 #48–#54。

**是什么**：6144→5120 projection、buffer copy 与首层 hidden residual建立。

**为什么需要**：GDN channels 要回到 model width；因为 entry residual=None，base residual 是 `H_in` 本身。

**怎么做/计算**：#48/#49 准备 `[5120,6144]` weight；#50 得 `[1,5120]`，#51 copy进 buffer。#52/#53 读取并 detach下一 norm weight；#54 得 `R_attn=projected+arg1_1`。

```text
Token axis 0..0                                        Mixer-channel axis
                                                       0                                      6143
                                                       ▲                                         ▲
Tensor: GDN_mix [1,6144]                               Formula: source=normalized_gated_GDN_heads
projection source                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ mix[0,0] ... mix[0,6143]                 │  ◀── single mixer row
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: P_out [1,5120]                                 Formula: P_out=GDN_mix@W_out^T
Tensor: R_attn [1,5120]                                Formula: R_attn=P_out+H_in
project-and-add                                 ──▶    ┌──────────────────────────────────────────┐
                                                       │ p[0,h]+h[0,h]=r_attn[0,h]                │  ◀── h=0..5119
                                                       └──────────────────────────────────────────┘
```

### Post-attention RMSNorm

节点范围为 #55–#64。

**是什么**：单 residual row 上的第二个 RMSNorm。

**为什么需要**：MLP 需要 normalized `[1,5120]` input，同时 `R_attn` 作为 residual保留。

**怎么做/计算**：#55 fp32，#56 square，#57 Hidden mean→`[1,1]`，#58 epsilon，#59 rsqrt，#60 normalize；#61 weight cast，#62 weight+1，#63 scale，#64 bf16。

```text
Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: R32 [1,5120]                                   Formula: R32=fp32(R_attn)
RMS source                                      ──▶    ┌──────────────────────────────────────────┐
                                                       │ r32[0,0]^2 ... r32[0,5119]^2             │  ◀── Hidden reduction
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Reduced Hidden axis 0..0
                                                       ▲                     ▲
Tensor: InvRMS1 [1,1]                                  Formula: 1/sqrt(mean_h(R32^2)+1e-6)
single post scale                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ inv1[0]                                  │  ◀── broadcast over Hidden
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_mlp [1,5120]                                 Formula: bf16(R32*InvRMS1*(1+W1))
MLP decode row                                  ──▶    ┌──────────────────────────────────────────┐
                                                       │ h_mlp[0,0] ... h_mlp[0,5119]             │  ◀── normalized input
                                                       └──────────────────────────────────────────┘
```

### Gated MLP projections

节点范围为 #65–#72。

**是什么**：single-token dense gated MLP。

**为什么需要**：对当前 decode row做 channel expansion和非线性后返回 5120 hidden。

**怎么做/计算**：#65/#66 准备 `[34816,5120]` weight；#67 得 `[1,34816]=[gate|up]`。#68 分配 `[1,17408]`，#69 fused boundary写 `SiLU(gate)*up`。#70/#71 准备 down weight，#72 得 `[1,5120]`；fused internals未展开。

```text
Token axis 0..0                                        Expanded-channel axis
                                                       0                  17407 17408          34815
                                                       ▲                      ▲ ▲                  ▲
Tensor: GU [1,34816]                                   Formula: GU=H_mlp@W_gate_up^T=[GATE|UP]
expanded decode row                             ──▶    ┌───────────────────────┬────────────────────┐
                                                       │ GATE [1,17408]        │ UP [1,17408]       │  ◀── paired features
                                                       └───────────────────────┴────────────────────┘

Token axis 0..0                                        Intermediate axis
                                                       0                                     17407
                                                       ▲                                         ▲
Tensor: M [1,17408]                                    Formula: M=SiLU(GATE)*UP
nonlinear product                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ m[0,j]=silu(g[0,j])*u[0,j]               │  ◀── j=0..17407
                                                       └──────────────────────────────────────────┘

Token axis 0..0                                        Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_out [1,5120]                                 Formula: H_out=M@W_down^T
decode hidden output                            ──▶    ┌──────────────────────────────────────────┐
                                                       │ h_out[0,0] ... h_out[0,5119]             │  ◀── restored width
                                                       └──────────────────────────────────────────┘
```

### Layer output

节点范围为 #73。

**是什么**：单-token hidden/residual tuple。

**为什么需要**：下一层分别消费 MLP output 和 residual stream。

**怎么做/计算**：#73 返回 `(mm_4,add_3)`，两者均 `[1,5120]`，不新增 arithmetic。

```text
Token axis 0..0                                        Hidden axis 0..5119
                                                       ▲                     ▲
Tensor: H_out [1,5120]                                 Formula: H_out=MLP_down(H_mlp)
hidden return                                   ──▶    [H_OUT_ROW]                                ◀── tuple item 0

Tensor: R_attn [1,5120]                                Formula: R_attn=ProjectedGDN+H_in
residual return                                 ──▶    [RESIDUAL_ROW]                              ◀── tuple item 1

Tensor: LayerTuple                                     Formula: LayerTuple=(H_out,R_attn)
packaged output                                 ──▶    [(1,5120),(1,5120)]                        ◀── no new arithmetic
```
