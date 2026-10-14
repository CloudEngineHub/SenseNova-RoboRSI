# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Preserve native stopping, source identity and authoritative scoring."""

from pathlib import Path

from .test_protocol_contracts import adapter


def test_native_policy_stop_uses_original_error_envelope_without_action(
    tmp_path, task, monkeypatch
):
    from robots.bench2dex.native import NativeRuntime

    runtime = NativeRuntime(
        tmp_path,
        upstream=tmp_path,
        assets=tmp_path,
        isaaclab=tmp_path,
        python=Path("/unused"),
    )
    runtime.task = task
    observed = []

    def finish():
        observed.append(runtime._commands.get_nowait())
        runtime.result = {"success": False, "terminated_reason": "error"}

    monkeypatch.setattr(runtime, "_next", finish)
    runtime.stop_policy()
    assert observed == [{"error": "Policy infrastructure failure"}]
    assert runtime.steps == 0 and runtime.policy_failed
    runtime.close()

def test_runtime_source_identity_does_not_require_unmerged_registration(monkeypatch):
    from roborsi.benchmarks import runtime_source
    from robots.bench2dex.benchmark_service import adapter_digest

    def unregistered(*args):
        raise ValueError("unsupported Benchmark source bundle")

    monkeypatch.setattr(runtime_source, "benchmark_source_digest", unregistered)
    assert len(adapter_digest()) == 64

def test_success_requires_native_stable_stop_not_transient_flag(tmp_path, task):
    boundary, native = adapter(tmp_path, task)
    boundary.start(task, "episode-1")
    boundary.ended = True
    native.result = {"success": True, "terminated_reason": "max_steps", "steps": 12}
    try:
        result = boundary.finish()
        assert result.score == 0 and not result.success
        assert result.details["official_success"] is True
    finally:
        boundary.close()
