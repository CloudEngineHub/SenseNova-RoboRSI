# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Fetch immutable native sources, omitting datasets and unrelated policies."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath


def main() -> None:
    """Run only while building the benchmark image."""
    lock = json.loads(Path(__file__).with_name("build-lock.json").read_text())
    for name, spec in lock["sources"].items():
        with urllib.request.urlopen(spec["url"], timeout=180) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != spec["sha256"]:
            raise ValueError(f"source archive changed: {name}")
        root = Path("/opt/IsaacLab" if name == "isaaclab" else "/opt/RoboLab")
        root.mkdir(parents=True, exist_ok=False)
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for entry in archive.getmembers():
                parts = PurePosixPath(entry.name).parts[1:]
                if not parts:
                    continue
                relative = PurePosixPath(*parts)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("unsafe upstream archive path")
                if name == "robolab" and not (
                    parts[0] == "robolab"
                    or str(relative).startswith("policies/harness_policy/")
                    or str(relative)
                    in {
                        "LICENSE",
                        "THIRD_PARTY_NOTICES.md",
                        "README.md",
                        "pyproject.toml",
                    }
                ):
                    continue
                if entry.isdir():
                    (root / relative).mkdir(parents=True, exist_ok=True)
                elif entry.isfile():
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.extractfile(entry).read())
                elif name == "robolab":
                    raise ValueError("unexpected linked upstream RoboLab source")


if __name__ == "__main__":
    main()
