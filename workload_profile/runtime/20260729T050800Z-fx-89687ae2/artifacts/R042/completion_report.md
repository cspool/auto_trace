# R042 完成报告

R042 已按 R032 handoff 的原始顺序完成 9 个 Qwen3.5-27B 固定输入 FX DAG
的 process 重建与手工可视化。共覆盖 1,079 个 FX 节点，严格且无重叠地
划分为 86 个 dependency-ordered processes；每个事件均同时提供机器可读
JSON、生成式重建 Markdown、逐节点 CSV，以及独立的手工
`fx_process_visualization.md` companion。

每个 process 的 companion 均以中文回答“是什么 / 为什么需要 /
怎么做/计算”，并在英文字符图中标出真实观测 shape、轴起止、代表元素、
数据流指针及平齐的 tensor/region 边界。最终独立验证逐项检查了 9 个事件、
86 个 process 的完整 FX 节点引用，以及所有图示的语言、shape、指针、
轴端点和矩形/内部 region 几何。

事件清单：

- `input1_layer0` / `selected:01`：linear_attention，prefill_chunk，77 nodes / 9 processes，`q/past/kv=4096/0/4096`
- `input1_layer3` / `selected:02`：full_attention，prefill_chunk，155 nodes / 10 processes，`q/past/kv=4096/0/4096`
- `input2_layer31` / `selected:03`：full_attention，prefill_chunk，155 nodes / 10 processes，`q/past/kv=4096/4096/8192`
- `input6_layer62` / `selected:04`：linear_attention，prefill_chunk，78 nodes / 9 processes，`q/past/kv=105/20480/20585`
- `input6_layer63` / `selected:05`：full_attention，prefill_chunk，155 nodes / 10 processes，`q/past/kv=105/20480/20585`
- `input7_layer0` / `selected:06`：linear_attention，decode，74 nodes / 9 processes，`q/past/kv=1/20585/20586`
- `input7_layer3` / `selected:07`：full_attention，decode，155 nodes / 10 processes，`q/past/kv=1/20585/20586`
- `input29_layer62` / `selected:08`：linear_attention，decode，75 nodes / 9 processes，`q/past/kv=1/20607/20608`
- `input29_layer63` / `selected:09`：full_attention，decode，155 nodes / 10 processes，`q/past/kv=1/20607/20608`

证据边界保持不变：这些是固定输入路径的 ATen/custom-op DAG；process 名称
是规则推导的结构分区，不是恢复出的模块所有权。GDN core、KV-cache mutation
和 unified attention 的内部 kernel/计算仍然不透明。R042 未加载或执行
meta-storage GraphModule，未把理论 FLOPs 或 FX 节点解释为实测延迟，也未
声称并发、分布式、剪枝、early-exit 或未观测分支覆盖。
