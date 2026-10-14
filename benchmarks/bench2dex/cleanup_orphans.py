# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Remove only metadata remnants left by upgrading NVIDIA-bundled packages."""

from __future__ import annotations

import argparse
import re
from importlib.metadata import distributions
from pathlib import Path


def clean_orphan_metadata(root: Path) -> list[str]:
    """Validate every remnant before deleting any obsolete installer markers.

    A real replacement distribution must exist. METADATA, RECORD, package code,
    unknown files and linked directories are never removed. Obsolete marker
    symlinks are unlinked without following their targets.
    """
    installed = list(distributions())

    def canonical(value: str) -> str:
        return re.sub(r"[-_.]+", "-", value).lower()

    names = {canonical(d.metadata["Name"]) for d in installed if d.metadata.get("Name")}
    pending = []
    for distribution in installed:
        if distribution.metadata.get("Name"):
            continue
        path = Path(distribution._path)
        match = re.fullmatch(r"(.+)-[0-9][^/]*\.dist-info", path.name)
        if (
            not match
            or canonical(match[1]) not in names
            or not path.resolve().is_relative_to(root.resolve())
            or any(parent.is_symlink() for parent in (path, *path.parents))
        ):
            raise ValueError(f"unrecognized incomplete distribution: {path}")
        children = list(path.iterdir())
        if any(
            child.name not in {"INSTALLER", "WHEEL", "top_level.txt"}
            or (not child.is_symlink() and not child.is_file())
            for child in children
        ):
            raise ValueError(
                f"incomplete distribution contains unrecognized files: {path}"
            )
        pending.append((path, children))
    for path, children in pending:
        for child in children:
            child.unlink()
        path.rmdir()
    return [str(path) for path, _ in pending]


def main() -> None:
    """Clean a container copy after pip has successfully replaced packages."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    for path in clean_orphan_metadata(args.root):
        print(f"Removed obsolete installer metadata: {path}")


if __name__ == "__main__":
    main()
