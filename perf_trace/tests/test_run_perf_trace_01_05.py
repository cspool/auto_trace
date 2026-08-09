from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import queue
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_perf_trace_01_05.py"
)
SPEC = importlib.util.spec_from_file_location("run_perf_trace_01_05", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, params))
        if method != "turn/start":
            raise AssertionError(f"unexpected request: {method}")
        return {"turn": {"id": "turn-1", "status": "inProgress"}}


class InitialTurnRaceTests(unittest.TestCase):
    def test_start_response_is_accepted_without_immediate_thread_read(self) -> None:
        scheduler = runner.RuntimeScheduler.__new__(runner.RuntimeScheduler)
        scheduler.client = FakeClient()
        scheduler.manifest = {"bindings": {"R08": {"skill": "test-skill"}}}
        record: dict[str, Any] = {
            "thread_id": "thread-1",
            "turn_ids": [],
        }
        scheduler._goal_record = lambda goal_id: record
        scheduler._skill_md = lambda goal_id: Path("/tmp/test-skill/SKILL.md")
        scheduler._prompt = lambda goal_id, handoff, artifact: "prompt"
        scheduler._turn_overrides = lambda: {}
        scheduler._checkpoint = lambda: None
        scheduler._transition = lambda goal_id, status: record.update(status=status)

        turn_id = scheduler._start_initial_turn(
            "R08",
            Path("/tmp/R08.json"),
            Path("/tmp/R08"),
        )

        self.assertEqual(turn_id, "turn-1")
        self.assertEqual(record["status"], "running")
        self.assertEqual(record["turn_ids"], ["turn-1"])
        self.assertEqual(
            scheduler.client.calls[0][0],
            "turn/start",
        )
        self.assertEqual(len(scheduler.client.calls), 1)


class RetryableTransportNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record: dict[str, Any] = {
            "thread_id": "thread-1",
            "turn_ids": ["turn-1"],
        }
        self.scheduler = runner.RuntimeScheduler.__new__(runner.RuntimeScheduler)
        self.scheduler.client = mock.Mock()
        self.scheduler.client.reader_errors = queue.Queue()
        self.scheduler.client.server_requests = queue.Queue()
        self.scheduler.client.notifications = queue.Queue()
        self.scheduler._goal_record = lambda goal_id: self.record
        self.scheduler._checkpoint = lambda: None

    def test_retryable_error_waits_for_recovery_event(self) -> None:
        retry = {
            "method": "error",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "willRetry": True,
                "error": {"message": "Reconnecting... 2/5"},
            },
        }
        self.scheduler.client.notifications.put(retry)

        observed = self.scheduler._drain_event("R07", timeout=0.01)

        self.assertEqual(observed, retry)
        self.assertEqual(self.record["transport_status"], "retrying")
        self.assertEqual(
            len(self.record["retryable_transport_error_history"]), 1
        )

        self.scheduler.client.notifications.put(
            {
                "method": "item/started",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "item": {"type": "commandExecution"},
                },
            }
        )
        self.scheduler._drain_event("R07", timeout=0.01)
        self.assertEqual(self.record["transport_status"], "connected")
        self.assertIn("transport_recovered_at", self.record)

    def test_nonretryable_error_remains_terminal(self) -> None:
        self.scheduler.client.notifications.put(
            {
                "method": "error",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "willRetry": False,
                    "error": {"message": "stream failed"},
                },
            }
        )

        with self.assertRaisesRegex(
            runner.SchedulerError, "app-server error notification"
        ):
            self.scheduler._drain_event("R07", timeout=0.01)
        self.assertEqual(self.record["transport_status"], "failed")


class ContinueExistingGoalTests(unittest.TestCase):
    def test_thread_resume_loads_persisted_rollout_before_goal_activation(self) -> None:
        scheduler = runner.RuntimeScheduler.__new__(runner.RuntimeScheduler)
        scheduler.client = mock.Mock()
        scheduler.project_root = Path("/tmp/project")
        scheduler.model = None
        record: dict[str, Any] = {"turn_ids": []}
        scheduler._goal_record = lambda goal_id: record
        scheduler._checkpoint = mock.Mock()
        resumed_thread = {
            "id": "thread-r07",
            "status": {"type": "idle"},
            "path": "/tmp/rollout.jsonl",
            "turns": [{"id": "turn-r07", "status": "interrupted"}],
        }
        scheduler.client.request.return_value = {"thread": resumed_thread}

        observed = scheduler._resume_persistent_thread("R07", "thread-r07")

        self.assertEqual(observed, resumed_thread)
        scheduler.client.request.assert_called_once_with(
            "thread/resume",
            {
                "threadId": "thread-r07",
                "cwd": "/tmp/project",
                "approvalPolicy": "never",
                "sandbox": "danger-full-access",
                "excludeTurns": False,
            },
        )
        self.assertEqual(record["thread_status"], {"type": "idle"})
        self.assertEqual(record["turn_ids"], ["turn-r07"])

    def test_paused_goal_is_reactivated_without_starting_a_new_thread(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            artifact_root = project / "runtime" / "artifacts" / "R07"
            artifact_root.mkdir(parents=True)
            handoff_dir = project / "runtime" / "handoffs"
            handoff_dir.mkdir(parents=True)
            record: dict[str, Any] = {
                "thread_id": "thread-r07",
                "runtime_artifact_root": str(
                    artifact_root.relative_to(project)
                ),
                "turn_ids": ["interrupted-turn"],
            }
            scheduler = runner.RuntimeScheduler.__new__(runner.RuntimeScheduler)
            scheduler.client = mock.Mock()
            scheduler.project_root = project
            scheduler.handoff_dir = handoff_dir
            scheduler.resume_context = {
                "start_goal": "R07",
                "continue_current_goal": True,
                "continued_goal": {
                    "goal_id": "R07",
                    "thread_id": "thread-r07",
                    "artifact_root": artifact_root,
                },
            }
            scheduler._goal_record = lambda goal_id: record
            scheduler._resume_persistent_thread = mock.Mock(
                return_value={"status": {"type": "idle"}, "turns": []}
            )
            scheduler._get_goal = mock.Mock(
                return_value={"threadId": "thread-r07", "status": "paused"}
            )
            scheduler._checkpoint = mock.Mock()
            scheduler._transition = mock.Mock()
            scheduler._set_goal_status = mock.Mock(
                return_value={"threadId": "thread-r07", "status": "active"}
            )
            scheduler._wait_for_goal_complete = mock.Mock()
            scheduler._wait_until_idle = mock.Mock()
            scheduler._append_handoff = mock.Mock()

            scheduler._continue_existing_goal("R07")

            scheduler._set_goal_status.assert_called_once_with("R07", "active")
            scheduler._wait_for_goal_complete.assert_called_once_with("R07")
            scheduler._append_handoff.assert_called_once_with(
                "R07", handoff_dir / "R07.json"
            )
            self.assertEqual(
                [
                    call
                    for call in scheduler.client.method_calls
                    if call[0] == "request"
                ],
                [],
            )


class PromptLedgerDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name) / "project"
        self.run_dir = self.project / "perf_trace" / "runtime" / "branch" / "run"
        self.run_dir.mkdir(parents=True)
        self.ledger_path = self.run_dir / "runtime_handoff_ledger.json"
        self.scheduler = runner.RuntimeScheduler.__new__(runner.RuntimeScheduler)
        self.scheduler.project_root = self.project
        self.scheduler.run_dir = self.run_dir
        self.scheduler.ledger_path = self.ledger_path
        self.scheduler.branch = "branch"
        self.scheduler.run_id = "run"
        self.scheduler.user_parameters = {"policy": "test"}
        self.scheduler.manifest = {
            "bindings": {"R10": {"skill": "test-reporting-skill"}}
        }
        self.handoff = self.run_dir / "handoffs" / "R10.json"
        self.artifacts = self.run_dir / "artifacts" / "R10"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def set_ledger(self, payload: dict[str, Any]) -> None:
        self.scheduler.ledger = payload
        write_json(self.ledger_path, payload)

    def test_small_ledger_is_compactly_inlined(self) -> None:
        self.set_ledger(
            {
                "schema_version": 1,
                "branch": "branch",
                "run_id": "run",
                "handoffs": [{"source_goal": "R09", "marker": "small"}],
            }
        )

        prompt = self.scheduler._prompt("R10", self.handoff, self.artifacts)

        self.assertIn("紧凑 JSON 内联", prompt)
        self.assertIn('"marker":"small"', prompt)
        self.assertEqual(
            self.scheduler._last_prompt_metadata["ledger_delivery"],
            "inline_compact_json",
        )
        self.assertLessEqual(len(prompt), runner.APP_SERVER_INPUT_SAFE_CHARS)

    def test_fresh_prompt_normalizes_only_exact_legacy_semantic_values(self) -> None:
        self.scheduler.branch = runner.FRESH_E2E_BRANCH
        payload = {
            "schema_version": 1,
            "branch": runner.FRESH_E2E_BRANCH,
            "run_id": "run",
            "handoffs": [
                {
                    "source_goal": "R05",
                    "analysis_strategy": (
                        "fresh_current_child_full_request_e2e_timeline"
                    ),
                    "implementation": (
                        "/project/build_current_child_dependency_adapter.py"
                    ),
                }
            ],
        }
        self.set_ledger(payload)

        prompt = self.scheduler._prompt("R10", self.handoff, self.artifacts)

        canonical = runner.canonicalize_prompt_ledger_semantics(payload)
        compact = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"))
        self.assertIn(compact, prompt)
        self.assertIn("prompt_view_only_exact_value_aliases", prompt)
        self.assertEqual(runner.load_json(self.ledger_path), payload)
        self.assertEqual(
            self.scheduler._last_prompt_metadata["ledger_semantic_view"],
            "canonical_exact_aliases",
        )

    def test_large_ledger_uses_hashed_filesystem_reference(self) -> None:
        sentinel = "LARGE_LEDGER_MUST_NOT_BE_INLINED"
        self.set_ledger(
            {
                "schema_version": 1,
                "branch": "branch",
                "run_id": "run",
                "handoffs": [
                    {
                        "source_goal": "R09",
                        "payload": sentinel
                        + ("x" * (runner.MAX_INLINE_LEDGER_CHARS + 1)),
                    }
                ],
            }
        )

        prompt = self.scheduler._prompt("R10", self.handoff, self.artifacts)

        self.assertIn("immutable_filesystem_json", prompt)
        self.assertIn(str(self.ledger_path), prompt)
        self.assertIn(sha256_file(self.ledger_path), prompt)
        self.assertNotIn(sentinel, prompt)
        self.assertEqual(
            self.scheduler._last_prompt_metadata["ledger_delivery"],
            "immutable_filesystem_json",
        )
        self.assertLessEqual(len(prompt), runner.APP_SERVER_INPUT_SAFE_CHARS)

    def test_prompt_rejects_disk_ledger_drift(self) -> None:
        payload = {
            "schema_version": 1,
            "branch": "branch",
            "run_id": "run",
            "handoffs": [],
        }
        self.set_ledger(payload)
        write_json(self.ledger_path, {**payload, "unexpected": True})

        with self.assertRaisesRegex(
            runner.SchedulerError,
            "differs from the scheduler checkpoint",
        ):
            self.scheduler._prompt("R10", self.handoff, self.artifacts)

    def test_append_rejects_ledger_changed_during_goal(self) -> None:
        payload = {
            "schema_version": 1,
            "branch": "branch",
            "run_id": "run",
            "handoffs": [],
        }
        self.set_ledger(payload)
        write_json(self.ledger_path, {**payload, "unexpected": True})
        self.scheduler._goal_record = lambda goal_id: {}

        with self.assertRaisesRegex(
            runner.SchedulerError,
            "changed while the Goal was running",
        ):
            self.scheduler._append_handoff("R10", self.handoff)

    def test_workflow05_handoff_requires_separate_evidence_state(self) -> None:
        payload = {
            "schema_version": 1,
            "runtime_goal": "R10",
            "status": "complete",
            "skill": "test-reporting-skill",
        }
        write_json(self.handoff, payload)

        with self.assertRaisesRegex(
            runner.SchedulerError,
            "execution_status is not complete",
        ):
            self.scheduler._read_handoff("R10", self.handoff)

        payload.update(
            {
                "execution_status": "complete",
                "evidence_status": "insufficient",
                "coverage_target_met": False,
                "next_authorization_required": True,
            }
        )
        write_json(self.handoff, payload)
        self.assertEqual(
            self.scheduler._read_handoff("R10", self.handoff),
            payload,
        )

        payload.update(
            {
                "evidence_status": "complete",
                "coverage_target_met": False,
                "next_authorization_required": False,
            }
        )
        write_json(self.handoff, payload)
        with self.assertRaisesRegex(
            runner.SchedulerError,
            "evidence_status=complete requires",
        ):
            self.scheduler._read_handoff("R10", self.handoff)


class BranchContractIsolationTests(unittest.TestCase):
    def test_active_branches_use_disjoint_mode_specific_workflow05_skills(self) -> None:
        self.assertNotIn(runner.FULL_BRANCH, runner.BRANCHES)
        fresh = {
            runner.RUNTIME_BINDINGS[goal]["skill"]
            for goal in runner.WORKFLOW05_GOALS
        }
        legacy = {
            runner.LEGACY_WORKFLOW05_BINDINGS[goal]["skill"]
            for goal in runner.WORKFLOW05_GOALS
        }
        self.assertTrue(fresh.isdisjoint(legacy))
        self.assertEqual(
            runner.RUNTIME_BINDINGS["R07"]["skill"],
            "qwen-dcu-workflow05-full-request-process-trace",
        )
        self.assertNotIn("selective", runner.RUNTIME_BINDINGS["R07"]["skill"])

        project = SCRIPT.parents[2]
        for skill_name in fresh:
            text = (
                project / "perf_trace" / "skills" / skill_name / "SKILL.md"
            ).read_text(encoding="utf-8")
            with self.subTest(mode="fresh", skill=skill_name):
                self.assertIn("fresh_no_prior_runtime_reuse", text)
                self.assertNotIn("Fresh Full-Request E2E Mode", text)
                self.assertNotIn("workflow04_reuse_manifest", text)
                self.assertNotIn("current_child_dependency_adapter", text)

        for skill_name in legacy:
            text = (
                project / "perf_trace" / "skills" / skill_name / "SKILL.md"
            ).read_text(encoding="utf-8")
            with self.subTest(mode="legacy", skill=skill_name):
                self.assertIn("historical_then_selective", text)
                self.assertNotIn("fresh_no_prior_runtime_reuse", text)

    def test_resume_uses_branch_binding_and_only_exact_stopped_aliases(self) -> None:
        legacy_manifest = runner.BRANCHES[runner.EXISTING_EVIDENCE_BRANCH][
            "payload"
        ]
        self.assertEqual(
            runner.expected_resume_skill(
                "R06",
                manifest=legacy_manifest,
                completed_manifest_goals=["R06"],
            ),
            runner.LEGACY_WORKFLOW05_BINDINGS["R06"]["skill"],
        )
        self.assertTrue(
            runner.runtime_skill_name_matches(
                "qwen-dcu-workflow05-selective-process-trace",
                "qwen-dcu-workflow05-full-request-process-trace",
            )
        )
        self.assertTrue(
            runner.runtime_skill_name_matches(
                "qwen-dcu-workflow05-selective-process-trace",
                "qwen-dcu-workflow05-legacy-selective-process-trace",
            )
        )
        self.assertFalse(
            runner.runtime_skill_name_matches(
                "unrelated-skill", "qwen-dcu-workflow05-legacy-evidence-planning"
            )
        )


class Workflow05ParameterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name) / "project"
        (self.project / "pra2026-bh408").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_old_run_parameters_inherit_new_gap_controls(self) -> None:
        current = runner.resolve_user_parameters(self.project, {})
        old = copy.deepcopy(current)
        for key in (
            "authorized_additional_process_targets",
            "authorized_process_remeasurements",
            "authorized_additional_hardware_family_keys",
            "utilization_classification_thresholds",
            "dependency_coverage_threshold",
            "opportunity_gate_thresholds",
            "dependency_adapter",
            "traffic_resource_model",
            "live_hardware_sampling",
        ):
            old.pop(key)

        canonical = runner.canonicalize_stored_user_parameters(
            self.project,
            old,
        )

        self.assertEqual(canonical["authorized_additional_process_targets"], [])
        self.assertEqual(canonical["authorized_process_remeasurements"], [])
        self.assertEqual(canonical["live_hardware_sampling"]["mode"], "disabled")

    def test_stopped_fresh_run_migrates_parent_child_labels_only(self) -> None:
        collector = self.project / "collector.py"
        collector.write_text("# test collector\n", encoding="utf-8")
        current = runner.resolve_user_parameters(
            self.project,
            {
                "evidence_acquisition_mode": "fresh_no_prior_runtime_reuse",
                "analysis_strategy": "fresh_run_full_request_e2e_timeline",
                "measurement_contract_policy": "same_run_same_request",
                "base_evidence_role_on_execution_path_change": (
                    "preserve_semantically_valid_stage_evidence"
                ),
                "fresh_e2e_contract": copy.deepcopy(runner.FRESH_E2E_CONTRACT),
                "target_cumulative_latency_coverage": 1.0,
                "timeline_visualization": {
                    "required": True,
                    "layer1_output": "E2E_PROCESS_TIMELINE.html",
                    "layer1_timing_semantics": (
                        "observed_fresh_run_request_process_and_device_timeline"
                    ),
                    "layer2_track_groups": list(runner.REQUIRED_LAYER2_TRACK_GROUPS),
                    "hardware_counter_semantics": (
                        "observed_se_active_cu_samples_plus_replay_projected_pmc"
                    ),
                },
                "live_hardware_sampling": {
                    "schema_version": 1,
                    "mode": "rsmi_se_snapshot",
                    "collector": {
                        "schema_version": 1,
                        "path": str(collector),
                        "sha256": sha256_file(collector),
                    },
                    "sample_interval_ms": 0.5,
                    "metrics": ["se_active_cu_pct"],
                    "minimum_samples_per_process": 3,
                    "maximum_clock_alignment_error_ns": 1_000_000,
                    "require_resolution_finer_than_process_window": True,
                },
            },
        )
        legacy = copy.deepcopy(current)
        legacy["analysis_strategy"] = (
            "fresh_current_child_full_request_e2e_timeline"
        )
        legacy["measurement_contract_policy"] = "current_child_same_request"
        legacy["historical_evidence_role_on_execution_path_change"] = (
            "planning_only"
        )
        legacy["fresh_e2e_contract"] = copy.deepcopy(
            runner.LEGACY_FRESH_E2E_CONTRACT_V0
        )
        legacy["timeline_visualization"]["layer1_timing_semantics"] = (
            "observed_current_child_request_process_and_device_timeline"
        )

        canonical = runner.canonicalize_stored_user_parameters(
            self.project,
            legacy,
        )

        self.assertEqual(canonical, current)

    def test_stopped_legacy_run_migrates_child_label_to_separate_axes(self) -> None:
        current = runner.resolve_user_parameters(self.project, {})
        legacy = copy.deepcopy(current)
        legacy["measurement_contract_policy"] = "current_child_same_request"

        canonical = runner.canonicalize_stored_user_parameters(
            self.project,
            legacy,
        )

        self.assertEqual(canonical, current)

    def test_extension_authorizes_exact_new_process_and_lower_threshold(self) -> None:
        stored = runner.resolve_user_parameters(self.project, {})
        supplied = {
            "selection_batch_id": "extension-test-001",
            "escalation_reason": "close-current-child-process-coverage-gap",
            "authorized_additional_process_targets": [
                "pra.fx_process.input5_layer6.qkv_projection"
            ],
            "minimum_expected_evidence_value": {
                "policy": "marginal_request_latency_fraction",
                "value": 0.004,
            },
        }

        resolved = runner.resolve_extension_user_parameters(
            self.project,
            stored,
            supplied,
            start_goal="R07",
        )

        self.assertEqual(resolved["selection_batch_id"], "extension-test-001")
        self.assertEqual(
            resolved["authorized_additional_process_targets"],
            supplied["authorized_additional_process_targets"],
        )
        self.assertEqual(
            resolved["minimum_expected_evidence_value"]["value"],
            0.004,
        )

    def test_extension_rejects_process_capture_after_r07(self) -> None:
        stored = runner.resolve_user_parameters(self.project, {})
        with self.assertRaisesRegex(
            runner.SchedulerError,
            "require --extend-from R06 or R07",
        ):
            runner.resolve_extension_user_parameters(
                self.project,
                stored,
                {
                    "selection_batch_id": "extension-test-001",
                    "escalation_reason": "late-process-capture",
                    "authorized_additional_process_targets": [
                        "pra.fx_process.input5_layer6.qkv_projection"
                    ],
                },
                start_goal="R08",
            )

    def test_live_sampler_interval_must_be_positive(self) -> None:
        with self.assertRaisesRegex(
            runner.SchedulerError,
            "sample_interval_ms must be in",
        ):
            runner.resolve_user_parameters(
                self.project,
                {
                    "live_hardware_sampling": {
                        "schema_version": 1,
                        "mode": "disabled",
                        "collector": None,
                        "sample_interval_ms": 0,
                        "metrics": [],
                        "minimum_samples_per_process": 3,
                        "maximum_clock_alignment_error_ns": None,
                        "require_resolution_finer_than_process_window": True,
                    }
                },
            )

    def test_live_sampler_requires_explicit_process_remeasurement(self) -> None:
        collector = self.project / "tools" / "collector"
        collector.parent.mkdir(parents=True)
        collector.write_text("collector", encoding="utf-8")
        stored = runner.resolve_user_parameters(self.project, {})
        sampling = {
            "schema_version": 1,
            "mode": "hy_smi_sidecar",
            "collector": {
                "schema_version": 1,
                "path": str(collector),
                "sha256": sha256_file(collector),
            },
            "sample_interval_ms": 0.5,
            "metrics": ["hcu_utilization_pct"],
            "minimum_samples_per_process": 3,
            "maximum_clock_alignment_error_ns": 100_000,
            "require_resolution_finer_than_process_window": True,
        }
        supplied = {
            "selection_batch_id": "extension-live-test-001",
            "escalation_reason": "collect-original-run-utilization",
            "live_hardware_sampling": sampling,
        }
        with self.assertRaisesRegex(
            runner.SchedulerError,
            "requires explicitly authorized process targets",
        ):
            runner.resolve_extension_user_parameters(
                self.project,
                stored,
                supplied,
                start_goal="R07",
            )

        supplied["authorized_process_remeasurements"] = [
            "pra.fx_process.input0_layer0.mlp"
        ]
        resolved = runner.resolve_extension_user_parameters(
            self.project,
            stored,
            supplied,
            start_goal="R07",
        )
        self.assertEqual(
            resolved["authorized_process_remeasurements"],
            ["pra.fx_process.input0_layer0.mlp"],
        )


class ResumeValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name) / "project"
        (self.project / "pra2026-bh408").mkdir(parents=True)
        self.branch = runner.FULL_BRANCH
        self.run_id = "resume-test"
        self.run_dir = (
            self.project
            / "perf_trace"
            / "runtime"
            / self.branch
            / self.run_id
        )
        self.manifest_path = (
            self.project / "perf_trace" / "manifests" / "test_manifest.json"
        )
        goals = ["R01", "R02", "R03"]
        self.manifest = {
            "schema_version": 1,
            "branch": self.branch,
            "goals": goals,
            "bindings": {
                goal_id: copy.deepcopy(runner.RUNTIME_BINDINGS[goal_id])
                for goal_id in goals
            },
            "requires": [],
        }
        write_json(self.manifest_path, self.manifest)
        handoffs: list[dict[str, Any]] = []
        for goal_id in goals[:2]:
            skill = runner.RUNTIME_BINDINGS[goal_id]["skill"]
            path = self.run_dir / "handoffs" / f"{goal_id}.json"
            payload = {
                "schema_version": 1,
                "runtime_goal": goal_id,
                "status": "complete",
                "skill": skill,
            }
            write_json(path, payload)
            handoffs.append(
                {
                    "source_goal": goal_id,
                    "status": "complete",
                    "skill": skill,
                    "path": str(path),
                    "sha256": sha256_file(path),
                    "payload": payload,
                }
            )
        parameters = runner.resolve_user_parameters(self.project, {})
        ledger_path = self.run_dir / "runtime_handoff_ledger.json"
        state_path = self.run_dir / "state.json"
        ledger = {
            "schema_version": 1,
            "branch": self.branch,
            "run_id": self.run_id,
            "upstream_ledger": None,
            "handoffs": handoffs,
        }
        state = {
            "schema_version": 1,
            "branch": self.branch,
            "manifest": str(self.manifest_path.relative_to(self.project)),
            "run_id": self.run_id,
            "status": "stopped",
            "current_goal": "R03",
            "user_parameters": parameters,
            "upstream_ledger": None,
            "ledger": str(ledger_path.relative_to(self.project)),
            "goals": {
                goal_id: {
                    "skill": runner.RUNTIME_BINDINGS[goal_id]["skill"],
                    "status": "complete" if goal_id != "R03" else "stopped",
                    "thread_id": None,
                    "turn_ids": [],
                    "goal": None,
                    "error": None,
                }
                for goal_id in goals
            },
        }
        write_json(ledger_path, ledger)
        write_json(state_path, state)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def load(
        self,
        requested_goal: str | None = "R03",
        *,
        replay: bool = False,
        continue_current_goal: bool = False,
    ) -> dict[str, Any]:
        return runner.load_resume_context(
            project_root=self.project,
            branch=self.branch,
            manifest_path=self.manifest_path,
            manifest=self.manifest,
            run_id=self.run_id,
            requested_goal=requested_goal,
            replay=replay,
            continue_current_goal=continue_current_goal,
        )

    def prepare_continuable_goal(self) -> Path:
        artifact_root = self.run_dir / "artifacts" / "R03"
        artifact_root.mkdir(parents=True)
        (artifact_root / "partial.txt").write_text("partial", encoding="utf-8")
        state_path = self.run_dir / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        record = state["goals"]["R03"]
        record["thread_id"] = "thread-r03"
        record["runtime_artifact_root"] = str(
            artifact_root.relative_to(self.project)
        )
        record["goal"] = {
            "threadId": "thread-r03",
            "status": "paused",
        }
        record["error"] = "retryable transport notification misclassified"
        write_json(state_path, state)
        return artifact_root

    def prepare_completed_uncommitted_goal(self) -> Path:
        artifact_root = self.prepare_continuable_goal()
        state_path = self.run_dir / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["goals"]["R03"]["goal"]["status"] = "complete"
        write_json(state_path, state)
        handoff_path = self.run_dir / "handoffs" / "R03.json"
        write_json(
            handoff_path,
            {
                "schema_version": 1,
                "runtime_goal": "R03",
                "status": "complete",
                "skill": runner.RUNTIME_BINDINGS["R03"]["skill"],
            },
        )
        return handoff_path

    def complete_run(self) -> None:
        ledger_path = self.run_dir / "runtime_handoff_ledger.json"
        state_path = self.run_dir / "state.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        goal_id = "R03"
        skill = runner.RUNTIME_BINDINGS[goal_id]["skill"]
        handoff_path = self.run_dir / "handoffs" / f"{goal_id}.json"
        payload = {
            "schema_version": 1,
            "runtime_goal": goal_id,
            "status": "complete",
            "skill": skill,
        }
        write_json(handoff_path, payload)
        ledger["handoffs"].append(
            {
                "source_goal": goal_id,
                "status": "complete",
                "skill": skill,
                "path": str(handoff_path),
                "sha256": sha256_file(handoff_path),
                "payload": payload,
            }
        )
        state["status"] = "complete"
        state["current_goal"] = None
        state["completed_at"] = "test-completed-at"
        state["goals"][goal_id]["status"] = "complete"
        state["goals"][goal_id]["runtime_handoff"] = str(
            handoff_path.relative_to(self.project)
        )
        state["goals"][goal_id]["handoff_index"] = 2
        write_json(ledger_path, ledger)
        write_json(state_path, state)

    def test_resume_accepts_first_incomplete_goal(self) -> None:
        context = self.load()
        self.assertEqual(context["start_goal"], "R03")
        self.assertEqual(context["goal_ids"], ["R03"])

    def test_resume_goal_can_be_selected_automatically(self) -> None:
        context = self.load(requested_goal=None)
        self.assertEqual(context["start_goal"], "R03")

    def test_current_goal_continuation_reuses_thread_and_artifact_root(self) -> None:
        artifact_root = self.prepare_continuable_goal()

        context = self.load(continue_current_goal=True)

        self.assertTrue(context["continue_current_goal"])
        self.assertEqual(context["continued_goal"]["thread_id"], "thread-r03")
        self.assertEqual(context["continued_goal"]["artifact_root"], artifact_root)

    def test_current_goal_continuation_promotes_valid_completed_handoff(self) -> None:
        handoff_path = self.prepare_completed_uncommitted_goal()
        context = self.load(continue_current_goal=True)

        self.assertTrue(
            context["continued_goal"]["promote_existing_handoff"]
        )
        self.assertEqual(
            context["continued_goal"]["existing_handoff"], handoff_path
        )

        scheduler = runner.RuntimeScheduler.__new__(runner.RuntimeScheduler)
        scheduler.resume_context = context
        scheduler.project_root = self.project
        scheduler.run_dir = self.run_dir
        scheduler.handoff_dir = self.run_dir / "handoffs"
        scheduler.state_path = self.run_dir / "state.json"
        scheduler.ledger_path = self.run_dir / "runtime_handoff_ledger.json"
        scheduler.manifest = self.manifest
        scheduler.model = "test-model"
        scheduler.state = {}
        scheduler.ledger = {}
        scheduler.execution_goal_ids = []
        scheduler.artifact_attempt_name = None
        scheduler.user_parameters = context["user_parameters"]
        scheduler.branch = self.branch
        scheduler.run_id = self.run_id
        scheduler.client = None

        scheduler._initialize_resume_runtime_files()
        scheduler._continue_existing_goal("R03")

        self.assertEqual(scheduler.state["goals"]["R03"]["status"], "complete")
        self.assertEqual(len(scheduler.ledger["handoffs"]), 3)
        self.assertEqual(scheduler.ledger["handoffs"][-1]["source_goal"], "R03")
        self.assertNotIn(
            "promoting_existing_handoff", scheduler.state["goals"]["R03"]
        )

    def test_normal_resume_refuses_uncommitted_completed_handoff(self) -> None:
        self.prepare_completed_uncommitted_goal()
        with self.assertRaisesRegex(
            runner.SchedulerError,
            "refusing to overwrite uncommitted resume handoff",
        ):
            self.load()

    def test_continuation_refuses_handoff_before_saved_goal_complete(self) -> None:
        self.prepare_continuable_goal()
        handoff_path = self.run_dir / "handoffs" / "R03.json"
        write_json(
            handoff_path,
            {
                "schema_version": 1,
                "runtime_goal": "R03",
                "status": "complete",
                "skill": runner.RUNTIME_BINDINGS["R03"]["skill"],
            },
        )
        with self.assertRaisesRegex(
            runner.SchedulerError,
            "saved Goal is paused",
        ):
            self.load(continue_current_goal=True)

    def test_current_goal_continuation_initialization_preserves_attempt(self) -> None:
        artifact_root = self.prepare_continuable_goal()
        context = self.load(continue_current_goal=True)
        scheduler = runner.RuntimeScheduler.__new__(runner.RuntimeScheduler)
        scheduler.resume_context = context
        scheduler.project_root = self.project
        scheduler.run_dir = self.run_dir
        scheduler.state_path = self.run_dir / "state.json"
        scheduler.ledger_path = self.run_dir / "runtime_handoff_ledger.json"
        scheduler.manifest = self.manifest
        scheduler.model = "test-model"
        scheduler.state = {}
        scheduler.ledger = {}
        scheduler.execution_goal_ids = []
        scheduler.artifact_attempt_name = None

        scheduler._initialize_resume_runtime_files()

        record = scheduler.state["goals"]["R03"]
        self.assertEqual(record["thread_id"], "thread-r03")
        self.assertEqual(
            record["runtime_artifact_root"],
            str(artifact_root.relative_to(self.project)),
        )
        self.assertEqual(record["status"], "pending")
        self.assertTrue(record["continuing_existing_thread"])
        self.assertEqual(len(record["continuation_history"]), 1)
        self.assertNotIn("attempt_history", record)

    def test_current_goal_continuation_requires_explicit_goal(self) -> None:
        self.prepare_continuable_goal()
        with self.assertRaisesRegex(
            runner.SchedulerError,
            "requires an explicit --resume-from",
        ):
            self.load(requested_goal=None, continue_current_goal=True)

    def test_resume_initialization_preserves_completed_prefix_and_audit(self) -> None:
        context = self.load()
        scheduler = runner.RuntimeScheduler.__new__(runner.RuntimeScheduler)
        scheduler.resume_context = context
        scheduler.project_root = self.project
        scheduler.run_dir = self.run_dir
        scheduler.state_path = self.run_dir / "state.json"
        scheduler.ledger_path = self.run_dir / "runtime_handoff_ledger.json"
        scheduler.manifest = self.manifest
        scheduler.model = "test-model"
        scheduler.state = {}
        scheduler.ledger = {}
        scheduler.execution_goal_ids = []
        scheduler.artifact_attempt_name = None

        scheduler._initialize_resume_runtime_files()

        self.assertEqual(scheduler.state["status"], "running")
        self.assertEqual(scheduler.state["goals"]["R02"]["status"], "complete")
        self.assertEqual(scheduler.state["goals"]["R03"]["status"], "pending")
        self.assertEqual(
            scheduler.state["goals"]["R03"]["attempt_history"][0]["status"],
            "stopped",
        )
        self.assertEqual(scheduler.state["resume_history"][0]["from_goal"], "R03")
        self.assertEqual(scheduler.execution_goal_ids, ["R03"])

    def test_resume_rejects_completed_or_skipped_goal(self) -> None:
        with self.assertRaisesRegex(
            runner.SchedulerError,
            "first incomplete Goal R03",
        ):
            self.load(requested_goal="R02")

    def test_resume_rejects_handoff_drift(self) -> None:
        path = self.run_dir / "handoffs" / "R02.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["unexpected"] = True
        write_json(path, payload)
        with self.assertRaisesRegex(runner.SchedulerError, "differs"):
            self.load()

    def test_stale_running_recovery_snapshots_and_stops_first_incomplete(self) -> None:
        state_path = self.run_dir / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["status"] = "running"
        state["execution_status"] = "running"
        state["goals"]["R03"]["status"] = "running"
        write_json(state_path, state)
        prior_state_sha256 = sha256_file(state_path)
        prior_ledger_sha256 = sha256_file(
            self.run_dir / "runtime_handoff_ledger.json"
        )

        recovery = runner.recover_stale_running_state(
            project_root=self.project,
            branch=self.branch,
            manifest_path=self.manifest_path,
            manifest=self.manifest,
            run_id=self.run_id,
            requested_goal="R03",
        )

        self.assertIsNotNone(recovery)
        assert recovery is not None
        recovered = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(recovered["status"], "stopped")
        self.assertEqual(recovered["execution_status"], "stopped")
        self.assertEqual(recovered["goals"]["R03"]["status"], "stopped")
        self.assertEqual(recovery["prior_state_sha256"], prior_state_sha256)
        self.assertEqual(recovery["prior_ledger_sha256"], prior_ledger_sha256)
        self.assertEqual(
            sha256_file(self.project / recovery["state_snapshot"]),
            prior_state_sha256,
        )
        self.assertEqual(
            sha256_file(self.project / recovery["ledger_snapshot"]),
            prior_ledger_sha256,
        )
        context = self.load()
        self.assertEqual(context["start_goal"], "R03")

    def test_stale_running_recovery_refuses_live_runtime_process(self) -> None:
        state_path = self.run_dir / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["status"] = "running"
        state["execution_status"] = "running"
        state["goals"]["R03"]["status"] = "running"
        write_json(state_path, state)

        with mock.patch.object(
            runner,
            "find_live_runtime_processes",
            return_value=[{"pid": 1234, "command": "active scheduler"}],
        ):
            with self.assertRaisesRegex(
                runner.SchedulerError,
                "runtime processes are still alive",
            ):
                runner.recover_stale_running_state(
                    project_root=self.project,
                    branch=self.branch,
                    manifest_path=self.manifest_path,
                    manifest=self.manifest,
                    run_id=self.run_id,
                    requested_goal="R03",
                )

        unchanged = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(unchanged["status"], "running")

    def test_resume_uses_new_attempt_directory_for_partial_artifacts(self) -> None:
        canonical = self.run_dir / "artifacts" / "R03"
        canonical.mkdir(parents=True)
        (canonical / "partial.txt").write_text("partial", encoding="utf-8")
        scheduler = runner.RuntimeScheduler.__new__(runner.RuntimeScheduler)
        scheduler.run_dir = self.run_dir
        scheduler.resume_context = {"start_goal": "R03"}

        selected = scheduler._select_artifact_root("R03")

        self.assertEqual(selected.name, "resume-001")
        self.assertTrue(selected.is_dir())

    def test_replay_accepts_completed_runtime_from_any_goal(self) -> None:
        self.complete_run()

        context = self.load(requested_goal="R02", replay=True)

        self.assertEqual(context["mode"], "replay")
        self.assertEqual(context["start_goal"], "R02")
        self.assertEqual(context["goal_ids"], ["R02", "R03"])
        self.assertEqual(context["ledger_prefix_length"], 1)

    def test_replay_initialization_preserves_prior_outputs_and_snapshots(self) -> None:
        self.complete_run()
        old_artifact = self.run_dir / "artifacts" / "R02" / "old.txt"
        old_artifact.parent.mkdir(parents=True)
        old_artifact.write_text("old", encoding="utf-8")
        prior_state_hash = sha256_file(self.run_dir / "state.json")
        prior_ledger_hash = sha256_file(
            self.run_dir / "runtime_handoff_ledger.json"
        )
        context = self.load(requested_goal="R02", replay=True)
        scheduler = runner.RuntimeScheduler.__new__(runner.RuntimeScheduler)
        scheduler.resume_context = context
        scheduler.project_root = self.project
        scheduler.run_dir = self.run_dir
        scheduler.handoff_dir = self.run_dir / "handoffs"
        scheduler.state_path = self.run_dir / "state.json"
        scheduler.ledger_path = self.run_dir / "runtime_handoff_ledger.json"
        scheduler.manifest = self.manifest
        scheduler.model = "test-model"
        scheduler.state = {}
        scheduler.ledger = {}
        scheduler.execution_goal_ids = []
        scheduler.artifact_attempt_name = None

        scheduler._initialize_resume_runtime_files()

        self.assertEqual(scheduler.state["status"], "running")
        self.assertEqual(scheduler.state["goals"]["R01"]["status"], "complete")
        self.assertEqual(scheduler.state["goals"]["R02"]["status"], "pending")
        self.assertEqual(len(scheduler.ledger["handoffs"]), 1)
        self.assertTrue((self.run_dir / "handoffs" / "R02.json").is_file())
        self.assertTrue((self.run_dir / "handoffs" / "R03.json").is_file())
        self.assertEqual(scheduler.handoff_dir.name, "replay-001")
        history = scheduler.state["replay_history"][0]
        self.assertEqual(history["prior_state_sha256"], prior_state_hash)
        self.assertEqual(history["prior_ledger_sha256"], prior_ledger_hash)
        self.assertEqual(
            sha256_file(self.project / history["state_snapshot"]),
            prior_state_hash,
        )
        self.assertEqual(
            sha256_file(self.project / history["ledger_snapshot"]),
            prior_ledger_hash,
        )
        selected = scheduler._select_artifact_root("R02")
        self.assertEqual(selected.name, "replay-001")
        self.assertEqual(old_artifact.read_text(encoding="utf-8"), "old")

    def test_replay_rejects_goal_after_incomplete_predecessor(self) -> None:
        state_path = self.run_dir / "state.json"
        ledger_path = self.run_dir / "runtime_handoff_ledger.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        state["goals"]["R02"]["status"] = "stopped"
        ledger["handoffs"] = ledger["handoffs"][:1]
        write_json(state_path, state)
        write_json(ledger_path, ledger)

        with self.assertRaisesRegex(
            runner.SchedulerError,
            "predecessor chain is incomplete at R02",
        ):
            self.load(requested_goal="R03", replay=True)


class Workflow05ExtensionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name) / "project"
        (self.project / "pra2026-bh408").mkdir(parents=True)
        self.branch = runner.FULL_BRANCH
        self.run_id = "extension-test"
        self.run_dir = (
            self.project
            / "perf_trace"
            / "runtime"
            / self.branch
            / self.run_id
        )
        self.manifest_path = (
            self.project / "perf_trace" / "manifests" / "workflow05-test.json"
        )
        goals = ["R06", "R07", "R08", "R09", "R10"]
        self.manifest = {
            "schema_version": 1,
            "branch": self.branch,
            "goals": goals,
            "bindings": {
                goal_id: copy.deepcopy(runner.RUNTIME_BINDINGS[goal_id])
                for goal_id in goals
            },
            "requires": [],
        }
        write_json(self.manifest_path, self.manifest)
        handoffs: list[dict[str, Any]] = []
        goal_records: dict[str, dict[str, Any]] = {}
        for index, goal_id in enumerate(goals):
            skill = runner.RUNTIME_BINDINGS[goal_id]["skill"]
            path = self.run_dir / "handoffs" / f"{goal_id}.json"
            payload = {
                "schema_version": 1,
                "runtime_goal": goal_id,
                "status": "complete",
                "skill": skill,
            }
            write_json(path, payload)
            handoffs.append(
                {
                    "source_goal": goal_id,
                    "status": "complete",
                    "skill": skill,
                    "path": str(path),
                    "sha256": sha256_file(path),
                    "payload": payload,
                }
            )
            goal_records[goal_id] = {
                "skill": skill,
                "status": "complete",
                "thread_id": None,
                "turn_ids": [],
                "goal": None,
                "error": None,
                "runtime_handoff": str(path.relative_to(self.project)),
                "handoff_index": index,
            }
        self.ledger_path = self.run_dir / "runtime_handoff_ledger.json"
        self.state_path = self.run_dir / "state.json"
        parameters = runner.resolve_user_parameters(self.project, {})
        write_json(
            self.ledger_path,
            {
                "schema_version": 1,
                "branch": self.branch,
                "run_id": self.run_id,
                "upstream_ledger": None,
                "handoffs": handoffs,
            },
        )
        write_json(
            self.state_path,
            {
                "schema_version": 1,
                "branch": self.branch,
                "manifest": str(self.manifest_path.relative_to(self.project)),
                "run_id": self.run_id,
                "status": "complete",
                "current_goal": None,
                "completed_at": "test-completed-at",
                "user_parameters": parameters,
                "upstream_ledger": None,
                "ledger": str(self.ledger_path.relative_to(self.project)),
                "goals": goal_records,
            },
        )
        self.extension_parameters = {
            "selection_batch_id": "extension-test-001",
            "escalation_reason": "close-current-child-process-coverage-gap",
            "authorized_additional_process_targets": [
                "pra.fx_process.input5_layer6.qkv_projection"
            ],
            "minimum_expected_evidence_value": {
                "policy": "marginal_request_latency_fraction",
                "value": 0.004,
            },
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def load(
        self,
        *,
        requested_goal: str = "R07",
        extension_parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return runner.load_resume_context(
            project_root=self.project,
            branch=self.branch,
            manifest_path=self.manifest_path,
            manifest=self.manifest,
            run_id=self.run_id,
            requested_goal=requested_goal,
            extend=True,
            extension_parameters=(
                extension_parameters or self.extension_parameters
            ),
        )

    def test_extension_accepts_complete_runtime_and_preserves_base(self) -> None:
        prior_state_hash = sha256_file(self.state_path)
        prior_ledger_hash = sha256_file(self.ledger_path)
        context = self.load()
        scheduler = runner.RuntimeScheduler(
            project_root=self.project,
            branch=self.branch,
            manifest_path=self.manifest_path,
            manifest=self.manifest,
            user_parameters=context["user_parameters"],
            upstream_ledger=None,
            upstream_provenance=None,
            codex_bin=Path("/bin/true"),
            model="test-model",
            run_id=self.run_id,
            poll_seconds=0.01,
            request_timeout=1.0,
            goal_timeout_seconds=0.0,
            idle_timeout_seconds=0.0,
            resume_context=context,
        )

        scheduler._initialize_resume_runtime_files()

        self.assertEqual(context["mode"], "extend")
        self.assertEqual(scheduler.execution_goal_ids, ["R07", "R08", "R09", "R10"])
        self.assertEqual(scheduler.handoff_dir.name, "extension-001")
        self.assertEqual(scheduler.state["status"], "running")
        self.assertEqual(scheduler.state["goals"]["R06"]["status"], "complete")
        self.assertEqual(scheduler.state["goals"]["R07"]["status"], "pending")
        self.assertEqual(len(scheduler.ledger["handoffs"]), 1)
        active = scheduler.state["active_extension"]
        self.assertEqual(active["base_ledger"]["handoff_count"], 5)
        self.assertEqual(active["base_ledger"]["sha256"], prior_ledger_hash)
        history = scheduler.state["extension_history"][0]
        self.assertEqual(history["prior_state_sha256"], prior_state_hash)
        self.assertEqual(history["prior_ledger_sha256"], prior_ledger_hash)
        frozen_ledger = self.project / active["base_ledger"]["path"]
        self.assertEqual(sha256_file(frozen_ledger), prior_ledger_hash)
        self.assertEqual(
            scheduler.state["user_parameters"]["selection_batch_id"],
            "extension-test-001",
        )
        self.assertTrue((self.run_dir / "handoffs" / "R10.json").is_file())

    def test_extension_rejects_non_complete_runtime(self) -> None:
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        state["status"] = "stopped"
        write_json(self.state_path, state)
        with self.assertRaisesRegex(
            runner.SchedulerError,
            "requires state.status=complete",
        ):
            self.load()

    def test_extension_can_start_at_r08_for_authorized_hardware_delta(self) -> None:
        context = self.load(
            requested_goal="R08",
            extension_parameters={
                "selection_batch_id": "extension-r08-test-001",
                "escalation_reason": "authorize-deferred-hardware-family",
                "authorized_additional_hardware_family_keys": [
                    "contract/child/11/19/11/mlp/family=reduction_softmax"
                ],
                "minimum_expected_evidence_value": {
                    "policy": "marginal_request_latency_fraction",
                    "value": 0.004,
                },
            },
        )

        self.assertEqual(context["start_goal"], "R08")
        self.assertEqual(context["goal_ids"], ["R08", "R09", "R10"])
        self.assertEqual(context["ledger_prefix_length"], 2)


class FreshHandoffValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name) / "project"
        self.branch = runner.FRESH_E2E_BRANCH
        self.run_id = "fresh-test-run"
        self.run_dir = (
            self.project / "perf_trace" / "runtime" / self.branch / self.run_id
        )
        self.artifacts = self.run_dir / "artifacts" / "R06"
        self.artifacts.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def reference(path: Path, **extra: Any) -> dict[str, Any]:
        return {
            "path": str(path.resolve()),
            "sha256": sha256_file(path),
            **extra,
        }

    def build_r06_payload(self) -> tuple[dict[str, Any], Path]:
        upstream = self.run_dir / "handoffs" / "R01.json"
        write_json(upstream, {"runtime_goal": "R01", "status": "complete"})
        ledger = self.run_dir / "runtime_handoff_ledger.json"
        write_json(
            ledger,
            {"branch": self.branch, "run_id": self.run_id, "handoffs": []},
        )
        contract = self.run_dir / "artifacts" / "R01" / "contract.json"
        write_json(contract, {"contract_id": "contract-1"})
        events = self.artifacts / "full_request_process_targets.txt"
        ranges = self.artifacts / "full_request_process_range_targets.txt"
        hardware = self.artifacts / "bounded_hardware_plan.csv"
        events.write_text("input0_layer0\n", encoding="utf-8")
        ranges.write_text(
            "pra.fx_process.input0_layer0.qkv_projection\n",
            encoding="utf-8",
        )
        hardware.write_text("kernel_family\ngemm\n", encoding="utf-8")
        lineage_id = "fresh-run:fresh-test-run:contract-1"
        targets_path = self.artifacts / "full_request_target_manifest.json"
        write_json(
            targets_path,
            {
                "schema_version": 1,
                "status": "PASS",
                "branch": self.branch,
                "run_id": self.run_id,
                "lineage_id": lineage_id,
                "capture_scope": "one_fresh_run_request_all_process_ranges",
                "event_target_file": self.reference(events, line_count=1),
                "range_target_file": self.reference(ranges, line_count=1),
                "r08_hardware_subset": self.reference(hardware, row_count=1),
            },
        )
        lineage_path = self.artifacts / "fresh_run_lineage_manifest.json"
        write_json(
            lineage_path,
            {
                "schema_version": 1,
                "status": "PASS",
                "branch": self.branch,
                "run_id": self.run_id,
                "lineage_id": lineage_id,
                "semantic_contract_id": "contract-1",
                "evidence_source_policy": "current_run_only",
                "source_change_policy": "stage_trace_instrumentation_allowed",
                "source_hash_equality_required": False,
                "external_runtime_reference_count": 0,
                "upstream_goals": list(runner.UPSTREAM_GOAL_IDS),
                "ledger": self.reference(ledger),
                "semantic_contract": self.reference(contract),
                "runtime_references": [self.reference(upstream)],
                "stage_instrumentation_deltas": [
                    {
                        "stage": "R02",
                        "before_revision": "revision-a",
                        "after_revision": "revision-b",
                    }
                ],
                "semantic_invariants": {"status": "PASS"},
                "target_manifest": self.reference(targets_path),
            },
        )
        return (
            {
                "evidence_status": "complete",
                "coverage_target_met": True,
                "next_authorization_required": False,
                "fresh_e2e_evidence": {
                    "schema_version": 1,
                    "status": "complete",
                    "lineage_id": lineage_id,
                    "fresh_run_lineage_manifest": self.reference(lineage_path),
                    "full_request_target_manifest": self.reference(targets_path),
                },
            },
            lineage_path,
        )

    def build_later_stage_payload(
        self,
        goal_id: str,
        evidence_key: str,
        evidence_payload: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        lineage_id = "fresh-run:fresh-test-run:contract-1"
        source_lineage = self.artifacts / f"{goal_id}_source_lineage.json"
        write_json(
            source_lineage,
            {
                "status": "complete",
                "lineage_id": lineage_id,
                "source_hash_equality_required": False,
            },
        )
        evidence_path = self.artifacts / f"{goal_id}_{evidence_key}.json"
        write_json(evidence_path, evidence_payload)
        return (
            {
                "evidence_status": "complete",
                "coverage_target_met": True,
                "next_authorization_required": False,
                "fresh_e2e_evidence": {
                    "schema_version": 1,
                    "status": "complete",
                    "lineage_id": lineage_id,
                    "source_lineage": self.reference(source_lineage),
                    evidence_key: self.reference(evidence_path),
                },
            },
            lineage_id,
        )

    def test_r06_allows_stage_source_revision_changes(self) -> None:
        payload, _ = self.build_r06_payload()

        runner.validate_fresh_e2e_handoff(
            "R06",
            payload,
            project_root=self.project,
            run_dir=self.run_dir,
            branch=self.branch,
            run_id=self.run_id,
            expected_lineage_id=None,
        )

    def test_frozen_r08_source_lineage_is_valid_when_semantics_are_fixed(
        self,
    ) -> None:
        lineage_id = "fresh-run:fresh-test-run:contract-1"
        source_lineage = self.artifacts / "R08_frozen_source_lineage.json"
        write_json(
            source_lineage,
            {
                "schema_version": 1,
                "status": "frozen",
                "runtime_goal": "R08",
                "lineage_id": lineage_id,
                "source_change_policy": "stage_trace_instrumentation_allowed",
                "source_hash_equality_required": False,
                "model_input_sampling_device_semantics_changed": False,
                "r07_process_family_identity_changed": False,
            },
        )

        runner._validate_fresh_source_lineage(
            {"source_lineage": self.reference(source_lineage)},
            goal_id="R08",
            lineage_id=lineage_id,
            project_root=self.project,
            run_dir=self.run_dir,
        )

    def test_frozen_r08_source_lineage_rejects_semantic_change(self) -> None:
        lineage_id = "fresh-run:fresh-test-run:contract-1"
        source_lineage = self.artifacts / "R08_changed_source_lineage.json"
        write_json(
            source_lineage,
            {
                "schema_version": 1,
                "status": "frozen",
                "runtime_goal": "R08",
                "lineage_id": lineage_id,
                "source_change_policy": "stage_trace_instrumentation_allowed",
                "source_hash_equality_required": False,
                "model_input_sampling_device_semantics_changed": True,
                "r07_process_family_identity_changed": False,
            },
        )

        with self.assertRaisesRegex(
            runner.SchedulerError,
            "semantically invalid",
        ):
            runner._validate_fresh_source_lineage(
                {"source_lineage": self.reference(source_lineage)},
                goal_id="R08",
                lineage_id=lineage_id,
                project_root=self.project,
                run_dir=self.run_dir,
            )

    def test_r06_rejects_another_runtime_tree(self) -> None:
        payload, lineage_path = self.build_r06_payload()
        external = (
            self.project
            / "perf_trace"
            / "runtime"
            / self.branch
            / "another-run"
            / "handoffs"
            / "R01.json"
        )
        write_json(external, {"runtime_goal": "R01", "status": "complete"})
        lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
        lineage["runtime_references"].append(self.reference(external))
        write_json(lineage_path, lineage)
        payload["fresh_e2e_evidence"]["fresh_run_lineage_manifest"] = (
            self.reference(lineage_path)
        )

        with self.assertRaisesRegex(runner.SchedulerError, "current run"):
            runner.validate_fresh_e2e_handoff(
                "R06",
                payload,
                project_root=self.project,
                run_dir=self.run_dir,
                branch=self.branch,
                run_id=self.run_id,
                expected_lineage_id=None,
            )

    def test_r09_rejects_old_five_table_analysis_contract(self) -> None:
        parameters = {
            "utilization_classification_thresholds": {
                "observed_se_active_cu_low_pct": 35.0,
                "low_kernel_concurrency_max_active_kernels": 1,
                "runtime_launch_gap_min_ns": 10_000,
            },
            "dependency_coverage_threshold": {"value": 0.75},
            "opportunity_gate_thresholds": {
                "minimum_exposed_duration_ns": 10_000,
                "minimum_exposed_fraction": 0.05,
                "slack_tolerance_ns": 1_000,
            },
        }
        configured_gates = {
            "low_se_utilization_pct": 35.0,
            "low_kernel_concurrency_max": 1,
            "minimum_launch_gap_ns": 10_000,
            "minimum_dependency_coverage": 0.75,
            "minimum_exposed_duration_ns": 10_000,
            "minimum_exposed_fraction": 0.05,
            "slack_tolerance_ns": 1_000,
            "require_all_seven_gates": True,
        }
        lineage_id = "fresh-run:fresh-test-run:contract-1"
        analysis = {
            "status": "PASS",
            "analysis_type": "fresh_run_full_request_e2e",
            "lineage_id": lineage_id,
            "full_request_observed_timeline": True,
            "high_latency_process_count": 1,
            "high_latency_processes_with_live_samples": 1,
            "fresh_run_dependency_adapter_consumed": True,
            "traffic_resource_model_consumed": True,
            "track_type_counts": {
                "request": 1,
                "forward": 1,
                "layer": 1,
                "hip_runtime": 1,
            },
            "configured_gates": configured_gates,
            "normalized_tables": {
                name: {"path": "unused.csv", "sha256": "unused", "row_count": 1}
                for name in runner.FRESH_E2E_NORMALIZED_TABLES[:5]
            },
        }
        payload, _ = self.build_later_stage_payload(
            "R09", "full_request_analysis", analysis
        )

        with self.assertRaisesRegex(
            runner.SchedulerError,
            "fresh full-request analysis is incomplete",
        ):
            runner.validate_fresh_e2e_handoff(
                "R09",
                payload,
                project_root=self.project,
                run_dir=self.run_dir,
                branch=self.branch,
                run_id=self.run_id,
                expected_lineage_id=lineage_id,
                user_parameters=parameters,
            )

    def test_r10_rejects_incomplete_view_coverage(self) -> None:
        lineage_id = "fresh-run:fresh-test-run:contract-1"
        acceptance = {
            "status": "PASS",
            "lineage_id": lineage_id,
            "self_contained_offline": True,
            "outputs": {
                name: {"path": "unused.html", "sha256": "unused"}
                for name in (
                    "index.html",
                    "E2E_PROCESS_TIMELINE.html",
                    "HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html",
                    "CONCURRENCY_UTILIZATION.html",
                )
            },
            "view_coverage": {
                "track_groups": list(runner.FRESH_E2E_VIEW_TRACK_GROUPS[:-1]),
                "filters_search_zoom": True,
                "source_table_hashes_verified": True,
                "evidence_legends_complete": True,
            },
        }
        payload, _ = self.build_later_stage_payload(
            "R10", "offline_acceptance_manifest", acceptance
        )

        with self.assertRaisesRegex(
            runner.SchedulerError,
            "offline fresh-E2E acceptance bundle is incomplete",
        ):
            runner.validate_fresh_e2e_handoff(
                "R10",
                payload,
                project_root=self.project,
                run_dir=self.run_dir,
                branch=self.branch,
                run_id=self.run_id,
                expected_lineage_id=lineage_id,
            )


class EvidenceSummaryTests(unittest.TestCase):
    def test_incomplete_coverage_is_not_reported_as_execution_failure(self) -> None:
        ledger = {
            "handoffs": [
                {
                    "source_goal": "R09",
                    "sha256": "a" * 64,
                    "payload": {
                        "evidence_status": "insufficient",
                        "coverage_and_risk": {
                            "target_state": {"coverage_target_met": False},
                            "terminal_sampling_decision": {
                                "decision": "requires_new_authorization",
                                "deferred_next_r07_batch": {
                                    "requested": True,
                                    "authorized_or_executed_by_this_goal": False,
                                },
                            },
                            "unresolved_bindings": {
                                "dependency": "unavailable",
                                "utilization": "unavailable",
                            },
                            "risk_summary": {
                                "confirmed_concurrency_opportunities": 0,
                                "candidate_only_opportunities": 4,
                            },
                        },
                    },
                }
            ]
        }

        summary = runner.derive_workflow05_evidence_summary(ledger)

        self.assertEqual(summary["evidence_status"], "insufficient")
        self.assertFalse(summary["coverage_target_met"])
        self.assertTrue(summary["next_authorization_required"])
        self.assertEqual(summary["unresolved_binding_count"], 2)


class CliTests(unittest.TestCase):
    def test_start_goal_alias_maps_to_resume_from(self) -> None:
        args = runner.parse_args(
            [
                "--branch",
                runner.EXISTING_EVIDENCE_BRANCH,
                "--resume-run-id",
                "run-1",
                "--start-goal",
                "R08",
            ]
        )
        self.assertEqual(args.resume_run_id, "run-1")
        self.assertEqual(args.resume_from, "R08")

    def test_replay_from_is_explicit_and_mutually_exclusive(self) -> None:
        args = runner.parse_args(
            [
                "--branch",
                runner.EXISTING_EVIDENCE_BRANCH,
                "--resume-run-id",
                "run-1",
                "--replay-from",
                "R08",
            ]
        )
        self.assertEqual(args.resume_run_id, "run-1")
        self.assertEqual(args.replay_from, "R08")
        self.assertIsNone(args.resume_from)

    def test_extend_from_has_explicit_parameters(self) -> None:
        args = runner.parse_args(
            [
                "--branch",
                runner.EXISTING_EVIDENCE_BRANCH,
                "--resume-run-id",
                "run-1",
                "--extend-from",
                "R07",
                "--extension-parameters",
                '{"selection_batch_id":"extension-001"}',
            ]
        )
        self.assertEqual(args.extend_from, "R07")
        self.assertIsNone(args.replay_from)
        self.assertIsNotNone(args.extension_parameters)

    def test_stale_running_recovery_flag_is_explicit(self) -> None:
        args = runner.parse_args(
            [
                "--branch",
                runner.FRESH_E2E_BRANCH,
                "--resume-run-id",
                "run-1",
                "--resume-from",
                "R04",
                "--recover-stale-running",
            ]
        )
        self.assertTrue(args.recover_stale_running)

    def test_current_goal_continuation_flag_is_explicit(self) -> None:
        args = runner.parse_args(
            [
                "--branch",
                runner.FRESH_E2E_BRANCH,
                "--resume-run-id",
                "run-1",
                "--resume-from",
                "R07",
                "--continue-current-goal",
            ]
        )
        self.assertTrue(args.continue_current_goal)
        self.assertEqual(args.resume_from, "R07")


if __name__ == "__main__":
    unittest.main()
