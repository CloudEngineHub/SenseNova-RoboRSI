# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""The RoboCasa365 export boundary works before its implementation PR lands."""

import json

from benchmarks.package import prepare_context
from roborsi.benchmarks.runtime_source import (
    benchmark_source_digest,
    benchmark_source_files,
)


def test_robocasa365_export_excludes_agent_material_and_tracks_native_edits(
    tmp_path,
):
    """Registration enables export without admitting the Agent preset."""
    root = tmp_path / "checkout"
    # The implementation is delivered separately. A synthetic checkout
    # exercises the public exporter on this framework-only change.
    for name in benchmark_source_files("robocasa365"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# declared server source\n")
    build = root / "benchmarks/robocasa365"
    (build / "Dockerfile").write_text("FROM scratch\n")
    (build / "Dockerfile.dockerignore").write_text("**\n")
    (build / "build-inputs.json").write_text(
        json.dumps({"schema_version": 1, "inputs": []})
    )
    for name in (
        "robots/robocasa/agent.yaml",
        "robots/robocasa/agents/baseline/agent.yaml",
        "robots/robocasa/agents/baseline/factory.py",
        "robots/robocasa/eval/validate_target50.py",
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private Agent material\n")

    context = prepare_context("robocasa365", tmp_path / "first", source_root=root)
    runtime = context / "benchmark-runtime"
    assert not any(
        b"private Agent material" in path.read_bytes()
        for path in context.rglob("*")
        if path.is_file()
    )
    before = benchmark_source_digest(root, "robocasa365")
    assert benchmark_source_digest(runtime, "robocasa365") == before
    (root / "robots/robocasa/agents/baseline/factory.py").write_text("changed\n")
    assert benchmark_source_digest(root, "robocasa365") == before

    (root / "robots/robocasa/primitives.py").write_text("changed primitive\n")
    after = benchmark_source_digest(root, "robocasa365")
    assert after != before
    second = prepare_context("robocasa365", tmp_path / "second", source_root=root)
    assert benchmark_source_digest(second / "benchmark-runtime", "robocasa365") == after
