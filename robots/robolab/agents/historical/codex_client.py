# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Historical RoboLab app-server episodes; separate from the standard MCP baseline."""

from __future__ import annotations

import errno
import hashlib
import json
import logging
import os
import selectors
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from tempfile import TemporaryDirectory

from robots.robolab.motion import TARGET_SCHEMA, robot_state, validate_target

from .images import image_data_url, validate_reasoning_effort
from .prompts import load_system_prompt

logger = logging.getLogger(__name__)
DEFAULT_BASE_URL = "https://api.openai.com/v1"


def provider_identity(base_url: str) -> dict[str, str]:
    """Identify the actual provider without persisting URLs or credentials."""
    return {
        "name": "robot_harness",
        "wire_api": "responses",
        "base_url_sha256": hashlib.sha256(base_url.encode()).hexdigest(),
    }


TOOLS = [
    {
        "type": "function",
        "name": "observe",
        "description": "Observe the robot without advancing simulation.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "act",
        "description": "Move to an absolute EEF target over steps control frames; wait for the resulting observation.",
        "inputSchema": TARGET_SCHEMA,
    },
]


class CodexClient:
    backend = "codex"
    auth = "api_key"
    finish_timeout = 15.0
    shutdown_timeout = 2.0
    cleanup_timeout = 2.0
    tools = TOOLS

    def __init__(
        self,
        model: str,
        *,
        timeout: float = 1200,
        image_size: int = 320,
        reasoning_effort: str = "max",
        codex_max_retries: int = 30,
        system_prompt: Path | None = None,
        executable: str = "codex",
    ) -> None:
        if not model or not 0 < timeout < float("inf") or image_size < 1:
            raise ValueError(
                "model, positive finite timeout, and positive image_size are required"
            )
        if (
            isinstance(codex_max_retries, bool)
            or not isinstance(codex_max_retries, int)
            or codex_max_retries < 0
        ):
            raise ValueError("codex_max_retries must be a non-negative integer")
        if sys.platform != "linux":
            raise RuntimeError("The isolated Codex harness currently requires Linux")
        self.executable = shutil.which(executable)
        if self.executable is None:
            raise RuntimeError("Codex CLI is missing; install Codex >= 0.159 first")
        self.model, self.timeout, self.image_size = model, timeout, image_size
        self.codex_max_retries = codex_max_retries
        self.reasoning_effort = validate_reasoning_effort(reasoning_effort)
        self.system = load_system_prompt(
            system_prompt or Path(__file__).parent / "prompts/codex_system.md"
        )
        self.env = dict(os.environ)
        self.base_url = self.env.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
        for name in ("CODEX_SESSION_ID", "CODEX_THREAD_ID", "CODEX_API_KEY"):
            self.env.pop(name, None)
        if not self.env.get("OPENAI_API_KEY"):
            raise RuntimeError("Codex harness requires OPENAI_API_KEY")
        self.last_response_text = self.last_usage = None
        self.events_path = self.stderr_path = None
        self._process = self._directory = self._selector = self._stderr = None
        self._process_lock = threading.Lock()
        self._cancelled = threading.Event()
        self.connection_cancelled = threading.Event()

    def _config(self, system: str) -> list[str]:
        # Sandbox aliases are symlinks: bwrap also needs their real executable,
        # which npm may install outside the minimal system-readable paths.
        codex_dir = Path(self.env.get("CODEX_HOME", str(Path.home() / ".codex")))
        filesystem_rules = {
            ":minimal": "read",
            ":workspace_roots": "write",
            str(codex_dir / "tmp/arg0"): "read",
        }
        for executable in self._sandbox_executables():
            filesystem_rules[str(executable)] = "read"
        filesystem = (
            "{"
            + ",".join(
                f"{json.dumps(path)}={json.dumps(access)}"
                for path, access in filesystem_rules.items()
            )
            + "}"
        )
        settings = {
            "model_provider": "robot_harness",
            "model_reasoning_effort": self.reasoning_effort,
            "developer_instructions": system,
            "approval_policy": "never",
            "default_permissions": "robot_harness",
            "permissions.robot_harness.network.enabled": False,
            "web_search": "disabled",
            "project_doc_max_bytes": 0,
            "allow_login_shell": False,
            "shell_environment_policy.inherit": "core",
            "shell_environment_policy.filters.PATH": "include",
            "model_providers.robot_harness.name": "Robot harness",
            "model_providers.robot_harness.wire_api": "responses",
            "model_providers.robot_harness.request_max_retries": self.codex_max_retries,
            "model_providers.robot_harness.stream_max_retries": self.codex_max_retries,
            "model_providers.robot_harness.requires_openai_auth": False,
            "model_providers.robot_harness.env_key": "OPENAI_API_KEY",
            "model_providers.robot_harness.base_url": self.base_url,
        }
        for feature in (
            "apps",
            "plugins",
            "remote_plugin",
            "hooks",
            "memories",
            "multi_agent",
            "browser_use",
            "computer_use",
            "image_generation",
            "shell_snapshot",
            "skill_search",
            "skill_mcp_dependency_install",
            "unbounded_connection_retries",
        ):
            settings[f"features.{feature}"] = False
        settings["features.skip_host_skill_discovery"] = True
        settings["features.goals"] = True
        args = ["-c", "permissions.robot_harness.filesystem=" + filesystem]
        for key, value in settings.items():
            args.extend(["-c", f"{key}={json.dumps(value)}"])
        return args

    def _sandbox_executables(self) -> list[Path]:
        """Expose runtime files without granting access to their install directories."""
        entrypoint = Path(self.executable).resolve()
        executables = {entrypoint}
        if entrypoint.name == "codex.js":
            # npm can nest or hoist the platform package. Resolve symlinks for
            # pnpm/bun layouts too; older bundles keep vendor beside bin/.
            vendor_roots = [entrypoint.parent.parent / "vendor"]
            for parent in entrypoint.parents:
                vendor_roots.extend(
                    (parent / "node_modules/@openai").glob("codex-linux-*/vendor")
                )
            for vendor in vendor_roots:
                for directory in ("bin", "codex"):
                    executables.update(
                        path.resolve()
                        for path in vendor.glob(f"*/{directory}/codex")
                        if path.is_file()
                    )
        return sorted(executables)

    def start_episode(
        self, instruction: str, *, max_steps: int, control_dt: float, log_dir: Path
    ) -> None:
        self._instruction = instruction
        self._max_steps, self._control_dt = max_steps, control_dt
        system = self.system
        deadline = time.monotonic() + self.timeout
        try:
            self._start_session(
                system, log_dir=log_dir, deadline=deadline, tools=self.tools
            )
            self._rpc(
                "thread/goal/set",
                {
                    "threadId": self._thread_id,
                    "status": "active",
                    "objective": "Execute this robot episode toward the supplied task until observe/act returns done=true. "
                    "Then stop acting and complete the goal. Task: "
                    + instruction[:3000],
                },
                deadline,
            )
        except BaseException:
            self.close()
            raise

    def _start_session(
        self,
        system: str,
        *,
        log_dir: Path,
        deadline: float,
        tools: list[dict],
    ) -> None:
        self.close()
        self._cancelled.clear()
        self.last_response_text = self.last_usage = None
        self._queue = deque()
        self._buffer = b""
        self._request_id = 0
        self._pending_act = None
        self._seen_calls = set()
        self._last_control_step = 0
        self._goal_status = "active"
        self._turn_started = False
        log_dir = Path(log_dir).resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        self.events_path, self.stderr_path = (
            log_dir / "events.jsonl",
            log_dir / "stderr.log",
        )
        # Codex refuses to create sandbox helpers under the system temp directory.
        # Use the experiment output directory for this disposable private store.
        self._directory = TemporaryDirectory(prefix="runtime_", dir=log_dir)
        root = Path(self._directory.name)
        try:
            work = root / "workspace"
            work.mkdir()
            codex_home = root / "codex"
            codex_home.mkdir(mode=0o700)
            # Native goals require persisted threads, outside the readable workspace.
            self.env["CODEX_HOME"] = str(codex_home)
            config = self._config(system)
            self._check_sandbox(work, config, deadline=deadline)
            with self._process_lock:
                self._check_cancelled()
                self._stderr = self.stderr_path.open("ab")
                self._process = subprocess.Popen(
                    [
                        self.executable,
                        "app-server",
                        "--stdio",
                        "--strict-config",
                        *config,
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=self._stderr,
                    env=self.env,
                    cwd=work,
                    start_new_session=True,
                )
            self._selector = selectors.DefaultSelector()
            self._selector.register(self._process.stdout, selectors.EVENT_READ)
            self._rpc(
                "initialize",
                {
                    "clientInfo": {"name": "robot_harness", "version": "2"},
                    "capabilities": {"experimentalApi": True},
                },
                deadline,
            )
            self._send({"method": "initialized", "params": {}})
            result = self._rpc(
                "thread/start",
                {
                    "model": self.model,
                    "modelProvider": "robot_harness",
                    "cwd": str(work),
                    "ephemeral": False,
                    "approvalPolicy": "never",
                    "permissions": "robot_harness",
                    "dynamicTools": tools,
                },
                deadline,
            )
            self._thread_id = result["thread"]["id"]
        except BaseException:
            self.close()
            raise

    def act(self, observation: dict, *, control_step: int) -> dict:
        deadline = time.monotonic() + self.timeout
        content = self._observation(observation, control_step, done=False)
        if not self._turn_started:
            self._turn_started = True
            self._rpc(
                "turn/start",
                {
                    "threadId": self._thread_id,
                    "input": [
                        {
                            "type": "text",
                            "text": "Execute the current episode autonomously. Start with observe().\n"
                            f"Task instruction: {self._instruction}\nControl period: {self._control_dt} seconds. "
                            f"Step budget: {self._max_steps}.",
                        }
                    ],
                },
                deadline,
            )
        self._complete_action(content, deadline)
        while True:
            try:
                event = self._next_event(deadline)
            except TimeoutError:
                self._require_active_goal()
                raise
            self._check_event(event, require_goal=True)
            if self._goal_status != "active":
                # A transport failure can block the goal before emitting its
                # error event. Preserve that diagnostic without allowing motion.
                deadline = min(deadline, time.monotonic() + 1)
            if event.get("method") != "item/tool/call":
                continue
            self._require_active_goal()
            params = self._tool_params(event)
            if params["tool"] == "observe":
                if params["arguments"] != {}:
                    raise ValueError("observe takes no arguments")
                self._tool_result(event["id"], content)
            elif params["tool"] == "act":
                target = self._validate_target(
                    params["arguments"], remaining_steps=self._max_steps - control_step
                )
                self._pending_act = event["id"]
                self._last_control_step = control_step
                return target
            else:
                raise ValueError(f"Unknown robot tool: {params['tool']}")

    def _validate_target(self, target: dict, *, remaining_steps: int) -> dict:
        return validate_target(target, remaining_steps=remaining_steps)

    def end_episode(self, observation: dict, *, control_step: int, reason: str) -> str:
        deadline = time.monotonic() + self.finish_timeout
        try:
            if reason == "execution_error":
                return "aborted"
            content = self._observation(
                observation, control_step, done=True, reason=reason
            )
            self._complete_action(content, deadline)
            while True:
                event = self._next_event(deadline)
                self._check_event(event, require_goal=False)
                if event.get("method") == "item/tool/call":
                    params = self._tool_params(event)
                    if params["tool"] == "observe" and params["arguments"] == {}:
                        self._tool_result(event["id"], content)
                    else:
                        self._tool_result(
                            event["id"],
                            [
                                {
                                    "type": "inputText",
                                    "text": "Episode ended; do not act again.",
                                }
                            ],
                            success=False,
                        )
                elif event.get("method") == "turn/completed":
                    # Stop any goal continuation even if the agent forgot to
                    # mark it complete. This records completion of execution,
                    # never a benchmark success claim.
                    self._rpc(
                        "thread/goal/set",
                        {"threadId": self._thread_id, "status": "complete"},
                        deadline,
                    )
                    return "completed"
        except TimeoutError:
            return "timeout"
        except Exception as error:
            self._log(
                "finish_error", {"type": type(error).__name__, "message": str(error)}
            )
            return "error"
        finally:
            self.close()

    def _observation(
        self, observation: dict, control_step: int, *, done: bool, reason=None
    ) -> list[dict]:
        state = {
            "robot_state": robot_state(observation),
            "control_step": control_step,
            "remaining_steps": max(0, self._max_steps - control_step),
            "control_dt": self._control_dt,
            "executed_steps": control_step - self._last_control_step,
            "done": done,
        }
        if reason is not None:
            state["end_reason"] = reason
        content = [{"type": "inputText", "text": json.dumps(state, allow_nan=False)}]
        for name in ("exterior_image", "wrist_image"):
            content.extend(
                [
                    {"type": "inputText", "text": f"Camera: {name}"},
                    {
                        "type": "inputImage",
                        "imageUrl": image_data_url(observation[name], self.image_size),
                    },
                ]
            )
        return content

    def _complete_action(self, content: list[dict], deadline: float) -> None:
        if self._pending_act is None:
            return
        # A protocol barrier collects calls issued before this action returned.
        # Reject parallel/stale actions rather than execute an unseen plan twice.
        goal = self._rpc("thread/goal/get", {"threadId": self._thread_id}, deadline)[
            "goal"
        ]
        if goal is None:
            raise RuntimeError("Codex cleared its goal before the environment ended")
        self._goal_status = goal["status"]
        self._require_active_goal()
        if any(
            event.get("method") == "item/tool/call" and event["params"]["tool"] == "act"
            for event in self._queue
        ):
            raise RuntimeError("Wait for each act result before issuing another act")
        self._tool_result(self._pending_act, content)
        self._pending_act = None

    def _tool_params(self, event: dict) -> dict:
        params = event["params"]
        if (
            params["threadId"] != self._thread_id
            or params["callId"] in self._seen_calls
        ):
            raise RuntimeError(
                "Unexpected thread or repeated tool call; no replay is allowed"
            )
        self._seen_calls.add(params["callId"])
        return params

    def _check_event(self, event: dict, *, require_goal: bool) -> None:
        method, params = event.get("method"), event.get("params", {})
        if method == "thread/goal/updated":
            self._goal_status = params["goal"]["status"]
        elif method == "thread/goal/cleared" and require_goal:
            raise RuntimeError("Codex cleared its goal before the environment ended")
        elif method == "thread/tokenUsage/updated":
            self.last_usage = params.get("tokenUsage")
        elif (
            method == "item/completed"
            and params.get("item", {}).get("type") == "agentMessage"
        ):
            self.last_response_text = params["item"].get("text")
        elif method == "turn/completed":
            turn = params["turn"]
            if turn["status"] != "completed":
                raise RuntimeError(f"Codex turn {turn['status']}: {turn.get('error')}")
            if require_goal:
                self._require_active_goal()
            # Native goals may continue after an intermediate completed turn.
        elif method == "error" and not params.get("willRetry", False):
            raise RuntimeError(f"Codex error: {params.get('error', params)}")
        elif "id" in event and method and method != "item/tool/call":
            self._send(
                {
                    "id": event["id"],
                    "error": {
                        "code": -32601,
                        "message": "Interactive requests are unavailable",
                    },
                }
            )
            raise RuntimeError(f"Unexpected Codex request: {method}")

    def _require_active_goal(self) -> None:
        if self._goal_status != "active":
            raise RuntimeError(
                f"Codex stopped its goal before the environment ended ({self._goal_status})"
            )

    def _rpc(self, method: str, params: dict, deadline: float) -> dict:
        self._request_id += 1
        request_id = self._request_id
        self._send({"id": request_id, "method": method, "params": params})
        while True:
            event = self._read(deadline)
            if event.get("id") == request_id and "method" not in event:
                if "error" in event:
                    raise RuntimeError(f"{method}: {event['error']}")
                return event["result"]
            self._queue.append(event)

    def _tool_result(
        self, request_id, content: list[dict], *, success: bool = True
    ) -> None:
        self._send(
            {
                "id": request_id,
                "result": {"contentItems": content, "success": success},
            }
        )

    def _send(self, event: dict) -> None:
        self._check_cancelled()
        self._process.stdin.write((json.dumps(event, allow_nan=False) + "\n").encode())
        self._process.stdin.flush()
        self._log("send", event)

    def _next_event(self, deadline: float) -> dict:
        self._check_cancelled()
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out waiting for Codex")
        return self._queue.popleft() if self._queue else self._read(deadline)

    def _read(self, deadline: float) -> dict:
        while b"\n" not in self._buffer:
            self._check_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Timed out waiting for Codex")
            if not self._selector.select(min(remaining, 0.2)):
                continue
            data = os.read(self._process.stdout.fileno(), 65536)
            if not data:
                raise RuntimeError(
                    f"Codex app-server closed its output; see {self.stderr_path}"
                )
            self._buffer += data
        line, self._buffer = self._buffer.split(b"\n", 1)
        event = json.loads(line)
        self._log("receive", event)
        return event

    def _log(self, direction: str, event: dict) -> None:
        if self.events_path is not None:
            with self.events_path.open("a") as stream:
                stream.write(
                    json.dumps(
                        {"direction": direction, "event": event}, allow_nan=False
                    )
                    + "\n"
                )

    def _check_cancelled(self) -> None:
        if self._cancelled.is_set() or self.connection_cancelled.is_set():
            raise RuntimeError("Codex session interrupted")

    def abort(self) -> None:
        """Thread-safe cancellation; resource disposal waits for the reader to exit."""
        with self._process_lock:
            self._cancelled.set()
            if self._process is not None:
                try:
                    os.killpg(self._process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def close(self) -> None:
        self.abort()
        if self._process is not None:
            deadline = time.monotonic() + self.shutdown_timeout
            try:
                self._process.wait(timeout=self.shutdown_timeout)
            except subprocess.TimeoutExpired as error:
                raise RuntimeError(
                    "Codex process did not terminate; retaining its runtime directory"
                ) from error
            # The npm launcher can exit before its killed native child releases
            # files. Zombies cannot write; a live group member must not be hidden.
            while self._group_running(self._process.pid):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(
                        "Codex process group did not terminate; retaining its runtime directory"
                    )
                time.sleep(min(0.05, remaining))
            self._process.stdin.close()
            self._process.stdout.close()
            self._process = None
        if self._selector is not None:
            self._selector.close()
            self._selector = None
        if self._stderr is not None:
            self._stderr.close()
            self._stderr = None
        if self._directory is not None:
            directory, self._directory = self._directory, None
            deadline = time.monotonic() + self.cleanup_timeout
            while True:
                try:
                    directory.cleanup()
                    break
                except OSError as error:
                    remaining = deadline - time.monotonic()
                    if (
                        error.errno in (errno.ENOTEMPTY, errno.EBUSY, errno.ESTALE)
                        and remaining > 0
                    ):
                        time.sleep(min(0.1, remaining))
                        continue
                    # A directory deletion failure is not a model failure. Keep
                    # diagnostics without a later GC/atexit deletion attempt.
                    directory._finalizer.detach()
                    logger.warning(
                        "Preserving Codex runtime directory %s after cleanup failed: %s",
                        directory.name,
                        error,
                    )
                    break

    @staticmethod
    def _group_running(group_id: int) -> bool:
        """Check only the session's process group; never signal unrelated agents."""
        try:
            os.killpg(group_id, 0)
        except ProcessLookupError:
            return False
        for path in Path("/proc").iterdir():
            if not path.name.isdigit():
                continue
            try:
                fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
            except (FileNotFoundError, ProcessLookupError):
                continue
            if int(fields[2]) == group_id and fields[0] not in ("Z", "X"):
                return True
        return False

    def _check_sandbox(
        self, work: Path, config: list[str], *, deadline: float | None = None
    ) -> None:
        """Fail before inference if the required tool isolation cannot run."""
        repo = Path(__file__).resolve().parents[4]
        codex_dir = Path(self.env.get("CODEX_HOME", str(Path.home() / ".codex")))
        probe = (
            "import os,socket; from pathlib import Path\n"
            "assert not any(name in os.environ for name in ('OPENAI_API_KEY','CODEX_API_KEY'))\n"
            f"assert not os.access({str(repo / 'README.md')!r},os.R_OK)\n"
            f"assert not os.access({str(codex_dir / 'auth.json')!r},os.R_OK)\n"
            "Path('.sandbox_probe').write_text('ok')\n"
            "Path('.sandbox_probe').unlink()\n"
            "try:\n s=socket.socket(); s.close()\n"
            "except PermissionError:\n pass\n"
            "else:\n raise RuntimeError('Tool networking is not isolated')\n"
        )
        result = subprocess.run(
            [
                self.executable,
                "sandbox",
                "-C",
                str(work),
                "-P",
                "robot_harness",
                *config,
                "--",
                "/usr/bin/python3",
                "-c",
                probe,
            ],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=20
            if deadline is None
            else min(20, max(0.001, deadline - time.monotonic())),
        )
        self.stderr_path.write_text(result.stderr)
        if result.returncode:
            raise RuntimeError(
                f"Codex tool isolation is unavailable: {result.stderr[-2000:]}"
            )
