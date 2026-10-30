# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Import verified assets into a fresh external RoboRSI registry directory."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from robots.robolab.assets import asset_spec, verify_assets


def prepare_assets(source: Path, destination: Path) -> dict:
    """Copy an exact asset tree; generated metadata and data stay outside source."""
    source, destination = source.resolve(), destination.resolve()
    checkout = Path(__file__).resolve().parents[2]
    if destination.is_relative_to(checkout) or destination.is_relative_to(source):
        raise ValueError("registry directory must be outside source and assets")
    expected = verify_assets(source)
    destination.mkdir(parents=True, exist_ok=False)
    target = destination / "assets/robolab"
    shutil.copytree(source, target)
    verify_assets(target)
    descriptor = {
        "name": "robolab",
        "version": asset_spec()["commit"],
        "kind": "directory",
        "path": "assets/robolab",
        "sha256": expected,
    }
    (destination / "asset.json").write_text(json.dumps(descriptor, indent=2) + "\n")
    return descriptor


def main() -> None:
    """Accept a downloaded pinned checkout's assets or an already verified copy."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_assets(args.source, args.destination)))


if __name__ == "__main__":
    main()
