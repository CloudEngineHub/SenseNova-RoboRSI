# Three-LIBERO single-image deployment

This deployment wrapper is for schedulers that accept only one container image
per job. It combines one locked three-LIBERO Agent image with either the LiLo or
PRO Benchmark image. Long++ and Ultra-Long use the LiLo build; PRO uses the PRO
build. Each evaluation job therefore starts exactly one image.

The image contains the native Benchmark, all three Agent bundles, sealed ICL
packages, tokenizer and Python dependencies. It does not contain model weights,
an API endpoint or credentials. The model API key remains a read-only runtime
secret and results use a writable runtime mount.

## Published images

The `v1.0.0-egl` images were built from RoboRSI commit
`281dc19296fbe2a4c5a7f01b8fc265529a5e0754` and pulled back from GHCR by digest:

```bash
LONGPP_IMAGE='ghcr.io/opensensenova/sensenova-roborsi-libero-long-plus-plus@sha256:4463b6a247617a51653e1b170cc1cbcbae1a2c773a06f21afdf8626aea5a11c9'
ULTRA_IMAGE='ghcr.io/opensensenova/sensenova-roborsi-libero-ultra-long@sha256:4463b6a247617a51653e1b170cc1cbcbae1a2c773a06f21afdf8626aea5a11c9'
PRO_IMAGE='ghcr.io/opensensenova/sensenova-roborsi-libero-pro@sha256:fd84be8ca67100624dac4a3ddf0de06e74e46c5d1d1b7c8088e6e0713fe70e29'
```

Long++ and Ultra-Long have separate Benchmark packages as required by the
registry convention, but intentionally share identical LiLo-native image
content. The `egl` suffix records the headless NVIDIA EGL rendering boundary;
the images do not ship a CUDA toolkit.

This is a deployment composition, not a replacement for the independently
attested Benchmark and Agent recipes. Build it from the repository root because
it overlays the reviewed RoboRSI source and runners:

```bash
docker build -f benchmarks/libero_three_combined/Dockerfile \
  --build-arg AGENT_IMAGE=repository/agent@sha256:DIGEST \
  --build-arg BENCHMARK_IMAGE=repository/libero-lilo@sha256:DIGEST \
  --build-arg ROBORSI_REVISION="$(git rev-parse HEAD)" \
  -t roborsi-libero-lilo-combined:local .
```

Use the PRO Benchmark digest to build the PRO image. Run one case with:

```bash
docker run --rm --gpus all \
  -v /path/to/model_api.key:/run/secrets/model_api.key:ro \
  -v /path/to/results:/results \
  "$LONGPP_IMAGE" \
  --benchmark libero_long_plus_plus --task t00-i01 \
  --run-id longpp-smoke --results-root /results/longpp-smoke \
  --api-key-file /run/secrets/model_api.key \
  --base-url https://your-responses-endpoint.example/v1
```

For the fixed 12/9/80 subsets, use `--entrypoint python` and pass
`-B /opt/roborsi/benchmarks/libero_three_combined/run_combined_subset.py` immediately after
the image reference. The runner defaults to 16 concurrent cases and one shared
GPU. It preserves every attempt and reuses a result only after matching the
image/code, Agent, ICL, model endpoint and timeout fingerprint, the previous
zero process exit, task/seed identity, and the native score file digest. It
exits nonzero while any case lacks a verified native terminal result.

# LIBERO-PRO, Long++ and Ultra-Long

This integration keeps simulator state and native scoring in standalone RoboRSI
Benchmark services. The Agent receives only declared observations and submits
either 7-DoF Panda `OSC_POSE` actions or one of the declared feedback primitives
(`move_to`, `move_pose`, wrist rotation, gripper control). Primitives compile to
physical 7-DoF actions inside the Benchmark and every physical step counts
toward the same budget. A single Agent dialogue persists for the whole episode,
including an optional failure-only continuation.

For a clean-host, image-only procedure, see the
[reproduction guide](README.md).

## Evaluation contracts

| Benchmark | Full set | Migration subset | Official 1× | Primary score |
| --- | ---: | ---: | ---: | --- |
| LIBERO-PRO Task/Swap | 8 suites × 10 tasks × 10 states = 800 | 80 tasks, fixed state 3 | 10,000 physical steps | final-goal success |
| LIBERO-Long++ | 12 configurations × 10 bare-reset trials = 120 | 12 configurations, fixed state 1 | 200 × ordered skills | ordered-prefix fraction; all skills for success |
| LIBERO-Ultra-Long | 9 configurations × 10 bare-reset trials = 90 | 9 configurations, fixed state 1 | 200 × ordered skills | ordered-prefix fraction; all skills for success |

`plus9_on_failure` defaults to false. When enabled, only a case that failed at
the official 1× boundary may continue, in the same environment and Agent
dialogue, up to 10× total physical steps. `result.json` and aggregate scores
always use the immutable 1× snapshot. `native/score.json` additionally records
cumulative recovery and the actual physical/decision step counts.

Long++ and Ultra-Long repeat labels are not random seeds. The official profile
performs the released bare random reset ten times; the deterministic migration
profile explicitly records fixed state 1. Their scorer advances only the
uninterrupted released skill order and never substitutes LIBERO final-goal
success for ordered success.

Both ordered benchmarks declare the historical
`lilo-instance-pose-feedback-v1` observation contract. Each observation includes
`instance_pose_feedback`: exact registered instance names, live world positions,
collision-geometry top/bottom heights, exact gripper contacts, held objects and
the current ordered skill/progress. This channel is read-only and never calls or
advances the scorer. It is intentionally part of the named evaluation condition;
do not combine these results with older vision-only runs.

The migration also preserves `libero-robot-state-feedback-v1`. Every ordered
observation names the `robot0_eef_pos`, xyzw quaternion, and
`robot0_gripper_qpos` values returned by the legacy v13 direct tools while
retaining the compact eight-dimensional `states` policy input. The
`roborsi_action` schema describes each legacy direct-control primitive explicitly;
in particular, `rotate_wrist` rotates in place and is not interchangeable with
`move_pose.target_yaw`. This compatibility layer does not change tasks, scoring,
initialization, or physical-step budgets.

The Long++ and Ultra-Long subset reported with the full study uses the v13
no-tool, token-accurate condition. PRO uses the persistent-memory ICL from its
full 800-case reference, with the same no-VLA/no-SAM3 tool surface, max
reasoning, context policy, turn budget and retry policy. This repository runs
the fixed-state-3 80-case migration subset, so its sample range remains
different from the full reference even though the Agent condition is aligned.

## Delivery results and evidence

The fixed 12/9/80 image run used the real model and simulator at the official 1x
boundary, without `plus9_on_failure`. The closest historical references and the
single-image results are:

| Benchmark | Historical reference | Image first pass | Image after infrastructure retries | Final difference |
| --- | ---: | ---: | ---: | ---: |
| Long++ | 12/12 | 11/12 | 11/12 | -1 |
| Ultra-Long | 8/9 | 7/9 | 8/9 | 0 |
| PRO | 78/80 | 74/80 | 79/80 | +1 |
| **Total** | **98/101** | **92/101** | **98/101** | **0** |

The final success count matches the closest historical references and each
Benchmark differs by at most one case. First-pass reliability did not match:
the image run had 94/101 legal native terminals, improving to 100/101 after
retrying only infrastructure/Agent errors. One PRO case remained without a
legal terminal. See the [concise validation note](README.md)
for the comparison boundary; this is not a claim of deterministic per-case
reproduction.

## Inputs

An evaluation requires:

1. This repository checkout and the versioned files under
   `configs/libero_three/`.
2. A Benchmark runtime: either a digest-locked image/manifest or the pinned
   source checkouts and Python environment declared by a host runtime config.
3. Read-only LIBERO assets required by that Benchmark runtime.
4. A sealed ICL package tree. Every package contains `manifest.json`, a complete
   SHA-256 inventory and a `payload/`; undeclared files and links are rejected.
5. An OpenAI-compatible endpoint and a key file named only by the private host
   runtime config. Credentials are never stored in a repository config.
6. The locked local tokenizer used by all three context engines.
   Pi0.5, SAM3, PaliGemma and model RPC/MCP endpoints are not dependencies of
   this three-benchmark condition.

The Benchmark image has no model dependency or model credential. The portable
Agent image embeds all three sealed ICL trees, the locked tokenizer, the three
installed Agent bundles and their Python dependencies. Only the model endpoint
and credential are injected at runtime. Agent and Benchmark may be deployed
independently. No VLA/SAM3 model service is started or contacted by this
condition. The generated Benchmark manifests request one GPU for accelerated,
more consistent MuJoCo EGL rendering; local CPU software rendering was also
verified, but is substantially slower.

## Build and lock Benchmark images

Run image builds on a builder, not a cluster login node:

```bash
python -m benchmarks.package --benchmark libero_pro \
  --output ../work/libero_three/build-pro
python -m benchmarks.package --benchmark libero_lilo \
  --output ../work/libero_three/build-lilo
python -m benchmarks.libero_pro.assets \
  --source /path/to/full-evaluation/libero/libero \
  --output-dir ../work/libero_three/libero-pro-assets \
  --build-context ../work/libero_three/build-pro
```

Build and push both contexts, retain their `repository@sha256:digest` values,
then run these commands inside the corresponding image:

```bash
python -m benchmarks.libero_pro.manifest \
  --image REGISTRY/roborsi-libero-pro@sha256:DIGEST \
  --profile migration_subset \
  --output /output/libero_pro/manifest.json

python -m benchmarks.libero_lilo.manifest \
  --image REGISTRY/roborsi-libero-lilo@sha256:DIGEST \
  --benchmark libero_long_plus_plus --profile migration_subset \
  --output /output/libero_long_plus_plus/manifest.json

python -m benchmarks.libero_lilo.manifest \
  --image REGISTRY/roborsi-libero-lilo@sha256:DIGEST \
  --benchmark libero_ultra_long --profile migration_subset \
  --output /output/libero_ultra_long/manifest.json
```

The PRO asset command seals only `bddl_files/` and `init_files/`, requires the
full-evaluation directory SHA-256
`04ae2020acf89315108a68743f99f8fe9c4cb9fc47e67712298a25a7179d616a`,
and stages the verified snapshot as `evaluation-assets/` in the PRO build
context. The Dockerfile verifies the same digest and embeds it at
`/opt/libero-pro-evaluation`. Both images materialize LIBERO's mutable path file
under `/tmp`; PRO therefore cannot silently fall back to incomplete checkout
evaluation files, and the final image has no AFS or runtime asset-mount
dependency.

Omit `--profile migration_subset` for the official full set. Add
`--plus9-on-failure` only for a separately named cumulative diagnostic. Never
compare a +9 run to a 1× run as if their stopping conditions were identical.

## Prepare the frozen ICL inputs

The preparation command reads an existing package family, verifies every file,
copies it to an external work directory, verifies it again, and emits a
diagnostic `package-map.json`. It never modifies the source. The authoritative
task-to-package maps remain in `configs/libero_three/`; canonical relocatable
Agent presets are in `robots/libero/agents/three_benchmark/`.

```bash
python benchmarks/libero_three_combined/prepare_context.py \
  --benchmark libero_long_plus_plus \
  --source /path/to/efficiency_aligned_v12 \
  --destination ../work/libero_three/longpp-icl

python benchmarks/libero_three_combined/prepare_context.py \
  --benchmark libero_ultra_long \
  --source /path/to/efficiency_aligned_v12 \
  --destination ../work/libero_three/ultra-icl

python benchmarks/libero_three_combined/prepare_context.py \
  --benchmark libero_pro \
  --source /path/to/pro_persistent_memory \
  --destination ../work/libero_three/pro-icl
```

In source mode, set `ROBORSI_LIBERO_LONGPP_ICL_ROOT`,
`ROBORSI_LIBERO_ULTRA_ICL_ROOT`, and `ROBORSI_LIBERO_PRO_ICL_ROOT` to the
corresponding external `packages/` directories. The portable Agent image below
sets those variables to its embedded, digest-verified copies. All three
repository presets use max reasoning effort, explicitly disable VLA and SAM3,
and enable Responses prompt caching. PRO disables model retries to match its
full reference; the ordered benchmarks retain three bounded retries for
transient transport/5xx failures.

All three presets use the token-accurate context policy: a 1,050,000-token
window, 128,000-token output reserve, 32,768-token overhead reserve, 0.75
summary trigger, eight complete recent exchanges and two image groups.
`run_source.py` injects the host-configured local tokenizer and its locked
SHA-256. Text history remains complete below the trigger; this is not
equivalent to a fixed recent-turn truncation.

The supported leaf presets are
`robots/libero/agents/three_benchmark/long_plus_plus_v13.yaml`,
`robots/libero/agents/three_benchmark/ultra_long_v13.yaml`, and
`robots/libero/agents/three_benchmark/pro.yaml`. `base.yaml` and `v13.yaml` are
inheritance-only parents.

Export and install a relocatable Agent bundle, for example:

```bash
python -m roborsi.agents.package \
  --config robots/libero/agents/three_benchmark/long_plus_plus_v13.yaml \
  --name libero_long_plus_plus_v13 \
  --output /tmp/libero-longpp-agent-build
python -m build --wheel /tmp/libero-longpp-agent-build
python -m pip install /tmp/libero-longpp-agent-build/dist/*.whl
```

Outside the checkout select `bundle:libero_long_plus_plus_v13`. The wheel
declares `roborsi[runtime]` and `tokenizers==0.22.2`. ICL payloads remain
outside the small wheel: source mode selects an external sealed tree, while the
portable Agent image copies the same verified tree into the image.

## Build the portable Agent image

First stage exactly the three sealed ICL roots and tokenizer. The command
rejects missing/extra package directories, links, count mismatches and any
content whose directory or file SHA-256 differs from `assets.lock.json`:

```bash
python benchmarks/libero_three_combined/prepare_agent_assets.py \
  --longpp-root ../work/libero_three/longpp-icl/packages \
  --ultra-root ../work/libero_three/ultra-icl/packages \
  --pro-root ../work/libero_three/pro-icl/packages \
  --tokenizer ../work/libero_three/tokenizer/tokenizer.json \
  --output dist/agent/libero-three-assets
```

Export all three bundles with the in-image tokenizer identity. Use fresh output
directories and then build all three wheels into `dist/agent/`:

```bash
python -m roborsi.agents.package \
  --config robots/libero/agents/three_benchmark/long_plus_plus_v13.yaml \
  --name libero_long_plus_plus_v13 \
  --set 'runtime.context.tokenizer_file="/opt/roborsi-agent-assets/tokenizer.json"' \
  --set 'runtime.context.tokenizer_sha256="0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3"' \
  --output ../work/libero_three/agent-bundle-longpp
python -m roborsi.agents.package \
  --config robots/libero/agents/three_benchmark/ultra_long_v13.yaml \
  --name libero_ultra_long_v13 \
  --set 'runtime.context.tokenizer_file="/opt/roborsi-agent-assets/tokenizer.json"' \
  --set 'runtime.context.tokenizer_sha256="0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3"' \
  --output ../work/libero_three/agent-bundle-ultra
python -m roborsi.agents.package \
  --config robots/libero/agents/three_benchmark/pro.yaml --name libero_pro \
  --set 'runtime.context.tokenizer_file="/opt/roborsi-agent-assets/tokenizer.json"' \
  --set 'runtime.context.tokenizer_sha256="0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3"' \
  --output ../work/libero_three/agent-bundle-pro
python -m build --wheel --outdir dist/agent ../work/libero_three/agent-bundle-longpp
python -m build --wheel --outdir dist/agent ../work/libero_three/agent-bundle-ultra
python -m build --wheel --outdir dist/agent ../work/libero_three/agent-bundle-pro
```

Build a local RoboRSI wheel and use it only to resolve a complete hash-locked
Python 3.11 dependency file, as described in `agents/python/README.md`. Then:

```bash
docker build --target libero_three -f agents/python/Dockerfile \
  --build-arg AGENT_REQUIREMENTS=dist/agent/requirements.txt \
  --build-arg 'AGENT_WHEEL=dist/agent/roborsi_agent_bundle_libero_*.whl' \
  --build-arg LIBERO_THREE_ASSETS=dist/agent/libero-three-assets \
  -t REGISTRY/roborsi-libero-three-agent:REVISION .
```

The final Docker stage reruns the package maps, counts and content digests and
fails the build if a bundle does not point to the embedded tokenizer. The image
contains no model weights, endpoint or credential.

## Source runtime on an AFS-capable machine

Copy `configs/libero_three/source-runtime.example.json` outside the checkout and
fill in machine-visible paths. A complete private host config names the Agent
Python/wrapper, model endpoint and key file, three ICL roots, the locked context
tokenizer, and the Benchmark Python/source/assets for each family. The public logical asset
contract is `benchmarks/libero_three_combined/assets.lock.json`; absolute AFS paths and
secrets deliberately stay in the private host config.

The PRO `pythonpath` entry must be the root of the pinned LIBERO-PRO checkout,
not its inner `libero/` directory. The required import is
`liberopro.liberopro`. Assets, BDDL files and init states are named
independently by the host config and may come from a separate frozen asset
bundle. A source evaluation does not read demonstrations, so a fresh PRO
checkout may legitimately have no `liberopro/datasets/` directory. Some
published pruned-init files can contain an empty set and some variant BDDL
files may fail to parse, so an evaluation config must point `init_states` and
`bddl_files` at the complete evaluation assets. Preflight loads and parses all
80 selected cases and rejects an empty or missing state or an invalid BDDL
before simulator allocation.

The intended portable AFS layout is:

```text
newrpent/
├── RoboRSI/                  # this Git checkout only
└── work/libero_three/        # private host config, ICL packages, runtimes, logs/results
```

The checkout can therefore be replaced or rebased without touching large or
private runtime state. On another machine that mounts the same AFS tree, only
the checkout and the private host config are needed; every remaining external
path is named by that config. The machine/container still needs an Ubuntu
22.04-compatible `python3.10` and Linux EGL/GL runtime libraries (`libgl1`,
`libegl1`, and `libglib2.0-0`). The LiLo venv entry resolves to
`/usr/bin/python3.10`; mounting AFS alone is not enough on a host without that
interpreter. The configured environments or wrappers carry the Python package
dependencies.

`system_packages` records `python3.10` and those host/container libraries
explicitly. `runtime_assets.context_tokenizer` is required only by Long++ and
Ultra-Long and is verified by SHA-256. No model checkpoint is required.

Audit every referenced source tree, Python, ICL manifest, tokenizer, key file,
selected PRO initial state and BDDL before running:

```bash
python benchmarks/libero_three_combined/check_source_runtime.py \
  --runtime-config ../work/libero_three/source-runtime.afs.json \
  --probe-python
```

Run one case without building an image:

```bash
python benchmarks/libero_three_combined/run_source.py \
  --runtime-config ../work/libero_three/source-runtime.afs.json \
  --benchmark libero_long_plus_plus \
  --task t00-i01 \
  --results-root ../work/libero_three/source-smoke/longpp-t00 \
  --run-id longpp-t00-smoke \
  --port 19081
```

The command fails when the case ends in an Agent or infrastructure error; only
`success` and native `task_failure` are valid evaluation terminals.

Run the complete configured migration subset with the same host config:

```bash
python benchmarks/libero_three_combined/run_source_subset.py \
  --runtime-config ../work/libero_three/source-runtime.afs.json \
  --benchmark libero_long_plus_plus \
  --results-root ../work/libero_three/source-repro/longpp \
  --run-id longpp-v13-icl \
  --max-concurrent 4
```

The repository context map is the authoritative case list (12 Long++, 9
Ultra-Long or 80 PRO). Repeating `--task` selects smoke cases without creating a
second task-list config. The subset runner keeps per-case logs and writes one
`summary.json` with success rate and mean native score; any invalid terminal
makes the command fail. It uses the same standalone Benchmark service and
canonical `roborsi_action` Agent path for all three benchmarks. Preflight and the
runner reject host configs that enable VLA, SAM3 or local model services.

## One-command preflight and evaluation

Validate the fully expanded cases, image locks, package hashes and Agent inputs
before allocating a simulator:

```bash
python benchmarks/libero_three_combined/run.py \
  --benchmark libero_long_plus_plus \
  --registry-root ../work/libero_three/registry \
  --agent-config bundle:libero_long_plus_plus_v13 \
  --agent-image REGISTRY/roborsi-libero-three-agent@sha256:DIGEST \
  --agent-credential-env OPENAI_API_KEY \
  --agent-credential-env OPENAI_BASE_URL \
  --results-root ../work/libero_three/results \
  --run-id longpp-v13-icl \
  --agent-set parameters.enable_vla=false \
  --agent-set parameters.enable_sam3=false \
  --dry-run
```

Remove `--dry-run` to execute locally. The machine needs Docker and access to
the external model endpoint; it does not need AFS or an m-cluster checkout. A
GPU is recommended for full runs, while CPU software rendering is suitable for
slower small validation runs. On SenseCore, `--sco-config` creates Benchmark
workers but is not combined with a local Docker Agent. Do not run MuJoCo,
models, image builds, or long evaluations on a login node.
`--resume-from` reuses only completed non-retryable cases whose complete locked
inputs match.

The migration validation order is Long++ (12), Ultra-Long (9), then PRO (80).
It is an ICL-only migration check. It validates protocol alignment, terminal
coverage, native scores, traces and media; without a newly run no-ICL arm it
must not be described as a causal ICL improvement.

## Outputs and acceptance

Keep downloaded/copied assets, generated inputs, caches and outputs outside the
checkout, for example below the sibling `../work/libero_three/` directory. Each
case contains:

- `result.json`: RoboRSI status, 1× native score and pinned provenance;
- `native/score.json`: 1× snapshot plus cumulative diagnostics;
- `native/episode.mp4`: streamed camera evidence when frames are available;
- `media/`: content-addressed observations returned to the Agent;
- `runner_trace/`: task/action/feedback envelopes;
- Agent trace and `agent-config.json`: selected model, package inputs and source
  fingerprint, without credential values.

Acceptance requires exactly 12, 9 and 80 planned subset cases, no missing
terminal record, no infrastructure/Agent error, readable native evidence and
the expected benchmark/source/config hashes. Score equality is useful evidence
but is not the sole gate because model services can be nondeterministic.

## Security and release rules

- Do not commit `work/`, credentials, model checkpoints, copied ICL packages,
  datasets, generated manifests tied to private registries, or result videos.
  The ICL/tokenizer copies are build inputs for the Agent image, not Git files.
- Keep all source pins and image digests immutable for a reported run.
- Treat reference evaluation directories as read-only inputs.
- A Benchmark service owns simulator files and native score; an Agent cannot
  write either result.
- Rebuild the image and regenerate its manifest after any adapter or scorer
  change. Source-digest verification rejects undeclared runtime files.

The published ms-sc-01 images below record the historical delivery. Their digests
stay unchanged. Rebuild images and manifests for current RoboRSI interfaces and
``/roborsi/`` mounts before running the current source.

| Role | Immutable image |
| --- | --- |
| Shared Agent | `registry.example.com/roborsi/ms-ccr/heart-libero-three-agent@sha256:33e4f5bd9947a208e83cbbbdc6b70297b0ebeb16893839ac2fb42fc627a1253e` |
| Long++ / Ultra-Long Benchmark | `registry.example.com/roborsi/ms-ccr/heart-libero-lilo@sha256:4e795cf962ff4680f88a757d4edba901440374e0c797246fc960221ba7822f81` |
| PRO Benchmark | `registry.example.com/roborsi/ms-ccr/heart-libero-pro@sha256:5fbf5694f17bd9500c1b495461e881464ecc29ebc26687d067b3c9a9a69606cf` |

All three were pulled back successfully by digest. Generated migration
manifests live outside Git at `../work/libero_three/registry-ms-ccr-v2/`; their
SHA-256 values are
`e63ffac8da2776fca25093acf344b9f7984f8ceb716089cb0c60832023ef5141`
(Long++),
`fd19a5c394d7556c22d2921744fd2e43541c7558821a3d42ab837f4d4f524fe8`
(Ultra-Long), and
`9ca4dcfd0641fff9fe63727f9e74dc817258b87bbe7929e87b0972ecb8f5149a`
(PRO).

The exact LiLo digest above was additionally run with a read-only root on the
local CPU software renderer. A Long++ no-op protocol probe reached its 600-step
1x boundary and produced native score, trace and video; this validates the
Benchmark execution path, not Agent task accuracy. Real-model scores are only
the results reported in the delivery-results section.

The locally verified unpacked sizes are about 4.85 GB for PRO, 3.98 GB for
LiLo, and 1.57 GB for the combined Agent image. The Agent's sealed ICL plus
tokenizer build input is about 49 MiB; most of its image size is the locked
Python/Agent CLI runtime. The current condition does not require Pi0.5 or SAM3,
so their historical checkpoints (about 10.9 GB raw in total) are deliberately
absent.

# Reproduce the three LIBERO evaluations

The pinned images below are historical delivery artifacts. Use their matching
source release to reproduce that delivery. Current RoboRSI requires rebuilt
images, new factories and ``/roborsi/`` mounts; follow the
[migration guide](source-en/rst_source/usage/roborsi_migration.rst) for a new run.

This guide runs the delivered LIBERO-PRO, Long++ and Ultra-Long evaluations on
a clean Linux host. Runtime assets formerly read from the m-cluster are sealed
in the images: the Benchmark images contain simulator, BDDL and init-state
assets; the shared Agent image contains the three ICL package families, locked
tokenizer and installed Agent bundles. Model weights and credentials are not in
the images.

## What you need

- Linux `x86_64`, Docker, Python 3.11 and enough disk for about 10.4 GB of
  unpacked images plus results.
- Access to `registry.example.com/roborsi/ms-ccr`.
- An OpenAI Responses-compatible endpoint that serves
  `gpt-6-astra`, plus its API key.
- This repository checkout at the PR revision. No AFS or m-cluster mount is
  required.

The Benchmark condition does not run a local VLA or SAM3 model. A GPU is not a
model dependency. The delivered manifests request one GPU for faster and more
consistent MuJoCo EGL rendering; CPU software rendering works but is much
slower and is intended only for small validation runs.

## Lock the images

```bash
export AGENT_IMAGE='registry.example.com/roborsi/ms-ccr/heart-libero-three-agent@sha256:33e4f5bd9947a208e83cbbbdc6b70297b0ebeb16893839ac2fb42fc627a1253e'
export LILO_IMAGE='registry.example.com/roborsi/ms-ccr/heart-libero-lilo@sha256:4e795cf962ff4680f88a757d4edba901440374e0c797246fc960221ba7822f81'
export PRO_IMAGE='registry.example.com/roborsi/ms-ccr/heart-libero-pro@sha256:5fbf5694f17bd9500c1b495461e881464ecc29ebc26687d067b3c9a9a69606cf'

docker pull "$AGENT_IMAGE"
docker pull "$LILO_IMAGE"
docker pull "$PRO_IMAGE"
```

## Single-image deployment

Schedulers that accept only one image per job can use the composition recipe
in [`benchmarks/libero_three_combined/`](../benchmarks/libero_three_combined/README.md).
Use the published immutable images directly:

```bash
export LONGPP_COMBINED_IMAGE='ghcr.io/opensensenova/sensenova-roborsi-libero-long-plus-plus@sha256:4463b6a247617a51653e1b170cc1cbcbae1a2c773a06f21afdf8626aea5a11c9'
export ULTRA_COMBINED_IMAGE='ghcr.io/opensensenova/sensenova-roborsi-libero-ultra-long@sha256:4463b6a247617a51653e1b170cc1cbcbae1a2c773a06f21afdf8626aea5a11c9'
export PRO_COMBINED_IMAGE='ghcr.io/opensensenova/sensenova-roborsi-libero-pro@sha256:fd84be8ca67100624dac4a3ddf0de06e74e46c5d1d1b7c8088e6e0713fe70e29'
```

Long++ and Ultra-Long have separate GHCR packages but share identical
LiLo+Agent image content; PRO uses a PRO+Agent image.
The image contains the Benchmark, Agent bundles, ICL and tokenizer. Runtime
inputs are limited to the model endpoint, a read-only API-key file and a
writable results directory. This mode has weaker isolation than the canonical
two-container deployment because the credential and Benchmark share a container.

Run the fixed subsets by overriding the entrypoint:

```bash
docker run --rm --gpus all \
  --entrypoint python \
  -v /path/to/model_api.key:/run/secrets/model_api.key:ro \
  -v "$RUN_ROOT/results:/results" "$LONGPP_COMBINED_IMAGE" \
  -B /opt/roborsi/benchmarks/libero_three_combined/run_combined_subset.py \
  --benchmark libero_long_plus_plus --run-id longpp-subset \
  --results-root /results/longpp-subset --max-concurrent 16 --gpu-count 1 \
  --api-key-file /run/secrets/model_api.key \
  --base-url https://your-responses-endpoint.example/v1
```

Long++ and Ultra-Long share `LILO_IMAGE`; select the service through the
manifest. PRO uses `PRO_IMAGE`. All three use the same `AGENT_IMAGE`, selecting
one installed bundle per evaluation.

## Install the Runner

From the repository root:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

Using a configured internal pip index is fine; it does not change the locked
container contents.

## Generate the local Benchmark registry

The manifests are generated by the exact Benchmark images so their runtime
identity, task list and image digest stay aligned.

```bash
export RUN_ROOT="$PWD/../work/libero-three-reproduction"
mkdir -p "$RUN_ROOT/registry/libero_long_plus_plus" \
  "$RUN_ROOT/registry/libero_ultra_long" \
  "$RUN_ROOT/registry/libero_pro" \
  "$RUN_ROOT/results"

docker run --rm --entrypoint python \
  -v "$RUN_ROOT/registry:/output" "$LILO_IMAGE" \
  -m benchmarks.libero_lilo.manifest \
  --image "$LILO_IMAGE" --benchmark libero_long_plus_plus \
  --profile migration_subset \
  --output /output/libero_long_plus_plus/manifest.json

docker run --rm --entrypoint python \
  -v "$RUN_ROOT/registry:/output" "$LILO_IMAGE" \
  -m benchmarks.libero_lilo.manifest \
  --image "$LILO_IMAGE" --benchmark libero_ultra_long \
  --profile migration_subset \
  --output /output/libero_ultra_long/manifest.json

docker run --rm --entrypoint python \
  -v "$RUN_ROOT/registry:/output" "$PRO_IMAGE" \
  -m benchmarks.libero_pro.manifest \
  --image "$PRO_IMAGE" --profile migration_subset \
  --output /output/libero_pro/manifest.json
```

Expected task counts are 12 Long++, 9 Ultra-Long and 80 PRO. Validate the
expanded plans before making model calls:

```bash
export OPENAI_API_KEY='replace-me'
export OPENAI_BASE_URL='https://your-responses-endpoint.example/v1'

python benchmarks/libero_three_combined/run.py \
  --benchmark libero_long_plus_plus \
  --registry-root "$RUN_ROOT/registry" \
  --agent-config bundle:libero_long_plus_plus_v13 \
  --agent-image "$AGENT_IMAGE" \
  --agent-credential-env OPENAI_API_KEY \
  --agent-credential-env OPENAI_BASE_URL \
  --results-root "$RUN_ROOT/results" --run-id longpp-plan --dry-run

python benchmarks/libero_three_combined/run.py \
  --benchmark libero_ultra_long \
  --registry-root "$RUN_ROOT/registry" \
  --agent-config bundle:libero_ultra_long_v13 \
  --agent-image "$AGENT_IMAGE" \
  --agent-credential-env OPENAI_API_KEY \
  --agent-credential-env OPENAI_BASE_URL \
  --results-root "$RUN_ROOT/results" --run-id ultra-plan --dry-run

python benchmarks/libero_three_combined/run.py \
  --benchmark libero_pro \
  --registry-root "$RUN_ROOT/registry" \
  --agent-config bundle:libero_pro \
  --agent-image "$AGENT_IMAGE" \
  --agent-credential-env OPENAI_API_KEY \
  --agent-credential-env OPENAI_BASE_URL \
  --results-root "$RUN_ROOT/results" --run-id pro-plan --dry-run
```

The key and endpoint are passed only to the isolated Agent container. They are
not added to the Benchmark containers, command arguments, manifests or result
records.

## Run a real-model sample

Start with one representative case. This is an actual Agent evaluation, not a
fixed-action or no-op simulator check.

```bash
bench eval \
  --registry-root "$RUN_ROOT/registry" \
  --results-root "$RUN_ROOT/results" --run-id longpp-one-case \
  --agent-config bundle:libero_long_plus_plus_v13 \
  --agent-image "$AGENT_IMAGE" \
  --agent-credential-env OPENAI_API_KEY \
  --agent-credential-env OPENAI_BASE_URL \
  --benchmark libero_long_plus_plus \
  --task libero_long_plus_plus:t00-i01 --seed 0 \
  --max-concurrent 1 --case-timeout-s 86400
```

For Ultra-Long use bundle `libero_ultra_long_v13`, benchmark
`libero_ultra_long` and task `libero_ultra_long:t00-i01`. For PRO use bundle
`libero_pro`, benchmark `libero_pro` and task
`libero_pro:libero_spatial_task-t00-i03`.

## Run each migration subset

Remove `--dry-run` from the three plan commands, choose a fresh run ID, and set
concurrency for the available simulator capacity. For example:

```bash
python benchmarks/libero_three_combined/run.py \
  --benchmark libero_long_plus_plus \
  --registry-root "$RUN_ROOT/registry" \
  --agent-config bundle:libero_long_plus_plus_v13 \
  --agent-image "$AGENT_IMAGE" \
  --agent-credential-env OPENAI_API_KEY \
  --agent-credential-env OPENAI_BASE_URL \
  --results-root "$RUN_ROOT/results" --run-id longpp-full \
  --max-concurrent 1 --case-timeout-s 86400
```

Repeat with the Ultra-Long and PRO benchmark/bundle pairs above. Do not enable
`plus9_on_failure` for the primary 1x score. Use `--resume-from OLD_RUN_ID` only
with a new run ID and unchanged locked inputs.

## Verify the outputs

Every completed case must contain `result.json`, `native/score.json`, native
video when frames are available, `runner_trace/`, media and the full Agent
trace. Only `success` and native `task_failure` are valid evaluation terminals;
infrastructure and Agent errors are not scores. The expected planned-case
counts are 12, 9 and 80.

The recorded real-model evidence and its exact limitations are in
[`README.md`](README.md). In particular, the
PRO 786/800 figure is a condition-aligned full-set reference, not a newly run
score for this repository's fixed-state-3 80-case subset.
