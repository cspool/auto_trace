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
from matplotlib.patches import Patch, Rectangle


TRACE = Path(
    "/public/home/tangyu408/auto_trace/perf_trace/acceptance/"
    "workflow01-10-fresh-e2e-dcu1-20260806-r10-replay002-all-rectangle-labels/"
    "E2E_PROCESS_TIMELINE.full.perfetto.json"
)
OUT_DIR = Path(__file__).resolve().parent
OUT_PNG = OUT_DIR / "single_batch_optimization_timeline.png"
OUT_SVG = OUT_DIR / "single_batch_optimization_timeline.svg"
PANEL_OUTPUTS = {
    "A": OUT_DIR / "panel_a_request_overview",
    "B": OUT_DIR / "panel_b_prefill_routes",
    "C": OUT_DIR / "panel_c_decode_composition",
    "D": OUT_DIR / "panel_d_decode_layer_zoom",
}


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

DEFAULT_RECTANGLE_SCALE = 3.0
C_RECTANGLE_SCALE = 9.0
D_RECTANGLE_SCALE = 6.0
A_RECTANGLE_LIMIT_S = 1.80
B_RECTANGLE_LIMIT_MS = 260.0
C_RECTANGLE_LIMIT_MS = 10.0
D_RECTANGLE_LIMIT_US = 360.0

# Physical readability scale. Duration transforms above remain unchanged so
# the displayed geometry keeps the documented coordinate meaning.
FIGURE_SIZE_IN = (32.0, 67.5)
A_FORWARD_THICKNESS = 0.425
A_LANE_SPACING = 0.50
B_ROW_SPACING = 1.35
C_BAR_WIDTH = 1.20
C_COLUMN_SPACING = 1.65
D_ROW_SPACING = 1.35
LOWER_LEFT_COORDINATE_FONT_SCALE = 2.0 / 3.0
STRICT_LANE_HEIGHT_SCALE = 0.5


def draw_scaled_rectangle(
    axis: plt.Axes,
    *,
    start: float,
    cross_start: float,
    duration: float,
    thickness: float,
    limit: float,
    color: str,
    scale: float = DEFAULT_RECTANGLE_SCALE,
    orientation: str = "horizontal",
    edgecolor: str = "white",
    linewidth: float = 0.35,
    fold_linewidth: float | None = None,
    fold_amplitude_fraction: float = 0.22,
    zorder: float = 2.0,
) -> tuple[float, bool]:
    """Scale a duration rectangle, folding capped spans into two blocks."""
    scaled = duration * scale
    visible = min(scaled, limit)
    folded = scaled > limit

    if not folded:
        if orientation == "horizontal":
            patch = Rectangle(
                (start, cross_start), visible, thickness,
                facecolor=color, edgecolor=edgecolor, linewidth=linewidth, zorder=zorder,
            )
        else:
            patch = Rectangle(
                (cross_start, start), thickness, visible,
                facecolor=color, edgecolor=edgecolor, linewidth=linewidth, zorder=zorder,
            )
        axis.add_patch(patch)
        return visible, False

    gap = visible * 0.10
    block = (visible - gap) / 2.0
    if orientation == "horizontal":
        axis.add_patch(
            Rectangle(
                (start, cross_start), block, thickness,
                facecolor=color, edgecolor=edgecolor, linewidth=linewidth, zorder=zorder,
            )
        )
        axis.add_patch(
            Rectangle(
                (start + block + gap, cross_start), block, thickness,
                facecolor=color, edgecolor=edgecolor, linewidth=linewidth, zorder=zorder,
            )
        )
        x0 = start + block
        y0 = cross_start + thickness / 2.0
        axis.plot(
            [x0, x0 + gap * 0.25, x0 + gap * 0.50, x0 + gap * 0.75, x0 + gap],
            [
                y0,
                y0 + thickness * fold_amplitude_fraction,
                y0 - thickness * fold_amplitude_fraction,
                y0 + thickness * fold_amplitude_fraction,
                y0,
            ],
            color="#263238",
            linewidth=fold_linewidth if fold_linewidth is not None else max(0.7, linewidth),
            zorder=zorder + 0.2,
            solid_capstyle="round", clip_on=True,
        )
    else:
        axis.add_patch(
            Rectangle(
                (cross_start, start), thickness, block,
                facecolor=color, edgecolor=edgecolor, linewidth=linewidth, zorder=zorder,
            )
        )
        axis.add_patch(
            Rectangle(
                (cross_start, start + block + gap), thickness, block,
                facecolor=color, edgecolor=edgecolor, linewidth=linewidth, zorder=zorder,
            )
        )
        x0 = cross_start + thickness / 2.0
        y0 = start + block
        axis.plot(
            [
                x0,
                x0 + thickness * fold_amplitude_fraction,
                x0 - thickness * fold_amplitude_fraction,
                x0 + thickness * fold_amplitude_fraction,
                x0,
            ],
            [y0, y0 + gap * 0.25, y0 + gap * 0.50, y0 + gap * 0.75, y0 + gap],
            color="#263238",
            linewidth=fold_linewidth if fold_linewidth is not None else max(0.7, linewidth),
            zorder=zorder + 0.2,
            solid_capstyle="round", clip_on=True,
        )
    return visible, True


def assert_axis_contains_rectangles(
    axis: plt.Axes,
    *,
    panel: str,
    x_bounds: tuple[float, float],
    y_bounds: tuple[float, float],
) -> None:
    """Fail if the declared rectangle envelope falls outside the data axes."""
    x_min, x_max = sorted(axis.get_xlim())
    y_min, y_max = sorted(axis.get_ylim())
    rect_x_min, rect_x_max = sorted(x_bounds)
    rect_y_min, rect_y_max = sorted(y_bounds)
    tolerance = 1e-9
    if rect_x_min < x_min - tolerance or rect_x_max > x_max + tolerance:
        raise RuntimeError(
            f"Panel {panel} rectangle x bounds {x_bounds} exceed axis bounds {axis.get_xlim()}"
        )
    if rect_y_min < y_min - tolerance or rect_y_max > y_max + tolerance:
        raise RuntimeError(
            f"Panel {panel} rectangle y bounds {y_bounds} exceed axis bounds {axis.get_ylim()}"
        )


def data_height_points(axis: plt.Axes, figure: plt.Figure, data_height: float) -> float:
    """Convert a vertical data-axis height to physical points."""
    y_span = abs(axis.get_ylim()[1] - axis.get_ylim()[0])
    return (
        data_height
        / y_span
        * axis.get_position().height
        * figure.get_figheight()
        * 72.0
    )


def data_height_for_points(axis: plt.Axes, figure: plt.Figure, points: float) -> float:
    """Return the data-axis height needed for an exact physical point height."""
    y_span = abs(axis.get_ylim()[1] - axis.get_ylim()[0])
    return points / 72.0 / figure.get_figheight() / axis.get_position().height * y_span


def label_lower_left_coordinate(
    axis: plt.Axes,
    *,
    x: float,
    y: float,
    text: str,
    fontsize: float,
) -> None:
    """Place one enlarged display-coordinate value at a rectangle's lower-left."""
    axis.annotate(
        text,
        xy=(x, y),
        xytext=(3.0, 3.0),
        textcoords="offset points",
        ha="left",
        va="bottom",
        fontsize=fontsize * LOWER_LEFT_COORDINATE_FONT_SCALE,
        color="#263238",
        bbox={"boxstyle": "square,pad=0.06", "facecolor": "white", "edgecolor": "none", "alpha": 0.82},
        clip_on=True,
        zorder=3.3,
    )


def hide_overflowing_rectangle_texts(
    figure: plt.Figure,
    entries: list[tuple[plt.Axes, object, float, float]],
) -> int:
    """Hide one-line labels that do not fit their visible rectangle block."""
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    hidden = 0
    for axis, artist, rectangle_width, rectangle_height in entries:
        origin = axis.transData.transform((0.0, 0.0))
        width_point = axis.transData.transform((rectangle_width, 0.0))
        height_point = axis.transData.transform((0.0, rectangle_height))
        width_pixels = abs(width_point[0] - origin[0])
        height_pixels = abs(height_point[1] - origin[1])
        bbox = artist.get_window_extent(renderer=renderer)
        if bbox.width > width_pixels * 0.92 or bbox.height > height_pixels * 0.88:
            artist.set_visible(False)
            hidden += 1
    return hidden


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


def save_clean_svg(figure, output_path: Path, **savefig_kwargs) -> None:
    """Save a deterministic, editable SVG without diff-noisy trailing spaces."""
    figure.savefig(output_path, metadata={"Date": None}, **savefig_kwargs)
    svg = output_path.read_text(encoding="utf-8")
    output_path.write_text(
        "\n".join(line.rstrip() for line in svg.splitlines()) + "\n",
        encoding="utf-8",
    )


def save_individual_panels(figure, panels: dict[str, plt.Axes]) -> None:
    """Export each panel with its own title, labels, legend, and annotations."""
    figure.canvas.draw()
    axes_visibility = {axis: axis.get_visible() for axis in figure.axes}
    text_visibility = {artist: artist.get_visible() for artist in figure.texts}

    try:
        for panel_id, panel_axis in panels.items():
            for axis in figure.axes:
                axis.set_visible(axis is panel_axis)
            for artist in figure.texts:
                artist.set_visible(False)

            figure.canvas.draw()
            renderer = figure.canvas.get_renderer()
            bbox_inches = panel_axis.get_tightbbox(renderer).transformed(
                figure.dpi_scale_trans.inverted()
            )
            bbox_inches = bbox_inches.padded(0.20)
            output_base = PANEL_OUTPUTS[panel_id]
            figure.savefig(
                output_base.with_suffix(".png"),
                dpi=210,
                bbox_inches=bbox_inches,
                facecolor="white",
            )
            save_clean_svg(
                figure,
                output_base.with_suffix(".svg"),
                bbox_inches=bbox_inches,
                facecolor="white",
            )
    finally:
        for axis, visible in axes_visibility.items():
            axis.set_visible(visible)
        for artist, visible in text_visibility.items():
            artist.set_visible(visible)


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
    decode_group_indices = [
        list(range(start, min(start + 3, len(decode_ids))))
        for start in range(0, len(decode_ids), 3)
    ]
    decode_group_labels = [
        f"{indices[0] + 1}-{indices[-1] + 1}"
        for indices in decode_group_indices
    ]
    decode_group_values = {
        category: [
            sum(decode_values[category][index] for index in indices) / len(indices)
            for indices in decode_group_indices
        ]
        for category in decode_categories
    }
    top_prefill_ranks: dict[tuple[str, int], int] = {}
    for index in range(len(prefill_ids)):
        ranked = sorted(
            (
                (prefill_values[category][index], category)
                for category in prefill_categories
                if prefill_values[category][index] > 0
            ),
            reverse=True,
        )[:5]
        for rank, (_, category) in enumerate(ranked, start=1):
            top_prefill_ranks[(category, index)] = rank

    top_decode_ranks: dict[tuple[str, int], int] = {}
    for index in range(len(decode_group_indices)):
        ranked = sorted(
            (
                (decode_group_values[category][index], category)
                for category in decode_categories
                if decode_group_values[category][index] > 0
            ),
            reverse=True,
        )[:5]
        for rank, (_, category) in enumerate(ranked, start=1):
            top_decode_ranks[(category, index)] = rank

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 16.5,
            "axes.titlesize": 22,
            "axes.labelsize": 20,
            "axes.labelweight": "semibold",
            "axes.edgecolor": "#485260",
            "axes.linewidth": 2.2,
            "xtick.labelsize": 18,
            "ytick.labelsize": 18,
            "xtick.major.width": 2.0,
            "ytick.major.width": 2.0,
            "xtick.major.size": 8.0,
            "ytick.major.size": 8.0,
            "xtick.color": "#374151",
            "ytick.color": "#374151",
            "text.color": "#17202A",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "svg.fonttype": "none",
            "svg.hashsalt": "single-batch-optimization-timeline",
        }
    )

    figure = plt.figure(figsize=FIGURE_SIZE_IN, constrained_layout=False)
    grid = figure.add_gridspec(
        4,
        1,
        height_ratios=[1.65, 2.75, 4.75, 2.85],
        hspace=0.86,
        top=0.925,
        bottom=0.065,
        left=0.075,
        right=0.975,
    )
    figure.suptitle(
        "Single-request optimization timeline — bh408 observed trace",
        fontsize=25,
        fontweight="bold",
        x=0.075,
        ha="left",
        y=0.977,
    )
    figure.text(
        0.075,
        0.947,
        "Existing trace only; 6 chunked-prefill forwards + 23 decode forwards, BF16 / TP=1 / eager instrumentation",
        fontsize=14.5,
        color="#566573",
        ha="left",
    )

    panels: dict[str, plt.Axes] = {}
    rectangle_texts: list[tuple[plt.Axes, object, float, float]] = []

    # A. Exact request-level wall-clock positions.
    axis = figure.add_subplot(grid[0])
    panels["A"] = axis
    request_seconds = request["dur_us"] / 1_000_000.0
    prefill_begin = forwards[1]["ts_us"] / 1_000_000.0
    prefill_end = (forwards[6]["ts_us"] + forwards[6]["dur_us"]) / 1_000_000.0
    decode_begin = forwards[7]["ts_us"] / 1_000_000.0
    decode_end = (forwards[29]["ts_us"] + forwards[29]["dur_us"]) / 1_000_000.0
    axis.axvspan(prefill_begin, prefill_end, color=COLORS["prefill"], alpha=0.08, linewidth=0)
    axis.axvspan(decode_begin, decode_end, color=COLORS["decode"], alpha=0.07, linewidth=0)
    forward_display_end = request_seconds
    forward_lane_y = [0.92 + lane * A_LANE_SPACING for lane in range(3)]
    forward_lane_ids = {
        lane: [
            forward_id
            for forward_id in range(1, 30)
            if (forward_id - 1) % len(forward_lane_y) == lane
        ]
        for lane in range(len(forward_lane_y))
    }
    forward_lane_totals = {
        lane: sum(forwards[forward_id]["dur_us"] for forward_id in forward_ids)
        for lane, forward_ids in forward_lane_ids.items()
    }
    top_forward_ids: dict[int, int] = {}
    for forward_ids in forward_lane_ids.values():
        for rank, forward_id in enumerate(
            sorted(forward_ids, key=lambda item: forwards[item]["dur_us"], reverse=True)[:5],
            start=1,
        ):
            top_forward_ids[forward_id] = rank
    for forward_id in range(1, 30):
        forward = forwards[forward_id]
        begin = forward["ts_us"] / 1_000_000.0
        duration = forward["dur_us"] / 1_000_000.0
        phase = "prefill" if forward["phase"] == "prefill_chunk" else forward["phase"]
        lane_y = forward_lane_y[(forward_id - 1) % len(forward_lane_y)]
        visible_duration, folded = draw_scaled_rectangle(
            axis,
            start=begin,
            cross_start=lane_y - A_FORWARD_THICKNESS / 2.0,
            duration=duration,
            thickness=A_FORWARD_THICKNESS,
            limit=A_RECTANGLE_LIMIT_S,
            color=COLORS[phase],
            edgecolor="white",
            linewidth=0.7,
        )
        lane = (forward_id - 1) % len(forward_lane_y)
        if top_forward_ids.get(forward_id, 99) <= 3:
            label_lower_left_coordinate(
                axis,
                x=begin,
                y=lane_y - A_FORWARD_THICKNESS / 2.0,
                text=f"{begin:.2f}",
                fontsize=23.0,
            )
        forward_id_label = f"P{forward_id}" if forward_id <= 6 else f"D{forward_id - 6}"
        axis.annotate(
            forward_id_label,
            xy=(
                begin + visible_duration,
                lane_y + A_FORWARD_THICKNESS / 2.0,
            ),
            xytext=(-3.0, -3.0),
            textcoords="offset points",
            ha="right",
            va="top",
            fontsize=23.0 * LOWER_LEFT_COORDINATE_FONT_SCALE,
            color="#17202A" if phase == "prefill" else "white",
            fontweight="normal",
            clip_on=True,
            zorder=3.2,
        )
        forward_display_end = max(forward_display_end, begin + visible_duration)
        if forward_id in top_forward_ids:
            rank = top_forward_ids[forward_id]
            label = f"#{rank} {forward['dur_us'] / forward_lane_totals[lane] * 100:.1f}%"
        else:
            label = ""
        if label:
            label_x = begin + visible_duration / 2
            if forward_id in top_forward_ids and folded:
                label_x = begin + visible_duration * 0.225
            text_artist = axis.text(
                label_x,
                lane_y,
                label,
                ha="center",
                va="center",
                fontsize=26.0,
                color="white",
                fontweight="normal",
                zorder=3,
            )
            text_block_width = visible_duration * (0.45 if folded else 1.0)
            rectangle_texts.append(
                (axis, text_artist, text_block_width, A_FORWARD_THICKNESS)
            )

    prefill_segments = []
    decode_segments = []
    for kernel in kernels:
        start = kernel["ts_us"] / 1_000_000.0
        end = (kernel["ts_us"] + kernel["dur_us"]) / 1_000_000.0
        segment = [(start, 0.30), (end, 0.30)]
        if kernel["forward"] <= 6:
            prefill_segments.append(segment)
        else:
            decode_segments.append(segment)
    prefill_kernel_collection = LineCollection(
        prefill_segments,
        colors=COLORS["prefill"],
        linewidths=1.0,
        capstyle="butt",
        rasterized=True,
    )
    decode_kernel_collection = LineCollection(
        decode_segments,
        colors=COLORS["decode"],
        linewidths=1.0,
        capstyle="butt",
        rasterized=True,
    )
    axis.add_collection(prefill_kernel_collection)
    axis.add_collection(decode_kernel_collection)
    axis.set_xlim(0, forward_display_end * 1.01)
    axis.set_ylim(-0.06, 2.58)
    shared_rectangle_height_points = data_height_points(
        axis, figure, A_FORWARD_THICKNESS
    )
    axis.set_yticks(
        [0.30, forward_lane_y[1]],
        [
            "Strict\nGPU\nkernels",
            "Forward\nenvelopes\n3 display lanes\nnot concurrent",
        ],
    )
    axis.set_xlabel(
        "X-axis — hybrid display time (seconds, s)\n"
        "left edge = observed start; visible width = min(3 x actual duration, 1.80 s)"
    )
    axis.set_ylabel("Y-axis — execution track\n(categorical; no physical unit)")
    axis.set_title("A  Observed end-to-end wall-clock positions", loc="left", fontweight="bold")
    axis.text(
        (prefill_begin + prefill_end) / 2,
        2.43,
        f"Prefill span {prefill_end - prefill_begin:.3f}s",
        ha="center",
        color="#9A6700",
        fontweight="bold",
    )
    axis.text(
        (decode_begin + decode_end) / 2,
        2.43,
        f"Decode span {decode_end - decode_begin:.3f}s",
        ha="center",
        color="#1E5AA8",
        fontweight="bold",
    )
    axis.text(
        0.0,
        -0.43,
        "Explanation — envelope = observed forward start-to-end span; the 3 lanes are round-robin display lanes, "
        "not concurrency; zigzag = display cap.\n"
        "P1-P6/D1-D23 at upper right = forward IDs, not durations; decode actual 0.460-0.601 s is shown as "
        "1.381-1.800 s.\n"
        "Top-5 percentages rank raw duration within each lane; #1/#2 labels may be omitted when they do not fit "
        "inside a folded block.\n"
        f"Observed request span = {request_seconds:.3f} s (instrumented; not production E2E).",
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=plt.rcParams["axes.labelsize"],
        color="#566573",
    )
    strict_lane_height_points = (
        shared_rectangle_height_points * STRICT_LANE_HEIGHT_SCALE
    )
    prefill_kernel_collection.set_linewidth(strict_lane_height_points)
    decode_kernel_collection.set_linewidth(strict_lane_height_points)
    axis.grid(axis="x", color="#D7DCE2", linewidth=1.15)
    axis.spines[["top", "right"]].set_visible(False)
    assert_axis_contains_rectangles(
        axis,
        panel="A",
        x_bounds=(0.0, forward_display_end),
        y_bounds=(forward_lane_y[0] - A_FORWARD_THICKNESS / 2.0,
                  forward_lane_y[-1] + A_FORWARD_THICKNESS / 2.0),
    )

    # B. Prefill composition, preserving one row per observed chunk.
    axis = figure.add_subplot(grid[1])
    panels["B"] = axis
    y = [index * B_ROW_SPACING for index in range(len(prefill_ids))]
    axis.set_ylim(y[-1] + 0.80, -0.75)
    b_bar_thickness = data_height_for_points(
        axis, figure, shared_rectangle_height_points
    )
    display_left = [0.0] * len(prefill_ids)
    for category in prefill_categories:
        values = prefill_values[category]
        for index, value in enumerate(values):
            if value <= 0:
                continue
            segment_start = display_left[index]
            visible_width, folded = draw_scaled_rectangle(
                axis,
                start=segment_start,
                cross_start=y[index] - b_bar_thickness / 2.0,
                duration=value,
                thickness=b_bar_thickness,
                limit=B_RECTANGLE_LIMIT_MS,
                color=COLORS[category],
            )
            rank = top_prefill_ranks.get((category, index))
            if rank is not None:
                label_x = segment_start + visible_width * (0.225 if folded else 0.5)
                label_color = (
                    "#17202A" if category in {"page784 tail", "page784 pack/merge", "Other"}
                    else "white"
                )
                rotate_label = visible_width < 55.0
                text_artist = axis.text(
                    label_x,
                    y[index],
                    f"#{rank} {value / prefill_totals[index] * 100:.1f}%",
                    ha="center",
                    va="center",
                    fontsize=18.0 if rotate_label else 26.0,
                    color=label_color,
                    fontweight="normal",
                    rotation=0,
                    zorder=3,
                )
                text_block_width = visible_width * (0.45 if folded else 1.0)
                rectangle_texts.append(
                    (axis, text_artist, text_block_width, b_bar_thickness)
                )
                if rank <= 3:
                    label_lower_left_coordinate(
                        axis,
                        x=segment_start,
                        y=y[index] + b_bar_thickness / 2.0,
                        text=f"{segment_start:.1f}",
                        fontsize=23.0,
                    )
            display_left[index] += visible_width
    max_prefill_display = max(display_left)
    for index, forward_id in enumerate(prefill_ids):
        route = "direct GQA6" if forward_id in {1, 6} else "page784 main + tail + merge"
        axis.text(
            display_left[index] + max_prefill_display * 0.015,
            y[index],
            f"kernel sum {prefill_totals[index]:.1f}ms  |  {route}",
            va="center",
            fontsize=18.0,
            color="#374151",
        )
    axis.set_xlim(0, max_prefill_display * 1.47)
    axis.set_yticks(y, [f"P{forward_id}" for forward_id in prefill_ids])
    axis.tick_params(axis="both", labelsize=24)
    axis.set_xlabel(
        "X-axis — cumulative display duration (milliseconds, ms)\n"
        "right edge = left edge + min(3 x actual kernel duration, 260 ms)"
    )
    axis.set_ylabel(
        "Y-axis — prefill forward/chunk ID\n"
        "(categorical; P1-P6, no physical unit)"
    )
    axis.set_title(
        "B  Prefill chunks — kernel-time composition exposes the GQA6/page784 routing",
        loc="left",
        fontweight="bold",
        pad=118,
    )
    axis.legend(
        handles=[Patch(facecolor=COLORS[category], label=category) for category in prefill_categories],
        ncol=4,
        loc="lower left",
        bbox_to_anchor=(0.0, 1.005),
        frameon=False,
        fontsize=20.0,
    )
    axis.text(
        0.995,
        1.035,
        "top5 per row = % of that row's kernel sum",
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        fontsize=18.0,
        color="#566573",
    )
    axis.grid(axis="x", color="#D7DCE2", linewidth=1.15)
    axis.spines[["top", "right"]].set_visible(False)
    assert_axis_contains_rectangles(
        axis,
        panel="B",
        x_bounds=(0.0, max(display_left)),
        y_bounds=(-b_bar_thickness / 2.0,
                  y[-1] + b_bar_thickness / 2.0),
    )

    # C. Decode composition, averaging each three adjacent, near-identical steps.
    axis = figure.add_subplot(grid[2])
    panels["C"] = axis
    x = [1.0 + index * C_COLUMN_SPACING for index in range(len(decode_group_indices))]
    display_bottom = [0.0] * len(decode_group_indices)
    for category in decode_categories:
        values = decode_group_values[category]
        for index, value in enumerate(values):
            if value <= 0:
                continue
            segment_start = display_bottom[index]
            visible_height, folded = draw_scaled_rectangle(
                axis,
                start=segment_start,
                cross_start=x[index] - C_BAR_WIDTH / 2.0,
                duration=value,
                thickness=C_BAR_WIDTH,
                limit=C_RECTANGLE_LIMIT_MS,
                color=COLORS[category],
                scale=C_RECTANGLE_SCALE,
                orientation="vertical",
                linewidth=0.25,
                fold_linewidth=2.6,
                fold_amplitude_fraction=0.36,
            )
            rank = top_decode_ranks.get((category, index))
            if rank is not None:
                label_y = segment_start + visible_height * (0.225 if folded else 0.5)
                label_color = "#17202A" if category in {"K17408 GEMV", "Other"} else "white"
                axis.text(
                    x[index],
                    label_y,
                    f"#{rank} {value:.3f}",
                    ha="center",
                    va="center",
                    fontsize=24.0,
                    color=label_color,
                    fontweight="bold",
                    rotation=0,
                    zorder=3,
                )
                if rank <= 3:
                    label_lower_left_coordinate(
                        axis,
                        x=x[index] - C_BAR_WIDTH / 2.0,
                        y=segment_start,
                        text=f"{segment_start:.1f}",
                        fontsize=31.5,
                    )
            display_bottom[index] += visible_height
    decode_mean = sum(decode_totals) / len(decode_totals)
    axis.text(
        0.55,
        max(display_bottom) * 1.055,
        f"actual trace mean {decode_mean:.2f}ms | modular production mean TPOT "
        "40.80-42.64ms (separate benchmark) | one column = mean of 3 adjacent steps; "
        "top5 labels use mean actual durations",
        ha="left",
        va="center",
        fontsize=18.0,
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
        fontsize=18.0,
    )
    axis.set_xlim(x[0] - 0.70, x[-1] + 1.00)
    axis.set_ylim(0, max(display_bottom) * 1.11)
    axis.set_xticks(x, decode_group_labels)
    axis.tick_params(axis="both", labelsize=24)
    axis.set_xlabel(
        "X-axis — decode-step group (step ID; categorical)\n"
        "each column = mean of 3 adjacent steps; final column = mean of steps 22-23"
    )
    axis.set_ylabel(
        "Y-axis — cumulative display duration (milliseconds, ms)\n"
        "top edge = bottom edge + min(9 x actual kernel duration, 10 ms)"
    )
    axis.set_title(
        "C  Decode — 3-step grouped means preserve the repeated GEMV composition",
        loc="left",
        fontweight="bold",
        pad=64,
    )
    axis.legend(
        handles=[Patch(facecolor=COLORS[category], label=category) for category in decode_categories],
        ncol=6,
        loc="lower left",
        bbox_to_anchor=(0.0, 1.005),
        frameon=False,
        fontsize=20.0,
    )
    axis.grid(axis="y", color="#D7DCE2", linewidth=1.15)
    axis.spines[["top", "right"]].set_visible(False)
    assert_axis_contains_rectangles(
        axis,
        panel="C",
        x_bounds=(x[0] - C_BAR_WIDTH / 2.0, x[-1] + C_BAR_WIDTH / 2.0),
        y_bounds=(0.0, max(display_bottom)),
    )

    # D. Exact launch positions for a representative decode layer.
    axis = figure.add_subplot(grid[3])
    panels["D"] = axis
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
    y_positions = {
        category: (len(zoom_categories) - index - 1) * D_ROW_SPACING
        for index, category in enumerate(zoom_categories)
    }
    axis.set_ylim(-0.95, max(y_positions.values()) + 1.50)
    d_bar_thickness = data_height_for_points(
        axis, figure, shared_rectangle_height_points
    )
    zoom_kernels_by_category = {
        category: [kernel for kernel in zoom_kernels if classify_zoom(kernel) == category]
        for category in zoom_categories
    }
    top_zoom_ranks: dict[tuple[float, str], int] = {}
    for category_kernels in zoom_kernels_by_category.values():
        for rank, kernel in enumerate(
            sorted(category_kernels, key=lambda item: item["dur_us"], reverse=True)[:5],
            start=1,
        ):
            top_zoom_ranks[(kernel["ts_us"], kernel["name"])] = rank
    zoom_display_tail_us = 0.0
    for kernel in zoom_kernels:
        category = classify_zoom(kernel)
        begin_us = kernel["ts_us"] - zoom_layer["ts_us"]
        duration_us = kernel["dur_us"]
        visible_duration, _ = draw_scaled_rectangle(
            axis,
            start=begin_us,
            cross_start=y_positions[category] - d_bar_thickness / 2.0,
            duration=duration_us,
            thickness=d_bar_thickness,
            limit=D_RECTANGLE_LIMIT_US,
            color=COLORS[category],
            scale=D_RECTANGLE_SCALE,
            edgecolor="#263238",
            linewidth=0.35,
        )
        rank = top_zoom_ranks.get((kernel["ts_us"], kernel["name"]))
        above = begin_us < 3800.0
        if rank is not None and rank <= 3:
            coordinate_above = not above
            coordinate_y = y_positions[category] + (
                d_bar_thickness / 2.0 if coordinate_above else -d_bar_thickness / 2.0
            )
            axis.annotate(
                f"{begin_us:.0f}",
                xy=(begin_us, coordinate_y),
                xytext=(3.0, 4.0 if coordinate_above else -4.0),
                textcoords="offset points",
                ha="left",
                va="bottom" if coordinate_above else "top",
                fontsize=23.0 * LOWER_LEFT_COORDINATE_FONT_SCALE,
                color="#263238",
                bbox={
                    "boxstyle": "square,pad=0.06",
                    "facecolor": "white",
                    "edgecolor": "none",
                    "alpha": 0.82,
                },
                clip_on=True,
                zorder=3.3,
            )
        zoom_display_tail_us = max(zoom_display_tail_us, begin_us + visible_duration)
        if duration_us >= 12.0:
            short_name = category
            if category == "Other" and "act_and_mul_kernel" in kernel["name"]:
                short_name = "act_and_mul"
            label_y = y_positions[category] + (0.70 if above else -0.70)
            rank_prefix = f"#{rank} " if rank is not None else ""
            axis.annotate(
                f"{rank_prefix}{short_name}\n{duration_us:.1f}",
                xy=(
                    begin_us + visible_duration / 2,
                    y_positions[category]
                    + (d_bar_thickness / 2.0 if above else -d_bar_thickness / 2.0),
                ),
                xytext=(begin_us + visible_duration / 2, label_y),
                ha="center",
                va="bottom" if above else "top",
                fontsize=18.0,
                color="#263238",
                arrowprops={"arrowstyle": "-", "color": "#64748B", "linewidth": 0.5},
            )
    zoom_sum_us = sum(kernel["dur_us"] for kernel in zoom_kernels)
    zoom_envelope_us = zoom_layer["dur_us"]
    zoom_tail_us = max(
        kernel["ts_us"] - zoom_layer["ts_us"] + kernel["dur_us"]
        for kernel in zoom_kernels
    )
    axis.axvline(zoom_envelope_us, color="#64748B", linestyle=":", linewidth=1.0)
    axis.set_xlim(0, max(zoom_envelope_us, zoom_tail_us, zoom_display_tail_us) * 1.015)
    axis.set_yticks(
        [y_positions[category] for category in zoom_categories],
        zoom_categories,
    )
    axis.tick_params(axis="both", labelsize=24)
    axis.set_xlabel(
        "X-axis — hybrid layer-relative time (microseconds, us)\n"
        "left edge = observed kernel start; visible width = min(6 x actual duration, 360 us)"
    )
    axis.set_ylabel(
        "Y-axis — strict-owned kernel category\n"
        "(categorical; no physical unit)"
    )
    axis.set_title(
        "D  Exact zoom — one observed decode layer (forward 10, layer 0)  "
        "[all time units: us]",
        loc="left",
        fontweight="bold",
        pad=106,
    )
    axis.text(
        0.995,
        1.025,
        f"11 kernels; kernel sum {zoom_sum_us:.1f}us; layer envelope {zoom_envelope_us:.1f}us\n"
        "Ticks locate observed starts; right edges are display-scaled; zigzag = cap; "
        "all labels are outside rectangles; title declares start/duration units. "
        "Gaps are not a production idle-time claim.",
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        fontsize=18.0,
        bbox={"boxstyle": "round,pad=0.4", "facecolor": "white", "edgecolor": "#CBD5E1"},
    )
    axis.grid(axis="x", color="#D7DCE2", linewidth=1.15)
    axis.spines[["top", "right"]].set_visible(False)
    assert_axis_contains_rectangles(
        axis,
        panel="D",
        x_bounds=(0.0, zoom_display_tail_us),
        y_bounds=(-d_bar_thickness / 2.0,
                  max(y_positions.values()) + d_bar_thickness / 2.0),
    )
    b_rectangle_height_points = data_height_points(
        panels["B"], figure, b_bar_thickness
    )
    d_rectangle_height_points = data_height_points(
        panels["D"], figure, d_bar_thickness
    )
    if max(
        abs(b_rectangle_height_points - shared_rectangle_height_points),
        abs(d_rectangle_height_points - shared_rectangle_height_points),
    ) > 1e-6:
        raise RuntimeError("Panels A, B, and D do not share one physical rectangle height")

    figure.text(
        0.075,
        0.018,
        "Evidence boundary: observed bh408@0abe1e1-dirty trace; no pre-optimization trace was rerun. "
        "Panels B/C sum strict-owned kernels by process attribution; async tails may extend beyond annotation envelopes. "
        "Nested process spans are not added.",
        fontsize=11.5,
        color="#566573",
        ha="left",
    )

    hidden_rectangle_texts = hide_overflowing_rectangle_texts(
        figure, rectangle_texts
    )

    figure.savefig(OUT_PNG, dpi=210, bbox_inches="tight")
    save_clean_svg(figure, OUT_SVG, bbox_inches="tight")
    save_individual_panels(figure, panels)
    plt.close(figure)

    prefill_kernel_ms = sum(prefill_totals)
    prefill_envelope_ms = sum(forwards[index]["dur_us"] for index in prefill_ids) / 1000.0
    print(f"wrote {OUT_PNG}")
    print(f"wrote {OUT_SVG}")
    for panel_id, output_base in PANEL_OUTPUTS.items():
        print(f"wrote panel {panel_id}: {output_base}.png / {output_base}.svg")
    print(f"request_span_ms={request['dur_us'] / 1000.0:.3f}")
    print(f"prefill_kernel_ms={prefill_kernel_ms:.3f}")
    print(f"prefill_envelope_ms={prefill_envelope_ms:.3f}")
    print(f"decode_kernel_ms={total_decode:.3f}")
    print(f"decode_kernel_ms_per_step={decode_mean:.3f}")
    print(f"decode_custom_gemv_share={gemv_decode / total_decode:.6f}")
    print(f"decode_custom_gemv_plus_mmac_share={gemm_decode / total_decode:.6f}")
    print(f"zoom_layer_kernel_ms={zoom_sum_us / 1000.0:.3f}")
    print(f"zoom_layer_envelope_ms={zoom_envelope_us / 1000.0:.3f}")
    print(f"abd_rectangle_height_points={shared_rectangle_height_points:.3f}")
    print(f"hidden_overflowing_rectangle_texts={hidden_rectangle_texts}")


if __name__ == "__main__":
    main()
