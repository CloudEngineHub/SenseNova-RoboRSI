# Copyright 2026 The Bench2Dex Evaluation Contributors.
# Licensing of this copied reference code is pending; see LICENSE_NOTICE.md.

"""Host-only bounded encoding and streaming inventory; no policy-visible changes."""

import io

from PIL import Image


def encode_rgb(rgb):
    target = io.BytesIO()
    Image.fromarray(rgb).save(target, format="PNG", compress_level=6, optimize=False)
    return target.getvalue()
