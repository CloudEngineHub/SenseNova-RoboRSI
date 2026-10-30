# RoboLab DROID, full-task 1x

[中文说明](README.zh-CN.md) · [Build](BUILD.md) · [Provenance](PROVENANCE.md)

This integration exposes 120 RoboLab manipulation tasks through the shared
RoboRSI Benchmark HTTP service. Each task retains its native instruction, seed-zero
initialization, 15 Hz control rate, 300–4500 control-frame budget, termination and
scoring. A chunked Cartesian action consumes physical control frames; it does not
multiply the native time budget. Observations contain DROID proprioception and two
320-pixel RGB views. Simulator ground truth is excluded.

Two explicitly different evaluation entries are provided:

| Entry | Agent and episode semantics | Reported result |
| --- | --- | --- |
| Standard RoboRSI | `EmbodiedAgent` → `CodexCliPlanner` → pinned `codex exec` / MCP; 120 independent seed-zero cases | Model performance has not been measured |
| Historical full-task 1x | Original app-server/goals policy and native runner; 120 tasks × 10 sequential runs in the recorded restart cohorts | Existing evidence: 685/1200 successes, **57.083333%**; mean native score **0.6804972351963321** |

The historical score is an audit of existing results, not a new standard-baseline
measurement. Re-execution preserves the recorded recipe and reset schedule; it
does not promise identical stochastic model responses or bitwise simulator replay.
See [provenance and limitations](PROVENANCE.md).

## Delivery status

Version `v0.1.2-isaac60` was published and pulled by digest on 2026-10-21:

```text
ghcr.io/opensensenova/sensenova-roborsi-robolab@sha256:519585576bb09c5fc4a09e6255e30d74189b86b0f8c526d3fe8d99c5031da04f
```

The pulled image matches the local build and passed dependency, source and runtime
identity checks. A 300-frame HTTP episode and direct native replay passed on
this exact image, including readable finalized HDF5 and owned-process cleanup.
These model-free checks cover one task and do not measure Agent performance.
The GHCR package is private; use an account with package
read access and locally configured credentials. Keep this registry digest as the
evaluation reference; a local Docker image ID is a different identity.

This branch includes the shared runtime exporter's `robolab` source registration
in `roborsi/benchmarks/runtime_source.py`. The published image was built from a
combined candidate containing the same registration.
Its recorded runtime source snapshot is `4cbb6378`, from the original integration.
See [BUILD.md](BUILD.md) for the distinction between this image and a new build
from the public checkout.

## Environments

Use Linux x86_64. Keep the Runner, standard Agent, historical Agent and native
simulator in separate environments. Commands below use a fresh external work
directory and this source checkout.

```bash
REPO="/absolute/path/to/RoboRSI"
WORK="/absolute/path/to/robolab-run"
REGISTRY="$WORK/registry"
mkdir -p "$WORK"
cd "$REPO"

uv venv --python "3.11" "$WORK/dev"
uv pip install --python "$WORK/dev/bin/python" -e . build
"$WORK/dev/bin/python" -m build --wheel --outdir "$WORK/core-dist" "$REPO"

uv venv --python "3.11" "$WORK/runner"
uv pip install --python "$WORK/runner/bin/python" \
  "$WORK"/core-dist/roborsi-*.whl \
  -r "$REPO/benchmarks/robolab/requirements-runner.lock.txt"
uv pip check --python "$WORK/runner/bin/python"
```

The Runner lock includes the complete standard core runtime lock and `h5py` for
checking completed native recordings before recovery. Its only local input is the separately built core wheel.
The [standard Agent](../../robots/robolab/agents/baseline/README.md) has a separate
wheel and executable lock. The [historical Agent](../../robots/robolab/agents/historical/README.md)
uses five pinned Python dependencies and the two original CLI versions.

## Assets and registry

The asset tree is external to both the repository and the image. Obtain it from
the pinned RoboLab Git LFS revision; retain the upstream asset licenses. Allow at
least 7 GB for assets and another copy for a new registry. The preparation command
checks all directory content, rejects links, and copies into a fresh destination.

```bash
UPSTREAM="$WORK/RoboLab-upstream"
GIT_LFS_SKIP_SMUDGE=1 git clone "https://github.com/DravenALG/RoboLab.git" "$UPSTREAM"
git -C "$UPSTREAM" checkout --detach "92ccc0ee1984a272d4748c92ed73144fa806a6f4"
git -C "$UPSTREAM" lfs pull --include="assets/**" --exclude=""

"$WORK/runner/bin/python" -m benchmarks.robolab.prepare \
  --source "$UPSTREAM/assets" --destination "$REGISTRY/robolab"
```

Expected tree: 2228 files, 6,141,046,362 file bytes, directory SHA-256
`718c6e372bab8f9eed3f096276f23ce03e6feb401e26456ebdb92c4d1959c62e`.
The registry stores the relative POSIX path `assets/robolab`; the container mount
is `/roborsi/assets/robolab`. Do not replace the copied tree with a symlink.

Use the published reference below, or the `reference` field of `image.json` for
your own published build. Generate the manifest using that image's own runtime
metadata:

```bash
IMAGE="ghcr.io/opensensenova/sensenova-roborsi-robolab@sha256:519585576bb09c5fc4a09e6255e30d74189b86b0f8c526d3fe8d99c5031da04f"
docker pull "$IMAGE"
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --read-only --tmpfs "/tmp:rw,nosuid,nodev,size=1g" \
  --mount "type=bind,src=$REGISTRY/robolab,dst=/registry" \
  --entrypoint python "$IMAGE" -P -m benchmarks.robolab.manifest \
  --image "$IMAGE" --asset "/registry/asset.json" --output "/registry/manifest.json"

"$WORK/runner/bin/python" - "$REGISTRY" <<'PY'
import sys
from roborsi.benchmarks.registry import BenchmarkRegistry
registry = BenchmarkRegistry([sys.argv[1]])
for name in registry.discover():
    locked = registry.lock(name)
    print(name, locked.image_reference)
    for identity in locked.list_tasks():
        task = locked.task_message(identity.task_id, identity.seed)
        print(task.task_id, task.seed, task.max_steps)
PY
```

The standard manifest lists 120 cases with seed 0. Historical run IDs 0–9 are
sequential reset positions, not independent seeds and not additional manifest cases.

## Standard HTTP execution

The measured native route requires a larger writable cache than the current
framework Docker executor's fixed 1 GiB `/tmp`. Start the same public service
explicitly with an 8 GiB tmpfs, then use the existing remote Benchmark option.
Reserve one RTX GPU per active environment, at least 8 CPU cores and 32 GB host
memory. Cold shader initialization can take several minutes; allow 900 seconds
for episode startup. The tested GPU was an RTX 4090 (24 GB).

```bash
docker run --rm --name "robolab-benchmark" \
  --gpus "device=0" --user "$(id -u):$(id -g)" \
  --read-only --tmpfs "/tmp:rw,nosuid,nodev,size=8g" --shm-size "2g" \
  --mount "type=bind,src=$REGISTRY/robolab/assets/robolab,dst=/roborsi/assets/robolab,readonly" \
  -p "127.0.0.1:8000:8000" "$IMAGE"
```

In another terminal, with the standard Agent wheel and pinned CLI installed as
described in its README, run from outside the checkout. Configure the provider
credentials locally before executing a paid model test. Endpoint overrides must
be explicit Agent settings; `OPENAI_BASE_URL` alone is not read by this preset.

```bash
cd "$WORK"
PATH="$CODEX_BIN_DIR:$PATH" "$WORK/agent/bin/bench" eval \
  --benchmark-url "robolab=http://127.0.0.1:8000" \
  --benchmark "robolab" --task "robolab:BowlStackingLeftOnRightTask" --seed 0 \
  --results-root "$WORK/results" --run-id "robolab-standard-001" \
  --max-concurrent 1 --timeout-s 900 --case-timeout-s 1200 \
  --agent-config "bundle:robolab_baseline" \
  --agent-set 'agent.planner_timeout_s=1200'
```

`codex_cli` requires `max_turns: null` and `max_tokens: null`; these are not
available model-cost caps. Native frame budgets, planner timeout and Runner case
timeout are distinct controls. The baseline targets `gpt-6-astra`, reasoning
effort `max`, at `https://api.openai.com/v1`. The second model attempt used that
same address with an explicit proxy environment and received a model response,
but the CLI rejected the simulation MCP action under approval policy
`never`. The case ended as `agent_error` without a canonical score. The framework
now accepts explicit per-tool approval of `roborsi_action` in MCP mode, and this
preset enables it while retaining global policy `never`. A new real-model run is
still needed for standard model acceptance. Record any alternate provider,
endpoint or budget as a different experiment configuration.

## Historical 120 × 10 reproduction

First follow the historical Agent installation instructions. Its CLI installer
produces `$WORK/codex/binaries.json`. The following command prints the exact
1200-run plan without starting containers or making model calls:

```bash
cd "$REPO"
"$WORK/runner/bin/python" -m benchmarks.robolab.reproduce \
  --image "$IMAGE" --assets "$REGISTRY/robolab/assets/robolab" \
  --codex-binaries "$WORK/codex/binaries.json" \
  --agent-python "$WORK/historical-agent/bin/python" \
  --output "$WORK/full-task-1x" --gpus "0,1,2,3"
```

Add `--execute` to start the paid experiment. `--shards 0 1` selects complete
shards; the default is all eight. GPU indices identify available host GPUs, not
native seeds. `--docker-host unix:///path/to/docker.sock` supports a separate
daemon. The launcher keeps model credentials on the Agent host and mounts only
assets, the native job and native outputs into the simulator container.

The original 24 completed worker processes are replayed in five ordered phases.
Tasks retain both resets per run, sequential RNG state and recorded restart
boundaries. `--resume` accepts only fully completed native processes, including a
crash between scoring and completion-marker publication. It rejects a partial
process because restarting it would change the RNG cohort. Use a fresh output
directory for a new attempt; do not edit completed rows to bypass this guard.

The saved plan and each Agent's `effective-config.json` contain the provider name,
wire API and SHA-256 of the exact selected base URL. `--resume` rejects a changed
endpoint or a legacy plan without that identity before starting any process.
The launcher pins the selected endpoint for all workers. URLs and API keys are
not written to those configuration records.

Recovery requires matching native logs and readable HDF5 final scores. A full
run must finish with all 1200 distinct task/run identities. Generated plans,
model logs, videos and HDF5 files remain outside this source repository.
