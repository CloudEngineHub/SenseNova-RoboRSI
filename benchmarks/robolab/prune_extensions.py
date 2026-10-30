# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Remove optional LLM extensions while retaining shared, deduplicated files."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

OPTIONAL = (
    "exts/isaacsim.replicator.experimental.mobility_gen",
    "exts/isaacsim.replicator.mobility_gen.examples",
    "exts/isaacsim.replicator.mobility_gen.ui",
    "extsDeprecated/isaacsim.replicator.mobility_gen",
    "extscache/isaacsim.replicator.agent.core-*",
    "extscache/isaacsim.replicator.agent.schema-*",
    "extscache/isaacsim.replicator.agent.ui-*",
    "extscache/isaacsim.replicator.caption.core-*",
    "extscache/omni.ai.behavior_tree_gen.bridge-*",
    "extscache/omni.ai.behavior_tree_gen.core-*",
    "extscache/omni.ai.langchain.agent.chat_iro-*",
    "extscache/omni.ai.langchain.core-*",
    "extscache/omni.ai.langchain.widget.core-*",
    "extscache/omni.metropolis.agent_registry-*",
    "extscache/omni.metropolis.pipeline-*",
    "extscache/omni.metropolis.schema-*",
    "extscache/omni.metropolis.utils-*",
)


def prune(root: Path) -> dict:
    """Preserve inbound shared-file links before removing complete extensions."""
    root = root.resolve()
    removed = [path for pattern in OPTIONAL for path in root.glob(pattern)]
    if not removed or any(path.is_symlink() for path in removed):
        raise ValueError("expected regular optional extension directories")

    def removed_path(path: Path) -> bool:
        return any(path.is_relative_to(directory) for directory in removed)

    shared = []
    for path in root.rglob("*"):
        if not path.is_symlink() or removed_path(path):
            continue
        target = path.resolve()
        if not removed_path(target):
            continue
        # NVIDIA deduplicates ordinary packages (including pip) into optional
        # extensions. Preserve the referenced bytes before removing their owner.
        temporary = path.with_name(path.name + ".robolab-materialized")
        if temporary.exists() or temporary.is_symlink():
            raise ValueError("unexpected materialization target")
        if target.is_file():
            shutil.copy2(target, temporary)
        elif target.is_dir():
            shutil.copytree(target, temporary, symlinks=False)
        else:
            raise ValueError(f"broken shared extension link: {path}")
        temporary.replace(path)
        shared.append(path.relative_to(root).as_posix())
    for path in removed:
        shutil.rmtree(path)
    return {
        "removed": [p.relative_to(root).as_posix() for p in removed],
        "materialized_shared_files": shared,
    }


def main() -> None:
    """Operate only on the Docker build's copy of the pinned native runtime."""
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.report.write_text(json.dumps(prune(args.root), indent=2) + "\n")


if __name__ == "__main__":
    main()
