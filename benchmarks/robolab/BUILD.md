# Rebuilding the native RoboLab image

The image contains the pinned DROID simulator, the declared Benchmark service
closure and its required Python dependencies. It contains no RoboRSI Agent,
planner, model credentials, Codex binary, model SDK installation or asset tree.
The historical module inside it is only the original native runner/client bridge;
the historical policy runs in its own host environment.

## Fixed inputs

| Input | Identity |
| --- | --- |
| Platform | `linux/amd64`, Ubuntu 24.04, bundled Python 3.12.13 |
| NVIDIA base | `nvcr.io/nvidia/isaac-sim@sha256:68735a60b6c15c85e0dd0098570c6d2cc79e928f2d068ce2790aa43284ac165d` |
| Native simulator build | `6.0.0-rc.59+release.41464.5f2772bc.gl` |
| Isaac Lab | `37ddf626871758333d6ed89cf64ad702aef127d0` (`v2.3.2`; Python distribution `isaaclab==0.54.2`) |
| RoboLab | `92ccc0ee1984a272d4748c92ed73144fa806a6f4` |
| Python closure | `native-image.constraints.txt` |

[build-lock.json](build-lock.json) records source archive URLs and SHA-256 values.
`fetch_native.py` downloads and verifies those archives. The Dockerfile applies:

1. `isaaclab-2.3.2-isaacsim6.patch`: the 24-file compatibility patch used by the
   source environment; original and patched file hashes are retained.
2. `isaaclab-native-dependencies.patch`: limits packaging dependencies to the
   tested rigid-body DROID route and reconciles its NumPy/Pillow constraints.
3. `robolab-harness-transport.patch`: keeps the original protocol-2 action client,
   removes the unnecessary OpenPI package dependency, supports the base image's
   WebSocket version, and skips already completed historical run IDs.

The build verifies all 249 pinned native source files used by the route. The
official standalone base supplies Torch `2.11.0+cu128`. `python-runtime.sh`
uses that prebundle and the base image's GLib; it does not modify host libraries.
The base's optional LLM extensions are removed after preserving any shared
packaging files referenced by its runtime.

The host needs Docker with Buildx, NVIDIA Container Toolkit, a compatible driver
and an RTX GPU. The base declares minimum driver `570.169`; use the selected
NVIDIA image's licensing and driver requirements. Accept its license before use.
Native runs set `OMNI_KIT_ACCEPT_EULA=YES`. Reserve at least 50 GB for the base,
build layers and final image, plus external assets/results. Large repeated video
runs require additional output space.

## Export, build and publish

The shared exporter registers the RoboLab runtime sources in
`roborsi/benchmarks/runtime_source.py`.

The published `v0.1.2-isaac60` image records the original runtime source snapshot
`4cbb63788eabf3e0e5e8122f9cf5248c047c3194`. This historical source identity is
not a revision of this public repository. The public runtime exporter has a
different set of benchmark registrations, which changes the source digest.
A build from this checkout is a new image and must use a new version tag;
it is not claimed to reproduce the published image byte for byte.

Export the registered sources and build:

```bash
cd "$REPO"
"$WORK/runner/bin/python" -m benchmarks.package \
  --benchmark "robolab" --output "$WORK/native-context"
"$WORK/runner/bin/python" -m benchmarks.robolab.build \
  --context "$WORK/native-context" --tag "v0.1.3-isaac60" \
  --evidence "$WORK/image-evidence"
```

The context contains `source.json` (runtime files/digest) and `build.json`
(build inputs, modes and digest). Keep both with the image evidence. The first
command needs a fresh destination. The build uses pinned base/source inputs and
the full native constraints; build cache use does not change those inputs.
The small OS build dependencies `patch` and `ca-certificates` come from the base
distribution's configured apt repositories, so their repository state is not
claimed to be a bit-for-bit operating-system rebuild lock.

Authenticate to GHCR locally with an account allowed to write the target package.
Use `docker login ghcr.io --password-stdin` with a secret manager or a local token
pipe; never place credentials in the context or evidence directory. Then build
and publish with a fresh evidence directory and an unused semantic-version tag:

```bash
"$WORK/runner/bin/python" -m benchmarks.robolab.build \
  --context "$WORK/native-context" --tag "v0.1.3-isaac60" \
  --evidence "$WORK/published-image-evidence" --publish
```

The script refuses an existing remote tag and refuses to interpret authentication
failure as tag absence. It pushes, verifies the registry manifest digest, pulls
by digest and checks that the pulled image ID matches the build. `image.json.reference` is populated only
for a completed publication. Choose a new tag when any source or build input
changes. Do not use `latest` or replace an existing version tag.

For a separate daemon/configuration, append
`--docker-host "unix:///path/to/docker.sock" --docker-config "/private/docker-config"`.
The optional `--network host` changes only build networking. Docker credentials
and CLI plugin directories are not build inputs and must not be uploaded as
validation evidence.

## Runtime

The service runs as an unprivileged UID. It reads assets at
`/roborsi/assets/robolab`, creates per-case files under its private `/tmp`, closes
the simulator before hashing HDF5 artifacts and removes its owned Kit cache.
HTTP observations/results use the framework's artifact transfer; the Agent needs
no shared filesystem. Use read-only rootfs, 8 GiB `/tmp`, 2 GiB shared memory and
one GPU per service. Container stdout is a runtime log, not an Agent trace.

Follow the [README](README.md) for explicit HTTP startup and manifest generation.

The reference host used Python 3.12.14, Torch CUDA 13.0 and a newer Warp package;
the delivered standalone image uses Python 3.12.13, Torch CUDA 12.8 and its bundled
Warp. Matching native simulator/physics libraries alone does not establish
bitwise identity with the historical environment. The supported route is DROID
rigid-body evaluation; other robots, training policies and exploratory tools are
outside this image's scope.

## Upstream licenses

Preserve the pinned native repository's `LICENSE` and `THIRD_PARTY_NOTICES.md`.
Assets are distributed separately through upstream Git LFS. They include mixed
licenses: CC0 backgrounds; CC BY-NC-SA assets; HOT3D CC BY-SA with additional
non-sale terms; YCB MIT; VOMP CC BY; and Kinova BSD terms. Consult the original
per-asset notices before redistributing or using them. The framework's Apache
license does not replace those asset licenses or the NVIDIA runtime license.
