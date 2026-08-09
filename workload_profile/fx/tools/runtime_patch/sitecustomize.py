"""Bootstrap the R032 selected-layer FX runtime sampler.

This directory is placed first on ``PYTHONPATH`` only for the R032 service.
The patch is opt-in and never changes an uninstrumented Python process.
"""

import os
import sys


if os.environ.get("VLLM_R032_FX_ENABLE") == "1":
    try:
        import r032_selected_layer_fx_patch

        r032_selected_layer_fx_patch.apply_patches()
    except BaseException as exc:  # pragma: no cover - boot evidence records this too.
        sys.stderr.write(f"[r032-selected-layer-fx] bootstrap failed: {exc!r}\n")
