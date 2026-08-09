"""Small R02 additions to the previously audited vLLM trace patch."""

from __future__ import annotations

import functools
import os
import time
import traceback
from typing import Any


_PREPARED = False
_PATCHED = False


def prepare_base(base: Any) -> None:
    """Enrich common fields and make list summaries device-sync safe."""
    global _PREPARED
    if _PREPARED:
        return
    _PREPARED = True

    original_write_event = base._write_event
    original_small_list = base._small_list

    def enriched_write_event(event_type: str, **payload: Any) -> None:
        payload.setdefault(
            "source_revision", os.environ.get("VLLM_TRACE_SOURCE_REVISION")
        )
        payload.setdefault("trace_mode", os.environ.get("VLLM_TRACE_MODE"))
        payload.setdefault("rank", os.environ.get("VLLM_TRACE_RANK", "0"))
        payload.setdefault(
            "worker_id", os.environ.get("VLLM_TRACE_WORKER_ID", "rank0")
        )
        payload.setdefault("device_id", os.environ.get("VLLM_TRACE_DEVICE_ID"))
        original_write_event(event_type, **payload)

    def sync_safe_small_list(
        value: Any, limit: int = 16
    ) -> dict[str, Any] | list[Any] | None:
        device = getattr(value, "device", None)
        if device is not None and str(device) != "cpu":
            summary = base._tensor_summary(value)
            if summary is not None:
                return {"device_tensor_summary": summary}
            return None
        return original_small_list(value, limit)

    base._write_event = enriched_write_event
    base._small_list = sync_safe_small_list
    base._ALWAYS_EVENTS.add("patch_loaded_extension")


def apply_patches(base: Any) -> None:
    """Patch the one R01-declared lifecycle gap: KVCacheManager.free."""
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    try:
        from vllm.v1.core.kv_cache_manager import KVCacheManager

        def free_wrapper(original: Any) -> Any:
            @functools.wraps(original)
            def wrapped(self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
                request_id = getattr(request, "request_id", None)
                free_before = None
                usage_before = None
                try:
                    free_before = self.block_pool.get_num_free_blocks()
                    usage_before = self.usage
                except Exception:
                    pass

                started = time.monotonic_ns()
                with base._record_scope("profile.kv_free"):
                    result = original(self, request, *args, **kwargs)

                free_after = None
                usage_after = None
                try:
                    free_after = self.block_pool.get_num_free_blocks()
                    usage_after = self.usage
                except Exception:
                    pass

                base._write_event(
                    "kv_free",
                    engine_step_id=base._current_step_id(),
                    cache_event_id=base._next_id(self, "_trace_cache_event_id"),
                    request_id=request_id,
                    duration_ns=time.monotonic_ns() - started,
                    request_status=str(getattr(request, "status", None)),
                    num_prompt_tokens=base._safe_int(
                        getattr(request, "num_prompt_tokens", None)
                    ),
                    num_computed_tokens=base._safe_int(
                        getattr(request, "num_computed_tokens", None)
                    ),
                    num_output_tokens=base._safe_int(
                        getattr(request, "num_output_tokens", None)
                    ),
                    free_blocks_before=free_before,
                    free_blocks_after=free_after,
                    freed_block_count=(
                        free_after - free_before
                        if free_before is not None and free_after is not None
                        else None
                    ),
                    cache_usage_before=usage_before,
                    cache_usage_after=usage_after,
                )
                return result

            return wrapped

        base._wrap_method(KVCacheManager, "free", free_wrapper)
        base._write_event(
            "patch_loaded_extension",
            extension="R02_kv_free_and_sync_safe_metadata",
            patched_symbols=["vllm.v1.core.kv_cache_manager.KVCacheManager.free"],
            device_tensor_to_list_forbidden=True,
        )
    except BaseException:
        base._write_event(
            "patch_error",
            where="r02_kv_free_extension",
            traceback=traceback.format_exc(),
        )
