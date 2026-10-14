# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Serve pinned Bench2Dex cases through RoboRSI's common HTTP implementation."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from functools import partial
from pathlib import Path

from roborsi.benchmarks.registry import directory_sha256
from roborsi.evaluation.http_artifacts import ArtifactPublisher
from roborsi.evaluation.messages import BenchmarkRuntimeInfo, Task
from roborsi.utils.config import get_project_env, require_project_env

from .contracts import EVALUATION_RULES, PROTOCOL, ROOT, file_sha256, validate_task
from .native import NativeRuntime
from .roborsi_adapter import Bench2DexAdapter


def read_catalog(path: Path) -> dict:
    """Validate immutable native case selection and its asset identity."""
    value = json.loads(path.read_text())
    if (
        value.get("schema_version") != 1
        or value.get("benchmark_commit") != PROTOCOL["upstream_commit"]
    ):
        raise ValueError("catalog version or native revision mismatch")
    tasks = [Task.from_dict(row) for row in value["tasks"]]
    if not tasks or len({(t.task_id, t.seed) for t in tasks}) != len(tasks):
        raise ValueError("catalog needs unique task/sample identities")
    for task in tasks:
        validate_task(task)
    return value


def adapter_digest() -> str:
    """Identify the declared benchmark-owned runtime, independent of packaging."""
    names = (
        "benchmark_service.py",
        "contracts.py",
        "native.py",
        "native_entry.py",
        "roborsi_adapter.py",
        "protocol.json",
        "tasks.json",
        "reference/__init__.py",
        "reference/core.py",
        "reference/calibration.py",
        "reference/kinematics_tool.py",
        "reference/robot.py",
        "reference/rendering.py",
        "reference/simulator.py",
        "reference/throughput.py",
        "reference/trajectory.py",
        "reference/transport.py",
    )
    digest = hashlib.sha256(b"bench2dex-adapter-v1\0")
    for name in sorted(names):
        path = ROOT / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("missing or linked benchmark source")
        digest.update(name.encode() + b"\0" + bytes.fromhex(file_sha256(path)))
    return digest.hexdigest()


class Bench2DexBenchmark:
    """Own native paths and reject cases outside the selected catalog."""

    name = "bench2dex"
    supports_episode_stop = True

    def __init__(self) -> None:
        self.upstream = Path(require_project_env("BENCH2DEX_ROOT")).resolve()
        self.isaaclab = Path(require_project_env("ISAACLAB_ROOT")).resolve()
        self.python = Path(require_project_env("ISAACLAB_PYTHON")).absolute()
        self.asset_root = Path(require_project_env("BENCH2DEX_ASSETS")).resolve()
        self.catalog_path = Path(require_project_env("BENCH2DEX_CATALOG")).resolve()
        self.catalog = read_catalog(self.catalog_path)
        self._assets = None

    def tasks(self) -> list[Task]:
        """Return only the frozen catalog's native sample indices."""
        if read_catalog(self.catalog_path) != self.catalog:
            raise ValueError("catalog changed after service creation")
        return [Task.from_dict(row) for row in self.catalog["tasks"]]

    def runtime_info(self) -> BenchmarkRuntimeInfo:
        """Report verified native revision and benchmark-owned source identity."""
        for path, pin in (
            (self.upstream, PROTOCOL["upstream_commit"]),
            (self.isaaclab, PROTOCOL["isaaclab_commit"]),
        ):
            if subprocess.check_output(
                ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
            ).strip() != pin or subprocess.check_output(
                ["git", "-C", str(path), "status", "--porcelain"], text=True
            ):
                raise ValueError("native source differs from its clean pinned revision")
        digest = adapter_digest()
        versions = subprocess.check_output(
            [
                str(self.python),
                "-c",
                "import json,importlib.metadata as m,sys; from pathlib import Path; names={d.metadata['Name'].lower():d.version for d in m.distributions()}; print(json.dumps({'python':sys.version.split()[0], 'isaacsim':names.get('isaacsim') or Path('/isaac-sim/VERSION').read_text().strip(), **{n:m.version(n) for n in ['torch','numpy','Pillow']}}))",
            ],
            text=True,
        )
        return BenchmarkRuntimeInfo(
            benchmark=self.name,
            benchmark_version="Bench2Dex-" + PROTOCOL["upstream_commit"][:12],
            benchmark_commit=PROTOCOL["upstream_commit"],
            adapter_version="bench2dex-adapter-sha256:" + digest,
            evaluation=EVALUATION_RULES,
            platform={
                "system": platform.system(),
                "machine": platform.machine(),
                "kernel": platform.release(),
                **json.loads(versions),
            },
        )

    def assets(self) -> list[dict]:
        """Hash the mounted sealed snapshot once; mounts must remain read-only."""
        if self._assets is None:
            digest = directory_sha256(self.asset_root)
            if digest != self.catalog["assets_sha256"]:
                raise ValueError("assets differ from the selected catalog")
            self._assets = [
                {"name": "bench2dex", "kind": "directory", "sha256": digest},
                {
                    "name": "bench2dex-catalog",
                    "kind": "file",
                    "sha256": file_sha256(self.catalog_path),
                },
            ]
        return self._assets

    def create_adapter(
        self, directory: Path, artifacts: ArtifactPublisher
    ) -> Bench2DexAdapter:
        """Allocate an independent simulator for one validated HTTP episode."""
        provider = self

        class SelectedAdapter(Bench2DexAdapter):
            def start(self, task, episode_id):
                if task not in provider.tasks():
                    raise ValueError("task differs from the exported catalog")
                return super().start(task, episode_id)

        return SelectedAdapter(
            directory,
            artifacts,
            runtime_factory=partial(
                NativeRuntime,
                upstream=self.upstream,
                assets=self.asset_root,
                isaaclab=self.isaaclab,
                python=self.python,
                timeout_s=float(get_project_env("BENCH2DEX_NATIVE_TIMEOUT_S", "900")),
            ),
        )


def make_bench2dex_benchmark() -> Bench2DexBenchmark:
    """Public service_host factory."""
    return Bench2DexBenchmark()
