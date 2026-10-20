# Copyright 2026 The Bench2Dex Evaluation Contributors.
# Licensed under the Apache License, Version 2.0.

"""Pure boundary rules. No simulator imports or access from the policy side."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

CAMERAS = {
    "baseline_4cam": (
        "cam_stereo_left",
        "cam_stereo_right",
        "cam_wrist_left",
        "cam_wrist_right",
    ),
    "baseline_3cam": ("cam_overhead", "cam_wrist_left", "cam_wrist_right"),
}


def canonical(value) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(canonical(value))
    temp.replace(path)


def sanitize_observation(raw: dict, profile: str, dof: int) -> tuple[dict, dict]:
    """Reconstruct from an allowlist; never serialize the incoming dictionary."""
    qpos = np.asarray(raw["joint_action"]["vector"])
    if qpos.shape != (dof,) or not np.isfinite(qpos).all():
        raise ValueError("Invalid active qpos")
    language = raw["language"]
    if not isinstance(language, str):
        raise ValueError("Task instruction must be text")
    images = {}
    for camera in CAMERAS[profile]:
        rgb = np.asarray(raw["observation"][camera]["rgb"])
        if rgb.dtype != np.uint8 or rgb.shape != (480, 640, 3):
            raise ValueError(f"Invalid RGB frame: {camera}")
        images[camera] = np.ascontiguousarray(rgb).copy()
    return {"instruction": language, "qpos": qpos.astype(np.float32).tolist()}, images


def save_observation(
    root: Path,
    index: int,
    raw: dict,
    profile: str,
    dof: int,
    remaining: int,
    path_prefix: str = "",
    calibrated: bool = False,
    encoder=None,
) -> dict:
    public, images = sanitize_observation(raw, profile, dof)
    folder = root / "observations" / f"{index:06d}"
    folder.mkdir(parents=True)
    public.update(
        policy_step=index,
        physics_step=index * 3,
        remaining_policy_steps=remaining,
        cameras=[],
    )
    if calibrated:
        from .calibration import validate_calibration

        public["camera_calibration"] = validate_calibration(
            raw["camera_calibration"], CAMERAS[profile]
        )
    from .throughput import encode_rgb

    encoded = (
        encoder.map(encode_rgb, images.values())
        if encoder
        else map(encode_rgb, images.values())
    )
    for (name, rgb), png in zip(images.items(), encoded):
        path = folder / f"{name}.png"
        path.write_bytes(png)
        public["cameras"].append(
            {
                "name": name,
                "path": path_prefix + str(path.relative_to(root)),
                "sha256": digest(path.read_bytes()),
                "rgb_sha256": digest(rgb.tobytes()),
            }
        )
    write_json(folder / "observation.json", public)
    return public


def validate_actions(payload: dict, dof: int, remaining: int) -> np.ndarray:
    if set(payload) != {"actions"}:
        raise ValueError("Action file must contain exactly the actions field")
    raw = np.asarray(payload["actions"])
    if raw.dtype.kind not in "ifu":
        raise ValueError("Actions must be numeric arrays, not strings or booleans")
    arr = raw.astype(np.float32)
    if arr.ndim != 2 or arr.shape[1] != dof or not 1 <= len(arr) <= remaining:
        raise ValueError("Expected a nonempty [steps, active_dof] chunk within budget")
    if not np.isfinite(arr).all():
        raise ValueError("Actions must be finite")
    return arr


def classify_result(row: dict) -> str:
    """Honor reach-and-stop, retain official metric details separately."""
    reason = row.get("terminated_reason")
    if reason in {"error", "shutdown", "skipped"}:
        return "infrastructure_error"
    if reason == "max_steps":
        return "failure"
    if reason == "stable_success" and row.get("success") is True:
        return "success"
    return "infrastructure_error"
