# input1_layer0 FX Process 手工解释与张量可视化

本文件对应 `selected:01` 的 linear-attention prefill 固定输入路径：第 1 次 forward、第 0 层，`q/past/kv=4096/0/4096`。以下 9 个 process 与重建文件顺序一致；字符图中的宽高均为压缩表示。

### Runtime FX inputs

节点范围为 #0–#2。

**是什么**：这是当前固定输入 FX DAG 的三个入口占位符：位置张量 `arg0_1=[3,4096]`、hidden states `arg1_1=[4096,5120]`，以及本次为 `None` 的 residual `arg2_1`。

**为什么需要**：decoder layer 必须从真实采样调用取得 token hidden rows；位置和 residual 也要保持调用签名一致。这个 linear-attention 固定分支不读取位置节点，而首层的 residual 尚未建立，因此后两项分别表现为“未被使用的位置占位符”和 `None`。

**怎么做/计算**：#0、#1、#2 都不做数值计算，只暴露固定输入。#1 的每个 token row 被 `_to_copy` 和后续 residual add 使用；#0、#2 的 users 为空，因而不能据此声称该固定 linear-attention 分支执行了位置编码或已有 residual 合并。

```text
Token axis (4096 rows, height compressed)             Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: H_in [4096,5120]                              Formula: H_in = sampled_hidden_states
sampled hidden rows                            ──▶    ┌──────────────────────────────────────────┐
                                                      │ TOKEN_ROW_0: h[0,0] ... h[0,5119]        │  ◀── first sampled row
                                                      │ TOKEN_ROWS_1_TO_4094                     │
                                                      │ TOKEN_ROW_4095: h[4095,0] ... h[...,5119]│  ◀── last sampled row
                                                      └──────────────────────────────────────────┘

Position-channel axis 0..2                            Token coordinate
                                                      0                                      4095
                                                      ▲                                         ▲
Tensor: P [3,4096]                                    Formula: P = sampled_positions; users(P) = empty
position placeholder                           ──▶    ┌──────────────────────────────────────────┐
                                                      │ POS_CHANNEL_0: p[0,0] ... p[0,4095]      │  ◀── preserved, not consumed here
                                                      │ POS_CHANNEL_1: p[1,0] ... p[1,4095]      │
                                                      │ POS_CHANNEL_2: p[2,0] ... p[2,4095]      │
                                                      └──────────────────────────────────────────┘

Tensor: R_in                                          Formula: R_in = None
residual placeholder                          ──▶    [NONE_RESIDUAL]                              ◀── no tensor rows at layer entry
```

### Input RMSNorm

节点范围为 #3–#15。

**是什么**：这是首层 hidden states 上展开的 Gemma-style RMSNorm，以及供 mixer 写入的 `[4096,5120]` 空输出缓冲区。

**为什么需要**：线性注意力的两个输入投影需要尺度稳定的 bf16 hidden rows；同时 decoder layer 预先分配与 normalized hidden 同形的输出缓冲区，供后面的 output projection 原位写入。

**怎么做/计算**：#3 读取 `[5120]` norm 参数，#4 `detach` 固定其梯度语义；#5 把 `arg1_1` 转为 fp32。#6 对每个 hidden element 平方，#7 沿 Hidden 轴求均值得到 `[4096,1]`，#8 加 `1e-6`，#9 求倒平方根；#10 将其广播乘回 fp32 hidden。#11 把权重转为 fp32，#12 对权重逐元素加 1，#13 应用到 normalized rows，#14 转回 bf16 得到 `[4096,5120]`。#15 只按该结果的形状、dtype 和 device 分配 `empty_like`，没有初始化数值。

```text
Token axis 0..4095 (height compressed)                Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: X32 [4096,5120]                               Formula: X32 = fp32(H_in)
fp32 source rows                               ──▶    ┌──────────────────────────────────────────┐
                                                      │ x[t,0]^2 ... x[t,5119]^2                 │  ◀── square each hidden element
                                                      │ t = 0 ... 4095                           │
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Reduced Hidden axis
                                                      0 (one scalar per token)                    0
                                                      ▲                                           ▲
Tensor: InvRMS [4096,1]                               Formula: InvRMS[t]=1/sqrt(mean_h(X32[t,h]^2)+1e-6)
hidden reduction                               ──▶    ┌──────────────────────────────────────────┐
                                                      │ inv_rms[0], ..., inv_rms[4095]           │  ◀── broadcast back over Hidden
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: H_norm [4096,5120]                            Formula: H_norm=bf16(X32*InvRMS*(1+W_norm))
normalized mixer input                         ──▶    ┌──────────────────────────────────────────┐
                                                      │ y[t,0] ... y[t,5119]                     │  ◀── same Token x Hidden coordinates
                                                      │ OUTPUT_BUFFER: same shape, uninitialized │
                                                      └──────────────────────────────────────────┘
```

### Attention/GDN input projections and head reshape

节点范围为 #16–#31。

**是什么**：这是 Qwen3.5 Gated DeltaNet 的两个输入投影：`in_proj_qkvz` 产生 mixed-QKV 与 Z，`in_proj_ba` 产生每个 value head 的 B/A 标量，并分配 core 输出。

**为什么需要**：不透明 GDN core 需要 mixed-QKV、B、A 和可写输出缓冲区；core 后的 gated RMSNorm 还需要与 value heads 对齐的 Z。

**怎么做/计算**：#16–#18 读取并转置 `[16384,5120]` 权重，再用 `H_norm` 做矩阵乘，得到 `[4096,16384]`。#19 按最后一维 `[10240,6144]` 切分，#20 是 mixed-QKV，#21 是 Z；#22 把 Z 解释为 `[4096,48,128]`。#23–#25 用 `[96,5120]` 权重做第二个投影得到 `[4096,96]`，#26 按 48 等分，#27/#28 分别为 B/A `[4096,48]`；#29/#30 生成 contiguous clone。#31 分配零初始化的 core 输出 `[4096,48,128]`。

```text
Token axis 0..4095                                    Projected-channel axis
                                                      0             10239 10240             16383
                                                      ▲                ▲ ▲                     ▲
Tensor: P_qkvz [4096,16384]                           Formula: P_qkvz=H_norm@W_qkvz^T
first projection                               ──▶    ┌──────────────────────────┬───────────────┐
                                                      │ MIXED_QKV [T,10240]      │ Z [T,6144]    │  ◀── explicit channel partition
                                                      │ qkv[t,0] ... qkv[t,10239]│ z[t,0]...     │
                                                      └──────────────────────────┴───────────────┘

Token axis 0..4095                                    BA-channel axis
                                                      0                    47 48                 95
                                                      ▲                     ▲ ▲                   ▲
Tensor: P_ba [4096,96]                                Formula: P_ba=H_norm@W_ba^T=[B|A]
second projection                              ──▶    ┌──────────────────────┬────────────────────┐
                                                      │ B [T,48]             │ A [T,48]           │  ◀── one scalar per value head
                                                      │ b[t,0] ... b[t,47]   │ a[t,0] ... a[t,47] │
                                                      └──────────────────────┴────────────────────┘

Head axis 0..47                                       Value-head dimension
                                                      0                                      127
                                                      ▲                                         ▲
Tensor: Z_heads [4096,48,128]                         Formula: Z_heads=reshape(Z)
Tensor: Core_buf [4096,48,128]                        Formula: Core_buf=zeros_like(Z_heads)
head-aligned tensors                           ──▶    ┌──────────────────────────────────────────┐
                                                      │ head 0: z[t,0,0] ... z[t,0,127]          │  ◀── Z gate row
                                                      │ heads 1 ... 46                           │
                                                      │ head 47: z[t,47,0] ... z[t,47,127]       │
                                                      └──────────────────────────────────────────┘
```

### Gated DeltaNet recurrent core

节点范围为 #32。

**是什么**：这是固定图中唯一的 `gdn_attention_core` 自定义调用边界。它接收 mixed-QKV、contiguous B/A 和零输出缓冲区，并以 layer-0 prefix 选择运行时上下文。

**为什么需要**：Gated DeltaNet 的状态递推与缓存更新由平台自定义实现完成；外层 FX 图必须把投影结果和可写输出交给该边界，才能继续执行 observed output normalization。

**怎么做/计算**：#32 的 observed 输入依次为 `getitem=[4096,10240]`、`clone=[4096,48]`、`clone_1=[4096,48]`、`zeros=[4096,48,128]` 和 prefix。调用本身没有普通 tensor user；后续直接读取被该调用写入的 `zeros`。metadata 另保留进入调用时的 `[1,3,10240]` 与 `[1,48,128,128]` 外部状态切片。FX 没有展开该自定义 op 的递推、kernel 或缓存内部计算，因此这里只把 `Core_buf` 的 mutation 作为证据。

```text
Token axis 0..4095                                    Mixed-channel axis
                                                      0                                     10239
                                                      ▲                                         ▲
Tensor: Mixed [4096,10240]                            Formula: Mixed=QKV_partition(P_qkvz)
projected core input                           ──▶    ┌──────────────────────────────────────────┐
                                                      │ mixed[t,0] ... mixed[t,10239]            │  ◀── observed opaque input
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Value-head axis
                                                      0                                       47
                                                      ▲                                         ▲
Tensor: BA [4096,48]                                  Formula: BA=(B,A) from P_ba
per-head controls                              ──▶    ┌──────────────────────────────────────────┐
                                                      │ b[t,0] ... b[t,47] / a[t,0] ... a[t,47]  │  ◀── two aligned control rows
                                                      └──────────────────────────────────────────┘

State-0 lane axis 0..2                                State-0 channel axis
                                                      0                                     10239
                                                      ▲                                         ▲
Tensor: State0_entry [1,3,10240]                      Formula: State0_entry=sampled_external_GDN_state_tensor_0
external state tensor 0                        ──▶    ┌──────────────────────────────────────────┐
                                                      │ STATE0_LANES_0_TO_2 x CHANNELS_0_TO_10239│ ◀── observed entry slice
                                                      └──────────────────────────────────────────┘

State head axis 0..47                                 State key/value axis 0..127
                                                      0                                      127
                                                      ▲                                         ▲
Tensor: S_entry [1,48,128,128]                        Formula: S_entry=sampled_external_GDN_state
external mutation state                        ──▶    ┌──────────────────────────────────────────┐
                                                      │ STATE_HEAD_0 ... STATE_HEAD_47           │  ◀── internals remain opaque
                                                      └──────────────────────────────────────────┘

Head axis 0..47                                       Value-head dimension 0..127
                                                      0                                      127
                                                      ▲                                         ▲
Tensor: Core_out [4096,48,128]                        Formula: Core_out=OpaqueGDN(Mixed,B,A,S_entry)
mutated output buffer                          ──▶    ┌──────────────────────────────────────────┐
                                                      │ core[t,head,0] ... core[t,head,127]      │  ◀── only boundary output is observed
                                                      └──────────────────────────────────────────┘
```

### Gated DeltaNet output RMSNorm and SiLU gate

节点范围为 #33–#50。

**是什么**：这是 GDN core 输出的 per-head RMSNorm、Z 的 SiLU gate，以及从 48 个 value heads 合并回 6144 channels 的过程。

**为什么需要**：递推输出和 Z 使用相同的 `[token,head,128]` 坐标；先稳定每个 head 的幅值，再由 Z 控制信息通过量，才能送入 6144→5120 output projection。

**怎么做/计算**：#33 把被写入的 core buffer 展平为 `[196608,128]`。#34 clone Z heads，#35 同样展平为 `[196608,128]`。#36 将 core 转 fp32；#37/#38 读取并转 fp32 `[128]` norm weight；#39 将 Z 转 fp32。#40 平方 core，#41 沿 128 维求均值得 `[196608,1]`，#42 加 `1e-6`，#43 `rsqrt`，#44 广播归一化，#45 乘 norm weight。#46 对 Z 做 SiLU，#47 将 normalized core 与 gate 逐元素相乘，#48 转 bf16；#49 恢复 `[4096,48,128]`，#50 合并为 `[4096,6144]`。

```text
Flattened token-head row axis 0..196607               Head dimension
                                                      0                                      127
                                                      ▲                                         ▲
Tensor: C32 [196608,128]                              Formula: C32=fp32(reshape(Core_out))
Tensor: Z32 [196608,128]                              Formula: Z32=fp32(reshape(Z_heads))
aligned core/Z rows                            ──▶    ┌──────────────────────────────────────────┐
                                                      │ c[r,0] ... c[r,127]                      │  ◀── same r maps one token/head
                                                      │ z[r,0] ... z[r,127]                      │
                                                      └──────────────────────────────────────────┘

Row axis 0..196607                                    Reduced head dimension
                                                      0 (one scalar per row)                    0
                                                      ▲                                          ▲
Tensor: InvRMS_c [196608,1]                           Formula: 1/sqrt(mean_d(C32^2)+1e-6)
per-head reduction                             ──▶    ┌──────────────────────────────────────────┐
                                                      │ inv_c[0] ... inv_c[196607]               │  ◀── broadcast over d=0..127
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Merged value channels
                                                      0                                      6143
                                                      ▲                                         ▲
Tensor: GDN_mix [4096,6144]                           Formula: merge_heads(bf16(C32*InvRMS_c*W*SiLU(Z32)))
normalized gated result                        ──▶    ┌──────────────────────────────────────────┐
                                                      │ heads 0..47 x dims 0..127                │  ◀── 48*128 = 6144
                                                      │ mix[t,0] ... mix[t,6143]                 │
                                                      └──────────────────────────────────────────┘
```

### Mixer output projection and residual

节点范围为 #51–#57。

**是什么**：这是 linear mixer 的 6144→5120 output projection、写入 decoder output buffer，并与首层输入建立 residual。

**为什么需要**：GDN head channels 必须回到 model hidden width；decoder 的下一归一化边界还需要保留“mixer 输出 + layer-entry hidden”的 residual tensor。

**怎么做/计算**：#51 读取 `[5120,6144]` 权重，#52 转置为 `[6144,5120]`；#53 用 `view_3=[4096,6144]` 做矩阵乘，得到 `[4096,5120]`。#54 把它写入 #15 分配的 `empty_like`。#55/#56 读取并 detach 下一 RMSNorm 的 `[5120]` 参数，作为后续 process 边界输入。#57 把 projected rows 与 `arg1_1` 逐元素相加，得到 `[4096,5120]` 的 `add_3` residual。

```text
Token axis 0..4095                                    Mixer-channel axis
                                                      0                                      6143
                                                      ▲                                         ▲
Tensor: GDN_mix [4096,6144]                           Formula: source=normalized_gated_GDN_heads
mixer rows                                     ──▶    ┌──────────────────────────────────────────┐
                                                      │ mix[t,0] ... mix[t,6143]                 │  ◀── projection source
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: P_out [4096,5120]                             Formula: P_out=GDN_mix@W_out^T
Tensor: R_base [4096,5120]                            Formula: R_base=H_in
aligned projected/residual rows                ──▶    ┌──────────────────────────────────────────┐
                                                      │ p[t,0] ... p[t,5119]                     │  ◀── copied into output buffer
                                                      │ r[t,0] ... r[t,5119]                     │
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: R_attn [4096,5120]                            Formula: R_attn=P_out+R_base
post-mixer residual                            ──▶    ┌──────────────────────────────────────────┐
                                                      │ r_attn[t,0] ... r_attn[t,5119]           │  ◀── exact elementwise coordinates
                                                      └──────────────────────────────────────────┘
```

### Post-attention RMSNorm

节点范围为 #58–#67。

**是什么**：这是 attention/mixer residual 边界上的第二个 Gemma-style RMSNorm，输出 MLP 的 bf16 输入。

**为什么需要**：MLP 的大宽度 gate/up projection 需要对每个 token 的 5120 hidden values 做 RMS 标准化，同时 residual `add_3` 保留给 layer output。

**怎么做/计算**：#58 把 `add_3` 转 fp32；#59 平方，#60 沿 Hidden 求均值 `[4096,1]`，#61 加 `1e-6`，#62 求 `rsqrt`，#63 广播乘回。#64 将 #56 的 detached weight 转 fp32，#65 逐元素加 1，#66 乘到 normalized rows，#67 转 bf16，得到 `[4096,5120]` 的 MLP 输入。

```text
Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: R32 [4096,5120]                               Formula: R32=fp32(R_attn)
residual rows                                  ──▶    ┌──────────────────────────────────────────┐
                                                      │ r32[t,0]^2 ... r32[t,5119]^2             │  ◀── reduction source
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Reduced Hidden axis
                                                      0                                         0
                                                      ▲                                         ▲
Tensor: InvRMS_post [4096,1]                          Formula: 1/sqrt(mean_h(R32^2)+1e-6)
RMS scalar band                                ──▶    ┌──────────────────────────────────────────┐
                                                      │ inv_post[0] ... inv_post[4095]           │  ◀── one scalar per token
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: H_mlp [4096,5120]                             Formula: H_mlp=bf16(R32*InvRMS_post*(1+W_post))
normalized MLP input                           ──▶    ┌──────────────────────────────────────────┐
                                                      │ h_mlp[t,0] ... h_mlp[t,5119]             │  ◀── same Token x Hidden layout
                                                      └──────────────────────────────────────────┘
```

### Gated MLP projections

节点范围为 #68–#75。

**是什么**：这是 dense gated MLP：5120→34816 的 fused gate/up projection、17408-wide SiLU-product，再降回 5120。

**为什么需要**：attention/linear mixer 负责 token mixing，MLP 在每个 token 内扩展 channel capacity并施加非线性，最后恢复 decoder hidden width。

**怎么做/计算**：#68 读取 `[34816,5120]` gate/up 权重，#69 转置；#70 与 `H_mlp` 相乘得到 `[4096,34816]`，其最后一维对应两个 17408-wide regions。#71 分配 `[4096,17408]` 输出。#72 的 fused `silu_and_mul` 边界把 gate region 做 SiLU 后与 up region逐元素相乘并写入该输出；FX 不展开其 kernel。#73 读取 `[5120,17408]` down weight，#74 转置，#75 做矩阵乘得到 `[4096,5120]`。

```text
Token axis 0..4095                                    Expanded-channel axis
                                                      0                  17407 17408          34815
                                                      ▲                      ▲ ▲                  ▲
Tensor: GU [4096,34816]                               Formula: GU=H_mlp@W_gate_up^T=[GATE|UP]
expanded projection                            ──▶    ┌───────────────────────┬────────────────────┐
                                                      │ GATE [T,17408]        │ UP [T,17408]       │  ◀── aligned channel pairs
                                                      │ g[t,0]...g[t,17407]   │ u[t,0]...u[t,17407]│
                                                      └───────────────────────┴────────────────────┘

Token axis 0..4095                                    Intermediate axis
                                                      0                                     17407
                                                      ▲                                         ▲
Tensor: M [4096,17408]                                Formula: M=SiLU(GATE)*UP
fused nonlinear product                        ──▶    ┌──────────────────────────────────────────┐
                                                      │ m[t,j]=silu(g[t,j])*u[t,j]               │  ◀── j=0,1,...,17407
                                                      └──────────────────────────────────────────┘

Token axis 0..4095                                    Hidden axis
                                                      0                                      5119
                                                      ▲                                         ▲
Tensor: H_out [4096,5120]                             Formula: H_out=M@W_down^T
down-projected layer output                    ──▶    ┌──────────────────────────────────────────┐
                                                      │ h_out[t,0] ... h_out[t,5119]             │  ◀── restored model width
                                                      └──────────────────────────────────────────┘
```

### Layer output

节点范围为 #76。

**是什么**：这是 FX `output` 节点对已经计算完成的两个 tensors 进行打包，不再执行数值变换。

**为什么需要**：decoder 调用方同时需要本层 MLP hidden output 和供下一层 residual 融合使用的 attention/mixer residual。

**怎么做/计算**：#76 返回 `(mm_4, add_3)`；前者是 `[4096,5120]` 的 MLP down-projection，后者是 `[4096,5120]` 的 post-mixer residual。它不新增 add、copy、cache 更新或其他计算。

```text
Token axis 0..4095                                    Hidden axis 0..5119
                                                      ▲                     ▲
Tensor: H_out [4096,5120]                             Formula: H_out=MLP_down(H_mlp)
computed hidden output                         ──▶    [H_OUT_ROWS]                               ◀── tuple item 0

Tensor: R_attn [4096,5120]                            Formula: R_attn=Projected_GDN+H_in
preserved residual                             ──▶    [RESIDUAL_ROWS]                             ◀── tuple item 1

Tensor: LayerTuple                                    Formula: LayerTuple=(H_out,R_attn)
packaged return                                ──▶    [(4096,5120),(4096,5120)]                  ◀── no new tensor arithmetic
```
