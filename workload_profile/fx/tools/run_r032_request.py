#!/usr/bin/env python3
"""Run the exact R02-selected single chat request with its source request id."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

from vllm.benchmarks.lib.endpoint_request_func import (
    RequestFuncInput,
    async_request_openai_chat_completions,
)
from vllm.transformers_utils.tokenizer import get_tokenizer


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def load_selected_request_id(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    request_ids = {row["request_id"] for row in rows}
    if len(rows) != 9 or len(request_ids) != 1:
        raise RuntimeError(
            f"expected nine selected rows for one request, got rows={len(rows)} "
            f"request_ids={sorted(request_ids)}"
        )
    return next(iter(request_ids))


async def run_request(
    request_input: RequestFuncInput,
) -> Any:
    timeout = aiohttp.ClientTimeout(total=1800)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        return await async_request_openai_chat_completions(
            request_input,
            session,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--selected-manifest", required=True, type=Path)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("/home/testdata/16-32K_throughput.jsonl"),
    )
    parser.add_argument("--model-path", default="/home/Qwen3.5-27B")
    parser.add_argument("--source-result", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    result_path = output_dir / "result.json"
    contract_path = output_dir / "request_contract.json"
    if result_path.exists() or contract_path.exists():
        raise RuntimeError(f"refusing to overwrite request evidence in {output_dir}")

    selected_manifest = args.selected_manifest.resolve()
    dataset = args.dataset.resolve()
    source_result_path = args.source_result.resolve()
    source_result = json.loads(source_result_path.read_text(encoding="utf-8"))
    source_request_id = load_selected_request_id(selected_manifest)
    if not source_request_id.startswith("chatcmpl-"):
        raise RuntimeError(f"unexpected source request id: {source_request_id}")
    header_request_id = source_request_id.removeprefix("chatcmpl-")

    first_line = next(
        line for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()
    )
    record = json.loads(first_line)
    raw_prompt = str(record["prompt"])
    tokenizer = get_tokenizer(args.model_path, trust_remote_code=True)
    benchmark_prompt = tokenizer.apply_chat_template(
        [{"role": "user", "content": raw_prompt}],
        add_generation_prompt=True,
        tokenize=False,
    )
    prompt_len = len(tokenizer(benchmark_prompt).input_ids)
    expected_input_lens = source_result.get("input_lens")
    if expected_input_lens != [prompt_len]:
        raise RuntimeError(
            f"request preprocessing drift: prompt_len={prompt_len}, "
            f"source={expected_input_lens}"
        )

    request_contract = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": f"http://{args.host}:{args.port}/v1/chat/completions",
        "model": "Qwen3.5-27B",
        "model_path": args.model_path,
        "dataset": str(dataset),
        "dataset_sha256": sha256_file(dataset),
        "selected_manifest": str(selected_manifest),
        "selected_manifest_sha256": sha256_file(selected_manifest),
        "source_result": str(source_result_path),
        "source_result_sha256": sha256_file(source_result_path),
        "source_request_id": source_request_id,
        "x_request_id": header_request_id,
        "prompt_sha256": hashlib.sha256(raw_prompt.encode()).hexdigest(),
        "benchmark_prompt_sha256": hashlib.sha256(
            benchmark_prompt.encode()
        ).hexdigest(),
        "prompt_len": prompt_len,
        "max_completion_tokens": 1024,
        "temperature": 0.0,
        "stream": True,
        "conversation_mode": (
            "OpenAI chat request containing the same tokenizer-templated custom "
            "dataset prompt used by vllm bench serve"
        ),
    }
    write_json_atomic(contract_path, request_contract)

    request_input = RequestFuncInput(
        prompt=benchmark_prompt,
        api_url=request_contract["endpoint"],
        prompt_len=prompt_len,
        output_len=1024,
        model=args.model_path,
        model_name="Qwen3.5-27B",
        extra_body={"temperature": 0.0},
        request_id=header_request_id,
    )
    started = time.perf_counter()
    response = asyncio.run(run_request(request_input))
    ended = time.perf_counter()
    completed = 1 if response.success else 0
    failed = 0 if response.success else 1
    output_tokens = int(response.output_tokens or 0)
    result = {
        "schema_version": 1,
        "date": datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
        "endpoint_type": "openai-chat",
        "backend": "openai-chat",
        "model_id": "Qwen3.5-27B",
        "tokenizer_id": args.model_path,
        "num_prompts": 1,
        "max_concurrency": 1,
        "temperature": 0.0,
        "custom_output_len": 1024,
        "request_id": source_request_id,
        "request_header_id": header_request_id,
        "completed": completed,
        "failed": failed,
        "duration": ended - started,
        "input_lens": [prompt_len],
        "output_lens": [output_tokens],
        "generated_texts": [response.generated_text],
        "errors": [response.error],
        "ttfts": [response.ttft],
        "itls": [response.itl],
        "response_equivalence_to_source": {
            "completed": completed == source_result.get("completed"),
            "failed": failed == source_result.get("failed"),
            "input_lens": [prompt_len] == source_result.get("input_lens"),
            "output_lens": [output_tokens] == source_result.get("output_lens"),
            "generated_texts": [response.generated_text]
            == source_result.get("generated_texts"),
        },
    }
    write_json_atomic(result_path, result)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    if not response.success or not all(
        result["response_equivalence_to_source"].values()
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
