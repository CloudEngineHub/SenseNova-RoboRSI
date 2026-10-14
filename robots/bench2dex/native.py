# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Drive the unchanged native simulator RPC one physical control interval at a time.

The first request submits the original entire action chunk. Intermediate requests
acknowledge the upstream update_obs callback without requesting another policy
chunk. Thus native policy-query counts and open-loop execution remain unchanged.
"""

from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import yaml

from roborsi.evaluation.messages import Task

from .contracts import PROTOCOL, file_sha256, validate_chunk, validate_task
from .reference.core import classify_result
from .reference.robot import kinematics
from .reference.transport import recv_message, send_message


class NativeRuntime:
    """Own exactly one native process; permit only validated public actions."""

    def __init__(
        self,
        directory: Path,
        *,
        upstream: Path,
        assets: Path,
        isaaclab: Path,
        python: Path,
        timeout_s: float = 900,
    ) -> None:
        self.directory = directory
        self.upstream, self.assets, self.isaaclab, self.python = (
            upstream,
            assets,
            isaaclab,
            python,
        )
        self.timeout_s = timeout_s
        self._events: queue.Queue = queue.Queue()
        self._commands: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._listener: socket.socket | None = None
        self._connection: socket.socket | None = None
        self._process: subprocess.Popen | None = None
        self._log = None
        self._kit_cache = None
        self.task: Task | None = None
        self.kinematic_card: dict = {}
        self.result: dict | None = None
        self.steps = 0
        self._remaining_chunk = 0
        self._expects_chunk = True
        self._started_at = 0.0
        self.policy_failed = False

    def _verify(self, task: Task) -> tuple[Path, dict]:
        row = validate_task(task)
        if (
            self.upstream.parent / "dex2bench_dataset"
        ).resolve() != self.assets.resolve():
            raise ValueError(
                "native USD paths require dex2bench_dataset beside Bench2Dex; link it to the selected assets"
            )
        for root, pin in (
            (self.upstream, PROTOCOL["upstream_commit"]),
            (self.isaaclab, PROTOCOL["isaaclab_commit"]),
        ):
            actual = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
            ).strip()
            dirty = subprocess.check_output(
                ["git", "-C", str(root), "status", "--porcelain"], text=True
            )
            if actual != pin or dirty:
                raise ValueError("native source must be clean at its pinned revision")
        scene = self.upstream / "scenes" / row["scene"]
        if file_sha256(scene) != row["scene_sha256"]:
            raise ValueError("native scene changed")
        maps = yaml.safe_load(
            (self.upstream / "robots/active_dof_maps.yml").read_text()
        )
        mapping = maps["robots"][row["robot_key"]]
        card = kinematics(self.assets / mapping["urdf_path"].removeprefix("Bench2Dex/"))
        card["urdf_to_runtime_joint_names"] = mapping.get("name_sanitize", {})
        active = set(mapping["active_joint_names"])
        mimics = {
            card["urdf_to_runtime_joint_names"].get(j["name"], j["name"])
            for j in card["joints"]
            if "mimic" in j
        }
        card["inactive_joint_positions"] = {
            n: 0.0
            for n in mapping["full_joint_names"]
            if n not in active and n not in mimics
        }
        self.kinematic_card = card
        return scene, row

    def start(self, task: Task) -> dict:
        """Launch the pinned simulator and wait for the first filtered input."""
        if self.task is not None or self._stop.is_set():
            raise ValueError("native runtime owns only one episode")
        scene, row = self._verify(task)
        self.task = task
        self.directory.mkdir(parents=True, exist_ok=False)
        output = self.directory / "benchmark"
        self._listener = socket.socket()
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(1)
        self._listener.settimeout(0.2)
        self._kit_cache = tempfile.TemporaryDirectory(prefix="bench2dex-kit-")
        command = [
            str(self.python),
            "-P",
            str(Path(__file__).with_name("native_entry.py")),
            "--upstream",
            str(self.upstream),
            "--task",
            str(scene),
            "--robot-key",
            row["robot_key"],
            "--policy-type",
            "REMOTE",
            "--remote-port",
            str(self._listener.getsockname()[1]),
            "--kit_args",
            f"--portable-root {self._kit_cache.name} "
            f"--/rtx-transient/resourcemanager/localTextureCachePath={self._kit_cache.name}/texturecache",
            "--enable-rgb",
            "--headless",
            "--active-dof",
            "--early-stop",
            "--episode-steps",
            str(task.max_steps),
            "--warmup-steps",
            str(PROTOCOL["warmup_steps"]),
            "--num-episodes",
            "1",
            "--start-episode",
            str(task.seed),
            "--seed",
            str(PROTOCOL["seed"]),
            "--inv-cov-seed",
            str(PROTOCOL["inv_cov_seed"]),
            "--generalization-profile",
            "inv_cov",
            "--enable-generalization",
            "--generalization-config",
            str(self.upstream / PROTOCOL["generalization_config"]),
            "--generalization-split",
            "unseen",
            "--output-dir",
            str(output),
            "--policy-name",
            "roborsi",
            "--record-dir",
            str(self.directory / "trajectories"),
            "--record-all",
            "--deployment-profile",
            PROTOCOL["deployment_profile"],
            "--camera-profile",
            PROTOCOL["observation_profile"],
        ]
        env = dict(os.environ)
        for key in (
            "DEX2BENCH_HEADLESS_DISABLE_ACTIVE_VIEWPORT",
            "DEX2BENCH_HEADLESS_RENDERING_MODE",
        ):
            if env.get(key) not in (None, "", "0"):
                raise ValueError(f"undeclared renderer override: {key}")
        cache = Path(self._kit_cache.name)
        for directory in ("home", "cache", "config", "matplotlib", "texturecache"):
            (cache / directory).mkdir()
        env.update(
            HOME=str(cache / "home"),
            XDG_CACHE_HOME=str(cache / "cache"),
            XDG_CONFIG_HOME=str(cache / "config"),
            MPLCONFIGDIR=str(cache / "matplotlib"),
            TORCH_EXTENSIONS_DIR=str(cache / "torch-extensions"),
            WARP_CACHE_PATH=str(cache / "warp"),
            PYTHONPATH=str(Path(__file__).resolve().parents[2]),
            PYTHONHASHSEED="0",
            PYTHONDONTWRITEBYTECODE="1",
            DEX2BENCH_DATASET_ROOT=str(self.assets),
            SAVE_STEP_IMAGES="",
            SAVE_INFERENCE_PREFLIGHT="",
        )
        (self.directory / "launch.json").write_text(
            json.dumps({"argv": command, "task": task.as_dict()}, indent=2)
        )
        self._log = (self.directory / "simulator.log").open("wb")
        self._thread = threading.Thread(
            target=self._serve, daemon=True, name="bench2dex-native-rpc"
        )
        self._thread.start()
        self._started_at = time.monotonic()
        try:
            self._process = subprocess.Popen(
                command,
                cwd=self.upstream,
                env=env,
                stdout=self._log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            raw = self._next()
            if raw is None:
                raise RuntimeError("native episode ended before its first observation")
            return raw
        except BaseException:
            self.close()
            raise

    def _serve(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    connection, _ = self._listener.accept()
                    break
                except TimeoutError:
                    continue
            else:
                return
            self._connection = connection
            reset = False
            with connection:
                while not self._stop.is_set():
                    message = recv_message(connection)
                    if message is None:
                        return
                    kind = message.get("command")
                    if kind == "reset":
                        if reset:
                            raise ValueError("unexpected second native reset")
                        reset = True
                        send_message(connection, {"result": None})
                    elif kind in ("get_action_chunk", "update_after_action"):
                        if not reset:
                            raise ValueError("native observation before reset")
                        self._events.put(
                            (kind == "get_action_chunk", message["observation"])
                        )
                        command = self._commands.get()
                        if command is None:
                            return
                        send_message(connection, command)
                    elif kind == "close":
                        send_message(connection, {"result": None})
                        return
                    else:
                        raise ValueError("unknown native RPC operation")
        except Exception as exc:
            if not self._stop.is_set():
                self._events.put(exc)

    def _next(self) -> dict | None:
        deadline = time.monotonic() + self.timeout_s
        while not self._stop.is_set():
            try:
                event = self._events.get(timeout=0.1)
            except queue.Empty:
                if self._process is not None and self._process.poll() is not None:
                    self._read_result()
                    return None
                if time.monotonic() >= deadline:
                    raise TimeoutError("native simulator observation timeout")
                continue
            if isinstance(event, Exception):
                raise RuntimeError("native RPC failed") from event
            self._expects_chunk, raw = event
            if self._expects_chunk != (self._remaining_chunk == 0):
                raise RuntimeError(
                    "native chunk boundary differs from submitted actions"
                )
            return raw
        raise RuntimeError("native runtime was closed")

    def advance(self, action: dict) -> dict | None:
        """Execute one row while preserving upstream chunk request semantics."""
        if (
            self.task is None
            or self.result is not None
            or self.steps >= self.task.max_steps
        ):
            raise ValueError("no active native control interval")
        if self._expects_chunk:
            chunk = validate_chunk(action, self.task, self.task.max_steps - self.steps)
            self._remaining_chunk = len(chunk)
            reply: Any = chunk
        else:
            if action != {"continue": True}:
                raise ValueError("cannot replace an open-loop chunk mid-execution")
            reply = None
        self._remaining_chunk -= 1
        self.steps += 1
        self._commands.put({"result": reply})
        return self._next()

    def stop_policy(self) -> None:
        """Use the original RPC error route for a verified policy failure."""
        if self.task is None or self.result is not None or not self._expects_chunk:
            raise ValueError("policy failure is valid only at an inference boundary")
        self.policy_failed = True
        self._commands.put({"error": "Policy infrastructure failure"})
        if self._next() is not None:
            raise RuntimeError("native runtime continued after policy failure")

    def _read_result(self) -> None:
        if self._process.returncode != 0:
            raise RuntimeError("native simulator failed; inspect its private log")
        path = self.directory / "benchmark/per_episode.jsonl"
        rows = [
            json.loads(line) for line in path.read_text().splitlines() if line.strip()
        ]
        rendering = json.loads((self.directory / "rendering.json").read_text())
        if len(rows) != 1 or rows[0].get("episode_index") != self.task.seed:
            raise RuntimeError("native result identity/count mismatch")
        if rendering.get("status") != "passed" or rendering.get("dependencies", {}).get(
            "unresolved"
        ):
            raise RuntimeError("native rendering validation did not pass")
        if classify_result(rows[0]) == "infrastructure_error" and not (
            self.policy_failed and rows[0].get("terminated_reason") == "error"
        ):
            raise RuntimeError("native run did not produce a valid scored outcome")
        self.result = rows[0]

    def close(self) -> None:
        """Release sockets and the native process, including failed startup."""
        self._stop.set()
        self._commands.put(None)
        if self._connection is not None:
            try:
                self._connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if self._listener is not None:
            self._listener.close()
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=10)
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self._log is not None:
            self._log.close()
        if self._kit_cache is not None:
            self._kit_cache.cleanup()
