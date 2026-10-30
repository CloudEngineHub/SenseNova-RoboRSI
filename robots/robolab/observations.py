# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""The historical harness's public DROID proprioception and two RGB cameras."""

from __future__ import annotations

import io
from typing import Any

import numpy as np
from PIL import Image

from robots.robolab.motion import robot_state

CAMERAS = {
    "exterior_image": "over_shoulder_left_camera",
    "wrist_image": "wrist_cam",
}
IMAGE_SIZE = 320


def _array(value: Any) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)[0]


def extract_observation(raw: dict) -> dict:
    """Select env zero without disclosing ground truth or scoring diagnostics."""
    proprio = raw["proprio_obs"]
    public = robot_state(
        {
            "position": _array(proprio["ee_pos"]),
            "quaternion": _array(proprio["ee_quat"]),
            "joint_positions": _array(proprio["arm_joint_pos"]),
            "gripper": float(_array(proprio["gripper_pos"]).reshape(-1)[0]),
        }
    )
    for name, camera in CAMERAS.items():
        pixels = _array(raw["image_obs"][camera])
        public[name] = resize_image(pixels)
    return public


def resize_image(pixels: Any) -> np.ndarray:
    """Apply the same aspect-preserving LANCZOS thumbnail as the source client."""
    pixels = np.asarray(pixels)
    if (
        pixels.dtype != np.uint8
        or pixels.ndim != 3
        or pixels.shape[2] != 3
        or min(pixels.shape[:2]) < 1
    ):
        raise ValueError("camera images must be nonempty RGB uint8 arrays")
    image = Image.fromarray(pixels)
    image.thumbnail((IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS)
    return np.asarray(image)


def png_bytes(pixels: Any) -> bytes:
    """Encode the public thumbnail losslessly for the shared media transport."""
    output = io.BytesIO()
    Image.fromarray(resize_image(pixels)).save(output, format="PNG")
    return output.getvalue()
