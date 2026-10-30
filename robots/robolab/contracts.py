# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Pinned DROID tasks, native budgets and scoring semantics."""

from __future__ import annotations

import json
from pathlib import Path

from roborsi.evaluation.messages import Task
from robots.robolab.motion import TARGET_SCHEMA

ROBOLAB_COMMIT = "92ccc0ee1984a272d4748c92ed73144fa806a6f4"
EVALUATION_RULES = {
    "success_metric": "native_success",
    "score_metric": "native_subtask_score",
    "aggregation": "case_mean",
    "error_denominator": "valid",
}
CAPABILITIES = {
    "action_schema": TARGET_SCHEMA,
    "observation_channels": ["exterior_image", "wrist_image"],
}


def catalog_tasks() -> list[Task]:
    """Expose the 120 original instructions with their unscaled native limits."""
    document = json.loads(Path(__file__).with_name("task_catalog.json").read_text())
    if document["schema_version"] != 1 or document["robolab_commit"] != ROBOLAB_COMMIT:
        raise ValueError("RoboLab task catalog revision differs")
    tasks = [
        Task(
            benchmark="robolab",
            task_id=item["task_id"],
            seed=0,
            instruction=item["instruction"],
            max_steps=item["max_steps"],
            native={
                "task_name": item["task_id"],
                "instruction_type": "default",
                "episode_length_s": item["episode_length_s"],
                "control_dt": item["control_dt"],
                "num_envs": 1,
                "resets_before_episode": 2,
                "renderer": "realtime",
                "action_representation": "robolab_base_link_absolute_xyz_quat_wxyz_gripper",
                "image_size": 320,
                "step_index": "submitted motion chunks",
                "native_budget": "physical control frames, with early native termination",
            },
            capabilities=CAPABILITIES,
        )
        for item in document["tasks"]
    ]
    if len(tasks) != 120 or len({t.task_id for t in tasks}) != 120:
        raise ValueError("RoboLab full task catalog must contain 120 unique tasks")
    return tasks


def validate_task(task: Task) -> None:
    """Reject changed task identities, seeds, instructions and physical budgets."""
    expected = next((t for t in catalog_tasks() if t.task_id == task.task_id), None)
    if expected is None or task != expected:
        raise ValueError("task differs from the pinned RoboLab 1x catalog")
