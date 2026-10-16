# Evaluation examples

Run these examples from a source checkout after installing the package.
Prepare a benchmark using [Getting started](../../docs/getting-started.md) /
[快速开始](../../docs/getting-started.zh-CN.md).

## Fixed actions

`hold_agent.py` reads all camera files and returns a seven-value LIBERO action
that leaves the arm stationary and keeps the gripper open. It supports all four
LIBERO benchmark names in this release. It is an integration check, not a solver.

```bash
bench eval --registry-root /absolute/path/to/registry \
  --results-root /absolute/path/to/results --run-id hold-1 \
  --benchmark libero --task libero:0 --seed 0 \
  --agent-factory examples.roborsi.hold_agent:make_agent \
  --agent-version hold-example-v1 --timeout-s 180 --case-timeout-s 900
```

## Custom model context

`model_agent.py` uses the public `EmbodiedAgent` and context callback interfaces.
Set the model placeholder in `model_agent.yaml`, provide `OPENAI_API_KEY`, and
optionally set `OPENAI_BASE_URL` for a compatible custom service.

```bash
bench eval --registry-root /absolute/path/to/registry \
  --results-root /absolute/path/to/results --run-id model-factory-1 \
  --benchmark libero --task libero:0 --seed 0 \
  --agent-factory examples.roborsi.model_agent:make_agent \
  --agent-version model-example-v1 --timeout-s 180 --case-timeout-s 14400
```

The callback preserves complete tool exchanges and initial task images. It
reduces history when the previous request reports 12,000 input tokens, when
images exceed 48, or when feedback exceeds 32 turns; it then retains eight
feedback turns. The token threshold is a soft limit based on reported usage,
not a prediction of the next request's size. Provider cache support may vary.

For normal model selection and context settings, use the general
[`configs/agents/embodied`](../../configs/agents/embodied) presets instead of
editing Python. Both examples leave scoring and environment stopping to the
benchmark. Caller-declared version labels do not verify installed dependencies.
