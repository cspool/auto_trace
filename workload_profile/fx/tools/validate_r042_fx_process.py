#!/usr/bin/env python3
"""Independently validate R042 FX reconstruction and manual companions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GENERATED_EXPLANATION_MARKERS = (
    "是什么",
    "为什么需要",
    "怎么做/计算",
    "Tensor:",
    "Formula:",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fx-root", type=Path, required=True)
    parser.add_argument("--r032-handoff", type=Path, required=True)
    parser.add_argument("--logical-run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-visualizations", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, role: str) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "role": role,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def check_artifact(
    record: dict[str, Any],
    errors: list[str],
    label: str,
) -> Path | None:
    try:
        path = Path(record["path"]).resolve()
    except Exception as exc:
        errors.append(f"{label}: invalid artifact record: {exc!r}")
        return None
    if not path.is_file():
        errors.append(f"{label}: missing file {path}")
        return None
    actual_hash = sha256_file(path)
    if actual_hash != record.get("sha256"):
        errors.append(
            f"{label}: SHA-256 mismatch {actual_hash} != {record.get('sha256')}"
        )
    if path.stat().st_size != record.get("size_bytes"):
        errors.append(f"{label}: size mismatch for {path}")
    return path


def sections_by_h3(markdown: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^### (.+)$", markdown))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        title = match.group(1).strip()
        if title in sections:
            raise ValueError(f"duplicate H3 section {title!r}")
        sections[title] = markdown[match.end() : end]
    return sections


def fenced_blocks(markdown: str) -> list[str]:
    return re.findall(r"```(?:text)?\n(.*?)```", markdown, flags=re.DOTALL)


def referenced_node_indices(text: str) -> set[int]:
    indices: set[int] = set()
    for start, end in re.findall(r"#(\d+)\s*[–-]\s*#(\d+)", text):
        indices.update(range(int(start), int(end) + 1))
    indices.update(int(index) for index in re.findall(r"#(\d+)", text))
    return indices


def validate_flat_rectangles(
    block: str,
    event_id: str,
    title: str,
    errors: list[str],
) -> None:
    lines = block.splitlines()
    rectangle_count = 0
    used_bottoms: set[int] = set()
    for line_number, line in enumerate(lines, start=1):
        if "┌" not in line:
            continue
        rectangle_count += 1
        if line.count("┌") != 1 or line.count("┐") != 1:
            errors.append(
                f"{event_id}/{title}: ambiguous top border on diagram line "
                f"{line_number}"
            )
            continue
        start = line.index("┌")
        end = line.index("┐")
        top_boundaries = [
            index for index, character in enumerate(line) if character in "┌┬┐"
        ]
        bottom_index = None
        for candidate_index in range(line_number, len(lines)):
            candidate = lines[candidate_index]
            if (
                "└" in candidate
                and candidate.index("└") == start
                and "┘" in candidate
                and candidate.index("┘") == end
            ):
                bottom_index = candidate_index
                break
        if bottom_index is None:
            errors.append(
                f"{event_id}/{title}: unclosed or jagged rectangle starting on "
                f"diagram line {line_number}"
            )
            continue
        used_bottoms.add(bottom_index)
        bottom_boundaries = [
            index
            for index, character in enumerate(lines[bottom_index])
            if character in "└┴┘"
        ]
        if bottom_boundaries != top_boundaries:
            errors.append(
                f"{event_id}/{title}: top/bottom region dividers differ on "
                f"diagram lines {line_number} and {bottom_index + 1}"
            )
        for content_index in range(line_number, bottom_index):
            content = lines[content_index]
            vertical_boundaries = [
                index for index, character in enumerate(content) if character == "│"
            ]
            if vertical_boundaries != top_boundaries:
                errors.append(
                    f"{event_id}/{title}: non-flat or misaligned vertical/region "
                    f"borders between diagram lines {line_number} and "
                    f"{bottom_index + 1}"
                )
                break
    for line_index, line in enumerate(lines):
        if "└" in line and line_index not in used_bottoms:
            errors.append(
                f"{event_id}/{title}: unmatched bottom border on diagram line "
                f"{line_index + 1}"
            )
    if rectangle_count == 0 and "Layer output" not in title:
        errors.append(f"{event_id}/{title}: no tensor rectangle found")


def validate_visualization(
    event_id: str,
    event_dir: Path,
    reconstruction: dict[str, Any],
    errors: list[str],
) -> dict[str, Any] | None:
    path = event_dir / "fx_process_visualization.md"
    if not path.is_file():
        errors.append(f"{event_id}: missing manual visualization companion")
        return None
    markdown = path.read_text(encoding="utf-8")
    try:
        sections = sections_by_h3(markdown)
    except ValueError as exc:
        errors.append(f"{event_id}: {exc}")
        return file_record(path, "manual_process_visualization")
    expected_titles = [stage["title"] for stage in reconstruction["stages"]]
    stages_by_title = {
        stage["title"]: stage for stage in reconstruction["stages"]
    }
    actual_titles = list(sections)
    if actual_titles != expected_titles:
        errors.append(
            f"{event_id}: visualization process order/titles differ: "
            f"{actual_titles} != {expected_titles}"
        )
    for title in expected_titles:
        section = sections.get(title, "")
        for marker in ("**是什么**", "**为什么需要**", "**怎么做/计算**"):
            if marker not in section:
                errors.append(f"{event_id}/{title}: missing {marker}")
        prose_only = re.sub(r"```(?:text)?\n.*?```", "", section, flags=re.DOTALL)
        if not re.search(r"[\u3400-\u9fff]", prose_only):
            errors.append(f"{event_id}/{title}: Chinese prose is missing")
        if "**怎么做/计算**：" in section:
            computation = section.split("**怎么做/计算**：", 1)[1].split("```", 1)[0]
            stage = stages_by_title[title]
            expected_indices = set(
                range(stage["start_index"], stage["end_index"] + 1)
            )
            missing_indices = sorted(
                expected_indices - referenced_node_indices(computation)
            )
            if missing_indices:
                errors.append(
                    f"{event_id}/{title}: computation prose omits FX nodes "
                    f"{missing_indices}"
                )
        if "Tensor:" not in section or "Formula:" not in section:
            errors.append(f"{event_id}/{title}: missing Tensor/Formula labels")
        if "──▶" not in section or "◀──" not in section:
            errors.append(f"{event_id}/{title}: missing explicit pointers")
        blocks = fenced_blocks(section)
        if not blocks:
            errors.append(f"{event_id}/{title}: missing fenced tensor diagram")
        for block in blocks:
            if not re.search(r"(?i)\baxis\b", block):
                errors.append(f"{event_id}/{title}: diagram axis label is missing")
            if block.count("▲") < 2:
                errors.append(
                    f"{event_id}/{title}: diagram lacks explicit axis endpoints"
                )
            for marker in ("Tensor:", "Formula:", "──▶", "◀──"):
                if marker not in block:
                    errors.append(
                        f"{event_id}/{title}: diagram is missing {marker}"
                    )
            if not re.search(
                r"\[(?:\d+|T)(?:\s*,\s*\d+)+\]",
                block,
            ):
                errors.append(
                    f"{event_id}/{title}: diagram lacks an observed tensor shape"
                )
            if re.search(r"[\u3400-\u9fff]", block):
                errors.append(f"{event_id}/{title}: CJK text appears inside diagram")
            if re.search(r"\b(?:aten|vllm|_C)\.", block):
                errors.append(
                    f"{event_id}/{title}: raw FX target appears inside diagram"
                )
            validate_flat_rectangles(block, event_id, title, errors)
    return file_record(path, "manual_process_visualization")


def main() -> None:
    args = parse_args()
    root = args.fx_root.resolve()
    handoff_path = args.r032_handoff.resolve()
    output_path = args.output.resolve()
    errors: list[str] = []
    checks: dict[str, bool] = {}

    if not root.is_dir():
        raise NotADirectoryError(root)
    if not handoff_path.is_file():
        raise FileNotFoundError(handoff_path)
    handoff = load_json(handoff_path)
    downstream = handoff.get("downstream_contract", {})
    expected_ids = list(downstream.get("ordered_fx_event_ids", []))
    expected_source_ids = list(downstream.get("ordered_source_event_ids", []))
    expected_selection_ids = list(
        handoff.get("selection", {}).get("ordered_selection_ids", [])
    )
    checks["r032_handoff_complete"] = (
        handoff.get("status") == "complete"
        and handoff.get("source_goal") == "R032"
        and downstream.get("consume_as_is") is True
        and handoff.get("runtime", {}).get("run_id") == args.logical_run_id
        and Path(downstream.get("fx_root", "")).resolve() == root
    )
    if not checks["r032_handoff_complete"]:
        errors.append("R032 handoff identity/completion check failed")

    json_manifest_path = root / "fx_process_reconstruction_manifest.json"
    csv_manifest_path = root / "fx_process_reconstruction_manifest.csv"
    if not json_manifest_path.is_file() or not csv_manifest_path.is_file():
        raise FileNotFoundError("R042 reconstruction manifests are missing")
    manifest = load_json(json_manifest_path)
    with csv_manifest_path.open(encoding="utf-8", newline="") as handle:
        csv_manifest = list(csv.DictReader(handle))
    json_ids = [row.get("event_id") for row in manifest.get("results", [])]
    csv_ids = [row.get("event_id") for row in csv_manifest]
    checks["manifest_order_and_count"] = (
        manifest.get("processed") == len(expected_ids)
        and manifest.get("ordered_event_ids") == expected_ids
        and manifest.get("ordered_source_event_ids") == expected_source_ids
        and manifest.get("ordered_selection_ids") == expected_selection_ids
        and json_ids == expected_ids
        and csv_ids == expected_ids
        and len(expected_ids) == len(set(expected_ids))
    )
    if not checks["manifest_order_and_count"]:
        errors.append("reconstruction manifest order/count/identity check failed")

    actual_dirs = sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir() and re.fullmatch(r"input\d+_layer\d+", path.name)
    )
    checks["event_directory_set_exact"] = actual_dirs == sorted(expected_ids)
    if not checks["event_directory_set_exact"]:
        errors.append(f"event directory set differs: {actual_dirs}")

    event_reports: list[dict[str, Any]] = []
    total_nodes = 0
    total_stages = 0
    visualizations: list[dict[str, Any]] = []
    for ordinal, event_id in enumerate(expected_ids):
        event_dir = root / event_id
        result = (
            manifest["results"][ordinal]
            if ordinal < len(manifest.get("results", []))
            else {}
        )
        if result.get("status") != "ok":
            errors.append(f"{event_id}: manifest status is not ok")
        for role in ("json", "markdown", "csv"):
            if isinstance(result.get(role), dict):
                check_artifact(result[role], errors, f"{event_id}/{role}")
            else:
                errors.append(f"{event_id}: missing {role} artifact record")

        reconstruction_path = event_dir / "fx_process_reconstruction.json"
        markdown_path = event_dir / "fx_process_reconstruction.md"
        nodes_csv_path = event_dir / "fx_process_nodes.csv"
        if not all(
            path.is_file()
            for path in (reconstruction_path, markdown_path, nodes_csv_path)
        ):
            errors.append(f"{event_id}: reconstruction output set is incomplete")
            continue
        reconstruction = load_json(reconstruction_path)
        markdown = markdown_path.read_text(encoding="utf-8")
        with nodes_csv_path.open(encoding="utf-8", newline="") as handle:
            node_rows = list(csv.DictReader(handle))

        identity = reconstruction.get("event_identity", {})
        identity_ok = (
            identity.get("event_id") == event_id
            and identity.get("selection_id") == expected_selection_ids[ordinal]
            and identity.get("source_event_id") == expected_source_ids[ordinal]
            and reconstruction.get("logical_pipeline_run_id")
            == args.logical_run_id
            and result.get("selection_id") == expected_selection_ids[ordinal]
            and result.get("source_event_id") == expected_source_ids[ordinal]
        )
        if not identity_ok:
            errors.append(f"{event_id}: event identity mismatch")

        nodes = reconstruction.get("nodes", [])
        stages = reconstruction.get("stages", [])
        node_count = reconstruction.get("node_count")
        stage_count = reconstruction.get("stage_count")
        indices = [row.get("index") for row in nodes]
        partitioned = [
            index
            for stage in stages
            for index in range(stage["start_index"], stage["end_index"] + 1)
        ]
        partition_ok = (
            node_count == len(nodes) == len(node_rows)
            and indices == list(range(len(nodes)))
            and sorted(partitioned) == list(range(len(nodes)))
            and len(partitioned) == len(set(partitioned))
            and stage_count == len(stages)
            and all(
                stage["node_count"]
                == stage["end_index"] - stage["start_index"] + 1
                for stage in stages
            )
            and all(
                nodes[index].get("process_stage") == stage["stage"]
                for stage in stages
                for index in range(stage["start_index"], stage["end_index"] + 1)
            )
        )
        if not partition_ok:
            errors.append(f"{event_id}: node/stage partition is inconsistent")

        csv_ok = all(
            int(csv_row["index"]) == node["index"]
            and csv_row["process_stage"] == node["process_stage"]
            and csv_row["name"] == node["name"]
            and csv_row["target"] == node["target"]
            for csv_row, node in zip(node_rows, nodes, strict=True)
        )
        if not csv_ok:
            errors.append(f"{event_id}: CSV rows differ from reconstruction JSON")

        try:
            markdown_sections = sections_by_h3(markdown)
        except ValueError as exc:
            errors.append(f"{event_id}: reconstruction markdown {exc}")
            markdown_sections = {}
        expected_titles = [stage["title"] for stage in stages]
        if list(markdown_sections) != expected_titles:
            errors.append(
                f"{event_id}: reconstruction Markdown process order differs"
            )
        if any(marker in markdown for marker in GENERATED_EXPLANATION_MARKERS):
            errors.append(
                f"{event_id}: generated reconstruction contains manual content"
            )

        for source_name, source_record in reconstruction.get(
            "source_artifacts", {}
        ).items():
            check_artifact(
                source_record, errors, f"{event_id}/source/{source_name}"
            )
        guards = reconstruction.get("evidence_guards", {})
        guards_ok = (
            guards.get("fixed_input_path_only") is True
            and guards.get("graph_module_not_executed") is True
            and guards.get("meta_storage_is_structural_evidence") is True
            and guards.get("process_labels_are_rule_derived") is True
            and guards.get("opaque_custom_op_internals_reconstructed") is False
            and guards.get("measured_latency_reported") is False
            and guards.get("pruning_or_early_exit_claimed") is False
        )
        if not guards_ok:
            errors.append(f"{event_id}: evidence guards are incomplete")

        visualization_record = None
        visualization_ok = not args.require_visualizations
        if args.require_visualizations:
            visualization_error_count = len(errors)
            visualization_record = validate_visualization(
                event_id, event_dir, reconstruction, errors
            )
            visualization_ok = len(errors) == visualization_error_count
            if visualization_record:
                visualizations.append(visualization_record)
        total_nodes += int(node_count or 0)
        total_stages += int(stage_count or 0)
        event_reports.append(
            {
                "event_id": event_id,
                "selection_id": expected_selection_ids[ordinal],
                "source_event_id": expected_source_ids[ordinal],
                "layer_type": identity.get("layer_type"),
                "phase": identity.get("phase"),
                "node_count": node_count,
                "stage_count": stage_count,
                "identity_ok": identity_ok,
                "partition_ok": partition_ok,
                "csv_ok": csv_ok,
                "visualization_ok": visualization_ok,
                "visualization": visualization_record,
            }
        )

    checks["all_event_identities_match"] = all(
        row["identity_ok"] for row in event_reports
    ) and len(event_reports) == len(expected_ids)
    checks["all_node_partitions_match"] = all(
        row["partition_ok"] for row in event_reports
    ) and len(event_reports) == len(expected_ids)
    checks["all_csv_tables_match"] = all(
        row["csv_ok"] for row in event_reports
    ) and len(event_reports) == len(expected_ids)
    checks["manual_visualization_coverage"] = (
        not args.require_visualizations
        or len(visualizations) == len(expected_ids)
    )
    if args.require_visualizations and not checks["manual_visualization_coverage"]:
        errors.append("manual visualization event coverage is incomplete")
    checks["manual_visualization_requirements"] = (
        not args.require_visualizations
        or (
            len(event_reports) == len(expected_ids)
            and all(row["visualization_ok"] for row in event_reports)
        )
    )
    if (
        args.require_visualizations
        and not checks["manual_visualization_requirements"]
    ):
        errors.append("manual visualization requirements are not all satisfied")

    passed = not errors and all(checks.values())
    report = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runtime_goal": "R042",
        "logical_pipeline_run_id": args.logical_run_id,
        "result": (
            "PASS_FOR_R042_RECONSTRUCTION_AND_VISUALIZATION"
            if passed and args.require_visualizations
            else "PASS_FOR_R042_RECONSTRUCTION"
            if passed
            else "FAIL"
        ),
        "require_visualizations": args.require_visualizations,
        "fx_root": str(root),
        "source_handoff": file_record(
            handoff_path, "complete_r032_runtime_handoff"
        ),
        "reconstruction_manifests": {
            "json": file_record(
                json_manifest_path, "fx_process_reconstruction_manifest"
            ),
            "csv": file_record(
                csv_manifest_path, "fx_process_reconstruction_manifest_table"
            ),
        },
        "counts": {
            "events": len(event_reports),
            "nodes": total_nodes,
            "processes": total_stages,
            "visualizations": len(visualizations),
        },
        "ordered_event_ids": expected_ids,
        "checks": checks,
        "events": event_reports,
        "errors": errors,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
