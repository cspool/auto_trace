#!/usr/bin/env python3
"""Focused tests for the Workflow-capability-complete adaptation control plane."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


SOURCE_ROOT = Path(__file__).resolve().parents[4]
ADAPTATION_RELATIVE_ROOT = Path(
    "workload_profile/workflows/project_adaptation"
)
SOURCE_ADAPTATION_ROOT = SOURCE_ROOT / ADAPTATION_RELATIVE_ROOT
ORCHESTRATOR = SOURCE_ADAPTATION_ROOT / "scripts" / "adapt_workload_profile.py"
SOURCE_PLAN = SOURCE_ADAPTATION_ROOT / "manifests" / "adaptation_plan.json"
FAKE_CODEX = Path(__file__).resolve().parent / "fake_codex_app_server.py"
VERIFIER = SOURCE_ADAPTATION_ROOT / "scripts" / "verify_adaptation_output.py"
STAGE_ORDER = (
    "A00",
    "A01",
    "A02",
    "A031",
    "A041",
    "A051",
    "A032",
    "A033",
    "A042",
    "A052",
    "A07",
)
PROTOCOL = "goal-owned-turns-v7-workflow-capability-complete"
STATE_NAME = "adaptation_state_workflow_capability_complete_v1.json"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


class WorkflowCapabilityBootstrapTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="adapt-bootstrap-capability-test-"
        )
        self.project_root = Path(self.temporary.name) / "project"
        self.project_root.mkdir(parents=True)
        self.plan = json.loads(SOURCE_PLAN.read_text(encoding="utf-8"))
        self.request_log = self.project_root / "fake-requests.jsonl"
        self.fake_server_state = self.project_root / "fake-server-state.json"
        self.adaptation_root = self.project_root / ADAPTATION_RELATIVE_ROOT
        self.state_path = (
            self.adaptation_root / "state" / STATE_NAME
        )
        self.plan_path = (
            self.adaptation_root / "manifests" / "adaptation_plan.json"
        )
        self._prepare_fixture()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _copy_contract_inputs(self) -> None:
        referenced_files = {
            self.plan["workflow_contract"],
            self.plan["implementation_plan"],
            self.plan["common_goal_contract"],
        }
        referenced_files.update(
            item["path"] for item in self.plan["workflow_inventory"]
        )
        for stage in self.plan["stages"]:
            referenced_files.add(stage["goal_template"])
            referenced_files.update(stage.get("workflow_requirements", []))
            authority = stage.get("workflow_authority")
            if isinstance(authority, dict):
                referenced_files.add(authority["path"])
            referenced_files.update(
                item["path"] for item in stage.get("binding_evidence", [])
            )
        for relative in sorted(referenced_files):
            source = SOURCE_ROOT / relative
            target = self.project_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def _prepare_source_skills(self) -> None:
        self.source_skill_roots: dict[str, Path] = {}
        declarations: dict[str, dict[str, Any]] = {}
        for stage in self.plan["stages"]:
            source_skill = stage.get("source_skill")
            if isinstance(source_skill, dict):
                declarations.setdefault(source_skill["name"], source_skill)
        for name, declaration in declarations.items():
            source_root = self.project_root / "fake_global_skills" / name
            self.source_skill_roots[name] = source_root
            for relative in declaration["file_set"]:
                path = source_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                if relative == "SKILL.md":
                    path.write_text(
                        "---\n"
                        f"name: {name}\n"
                        "description: Fake source Skill.\n"
                        "---\n\n"
                        "# Source method\n",
                        encoding="utf-8",
                    )
                elif relative == "agents/openai.yaml":
                    path.write_text(
                        "interface:\n"
                        f'  display_name: "{name}"\n'
                        '  short_description: "Fixture source Skill"\n'
                        f'  default_prompt: "Use ${name}."\n',
                        encoding="utf-8",
                    )
                else:
                    path.write_text(
                        "#!/usr/bin/env python3\n"
                        "\"\"\"Fixture bundled source resource.\"\"\"\n",
                        encoding="utf-8",
                    )
            declaration_hash = tree_digest(source_root)
            for stage in self.plan["stages"]:
                source_skill = stage.get("source_skill")
                if (
                    isinstance(source_skill, dict)
                    and source_skill["name"] == name
                ):
                    source_skill["tree_sha256"] = declaration_hash

    def _write_skill(
        self,
        stage: dict[str, Any],
    ) -> None:
        output_skill = stage["output_skill"]
        skill_root = self.project_root / output_skill["path"]
        source_skill = stage.get("source_skill")
        if isinstance(source_skill, dict):
            source_root = self.source_skill_roots[source_skill["name"]]
            for source_file in source_root.rglob("*"):
                if source_file.is_file():
                    target = skill_root / source_file.relative_to(source_root)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(source_file.read_bytes())
            body = "Use pra2026-bh408 with Qwen3.5, vLLM V1, ROCm/DCU."
        else:
            for relative in output_skill["file_set"]:
                path = skill_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            markers = "\n".join(stage["required_markers"])
            body = (
                "Use pra2026-bh408 with Qwen3.5, vLLM V1, ROCm/DCU.\n"
                "Preserve unresolved bindings through runtime discovery.\n"
                f"{markers}\n"
            )
        (skill_root / "SKILL.md").write_text(
            "---\n"
            f"name: {output_skill['name']}\n"
            "description: Fixture target Skill.\n"
            "---\n\n"
            "# Fixture Skill\n\n"
            f"{body}\n",
            encoding="utf-8",
        )
        (skill_root / "agents" / "openai.yaml").write_text(
            "interface:\n"
            f'  display_name: "{output_skill["name"]}"\n'
            '  short_description: "Fixture target Skill"\n'
            f'  default_prompt: "Use ${output_skill["name"]}."\n',
            encoding="utf-8",
        )
        handoff: dict[str, Any] = {
            "schema_version": 1,
            "stage_id": stage["id"],
            "status": "complete",
            "outputs": {"skill": output_skill["path"]},
        }
        if stage["kind"] == "workflow_gap_skill_generation":
            handoff.update(
                {
                    "authority_type": "workflow_gap",
                    "workflow_authority": stage["workflow_authority"],
                }
            )
        write_json(self.project_root / stage["handoff"], handoff)

    def _write_scheduler_outputs(self) -> None:
        scheduler_stage = self.plan["stages"][-1]
        scheduler = (
            self.project_root / scheduler_stage["runtime_outputs"]["scheduler"]
        )
        scheduler.parent.mkdir(parents=True, exist_ok=True)
        scheduler.write_text(
            "#!/usr/bin/env python3\n"
            "import argparse, json\n"
            "from pathlib import Path\n"
            "class RuntimeScheduler:\n"
            "    def _thread_start_params(self):\n"
            "        return {'ephemeral': False}\n"
            "p=argparse.ArgumentParser()\n"
            "p.add_argument('--project-root', required=True)\n"
            "p.add_argument('--branch', choices=('dispatch','fx'), required=True)\n"
            "p.add_argument('--dry-run', action='store_true')\n"
            "a=p.parse_args()\n"
            "path=Path(a.project_root)/'workload_profile'/'manifests'/"
            "(a.branch+'_pipeline.json')\n"
            "print(json.dumps(json.loads(path.read_text())))\n",
            encoding="utf-8",
        )
        by_stage = {
            stage["id"]: stage
            for stage in self.plan["stages"]
            if isinstance(stage.get("output_skill"), dict)
        }
        outputs = scheduler_stage["runtime_outputs"]
        for branch, entries in scheduler_stage["runtime_branches"].items():
            goals = [entry["id"] for entry in entries]
            bindings = {
                entry["id"]: {
                    "skill": by_stage[entry["stage"]]["output_skill"]["name"]
                }
                for entry in entries
            }
            write_json(
                self.project_root / outputs[branch],
                {
                    "branch": branch,
                    "goals": goals,
                    "bindings": bindings,
                },
            )
        write_json(
            self.project_root / scheduler_stage["handoff"],
            {
                "schema_version": 1,
                "stage_id": "A07",
                "status": "complete",
                "outputs": outputs,
            },
        )

    def _prepare_fixture(self) -> None:
        self._copy_contract_inputs()
        self._prepare_source_skills()
        passing_source_gate = [
            sys.executable,
            "-c",
            "import sys; sys.exit(0)",
            "{source_skill_root}",
        ]
        passing_other_gate = [
            sys.executable,
            "-c",
            "import sys; sys.exit(0)",
        ]
        for stage in self.plan["stages"]:
            if stage["kind"] == "source_skill_text_alignment":
                stage["final_gate"] = passing_source_gate
            else:
                stage["final_gate"] = passing_other_gate
            if isinstance(stage.get("output_skill"), dict):
                self._write_skill(stage)
        self._write_scheduler_outputs()
        write_json(self.plan_path, self.plan)

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment["FAKE_PROJECT_ROOT"] = str(self.project_root)
        environment["FAKE_CODEX_LOG"] = str(self.request_log)
        environment["FAKE_SERVER_STATE"] = str(self.fake_server_state)
        return environment

    def _run_arguments(self) -> list[str]:
        return [
            sys.executable,
            str(ORCHESTRATOR),
            "run",
            "--project-root",
            str(self.project_root),
            "--plan",
            str(self.plan_path),
            "--state-file",
            str(self.state_path),
            "--codex-bin",
            str(FAKE_CODEX),
            "--request-timeout",
            "10",
            "--stage-timeout",
            "30",
            "--progress-interval",
            "0.1",
        ]

    def _run(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self._run_arguments(),
            cwd=self.project_root,
            env=self._environment(),
            text=True,
            capture_output=True,
            timeout=90,
            check=False,
        )

    def _resume(self) -> subprocess.CompletedProcess[str]:
        arguments = self._run_arguments()
        arguments[arguments.index("run")] = "resume"
        return subprocess.run(
            arguments,
            cwd=self.project_root,
            env=self._environment(),
            text=True,
            capture_output=True,
            timeout=90,
            check=False,
        )

    def _requests(self) -> list[dict[str, Any]]:
        return [
            json.loads(line)
            for line in self.request_log.read_text(encoding="utf-8").splitlines()
        ]

    def test_dry_run_reports_complete_control_plane_without_state(self) -> None:
        default_state = self.adaptation_root / "state" / STATE_NAME
        completed = subprocess.run(
            [
                sys.executable,
                str(ORCHESTRATOR),
                "run",
                "--project-root",
                str(self.project_root),
                "--plan",
                str(self.plan_path),
                "--codex-bin",
                str(FAKE_CODEX),
                "--dry-run",
            ],
            cwd=self.project_root,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["state_file"].endswith(STATE_NAME))
        self.assertEqual(payload["orchestration_protocol"], PROTOCOL)
        self.assertEqual(payload["goal_token_budget_policy"], "unset")
        self.assertEqual(
            [stage["id"] for stage in payload["stages"]],
            list(STAGE_ORDER),
        )
        self.assertEqual(
            [stage["kind"] for stage in payload["stages"]].count(
                "workflow_gap_skill_generation"
            ),
            4,
        )
        self.assertFalse(default_state.exists())
        self.assertFalse(self.request_log.exists())

    def test_serializes_ten_skill_stages_then_scheduler(self) -> None:
        completed = self._run()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "COMPLETE")
        self.assertEqual(state["schema_version"], 7)
        self.assertEqual(
            [state["stages"][stage]["status"] for stage in STAGE_ORDER],
            ["COMMITTED"] * len(STAGE_ORDER),
        )
        requests = self._requests()
        goals = [
            item
            for item in requests
            if item.get("method") == "thread/goal/set"
            and item.get("params", {}).get("objective")
        ]
        turns = [
            item for item in requests if item.get("method") == "turn/start"
        ]
        self.assertEqual(len(goals), len(STAGE_ORDER))
        self.assertEqual(len(turns), len(STAGE_ORDER))
        self.assertTrue(
            all("tokenBudget" not in item["params"] for item in goals)
        )
        for stage, turn in zip(self.plan["stages"], turns):
            skill_items = [
                item["name"]
                for item in turn["params"]["input"]
                if item.get("type") == "skill"
            ]
            source_skill = stage.get("source_skill")
            expected = (
                [source_skill["name"]]
                if isinstance(source_skill, dict)
                else []
            )
            self.assertEqual(skill_items, expected)

    def test_final_gate_failure_resumes_without_recreating_a00(self) -> None:
        marker = self.project_root / "allow-a00-final"
        self.plan["stages"][0]["final_gate"] = [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; import sys; "
                f"sys.exit(0 if Path({str(marker)!r}).exists() else 9)"
            ),
        ]
        write_json(self.plan_path, self.plan)
        first = self._run()
        self.assertNotEqual(first.returncode, 0)
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["stages"]["A00"]["status"], "GATE_FAILED")
        self.assertEqual(state["stages"]["A00"]["goal"]["status"], "complete")
        self.assertEqual(state["stages"]["A01"]["status"], "NOT_STARTED")
        marker.touch()
        resumed = self._resume()
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        created = [
            item
            for item in self._requests()
            if item.get("method") == "thread/goal/set"
            and item.get("params", {}).get("objective")
        ]
        self.assertEqual(len(created), len(STAGE_ORDER))
        self.assertEqual(
            sum(
                "完成 A00" in item["params"]["objective"]
                for item in created
            ),
            1,
        )

    def _run_verifier(
        self,
        stage_id: str,
    ) -> subprocess.CompletedProcess[str]:
        stage = next(
            item for item in self.plan["stages"] if item["id"] == stage_id
        )
        arguments = [
            sys.executable,
            str(VERIFIER),
            "--project-root",
            str(self.project_root),
            "--plan",
            str(self.plan_path),
            "--stage",
            stage_id,
        ]
        source_skill = stage.get("source_skill")
        if isinstance(source_skill, dict):
            arguments.extend(
                [
                    "--source-skill-root",
                    str(self.source_skill_roots[source_skill["name"]]),
                ]
            )
        return subprocess.run(
            arguments,
            cwd=self.project_root,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

    def test_verifier_accepts_source_gap_and_scheduler_stages(self) -> None:
        expected_gates = {
            "A01": "source-skill-mirror-alignment",
            "A033": "workflow-gap-skill-synthesis",
            "A07": "runtime-scheduler-generation",
        }
        for stage_id, expected_gate in expected_gates.items():
            with self.subTest(stage_id=stage_id):
                completed = self._run_verifier(stage_id)
                self.assertEqual(
                    completed.returncode,
                    0,
                    completed.stdout + completed.stderr,
                )
                self.assertEqual(
                    json.loads(completed.stdout)["gate"],
                    expected_gate,
                )

    def test_gap_verifier_rejects_undeclared_extra_file(self) -> None:
        stage = next(
            item for item in self.plan["stages"] if item["id"] == "A033"
        )
        extra = (
            self.project_root
            / stage["output_skill"]["path"]
            / "references"
            / "goal-spec.md"
        )
        extra.parent.mkdir(parents=True)
        extra.write_text("# obsolete parallel contract\n", encoding="utf-8")
        completed = self._run_verifier("A033")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("file set must be", completed.stdout)

    def test_scheduler_verifier_rejects_parallel_goal_spec_binding(self) -> None:
        scheduler_stage = self.plan["stages"][-1]
        dispatch_path = (
            self.project_root
            / scheduler_stage["runtime_outputs"]["dispatch"]
        )
        payload = json.loads(dispatch_path.read_text(encoding="utf-8"))
        first_goal = payload["goals"][0]
        payload["bindings"][first_goal]["goal_spec"] = "forbidden.md"
        write_json(dispatch_path, payload)
        completed = self._run_verifier("A07")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("binding must contain only skill", completed.stdout)

    def test_plan_rejects_handoff_outside_workload_profile(self) -> None:
        self.plan["stages"][0]["handoff"] = "escaped-handoff.json"
        write_json(self.plan_path, self.plan)
        completed = subprocess.run(
            [
                sys.executable,
                str(ORCHESTRATOR),
                "run",
                "--project-root",
                str(self.project_root),
                "--plan",
                str(self.plan_path),
                "--codex-bin",
                str(FAKE_CODEX),
                "--dry-run",
            ],
            cwd=self.project_root,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("escapes workload_profile root", completed.stderr)


if __name__ == "__main__":
    unittest.main()
