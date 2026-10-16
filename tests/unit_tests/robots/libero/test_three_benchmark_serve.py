# Copyright 2026 The HEART Authors.
# Licensed under the Apache License, Version 2.0 (the "License");

from robots.libero import three_benchmark_serve


def test_serve_freezes_manifest_visible_environment(monkeypatch):
    received = []
    environment = {}

    def fake_serve(arguments):
        received.extend(arguments)

    import roborsi.evaluation.service_host

    monkeypatch.setattr(roborsi.evaluation.service_host, "main", fake_serve)
    monkeypatch.setattr(three_benchmark_serve.os, "environ", environment)
    three_benchmark_serve.main(
        [
            "--benchmark",
            "libero_ultra_long",
            "--profile",
            "migration_subset",
            "--plus9-on-failure",
        ]
    )
    assert environment["ROBORSI_LIBERO_BENCHMARK"] == "libero_ultra_long"
    assert environment["ROBORSI_LIBERO_PROFILE"] == "migration_subset"
    assert environment["ROBORSI_LIBERO_PLUS9"] == "1"
    assert received[-2:] == ["--port", "8000"]
