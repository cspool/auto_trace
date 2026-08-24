# input2_layer31 FX Process 手工解释与张量可视化

本文件对应 `selected:03` 的 full-attention prefill 固定输入路径：第 2 次 forward、第 31 层，`q/past/kv=4096/4096/8192`。以下 10 个 process 逐一覆盖本事件的 155 个 FX nodes。

### Runtime FX inputs

节点范围为 #0–#2。

**是什么**：placeholder 提供 positions `[3,4096]`、hidden states `[4096,5120]` 和 residual `[4096,5120]`。

**为什么需要**：第 31 层在第二个 4096-token prefill chunk 上工作；hidden/residual 必须按 token 对齐，positions 则驱动本 chunk 的 MRoPE lookup。

**怎么做/计算**：#0–#2 本身没有 arithmetic。#0 被 position index 使用；#1/#2 被 #5 逐元素相加。它们只证明这一固定采样调用的输入，不代表其他 chunk 或 batch。

```text
Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: H_in [4096,5120]                              Formula: H_in=sampled_hidden_states
Tensor: R_in [4096,5120]                              Formula: R_in=sampled_residual
aligned input rows                             ──▶    ┌──────────────────────────────────────────┐
                                                      │ h[t,0] ... h[t,5119]                     │  ◀── hidden row t
                                                      │ r[t,0] ... r[t,5119]                     │  ◀── residual row t
                                                      └──────────────────────────────────────────┘

Position channel axis 0..2                            Token axis
                                                      0                                      4095
                                                      ▲                                         ▲
Tensor: P [3,4096]                                    Formula: P=sampled_positions_for_chunk_2
position rows                                  ──▶    ┌──────────────────────────────────────────┐
                                                      │ p[0,t], p[1,t], p[2,t]                   │  ◀── t=0..4095
                                                      └──────────────────────────────────────────┘
```

### Input RMSNorm

节点范围为 #3–#16。

**是什么**：residual add 后展开的 Gemma-style RMSNorm，并分配 attention 输出缓冲区。

**为什么需要**：Q/gate/K/V projection 共享稳定的 bf16 input；未归一化 residual sum 要跨越 attention 保留下来。

**怎么做/计算**：#3/#4 读取并 detach `[5120]` weight；#5 计算 `R0=arg1_1+arg2_1`。#6 转 fp32，#7 square，#8 对 Hidden mean 成 `[4096,1]`，#9 加 `1e-6`，#10 `rsqrt`，#11 广播缩放。#12 把 weight 转 fp32，#13 加 1，#14 应用权重，#15 转回 bf16；#16 `empty_like` 仅分配 `[4096,5120]` buffer。

```text
Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: R0 [4096,5120]                                Formula: R0=H_in+R_in
residual fusion                                ──▶    ┌──────────────────────────────────────────┐
                                                      │ r0[t,0] ... r0[t,5119]                   │  ◀── aligned elementwise sum
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Reduced Hidden axis
                                                      0                                         0
                                                      ▲                                         ▲
Tensor: InvRMS0 [4096,1]                              Formula: 1/sqrt(mean_h(fp32(R0)^2)+1e-6)
RMS scalar band                                ──▶    ┌──────────────────────────────────────────┐
                                                      │ inv0[0] ... inv0[4095]                   │  ◀── one scale per token
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: H_norm [4096,5120]                            Formula: bf16(fp32(R0)*InvRMS0*(1+W0))
normalized projection input                    ──▶    ┌──────────────────────────────────────────┐
                                                      │ h_norm[t,0] ... h_norm[t,5119]           │  ◀── output buffer has same shape
                                                      └──────────────────────────────────────────┘
```

### Attention/GDN input projections and head reshape

节点范围为 #17–#59。

**是什么**：fused Q/gate/K/V projection、Q/gate 拆分，以及 Q/K 的 256-wide per-head RMSNorm。

**为什么需要**：该 full-attention 层需要 24 Q heads、4 KV heads 和一个与 Q 同形的 output gate。

**怎么做/计算**：#17/#18 准备 `[14336,5120]` projection weight，#19 得 `[4096,14336]`；#20 按 `[12288,1024,1024]` split，#21–#23 是 Q-gate/K/V。#24 view Q-gate 为 `[4096,24,512]`，#25–#27 二分成 Q 与 gate `[4096,24,256]`；#28–#31 clone/flatten 两者。#32 恢复 Q heads；#33–#45 对 Q 执行 weight detach、fp32 cast、square、mean over 256、epsilon、rsqrt、weight `(1+w)`、bf16 cast 和 flatten。#46 恢复 K `[4096,4,256]`；#47–#59 对 K 执行相同链。V 保持 `[4096,1024]`，稍后只 view。

```text
Token axis 0..4095                                    Fused channel axis
                                                      0        12287 12288 13311 13312       14335
                                                      ▲            ▲ ▲         ▲ ▲               ▲
Tensor: QGKV [4096,14336]                             Formula: QGKV=H_norm@W_qgkv^T
channel partition                              ──▶    ┌──────────────────────┬──────────┬──────────┐
                                                      │ Q_GATE [T,12288]     │ K[T,1024]│ V[T,1024]│ ◀── exact split sizes
                                                      └──────────────────────┴──────────┴──────────┘

Query-head axis 0..23                                 Head dimension
                                                      0                  255 256                 511
                                                      ▲                    ▲ ▲                     ▲
Tensor: QGate [4096,24,512]                           Formula: QGate=[Q_raw|Gate]
Q/gate split                                   ──▶    ┌──────────────────────┬─────────────────────┐
                                                      │ Q_RAW [T,24,256]     │ GATE [T,24,256]     │  ◀── same head index
                                                      └──────────────────────┴─────────────────────┘

Head axis Q=0..23 / K=0..3                            Head dimension
                                                      0                                      255
                                                      ▲                                         ▲
Tensor: Qn [4096,24,256]                              Formula: Qn=RMSNorm_head(Q_raw)
Tensor: Kn [4096,4,256]                               Formula: Kn=RMSNorm_head(K_raw)
normalized heads                               ──▶    ┌──────────────────────────────────────────┐
                                                      │ qn[t,h,0] ... qn[t,h,255]                │  ◀── h=0..23
                                                      │ kn[t,j,0] ... kn[t,j,255]                │  ◀── j=0..3
                                                      └──────────────────────────────────────────┘
```

### RoPE position embedding

节点范围为 #60–#118。

**是什么**：三通道 positions 的 MRoPE table lookup 与 Q/K 前 64 head dims 的 rotate-half 组合。

**为什么需要**：第二 prefill chunk 的 Q/K 必须携带其真实位置；仅 64 rotary dims 被改变，192 dims 直通。

**怎么做/计算**：#60/#61 从 `[1048576,64]` table 按 `P` 取得 `[3,4096,64]`；#62–#64 split 为 cos/sin `[3,4096,32]`。#65–#74 对 cos 选 channel 0 并 clone，再把 channel 1 的 `[1:33:3]` 11 列和 channel 2 的 `[2:30:3]` 10 列 copy 到对应 feature positions；#75–#84 对 sin 对称执行。#85–#101 把 Q view 为 `[4096,24,256]`，切 `[64|192]`，将 64 再分 `[32|32]`，以 `x0*c-x1*s`、`x1*c+x0*s` 组合并拼回 pass-through，flatten 为 `[4096,6144]`。#102–#118 对 K `[4096,4,256]` 做同样计算，得到 `[4096,1024]`。

```text
Position channel axis 0..2                            Table feature axis
                                                      0                 31 32                63
                                                      ▲                   ▲ ▲                   ▲
Tensor: CS_raw [3,4096,64]                            Formula: CS_raw=RotaryTable[P]=[COS_raw|SIN_raw]
indexed rotary values                          ──▶    ┌─────────────────────┬─────────────────────┐
                                                      │ COS_RAW [3,T,32]    │ SIN_RAW [3,T,32]    │  ◀── T=4096
                                                      └─────────────────────┴─────────────────────┘

Token axis 0..4095                                    Rotary scalar axis
                                                      0                                      31
                                                      ▲                                         ▲
Tensor: Cos,Sin [4096,32]                             Formula: interleave(channel0,channel1[11],channel2[10])
MRoPE scalar rows                              ──▶    ┌──────────────────────────────────────────┐
                                                      │ cos[t,0..31] / sin[t,0..31]              │  ◀── broadcast across heads
                                                      └──────────────────────────────────────────┘

Head axis Q=0..23 / K=0..3                            Head dimension
                                                      0          31 32       63 64            255
                                                      ▲            ▲ ▲         ▲ ▲                ▲
Tensor: QK_rot [T,heads,256]                          Formula: [x0*c-x1*s|x1*c+x0*s|x_pass]
partial rotary heads                           ──▶    ┌─────────────┬─────────────┬────────────────┐
                                                      │ ROT_FIRST32 │ ROT_SECOND32│ PASS_192       │  ◀── d=0..255
                                                      └─────────────┴─────────────┴────────────────┘
```

### KV-cache update and unified full attention

节点范围为 #119–#125。

**是什么**：Q/K/V head views、attention output allocation、layer-31 KV-cache mutation 和 unified-attention opaque boundary。

**为什么需要**：本 chunk 的 4096 K/V rows 要追加到已有 4096-token context，形成 `kv_len=8192`，随后为 4096 Q rows生成 context。

**怎么做/计算**：#119 分配 `[4096,6144]`；#120/#121 view Q 和 output 为 `[4096,24,256]`，#122/#123 view K/V 为 `[4096,4,256]`。#124 以 K/V 和 layer-31 prefix 更新外部 cache，并产生 `[0]` dependency token；入口 active cache snapshot 是 `[2,12,784,4,256]`。#125 以 Q/K/V、output、prefix、#124 token调用 unified attention并写 output。QK scores、mask、softmax 和 value aggregation 未作为 FX nodes 展开。

```text
Token axis 0..4095                                    Head dimension
                                                      0                                      255
                                                      ▲                                         ▲
Tensor: Q [4096,24,256]                               Formula: Q=reshape(Q_rot)
Tensor: K,V [4096,4,256]                              Formula: K=reshape(K_rot); V=reshape(V_proj)
current chunk heads                            ──▶    ┌──────────────────────────────────────────┐
                                                      │ Q_HEADS_0_TO_23 / KV_HEADS_0_TO_3        │  ◀── shared token order
                                                      │ q/k/v[t,head,0] ... [t,head,255]         │
                                                      └──────────────────────────────────────────┘

Snapshot-local block axis 0..11                       Last dimensions KV-head x Head-dim
                                                      0                                      255
                                                      ▲                                         ▲
Tensor: Cache_entry [2,12,784,4,256]                  Formula: Cache_next=OpaqueCacheUpdate(Cache_entry,K,V)
entry cache state                              ──▶    ┌──────────────────────────────────────────┐
                                                      │ ACTIVE_IDS: 0,4..14; 784 x 4 x 256       │  ◀── mutation internals opaque
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Merged query-head channels
                                                      0                                      6143
                                                      ▲                                         ▲
Tensor: A_out [4096,6144]                             Formula: A_out=OpaqueUnifiedAttention(Q,K,V,Cache_next)
attention output                               ──▶    ┌──────────────────────────────────────────┐
                                                      │ context[t,0] ... context[t,6143]         │  ◀── observed writable output
                                                      └──────────────────────────────────────────┘
```

### Attention output gate and hidden reshape

节点范围为 #126–#128。

**是什么**：attention context 的 24-head merge 与 sigmoid gate。

**为什么需要**：projection 时保留的 gate 与每个 attention output channel 对齐，用来调节 6144-wide context。

**怎么做/计算**：#126 view output buffer 为 `[4096,6144]`；#127 对 gate flat tensor做 sigmoid；#128 逐坐标相乘成 `[4096,6144]`。

```text
Token axis 0..4095                                    Mixer-channel axis
                                                      0                                      6143
                                                      ▲                                         ▲
Tensor: A_flat [4096,6144]                            Formula: A_flat=merge_heads(A_out)
context rows                                   ──▶    ┌──────────────────────────────────────────┐
                                                      │ a[t,0] ... a[t,6143]                     │  ◀── source context
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Mixer-channel axis
                                                      0                                      6143
                                                      ▲                                         ▲
Tensor: Gate01 [4096,6144]                            Formula: Gate01=sigmoid(Gate_flat)
gate rows                                      ──▶    ┌──────────────────────────────────────────┐
                                                      │ g[t,0] ... g[t,6143]                     │  ◀── values in (0,1)
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Mixer-channel axis
                                                      0                                      6143
                                                      ▲                                         ▲
Tensor: A_gated [4096,6144]                           Formula: A_gated=A_flat*Gate01
gated result                                   ──▶    ┌──────────────────────────────────────────┐
                                                      │ a_g[t,j]=a[t,j]*g[t,j], j=0..6143        │  ◀── elementwise relation
                                                      └──────────────────────────────────────────┘
```

### Mixer output projection and residual

节点范围为 #129–#135。

**是什么**：6144→5120 output projection、buffer copy、residual add。

**为什么需要**：full-attention context 要恢复 model width，并与 attention 前的 `R0` 汇合。

**怎么做/计算**：#129/#130 准备 `[5120,6144]` weight；#131 矩阵乘得 `[4096,5120]`，#132 copy 到预分配 buffer。#133/#134 读取并 detach post-attention norm weight。#135 计算 `R_attn=projected+R0`。

```text
Token axis 0..4095                                    Mixer-channel axis
                                                      0                                      6143
                                                      ▲                                         ▲
Tensor: A_gated [4096,6144]                           Formula: source=A_flat*Gate01
projection source                              ──▶    ┌──────────────────────────────────────────┐
                                                      │ a_g[t,0] ... a_g[t,6143]                 │  ◀── 6144 input channels
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: P_attn [4096,5120]                            Formula: P_attn=A_gated@W_out^T
Tensor: R_attn [4096,5120]                            Formula: R_attn=P_attn+R0
project-and-add                                ──▶    ┌──────────────────────────────────────────┐
                                                      │ p[t,h] + r0[t,h] = r_attn[t,h]           │  ◀── h=0..5119
                                                      └──────────────────────────────────────────┘
```

### Post-attention RMSNorm

节点范围为 #136–#145。

**是什么**：`R_attn` 上展开的第二个 RMSNorm。

**为什么需要**：MLP 接收 normalized bf16 rows，而 residual stream 保持未归一化。

**怎么做/计算**：#136 fp32 cast；#137 square；#138 Hidden mean→`[4096,1]`；#139 加 epsilon；#140 rsqrt；#141 广播归一化；#142 weight cast；#143 weight+1；#144 scaling；#145 bf16 cast得到 `[4096,5120]`。

```text
Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: R32 [4096,5120]                               Formula: R32=fp32(R_attn)
RMS source                                     ──▶    ┌──────────────────────────────────────────┐
                                                      │ r32[t,0]^2 ... r32[t,5119]^2             │  ◀── hidden reduction
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Reduced Hidden axis
                                                      0                                         0
                                                      ▲                                         ▲
Tensor: InvRMS1 [4096,1]                              Formula: 1/sqrt(mean_h(R32^2)+1e-6)
scale band                                     ──▶    ┌──────────────────────────────────────────┐
                                                      │ inv1[0] ... inv1[4095]                   │  ◀── one scalar per token
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: H_mlp [4096,5120]                             Formula: bf16(R32*InvRMS1*(1+W1))
MLP input                                      ──▶    ┌──────────────────────────────────────────┐
                                                      │ h_mlp[t,0] ... h_mlp[t,5119]             │  ◀── normalized rows
                                                      └──────────────────────────────────────────┘
```

### Gated MLP projections

节点范围为 #146–#153。

**是什么**：dense gate/up expansion、fused SiLU-product 和 down projection。

**为什么需要**：它提供 token-wise channel mixing 与非线性，并返回 5120 hidden width。

**怎么做/计算**：#146/#147 准备 `[34816,5120]` weight，#148 得 `[4096,34816]=[gate|up]`。#149 分配 `[4096,17408]`；#150 fused boundary写入 `SiLU(gate)*up`。#151/#152 准备 down weight，#153 得 `[4096,5120]`；fused kernel 内部未展开。

```text
Token axis 0..4095                                    Expanded-channel axis
                                                      0                  17407 17408          34815
                                                      ▲                      ▲ ▲                  ▲
Tensor: GU [4096,34816]                               Formula: GU=H_mlp@W_gate_up^T=[GATE|UP]
expanded channels                              ──▶    ┌───────────────────────┬────────────────────┐
                                                      │ GATE [T,17408]        │ UP [T,17408]       │  ◀── paired features
                                                      └───────────────────────┴────────────────────┘

Token axis 0..4095                                    Intermediate axis
                                                      0                                     17407
                                                      ▲                                         ▲
Tensor: M [4096,17408]                                Formula: M=SiLU(GATE)*UP
nonlinear rows                                 ──▶    ┌──────────────────────────────────────────┐
                                                      │ m[t,j]=silu(g[t,j])*u[t,j]               │  ◀── j=0..17407
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: H_out [4096,5120]                             Formula: H_out=M@W_down^T
layer hidden output                            ──▶    ┌──────────────────────────────────────────┐
                                                      │ h_out[t,0] ... h_out[t,5119]             │  ◀── down-projected rows
                                                      └──────────────────────────────────────────┘
```

### Layer output

节点范围为 #154。

**是什么**：output 节点返回 hidden/residual tuple。

**为什么需要**：下一层分别消费本层 MLP output 和 residual stream。

**怎么做/计算**：#154 只打包 `(mm_3,add_9)`，即两个 `[4096,5120]` tensors；没有额外数值计算。

```text
Token axis 0..4095                                    Hidden axis 0..5119
                                                      ▲                     ▲
Tensor: H_out [4096,5120]                             Formula: H_out=MLP_down(H_mlp)
hidden return                                  ──▶    [H_OUT_ROWS]                               ◀── tuple item 0

Tensor: R_attn [4096,5120]                            Formula: R_attn=ProjectedAttention+R0
residual return                                ──▶    [RESIDUAL_ROWS]                             ◀── tuple item 1

Tensor: LayerTuple                                    Formula: LayerTuple=(H_out,R_attn)
packaged output                                ──▶    [(4096,5120),(4096,5120)]                  ◀── no new arithmetic
```
