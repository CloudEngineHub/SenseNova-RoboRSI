# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Build an exported context and record image identity; publishing is explicit."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def main() -> None:
    """Require a real builder and verify the produced digest through the registry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[^\s@]+:[A-Za-z0-9_.-]+", args.tag):
        parser.error("tag must include an explicit repository and tag")
    args.evidence.mkdir(parents=True, exist_ok=False)
    command = [
        "docker",
        "buildx",
        "build",
        "--platform",
        "linux/amd64",
        "--provenance=true",
        "--metadata-file",
        str((args.evidence / "build-metadata.json").resolve()),
        "--tag",
        args.tag,
        "--push" if args.publish else "--load",
        str(args.context.resolve()),
    ]
    with (args.evidence / "build.log").open("w") as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
    metadata = json.loads((args.evidence / "build-metadata.json").read_text())
    digest = metadata["containerimage.digest"]
    if not re.fullmatch("sha256:[0-9a-f]{64}", digest):
        raise ValueError("builder did not return a valid image digest")
    reference = args.tag.rsplit(":", 1)[0] + "@" + digest
    if args.publish:
        with (args.evidence / "registry-inspection.json").open("w") as output:
            subprocess.run(
                ["docker", "buildx", "imagetools", "inspect", "--raw", reference],
                check=True,
                stdout=output,
            )
        subprocess.run(["docker", "pull", reference], check=True)
    with (args.evidence / "image-python.lock.txt").open("w") as output:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "/opt/bench2dex/bin/python",
                reference if args.publish else args.tag,
                "-m",
                "pip",
                "freeze",
                "--all",
            ],
            check=True,
            stdout=output,
        )
    (args.evidence / "image.json").write_text(
        json.dumps(
            {
                "reference": reference,
                "published_and_pulled": args.publish,
                "gpu_validation": "pending",
                "source": json.loads((args.context / "source.json").read_text()),
            },
            indent=2,
        )
        + "\n"
    )
    print(reference)


if __name__ == "__main__":
    main()
