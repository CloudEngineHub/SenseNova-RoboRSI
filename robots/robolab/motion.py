# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Validate absolute EEF targets and interpolate robot-root poses."""

from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation, Slerp


def finite_vector(value, size: int, name: str) -> np.ndarray:
    vector = np.asarray(value, dtype=np.float64)
    if vector.shape != (size,) or not np.isfinite(vector).all():
        raise ValueError(f"{name} must contain {size} finite numbers")
    return vector


def unit_quaternion(value) -> np.ndarray:
    quaternion = finite_vector(value, 4, "quaternion (wxyz)")
    norm = np.linalg.norm(quaternion)
    if not np.isfinite(norm) or norm < 1e-8:
        raise ValueError("quaternion must have a nonzero finite norm")
    return quaternion / norm


def positive_int(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def robot_state(observation: dict) -> dict:
    """Select public proprioception; never forward arbitrary simulator fields."""
    state = {
        "position": finite_vector(observation["position"], 3, "position").tolist(),
        "quaternion": unit_quaternion(observation["quaternion"]).tolist(),
        "joint_positions": finite_vector(
            observation["joint_positions"], 7, "joint_positions"
        ).tolist(),
        "gripper": float(finite_vector([observation["gripper"]], 1, "gripper")[0]),
    }
    if not 0 <= state["gripper"] <= 1:
        raise ValueError("Observed gripper must be in [0, 1]")
    return state


def validate_target(target: dict, *, remaining_steps: int | None = None) -> dict:
    if not isinstance(target, dict) or set(target) != {
        "position",
        "quaternion",
        "gripper",
        "steps",
    }:
        raise ValueError(
            "Target must contain only position, quaternion, gripper, and steps"
        )
    position = finite_vector(target["position"], 3, "position")
    quaternion = unit_quaternion(target["quaternion"])
    gripper = target["gripper"]
    if isinstance(gripper, bool) or gripper not in (0, 1):
        raise ValueError("Target gripper must be 0 (open) or 1 (closed)")
    steps = positive_int(target["steps"], "steps")
    if remaining_steps is not None and steps > remaining_steps:
        raise ValueError("steps cannot exceed the remaining episode steps")
    return {
        "position": position.tolist(),
        "quaternion": quaternion.tolist(),
        "gripper": int(gripper),
        "steps": steps,
    }


def interpolate_actions(position, quaternion, target: dict) -> np.ndarray:
    """Return H x 8 actions: xyz, quaternion wxyz, binary gripper.

    The first action advances 1/H toward the target; the final action is the
    target. Pose commands are for the same control point as the observation.
    """
    start_position = finite_vector(position, 3, "current position")
    start_quaternion = unit_quaternion(quaternion)
    target = validate_target(target)
    horizon = target["steps"]
    fractions = np.arange(1, horizon + 1, dtype=np.float64) / horizon
    positions = start_position + fractions[:, None] * (
        np.asarray(target["position"]) - start_position
    )
    # SciPy expects xyzw; RoboLab and the model use wxyz.
    rotations = Rotation.from_quat(
        np.array([start_quaternion, target["quaternion"]])[:, [1, 2, 3, 0]]
    )
    quaternions = Slerp([0.0, 1.0], rotations)(fractions).as_quat()[:, [3, 0, 1, 2]]
    actions = np.column_stack(
        [
            positions,
            quaternions,
            np.full(horizon, target["gripper"]),
        ]
    )
    actions = actions.astype(np.float32)
    if not np.isfinite(actions).all():
        raise ValueError("Interpolated actions must be finite float32 values")
    return actions


TARGET_SCHEMA = {
    "type": "object",
    "properties": {
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 3,
            "maxItems": 3,
        },
        "quaternion": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 4,
            "maxItems": 4,
        },
        "gripper": {"type": "integer", "enum": [0, 1]},
        "steps": {"type": "integer", "minimum": 1},
    },
    "required": ["position", "quaternion", "gripper", "steps"],
    "additionalProperties": False,
}
