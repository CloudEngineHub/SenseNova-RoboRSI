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
