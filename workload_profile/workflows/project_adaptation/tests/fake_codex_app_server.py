#!/usr/bin/env python3
"""Small deterministic Codex/app-server fake for orchestrator tests."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


def send(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def write_protocol_schema(arguments: list[str]) -> int:
    try:
        output_dir = Path(arguments[arguments.index("--out") + 1])
    except (ValueError, IndexError):
        print("missing --out", file=sys.stderr)
        return 2
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "fake": True,
        "version": "0.145.0",
        "methods": [
            "thread/start",
            "thread/goal/set",
            "turn/start",
            "model/list",
            "skills/list",
        ],
    }
    (output_dir / "codex_app_server_protocol.v2.schemas.json").write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )
    return 0


def discover_fake_skills() -> list[dict[str, Any]]:
    project_root_value = os.environ.get("FAKE_PROJECT_ROOT")
    if not project_root_value:
        return []
    project_root = Path(project_root_value)
    roots = [
        project_root / "fake_global_skills",
        project_root / "workload_profile" / "skills",
    ]
    skills: list[dict[str, Any]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for skill_md in sorted(root.glob("*/SKILL.md")):
            skills.append(
                {
                    "name": skill_md.parent.name,
                    "description": "fake test Skill",
                    "enabled": True,
                    "path": str(skill_md.resolve()),
                    "scope": "repo",
                    "interface": None,
                    "dependencies": None,
                    "shortDescription": None,
                }
            )
    return skills


def append_request_log(message: dict[str, Any]) -> None:
    log_value = os.environ.get("FAKE_CODEX_LOG")
    if not log_value:
        return
    with Path(log_value).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(message, ensure_ascii=False) + "\n")


def goal_payload(thread_id: str, stored: dict[str, Any]) -> dict[str, Any]:
    return {
        "threadId": thread_id,
        "objective": stored["objective"],
        "status": stored["status"],
        "tokenBudget": stored.get("tokenBudget"),
        "tokensUsed": stored.get("tokensUsed", 100),
        "timeUsedSeconds": stored.get("timeUsedSeconds", 1),
        "createdAt": 1,
        "updatedAt": 2,
    }


def run_server() -> int:
    state_path_value = os.environ.get("FAKE_SERVER_STATE")
    state_path = Path(state_path_value) if state_path_value else None
    if state_path is not None and state_path.is_file():
        persisted = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        persisted = {
            "threads": {},
            "goals": {},
            "thread_counter": 0,
            "turn_counter": 0,
        }
    threads: dict[str, dict[str, Any]] = persisted["threads"]
    goals: dict[str, dict[str, Any]] = persisted["goals"]
    thread_counter = int(persisted["thread_counter"])
    turn_counter = int(persisted["turn_counter"])

    def save_state() -> None:
        if state_path is None:
            return
        state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = state_path.with_name(f".{state_path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(
                {
                    "threads": threads,
                    "goals": goals,
                    "thread_counter": thread_counter,
                    "turn_counter": turn_counter,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, state_path)

    def emit_goal_turn(thread_id: str, *, complete_goal: bool) -> None:
        """Emit one server-observed Turn; automatic Turns have no client request."""
        nonlocal turn_counter
        turn_counter += 1
        turn_id = f"turn_{turn_counter:02d}"
        turn = {
            "id": turn_id,
            "status": "inProgress",
            "items": [],
            "error": None,
        }
        threads[thread_id]["turns"].append(turn)
        threads[thread_id]["status"] = {"type": "active", "activeFlags": []}
        send(
            {
                "method": "turn/started",
                "params": {"threadId": thread_id, "turn": turn},
            }
        )
        send(
            {
                "method": "thread/status/changed",
                "params": {
                    "threadId": thread_id,
                    "status": {"type": "active", "activeFlags": []},
                },
            }
        )

        objective = goals[thread_id]["objective"]
        stage_match = re.search(
            r"\b(A(?:00|01|02|031|041|051|032|033|042|052|07))\b",
            objective,
        )
        stage_id = stage_match.group(1) if stage_match else ""
        stage_turns = len(threads[thread_id]["turns"])
        command_item = {
            "id": f"item_command_{turn_counter:02d}",
            "type": "commandExecution",
            "status": "inProgress",
            "command": f"fixture-command {stage_id} turn={stage_turns}",
            "aggregatedOutput": "",
            "exitCode": None,
        }
        send(
            {
                "method": "item/started",
                "params": {"threadId": thread_id, "item": command_item},
            }
        )
        command_item.update(
            {
                "status": "completed",
                "aggregatedOutput": "fixture command passed",
                "exitCode": 0,
            }
        )
        send(
            {
                "method": "item/completed",
                "params": {"threadId": thread_id, "item": command_item},
            }
        )
        send(
            {
                "method": "item/completed",
                "params": {
                    "threadId": thread_id,
                    "item": {
                        "id": f"item_message_{turn_counter:02d}",
                        "type": "agentMessage",
                        "text": f"fixture progress {stage_id} turn={stage_turns}",
                    },
                },
            }
        )
        if complete_goal:
            goals[thread_id]["status"] = "complete"
            goals[thread_id]["tokensUsed"] = 1234
            goals[thread_id]["timeUsedSeconds"] = 12
            send(
                {
                    "method": "thread/goal/updated",
                    "params": {
                        "threadId": thread_id,
                        "goal": goal_payload(thread_id, goals[thread_id]),
                    },
                }
            )

        turn["status"] = "completed"
        threads[thread_id]["status"] = {"type": "idle"}
        save_state()
        send(
            {
                "method": "turn/completed",
                "params": {"threadId": thread_id, "turn": turn},
            }
        )
        send(
            {
                "method": "thread/status/changed",
                "params": {
                    "threadId": thread_id,
                    "status": {"type": "idle"},
                },
            }
        )

    def maybe_continue_goal(thread_id: str) -> None:
        stored = goals.get(thread_id)
        if (
            isinstance(stored, dict)
            and stored.get("objective")
            and stored.get("status") == "active"
            and threads[thread_id]["status"].get("type") == "idle"
        ):
            emit_goal_turn(thread_id, complete_goal=True)

    for line in sys.stdin:
        message = json.loads(line)
        append_request_log(message)
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        if request_id is None:
            continue
        if method == "initialize":
            send(
                {
                    "id": request_id,
                    "result": {
                        "userAgent": "fake-codex/0.145.0",
                        "platformFamily": "unix",
                        "platformOs": "linux",
                    },
                }
            )
        elif method == "model/list":
            send(
                {
                    "id": request_id,
                    "result": {
                        "data": [
                            {
                                "id": "gpt-5.6-sol",
                                "model": "gpt-5.6-sol",
                                "displayName": "GPT-5.6 Sol",
                                "description": "fake",
                                "hidden": False,
                                "isDefault": True,
                                "defaultReasoningEffort": "medium",
                                "supportedReasoningEfforts": [
                                    {
                                        "reasoningEffort": "max",
                                        "description": "fake max",
                                    }
                                ],
                            }
                        ],
                        "nextCursor": None,
                    },
                }
            )
        elif method == "account/read":
            send(
                {
                    "id": request_id,
                    "result": {
                        "account": {"type": "chatgpt"},
                        "requiresOpenaiAuth": True,
                    },
                }
            )
        elif method == "skills/extraRoots/set":
            send({"id": request_id, "result": {}})
        elif method == "skills/list":
            send(
                {
                    "id": request_id,
                    "result": {
                        "data": [
                            {
                                "cwd": os.environ.get("FAKE_PROJECT_ROOT", ""),
                                "skills": discover_fake_skills(),
                                "errors": [],
                            }
                        ]
                    },
                }
            )
        elif method == "thread/start":
            thread_counter += 1
            thread_id = f"thr_{thread_counter:02d}"
            threads[thread_id] = {"turns": [], "status": {"type": "idle"}}
            save_state()
            send(
                {
                    "id": request_id,
                    "result": {
                        "thread": {"id": thread_id, "status": {"type": "idle"}},
                        "model": params.get("model", "gpt-5.6-sol"),
                        "modelProvider": "openai",
                        "cwd": params.get("cwd", ""),
                        "approvalPolicy": params.get("approvalPolicy", "never"),
                        "approvalsReviewer": "user",
                        "sandbox": {"type": "workspaceWrite"},
                    },
                }
            )
            send(
                {
                    "method": "thread/started",
                    "params": {"thread": {"id": thread_id}},
                }
            )
        elif method == "thread/resume":
            thread_id = params["threadId"]
            send(
                {
                    "id": request_id,
                    "result": {"thread": {"id": thread_id, **threads[thread_id]}},
                }
            )
            maybe_continue_goal(thread_id)
        elif method == "thread/goal/set":
            thread_id = params["threadId"]
            current = goals.get(
                thread_id,
                {
                    "objective": "",
                    "status": "active",
                    "tokenBudget": None,
                    "tokensUsed": 0,
                    "timeUsedSeconds": 0,
                },
            )
            if params.get("objective") is not None:
                current["objective"] = params["objective"]
                current["tokensUsed"] = 0
                current["timeUsedSeconds"] = 0
            if params.get("status") is not None:
                current["status"] = params["status"]
            if "tokenBudget" in params and params["tokenBudget"] is not None:
                current["tokenBudget"] = params["tokenBudget"]
            goals[thread_id] = current
            save_state()
            goal = goal_payload(thread_id, current)
            send({"id": request_id, "result": {"goal": goal}})
            send(
                {
                    "method": "thread/goal/updated",
                    "params": {"threadId": thread_id, "goal": goal},
                }
            )
            maybe_continue_goal(thread_id)
        elif method == "thread/goal/get":
            thread_id = params["threadId"]
            stored = goals.get(thread_id)
            send(
                {
                    "id": request_id,
                    "result": {
                        "goal": goal_payload(thread_id, stored) if stored else None
                    },
                }
            )
        elif method == "turn/start":
            thread_id = params["threadId"]
            response_turn = {
                "id": f"turn_{turn_counter + 1:02d}",
                "status": "inProgress",
                "items": [],
                "error": None,
            }
            send({"id": request_id, "result": {"turn": response_turn}})
            emit_goal_turn(thread_id, complete_goal=False)
        elif method == "thread/read":
            thread_id = params["threadId"]
            thread = {"id": thread_id, **threads[thread_id]}
            if not params.get("includeTurns"):
                thread = {
                    "id": thread_id,
                    "status": threads[thread_id]["status"],
                    "turns": [],
                }
            send({"id": request_id, "result": {"thread": thread}})
        elif method == "turn/interrupt":
            thread_id = params["threadId"]
            turn_id = params["turnId"]
            for turn in threads[thread_id]["turns"]:
                if turn["id"] == turn_id:
                    turn["status"] = "interrupted"
            threads[thread_id]["status"] = {"type": "idle"}
            save_state()
            send({"id": request_id, "result": {}})
        else:
            send(
                {
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"fake method not found: {method}",
                    },
                }
            )
    return 0


def main() -> int:
    arguments = sys.argv[1:]
    if arguments == ["--version"]:
        print("codex-cli 0.145.0")
        return 0
    if arguments[:2] == ["app-server", "generate-json-schema"]:
        return write_protocol_schema(arguments[2:])
    if arguments and arguments[0] == "app-server":
        return run_server()
    print(f"unsupported fake Codex arguments: {arguments}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
