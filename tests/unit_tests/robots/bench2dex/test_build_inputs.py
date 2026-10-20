# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Check native build inputs without downloading the simulator image."""

from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def test_native_requirements_accept_recorded_environment_versions():
    """Direct requirements must not contradict the Dockerfile's constraints."""
    directory = Path(__file__).resolve().parents[4] / "benchmarks/bench2dex"

    def requirements(name):
        return [
            Requirement(line.strip())
            for line in (directory / name).read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

    locked = {}
    for requirement in requirements("native-environment.lock.txt"):
        specifier = next(iter(requirement.specifier))
        assert specifier.operator == "=="
        locked[canonicalize_name(requirement.name)] = specifier.version

    for requirement in requirements("native-requirements.txt"):
        version = locked.get(canonicalize_name(requirement.name))
        if version is not None:
            assert version in requirement.specifier, (str(requirement), version)


def test_failed_image_check_prevents_publication(monkeypatch, tmp_path):
    """A failed local runtime check must stop before any registry push."""
    import subprocess
    import sys

    import pytest

    from benchmarks.bench2dex import build

    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if command[:2] == ["docker", "run"]:
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(build.subprocess, "run", run)
    monkeypatch.setattr(
        build.subprocess, "check_output", lambda *a, **kw: "sha256:" + "a" * 64
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build",
            "--context",
            str(tmp_path / "context"),
            "--tag",
            "example.org/bench:test",
            "--evidence",
            str(tmp_path / "evidence"),
            "--publish",
        ],
    )
    with pytest.raises(subprocess.CalledProcessError):
        build.main()
    assert any(command[:2] == ["docker", "run"] for command in commands)
    assert not any(command[:2] == ["docker", "push"] for command in commands)
    assert not (tmp_path / "evidence/image.json").exists()


def test_adapter_identity_includes_native_kinematics(monkeypatch, tmp_path):
    """Calibration uses this helper, so changing it must invalidate the identity."""
    import shutil

    from robots.bench2dex import benchmark_service

    source = benchmark_service.ROOT
    shutil.copytree(source, tmp_path / "robot")
    monkeypatch.setattr(benchmark_service, "ROOT", tmp_path / "robot")
    original = benchmark_service.adapter_digest()
    path = tmp_path / "robot/reference/kinematics_tool.py"
    path.write_text(path.read_text() + "\n# altered native helper\n")
    assert benchmark_service.adapter_digest() != original


def test_cleanup_removes_only_obsolete_installer_markers(monkeypatch, tmp_path):
    """The base's old installer markers go; the replacement stays intact."""
    from importlib.metadata import PathDistribution

    from benchmarks.bench2dex import cleanup_orphans

    valid = tmp_path / "demo-2.0.dist-info"
    valid.mkdir()
    (valid / "METADATA").write_text("Name: demo\nVersion: 2.0\n")
    old = tmp_path / "demo-1.0.dist-info"
    old.mkdir()
    (old / "INSTALLER").write_text("pip")
    monkeypatch.setattr(
        cleanup_orphans,
        "distributions",
        lambda: [PathDistribution(valid), PathDistribution(old)],
    )
    assert cleanup_orphans.clean_orphan_metadata(tmp_path) == [str(old)]
    assert not old.exists()
    assert (valid / "METADATA").read_text() == "Name: demo\nVersion: 2.0\n"


def test_cleanup_refuses_unrecognized_package_contents(monkeypatch, tmp_path):
    """An unexpected file must not be hidden to make source verification pass."""
    from importlib.metadata import PathDistribution

    import pytest

    from benchmarks.bench2dex import cleanup_orphans

    valid = tmp_path / "demo-2.0.dist-info"
    valid.mkdir()
    (valid / "METADATA").write_text("Name: demo\nVersion: 2.0\n")
    old = tmp_path / "demo-1.0.dist-info"
    old.mkdir()
    (old / "RECORD").write_text("unknown.py,,\n")
    monkeypatch.setattr(
        cleanup_orphans,
        "distributions",
        lambda: [PathDistribution(valid), PathDistribution(old)],
    )
    with pytest.raises(ValueError, match="unrecognized files"):
        cleanup_orphans.clean_orphan_metadata(tmp_path)
    assert (old / "RECORD").is_file()


def test_cleanup_unlinks_marker_without_following_target(monkeypatch, tmp_path):
    """NVIDIA's leftover marker links must not cause deletion of their targets."""
    from importlib.metadata import PathDistribution

    from benchmarks.bench2dex import cleanup_orphans

    valid = tmp_path / "demo-2.0.dist-info"
    valid.mkdir()
    (valid / "METADATA").write_text("Name: demo\nVersion: 2.0\n")
    old = tmp_path / "demo-1.0.dist-info"
    old.mkdir()
    target = tmp_path / "installer-marker"
    target.write_text("pip")
    (old / "INSTALLER").symlink_to(target)
    monkeypatch.setattr(
        cleanup_orphans,
        "distributions",
        lambda: [PathDistribution(valid), PathDistribution(old)],
    )
    cleanup_orphans.clean_orphan_metadata(tmp_path)
    assert target.read_text() == "pip"
    assert not old.exists()
