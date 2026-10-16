# LIBERO CPU benchmark

This Linux x86-64 image serves the standard LIBERO benchmark through HTTP.
It pins Python 3.11, MuJoCo 3.3.0, robosuite 1.5.2 and the RLinf environment
wrapper. OSMesa provides CPU rendering. Agents run separately; results, camera
files and logs cross HTTP without mounting the Runner output directory.

## Build and prepare assets

Install the framework first, then use an absolute workspace outside the checkout.
Docker and network access to the pinned build sources are required.

```bash
export ROBORSI_WORKSPACE=/absolute/path/to/libero-work
python -m benchmarks.libero.download_assets \
  --output-dir "$ROBORSI_WORKSPACE/registry/libero"
python -m benchmarks.package --benchmark libero \
  --output "$ROBORSI_WORKSPACE/build"
docker build -t YOUR_REGISTRY/roborsi-libero:BUILD "$ROBORSI_WORKSPACE/build"
docker push YOUR_REGISTRY/roborsi-libero:BUILD
export ROBORSI_IMAGE=$(docker image inspect YOUR_REGISTRY/roborsi-libero:BUILD \
  --format '{{index .RepoDigests 0}}')
```

Replace `YOUR_REGISTRY` and `BUILD` with your registry and image tag. The asset
preparer downloads the pinned
[LIBERO-assets snapshot](https://huggingface.co/datasets/RLinf/LIBERO-assets/tree/3ba78404b48e8c70fa4ac9782d5aac8e5b46d55f)
and records a directory checksum. Source revisions and dependency hashes remain
in the Dockerfile and requirements lock. The image uses environment modules
without installing the RLinf training stack.

## Export a manifest

Generate task metadata inside the built image so its recorded versions match
the runtime. The image reference must include a repository digest.

```bash
docker run --rm --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$ROBORSI_WORKSPACE/registry/libero,dst=/config" \
  "$ROBORSI_IMAGE" python -m benchmarks.libero.manifest \
  --image "$ROBORSI_IMAGE" --asset /config/asset.json \
  --output /config/manifest.json --suite libero_spatial --seed 0
```

Repeat `--seed` for more initial states. `--max-steps` defaults to 600; use 3 for
short integration checks. Changing this limit changes the evaluation condition.
The runtime performs 15 settling steps before Agent actions.

## Evaluate

```bash
bench eval --registry-root "$ROBORSI_WORKSPACE/registry" \
  --results-root "$ROBORSI_WORKSPACE/results" --run-id hold-1 \
  --agent-factory examples.roborsi.hold_agent:make_agent \
  --agent-version hold-example-v1 --benchmark libero --task libero:0 --seed 0 \
  --timeout-s 180 --case-timeout-s 900
```

The example keeps the gripper open and is expected to fail the manipulation
objective. See [Agents](../../docs/agents.md) for model presets and
[Evaluation](../../docs/evaluation.md) for results, status, comparison and resume.

The supported native controller is Panda `OSC_POSE` at 20 Hz. A raw action has
seven finite numbers: base-frame translation x/y/z, axis-angle rotation x/y/z,
and gripper command. Arm components are clipped to `[-1, 1]` and scaled to
±0.05 metres or ±0.5 radians. Negative gripper input opens, positive closes,
and zero preserves the command. Invalid payloads fail before native stepping.

## Serve HTTP independently

Set `LIBERO_SNAPSHOT` to the downloaded snapshot directory named by `asset.json`.
The service needs only that read-only asset mount:

```bash
docker run --rm --read-only --tmpfs /tmp:rw,nosuid,nodev,size=1g \
  --user "$(id -u):$(id -g)" -p 127.0.0.1:8000:8000 \
  --mount "type=bind,src=$LIBERO_SNAPSHOT,dst=/roborsi/assets/libero,readonly" \
  "$ROBORSI_IMAGE"
```

The default catalog is `libero_spatial`, seed 0, 600 steps. Environment variables
`ROBORSI_LIBERO_SUITE`, `ROBORSI_LIBERO_SEEDS` (JSON array) and
`ROBORSI_LIBERO_MAX_STEPS` control it. For authenticated deployment, pass an
existing `ROBORSI_BENCHMARK_TOKEN` with Docker `--env ROBORSI_BENCHMARK_TOKEN`.
Remote Agents use `--benchmark-url libero=...`; see the evaluation guide.

[Native tests](../../tests/README.md#libero-cpu-evaluation-check) compare fixed
actions with direct LIBERO calls. No native execution or model score is implied
by offline test success. Rebuild the image and regenerate its manifest together
after changing the adapter or action contract.
