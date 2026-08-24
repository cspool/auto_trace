# input6_layer62 FX Process 手工解释与张量可视化

本文件对应 `selected:04` 的 linear-attention prefill 固定输入路径：第 6 次 forward、第 62 层，`q/past/kv=105/20480/20585`。以下 9 个 process 覆盖全部 78 个 FX nodes。

### Runtime FX inputs

节点范围为 #0–#2。

**是什么**：placeholder 提供 positions `[3,105]`、hidden states `[105,5120]` 和 residual `[105,5120]`。

**为什么需要**：这是长 prompt 最后一个 105-token chunk；第 62 层需要 hidden/residual 对齐输入，而调用签名仍保留 positions。

**怎么做/计算**：#0–#2 不计算。#1/#2 被 #5 相加；#0 在这个 fixed linear-attention graph 中没有 user，所以不能把位置编码操作归入该路径。

```text
Token axis 0..104                                      Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_in [105,5120]                                Formula: H_in=sampled_hidden_states
Tensor: R_in [105,5120]                                Formula: R_in=sampled_residual
aligned tail-chunk rows                         ──▶    ┌──────────────────────────────────────────┐
                                                       │ h[t,0] ... h[t,5119]                     │  ◀── t=0..104
                                                       │ r[t,0] ... r[t,5119]                     │
                                                       └──────────────────────────────────────────┘

Position channel axis 0..2                             Token axis
                                                       0                                       104
                                                       ▲                                         ▲
Tensor: P [3,105]                                      Formula: P=sampled_positions; users(P)=empty
position placeholder                            ──▶    ┌──────────────────────────────────────────┐
                                                       │ p[0,t], p[1,t], p[2,t]                   │  ◀── preserved only
                                                       └──────────────────────────────────────────┘
```

### Input RMSNorm

节点范围为 #3–#16。

**是什么**：hidden/residual 融合后的 Gemma-style RMSNorm，以及 `[105,5120]` mixer output buffer。

**为什么需要**：GDN 两个 projection 共享 normalized tail-chunk rows；原 residual sum 同时要保留到 mixer output 之后。

**怎么做/计算**：#3/#4 读取并 detach `[5120]` weight；#5 计算 `R0=arg1_1+arg2_1`。#6 fp32 cast，#7 square，#8 Hidden mean→`[105,1]`，#9 加 `1e-6`，#10 rsqrt，#11 广播缩放。#12 weight cast，#13 weight+1，#14 应用缩放，#15 bf16 cast得 `[105,5120]`；#16 `empty_like` 分配未初始化同形 buffer。

```text
Token axis 0..104                                      Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: R0 [105,5120]                                  Formula: R0=H_in+R_in
residual fusion                                 ──▶    ┌──────────────────────────────────────────┐
                                                       │ r0[t,0] ... r0[t,5119]                   │  ◀── t=0..104
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Reduced Hidden axis
                                                       0                                         0
                                                       ▲                                         ▲
Tensor: InvRMS0 [105,1]                                Formula: 1/sqrt(mean_h(fp32(R0)^2)+1e-6)
per-token RMS                                   ──▶    ┌──────────────────────────────────────────┐
                                                       │ inv0[0] ... inv0[104]                    │  ◀── broadcast to 5120 columns
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_norm [105,5120]                              Formula: bf16(fp32(R0)*InvRMS0*(1+W0))
normalized GDN input                            ──▶    ┌──────────────────────────────────────────┐
                                                       │ h_norm[t,0] ... h_norm[t,5119]           │  ◀── output buffer has same shape
                                                       └──────────────────────────────────────────┘
```

### Attention/GDN input projections and head reshape

节点范围为 #17–#32。

**是什么**：GDN 的 `in_proj_qkvz`、`in_proj_ba`、Z head reshape、B/A contiguous copies 和 core output allocation。

**为什么需要**：opaque core 需要 mixed-QKV `[105,10240]`、B/A `[105,48]` 以及 `[105,48,128]` 输出；后续 gate 需要同形 Z。

**怎么做/计算**：#17/#18 准备 `[16384,5120]` weight，#19 得 `[105,16384]`；#20–#22 split 为 mixed-QKV `[105,10240]` 与 Z `[105,6144]`，#23 view Z `[105,48,128]`。#24/#25 准备 `[96,5120]` weight，#26 得 `[105,96]`；#27–#29 等分为 B/A `[105,48]`，#30/#31 clone为 contiguous。#32 zeros分配 `[105,48,128]`。

```text
Token axis 0..104                                      Projected-channel axis
                                                       0             10239 10240             16383
                                                       ▲                ▲ ▲                     ▲
Tensor: P_qkvz [105,16384]                             Formula: P_qkvz=H_norm@W_qkvz^T
QKV/Z partition                                 ──▶    ┌──────────────────────────┬───────────────┐
                                                       │ MIXED_QKV [T,10240]      │ Z [T,6144]    │  ◀── T=105
                                                       └──────────────────────────┴───────────────┘

Token axis 0..104                                      BA-channel axis
                                                       0                    47 48                 95
                                                       ▲                     ▲ ▲                   ▲
Tensor: P_ba [105,96]                                  Formula: P_ba=H_norm@W_ba^T=[B|A]
B/A controls                                    ──▶    ┌──────────────────────┬────────────────────┐
                                                       │ B [T,48]             │ A [T,48]           │  ◀── contiguous head scalars
                                                       └──────────────────────┴────────────────────┘

Head axis 0..47                                        Value-head dimension
                                                       0                                      127
                                                       ▲                                         ▲
Tensor: Z_heads [105,48,128]                           Formula: Z_heads=reshape(Z)
Tensor: Core_buf [105,48,128]                          Formula: Core_buf=zeros_like(Z_heads)
head-aligned tensors                            ──▶    ┌──────────────────────────────────────────┐
                                                       │ z/core[t,head,0] ... [t,head,127]        │  ◀── head=0..47
                                                       └──────────────────────────────────────────┘
```

### Gated DeltaNet recurrent core

节点范围为 #33。

**是什么**：单个 `gdn_attention_core` opaque custom-op boundary，prefix 指向 layer 62。

**为什么需要**：该边界负责运行时 GDN state mutation 与 core output；外围 FX 只提供 projections 和 output buffer。

**怎么做/计算**：#33 的 inputs 是 mixed-QKV、B clone、A clone、zero buffer 和 prefix。普通 return 无 user，后续读取被写入的 buffer。metadata 保留 `[1,3,10240]` 与 `[1,48,128,128]` entry state snapshots；内部递推、cache ownership和 kernel不在 FX DAG 中。

```text
Token axis 0..104                                      Mixed-channel axis
                                                       0                                     10239
                                                       ▲                                         ▲
Tensor: Mixed [105,10240]                              Formula: Mixed=QKV_partition(P_qkvz)
core projected rows                             ──▶    ┌──────────────────────────────────────────┐
                                                       │ mixed[t,0] ... mixed[t,10239]            │  ◀── observed opaque input
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Value-head axis
                                                       0                                       47
                                                       ▲                                         ▲
Tensor: B,A [105,48]                                   Formula: B,A=split(P_ba)
per-head controls                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ b[t,0..47] / a[t,0..47]                  │  ◀── aligned to value heads
                                                       └──────────────────────────────────────────┘

State-0 lane axis 0..2                                 State-0 channel axis
                                                       0                                     10239
                                                       ▲                                         ▲
Tensor: State0_entry [1,3,10240]                       Formula: State0_entry=sampled_external_GDN_state_tensor_0
external state tensor 0                         ──▶    ┌──────────────────────────────────────────┐
                                                       │ STATE0_LANES_0_TO_2 x CHANNELS_0_TO_10239│ ◀── observed entry slice
                                                       └──────────────────────────────────────────┘

State head axis 0..47                                  State dimension 0..127
                                                       0                                      127
                                                       ▲                                         ▲
Tensor: S_entry [1,48,128,128]                         Formula: S_entry=sampled_external_GDN_state
external state                                  ──▶    ┌──────────────────────────────────────────┐
                                                       │ STATE_HEADS_0_TO_47                      │  ◀── mutation internals opaque
                                                       └──────────────────────────────────────────┘

Head axis 0..47                                        Value-head dimension 0..127
                                                       0                                      127
                                                       ▲                                         ▲
Tensor: Core_out [105,48,128]                          Formula: Core_out=OpaqueGDN(Mixed,B,A,S_entry)
mutated output                                  ──▶    ┌──────────────────────────────────────────┐
                                                       │ core[t,head,0] ... core[t,head,127]      │  ◀── boundary output only
                                                       └──────────────────────────────────────────┘
```

### Gated DeltaNet output RMSNorm and SiLU gate

节点范围为 #34–#51。

**是什么**：core output 的 per-head RMSNorm、Z SiLU gate 与 head merge。

**为什么需要**：105×48 个 core/Z rows 必须按相同 128-dim坐标归一化和 gating，之后才能形成 6144-wide mixer rows。

**怎么做/计算**：#34 把 core view为 `[5040,128]`；#35 clone Z，#36 unsafe-view同形。#37 core fp32，#38/#39 读取并 cast `[128]` weight，#40 Z fp32。#41 square，#42 mean over 128→`[5040,1]`，#43 加 epsilon，#44 rsqrt，#45 normalize，#46 weight scaling。#47 SiLU(Z)，#48逐元素乘，#49 bf16，#50 reshape `[105,48,128]`，#51 merge `[105,6144]`。

```text
Flattened token-head row axis 0..5039                  Head dimension
                                                       0                                      127
                                                       ▲                                         ▲
Tensor: C32 [5040,128]                                 Formula: C32=fp32(reshape(Core_out))
Tensor: Z32 [5040,128]                                 Formula: Z32=fp32(reshape(Z_heads))
aligned core/Z rows                             ──▶    ┌──────────────────────────────────────────┐
                                                       │ c[r,0..127] / z[r,0..127]                │  ◀── r=t*48+head
                                                       └──────────────────────────────────────────┘

Row axis 0..5039                                       Reduced head dimension
                                                       0                                         0
                                                       ▲                                         ▲
Tensor: InvRMS_c [5040,1]                              Formula: 1/sqrt(mean_d(C32^2)+1e-6)
per-head scales                                 ──▶    ┌──────────────────────────────────────────┐
                                                       │ inv_c[0] ... inv_c[5039]                 │  ◀── broadcast over d=0..127
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Merged value channels
                                                       0                                      6143
                                                       ▲                                         ▲
Tensor: GDN_mix [105,6144]                             Formula: merge_heads(bf16(C32*InvRMS_c*W*SiLU(Z32)))
normalized gated mixer                          ──▶    ┌──────────────────────────────────────────┐
                                                       │ mix[t,0] ... mix[t,6143]                 │  ◀── 48*128 channels
                                                       └──────────────────────────────────────────┘
```

### Mixer output projection and residual

节点范围为 #52–#58。

**是什么**：6144→5120 GDN output projection、buffer copy、与 `R0` 的 residual add。

**为什么需要**：head-merged output 必须回到 model width，并接回已包含 layer-entry residual 的 stream。

**怎么做/计算**：#52/#53 准备 `[5120,6144]` weight；#54 得 `[105,5120]`，#55 copy 到 #16 buffer。#56/#57 读取并 detach下一 norm weight。#58 计算 `R_attn=projected+R0`，shape `[105,5120]`。

```text
Token axis 0..104                                      Mixer-channel axis
                                                       0                                      6143
                                                       ▲                                         ▲
Tensor: GDN_mix [105,6144]                             Formula: source=normalized_gated_GDN_heads
projection source                               ──▶    ┌──────────────────────────────────────────┐
                                                       │ mix[t,0] ... mix[t,6143]                 │  ◀── t=0..104
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: P_out [105,5120]                               Formula: P_out=GDN_mix@W_out^T
Tensor: R_attn [105,5120]                              Formula: R_attn=P_out+R0
project-and-add                                 ──▶    ┌──────────────────────────────────────────┐
                                                       │ p[t,h]+r0[t,h]=r_attn[t,h]               │  ◀── h=0..5119
                                                       └──────────────────────────────────────────┘
```

### Post-attention RMSNorm

节点范围为 #59–#68。

**是什么**：`R_attn` 上的第二个 RMSNorm，产生 MLP input。

**为什么需要**：MLP 的 34816-wide projection 要接收尺度稳定的 `[105,5120]` rows。

**怎么做/计算**：#59 fp32 cast，#60 square，#61 Hidden mean→`[105,1]`，#62 epsilon add，#63 rsqrt，#64 normalize；#65 weight cast，#66 weight+1，#67 scaling，#68 bf16 cast得 `[105,5120]`。

```text
Token axis 0..104                                      Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: R32 [105,5120]                                 Formula: R32=fp32(R_attn)
RMS source                                      ──▶    ┌──────────────────────────────────────────┐
                                                       │ r32[t,0]^2 ... r32[t,5119]^2             │  ◀── hidden reduction source
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Reduced Hidden axis
                                                       0                                         0
                                                       ▲                                         ▲
Tensor: InvRMS1 [105,1]                                Formula: 1/sqrt(mean_h(R32^2)+1e-6)
scale band                                      ──▶    ┌──────────────────────────────────────────┐
                                                       │ inv1[0] ... inv1[104]                    │  ◀── one scalar per token
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_mlp [105,5120]                               Formula: bf16(R32*InvRMS1*(1+W1))
normalized MLP rows                             ──▶    ┌──────────────────────────────────────────┐
                                                       │ h_mlp[t,0] ... h_mlp[t,5119]             │  ◀── Token x Hidden
                                                       └──────────────────────────────────────────┘
```

### Gated MLP projections

节点范围为 #69–#76。

**是什么**：dense gate/up projection、fused SiLU-product、down projection。

**为什么需要**：对每个 tail-chunk token扩展 channel并施加 gated nonlinearity，再恢复 5120 width。

**怎么做/计算**：#69/#70 准备 `[34816,5120]` weight；#71 得 `[105,34816]=[gate|up]`。#72 分配 `[105,17408]`，#73 fused boundary写入 `SiLU(gate)*up`。#74/#75 准备 `[5120,17408]` down weight，#76 得 `[105,5120]`；fused kernel不在 FX 内展开。

```text
Token axis 0..104                                      Expanded-channel axis
                                                       0                  17407 17408          34815
                                                       ▲                      ▲ ▲                  ▲
Tensor: GU [105,34816]                                 Formula: GU=H_mlp@W_gate_up^T=[GATE|UP]
expanded channels                               ──▶    ┌───────────────────────┬────────────────────┐
                                                       │ GATE [T,17408]        │ UP [T,17408]       │  ◀── paired regions
                                                       └───────────────────────┴────────────────────┘

Token axis 0..104                                      Intermediate axis
                                                       0                                     17407
                                                       ▲                                         ▲
Tensor: M [105,17408]                                  Formula: M=SiLU(GATE)*UP
nonlinear result                                ──▶    ┌──────────────────────────────────────────┐
                                                       │ m[t,j]=silu(g[t,j])*u[t,j]               │  ◀── j=0..17407
                                                       └──────────────────────────────────────────┘

Token axis 0..104                                      Hidden axis
                                                       0                                      5119
                                                       ▲                                         ▲
Tensor: H_out [105,5120]                               Formula: H_out=M@W_down^T
down projection                                 ──▶    ┌──────────────────────────────────────────┐
                                                       │ h_out[t,0] ... h_out[t,5119]             │  ◀── restored model width
                                                       └──────────────────────────────────────────┘
```

### Layer output

节点范围为 #77。

**是什么**：output 节点返回 MLP hidden 与 mixer residual。

**为什么需要**：下一层分别消费这两个 `[105,5120]` tensors。

**怎么做/计算**：#77 只打包 `(mm_4,add_4)`；没有新的 arithmetic、copy 或 state mutation。

```text
Token axis 0..104                                      Hidden axis 0..5119
                                                       ▲                     ▲
Tensor: H_out [105,5120]                               Formula: H_out=MLP_down(H_mlp)
hidden return                                   ──▶    [H_OUT_ROWS]                               ◀── tuple item 0

Tensor: R_attn [105,5120]                              Formula: R_attn=ProjectedGDN+R0
residual return                                 ──▶    [RESIDUAL_ROWS]                             ◀── tuple item 1

Tensor: LayerTuple                                     Formula: LayerTuple=(H_out,R_attn)
packaged output                                 ──▶    [(105,5120),(105,5120)]                    ◀── no new arithmetic
```
