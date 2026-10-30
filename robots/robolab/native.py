# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Run the pinned native DROID environment on its process's main thread."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from pathlib import Path

from roborsi.evaluation.messages import Task
from robots.robolab.contracts import validate_task
from robots.robolab.observations import extract_observation


def native_root() -> Path:
    return Path(os.environ.get("ROBORSI_ROBOLAB_ROOT", "/opt/RoboLab")).resolve()


def verify_native_source(root: Path) -> None:
    """Verify the native evaluation source, including the historical scorer."""
    manifest = json.loads(Path(__file__).with_name("native_files.json").read_text())
    for name, digest in manifest["files"].items():
        path = root / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"RoboLab native source differs: {name}")


class RoboLabRuntime:
    """Own one simulator, two native resets and the original evaluation scorer."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory / "native"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.env = self.app = None
        self.task = self.cfg = self.raw = None
        self.steps = 0
        self._result = None

    def start(self, task: Task) -> dict:
        """Create exactly one DROID task; never override its configured horizon."""
        validate_task(task)
        root = native_root()
        verify_native_source(root)
        sys.path.insert(0, str(root))
        import cv2  # noqa: F401 -- must precede Isaac Lab imports
        from isaaclab.app import AppLauncher

        cache = self.directory / "kit"
        cache.mkdir()
        self.app = AppLauncher(
            headless=True,
            enable_cameras=True,
            device="cuda:0",
            kit_args=f"--portable-root {cache} --/renderer/multiGpu/enabled=false",
        ).app
        import robolab
        from robolab.constants import set_output_dir
        from robolab.core.environments.runtime import create_env
        from robolab.registrations.droid.auto_env_registrations_abs_ik import (
            auto_register_droid_abs_ik_envs,
        )

        if not Path(robolab.__file__).resolve().is_relative_to(root):
            raise ValueError(
                "a different RoboLab installation shadows the pinned source"
            )
        auto_register_droid_abs_ik_envs(task_dirs=["benchmark"], task=[task.task_id])
        set_output_dir(str(self.directory))
        self.env, self.cfg = create_env(
            task.task_id,
            device="cuda:0",
            seed=task.seed,
            num_envs=1,
            instruction_type="default",
            policy="harness",
            renderer="realtime",
        )
        self.task = task
        if (
            self.cfg.instruction != task.instruction
            or int(self.env.max_episode_length) != task.max_steps
            or not math.isclose(self.cfg.sim.dt * self.cfg.decimation, 1 / 15)
        ):
            raise ValueError(
                "native instruction, budget or control period differs from catalog"
            )
        self.raw, _ = self.env.reset()
        self.raw, _ = self.env.reset()
        self.env.recorder_manager.set_hdf5_file("run_0.hdf5")
        self.env.recorder_manager.set_episode_index(0, env_ids=[0])
        return extract_observation(self.raw)

    def step(self, row: list[float]) -> tuple[dict, bool, bool]:
        """Execute one physical frame using RoboLab's absolute IK action manager."""
        import torch

        if self.env is None or self._result is not None:
            raise RuntimeError("RoboLab native environment is not active")
        self.raw, _, terminated, truncated, _ = self.env.step(
            torch.tensor([row], dtype=torch.float32, device=self.env.device)
        )
        self.steps += 1
        terminal, timeout = bool(terminated[0]), bool(truncated[0])
        if bool(self.env.all_terminated) != (terminal or timeout):
            raise RuntimeError("native freeze and termination flags disagree")
        return extract_observation(self.raw), terminal, timeout

    def finish(self) -> dict:
        """Return native scoring only after recording finalization succeeds."""
        if self._result is not None:
            return self._result
        from robolab.eval.summarize import summarize_run

        results = self.env.get_env_results()
        if len(results) != 1 or type(results[0].get("success")) is not bool:
            raise RuntimeError("RoboLab has not produced a native terminal result")
        path = self.directory / "episode_results.jsonl"
        summarize_run(
            env_results=results,
            msgs=[],
            env=self.env,
            env_cfg=self.cfg,
            num_envs=1,
            run_idx=0,
            run_name=f"{self.task.task_id}_0",
            task_env=self.task.task_id,
            scene_output_dir=str(self.directory),
            policy="harness",
            episode_results=[],
            episode_results_file=str(path),
            enable_subtask_progress=True,
            instruction_type="default",
        )
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        if len(rows) != 1:
            raise RuntimeError("native scorer must produce exactly one result")
        result = rows[0]
        score = result.get("score")
        if type(score) not in (int, float) or not math.isfinite(score):
            raise RuntimeError("RoboLab did not produce a finite native subtask score")
        # Finish must acknowledge durable records before app.close() exits Kit.
        self.env.recorder_manager.close()
        self._result = result
        return result

    def close(self) -> None:
        """Release native resources even if environment creation or scoring failed."""
        try:
            if self.env is not None:
                self.env.close()
                self.env = None
        finally:
            if self.app is not None:
                self.app.close()
                self.app = None


def make_runtime(directory: Path) -> RoboLabRuntime:
    return RoboLabRuntime(directory)
