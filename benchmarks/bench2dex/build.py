# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Build, check and optionally publish an exported benchmark-only image."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def check_image(image: str, evidence: Path, expected_source_sha256: str) -> dict:
    """Require a healthy benchmark runtime matching the exported source."""
    commands = {
        "pip-check.txt": ["-m", "pip", "check"],
        "image-python.lock.txt": ["-m", "pip", "freeze", "--all"],
        "source-check.txt": [
            "-P",
            "-c",
            "import json; from pathlib import Path; "
            "from roborsi.benchmarks.runtime_source import "
            "benchmark_source_digest, verify_benchmark_runtime; "
            "verify_benchmark_runtime(Path('/opt/roborsi'), 'bench2dex'); "
            "from robots.bench2dex.benchmark_service import "
            "Bench2DexBenchmark, adapter_digest; "
            "print(json.dumps({'source_sha256': "
            "benchmark_source_digest(Path('/opt/roborsi'), 'bench2dex'), "
            "'adapter_version': 'bench2dex-adapter-sha256:' + adapter_digest()}))",
        ],
    }
    for filename, command in commands.items():
        with (evidence / filename).open("w") as output:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network=none",
                    "--entrypoint",
                    "/opt/bench2dex/bin/python",
                    image,
                    *command,
                ],
                check=True,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
    identity = json.loads((evidence / "source-check.txt").read_text())
    if identity["source_sha256"] != expected_source_sha256:
        raise ValueError("image benchmark source differs from exported build context")
    return identity


def main() -> None:
    """Check locally first, and report a registry reference only after a pull."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument(
        "--network", choices=("default", "host", "none"), default="default"
    )
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[^\s@]+:[A-Za-z0-9_.-]+", args.tag):
        parser.error("tag must include an explicit repository and tag")
    source = json.loads((args.context / "source.json").read_text())
    args.evidence.mkdir(parents=True, exist_ok=False)
    command = [
        "docker",
        "buildx",
        "build",
        "--platform",
        "linux/amd64",
        "--load",
        "--network",
        args.network,
        "--metadata-file",
        str((args.evidence / "build-metadata.json").resolve()),
        "--tag",
        args.tag,
        str(args.context.resolve()),
    ]
    with (args.evidence / "build.log").open("w") as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
    image_id = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}}", args.tag], text=True
    ).strip()
    identity = check_image(image_id, args.evidence, source["sha256"])
    reference = None
    if args.publish:
        # Re-check the tag immediately before push; checks above ran by image ID.
        if (
            subprocess.check_output(
                ["docker", "image", "inspect", "--format", "{{.Id}}", args.tag],
                text=True,
            ).strip()
            != image_id
        ):
            raise ValueError("image tag changed during validation")
        with (args.evidence / "push.log").open("w") as output:
            subprocess.run(
                ["docker", "push", args.tag],
                check=True,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        repository = args.tag.rsplit(":", 1)[0]
        digests = json.loads(
            subprocess.check_output(
                [
                    "docker",
                    "image",
                    "inspect",
                    "--format",
                    "{{json .RepoDigests}}",
                    args.tag,
                ],
                text=True,
            )
        )
        reference = next(
            (d for d in digests if d.startswith(repository + "@sha256:")), None
        )
        if reference is None or not re.fullmatch(
            r"[^\s@]+@sha256:[0-9a-f]{64}", reference
        ):
            raise ValueError(
                "push did not record a digest for the requested repository"
            )
        raw = subprocess.check_output(
            ["docker", "buildx", "imagetools", "inspect", "--raw", reference]
        )
        (args.evidence / "registry-inspection.json").write_bytes(raw)
        # Inspect may append a newline; verify either exact transport representation.
        digest = reference.rsplit("@sha256:", 1)[1]
        if not any(
            hashlib.sha256(data).hexdigest() == digest
            for data in (raw, raw.rstrip(b"\n"))
        ):
            raise ValueError("registry manifest differs from the published digest")
        subprocess.run(["docker", "pull", reference], check=True)
        if (
            subprocess.check_output(
                ["docker", "image", "inspect", "--format", "{{.Id}}", reference],
                text=True,
            ).strip()
            != image_id
        ):
            raise ValueError("pulled image differs from the validated local image")
        pulled = args.evidence / "pulled-image"
        pulled.mkdir()
        check_image(reference, pulled, source["sha256"])
    (args.evidence / "image.json").write_text(
        json.dumps(
            {
                "reference": reference,
                "local_image_id": image_id,
                "published_and_pulled": args.publish,
                "gpu_validation": "pending",
                "source": source,
                "runtime_identity": identity,
                "build": json.loads((args.context / "build.json").read_text()),
            },
            indent=2,
        )
        + "\n"
    )
    print(
        reference or f"Validated local image: {image_id}; registry publication pending"
    )


if __name__ == "__main__":
    main()
