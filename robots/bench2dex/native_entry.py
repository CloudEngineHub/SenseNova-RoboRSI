# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Load the simulator wrapper without colliding with upstream's robots package."""

from __future__ import annotations

import importlib.util
import os
import runpy
import sys
import traceback
from pathlib import Path


def main() -> None:
    """Use an isolated module name; Bench2Dex owns top-level ``robots``."""
    path = Path(__file__).resolve().parent / "reference/__init__.py"
    spec = importlib.util.spec_from_file_location("bench2dex_reference", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        runpy.run_module("bench2dex_reference.simulator", run_name="__main__")
    except BaseException:
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        # Kit extension destructors can hang after an import/startup failure.
        os._exit(1)


if __name__ == "__main__":
    main()
