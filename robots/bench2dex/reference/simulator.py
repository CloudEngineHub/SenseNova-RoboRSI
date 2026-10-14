# Copyright 2026 The Bench2Dex Evaluation Contributors.
# Licensing of this copied reference code is pending; see LICENSE_NOTICE.md.

"""Trusted entrypoint. Adapt upstream in memory without modifying its files."""

import argparse
import faulthandler
import os
import runpy
import sys
from functools import partial
from pathlib import Path

# A one-time private diagnostic for unexpectedly slow Kit startup; no time limit.
faulthandler.enable()
faulthandler.dump_traceback_later(90, repeat=False)

parser = argparse.ArgumentParser()
parser.add_argument("--upstream", required=True)
parser.add_argument("--deployment-profile", choices=["calibrated_deployment_v2"])
parser.add_argument(
    "--camera-profile",
    choices=["baseline_4cam", "baseline_3cam"],
    default="baseline_4cam",
)
opts, upstream_args = parser.parse_known_args()
repo = Path(opts.upstream).resolve()
sys.path.insert(0, str(repo))
from script import policy_rpc  # noqa: E402 - upstream is selected before import


class PatientClient(policy_rpc.RemotePolicyClient):
    def __init__(self, host, port, timeout_s=None):
        # The baseline's 30 s transport timeout is unsuitable for Codex reasoning.
        # This changes wall-clock waiting only; physics and metric code are intact.
        super().__init__(host, port, timeout_s=timeout_s)


policy_rpc.RemotePolicyClient = PatientClient
sys.argv = [str(repo / "run_policy.py"), *upstream_args]
ns = runpy.run_path(str(repo / "run_policy.py"), run_name="gpt6_upstream")
faulthandler.cancel_dump_traceback_later()
scope = ns["main"].__globals__
original = scope["_build_remote_policy_obs"]
from utils import inference_recorder  # noqa: E402 - requires initialized Kit

from .trajectory import TrajectoryRecorder  # noqa: E402 - initialized after Kit

trajectory_context = {
    "scene_file": scope["args_cli"].task,
    "scene_name": Path(scope["args_cli"].task).stem,
    "robot_key": scope["args_cli"].robot_key,
}
inference_recorder.InferenceRecorder = partial(
    TrajectoryRecorder, context=trajectory_context
)

# Gate before the first policy observation/model request, not after scoring.
# Capture actual effective RTX values rather than inferring them from a Kit file.
rendering_checked = False


def check_rendering():
    global rendering_checked
    if not rendering_checked:
        import carb
        from isaacsim.core.utils.stage import get_current_stage

        from .rendering import validate_rendering

        output = Path(scope["args_cli"].output_dir).parent / "rendering.json"
        settings = carb.settings.get_settings()
        tokens = carb.tokens.get_tokens_interface()
        search_paths = []
        for key in ("required", "templates"):
            value = settings.get(f"/renderer/mdl/searchPaths/{key}") or ""
            search_paths.extend(tokens.resolve(p) for p in value.split(";") if p)
        validate_rendering(
            get_current_stage(), settings, output, search_paths=search_paths
        )
        rendering_checked = True


original_episode = scope["_run_episode"]


def checked_episode(*args, **kwargs):
    global rendering_checked
    rendering_checked = False
    return original_episode(*args, **kwargs)


scope["_run_episode"] = checked_episode


def observation_with_robot_card(frames, robot_art, **kwargs):
    check_rendering()
    obs = original(frames, robot_art, **kwargs)
    info = scope["_active_dof_info"]
    names = list(info.active_joint_names)
    trajectory_context.update(robot=robot_art, action_names=names)
    # Preserve calibration only in the private recorder context. The policy
    # observation allowlist remains unchanged and never sees these fields.
    trajectory_context["camera_frames"] = frames
    limits = robot_art.data.joint_pos_limits[0].detach().cpu().numpy()
    limits = limits[info.active_indices]
    obs["robot_metadata"] = {
        "robot_key": info.robot_key,
        "active_joint_names": names,
        "position_limits": limits.tolist(),
        "action_semantics": "absolute active-joint position targets",
        "joint_units": ["radian_or_metre_per_URDF_type"] * len(names),
        "physics_hz": 60,
        "policy_hz": 20,
    }
    if opts.deployment_profile:
        import numpy as np
        from scipy.spatial.transform import Rotation

        from .calibration import export_calibration
        from .core import CAMERAS
        from .kinematics_tool import root_link
        from .robot import kinematics

        if "calibration_base_link" not in trajectory_context:
            import yaml

            maps = yaml.safe_load((repo / "robots/active_dof_maps.yml").read_text())
            uri = maps["robots"][info.robot_key]["urdf_path"].removeprefix("Bench2Dex/")
            base = root_link(
                kinematics(Path(os.environ["DEX2BENCH_DATASET_ROOT"]) / uri)["joints"]
            )
            if base not in robot_art.body_names:
                raise RuntimeError("URDF base link not found in runtime articulation")
            trajectory_context["calibration_base_link"] = base
        base = trajectory_context["calibration_base_link"]
        pose = (
            robot_art.data.body_link_pose_w[0, robot_art.body_names.index(base)]
            .detach()
            .cpu()
            .numpy()
        )
        world_from_base = np.eye(4)
        world_from_base[:3, :3] = Rotation.from_quat(pose[[4, 5, 6, 3]]).as_matrix()
        world_from_base[:3, 3] = pose[:3]
        obs["camera_calibration"] = export_calibration(
            frames, world_from_base, base, CAMERAS[opts.camera_profile]
        )
    return obs


scope["_build_remote_policy_obs"] = observation_with_robot_card
exit_code = 0
try:
    ns["main"]()
except Exception:
    import traceback

    traceback.print_exc()
    exit_code = 1
finally:
    ns["simulation_app"].close()
    # Match upstream teardown: Kit's extension destructors are not Python-safe.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
