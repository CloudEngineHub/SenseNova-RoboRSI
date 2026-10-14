# Copyright 2026 The Bench2Dex Evaluation Contributors.
# Licensing of this copied reference code is pending; see LICENSE_NOTICE.md.

"""Trusted camera-only allowlist; expose optical poses in robot coordinates."""

import numpy as np

PROFILE = "calibrated_deployment_v2"
# Isaac camera axes: forward/left/up; optical axes: right/down/forward.
RAW_FROM_OPTICAL = np.array(
    [[0, 0, 1, 0], [-1, 0, 0, 0], [0, -1, 0, 0], [0, 0, 0, 1]], dtype=float
)


def rigid(value):
    array = np.asarray(value, dtype=float)
    if array.shape != (4, 4) or not np.isfinite(array).all():
        raise ValueError("Invalid calibration transform")
    if (
        not np.allclose(array[3], [0, 0, 0, 1], atol=1e-6)
        or not np.allclose(array[:3, :3].T @ array[:3, :3], np.eye(3), atol=1e-4)
        or not np.isclose(np.linalg.det(array[:3, :3]), 1, atol=1e-4)
    ):
        raise ValueError("Calibration transform is not rigid")
    return array


def export_calibration(frames, world_from_base, base_link, cameras):
    base_from_world = np.linalg.inv(rigid(world_from_base))
    result = {}
    for name in cameras:
        frame = frames[name]
        model = frame.camera_model
        if model not in ("pinhole", "fisheye"):
            raise ValueError("Unsupported camera model")
        matrix = frame.fisheye_camera_matrix if model == "fisheye" else frame.intrinsic
        distortion = frame.distortion_coefficients
        if model == "fisheye" and distortion is None:
            raise ValueError("Missing fisheye distortion")
        # Reconstruct from selected fields; never copy a CameraFrame dictionary.
        result[name] = {
            "camera_model": model,
            "image_size_wh": list(reversed(frame.image_shape)),
            "intrinsic_matrix": np.asarray(matrix).tolist(),
            "distortion_coefficients": []
            if distortion is None
            else np.asarray(distortion).tolist(),
            "T_robot_base_from_camera_optical": (
                base_from_world
                @ rigid(frame.extrinsic_world_from_cam)
                @ RAW_FROM_OPTICAL
            ).tolist(),
            "robot_base_link": base_link,
            "optical_axes": "x_right_y_down_z_forward",
            "length_unit": "metre",
            "source": "exact_simulator_calibration_after_reset_randomization",
        }
    return validate_calibration(result, cameras)


def validate_calibration(raw, cameras):
    keys = {
        "camera_model",
        "image_size_wh",
        "intrinsic_matrix",
        "distortion_coefficients",
        "T_robot_base_from_camera_optical",
        "robot_base_link",
        "optical_axes",
        "length_unit",
        "source",
    }
    output = {}
    for name in cameras:
        item = raw[name]
        if set(item) != keys or item["camera_model"] not in ("pinhole", "fisheye"):
            raise ValueError("Unexpected calibration fields/model")
        matrix = np.asarray(item["intrinsic_matrix"], dtype=float)
        distortion = np.asarray(item["distortion_coefficients"], dtype=float)
        if (
            matrix.shape != (3, 3)
            or not np.isfinite(matrix).all()
            or matrix[0, 0] <= 0
            or matrix[1, 1] <= 0
            or not np.allclose(matrix[2], [0, 0, 1])
        ):
            raise ValueError("Invalid camera intrinsic matrix")
        if not np.isfinite(distortion).all() or distortion.shape != (
            (4,) if item["camera_model"] == "fisheye" else (0,)
        ):
            raise ValueError("Invalid/unsupported distortion model")
        if (
            item["image_size_wh"] != [640, 480]
            or item["optical_axes"] != "x_right_y_down_z_forward"
            or item["length_unit"] != "metre"
        ):
            raise ValueError("Calibration image size or convention mismatch")
        if item[
            "source"
        ] != "exact_simulator_calibration_after_reset_randomization" or not isinstance(
            item["robot_base_link"], str
        ):
            raise ValueError("Calibration provenance/frame mismatch")
        rigid(item["T_robot_base_from_camera_optical"])
        output[name] = {key: item[key] for key in sorted(keys)}
    return output
