#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 6 ]; then
    echo "usage: $0 TRACE_DIR CANONICAL_MANIFEST SELECTION_HANDOFF SOURCE_TRACE RUN_ID CONTRACT_ID" >&2
    exit 2
fi

TRACE_DIR="$1"
CANONICAL_MANIFEST="$2"
SELECTION_HANDOFF="$3"
SOURCE_TRACE="$4"
RUN_ID="$5"
CONTRACT_ID="$6"

PROJECT_ROOT="${R032_PROJECT_ROOT:-/public/home/tangyu408/Qwen_DCU_Worker_0}"
SOURCE_ROOT="${PROJECT_ROOT}/pra2026-bh408"
MODEL_PATH="/home/Qwen3.5-27B"
RUNTIME_PATCH="${PROJECT_ROOT}/workload_profile/fx/tools/runtime_patch"
RUNTIME_FX_UTILS="${PROJECT_ROOT}/workload_profile_bk/tools/fx_patch"

for path in \
    "${CANONICAL_MANIFEST}" \
    "${SELECTION_HANDOFF}" \
    "${SOURCE_TRACE}" \
    "${SOURCE_ROOT}/scripts/cscc_gfx936_env.sh" \
    "${RUNTIME_PATCH}/sitecustomize.py" \
    "${RUNTIME_PATCH}/r032_selected_layer_fx_patch.py" \
    "${RUNTIME_FX_UTILS}/vllm_selected_layer_fx_patch.py" \
    "${MODEL_PATH}/config.json"
do
    if [ ! -f "${path}" ]; then
        echo "required file does not exist: ${path}" >&2
        exit 1
    fi
done

if [ -e "${TRACE_DIR}" ] && [ -n "$(find "${TRACE_DIR}" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
    echo "refusing to reuse non-empty trace directory: ${TRACE_DIR}" >&2
    exit 1
fi
mkdir -p "${TRACE_DIR}"

source "${SOURCE_ROOT}/scripts/cscc_gfx936_env.sh"
export HIP_VISIBLE_DEVICES=0
export CUDA_VISIBLE_DEVICES=0
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
export VLLM_RPC_TIMEOUT=1800000

export PYTHONPATH="${RUNTIME_PATCH}:${RUNTIME_FX_UTILS}${PYTHONPATH:+:${PYTHONPATH}}"
export VLLM_R032_FX_ENABLE=1
export VLLM_SELECTED_LAYER_FX_DIR="${TRACE_DIR}"
export VLLM_SELECTED_LAYER_FX_ARM_FILE="${TRACE_DIR}/FX_ARMED"
export VLLM_SELECTED_LAYER_FX_CANONICAL_MANIFEST="${CANONICAL_MANIFEST}"
export VLLM_SELECTED_LAYER_FX_SELECTION_HANDOFF="${SELECTION_HANDOFF}"
export VLLM_SELECTED_LAYER_FX_SOURCE_TRACE="${SOURCE_TRACE}"
export VLLM_SELECTED_LAYER_FX_TRACING_MODE=fake
export VLLM_SELECTED_LAYER_FX_ALLOW_NON_FAKE_INPUTS=1
export VLLM_SELECTED_LAYER_FX_STRIP_TENSOR_DATA_FOR_SAVE=1
export VLLM_R032_FX_FINALIZE_FILE="${TRACE_DIR}/FINALIZE_REQUESTED"
export VLLM_R032_FX_DONE_FILE="${TRACE_DIR}/FINALIZE_DONE.json"
export VLLM_R032_FINALIZE_PROTOCOL="controller creates FINALIZE_REQUESTED only after the single HTTP request client has returned"
export VLLM_TRACE_RUN_ID="${RUN_ID}"
export VLLM_TRACE_CONTRACT_ID="${CONTRACT_ID}"
export VLLM_R032_SOURCE_ROOT="${SOURCE_ROOT}"
export VLLM_R032_SOURCE_REVISION=3d03614452cd0a925abc82a7686560ff80252dfa
export VLLM_R032_MODEL_PATH="${MODEL_PATH}"
export VLLM_R032_MODEL_CONFIG_SHA256=f8d190c5b89c1521220f935d2567a587d6e291ed69066a45a106560b05a2174c
export VLLM_R032_DEVICE_ID=HCU0:TCA23906041001
export VLLM_R032_DEVICE_SERIAL=01-000205-08VGT2

exec vllm serve "${MODEL_PATH}" \
    --served-model-name Qwen3.5-27B \
    --port 8001 \
    --trust-remote-code \
    --dtype bfloat16 \
    --tensor-parallel-size 1 \
    --max-num-seqs 128 \
    --max-num-batched-tokens 4096 \
    --gpu-memory-utilization 0.95 \
    --default-chat-template-kwargs '{"enable_thinking": false}' \
    --reasoning-parser qwen3 \
    --enable-auto-tool-choice \
    --tool-call-parser qwen3_coder \
    --enforce-eager
