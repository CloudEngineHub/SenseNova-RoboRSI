# RoboCasa365 Target50

This recipe serves the RoboCasa365 Target50 protocol through RoboRSI's shared
Benchmark HTTP service. One RoboRSI action runs one RoboCasa tool
(`navigate_to`, `rldx_skill`, `view_env_state`, ...); the episode ends when the
Agent calls `finish` or the planner stops, and the native verdict is the
simulator's final `state.success`.

| Item | Value |
| --- | --- |
| Benchmark ID | `robocasa365` |
| Image | `ghcr.io/opensensenova/sensenova-roborsi-robocasa365@sha256:46464c117954398381edbb1c8dec10e78f3c586ff3f27c9f825209b07d096aef` (tag `v1.1.3-cu126`, linux/amd64, private GHCR package of the OpenSenseNova organization) |
| Simulator | `RLinf/robocasa@2692d8fc5fd86708a1b2028dcbce892ec418a9e7`, `RLinf/robosuite@97cfbde4b68d8ec43dad20cf4747297866a6ca2e`, mujoco 3.3.1 |
| VLA | RLDX-1 `RLWRLD/RLDX-1-FT-RC365@587e9ecdcc5e7184fcc17f58713908edff5af041`, served by the same image as a separate process |
| Cells | 340: 18 atomic tasks × seeds 1-10, 16 composite seen and 16 composite unseen tasks × seeds 1-5 (`robots/robocasa/eval/target50.json`) |
| Score | mean of the 50 per-task success rates (`task_weighted_success_rate`, cells without a valid result count as failures) |
| ICL package | `sensenova/SenseNova-RoboRSI-Packages`, `robocasa365/v1.0.0`, revision `57ce03cfbecae381c8f95022374127043ee3cf30` |
| Agent | `robots/robocasa/agent.yaml` (Native, `planner: api`) |

## One command

With Docker, the NVIDIA container toolkit, a RoboRSI checkout installed with
`pip install -e '.[runtime]'` and the ICL package downloaded (see below):

```bash
docker login ghcr.io
OPENAI_API_KEY=... benchmarks/robocasa365/run_eval.sh \
  --model gpt-6-astra --base-url https://your-endpoint/v1 \
  --cells seed1 --icl-root /abs/roborsi-packages/robocasa365/v1.0.0 \
  --results /abs/results --run-id gpt6_seed1 --gpu 0 --parallel 4
```

It starts one RLDX-1 service and `--parallel` Benchmark services from the
image, splits the cells over that many runners, stops the services afterwards
and prints the Target50 score. `--cells all` runs the 340 cells,
`--openai-format chat` uses Chat Completions. Score any set of runs again with
`python -m benchmarks.robocasa365.score RUN_DIR... --cells seed1`; cells
without a valid result are listed for a re-run.

## Services

A cell needs two services: the Benchmark service, which owns one kitchen per
episode, and an RLDX-1 service shared by all episodes. Both run from the image.

```bash
IMAGE=ghcr.io/opensensenova/sensenova-roborsi-robocasa365@sha256:46464c117954398381edbb1c8dec10e78f3c586ff3f27c9f825209b07d096aef
docker login ghcr.io   # an account in the OpenSenseNova organization

# RLDX-1 on one GPU (about 16 GB).
docker run -d --name rldx --gpus '"device=0"' --network host "$IMAGE" \
  python robots/robocasa/vla_server.py --model-path /opt/rldx/RLDX-1-FT-RC365 \
    --transport http --host 127.0.0.1 --port 18710

# Benchmark service. Kitchens render with OSMesa on the CPU.
docker run -d --name robocasa365 --network host \
  -e ROBORSI_ROBOCASA_VLA_ENDPOINT=http://127.0.0.1:18710 \
  "$IMAGE" python -m roborsi.evaluation.service_host --kind benchmark \
    --factory robots.robocasa.benchmark_service:make_robocasa365_benchmark \
    --host 127.0.0.1 --port 18800
```

Without `ROBORSI_ROBOCASA_VLA_ENDPOINT` the Benchmark service starts its own
RLDX-1 server from `RLDX_CHECKPOINT` (set in the image) on its first episode and
shares it with later ones; this is how a container started from the Registry
manifest runs, with the one GPU the manifest requests. Each episode's RLDX-1
session is closed when the episode ends.
`ROBORSI_ROBOCASA_CELLS=seed1` restricts the catalog to the 50 seed-1 cells.
Each episode starts its own `env_server` process; a kitchen takes 1-4 minutes
to load and an episode needs about 4 CPU cores and 8 GB of memory. The service
pins the Target50 RLDX limits (`RLDX_MAX_CHUNKS=40`, settle patience 999,
8 action steps per chunk) for every episode.

## Registry

```bash
python -m benchmarks.robocasa365.manifest --image "$IMAGE" \
  --output /path/to/registry/robocasa365/manifest.json
```

The manifest declares the image, the 340 cells, the action schema and the
scoring rule. Kitchen assets and RLDX-1 weights are inside the image, so the
asset list is empty.

## Agent and evaluation

Download the ICL package at the pinned revision:

```python
from huggingface_hub import snapshot_download

root = snapshot_download(
    repo_id="sensenova/SenseNova-RoboRSI-Packages",
    repo_type="dataset",
    revision="57ce03cfbecae381c8f95022374127043ee3cf30",
    allow_patterns=["robocasa365/v1.0.0/*", "scripts/verify_package.py"],
    local_dir="./roborsi-packages",
)
```

```bash
python roborsi-packages/scripts/verify_package.py \
  roborsi-packages/robocasa365/v1.0.0 \
  --manifest-sha256 88dfecd78fada13a6fc7aa2b13d1a7c61cb005451b72d53c0d3f25cc2f6a90bf

export OPENAI_API_KEY=...            # the model provider's key
export ROBORSI_ROBOCASA365_ICL_ROOT=$PWD/roborsi-packages/robocasa365/v1.0.0
bench eval \
  --benchmark-url robocasa365=http://127.0.0.1:18800 \
  --benchmark robocasa365 --task robocasa365:OpenDrawer --seed 1 \
  --results-root /path/to/results --run-id robocasa365_smoke \
  --agent-config robots/robocasa/agent.yaml \
  --agent-set 'runtime.llm.base_url="https://your-endpoint/v1"' \
  --max-concurrent 1 --timeout-s 1800 --case-timeout-s 4500
```

The baseline Agent is the Native planner with the settings of the reported
Target50 runs: `gpt-6-astra` through the Responses API, reasoning
effort `xhigh`, at most 100 model turns, 32768 output tokens per turn and the
two most recent image groups kept in context. Its factory loads the task's
seed-0 memory from the ICL package (checked against the package catalog) and
sets the planner wall clock to the split's Target50 limit, 1800 s for atomic
and 3600 s for composite cells. `parameters.memory: false` runs without memory.
Only the Native backend is delivered and validated for this benchmark.

## Validation

See [VALIDATION.md](VALIDATION.md).

## Environment

`requirements.txt` is the resolved Python environment of the image
(Python 3.10.21, torch 2.7.0+cu126, RoboCasa, robosuite and RLDX-1 at the
commits above). The Agent side needs only `roborsi[runtime]`.

## Building the image

See [BUILD.md](BUILD.md).
