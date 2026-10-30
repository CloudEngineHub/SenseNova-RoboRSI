# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Verify the complete external asset tree against the pinned upstream release."""

from __future__ import annotations

import json
from pathlib import Path

from roborsi.benchmarks.registry import directory_sha256


def asset_spec() -> dict:
    """Return build-owned metadata, never trust a descriptor supplied by a client."""
    return json.loads(Path(__file__).with_name("assets.json").read_text())


def verify_assets(path: Path) -> str:
    """Hash real files and reject altered, missing, additional or linked assets."""
    expected = asset_spec()["sha256"]
    actual = directory_sha256(path)
    if actual != expected:
        raise ValueError("RoboLab assets differ from the pinned release")
    return actual
