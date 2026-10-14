# Copyright 2026 The Bench2Dex Evaluation Contributors.
# Licensing of this copied reference code is pending; see LICENSE_NOTICE.md.

"""Trusted, incremental recorder using Bench2Dex's HDF5 replay field names.

Called at the upstream 20 Hz pre-action recording point. Each sample is closed
to disk independently; unfinished episodes remain explicitly in partial/.
This is a sampled visualization trajectory, not a full physics checkpoint.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import h5py
import numpy as np
from PIL import Image


class TrajectoryRecorder:
    def __init__(self, record_dir, record_all=False, *, clear=True, context=None):
        self.root = Path(record_dir)
        # Never implement upstream's destructive directory clearing behavior.
        if self.root.exists() and any(self.root.rglob("*.hdf5")):
            raise ValueError("Trajectory directory must not contain existing episodes")
        self.context = context if context is not None else {}
        self.path = None
        self.object_ids = []
        self.frames = 0
        self.started = None

    def start_episode(
        self,
        object_ids,
        camera_ids,
        episode_idx=-1,
        *,
        joint_names=None,
        action_names=None,
        metadata=None,
    ):
        if self.path is not None:
            raise RuntimeError("Previous trajectory was not finalized")
        self.path = self.root / "partial" / f"episode_{episode_idx:06d}.hdf5"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.object_ids, self.camera_ids = list(object_ids), list(camera_ids)
        self.frames, self.started = 0, time.monotonic()
        with h5py.File(self.path, "x") as hf:
            meta = hf.create_group("meta")
            meta.create_dataset("frame_count", data=np.int64(0))
            meta.create_dataset("episode_index", data=np.int64(episode_idx))
            meta.create_dataset("fps", data=np.float64(20))
            meta.create_dataset("physics_hz", data=np.int64(60))
            meta.create_dataset("physics_dt", data=np.float64(1 / 60))
            meta.create_dataset("step_stride", data=np.int64(3))
            hf.attrs["finalized"] = False
            hf.attrs["sample_phase"] = "pre_action; no extra terminal-state sample"
            hf.attrs["policy_step_offset"] = self.context.get("policy_step_offset", 0)
            hf.attrs["image_encoding"] = (
                "JPEG quality=90, original resolution; policy PNGs archived separately"
            )
            for key, value in (metadata or {}).items():
                self._text(hf, f"meta/{key}", json.dumps(value, sort_keys=True))
            for key in ("scene_file", "scene_name", "robot_key"):
                self._text(hf, f"meta/{key}", self.context.get(key, ""))
            if joint_names:
                self._names(hf, "robot/joint_names", joint_names)
            if action_names:
                self._names(hf, "action/action_names", action_names)

    @staticmethod
    def _text(hf, key, value):
        hf.create_dataset(key, data=value, dtype=h5py.string_dtype("utf-8"))

    @staticmethod
    def _names(hf, key, values):
        if key not in hf:
            hf.create_dataset(
                key, data=np.asarray(values, dtype=h5py.string_dtype("utf-8"))
            )

    def _append(self, hf, key, value):
        value = np.asarray(value)
        if key not in hf:
            hf.create_dataset(
                key,
                shape=(0, *value.shape),
                maxshape=(None, *value.shape),
                chunks=(1, *value.shape),
                dtype=value.dtype,
            )
        ds = hf[key]
        if ds.shape[0] != self.frames:
            raise ValueError(f"Noncontiguous trajectory field: {key}")
        ds.resize(self.frames + 1, axis=0)
        ds[self.frames] = value

    def current_object_ids(self):
        return self.object_ids

    def record_step(self, qpos, action, object_states, camera_frames):
        if self.path is None:
            raise RuntimeError("Trajectory has not started")
        with h5py.File(self.path, "a") as hf:
            robot = self.context.get("robot")
            if robot is not None:
                self._names(hf, "robot/joint_names", list(robot.data.joint_names))
                for name, attr in (
                    ("qvel", "joint_vel"),
                    ("root_state_world", "root_state_w"),
                ):
                    self._append(
                        hf,
                        f"robot/{name}",
                        getattr(robot.data, attr)[0].detach().cpu().numpy(),
                    )
            if self.context.get("action_names"):
                self._names(hf, "action/action_names", self.context["action_names"])
            self._append(hf, "robot/qpos", np.asarray(qpos, dtype=np.float32))
            self._append(hf, "action/commanded", np.asarray(action, dtype=np.float32))
            absolute_step = self.frames + self.context.get("policy_step_offset", 0)
            self._append(hf, "time/physics_step", np.int64(absolute_step * 3))
            self._append(hf, "time/sim_seconds", np.float64(absolute_step / 20))
            for oid in self.object_ids:
                state = object_states.get(oid)
                if state is None:
                    raise ValueError(f"Missing recorded object state: {oid}")
                for key in (
                    "pose_world",
                    "lin_vel_world",
                    "ang_vel_world",
                    "qpos",
                    "qvel",
                ):
                    if key in state and state[key] is not None:
                        self._append(
                            hf,
                            f"objects/{oid}/{key}",
                            np.asarray(state[key], dtype=np.float32),
                        )
                if "joint_names" in state:
                    self._names(hf, f"objects/{oid}/joint_names", state["joint_names"])
            for cid in self.camera_ids:
                camera = self.context.get("camera_frames", {}).get(cid)
                for name in (
                    "intrinsic",
                    "extrinsic_world_from_cam",
                    "cam_pos_w",
                    "cam_quat_wxyz",
                    "distortion_coefficients",
                    "fisheye_camera_matrix",
                    "clipping_range",
                ):
                    value = (
                        camera.get(name)
                        if isinstance(camera, dict)
                        else getattr(camera, name, None)
                    )
                    if value is not None:
                        self._append(hf, f"cameras/{cid}/{name}", np.asarray(value))
                model = (
                    camera.get("camera_model")
                    if isinstance(camera, dict)
                    else getattr(camera, "camera_model", None)
                )
                if model is not None and f"cameras/{cid}/camera_model" not in hf:
                    self._text(hf, f"cameras/{cid}/camera_model", model)
                frame = camera_frames.get(cid)
                encoded = io.BytesIO()
                if frame is not None:
                    Image.fromarray(np.asarray(frame, dtype=np.uint8)[..., :3]).save(
                        encoded, format="JPEG", quality=90, subsampling=0
                    )
                key = f"cameras/{cid}/rgb"
                if key not in hf:
                    hf.create_dataset(
                        key,
                        shape=(0,),
                        maxshape=(None,),
                        chunks=(1,),
                        dtype=h5py.vlen_dtype(np.dtype("uint8")),
                    )
                hf[key].resize(self.frames + 1, axis=0)
                hf[key][self.frames] = np.frombuffer(encoded.getvalue(), dtype=np.uint8)
            # Commit marker written last. An interrupted sample beyond this
            # count must never be interpreted as a complete state.
            self.frames += 1
            hf["meta/frame_count"][()] = self.frames
            hf.flush()

    def finish_episode(self, success):
        if self.path is None:
            return None
        with h5py.File(self.path, "a") as hf:
            hf.attrs["finalized"] = True
            hf.attrs["official_success"] = bool(success)
            hf.attrs["recording_wall_seconds"] = time.monotonic() - self.started
        target = self.root / ("success" if success else "failure") / self.path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(target)
        self.path.rename(target)
        self.path = None
        return str(target)
