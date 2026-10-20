# Copyright 2026 The HEART Authors.
# Licensed under the Apache License, Version 2.0 (the "License");

"""Tests for the three-LIBERO source-runtime preflight."""

import json
from pathlib import Path

import pytest

from benchmarks.libero_three_combined.prepare_agent_assets import prepare as prepare_agent_assets
from benchmarks.libero_three_combined.run_combined import _CASES as _COMBINED_CASES
from benchmarks.libero_three_combined.run_combined_subset import _summary as _combined_summary
from benchmarks.libero_three_combined.run_combined_subset import _tasks as _combined_tasks


def test_combined_runner_uses_the_installed_agent_bundles() -> None:
    assert _COMBINED_CASES == {
        "libero_long_plus_plus": (
            "bundle:libero_long_plus_plus_v13",
            "t00-i01",
        ),
        "libero_ultra_long": ("bundle:libero_ultra_long_v13", "t00-i01"),
        "libero_pro": ("bundle:libero_pro", "libero_spatial_task-t00-i03"),
    }


def test_combined_subset_uses_all_locked_context_map_tasks() -> None:
    repository = Path(__file__).resolve().parents[4]

    assert len(_combined_tasks(repository, "libero_long_plus_plus")) == 12
    assert len(_combined_tasks(repository, "libero_ultra_long")) == 9
    assert len(_combined_tasks(repository, "libero_pro")) == 80


def test_combined_summary_keeps_invalid_attempts_out_of_completed_count() -> None:
    summary = _combined_summary(
        "libero_pro",
        "combined",
        ("success", "task-failure", "agent-error"),
        {
            "success": {
                "returncode": 0,
                "status": "success",
                "success": True,
                "score": 1.0,
            },
            "task-failure": {
                "returncode": 0,
                "status": "task_failure",
                "success": False,
                "score": 0.5,
            },
            "agent-error": {
                "returncode": 1,
                "status": "agent_error",
                "success": False,
            },
        },
    )

    assert summary["planned"] == 3
    assert summary["completed"] == 2
    assert summary["failed"] == 1
    assert summary["successes"] == 1
    assert summary["task_failures"] == 1
    assert summary["mean_score"] == pytest.approx(0.75)


def test_combined_image_uses_only_roborsi_runtime_names() -> None:
    repository = Path(__file__).resolve().parents[4]
    dockerfile = (
        repository / "benchmarks/libero_three_combined/Dockerfile"
    ).read_text()

    assert "COPY roborsi/ /opt/roborsi/roborsi/" in dockerfile
    assert "ROBORSI_CONTEXT_TOKENIZER_PATH" in dockerfile
    assert "roborsi.evaluation.cli" not in dockerfile
    assert "/opt/heart" not in dockerfile


def test_agent_asset_lock_records_content_snapshots() -> None:
    repository = Path(__file__).resolve().parents[4]
    lock = json.loads(
        (repository / "benchmarks/libero_three_combined/assets.lock.json").read_text()
    )

    for name in (
        "libero_long_plus_plus_icl",
        "libero_ultra_long_icl",
        "libero_pro_icl",
    ):
        assert len(lock["assets"][name]["snapshot_sha256"]) == 64


def test_agent_asset_staging_requires_all_three_roots(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="expected ICL roots"):
        prepare_agent_assets(
            {},
            tmp_path / "tokenizer.json",
            tmp_path / "output",
            repository=tmp_path,
        )
