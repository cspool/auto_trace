# Batch8 优化的可视化时间线分析

状态：证据提取完成，报告和图表生成中。

采用 `perf_trace/skills/build-optimization-trace-report/SKILL.md`，读取已验收的同一 R09/R10 谱系。全部 23,660 个 kernel 均通过原生 HIP launch index 与 process 归属检查；累计原始 kernel 时长 3,154.602493 ms。完整统计见 `data/analysis.json`，可复算脚本为 `analyze_trace.py`。

当前确认：GQA6 224 次，其中 BM32 / 单卡 B3–B4 128 次；GDN fused RMSNorm 672 次。96 次 packed decode 的实际 launch 是 B4 / 64 threads 的官方回退，B1–B3 专用路径未命中。请求 phase 标签与整个混合 batch 的 kernel 工作量分开处理；没有可比基线，不作加速比结论。

正式 R08–R10 产物保持已封存状态。本目录是用户另行请求的解释报告。
