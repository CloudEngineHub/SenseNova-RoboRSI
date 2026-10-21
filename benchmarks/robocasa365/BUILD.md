# Building the RoboCasa365 image

The image is the Target50 environment image plus two layers: one removes the
Agent-side packages and the earlier one-process application, the other adds the
RoboRSI service sources. `Dockerfile` states both; `layers.py` and the `crane`
commands below produce the same layers on a host without a container daemon,
which is how the published image was built.

## Base image

`ghcr.io/opensensenova/sensenova-roborsi-robocasa365@sha256:8494fef17ee5979a072967632a2cb6ca885a165e87b01fb88d40c9f88b5b82e1`
(tag `v1.0.0-cu126`, Docker v2 manifest, 21 layers, 25.94 GB compressed).

| Path | Content |
| --- | --- |
| base | `ubuntu:22.04` `@sha256:08ea48a03a3e78ebc7cd526e6a275053223aadd88bfc09cc49b06d5281525fde` with OSMesa, EGL and GL runtime libraries |
| `/opt/rpent-py310` | Python 3.10 environment: torch 2.7.0+cu126, mujoco 3.3.1, robocasa `2692d8fc`, robosuite `97cfbde4`, rlinf-rldx 1.0.1.post10 and the versions pinned by `robots/robocasa/eval/target50-constraints.txt` |
| `/opt/robocasa-assets` | RoboCasa kitchen assets for robocasa `2692d8fc` |
| `/opt/rldx/RLDX-1-FT-RC365` | `RLWRLD/RLDX-1-FT-RC365@587e9ecdcc5e7184fcc17f58713908edff5af041` |
| `/opt/hf-cache` | configuration files of `RLWRLD/RLDX-1-VLM@4b9f870d1287e0d38d7eb1445e6d8c60afe66dd7` (no weights) |
| `/opt/heart-robocasa/BUILD` | `pip_freeze.txt`, `dpkg.txt` and `build.json` recorded when the base was assembled |

The base was assembled with `crane` from these components; its complete package
list is `/opt/heart-robocasa/BUILD/pip_freeze.txt` and `dpkg.txt` inside the
image. It needs an NVIDIA driver supporting CUDA 12.6 for RLDX-1; kitchens
render with OSMesa on the CPU.

## Layers added by this recipe

1. Uninstall `agent-packages.txt` (anthropic, claude-agent-sdk, mcp, openai,
   openai-codex, openai-codex-cli-bin, pydantic-ai-harness, pydantic-ai-slim)
   and remove the earlier application under `/opt/heart-robocasa`, keeping its
   `BUILD` records. Nothing that stays requires a removed distribution.
2. Copy the exported `benchmark-runtime/` to `/opt/roborsi`, check it with
   `verify_benchmark_runtime`, and start the Benchmark service by default.

## With Docker

```bash
python -m benchmarks.package --benchmark robocasa365 --output /path/to/context
docker build -t robocasa365:local /path/to/context
```

## Without a container daemon

```bash
python -m benchmarks.package --benchmark robocasa365 --output CONTEXT
crane export "$BASE" - | tar -x -C ROOTFS          # the base filesystem
python3 benchmarks/robocasa365/layers.py --rootfs ROOTFS --context CONTEXT --output LAYERS
crane append -b "$BASE" -f LAYERS/10-remove.tar -f LAYERS/20-roborsi.tar -t "$REPO:build"
crane mutate "$REPO:build" --entrypoint= \
  --env PATH=/opt/rpent-py310/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  --env PYTHONPATH=/opt/roborsi --env PYTHONDONTWRITEBYTECODE=1 \
  --workdir /opt/roborsi \
  --cmd python,-m,roborsi.evaluation.service_host,--kind,benchmark,--factory,robots.robocasa.benchmark_service:make_robocasa365_benchmark,--host,0.0.0.0,--port,8000 \
  -t "$REPO:v1.1.2-cu126"
```

`layers.py` writes OCI whiteouts for every file the uninstalled distributions'
`RECORD` lists and for the removed application paths, and a source layer with
fixed ownership and timestamps. Apply both to `ROOTFS` to obtain the image
filesystem for an isolated check:

```bash
while read -r p; do rm -rf "ROOTFS$p"; done < LAYERS/removed.txt
tar -xf LAYERS/20-roborsi.tar -C ROOTFS
```

## Published build

See [VALIDATION.md](VALIDATION.md) for the context digest (`build.json`), the
layer digests, the final image digest and the checks run on it.
