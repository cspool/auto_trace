# R032 completion report

R032 completed the selected-layer Qwen3.5-27B FX trace stage for pipeline run
`20260729T050800Z-fx-89687ae2` on HCU0. A fresh eager vLLM V1 request reproduced the
R02 request output. The client reused the exact R02 external request ID; vLLM
V1 then applied its normal 8-hex internal scheduler-instance suffix. Both IDs
and their verified one-to-one mapping are preserved.

The evidence boundary is strict: nine selected decoder-layer inputs and their
replay-relevant forward-context/cache state were cloned at live layer entry;
the real response came only from the original eager forward. After the request
client returned, the worker observed the finalize marker, reached zero active
model executions, restored both R032 wrappers, and only then ran fixed-input
`make_fx` replay.

Counts:

- 29 effective forwards and 1,856 observed loaded-layer calls
- 9 uniquely sampled selected events
- 9 successful FX traces
- 0 FX trace errors
- 0 patch, capture, serialization, or wrapper-restoration errors

Selected artifacts:

- `input1_layer0` / `chatcmpl-bench-7f1746b7-0-9eeec82b|s1|f1|l0|o0`: linear_attention, 77 nodes
- `input1_layer3` / `chatcmpl-bench-7f1746b7-0-9eeec82b|s1|f1|l3|o0`: full_attention, 155 nodes
- `input2_layer31` / `chatcmpl-bench-7f1746b7-0-9eeec82b|s2|f2|l31|o0`: full_attention, 155 nodes
- `input6_layer62` / `chatcmpl-bench-7f1746b7-0-9eeec82b|s6|f6|l62|o0`: linear_attention, 78 nodes
- `input6_layer63` / `chatcmpl-bench-7f1746b7-0-9eeec82b|s6|f6|l63|o0`: full_attention, 155 nodes
- `input7_layer0` / `chatcmpl-bench-7f1746b7-0-9eeec82b|s7|f7|l0|o0`: linear_attention, 74 nodes
- `input7_layer3` / `chatcmpl-bench-7f1746b7-0-9eeec82b|s7|f7|l3|o0`: full_attention, 155 nodes
- `input29_layer62` / `chatcmpl-bench-7f1746b7-0-9eeec82b|s29|f29|l62|o0`: linear_attention, 75 nodes
- `input29_layer63` / `chatcmpl-bench-7f1746b7-0-9eeec82b|s29|f29|l63|o0`: full_attention, 155 nodes

ROCm/DCU GDN and unified-attention custom operations remain opaque FX nodes.
These graphs do not expose their internal kernels, do not constitute measured
latency, do not prove unobserved branches, and do not extend this single-request
TP/PP/DP=1 evidence to concurrent or distributed execution. No reconstruction
or visualization stage was run. The GraphModule serialization intentionally
uses meta storage instead of duplicating model weights; it is structural FX
evidence, not a directly executable decoder-layer checkpoint.
