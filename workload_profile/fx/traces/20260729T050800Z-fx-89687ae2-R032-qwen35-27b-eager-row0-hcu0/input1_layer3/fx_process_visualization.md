# input1_layer3 FX Process 手工解释与张量可视化

本文件对应 `selected:02` 的 full-attention prefill 固定输入路径：第 1 次 forward、第 3 层，`q/past/kv=4096/0/4096`。以下 10 个 process 与重建文件顺序一致；字符图按 observed shape 压缩。

### Runtime FX inputs

节点范围为 #0–#2。

**是什么**：三个 placeholder 分别暴露 MRoPE positions `arg0_1=[3,4096]`、hidden states `arg1_1=[4096,5120]` 和 residual `arg2_1=[4096,5120]`。

**为什么需要**：full-attention 路径既要把 hidden 与已有 residual 融合，又要用三通道 position ids 查询 rotary table；三者必须保留真实采样调用的 token 对齐关系。

**怎么做/计算**：#0–#2 不做数值运算。#0 后续输入 position-table index；#1/#2 进入逐元素 residual add。所有 tensors 都沿相同的 4096-token 次序，不能从 placeholders 推断未出现的 batch 或并发请求。

```text
Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: H_in [4096,5120]                              Formula: H_in=sampled_hidden_states
Tensor: R_in [4096,5120]                              Formula: R_in=sampled_residual
aligned layer-entry rows                       ──▶    ┌──────────────────────────────────────────┐
                                                      │ h[t,0] ... h[t,5119]                     │  ◀── hidden row t
                                                      │ r[t,0] ... r[t,5119]                     │  ◀── residual row t
                                                      └──────────────────────────────────────────┘

Position channel axis 0..2                            Token axis
                                                      0                                      4095
                                                      ▲                                         ▲
Tensor: P [3,4096]                                    Formula: P=sampled_MRoPE_positions
position rows                                  ──▶    ┌──────────────────────────────────────────┐
                                                      │ p[0,0] ... p[0,4095]                     │  ◀── channel 0
                                                      │ p[1,0] ... p[1,4095]                     │
                                                      │ p[2,0] ... p[2,4095]                     │
                                                      └──────────────────────────────────────────┘
```

### Input RMSNorm

节点范围为 #3–#16。

**是什么**：这是 residual 合并后的 Gemma-style RMSNorm，以及 full-attention output 的同形空缓冲区。

**为什么需要**：Q/K/V/gate 的共享 projection 需要规范化 hidden；原始 residual sum 必须同时保留，供 attention output projection 后再次相加。

**怎么做/计算**：#3/#4 读取并 detach `[5120]` norm weight；#5 计算 `add=arg1_1+arg2_1`。#6 转 fp32，#7 平方，#8 沿 Hidden 求 mean 得 `[4096,1]`，#9 加 `1e-6`，#10 `rsqrt`，#11 广播归一化。#12 把 weight 转 fp32，#13 加 1，#14 逐元素缩放，#15 转 bf16 得 `[4096,5120]`；#16 只分配同形、未初始化的 attention output buffer。

```text
Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: R0 [4096,5120]                                Formula: R0=H_in+R_in
entry residual sum                             ──▶    ┌──────────────────────────────────────────┐
                                                      │ r0[t,0] ... r0[t,5119]                   │  ◀── elementwise aligned add
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Reduced Hidden axis
                                                      0                                         0
                                                      ▲                                         ▲
Tensor: InvRMS0 [4096,1]                              Formula: 1/sqrt(mean_h(fp32(R0)^2)+1e-6)
per-token RMS band                             ──▶    ┌──────────────────────────────────────────┐
                                                      │ inv0[0] ... inv0[4095]                   │  ◀── broadcast over h=0..5119
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: H_norm [4096,5120]                            Formula: bf16(fp32(R0)*InvRMS0*(1+W0))
shared projection input                        ──▶    ┌──────────────────────────────────────────┐
                                                      │ h_norm[t,0] ... h_norm[t,5119]           │  ◀── normalized hidden row
                                                      │ ATTN_BUFFER: same shape, uninitialized   │
                                                      └──────────────────────────────────────────┘
```

### Attention/GDN input projections and head reshape

节点范围为 #17–#59。

**是什么**：这是 full-attention 的 fused Q/gate/K/V projection、Q/gate channel split，以及 Q/K 的 per-head RMSNorm。

**为什么需要**：unified attention 需要 24 个 query heads、4 个 KV heads、每头 256 dims；Q 和 K 在 RoPE 前先各自规范化，而 24-head gate 要保留到 attention output 之后。

**怎么做/计算**：#17/#18 读取并转置 `[14336,5120]` 权重，#19 计算 `[4096,14336]`；#20 按 `[12288,1024,1024]` 分割，#21/#22/#23 得 Q-gate、K、V。#24 把 Q-gate view 为 `[4096,24,512]`，#25–#27 沿最后一维二等分成 Q/gate `[4096,24,256]`；#28/#30 clone，#29/#31 分别 flatten 成 `[4096,6144]`。#32 恢复 Q heads；#33/#34 读取 Q norm weight，#35–#44 完成 fp32 square→mean(256)→epsilon→rsqrt→weight scaling→bf16，#45 flatten。#46 把 K 变为 `[4096,4,256]`；#47/#48 读取 K norm weight，#49–#58 执行同一 per-head RMS 链，#59 flatten 为 `[4096,1024]`。V `getitem_2=[4096,1024]` 未在本 process 内改变。

```text
Token axis 0..4095                                    Fused channel axis
                                                      0        12287 12288 13311 13312       14335
                                                      ▲            ▲ ▲         ▲ ▲               ▲
Tensor: QGKV [4096,14336]                             Formula: QGKV=H_norm@W_qgkv^T
fused projection                               ──▶    ┌──────────────────────┬──────────┬──────────┐
                                                      │ Q_GATE [T,12288]     │ K[T,1024]│ V[T,1024]│ ◀── observed split
                                                      └──────────────────────┴──────────┴──────────┘

Query-head axis 0..23                                 Head dimension
                                                      0                  255 256                 511
                                                      ▲                    ▲ ▲                     ▲
Tensor: QGate_heads [4096,24,512]                     Formula: reshape(Q_GATE)=[Q_raw|Gate]
per-query-head partition                       ──▶    ┌──────────────────────┬─────────────────────┐
                                                      │ Q_RAW [T,24,256]     │ GATE [T,24,256]     │  ◀── matched head coordinates
                                                      └──────────────────────┴─────────────────────┘

Head axis Q=0..23 / K=0..3                            Head dimension
                                                      0                                      255
                                                      ▲                                         ▲
Tensor: Qn [4096,24,256]                              Formula: Qn=RMSNorm_head(Q_raw)
Tensor: Kn [4096,4,256]                               Formula: Kn=RMSNorm_head(K_raw)
normalized Q/K heads                           ──▶    ┌──────────────────────────────────────────┐
                                                      │ qn[t,h,0] ... qn[t,h,255]                │  ◀── 24 query heads
                                                      │ kn[t,j,0] ... kn[t,j,255]                │  ◀── 4 KV heads
                                                      └──────────────────────────────────────────┘
```

### RoPE position embedding

节点范围为 #60–#118。

**是什么**：这是由三通道 positions 查表、重排 cos/sin bands，并仅旋转 Q/K 每头前 64 dims 的 observed MRoPE 计算。

**为什么需要**：full attention 需要把 token position 编码进 Q/K；后 192 head dims 保持原值，使最终 head width 仍为 256。

**怎么做/计算**：#60 读取 `[1048576,64]` rotary table，#61 用 `arg0_1=[3,4096]` index 得 `[3,4096,64]`；#62–#64 分成 cos/sin 两个 `[3,4096,32]` tensors。对 cos，#65/#66 选 channel 0 并 clone；#67–#70 把 channel 1 的 feature slice `[1:33:3]`（11 列）copy 到相同目标列；#71–#74 把 channel 2 的 `[2:30:3]`（10 列）copy 到目标。#75–#84 对 sin 对称执行 select/clone/slice/copy。

#85 把 Qn view 为 `[4096,24,256]`，#86/#87 切成 rotary 64 与 pass-through 192；#88/#89 给 cos/sin 增加 head broadcast 轴。#90–#92 把 rotary 64 二分为 32+32；#93–#99 计算第一半 `q0*cos-q1*sin`、第二半 `q1*cos+q0*sin` 并 concat；#100 拼回 192 dims，#101 flatten 为 `[4096,6144]`。#102–#118 对 4-head K 执行同一切片、乘/减/加/concat，输出 `[4096,1024]`。

```text
Position channel axis 0..2                            Rotary-table feature axis
                                                      0                 31 32                63
                                                      ▲                   ▲ ▲                   ▲
Tensor: CS_raw [3,4096,64]                            Formula: CS_raw=RotaryTable[P]=[COS_raw|SIN_raw]
position-indexed bands                         ──▶    ┌─────────────────────┬─────────────────────┐
                                                      │ COS_RAW [3,T,32]    │ SIN_RAW [3,T,32]    │  ◀── T=4096
                                                      └─────────────────────┴─────────────────────┘

Token axis 0..4095                                    Rotary scalar axis
                                                      0                                      31
                                                      ▲                                         ▲
Tensor: Cos [4096,32]                                 Formula: Cos=interleave(COS_raw channels 0,1,2)
Tensor: Sin [4096,32]                                 Formula: Sin=interleave(SIN_raw channels 0,1,2)
MRoPE scalar rows                              ──▶    ┌──────────────────────────────────────────┐
                                                      │ c[t,0] ... c[t,31]                       │  ◀── copied 11+10 feature bands
                                                      │ s[t,0] ... s[t,31]                       │
                                                      └──────────────────────────────────────────┘

Head axis Q=0..23 / K=0..3                            Head dimension
                                                      0          31 32       63 64            255
                                                      ▲            ▲ ▲         ▲ ▲                ▲
Tensor: QK_rot [T,heads,256]                          Formula: [x0*c-x1*s | x1*c+x0*s | x_pass]
partial rotary result                          ──▶    ┌─────────────┬─────────────┬────────────────┐
                                                      │ ROT_FIRST32 │ ROT_SECOND32│ PASS_192       │  ◀── same layout for Q and K
                                                      │ d=0..31     │ d=32..63    │ d=64..255      │
                                                      └─────────────┴─────────────┴────────────────┘
```

### KV-cache update and unified full attention

节点范围为 #119–#125。

**是什么**：这是 attention output allocation、Q/K/V head views、opaque KV-cache update 与 opaque ROCm/DCU unified-attention 调用。

**为什么需要**：当前 4096 query tokens 的 K/V 要进入运行时 cache，并由 unified backend 结合当前 Q 和 cache 生成 24-head context。该 backend 是本 FX 图的实现边界。

**怎么做/计算**：#119 分配 `[4096,6144]` bf16 输出，#120 把 rotated Q view 为 `[4096,24,256]`，#121 把输出 view 为同形；#122/#123 把 rotated K 和原 V view 为 `[4096,4,256]`。#124 用 K/V 与 layer-3 prefix 调用 cache update，返回 shape `[0]` 的依赖 token并产生外部 mutation；入口 metadata 保留 active cache slice `[2,7,784,4,256]`。#125 接收 Q/K/V、可写 output、prefix 与 #124 token并写 output。FX 未展开 QK scores、mask、softmax、value reduction或内部 kernels，因此这些不能作为 observed ATen ops 描述。

```text
Token axis 0..4095                                    Head dimension
                                                      0                                      255
                                                      ▲                                         ▲
Tensor: Q [4096,24,256]                               Formula: Q=reshape(Q_rot)
query heads                                    ──▶    ┌──────────────────────────────────────────┐
                                                      │ q[t,head,0] ... q[t,head,255]            │  ◀── head=0..23
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Head dimension
                                                      0                                      255
                                                      ▲                                         ▲
Tensor: K,V [4096,4,256]                              Formula: K=reshape(K_rot); V=reshape(V_proj)
KV heads                                       ──▶    ┌──────────────────────────────────────────┐
                                                      │ k/v[t,kv_head,0] ... k/v[t,kv_head,255]  │  ◀── kv_head=0..3
                                                      └──────────────────────────────────────────┘

Snapshot-local block axis 0..6                        Last dimensions KV-head x Head-dim
                                                      0                                      255
                                                      ▲                                         ▲
Tensor: Cache_entry [2,7,784,4,256]                   Formula: Cache_next=OpaqueCacheUpdate(Cache_entry,K,V)
sampled external cache                         ──▶    ┌──────────────────────────────────────────┐
                                                      │ ACTIVE_IDS: 0,4..9; 784 x 4 x 256        │  ◀── mutation internals not exposed
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Query-head x Head-dim
                                                      0                                      6143
                                                      ▲                                         ▲
Tensor: A_out [4096,6144]                             Formula: A_out=OpaqueUnifiedAttention(Q,K,V,Cache_next)
mutated attention buffer                       ──▶    ┌──────────────────────────────────────────┐
                                                      │ context[t,0] ... context[t,6143]         │  ◀── 24*256 observed output layout
                                                      └──────────────────────────────────────────┘
```

### Attention output gate and hidden reshape

节点范围为 #126–#128。

**是什么**：这是 unified-attention 输出与 projection 时保留的 Q gate 进行逐元素 sigmoid gating。

**为什么需要**：每个 token、query head 和 head dimension 都有对应 gate；它在 6144-channel mixer space 中调节 attention context，再进入 output projection。

**怎么做/计算**：#126 将被 unified op 写入的 `[4096,24,256]` output view 展平为 `[4096,6144]`；#127 对 `_unsafe_view_1=[4096,6144]` gate 做 sigmoid；#128 在完全相同坐标上逐元素相乘，得到 `mul_14=[4096,6144]`。

```text
Token axis 0..4095                                    Mixer-channel axis
                                                      0                                      6143
                                                      ▲                                         ▲
Tensor: A_flat [4096,6144]                            Formula: A_flat=merge_heads(A_out)
attention context                              ──▶    ┌──────────────────────────────────────────┐
                                                      │ a[t,0] ... a[t,6143]                     │  ◀── 24 heads merged
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Mixer-channel axis
                                                      0                                      6143
                                                      ▲                                         ▲
Tensor: G [4096,6144]                                 Formula: G=sigmoid(Gate_flat)
aligned gate                                   ──▶    ┌──────────────────────────────────────────┐
                                                      │ g[t,0] ... g[t,6143], each in (0,1)      │  ◀── same coordinates as A_flat
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Mixer-channel axis
                                                      0                                      6143
                                                      ▲                                         ▲
Tensor: A_gated [4096,6144]                           Formula: A_gated=A_flat*G
gated mixer rows                               ──▶    ┌──────────────────────────────────────────┐
                                                      │ a_g[t,j]=a[t,j]*g[t,j]                   │  ◀── j=0..6143
                                                      └──────────────────────────────────────────┘
```

### Mixer output projection and residual

节点范围为 #129–#135。

**是什么**：这是 gated attention 的 6144→5120 output projection、output-buffer write，以及与 `R0` 的 residual add。

**为什么需要**：attention head channels 必须回到 model hidden width；其结果与输入归一化前保留的 residual sum 合并，形成 MLP 前边界。

**怎么做/计算**：#129/#130 读取并转置 `[5120,6144]` 权重；#131 计算 `[4096,5120]` projection，#132 copy 到 #16 的 buffer。#133/#134 读取并 detach 下一 RMSNorm 的 `[5120]` weight。#135 逐元素计算 `add_9=copy__4+add`，其中 `add` 就是 `R0`，shape 保持 `[4096,5120]`。

```text
Token axis 0..4095                                    Mixer-channel axis
                                                      0                                      6143
                                                      ▲                                         ▲
Tensor: A_gated [4096,6144]                           Formula: source=A_flat*sigmoid(Gate_flat)
gated attention rows                           ──▶    ┌──────────────────────────────────────────┐
                                                      │ a_g[t,0] ... a_g[t,6143]                 │  ◀── projection source
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: P_attn [4096,5120]                            Formula: P_attn=A_gated@W_out^T
Tensor: R0 [4096,5120]                                Formula: R0=H_in+R_in
aligned rows                                   ──▶    ┌──────────────────────────────────────────┐
                                                      │ p_attn[t,h] / r0[t,h], h=0..5119         │  ◀── same Token x Hidden grid
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: R_attn [4096,5120]                            Formula: R_attn=P_attn+R0
post-attention residual                        ──▶    ┌──────────────────────────────────────────┐
                                                      │ r_attn[t,0] ... r_attn[t,5119]           │  ◀── exact elementwise add
                                                      └──────────────────────────────────────────┘
```

### Post-attention RMSNorm

节点范围为 #136–#145。

**是什么**：这是 full-attention residual 上的第二个 Gemma-style RMSNorm，产生 MLP 输入。

**为什么需要**：它稳定每个 token 的 5120-wide residual，同时保留未归一化的 `R_attn` 作为 layer return 中的 residual。

**怎么做/计算**：#136 转 fp32，#137 平方，#138 沿 Hidden mean 得 `[4096,1]`，#139 加 `1e-6`，#140 `rsqrt`，#141 广播乘回；#142 把 detached weight 转 fp32，#143 加 1，#144 逐元素应用，#145 转 bf16 得 `[4096,5120]`。

```text
Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: R32 [4096,5120]                               Formula: R32=fp32(R_attn)
residual source                                ──▶    ┌──────────────────────────────────────────┐
                                                      │ r32[t,0]^2 ... r32[t,5119]^2             │  ◀── RMS reduction source
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Reduced Hidden axis
                                                      0                                         0
                                                      ▲                                         ▲
Tensor: InvRMS1 [4096,1]                              Formula: 1/sqrt(mean_h(R32^2)+1e-6)
per-token scale                                ──▶    ┌──────────────────────────────────────────┐
                                                      │ inv1[0] ... inv1[4095]                   │  ◀── broadcast to 5120 columns
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: H_mlp [4096,5120]                             Formula: bf16(R32*InvRMS1*(1+W1))
normalized MLP rows                            ──▶    ┌──────────────────────────────────────────┐
                                                      │ h_mlp[t,0] ... h_mlp[t,5119]             │  ◀── model-width output
                                                      └──────────────────────────────────────────┘
```

### Gated MLP projections

节点范围为 #146–#153。

**是什么**：这是 5120→34816→17408→5120 的 dense gated MLP。

**为什么需要**：它在每个 token 内扩展 channels、执行 SiLU-gated 非线性，再回到 decoder hidden width。

**怎么做/计算**：#146/#147 读取并转置 `[34816,5120]` gate/up weight；#148 得 `[4096,34816]`。#149 分配 `[4096,17408]`，#150 的 fused `silu_and_mul` 按两个 17408-wide regions 计算 `SiLU(gate)*up` 并写入；FX 不展开 fused kernel。#151/#152 读取并转置 `[5120,17408]` down weight，#153 得 `[4096,5120]`。

```text
Token axis 0..4095                                    Expanded-channel axis
                                                      0                  17407 17408          34815
                                                      ▲                      ▲ ▲                  ▲
Tensor: GU [4096,34816]                               Formula: GU=H_mlp@W_gate_up^T=[GATE|UP]
expanded rows                                  ──▶    ┌───────────────────────┬────────────────────┐
                                                      │ GATE [T,17408]        │ UP [T,17408]       │  ◀── aligned channel pairs
                                                      └───────────────────────┴────────────────────┘

Token axis 0..4095                                    Intermediate axis
                                                      0                                     17407
                                                      ▲                                         ▲
Tensor: M [4096,17408]                                Formula: M=SiLU(GATE)*UP
nonlinear product                              ──▶    ┌──────────────────────────────────────────┐
                                                      │ m[t,j]=silu(g[t,j])*u[t,j]               │  ◀── j=0..17407
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: H_out [4096,5120]                             Formula: H_out=M@W_down^T
down projection                                ──▶    ┌──────────────────────────────────────────┐
                                                      │ h_out[t,0] ... h_out[t,5119]             │  ◀── restored width
                                                      └──────────────────────────────────────────┘
```

### Layer output

节点范围为 #154。

**是什么**：FX output 把本层 hidden output 和 attention residual 打包为 tuple。

**为什么需要**：下一 decoder layer 要继续使用 MLP output，同时 residual stream 作为独立 tensor 传递。

**怎么做/计算**：#154 返回 `(mm_3, add_9)`，两者均为 `[4096,5120]`。这里不再执行 projection、residual add、cache update 或 alias copy。

```text
Token axis 0..4095                                    Hidden axis 0..5119
                                                      ▲                     ▲
Tensor: H_out [4096,5120]                             Formula: H_out=MLP_down(H_mlp)
computed hidden output                         ──▶    [H_OUT_ROWS]                               ◀── tuple item 0

Tensor: R_attn [4096,5120]                            Formula: R_attn=ProjectedAttention+R0
preserved residual                             ──▶    [RESIDUAL_ROWS]                             ◀── tuple item 1

Tensor: LayerTuple                                    Formula: LayerTuple=(H_out,R_attn)
packaged return                                ──▶    [(4096,5120),(4096,5120)]                  ◀── no new arithmetic
```
