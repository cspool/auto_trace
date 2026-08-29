from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEDULER_PATH = PROJECT_ROOT / "perf_trace/scripts/run_perf_trace_01_05.py"
SPEC = importlib.util.spec_from_file_location("run_perf_trace_01_05", SCHEDULER_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FreshBranchContractTests(unittest.TestCase):
    def test_only_fresh_r01_r10_branch_is_active(self) -> None:
        self.assertEqual(list(runner.BRANCHES), [runner.FRESH_E2E_BRANCH])
        contract = runner.BRANCHES[runner.FRESH_E2E_BRANCH]["payload"]
        self.assertEqual(contract["goals"], [f"R{i:02d}" for i in range(1, 11)])
        self.assertEqual(contract["bindings"], runner.RUNTIME_BINDINGS)

    def test_committed_manifest_matches_runtime_contract(self) -> None:
        path, manifest, hashes = runner.validate_runtime_inputs(
            PROJECT_ROOT, runner.FRESH_E2E_BRANCH
        )
        self.assertEqual(
            path,
            PROJECT_ROOT / "perf_trace/manifests/workflow01_10_fresh_e2e_pipeline.json",
        )
        self.assertEqual(manifest, runner.BRANCHES[runner.FRESH_E2E_BRANCH]["payload"])
        self.assertEqual(set(hashes), {value["skill"] for value in runner.RUNTIME_BINDINGS.values()})

    def test_fresh_defaults_require_no_external_ledger(self) -> None:
        parameters = runner.resolve_user_parameters(PROJECT_ROOT, {})
        self.assertEqual(
            parameters["evidence_acquisition_mode"],
            "fresh_no_prior_runtime_reuse",
        )
        self.assertEqual(
            parameters["analysis_strategy"],
            "fresh_run_full_request_e2e_timeline",
        )
        self.assertEqual(parameters["fresh_e2e_contract"], runner.FRESH_E2E_CONTRACT)
        runner.validate_branch_user_parameters(runner.FRESH_E2E_BRANCH, parameters)

    def test_reuse_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(runner.SchedulerError, "fresh_no_prior"):
            runner.resolve_user_parameters(
                PROJECT_ROOT,
                {"evidence_acquisition_mode": "historical_then_selective"},
            )

    def test_dry_run_is_one_strict_serial_chain(self) -> None:
        manifest_path, manifest, hashes = runner.validate_runtime_inputs(
            PROJECT_ROOT, runner.FRESH_E2E_BRANCH
        )
        parameters = runner.resolve_user_parameters(PROJECT_ROOT, {})
        payload = runner.dry_run_payload(
            project_root=PROJECT_ROOT,
            branch=runner.FRESH_E2E_BRANCH,
            manifest_path=manifest_path,
            manifest=manifest,
            skill_hashes=hashes,
            user_parameters=parameters,
            upstream_provenance=None,
            upstream_was_supplied=False,
            run_id=None,
            model=None,
        )
        self.assertFalse(payload["upstream_ledger"]["required_for_execution"])
        self.assertEqual([goal["id"] for goal in payload["goals"]], manifest["goals"])
        for index, goal in enumerate(payload["goals"]):
            self.assertEqual(goal["predecessors"], manifest["goals"][:index])

    def test_r10_requires_top_latency_process_colors_and_all_rectangle_labels(self) -> None:
        skill = (
            PROJECT_ROOT
            / "perf_trace/skills/qwen-dcu-workflow05-trace-visualization-reporting/SKILL.md"
        ).read_text(encoding="utf-8")
        required_contract = (
            "## Top-Latency Process Colors and All Rectangle Labels",
            "hiptx_end_ns - hiptx_begin_ns",
            "min(10, valid_process_count)",
            "#4E79A7 #F28E2B #E15759 #76B7B2 #59A14F",
            "#EDC948 #B07AA1 #FF9DA7 #9C755F #BAB0AC",
            "top_latency_processes",
            "top_latency_process_colors_verified",
            "zoomed_process_labels_verified",
            "all_timeline_rectangle_labels_verified",
        )
        for requirement in required_contract:
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, skill)

        config = json.loads(
            (
                PROJECT_ROOT
                / "perf_trace/configs/workflow01_10_fresh_e2e_dcu1.json"
            ).read_text(encoding="utf-8")
        )
        timeline = config["timeline_visualization"]
        runner.validate_timeline_visualization_contract(timeline)
        self.assertEqual(
            timeline["top_latency_process_color_count"],
            runner.TOP_LATENCY_PROCESS_COLOR_COUNT,
        )
        self.assertEqual(
            timeline["top_latency_process_palette"],
            list(runner.TOP_LATENCY_PROCESS_PALETTE),
        )
        self.assertIs(timeline["show_process_name_when_zoomed"], True)
        self.assertEqual(
            timeline["rectangle_label_groups"],
            list(runner.TIMELINE_RECTANGLE_LABEL_GROUPS),
        )
        self.assertIs(timeline["show_all_timeline_labels_when_zoomed"], True)

        for key, invalid in (
            ("top_latency_process_color_count", 9),
            ("top_latency_process_palette", ["#000000"] * 10),
            ("show_process_name_when_zoomed", False),
            ("rectangle_label_groups", ["process"]),
            ("show_all_timeline_labels_when_zoomed", False),
        ):
            changed = dict(timeline)
            changed[key] = invalid
            with self.subTest(rejected_key=key):
                with self.assertRaisesRegex(
                    runner.SchedulerError, "timeline_visualization contract"
                ):
                    runner.validate_timeline_visualization_contract(changed)


class FreshHandoffValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name) / "project"
        self.run_dir = (
            self.project
            / "perf_trace/runtime"
            / runner.FRESH_E2E_BRANCH
            / "fresh-test"
        )
        self.run_dir.mkdir(parents=True)
        self.ledger: dict[str, object] = {
            "schema_version": 1,
            "branch": runner.FRESH_E2E_BRANCH,
            "run_id": "fresh-test",
            "handoffs": [],
        }
        self.parameters = {
            "evidence_acquisition_mode": "fresh_no_prior_runtime_reuse"
        }
        self.lineage_id = "fresh-run:fresh-test:contract-1"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_payload(self, goal_id: str) -> dict[str, object]:
        evidence: dict[str, object] = {
            "schema_version": 1,
            "status": "complete",
            "lineage_id": self.lineage_id,
        }
        artifact_root = self.run_dir / "artifacts" / goal_id
        artifact_root.mkdir(parents=True)
        for key in runner.FRESH_HANDOFF_ARTIFACT_KEYS[goal_id]:
            path = artifact_root / f"{key}.json"
            path.write_text(json.dumps({"goal": goal_id, "key": key}))
            evidence[key] = {"path": str(path), "sha256": sha256_file(path)}
        return {
            "runtime_goal": goal_id,
            "status": "complete",
            "skill": runner.RUNTIME_BINDINGS[goal_id]["skill"],
            "execution_status": "complete",
            "evidence_status": "complete",
            "coverage_target_met": True,
            "next_authorization_required": False,
            "fresh_e2e_evidence": evidence,
        }

    def test_r06_r10_handoffs_keep_one_lineage(self) -> None:
        handoffs = self.ledger["handoffs"]
        assert isinstance(handoffs, list)
        for goal_id in ("R06", "R07", "R08", "R09", "R10"):
            payload = self.make_payload(goal_id)
            runner.validate_scheduler_handoff_payload(
                goal_id,
                payload,
                expected_skill=runner.RUNTIME_BINDINGS[goal_id]["skill"],
                project_root=self.project,
                run_dir=self.run_dir,
                branch=runner.FRESH_E2E_BRANCH,
                run_id="fresh-test",
                ledger=self.ledger,
                user_parameters=self.parameters,
            )
            handoffs.append({"source_goal": goal_id, "payload": payload})

    def test_lineage_change_is_rejected(self) -> None:
        r06 = self.make_payload("R06")
        handoffs = self.ledger["handoffs"]
        assert isinstance(handoffs, list)
        handoffs.append({"source_goal": "R06", "payload": r06})
        r07 = self.make_payload("R07")
        evidence = r07["fresh_e2e_evidence"]
        assert isinstance(evidence, dict)
        evidence["lineage_id"] = "fresh-run:other"
        with self.assertRaisesRegex(runner.SchedulerError, "lineage_id changed"):
            runner.validate_scheduler_handoff_payload(
                "R07",
                r07,
                expected_skill=runner.RUNTIME_BINDINGS["R07"]["skill"],
                project_root=self.project,
                run_dir=self.run_dir,
                branch=runner.FRESH_E2E_BRANCH,
                run_id="fresh-test",
                ledger=self.ledger,
                user_parameters=self.parameters,
            )

    def test_artifact_outside_run_is_rejected(self) -> None:
        payload = self.make_payload("R06")
        evidence = payload["fresh_e2e_evidence"]
        assert isinstance(evidence, dict)
        outside = self.project / "outside.json"
        outside.write_text("{}")
        evidence["fresh_run_lineage_manifest"] = {
            "path": str(outside),
            "sha256": sha256_file(outside),
        }
        with self.assertRaisesRegex(runner.SchedulerError, "escapes the active run"):
            runner.validate_scheduler_handoff_payload(
                "R06",
                payload,
                expected_skill=runner.RUNTIME_BINDINGS["R06"]["skill"],
                project_root=self.project,
                run_dir=self.run_dir,
                branch=runner.FRESH_E2E_BRANCH,
                run_id="fresh-test",
                ledger=self.ledger,
                user_parameters=self.parameters,
            )


if __name__ == "__main__":
    unittest.main()
