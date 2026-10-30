# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Install the two historical official CLI packages into a private directory."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath


def install(destination: Path) -> dict[str, str]:
    """Verify archive and binary hashes without changing a global installation."""
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("this historical lock supports Linux x86_64")
    lock = json.loads(Path(__file__).with_name("codex-binaries.json").read_text())
    destination.mkdir(parents=True, exist_ok=False)
    binaries = {}
    for version, spec in lock["versions"].items():
        with urllib.request.urlopen(spec["url"], timeout=180) as response:
            raw = response.read()
        if hashlib.sha256(raw).hexdigest() != spec["archive_sha256"]:
            raise ValueError(f"official CLI archive hash differs: {version}")
        root = destination / version
        root.mkdir()
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            for member in archive.getmembers():
                name = PurePosixPath(member.name)
                if (
                    name.is_absolute()
                    or ".." in name.parts
                    or not (member.isfile() or member.isdir())
                ):
                    raise ValueError("CLI archive contains an unsafe member")
            archive.extractall(root, filter="data")
        path = root / spec["member"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != spec["binary_sha256"]:
            raise ValueError(f"CLI binary hash differs: {version}")
        binaries[version] = str(path.resolve())
    (destination / "binaries.json").write_text(json.dumps(binaries, indent=2) + "\n")
    return binaries


def main() -> None:
    """Print the verified executable paths for the reproduction launcher."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(install(args.destination)))


if __name__ == "__main__":
    main()
