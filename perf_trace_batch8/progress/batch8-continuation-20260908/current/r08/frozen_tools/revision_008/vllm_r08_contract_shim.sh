#!/usr/bin/env bash
set -euo pipefail
exec /usr/bin/python -B /public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R08/continuation_001/tools/revision_008/launch_vllm.py "$@" --long-prefill-token-threshold 512
