# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Isolate Isaac's native owner process from the shared benchmark HTTP server."""

from __future__ import annotations

import math
import os
import shutil
import signal
import sys
import time
from pathlib import Path

from roborsi.evaluation.http_artifacts import ArtifactPublisher
from roborsi.evaluation.messages import (
    Action,
    NativeResult,
    StartResult,
    StepResult,
    Task,
)
from roborsi.utils.daemon import ProcessDaemon, pick_free_port
from roborsi.utils.rpc import make_rpc_client, wait_for_ready
from robots.robolab.contracts import validate_task


class NativeWorkerProcess(ProcessDaemon):
    """Retain the shared daemon while owning the worker's Linux process group."""

    def start(self) -> None:
        # Place the Python launcher, interpreter and Kit descendants in one
        # session. NVIDIA's python.sh keeps a shell parent, so doing setsid only
        # inside worker.main would leave its group outside this daemon's PID.
        self.cmd = ["setsid", "--", *self.cmd]
        super().start()
        self._group_id = self._proc.pid

    def _group_running(self) -> bool:
        self.poll()
        for entry in Path("/proc").iterdir():
            if not entry.name.isdecimal():
                continue
            try:
                fields = (entry / "stat").read_text().rpartition(")")[2].split()
                if int(fields[2]) == self._group_id and fields[0] not in {"Z", "X"}:
                    return True
            except (FileNotFoundError, ProcessLookupError):
                continue
        return False

    def stop(self, timeout: float = 5) -> None:
        """Clean descendants even when Kit has already exited the direct worker."""
        try:
            group = getattr(self, "_group_id", None)
            if group is not None:
                if group == os.getpgrp():
                    raise RuntimeError("native worker did not establish an owned group")
                for signum in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(group, signum)
                    except ProcessLookupError:
                        break
                    deadline = time.monotonic() + timeout
                    while self._group_running() and time.monotonic() < deadline:
                        time.sleep(0.02)
                    if not self._group_running():
                        break
                else:
                    raise TimeoutError("RoboLab native descendants survived cleanup")
        finally:
            super().stop(timeout=timeout)


class RoboLabAdapter:
    """Own one lazy native worker and transfer artifacts through public helpers."""

    def __init__(
        self,
        directory: Path,
        artifacts: ArtifactPublisher,
        *,
        factory: str = "robots.robolab.native:make_runtime",
        timeout_s: float = 3600,
    ) -> None:
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("RoboLab timeout must be finite and positive")
        self.directory, self.artifacts, self.timeout = directory, artifacts, timeout_s
        self.closed = self._cleanup_complete = False
        self._result: NativeResult | None = None
        (directory / "native").mkdir(parents=True, exist_ok=True)
        root = Path(__file__).resolve().parents[2]
        env = {
            key: value
            for key, value in os.environ.items()
            if key.startswith(
                (
                    "ROBORSI_ROBOLAB_",
                    "OMNI_",
                    "CUDA_",
                    "NVIDIA_",
                    "VK_",
                    "XDG_",
                    "__GL_",
                )
            )
            or key
            in {
                "PATH",
                "HOME",
                "LANG",
                "LC_ALL",
                "LD_LIBRARY_PATH",
                "TMPDIR",
                "PYTHONPATH",
                "ACCEPT_EULA",
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MPLCONFIGDIR",
                "TORCH_EXTENSIONS_DIR",
                "WARP_CACHE_PATH",
            }
        }
        env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONNOUSERSITE"] = "1"
        port = pick_free_port()
        self.daemon = NativeWorkerProcess(
            "robolab-native",
            [
                os.environ.get("ROBORSI_ROBOLAB_PYTHON", sys.executable),
                "-m",
                "robots.robolab.worker",
                "--port",
                str(port),
                "--directory",
                str(directory),
                "--factory",
                factory,
            ],
            cwd=str(directory),
            log_path=str(directory / "native/worker.log"),
            prepend_rlinf_path=False,
            env_overrides=env,
            inherit_environment=False,
        )
        self.rpc = make_rpc_client(f"http://127.0.0.1:{port}")
        try:
            self.daemon.start()
            wait_for_ready(self.rpc, timeout_s=30, daemon=self.daemon)
        except BaseException:
            self.close()
            raise

    def _call(self, operation: str, payload: dict) -> dict:
        if self.closed:
            raise RuntimeError("RoboLab adapter is closed")
        return self.rpc.call("request", (operation, payload), timeout_s=self.timeout)

    def _publish(self, result: StartResult | StepResult) -> None:
        for ref in result.observation.media:
            self.artifacts.publish(
                ref.ref,
                "image",
                ref.mime_type,
                step_index=result.observation.step_index,
                sha256=ref.sha256,
                size_bytes=ref.size_bytes,
            )

    def start(self, task: Task, episode_id: str) -> StartResult:
        validate_task(task)
        result = StartResult.from_dict(
            self._call("start", {"task": task.as_dict(), "episode_id": episode_id})
        )
        self._publish(result)
        return result

    def step(self, action: Action) -> StepResult:
        result = StepResult.from_dict(self._call("step", action.as_dict()))
        self._publish(result)
        return result

    def finish(self) -> NativeResult:
        if self._result is None:
            try:
                # The runtime's finish ACK includes recorder finalization.
                # App shutdown may exit Kit without replying to the cleanup RPC.
                result = NativeResult.from_dict(self._call("finish", {}))
            finally:
                self.close()
            self._result = result
        result = self._result
        self.artifacts.publish(
            result.source,
            "native_result",
            "application/json",
            sha256=result.source_sha256,
        )
        for filename, mime in (
            ("worker.log", "text/plain"),
            ("actions.jsonl", "application/x-ndjson"),
            ("episode_results.jsonl", "application/x-ndjson"),
            ("log_0_env0.json", "application/json"),
            ("env_cfg.json", "application/json"),
            ("run_0.hdf5", "application/x-hdf5"),
        ):
            path = self.directory / "native" / filename
            if path.is_file():
                self.artifacts.publish("native/" + filename, "file", mime)
        return result

    def close(self) -> None:
        """Cancel owned work, reap descendants and retain retryable cleanup state."""
        if self._cleanup_complete:
            return
        self.closed = True
        try:
            if self.daemon.poll() is None:
                try:
                    self.rpc.call("request", ("close", {}), timeout_s=5)
                    self.rpc.call("shutdown", timeout_s=1)
                except Exception:
                    pass
        finally:
            try:
                self.daemon.stop(timeout=5)
            finally:
                self.rpc.close()
        cache = self.directory / "native/kit"
        if cache.exists():
            shutil.rmtree(cache)
        self._cleanup_complete = True
