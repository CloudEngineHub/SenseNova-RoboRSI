# BEHAVIOR-1K

[简体中文](README.zh-CN.md) · [All guides](../../docs/README.md)

This integration exposes BEHAVIOR-1K through the shared Benchmark service and
Runner. It provides native task inspection, an isolated simulator worker, the
official 21D action interface, RGB-D observations and native scoring.

## Tasks, actions and scores

The native source is BEHAVIOR-1K v3.9.2, commit
`b1979916ec1549b10a4e65e630bc6504a9af1b00`. The
[task selection](official_tasks.json) contains 100 tasks. Catalog preparation
resets each selected task and reads its actual instruction and step limit.
The service exposes the tasks in that catalog using `public_test` instance
301 (public-test index 0), seed 0.

Each action is `{"action": [...]}` with exactly 21 finite values, in this order:

| Values | Control |
| --- | --- |
| 3 | Base velocity |
| 4 | Torso joint targets |
| 6 | Left end-effector position and rotation vector in the base frame |
| 1 | Left gripper |
| 6 | Right end-effector position and rotation vector in the base frame |
| 1 | Right gripper |

Actions must satisfy the native bounds; the adapter rejects out-of-range
commands without clipping or normalization. Observations contain full-resolution
head and wrist RGB/depth PNGs, public proprioception and action bounds. Depth
images encode inverse log intensity over 0.01–10 m with a 3.5 m shift; pixel
values are display intensities, not metric distances.

Success comes from native `task.success`; score comes from the official
aggregated `q_score.final`. An explicit stop scores the current state without
advancing physics. Native step or metric failures are reported as infrastructure
errors. Each episode owns an isolated simulator process and bounded cleanup.

## Environment and image

Use Linux x86_64, Python 3.11, Docker, a supported NVIDIA driver and the NVIDIA
Container Toolkit. Simulation requires an RTX-class GPU; 24 GB VRAM is
recommended. Provide 32 GB RAM and at least 80 GB free build disk, plus storage
for licensed assets and their snapshot.

The [build lock](build-lock.json) pins the upstream `linux/amd64` image, about
14.7 GB compressed. The Dockerfile installs the pinned native source and hashed
service requirements. The image records its native dependency freeze and build
evidence.

Install the Agent and evaluator from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[runtime]'
```

Set `BEHAVIOR_DELIVERY` to an absolute directory outside the checkout, without
symlink components. Set `BEHAVIOR_IMAGE_TAG` to a new tag in a container registry
you can publish to. Use a fresh build directory:

```bash
mkdir -p "$BEHAVIOR_DELIVERY"
BEHAVIOR_BUILD="$BEHAVIOR_DELIVERY/build"
python -m benchmarks.package --benchmark behavior_1k --output "$BEHAVIOR_BUILD"
python "$BEHAVIOR_BUILD/build_image.py" --tag "$BEHAVIOR_IMAGE_TAG"
```

After authenticating to your registry, publish this build and resolve its digest:

```bash
docker push "$BEHAVIOR_IMAGE_TAG"
docker pull "$BEHAVIOR_IMAGE_TAG"
BEHAVIOR_IMAGE=$(docker image inspect "$BEHAVIOR_IMAGE_TAG" --format '{{index .RepoDigests 0}}')
```

Use this build's actual `repository@sha256:digest` throughout the following
commands. The upstream base digest identifies the base environment only.
Retain the exported `source.json`, `build.json`, `build-lock.json` and final
image digest with your deployment records.

## Assets, catalog and registry

Obtain the assets and key through the upstream licensed installation process.
Set `BEHAVIOR_DATA` to that private asset directory, containing:

```text
behavior-1k-assets/
omnigibson-robot-assets/
2026-challenge-task-instances/
omnigibson.key
```

Keep the key in the private asset mount. Asset preparation copies the complete
directory into a snapshot and hashes it; reserve enough space for both copies.
Run from the repository root:

```bash
python -m benchmarks.behavior_1k.prepare assets \
  --source "$BEHAVIOR_DATA" \
  --output-dir "$BEHAVIOR_DELIVERY/registry/behavior_1k/assets"
BEHAVIOR_SNAPSHOT=$(python -c \
  'import json, sys; print(json.load(open(sys.argv[1]))["path"])' \
  "$BEHAVIOR_DELIVERY/registry/behavior_1k/assets/asset.json")
```

Generate a catalog inside your image. This command starts the native simulator
and resets `sorting_vegetables`. Repeat `--task` to include more names from the
100-task selection. The catalog and work directories must be new.

```bash
docker run --rm --gpus all \
  --mount type=bind,src="$BEHAVIOR_SNAPSHOT",dst=/roborsi/assets/behavior_1k,readonly \
  --mount type=bind,src="$BEHAVIOR_DELIVERY",dst=/delivery \
  "$BEHAVIOR_IMAGE" python -m benchmarks.behavior_1k.prepare catalog \
  --task sorting_vegetables \
  --output-dir /delivery/registry/behavior_1k/catalog \
  --work-dir /delivery/catalog-work
```

Read the runtime identity from the same image, then create its manifest:

```bash
docker run --rm \
  --mount type=bind,src="$BEHAVIOR_DELIVERY",dst=/delivery \
  "$BEHAVIOR_IMAGE" python -m benchmarks.behavior_1k.prepare runtime-info \
  --output /delivery/runtime-info.json

python -m benchmarks.behavior_1k.prepare manifest \
  --image "$BEHAVIOR_IMAGE" \
  --assets "$BEHAVIOR_SNAPSHOT" \
  --catalog "$BEHAVIOR_DELIVERY/registry/behavior_1k/catalog" \
  --runtime-info "$BEHAVIOR_DELIVERY/runtime-info.json" \
  --output "$BEHAVIOR_DELIVERY/registry/behavior_1k/manifest.json"
```

The resulting layout is:

```text
registry/behavior_1k/
  assets/
    asset.json
    snapshots/<sha256>/
  catalog/catalog.json
  manifest.json
```

Assets and catalog must be inside the manifest directory without parent
traversal or symlinks. The manifest records their relative paths and hashes,
the image digest and inspected tasks. Registry launch mounts the snapshot at
`/roborsi/assets/behavior_1k` and the catalog at
`/roborsi/assets/behavior_1k-catalog`.

## Evaluate with an Agent

Set `OPENAI_API_KEY` in the Agent environment and select a vision model with
tool calling. The shared preset receives the task, 21D action schema and RGB-D
observations:

```bash
bench eval --registry-root "$BEHAVIOR_DELIVERY/registry" \
  --results-root "$BEHAVIOR_DELIVERY/results" --run-id behavior-1 \
  --benchmark behavior_1k --task behavior_1k:sorting_vegetables --seed 0 \
  --agent-config configs/agents/embodied/default.yaml \
  --agent-set 'runtime.llm.model="YOUR_VISION_TOOL_MODEL"' \
  --agent-set 'agent.action_timeout_s=900' \
  --timeout-s 900 --case-timeout-s 7200
```

The native task limit comes from the catalog; Agent turn limits and Runner
timeouts are separate controls. See [Agent configuration](../../docs/agents.md)
and [evaluation](../../docs/evaluation.md) for budgets, artifacts and resume.
Offline checks are described in the [test guide](../../tests/README.md).

The native simulator, robot assets and datasets retain their upstream licenses
and access terms.
