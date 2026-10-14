# Copyright 2026 The HEART Authors.
# Licensed under the Apache License, Version 2.0 (the "License");

"""Official R1Pro 21D control and offline 23D demonstration conversion."""

import copy


EEF21 = "r1pro_eef21_v1"


def action_dimension(profile=EEF21):
    if profile != EEF21:
        raise ValueError(f"Unknown R1Pro action_profile: {profile!r}")
    return 21


def validate_include_depth(profile, include_depth):
    """Keep official evaluation on the official full-resolution RGB-D wrapper."""
    if type(include_depth) is not bool:
        raise ValueError("include_depth must be boolean")
    if not include_depth:
        raise ValueError("official requires RGBDFullResWrapper (include_depth=true)")
    return include_depth


def robot_config_for_profile(config, profile=EEF21):
    """Replace complete arm blocks: JointController-only arguments are invalid for IK."""
    action_dimension(profile)
    result = copy.deepcopy(config)
    result["action_normalize"] = False
    for arm in ("left", "right"):
        result["controller_config"][f"arm_{arm}"] = {
            "name": "InverseKinematicsController",
            "mode": "absolute_pose",
            "command_input_limits": None,
            "command_output_limits": None,
            "use_impedances": False,
            "pos_kp": 150,
            "smoothing_filter_size": 2,
        }
    return result
