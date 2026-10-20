# Copyright 2026 The HEART Authors.
# Licensed under the Apache License, Version 2.0 (the "License");

"""Run a complete three-LIBERO migration subset in one deployment image."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

_EXPECTED = {
    "libero_long_plus_plus": 12,
    "libero_ultra_long": 9,
    "libero_pro": 80,
}
_VALID_TERMINALS = {"success", "task_failure"}


def _tasks(repository: Path, benchmark: str) -> tuple[str, ...]:
    path = repository / "robots/libero/agents/three_benchmark/context_maps" / f"{benchmark}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    packages = document.get("packages") if isinstance(document, dict) else None
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != 1
        or not isinstance(packages, dict)
    ):
        raise ValueError(f"invalid repository context map: {path}")
    tasks = tuple(sorted(packages))
    if len(tasks) != _EXPECTED[benchmark]:
        raise ValueError(f"{benchmark} context map needs {_EXPECTED[benchmark]} tasks")
    return tasks


def _record_result(root: Path) -> dict[str, Any]:
    matches = list(root.rglob("result.json"))
    if len(matches) != 1:
        return {"status": "missing", "result_count": len(matches)}
    result = json.loads(matches[0].read_text(encoding="utf-8"))
    return {key: result.get(key) for key in ("status", "success", "score", "error")}


def _completed_attempt(case_root: Path) -> tuple[Path, dict[str, Any]] | None:
    for attempt in sorted(case_root.glob("attempt-*"), reverse=True):
        record = _record_result(attempt)
        if record.get("status") in _VALID_TERMINALS:
            return attempt, record
    return None


def _next_attempt(case_root: Path) -> Path:
    numbers = []
    for path in case_root.glob("attempt-*"):
        try:
            numbers.append(int(path.name.removeprefix("attempt-")))
        except ValueError:
            continue
    return case_root / f"attempt-{max(numbers, default=0) + 1:04d}"


def _summary(
    benchmark: str, run_id: str, selected: tuple[str, ...], records: dict[str, Any]
) -> dict[str, Any]:
    ordered = [records[task] for task in selected]
    invalid = [
        record
        for record in ordered
        if record.get("returncode") != 0 or record.get("status") not in _VALID_TERMINALS
    ]
    scores = [
        float(record["score"])
        for record in ordered
        if isinstance(record.get("score"), (int, float))
    ]
    successes = sum(record.get("success") is True for record in ordered)
    return {
        "schema_version": 1,
        "benchmark": benchmark,
        "run_id": run_id,
        "planned": len(selected),
        "completed": len(selected) - len(invalid),
        "failed": len(invalid),
        "successes": successes,
        "task_failures": sum(
            record.get("status") == "task_failure" for record in ordered
        ),
        "success_rate": successes / len(selected) if selected else 0.0,
        "mean_score": sum(scores) / len(scores) if scores else None,
        "cases": ordered,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=tuple(_EXPECTED), required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--task", action="append", default=[])
    parser.add_argument("--max-concurrent", type=int, default=16)
    parser.add_argument("--gpu-count", type=int, default=1)
    parser.add_argument("--port-base", type=int, default=18400)
    parser.add_argument("--timeout-s", type=float, default=43200)
    parser.add_argument("--case-timeout-s", type=float, default=14400)
    parser.add_argument("--api-key-file", type=Path, required=True)
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL"))
    args = parser.parse_args()
    if args.max_concurrent < 1:
        parser.error("--max-concurrent must be positive")
    if args.gpu_count < 1:
        parser.error("--gpu-count must be positive")
    if not args.base_url:
        parser.error("--base-url or OPENAI_BASE_URL is required")

    repository = Path(__file__).resolve().parents[2]
    declared = _tasks(repository, args.benchmark)
    selected = tuple(args.task) if args.task else declared
    if len(selected) != len(set(selected)) or not set(selected) <= set(declared):
        parser.error("--task values must be unique members of the migration subset")

    root = args.results_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    plan = {
        "schema_version": 1,
        "benchmark": args.benchmark,
        "run_id": args.run_id,
        "tasks": list(selected),
        "max_concurrent": args.max_concurrent,
        "gpu_count": args.gpu_count,
    }
    plan_path = root / "subset-plan.json"
    if plan_path.exists():
        existing = json.loads(plan_path.read_text(encoding="utf-8"))
        if existing != plan:
            raise ValueError("results root belongs to a different subset plan")
    else:
        plan_path.write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def run(index_task: tuple[int, str]) -> tuple[str, dict[str, Any]]:
        index, task = index_task
        case_root = root / "cases" / task
        completed = _completed_attempt(case_root)
        if completed is not None:
            attempt, record = completed
            return task, {
                "task_id": task,
                "returncode": 0,
                "attempt": attempt.name,
                "cached": True,
                **record,
            }

        attempt = _next_attempt(case_root)
        log_path = root / "logs" / f"{task}-{attempt.name}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-B",
            str(repository / "benchmarks/libero_three_combined/run_combined.py"),
            "--benchmark",
            args.benchmark,
            "--task",
            task,
            "--run-id",
            f"{args.run_id}-{task}-{attempt.name}",
            "--results-root",
            str(attempt),
            "--port",
            str(args.port_base + index),
            "--timeout-s",
            str(args.timeout_s),
            "--case-timeout-s",
            str(args.case_timeout_s),
            "--api-key-file",
            str(args.api_key_file),
            "--base-url",
            args.base_url,
        ]
        with log_path.open("w", encoding="utf-8") as log:
            completed_process = subprocess.run(
                command,
                cwd=repository,
                env={
                    **os.environ,
                    "MUJOCO_EGL_DEVICE_ID": str(index % args.gpu_count),
                    "OMP_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1",
                },
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        return task, {
            "task_id": task,
            "returncode": completed_process.returncode,
            "attempt": attempt.name,
            "cached": False,
            **_record_result(attempt),
        }

    records: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=args.max_concurrent) as executor:
        futures = {executor.submit(run, item): item[1] for item in enumerate(selected)}
        for future in as_completed(futures):
            task, record = future.result()
            records[task] = record
            print(
                "ROBORSI_SUBSET_CASE="
                + json.dumps(
                    {
                        "benchmark": args.benchmark,
                        "task_id": task,
                        "status": record.get("status"),
                        "success": record.get("success"),
                        "score": record.get("score"),
                        "returncode": record["returncode"],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

    summary = _summary(args.benchmark, args.run_id, selected, records)
    (root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "ROBORSI_SUBSET_RESULT="
        + json.dumps(
            {key: summary[key] for key in summary if key != "cases"},
            sort_keys=True,
        ),
        flush=True,
    )
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
