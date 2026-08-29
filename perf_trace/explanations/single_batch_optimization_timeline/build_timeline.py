#!/usr/bin/env python3
"""Build an evidence-bound static explanation from the accepted Perfetto trace.

This script only reads the existing trace.  It does not run the model, profiler,
or accelerator.  Chrome-trace timestamps and durations are in microseconds.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import ijson
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import Patch


TRACE = Path(
    "/public/home/tangyu408/auto_trace/perf_trace/acceptance/"
    "workflow01-10-fresh-e2e-dcu1-20260806-r10-replay002-all-rectangle-labels/"
    "E2E_PROCESS_TIMELINE.full.perfetto.json"
)
OUT_DIR = Path(__file__).resolve().parent
OUT_PNG = OUT_DIR / "single_batch_optimization_timeline.png"
OUT_SVG = OUT_DIR / "single_batch_optimization_timeline.svg"


COLORS = {
    "prefill": "#E69F00",
    "decode": "#3B82F6",
    "MMAC GEMM": "#7E57C2",
    "GDN recurrent": "#009E73",
    "GQA6 direct": "#0072B2",
    "page784 main": "#D55E00",
    "page784 tail": "#F0C84B",
    "page784 pack/merge": "#CC79A7",
    "K5120 GEMV": "#E64B35",
    "K17408 GEMV": "#F39C34",
    "Decode attention": "#4C78A8",
    "RMS/copy": "#66C2A5",
    "Other": "#A7ADB7",
}


def input_id(process: str) -> int | None:
    match = re.search(r"input(\d+)_layer", process)
    return int(match.group(1)) if match else None


def classify_prefill(kernel: dict) -> str:
    name = kernel["name"]
    family = kernel["family"]
    process = kernel["process"]
    if "kernel_unified_attention_2d_gqa6" in name:
        return "GQA6 direct"
    if "flash_fwd_unified_kernel_16x64_prefetch" in name and "kv_cache_attention" in process:
        return "page784 main"
    if "flash_fwd_kernel_16x64_prefetch" in name and "kv_cache_attention" in process:
        return "page784 tail"
    if "_merge_three_attn_states" in name or "_pack_page784_residual" in name:
        return "page784 pack/merge"
    if family == "TunableOp_MMAC_GEMM":
        return "MMAC GEMM"
    if family == "GDN_recurrent":
        return "GDN recurrent"
    return "Other"


def classify_decode(kernel: dict) -> str:
    name = kernel["name"]
    family = kernel["family"]
    if "LLGemm1_k5120_pairreduce640_kernel" in name:
        return "K5120 GEMV"
    if "LLGemm1_qwen35_output_kernel<17408" in name:
        return "K17408 GEMV"
    if family == "TunableOp_MMAC_GEMM":
        return "MMAC GEMM"
    if "kernel_unified_attention_3d" in name:
        return "Decode attention"
    if family == "GDN_recurrent":
        return "GDN recurrent"
    return "Other"


def classify_zoom(kernel: dict) -> str:
    category = classify_decode(kernel)
    if category != "Other":
        return category
    if kernel["family"] in {"RMSNorm", "copy_cache"}:
        return "RMS/copy"
    return "Other"


def read_trace() -> tuple[dict, dict[int, dict], list[dict], dict]:
    request: dict = {}
    forwards: dict[int, dict] = {}
    kernels: list[dict] = []
    zoom_layer: dict = {}

    with TRACE.open("rb") as stream:
        for event in ijson.items(stream, "traceEvents.item"):
            category = event.get("cat")
            args = event.get("args", {})
            if category == "request":
                request = {
                    "ts_us": float(event["ts"]),
                    "dur_us": float(event["dur"]),
                }
            elif category == "forward":
                forward_id = int(event["name"].split()[-1])
                forwards[forward_id] = {
                    "id": forward_id,
                    "phase": args.get("phase", ""),
                    "ts_us": float(event["ts"]),
                    "dur_us": float(event["dur"]),
                }
            elif category == "layer" and args.get("forward") == "10" and args.get("layer") == "0":
                zoom_layer = {
                    "forward": 10,
                    "layer": 0,
                    "ts_us": float(event["ts"]),
                    "dur_us": float(event["dur"]),
                }
            elif category == "strict_owned_kernel":
                process = args.get("process", "")
                forward_id = input_id(process)
                if forward_id is None:
                    continue
                kernels.append(
                    {
                        "forward": forward_id,
                        "name": event.get("name", ""),
                        "family": args.get("family", ""),
                        "process": process,
                        "ts_us": float(event["ts"]),
                        "dur_us": float(event["dur"]),
                    }
                )

    if not request or len(forwards) != 29 or not zoom_layer:
        raise RuntimeError("Trace hierarchy did not match the accepted 1-request/29-forward contract")
    return request, forwards, kernels, zoom_layer


def stacked_values(
    ids: list[int], kernels_by_forward: dict[int, list[dict]], classifier, categories: list[str]
) -> tuple[dict[str, list[float]], list[float]]:
    values = {category: [] for category in categories}
    totals: list[float] = []
    for forward_id in ids:
        row = defaultdict(float)
        for kernel in kernels_by_forward[forward_id]:
            row[classifier(kernel)] += kernel["dur_us"] / 1000.0
        for category in categories:
            values[category].append(row[category])
        totals.append(sum(row.values()))
    return values, totals


def main() -> None:
    request, forwards, kernels, zoom_layer = read_trace()
    kernels_by_forward: dict[int, list[dict]] = defaultdict(list)
    for kernel in kernels:
        kernels_by_forward[kernel["forward"]].append(kernel)

    prefill_ids = list(range(1, 7))
    decode_ids = list(range(7, 30))
    prefill_categories = [
        "MMAC GEMM",
        "GDN recurrent",
        "GQA6 direct",
        "page784 main",
        "page784 tail",
        "page784 pack/merge",
        "Other",
    ]
    decode_categories = [
        "K5120 GEMV",
        "K17408 GEMV",
        "MMAC GEMM",
        "Decode attention",
        "GDN recurrent",
        "Other",
    ]
    prefill_values, prefill_totals = stacked_values(
        prefill_ids, kernels_by_forward, classify_prefill, prefill_categories
    )
    decode_values, decode_totals = stacked_values(
        decode_ids, kernels_by_forward, classify_decode, decode_categories
    )

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10.5,
            "axes.titlesize": 13,
            "axes.labelsize": 10.5,
            "axes.edgecolor": "#485260",
            "axes.linewidth": 0.8,
            "xtick.color": "#374151",
            "ytick.color": "#374151",
            "text.color": "#17202A",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )

    figure = plt.figure(figsize=(16, 14), constrained_layout=False)
    grid = figure.add_gridspec(
        4,
        1,
        height_ratios=[1.25, 2.4, 2.5, 2.35],
        hspace=0.55,
        top=0.925,
        bottom=0.065,
        left=0.075,
        right=0.975,
    )
    figure.suptitle(
        "Single-request optimization timeline — bh408 observed trace",
        fontsize=19,
        fontweight="bold",
        x=0.075,
        ha="left",
        y=0.977,
    )
    figure.text(
        0.075,
        0.947,
        "Existing trace only; 6 chunked-prefill forwards + 23 decode forwards, BF16 / TP=1 / eager instrumentation",
        fontsize=11,
        color="#566573",
        ha="left",
    )

    # A. Exact request-level wall-clock positions.
    axis = figure.add_subplot(grid[0])
    request_seconds = request["dur_us"] / 1_000_000.0
    prefill_begin = forwards[1]["ts_us"] / 1_000_000.0
    prefill_end = (forwards[6]["ts_us"] + forwards[6]["dur_us"]) / 1_000_000.0
    decode_begin = forwards[7]["ts_us"] / 1_000_000.0
    decode_end = (forwards[29]["ts_us"] + forwards[29]["dur_us"]) / 1_000_000.0
    axis.axvspan(prefill_begin, prefill_end, color=COLORS["prefill"], alpha=0.08, linewidth=0)
    axis.axvspan(decode_begin, decode_end, color=COLORS["decode"], alpha=0.07, linewidth=0)
    for forward_id in range(1, 30):
        forward = forwards[forward_id]
        begin = forward["ts_us"] / 1_000_000.0
        duration = forward["dur_us"] / 1_000_000.0
        phase = "prefill" if forward["phase"] == "prefill_chunk" else forward["phase"]
        axis.broken_barh(
            [(begin, duration)],
            (0.76, 0.48),
            facecolors=COLORS[phase],
            edgecolors="white",
            linewidth=0.7,
        )
        if forward_id <= 6:
            label = f"P{forward_id}"
        else:
            decode_step = forward_id - 6
            label = f"D{decode_step}" if decode_step in {1, 5, 10, 15, 20, 23} else ""
        if label:
            axis.text(begin + duration / 2, 1.0, label, ha="center", va="center", fontsize=8, color="white")

    prefill_segments = []
    decode_segments = []
    for kernel in kernels:
        start = kernel["ts_us"] / 1_000_000.0
        end = (kernel["ts_us"] + kernel["dur_us"]) / 1_000_000.0
        segment = [(start, 0.27), (end, 0.27)]
        if kernel["forward"] <= 6:
            prefill_segments.append(segment)
        else:
            decode_segments.append(segment)
    axis.add_collection(
        LineCollection(prefill_segments, colors=COLORS["prefill"], linewidths=3.6, rasterized=True)
    )
    axis.add_collection(
        LineCollection(decode_segments, colors=COLORS["decode"], linewidths=3.6, rasterized=True)
    )
    axis.set_xlim(0, request_seconds)
    axis.set_ylim(-0.02, 1.47)
    axis.set_yticks([0.27, 1.0], ["Strict GPU kernels", "Forward envelopes"])
    axis.set_xlabel("Time from request begin (s)")
    axis.set_title("A  Observed end-to-end wall-clock positions", loc="left", fontweight="bold")
    axis.text(
        (prefill_begin + prefill_end) / 2,
        1.38,
        f"Prefill span {prefill_end - prefill_begin:.3f}s",
        ha="center",
        color="#9A6700",
        fontweight="bold",
    )
    axis.text(
        (decode_begin + decode_end) / 2,
        1.38,
        f"Decode span {decode_end - decode_begin:.3f}s",
        ha="center",
        color="#1E5AA8",
        fontweight="bold",
    )
    axis.text(
        request_seconds,
        0.02,
        f"request span {request_seconds:.3f}s (instrumented; not production E2E)",
        ha="right",
        va="bottom",
        fontsize=9,
        color="#6B7280",
    )
    axis.grid(axis="x", color="#E5E7EB", linewidth=0.7)
    axis.spines[["top", "right"]].set_visible(False)

    # B. Prefill composition, preserving one row per observed chunk.
    axis = figure.add_subplot(grid[1])
    y = list(range(len(prefill_ids)))
    left = [0.0] * len(prefill_ids)
    for category in prefill_categories:
        values = prefill_values[category]
        axis.barh(
            y,
            values,
            left=left,
            height=0.68,
            label=category,
            color=COLORS[category],
            edgecolor="white",
            linewidth=0.35,
        )
        left = [a + b for a, b in zip(left, values)]
    max_prefill = max(prefill_totals)
    for index, forward_id in enumerate(prefill_ids):
        route = "direct GQA6" if forward_id in {1, 6} else "page784 main + tail + merge"
        axis.text(
            prefill_totals[index] + max_prefill * 0.015,
            index,
            f"kernel sum {prefill_totals[index]:.1f}ms  |  {route}",
            va="center",
            fontsize=8.8,
            color="#374151",
        )
    axis.set_xlim(0, max_prefill * 1.47)
    axis.set_yticks(y, [f"P{forward_id}" for forward_id in prefill_ids])
    axis.invert_yaxis()
    axis.set_xlabel("Accumulated strict GPU-kernel time (ms)")
    axis.set_title(
        "B  Prefill chunks — kernel-time composition exposes the GQA6/page784 routing",
        loc="left",
        fontweight="bold",
        pad=48,
    )
    axis.legend(ncol=4, loc="lower left", bbox_to_anchor=(0.0, 1.005), frameon=False, fontsize=8.8)
    axis.grid(axis="x", color="#E5E7EB", linewidth=0.7)
    axis.spines[["top", "right"]].set_visible(False)

    # C. Decode composition per token/forward.
    axis = figure.add_subplot(grid[2])
    x = list(range(1, len(decode_ids) + 1))
    bottom = [0.0] * len(decode_ids)
    for category in decode_categories:
        values = decode_values[category]
        axis.bar(
            x,
            values,
            bottom=bottom,
            width=0.82,
            label=category,
            color=COLORS[category],
            edgecolor="white",
            linewidth=0.25,
        )
        bottom = [a + b for a, b in zip(bottom, values)]
    decode_mean = sum(decode_totals) / len(decode_totals)
    axis.axhline(decode_mean, color="#111827", linestyle="--", linewidth=1.2)
    axis.text(
        23.45,
        decode_mean,
        f" mean {decode_mean:.2f}ms",
        ha="left",
        va="center",
        fontsize=9,
        color="#111827",
    )
    axis.axhspan(40.80, 42.64, color="#111827", alpha=0.055, linewidth=0)
    axis.text(
        0.55,
        41.72,
        "modular production mean TPOT range (separate benchmark)",
        ha="left",
        va="center",
        fontsize=8.2,
        color="#4B5563",
    )
    total_decode = sum(decode_totals)
    gemv_decode = sum(decode_values["K5120 GEMV"]) + sum(decode_values["K17408 GEMV"])
    gemm_decode = gemv_decode + sum(decode_values["MMAC GEMM"])
    axis.text(
        0.985,
        0.94,
        f"K5120 + K17408 = {gemv_decode / total_decode * 100:.1f}% of decode GPU time\n"
        f"+ MMAC GEMM = {gemm_decode / total_decode * 100:.1f}%",
        transform=axis.transAxes,
        ha="right",
        va="top",
        bbox={"boxstyle": "round,pad=0.4", "facecolor": "white", "edgecolor": "#CBD5E1"},
        fontsize=9.2,
    )
    axis.set_xlim(0.3, 24.4)
    axis.set_xticks([1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23])
    axis.set_xlabel("Decode step")
    axis.set_ylabel("Accumulated strict GPU-kernel time (ms)")
    axis.set_title(
        "C  Decode — the two custom GEMV paths dominate every step",
        loc="left",
        fontweight="bold",
        pad=48,
    )
    axis.legend(ncol=6, loc="lower left", bbox_to_anchor=(0.0, 1.005), frameon=False, fontsize=8.8)
    axis.grid(axis="y", color="#E5E7EB", linewidth=0.7)
    axis.spines[["top", "right"]].set_visible(False)

    # D. Exact launch positions for a representative decode layer.
    axis = figure.add_subplot(grid[3])
    zoom_kernels = [
        kernel for kernel in kernels_by_forward[10] if "input10_layer0." in kernel["process"]
    ]
    zoom_categories = [
        "K5120 GEMV",
        "K17408 GEMV",
        "MMAC GEMM",
        "GDN recurrent",
        "RMS/copy",
        "Other",
    ]
    y_positions = {category: len(zoom_categories) - index - 1 for index, category in enumerate(zoom_categories)}
    for kernel in zoom_kernels:
        category = classify_zoom(kernel)
        begin_ms = (kernel["ts_us"] - zoom_layer["ts_us"]) / 1000.0
        duration_ms = kernel["dur_us"] / 1000.0
        axis.broken_barh(
            [(begin_ms, duration_ms)],
            (y_positions[category] - 0.30, 0.60),
            facecolors=COLORS[category],
            edgecolors="#263238",
            linewidth=0.35,
        )
        if duration_ms >= 0.012:
            short_name = category
            if category == "Other" and "act_and_mul_kernel" in kernel["name"]:
                short_name = "act_and_mul"
            above = begin_ms < 3.8
            label_y = y_positions[category] + (0.55 if above else -0.55)
            axis.annotate(
                f"{short_name}\n{duration_ms * 1000:.1f}us",
                xy=(begin_ms + duration_ms / 2, y_positions[category] + 0.31),
                xytext=(begin_ms + duration_ms / 2, label_y),
                ha="center",
                va="bottom" if above else "top",
                fontsize=7.2,
                color="#263238",
                arrowprops={"arrowstyle": "-", "color": "#64748B", "linewidth": 0.5},
            )
    zoom_sum_ms = sum(kernel["dur_us"] for kernel in zoom_kernels) / 1000.0
    zoom_envelope_ms = zoom_layer["dur_us"] / 1000.0
    zoom_tail_ms = max(
        (kernel["ts_us"] - zoom_layer["ts_us"] + kernel["dur_us"]) / 1000.0
        for kernel in zoom_kernels
    )
    axis.axvline(zoom_envelope_ms, color="#64748B", linestyle=":", linewidth=1.0)
    axis.set_xlim(0, max(zoom_envelope_ms, zoom_tail_ms) * 1.015)
    axis.set_ylim(-0.65, len(zoom_categories) - 0.05)
    axis.set_yticks(
        [y_positions[category] for category in zoom_categories],
        zoom_categories,
    )
    axis.set_xlabel("Time from forward 10 / layer 0 begin (ms)")
    axis.set_title(
        "D  Exact zoom — one observed decode layer (forward 10, layer 0)",
        loc="left",
        fontweight="bold",
    )
    axis.text(
        0.995,
        1.035,
        f"11 kernels; kernel sum {zoom_sum_ms:.3f}ms; layer envelope {zoom_envelope_ms:.3f}ms\n"
        "Gaps include eager/runtime/tracing effects; they are not a production idle-time claim.",
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        fontsize=8.7,
        bbox={"boxstyle": "round,pad=0.4", "facecolor": "white", "edgecolor": "#CBD5E1"},
    )
    axis.grid(axis="x", color="#E5E7EB", linewidth=0.7)
    axis.spines[["top", "right"]].set_visible(False)

    figure.text(
        0.075,
        0.018,
        "Evidence boundary: observed bh408@0abe1e1-dirty trace; no pre-optimization trace was rerun. "
        "Panels B/C sum strict-owned kernels by process attribution; async tails may extend beyond annotation envelopes. "
        "Nested process spans are not added.",
        fontsize=9.2,
        color="#566573",
        ha="left",
    )

    figure.savefig(OUT_PNG, dpi=210, bbox_inches="tight")
    figure.savefig(OUT_SVG, bbox_inches="tight")
    plt.close(figure)

    prefill_kernel_ms = sum(prefill_totals)
    prefill_envelope_ms = sum(forwards[index]["dur_us"] for index in prefill_ids) / 1000.0
    print(f"wrote {OUT_PNG}")
    print(f"wrote {OUT_SVG}")
    print(f"request_span_ms={request['dur_us'] / 1000.0:.3f}")
    print(f"prefill_kernel_ms={prefill_kernel_ms:.3f}")
    print(f"prefill_envelope_ms={prefill_envelope_ms:.3f}")
    print(f"decode_kernel_ms={total_decode:.3f}")
    print(f"decode_kernel_ms_per_step={decode_mean:.3f}")
    print(f"decode_custom_gemv_share={gemv_decode / total_decode:.6f}")
    print(f"decode_custom_gemv_plus_mmac_share={gemm_decode / total_decode:.6f}")
    print(f"zoom_layer_kernel_ms={zoom_sum_ms:.3f}")
    print(f"zoom_layer_envelope_ms={zoom_envelope_ms:.3f}")


if __name__ == "__main__":
    main()
