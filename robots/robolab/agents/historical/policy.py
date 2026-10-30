# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Historical sequential RoboLab episode protocol and Codex policy."""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from pathlib import Path

from robots.robolab.motion import interpolate_actions, positive_int, validate_target

from .episode_stats import EpisodeStats

ACTION_REPRESENTATION = "robolab_base_link_absolute_xyz_quat_wxyz_gripper"
PROTOCOL_VERSION = 2
logger = logging.getLogger(__name__)


class EpisodePolicy:
    def __init__(self, backend, log_path: Path, *, image_size: int = 320) -> None:
        self.backend = backend
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.stats_path = self.log_path.with_name(
            f"{self.log_path.stem}.episodes.jsonl"
        )
        self._episode_stats = None
        self.metadata = {
            "policy": "harness",
            "protocol_version": PROTOCOL_VERSION,
            "model": backend.model,
            "backend": backend.backend,
            "reasoning_effort": backend.reasoning_effort,
            "auth": backend.auth,
            "action_representation": ACTION_REPRESENTATION,
            "action_dim": 8,
            "image_size": image_size,
            "supports_batch_inference": False,
        }
        self._episode_id = None
        self._next_step = 0
        self._last_control_step = self._expected_control_step = 0
        self._failed = self._ended = False
        self._episode_count = 0
        self._disconnected = threading.Event()

    def connect(self) -> None:
        self._disconnected.clear()

    def disconnect(self) -> None:
        self._disconnected.set()
        self.abort()

    def infer(self, request: dict) -> dict:
        started = time.monotonic()
        record = {
            key: request.get(key)
            for key in (
                "type",
                "episode_id",
                "decision_step",
                "control_step",
                "instruction",
                "reason",
            )
        }
        record.update(
            {
                key: self.metadata[key]
                for key in ("model", "backend", "reasoning_effort", "auth")
            }
        )
        called_backend = False
        confirmed_control_step = None
        try:
            if self._disconnected.is_set():
                raise RuntimeError("Harness client disconnected")
            ending = request.get("type") == "end_episode"
            if request.get("type") not in ("infer", "end_episode"):
                raise ValueError("Expected infer or end_episode request")
            episode_id = request["episode_id"]
            if not isinstance(episode_id, str) or not episode_id:
                raise ValueError("A nonempty episode_id is required")
            if request.get("env_id") != 0:
                raise ValueError("The minimal harness supports only env_id=0")
            if episode_id != self._episode_id:
                if (
                    ending
                    or request["decision_step"] != 0
                    or request["control_step"] != 0
                ):
                    raise ValueError(
                        "A new episode must start at decision_step=0 and control_step=0"
                    )
                if self._episode_id is not None and not (self._ended or self._failed):
                    raise ValueError("End the previous episode before starting another")
                instruction = request["instruction"]
                if not isinstance(instruction, str) or not instruction.strip():
                    raise ValueError("A nonempty task instruction is required")
                self._max_steps = positive_int(request["max_steps"], "max_steps")
                self._control_dt = float(request["control_dt"])
                if not math.isfinite(self._control_dt) or self._control_dt <= 0:
                    raise ValueError("control_dt must be positive and finite")
                self._episode_id, self._instruction = episode_id, instruction
                self._next_step = self._last_control_step = (
                    self._expected_control_step
                ) = 0
                self._failed = self._ended = False
                self._episode_count += 1
                self._record_stats("start", started=started)
                self._start_episode()
            if self._failed:
                raise RuntimeError(
                    "This episode already had an execution error; no retry is allowed"
                )
            if self._ended:
                raise ValueError("This episode has already ended")
            if request["decision_step"] != self._next_step:
                raise ValueError(
                    "Out-of-order or repeated decision; no resampling is allowed"
                )
            control_step = request["control_step"]
            if isinstance(control_step, bool) or not isinstance(control_step, int):
                raise ValueError("control_step must be an integer")
            if ending:
                if (
                    not self._last_control_step
                    <= control_step
                    <= self._expected_control_step
                ):
                    raise ValueError("Invalid final control_step")
                if request["reason"] not in (
                    "native_terminal",
                    "time_limit",
                    "execution_error",
                ):
                    raise ValueError("Invalid episode end reason")
                confirmed_control_step = control_step
                called_backend = True
                result = self._end_episode(request)
                self._ended = True
                record.update(
                    status="ended",
                    executed_steps=control_step - self._last_control_step,
                    **result,
                )
                return {"ended": True, **result}
            if (
                control_step != self._expected_control_step
                or control_step >= self._max_steps
            ):
                raise ValueError(
                    "Unexpected control_step or episode step budget exhausted"
                )
            if request["instruction"] != self._instruction:
                raise ValueError("The task instruction cannot change within an episode")
            if (
                request["max_steps"] != self._max_steps
                or request["control_dt"] != self._control_dt
            ):
                raise ValueError("Episode limits cannot change within an episode")
            confirmed_control_step = control_step
            called_backend = True
            target = self._validate_target(
                self._act(request), remaining_steps=self._max_steps - control_step
            )
            observation = request["observation"]
            actions = self._encode_actions(observation, target)
            record.update(
                status="ok",
                target=target,
                actions=actions.tolist(),
                executed_steps=control_step - self._last_control_step,
            )
            self._last_control_step = control_step
            self._expected_control_step = control_step + len(actions)
            self._next_step += 1
            return {"actions": actions}
        except BaseException as error:
            self._failed = True
            self.abort()
            record.update(
                status="execution_error",
                error_type=type(error).__name__,
                error=str(error),
            )
            raise
        finally:
            finished = time.monotonic()
            record["elapsed_ms"] = (finished - started) * 1000
            if called_backend and (not ending or self.metadata["backend"] == "codex"):
                record.update(self._diagnostics())
            with self.log_path.open("a") as log:
                log.write(json.dumps(record, allow_nan=False) + "\n")
            self._record_stats(
                "request",
                record=record,
                finished=finished,
                called_backend=called_backend,
                confirmed_control_step=confirmed_control_step,
            )

    def _validate_target(self, target: dict, *, remaining_steps: int) -> dict:
        return validate_target(target, remaining_steps=remaining_steps)

    def _encode_actions(self, observation: dict, target: dict):
        return interpolate_actions(
            observation["position"], observation["quaternion"], target
        )

    def _record_stats(self, operation: str, **values) -> None:
        """Statistics never participate in model input or execution control."""
        try:
            if operation == "start":
                self._episode_stats = None
                self._episode_stats = EpisodeStats(
                    log_path=self.log_path,
                    stats_path=self.stats_path,
                    metadata=self.metadata,
                    episode_id=self._episode_id,
                    episode_index=self._episode_count,
                    instruction=self._instruction,
                    max_steps=self._max_steps,
                    control_dt=self._control_dt,
                    **values,
                )
            elif self._episode_stats is not None and not self._episode_stats.finalized:
                if operation == "request":
                    self._episode_stats.request(
                        disconnected=self._disconnected.is_set(), **values
                    )
                elif operation == "close":
                    self._episode_stats.finish(
                        "interrupted",
                        "disconnected"
                        if self._disconnected.is_set()
                        else "server_closed",
                        time.monotonic(),
                    )
        except Exception:
            # A broken accumulator must not later publish an apparently complete
            # result, nor affect returned actions, original errors, or cleanup.
            self._episode_stats = None
            try:
                logger.warning(
                    "Episode statistics unavailable for %s (%s)",
                    self._episode_id,
                    operation,
                    exc_info=True,
                )
            except Exception:
                pass  # Even a failing logging handler must not affect execution.

    def abort(self) -> None:
        """Wake an in-flight request when its WebSocket disconnects."""

    def close(self) -> None:
        self.abort()
        if self._episode_id is not None and not (self._ended or self._failed):
            self._failed = True
            with self.log_path.open("a") as log:
                log.write(
                    json.dumps(
                        {
                            "episode_id": self._episode_id,
                            "status": "interrupted",
                        }
                    )
                    + "\n"
                )


class CodexPolicy(EpisodePolicy):
    def __init__(self, backend, log_path: Path, *, image_size: int = 320) -> None:
        super().__init__(backend, log_path, image_size=image_size)
        backend.connection_cancelled = self._disconnected

    def _start_episode(self) -> None:
        directory = self.log_path.with_suffix("") / f"episode-{self._episode_count:04d}"
        self.backend.start_episode(
            self._instruction,
            max_steps=self._max_steps,
            control_dt=self._control_dt,
            log_dir=directory,
        )

    def _act(self, request: dict) -> dict:
        return self.backend.act(
            request["observation"], control_step=request["control_step"]
        )

    def _end_episode(self, request: dict) -> dict:
        return {
            "codex_finish": self.backend.end_episode(
                request["observation"],
                control_step=request["control_step"],
                reason=request["reason"],
            )
        }

    def _diagnostics(self) -> dict:
        return {
            "model_output": self.backend.last_response_text,
            "usage": self.backend.last_usage,
            "codex_events_path": str(self.backend.events_path),
            "codex_stderr_path": str(self.backend.stderr_path),
        }

    def abort(self) -> None:
        self.backend.abort()

    def close(self) -> None:
        super().close()
        self.backend.close()
        self._record_stats("close")
