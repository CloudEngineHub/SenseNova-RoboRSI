# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Download and seal the official testing assets at the evaluation revision."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath

from roborsi.benchmarks.registry import directory_sha256
from robots.bench2dex.contracts import ASSET_REVISION, file_sha256
from robots.bench2dex.reference.core import write_json


def seal(source: Path, output: Path, *, download: bool = False) -> dict:
    """Verify official Git/LFS object IDs and copy only the selected assets."""
    from huggingface_hub import HfApi, snapshot_download

    selection = json.loads(
        Path(__file__).with_name("assets-selection.json").read_text()
    )
    if (
        selection["repo_id"] != "Bench2Dex/Assets"
        or selection["revision"] != ASSET_REVISION
    ):
        raise ValueError("asset selection does not match the evaluation")
    if output.exists() or output.is_symlink():
        raise ValueError("choose a new sealed output directory")
    inventory = []
    for item in HfApi().list_repo_tree(
        selection["repo_id"],
        repo_type="dataset",
        revision=ASSET_REVISION,
        recursive=True,
    ):
        if not hasattr(item, "size") or not any(
            fnmatch.fnmatchcase(item.path, p) for p in selection["include"]
        ):
            continue
        path = PurePosixPath(item.path)
        if path.is_absolute() or ".." in path.parts or "\\" in item.path:
            raise ValueError("unsafe official asset path")
        lfs = getattr(item, "lfs", None)
        expected = (
            lfs.get("sha256") if isinstance(lfs, dict) else getattr(lfs, "sha256", None)
        )
        inventory.append(
            {
                "path": item.path,
                "bytes": item.size,
                "lfs_sha256": expected,
                "git_blob": item.blob_id,
            }
        )
    if not inventory:
        raise ValueError("official metadata returned an empty selection")
    if download:
        snapshot_download(
            repo_id=selection["repo_id"],
            repo_type="dataset",
            revision=ASSET_REVISION,
            allow_patterns=selection["include"],
            local_dir=source,
            max_workers=2,
        )
    # Validate before copying. A downloaded .cache and local logs never enter the seal.
    for row in inventory:
        path = source / row["path"]
        if (
            not path.is_file()
            or path.is_symlink()
            or not path.resolve().is_relative_to(source.resolve())
            or path.stat().st_size != row["bytes"]
        ):
            raise ValueError(f"missing or invalid asset: {row['path']}")
        digest = file_sha256(path)
        if row["lfs_sha256"]:
            valid = digest == row["lfs_sha256"]
        else:
            blob = hashlib.sha1(b"blob " + str(row["bytes"]).encode() + b"\0")
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    blob.update(chunk)
            valid = blob.hexdigest() == row["git_blob"]
        if not valid:
            raise ValueError(f"official asset checksum mismatch: {row['path']}")
        row["sha256"] = digest
    output.mkdir(parents=True)
    try:
        for row in inventory:
            destination = output / row["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / row["path"], destination)
            if file_sha256(destination) != row["sha256"]:
                raise ValueError("asset changed while copying")
        record = {
            "schema_version": 1,
            "repo_id": selection["repo_id"],
            "revision": ASSET_REVISION,
            "files": sorted(inventory, key=lambda r: r["path"]),
            "sha256": directory_sha256(output),
        }
        write_json(output.with_name(output.name + ".inventory.json"), record)
        return record
    except BaseException:
        shutil.rmtree(output)
        raise


def main() -> None:
    """Use --source for an existing download or --download to fetch it first."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    record = seal(args.source, args.output, download=args.download)
    print(
        json.dumps(
            {
                "files": len(record["files"]),
                "sha256": record["sha256"],
                "revision": record["revision"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
