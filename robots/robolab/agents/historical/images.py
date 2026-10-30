# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Original PNG encoding and reasoning-effort validation without API dependencies."""

import base64
import io

import numpy as np
from PIL import Image


def prepare_image(image: np.ndarray, image_size: int) -> Image.Image:
    image = np.asarray(image)
    if (
        image.dtype != np.uint8
        or image.ndim != 3
        or image.shape[2] != 3
        or min(image.shape[:2]) < 1
    ):
        raise ValueError("Images must be nonempty H x W x 3 uint8 RGB arrays")
    pil_image = Image.fromarray(image)
    pil_image.thumbnail((image_size, image_size), Image.Resampling.LANCZOS)
    return pil_image


def image_data_url(image: np.ndarray, image_size: int) -> str:
    buffer = io.BytesIO()
    prepare_image(image, image_size).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode(
        "ascii"
    )


def validate_reasoning_effort(value: str) -> str:
    if value not in ("none", "minimal", "low", "medium", "high", "xhigh", "max"):
        raise ValueError(f"Unsupported reasoning_effort: {value!r}")
    return value
