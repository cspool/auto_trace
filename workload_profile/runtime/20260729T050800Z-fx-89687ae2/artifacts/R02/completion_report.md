# R02 Algorithmic Trace And Layer Selection

- Trace: `20260729T050800Z-fx-89687ae2-R02-qwen35-27b-eager-row0-hcu0`
- Runtime: current optimized Qwen3.5-27B vLLM V1 runtime, with `--enforce-eager` only to preserve Python layer visibility.
- Fresh request: 20574 benchmark input tokens, 23 generated tokens, 0 failures.
- Complete forwards: 29 (6 prefill and 23 decode), each with 64 loaded layers.
- Decisions: 171 scheduler/cache/model-route/sampling/output rows; direct terminal cache free was observed.
- FLOPs: 9280 analytic rows; these are theoretical FLOPs, not measured ROCm/DCU latency.
- Selected events: 9, each uniquely joined to `layer_trace.csv` and backed by actual decision rows.
- Qwen3.5 multimodal pruning is disabled; no pruning or early-exit rows were fabricated.
- Scope: one deterministic request with max concurrency 1; no concurrent/distributed claim.
- No DispatchMode, FX, reconstruction, ONNX, or visualization work was run.

## Selected events

- `selected:01` P0 `initial_prefill_early_linear`: (step=1, forward=1, layer=0, occurrence=0, phase=prefill_chunk, q=4096, past=0, kv=4096, type=linear_attention).
- `selected:02` P0 `initial_prefill_early_full_attention`: (step=1, forward=1, layer=3, occurrence=0, phase=prefill_chunk, q=4096, past=0, kv=4096, type=full_attention).
- `selected:03` P1 `post_initial_cache_growth_boundary`: (step=2, forward=2, layer=31, occurrence=0, phase=prefill_chunk, q=4096, past=4096, kv=8192, type=full_attention).
- `selected:04` P1 `tail_prefill_late_linear`: (step=6, forward=6, layer=62, occurrence=0, phase=prefill_chunk, q=105, past=20480, kv=20585, type=linear_attention).
- `selected:05` P1 `tail_prefill_late_full_attention`: (step=6, forward=6, layer=63, occurrence=0, phase=prefill_chunk, q=105, past=20480, kv=20585, type=full_attention).
- `selected:06` P3 `first_decode_early_linear`: (step=7, forward=7, layer=0, occurrence=0, phase=decode, q=1, past=20585, kv=20586, type=linear_attention).
- `selected:07` P3 `first_decode_early_full_attention`: (step=7, forward=7, layer=3, occurrence=0, phase=decode, q=1, past=20585, kv=20586, type=full_attention).
- `selected:08` P3 `late_decode_late_linear`: (step=29, forward=29, layer=62, occurrence=0, phase=decode, q=1, past=20607, kv=20608, type=linear_attention).
- `selected:09` P0 `late_decode_terminal_full_attention`: (step=29, forward=29, layer=63, occurrence=0, phase=decode, q=1, past=20607, kv=20608, type=full_attention).
