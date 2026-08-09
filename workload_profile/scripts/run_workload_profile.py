#!/usr/bin/env python3
"""Run one serial workload-profile Goal branch through Codex app-server."""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_PIPELINES = {
    "dispatch": ["R01", "R02", "R031", "R041"],
    "fx": ["R01", "R02", "R032", "R042"],
}
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
STOP_GOAL_STATUSES = {
    "blocked",
    "usageLimited",
    "budgetLimited",
    "paused",
    "failed",
    "interrupted",
    "cancelled",
}
APPROVAL_POLICY = "never"


class SchedulerError(RuntimeError):
    """A deterministic runtime-scheduling failure."""


class RpcError(SchedulerError):
    """A Codex app-server request or transport failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SchedulerError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SchedulerError(f"invalid JSON file {path}: {exc}") from exc


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def ensure_within(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise SchedulerError(f"{label} escapes {root}: {path}") from exc
    return resolved


def validate_manifest(
    project_root: Path,
    branch: str,
    payload: Any,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SchedulerError("pipeline manifest must be a JSON object")
    if set(payload) != {"branch", "goals", "bindings"}:
        raise SchedulerError(
            "pipeline manifest must contain only branch, goals, and bindings"
        )
    if payload.get("branch") != branch:
        raise SchedulerError(
            f"manifest branch is {payload.get('branch')!r}, expected {branch!r}"
        )
    goals = payload.get("goals")
    expected = EXPECTED_PIPELINES[branch]
    if goals != expected:
        raise SchedulerError(
            f"{branch} goals must be {expected}; received {goals!r}"
        )
    bindings = payload.get("bindings")
    if not isinstance(bindings, dict) or set(bindings) != set(expected):
        raise SchedulerError(
            f"{branch} bindings must have exactly these keys: {expected}"
        )
    for goal_id in expected:
        binding = bindings.get(goal_id)
        if not isinstance(binding, dict) or set(binding) != {"skill"}:
            raise SchedulerError(
                f"{goal_id} binding must contain only a skill name"
            )
        skill = binding.get("skill")
        if not isinstance(skill, str) or not SKILL_NAME_RE.fullmatch(skill):
            raise SchedulerError(f"{goal_id} has invalid Skill name {skill!r}")
        skill_file = (
            project_root / "workload_profile" / "skills" / skill / "SKILL.md"
        )
        if not skill_file.is_file():
            raise SchedulerError(f"{goal_id} Skill is missing: {skill_file}")
    return payload


def load_user_parameters(args: argparse.Namespace) -> dict[str, Any]:
    parameters: dict[str, Any] = {}
    if args.params_file is not None:
        loaded = load_json(args.params_file.resolve())
        if not isinstance(loaded, dict):
            raise SchedulerError("--params-file must contain a JSON object")
        parameters.update(loaded)
    for item in args.param:
        if "=" not in item:
            raise SchedulerError(f"--param must use KEY=VALUE: {item!r}")
        key, raw_value = item.split("=", 1)
        if not key:
            raise SchedulerError("--param key must not be empty")
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            value = raw_value
        parameters[key] = value
    return parameters


class AppServerClient:
    """Minimal concurrent JSONL client for one Codex app-server process."""

    def __init__(
        self,
        codex_bin: str,
        cwd: Path,
        raw_log_path: Path,
        stderr_log_path: Path,
        request_timeout: float,
    ) -> None:
        self.codex_bin = codex_bin
        self.cwd = cwd
        self.raw_log_path = raw_log_path
        self.stderr_log_path = stderr_log_path
        self.request_timeout = request_timeout
        self.process: subprocess.Popen[str] | None = None
        self.notifications: queue.Queue[dict[str, Any]] = queue.Queue()
        self.reader_errors: queue.Queue[str] = queue.Queue()
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._next_id = 1
        self._raw_log: Any = None
        self._stderr_log: Any = None
        self._reader_thread: threading.Thread | None = None

    def start(self) -> None:
        self.raw_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._raw_log = self.raw_log_path.open("a", encoding="utf-8")
        self._stderr_log = self.stderr_log_path.open("a", encoding="utf-8")
        try:
            self.process = subprocess.Popen(
                [self.codex_bin, "app-server", "--listen", "stdio://"],
                cwd=self.cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._stderr_log,
                text=True,
                bufsize=1,
            )
        except OSError:
            self._raw_log.close()
            self._stderr_log.close()
            raise
        self._reader_thread = threading.Thread(
            target=self._read_stdout,
            name="workload-profile-app-server-reader",
            daemon=True,
        )
        self._reader_thread.start()

    def _log(self, direction: str, message: Any) -> None:
        if self._raw_log is None:
            return
        record = {
            "observed_at": utc_now(),
            "direction": direction,
            "message": message,
        }
        with self._log_lock:
            self._raw_log.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._raw_log.flush()

    def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        for line in self.process.stdout:
            stripped = line.rstrip("\n")
            try:
                message = json.loads(stripped)
            except json.JSONDecodeError as exc:
                self._log("server-invalid-json", stripped)
                self.reader_errors.put(
                    f"invalid app-server JSON: {exc}: {stripped}"
                )
                continue
            self._log("server", message)
            if not isinstance(message, dict):
                self.reader_errors.put(
                    f"app-server message is not an object: {message!r}"
                )
                continue
            if "id" in message and ("result" in message or "error" in message):
                with self._pending_lock:
                    waiter = self._pending.get(message["id"])
                if waiter is None:
                    self.reader_errors.put(
                        f"response for unknown request id {message.get('id')}"
                    )
                else:
                    waiter.put(message)
            elif "id" in message and "method" in message:
                self._reject_server_request(message)
                self.reader_errors.put(
                    "app-server requested interactive action "
                    f"{message.get('method')}"
                )
            else:
                self.notifications.put(message)
        self.reader_errors.put("app-server stdout closed")

    def _write(self, message: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise RpcError("app-server is not running")
        if self.process.poll() is not None:
            raise RpcError(f"app-server exited with code {self.process.returncode}")
        encoded = json.dumps(message, ensure_ascii=False)
        self._log("client", message)
        with self._write_lock:
            self.process.stdin.write(encoded + "\n")
            self.process.stdin.flush()

    def _reject_server_request(self, message: dict[str, Any]) -> None:
        try:
            self._write(
                {
                    "id": message["id"],
                    "error": {
                        "code": -32000,
                        "message": (
                            "The non-interactive runtime scheduler cannot "
                            f"answer {message.get('method')}"
                        ),
                    },
                }
            )
        except RpcError as exc:
            self.reader_errors.put(str(exc))

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        self.check_health()
        with self._pending_lock:
            request_id = self._next_id
            self._next_id += 1
            waiter: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self._pending[request_id] = waiter
        message: dict[str, Any] = {"method": method, "id": request_id}
        if params is not None:
            message["params"] = params
        self._write(message)
        try:
            response = waiter.get(timeout=timeout or self.request_timeout)
        except queue.Empty as exc:
            raise RpcError(f"timeout waiting for {method} response") from exc
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)
        if "error" in response:
            raise RpcError(f"{method} failed: {response['error']}")
        return response.get("result")

    def notify(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = params
        self._write(message)

    def initialize(self) -> None:
        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "qwen_dcu_workload_profile_runtime",
                    "title": "Qwen DCU Workload Profile Runtime",
                    "version": "1.0.0",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        self.notify("initialized", {})

    def check_health(self) -> None:
        if not self.reader_errors.empty():
            raise RpcError(self.reader_errors.get_nowait())
        if self.process is not None and self.process.poll() is not None:
            raise RpcError(f"app-server exited with code {self.process.returncode}")

    def close(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            try:
                if process.stdin is not None:
                    process.stdin.close()
            except OSError:
                pass
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1)
        if self._raw_log is not None:
            self._raw_log.close()
        if self._stderr_log is not None:
            self._stderr_log.close()


class RuntimeScheduler:
    """Create and wait for one independent Goal per manifest stage."""

    def __init__(
        self,
        project_root: Path,
        branch: str,
        manifest: dict[str, Any],
        user_parameters: dict[str, Any],
        run_id: str,
        codex_bin: str,
        model: str | None,
        sandbox_policy: str,
        network_access: bool,
        request_timeout: float,
        poll_interval: float,
    ) -> None:
        self.project_root = project_root
        self.workload_root = project_root / "workload_profile"
        self.branch = branch
        self.manifest = manifest
        self.user_parameters = user_parameters
        self.run_id = run_id
        self.codex_bin = codex_bin
        self.model = model
        self.sandbox_policy = sandbox_policy
        self.network_access = network_access
        self.request_timeout = request_timeout
        self.poll_interval = poll_interval
        self.run_dir = ensure_within(
            self.workload_root / "runtime" / run_id,
            self.workload_root,
            "runtime directory",
        )
        self.handoff_dir = self.run_dir / "handoffs"
        self.state_path = self.run_dir / "state.json"
        self.state: dict[str, Any] = {}
        self.client: AppServerClient | None = None
        self.current_goal_id: str | None = None

    def _thread_start_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "cwd": str(self.project_root),
            "approvalPolicy": APPROVAL_POLICY,
            "sandbox": self.sandbox_policy,
            "ephemeral": False,
        }
        if self.model:
            params["model"] = self.model
        return params

    def _turn_overrides(self) -> dict[str, Any]:
        if self.sandbox_policy == "danger-full-access":
            sandbox: dict[str, Any] = {"type": "dangerFullAccess"}
        else:
            sandbox = {
                "type": "workspaceWrite",
                "writableRoots": [str(self.project_root)],
                "networkAccess": self.network_access,
            }
        params: dict[str, Any] = {
            "cwd": str(self.project_root),
            "approvalPolicy": APPROVAL_POLICY,
            "sandboxPolicy": sandbox,
            "effort": "max",
            "summary": "concise",
        }
        if self.model:
            params["model"] = self.model
        return params

    def _checkpoint(self) -> None:
        self.state["updated_at"] = utc_now()
        atomic_write_json(self.state_path, self.state)

    def _stage_record(self, goal_id: str) -> dict[str, Any]:
        return self.state["stages"][goal_id]

    def _set_stage_status(
        self,
        goal_id: str,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        record = self._stage_record(goal_id)
        record["status"] = status
        record["updated_at"] = utc_now()
        if error is not None:
            record["error"] = error
        self._checkpoint()

    def _runtime_prompt(
        self,
        goal_id: str,
        skill: str,
        output_handoff: Path,
        previous_handoff: dict[str, Any] | None,
    ) -> str:
        runtime_parameters = {
            "project_root": str(self.project_root),
            "branch": self.branch,
            "run_id": self.run_id,
            "runtime_goal": goal_id,
            "runtime_handoff_output": str(output_handoff),
            "user": self.user_parameters,
        }
        return "\n".join(
            [
                f"${skill}",
                "",
                f"你现在只执行运行 Goal {goal_id}。",
                (
                    f"已附加的 {skill} Skill 是本 Goal 的完整目标约束；"
                    "严格遵循其方法、顺序、验证、错误边界和完成条件。"
                ),
                "运行参数：",
                json.dumps(runtime_parameters, ensure_ascii=False, indent=2),
                "前序 runtime handoff：",
                json.dumps(previous_handoff, ensure_ascii=False, indent=2),
                (
                    "只使用这一个已附加 Skill。成功时把本 Goal 的 runtime "
                    "handoff 写到运行参数指定的绝对路径；该 JSON 必须索引"
                    "本次真实产物和证据，使下一串行 Goal 可以按原样消费。"
                ),
                (
                    "只有完成 Skill 的全部完成条件且 runtime handoff 已写入"
                    "后，才把当前 Goal 标记为 complete；受阻时如实使用 Goal "
                    "终态并停止。"
                ),
            ]
        )

    def _get_goal(self, thread_id: str) -> dict[str, Any] | None:
        assert self.client is not None
        result = self.client.request("thread/goal/get", {"threadId": thread_id})
        goal = result.get("goal")
        return goal if isinstance(goal, dict) else None

    def _thread(self, thread_id: str) -> dict[str, Any]:
        assert self.client is not None
        result = self.client.request(
            "thread/read",
            {"threadId": thread_id, "includeTurns": True},
        )
        thread = result.get("thread")
        if not isinstance(thread, dict):
            raise SchedulerError(f"thread/read returned no thread for {thread_id}")
        return thread

    @staticmethod
    def _thread_status(thread: dict[str, Any]) -> str | None:
        status = thread.get("status")
        if isinstance(status, dict):
            value = status.get("type")
            return value if isinstance(value, str) else None
        return status if isinstance(status, str) else None

    def _drain_notifications(self, thread_id: str) -> None:
        assert self.client is not None
        self.client.check_health()
        while True:
            try:
                message = self.client.notifications.get_nowait()
            except queue.Empty:
                return
            params = message.get("params")
            if not isinstance(params, dict):
                continue
            observed_thread = params.get("threadId")
            if observed_thread not in (None, thread_id):
                continue
            method = message.get("method")
            if method == "turn/completed":
                turn = params.get("turn")
                if isinstance(turn, dict) and turn.get("status") in {
                    "failed",
                    "interrupted",
                }:
                    raise SchedulerError(
                        f"Turn {turn.get('id')} ended with {turn.get('status')}"
                    )

    def _wait_for_initial_turn(
        self,
        thread_id: str,
        turn_id: str,
        timeout: float = 30.0,
    ) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._drain_notifications(thread_id)
            thread = self._thread(thread_id)
            for turn in thread.get("turns", []):
                if not isinstance(turn, dict) or turn.get("id") != turn_id:
                    continue
                if turn.get("status") in {"failed", "interrupted"}:
                    raise SchedulerError(
                        f"initial Turn {turn_id} ended with {turn.get('status')}"
                    )
                return
            time.sleep(0.1)
        raise SchedulerError(f"initial Turn {turn_id} was not observable")

    def _wait_for_goal(self, goal_id: str, thread_id: str) -> dict[str, Any]:
        assert self.client is not None
        while True:
            self._drain_notifications(thread_id)
            goal = self._get_goal(thread_id)
            if goal is None:
                raise SchedulerError(f"{goal_id}: Goal disappeared")
            self._stage_record(goal_id)["goal"] = goal
            self._checkpoint()
            status = goal.get("status")
            if status == "complete":
                return goal
            if status in STOP_GOAL_STATUSES:
                raise SchedulerError(f"{goal_id}: Goal reached stop status {status}")
            if status != "active":
                raise SchedulerError(
                    f"{goal_id}: unexpected Goal status {status!r}"
                )
            time.sleep(self.poll_interval)

    def _wait_until_idle(self, thread_id: str) -> None:
        while True:
            self._drain_notifications(thread_id)
            thread = self._thread(thread_id)
            active_turns = [
                turn
                for turn in thread.get("turns", [])
                if isinstance(turn, dict) and turn.get("status") == "inProgress"
            ]
            if self._thread_status(thread) == "idle" and not active_turns:
                return
            time.sleep(min(self.poll_interval, 1.0))

    def _stop_current_goal(self) -> None:
        if self.client is None or self.current_goal_id is None:
            return
        record = self._stage_record(self.current_goal_id)
        thread_id = record.get("thread_id")
        if not isinstance(thread_id, str):
            return
        try:
            goal = self._get_goal(thread_id)
            if isinstance(goal, dict) and goal.get("status") == "active":
                self.client.request(
                    "thread/goal/set",
                    {"threadId": thread_id, "status": "paused"},
                    timeout=30,
                )
            thread = self._thread(thread_id)
            for turn in thread.get("turns", []):
                if not isinstance(turn, dict) or turn.get("status") != "inProgress":
                    continue
                turn_id = turn.get("id")
                if isinstance(turn_id, str):
                    self.client.request(
                        "turn/interrupt",
                        {"threadId": thread_id, "turnId": turn_id},
                        timeout=30,
                    )
        except SchedulerError:
            return

    def _read_handoff(self, goal_id: str, path: Path) -> dict[str, Any]:
        payload = load_json(path)
        if not isinstance(payload, dict) or not payload:
            raise SchedulerError(
                f"{goal_id}: runtime handoff must be a non-empty JSON object: {path}"
            )
        return {
            "source_goal": goal_id,
            "path": str(path),
            "payload": payload,
        }

    def _execute_goal(
        self,
        goal_id: str,
        skill: str,
        previous_handoff: dict[str, Any] | None,
    ) -> dict[str, Any]:
        assert self.client is not None
        self.current_goal_id = goal_id
        record = self._stage_record(goal_id)
        handoff_path = self.handoff_dir / f"{goal_id}.json"
        if handoff_path.exists():
            raise SchedulerError(
                f"{goal_id}: refusing to reuse runtime handoff {handoff_path}"
            )

        thread_result = self.client.request(
            "thread/start",
            self._thread_start_params(),
        )
        thread_id = thread_result.get("thread", {}).get("id")
        if not isinstance(thread_id, str):
            raise SchedulerError(f"{goal_id}: thread/start returned no id")
        record["thread_id"] = thread_id
        self._set_stage_status(goal_id, "thread_created")

        objective = f"Execute runtime Goal {goal_id} with attached Skill {skill}"
        goal_result = self.client.request(
            "thread/goal/set",
            {
                "threadId": thread_id,
                "objective": objective,
                "status": "paused",
            },
        )
        record["goal"] = goal_result.get("goal")
        self._checkpoint()

        skill_path = (
            self.workload_root / "skills" / skill / "SKILL.md"
        ).resolve()
        prompt = self._runtime_prompt(
            goal_id,
            skill,
            handoff_path,
            previous_handoff,
        )
        turn_result = self.client.request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": [
                    {"type": "text", "text": prompt},
                    {"type": "skill", "name": skill, "path": str(skill_path)},
                ],
                **self._turn_overrides(),
            },
        )
        turn_id = turn_result.get("turn", {}).get("id")
        if not isinstance(turn_id, str):
            raise SchedulerError(f"{goal_id}: turn/start returned no Turn id")
        record["initial_turn_id"] = turn_id
        self._set_stage_status(goal_id, "running")
        self._wait_for_initial_turn(thread_id, turn_id)

        goal = self._get_goal(thread_id)
        if goal is None:
            raise SchedulerError(f"{goal_id}: Goal disappeared after initial Turn")
        status = goal.get("status")
        if status == "paused":
            result = self.client.request(
                "thread/goal/set",
                {"threadId": thread_id, "status": "active"},
            )
            record["goal"] = result.get("goal")
            self._checkpoint()
        elif status == "complete":
            record["goal"] = goal
            self._checkpoint()
        elif status in STOP_GOAL_STATUSES:
            raise SchedulerError(f"{goal_id}: Goal reached stop status {status}")
        elif status != "active":
            raise SchedulerError(
                f"{goal_id}: unexpected Goal status after initial Turn: {status!r}"
            )

        goal = self._wait_for_goal(goal_id, thread_id)
        self._wait_until_idle(thread_id)
        record["goal"] = goal
        handoff = self._read_handoff(goal_id, handoff_path)
        record["runtime_handoff"] = str(
            handoff_path.relative_to(self.project_root)
        )
        self._set_stage_status(goal_id, "complete")
        self.current_goal_id = None
        return handoff

    def run(self) -> dict[str, Any]:
        if self.run_dir.exists():
            raise SchedulerError(
                f"runtime directory already exists; choose another --run-id: "
                f"{self.run_dir}"
            )
        self.handoff_dir.mkdir(parents=True)
        goals = self.manifest["goals"]
        self.state = {
            "schema_version": 1,
            "run_id": self.run_id,
            "branch": self.branch,
            "status": "running",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "user_parameters": self.user_parameters,
            "stages": {
                goal_id: {
                    "skill": self.manifest["bindings"][goal_id]["skill"],
                    "status": "pending",
                }
                for goal_id in goals
            },
        }
        self._checkpoint()
        self.client = AppServerClient(
            codex_bin=self.codex_bin,
            cwd=self.project_root,
            raw_log_path=self.run_dir / "app_server.jsonl",
            stderr_log_path=self.run_dir / "app_server.stderr.log",
            request_timeout=self.request_timeout,
        )
        try:
            self.client.start()
            self.client.initialize()
            previous_handoff: dict[str, Any] | None = None
            for goal_id in goals:
                skill = self.manifest["bindings"][goal_id]["skill"]
                print(
                    f"[{self.branch}] starting {goal_id} with {skill}",
                    file=sys.stderr,
                    flush=True,
                )
                previous_handoff = self._execute_goal(
                    goal_id,
                    skill,
                    previous_handoff,
                )
            self.state["status"] = "complete"
            self.state["completed_at"] = utc_now()
            self._checkpoint()
            return {
                "status": "complete",
                "branch": self.branch,
                "run_id": self.run_id,
                "goals": goals,
                "state": str(self.state_path.relative_to(self.project_root)),
            }
        except KeyboardInterrupt:
            self._stop_current_goal()
            self.state["status"] = "interrupted"
            self.state["error"] = "operator interruption"
            self._checkpoint()
            raise
        except Exception as exc:
            self._stop_current_goal()
            if self.current_goal_id is not None:
                self._set_stage_status(
                    self.current_goal_id,
                    "stopped",
                    error=str(exc),
                )
            self.state["status"] = "stopped"
            self.state["error"] = str(exc)
            self._checkpoint()
            raise
        finally:
            if self.client is not None:
                self.client.close()


def default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_run_id(branch: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{branch}-{uuid.uuid4().hex[:8]}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Dispatch or FX workload-profile branch as four serial "
            "Codex Goals, each constrained by one adapted Skill."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=default_project_root(),
        help="Project root (default: inferred from this script).",
    )
    parser.add_argument(
        "--branch",
        choices=tuple(EXPECTED_PIPELINES),
        required=True,
        help="Serial Goal branch to run.",
    )
    parser.add_argument(
        "--params-file",
        type=Path,
        help="JSON object containing user runtime parameters.",
    )
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Add or override one user runtime parameter; VALUE is decoded as "
            "JSON when possible. May be repeated."
        ),
    )
    parser.add_argument(
        "--run-id",
        help="Unique runtime id; outputs stay under workload_profile/runtime/.",
    )
    parser.add_argument(
        "--codex-bin",
        default=shutil.which("codex") or "codex",
        help="Codex executable (default: codex from PATH).",
    )
    parser.add_argument(
        "--model",
        help="Optional Codex model override; the configured default is used otherwise.",
    )
    parser.add_argument(
        "--sandbox-policy",
        choices=("danger-full-access", "workspace-write"),
        default="danger-full-access",
    )
    parser.add_argument(
        "--network-access",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Allow network access with workspace-write (default: true).",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=120.0,
        help="Seconds to wait for one app-server RPC response.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds between Goal status polls.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the selected Goal order without creating Goals.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        project_root = args.project_root.resolve()
        if not project_root.is_dir():
            raise SchedulerError(f"project root is not a directory: {project_root}")
        workload_root = project_root / "workload_profile"
        if not workload_root.is_dir():
            raise SchedulerError(f"workload_profile is missing: {workload_root}")
        manifest_path = (
            workload_root / "manifests" / f"{args.branch}_pipeline.json"
        )
        manifest = validate_manifest(
            project_root,
            args.branch,
            load_json(manifest_path),
        )
        user_parameters = load_user_parameters(args)
        if args.request_timeout <= 0:
            raise SchedulerError("--request-timeout must be positive")
        if args.poll_interval <= 0:
            raise SchedulerError("--poll-interval must be positive")
        if args.dry_run:
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            return 0
        run_id = args.run_id or default_run_id(args.branch)
        if not RUN_ID_RE.fullmatch(run_id):
            raise SchedulerError(
                "--run-id must start with an alphanumeric character and contain "
                "only letters, digits, dot, underscore, or hyphen"
            )
        scheduler = RuntimeScheduler(
            project_root=project_root,
            branch=args.branch,
            manifest=manifest,
            user_parameters=user_parameters,
            run_id=run_id,
            codex_bin=args.codex_bin,
            model=args.model,
            sandbox_policy=args.sandbox_policy,
            network_access=args.network_access,
            request_timeout=args.request_timeout,
            poll_interval=args.poll_interval,
        )
        result = scheduler.run()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        print("runtime scheduling interrupted", file=sys.stderr)
        return 130
    except (SchedulerError, OSError) as exc:
        print(f"runtime scheduling failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
