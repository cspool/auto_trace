"""Adapt observed startup profile memory; preserve exact R01 final cache geometry."""
import functools,time
from typing import Any

def install(original):
    import torch
    from vllm.v1.core.kv_cache_utils import get_kv_cache_groups
    from vllm.v1.worker.gpu_worker import Worker as GPUWorker
    current=GPUWorker.determine_available_memory
    if getattr(current,'_r08_current_memory_profile',False):return
    if not getattr(current,'_qwen_dcu_r01_kv_target_restored',False):
        raise RuntimeError('original R01 worker policy missing')
    current_determine=current.__wrapped__
    EXPECTED_KV_CACHE_TOKENS=original.EXPECTED_KV_CACHE_TOKENS
    MINIMUM_POST_RESTORATION_RESERVE_BYTES=original.MINIMUM_POST_RESTORATION_RESERVE_BYTES
    PHYSICAL_DEVICE_BY_DP_RANK=original.PHYSICAL_DEVICE_BY_DP_RANK
    _append_event=original._append_event
    def determine_available_memory(worker: Any) -> int:
        observed_bytes = int(current_determine(worker))
        specs = dict(worker.get_kv_cache_spec())
        if len(specs) != 64:
            raise RuntimeError(f"R01 KV spec inventory mismatch: {len(specs)}")
        groups = get_kv_cache_groups(worker.vllm_config, dict(specs))
        if len(groups) != 4:
            raise RuntimeError(f"R01 hybrid KV group count mismatch: {len(groups)}")
        block_sizes = {int(group.kv_cache_spec.block_size) for group in groups}
        page_sizes = {int(group.kv_cache_spec.page_size_bytes) for group in groups}
        group_sizes = {len(group.layer_names) for group in groups}
        if (
            block_sizes != {784, 262_144}
            or page_sizes != {3_211_264}
            or group_sizes != {16}
        ):
            raise RuntimeError(
                "R01 hybrid KV geometry mismatch: "
                f"block_sizes={block_sizes} page_sizes={page_sizes} "
                f"group_sizes={group_sizes}"
            )
        block_size = min(block_sizes)
        page_size = page_sizes.pop()
        group_size = group_sizes.pop()
        observed_num_blocks = observed_bytes // page_size // group_size
        observed_tokens = observed_num_blocks // len(groups) * block_size
        if observed_bytes <= 0:
            raise RuntimeError("R08 measured KV memory must be positive")
        if EXPECTED_KV_CACHE_TOKENS % block_size:
            raise RuntimeError("R01 target KV tokens are not block aligned")
        target_num_blocks = (
            EXPECTED_KV_CACHE_TOKENS // block_size * len(groups)
        )
        target_bytes = target_num_blocks * page_size * group_size
        restoration_bytes = target_bytes - observed_bytes
        if restoration_bytes <= 0:
            raise RuntimeError(
                f"R01 KV restoration is not positive: {restoration_bytes}"
            )
        unrequested_reserve_bytes = int(
            worker.init_snapshot.free_memory - worker.requested_memory
        )
        remaining_reserve_bytes = unrequested_reserve_bytes - restoration_bytes
        if remaining_reserve_bytes < MINIMUM_POST_RESTORATION_RESERVE_BYTES:
            raise RuntimeError(
                "R01 KV restoration would consume the safety reserve: "
                f"remaining={remaining_reserve_bytes}"
            )
        dp_rank = int(torch.cuda.current_device())
        worker.available_kv_cache_memory_bytes = target_bytes
        _append_event(
            {
                "kind": "kv_cache_profile_overhead_restoration",
                "status": "ready",
                "dp_rank": dp_rank,
                "physical_device_id": PHYSICAL_DEVICE_BY_DP_RANK[dp_rank],
                "observed_available_bytes": observed_bytes,
                "observed_num_blocks": observed_num_blocks,
                "observed_cache_tokens": observed_tokens,
                "target_available_bytes": target_bytes,
                "target_num_blocks": target_num_blocks,
                "target_cache_tokens": EXPECTED_KV_CACHE_TOKENS,
                "restoration_bytes": restoration_bytes,
                "unrequested_reserve_bytes": unrequested_reserve_bytes,
                "remaining_reserve_bytes": remaining_reserve_bytes,
                "minimum_required_remaining_reserve_bytes": (
                    MINIMUM_POST_RESTORATION_RESERVE_BYTES
                ),
                "hybrid_group_count": len(groups),
                "layers_per_group": group_size,
                "block_size_tokens": block_size,
                "page_size_bytes": page_size,
                "reason": "r08_current_device_measured_profile_peak_compensation_same_final_cache_target",
                "realtime_ns": time.time_ns(),
                "monotonic_ns": time.perf_counter_ns(),
            }
        )
        print(
            "R01_KV_TARGET_RESTORATION "
            f"dp_rank={dp_rank} observed_tokens={observed_tokens} "
            f"target_tokens={EXPECTED_KV_CACHE_TOKENS} "
            f"observed_bytes={observed_bytes} target_bytes={target_bytes} "
            f"restoration_bytes={restoration_bytes} "
            f"remaining_reserve_bytes={remaining_reserve_bytes} status=ready",
            flush=True,
        )
        return target_bytes
    determine_available_memory._r08_current_memory_profile=True
    determine_available_memory._qwen_dcu_r01_kv_target_restored=True
    GPUWorker.determine_available_memory=determine_available_memory
