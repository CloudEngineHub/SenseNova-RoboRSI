# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""The Bench2Dex export boundary works before its implementation PR lands."""

import json

from benchmarks.package import prepare_context
from roborsi.benchmarks.runtime_source import (
    benchmark_source_digest,
    benchmark_source_files,
)


def test_bench2dex_export_excludes_agent_data_and_tracks_native_edits(tmp_path):
    """Registration enables export without admitting adjacent Agent resources."""
    root = tmp_path / "checkout"
    # The implementation is delivered separately in #80. A synthetic checkout
    # exercises the public exporter on this framework-only PR without a skip.
    for name in benchmark_source_files("bench2dex"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# declared server source\n")
    build = root / "benchmarks/bench2dex"
    build.mkdir(parents=True)
    (build / "Dockerfile").write_text("FROM scratch\n")
    (build / "Dockerfile.dockerignore").write_text("**\n")
    (build / "build-inputs.json").write_text(
        json.dumps({"schema_version": 1, "inputs": []})
    )
    for name in (
        "robots/bench2dex/agent.py",
        "robots/bench2dex/agents/baseline/prompt.txt",
        "robots/bench2dex/reference/agent_evaluator.zip",
        "robots/bench2dex/resources/icl_package.zip",
        "benchmarks/bench2dex/auth.json",
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private Agent material\n")

    context = prepare_context("bench2dex", tmp_path / "first", source_root=root)
    runtime = context / "benchmark-runtime"
    assert not any(
        b"private Agent material" in path.read_bytes()
        for path in context.rglob("*")
        if path.is_file()
    )
    before = benchmark_source_digest(root, "bench2dex")
    assert benchmark_source_digest(runtime, "bench2dex") == before
    (root / "robots/bench2dex/agent.py").write_text("changed external Agent\n")
    assert benchmark_source_digest(root, "bench2dex") == before

    helper = root / "robots/bench2dex/reference/kinematics_tool.py"
    helper.write_text("changed calibration helper\n")
    after = benchmark_source_digest(root, "bench2dex")
    assert after != before
    second = prepare_context("bench2dex", tmp_path / "second", source_root=root)
    assert benchmark_source_digest(second / "benchmark-runtime", "bench2dex") == after
