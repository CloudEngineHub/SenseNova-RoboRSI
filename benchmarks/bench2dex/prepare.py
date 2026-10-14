# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Export frozen case catalogs and schema-validated Registry manifests."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from jsonschema import Draft202012Validator

from roborsi.benchmarks.registry import benchmark_manifest_schema, directory_sha256
from robots.bench2dex.benchmark_service import adapter_digest, read_catalog
from robots.bench2dex.contracts import (
    ASSET_REVISION,
    EVALUATION_RULES,
    PROTOCOL,
    TASKS,
    file_sha256,
    task_for,
)
from robots.bench2dex.reference.core import write_json


def build_manifest(image: str, assets: Path, catalog_path: Path, output: Path) -> dict:
    """Require an actual image digest and locally verified mounted artifacts."""
    repository, separator, digest = image.partition("@")
    if not separator:
        raise ValueError("provide the published repository@sha256:digest")
    catalog = read_catalog(catalog_path)
    if directory_sha256(assets) != catalog["assets_sha256"]:
        raise ValueError("asset snapshot differs from catalog")
    groups = defaultdict(list)
    for row in catalog["tasks"]:
        groups[row["task_id"]].append(row)
    tasks = []
    for name, rows in groups.items():
        if len({row["max_steps"] for row in rows}) != 1:
            raise ValueError("a task must have one control budget")
        tasks.append(
            {
                "task_id": name,
                "seeds": [r["seed"] for r in rows],
                "native": rows[0]["native"],
                "native_by_seed": {str(r["seed"]): r["native"] for r in rows},
                "instruction": rows[0]["instruction"],
                "max_steps": rows[0]["max_steps"],
            }
        )
    document = {
        "schema_version": 1,
        "benchmark": "bench2dex",
        "benchmark_version": "Bench2Dex-" + PROTOCOL["upstream_commit"][:12],
        "benchmark_commit": PROTOCOL["upstream_commit"],
        "adapter_version": "bench2dex-adapter-sha256:" + adapter_digest(),
        "image_repository": repository,
        "image_digest": digest,
        "assets_version": ASSET_REVISION,
        "assets": [
            {
                "name": "bench2dex",
                "kind": "directory",
                "version": ASSET_REVISION,
                "path": str(assets.resolve()),
                "sha256": catalog["assets_sha256"],
            },
            {
                "name": "bench2dex-catalog",
                "kind": "file",
                "version": "1",
                "path": str(catalog_path.resolve()),
                "sha256": file_sha256(catalog_path),
            },
        ],
        "adapter_command": [
            "python",
            "-P",
            "-m",
            "roborsi.evaluation.service_host",
            "--kind",
            "benchmark",
            "--factory",
            "robots.bench2dex.benchmark_service:make_bench2dex_benchmark",
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
        "capabilities": catalog["tasks"][0]["capabilities"],
        "evaluation": EVALUATION_RULES,
        "tasks": tasks,
    }
    Draft202012Validator(benchmark_manifest_schema()).validate(document)
    # These are generated operator-local bindings, never distributed config paths.
    write_json(output, document)
    return document


def main() -> None:
    """Keep diagnostic budgets explicitly separate from scored evaluation."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    catalog = commands.add_parser("catalog")
    catalog.add_argument("--assets", type=Path, required=True)
    catalog.add_argument("--task", choices=sorted(TASKS), action="append")
    catalog.add_argument("--sample", type=int, action="append")
    catalog.add_argument("--smoke-steps", type=int)
    catalog.add_argument("--output", type=Path, required=True)
    manifest = commands.add_parser("manifest")
    manifest.add_argument("--image", required=True)
    manifest.add_argument("--assets", type=Path, required=True)
    manifest.add_argument("--catalog", type=Path, required=True)
    manifest.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a new output file")
    if args.command == "catalog":
        tasks = args.task or sorted(TASKS, key=int)
        samples = args.sample or [5]
        if len(tasks) != len(set(tasks)) or len(samples) != len(set(samples)):
            parser.error("duplicate tasks or samples")
        write_json(
            args.output,
            {
                "schema_version": 1,
                "benchmark_commit": PROTOCOL["upstream_commit"],
                "assets_revision": ASSET_REVISION,
                "assets_sha256": directory_sha256(args.assets),
                "tasks": [
                    task_for(t, s, smoke_steps=args.smoke_steps).as_dict()
                    for t in tasks
                    for s in samples
                ],
            },
        )
    else:
        build_manifest(args.image, args.assets, args.catalog, args.output)


if __name__ == "__main__":
    main()
