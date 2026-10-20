# Copyright 2026 The Bench2Dex Evaluation Contributors.
# Licensed under the Apache License, Version 2.0.


"""Encode sanitized native RGB observations as PNG bytes."""

import io

from PIL import Image


def encode_rgb(rgb):
    target = io.BytesIO()
    Image.fromarray(rgb).save(target, format="PNG", compress_level=6, optimize=False)
    return target.getvalue()
