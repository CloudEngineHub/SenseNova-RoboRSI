# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Passive episode accounting. This module has no access to a model or process."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

TOKEN_FIELDS = {
    "input_tokens": "inputTokens",
    "output_tokens": "outputTokens",
    "total_tokens": "totalTokens",
    "cached_input_tokens": "cachedInputTokens",
    "cache_write_input_tokens": "cacheWriteInputTokens",
    "reasoning_output_tokens": "reasoningOutputTokens",
}


def normalize_usage(usage: object) -> dict:
    """Keep unavailable counters distinct from reported zeros; never add details."""
    source = usage.get("total") if isinstance(usage, dict) else None
    result = {}
    for name, field in TOKEN_FIELDS.items():
        value = source.get(field) if isinstance(source, dict) else None
        result[name] = value if type(value) is int and value >= 0 else None
    return result


def read_codex_usage(path: Path) -> tuple[dict | None, bool]:
    """Scan only already recorded notifications, including those queued by an RPC.

    A damaged/missing log is a statistics problem, never a reason to ask Codex
    for more data. Preserve the last usable snapshot on a partial read.
    """
    latest = None
    complete = True
    try:
        with path.open("rb") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                    event = row.get("event", {})
                    if (
                        row.get("direction") != "receive"
                        or event.get("method") != "thread/tokenUsage/updated"
                    ):
                        continue
                    usage = normalize_usage(event.get("params", {}).get("tokenUsage"))
                    if any(value is not None for value in usage.values()):
                        latest = usage
                    else:
                        complete = False
                except (ValueError, UnicodeError, AttributeError, TypeError):
                    complete = False
    except OSError:
        complete = False
    if not complete:
        logger.warning(
            "Codex statistics log is missing, unreadable, or damaged: %s; usage is partial",
            path,
        )
    return latest, complete


class EpisodeStats:
    def __init__(
        self,
        *,
        log_path: Path,
        stats_path: Path,
        metadata: dict,
        episode_id: str,
        episode_index: int,
        instruction: str,
        max_steps: int,
        control_dt: float,
        started: float,
    ) -> None:
        self.stats_path = stats_path
        self.events_path = (
            log_path.with_suffix("") / f"episode-{episode_index:04d}" / "events.jsonl"
        )
        self.started = started
        self.finalized = False
        self.backend = metadata["backend"]
        if self.backend != "codex":
            raise ValueError("the historical cohort uses only Codex app-server")
        self.data = {
            "schema_version": 1,
            "episode_id": episode_id,
            "episode_index": episode_index,
            **{key: metadata[key] for key in ("backend", "model", "reasoning_effort")},
            "instruction": instruction,
            "max_steps": max_steps,
            "control_dt": control_dt,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "harness_seconds": 0.0,
            "finish_seconds": 0.0,
            "decision_count": 0,
            "issued_control_steps": 0,
            "executed_control_steps": 0,
            "control_steps_complete": False,
            "tokens": dict.fromkeys(TOKEN_FIELDS),
            "usage_complete": True,
            # Retain the historical accounting schema without an API backend.
            "api_attempt_count": None,
            "api_retry_count": None,
        }

    def request(
        self,
        *,
        record: dict,
        finished: float,
        called_backend: bool,
        confirmed_control_step: int | None,
        disconnected: bool,
    ) -> None:
        if self.finalized:
            return
        data = self.data
        data["harness_seconds"] += record["elapsed_ms"] / 1000
        ending = record["type"] == "end_episode"
        if ending:
            data["finish_seconds"] += record["elapsed_ms"] / 1000
        if confirmed_control_step is not None:
            data["executed_control_steps"] = confirmed_control_step
            data["control_steps_complete"] = ending
        if record["status"] == "ok":
            data["decision_count"] += 1
            data["issued_control_steps"] += len(record["actions"])
        if called_backend:
            usage = normalize_usage(record.get("usage"))
            if any(value is not None for value in usage.values()):
                # Fallback if the current episode's event log cannot be read.
                data["tokens"] = usage
        if disconnected or record.get("error_type") in (
            "KeyboardInterrupt",
            "SystemExit",
        ):
            self.finish(
                "interrupted",
                "disconnected" if disconnected else "interrupted",
                finished,
                record,
            )
        elif record["status"] == "execution_error":
            self.finish("execution_error", "execution_error", finished, record)
        elif record["status"] == "ended":
            failed = (
                record.get("reason") == "execution_error"
                or record.get("codex_finish", "completed") != "completed"
            )
            self.finish(
                "execution_error" if failed else "ended",
                record.get("reason"),
                finished,
                record,
            )

    def finish(
        self, status: str, reason: str, finished: float, record: dict | None = None
    ) -> None:
        if self.finalized:
            return
        # Freeze all times before scanning/writing logs. Mark first so failures
        # cannot cause a duplicate summary on a later close or request.
        self.finalized = True
        data = self.data
        data.update(
            ended_at=datetime.now(timezone.utc).isoformat(),
            wall_seconds=finished - self.started,
            status=status,
            end_reason=reason,
            simulated_seconds=data["executed_control_steps"] * data["control_dt"],
        )
        if record is not None:
            for key in ("error_type", "error", "codex_finish"):
                if key in record:
                    data[key] = record[key]
        usage, complete = read_codex_usage(self.events_path)
        if usage is not None:
            data["tokens"] = usage
        data["usage_complete"] &= complete and usage is not None
        data["usage_complete"] &= status == "ended" and all(
            value is not None for value in data["tokens"].values()
        )
        try:
            with self.stats_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(data, allow_nan=False) + "\n")
        finally:
            logger.info(
                "Episode %s (%s/%s) %s: wall=%.3fs harness=%.3fs tokens=%s "
                "usage_complete=%s decisions=%d executed_steps=%d steps_complete=%s; statistics: %s",
                data["episode_id"],
                self.backend,
                data["model"],
                status,
                data["wall_seconds"],
                data["harness_seconds"],
                data["tokens"]["total_tokens"],
                data["usage_complete"],
                data["decision_count"],
                data["executed_control_steps"],
                data["control_steps_complete"],
                self.stats_path,
            )
