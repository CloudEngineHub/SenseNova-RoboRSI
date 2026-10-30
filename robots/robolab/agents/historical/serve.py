# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Serve the historical app-server policy using an explicitly pinned binary."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import signal
import subprocess
from pathlib import Path

from .codex_client import CodexClient, provider_identity
from .policy import CodexPolicy


def check_binary(executable: Path, version: str) -> dict:
    """Check the installed binary against the delivered upstream package lock."""
    manifest = json.loads(Path(__file__).with_name("codex-binaries.json").read_text())
    expected = manifest["versions"][version]
    actual = subprocess.check_output(
        [str(executable.resolve()), "--version"], text=True, timeout=20
    ).strip()
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    if actual != expected["version_output"] or digest != expected["binary_sha256"]:
        raise ValueError("Codex executable/version differs from codex-binaries.json")
    return {"version": actual, "sha256": digest}


def main() -> None:
    """Keep credentials on the Agent host and persist the effective settings."""
    from .websocket_server import WebsocketPolicyServer

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument(
        "--codex-version", choices=("0.159.2", "0.160.0"), required=True
    )
    parser.add_argument("--log-dir", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8020)
    args = parser.parse_args()
    binary = check_binary(args.codex, args.codex_version)
    args.log_dir.mkdir(parents=True, exist_ok=False)
    client = CodexClient(
        "gpt-6-astra",
        timeout=1200,
        image_size=320,
        reasoning_effort="max",
        codex_max_retries=30,
        executable=str(args.codex.resolve()),
    )
    policy = CodexPolicy(client, args.log_dir / "decisions.jsonl", image_size=320)
    config = {
        "schema_version": 1,
        "entry": "historical_app_server",
        "codex": binary,
        "model": client.model,
        "provider": provider_identity(client.base_url),
        "reasoning_effort": client.reasoning_effort,
        "image_size": client.image_size,
        "timeout": client.timeout,
        "codex_max_retries": client.codex_max_retries,
        "exploration": False,
        "prompt_sha256": hashlib.sha256(client.system.encode()).hexdigest(),
    }
    (args.log_dir / "effective-config.json").write_text(
        json.dumps(config, indent=2) + "\n"
    )

    def stop(_signum: int, _frame: object) -> None:
        policy.disconnect()
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        WebsocketPolicyServer(policy, host=args.host, port=args.port).serve_forever()
    finally:
        policy.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, force=True)
    main()
