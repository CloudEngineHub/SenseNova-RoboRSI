# Build the RoboCasa365 benchmark image

[简体中文](BUILD.zh-CN.md) · [Benchmark guide](README.md)

The Dockerfile extends an existing Target50 environment. Its default base is:

```text
ghcr.io/opensensenova/sensenova-roborsi-robocasa365@sha256:8494fef17ee5979a072967632a2cb6ca885a165e87b01fb88d40c9f88b5b82e1
```

The source delivery identifies this GHCR package as private. Obtain authorized
pull access before building, or supply an equivalent base through the existing
`ROBOCASA365_BASE_IMAGE` argument. A digest identifies content; it does not grant
registry access. This repository does not contain a complete, independently
reproducible recipe for assembling that base from public inputs.

## Native base contract

The inherited base is Linux amd64, approximately 25.94 GB compressed, and provides:

| Path | Required content |
| --- | --- |
| `/opt/rpent-py310` | Python 3.10.21, Torch 2.7.0+cu126, MuJoCo 3.3.1, the pinned RoboCasa/robosuite/RLDX packages |
| `/opt/robocasa-assets` | Kitchen assets for RoboCasa commit `2692d8fc5fd86708a1b2028dcbce892ec418a9e7` |
| `/opt/rldx/RLDX-1-FT-RC365` | RLDX-1 checkpoint revision `587e9ecdcc5e7184fcc17f58713908edff5af041` |
| `/opt/hf-cache` | RLDX VLM configuration revision `4b9f870d1287e0d38d7eb1445e6d8c60afe66dd7` |
| `/opt/heart-robocasa/BUILD` | Original base environment records |

The base supplies OSMesa/EGL/GL system libraries and runtime configuration,
including `RLDX_CHECKPOINT` and the simulator asset locations. A replacement base
must provide compatible paths, packages, assets, weights and environment settings.
The Dockerfile also expects `/opt/heart-robocasa` to exist during cleanup.

[`requirements.txt`](requirements.txt) preserves the original image's resolved
Python environment. It is an environment record, not a minimal dependency lock
or a standalone base-image build recipe. The Dockerfile inherits these packages;
it does not install that file. Native source revisions are also recorded in
[`target50.json`](../../robots/robocasa/eval/target50.json).

## Export and build

From a source checkout with the framework installed, export to a new directory:

```bash
python -m benchmarks.package --benchmark robocasa365 \
  --output work/robocasa365/build
docker login ghcr.io
docker build --platform linux/amd64 -t robocasa365:local work/robocasa365/build
export ROBOCASA365_IMAGE=robocasa365:local
```

`docker login` uses your authorized registry credentials. Keep credentials out of
build arguments and source files. If using your own compatible base:

```bash
docker build --platform linux/amd64 \
  --build-arg ROBOCASA365_BASE_IMAGE="$YOUR_COMPATIBLE_BASE_DIGEST" \
  -t robocasa365:local work/robocasa365/build
```

`build-inputs.json` declares `agent-packages.txt` in addition to the standard
Docker files. The image uninstalls the inherited Agent distributions, removes
the earlier application while retaining its `BUILD` records, and copies only the
declared benchmark runtime. The native RLDX code and checkpoint remain because
the manipulation tools call them. `verify_benchmark_runtime` checks the exported
source boundary and rejects inherited Agent packages.

Retain exported `source.json` and `build.json` with your build evidence. The base
digest and any earlier delivery digest are not the digest of this rebuilt image.
After pushing your own image tag, obtain its repository digest with
`docker image inspect YOUR_IMAGE_TAG --format '{{json .RepoDigests}}'` and use
that exact value for Registry registration. See [README.md](README.md).

## Verification

Exporting the context and importing its service sources can be checked without
Docker, model credentials or simulator dependencies. Offline coverage includes:

```bash
pytest tests/unit_tests/roborsi/benchmarks/test_robocasa365_registration.py \
  tests/unit_tests/robots/robocasa/test_runtime_bundle.py \
  tests/unit_tests/robots/robocasa/test_roborsi_adapter.py \
  tests/unit_tests/robots/robocasa/test_score.py -v
```

A real image build still requires the base and container tooling. Native
acceptance additionally requires the licensed assets, checkpoint and compatible
GPU host. Source exports and offline fake-toolkit tests do not establish native
task success. No validation of an earlier image is claimed for this rebuild.
