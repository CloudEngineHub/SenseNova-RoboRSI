# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Exercise real wrapper/child cleanup without a GPU or native simulator."""

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from roborsi.evaluation.http_artifacts import ArtifactPublisher
from robots.bench2dex import native
from robots.bench2dex.roborsi_adapter import Bench2DexAdapter

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="native stack is Linux")


def running(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()
    except (FileNotFoundError, ProcessLookupError):
        return False
    return fields[0] not in {"Z", "X"}


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, (
            "process fixture did not reach expected state"
        )
        time.sleep(0.01)


@pytest.mark.parametrize(
    "parent_exits", [False, True], ids=["waiting-wrapper", "exited-wrapper"]
)
@pytest.mark.parametrize("ignore_term", [False, True], ids=["term", "kill-escalation"])
@pytest.mark.parametrize("through_adapter", [False, True], ids=["runtime", "adapter"])
def test_close_stops_native_children_after_wrapper_exit(
    tmp_path, monkeypatch, parent_exits, ignore_term, through_adapter
):
    """A wrapper exit must not hide a live or TERM-resistant simulator child."""
    monkeypatch.setattr(native, "_PROCESS_TERM_TIMEOUT_S", 0.2, raising=False)
    monkeypatch.setattr(native, "_PROCESS_KILL_TIMEOUT_S", 2.0, raising=False)
    child = tmp_path / "child.py"
    marker = tmp_path / "child.pid"
    child.write_text(
        "import os, signal, sys, time\n"
        "from pathlib import Path\n"
        + ("signal.signal(signal.SIGTERM, signal.SIG_IGN)\n" if ignore_term else "")
        + "Path(sys.argv[1]).write_text(str(os.getpid()))\n"
        "while True: time.sleep(1)\n"
    )
    # Match python-runtime.sh -> Isaac Sim python.sh -> actual interpreter.
    command = '"$1" "$2" "$3" &\n' + ("exit 0\n" if parent_exits else "wait\n")
    process = subprocess.Popen(
        [
            "/bin/sh",
            "-c",
            command,
            "native-wrapper",
            sys.executable,
            str(child),
            str(marker),
        ],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    runtime = native.NativeRuntime(
        tmp_path / "runtime",
        upstream=tmp_path,
        assets=tmp_path,
        isaaclab=tmp_path,
        python=Path(sys.executable),
    )
    runtime._process = process
    runtime._kit_cache = tempfile.TemporaryDirectory(dir=tmp_path)
    cache = Path(runtime._kit_cache.name)
    runtime._log = (tmp_path / "simulator.log").open("wb")
    try:
        owner = (
            Bench2DexAdapter(
                tmp_path / "adapter",
                ArtifactPublisher(tmp_path / "adapter", "cleanup"),
                runtime_factory=lambda directory: runtime,
            )
            if through_adapter
            else runtime
        )
        wait_until(lambda: marker.exists() and marker.read_text().strip())
        pid = int(marker.read_text())
        assert os.getpgid(pid) == process.pid
        if parent_exits:
            assert process.wait(timeout=5) == 0
        assert running(pid)
        started = time.monotonic()
        owner.close()
        assert time.monotonic() - started < 4
        assert not running(pid), "simulator child survived NativeRuntime.close()"
        assert process.poll() is not None
        assert runtime._log.closed and not cache.exists()
        with monkeypatch.context() as closed:

            def unexpected_signal(*args):
                raise AssertionError(
                    "repeated close signalled a released process group"
                )

            closed.setattr(native.os, "killpg", unexpected_signal)
            owner.close()
        assert not running(pid)
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        runtime._log.close()
        runtime._kit_cache.cleanup()


@pytest.mark.parametrize("through_adapter", [False, True], ids=["runtime", "adapter"])
def test_failed_group_cleanup_keeps_resources_for_retry(
    tmp_path, monkeypatch, through_adapter
):
    """A bounded cleanup failure must not release a live simulator's cache."""
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    runtime = native.NativeRuntime(
        tmp_path / "runtime",
        upstream=tmp_path,
        assets=tmp_path,
        isaaclab=tmp_path,
        python=Path(sys.executable),
    )
    runtime._process = process
    runtime._kit_cache = tempfile.TemporaryDirectory(dir=tmp_path)
    cache = Path(runtime._kit_cache.name)
    runtime._log = (tmp_path / "simulator.log").open("wb")
    real_killpg = os.killpg
    try:
        owner = (
            Bench2DexAdapter(
                tmp_path / "adapter",
                ArtifactPublisher(tmp_path / "adapter", "cleanup"),
                runtime_factory=lambda directory: runtime,
            )
            if through_adapter
            else runtime
        )
        with monkeypatch.context() as blocked:
            blocked.setattr(native, "_PROCESS_TERM_TIMEOUT_S", 0.02)
            blocked.setattr(native, "_PROCESS_KILL_TIMEOUT_S", 0.02)
            blocked.setattr(
                native.os,
                "killpg",
                lambda pid, sig: real_killpg(pid, sig) if sig == 0 else None,
            )
            started = time.monotonic()
            with pytest.raises(TimeoutError, match="process group did not stop"):
                owner.close()
            assert time.monotonic() - started < 2
        assert running(process.pid) and runtime._process is process
        assert cache.is_dir() and not runtime._log.closed
        if through_adapter:
            assert not owner.closed, "failed cleanup must remain retryable"
        owner.close()
        assert not running(process.pid) and runtime._process_group_closed
        assert not cache.exists() and runtime._log.closed
        if through_adapter:
            assert owner.closed
            with monkeypatch.context() as closed:
                closed.setattr(
                    runtime,
                    "close",
                    lambda: pytest.fail("successful Adapter close must be idempotent"),
                )
                owner.close()
    finally:
        try:
            real_killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        runtime._log.close()
        runtime._kit_cache.cleanup()


def test_adapter_retries_late_cache_cleanup(tmp_path, monkeypatch):
    """A late cleanup error must not bypass unfinished cache cleanup either."""
    runtime = native.NativeRuntime(
        tmp_path / "runtime",
        upstream=tmp_path,
        assets=tmp_path,
        isaaclab=tmp_path,
        python=Path(sys.executable),
    )
    adapter = Bench2DexAdapter(
        tmp_path / "adapter",
        ArtifactPublisher(tmp_path / "adapter", "cleanup"),
        runtime_factory=lambda directory: runtime,
    )
    with tempfile.TemporaryDirectory(dir=tmp_path) as cache_root:
        runtime._kit_cache = tempfile.TemporaryDirectory(dir=cache_root)
        cache = Path(runtime._kit_cache.name)
        with monkeypatch.context() as blocked:

            def fail_cleanup():
                raise OSError("cache cleanup failed")

            blocked.setattr(runtime._kit_cache, "cleanup", fail_cleanup)
            with pytest.raises(OSError, match="cache cleanup failed"):
                adapter.close()
        assert not adapter.closed and cache.is_dir()
        adapter.close()
        assert adapter.closed and not cache.exists()
