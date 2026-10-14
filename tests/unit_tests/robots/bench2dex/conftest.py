# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Shared synthetic task and sealed ICL fixtures."""


import pytest

from robots.bench2dex import contracts


@pytest.fixture
def task():
    return contracts.task_for("26", 5, smoke_steps=4)
