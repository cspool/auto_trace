# input6_layer63 FX Process 手工解释与张量可视化

本文件对应 `selected:05` 的 full-attention prefill 固定输入路径：第 6 次 forward、第 63 层，`q/past/kv=105/20480/20585`。以下 10 个 process 覆盖全部 155 个 FX nodes。

### Runtime FX inputs

节点范围为 #0–#2。

**是什么**：positions `[3,105]`、hidden states `[105,5120]`、residual `[105,5120]` 三个固定输入。

**为什么需要**：长 prompt 的尾部 105-token chunk 仍要执行 residual fusion、MRoPE 和 full attention；三类输入共享 token 轴。

**怎么做/计算**：#0–#2 不做 numerical computation。#0 供 position table index；#1/#2 在 #5 逐元素相加。

```text
Token axis 0..104                                      Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_in [105,5120]                                Formula: H_in=sampled_hidden_states
Tensor: R_in [105,5120]                                Formula: R_in=sampled_residual
aligned tail rows                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ h[t,0..5119] / r[t,0..5119]              │  ◀── t=0..104
                                                       └──────────────────────────────────────────┘

Position channel axis 0..2                             Token axis
                                                       0                                       104
                                                       ▲                                         ▲
Tensor: P [3,105]                                      Formula: P=sampled_MRoPE_positions
position rows                                   ──▶    ┌──────────────────────────────────────────┐
                                                       │ p[0,t], p[1,t], p[2,t]                   │  ◀── t=0..104
                                                       └──────────────────────────────────────────┘
```

### Input RMSNorm

节点范围为 #3–#16。

**是什么**：residual add、Gemma-style RMSNorm 和 attention buffer allocation。

**为什么需要**：Q/gate/K/V projection 需要 normalized hidden，attention projection 后还要接回原 residual sum。

**怎么做/计算**：#3/#4 读取并 detach `[5120]` weight；#5 得 `R0=H_in+R_in`。#6 fp32，#7 square，#8 Hidden mean→`[105,1]`，#9 加 `1e-6`，#10 rsqrt，#11 normalize；#12 weight fp32，#13 weight+1，#14 scale，#15 bf16→`[105,5120]`。#16 仅分配同形未初始化 buffer。

```text
Token axis 0..104                                      Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: R0 [105,5120]                                  Formula: R0=H_in+R_in
residual sum                                    ──▶    ┌──────────────────────────────────────────┐
                                                       │ r0[t,0] ... r0[t,5119]                   │  ◀── aligned add
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Reduced Hidden axis
                                                       0                                         0
                                                       ▲                                         ▲
Tensor: InvRMS0 [105,1]                                Formula: 1/sqrt(mean_h(fp32(R0)^2)+1e-6)
RMS scale                                       ──▶    ┌──────────────────────────────────────────┐
                                                       │ inv0[0] ... inv0[104]                    │  ◀── broadcast to Hidden
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_norm [105,5120]                              Formula: bf16(fp32(R0)*InvRMS0*(1+W0))
normalized rows                                 ──▶    ┌──────────────────────────────────────────┐
                                                       │ h_norm[t,0] ... h_norm[t,5119]           │  ◀── shared projection input
                                                       └──────────────────────────────────────────┘
```

### Attention/GDN input projections and head reshape

节点范围为 #17–#59。

**是什么**：fused Q/gate/K/V projection、Q/gate split 与 Q/K head RMSNorm。

**为什么需要**：该层把每个 token 映射为 24 个 Q heads、4 个 KV heads和24个 output-gate heads，每头 256 dims。

**怎么做/计算**：#17/#18 准备 `[14336,5120]` weight，#19 得 `[105,14336]`；#20–#23 按 `[12288,1024,1024]` 分成 Q-gate/K/V。#24–#31 把 Q-gate view `[105,24,512]`，等分 Q/gate `[105,24,256]` 并 clone/flatten。#32–#45 对 Q 做 `[105,24,256]` per-head fp32 square→mean→epsilon→rsqrt→`(1+w)` scaling→bf16，flatten `[105,6144]`。#46–#59 对 K `[105,4,256]` 做相同链并 flatten `[105,1024]`；V 保持 `[105,1024]`。

```text
Token axis 0..104                                      Fused channel axis
                                                       0        12287 12288 13311 13312       14335
                                                       ▲            ▲ ▲         ▲ ▲               ▲
Tensor: QGKV [105,14336]                               Formula: QGKV=H_norm@W_qgkv^T
fused partition                                 ──▶    ┌──────────────────────┬──────────┬──────────┐
                                                       │ Q_GATE [T,12288]     │ K[T,1024]│ V[T,1024]│ ◀── T=105
                                                       └──────────────────────┴──────────┴──────────┘

Query-head axis 0..23                                  Head dimension
                                                       0                  255 256                 511
                                                       ▲                    ▲ ▲                     ▲
Tensor: QGate [105,24,512]                             Formula: QGate=[Q_raw|Gate]
per-head split                                  ──▶    ┌──────────────────────┬─────────────────────┐
                                                       │ Q_RAW [T,24,256]     │ GATE [T,24,256]     │  ◀── aligned head coordinates
                                                       └──────────────────────┴─────────────────────┘

Head axis Q=0..23 / K=0..3                             Head dimension
                                                       0                                      255
                                                       ▲                                         ▲
Tensor: Qn [105,24,256]                                Formula: Qn=RMSNorm_head(Q_raw)
Tensor: Kn [105,4,256]                                 Formula: Kn=RMSNorm_head(K_raw)
normalized heads                                ──▶    ┌──────────────────────────────────────────┐
                                                       │ qn[t,h,0..255] / kn[t,j,0..255]          │  ◀── h=0..23, j=0..3
                                                       └──────────────────────────────────────────┘
```

### RoPE position embedding

节点范围为 #60–#118。

**是什么**：MRoPE lookup、cos/sin feature interleave，以及 Q/K 前 64 dims 的 partial rotation。

**为什么需要**：105 new tokens 的 Q/K 要编码其 positions，同时保留每头后 192 dims。

**怎么做/计算**：#60/#61 用 `P` index `[1048576,64]` table得 `[3,105,64]`；#62–#64 split cos/sin `[3,105,32]`。#65–#74 以 channel-0 clone 为底，把 channel-1 `[1:33:3]` 的 11 列和 channel-2 `[2:30:3]` 的 10 列 copy 到 cos；#75–#84 对 sin 对称。#85–#101 将 Q `[105,24,256]` 切 `[64|192]`，64 再分 32+32，计算 `x0*c-x1*s` 与 `x1*c+x0*s`，拼回后 flatten。#102–#118 对 K `[105,4,256]` 同样处理。

```text
Position channel axis 0..2                             Table feature axis
                                                       0                 31 32                63
                                                       ▲                   ▲ ▲                   ▲
Tensor: CS_raw [3,105,64]                              Formula: CS_raw=RotaryTable[P]=[COS_raw|SIN_raw]
position lookup                                 ──▶    ┌─────────────────────┬─────────────────────┐
                                                       │ COS_RAW [3,T,32]    │ SIN_RAW [3,T,32]    │  ◀── T=105
                                                       └─────────────────────┴─────────────────────┘

Token axis 0..104                                      Rotary scalar axis
                                                       0                                      31
                                                       ▲                                         ▲
Tensor: Cos,Sin [105,32]                               Formula: interleave(channel0,channel1[11],channel2[10])
MRoPE scalars                                   ──▶    ┌──────────────────────────────────────────┐
                                                       │ cos[t,0..31] / sin[t,0..31]              │  ◀── head-broadcast values
                                                       └──────────────────────────────────────────┘

Head axis Q=0..23 / K=0..3                             Head dimension
                                                       0          31 32       63 64            255
                                                       ▲            ▲ ▲         ▲ ▲                ▲
Tensor: QK_rot [T,heads,256]                           Formula: [x0*c-x1*s|x1*c+x0*s|x_pass]
partial rotation                                ──▶    ┌─────────────┬─────────────┬────────────────┐
                                                       │ ROT_FIRST32 │ ROT_SECOND32│ PASS_192       │  ◀── d=0..255
                                                       └─────────────┴─────────────┴────────────────┘
```

### KV-cache update and unified full attention

节点范围为 #119–#125。

**是什么**：output allocation、Q/K/V views、opaque cache update 和 opaque unified attention。

**为什么需要**：105 K/V rows 要接到 20480-token past，得到 20585 KV length；105 Q rows随后从 unified backend 取得 context。

**怎么做/计算**：#119 分配 `[105,6144]`；#120/#121 view Q/output `[105,24,256]`，#122/#123 view K/V `[105,4,256]`。#124 以 layer-63 prefix 更新 external cache，返回 `[0]` dependency；entry snapshot 为 `[2,28,784,4,256]`。#125 写 output。内部 QK、mask、softmax、V reduction 与 ROCm/DCU kernels未展开。

```text
Token axis 0..104                                      Head dimension
                                                       0                                      255
                                                       ▲                                         ▲
Tensor: Q [105,24,256]                                 Formula: Q=reshape(Q_rot)
Tensor: K,V [105,4,256]                                Formula: K=reshape(K_rot); V=reshape(V_proj)
current tail heads                              ──▶    ┌──────────────────────────────────────────┐
                                                       │ Q_HEADS_0_TO_23 / KV_HEADS_0_TO_3        │  ◀── t=0..104
                                                       └──────────────────────────────────────────┘

Snapshot-local block axis 0..27                        Last dimensions KV-head x Head-dim
                                                       0                                      255
                                                       ▲                                         ▲
Tensor: Cache_entry [2,28,784,4,256]                   Formula: Cache_next=OpaqueCacheUpdate(Cache_entry,K,V)
entry cache state                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ ACTIVE_IDS: 0,4..30; 784 x 4 x 256       │  ◀── mutation internals opaque
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Merged query-head channels
                                                       0                                      6143
                                                       ▲                                         ▲
Tensor: A_out [105,6144]                               Formula: A_out=OpaqueUnifiedAttention(Q,K,V,Cache_next)
attention context                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ context[t,0] ... context[t,6143]         │  ◀── writable observed output
                                                       └──────────────────────────────────────────┘
```

### Attention output gate and hidden reshape

节点范围为 #126–#128。

**是什么**：attention output head merge 与 sigmoid output gate。

**为什么需要**：gate 与 6144 context channels逐元素对齐，控制 full-attention mixer output。

**怎么做/计算**：#126 把 `[105,24,256]` output view成 `[105,6144]`；#127 sigmoid gate `[105,6144]`；#128逐元素乘，输出 `[105,6144]`。

```text
Token axis 0..104                                      Mixer-channel axis
                                                       0                                      6143
                                                       ▲                                         ▲
Tensor: A_flat [105,6144]                              Formula: A_flat=merge_heads(A_out)
context rows                                    ──▶    ┌──────────────────────────────────────────┐
                                                       │ a[t,0] ... a[t,6143]                     │  ◀── 24*256 channels
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Mixer-channel axis
                                                       0                                      6143
                                                       ▲                                         ▲
Tensor: Gate01 [105,6144]                              Formula: Gate01=sigmoid(Gate_flat)
gate rows                                       ──▶    ┌──────────────────────────────────────────┐
                                                       │ g[t,0] ... g[t,6143]                     │  ◀── same grid as A_flat
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Mixer-channel axis
                                                       0                                      6143
                                                       ▲                                         ▲
Tensor: A_gated [105,6144]                             Formula: A_gated=A_flat*Gate01
gated context                                   ──▶    ┌──────────────────────────────────────────┐
                                                       │ a_g[t,j]=a[t,j]*g[t,j], j=0..6143        │  ◀── elementwise
                                                       └──────────────────────────────────────────┘
```

### Mixer output projection and residual

节点范围为 #129–#135。

**是什么**：6144→5120 projection、buffer write 和 residual fusion。

**为什么需要**：gated context 要恢复 model width 并与 `R0` 合并。

**怎么做/计算**：#129/#130 准备 `[5120,6144]` weight；#131 得 `[105,5120]`，#132 copy 到 buffer。#133/#134 读取并 detach下一 norm weight；#135 计算 `R_attn=projected+R0`。

```text
Token axis 0..104                                      Mixer-channel axis
                                                       0                                      6143
                                                       ▲                                         ▲
Tensor: A_gated [105,6144]                             Formula: source=A_flat*Gate01
projection source                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ a_g[t,0] ... a_g[t,6143]                 │  ◀── source rows
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: P_attn [105,5120]                              Formula: P_attn=A_gated@W_out^T
Tensor: R_attn [105,5120]                              Formula: R_attn=P_attn+R0
project-and-add                                 ──▶    ┌──────────────────────────────────────────┐
                                                       │ p[t,h]+r0[t,h]=r_attn[t,h]               │  ◀── h=0..5119
                                                       └──────────────────────────────────────────┘
```

### Post-attention RMSNorm

节点范围为 #136–#145。

**是什么**：`R_attn` 上的第二个 Gemma-style RMSNorm。

**为什么需要**：dense MLP 要接收 normalized bf16 tail rows，residual stream则保持原值。

**怎么做/计算**：#136 fp32，#137 square，#138 Hidden mean→`[105,1]`，#139 epsilon，#140 rsqrt，#141 normalize；#142 weight fp32，#143 weight+1，#144 scale，#145 bf16→`[105,5120]`。

```text
Token axis 0..104                                      Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: R32 [105,5120]                                 Formula: R32=fp32(R_attn)
RMS source                                      ──▶    ┌──────────────────────────────────────────┐
                                                       │ r32[t,0]^2 ... r32[t,5119]^2             │  ◀── Hidden reduction
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Reduced Hidden axis
                                                       0                                         0
                                                       ▲                                         ▲
Tensor: InvRMS1 [105,1]                                Formula: 1/sqrt(mean_h(R32^2)+1e-6)
per-token scale                                 ──▶    ┌──────────────────────────────────────────┐
                                                       │ inv1[0] ... inv1[104]                    │  ◀── one scalar per row
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_mlp [105,5120]                               Formula: bf16(R32*InvRMS1*(1+W1))
MLP input                                       ──▶    ┌──────────────────────────────────────────┐
                                                       │ h_mlp[t,0] ... h_mlp[t,5119]             │  ◀── normalized rows
                                                       └──────────────────────────────────────────┘
```

### Gated MLP projections

节点范围为 #146–#153。

**是什么**：gate/up expansion、fused SiLU-product 和 down projection。

**为什么需要**：在每个 token 内扩展至 17408 intermediate features并恢复 5120 hidden。

**怎么做/计算**：#146/#147 准备 `[34816,5120]` weight；#148 得 `[105,34816]=[gate|up]`。#149 分配 `[105,17408]`，#150 fused boundary写 `SiLU(gate)*up`。#151/#152 准备 down weight，#153 得 `[105,5120]`；kernel内部未展开。

```text
Token axis 0..104                                      Expanded-channel axis
                                                       0                  17407 17408          34815
                                                       ▲                      ▲ ▲                  ▲
Tensor: GU [105,34816]                                 Formula: GU=H_mlp@W_gate_up^T=[GATE|UP]
expanded projection                             ──▶    ┌───────────────────────┬────────────────────┐
                                                       │ GATE [T,17408]        │ UP [T,17408]       │  ◀── aligned regions
                                                       └───────────────────────┴────────────────────┘

Token axis 0..104                                      Intermediate axis
                                                       0                                     17407
                                                       ▲                                         ▲
Tensor: M [105,17408]                                  Formula: M=SiLU(GATE)*UP
nonlinear product                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ m[t,j]=silu(g[t,j])*u[t,j]               │  ◀── j=0..17407
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_out [105,5120]                               Formula: H_out=M@W_down^T
down projection                                 ──▶    ┌──────────────────────────────────────────┐
                                                       │ h_out[t,0] ... h_out[t,5119]             │  ◀── model-width result
                                                       └──────────────────────────────────────────┘
```

### Layer output

节点范围为 #154。

**是什么**：hidden/residual tuple packaging。

**为什么需要**：下一层需要 MLP output 与 residual stream。

**怎么做/计算**：#154 返回 `(mm_3,add_9)`，两个 tensors均为 `[105,5120]`，没有新增计算。

```text
Token axis 0..104                                      Hidden axis 0..5119
                                                       ▲                     ▲
Tensor: H_out [105,5120]                               Formula: H_out=MLP_down(H_mlp)
hidden return                                   ──▶    [H_OUT_ROWS]                               ◀── tuple item 0

Tensor: R_attn [105,5120]                              Formula: R_attn=ProjectedAttention+R0
residual return                                 ──▶    [RESIDUAL_ROWS]                             ◀── tuple item 1

Tensor: LayerTuple                                     Formula: LayerTuple=(H_out,R_attn)
packaged output                                 ──▶    [(105,5120),(105,5120)]                    ◀── no new arithmetic
```
