# Copyright 2026 The Bench2Dex Evaluation Contributors.
# Licensed under the Apache License, Version 2.0.

"""Find the URDF root used by native camera calibration."""


def root_link(joints):
    roots = {j["parent"]["link"] for j in joints} - {j["child"]["link"] for j in joints}
    if len(roots) != 1:
        raise ValueError("Expected one connected robot root")
    return roots.pop()
