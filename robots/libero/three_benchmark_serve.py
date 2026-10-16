# Copyright 2026 The HEART Authors.
# Licensed under the Apache License, Version 2.0 (the "License");

"""Freeze three-LIBERO provider settings in a manifest-visible command."""

from __future__ import annotations

import argparse
import os


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmark",
        choices=("libero_pro", "libero_long_plus_plus", "libero_ultra_long"),
        required=True,
    )
    parser.add_argument(
        "--profile", choices=("official", "migration_subset"), required=True
    )
    parser.add_argument("--plus9-on-failure", action="store_true")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    os.environ["ROBORSI_LIBERO_BENCHMARK"] = args.benchmark
    os.environ["ROBORSI_LIBERO_PROFILE"] = args.profile
    os.environ["ROBORSI_LIBERO_PLUS9"] = "1" if args.plus9_on_failure else "0"
    from roborsi.evaluation.service_host import main as serve

    serve(
        [
            "--kind",
            "benchmark",
            "--factory",
            "robots.libero.three_benchmark_service:make_three_libero_benchmark",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ]
    )


if __name__ == "__main__":
    main()
