# Copyright 2026 The Bench2Dex Evaluation Contributors.
# Licensing of this copied reference code is pending; see LICENSE_NOTICE.md.

"""Static, deployment-accessible kinematic description; no scene geometry."""

import xml.etree.ElementTree as ET
from pathlib import Path


def kinematics(urdf: Path) -> dict:
    tree = ET.parse(urdf).getroot()
    joints = []
    for joint in tree.findall("joint"):
        item = {"name": joint.attrib["name"], "type": joint.attrib["type"]}
        for tag, keys in {
            "parent": ("link",),
            "child": ("link",),
            "origin": ("xyz", "rpy"),
            "axis": ("xyz",),
            "limit": ("lower", "upper", "effort", "velocity"),
            "mimic": ("joint", "multiplier", "offset"),
        }.items():
            element = joint.find(tag)
            if element is not None:
                item[tag] = {k: element.attrib[k] for k in keys if k in element.attrib}
        joints.append(item)
    return {
        "coordinate_frame": "URDF robot base (not simulator world)",
        "length_unit": "metre",
        "angle_unit": "radian",
        "joints": joints,
    }
