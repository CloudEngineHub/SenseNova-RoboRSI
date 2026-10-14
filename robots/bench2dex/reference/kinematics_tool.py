# Copyright 2026 The Bench2Dex Evaluation Contributors.
# Licensing of this copied reference code is pending; see LICENSE_NOTICE.md.

"""Policy-safe URDF kinematics. No simulator imports, task logic or execution."""


def root_link(joints):
    roots = {j["parent"]["link"] for j in joints} - {j["child"]["link"] for j in joints}
    if len(roots) != 1:
        raise ValueError("Expected one connected robot root")
    return roots.pop()
