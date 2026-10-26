# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Generated Bench2Dex manifests must satisfy the strict local Registry."""

import json

import pytest

from benchmarks.bench2dex.prepare import build_manifest
from roborsi.benchmarks.registry import BenchmarkRegistry, directory_sha256
from robots.bench2dex.benchmark_service import adapter_digest
from robots.bench2dex.contracts import ASSET_REVISION, PROTOCOL, task_for

IMAGE = "example.org/bench2dex@sha256:" + "1" * 64


@pytest.fixture
def manifest_inputs(tmp_path):
    root = tmp_path / "registry/bench2dex"
    assets = root / "assets"
    assets.mkdir(parents=True)
    (assets / "fixture.bin").write_bytes(b"sealed native asset fixture")
    catalog = root / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "benchmark_commit": PROTOCOL["upstream_commit"],
                "assets_revision": ASSET_REVISION,
                "assets_sha256": directory_sha256(assets),
                "tasks": [task_for("26", 5, smoke_steps=4).as_dict()],
            }
        )
    )
    return assets, catalog, root / "manifest.json"


def test_generated_manifest_loads_in_strict_registry(manifest_inputs):
    assets, catalog, output = manifest_inputs
    document = build_manifest(IMAGE, assets, catalog, output)
    assert [asset["path"] for asset in document["assets"]] == ["assets", "catalog.json"]
    lock = BenchmarkRegistry([output.parent.parent]).lock("bench2dex")
    assert lock.image_reference == IMAGE
    assert (
        lock.as_dict()["adapter_version"]
        == "bench2dex-adapter-sha256:" + adapter_digest()
    )
    assert lock.task_message("26", 5) == task_for("26", 5, smoke_steps=4)
    (assets / "fixture.bin").write_bytes(b"changed asset")
    with pytest.raises(ValueError, match="asset digest mismatch"):
        lock.verify()


@pytest.mark.parametrize("outside", ["assets", "catalog"])
def test_manifest_rejects_artifacts_outside_registry(
    manifest_inputs, tmp_path, outside
):
    assets, catalog, output = manifest_inputs
    if outside == "assets":
        assets = assets.rename(tmp_path / "external-assets")
    else:
        catalog = catalog.rename(tmp_path / "external-catalog.json")
    with pytest.raises(ValueError, match="inside the manifest directory"):
        build_manifest(IMAGE, assets, catalog, output)
    assert not output.exists()


def test_manifest_accepts_registry_directory_alias(manifest_inputs, tmp_path):
    assets, catalog, output = manifest_inputs
    root = output.parent
    physical = root.rename(tmp_path / "physical-benchmark")
    root.symlink_to(physical, target_is_directory=True)
    build_manifest(IMAGE, assets, catalog, output)
    lock = BenchmarkRegistry([root.parent]).lock("bench2dex")
    assert lock.task_message("26", 5) == task_for("26", 5, smoke_steps=4)


@pytest.mark.parametrize("linked", ["assets", "catalog"])
def test_manifest_rejects_linked_artifacts(manifest_inputs, linked):
    assets, catalog, output = manifest_inputs
    alias = output.parent / "alias"
    if linked == "assets":
        alias.symlink_to(assets, target_is_directory=True)
        assets = alias
    else:
        alias.symlink_to(catalog)
        catalog = alias
    with pytest.raises(ValueError, match="symlink"):
        build_manifest(IMAGE, assets, catalog, output)
    assert not output.exists()
