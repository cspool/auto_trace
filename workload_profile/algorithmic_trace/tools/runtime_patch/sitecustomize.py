"""Bootstrap the audited Qwen3.5 runtime tracer for R02.

The proven base patch is loaded from the path declared by
``VLLM_TRACE_BASE_PATCH_DIR``.  The local extension enriches common identity
fields, rejects device-tensor list conversion, and adds the missing KV free
transition before the base patches are applied.
"""

from __future__ import annotations

import os
import sys


if os.environ.get("VLLM_TRACE_PATCH_ENABLE") == "1":
    try:
        base_patch_dir = os.environ["VLLM_TRACE_BASE_PATCH_DIR"]
        if base_patch_dir not in sys.path:
            sys.path.append(base_patch_dir)

        import r02_trace_extension
        import vllm_trace_patch

        r02_trace_extension.prepare_base(vllm_trace_patch)
        vllm_trace_patch.apply_patches()
        r02_trace_extension.apply_patches(vllm_trace_patch)
    except BaseException as exc:  # pragma: no cover - audit fails closed later.
        sys.stderr.write(
            f"[r02-trace-bootstrap] failed to apply patches: {exc!r}\n"
        )
