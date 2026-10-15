# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Offline contract tests with synthetic pixels; no model or simulator is used."""

from __future__ import annotations

import copy
import hashlib
import json

import numpy as np
import pytest

from roborsi.evaluation.http_artifacts import ArtifactPublisher
from roborsi.evaluation.messages import Action
from robots.bench2dex import contracts
from robots.bench2dex.reference.core import CAMERAS
from robots.bench2dex.roborsi_adapter import Bench2DexAdapter


@pytest.mark.parametrize("size", [0, 3, 1024 * 1024 + 3])
def test_artifact_hash_works_without_python311_file_digest(tmp_path, monkeypatch, size):
    data = (bytes(range(256)) * (size // 256 + 1))[:size]
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(data)
    monkeypatch.delattr(hashlib, "file_digest", raising=False)

    assert contracts.file_sha256(artifact) == hashlib.sha256(data).hexdigest()


def raw_observation(task, step):
    names = [f"joint_{i}" for i in range(54)]
    calibration = {
        "camera_model": "pinhole",
        "image_size_wh": [640, 480],
        "intrinsic_matrix": [[400, 0, 320], [0, 400, 240], [0, 0, 1]],
        "distortion_coefficients": [],
        "T_robot_base_from_camera_optical": np.eye(4).tolist(),
        "robot_base_link": "base",
        "optical_axes": "x_right_y_down_z_forward",
        "length_unit": "metre",
        "source": "exact_simulator_calibration_after_reset_randomization",
    }
    return {
        "language": task.instruction,
        "joint_action": {"vector": np.full(54, step / 100, np.float32)},
        "observation": {
            camera: {
                "rgb": np.full((480, 640, 3), step + i, np.uint8),
                "depth": "PRIVATE",
            }
            for i, camera in enumerate(CAMERAS["baseline_4cam"])
        },
        "camera_calibration": {
            camera: copy.deepcopy(calibration) for camera in CAMERAS["baseline_4cam"]
        },
        "robot_metadata": {
            "robot_key": task.native["robot_key"],
            "active_joint_names": names,
            "position_limits": [[-3, 3]] * 54,
            "action_semantics": "absolute active-joint position targets",
            "joint_units": ["radian_or_metre_per_URDF_type"] * 54,
            "physics_hz": 60,
            "policy_hz": 20,
        },
        "object_poses": "PRIVATE",
        "success": "PRIVATE",
        "reset_seed": "PRIVATE",
    }


class FakeNative:
    def __init__(self, task):
        self.task = task
        self.steps = 0
        self.result = None
        self.requests = []
        self.closed = False
        self.kinematic_card = {
            "joints": [
                {
                    "name": f"joint_{i}",
                    "type": "revolute",
                    "parent": {"link": "base"},
                    "child": {"link": f"link_{i}"},
                }
                for i in range(54)
            ],
            "inactive_joint_positions": {},
        }

    def start(self, task):
        assert task == self.task
        return raw_observation(task, 0)

    def advance(self, data):
        self.requests.append(data)
        self.steps += 1
        if self.steps == self.task.max_steps:
            self.result = {
                "success": False,
                "terminated_reason": "max_steps",
                "steps": self.steps * 3,
                "episode_index": self.task.seed,
            }
            return None
        return raw_observation(self.task, self.steps)

    def close(self):
        self.closed = True


def adapter(tmp_path, task):
    native = FakeNative(task)
    directory = tmp_path / "benchmark"
    publisher = ArtifactPublisher(directory, "episode-1")
    return Bench2DexAdapter(
        directory, publisher, runtime_factory=lambda _: native
    ), native


def test_all_native_tasks_preserve_budget_and_explicit_seed_mapping():
    assert len(contracts.TASKS) == 26
    for task_id, row in contracts.TASKS.items():
        task = contracts.task_for(task_id, 7)
        assert task.seed == 7 and task.native["episode_index"] == 7
        assert task.native["seed"] == 100000000
        assert task.native["inv_cov_seed"] == 200000000
        assert task.max_steps == row["policy_budget"]
        assert not task.native["smoke_only"]
        contracts.validate_task(task)
        with pytest.raises(ValueError):
            contracts.validate_task(
                task.model_copy(update={"max_steps": task.max_steps + 1})
            )


def test_sensor_whitelist_and_terminal_score_separation(tmp_path, task):
    boundary, native = adapter(tmp_path, task)
    start = boundary.start(task, "episode-1")
    assert "PRIVATE" not in json.dumps(start.observation.data)
    assert len(start.observation.media) == 4
    assert start.observation.data["sample"]["physics_step"] == 0
    for index in range(4):
        result = boundary.step(
            Action(
                benchmark="bench2dex",
                episode_id="episode-1",
                step_index=index,
                data={"actions": [[0] * 54]},
            )
        )
    assert result.observation.data == {"episode_done": True}
    assert result.native == {} and result.reward is None
    score = boundary.finish()
    assert not score.success and score.score == 0
    assert score.details["steps"] == 12
    assert not score.details["eligible_for_evaluation"]
    boundary.close()
    boundary.close()
    assert native.closed


@pytest.mark.parametrize(
    "payload",
    [
        {"actions": [[float("nan")] * 54]},
        {"actions": [[0] * 53]},
        {"actions": [[0] * 54] * 5},
        {"actions": [[True] * 54]},
    ],
)
def test_invalid_actions_fail_before_execution(task, payload):
    with pytest.raises(ValueError):
        contracts.validate_chunk(payload, task, 4)


def test_public_http_preserves_images_score_and_cleanup(tmp_path, task):
    """Run the actual common HTTP implementation across distinct media roots."""
    import threading

    from roborsi.evaluation.benchmark_client import BenchmarkClient
    from roborsi.evaluation.benchmark_http import (
        BenchmarkApplication,
        BenchmarkHttpServer,
    )
    from roborsi.evaluation.media import CaseMediaChannel

    native = FakeNative(task)

    class Provider:
        name = "bench2dex"

        def tasks(self):
            return [task]

        def runtime_info(self):
            return None

        def assets(self):
            return []

        def create_adapter(self, directory, publisher):
            return Bench2DexAdapter(
                directory, publisher, runtime_factory=lambda _: native
            )

    app = BenchmarkApplication(Provider(), tmp_path / "server-private")
    server = BenchmarkHttpServer(("127.0.0.1", 0), app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = BenchmarkClient(f"http://127.0.0.1:{server.server_port}")
    channel = CaseMediaChannel(tmp_path / "runner/media")
    try:
        start = client.start(task, "http-case", timeout_s=5)
        client.collect_observation(start.observation, channel, timeout_s=5)
        for i in range(task.max_steps):
            result = client.step(
                Action(
                    benchmark="bench2dex",
                    episode_id="http-case",
                    step_index=i,
                    data={"actions": [[0.0] * 54]},
                ),
                timeout_s=5,
            )
            if not result.terminated:
                client.collect_observation(result.observation, channel, timeout_s=5)
        assert result.observation.data == {"episode_done": True}
        scored = client.finish(timeout_s=5)
        client.collect_native(scored, channel.media_dir.parent, timeout_s=5)
        assert scored.score == 0 and scored.success is False
        assert len([x for x in client.artifacts() if x.kind == "image"]) == 16
        client.close()
        client.delete("http-case")
        assert native.closed
        channel.verify_observation(start.observation)
        assert (channel.media_dir.parent / "native/result.json").is_file()
    finally:
        app.close()
        server.shutdown()
        server.server_close()
        thread.join(3)
