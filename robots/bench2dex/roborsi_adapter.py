# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Preserve the native sensor, chunk, termination and scoring boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from roborsi.evaluation.http_artifacts import ArtifactPublisher
from roborsi.evaluation.media import CaseMediaChannel
from roborsi.evaluation.messages import (
    Action,
    EpisodeStop,
    NativeResult,
    Observation,
    StartResult,
    StepResult,
    Task,
)

from .contracts import PROTOCOL, TASKS, file_sha256, validate_task
from .reference.core import classify_result, save_observation, write_json


class Bench2DexAdapter:
    """Adapt one private simulator without putting native scores in tool feedback."""

    def __init__(
        self,
        directory: Path,
        artifacts: ArtifactPublisher,
        *,
        runtime_factory: Callable,
    ) -> None:
        self.directory, self.artifacts = directory, artifacts
        self.runtime = runtime_factory(directory / "native/runtime")
        self.media = CaseMediaChannel(directory / "media")
        self.task: Task | None = None
        self.episode_id: str | None = None
        self.step_index = 0
        self.ended = False
        self.closed = False
        self.policy_failed = False
        self._card: dict | None = None
        self._robot_metadata: dict | None = None

    def start(self, task: Task, episode_id: str) -> StartResult:
        """Validate identity, reset once, and expose only deployment information."""
        if self.task is not None or self.closed:
            raise ValueError("adapter owns one episode")
        validate_task(task)
        self.task, self.episode_id = task, episode_id
        try:
            raw = self.runtime.start(task)
            return StartResult(
                task=task,
                observation=self._observation(raw),
                capabilities=task.capabilities,
            )
        except BaseException:
            self.close()
            raise

    def _observation(self, raw: dict) -> Observation:
        if raw["language"] != self.task.instruction:
            raise ValueError("native instruction changed")
        metadata = raw["robot_metadata"]
        allowed = {
            "robot_key",
            "active_joint_names",
            "position_limits",
            "action_semantics",
            "joint_units",
            "physics_hz",
            "policy_hz",
        }
        if (
            set(metadata) != allowed
            or metadata["robot_key"] != self.task.native["robot_key"]
        ):
            raise ValueError("invalid robot information boundary")
        if (
            len(metadata["active_joint_names"]) != TASKS[self.task.task_id]["dof"]
            or metadata["physics_hz"] != 60
            or metadata["policy_hz"] != 20
        ):
            raise ValueError("native joint dimension or control clock changed")
        if self._card is None:
            self._robot_metadata = json.loads(json.dumps(metadata))
            self._card = {
                **self._robot_metadata,
                "kinematics": self.runtime.kinematic_card,
            }
            self._card["inactive_joint_positions"] = self.runtime.kinematic_card[
                "inactive_joint_positions"
            ]
            names = self.runtime.kinematic_card.get("urdf_to_runtime_joint_names", {})
            kinds = {
                names.get(j["name"], j["name"]): j["type"]
                for j in self.runtime.kinematic_card["joints"]
            }
            self._card["resolved_joint_units"] = [
                "metre" if kinds[n] == "prismatic" else "radian"
                for n in metadata["active_joint_names"]
            ]
        elif metadata != self._robot_metadata:
            raise ValueError("robot metadata changed within an episode")
        public_root = self.directory / "native/public-input"
        sample = save_observation(
            public_root,
            self.step_index,
            raw,
            PROTOCOL["observation_profile"],
            len(metadata["active_joint_names"]),
            self.task.max_steps - self.step_index,
            path_prefix="input/",
            calibrated=True,
        )
        references = []
        for camera in sample["cameras"]:
            relative = camera["path"].removeprefix("input/")
            reference = self.media.write(
                self.episode_id,
                self.step_index,
                (public_root / relative).read_bytes(),
                "image/png",
            )
            self.artifacts.publish(
                reference.ref,
                "image",
                reference.mime_type,
                step_index=self.step_index,
                sha256=reference.sha256,
                size_bytes=reference.size_bytes,
            )
            references.append(reference)
        return Observation(
            benchmark="bench2dex",
            episode_id=self.episode_id,
            step_index=self.step_index,
            data={"sample": sample, "robot": self._card},
            media=tuple(references),
        )

    def step(self, action: Action) -> StepResult:
        """Advance one 20 Hz interval; all native chunk scheduling stays private."""
        if self.task is None or self.ended or self.closed:
            raise ValueError("adapter has no active episode")
        if (action.benchmark, action.episode_id, action.step_index) != (
            "bench2dex",
            self.episode_id,
            self.step_index,
        ):
            raise ValueError("action identity or order mismatch")
        raw = self.runtime.advance(action.data)
        self.step_index += 1
        if raw is not None:
            if self.step_index >= self.task.max_steps:
                raise RuntimeError("native runtime exceeded its policy budget")
            return StepResult(
                observation=self._observation(raw), terminated=False, truncated=False
            )
        self.ended = True
        # Exactly the original generic terminal message: no post-terminal image,
        # success flag, reward, object state, native reason or reset metadata.
        return StepResult(
            observation=Observation(
                benchmark="bench2dex",
                episode_id=self.episode_id,
                step_index=self.step_index,
                data={"episode_done": True},
            ),
            terminated=True,
            truncated=False,
            termination_reason="episode_ended",
            reward=None,
            native={},
        )

    def stop(self, request: EpisodeStop) -> StepResult:
        """Score invalid/early-ended policies through the original RPC error path."""
        if (
            self.task is None
            or self.ended
            or self.closed
            or (
                request.benchmark,
                request.episode_id,
                request.step_index,
            )
            != ("bench2dex", self.episode_id, self.step_index)
        ):
            raise ValueError("policy stop identity/order mismatch")
        if request.reason != "policy_failure" or request.details:
            raise ValueError("only an explicit policy failure is a scored stop")
        self.runtime.stop_policy()
        self.policy_failed = True
        self.ended = True
        return StepResult(
            observation=Observation(
                benchmark="bench2dex",
                episode_id=self.episode_id,
                step_index=self.step_index,
                data={"episode_done": True},
            ),
            terminated=True,
            truncated=False,
            termination_reason="episode_ended",
        )

    def finish(self) -> NativeResult:
        """Publish the authoritative outcome separately from Agent feedback."""
        if not self.ended or self.runtime.result is None:
            raise RuntimeError(
                "native scoring is unavailable for an incomplete episode"
            )
        row = self.runtime.result
        success = classify_result(row) == "success" and not self.policy_failed
        evidence = {
            "success": success,
            "official_success": row["success"],
            "policy_failure": self.policy_failed,
            "terminated_reason": row["terminated_reason"],
            "steps": row.get("steps"),
            "stable_success_step": row.get("stable_success_step"),
            "policy_steps": self.step_index,
            "policy_query_count": row.get("policy_query_count"),
            "metrics": {
                k: v
                for k, v in row.items()
                if k
                not in {"scene", "scene_generalization_sample", "timeseries", "error"}
            },
            "episode_index": self.task.seed,
            "smoke_only": self.task.native["smoke_only"],
            "eligible_for_evaluation": not self.task.native["smoke_only"],
        }
        path = self.directory / "native/result.json"
        write_json(path, evidence)
        self.artifacts.publish(
            "native/result.json", "native_result", "application/json"
        )
        return NativeResult(
            task=self.task,
            episode_id=self.episode_id,
            success=success,
            score=float(success),
            details=evidence,
            source="native/result.json",
            source_sha256=file_sha256(path),
        )

    def close(self) -> None:
        """Release simulator resources once, including cancelled episodes."""
        if not self.closed:
            self.closed = True
            self.runtime.close()
