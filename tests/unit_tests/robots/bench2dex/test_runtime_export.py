# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Standard Bench2Dex export includes its native closure and no Agent code."""

import json
import subprocess
import sys
from pathlib import Path

from roborsi.benchmarks.runtime_source import benchmark_source_digest

ROOT = Path(__file__).resolve().parents[4]


def test_standard_export_imports_service_without_agent_or_simulator(tmp_path):
    """Exercise the public CLI and import its output outside the source tree."""
    context = tmp_path / "fresh context"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "benchmarks.package",
            "--benchmark",
            "bench2dex",
            "--output",
            str(context),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    runtime = context / "benchmark-runtime"
    source = json.loads((context / "source.json").read_text())
    assert source["sha256"] == benchmark_source_digest(ROOT, "bench2dex")
    assert source["sha256"] == benchmark_source_digest(runtime, "bench2dex")
    assert set(source["files"]) == {
        p.relative_to(runtime).as_posix() for p in runtime.rglob("*") if p.is_file()
    }
    assert not list(runtime.rglob("*.zip"))
    assert not (runtime / "robots/bench2dex/agent.py").exists()
    assert not (runtime / "roborsi/embodied_agent.py").exists()
    code = r"""
import importlib.abc, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
blocked = ('roborsi.embodied_agent', 'roborsi.planner', 'roborsi.llm',
           'robots.bench2dex.agent', 'gpt6_eval', 'openai', 'anthropic',
           'pydantic_ai', 'mcp', 'isaacsim', 'isaaclab', 'omni')
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == p or fullname.startswith(p + '.') for p in blocked):
            raise AssertionError('Unexpected import in Benchmark: ' + fullname)
sys.meta_path.insert(0, Guard())
from robots.bench2dex.benchmark_service import Bench2DexBenchmark
from robots.bench2dex.native import NativeRuntime
from roborsi.evaluation.service_host import main
for name, module in tuple(sys.modules.items()):
    if name.split('.')[0] in ('robots', 'roborsi') and getattr(module, '__file__', None):
        assert Path(module.__file__).is_relative_to(sys.argv[1]), name
main(['--kind', 'benchmark', '--help'])
"""
    imported = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code, str(runtime)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert imported.returncode == 0, imported.stderr
    assert "--kind" in imported.stdout
