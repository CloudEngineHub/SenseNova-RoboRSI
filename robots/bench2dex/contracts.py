# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Pinned Bench2Dex task identity and public evaluation boundaries."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from roborsi.evaluation.messages import Task

ROOT = Path(__file__).resolve().parent
PROTOCOL = json.loads((ROOT / "protocol.json").read_text())
CATALOG = json.loads((ROOT / "tasks.json").read_text())
TASKS = {str(row["task_id"]): row for row in CATALOG["tasks"]}
ASSET_REVISION = "bf65215f844d1fca30750e4cc70d7266650abf0a"
ACTION_SCHEMA = {
    "oneOf": [
        {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "number"},
                    },
                }
            },
            "required": ["actions"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"continue": {"const": True}},
            "required": ["continue"],
            "additionalProperties": False,
        },
    ]
}
EVALUATION_RULES = {
    "success_metric": "native_success",
    "score_metric": "native_episode_success",
    "aggregation": "case_mean",
    "error_denominator": "expected",
}


def file_sha256(path: Path) -> str:
    """Hash an artifact without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def task_for(
    task_id: str, episode_index: int = 5, *, smoke_steps: int | None = None
) -> Task:
    """Map a RoboRSI seed to the native reset sample index, not RNG seed."""
    row = TASKS[str(task_id)]
    if type(episode_index) is not int or episode_index < 0:
        raise ValueError("episode index must be a nonnegative integer")
    if smoke_steps is not None and (
        type(smoke_steps) is not int or not 1 <= smoke_steps <= row["policy_budget"]
    ):
        raise ValueError("smoke steps must be within the native budget")
    return Task(
        benchmark="bench2dex",
        task_id=str(task_id),
        seed=episode_index,
        instruction=row["instruction"],
        max_steps=smoke_steps or row["policy_budget"],
        native={
            "episode_index": episode_index,
            "seed": PROTOCOL["seed"],
            "inv_cov_seed": PROTOCOL["inv_cov_seed"],
            "split": "unseen",
            "profile": "inv_cov",
            "robot_key": row["robot_key"],
            "scene_sha256": row["scene_sha256"],
            "official_policy_budget": row["policy_budget"],
            "smoke_only": smoke_steps is not None,
        },
        capabilities={
            "action_schema": ACTION_SCHEMA,
            "observation_channels": [
                "cam_stereo_left",
                "cam_stereo_right",
                "cam_wrist_left",
                "cam_wrist_right",
            ],
        },
    )


def validate_task(task: Task) -> dict:
    """Reject changed instruction, seed mapping, budget or capability contracts."""
    smoke = task.max_steps if task.native.get("smoke_only") is True else None
    expected = task_for(task.task_id, task.seed, smoke_steps=smoke)
    if task != expected:
        raise ValueError("task differs from the pinned Bench2Dex contract")
    return TASKS[task.task_id]


def validate_chunk(value: dict, task: Task, remaining: int) -> np.ndarray:
    """Apply the standalone finite float32 chunk validator unchanged."""
    from .reference.core import validate_actions

    return validate_actions(value, TASKS[task.task_id]["dof"], remaining)
