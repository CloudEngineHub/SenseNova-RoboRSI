# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Run the completed historical 120 x 10 cohort with its original reset segments."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import queue
import re
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

from roborsi.evaluation.result import write_json_atomic
from robots.robolab.agents.historical.codex_client import (
    DEFAULT_BASE_URL,
    provider_identity,
)
from robots.robolab.agents.historical.serve import check_binary
from robots.robolab.assets import verify_assets
from robots.robolab.historical_native import (
    completed_runs,
    validate_result,
    validate_segments,
)


def load_plan(shards: list[int]) -> list[dict]:
    """Select whole shards without changing any included task's reset schedule."""
    root = Path(__file__).parent
    schedule = json.loads((root / "historical_schedule.json").read_text())
    recipe = json.loads((root / "full_task_1x.json").read_text())
    jobs = []
    seen = set()
    for index, phase in enumerate(schedule["phases"]):
        for worker in phase["workers"]:
            validate_segments(worker)
            for segment in worker["segments"]:
                for run in segment["run_ids"]:
                    identity = (segment["task_id"], run)
                    if identity in seen:
                        raise ValueError("duplicate task/run in historical schedule")
                    seen.add(identity)
            if worker["shard"] in shards:
                jobs.append(
                    {
                        **worker,
                        "phase": index,
                        "reference_process_group": phase["reference_process_group"],
                        "output_folder": recipe["shards"][worker["shard"]][
                            "reference_folder"
                        ],
                    }
                )
    expected = {
        (name, run)
        for shard in recipe["shards"]
        for name in shard["tasks"]
        for run in range(10)
    }
    if seen != expected:
        raise ValueError("historical schedule must cover exactly 1200 distinct runs")
    return jobs


def stop_process(process: subprocess.Popen | None) -> None:
    """Give the server time to reap its independently grouped Codex child."""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def verify_trial(row: dict, result_file: Path) -> tuple[str, int]:
    """Require finalized native evidence before accepting a completed run."""
    name, run = validate_result(row)
    task_dir = result_file.parent / name
    for filename in ("env_cfg.json", f"log_{run}_env0.json", f"run_{run}.hdf5"):
        artifact = task_dir / filename
        if not artifact.is_file() or artifact.stat().st_size == 0:
            raise ValueError(f"missing native artifact: {artifact}")
    detail = json.loads((task_dir / f"log_{run}_env0.json").read_text())
    expected = {
        "schema_version": 2,
        "task": name,
        "run": run,
        "env_id": 0,
        "success": row["success"],
    }
    if any(
        type(detail.get(key)) is not type(value) or detail[key] != value
        for key, value in expected.items()
    ):
        raise ValueError(f"native log identity or success disagrees for {name}/{run}")
    import h5py

    try:
        with h5py.File(task_dir / f"run_{run}.hdf5", "r") as recording:
            score = float(recording["data/demo_0/subtask/score"][-1].item())
    except (OSError, KeyError, ValueError, IndexError, TypeError) as exc:
        raise ValueError(f"invalid native HDF5 score for {name}/{run}") from exc
    if not math.isfinite(score) or score != row["score"]:
        raise ValueError(f"native HDF5 score disagrees for {name}/{run}")
    return name, run


def verify_completed_job(
    job: dict, directory: Path, result_file: Path, *, exact_prefix: bool
) -> None:
    """Recover only a wholly completed native process, never a partial RNG cohort."""
    if json.loads((directory / "job.json").read_text()) != job:
        raise ValueError("saved process does not match the historical plan")
    if (
        "ROBOLAB_HISTORICAL_SEGMENT_COMPLETED"
        not in (directory / "client.log").read_text()
    ):
        raise ValueError("native shutdown did not confirm the complete segment")
    expected = {(s["task_id"], run) for s in job["segments"] for run in s["run_ids"]}
    selected = set()
    for line in result_file.read_text().splitlines():
        row = json.loads(line)
        identity = (row.get("env_name"), row.get("run"))
        if identity in expected:
            verify_trial(row, result_file)
            if identity in selected:
                raise ValueError("duplicate native process result")
            selected.add(identity)
    if selected != expected:
        raise ValueError("native process result coverage differs")
    for segment in job["segments"]:
        actual = completed_runs(result_file, segment["task_id"])
        prefix = set(range(segment["run_ids"][-1] + 1))
        if (exact_prefix and actual != prefix) or not prefix <= actual:
            raise ValueError("native results differ from the historical reset boundary")


def mark_completed(job: dict, directory: Path) -> None:
    write_json_atomic(directory / "completed.json", {"job": job, "model_called": True})


def run_worker(
    job: dict,
    slot: tuple[str, int],
    args: argparse.Namespace,
    binaries: dict,
    stopped: threading.Event,
) -> None:
    """Keep model credentials on the host and native outputs on a separate mount."""
    gpu, port = slot
    name = f"phase-{job['phase']}-shard-{job['shard']}"
    directory = args.output / "processes" / name
    result_file = (
        args.output / "native" / job["output_folder"] / "episode_results.jsonl"
    )
    if directory.exists():
        if not args.resume:
            raise ValueError("a process directory already exists")
        try:
            verify_completed_job(job, directory, result_file, exact_prefix=False)
        except (OSError, ValueError, KeyError) as exc:
            raise ValueError(
                f"partial process {name}: use a fresh output directory to preserve the reset schedule"
            ) from exc
        # Covers a crash after native scoring but before writing this marker.
        mark_completed(job, directory)
        return
    for segment in job["segments"]:
        if completed_runs(result_file, segment["task_id"]) != set(
            range(segment["run_ids"][0])
        ):
            raise ValueError(
                "native results do not match the next historical reset boundary"
            )
    directory.mkdir(parents=True)
    job_path = directory / "job.json"
    job_path.write_text(json.dumps(job, indent=2) + "\n")
    server = native = None
    container = f"robolab-{args.run_id}-{name}"
    docker = ["docker", *(["--host", args.docker_host] if args.docker_host else [])]
    server_command = [
        str(args.agent_python),
        "-m",
        "robots.robolab.agents.historical.serve",
        "--codex",
        binaries[job["codex_version"]],
        "--codex-version",
        job["codex_version"],
        "--log-dir",
        str(directory / "agent"),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    native_command = [
        *docker,
        "run",
        "--rm",
        "--name",
        container,
        "--network",
        "host",
        "--gpus",
        f"device={gpu}",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--shm-size",
        "4g",
        "--tmpfs",
        "/tmp:rw,nosuid,size=8g,mode=1777",
        "--env",
        "OMNI_KIT_ACCEPT_EULA=YES",
        "--env",
        "CUDA_VISIBLE_DEVICES=0",
        "--mount",
        f"type=bind,source={args.assets},target=/roborsi/assets/robolab,readonly",
        "--mount",
        f"type=bind,source={args.output / 'native'},target=/opt/RoboLab/output",
        "--mount",
        f"type=bind,source={job_path},target=/job.json,readonly",
        "--entrypoint",
        "python",
        args.image,
        "-P",
        "-m",
        "robots.robolab.historical_native",
        "--job",
        "/job.json",
        "--output-folder",
        job["output_folder"],
        "--remote-port",
        str(port),
        "--kit-root",
        "/tmp/kit",
    ]
    (directory / "commands.json").write_text(
        json.dumps({"server": server_command, "native": native_command}, indent=2)
        + "\n"
    )
    try:
        with (
            (directory / "server.log").open("w") as server_log,
            (directory / "client.log").open("w") as client_log,
        ):
            server = subprocess.Popen(
                server_command,
                stdout=server_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                cwd=Path(__file__).resolve().parents[2],
                env={**os.environ, "OPENAI_BASE_URL": args.model_base_url},
            )
            deadline = time.monotonic() + 60
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            while True:
                if stopped.is_set() or server.poll() is not None:
                    raise RuntimeError(
                        "historical policy server stopped before readiness"
                    )
                try:
                    with opener.open(
                        f"http://127.0.0.1:{port}/healthz", timeout=1
                    ) as response:
                        if response.read() == b"OK\n":
                            break
                except (OSError, urllib.error.URLError):
                    pass
                if time.monotonic() > deadline:
                    raise TimeoutError("historical policy server readiness timed out")
                time.sleep(0.2)
            native = subprocess.Popen(
                native_command,
                stdout=client_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            while native.poll() is None:
                if stopped.is_set() or server.poll() is not None:
                    raise RuntimeError(
                        "historical process interrupted; partial outputs are retained"
                    )
                time.sleep(0.5)
            if native.returncode != 0:
                raise RuntimeError(
                    f"native process failed with exit {native.returncode}: {name}"
                )
        verify_completed_job(job, directory, result_file, exact_prefix=True)
        mark_completed(job, directory)
    finally:
        try:
            if native is not None:
                try:
                    subprocess.run(
                        [*docker, "stop", "--time", "10", container],
                        timeout=20,
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except subprocess.TimeoutExpired:
                    subprocess.run(
                        [*docker, "kill", container],
                        timeout=10,
                        check=True,
                        stdout=subprocess.DEVNULL,
                    )
        finally:
            try:
                stop_process(native)
            finally:
                stop_process(server)


def main() -> None:
    """Print a plan by default; --execute explicitly starts paid model calls."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", required=True, help="published repository@sha256:digest"
    )
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--codex-binaries", type=Path, required=True)
    parser.add_argument(
        "--agent-python",
        type=Path,
        help="isolated historical Agent Python (required with --execute)",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--gpus", default="0", help="comma-separated physical GPU indices"
    )
    parser.add_argument(
        "--shards", type=int, nargs="+", default=list(range(8)), choices=range(8)
    )
    parser.add_argument("--base-port", type=int, default=8020)
    parser.add_argument("--docker-host")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--resume", action="store_true", help="resume only completed process boundaries"
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", args.image):
        parser.error("image must be immutable repository@sha256:digest")
    gpus = args.gpus.split(",")
    if not all(gpu.isdecimal() for gpu in gpus) or len(set(gpus)) != len(gpus):
        parser.error("GPU indices must be nonempty and unique")
    if len(set(args.shards)) != len(
        args.shards
    ) or not 1 <= args.base_port <= 65535 - len(gpus):
        parser.error("invalid shards or port range")
    jobs = load_plan(args.shards)
    args.model_base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    plan = {
        "schema_version": 2,
        "image": args.image,
        "jobs": jobs,
        "expected_episodes": sum(
            len(s["run_ids"]) for j in jobs for s in j["segments"]
        ),
        "model": "gpt-6-astra",
        "provider": provider_identity(args.model_base_url),
        "reasoning_effort": "max",
        "budget_multiplier": 1,
    }
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return
    if args.agent_python is None or not args.agent_python.is_file():
        parser.error("--execute requires the separately installed --agent-python")
    args.agent_python = args.agent_python.absolute()
    args.assets, args.output = args.assets.resolve(), args.output.resolve()
    if args.output.is_relative_to(Path(__file__).resolve().parents[2]):
        parser.error("experiment outputs must stay outside the source repository")
    if args.resume:
        if json.loads((args.output / "plan.json").read_text()) != plan:
            parser.error("resume plan differs from the saved experiment")
    verify_assets(args.assets)
    binaries = json.loads(args.codex_binaries.read_text())
    for version in {job["codex_version"] for job in jobs}:
        binaries[version] = str(Path(binaries[version]).resolve())
        check_binary(Path(binaries[version]), version)
    fingerprint = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    if not args.resume:
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    args.run_id = fingerprint[:8] + "-" + uuid4().hex[:8]
    (args.output / "native").mkdir(exist_ok=True)
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    slots = queue.Queue()
    for index, gpu in enumerate(gpus):
        slots.put((gpu, args.base_port + index))

    def work(job: dict) -> None:
        slot = slots.get()
        try:
            if not stopped.is_set():
                run_worker(job, slot, args, binaries, stopped)
        except BaseException:
            stopped.set()
            raise
        finally:
            slots.put(slot)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(gpus)) as pool:
        for phase in sorted({job["phase"] for job in jobs}):
            futures = [pool.submit(work, job) for job in jobs if job["phase"] == phase]
            for future in concurrent.futures.as_completed(futures):
                future.result()
            if stopped.is_set():
                raise RuntimeError("historical experiment interrupted")
    if set(args.shards) == set(range(8)):
        expected = {
            (segment["task_id"], run)
            for job in jobs
            for segment in job["segments"]
            for run in segment["run_ids"]
        }
        seen = set()
        for path in sorted((args.output / "native").glob("*/episode_results.jsonl")):
            for line in path.read_text().splitlines():
                identity = verify_trial(json.loads(line), path)
                if identity in seen:
                    raise ValueError("duplicate native trial in completed experiment")
                seen.add(identity)
        if seen != expected:
            raise ValueError("completed experiment must contain exactly 1200 trials")
    print(f"Completed {plan['expected_episodes']} native episodes: {args.output}")


if __name__ == "__main__":
    main()
