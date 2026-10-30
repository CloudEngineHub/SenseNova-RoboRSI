# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Publish the pinned RoboLab task catalog through the common HTTP service."""

from __future__ import annotations

import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from roborsi.benchmarks.runtime_source import benchmark_source_digest
from roborsi.evaluation.http_artifacts import ArtifactPublisher
from roborsi.evaluation.messages import BenchmarkRuntimeInfo, Task
from robots.robolab.assets import verify_assets
from robots.robolab.contracts import EVALUATION_RULES, ROBOLAB_COMMIT, catalog_tasks
from robots.robolab.native import native_root, verify_native_source
from robots.robolab.roborsi_adapter import RoboLabAdapter


class RoboLabBenchmark:
    """Expose original task identity and a fresh isolated simulator per case."""

    name = "robolab"

    def tasks(self) -> list[Task]:
        return catalog_tasks()

    def runtime_info(self) -> BenchmarkRuntimeInfo:
        verify_native_source(native_root())
        root = Path(__file__).resolve().parents[2]
        # This registration must be delivered by the framework owner. Do not
        # substitute a local hash or disable the shared runtime verification.
        digest = benchmark_source_digest(root, "robolab")
        versions = {}
        for name in ("isaacsim", "isaaclab", "torch", "numpy"):
            try:
                versions[name] = version(name)
            except PackageNotFoundError:
                versions[name] = "not-installed"
        return BenchmarkRuntimeInfo(
            benchmark=self.name,
            benchmark_version="RoboLab-" + ROBOLAB_COMMIT[:12],
            benchmark_commit=ROBOLAB_COMMIT,
            adapter_version="roborsi-source-sha256:" + digest,
            evaluation=EVALUATION_RULES,
            platform={
                "system": platform.system(),
                "machine": platform.machine(),
                "python": platform.python_version(),
                **versions,
            },
        )

    def assets(self) -> list[dict]:
        digest = verify_assets((native_root() / "assets").resolve())
        return [{"name": "robolab", "kind": "directory", "sha256": digest}]

    def create_adapter(
        self, directory: Path, artifacts: ArtifactPublisher
    ) -> RoboLabAdapter:
        return RoboLabAdapter(directory, artifacts)


def make_robolab_benchmark() -> RoboLabBenchmark:
    return RoboLabBenchmark()
