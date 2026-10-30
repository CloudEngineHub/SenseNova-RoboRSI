# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Build, verify and optionally publish a digest-pinned native RoboLab image."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

REPOSITORY = "ghcr.io/opensensenova/sensenova-roborsi-robolab"


def image_id(docker: list[str], reference: str) -> str:
    return subprocess.check_output(
        [*docker, "image", "inspect", "--format", "{{.Id}}", reference],
        text=True,
        timeout=30,
    ).strip()


def main() -> None:
    """Publish only new version tags, inspect the registry digest, then pull it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--tag", required=True, help="vMAJOR.MINOR.PATCH-environment")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--docker-host")
    parser.add_argument("--docker-config", type=Path)
    parser.add_argument(
        "--network", choices=("default", "host", "none"), default="default"
    )
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"v?\d+\.\d+\.\d+-[a-z][a-z0-9.-]*", args.tag):
        parser.error("use an explicit semantic version and environment, never latest")
    docker = ["docker"]
    if args.docker_config:
        docker += ["--config", str(args.docker_config.resolve())]
    if args.docker_host:
        docker += ["--host", args.docker_host]
    source = json.loads((args.context / "source.json").read_text())
    build = json.loads((args.context / "build.json").read_text())
    if source["benchmark"] != "robolab" or build["benchmark"] != "robolab":
        parser.error("context must come from the shared RoboLab exporter")
    args.evidence.mkdir(parents=True, exist_ok=False)
    tag = f"{REPOSITORY}:{args.tag}"
    with (args.evidence / "build.log").open("w") as output:
        subprocess.run(
            [
                *docker,
                "buildx",
                "build",
                "--load",
                "--platform",
                "linux/amd64",
                "--progress",
                "plain",
                "--network",
                args.network,
                "--metadata-file",
                str((args.evidence / "metadata.json").resolve()),
                "--tag",
                tag,
                str(args.context.resolve()),
            ],
            check=True,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
    identity = image_id(docker, tag)
    reference = None
    if args.publish:
        existing = subprocess.run(
            [*docker, "buildx", "imagetools", "inspect", tag],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if existing.returncode == 0:
            raise ValueError("registry tag already exists; choose a new version")
        message = (existing.stdout + existing.stderr).lower()
        if not any(
            text in message
            for text in ("not found", "manifest unknown", "name unknown", "404")
        ):
            raise RuntimeError(
                "cannot establish that the registry tag is new: " + message
            )
        if image_id(docker, tag) != identity:
            raise ValueError("local tag changed during validation")
        with (args.evidence / "push.log").open("w") as output:
            subprocess.run(
                [*docker, "push", tag],
                check=True,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        digests = json.loads(
            subprocess.check_output(
                [*docker, "image", "inspect", "--format", "{{json .RepoDigests}}", tag],
                text=True,
            )
        )
        reference = next(
            (ref for ref in digests if ref.startswith(REPOSITORY + "@sha256:")), None
        )
        if reference is None or not re.fullmatch(
            re.escape(REPOSITORY) + r"@sha256:[0-9a-f]{64}", reference
        ):
            raise ValueError("push did not produce the requested repository digest")
        raw = subprocess.check_output(
            [*docker, "buildx", "imagetools", "inspect", "--raw", reference], timeout=60
        )
        (args.evidence / "registry-manifest.json").write_bytes(raw)
        digest = reference.split("@sha256:")[1]
        if not any(
            hashlib.sha256(data).hexdigest() == digest
            for data in (raw, raw.rstrip(b"\n"))
        ):
            raise ValueError("registry manifest digest differs")
        with (args.evidence / "pull.log").open("w") as output:
            subprocess.run(
                [*docker, "pull", reference],
                check=True,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        if image_id(docker, reference) != identity:
            raise ValueError("pulled image differs from the validated local image")
    report = {
        "schema_version": 1,
        "tag": tag,
        "reference": reference,
        "local_image_id": identity,
        "published_and_pulled": args.publish,
        "source": source,
        "build": build,
    }
    (args.evidence / "image.json").write_text(json.dumps(report, indent=2) + "\n")
    print(reference or identity)


if __name__ == "__main__":
    main()
