# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""The RoboCasa365 export boundary includes only its native service sources."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

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
    # A synthetic checkout exercises the public export and digest boundaries.
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


@pytest.mark.parametrize("entry", ["service", "manifest"])
def test_exported_robocasa365_help_and_catalog_without_agent_or_native_imports(
    tmp_path, entry
):
    """The isolated bundle resolves lazy dependencies without a model or simulator."""
    root = Path(__file__).resolve().parents[4]
    context = prepare_context("robocasa365", tmp_path / "context", source_root=root)
    runtime = context / "benchmark-runtime"
    assert {
        path.relative_to(runtime).as_posix()
        for path in runtime.rglob("*")
        if path.is_file()
    } == set(benchmark_source_files("robocasa365"))
    assert benchmark_source_digest(root, "robocasa365") == benchmark_source_digest(
        runtime, "robocasa365"
    )
    code = r"""
import importlib.abc
import sys
from pathlib import Path
runtime = Path(sys.argv[1]).resolve()
entry = sys.argv[2]
sys.path.insert(0, str(runtime))
blocked = (
    'roborsi.embodied_agent', 'roborsi.agents', 'roborsi.planner',
    'roborsi.llm', 'roborsi.memory', 'roborsi.prompt',
    'roborsi.evaluation.services', 'robots.robocasa.agents',
    'robots.robocasa.prompts', 'robots.robocasa.robot_spec',
    'openai', 'anthropic', 'pydantic_ai', 'mcp', 'torch', 'mujoco',
    'robosuite', 'robocasa', 'rlinf', 'rldx', 'sam3',
)
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in blocked):
            raise AssertionError('Unexpected import: ' + fullname)
sys.meta_path.insert(0, Guard())
from robots.robocasa.benchmark_service import RoboCasa365Benchmark
provider = RoboCasa365Benchmark(None)
assert len(provider.tasks()) == 340
assert len(RoboCasa365Benchmark(None, cells='seed1').tasks()) == 50
assert provider.runtime_info().benchmark == 'robocasa365'
from benchmarks.robocasa365 import manifest
assert sum(len(task['seeds']) for task in manifest.manifest('example.invalid/benchmark@sha256:' + 'a' * 64)['tasks']) == 340
for name, loaded in tuple(sys.modules.items()):
    if name.split('.')[0] in ('roborsi', 'robots', 'benchmarks') and getattr(loaded, '__file__', None):
        assert Path(loaded.__file__).is_relative_to(runtime), (name, loaded.__file__)
if entry == 'manifest':
    sys.argv = ['manifest', '--help']
    manifest.main()
else:
    from roborsi.evaluation.service_host import main
    main(['--kind', 'benchmark', '--help'])
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code, str(runtime), entry],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert ("--image" if entry == "manifest" else "--kind") in result.stdout
