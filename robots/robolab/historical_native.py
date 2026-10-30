# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Replay one historical native process segment using RoboLab's original runner."""

from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from pathlib import Path

from robots.robolab.contracts import catalog_tasks
from robots.robolab.native import native_root, verify_native_source


def validate_segments(document: dict) -> list[dict]:
    """Require contiguous original run numbers and declared native task names."""
    segments = document["segments"]
    names = {task.task_id for task in catalog_tasks()}
    seen = set()
    if not segments:
        raise ValueError("empty historical process segment")
    for segment in segments:
        name, runs = segment["task_id"], segment["run_ids"]
        if name not in names or name in seen or not runs:
            raise ValueError("unknown or repeated historical task")
        if any(type(run) is not int or not 0 <= run < 10 for run in runs):
            raise ValueError("historical run IDs must be integers from zero to nine")
        if runs != list(range(runs[0], runs[-1] + 1)):
            raise ValueError("historical run IDs must be contiguous and ordered")
        seen.add(name)
    return segments


def validate_result(row: dict) -> tuple[str, int]:
    """A native completion requires explicit identity, outcome and finite score."""
    name, run = row.get("env_name"), row.get("run")
    if (
        not isinstance(name, str)
        or type(run) is not int
        or not 0 <= run < 10
        or type(row.get("episode")) is not int
        or row["episode"] != run
        or type(row.get("env_id")) is not int
        or row["env_id"] != 0
        or row.get("policy") != "harness"
        or row.get("instruction_type") != "default"
        or type(row.get("success")) is not bool
        or not isinstance(row.get("reason"), str)
        or not row["reason"].strip()
        or type(row.get("score")) not in (int, float)
        or not math.isfinite(row["score"])
    ):
        raise ValueError("unscored or incompatible historical result")
    return name, run


def completed_runs(path: Path, task_id: str) -> set[int]:
    """Refuse duplicates and unscored rows before invoking a paid policy."""
    runs = set()
    if path.is_file():
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row["env_name"] != task_id:
                continue
            _, index = validate_result(row)
            if index in runs:
                raise ValueError("duplicate or unscored historical result")
            runs.add(index)
    return runs


def main() -> None:
    """One Kit process; each task retains sequential double resets and scoring."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--output-folder", required=True)
    parser.add_argument("--remote-host", default="127.0.0.1")
    parser.add_argument("--remote-port", type=int, required=True)
    parser.add_argument("--kit-root", type=Path, required=True)
    args = parser.parse_args()
    if Path(args.output_folder).name != args.output_folder or args.output_folder in {
        ".",
        "..",
    }:
        parser.error("output folder must be a single relative name")
    segments = validate_segments(json.loads(args.job.read_text()))
    root = native_root()
    verify_native_source(root)
    results = root / "output" / args.output_folder / "episode_results.jsonl"
    for segment in segments:
        if completed_runs(results, segment["task_id"]) != set(
            range(segment["run_ids"][0])
        ):
            raise ValueError(
                "existing results change the historical reset schedule; use a fresh run directory"
            )
    sys.path.insert(0, str(root))
    import cv2  # noqa: F401 -- must precede Isaac Lab
    from isaaclab.app import AppLauncher
    from robolab.eval.runner import add_common_eval_args

    native_parser = argparse.ArgumentParser()
    add_common_eval_args(native_parser)
    AppLauncher.add_app_launcher_args(native_parser)
    native_args = native_parser.parse_args(
        [
            "--num-envs",
            "1",
            "--headless",
            "--device",
            "cuda:0",
            "--instruction-type",
            "default",
            "--video-mode",
            "all",
            "--renderer",
            "realtime",
            "--output-folder-name",
            args.output_folder,
            "--kit_args",
            f"--portable-root {args.kit_root} --/renderer/multiGpu/enabled=false --/renderer/activeGpu=0",
        ]
    )
    native_args.enable_cameras = True
    app = AppLauncher(native_args).app
    clients = []
    try:
        from policies.harness_policy.client import HarnessClient, validate_eval_args
        from robolab.eval.runner import run_evaluation
        from robolab.registrations.droid.auto_env_registrations_abs_ik import (
            auto_register_droid_abs_ik_envs,
        )

        auto_register_droid_abs_ik_envs(
            task_dirs=["benchmark"], task=[s["task_id"] for s in segments]
        )

        def make_client(_eval_args):
            if clients:
                clients.pop().close()
            client = HarnessClient(args.remote_host, args.remote_port, timeout=2400)
            clients.append(client)
            return client

        for segment in segments:
            native_args.task = [segment["task_id"]]
            native_args.num_runs = segment["run_ids"][-1] + 1
            validate_eval_args(native_args)
            run_evaluation(native_args, policy="harness", client_factory=make_client)
            if completed_runs(results, segment["task_id"]) != set(
                range(native_args.num_runs)
            ):
                raise RuntimeError(
                    "native runner did not complete the requested segment"
                )
        print("ROBOLAB_HISTORICAL_SEGMENT_COMPLETED", flush=True)
    except BaseException:
        # Kit fast shutdown must not hide the original exception from a log.
        traceback.print_exc()
        raise
    finally:
        for client in clients:
            client.close()
        app.close()


if __name__ == "__main__":
    main()
