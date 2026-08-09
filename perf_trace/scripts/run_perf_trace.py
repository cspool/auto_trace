#!/usr/bin/env python3
"""Run the Qwen/DCU core-attribution Skills as five serial Codex Goals."""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BRANCH = "core-attribution"
GOAL_IDS = ("R01", "R02", "R03", "R04", "R05")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
BINDINGS = {
    "R01": {"skill": "qwen-dcu-same-input-layer-wise-workflow"},
    "R02": {"skill": "qwen-dcu-fx-process-nvtx-instrumentation"},
    "R03": {"skill": "qwen-dcu-process-performance-breakdown"},
    "R04": {"skill": "qwen-dcu-process-gpu-hardware-trace"},
    "R05": {"skill": "qwen-dcu-segmented-process-attribution"},
}
EXPECTED_MANIFEST = {
    "schema_version": 1,
    "branch": BRANCH,
    "goals": list(GOAL_IDS),
    "bindings": BINDINGS,
}
TERMINAL_GOAL_STATUSES = {
    "blocked",
    "usageLimited",
    "budgetLimited",
    "failed",
    "interrupted",
    "cancelled",
    "complete",
}
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
SANDBOX_POLICY = "danger-full-access"
TURN_SANDBOX_POLICY = {"type": "dangerFullAccess"}


class SchedulerError(RuntimeError):
    """A deterministic runtime scheduling failure."""


class RpcError(SchedulerError):
    """An app-server JSON-RPC failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{secrets.token_hex(4)}"


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    )
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise SchedulerError(f"required JSON file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SchedulerError(f"invalid JSON in {path}: {exc}") from exc


def require_under(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise SchedulerError(f"path escapes the project root: {resolved}") from exc
    return resolved


def parse_user_parameters(
    inline_value: str,
    file_value: str | None,
) -> dict[str, Any]:
    if file_value:
        source = Path(file_value).expanduser().resolve()
        payload = load_json(source)
    else:
        try:
            payload = json.loads(inline_value)
        except json.JSONDecodeError as exc:
            raise SchedulerError(
                f"--user-parameters must be a JSON object: {exc}"
            ) from exc
    if not isinstance(payload, dict):
        raise SchedulerError("user parameters must be a JSON object")
    return payload


def resolve_codex_binary(value: str | None) -> Path:
    if value is None:
        discovered = shutil.which("codex")
        if discovered is None:
            raise SchedulerError(
                "Codex executable was not found; pass --codex-bin at runtime"
            )
        candidate = Path(discovered)
    elif "/" in value:
        candidate = Path(value).expanduser()
    else:
        discovered = shutil.which(value)
        if discovered is None:
            raise SchedulerError(f"Codex executable was not found: {value}")
        candidate = Path(discovered)
    resolved = candidate.resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise SchedulerError(f"Codex executable is not runnable: {resolved}")
    return resolved


class AppServerClient:
    """Thread-safe JSONL client for one Codex app-server process."""

    def __init__(
        self,
        *,
        codex_bin: Path,
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
        self.server_requests: queue.Queue[dict[str, Any]] = queue.Queue()
        self.reader_errors: queue.Queue[str] = queue.Queue()
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._next_id = 1
        self._raw_log: Any = None
        self._stderr_log: Any = None
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        self.raw_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.stderr_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._raw_log = self.raw_log_path.open("a", encoding="utf-8")
        self._stderr_log = self.stderr_log_path.open("a", encoding="utf-8")
        self.process = subprocess.Popen(
            [str(self.codex_bin), "app-server", "--listen", "stdio://"],
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        stdout_thread = threading.Thread(
            target=self._read_stdout,
            name="perf-trace-app-server-stdout",
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._read_stderr,
            name="perf-trace-app-server-stderr",
            daemon=True,
        )
        self._threads = [stdout_thread, stderr_thread]
        for thread in self._threads:
            thread.start()

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
            if not stripped:
                continue
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
                self.server_requests.put(message)
                self._reject_server_request(message)
            else:
                self.notifications.put(message)
        self.reader_errors.put(
            f"app-server stdout closed with exit code "
            f"{self.process.returncode}"
        )

    def _read_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        for line in self.process.stderr:
            if self._stderr_log is not None:
                self._stderr_log.write(f"{utc_now()} {line}")
                self._stderr_log.flush()

    def _write(self, message: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise RpcError("app-server is not running")
        if self.process.poll() is not None:
            raise RpcError(
                f"app-server exited with code {self.process.returncode}"
            )
        encoded = json.dumps(message, ensure_ascii=False)
        self._log("client", message)
        with self._write_lock:
            self.process.stdin.write(encoded + "\n")
            self.process.stdin.flush()

    def _reject_server_request(self, message: dict[str, Any]) -> None:
        response = {
            "id": message["id"],
            "error": {
                "code": -32000,
                "message": (
                    "The non-interactive perf-trace scheduler cannot answer "
                    f"server request {message.get('method')}"
                ),
            },
        }
        try:
            self._write(response)
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

    def check_health(self) -> None:
        if not self.reader_errors.empty():
            raise RpcError(self.reader_errors.get_nowait())
        if self.process is not None and self.process.poll() is not None:
            raise RpcError(
                f"app-server exited with code {self.process.returncode}"
            )

    def notify(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = params
        self._write(message)

    def initialize(self) -> Any:
        result = self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "qwen_dcu_perf_trace_runtime",
                    "title": "Qwen DCU Perf Trace Runtime",
                    "version": "1.0.0",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        self.notify("initialized", {})
        return result

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
        for thread in self._threads:
            thread.join(timeout=1)
        if self._raw_log is not None:
            self._raw_log.close()
        if self._stderr_log is not None:
            self._stderr_log.close()


class RuntimeScheduler:
    """Run one persistent-thread Goal at a time in manifest order."""

    def __init__(
        self,
        *,
        project_root: Path,
        manifest_path: Path,
        manifest: dict[str, Any],
        user_parameters: dict[str, Any],
        codex_bin: Path,
        model: str | None,
        run_id: str,
        poll_seconds: float,
        request_timeout: float,
        goal_timeout_seconds: float,
        idle_timeout_seconds: float,
    ) -> None:
        self.project_root = project_root
        self.manifest_path = manifest_path
        self.manifest = manifest
        self.user_parameters = user_parameters
        self.codex_bin = codex_bin
        self.model = model
        self.run_id = run_id
        self.poll_seconds = poll_seconds
        self.request_timeout = request_timeout
        self.goal_timeout_seconds = goal_timeout_seconds
        self.idle_timeout_seconds = idle_timeout_seconds
        runtime_root = require_under(
            project_root / "perf_trace" / "runtime" / BRANCH,
            project_root,
        )
        self.run_dir = runtime_root / run_id
        self.handoff_dir = self.run_dir / "handoffs"
        self.state_path = self.run_dir / "state.json"
        self.ledger_path = self.run_dir / "runtime_handoff_ledger.json"
        self.client: AppServerClient | None = None
        self.current_goal_id: str | None = None
        self.state: dict[str, Any] = {}
        self.ledger: dict[str, Any] = {}

    def _thread_start_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "cwd": str(self.project_root),
            "approvalPolicy": APPROVAL_POLICY,
            "sandbox": SANDBOX_POLICY,
            "ephemeral": False,
        }
        if self.model:
            params["model"] = self.model
        return params

    def _turn_overrides(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "cwd": str(self.project_root),
            "approvalPolicy": APPROVAL_POLICY,
            "sandboxPolicy": TURN_SANDBOX_POLICY,
            "effort": "max",
            "summary": "concise",
        }
        if self.model:
            params["model"] = self.model
        return params

    def _skill_md(self, goal_id: str) -> Path:
        skill_name = self.manifest["bindings"][goal_id]["skill"]
        path = require_under(
            self.project_root
            / "perf_trace"
            / "skills"
            / skill_name
            / "SKILL.md",
            self.project_root,
        )
        if not path.is_file():
            raise SchedulerError(f"runtime Skill is missing: {path}")
        return path

    def _prompt(
        self,
        goal_id: str,
        output_handoff: Path,
        artifact_root: Path,
    ) -> str:
        skill_name = self.manifest["bindings"][goal_id]["skill"]
        runtime_parameters = {
            "project_root": str(self.project_root),
            "branch": BRANCH,
            "run_id": self.run_id,
            "runtime_goal": goal_id,
            "runtime_root": str(self.run_dir),
            "runtime_artifact_root": str(artifact_root),
            "runtime_handoff_output": str(output_handoff),
            "user": self.user_parameters,
        }
        return "\n".join(
            [
                f"${skill_name}",
                "",
                f"你现在只执行运行 Goal {goal_id}。",
                (
                    f"已附加的 {skill_name} Skill 是本 Goal 的完整目标约束；"
                    "严格遵循其方法、顺序、验证、错误边界、证据边界和完成"
                    "条件。"
                ),
                "运行参数：",
                json.dumps(
                    runtime_parameters,
                    ensure_ascii=False,
                    indent=2,
                ),
                "累计前序 runtime handoff ledger：",
                json.dumps(
                    self.ledger.get("handoffs", []),
                    ensure_ascii=False,
                    indent=2,
                ),
                (
                    "只使用这一个已附加 Skill。成功时把本 Goal 的 runtime "
                    "handoff 写到运行参数指定的绝对路径；该 JSON 必须是非空"
                    "对象并索引本次真实产物和证据，使后续 Goal 能按原样消费。"
                ),
                (
                    "本 Goal 新生成的业务运行产物必须写在 "
                    "runtime_artifact_root 内，调度 handoff 只写到 "
                    "runtime_handoff_output；两者均位于 runtime_root。Skill "
                    "明确要求的当前项目源码修改仍写到其既定源码路径。用户"
                    "参数不得把运行产物重定向到 project_root/perf_trace "
                    "之外。"
                ),
                (
                    "只有完成 Skill 的全部完成条件且 runtime handoff 已写入"
                    "后，才把当前 Goal 标记为 complete；受阻、失败或中断时"
                    "如实使用对应终态并停止。"
                ),
            ]
        )

    def _goal_objective(self, goal_id: str) -> str:
        skill_name = self.manifest["bindings"][goal_id]["skill"]
        return (
            f"Execute runtime stage {goal_id} with ${skill_name}, the supplied "
            "user parameters, and the cumulative prior runtime handoff ledger; "
            "reach complete only after the Skill completion conditions hold."
        )

    def _initialize_runtime_files(self) -> None:
        if not RUN_ID_RE.fullmatch(self.run_id):
            raise SchedulerError(
                "run id must start with an alphanumeric character, use only "
                "letters, digits, dot, underscore, or hyphen, and contain at "
                "most 128 characters"
            )
        if self.run_dir.exists():
            raise SchedulerError(
                f"runtime output directory already exists: {self.run_dir}"
            )
        self.handoff_dir.mkdir(parents=True)
        created_at = utc_now()
        self.state = {
            "schema_version": 1,
            "branch": BRANCH,
            "manifest": str(self.manifest_path.relative_to(self.project_root)),
            "run_id": self.run_id,
            "status": "running",
            "created_at": created_at,
            "updated_at": created_at,
            "current_goal": None,
            "user_parameters": self.user_parameters,
            "ledger": str(self.ledger_path.relative_to(self.project_root)),
            "goals": {
                goal_id: {
                    "skill": self.manifest["bindings"][goal_id]["skill"],
                    "status": "pending",
                    "thread_id": None,
                    "turn_ids": [],
                    "goal": None,
                    "error": None,
                }
                for goal_id in self.manifest["goals"]
            },
        }
        self.ledger = {
            "schema_version": 1,
            "branch": BRANCH,
            "run_id": self.run_id,
            "handoffs": [],
        }
        self._checkpoint()
        atomic_write_json(self.ledger_path, self.ledger)

    def _checkpoint(self) -> None:
        if self.state:
            self.state["updated_at"] = utc_now()
            atomic_write_json(self.state_path, self.state)

    def _goal_record(self, goal_id: str) -> dict[str, Any]:
        return self.state["goals"][goal_id]

    def _transition(
        self,
        goal_id: str,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        record = self._goal_record(goal_id)
        record["status"] = status
        record["error"] = error
        self.state["current_goal"] = goal_id
        self._checkpoint()

    def _start_client(self) -> None:
        self.client = AppServerClient(
            codex_bin=self.codex_bin,
            cwd=self.project_root,
            raw_log_path=self.run_dir / "app_server.jsonl",
            stderr_log_path=self.run_dir / "app_server.stderr.log",
            request_timeout=self.request_timeout,
        )
        self.client.start()
        self.client.initialize()
        skill_root = self.project_root / "perf_trace" / "skills"
        self.client.request(
            "skills/extraRoots/set",
            {"extraRoots": [str(skill_root)]},
        )
        result = self.client.request(
            "skills/list",
            {
                "cwds": [str(self.project_root)],
                "forceReload": True,
            },
        )
        discovered: dict[str, Path] = {}
        for entry in result.get("data", []):
            for skill in entry.get("skills", []):
                name = skill.get("name")
                path = skill.get("path")
                if (
                    isinstance(name, str)
                    and isinstance(path, str)
                    and skill.get("enabled", True)
                ):
                    discovered.setdefault(name, Path(path).resolve())
        for goal_id in self.manifest["goals"]:
            name = self.manifest["bindings"][goal_id]["skill"]
            expected = self._skill_md(goal_id)
            actual = discovered.get(name)
            if actual != expected:
                raise SchedulerError(
                    "runtime Skill discovery mismatch: "
                    f"name={name} actual={actual} expected={expected}"
                )

    def _get_goal(self, thread_id: str) -> dict[str, Any]:
        assert self.client is not None
        result = self.client.request(
            "thread/goal/get",
            {"threadId": thread_id},
        )
        goal = result.get("goal")
        if not isinstance(goal, dict):
            raise SchedulerError(
                f"thread/goal/get returned no Goal for {thread_id}"
            )
        return goal

    def _set_goal_status(
        self,
        goal_id: str,
        status: str,
    ) -> dict[str, Any]:
        assert self.client is not None
        record = self._goal_record(goal_id)
        result = self.client.request(
            "thread/goal/set",
            {
                "threadId": record["thread_id"],
                "status": status,
            },
        )
        goal = result.get("goal")
        if not isinstance(goal, dict):
            raise SchedulerError(
                f"{goal_id}: thread/goal/set returned no Goal"
            )
        record["goal"] = goal
        self._checkpoint()
        return goal

    def _get_thread(
        self,
        thread_id: str,
        *,
        include_turns: bool,
    ) -> dict[str, Any]:
        assert self.client is not None
        result = self.client.request(
            "thread/read",
            {
                "threadId": thread_id,
                "includeTurns": include_turns,
            },
        )
        thread = result.get("thread")
        if not isinstance(thread, dict):
            raise SchedulerError(
                f"thread/read returned no thread for {thread_id}"
            )
        return thread

    @staticmethod
    def _thread_status_type(thread: dict[str, Any]) -> str | None:
        status = thread.get("status")
        if isinstance(status, dict):
            value = status.get("type")
            return value if isinstance(value, str) else None
        return status if isinstance(status, str) else None

    def _record_thread(self, goal_id: str, thread: dict[str, Any]) -> None:
        record = self._goal_record(goal_id)
        turn_ids: list[str] = []
        for turn in thread.get("turns", []):
            if isinstance(turn, dict) and isinstance(turn.get("id"), str):
                turn_ids.append(turn["id"])
        record["turn_ids"] = turn_ids
        record["thread_status"] = thread.get("status")
        self._checkpoint()

    def _drain_event(
        self,
        goal_id: str,
        *,
        timeout: float,
    ) -> dict[str, Any] | None:
        assert self.client is not None
        if not self.client.reader_errors.empty():
            raise SchedulerError(self.client.reader_errors.get_nowait())
        if not self.client.server_requests.empty():
            request = self.client.server_requests.get_nowait()
            raise SchedulerError(
                f"{goal_id}: app-server requested interactive action "
                f"{request.get('method')}"
            )
        try:
            message = self.client.notifications.get(timeout=timeout)
        except queue.Empty:
            return None
        method = message.get("method")
        params = message.get("params", {})
        if not isinstance(params, dict):
            return message
        record = self._goal_record(goal_id)
        if params.get("threadId") not in (None, record.get("thread_id")):
            return message
        if method == "turn/started":
            turn_id = params.get("turn", {}).get("id")
            if isinstance(turn_id, str) and turn_id not in record["turn_ids"]:
                record["turn_ids"].append(turn_id)
                self._checkpoint()
        elif method == "turn/completed":
            turn = params.get("turn", {})
            turn_id = turn.get("id")
            status = turn.get("status")
            record["last_turn"] = {
                "id": turn_id,
                "status": status,
                "error": turn.get("error"),
            }
            self._checkpoint()
            if status in {"failed", "interrupted"}:
                raise SchedulerError(
                    f"{goal_id}: Turn {turn_id} ended with {status}"
                )
        elif method == "thread/goal/updated":
            goal = params.get("goal")
            if isinstance(goal, dict):
                record["goal"] = goal
                self._checkpoint()
        elif method == "thread/status/changed":
            record["thread_status"] = params.get("status")
            self._checkpoint()
        elif method == "error":
            raise SchedulerError(
                f"{goal_id}: app-server error notification: {params}"
            )
        return message

    def _wait_for_turn_observation(
        self,
        goal_id: str,
        turn_id: str,
    ) -> None:
        record = self._goal_record(goal_id)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            self._drain_event(goal_id, timeout=0.1)
            thread = self._get_thread(
                record["thread_id"],
                include_turns=True,
            )
            self._record_thread(goal_id, thread)
            for turn in thread.get("turns", []):
                if not isinstance(turn, dict) or turn.get("id") != turn_id:
                    continue
                status = turn.get("status")
                if status in {"failed", "interrupted"}:
                    raise SchedulerError(
                        f"{goal_id}: initial Turn {turn_id} ended with {status}"
                    )
                return
            time.sleep(0.1)
        raise SchedulerError(
            f"{goal_id}: initial Turn {turn_id} was not observable"
        )

    def _start_initial_turn(
        self,
        goal_id: str,
        output_handoff: Path,
        artifact_root: Path,
    ) -> str:
        assert self.client is not None
        record = self._goal_record(goal_id)
        skill_name = self.manifest["bindings"][goal_id]["skill"]
        params = {
            "threadId": record["thread_id"],
            "input": [
                {
                    "type": "text",
                    "text": self._prompt(
                        goal_id,
                        output_handoff,
                        artifact_root,
                    ),
                },
                {
                    "type": "skill",
                    "name": skill_name,
                    "path": str(self._skill_md(goal_id)),
                },
            ],
            **self._turn_overrides(),
        }
        result = self.client.request("turn/start", params)
        turn_id = result.get("turn", {}).get("id")
        if not isinstance(turn_id, str):
            raise SchedulerError(
                f"{goal_id}: turn/start returned no Turn id"
            )
        record["initial_turn_id"] = turn_id
        if turn_id not in record["turn_ids"]:
            record["turn_ids"].append(turn_id)
        self._transition(goal_id, "running")
        self._wait_for_turn_observation(goal_id, turn_id)
        return turn_id

    def _wait_until_idle(self, goal_id: str) -> dict[str, Any]:
        record = self._goal_record(goal_id)
        deadline = (
            time.monotonic() + self.idle_timeout_seconds
            if self.idle_timeout_seconds > 0
            else None
        )
        while deadline is None or time.monotonic() < deadline:
            self._drain_event(goal_id, timeout=0.2)
            thread = self._get_thread(
                record["thread_id"],
                include_turns=True,
            )
            self._record_thread(goal_id, thread)
            active_turn = any(
                isinstance(turn, dict)
                and turn.get("status") == "inProgress"
                for turn in thread.get("turns", [])
            )
            if self._thread_status_type(thread) == "idle" and not active_turn:
                return thread
            time.sleep(0.2)
        raise SchedulerError(
            f"{goal_id}: thread did not become idle after Goal completion"
        )

    def _read_handoff(
        self,
        goal_id: str,
        path: Path,
    ) -> dict[str, Any]:
        payload = load_json(path)
        if not isinstance(payload, dict) or not payload:
            raise SchedulerError(
                f"{goal_id}: runtime handoff must be a non-empty JSON object: "
                f"{path}"
            )
        return payload

    def _append_handoff(
        self,
        goal_id: str,
        path: Path,
    ) -> None:
        record = self._goal_record(goal_id)
        payload = self._read_handoff(goal_id, path)
        entry = {
            "source_goal": goal_id,
            "skill": self.manifest["bindings"][goal_id]["skill"],
            "path": str(path),
            "payload": payload,
        }
        self.ledger["handoffs"].append(entry)
        atomic_write_json(self.ledger_path, self.ledger)
        record["handoff_index"] = len(self.ledger["handoffs"]) - 1
        record["runtime_handoff"] = str(path.relative_to(self.project_root))
        self._transition(goal_id, "complete")

    def _wait_for_goal_complete(self, goal_id: str) -> None:
        record = self._goal_record(goal_id)
        deadline = (
            time.monotonic() + self.goal_timeout_seconds
            if self.goal_timeout_seconds > 0
            else None
        )
        last_poll = 0.0
        while deadline is None or time.monotonic() < deadline:
            self._drain_event(goal_id, timeout=0.5)
            now = time.monotonic()
            if now - last_poll < self.poll_seconds:
                continue
            goal = self._get_goal(record["thread_id"])
            record["goal"] = goal
            self._checkpoint()
            status = goal.get("status")
            if status == "complete":
                return
            if status in STOP_GOAL_STATUSES:
                raise SchedulerError(
                    f"{goal_id}: Goal reached stop status {status}"
                )
            if status != "active":
                raise SchedulerError(
                    f"{goal_id}: inconsistent Goal status {status}"
                )
            thread = self._get_thread(
                record["thread_id"],
                include_turns=False,
            )
            thread_status = self._thread_status_type(thread)
            if thread_status not in {"active", "idle"}:
                raise SchedulerError(
                    f"{goal_id}: inconsistent thread status {thread_status}"
                )
            last_poll = now
        raise SchedulerError(
            f"{goal_id}: Goal exceeded {self.goal_timeout_seconds} seconds"
        )

    def _run_goal(self, goal_id: str) -> None:
        assert self.client is not None
        record = self._goal_record(goal_id)
        output_handoff = self.handoff_dir / f"{goal_id}.json"
        artifact_root = self.run_dir / "artifacts" / goal_id
        if output_handoff.exists():
            raise SchedulerError(
                f"{goal_id}: refusing to reuse runtime handoff "
                f"{output_handoff}"
            )
        artifact_root.mkdir(parents=True)
        record["runtime_artifact_root"] = str(
            artifact_root.relative_to(self.project_root)
        )
        self._checkpoint()
        result = self.client.request(
            "thread/start",
            self._thread_start_params(),
        )
        thread = result.get("thread")
        thread_id = thread.get("id") if isinstance(thread, dict) else None
        if not isinstance(thread_id, str):
            raise SchedulerError(
                f"{goal_id}: thread/start returned no thread id"
            )
        record["thread_id"] = thread_id
        record["thread_status"] = thread.get("status")
        self._transition(goal_id, "thread_created")
        goal_result = self.client.request(
            "thread/goal/set",
            {
                "threadId": thread_id,
                "objective": self._goal_objective(goal_id),
                "status": "paused",
            },
        )
        goal = goal_result.get("goal")
        if not isinstance(goal, dict):
            raise SchedulerError(
                f"{goal_id}: thread/goal/set returned no Goal"
            )
        record["goal"] = goal
        self._checkpoint()
        self._start_initial_turn(
            goal_id,
            output_handoff,
            artifact_root,
        )
        goal = self._get_goal(thread_id)
        record["goal"] = goal
        self._checkpoint()
        status = goal.get("status")
        if status == "complete":
            self._wait_until_idle(goal_id)
            self._append_handoff(goal_id, output_handoff)
            return
        if status in TERMINAL_GOAL_STATUSES:
            raise SchedulerError(
                f"{goal_id}: Goal reached stop status {status}"
            )
        if status == "paused":
            self._set_goal_status(goal_id, "active")
        elif status != "active":
            raise SchedulerError(
                f"{goal_id}: unexpected Goal status after initial Turn: "
                f"{status}"
            )
        self._wait_for_goal_complete(goal_id)
        self._wait_until_idle(goal_id)
        self._append_handoff(goal_id, output_handoff)

    def _pause_current_goal(self) -> None:
        if self.client is None or self.current_goal_id is None:
            return
        goal_id = self.current_goal_id
        record = self._goal_record(goal_id)
        thread_id = record.get("thread_id")
        if not isinstance(thread_id, str):
            return
        try:
            goal = self._get_goal(thread_id)
            if goal.get("status") == "active":
                self._set_goal_status(goal_id, "paused")
        except SchedulerError:
            pass
        try:
            thread = self._get_thread(thread_id, include_turns=True)
            for turn in thread.get("turns", []):
                if (
                    isinstance(turn, dict)
                    and turn.get("status") == "inProgress"
                    and isinstance(turn.get("id"), str)
                ):
                    try:
                        self.client.request(
                            "turn/interrupt",
                            {
                                "threadId": thread_id,
                                "turnId": turn["id"],
                            },
                            timeout=30,
                        )
                    except SchedulerError:
                        pass
        except SchedulerError:
            pass

    def run(self) -> dict[str, Any]:
        self._initialize_runtime_files()
        try:
            self._start_client()
            for index, goal_id in enumerate(self.manifest["goals"]):
                if index:
                    predecessor = self.manifest["goals"][index - 1]
                    if self._goal_record(predecessor)["status"] != "complete":
                        raise SchedulerError(
                            f"{goal_id}: predecessor {predecessor} is not complete"
                        )
                self.current_goal_id = goal_id
                self._run_goal(goal_id)
            self.current_goal_id = None
            self.state["current_goal"] = None
            self.state["status"] = "complete"
            self.state["completed_at"] = utc_now()
            self._checkpoint()
            return {
                "status": "complete",
                "branch": BRANCH,
                "run_id": self.run_id,
                "run_dir": str(self.run_dir),
                "goals": list(self.manifest["goals"]),
                "ledger": str(self.ledger_path),
            }
        except BaseException as exc:
            self._pause_current_goal()
            self.state["status"] = "stopped"
            self.state["last_error"] = str(exc)
            if self.current_goal_id is not None:
                record = self._goal_record(self.current_goal_id)
                if record["status"] != "complete":
                    record["status"] = "stopped"
                    record["error"] = str(exc)
            self._checkpoint()
            raise
        finally:
            if self.client is not None:
                self.client.close()


def validate_runtime_inputs(
    project_root: Path,
) -> tuple[Path, dict[str, Any]]:
    if not project_root.is_dir():
        raise SchedulerError(f"project root is not a directory: {project_root}")
    manifest_path = require_under(
        project_root
        / "perf_trace"
        / "manifests"
        / "core_attribution_pipeline.json",
        project_root,
    )
    manifest = load_json(manifest_path)
    if manifest != EXPECTED_MANIFEST:
        raise SchedulerError(
            f"runtime manifest does not match the {BRANCH} contract: "
            f"{manifest_path}"
        )
    for goal_id in manifest["goals"]:
        skill_name = manifest["bindings"][goal_id]["skill"]
        skill_md = require_under(
            project_root
            / "perf_trace"
            / "skills"
            / skill_name
            / "SKILL.md",
            project_root,
        )
        if not skill_md.is_file():
            raise SchedulerError(f"runtime Skill is missing: {skill_md}")
    return manifest_path, manifest


def dry_run_payload(
    *,
    project_root: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    user_parameters: dict[str, Any],
    run_id: str | None,
    model: str | None,
) -> dict[str, Any]:
    goals: list[dict[str, Any]] = []
    for index, goal_id in enumerate(manifest["goals"]):
        goals.append(
            {
                "id": goal_id,
                "skill": manifest["bindings"][goal_id]["skill"],
                "predecessors": list(manifest["goals"][:index]),
                "persistent_thread": True,
                "effort": "max",
                "runtime_handoff": (
                    f"perf_trace/runtime/{BRANCH}/<run-id>/handoffs/"
                    f"{goal_id}.json"
                ),
                "runtime_artifact_root": (
                    f"perf_trace/runtime/{BRANCH}/<run-id>/artifacts/"
                    f"{goal_id}"
                ),
            }
        )
    return {
        "dry_run": True,
        "branch": BRANCH,
        "project_root": str(project_root),
        "manifest": str(manifest_path),
        "model": model,
        "run_id": run_id or "<generated-at-runtime>",
        "runtime_root": str(
            project_root / "perf_trace" / "runtime" / BRANCH
        ),
        "user_parameters": user_parameters,
        "goals": goals,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Qwen3.5-27B vLLM/PRA ROCm/DCU/HIP core-attribution "
            "pipeline as five serial persistent-thread Goals."
        )
    )
    default_root = Path(__file__).resolve().parents[2]
    parser.add_argument(
        "--project-root",
        default=str(default_root),
        help="Qwen_DCU_Worker_0 project root.",
    )
    parser.add_argument(
        "--branch",
        required=True,
        choices=[BRANCH],
        help="Explicit runtime branch selection.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the validated serial plan without contacting app-server.",
    )
    parameter_group = parser.add_mutually_exclusive_group()
    parameter_group.add_argument(
        "--user-parameters",
        default="{}",
        help="Runtime user parameters as one JSON object.",
    )
    parameter_group.add_argument(
        "--user-parameters-file",
        help="Path to a JSON object containing runtime user parameters.",
    )
    parser.add_argument(
        "--run-id",
        help="Fresh run directory name under perf_trace/runtime/core-attribution.",
    )
    parser.add_argument(
        "--codex-bin",
        help="Codex executable path or command name; resolved only for real runs.",
    )
    parser.add_argument(
        "--model",
        help=(
            "Optional Codex model override for every runtime Goal; the "
            "configured default is used when omitted."
        ),
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=2.0,
        help="Goal status polling interval (default: 2).",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=120.0,
        help="App-server request timeout (default: 120).",
    )
    parser.add_argument(
        "--goal-timeout-seconds",
        type=float,
        default=0.0,
        help="Per-Goal timeout; 0 waits without a scheduler deadline.",
    )
    parser.add_argument(
        "--idle-timeout-seconds",
        type=float,
        default=0.0,
        help=(
            "Wait for a complete Goal thread to become idle; 0 waits without "
            "a scheduler deadline."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if args.poll_seconds <= 0:
            raise SchedulerError("--poll-seconds must be greater than zero")
        if args.request_timeout_seconds <= 0:
            raise SchedulerError(
                "--request-timeout-seconds must be greater than zero"
            )
        if args.goal_timeout_seconds < 0:
            raise SchedulerError(
                "--goal-timeout-seconds must be zero or greater"
            )
        if args.idle_timeout_seconds < 0:
            raise SchedulerError(
                "--idle-timeout-seconds must be zero or greater"
            )
        project_root = Path(args.project_root).expanduser().resolve()
        manifest_path, manifest = validate_runtime_inputs(project_root)
        user_parameters = parse_user_parameters(
            args.user_parameters,
            args.user_parameters_file,
        )
        if args.dry_run:
            print(
                json.dumps(
                    dry_run_payload(
                        project_root=project_root,
                        manifest_path=manifest_path,
                        manifest=manifest,
                        user_parameters=user_parameters,
                        run_id=args.run_id,
                        model=args.model,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        codex_bin = resolve_codex_binary(args.codex_bin)
        scheduler = RuntimeScheduler(
            project_root=project_root,
            manifest_path=manifest_path,
            manifest=manifest,
            user_parameters=user_parameters,
            codex_bin=codex_bin,
            model=args.model,
            run_id=args.run_id or default_run_id(),
            poll_seconds=args.poll_seconds,
            request_timeout=args.request_timeout_seconds,
            goal_timeout_seconds=args.goal_timeout_seconds,
            idle_timeout_seconds=args.idle_timeout_seconds,
        )
        print(
            json.dumps(
                scheduler.run(),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except KeyboardInterrupt:
        print("perf-trace scheduler interrupted", file=sys.stderr)
        return 130
    except SchedulerError as exc:
        print(f"perf-trace scheduler failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
