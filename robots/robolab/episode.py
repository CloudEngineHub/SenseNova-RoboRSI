# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Map complete EEF motions to native frames and public HTTP observations."""

from __future__ import annotations

import hashlib
import json
import math
import traceback
from pathlib import Path
from typing import Any

from roborsi.evaluation.media import CaseMediaChannel
from roborsi.evaluation.messages import (
    Action,
    NativeResult,
    Observation,
    StartResult,
    StepResult,
    Task,
)
from robots.robolab.contracts import validate_task
from robots.robolab.motion import interpolate_actions, robot_state, validate_target
from robots.robolab.observations import CAMERAS, png_bytes


class RoboLabEpisode:
    """Count decisions and physical control steps separately; stop at native done."""

    def __init__(self, directory: Path, runtime: Any) -> None:
        self.directory, self.runtime = directory, runtime
        (directory / "native").mkdir(parents=True, exist_ok=True)
        self.media = CaseMediaChannel(directory / "media")
        self.task: Task | None = None
        self.episode_id = ""
        self.decisions = self.control_steps = 0
        self.ended = self.closed = False
        self.values: dict | None = None
        self.result: NativeResult | None = None

    def _observation(self, *, executed_steps: int = 0) -> Observation:
        data = {
            **robot_state(self.values),
            "instruction": self.task.instruction,
            "control_step": self.control_steps,
            "remaining_steps": self.task.max_steps - self.control_steps,
            "max_steps": self.task.max_steps,
            "control_dt": self.task.native["control_dt"],
            "executed_steps": executed_steps,
            "done": self.ended,
            "media_fields": {name: index for index, name in enumerate(CAMERAS)},
        }
        refs = tuple(
            self.media.write(
                self.episode_id,
                self.decisions,
                png_bytes(self.values[name]),
                "image/png",
            )
            for name in CAMERAS
        )
        return Observation(
            benchmark="robolab",
            episode_id=self.episode_id,
            step_index=self.decisions,
            data=data,
            media=refs,
        )

    def start(self, task: Task, episode_id: str) -> StartResult:
        if self.task is not None or self.closed:
            raise RuntimeError("RoboLab episode already used")
        validate_task(task)
        self.task, self.episode_id = task, episode_id
        try:
            self.values = self.runtime.start(task)
            return StartResult(
                task=task,
                observation=self._observation(),
                capabilities=task.capabilities,
            )
        except BaseException:
            traceback.print_exc()
            self.close()
            raise

    def step(self, action: Action) -> StepResult:
        """Validate before moving, interpolate once, then respect early termination."""
        if self.task is None or self.closed or self.ended:
            raise RuntimeError("RoboLab episode is not active")
        if (action.benchmark, action.episode_id, action.step_index) != (
            "robolab",
            self.episode_id,
            self.decisions,
        ):
            raise ValueError("RoboLab action identity or sequence differs")
        target = validate_target(
            action.data, remaining_steps=self.task.max_steps - self.control_steps
        )
        rows = interpolate_actions(
            self.values["position"], self.values["quaternion"], target
        )
        executed = 0
        terminated = truncated = False
        with (self.directory / "native/actions.jsonl").open("a") as log:
            for row in rows:
                values, terminated, truncated = self.runtime.step(row.tolist())
                if type(terminated) is not bool or type(truncated) is not bool:
                    raise ValueError(
                        "native termination flags must be explicit booleans"
                    )
                self.values = values
                self.control_steps += 1
                executed += 1
                self.ended = terminated or truncated
                log.write(
                    json.dumps(
                        {
                            "control_step": self.control_steps,
                            "action": row.tolist(),
                            "native_done": self.ended,
                            "terminated": terminated,
                            "truncated": truncated,
                        }
                    )
                    + "\n"
                )
                if self.ended:
                    break
                if self.control_steps == self.task.max_steps:
                    raise RuntimeError(
                        "native time limit did not terminate the environment"
                    )
        self.decisions += 1
        return StepResult(
            observation=self._observation(executed_steps=executed),
            terminated=terminated,
            truncated=truncated,
            termination_reason=("native_terminal" if terminated else "time_limit")
            if self.ended
            else None,
        )

    def finish(self) -> NativeResult:
        """Publish native evidence; a model's completion cannot grant success."""
        if self.result is not None:
            return self.result
        if self.task is None or not self.ended or self.closed:
            raise RuntimeError("finish requires a terminated RoboLab episode")
        native = self.runtime.finish()
        if type(native.get("success")) is not bool:
            raise ValueError("missing native success")
        score = native.get("score")
        if type(score) not in (int, float) or not math.isfinite(score):
            raise ValueError("missing finite native score")
        # Native trajectory diagnostics can contain NaN for a stationary trace.
        # Keep their original bytes as an artifact, but do not put non-JSON
        # diagnostics into the public result or reinterpret them as scores.
        reported = {key: value for key, value in native.items() if key != "metrics"}
        metrics = native.get("metrics", {})
        reported["metrics"] = {
            key: value if type(value) in (int, float) and math.isfinite(value) else None
            for key, value in metrics.items()
        }
        details = {
            "native": reported,
            "control_steps": self.control_steps,
            "decision_steps": self.decisions,
        }
        path = self.directory / "native/result.json"
        path.write_text(json.dumps(details, indent=2, allow_nan=False) + "\n")
        self.result = NativeResult(
            task=self.task,
            episode_id=self.episode_id,
            success=native["success"],
            score=float(score),
            details=details,
            source="native/result.json",
            source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        return self.result

    def close(self) -> None:
        if not self.closed:
            self.runtime.close()
            self.closed = True
