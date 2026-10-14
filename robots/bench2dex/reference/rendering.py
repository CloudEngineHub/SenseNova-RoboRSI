# Copyright 2026 The Bench2Dex Evaluation Contributors.
# Licensing of this copied reference code is pending; see LICENSE_NOTICE.md.

"""Trusted rendering provenance and USD dependency gate; never policy-mounted."""

from pathlib import Path

from .core import write_json

SETTING_KEYS = (
    "/isaaclab/rendering/rendering_mode",
    "/rtx/rendermode",
    "/rtx/translucency/enabled",
    "/rtx/reflections/enabled",
    "/rtx/indirectDiffuse/enabled",
    "/rtx/ambientOcclusion/enabled",
    "/rtx/directLighting/sampledLighting/enabled",
    "/rtx/directLighting/sampledLighting/samplesPerPixel",
    "/rtx/post/dlss/execMode",
    "/rtx/sceneDb/ambientLightIntensity",
    "/rtx/shadows/enabled",
    "/omni/replicator/asyncRendering",
    "/app/renderer/waitIdle",
    "/app/hydraEngine/waitIdle",
)


def dependency_report(root_layer, compute_dependencies, *, search_paths=()):
    """Use USD's resolver recursively (including binary layers and textures).

    An existing top-level USD is insufficient: payloads can reference missing
    furniture or textures and still produce apparently valid RGB images.
    No missing-reference exceptions or fallback assets are allowed here.
    """
    if search_paths:
        from pxr import Ar

        # Match the renderer's installed MDL module search paths. This is a
        # scoped resolver context for the audit, not a renderer modification.
        with Ar.ResolverContextBinder(Ar.DefaultResolverContext(list(search_paths))):
            layers, assets, unresolved = compute_dependencies(root_layer)
    else:
        layers, assets, unresolved = compute_dependencies(root_layer)
    return {
        "layers": sorted(str(layer.identifier) for layer in layers),
        "assets": sorted(str(asset) for asset in assets),
        "unresolved": sorted({str(asset) for asset in unresolved}),
    }


def validate_rendering(
    stage, settings, output, *, compute_dependencies=None, search_paths=()
):
    if compute_dependencies is None:
        from pxr import UsdUtils

        compute_dependencies = UsdUtils.ComputeAllDependencies
    dependencies = dependency_report(
        stage.GetRootLayer().identifier, compute_dependencies, search_paths=search_paths
    )
    report = {
        "schema_version": 1,
        "profile": "upstream_default",
        "settings": {key: settings.get(key) for key in SETTING_KEYS},
        "dependencies": dependencies,
        "mdl_search_paths": list(search_paths),
        "status": "failed" if dependencies["unresolved"] else "passed",
        "scope": "USD asset dependency resolution; not a guarantee of photorealism or pixel parity",
        "policy_rgb": "640x480 uint8 lossless PNG, original baseline camera subset",
    }
    write_json(Path(output), report)
    if dependencies["unresolved"]:
        raise RuntimeError(
            f"Rendering preflight: {len(dependencies['unresolved'])} unresolved USD assets. "
            f"Repair testing assets before evaluation; see {output}"
        )
    return report
