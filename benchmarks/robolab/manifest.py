# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Register the 120 native seed-zero cases for the standard RoboRSI baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from roborsi.benchmarks.registry import benchmark_manifest_schema
from roborsi.evaluation.messages import BenchmarkRuntimeInfo
from roborsi.evaluation.result import write_json_atomic
from robots.robolab.assets import asset_spec
from robots.robolab.benchmark_service import RoboLabBenchmark
from robots.robolab.contracts import CAPABILITIES, ROBOLAB_COMMIT, catalog_tasks


def build_manifest(image: str, asset: dict, runtime: BenchmarkRuntimeInfo) -> dict:
    """Keep sequential historical repetitions distinct from independent cases."""
    repository, separator, digest = image.partition("@")
    if not separator or runtime.benchmark != "robolab":
        raise ValueError("a RoboLab runtime and repository@sha256:digest are required")
    if (
        asset.get("sha256") != asset_spec()["sha256"]
        or asset.get("version") != ROBOLAB_COMMIT
    ):
        raise ValueError("asset descriptor does not match pinned RoboLab assets")
    document = {
        "schema_version": 1,
        "benchmark": "robolab",
        "benchmark_version": runtime.benchmark_version,
        "benchmark_commit": runtime.benchmark_commit,
        "adapter_version": runtime.adapter_version,
        "image_repository": repository,
        "image_digest": digest,
        "assets_version": asset["version"],
        "assets": [asset],
        "adapter_command": [
            "python",
            "-P",
            "-m",
            "roborsi.evaluation.service_host",
            "--kind",
            "benchmark",
            "--factory",
            "robots.robolab.benchmark_service:make_robolab_benchmark",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ],
        "service_port": 8000,
        "resources": {
            "gpus": 1,
            "cpus": 8,
            "memory_mb": 32768,
            "startup_timeout_s": 900,
        },
        "capabilities": {
            "action_schema": CAPABILITIES["action_schema"],
            "observation_channels": CAPABILITIES["observation_channels"],
        },
        "evaluation": runtime.evaluation,
        "tasks": [
            {
                "task_id": task.task_id,
                "seeds": [0],
                "native": task.native,
                "instruction": task.instruction,
                "max_steps": task.max_steps,
            }
            for task in catalog_tasks()
        ],
    }
    Draft202012Validator(benchmark_manifest_schema()).validate(document)
    return document


def main() -> None:
    """Run inside the built image to bind runtime metadata to its real digest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    write_json_atomic(
        args.output,
        build_manifest(
            args.image,
            json.loads(args.asset.read_text()),
            RoboLabBenchmark().runtime_info(),
        ),
    )


if __name__ == "__main__":
    main()
